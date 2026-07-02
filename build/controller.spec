# PyInstaller spec for the desktop controller app.
#
# Build with:
#   pyinstaller build/controller.spec
#
# (equivalent to running, from the project root:
#   pyinstaller --onefile --windowed --name DiceBotController controller_app.py
# — this spec just pins that same configuration so it's reproducible.)
#
# Output: dist/DiceBotController.exe

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ["../controller_app.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=[
        "gspread",
        "google.oauth2.service_account",
        "discord",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="DiceBotController",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
