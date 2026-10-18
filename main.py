# coding:utf-8
"""实时语音输入小助手入口。

纯托盘程序：
- 按全局热键（默认鼠标中键）开始/停止录音，识别文字自动注入当前输入框
- 托盘菜单：启用开关、开机自启动、设置、退出
- 设置窗口：API Key 输入框、热键选择、跳转火山控制台链接
"""

import ctypes
import os
import sys

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QSystemTrayIcon, QVBoxLayout, QWidget,
)

import autostart
import config
from hotkey_trigger import hotkey_display
from log_util import get_logger, setup_logging
from toast import show_toast
from voice_input_controller import VoiceInputController
from history_window import HistoryWindow

log = get_logger('voice.app')

APP_NAME = '实时语音输入小助手'
VOLC_API_KEY_URL = 'https://console.volcengine.com/iam/keymanage/'

# 单实例互斥体名；Local\ 前缀 = 当前登录会话内唯一
_SINGLE_INSTANCE_MUTEX = 'Local\\VoiceInputAssistant'
_ERROR_ALREADY_EXISTS = 183

_k32 = ctypes.WinDLL('kernel32', use_last_error=True)


def _acquire_single_instance():
    """尝试创建单实例命名互斥体；已有实例在运行时返回 False。

    句柄由系统在进程退出时回收，无需显式释放。
    """
    _k32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX)
    return ctypes.get_last_error() != _ERROR_ALREADY_EXISTS

# 可选热键列表：(显示名称, config 值)
_HOTKEY_OPTIONS = [
    ('鼠标中键（推荐）', 'mouse:middle'),
    ('鼠标侧键1（后退键）', 'mouse:x1'),
    ('鼠标侧键2（前进键）', 'mouse:x2'),
    ('右Alt', 'key:alt_r'),
    ('F8', 'key:f8'),
    ('F9', 'key:f9'),
    ('F10', 'key:f10'),
]


def _make_icon():
    """加载打包内置的头像图标；找不到时回退到纯色圆形。"""
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    ico_path = os.path.join(base, 'app_icon.ico')
    if os.path.isfile(ico_path):
        return QIcon(ico_path)
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(120, 100, 255))
    painter.drawEllipse(4, 4, 56, 56)
    painter.end()
    return QIcon(pixmap)


class SettingsDialog(QDialog):
    """设置弹窗：API Key 输入、热键选择、跳转火山控制台、测试连接。"""

    # 测试线程 → UI 线程的结果回传：(是否成功, 结果文字)。
    # QTimer.singleShot 在普通 Python 线程里不会触发（没有 Qt 事件循环），
    # 跨线程更新 UI 必须走 Signal 的队列连接。
    _test_done = Signal(bool, str)

    def __init__(self, parent=None):
        """搭建表单：说明文字、链接按钮、API Key 输入框、热键下拉、测试/保存/取消。"""
        super().__init__(parent)
        self._test_done.connect(self._on_test_done)
        self.setWindowTitle(APP_NAME + ' — 设置')
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setMinimumWidth(440)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        hint = QLabel('语音识别使用火山引擎 ASR，需要填写 API Key。')
        hint.setWordWrap(True)
        layout.addWidget(hint)

        link_btn = QPushButton('去火山控制台获取 API Key ↗')
        link_btn.setStyleSheet('QPushButton { color: #5b6ef5; border: none; text-align: left; padding: 0; }')
        link_btn.setCursor(Qt.PointingHandCursor)
        link_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(VOLC_API_KEY_URL)))
        layout.addWidget(link_btn)

        form = QFormLayout()
        form.setSpacing(8)

        # API Key 行：输入框 + 测试按钮并排
        key_widget = QWidget()
        key_row = QHBoxLayout(key_widget)
        key_row.setContentsMargins(0, 0, 0, 0)
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText('粘贴 API Key')
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setText(config.api_key())
        key_row.addWidget(self._key_edit)
        self._test_btn = QPushButton('测试连接')
        self._test_btn.setFixedWidth(80)
        self._test_btn.clicked.connect(self._test_connection)
        key_row.addWidget(self._test_btn)
        form.addRow('API Key：', key_widget)

        # 测试结果标签
        self._test_result = QLabel('')
        self._test_result.setWordWrap(True)
        form.addRow('', self._test_result)

        self._hotkey_combo = QComboBox()
        self._hotkey_combo.addItem('未配置', '')
        current_hotkey = config.get('hotkey') or ''
        selected_idx = 0
        for i, (label, value) in enumerate(_HOTKEY_OPTIONS):
            self._hotkey_combo.addItem(label, value)
            if value == current_hotkey:
                selected_idx = i + 1
        self._hotkey_combo.setCurrentIndex(selected_idx)
        form.addRow('触发按键：', self._hotkey_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('保存')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _test_connection(self):
        """用当前填写的 API Key 测试 WebSocket 握手，显示结果。"""
        import threading
        key = self._key_edit.text().strip()
        if not key:
            self._show_result('请先填写 API Key', ok=False)
            return
        self._test_btn.setEnabled(False)
        self._show_result('连接中…', ok=None)

        def emit_result(ok, text):
            # 窗口可能在测试结束前被关闭销毁，此时静默放弃结果
            try:
                self._test_done.emit(ok, text)
            except RuntimeError:
                pass

        def do_test():
            try:
                import asyncio, inspect

                import websockets
                from asr_client import ASR_URL, AsrSession

                async def _ping():
                    # 待测 key 通过参数进入请求头，不改动全局配置
                    header_arg = ('additional_headers'
                                  if 'additional_headers' in inspect.signature(websockets.connect).parameters
                                  else 'extra_headers')
                    sess = AsrSession(text_cb=lambda x: None, final_cb=lambda x: None,
                                      status_cb=lambda x: None, error_cb=lambda x: None)
                    kw = {header_arg: sess._headers(key), 'ping_interval': None, 'open_timeout': 8}
                    if 'proxy' in inspect.signature(websockets.connect).parameters:
                        kw['proxy'] = None
                    ws = await asyncio.wait_for(websockets.connect(ASR_URL, **kw), timeout=10)
                    await ws.close()

                asyncio.run(_ping())
                emit_result(True, '连接成功 ✓')
            except Exception as e:
                msg = str(e)
                if '401' in msg or 'Unauthorized' in msg.lower():
                    msg = 'API Key 无效（401 未授权）'
                elif 'timeout' in msg.lower() or 'TimeoutError' in type(e).__name__:
                    msg = '连接超时，请检查网络'
                else:
                    msg = '连接失败：' + msg[:60]
                emit_result(False, msg)

        threading.Thread(target=do_test, daemon=True).start()

    def _on_test_done(self, ok, text):
        """主线程接收测试结果：更新提示文字并恢复按钮。"""
        self._show_result(text, ok)
        self._test_btn.setEnabled(True)

    def _show_result(self, text, ok):
        """更新测试结果标签样式。"""
        if ok is None:
            color = '#888'
        elif ok:
            color = '#27ae60'
        else:
            color = '#c0392b'
        self._test_result.setStyleSheet(f'color: {color}; font-size: 12px;')
        self._test_result.setText(text)

    def _save(self):
        """保存 API Key 与热键配置并关闭窗口。"""
        key = self._key_edit.text().strip()
        hotkey = self._hotkey_combo.currentData()
        config.set_many({'api_key': key, 'hotkey': hotkey})
        self.accept()


def _confirm_exit():
    """弹退出确认框；返回 True 表示用户确认退出。"""
    box = QMessageBox()
    box.setIcon(QMessageBox.Question)
    box.setWindowTitle(APP_NAME)
    box.setText('确定要退出%s吗？退出后按热键将无法语音输入。' % APP_NAME)
    quit_btn = box.addButton('退出', QMessageBox.AcceptRole)
    box.addButton('取消', QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is quit_btn


def main():
    """应用主入口：初始化 Qt、托盘与控制器，进入事件循环。"""
    setup_logging()
    log.info('启动 %s', APP_NAME)
    config.load()
    # exe 被挪动后注册表自启动路径会过期，启动时顺手修正
    autostart_healed = autostart.heal()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # ── 单实例锁 ──────────────────────────────────────────────────────
    if not _acquire_single_instance():
        log.warning('已有实例在运行，本次启动退出')
        show_toast('小助手已在运行，无需重复启动', duration_ms=1800)
        QTimer.singleShot(2000, app.quit)
        return app.exec()

    icon = _make_icon()
    app.setWindowIcon(icon)
    controller = VoiceInputController()

    # ── 托盘 ──────────────────────────────────────────────────────────
    tray = QSystemTrayIcon(icon)
    tray.setToolTip(APP_NAME)

    # 提示统一走自绘 toast：系统通知被关掉时托盘气泡会静默失效
    controller.notify.connect(show_toast)

    menu = QMenu()

    toggle_action = QAction('启用语音输入', menu, checkable=True)
    toggle_action.setChecked(bool(config.get('enabled')))

    def on_toggled(checked):
        config.set_many({'enabled': bool(checked)})
        controller.apply_settings()
        show_toast('语音输入已' + ('启用' if checked else '停用'))

    toggle_action.toggled.connect(on_toggled)
    menu.addAction(toggle_action)

    autostart_action = QAction('开机自动启动', menu, checkable=True)
    autostart_action.setChecked(autostart.is_enabled())

    def on_autostart_toggled(checked):
        try:
            autostart.set_enabled(checked)
            show_toast('开机自启动已' + ('开启' if checked else '关闭'))
        except Exception as e:
            autostart_action.setChecked(not checked)
            show_toast('设置失败：%s' % str(e)[:60], warning=True)

    autostart_action.toggled.connect(on_autostart_toggled)
    menu.addAction(autostart_action)

    menu.addSeparator()

    settings_action = QAction('设置…', menu)

    def on_settings():
        old_hotkey = config.get('hotkey')
        dlg = SettingsDialog()
        dlg.setWindowIcon(icon)
        if dlg.exec() == QDialog.Accepted:
            # 热键变了需要重启监听器
            if config.get('hotkey') != old_hotkey:
                controller.apply_settings()
            show_toast('设置已保存')

    settings_action.triggered.connect(on_settings)
    menu.addAction(settings_action)

    menu.addSeparator()

    history_window = HistoryWindow()
    history_window.setWindowIcon(icon)

    history_action = QAction('识别历史…', menu)
    history_action.triggered.connect(history_window.show_and_raise)
    menu.addAction(history_action)

    # 双击托盘图标也打开历史窗口
    def on_tray_activated(reason):
        # Windows 上 reason 是 int，DoubleClick=2，Trigger(单击)=3
        if int(reason) in (2, 3):
            history_window.show_and_raise()

    tray.activated.connect(on_tray_activated)

    menu.addSeparator()

    quit_action = QAction('退出', menu)

    def on_quit():
        """托盘退出：确认后停掉控制器，托盘图标先消失，短暂提示再退出。"""
        if not _confirm_exit():
            return
        log.info('托盘退出')
        controller.shutdown()
        tray.hide()
        show_toast('已退出', duration_ms=1200)
        QTimer.singleShot(1300, app.quit)

    quit_action.triggered.connect(on_quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()

    # 没配置时直接打开设置窗口；配置齐全则用自绘气泡提示一次用法，
    # 避免静默启动让人以为没启动成功（系统通知关闭时托盘气泡弹不出来）
    if not config.api_key() or not config.get('hotkey'):
        QTimer.singleShot(300, on_settings)
    else:
        def show_startup_tip():
            tip = '已启动：按%s开始语音输入，再按一次停止' % hotkey_display(config.get('hotkey'))
            if autostart_healed:
                tip = '开机自启动路径已随 exe 位置更新。' + tip
            show_toast(tip)
        QTimer.singleShot(600, show_startup_tip)

    controller.apply_settings()
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
