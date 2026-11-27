"""Script maintenance commands: preview a reflow, apply it, snapshot it."""

import os
import re
import shutil

from .errors import ScriptError
from .rebreak import rebreak, report
from .text import read_lines


def _norm(text):
    """Text with any whitespace removed, for verbatim comparison."""
    return re.sub(r"\s+", "", text)


def _pair(primary_path, secondary_path):
    for path in (primary_path, secondary_path):
        if not os.path.isfile(path):
            raise ScriptError("Script not found: %s" % path)
    primary = read_lines(primary_path)
    secondary = read_lines(secondary_path)
    if len(primary) != len(secondary):
        raise ScriptError(
            "Line count mismatch: %s has %d lines, %s has %d. They must be a "
            "1:1 pair." % (os.path.basename(primary_path), len(primary),
                           os.path.basename(secondary_path), len(secondary)))
    if not primary:
        raise ScriptError("Primary script is empty")
    return primary, secondary


def preview(primary_path, secondary_path, max_primary=42, max_secondary=20,
            min_len=18):
    """Compute a reflow without writing anything.

    The returned `primary`/`secondary` pairs let a UI show the old and new
    breaks side by side. Raises ScriptError if reflowing would alter any text.
    """
    primary, secondary = _pair(primary_path, secondary_path)
    new_primary, new_secondary = rebreak(
        primary, secondary, max_primary=max_primary,
        max_secondary=max_secondary, min_len=min_len)

    if _norm("".join(primary)) != _norm("".join(new_primary)) or \
            _norm("".join(secondary)) != _norm("".join(new_secondary)):
        raise ScriptError(
            "Refusing to reflow: the new breaks would change the text. Nothing "
            "was written.")

    return {
        "before": report(primary, max_primary),
        "after": report(new_primary, max_primary),
        "secondary_before": report(secondary, max_secondary),
        "secondary_after": report(new_secondary, max_secondary),
        "primary": {"before": primary, "after": new_primary},
        "secondary": {"before": secondary, "after": new_secondary},
        "changed": primary != new_primary or secondary != new_secondary,
        "max_primary": max_primary,
        "max_secondary": max_secondary,
        "min_len": min_len,
    }


def reflow(primary_path, secondary_path, backup=True, **kwargs):
    """Re-break the paired scripts in place; return the preview that was applied."""
    data = preview(primary_path, secondary_path, **kwargs)

    if backup:
        for path in (primary_path, secondary_path):
            stem, ext = os.path.splitext(path)
            keep = stem + ".orig" + ext
            if not os.path.exists(keep):  # never clobber the true original
                shutil.copy2(path, keep)

    with open(primary_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(data["primary"]["after"]) + "\n")
    with open(secondary_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(data["secondary"]["after"]) + "\n")
    return data
