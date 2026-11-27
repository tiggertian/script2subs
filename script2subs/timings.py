"""Read narration timings from AutoSubs JSON or from any SRT.

Both loaders return (units, kind) where units are (start, end, text) tuples and
kind is "word" or "segment". build_transcript_tokens() then spreads a unit's
time span across its words so everything downstream works in word time.
"""

import json
import re

from .text import tokenize

SRT_TIME = re.compile(r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})")


def _hms(s):
    m = SRT_TIME.search(s)
    if not m:
        return None
    h, mi, se, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")[:3]) / 1000.0


def parse_srt(path):
    with open(path, encoding="utf-8-sig") as f:
        text = f.read().replace("\r\n", "\n").replace("\r", "\n")
    units = []
    for block in re.split(r"\n\s*\n", text.strip()):
        ls = [l for l in block.split("\n") if l.strip()]
        ti = next((i for i, l in enumerate(ls) if "-->" in l), None)
        if ti is None:
            continue
        left, right = ls[ti].split("-->", 1)
        start, end = _hms(left), _hms(right)
        body = " ".join(ls[ti + 1:]).strip()
        if start is not None and end is not None and body:
            units.append((start, end, body))
    return units, "segment"


def _num(v):
    return float(v) if isinstance(v, (int, float)) else None


def _preferred_branch(data):
    """AutoSubs writes both refined `segments` and raw `originalSegments`.

    Walking both would duplicate every word at two different timings, so only
    one branch is used. Anything else is walked whole.
    """
    if isinstance(data, dict):
        for key in ("segments", "originalSegments"):
            if isinstance(data.get(key), list) and data[key]:
                return data[key]
    return data


def parse_json(path):
    with open(path, encoding="utf-8-sig") as f:
        data = json.load(f)

    words, segs = [], []

    def walk(o):
        if isinstance(o, dict):
            low = {k.lower(): v for k, v in o.items()}
            s = _num(low.get("start", low.get("start_time", low.get("starttime"))))
            e = _num(low.get("end", low.get("end_time", low.get("endtime"))))
            if s is not None and e is not None:
                w = low.get("word", low.get("token"))
                t = low.get("text")
                if isinstance(w, str) and w.strip():
                    words.append((s, e, w.strip()))
                elif isinstance(t, str) and t.strip():
                    segs.append((s, e, t.strip()))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(_preferred_branch(data))
    words.sort(key=lambda u: (u[0], u[1]))
    segs.sort(key=lambda u: (u[0], u[1]))

    # drop exact duplicate units that nested structures may repeat
    def dedupe(units):
        out, last = [], None
        for u in units:
            if u != last:
                out.append(u)
            last = u
        return out

    if words:
        return dedupe(words), "word"
    if segs:
        return dedupe(segs), "segment"
    raise SystemExit("No timings found in %s" % path)


def load(path):
    """Timings from .json (AutoSubs) or .srt."""
    if path.lower().endswith(".json"):
        return parse_json(path)
    return parse_srt(path)


def build_transcript_tokens(units):
    """(token, start, end) for the whole transcript, one per word."""
    tokens = []
    for s, e, text in units:
        parts = tokenize(text)
        if not parts:
            continue
        step = max(e - s, 0.04) / len(parts)
        for i, p in enumerate(parts):
            tokens.append((p, s + i * step, s + (i + 1) * step))
    return tokens
