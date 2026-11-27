"""Per-cue flags and run-level warnings shown in the UI and CLI."""

from .langs import FUNC_END, TRAILING_PUNCT, cps_limit, display_chars


def cue_flags(primary, secondary, dur, opts, primary_cjk, secondary_cjk):
    """Non-fatal problems a reviewer should look at for one cue."""
    flags = []

    if len(primary) > opts.max_primary:
        flags.append({"code": "over-limit", "track": "primary",
                      "label": "%d chars" % len(primary)})
    if secondary and len(secondary) > opts.max_secondary:
        flags.append({"code": "over-limit", "track": "secondary",
                      "label": "%d chars" % len(secondary)})

    if dur > 0:
        cps = display_chars(primary) / dur
        if cps > cps_limit(primary_cjk):
            flags.append({"code": "reading-speed", "track": "primary",
                          "label": "%.0f cps" % cps})

    if dur + 1e-6 < opts.min_dur:
        flags.append({"code": "too-short", "track": "primary",
                      "label": "%.2fs" % dur})

    if not primary_cjk:
        words = primary.split()
        if words:
            last = words[-1].rstrip(TRAILING_PUNCT).lower()
            if last in FUNC_END:
                flags.append({"code": "dangling", "track": "primary",
                              "label": "ends on “%s”" % last})
    return flags


def summarize(cues, summary, opts):
    """Attach counts and human-readable warnings to a pipeline summary."""
    counts = {}
    for cue in cues:
        for flag in cue["flags"]:
            counts[flag["code"]] = counts.get(flag["code"], 0) + 1

    fps = 24.0
    flicker = 0
    for cue in cues[:-1]:
        gap = cue.get("gap_after")
        if gap is not None and 0 < gap < 1.0 / fps:
            flicker += 1

    warnings = []
    if summary["match_pct"] < 85:
        warnings.append({
            "code": "low-match",
            "text": "Only %.1f%% of script words matched the transcript. Check "
                    "that the script and the narration are the same take."
                    % summary["match_pct"]})
    if flicker:
        warnings.append({
            "code": "flicker",
            "text": "%d cue gap(s) are shorter than one 24 fps frame; the text "
                    "may flicker. Use --gap 0 (the default) to butt-join cues."
                    % flicker})
    if counts.get("reading-speed"):
        warnings.append({
            "code": "reading-speed",
            "text": "%d cue(s) exceed the recommended reading speed (%d cps)."
                    % (counts["reading-speed"], cps_limit(summary["primary_cjk"]))})
    if counts.get("over-limit"):
        warnings.append({
            "code": "over-limit",
            "text": "%d cue(s) exceed their line length target."
                    % counts["over-limit"]})
    if summary["script_tokens"] - summary["matched"]:
        warnings.append({
            "code": "unmatched",
            "text": "%d script word(s) had no transcript match; their times "
                    "were interpolated." % (summary["script_tokens"] - summary["matched"])})
    return counts, flicker, warnings
