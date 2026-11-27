"""Single entry point for the packaged macOS app and its CLI.

Launched from Finder it gets no arguments and opens the dashboard; run from a
terminal with arguments it behaves exactly like the ``script2subs`` command.
"""

import os
import sys


def _argv():
    # Finder may pass a legacy Process Serial Number argument on launch.
    return [a for a in sys.argv[1:] if not a.startswith("-psn_")]


def main():
    args = _argv()
    if not args:
        from script2subs.ui.app import main as ui_main
        return ui_main(["--project", os.path.expanduser("~")])
    from script2subs.cli import main as cli_main
    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main() or 0)
