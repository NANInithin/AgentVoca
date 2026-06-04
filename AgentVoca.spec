# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec file for AgentVoca.
#
# Usage:
#   macOS / Linux:  uv run pyinstaller AgentVoca.spec
#   Windows:        uv run pyinstaller AgentVoca.spec
#
# Output is placed in dist/.
# On macOS a .app bundle is created; on Windows a .exe is created.

import sys
import os
from pathlib import Path

ROOT = Path(SPECPATH)

# Collect faster_whisper data files (ONNX VAD model, tokenizer, etc.)
# PyInstaller does not auto-collect non-Python assets from packages.
import faster_whisper as _fw
FW_ASSETS = os.path.join(os.path.dirname(_fw.__file__), "assets")

block_cipher = None

# Windows version metadata embedded in the .exe (right-click → Properties → Details)
VERSION_FILE = str(ROOT / "version_info.txt")

a = Analysis(
    [str(ROOT / "src" / "agentvoca" / "main.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "config.example.yaml"), "."),
        (str(ROOT / "examples"), "examples"),
        (str(ROOT / "docs"), "docs"),
        # Bundle faster_whisper's ONNX assets (silero VAD model, tokenizer, etc.)
        (FW_ASSETS, "faster_whisper/assets"),
    ],
    hiddenimports=[
        # silero-vad loads models via torch hub; ensure torch is included
        "silero_vad",
        "torch",
        "torchaudio",
        # sounddevice loads PortAudio at runtime
        "sounddevice",
        "_sounddevice_data",
        # faster-whisper / ctranslate2
        "faster_whisper",
        "ctranslate2",
        # PySide6 platform plugins
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        # pynput platform-specific backends
        "pynput.keyboard._win32",
        "pynput.keyboard._darwin",
        "pynput.keyboard._xorg",
        "pynput.mouse._win32",
        "pynput.mouse._darwin",
        "pynput.mouse._xorg",
        # pyautogui platform helpers
        "pyautogui",
        "pyperclip",
        # structlog
        "structlog",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # exclude heavy unused optional backends
        "matplotlib",
        "IPython",
        "jupyter",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

#
# ── macOS .app bundle ───────────────────────────────────────────────────────
#
if sys.platform == "darwin":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="AgentVoca",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="AgentVoca",
    )
    app = BUNDLE(
        coll,
        name="AgentVoca.app",
        icon=None,
        bundle_identifier="com.agentvoca.app",
        info_plist={
            "NSMicrophoneUsageDescription": (
                "AgentVoca captures microphone audio for voice dictation."
            ),
            "NSAccessibilityUsageDescription": (
                "AgentVoca requires accessibility access to simulate keyboard input."
            ),
            "LSUIElement": True,  # background / tray-only app, no Dock icon
        },
    )

#
# ── Windows one-folder build ──────────────────────────────────────────────────
#
# Produces dist/AgentVoca/AgentVoca.exe plus all DLLs/data in the same folder.
# One-folder is easier to debug and less likely to trigger antivirus than a
# single packed .exe. For a release build, change exclude_binaries=True to
# False and remove COLLECT to produce a single .exe instead.
#
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="AgentVoca",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        console=True,   # keep console open so log output is visible during testing
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=None,
        version=VERSION_FILE,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name="AgentVoca",
    )
