# -*- mode: python ; coding: utf-8 -*-
# Build command:
#   python -m PyInstaller --clean -y Step4_Build_Classified_Labels.spec
# Optional debug console:
#   set POKER_TOOL_DEBUG_CONSOLE=1
#   python -m PyInstaller --clean -y Step4_Build_Classified_Labels.spec

import os

DEBUG_CONSOLE = os.environ.get("POKER_TOOL_DEBUG_CONSOLE", "0") == "1"


a = Analysis(
    ['Step4_build_classified_labels.py'],
    pathex=[os.getcwd()],
    binaries=[],
    datas=[],
    hiddenimports=['cv2'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Step4_Build_Classified_Labels',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=DEBUG_CONSOLE,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Step4_Build_Classified_Labels',
)
