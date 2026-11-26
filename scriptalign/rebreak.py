"""Re-flow a paired subtitle script so cues end on phrases, not mid-clause.

The two scripts are already aligned line-for-line, so their existing line
boundaries are used as correspondence anchors: every anchor gives a known
(primary character offset -> secondary character offset) pair. The primary
script is then re-segmented on its own at phrase boundaries, and each new
break is mapped back through those anchors to the secondary script and snapped
to the nearest punctuation mark. Both files therefore get the same number of
lines without either text changing.

Either script may be space-delimited or CJK; each script picks its own joiner,
break points and snapping rules.
"""

import re

from .langs import (CJK_CLAUSE_END, CJK_PHRASE_START, CJK_SENT_END,
                    CJK_SOFT_END, FUNC_END, is_cjk_script, joiner)

EN_CLOSE = ".,;:!?—\"”)…"
CJK_CLOSE = "，。；：、！？…—）」』】"


def _anchors(lines, sep):
    """Character offset at the start of each line in the joined text."""
    offsets, pos = [], 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + len(sep)
    return offsets, pos - len(sep)


def _map_position(pos, src_anchors, dst_anchors, dst_len):
    """Piecewise-linear primary->secondary character mapping."""
    for k in range(len(src_anchors) - 1):
        a, b = src_anchors[k], src_anchors[k + 1]
        if a <= pos <= b:
            t = (pos - a) / (b - a) if b > a else 0.0
            return dst_anchors[k] + t * (dst_anchors[k + 1] - dst_anchors[k])
    return float(dst_len)


def _spaced_primary_ends(text, max_len, min_len):
    """End offsets of primary lines for a space-delimited script."""
    words = text.split()
    lens = [len(w) for w in words]
    n = len(words)
    # a numbered heading ("1.") must open a cue and keep its title with it
    heads = [i for i, w in enumerate(words) if w.rstrip() in
             ("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")]
    head_set = set(heads)
    cuts = []
    i = 0
    while i < n:
        nxt = next((h for h in heads if h > i), None)
        cap = max_len + 8 if i in head_set else max_len
        cur = 0
        j = i
        best, best_score = None, None
        while j < n:
            cur += lens[j] + (1 if j > i else 0)
            if cur > cap and j > i:
                break
            j += 1
            if nxt is not None and j > nxt:
                break
            if j - 1 in heads:
                continue  # never end a cue on the heading number itself
            tail = words[j - 1].rstrip()
            last = tail.strip(".,;:!?—\"”()").lower()
            score = -abs(cur - max_len * 0.85) * 0.35
            if tail.endswith(tuple(".!?")):
                score += 14
            elif tail.endswith((",", ";", ":", "—", "\"", "”", ")")):
                score += 8
            if last in FUNC_END:
                score -= 9
            if j < n and words[j].strip(".,;:!?—\"”()").lower() in FUNC_END:
                score -= 1
            if cur < min_len:
                score -= (min_len - cur) * 1.2
            if best_score is None or score > best_score:
                best, best_score = j, score
        if best is None:
            best = nxt if nxt is not None and nxt > i else i + 1
        cuts.append(sum(lens[i:best]) + (best - i - 1))
        i = best
    # cumulative absolute offsets (separator is one space)
    out, off = [], 0
    for c in cuts:
        off += c
        out.append(off)
        off += 1
    return out


def _cjk_primary_ends(text, max_len, min_len):
    """End offsets of primary lines for a CJK script (no word spaces)."""
    n = len(text)
    out = []
    i = 0
    while i < n:
        while i < n and text[i] == " ":
            i += 1
        if i >= n:
            break
        limit = min(n, i + max_len + 6)

        strong = None
        for j in range(min(n, i + min_len), limit + 1):
            if text[j - 1] in CJK_SENT_END:
                strong = j
                break
        if strong is not None:
            best = strong
        else:
            clauses = [j for j in range(min(n, i + min_len), limit + 1)
                       if text[j - 1] in CJK_CLAUSE_END]
            if clauses:
                best = clauses[-1]
            else:
                j = min(n, i + max_len)
                # do not cut a Latin word or number in half
                while j > i + 1 and text[j - 1].isascii() and text[j - 1].isalnum() \
                        and j < n and text[j].isascii() and text[j].isalnum():
                    j -= 1
                best = j
        out.append(best)
        i = best
    return out


def _secondary_cuts_cjk(text, targets, max_zh=20, min_zh=4):
    """Cut a CJK secondary script near each mapped target, preferring punctuation.

    A greedy snap drifts: once a cue overshoots, the next one cannot move back
    and the whole script slides. This is a small monotonic DP instead, so each
    cut stays as close to its target as the punctuation allows.
    """
    n = len(text)
    punct = set(i + 1 for i, ch in enumerate(text) if ch in CJK_CLOSE)
    n_cuts = len(targets)

    def boundary_cost(p):
        if p in punct:
            return 0.0
        if p + 1 < n and text[p] in "12345" and text[p + 1] == ".":
            return 0.0  # start a cue on a numbered heading
        cost = 8.0
        if p > 0 and text[p - 1] in CJK_SOFT_END:
            cost = 3.0
        if text[p:p + 2] in CJK_PHRASE_START:
            cost = min(cost, 2.0)
        return cost

    def candidates(k):
        if k == n_cuts - 1:
            return [n]
        t = int(round(targets[k]))
        lo, hi = max(min_zh, t - 20), min(n - 1, t + 20)
        return list(range(lo, hi + 1))

    positions, costs, parents = [0], [0.0], [-1]
    history = []
    for k in range(n_cuts):
        history.append((positions, parents))
        new_pos, new_cost, new_par = [], [], []
        for p in candidates(k):
            best, best_i = None, None
            for qi, q in enumerate(positions):
                gap = p - q
                if gap < min_zh:
                    continue
                cost = costs[qi] + abs(p - targets[k]) + boundary_cost(p)
                if gap > max_zh:
                    cost += (gap - max_zh) * 1.5
                if best is None or cost < best:
                    best, best_i = cost, qi
            if best is not None:
                new_pos.append(p)
                new_cost.append(best)
                new_par.append(best_i)
        if not new_pos:
            last = max(positions)
            p = min(n, max(last + min_zh, int(round(targets[k]))))
            new_pos, new_cost = [p], [min(costs) + abs(p - targets[k])]
            new_par = [costs.index(min(costs))]
        positions, costs, parents = new_pos, new_cost, new_par

    cuts = []
    i = min(range(len(costs)), key=costs.__getitem__)
    for k in range(n_cuts - 1, -1, -1):
        cuts.append(positions[i])
        prev_i = parents[i]
        positions, parents = history[k]
        i = prev_i
    cuts.reverse()
    cuts[-1] = n
    return cuts


def _secondary_cuts_words(text, targets, max_len=42, min_len=12):
    """Cut a space-delimited secondary script at word boundaries near targets.

    Same monotonic DP shape as the CJK cutter, but candidate break points are
    the starts of words (after whitespace) rather than every character.
    """
    n = len(text)
    starts = [m.start() for m in re.finditer(r"\S+", text)][1:]
    bounds = sorted(set(starts + [n]))
    n_cuts = len(targets)
    punct = set(EN_CLOSE)

    def boundary_cost(p):
        if p >= n:
            return 0.0
        if p > 0 and text[p - 1] in punct:
            return 0.0
        return 2.0

    def candidates(k, prev):
        if k == n_cuts - 1:
            return [n]
        t = targets[k]
        lo, hi = max(prev + 1, int(t - max_len)), int(t + max_len)
        near = [p for p in bounds if lo <= p <= hi]
        if near:
            return near
        after = [p for p in bounds if p >= prev + 1]
        return after[:1] or [n]

    positions, costs, parents = [0], [0.0], [-1]
    history = []
    for k in range(n_cuts):
        history.append((positions, parents))
        new_pos, new_cost, new_par = [], [], []
        for qi, q in enumerate(positions):
            for p in candidates(k, q):
                gap = p - q
                cost = costs[qi] + abs(p - targets[k]) + boundary_cost(p)
                if gap < min_len:
                    cost += (min_len - gap) * 2.0
                if gap > max_len:
                    cost += (gap - max_len) * 1.5
                new_pos.append(p)
                new_cost.append(cost)
                new_par.append(qi)
        if not new_pos:
            p = n
            new_pos, new_cost = [p], [min(costs) + abs(p - targets[k])]
            new_par = [costs.index(min(costs))]
        positions, costs, parents = new_pos, new_cost, new_par

    cuts = []
    i = min(range(len(costs)), key=costs.__getitem__)
    for k in range(n_cuts - 1, -1, -1):
        cuts.append(positions[i])
        prev_i = parents[i]
        positions, parents = history[k]
        i = prev_i
    cuts.reverse()
    cuts[-1] = n
    return cuts


def _absorb_orphans(lines, min_len, limit=46, sep=" "):
    """Pull a stub line back into the previous cue when it fits."""
    out = []
    for line in lines:
        if out and len(line) < min_len and len(out[-1]) + len(sep) + len(line) <= limit:
            out[-1] = out[-1] + sep + line
        else:
            out.append(line)
    return out


def rebreak(primary, secondary, max_primary=42, max_secondary=20, min_len=18):
    """Return (primary, secondary) line lists with phrase-aware breaks."""
    psep = joiner(primary)
    ssep = joiner(secondary)
    src = psep.join(primary)
    dst = ssep.join(secondary)
    sa, _ = _anchors(primary, psep)
    da, _ = _anchors(secondary, ssep)

    if is_cjk_script(primary):
        raw_ends = _cjk_primary_ends(src, max_primary, min_len)
    else:
        raw_ends = _spaced_primary_ends(src, max_primary, min_len)

    new_primary, pos = [], 0
    for e in raw_ends:
        line = src[pos:e]
        new_primary.append(line if psep else line.strip())
        pos = e + len(psep)
    new_primary = _absorb_orphans(new_primary, min_len, sep=psep)

    ends, pos = [], 0
    for line in new_primary:
        pos += len(line)
        ends.append(pos)
        pos += len(psep)

    targets = [_map_position(e, sa, da, len(dst)) for e in ends]
    if is_cjk_script(secondary):
        cuts = _secondary_cuts_cjk(dst, targets, max_zh=max_secondary)
    else:
        cuts = _secondary_cuts_words(dst, targets, max_len=max_secondary)

    new_secondary, pos = [], 0
    for c in cuts:
        new_secondary.append(dst[pos:c].strip())
        pos = c
    return new_primary, new_secondary


def report(lines, max_len=42):
    long_ = sum(1 for l in lines if len(l) > max_len)
    cjk = is_cjk_script(lines)
    func = 0
    if not cjk:
        for l in lines:
            w = l.split()
            if w and w[-1].strip(".,;:!?—\"”()").lower() in FUNC_END:
                func += 1
    else:
        for l in lines:
            if l and l[0:2] in CJK_PHRASE_START:
                func += 1
    lens = [len(l) for l in lines]
    return {"lines": len(lines), "over_max": long_, "dangling": func,
            "avg": sum(lens) / max(len(lens), 1), "max": max(lens),
            "cjk": cjk}
