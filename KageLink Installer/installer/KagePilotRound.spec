# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

root = os.path.abspath(os.path.join(SPECPATH, '..'))
agent = os.path.join(root, 'pc_agent')
datas = [
    (
        os.path.join(agent, 'config', 'kage_pilot_combat_target.json'),
        'config',
    ),
]
binaries = []
hiddenimports = collect_submodules('pc_agent') + [
    'kage_pilot_visual_return',
    'win32timezone',
    'win32ui',
    'win32gui',
    'win32api',
    'win32con',
    'win32process',
]

# Runtime hooks for numpy/OpenCV/Pillow are sufficient. collect_all() pulled in
# large test and development trees that were extracted on every round start,
# extending the post-OK interval while the opponent was already attacking.
a = Analysis(
    [os.path.join(agent, 'kage_pilot_round.py')],
    pathex=[agent],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy.tests',
        'numpy.testing.tests',
        'numpy.distutils',
        'numpy.f2py.tests',
        'PIL.ImageQt',
        'tkinter.test',
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KagePilotRound',
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
    icon=os.path.join(SPECPATH, 'assets', 'kagelink.ico'),
)
