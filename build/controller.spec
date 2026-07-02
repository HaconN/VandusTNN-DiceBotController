# PyInstaller spec for the desktop controller app.
#
# Build with (from the project root):
#   pyinstaller build/controller.spec
#
# Output: a sibling folder next to the project root, e.g. if this project
# lives at C:\Work\Commu\Vandus\DiscordBot, the exe lands at
# C:\Work\Commu\Vandus\DiceBotController-Release\DiceBotController.exe
# — set below via CONF['distpath'] so no --distpath flag is needed.
# The intermediate build/work cache stays inside the project, in
# build/controller/, same as PyInstaller's own default.

# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.config import CONF

block_cipher = None

# SPECPATH is this file's directory (…/DiscordBot/build), injected by PyInstaller.
PROJECT_ROOT = os.path.dirname(SPECPATH)
RELEASE_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), "DiceBotController-Release")

CONF["workpath"] = os.path.join(PROJECT_ROOT, "build", "controller")
CONF["distpath"] = RELEASE_DIR
os.makedirs(CONF["workpath"], exist_ok=True)
os.makedirs(CONF["distpath"], exist_ok=True)

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
