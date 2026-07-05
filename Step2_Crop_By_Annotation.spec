# -*- mode: python ; coding: utf-8 -*-
# Build command:
#   python -m PyInstaller --clean -y Step2_Crop_By_Annotation.spec
# Optional debug console:
#   set POKER_TOOL_DEBUG_CONSOLE=1
#   python -m PyInstaller --clean -y Step2_Crop_By_Annotation.spec

import os

DEBUG_CONSOLE = os.environ.get("POKER_TOOL_DEBUG_CONSOLE", "0") == "1"


a = Analysis(
    ['Step2_Crop_by_annotation.py'],
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
    name='Step2_Crop_By_Annotation',
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
    name='Step2_Crop_By_Annotation',
)
