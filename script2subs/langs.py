"""Script detection and per-script readability constants.

Script2Subs works with any pair of hand-authored scripts. It needs to know
whether a script is written with spaces between words (English, Spanish, ...)
or without (Chinese, Japanese), because that decides how lines are joined,
where safe break points are, and how fast a cue may be read.

Detection is per script, not per line: one line that is just a brand name in
Latin letters should not flip the whole Chinese script to word-based rules.
"""

import re

CJK = re.compile(
    r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af]")

# sentence-final and clause-final punctuation shared by Chinese and Japanese
CJK_SENT_END = "。！？!?；;"
CJK_CLAUSE_END = "，、：,:"

# Characters that commonly close a Chinese/Japanese clause or phrase; breaking
# after them rarely splits a word.
CJK_SOFT_END = set("的了是和也都就而但因与及中时后前里上下们这那过")

# Words that read badly when split off the start of a cue.
CJK_PHRASE_START = (
    "但是", "所以", "因为", "如果", "就是", "而且", "并且", "然后", "可以",
    "我们", "他们", "你们", "这个", "那个", "还是", "以及", "只有", "已经",
    "一些", "很多", "不是", "没有")

# English function words that should not end a cue.
FUNC_END = set("""a an the of to and or but in on at for with as is are was were
be been being that this these it its his her their our your my from by into than
then when while if so not such which who whom whose what how there here we you
they i he she""".split())

# Netflix-style reading speed ceilings, in characters per second.
CPS_LATIN = 20.0
CPS_CJK = 9.0

TRAILING_PUNCT = ".,;:!?—\"”’)…」』"


def is_cjk_script(lines):
    """True when most non-space characters in the script are CJK."""
    text = "".join(lines)
    letters = [ch for ch in text if not ch.isspace()]
    if not letters:
        return False
    cjk = sum(1 for ch in letters if CJK.match(ch))
    return cjk / len(letters) >= 0.2


def joiner(lines):
    """Separator used to join a script's lines back into running text."""
    return "" if is_cjk_script(lines) else " "


def cps_limit(is_cjk):
    return CPS_CJK if is_cjk else CPS_LATIN


def display_chars(text):
    """Characters that count toward reading speed (whitespace excluded)."""
    return sum(1 for ch in text if not ch.isspace())
