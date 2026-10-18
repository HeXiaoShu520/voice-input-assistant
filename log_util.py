# coding:utf-8
"""应用日志工具：统一格式与输出，替代散落在各模块的 print 调试输出。

用法：
    from log_util import get_logger
    log = get_logger('voice.chat')
    log.info('进入录音状态')

日志格式：[时间.毫秒] [模块名] 消息，输出到 stdout；
应用入口（main.py）调用 setup_logging() 后全局生效。
"""

import logging
import os
import sys

# 防止重复初始化根 logger 时叠加 handler，导致同一条日志打印多次
_CONFIGURED = False

# 统一日志格式：本地时间精确到毫秒，附带模块名便于过滤
_FORMAT = '[%(asctime)s.%(msecs)03d] [%(name)s] %(message)s'
_DATEFMT = '%Y-%m-%d %H:%M:%S'


def setup_logging(level=logging.INFO):
    """初始化根 logger（幂等，重复调用无副作用）。

    日志同时输出到控制台和滚动文件（pythonw 静默启动时控制台不存在，
    文件是唯一的日志出口）；文件按 1MB 轮转，保留 3 份备份。
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    # 控制台输出统一 UTF-8：GBK 编不了 ✓ 等字符会导致 logging 报错
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            try:
                stream.reconfigure(encoding='utf-8')
            except Exception:
                pass
    formatter = logging.Formatter(_FORMAT, _DATEFMT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root = logging.getLogger()
    root.addHandler(console)

    from logging.handlers import RotatingFileHandler
    import os

    import config

    log_dir = str(config.DATA_DIR / 'logs')
    os.makedirs(log_dir, exist_ok=True)
    file_handler = RotatingFileHandler(os.path.join(log_dir, 'voice_input.log'),
                                       maxBytes=1_000_000, backupCount=3, encoding='utf-8')
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name):
    """返回命名 logger；未初始化时先按默认级别初始化，保证模块可独立运行。"""
    if not _CONFIGURED:
        setup_logging()
    return logging.getLogger(name)
