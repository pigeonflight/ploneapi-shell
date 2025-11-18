# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Plone API Shell Streamlit app.
"""

import sys
from pathlib import Path

# Get the project root directory
project_root = Path(SPECPATH).parent

# Collect all data files needed
media_path = project_root / "media"
ploneapi_path = project_root / "ploneapi_shell"

datas = []
if media_path.exists():
    datas.append((str(media_path), "media"))
if ploneapi_path.exists():
    # Include the entire ploneapi_shell package as data
    # This ensures web.py and other files are available
    datas.append((str(ploneapi_path), "ploneapi_shell"))

# Hidden imports that PyInstaller might miss
hiddenimports = [
    'streamlit',
    'streamlit.web.cli',
    'streamlit.runtime.scriptrunner',
    'streamlit.runtime.state',
    'streamlit.runtime.caching',
    'streamlit.components.v1',
    'ploneapi_shell',
    'ploneapi_shell.api',
    'ploneapi_shell.web',
    'httpx',
    'typer',
    'rich',
    'prompt_toolkit',
    'thefuzz',
    'pandas',
    'altair',
    'plotly',
    'pyarrow',
    'tornado',
    'watchdog',
    'click',
    'pyyaml',
    'toml',
    'protobuf',
    'numpy',
    'pillow',
    'blinker',
    'cachetools',
    'packaging',
    'python-dateutil',
    'pytz',
]

a = Analysis(
    ['ploneapi_shell/streamlit_launcher.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# Get code signing identity from environment variable or use None
import os
codesign_identity = os.environ.get('CODESIGN_IDENTITY', None)
entitlements_file = os.environ.get('ENTITLEMENTS_FILE', None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PloneAPIShell',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Set to False for windowed app, True for console
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=codesign_identity,
    entitlements_file=entitlements_file,
    icon=str(project_root / "media" / "plone-logo.icns") if (project_root / "media" / "plone-logo.icns").exists() else None,
)

# Create macOS app bundle
app = BUNDLE(
    exe,
    name='PloneAPIShell.app',
    icon=str(project_root / "media" / "plone-logo.icns") if (project_root / "media" / "plone-logo.icns").exists() else None,
    bundle_identifier='com.ploneapi.shell',
    codesign_identity=codesign_identity,
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '0.1.7',
        'CFBundleVersion': '0.1.7',
        'NSHumanReadableCopyright': 'Copyright © 2025 David Bain',
        'LSMinimumSystemVersion': '10.13',
    },
)

