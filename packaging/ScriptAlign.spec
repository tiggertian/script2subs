# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: build ScriptAlign.app (GUI) that doubles as a CLI.

Run via packaging/build_app.sh, which supplies the interpreter and paths.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
STATIC = os.path.join(ROOT, "scriptalign", "ui", "static")

a = Analysis(
    [os.path.join(SPECPATH, "entry.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[(STATIC, os.path.join("scriptalign", "ui", "static"))],
    hiddenimports=[
        "webview.platforms.cocoa",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ScriptAlign",
    debug=False,
    strip=False,
    upx=False,
    # Console bootloader so stdout/stderr work when invoked as a CLI. On macOS,
    # Finder launches the bundle via LaunchServices with no TTY, so double-click
    # still opens the GUI without a terminal window.
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ScriptAlign",
)

app = BUNDLE(
    coll,
    name="ScriptAlign.app",
    icon=None,
    bundle_identifier="app.scriptalign.ScriptAlign",
    info_plist={
        "CFBundleName": "ScriptAlign",
        "CFBundleDisplayName": "ScriptAlign",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "MIT License",
        "LSApplicationCategoryType": "public.app-category.video",
    },
)
