"""Synthetic fixtures generated at test time (no checked-in example files)."""

import json
import os

DEMO_ENGLISH = [
    "Welcome to our fencing club.",
    "Fencing builds focus, speed, and confidence.",
    "Every session starts with footwork.",
    "Beginners learn with a mask and a light blade.",
    "Coaches watch every touch and every habit.",
    "Progress is measured in small wins.",
    "Parents see the change within a season.",
    "Come try a free session this weekend.",
]

DEMO_CHINESE = [
    "欢迎来到我们的击剑俱乐部。",
    "击剑能培养专注、速度和自信。",
    "每节课都从步法开始。",
    "初学者会戴上护面，拿起轻剑。",
    "教练会关注每一次交锋和每一个习惯。",
    "进步来自一次次小小的胜利。",
    "一个赛季内，家长就能看到变化。",
    "这个周末，来体验一节免费课程吧。",
]


def write_demo(folder):
    """Write english.txt, chinese.txt and narration.json; return their paths.

    The transcript words mirror the English script line-for-line, so alignment
    matches 100% and produces one cue per line.
    """
    os.makedirs(folder, exist_ok=True)
    en = os.path.join(folder, "english.txt")
    zh = os.path.join(folder, "chinese.txt")
    timings = os.path.join(folder, "narration.json")

    with open(en, "w", encoding="utf-8") as f:
        f.write("\n".join(DEMO_ENGLISH) + "\n")
    with open(zh, "w", encoding="utf-8") as f:
        f.write("\n".join(DEMO_CHINESE) + "\n")

    segments = []
    t = 0.5
    for line in DEMO_ENGLISH:
        words = []
        for word in line.split():
            words.append({"word": word, "start": round(t, 3),
                          "end": round(t + 0.3, 3)})
            t += 0.4
        segments.append({"start": words[0]["start"], "end": words[-1]["end"],
                         "text": line, "words": words})
        t += 0.6
    with open(timings, "w", encoding="utf-8") as f:
        json.dump({"language": "en", "segments": segments}, f)

    return en, zh, timings
