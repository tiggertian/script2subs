"""Sequence alignment of script words against transcript words."""

MATCH, MISS, GAP = 3, -1, -1


def align(a, b):
    """Global Needleman-Wunsch alignment; returns {script_index: transcript_index}.

    Only exact token matches are recorded, so a paraphrased or misheard word
    leaves its script word unmapped and interpolate() fills it in later.
    """
    n, m = len(a), len(b)
    prev = [j * GAP for j in range(m + 1)]
    dirs = [bytearray(m + 1) for _ in range(n + 1)]
    for j in range(1, m + 1):
        dirs[0][j] = 2  # left
    for i in range(1, n + 1):
        cur = [0] * (m + 1)
        cur[0] = i * GAP
        dirs[i][0] = 1  # up
        ai = a[i - 1]
        for j in range(1, m + 1):
            best, d = prev[j - 1] + (MATCH if ai == b[j - 1] else MISS), 0
            up = prev[j] + GAP
            left = cur[j - 1] + GAP
            if up > best:
                best, d = up, 1
            if left > best:
                best, d = left, 2
            cur[j] = best
            dirs[i][j] = d
        prev = cur

    mapping = {}
    i, j = n, m
    while i > 0 or j > 0:
        d = dirs[i][j] if (i > 0 and j > 0) else (1 if i > 0 else 2)
        if i > 0 and j > 0 and d == 0:
            if a[i - 1] == b[j - 1]:
                mapping[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif i > 0 and (j == 0 or d == 1):
            i -= 1
        else:
            j -= 1
    return mapping


def interpolate(times, total_start, total_end):
    """Fill None entries: linearly between known neighbours, evenly if none."""
    n = len(times)
    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        step = (total_end - total_start) / max(n, 1)
        return [(total_start + i * step, total_start + (i + 1) * step) for i in range(n)]
    if known[0] > 0:
        t = times[known[0]][0]
        for i in range(known[0]):
            times[i] = (t, t)
    if known[-1] < n - 1:
        t = times[known[-1]][1]
        for i in range(known[-1] + 1, n):
            times[i] = (t, t)
    for k in range(len(known) - 1):
        i1, i2 = known[k], known[k + 1]
        if i2 - i1 <= 1:
            continue
        t1, t2 = times[i1][1], times[i2][0]
        for off, i in enumerate(range(i1 + 1, i2), 1):
            t = t1 + (t2 - t1) * off / (i2 - i1)
            times[i] = (t, t)
    return times
