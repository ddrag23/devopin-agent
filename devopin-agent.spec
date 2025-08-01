# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('core', 'core'),
        ('models', 'models'),
    ],
    hiddenimports=[
        'core.config',
        'core.monitor_agent',
        'core.socket_server',
        'core.system',
        'core.service',
        'core.parser',
        'models.data_classes',
        'psutil',
        'yaml',
        'requests',
        'threading',
        'socket',
        'json',
        'logging',
        'signal',
        'sys',
        'time',
        'subprocess',
        'os',
        'pathlib',
        'typing',
        'datetime',
        're',
        'collections',
        'dataclasses',
        'enum',
        'dateutil',
        'dateutil.parser',
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
    name='devopin-agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)