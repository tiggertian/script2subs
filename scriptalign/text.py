"""Subtitle script loading and word tokenisation."""

import re

CURLY = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})
WORD_SPLIT = re.compile(r"[\s\-/]+")
NON_WORD = re.compile(r"[^\w]|_")


def tokenize(text):
    """Lowercase word list, punctuation and possessives stripped.

    'Top-32-ranked' -> ['top', '32', 'ranked'];  'I’m' -> ['im'].
    Both the script and the transcript go through this, so exact spelling
    differences (curly vs straight quotes) do not break word matching.
    """
    text = text.translate(CURLY).lower()
    out = []
    for raw in WORD_SPLIT.split(text):
        tok = NON_WORD.sub("", raw)
        if tok:
            out.append(tok)
    return out


def read_lines(path):
    """Non-empty lines of a subtitle script, in order."""
    with open(path, encoding="utf-8-sig") as f:
        lines = [ln.strip() for ln in f.read().splitlines()]
    return [ln for ln in lines if ln]
