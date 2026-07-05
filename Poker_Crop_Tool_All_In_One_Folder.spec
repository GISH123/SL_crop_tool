# -*- mode: python ; coding: utf-8 -*-
# Build command:
#   python -m PyInstaller --clean -y Poker_Crop_Tool_All_In_One_Folder.spec
# Debug console build:
#   set POKER_TOOL_DEBUG_CONSOLE=1
#   python -m PyInstaller --clean -y Poker_Crop_Tool_All_In_One_Folder.spec
#
# Output:
#   dist/Poker_Crop_Tool/
#     Step1_Annotation_Tool.exe
#     Step2_Crop_By_Annotation.exe
#     Step3_YOLO11_HTTP_Predict.exe
#     Step4_Build_Classified_Labels.exe
#     _internal/

import os

DEBUG_CONSOLE = os.environ.get("POKER_TOOL_DEBUG_CONSOLE", "0") == "1"
COMMON_HIDDEN_IMPORTS = [
    'cv2',
    'numpy',
    'tkinter',
    'tkinter.filedialog',
    'tkinter.messagebox',
    'tkinter.simpledialog',
    'tkinter.ttk',
]
COMMON_ANALYSIS_KWARGS = dict(
    pathex=[os.getcwd()],
    binaries=[],
    datas=[],
    hiddenimports=COMMON_HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

a1 = Analysis(['Step1_get_poker_annotation.py'], **COMMON_ANALYSIS_KWARGS)
a2 = Analysis(['Step2_Crop_by_annotation.py'], **COMMON_ANALYSIS_KWARGS)
a3 = Analysis(['Step3_YOLO11_HTTP_Predict.py'], **COMMON_ANALYSIS_KWARGS)
a4 = Analysis(['Step4_build_classified_labels.py'], **COMMON_ANALYSIS_KWARGS)

pyz1 = PYZ(a1.pure)
pyz2 = PYZ(a2.pure)
pyz3 = PYZ(a3.pure)
pyz4 = PYZ(a4.pure)

exe1 = EXE(
    pyz1,
    a1.scripts,
    [],
    exclude_binaries=True,
    name='Step1_Annotation_Tool',
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

exe2 = EXE(
    pyz2,
    a2.scripts,
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

exe3 = EXE(
    pyz3,
    a3.scripts,
    [],
    exclude_binaries=True,
    name='Step3_YOLO11_HTTP_Predict',
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

exe4 = EXE(
    pyz4,
    a4.scripts,
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
    exe1,
    exe2,
    exe3,
    exe4,
    a1.binaries,
    a1.datas,
    a2.binaries,
    a2.datas,
    a3.binaries,
    a3.datas,
    a4.binaries,
    a4.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Poker_Crop_Tool',
)
