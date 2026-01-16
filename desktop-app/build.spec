# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Gmail Email Cleanmail Desktop App
Run with: pyinstaller build.spec
"""

import sys
from pathlib import Path

block_cipher = None

# Get the absolute path to the project
project_path = Path(SPECPATH)

a = Analysis(
    ['run.py'],
    pathex=[str(project_path)],
    binaries=[],
    datas=[
        # Include config and data directories
        ('config', 'config'),
        ('data', 'data'),
    ],
    hiddenimports=[
        'google.auth',
        'google.auth.transport.requests',
        'google.oauth2.credentials',
        'google_auth_oauthlib.flow',
        'googleapiclient.discovery',
        'googleapiclient.errors',
        'PySide6',
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
    name='GmailEmailCleanmail',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you have one
)
