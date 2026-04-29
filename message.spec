# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = (
    collect_submodules("textual")
    + collect_submodules("textual_image")
    + collect_submodules("rich")
    + collect_submodules("PIL")
    + [
        "json",
        "os",
        "sys",
        "re",
        "time",
        "secrets",
        "hashlib",
        "sqlite3",
        "atexit",
        "datetime",
        "io",
        "db",
        "auth",
        "screens",
        "utils",
    ]
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("style.tcss", "."),
        ("icon.ico", "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "tkinter",
        "IPython",
        "notebook",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CLI-Message",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="icon.ico",
)