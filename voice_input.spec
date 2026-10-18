# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for 实时语音输入小助手（裁剪 PySide6 无用模块）

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('app_icon.ico', '.')],
    hiddenimports=[
        'pynput.keyboard._win32',
        'pynput.mouse._win32',
        'sounddevice',
        'websockets',
        'winreg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'PIL', 'cv2',
        # PySide6 用不到的模块
        'PySide6.QtNetwork', 'PySide6.QtQml', 'PySide6.QtQuick',
        'PySide6.QtQuickWidgets', 'PySide6.QtSql', 'PySide6.QtTest',
        'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtWebEngine',
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebSockets', 'PySide6.QtMultimedia',
        'PySide6.QtMultimediaWidgets', 'PySide6.Qt3DCore',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtPositioning', 'PySide6.QtSensors',
        'PySide6.QtSerialPort', 'PySide6.QtStateMachine',
        'PySide6.QtSvgWidgets', 'PySide6.QtVirtualKeyboard',
        'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
        'PySide6.QtXml', 'PySide6.QtConcurrent',
        'PySide6.QtHelp', 'PySide6.QtPrintSupport',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 过滤掉不需要的 PySide6 二进制文件
_EXCLUDE_PATTERNS = [
    'Qt6Quick', 'Qt6Qml', 'Qt6Pdf', 'Qt6Network',
    'Qt6OpenGL', 'Qt6VirtualKeyboard', 'Qt6Multimedia',
    'Qt6WebEngine', 'Qt6Bluetooth', 'Qt6Nfc',
    'Qt6Sensors', 'Qt6SerialPort', 'Qt6StateMachine',
    'Qt6Charts', 'Qt6DataVisualization', 'Qt63D',
    'opengl32sw',       # 19MB 软件渲染 OpenGL
    'Qt6PrintSupport',
]
_EXCLUDE_DATA_PATTERNS = [
    '.qm',              # 所有翻译文件
    'qjpeg', 'qwebp', 'qtiff', 'qgif', 'qicns',  # 图片格式插件（只留 qico）
    'qvirtualkeyboard', 'qpdf',
    'qdirect2d',        # Direct2D 平台插件（保留 qwindows）
]

def _should_exclude_binary(name):
    nl = name.lower()
    return any(p.lower() in nl for p in _EXCLUDE_PATTERNS)

def _should_exclude_data(name):
    nl = name.lower()
    return any(p.lower() in nl for p in _EXCLUDE_DATA_PATTERNS)

a.binaries = [(n, p, t) for n, p, t in a.binaries if not _should_exclude_binary(n)]
a.datas = [(n, p, t) for n, p, t in a.datas if not _should_exclude_data(n)]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='实时语音输入小助手',
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
    icon='app_icon.ico',
)

