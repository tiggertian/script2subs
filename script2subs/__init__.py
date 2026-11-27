"""Script2Subs — verbatim bilingual subtitles from AutoSubs word timings.

AutoSubs listens and transcribes. Script2Subs aligns your own script to those
timings, keeps the wording exactly as written, and produces Resolve-ready SRTs.

Typical use, from a project folder holding english.txt, chinese.txt and the
narration audio:

    script2subs --audio narration.wav
    script2subs ui
"""

__version__ = "0.2.1"
__all__ = ["__version__"]
