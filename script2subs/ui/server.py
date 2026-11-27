"""Local HTTP server for the Script2Subs desktop UI.

Exposes a small JSON API on 127.0.0.1:

    GET  /api/state           current paths, options, result and job
    POST /api/state           set paths and/or options
    GET  /api/browse          list a directory (path picker)
    POST /api/reflow          preview or apply a script reflow
    POST /api/align           run the alignment
    POST /api/transcribe      start an AutoSubs transcription job
    GET  /api/job             poll the transcription job
    POST /api/export          write the SRTs and timing report
    POST /api/reveal          show a file in the OS file manager
    GET  /api/media           stream the selected audio/video (Range aware)

Every POST needs the per-session token in `X-Script2Subs-Token`. Requests
carrying a foreign `Origin` are rejected.
"""

import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .. import __version__
from ..errors import ScriptError
from ..langs import is_cjk_script
from ..pipeline import Options, align_scripts, export_files, read_pair
from ..tools import preview, reflow
from ..text import read_lines

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".aif", ".aiff"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".avi"}
MEDIA_EXT = AUDIO_EXT | VIDEO_EXT
MODEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
LANG_RE = re.compile(r"^[A-Za-z][A-Za-z-]{0,11}$")
MAX_BODY = 1 << 20
CHUNK = 64 * 1024


def _media_info(path):
    path = os.path.expanduser(path or "")
    if not path or not os.path.isfile(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    if ext in VIDEO_EXT:
        kind = "video"
    elif ext in AUDIO_EXT:
        kind = "audio"
    else:
        kind = None
    return {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "ext": ext,
        "kind": kind,
        "size": os.path.getsize(path),
        "mtime": os.path.getmtime(path),
    }


def _script_info(path):
    path = os.path.expanduser(path or "")
    if not path or not os.path.isfile(path):
        return None
    lines = read_lines(path)
    return {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "lines": len(lines),
        "cjk": is_cjk_script(lines),
        "bytes": os.path.getsize(path),
    }


def _file_info(path):
    path = os.path.expanduser(path or "")
    if not path or not os.path.isfile(path):
        return None
    return {
        "path": os.path.abspath(path),
        "name": os.path.basename(path),
        "bytes": os.path.getsize(path),
        "mtime": os.path.getmtime(path),
    }


class Job:
    """One AutoSubs transcription subprocess, with a log tail."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.lines = []
        self.exit_code = None
        self.command = None
        self.json_path = None
        self.started = None

    def start(self, command, json_path):
        with self.lock:
            if self.running:
                raise ScriptError("A transcription is already running.")
            self.running = True
            self.lines = []
            self.exit_code = None
            self.command = command
            self.json_path = json_path
            self.started = time.time()
        threading.Thread(target=self._run, args=(command,), daemon=True).start()

    def _append(self, line):
        with self.lock:
            self.lines.append(line.rstrip("\n"))
            if len(self.lines) > 800:
                del self.lines[:200]

    def _run(self, command):
        code = 0
        try:
            proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1)
            for line in proc.stdout:
                self._append(line)
            code = proc.wait()
        except FileNotFoundError:
            self._append("error: autosubs not found on PATH. Install AutoSubs "
                         "from https://github.com/tmoroney/auto-subs")
            code = 127
        except Exception as exc:  # pragma: no cover - defensive
            self._append("error: %s" % exc)
            code = 1
        finally:
            with self.lock:
                self.running = False
                self.exit_code = code
            if code == 0 and self.json_path and os.path.exists(self.json_path):
                self._append("wrote %s" % self.json_path)

    def snapshot(self):
        with self.lock:
            return {
                "running": self.running,
                "lines": list(self.lines[-200:]),
                "exit_code": self.exit_code,
                "command": self.command,
                "json_path": self.json_path,
                "json_ready": bool(self.json_path and os.path.exists(self.json_path)),
                "started": self.started,
            }


class AppState:
    def __init__(self, project_dir=None):
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(24)
        self.paths = {"audio": "", "timings": "", "primary": "", "secondary": ""}
        self.options = Options()
        self.result = None
        self.job = Job()
        self.outdir = ""
        if project_dir:
            self._prefill(project_dir)

    def _prefill(self, directory):
        directory = os.path.abspath(os.path.expanduser(directory))
        if not os.path.isdir(directory):
            return
        for key, name in (("primary", "english.txt"),
                          ("secondary", "chinese.txt")):
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                self.paths[key] = path
        for name in sorted(os.listdir(directory)):
            if name.lower().endswith(".json") and not name.startswith("."):
                self.paths["timings"] = os.path.join(directory, name)
                break
        for name in sorted(os.listdir(directory)):
            info = _media_info(os.path.join(directory, name))
            if info and info["kind"]:
                self.paths["audio"] = info["path"]
                break
        self.outdir = directory

    def snapshot(self):
        with self.lock:
            return {
                "version": __version__,
                "paths": dict(self.paths),
                "files": {
                    "audio": _media_info(self.paths["audio"]),
                    "timings": _file_info(self.paths["timings"]),
                    "primary": _script_info(self.paths["primary"]),
                    "secondary": _script_info(self.paths["secondary"]),
                },
                "options": asdict(self.options),
                "outdir": self.outdir,
                "result": self.result,
                "job": self.job.snapshot(),
                "engine": {
                    "autosubs": shutil.which("autosubs"),
                    "platform": sys.platform,
                },
            }


def _safe_child(base, name):
    path = os.path.abspath(os.path.join(base, name))
    if path != base and not path.startswith(base + os.sep):
        return None
    return path


def _reveal(path):
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.exists(path):
        raise ScriptError("Path not found: %s" % path)
    if sys.platform == "darwin":
        cmd = ["open", "-R", path] if os.path.isfile(path) else ["open", path]
    elif os.name == "nt":
        cmd = ["explorer", "/select,", path] if os.path.isfile(path) else ["explorer", path]
    else:
        cmd = ["xdg-open", os.path.dirname(path) if os.path.isfile(path) else path]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Handler(BaseHTTPRequestHandler):
    server_version = "Script2Subs/" + __version__
    protocol_version = "HTTP/1.1"
    state = None  # set by make_server

    # ------------------------------------------------------------------ utils
    def log_message(self, fmt, *args):
        pass

    def _send_bytes(self, body, status=200, ctype="application/json; charset=utf-8",
                    extra=None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        for key, value in (extra or []):
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj, status=200):
        self._send_bytes(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                         status=status)

    def _error(self, message, status=400):
        self._json({"error": str(message)}, status=status)

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise ScriptError("Invalid Content-Length")
        if length > MAX_BODY:
            raise ScriptError("Request body too large")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ScriptError("Request body must be JSON")
        return data if isinstance(data, dict) else {}

    def _check_post(self):
        origin = self.headers.get("Origin")
        if origin:
            parsed = urlparse(origin)
            host = self.headers.get("Host", "")
            if parsed.netloc != host or parsed.scheme not in ("http", "https"):
                return False
        token = self.headers.get("X-Script2Subs-Token", "")
        return secrets.compare_digest(token, self.state.token)

    # ------------------------------------------------------------------- GET
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/":
                return self._serve_index()
            if path.startswith("/static/"):
                return self._serve_static(path[len("/static/"):])
            if path == "/api/state":
                return self._json(self.state.snapshot())
            if path == "/api/health":
                return self._json({"ok": True, "version": __version__})
            if path == "/api/browse":
                return self._browse(parsed.query)
            if path == "/api/job":
                return self._job_status()
            if path == "/api/media":
                return self._serve_media(parsed.query)
            return self._error("Not found", 404)
        except ScriptError as exc:
            return self._error(exc, 400)
        except Exception as exc:  # pragma: no cover - defensive
            self.log_error("GET %s failed: %r", path, exc)
            return self._error("Internal error: %s" % exc, 500)

    def _serve_index(self):
        path = os.path.join(STATIC_DIR, "index.html")
        with open(path, encoding="utf-8") as f:
            html = f.read()
        html = html.replace("__SCRIPT2SUBS_TOKEN__", self.state.token)
        html = html.replace("__SCRIPT2SUBS_VERSION__", __version__)
        self._send_bytes(html.encode("utf-8"), ctype="text/html; charset=utf-8")

    def _serve_static(self, name):
        if "/" in name or "\\" in name or name.startswith("."):
            return self._error("Not found", 404)
        path = _safe_child(STATIC_DIR, name)
        if not path or not os.path.isfile(path):
            return self._error("Not found", 404)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",
                                                  "application/json"):
            ctype += "; charset=utf-8"
        with open(path, "rb") as f:
            body = f.read()
        self._send_bytes(body, ctype=ctype)

    def _browse(self, query):
        params = parse_qs(query)
        wanted = (params.get("path") or [""])[0]
        kind = (params.get("kind") or [""])[0]
        if wanted:
            path = os.path.abspath(os.path.expanduser(wanted))
        else:
            path = self.state.outdir or os.getcwd()
        if os.path.isfile(path):
            path = os.path.dirname(path)
        if not os.path.isdir(path):
            raise ScriptError("Not a folder: %s" % path)

        dirs, files = [], []
        try:
            names = sorted(os.listdir(path), key=str.lower)
        except PermissionError:
            raise ScriptError("Permission denied: %s" % path)
        for name in names:
            if name.startswith("."):
                continue
            full = os.path.join(path, name)
            try:
                if os.path.isdir(full):
                    dirs.append({"name": name, "path": full, "is_dir": True})
                    continue
            except OSError:
                continue
            ext = os.path.splitext(name)[1].lower()
            if kind == "media" and ext not in MEDIA_EXT:
                continue
            if kind == "json" and ext != ".json":
                continue
            if kind == "script" and ext not in (".txt", ".srt", ".vtt"):
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            files.append({"name": name, "path": full, "is_dir": False,
                          "ext": ext, "size": size})
            if len(files) + len(dirs) >= 500:
                break

        parent = os.path.dirname(path)
        return self._json({
            "path": path,
            "parent": parent if parent != path else None,
            "home": os.path.expanduser("~"),
            "dirs": dirs,
            "files": files,
        })

    def _job_status(self):
        snap = self.state.job.snapshot()
        with self.state.lock:
            if snap["json_ready"] and not self.state.paths["timings"]:
                self.state.paths["timings"] = snap["json_path"]
        snap["state"] = self.state.snapshot()
        return self._json(snap)

    def _serve_media(self, query):
        params = parse_qs(query)
        which = (params.get("file") or ["audio"])[0]
        if which != "audio":
            return self._error("Unknown media", 404)
        path = self.state.paths.get("audio")
        if not path or not os.path.isfile(path):
            return self._error("No audio selected", 404)

        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        start, end = 0, size - 1
        status = HTTPStatus.OK
        rng = self.headers.get("Range")

        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)$", rng.strip())
            if not m:
                return self._range_not_satisfiable(size)
            first, second = m.groups()
            if first == "" and second == "":
                return self._range_not_satisfiable(size)
            if first == "":
                length = int(second)
                if length <= 0:
                    return self._range_not_satisfiable(size)
                start = max(size - length, 0)
                end = size - 1
            else:
                start = int(first)
                end = int(second) if second else size - 1
                if start >= size or end < start:
                    return self._range_not_satisfiable(size)
                end = min(end, size - 1)
            status = HTTPStatus.PARTIAL_CONTENT

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

        remaining = length
        with open(path, "rb") as f:
            f.seek(start)
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                remaining -= len(chunk)

    def _range_not_satisfiable(self, size):
        self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
        self.send_header("Content-Range", "bytes */%d" % size)
        self.send_header("Content-Length", "0")
        self.end_headers()

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        path = urlparse(self.path).path
        if not self._check_post():
            self.close_connection = True
            return self._error("Forbidden", 403)
        try:
            data = self._read_json()
            if path == "/api/state":
                return self._update_state(data)
            if path == "/api/reflow":
                return self._reflow(data)
            if path == "/api/align":
                return self._align()
            if path == "/api/transcribe":
                return self._transcribe(data)
            if path == "/api/export":
                return self._export(data)
            if path == "/api/reveal":
                return self._reveal_path(data)
            return self._error("Not found", 404)
        except ScriptError as exc:
            return self._error(exc, 400)
        except ValueError as exc:
            return self._error(exc, 400)
        except Exception as exc:  # pragma: no cover - defensive
            self.log_error("POST %s failed: %r", path, exc)
            return self._error("Internal error: %s" % exc, 500)

    def _update_state(self, data):
        updates = {}
        incoming = data.get("paths") or {}
        for key in ("audio", "timings", "primary", "secondary"):
            if key not in incoming:
                continue
            value = str(incoming[key] or "").strip()
            if value:
                value = os.path.abspath(os.path.expanduser(value))
                if not os.path.isfile(value):
                    raise ScriptError("%s not found: %s" % (key, value))
            updates[key] = value

        options = None
        if "options" in data:
            merged = asdict(self.state.options)
            merged.update({k: v for k, v in (data["options"] or {}).items()
                           if k in merged})
            options = Options.from_dict(merged)

        outdir = None
        if "outdir" in data:
            value = str(data["outdir"] or "").strip()
            if value:
                value = os.path.abspath(os.path.expanduser(value))
                if not os.path.isdir(value):
                    raise ScriptError("Output folder not found: %s" % value)
                outdir = value

        with self.state.lock:
            if updates:
                self.state.paths.update(updates)
                self.state.result = None
            if options is not None:
                self.state.options = options
                # Keep the result; the UI flags it as stale until re-run.
            if outdir is not None:
                self.state.outdir = outdir
        return self._json(self.state.snapshot())

    def _reflow(self, data):
        with self.state.lock:
            paths = dict(self.state.paths)
            opts = self.state.options
        kwargs = {}
        for key in ("max_primary", "max_secondary", "min_len"):
            if key in data:
                kwargs[key] = data[key]
        kwargs.setdefault("max_primary", opts.max_primary)
        kwargs.setdefault("max_secondary", opts.max_secondary)
        kwargs.setdefault("min_len", opts.min_len)
        merged = Options.from_dict({
            **asdict(opts), **kwargs})
        kwargs = {"max_primary": merged.max_primary,
                  "max_secondary": merged.max_secondary,
                  "min_len": merged.min_len}

        if data.get("dry_run"):
            result = preview(paths["primary"], paths["secondary"], **kwargs)
        else:
            result = reflow(paths["primary"], paths["secondary"], **kwargs)
            with self.state.lock:
                self.state.result = None
        return self._json({"reflow": result, "state": self.state.snapshot()})

    def _align(self):
        with self.state.lock:
            paths = dict(self.state.paths)
            opts = self.state.options
        if not paths["primary"] or not paths["secondary"]:
            raise ScriptError("Choose both scripts first.")
        if not paths["timings"]:
            raise ScriptError(
                "No AutoSubs timings yet. Transcribe the narration or choose a "
                "JSON/SRT file first.")
        primary, secondary = read_pair(paths["primary"], paths["secondary"])
        result = align_scripts(primary, secondary, paths["timings"], opts)
        result["primary_path"] = paths["primary"]
        result["secondary_path"] = paths["secondary"]
        with self.state.lock:
            self.state.result = result
        return self._json({"result": result, "state": self.state.snapshot()})

    def _transcribe(self, data):
        with self.state.lock:
            audio = self.state.paths["audio"]
        if not audio or not os.path.isfile(audio):
            raise ScriptError("Choose the narration audio first.")
        model = str(data.get("model") or "large-v3-turbo")
        if not MODEL_RE.match(model):
            raise ScriptError("Invalid model name: %s" % model)
        lang = str(data.get("lang") or "").strip()
        if lang and not LANG_RE.match(lang):
            raise ScriptError("Invalid language code: %s" % lang)
        forced = data.get("forced_alignment", True)
        json_path = str(data.get("json") or "").strip()
        if json_path:
            json_path = os.path.abspath(os.path.expanduser(json_path))
        else:
            json_path = os.path.splitext(audio)[0] + ".json"

        autosubs = shutil.which("autosubs") or "autosubs"
        cmd = [autosubs, audio, "-m", model, "-f", "json", "-o", json_path]
        if lang:
            cmd += ["-l", lang]
        if forced:
            cmd.append("--forced-alignment")

        self.state.job.start(cmd, json_path)
        with self.state.lock:
            self.state.paths["timings"] = json_path
        return self._json({"job": self.state.job.snapshot(),
                           "state": self.state.snapshot()})

    def _export(self, data):
        with self.state.lock:
            result = self.state.result
            paths = dict(self.state.paths)
            outdir = (data.get("outdir") or self.state.outdir or "").strip()
        if not result:
            raise ScriptError("Run the alignment before exporting.")
        if not outdir:
            outdir = os.path.dirname(paths["primary"]) or os.getcwd()
        outdir = os.path.abspath(os.path.expanduser(outdir))
        os.makedirs(outdir, exist_ok=True)
        files = export_files(result, paths["primary"], paths["secondary"], outdir)
        with self.state.lock:
            self.state.outdir = outdir
        return self._json({"files": files, "outdir": outdir,
                           "state": self.state.snapshot()})

    def _reveal_path(self, data):
        path = str(data.get("path") or "")
        if not path:
            raise ScriptError("No path to reveal")
        _reveal(path)
        return self._json({"ok": True})


def make_server(state, host="127.0.0.1", port=0):
    handler = type("BoundHandler", (Handler,), {"state": state})
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
