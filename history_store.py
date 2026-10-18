# coding:utf-8
r"""识别历史存储：追加写入数据目录（exe 同级 data\）的 history.json，最多保留 200 条。"""

import json
import os
from datetime import datetime

import config

_MAX_ENTRIES = 200
_history_file = str(config.DATA_DIR / 'history.json')


def _load_raw():
    try:
        if os.path.isfile(_history_file):
            with open(_history_file, encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def append(text):
    """追加一条识别记录（文字 + 当前时间）。"""
    text = (text or '').strip()
    if not text:
        return
    entries = _load_raw()
    entries.append({'text': text, 'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
    if len(entries) > _MAX_ENTRIES:
        entries = entries[-_MAX_ENTRIES:]
    os.makedirs(os.path.dirname(_history_file), exist_ok=True)
    with open(_history_file, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def load():
    """返回历史列表，最新的在前。每项为 {'text': ..., 'time': ...}。"""
    return list(reversed(_load_raw()))
