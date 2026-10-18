# coding:utf-8
"""语音输入控制器。

监听全局热键：第一次按下开始录音，再次按下停止并把识别结果注入
当前焦点输入框。从 MiniPet 的 DailyInputController 精简而来：
去掉了与语音聊天共用的麦克风资源协调、唤醒词互斥和宠物提醒卡片，
只保留录音生命周期与文字注入的业务逻辑。

ASR worker 的生命周期（standby 预连接、closing 隔离、身份过滤）
统一由 AsrRoundPool 管理，本类只负责输入浮窗 UI 与文字注入。
"""

import re

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

import config
import history_store
from asr_client import AsrWorker
from asr_round_pool import AsrRoundPool
from hotkey_trigger import HotkeyTrigger
from input_bar import InputBar
from log_util import get_logger

log = get_logger('voice.input')

# ASR 文本对比时忽略的字符：标点和空白不参与重叠计算
_ASR_IGNORE_RE = re.compile(r'[，,、：:；;。！？!?.\s～~…·]')

# 录音上限与 MiniPet 保持一致：5 分钟
RECORDING_MAX_MS = 5 * 60 * 1000


def _normalize_asr_text(text):
    """去掉标点与空白，用于临时识别与最终结果的重叠对比。"""
    return _ASR_IGNORE_RE.sub('', text or '')


def merge_asr_text(current, final):
    """把停止后到达的 final 识别结果合并进已有文本。

    临时识别与最终结果往往只差标点或个别增量，无条件拼接会造成文本
    翻倍。这里按"归一化后缀/前缀最大重叠"合并，只追加真正新增的部分。
    """
    current = (current or '').strip()
    final = (final or '').strip()
    if not final:
        return current
    if not current:
        return final
    cur_n = _normalize_asr_text(current)
    fin_n = _normalize_asr_text(final)
    if not fin_n:
        return current
    overlap = 0
    for k in range(min(len(cur_n), len(fin_n)), 0, -1):
        if cur_n.endswith(fin_n[:k]):
            overlap = k
            break
    # 把归一化重叠长度映射回 final 的原始下标，保留新增部分的原始标点
    consumed = 0
    idx = 0
    while idx < len(final) and consumed < overlap:
        consumed += len(_ASR_IGNORE_RE.sub('', final[idx]))
        idx += 1
    tail = final[idx:].strip()
    if not tail:
        return current
    if not _ASR_IGNORE_RE.sub('', tail):
        # 尾巴纯是标点（final 原样重发整句时的残留），仅补缺失的句末标点
        if current and current[-1] in '，,、：:；;。！？!?.…～':
            return current
        return current + tail
    return (current + tail).strip()


class VoiceInputController(QObject):

    # 需要托盘气泡通知时发出：(消息文字, 是否警告)
    notify = Signal(str, bool)

    def __init__(self, parent=None):
        """初始化轮次池、悬浮胶囊与录音状态；热键等 apply_settings() 启动。"""
        super().__init__(parent)
        self._input_bar = InputBar()
        self._listener = None
        # ASR worker 生命周期交给轮次池；本类只维护各轮次自己的文本缓冲
        self._pool = AsrRoundPool(
            worker_factory=lambda parent: AsrWorker(parent=parent),
            handlers={
                'status': self._on_status,
                'text': self._on_text_received,
                'final': self._on_final_received,
                'error': self._on_error,
                'finished': self._on_asr_finished,
            },
            parent=self,
        )
        # closing 轮次的文本缓冲：worker → {'text': 已确认文字, 'finals': set()}
        self._closing_rounds = {}
        self._recording = False
        self._last_text = ''
        self._accumulated_text = ''
        self._pending_inject_text = ''
        self._input_anchor = None
        self._record_timeout_timer = QTimer(self)
        self._record_timeout_timer.setSingleShot(True)
        self._record_timeout_timer.timeout.connect(self._on_recording_timeout)
        # 连接超时保底：录音开始后 12 秒未收到 ASR 连接成功则自动报错
        self._connect_timeout_timer = QTimer(self)
        self._connect_timeout_timer.setSingleShot(True)
        self._connect_timeout_timer.timeout.connect(self._on_connect_timeout)

    # 兼容属性：worker 真实状态存于轮次池，这里只做读写转发
    @property
    def _asr_worker(self):
        """当前活跃 ASR worker（可能是待命的 standby）。"""
        return self._pool.active_worker

    @_asr_worker.setter
    def _asr_worker(self, worker):
        self._pool.set_active(worker)

    # ── 设置与热键 ──────────────────────────────────────────────────────

    def apply_settings(self):
        """按配置重建热键监听；总开关关闭时停止；热键变更时重启。"""
        enabled = bool(config.get('enabled'))
        log.info('设置更新 enabled=%s', enabled)
        if not enabled:
            self._stop_listener()
            return
        # 热键变了就重建监听器
        new_hotkey = str(config.get('hotkey') or '').strip()
        current_hotkey = self._listener.hotkey if self._listener is not None else ''
        if self._listener is not None and current_hotkey != new_hotkey:
            self._stop_listener()
        self._ensure_listener()

    def _ensure_listener(self):
        """启动全局热键监听（已启动则跳过；热键未配置则不启动）。"""
        hotkey = str(config.get('hotkey') or '').strip()
        if not hotkey:
            return
        if self._listener is not None:
            return
        self._listener = HotkeyTrigger(hotkey, parent=self)
        self._listener.triggered.connect(self._on_hotkey_toggled)
        self._listener.start()
        log.info('语音输入触发器已启动: %s', hotkey)

    def _stop_listener(self):
        """停止热键监听并关闭录音轮次。"""
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
            log.info('热键监听器已停止')
        self._pool.shutdown()

    # ── 热键触发 ────────────────────────────────────────────────────────

    def _on_hotkey_toggled(self, x, y):
        """热键按下：以光标位置为锚点，切换录音开始/停止。"""
        cursor_pos = QCursor.pos()
        self._input_anchor = (cursor_pos.x(), cursor_pos.y())
        # 若上一次 worker 已结束但没被清理，补清
        if self._asr_worker is not None and not self._asr_worker.isRunning():
            log.info('清理旧录音任务')
            self._pool.discard_active()
            self._recording = False
        if self._recording:
            self._stop_recording()
            return
        self._start_recording()

    # ── 录音生命周期 ─────────────────────────────────────────────────────

    def _start_recording(self):
        """开始一轮录音：无论 standby 是否已连上，都立即进入采集状态。

        worker 未建立时先创建；连接就绪与否由 AsrWorker 内部处理
        （begin_capture 先开麦缓冲，握手完成后自动补发）。
        """
        if not config.api_key():
            log.info('缺少 API Key，无法录音')
            self.notify.emit('请先右键托盘 → 设置，填写 API Key', True)
            return
        # recording 先置 True，防止 worker 一启动就失败时 _on_error 走静默分支
        self._recording = True
        self._last_text = ''
        self._accumulated_text = ''
        # 上一轮 worker 已结束时先丢弃，避免复用已结束的 SAUC 会话
        self._pool.discard_dead_active()
        self._pool.start_recording(self)
        worker = self._pool.active_worker
        connecting = not (worker is not None and worker.is_connected())
        log.info('开始录音' + ('（连接建立中）' if connecting else ''))
        # 直连握手约 200ms，胶囊直接以录音动效小圆出现，不展示"正在连接"文案，
        # 避免弹出→变长→缩回的宽度抖动；连接卡死由 12 秒超时兜底报错
        self._show_input_bar()
        self._record_timeout_timer.start(RECORDING_MAX_MS)
        if connecting:
            self._connect_timeout_timer.start(12000)

    def _stop_recording(self):
        """停止录音：结束轮次并等待服务端最后一批 final 后注入文本。"""
        log.info('停止录音')
        self._record_timeout_timer.stop()
        self._connect_timeout_timer.stop()
        self._recording = False
        self._hide_input_bar()
        # 先保存当前已有的识别文字；停止后服务端可能还会回来最后一批 final，
        # 那部分会在 _on_asr_finished 里追加进来
        self._pending_inject_text = self._accumulated_text or self._last_text
        self._accumulated_text = ''
        worker = self._pool.active_worker
        if worker is not None:
            # 每轮独立连接：结束轮次（finish），文本缓冲归入旧轮；
            # 直连握手仅约 200ms，无需预建下一轮
            self._pool.finish_round(self)
            self._closing_rounds[worker] = {'text': self._pending_inject_text, 'finals': set()}
            # 立即清空，防止停止流程重复触发时把陈旧文本再注入一遍
            self._pending_inject_text = ''
        else:
            self._flush_pending_inject()

    def _on_recording_timeout(self):
        """录音达到 5 分钟上限：自动结束并把已识别内容注入。"""
        if not self._recording:
            return
        text = (self._accumulated_text or self._last_text).strip()
        self._stop_recording()
        self._input_bar.flash_message(
            '已录满 5 分钟，内容已输入' if text else '已录满 5 分钟，未识别到内容',
            duration_ms=2200,
        )

    def _finish_recording(self, reason=''):
        """异常结束（网络错误等）：丢弃缓冲并复位状态。"""
        log.info('录音结束 reason=%s', reason or 'callback')
        self._hide_input_bar()
        self._record_timeout_timer.stop()
        self._connect_timeout_timer.stop()
        self._recording = False
        self._accumulated_text = ''
        self._pool.discard_active()

    def _on_connect_timeout(self):
        """连接超时保底：12 秒内未收到 ASR 响应，强制关闭胶囊并提示。"""
        if not self._recording:
            return
        log.warning('ASR 连接超时')
        self._finish_recording('connect_timeout')
        msg = '连接语音服务超时，请检查网络或 API Key'
        self._input_bar.flash_message(msg, duration_ms=3000)
        self.notify.emit(msg, True)

    def _show_input_bar(self):
        """在热键位置显示录音胶囊：直接进入录音动效，无连接中过渡。"""
        self._input_bar.show_listening(self._input_anchor)

    def _update_input_bar(self, text=''):
        """更新悬浮胶囊中的识别文字。"""
        self._input_bar.update_text(text)

    def _hide_input_bar(self):
        """关闭悬浮胶囊。"""
        self._input_bar.hide_bar()

    # ── ASR 回调 ─────────────────────────────────────────────────────────

    def _on_status(self, worker, text):
        """显示首次连接和开始识别的状态。"""
        if worker is not self._asr_worker or not self._recording:
            return
        if text == 'ASR已连接' and self._recording:
            self._connect_timeout_timer.stop()
            worker.start_recording()
            self._input_bar.update_text('')

    def _on_text_received(self, worker, text):
        """中间识别结果：只接受当前录音 worker，旧 worker 延迟回调一律丢弃。"""
        if not self._recording or worker is not self._asr_worker:
            return
        if text and self._recording:
            self._last_text = text
            self._update_input_bar(text)

    def _on_final_received(self, worker, text):
        """最终识别结果：每个 worker 的结果只写入自己的轮次。"""
        text = (text or '').strip()
        if not text:
            return
        if worker is self._asr_worker:
            merged = merge_asr_text(self._accumulated_text, text)
            if merged != self._accumulated_text:
                self._accumulated_text = merged
                self._update_input_bar(self._accumulated_text)
            return
        round_state = self._closing_rounds.get(worker)
        if round_state is None:
            log.info('忽略旧录音结果: %r', text)
            return
        merged = merge_asr_text(round_state['text'], text)
        if merged != round_state['text']:
            round_state['text'] = merged

    def _on_error(self, worker, text):
        """ASR 错误：closing 轮静默废弃；录音中报错才提示用户。"""
        if worker in self._closing_rounds:
            self._closing_rounds.pop(worker, None)
            return
        if not self._pool.is_active(worker):
            return
        if not self._recording:
            # standby 空闲被服务端断开属正常现象，静默销毁，下次录音前自动重建。
            log.info('standby 连接失效，静默废弃: %s', text)
            self._pool.discard_active()
            return
        log.warning('识别错误: %s', text)
        self._finish_recording('error')
        text = str(text)
        # 401 是最常见的凭证问题，翻译成人话并引导用户去设置
        if '401' in text or 'Unauthorized' in text.lower():
            msg = 'API Key 无效（401），请到托盘设置里更换 API Key'
        elif '403' in text:
            msg = '无权访问该服务（403），请检查 API Key 权限或套餐'
        else:
            msg = '语音服务连接失败：%s' % text[:40]
        self._input_bar.flash_message(msg, duration_ms=2200)
        self.notify.emit(msg, True)

    def _on_asr_finished(self, worker, branch):
        """旧轮收尾完成则注入其文本；当前 worker 结束则复位录音状态。"""
        if worker in self._closing_rounds:
            round_state = self._closing_rounds.pop(worker)
            text = round_state['text']
            if text:
                QTimer.singleShot(80, lambda value=text: self._inject_text(value))
            return
        log.info('识别任务结束 branch=%s recording=%s', branch, self._recording)
        if branch == 'active':
            self._record_timeout_timer.stop()
            self._hide_input_bar()
            self._recording = False
            # standby 空闲死亡后不自动重建，避免空闲期循环握手；下次按热键再按需建连。

    # ── 文字注入 ──────────────────────────────────────────────────────────

    def _flush_pending_inject(self):
        """注入停止时暂存的文本（无 worker 时的兜底路径）。"""
        text = self._pending_inject_text
        self._pending_inject_text = ''
        if text:
            QTimer.singleShot(80, lambda: self._inject_text(text))

    def _inject_text(self, text):
        """把识别文本注入当前焦点输入框（paste=复制粘贴 / typing=模拟打字）。"""
        log.info('输入文字: %r', text)
        history_store.append(text)
        try:
            import time

            from pynput.keyboard import Controller, Key

            mode = config.get('inject_mode') or 'paste'
            if mode == 'typing':
                # 模拟打字：与真实键入最接近，但目标窗口刚激活或中文输入法
                # 挂起时可能吞掉开头字符
                Controller().type(text)
                return
            # 复制粘贴（默认）：中文长文本零丢失，绕开输入法干扰。
            # 粘贴是异步的，稍等目标窗口读取完再把剪贴板还原成用户原有的内容
            clipboard = QApplication.clipboard()
            previous = clipboard.text()
            clipboard.setText(text)
            time.sleep(0.05)
            keyboard = Controller()
            with keyboard.pressed(Key.ctrl):
                keyboard.press('v')
                keyboard.release('v')
            if previous:
                QTimer.singleShot(600, lambda: QApplication.clipboard().setText(previous))
        except Exception as e:
            log.warning('输入失败: %s', e)

    # ── 生命周期 ──────────────────────────────────────────────────────────

    def shutdown(self):
        """应用退出：停监听器，finish 全部 worker（含 closing）并有界等待。"""
        log.info('关闭')
        self._stop_listener()
        self._record_timeout_timer.stop()
        self._hide_input_bar()
        self._recording = False
        self._closing_rounds.clear()
        self._pool.shutdown()
