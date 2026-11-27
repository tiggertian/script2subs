"""Launch the Script2Subs desktop window.

Order of preference:
1. pywebview (a native webview window), if installed;
2. a Chrome/Chromium/Edge app window, if found;
3. the default browser.

The server always binds to 127.0.0.1. Use `--no-window` for a headless run
(handy for screenshots and smoke tests) and Ctrl+C to stop.
"""

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser

from ..autosubs import find_autosubs
from .server import AppState, make_server


def _chrome_candidates():
    return [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("msedge"),
    ]


def _open_chrome_app(url):
    for exe in _chrome_candidates():
        if exe and os.path.exists(exe):
            subprocess.Popen(
                [exe, "--app=%s" % url, "--window-size=1320,900"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    return False


def _open_pywebview(url):
    try:
        import webview
    except Exception as exc:
        return False, "pywebview not installed (%s)" % exc
    try:
        webview.create_window(
            "Script2Subs", url, width=1320, height=900, min_size=(1024, 700),
            background_color="#0a0c10")
        webview.start()
        return True, "pywebview"
    except Exception as exc:  # pragma: no cover - platform dependent
        return False, "pywebview failed (%s)" % exc


def _wait_forever():
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="script2subs ui",
        description="Open the Script2Subs desktop app for the current folder.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default: 127.0.0.1 only)")
    parser.add_argument("--port", type=int, default=0,
                        help="server port (default: pick a free port)")
    parser.add_argument("--project", default=".",
                        help="prefill paths from this folder (default: .)")
    parser.add_argument("--no-window", action="store_true",
                        help="serve only; do not open a window")
    parser.add_argument("--browser", action="store_true",
                        help="open in the default browser, not an app window")
    args = parser.parse_args(argv)

    state = AppState(project_dir=args.project)
    server = make_server(state, host=args.host, port=args.port)
    host, port = server.server_address[0], server.server_address[1]
    url = "http://%s:%d/" % (host, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    engine = "AutoSubs found" if find_autosubs() else \
        "AutoSubs not on PATH (install it to transcribe)"
    print("Script2Subs %s — %s" % (state.snapshot()["version"], engine))
    print("serving %s  (Ctrl+C to quit)" % url)

    try:
        if args.no_window:
            _wait_forever()
            return 0

        if args.browser:
            webbrowser.open(url)
            _wait_forever()
            return 0

        opened, why = _open_pywebview(url)
        if not opened:
            print("note: %s" % why)
            if _open_chrome_app(url):
                print("opened a Chrome app window; close it and press Ctrl+C")
                _wait_forever()
            else:
                print("opening your default browser")
                webbrowser.open(url)
                _wait_forever()
        return 0
    except KeyboardInterrupt:
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    sys.exit(main())
