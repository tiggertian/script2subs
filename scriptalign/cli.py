"""Command line entry point.

    scriptalign --audio narration.wav
    scriptalign --timings narration.json
    scriptalign ui
    scriptalign reflow --dry-run

The flat form (no subcommand) aligns scripts; `ui` and `reflow` are
convenience entry points for the desktop app and for re-breaking scripts.
"""

import argparse
import os
import subprocess
import sys

from . import __version__
from .errors import ScriptError
from .pipeline import Options, align_scripts, export_files, read_pair
from .tools import reflow as apply_reflow

EPILOG = """\
examples:
  # transcribe the narration with AutoSubs, then time the script to it
  scriptalign --audio narration.wav

  # reuse an existing AutoSubs JSON (or any SRT of the narration)
  scriptalign --timings narration.json

  # audio starting 1h into the timeline (Resolve TC 01:00:00:00)
  scriptalign --audio narration.wav --offset 3600

  # open the desktop app
  scriptalign ui

DaVinci Resolve:
  1. Media Pool -> Import Subtitle -> bilingual.srt
  2. Select it -> Insert Selected Subtitles to Timeline Using Timecode
  3. Timeline start timecode must be 00:00:00:00, or pass --offset
"""


def _add_timing_args(p):
    p.add_argument("--en", default="english.txt",
                   help="primary script (default: english.txt)")
    p.add_argument("--zh", default="chinese.txt",
                   help="second script (default: chinese.txt)")
    p.add_argument("--outdir", default=".", help="output folder (default: .)")
    p.add_argument("--offset", type=float, default=0.0,
                   help="seconds added to every cue")
    p.add_argument("--min-dur", type=float, default=0.8,
                   help="minimum cue duration")
    p.add_argument("--gap", type=float, default=0.0,
                   help="blank to leave between consecutive cues (0 = butt-joined, "
                        "avoids 1-frame flicker when rendered at 24 fps)")
    p.add_argument("--hold", type=float, default=1.0,
                   help="bridge pauses up to this many seconds (default: 1.0)")
    p.add_argument("--linger", type=float, default=0.4,
                   help="hold each cue this long past its last word (default: 0.4)")


def _add_reflow_args(p):
    p.add_argument("--max-chars", type=int, default=42,
                   help="target max characters per primary line")
    p.add_argument("--max-chars-secondary", type=int, default=20,
                   help="target max characters per second-language line")
    p.add_argument("--min-len", type=int, default=18,
                   help="minimum characters per primary line")


def build_parser():
    p = argparse.ArgumentParser(
        prog="scriptalign",
        description="Time hand-authored subtitle scripts to narration audio "
                    "using AutoSubs word timings.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--audio",
                     help="narration audio/video; transcribed with AutoSubs")
    src.add_argument("--timings",
                     help="AutoSubs .json or any .srt of the narration")

    _add_timing_args(p)
    _add_reflow_args(p)

    p.add_argument("--rebreak", action="store_true",
                   help="re-flow both scripts at phrase boundaries before timing "
                        "(text is never altered; .orig backups are written)")
    p.add_argument("--no-backup", action="store_true",
                   help="do not write .orig copies before --rebreak rewrites")

    p.add_argument("--json", help="transcript JSON path (default: alongside the audio)")
    p.add_argument("--model", default="large-v3-turbo",
                   help="AutoSubs model (default: large-v3-turbo)")
    p.add_argument("--lang", default="en", help="narration language (default: en)")
    p.add_argument("--force", action="store_true",
                   help="re-transcribe even if the JSON is up to date")
    p.add_argument("--no-forced-alignment", action="store_true",
                   help="skip AutoSubs' MMS word-level refinement")
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    return p


def ensure_transcript(args):
    """Return the path of a transcript JSON, running AutoSubs if needed."""
    audio = os.path.abspath(args.audio)
    if not os.path.exists(audio):
        raise ScriptError("Audio not found: %s" % audio)
    json_path = os.path.abspath(
        args.json or os.path.splitext(audio)[0] + ".json")

    if not args.force and os.path.exists(json_path) \
            and os.path.getmtime(json_path) >= os.path.getmtime(audio):
        print("reusing transcript %s" % json_path)
        return json_path

    cmd = ["autosubs", audio, "-m", args.model, "-f", "json", "-o", json_path]
    if args.lang:
        cmd += ["-l", args.lang]
    if not args.no_forced_alignment:
        cmd.append("--forced-alignment")
    print("transcribing with AutoSubs (%s)..." % args.model)
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        raise ScriptError(
            "autosubs not found on PATH; install AutoSubs "
            "(https://github.com/tmoroney/auto-subs) or pass --timings")
    except subprocess.CalledProcessError as exc:
        raise ScriptError("AutoSubs failed with exit code %d" % exc.returncode)

    if not os.path.exists(json_path):
        raise ScriptError("AutoSubs did not write %s" % json_path)
    return json_path


def _refowler(opts):
    return dict(max_primary=opts.max_primary,
                max_secondary=opts.max_secondary, min_len=opts.min_len)


def _print_reflow(data):
    before, after = data["before"], data["after"]
    print("reflowed %d -> %d cues | lines over %d chars: %d -> %d | "
          "dangling endings: %d -> %d"
          % (before["lines"], after["lines"], data["max_primary"],
             before["over_max"], after["over_max"],
             before["dangling"], after["dangling"]))


def align_main(argv):
    parser = build_parser()
    args = parser.parse_args(argv)
    opts = Options(offset=args.offset, min_dur=args.min_dur, gap=args.gap,
                   hold=args.hold, linger=args.linger,
                   max_primary=args.max_chars,
                   max_secondary=args.max_chars_secondary,
                   min_len=args.min_len)
    try:
        opts.validate()
        os.makedirs(args.outdir, exist_ok=True)
        if args.rebreak:
            _print_reflow(apply_reflow(
                args.en, args.zh, backup=not args.no_backup, **_refowler(opts)))

        primary, secondary = read_pair(args.en, args.zh)
        timings_path = args.timings if args.timings else ensure_transcript(args)
        result = align_scripts(primary, secondary, timings_path, opts)
        summary = result["summary"]
        print("tokens: script=%d transcript=%d matched=%d (%.1f%%)"
              % (summary["script_tokens"], summary["transcript_tokens"],
                 summary["matched"], summary["match_pct"]))
        for warning in summary["warnings"]:
            print("warning: " + warning["text"])
        paths = export_files(result, args.en, args.zh, args.outdir)
    except (ScriptError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1

    print("cues: %d  |  first %.2fs  last %.2fs  |  text held through %d short pauses"
          % (summary["cues"], summary["first"], summary["last"],
             summary["pauses_bridged"]))
    print("wrote %s -> %s" % (", ".join(os.path.basename(p) for p in paths),
                              os.path.abspath(args.outdir)))
    return 0


def reflow_main(argv):
    parser = argparse.ArgumentParser(
        prog="scriptalign reflow",
        description="Re-flow a 1:1 script pair at phrase boundaries. Text is "
                    "never changed; only line breaks move.")
    parser.add_argument("--en", default="english.txt", help="primary script")
    parser.add_argument("--zh", default="chinese.txt", help="second script")
    _add_reflow_args(parser)
    parser.add_argument("--dry-run", action="store_true",
                        help="print the summary without writing")
    parser.add_argument("--no-backup", action="store_true",
                        help="do not write .orig copies before rewriting")
    args = parser.parse_args(argv)
    try:
        if args.dry_run:
            from .tools import preview
            data = preview(args.en, args.zh, max_primary=args.max_chars,
                           max_secondary=args.max_chars_secondary,
                           min_len=args.min_len)
        else:
            data = apply_reflow(args.en, args.zh,
                                backup=not args.no_backup,
                                max_primary=args.max_chars,
                                max_secondary=args.max_chars_secondary,
                                min_len=args.min_len)
    except ScriptError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    _print_reflow(data)
    if args.dry_run:
        print("dry run: nothing written")
    else:
        print("rewrote %s and %s" % (args.en, args.zh))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("ui", "serve"):
        from .ui.app import main as ui_main
        return ui_main(argv[1:])
    if argv and argv[0] == "reflow":
        return reflow_main(argv[1:])
    if argv and argv[0] == "align":
        return align_main(argv[1:])
    return align_main(argv)


if __name__ == "__main__":
    sys.exit(main())
