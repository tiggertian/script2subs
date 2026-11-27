"""python3 -m unittest discover -s tests -v"""

import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from script2subs.align import align, interpolate
from script2subs.cues import line_spans, make_cues
from script2subs.diagnostics import cue_flags, summarize
from script2subs.errors import ScriptError
from script2subs.langs import is_cjk_script, joiner
from script2subs.pipeline import Options, align_scripts, export_files, read_pair
from script2subs.rebreak import rebreak
from script2subs.srt import srt_time, write_srt
from script2subs.text import tokenize
from script2subs.timings import build_transcript_tokens, parse_json, parse_srt

DEMO = os.path.join(HERE, "examples", "demo")
DEMO_EN = os.path.join(DEMO, "demo_english.txt")
DEMO_ZH = os.path.join(DEMO, "demo_chinese.txt")
DEMO_JSON = os.path.join(DEMO, "demo.json")


def whisper_json(segments, original=None):
    """Minimal AutoSubs-shaped document; `original` mimics originalSegments."""
    data = {"segments": segments}
    if original is not None:
        data["originalSegments"] = original
    path = os.path.join(tempfile.mkdtemp(), "n.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


def strip_space(text):
    return re.sub(r"\s+", "", text)


class TextTests(unittest.TestCase):
    def test_tokenize(self):
        self.assertEqual(tokenize("Top-32-ranked"), ["top", "32", "ranked"])
        self.assertEqual(tokenize("I’m"), ["im"])
        self.assertEqual(tokenize("— and/or —"), ["and", "or"])


class LangTests(unittest.TestCase):
    def test_cjk_detection(self):
        self.assertTrue(is_cjk_script(["欢迎来到我们的击剑俱乐部。"]))
        self.assertTrue(is_cjk_script(["15岁，来自北京艾鲁特击剑训练中心。"]))
        self.assertFalse(is_cjk_script(["Welcome to our fencing club."]))
        self.assertFalse(is_cjk_script(["Tigger from Beijing 北京"]))

    def test_joiner(self):
        self.assertEqual(joiner(["你好。", "再见。"]), "")
        self.assertEqual(joiner(["Hello.", "Goodbye."]), " ")


class TimingTests(unittest.TestCase):
    def test_prefers_refined_segments_over_original(self):
        refined = [{"start": 1.0, "end": 1.5, "text": "Hello there",
                    "words": [{"word": "Hello", "start": 1.0, "end": 1.2},
                              {"word": "there", "start": 1.2, "end": 1.5}]}]
        raw = [{"start": 0.9, "end": 1.6, "text": "Hello there",
                "words": [{"word": "Hello", "start": 0.9, "end": 1.1},
                          {"word": "there", "start": 1.1, "end": 1.4}]}]
        units, kind = parse_json(whisper_json(refined, raw))
        self.assertEqual(kind, "word")
        self.assertEqual(len(units), 2)  # not duplicated
        self.assertEqual(units[0][0], 1.0)

    def test_srt_round_trip(self):
        path = os.path.join(tempfile.mkdtemp(), "a.srt")
        write_srt(path, [(1.5, 2.25, "one"), (2.5, 3.0, "two")])
        units, kind = parse_srt(path)
        self.assertEqual(kind, "segment")
        self.assertEqual(len(units), 2)
        self.assertAlmostEqual(units[0][0], 1.5)
        self.assertAlmostEqual(units[0][1], 2.25)
        self.assertEqual(srt_time(3661.004), "01:01:01,004")


class AlignTests(unittest.TestCase):
    def test_align_skips_unmatched_word(self):
        mapping = align(["a", "b", "c"], ["a", "x", "c"])
        self.assertEqual(mapping, {0: 0, 2: 2})

    def test_interpolate_fills_gap(self):
        times = interpolate([(0.0, 0.5), None, (2.0, 2.5)], 0.0, 2.5)
        self.assertAlmostEqual(times[1][0], 1.25)


class CueTests(unittest.TestCase):
    def test_short_pause_is_bridged_long_pause_is_kept(self):
        lines = ["one", "two", "three"]
        starts = [0.0, 1.5, 6.0]
        ends = [1.0, 2.0, 7.0]
        cues = make_cues(lines, starts, ends, min_dur=0.1, hold=1.0, linger=0.4)
        self.assertEqual(cues[0][1], 1.5)  # bridged, butt-joined (no frame gap)
        self.assertAlmostEqual(cues[1][1], 2.4, places=6)          # lingered

    def test_line_spans_cover_first_and_last_word(self):
        starts, ends = line_spans([(1.0, 1.2), (1.3, 1.6), (2.0, 2.4)],
                                  [0, 0, 1], 2)
        self.assertEqual(starts, [1.0, 2.0])
        self.assertEqual(ends, [1.6, 2.4])

    def test_no_overlap_and_min_duration(self):
        lines = ["a", "b"]
        cues = make_cues(lines, [0.0, 0.2], [0.1, 0.3], min_dur=0.8)
        self.assertGreaterEqual(cues[0][1] - cues[0][0], 0.8)
        self.assertLessEqual(cues[0][1], cues[1][0])


class RebreakTests(unittest.TestCase):
    def test_preserves_text_and_equal_counts(self):
        en = ["Hello there my friend, how", "are you doing today? I hope",
              "you are well."]
        zh = ["你好，我的朋友，", "你今天怎么样？", "希望你一切都好。"]
        pe, pz = rebreak(en, zh, max_primary=30, min_len=12)
        self.assertEqual(len(pe), len(pz))
        self.assertEqual(strip_space("".join(en)), strip_space("".join(pe)))
        self.assertEqual("".join(zh), "".join(pz))

    def test_numbered_heading_starts_a_cue(self):
        en = ["I would summarize them as follows: 1. Improved",
              "Concentration. Fencing is fun."]
        zh = ["我总结如下：1.提高专注力。", "击剑很有趣。"]
        pe, _ = rebreak(en, zh, max_primary=42, min_len=18)
        self.assertTrue(any(l.startswith("1. ") for l in pe))
        self.assertFalse(any(l.endswith(": 1.") for l in pe))

    def test_latin_secondary_breaks_on_words(self):
        en = ["Hello there, my friend,", "how are you doing today?",
              "I hope you are well."]
        es = ["Hola, mi amigo,", "¿cómo estás hoy?", "Espero que estés bien."]
        pe, ps = rebreak(en, es, max_primary=24, max_secondary=18, min_len=10)
        self.assertEqual(len(pe), len(ps))
        self.assertEqual(strip_space("".join(en)), strip_space("".join(pe)))
        self.assertEqual(strip_space("".join(es)), strip_space("".join(ps)))
        for line in ps:
            self.assertEqual(line, " ".join(line.split()))
            for word in line.split():
                self.assertIn(word, " ".join(es))

    def test_cjk_primary(self):
        zh = ["欢迎来到我们的击剑俱乐部。", "击剑能培养专注、速度和自信。",
              "每节课都从步法开始。"]
        en = ["Welcome to our fencing club.", "Fencing builds focus and confidence.",
              "Every session starts with footwork."]
        pz, pe = rebreak(zh, en, max_primary=14, max_secondary=30, min_len=6)
        self.assertEqual(len(pz), len(pe))
        self.assertEqual("".join(zh), "".join(pz))
        self.assertEqual(strip_space("".join(en)), strip_space("".join(pe)))


class DiagnosticsTests(unittest.TestCase):
    def test_flags(self):
        opts = Options(max_primary=10, max_secondary=8)
        flags = cue_flags("This ends with the", "这一行很长很长", 0.5, opts,
                          primary_cjk=False, secondary_cjk=True)
        codes = {f["code"] for f in flags}
        self.assertIn("over-limit", codes)
        self.assertIn("reading-speed", codes)
        self.assertIn("too-short", codes)
        self.assertIn("dangling", codes)

    def test_summary_warns_about_flicker(self):
        cues = [{"flags": [], "gap_after": 0.01},
                {"flags": [], "gap_after": None}]
        summary = {"match_pct": 99.0, "script_tokens": 10, "matched": 10,
                   "primary_cjk": False}
        counts, flicker, warnings = summarize(cues, summary, Options())
        self.assertEqual(flicker, 1)
        self.assertTrue(any(w["code"] == "flicker" for w in warnings))


class PipelineTests(unittest.TestCase):
    def test_demo_end_to_end_and_export(self):
        primary, secondary = read_pair(DEMO_EN, DEMO_ZH)
        result = align_scripts(primary, secondary, DEMO_JSON, Options())
        self.assertEqual(result["summary"]["cues"], 8)
        self.assertEqual(result["summary"]["match_pct"], 100.0)
        self.assertEqual(len(result["cues"]), 8)
        self.assertTrue(result["summary"]["primary_cjk"] is False)
        self.assertTrue(result["summary"]["secondary_cjk"] is True)

        out = tempfile.mkdtemp()
        files = export_files(result, DEMO_EN, DEMO_ZH, out)
        self.assertEqual(len(files), 4)
        for path in files:
            self.assertTrue(os.path.isfile(path))
        with open(files[2], encoding="utf-8") as f:
            bilingual = f.read()
        self.assertIn("Welcome to our fencing club.", bilingual)
        self.assertIn("欢迎来到我们的击剑俱乐部。", bilingual)

    def test_line_count_mismatch_is_rejected(self):
        folder = tempfile.mkdtemp()
        en = os.path.join(folder, "english.txt")
        zh = os.path.join(folder, "chinese.txt")
        with open(en, "w", encoding="utf-8") as f:
            f.write("one\ntwo\n")
        with open(zh, "w", encoding="utf-8") as f:
            f.write("一\n")
        with self.assertRaises(ScriptError):
            read_pair(en, zh)


class EndToEndTests(unittest.TestCase):
    def test_three_line_script_gets_three_cues(self):
        segs = [{"start": 0.0, "end": 3.0, "text": "hello there friend how are you",
                 "words": [{"word": w, "start": i * 0.5, "end": i * 0.5 + 0.5}
                           for i, w in enumerate(
                               "hello there friend how are you".split())]}]
        units, _ = parse_json(whisper_json(segs))
        tokens = build_transcript_tokens(units)
        self.assertEqual(len(tokens), 6)


if __name__ == "__main__":
    unittest.main()
