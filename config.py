# coding:utf-8
r"""
实时语音输入小助手全局配置模块。

职责：
- 维护软件数据目录路径（便携模式：exe/源码同级 data\；目录不可写时回退 %APPDATA%\VoiceInput）。
- 定义默认配置。
- 从 settings.json 加载配置并保存变更。

高级配置（inject_mode 等）直接编辑 settings.json，重启后生效。
"""

import json
import os
import shutil
import sys
from pathlib import Path

# 火山 ASR 协议里的应用标识，仅用于服务端统计，不参与鉴权
APP_ID = 'voice-input'

DEFAULT_CONFIG = {
    'enabled': True,    # 语音输入总开关（托盘菜单可切换）
    'api_key': '',      # 火山引擎 API Key
    'hotkey': '',       # 触发键：空=未配置，mouse:middle / mouse:x1 / key:f8 等
    'inject_mode': 'paste',  # 注入方式：paste=复制粘贴（推荐）/ typing=模拟打字
}

_config = dict(DEFAULT_CONFIG)


def _resolve_data_dir():
    """数据目录：优先 exe（或源码）同级 data\，随软件走、免安装；不可写时回退 %APPDATA%。"""
    if getattr(sys, 'frozen', False):
        # onefile 模式下 sys._MEIPASS 是临时解压目录，必须用 exe 自身所在目录
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    portable = base / 'data'
    try:
        portable.mkdir(parents=True, exist_ok=True)
        probe = portable / '.write_test'
        probe.write_text('', encoding='utf-8')
        probe.unlink()
        return portable
    except Exception:
        # exe 放在只读位置（如 Program Files）时写不了同级目录，回退用户目录
        pass
    fallback = Path(os.environ.get('APPDATA', '~')).expanduser() / 'VoiceInput'
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


DATA_DIR = _resolve_data_dir()
SETTINGS_FILE = DATA_DIR / 'settings.json'
# 旧版本把配置写在 %APPDATA%\VoiceInput\，用于一次性迁移
LEGACY_DATA_DIR = Path(os.environ.get('APPDATA', '~')).expanduser() / 'VoiceInput'


def api_key():
    """返回当前生效的火山 API Key；每轮 ASR 会话建立时动态读取。"""
    return str(_config.get('api_key') or '').strip()


def _migrate_legacy_data():
    """一次性迁移：便携目录缺配置而旧 %APPDATA% 目录里有时，把配置/历史复制过来。"""
    if DATA_DIR == LEGACY_DATA_DIR:
        return
    for name in ('settings.json', 'history.json'):
        src = LEGACY_DATA_DIR / name
        dst = DATA_DIR / name
        if dst.exists() or not src.is_file():
            continue
        try:
            shutil.copy2(src, dst)
        except Exception:
            pass


def load():
    """从 data/settings.json 读取配置，缺失或损坏时回退默认值。"""
    global _config
    _migrate_legacy_data()
    merged = dict(DEFAULT_CONFIG)
    try:
        if SETTINGS_FILE.is_file():
            data = json.loads(SETTINGS_FILE.read_text(encoding='utf-8'))
            if isinstance(data, dict):
                merged.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
    except Exception:
        pass
    _config = merged
    return dict(_config)


def save():
    r"""把当前配置写入数据目录的 settings.json（exe 同级便携目录）。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(_config, ensure_ascii=False, indent=2), encoding='utf-8')


def get(key):
    """读取单个配置项；未加载过时返回默认值。"""
    return _config.get(key, DEFAULT_CONFIG.get(key))


def set_many(values):
    """批量更新配置并落盘；只接受默认配置里存在的键。"""
    for key, value in values.items():
        if key in DEFAULT_CONFIG:
            _config[key] = value
    save()
