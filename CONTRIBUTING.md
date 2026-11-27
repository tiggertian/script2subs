# Contributing to Script2Subs

Thanks for helping. Script2Subs is a small, dependency-free tool, and the
principles below keep it that way.

## Ground rules

- **Never change the user's script text.** Alignment and re-flow decide *when*
  and *where* lines break — never *what* they say. Any change that rewrites,
  trims, corrects, or normalizes script characters is a bug. The re-flow code
  already verifies this by comparing whitespace-stripped text and refusing to
  write if anything differs; keep that guarantee intact.
- **Stdlib only at runtime.** The server, CLI, and pipeline use the Python
  standard library. `pywebview` is an optional extra for the desktop window. Add
  a runtime dependency only if there is no reasonable stdlib path, and discuss
  it first.
- **One cue per script line.** Don't introduce cue merging or splitting that
  breaks the line-for-line contract with the paired script.
- **The local app stays local.** Bind to `127.0.0.1`, keep the per-session
  token and origin checks on state-changing requests, and never expose arbitrary
  file reads beyond the selected media.

## Getting set up

```bash
python -m pip install -e ".[dev]"
python -m unittest discover -s tests -v
```

The test suite generates its own synthetic fixtures — no example files are
checked in. And the app:

```bash
script2subs ui            # native window / Chrome app / browser
script2subs ui --no-window
```

## Where things live

- `script2subs/pipeline.py` — the shared path both the CLI and UI call.
- `script2subs/align.py` — sequence alignment; the heart of the timing.
- `script2subs/rebreak.py` and `script2subs/langs.py` — re-flow, including CJK
  rules. Changes here are the easiest to get subtly wrong; add tests.
- `script2subs/ui/` — local server (`server.py`), launcher (`app.py`), and the
  no-build SPA in `static/`.
- `tests/` — unit tests plus a live-server integration test.

## Tests

- Add a test for every behavior change, especially in re-flow, alignment, and
  the server's request handling.
- The server tests start a real `ThreadingHTTPServer` on an ephemeral port and
  exercise real HTTP; prefer extending them over mocking.
- Keep tests hermetic: write to temporary directories, don't depend on the
  client narration files (they're gitignored).
- Run the full suite before opening a pull request; CI runs 3.10–3.13.

## Changing output format

The SRT and timing-report formats are user-facing. If you change them, update
the tests and the README together, and mention the change in your pull request.
Byte-stability of existing output is a feature — if a refactor shouldn't change
output, verify it didn't.

## Pull requests

- Keep changes focused; one concern per pull request.
- Describe *why*, not just *what*. Screenshots help for UI changes.
- Match the existing style: small modules, clear names, comments only where the
  logic isn't obvious.

## Attribution

Script2Subs builds on AutoSubs (MIT). Don't copy AutoSubs source into this
repository — it's invoked as an external tool. If you add a dependency or borrow
an algorithm, note its license and add it to [NOTICE](NOTICE).
