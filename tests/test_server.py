"""Smoke tests for the local UI server."""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import wave

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from script2subs.ui.server import AppState, make_server

DEMO = os.path.join(HERE, "examples", "demo")
DEMO_EN = os.path.join(DEMO, "demo_english.txt")
DEMO_ZH = os.path.join(DEMO, "demo_chinese.txt")
DEMO_JSON = os.path.join(DEMO, "demo.json")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.wav = os.path.join(cls.tmp, "narration.wav")
        with wave.open(cls.wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(8000)
            w.writeframes(b"\x00\x00" * 8000)

        cls.state = AppState()
        cls.state.paths.update({
            "audio": cls.wav,
            "timings": DEMO_JSON,
            "primary": DEMO_EN,
            "secondary": DEMO_ZH,
        })
        cls.state.outdir = cls.tmp
        cls.server = make_server(cls.state, port=0)
        cls.host, cls.port = cls.server.server_address[:2]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def url(self, path):
        return "http://%s:%d%s" % (self.host, self.port, path)

    def get(self, path, headers=None):
        req = urllib.request.Request(self.url(path), headers=headers or {})
        with urllib.request.urlopen(req, timeout=10) as res:
            return res.status, dict(res.headers), res.read()

    def post(self, path, body, token=True, origin=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Script2Subs-Token"] = self.state.token
        if origin:
            headers["Origin"] = origin
        req = urllib.request.Request(
            self.url(path), data=json.dumps(body).encode("utf-8"),
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                return res.status, dict(res.headers), res.read()
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, dict(exc.headers), exc.read()
            finally:
                exc.close()

    def test_health_and_index(self):
        status, _, body = self.get("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["ok"])

        status, _, body = self.get("/")
        html = body.decode("utf-8")
        self.assertEqual(status, 200)
        self.assertIn("Script2Subs", html)
        self.assertIn(self.state.token, html)

    def test_state_reports_files(self):
        _, _, body = self.get("/api/state")
        data = json.loads(body)
        self.assertEqual(data["files"]["primary"]["lines"], 8)
        self.assertEqual(data["files"]["secondary"]["lines"], 8)
        self.assertEqual(data["files"]["audio"]["kind"], "audio")
        self.assertTrue(data["engine"])

    def test_post_requires_token_and_same_origin(self):
        status, _, _ = self.post("/api/state", {}, token=False)
        self.assertEqual(status, 403)
        status, _, _ = self.post("/api/state", {}, token=True,
                                 origin="http://evil.example")
        self.assertEqual(status, 403)

    def test_unknown_file_is_rejected(self):
        status, _, body = self.post(
            "/api/state", {"paths": {"audio": "/definitely/not/here.wav"}})
        self.assertEqual(status, 400)
        self.assertIn("not found", json.loads(body)["error"])

    def test_browse_lists_demo_scripts(self):
        _, _, body = self.get(
            "/api/browse?path=%s&kind=script" % urllib.request.quote(DEMO))
        data = json.loads(body)
        names = {f["name"] for f in data["files"]}
        self.assertIn("demo_english.txt", names)
        self.assertIn("demo_chinese.txt", names)

    def test_align_then_export(self):
        status, _, body = self.post("/api/align", {})
        self.assertEqual(status, 200)
        result = json.loads(body)["result"]
        self.assertEqual(result["summary"]["cues"], 8)

        out = os.path.join(self.tmp, "out")
        status, _, body = self.post("/api/export", {"outdir": out})
        self.assertEqual(status, 200)
        files = json.loads(body)["files"]
        self.assertEqual(len(files), 4)
        self.assertTrue(all(os.path.isfile(p) for p in files))

    def test_options_keep_result_but_mark_stale(self):
        self.post("/api/align", {})
        status, _, body = self.post("/api/state", {"options": {"hold": 0.5}})
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIsNotNone(data["result"])
        self.assertEqual(data["options"]["hold"], 0.5)

    def test_media_range(self):
        status, headers, body = self.get(
            "/api/media?file=audio", headers={"Range": "bytes=0-99"})
        self.assertEqual(status, 206)
        self.assertEqual(len(body), 100)
        self.assertTrue(headers["Content-Range"].startswith("bytes 0-99/"))

        status, headers, body = self.get("/api/media?file=audio")
        self.assertEqual(status, 200)
        self.assertTrue(headers["Accept-Ranges"] == "bytes")


if __name__ == "__main__":
    unittest.main()
