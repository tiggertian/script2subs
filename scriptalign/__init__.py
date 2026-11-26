"""ScriptAlign — verbatim bilingual subtitles from AutoSubs word timings.

AutoSubs listens and transcribes. ScriptAlign aligns your own script to those
timings, keeps the wording exactly as written, and produces Resolve-ready SRTs.

Typical use, from a project folder holding english.txt, chinese.txt and the
narration audio:

    scriptalign --audio narration.wav
    scriptalign ui
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
