"""SRT and CSV writers."""

import csv


def srt_time(t):
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def write_srt(path, cues, second=None):
    """Write cues; `second` adds a translation line under each cue."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for idx, (start, end, text) in enumerate(cues, 1):
            body = text if second is None else text + "\n" + second[idx - 1]
            f.write("%d\n%s --> %s\n%s\n\n"
                    % (idx, srt_time(start), srt_time(end), body))


def write_report(path, cues, second=None):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["line", "start", "end", "dur", "text", "translation"])
        for li, (st, et, text) in enumerate(cues, 1):
            w.writerow([li, srt_time(st), srt_time(et), "%.2f" % (et - st),
                        text, second[li - 1] if second else ""])
