"""The alignment pipeline, shared by the CLI and the desktop UI.

AutoSubs does the listening: it transcribes the narration and refines the
result to word-level timings (its JSON output, usually with
``--forced-alignment``). This module does the aligning: it matches the
hand-authored script against those timings, fills in paraphrased words, turns
one cue per script line, and reports where a reviewer should look.
"""

import os
from dataclasses import asdict, dataclass

from .align import align, interpolate
from .cues import line_spans, make_cues
from .diagnostics import cue_flags, summarize
from .errors import ScriptError
from .langs import display_chars, is_cjk_script
from .srt import write_report, write_srt
from .text import read_lines, tokenize
from .timings import build_transcript_tokens, load


@dataclass
class Options:
    """Timing and readability knobs shared by align and reflow."""

    offset: float = 0.0
    min_dur: float = 0.8
    gap: float = 0.0
    hold: float = 1.0
    linger: float = 0.4
    max_primary: int = 42
    max_secondary: int = 20
    min_len: int = 18

    @classmethod
    def from_dict(cls, data):
        out = cls()
        for key, value in (data or {}).items():
            if hasattr(out, key) and value is not None:
                setattr(out, key, value)
        out.validate()
        return out

    def validate(self):
        checks = {
            "offset": (0.0, 86400.0), "min_dur": (0.0, 10.0),
            "gap": (0.0, 5.0), "hold": (0.0, 10.0), "linger": (0.0, 10.0),
            "max_primary": (8, 120), "max_secondary": (8, 120),
            "min_len": (0, 100),
        }
        for name, (lo, hi) in checks.items():
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValueError("%s must be a number" % name)
            if not lo <= value <= hi:
                raise ValueError("%s must be between %s and %s" % (name, lo, hi))


def read_pair(primary_path, secondary_path):
    """Read two scripts and enforce the line-for-line contract."""
    for path in (primary_path, secondary_path):
        if not os.path.isfile(path):
            raise ScriptError("Script not found: %s" % path)
    primary = read_lines(primary_path)
    secondary = read_lines(secondary_path)
    if not primary:
        raise ScriptError("Primary script is empty: %s" % primary_path)
    if len(primary) != len(secondary):
        raise ScriptError(
            "Line count mismatch: %s has %d lines, %s has %d. They must be a "
            "1:1 pair." % (os.path.basename(primary_path), len(primary),
                           os.path.basename(secondary_path), len(secondary)))
    return primary, secondary


def align_scripts(primary, secondary, timings_path, opts):
    """Time `primary` and `secondary` against AutoSubs timings.

    Returns a JSON-safe dict with per-cue rows, run statistics and warnings.
    Raises ScriptError for problems the user can fix.
    """
    if not os.path.isfile(timings_path):
        raise ScriptError("Timings not found: %s" % timings_path)

    units, kind = load(timings_path)
    transcript = build_transcript_tokens(units)
    if not transcript:
        raise ScriptError("No words found in %s" % timings_path)

    tokens, line_of = [], []
    for li, line in enumerate(primary):
        for tok in tokenize(line):
            tokens.append(tok)
            line_of.append(li)
    if not tokens:
        raise ScriptError("Primary script has no words")

    mapping = align(tokens, [t for t, _, _ in transcript])
    if not mapping:
        raise ScriptError(
            "No script word matched the transcript. Is this the right script "
            "for this audio?")

    times = [None] * len(tokens)
    for si, tj in mapping.items():
        _, start, end = transcript[tj]
        times[si] = (start, end)
    times = interpolate(times, transcript[0][1], transcript[-1][2])

    starts, ends = line_spans(times, line_of, len(primary))
    cues = make_cues(primary, starts, ends, offset=opts.offset,
                     min_dur=opts.min_dur, gap=opts.gap,
                     hold=opts.hold, linger=opts.linger)

    primary_cjk = is_cjk_script(primary)
    secondary_cjk = is_cjk_script(secondary)
    rows = []
    for i, (start, end, text) in enumerate(cues):
        dur = end - start
        gap_after = cues[i + 1][0] - end if i + 1 < len(cues) else None
        flags = cue_flags(text, secondary[i], dur, opts,
                          primary_cjk, secondary_cjk)
        rows.append({
            "n": i + 1,
            "start": round(start, 3),
            "end": round(end, 3),
            "dur": round(dur, 3),
            "primary": text,
            "secondary": secondary[i],
            "cps": round(display_chars(text) / dur, 1) if dur > 0 else None,
            "gap_after": round(gap_after, 3) if gap_after is not None else None,
            "flags": flags,
        })

    pauses = sum(1 for i in range(1, len(cues))
                 if cues[i][0] - cues[i - 1][1] <= opts.gap * 2)
    summary = {
        "cues": len(cues),
        "first": round(cues[0][0], 3),
        "last": round(cues[-1][1], 3),
        "script_tokens": len(tokens),
        "transcript_tokens": len(transcript),
        "matched": len(mapping),
        "match_pct": round(100.0 * len(mapping) / len(tokens), 1),
        "transcript_kind": kind,
        "pauses_bridged": pauses,
        "primary_cjk": primary_cjk,
        "secondary_cjk": secondary_cjk,
    }
    counts, flicker, warnings = summarize(rows, summary, opts)
    summary["counts"] = counts
    summary["flicker_risks"] = flicker
    summary["warnings"] = warnings

    return {
        "cues": rows,
        "summary": summary,
        "options": asdict(opts),
        "timings_path": timings_path,
        "primary_path": None,
        "secondary_path": None,
    }


def export_files(result, primary_path, secondary_path, outdir):
    """Write primary, secondary, bilingual SRTs and the timing report."""
    if not result or not result.get("cues"):
        raise ScriptError("Run the alignment before exporting.")
    os.makedirs(outdir, exist_ok=True)

    primary = read_lines(primary_path)
    secondary = read_lines(secondary_path)
    if len(primary) != len(secondary):
        raise ScriptError("Scripts are no longer a 1:1 pair; re-check them.")

    cues = [(c["start"], c["end"], c["primary"]) for c in result["cues"]]
    if len(cues) != len(primary):
        raise ScriptError(
            "The alignment used a different script version. Re-run alignment.")

    primary_out = os.path.join(
        outdir, os.path.splitext(os.path.basename(primary_path))[0] + ".srt")
    secondary_out = os.path.join(
        outdir, os.path.splitext(os.path.basename(secondary_path))[0] + ".srt")
    bilingual_out = os.path.join(outdir, "bilingual.srt")
    report_out = os.path.join(outdir, "timing_report.csv")

    write_srt(primary_out, cues)
    write_srt(secondary_out, [(st, et, secondary[i])
                              for i, (st, et, _) in enumerate(cues)])
    write_srt(bilingual_out, cues, second=secondary)
    write_report(report_out, cues, secondary)
    return [primary_out, secondary_out, bilingual_out, report_out]
