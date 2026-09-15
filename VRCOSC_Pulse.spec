# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    # 使用 SPECPATH（spec 文件所在目录），避免硬编码旧机器路径
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        ('resources/fonts', 'resources/fonts'),
        ('resources/icons', 'resources/icons'),
    ],
    hiddenimports=[
        # Core app packages and modules
        'app',
        'app.main_window',
        'app.ui',
        'app.ui.components',
        'app.ui.widgets',
        'app.ui.layout',
        'app.ui.background',
        'app.ui.animation',
        'app.dialogs',
        'app.dialogs.settings',
        'app.core',
        'app.core.system',
        'app.core.composer',
        'app.core.osc',
        'app.core.state',
        # Utils
        'utils',
        'utils.blur',
        # Plugin system
        'plugins',
        'plugins.base',
        'plugins.manager',
        'plugins.local',
        'plugins.local.hello_plugin',
        'plugins.local.hide_console',
        'plugins.local.pause_on_y',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='VRCOSC Pulse',
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
