# coding:utf-8
"""实时语音输入小助手入口。

托盘常驻 + 主界面程序：
- 双击 exe 打开主界面（开关、触发按键、注入方式、API Key、连接测试）；
  关闭主界面只是最小化到托盘，语音输入继续可用
- 按全局热键（默认鼠标中键）开始/停止录音，识别文字自动注入当前输入框
- 托盘菜单：启用开关、开机自启动、打开主界面、识别历史、退出
"""

import ctypes
import os
import sys

from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget,
)

import autostart
import config
from hotkey_trigger import hotkey_display
from log_util import get_logger, setup_logging
from toast import show_toast
from ui_theme import APP_QSS, ToggleSwitch
from voice_input_controller import VoiceInputController
from history_window import HistoryWindow

log = get_logger('voice.app')

APP_NAME = '实时语音输入小助手'
# 语音服务购买/开通 与 API 密钥管理 的控制台直链
VOLC_ACTIVATE_URL = 'https://console.volcengine.com/speech/new/setting/activate?projectName=default'
VOLC_API_KEY_URL = 'https://console.volcengine.com/speech/new/setting/apikeys?projectName=default'

# 开机自启动以静默方式拉起（只进托盘，不弹主界面）
_TRAY_ARG = '--tray'

# 单实例互斥体名；Local\ 前缀 = 当前登录会话内唯一
_SINGLE_INSTANCE_MUTEX = 'Local\\VoiceInputAssistant'
# 二次启动时用来唤出已运行实例主界面的命名事件
_SHOW_EVENT_NAME = 'Local\\VoiceInputAssistantShow'
_ERROR_ALREADY_EXISTS = 183

_k32 = ctypes.WinDLL('kernel32', use_last_error=True)


def _acquire_single_instance():
    """尝试创建单实例命名互斥体；已有实例在运行时返回 False。

    句柄由系统在进程退出时回收，无需显式释放。
    """
    _k32.CreateMutexW(None, False, _SINGLE_INSTANCE_MUTEX)
    return ctypes.get_last_error() != _ERROR_ALREADY_EXISTS


def _create_show_event():
    """创建（或打开）唤出主界面的命名事件，返回句柄。"""
    return _k32.CreateEventW(None, True, False, _SHOW_EVENT_NAME)


def _signal_show_event():
    """通知已运行的实例显示主界面；成功返回 True。"""
    EVENT_MODIFY_STATE = 0x0002
    handle = _k32.OpenEventW(EVENT_MODIFY_STATE, False, _SHOW_EVENT_NAME)
    if not handle:
        return False
    _k32.SetEvent(handle)
    _k32.CloseHandle(handle)
    return True


def _poll_show_event(handle, callback):
    """事件被触发（有新的二次启动）时调用 callback 并复位事件。"""
    if _k32.WaitForSingleObject(handle, 0) == 0:  # WAIT_OBJECT_0
        _k32.ResetEvent(handle)
        callback()


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

# 文字注入方式：(显示名称, config 值)
_INJECT_OPTIONS = [
    ('复制粘贴（推荐，零丢失）', 'paste'),
    ('模拟打字', 'typing'),
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


def _combo_set_by_data(combo, data):
    """按下拉项的 data 选中对应项；找不到时选第 0 项。"""
    idx = combo.findData(data)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


async def _api_handshake(key):
    """对火山 ASR 端点做一次 WebSocket 握手；成功静默返回，失败抛异常。"""
    import asyncio
    import inspect
    import uuid

    import websockets
    from asr_client import ASR_RESOURCE_ID, ASR_URL

    request_id = str(uuid.uuid4())
    headers = {
        'X-Api-Key': key,
        'X-Api-Resource-Id': ASR_RESOURCE_ID,
        'X-Api-Request-Id': request_id,
        'X-Api-Connect-Id': request_id,
        'X-Api-Sequence': '-1',
    }
    header_arg = ('additional_headers'
                  if 'additional_headers' in inspect.signature(websockets.connect).parameters
                  else 'extra_headers')
    kw = {header_arg: headers, 'ping_interval': None, 'open_timeout': 8}
    if 'proxy' in inspect.signature(websockets.connect).parameters:
        kw['proxy'] = None
    ws = await asyncio.wait_for(websockets.connect(ASR_URL, **kw), timeout=10)
    await ws.close()


class MainWindow(QWidget):
    """主界面：语音输入开关、触发按键、注入方式与 API Key 设置。

    双击 exe 或托盘菜单均可打开；关闭窗口只是最小化到托盘。
    开关类选项改动立即生效；表单字段点「保存设置」后生效。
    """

    # 测试线程 → UI 线程的结果回传：(是否成功, 结果文字)。
    # QTimer.singleShot 在普通 Python 线程里不会触发（没有 Qt 事件循环），
    # 跨线程更新 UI 必须走 Signal 的队列连接。
    _test_done = Signal(bool, str)
    # 开关改动交给 main() 统一处理：写配置、重启监听器、同步托盘菜单
    enabled_toggled = Signal(bool)
    autostart_toggled = Signal(bool)
    quit_requested = Signal()

    def __init__(self, controller, icon, history_window):
        super().__init__()
        self._controller = controller
        self._test_done.connect(self._on_test_done)  # 必须连接：否则测试结果永远到不了界面
        self._force_quit = False  # 真正退出时置 True，让 closeEvent 放行
        self.setObjectName('MainWindow')
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icon)
        self.setMinimumWidth(500)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)

        # ── 标题区 + 页面切换 ─────────────────────────────────────
        header = QHBoxLayout()
        icon_label = QLabel()
        if icon is not None and not icon.isNull():
            icon_label.setPixmap(icon.pixmap(44, 44))
        header.addWidget(icon_label)
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        app_title = QLabel(APP_NAME)
        app_title.setObjectName('appTitle')
        title_col.addWidget(app_title)
        app_subtitle = QLabel('按热键说话，实时出字，自动打进光标处')
        app_subtitle.setObjectName('appSubtitle')
        title_col.addWidget(app_subtitle)
        header.addLayout(title_col)
        header.addStretch(1)

        # 分段开关：设置 / 识别历史 两个可切换页面
        self._seg_group = QButtonGroup(self)
        self._seg_group.setExclusive(True)
        seg_box = QHBoxLayout()
        seg_box.setSpacing(6)
        for page_id, label in ((0, '设置'), (1, '识别历史')):
            btn = QPushButton(label)
            btn.setObjectName('seg')
            btn.setCheckable(True)
            btn.setChecked(page_id == 0)
            self._seg_group.addButton(btn, page_id)
            seg_box.addWidget(btn)
        header.addLayout(seg_box)
        root.addLayout(header)

        # ── 状态胶囊 ──────────────────────────────────────────────
        self._status_label = QLabel('')
        self._status_label.setObjectName('statusPill')
        self._status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        root.addWidget(self._status_label)

        # ── 页面栈：0=设置页 1=识别历史页 ─────────────────────────
        self._stack = QStackedWidget()
        self._seg_group.idClicked.connect(self._stack.setCurrentIndex)

        settings_page = QWidget()
        settings_page.setObjectName('pageSettings')
        page = QVBoxLayout(settings_page)
        page.setContentsMargins(0, 0, 0, 0)
        page.setSpacing(12)

        # ── 基础设置卡片 ──────────────────────────────────────────
        basic_card = QFrame()
        basic_card.setObjectName('card')
        basic = QVBoxLayout(basic_card)
        basic.setContentsMargins(16, 12, 16, 14)
        basic.setSpacing(10)
        basic_title = QLabel('基础设置')
        basic_title.setObjectName('sectionTitle')
        basic.addWidget(basic_title)

        form = QFormLayout()
        form.setSpacing(10)

        self._enabled_check = ToggleSwitch('启用语音输入（关闭后热键无效）')
        self._enabled_check.setChecked(bool(config.get('enabled')))
        self._enabled_check.toggled.connect(self.enabled_toggled.emit)
        form.addRow(self._enabled_check)

        self._autostart_check = ToggleSwitch('开机自动启动（静默启动到托盘）')
        self._autostart_check.setChecked(autostart.is_enabled())
        self._autostart_check.toggled.connect(self.autostart_toggled.emit)
        form.addRow(self._autostart_check)

        self._hotkey_combo = QComboBox()
        for label, value in _HOTKEY_OPTIONS:
            self._hotkey_combo.addItem(label, value)
        _combo_set_by_data(self._hotkey_combo, config.get('hotkey'))
        form.addRow('触发按键：', self._hotkey_combo)

        self._inject_combo = QComboBox()
        for label, value in _INJECT_OPTIONS:
            self._inject_combo.addItem(label, value)
        _combo_set_by_data(self._inject_combo, config.get('inject_mode') or 'paste')
        form.addRow('注入方式：', self._inject_combo)
        basic.addLayout(form)
        page.addWidget(basic_card)

        # ── API Key 卡片 ──────────────────────────────────────────
        key_card = QFrame()
        key_card.setObjectName('card')
        key_layout = QVBoxLayout(key_card)
        key_layout.setContentsMargins(16, 12, 16, 14)
        key_layout.setSpacing(10)
        key_title = QLabel('火山引擎 API Key')
        key_title.setObjectName('sectionTitle')
        key_layout.addWidget(key_title)

        key_hint = QLabel('语音识别使用火山引擎流式 ASR：新用户有免费额度，点下方链接即可直接申请开通，'
                          '再把获取的 API Key 填入下方。')
        key_hint.setWordWrap(True)
        key_layout.addWidget(key_hint)

        link_activate = QPushButton('① 开通语音服务（新人有免费额度，点击直接申请）↗')
        link_activate.setStyleSheet('QPushButton { color: #5b6ef5; border: none; text-align: left; padding: 0; }')
        link_activate.setCursor(Qt.PointingHandCursor)
        link_activate.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(VOLC_ACTIVATE_URL)))
        key_layout.addWidget(link_activate)

        link_btn = QPushButton('② 获取 API Key ↗')
        link_btn.setStyleSheet('QPushButton { color: #5b6ef5; border: none; text-align: left; padding: 0; }')
        link_btn.setCursor(Qt.PointingHandCursor)
        link_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(VOLC_API_KEY_URL)))
        key_layout.addWidget(link_btn)

        key_row = QHBoxLayout()
        self._key_edit = QLineEdit()
        self._key_edit.setPlaceholderText('粘贴 API Key')
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setText(config.api_key())
        key_row.addWidget(self._key_edit)
        self._test_btn = QPushButton('测试连接')
        self._test_btn.setFixedWidth(88)
        self._test_btn.clicked.connect(self._test_connection)
        key_row.addWidget(self._test_btn)

        key_form = QFormLayout()
        key_form.setSpacing(8)
        key_form.addRow('API Key：', key_row)
        key_layout.addLayout(key_form)

        self._test_result = QLabel('')
        self._test_result.setWordWrap(True)
        key_layout.addWidget(self._test_result)
        page.addWidget(key_card)

        # ── 底部按钮 ──────────────────────────────────────────────
        btns = QHBoxLayout()
        btns.addStretch(1)
        quit_btn = QPushButton('退出程序')
        quit_btn.setObjectName('danger')
        quit_btn.clicked.connect(self.quit_requested.emit)
        btns.addWidget(quit_btn)
        save_btn = QPushButton('保存设置')
        save_btn.setObjectName('primary')
        save_btn.setDefault(True)
        save_btn.setFixedWidth(110)
        save_btn.clicked.connect(self._save)
        btns.addWidget(save_btn)
        page.addLayout(btns)

        self._stack.addWidget(settings_page)
        self._stack.addWidget(history_window)  # 识别历史作为第二个页面
        root.addWidget(self._stack)

        self._update_status()

    def _stack_set_page(self, page_id):
        self._stack.setCurrentIndex(page_id)

    # ── 状态与联动 ────────────────────────────────────────────────
    # 状态胶囊的配色：前景/底色/圆点（随状态切换）
    _STATUS_STYLES = {
        'ok': ('#1e8e4e', '#eafaf1'),
        'warn': ('#b9770e', '#fef5e7'),
        'off': ('#6b7280', '#eef0f4'),
    }

    def _update_status(self):
        """顶部状态胶囊：结合开关/密钥/热键告诉用户现在怎么用。"""
        if not config.get('enabled'):
            state = 'off'
            txt = '语音输入当前已停用，勾选上方开关即可恢复'
        elif not config.api_key():
            state = 'warn'
            txt = '还差一步：在下方填写 API Key 并点「保存设置」'
        else:
            state = 'ok'
            txt = ('按%s说话，实时出字；再按一次停止并输入'
                   % hotkey_display(config.get('hotkey') or _HOTKEY_OPTIONS[0][1]))
        fg, bg = self._STATUS_STYLES[state]
        self._status_label.setStyleSheet('QLabel#statusPill { color: %s; background-color: %s; }' % (fg, bg))
        self._status_label.setText('●  ' + txt)

    def sync_enabled_check(self, checked):
        """托盘菜单等外部改动后回写勾选框（不触发 toggled 信号）。"""
        self._enabled_check.blockSignals(True)
        self._enabled_check.setChecked(bool(checked))
        self._enabled_check.blockSignals(False)
        self._update_status()

    def sync_autostart_check(self, checked):
        """注册表写入结果（含失败回退）后回写勾选框。"""
        self._autostart_check.blockSignals(True)
        self._autostart_check.setChecked(bool(checked))
        self._autostart_check.blockSignals(False)

    def _switch_page(self, page_id):
        """切换页面并同步分段按钮状态（用户点击与程序跳转共用）。"""
        self._stack.setCurrentIndex(page_id)
        for b in self._seg_group.buttons():
            b.blockSignals(True)
            b.setChecked(self._seg_group.id(b) == page_id)
            b.blockSignals(False)

    def show_and_raise(self, page=None):
        """显示主界面；page=0 设置页 / 1 识别历史页，None 保持当前页。"""
        if page is not None:
            self._switch_page(page)
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized)
        self.raise_()
        self.activateWindow()
        try:
            # Windows 可能拒绝后台进程抢前台，直接对原生窗口句柄强制置前
            import ctypes
            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        except Exception:
            pass

    def closeEvent(self, event):
        """点 X 只是最小化到托盘；真正退出流程（_force_quit）才放行关闭。"""
        if self._force_quit:
            event.accept()
            return
        event.ignore()
        self.hide()
        show_toast('已最小化到托盘，语音输入继续可用', duration_ms=1500)

    # ── API Key 连接测试 ──────────────────────────────────────────
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
                import asyncio

                import websockets
                log.info('测试连接：开始 (websockets=%s)', getattr(websockets, '__version__', '?'))
                asyncio.run(_api_handshake(key))
                log.info('测试连接：握手成功')
                emit_result(True, '连接成功 ✓')
            except Exception as e:
                log.warning('测试连接失败: %r', e)
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
        self._show_result(text, ok)
        self._test_btn.setEnabled(True)

    def _show_result(self, text, ok):
        if ok is None:
            color = '#888'
        elif ok:
            color = '#27ae60'
        else:
            color = '#c0392b'
        self._test_result.setStyleSheet(f'color: {color}; font-size: 12px;')
        self._test_result.setText(text)

    # ── 保存（表单字段） ──────────────────────────────────────────
    def _save(self):
        """保存 API Key、触发按键与注入方式；热键变更会重启监听器。"""
        old_hotkey = config.get('hotkey')
        config.set_many({
            'api_key': self._key_edit.text().strip(),
            'hotkey': self._hotkey_combo.currentData(),
            'inject_mode': self._inject_combo.currentData(),
        })
        if config.get('hotkey') != old_hotkey:
            self._controller.apply_settings()
        self._update_status()
        show_toast('设置已保存')


def _default_page():
    """启动时主界面默认页：配置齐全 → 识别历史（日常查看）；未配置 → 设置页（引导配置）。"""
    return 1 if (config.api_key() and config.get('hotkey')) else 0


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
    """应用主入口：初始化 Qt、托盘、主界面与控制器，进入事件循环。"""
    setup_logging()
    log.info('启动 %s', APP_NAME)
    config.load()

    # 诊断模式：只跑一次连接测试就退出，用于排查打包环境的网络问题
    if '--selftest' in sys.argv[1:]:
        import asyncio

        try:
            import ssl
            log.info('自检：ssl=%s', ssl.OPENSSL_VERSION)
        except Exception as e:
            log.warning('自检：ssl 导入失败 %r', e)
        try:
            import websockets
            log.info('自检：websockets=%s', getattr(websockets, '__version__', '?'))
        except Exception as e:
            log.warning('自检：websockets 导入失败 %r', e)
        log.info('自检：开始连接测试')
        try:
            asyncio.run(_api_handshake(config.api_key()))
            log.info('自检：连接成功 ✓')
        except Exception as e:
            log.warning('自检：连接失败 %r', e)
        return 0

    # exe 被挪动后注册表自启动路径会过期，启动时顺手修正
    autostart_healed = autostart.heal()
    # 开机自启动（--tray）静默拉起：只进托盘，不弹主界面
    start_minimized = _TRAY_ARG in sys.argv[1:]

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(APP_QSS)

    # ── 单实例锁 ──────────────────────────────────────────────
    if not _acquire_single_instance():
        # 已有实例在运行：唤出它的主界面，然后本进程退出
        activated = _signal_show_event()
        log.warning('已有实例在运行，本次启动退出（唤出主界面%s）', '成功' if activated else '失败')
        show_toast('小助手已在运行，已为你唤出主界面' if activated else '小助手已在运行，无需重复启动',
                   duration_ms=1800)
        QTimer.singleShot(1800, lambda: app.exit(0))
        return app.exec()

    show_event = _create_show_event()

    icon = _make_icon()
    app.setWindowIcon(icon)
    controller = VoiceInputController()

    history_window = HistoryWindow()
    history_window.setWindowIcon(icon)

    # ── 主界面 ────────────────────────────────────────────────
    win = MainWindow(controller, icon, history_window)

    # 监听二次启动的唤出请求：双击 exe 时把已运行实例的主界面弹到最前
    def _on_show_requested():
        log.info('收到二次启动的唤出请求，显示主界面')
        win.show_and_raise(_default_page())

    show_watcher = QTimer(app)
    show_watcher.setInterval(300)
    show_watcher.timeout.connect(lambda: _poll_show_event(show_event, _on_show_requested))
    show_watcher.start()

    # 界面自检：固定间隔状态机，逐步验证 测试连接 → 历史页 → 托盘双击
    if '--uitest' in sys.argv[1:]:
        uitest_step = {'n': 0}

        def uitest_tick():
            n = uitest_step['n']
            uitest_step['n'] = n + 1
            if n == 0:
                log.info('UITEST[0] 触发测试连接')
                win._test_connection()
            elif n == 2:
                log.info('UITEST[2] 结果=%r 按钮可用=%s',
                         win._test_result.text(), win._test_btn.isEnabled())
                log.info('UITEST[2] 切换到识别历史页')
                win._switch_page(1)
            elif n == 4:
                log.info('UITEST[4] 历史页可见=%s 当前页=%s',
                         history_window.isVisible(), win._stack.currentIndex())
                log.info('UITEST[4] 模拟托盘双击')
                tray.activated.emit(QSystemTrayIcon.DoubleClick)
            elif n == 6:
                log.info('UITEST[6] 托盘双击后 主界面可见=%s 当前页=%s',
                         win.isVisible(), win._stack.currentIndex())
                log.info('UITEST 完成')
                app.exit(0)

        tick = QTimer(app)
        tick.setInterval(700)
        tick.timeout.connect(uitest_tick)
        tick.start()
        QTimer.singleShot(25000, lambda: app.exit(1))  # 保底退出

    # ── 托盘 ──────────────────────────────────────────────────
    tray = QSystemTrayIcon(icon)
    tray.setToolTip(APP_NAME)

    # 提示统一走自绘 toast：系统通知被关掉时托盘气泡会静默失效
    controller.notify.connect(show_toast)

    menu = QMenu()

    # 启用开关：托盘与主界面两处入口，逻辑集中在这一个处理函数
    toggle_action = QAction('启用语音输入', menu, checkable=True)
    toggle_action.setChecked(bool(config.get('enabled')))

    def on_enabled_changed(checked):
        config.set_many({'enabled': bool(checked)})
        controller.apply_settings()
        show_toast('语音输入已' + ('启用' if checked else '停用'))
        toggle_action.blockSignals(True)
        toggle_action.setChecked(bool(checked))
        toggle_action.blockSignals(False)
        win.sync_enabled_check(checked)

    toggle_action.toggled.connect(on_enabled_changed)
    win.enabled_toggled.connect(on_enabled_changed)
    menu.addAction(toggle_action)

    # 开机自启动：同样是托盘/主界面两处入口
    autostart_action = QAction('开机自动启动', menu, checkable=True)
    autostart_action.setChecked(autostart.is_enabled())

    def on_autostart_changed(checked):
        try:
            autostart.set_enabled(checked)
            show_toast('开机自启动已' + ('开启' if checked else '关闭'))
        except Exception as e:
            show_toast('设置失败：%s' % str(e)[:60], warning=True)
            checked = not checked
        autostart_action.blockSignals(True)
        autostart_action.setChecked(bool(checked))
        autostart_action.blockSignals(False)
        win.sync_autostart_check(checked)

    autostart_action.toggled.connect(on_autostart_changed)
    win.autostart_toggled.connect(on_autostart_changed)
    menu.addAction(autostart_action)

    menu.addSeparator()

    main_window_action = QAction('打开主界面…', menu)
    main_window_action.triggered.connect(lambda: win.show_and_raise())
    menu.addAction(main_window_action)

    menu.addSeparator()

    # 单击/双击托盘图标：打开主界面（设置页）；历史页在主界面里切换
    def on_tray_activated(reason):
        # PySide6 6.11 的 reason 是 ActivationReason 枚举，不能 int()，
        # 否则槽函数抛 TypeError，托盘点击就"没有任何反应"
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            win.show_and_raise(0)

    tray.activated.connect(on_tray_activated)

    menu.addSeparator()

    quit_action = QAction('退出', menu)

    def on_quit():
        """托盘/主界面退出：确认后停掉控制器，托盘图标先消失，短暂提示再退出。"""
        if not _confirm_exit():
            return
        log.info('托盘退出')
        controller.shutdown()
        tray.hide()
        win._force_quit = True  # 让主窗口 closeEvent 放行，quit 不被"最小化到托盘"否决
        win.hide()
        show_toast('已退出', duration_ms=1200)
        # 注意用 exit(0)：Qt 6.9+ 的 quit() 会被拒绝关闭的窗口否决，导致进程不退出
        QTimer.singleShot(1300, lambda: app.exit(0))

    quit_action.triggered.connect(on_quit)
    win.quit_requested.connect(on_quit)
    menu.addAction(quit_action)

    tray.setContextMenu(menu)
    tray.show()

    # 双击 exe / 手动启动：弹出主界面（配置过默认看识别历史，没配置默认进设置）；
    # 开机自启动静默进托盘
    if not start_minimized:
        win.show_and_raise(_default_page())

    # 配置齐全则气泡提示一次用法；exe 挪动后自启动路径已修正时一并告知
    if config.api_key() and config.get('hotkey'):
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
