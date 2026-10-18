# coding:utf-8
"""Windows 开机自启动管理。

通过注册表 HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 实现：
- 写入/删除当前 exe（或脚本）的路径
- 读取当前是否已启用

使用 HKCU（当前用户）而不是 HKLM（所有用户），不需要管理员权限。
"""

import os
import sys
import winreg
from pathlib import Path

# 注册表启动项键名
_REG_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
_VALUE_NAME = 'VoiceInput'


def _exe_path():
    """返回要写入注册表的启动路径。
    - 已打包为 exe：直接返回 exe 绝对路径
    - 直接运行脚本：返回 pythonw + main.py 的完整命令，静默启动无黑窗
    """
    if getattr(sys, 'frozen', False):
        return str(Path(sys.executable).resolve())
    python = Path(sys.executable)
    # pythonw.exe 静默启动（无控制台窗口）
    pythonw = python.with_name('pythonw.exe')
    if not pythonw.is_file():
        pythonw = python
    main = Path(__file__).resolve().parent / 'main.py'
    return '"%s" "%s"' % (pythonw, main)


def is_enabled():
    """返回当前是否已设置为开机自启动。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, _VALUE_NAME)
        winreg.CloseKey(key)
        return bool(val)
    except FileNotFoundError:
        return False
    except Exception:
        return False


def enable():
    """写入注册表启动项；已存在时覆盖（路径可能因版本更新而变化）。"""
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _exe_path())
    winreg.CloseKey(key)


def disable():
    """删除注册表启动项；不存在时静默忽略。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, _VALUE_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass


def set_enabled(enabled):
    """设置自启动状态；enable=True 写入，False 删除。"""
    if enabled:
        enable()
    else:
        disable()


def _points_to_current():
    """注册表启动项是否存在且指向当前 exe/脚本路径。"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_KEY, 0, winreg.KEY_READ)
        val, _ = winreg.QueryValueEx(key, _VALUE_NAME)
        winreg.CloseKey(key)
    except Exception:
        return False
    current = _exe_path()
    if getattr(sys, 'frozen', False):
        # exe 模式存的是纯路径，按路径规则比较（忽略大小写与分隔符差异）
        return os.path.normcase(os.path.normpath(str(val))) == os.path.normcase(os.path.normpath(current))
    return str(val).strip() == current.strip()


def heal():
    """自启动已开启但注册表路径过期（exe 被挪动过）时，重写为当前路径。

    未开启自启动时不动；返回是否发生了修复，供启动提示使用。
    """
    if is_enabled() and not _points_to_current():
        enable()
        return True
    return False
