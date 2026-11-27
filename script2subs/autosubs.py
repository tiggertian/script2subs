"""Locate the AutoSubs CLI, including one embedded in the macOS app bundle.

AutoSubs is an external MIT project; nothing here imports it. We only find the
``autosubs`` executable to run headlessly. When Script2Subs is packaged as a
macOS app, an ``AutoSubs.app`` copied into ``Contents/Resources`` is used
automatically (see packaging/build_app.sh, BUNDLE_AUTOSUBS=1).
"""

import os
import shutil
import sys

_BIN = "autosubs"


def _embedded_candidates():
    # Frozen layout: .../Script2Subs.app/Contents/MacOS/Script2Subs
    exe = os.path.abspath(sys.executable)
    contents = os.path.dirname(os.path.dirname(exe))  # .../Contents
    res = os.path.join(contents, "Resources")
    return [
        os.path.join(res, "AutoSubs.app", "Contents", "MacOS", _BIN),
        os.path.join(res, "bin", _BIN),
        os.path.join(res, _BIN),
    ]


def find_autosubs():
    """Absolute path to the AutoSubs CLI, or None if it cannot be found."""
    env = os.environ.get("AUTOSUBS_BIN")
    if env and os.path.isfile(env):
        return env
    for candidate in _embedded_candidates():
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(_BIN)


def autosubs_command():
    """The path to execute, or the bare name so the OS reports a clear error."""
    return find_autosubs() or _BIN
