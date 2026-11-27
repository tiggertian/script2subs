#!/bin/bash
# Build Script2Subs.app and package it for a GitHub release:
#   dist/Script2Subs-<ver>.dmg              drag-to-Applications installer
#   dist/Script2Subs-<ver>-macos-<arch>.zip the .app on its own
#
#   ./packaging/make_dist.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VER="$(grep -m1 '^version = ' pyproject.toml | cut -d'"' -f2)"
ARCH="$(uname -m)"

./packaging/build_app.sh

APP="$ROOT/dist/Script2Subs.app"

# DMG staging folder: the app plus an Applications shortcut to drag onto.
STAGE="$ROOT/build/dmg"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"

DMG="$ROOT/dist/Script2Subs-$VER.dmg"
rm -f "$DMG"
hdiutil create -volname "Script2Subs" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

ZIP="$ROOT/dist/Script2Subs-$VER-macos-$ARCH.zip"
rm -f "$ZIP"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"

echo ">> dmg: $DMG"
echo ">> zip: $ZIP"
