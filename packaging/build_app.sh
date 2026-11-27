#!/bin/bash
# Build ScriptAlign.app — a macOS bundle that opens the dashboard on
# double-click and also serves as the `scriptalign` CLI.
#
#   ./packaging/build_app.sh
#
# Env overrides:
#   PYTHON=/opt/homebrew/bin/python3.14   interpreter used for the build
#   BUILD_VENV=/tmp/sa-build              where to put the build venv
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3.14}"
VENV="${BUILD_VENV:-$ROOT/.build-venv}"

echo ">> interpreter: $PY"
"$PY" -c 'import sys; assert sys.version_info >= (3, 10), sys.version; print(">> python", sys.version.split()[0])'

if [ ! -d "$VENV" ]; then
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV/bin/python" -m pip install -r "$ROOT/packaging/requirements-build.txt"

rm -rf "$ROOT/build" "$ROOT/dist"
"$VENV/bin/pyinstaller" "$ROOT/packaging/ScriptAlign.spec" \
  --distpath "$ROOT/dist" --workpath "$ROOT/build" --noconfirm

APP="$ROOT/dist/ScriptAlign.app"
# NB: macOS filesystems are case-insensitive, so this wrapper must NOT be
# named "scriptalign" — that would overwrite "ScriptAlign" (the real binary).
WRAP="$APP/Contents/MacOS/scriptalign-cli"
cat > "$WRAP" <<'SH'
#!/bin/bash
exec "$(cd "$(dirname "$0")" && pwd)/ScriptAlign" "$@"
SH
chmod +x "$WRAP"

echo ">> built: $APP"
echo ">> GUI:  open \"$APP\""
echo ">> CLI:  \"$WRAP\" --version"
echo ">> or:   ln -sf \"$WRAP\" /usr/local/bin/scriptalign"
