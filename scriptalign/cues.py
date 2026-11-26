"""Turn word timings into one cue per script line."""


def line_spans(token_times, line_of, n_lines):
    """First/last word time for each script line, gaps filled from neighbours."""
    starts = [float("inf")] * n_lines
    ends = [float("-inf")] * n_lines
    for si, (st, et) in enumerate(token_times):
        li = line_of[si]
        starts[li] = min(starts[li], st)
        ends[li] = max(ends[li], et)
    _fill_missing(starts, ends)
    return starts, ends


def _fill_missing(starts, ends):
    """A line with no matchable words inherits the span of the previous line."""
    last = None
    for i in range(len(starts)):
        if starts[i] == float("inf") or ends[i] == float("-inf"):
            if last is None:
                nxt = next((j for j in range(i + 1, len(starts))
                            if starts[j] != float("inf")), None)
                if nxt is None:
                    starts[i], ends[i] = 0.0, 0.0
                else:
                    starts[i], ends[i] = starts[nxt], starts[nxt]
            else:
                starts[i], ends[i] = last, last
        else:
            last = ends[i]


def make_cues(lines, starts, ends, offset=0.0, min_dur=0.8, gap=0.0,
              hold=1.0, linger=0.4):
    """Cue timings in order.

    A cue's natural span is its first-to-last spoken word, which leaves a blank
    at every breath. `hold` bridges silences up to that many seconds so the
    text stays on screen continuously; longer pauses keep a real gap, shortened
    by `linger` past the last word.
    """
    cues = []
    prev_end = None
    for li, text in enumerate(lines):
        st = starts[li] + offset
        et = ends[li] + offset
        if et - st < min_dur:
            et = st + min_dur
        if prev_end is not None and st < prev_end + gap:
            st = prev_end + gap
            if et < st + min_dur:
                et = st + min_dur
        cues.append((st, et, text))
        prev_end = et

    for i in range(len(cues) - 1):
        st, et, text = cues[i]
        nxt = cues[i + 1][0]
        silence = nxt - et
        if silence <= 0:
            continue
        if silence <= hold:
            cues[i] = (st, nxt - gap, text)
        else:
            cues[i] = (st, min(et + linger, nxt - gap), text)
    return cues
