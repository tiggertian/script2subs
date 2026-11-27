#!/bin/bash
# Download the official AutoSubs macOS app (MIT) into .cache/autosubs so a build
# can embed it. Transcription models are NOT bundled — AutoSubs fetches them on
# first use. Note: the optional MMS forced-alignment weights are CC BY-NC 4.0
# (non-commercial), downloaded by AutoSubs, not by us.
#
#   ./packaging/fetch_autosubs.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

case "$(uname -m)" in
  arm64)  ASSET="AutoSubs-macos-aarch64.app.tar.gz" ;;
  x86_64) ASSET="AutoSubs-macos-x86_64.app.tar.gz" ;;
  *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;;
esac

DEST="$ROOT/.cache/autosubs"
if [ -d "$DEST/AutoSubs.app" ]; then
  echo ">> already fetched: $DEST/AutoSubs.app"
  exit 0
fi

mkdir -p "$DEST"
URL="https://github.com/tmoroney/auto-subs/releases/latest/download/$ASSET"
echo ">> downloading $URL"
curl -fL --retry 3 -o "$DEST/autosubs.tar.gz" "$URL"
tar -xzf "$DEST/autosubs.tar.gz" -C "$DEST"
rm -f "$DEST/autosubs.tar.gz"
echo ">> fetched $DEST/AutoSubs.app"
