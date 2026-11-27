# Script2Subs

**Verbatim bilingual subtitles, timed to your narration with AutoSubs.**

You write the script. You record the narration. Script2Subs listens to the
recording with [AutoSubs](https://github.com/tmoroney/auto-subs), lines your
hand-authored script up against the word-level timings, and exports subtitles
that say exactly what you wrote — in one language or two — as
DaVinci Resolve-ready SRT files.

- **Verbatim.** Your script text is never rewritten, paraphrased, or
  auto-corrected. Alignment only decides *when* each line appears.
- **Bilingual by design.** Keep a primary and a secondary script as a strict
  line-for-line pair and get a single stacked track with both languages.
- **CJK-aware.** Line re-flow and reading-speed checks understand Chinese
  (and other CJK scripts) — character-based wrapping, punctuation-aware breaks.
- **One cue per script line.** Re-flow at phrase boundaries instead of
  guessing breaks that split words.
- **Review built in.** A local desktop app plays the audio, highlights each
  cue, flags lines that are too fast or too long, and lets you tweak timing
  without leaving the window.

Script2Subs is an independent project built on AutoSubs' command-line tool. It
calls `autosubs`, reads the JSON word timings AutoSubs writes, and does all of
the alignment, re-flow, pairing, diagnostics, UI, and SRT generation itself. See
[NOTICE](NOTICE).

---

## How it works

```
narration audio ──▶ autosubs (whisper + MMS forced alignment) ──▶ word timings (JSON)
                                                                        │
your primary script ─┐                                                  ▼
your secondary script ┴──▶ Script2Subs ── sequence-align ──▶ time each line ──▶ SRT ×3 + report
```

1. **AutoSubs listens.** It transcribes the narration and, with
   `--forced-alignment`, refines every word to a start and end time.
2. **Script2Subs aligns.** Your script's words are matched against the
   transcript with a global (Needleman–Wunsch) sequence alignment. Exact matches
   anchor the timing; words that were paraphrased or mis-heard are interpolated
   between their neighbours.
3. **One cue per line.** Each script line becomes one cue, timed from its first
   and last matched word. Short pauses are bridged so the text doesn't blink
   off and on; very short cues are lengthened; optional offsets line the result
   up with a timeline that doesn't start at zero.
4. **Export.** Primary, secondary, and bilingual `.srt` files plus a
   `timing_report.csv` you can open while reviewing.

## Install

### macOS app (no Python required)

Download the latest `Script2Subs-*.dmg` from the
[Releases](https://github.com/tiggertian/script2subs/releases) page, open it, and
drag **Script2Subs** to Applications. It opens the dashboard, and the same
bundle exposes the CLI:

```bash
ln -sf "/Applications/Script2Subs.app/Contents/MacOS/script2subs-cli" /usr/local/bin/script2subs
script2subs --version
```

The build is unsigned, so the first launch needs right-click → **Open** (or
`xattr -dr com.apple.quarantine /Applications/Script2Subs.app`). It bundles
Python and the frontend but not AutoSubs — install AutoSubs separately, or feed
it existing timings JSON/SRT.

### From source or PyPI

Script2Subs needs **Python 3.10+** and, for transcription, the
[AutoSubs](https://github.com/tmoroney/auto-subs) CLI on your `PATH`.
If you already have AutoSubs word timings (or any SRT of the narration), you can
use Script2Subs without installing AutoSubs at all.

```bash
git clone <your-repo-url> script2subs
cd script2subs
python -m pip install -e .
```

That installs the `script2subs` command. For the desktop window, install the
optional UI dependency (recommended):

```bash
python -m pip install -e ".[ui]"      # adds pywebview
```

**No install needed.** The CLI and server are stdlib-only, so you can run
straight from a checkout. On macOS, double-click `Script2Subs.command` to open
the dashboard, or run `python3 -m script2subs ui`.

Without `pywebview`, `script2subs ui` still works: it looks for a Chrome,
Chromium, or Edge install and opens a chromeless app window, and falls back to
your default browser. The server always binds to `127.0.0.1`.

## Quickstart

```bash
# 1. time your scripts against the narration (transcribes with AutoSubs)
script2subs --audio narration.wav

# 2. or reuse AutoSubs JSON / any SRT you already have
script2subs --timings narration.json

# 3. open the desktop app
script2subs ui
```

Defaults: primary `english.txt`, secondary `chinese.txt`, output `.`. Override
with `--en`, `--zh`, `--outdir`.

You get four files:

| File | What it is |
| --- | --- |
| `english.srt` | Primary-language cues |
| `chinese.srt` | Secondary-language cues (same timings) |
| `bilingual.srt` | Both languages stacked in one cue — **use this one in Resolve** |
| `timing_report.csv` | Per-cue timing, CPS, gaps, and flags for review |

## The script contract

- Two plain-text files, one line per cue.
- They must have **exactly the same number of lines** — line *N* in one is line
  *N* in the other. Blank lines are dropped, so leave no gaps in either file.
- Write the text the way you want it to read on screen. Script2Subs will not
  change a single character of it. If a re-flow step would, it refuses.

If the line counts differ, Script2Subs stops with a message telling you which
file has how many lines.

## Re-flowing long lines

Aligned scripts often have lines too long to read comfortably. `script2subs
reflow` re-breaks both files at phrase boundaries — **without changing the
text** — and writes `.orig` backups the first time. Preview it before writing:

```bash
script2subs reflow --dry-run          # show what would change
script2subs reflow                    # apply, keeping .orig copies
script2subs reflow --max-chars 38 --max-chars-secondary 18 --min-len 16
```

The re-flow keeps every character: it strips whitespace and compares the
original and re-broken text, and aborts if anything would change. For CJK
scripts it wraps by character at sentence and clause punctuation; for
space-delimited scripts it wraps at word boundaries. You can also do this as
part of alignment with `script2subs align --rebreak`.

## Diagnostics

The report and the UI flag cues worth a second look:

- **over-limit** — a line longer than `--max-chars` (primary) or
  `--max-chars-secondary`.
- **reading-speed** — above 20 characters/second (Latin) or 9 characters/second
  (CJK), Netflix-style thresholds.
- **too-short** — a cue shorter than `--min-dur`.
- **dangling** — the line ends on an English function word ("the", "and", …).
- **low-match** / **unmatched** — the script and the transcript disagree in
  enough places that the timing may be wrong; usually means the audio and
  script don't correspond.

The CLI prints a one-line summary plus any warnings after each run.

## Timing options

| Flag | Default | Effect |
| --- | --- | --- |
| `--offset SECONDS` | `0` | Added to every cue. Use when the timeline doesn't start at `00:00:00:00`. |
| `--min-dur SECONDS` | `0.8` | Cue is stretched to at least this long. |
| `--gap SECONDS` | `0` | Blank left between cues. `0` butt-joins them, which avoids a one-frame flicker at 24 fps. |
| `--hold SECONDS` | `1.0` | Pauses up to this long are bridged — text stays up instead of blinking. |
| `--linger SECONDS` | `0.4` | Each cue holds this long past its last word. |
| `--max-chars N` | `42` | Primary line length target. |
| `--max-chars-secondary N` | `20` | Secondary line length target. |
| `--min-len N` | `18` | Minimum characters per primary re-flow line. |

Transcription flags for `--audio`: `--model` (default `large-v3-turbo`),
`--lang` (default `en`), `--json`, `--force`, `--no-forced-alignment`,
`--no-backup`.

## Using it in DaVinci Resolve

1. Import `bilingual.srt` into the Media Pool (**File → Import → Subtitle**).
2. Drag it onto the timeline, or right-click → **Insert Selected Subtitles to
   Timeline Using Timecode**.
3. The timeline's start timecode must match where the narration starts. If the
   timeline starts at `00:00:00:00`, no offset is needed. If it starts later
   (say `01:00:00:00`), add `--offset 3600` when aligning.
4. The bilingual file is one stacked track, so both languages stay in sync and
   move together.

For social cuts you can also burn the subtitles in directly for a consistent
look across platforms.

## The desktop app

`script2subs ui` opens a four-step workflow in a native window:

1. **Source** — pick the narration and the AutoSubs timings. Don't have
   timings yet? Transcribe from the app: choose a model and language, run it,
   and its log streams in the window.
2. **Scripts** — pick the primary/secondary pair. The app checks they're 1:1
   and lets you preview and apply re-flow with a live diff.
3. **Review** — run the alignment, then scrub the audio with the cue table
   highlighted in time. Tweak timing knobs and see the stale-result banner until
   you re-run.
4. **Export** — choose an output folder, write the files, and reveal them in
   your file manager.

It's a local-only app: the server binds to `127.0.0.1`, state-changing requests
need a per-session token, and the origin is checked. Useful flags:
`--no-window` (headless), `--browser`, `--port N`, `--project DIR`.

## Demo

No narration handy? The repo ships a tiny synthetic example:

```bash
script2subs --timings examples/demo/demo.json \
  --en examples/demo/demo_english.txt \
  --zh examples/demo/demo_chinese.txt \
  --outdir /tmp/demo-out
```

It produces eight cues at 100% word match. The client narration and generated
deliverables in the repo root are intentionally ignored by git — only the demo
is checked in.

## Project layout

```
script2subs/
  cli.py          command line entry point (align, reflow, ui)
  pipeline.py     shared alignment pipeline used by the CLI and UI
  align.py        Needleman–Wunsch sequence alignment + interpolation
  timings.py      AutoSubs JSON / SRT loading → transcript tokens
  cues.py         per-line cue timing (hold, linger, min-dur, gap)
  rebreak.py      text-preserving re-flow (Latin + CJK)
  langs.py        CJK detection, joiners, CPS thresholds
  diagnostics.py  per-cue flags and run-level warnings
  srt.py          SRT and timing-report writers
  text.py         tokenizer and line reader
  tools.py        reflow preview/apply with the verbatim guarantee
  errors.py       user-facing error type
  ui/             local HTTP server, desktop launcher, static SPA
examples/demo/    synthetic scripts + timings for the docs and CI
tests/            unit and integration tests
```

## Packaging a macOS app

`packaging/build_app.sh` builds `dist/Script2Subs.app` with PyInstaller. The
bundle opens the dashboard on double-click **and** works as the `script2subs`
CLI — no Python needed on the target machine:

```bash
./packaging/build_app.sh                  # build dist/Script2Subs.app
open "dist/Script2Subs.app"               # GUI dashboard
dist/Script2Subs.app/Contents/MacOS/script2subs-cli --version   # CLI

# optional: put the CLI on your PATH
ln -sf "$PWD/dist/Script2Subs.app/Contents/MacOS/script2subs-cli" /usr/local/bin/script2subs
```

For release artifacts, run `./packaging/make_dist.sh` — it builds the app and
writes a DMG (drag-to-Applications installer) plus a `.zip` under `dist/`, named
with the version and architecture. Attach those to a GitHub release.

The build defaults to `python3.14` (override with `PYTHON=/path/to/python3.14`)
and installs PyInstaller + pywebview into `.build-venv/`. The bundle includes
Python and the `ui/static` frontend, but **not** AutoSubs — install AutoSubs
separately to transcribe. The app is unsigned; to share it, sign and notarize
it with your Developer ID.

## Development

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

The suite covers alignment, re-flow (Latin and CJK), diagnostics, the full demo
pipeline, and a live local server (routes, token/origin checks, Range requests,
align → export). CI runs it on Python 3.10–3.13.

## License and attribution

MIT — see [LICENSE](LICENSE). Script2Subs is built on
[AutoSubs](https://github.com/tmoroney/auto-subs) by tmoroney and contributors
(MIT); it invokes the AutoSubs CLI and reads its JSON output, and includes no
AutoSubs source. See [NOTICE](NOTICE).
