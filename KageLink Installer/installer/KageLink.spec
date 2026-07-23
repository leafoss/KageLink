# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, '..'))
agent = os.path.join(root, 'pc_agent')
datas = [(os.path.join(agent, 'web'), 'web')]
binaries = []
hiddenimports = ['app'] + collect_submodules('pc_agent') + ['win32timezone', 'win32ui', 'win32gui', 'win32api', 'win32con', 'win32process', 'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on']
for package in ['uvicorn', 'fastapi', 'starlette', 'pydantic', 'pydantic_core', 'websockets', 'anyio', 'mss', 'PIL']:
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(agent, 'kagelink_launcher.py')],
    pathex=[agent],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KageLink',
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
    icon=os.path.join(SPECPATH, 'assets', 'kagelink.ico'),
)
