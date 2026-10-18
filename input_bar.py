# coding:utf-8
"""语音输入悬浮胶囊。

从 MiniPet 的 VoiceOrbWidget / DailyInputBar 精简而来，只保留语音输入
需要的三个状态：connecting（握手中）/ typing（录音识别中）/ error。
配色直接内联（极光主题），不再依赖主题系统。
"""

import math

from PySide6.QtCore import QEasingCurve, QPoint, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal, Property
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

# 内联的极光主题配色：胶囊背景、边框、文字与点缀色
_COLORS = {
    'bg': (248, 246, 255, 246),
    'border': (168, 148, 255, 238),
    'dot': (130, 100, 255),
    'text': (35, 28, 62, 235),
}
_GLOW = ((255, 255, 255, 112), (215, 200, 255, 55))


class OrbWidget(QWidget):
    """胶囊绘制组件：负责宽度动画、状态图标与识别文本的渲染。"""

    width_changed = Signal()

    def __init__(self, parent=None):
        """初始化尺寸约束与动画状态，默认处于空白 typing 态。"""
        super().__init__(parent)
        self.state = 'typing'   # 当前状态：connecting / typing / error
        self.phase = 0          # 动画相位，由宿主窗口的定时器推进
        self.text = ''          # 球内展示文本
        self.min_orb_width = 40
        self.max_orb_width = 760
        self.orb_height = 40
        self.multiline = False         # 文本超长时切多行布局
        self.icon_area_width = 40      # 左侧状态图标固定占宽
        self.text_right_padding = 12   # 文本右侧留白
        self._orb_width = self.min_orb_width
        self._target_width = self.min_orb_width
        self.width_anim = None
        # 涟漪列表：每项为 progress float 0.0→1.0，营造拾音扩散感
        self._ripples = []
        self._ripple_tick = 0
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.min_orb_width, self.orb_height)

    def get_orb_width(self):
        """Qt Property 读取器：返回当前球体宽度。"""
        return self._orb_width

    def set_orb_width(self, width):
        """Qt Property 写入器：夹取到合法区间后应用宽度并广播变化。"""
        width = int(max(self.min_orb_width, min(self.max_orb_width, width)))
        if self._orb_width == width:
            return
        self._orb_width = width
        self.setFixedWidth(width)
        self.width_changed.emit()
        self.update()

    orbWidth = Property(int, get_orb_width, set_orb_width)

    def set_state(self, state):
        """切换状态；状态变化时相位归零，让新动画从头播放。"""
        if self.state != state:
            self.state = state
            self.phase = 0
        self.update()

    def set_text(self, text):
        """更新展示文本，并按文本内容触发球体宽度动画。"""
        self.text = str(text or '').strip()
        # 超过 35 个字符按多行文本布局（球体高度撑到 64），否则单行省略
        self.multiline = len(self.text) > 35
        self._animate_to_text_width()
        self.update()

    def set_initial_content(self, state, text):
        """重置状态和尺寸，确保上一轮宽度动画不会残留。"""
        self.state = state
        self.phase = 0
        self.text = str(text or '').strip()
        self.multiline = len(self.text) > 35
        if self.width_anim is not None:
            self.width_anim.stop()
            self.width_anim = None
        self.setFixedHeight(64 if self.multiline else self.orb_height)
        self._target_width = self._text_target_width(self.text)
        self._orb_width = self._target_width
        self.setFixedWidth(self._target_width)
        self.update()

    def tick(self):
        """推进一帧动画：相位、涟漪，并请求重绘。"""
        self.phase = (self.phase + 1) % 24
        self._tick_ripples()
        self.update()

    def _tick_ripples(self):
        """推进所有涟漪（progress 0.0→1.0），typing 态按间隔生成新涟漪。"""
        self._ripples = [p + 0.022 for p in self._ripples if p + 0.022 < 1.0]
        if self.state == 'typing':
            self._ripple_tick += 1
            if self._ripple_tick >= 22 and len(self._ripples) < 3:
                self._ripples.append(0.0)
                self._ripple_tick = 0
        else:
            self._ripple_tick = 0

    def _text_font(self):
        """构建球内文字使用的统一字体（雅黑 10pt）。"""
        font = self.font()
        font.setPointSize(10)
        font.setFamily('Microsoft YaHei UI')
        return font

    def _text_target_width(self, text):
        """根据文本计算球体目标宽度：图标区 + 文本宽 + 右侧留白。"""
        if not text:
            return self.min_orb_width
        fm = QFontMetrics(self._text_font())
        if len(text) > 35:
            # 多行文本：只按第一行 35 字符估宽，限制在 [220, 680] 内避免球体过宽
            return self.icon_area_width + 8 + min(680, max(220, fm.horizontalAdvance(text[:35]))) + self.text_right_padding
        target = self.icon_area_width + 8 + fm.horizontalAdvance(text) + self.text_right_padding
        return max(self.min_orb_width, min(self.max_orb_width, target))

    def _animate_to_text_width(self):
        """启动宽度动画；文字变短时用较慢动画避免视觉跳变。"""
        target = self._text_target_width(self.text)
        if abs(target - self._target_width) < 2:
            return
        self._target_width = target
        if self.width_anim is not None:
            self.width_anim.stop()
        self.width_anim = QPropertyAnimation(self, b'orbWidth', self)
        self.width_anim.setDuration(220 if target <= self.min_orb_width else 180)
        self.width_anim.setStartValue(self._orb_width)
        self.width_anim.setEndValue(target)
        self.width_anim.setEasingCurve(QEasingCurve.InOutCubic if target <= self.min_orb_width else QEasingCurve.OutCubic)
        self.width_anim.start()

    def paintEvent(self, event):
        """绘制胶囊底色、材质高光、状态图标和文本。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pill = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg, border = self._background_colors()
        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)
        self._paint_material_glow(painter, pill)

        icon_rect = QRectF(0, 0, self.icon_area_width, self.height()).adjusted(4, 4, -4, -4)
        if self.state == 'typing':
            self._paint_typing(painter, icon_rect)
        elif self.state == 'connecting':
            self._paint_connecting(painter, icon_rect)
        else:
            self._paint_status_dot(painter, icon_rect, QColor(255, 90, 80, 220))
        self._paint_text(painter)

    def _paint_material_glow(self, painter, pill):
        """叠加拟物质感：左上角径向高光渐变 + 顶部弧形反光线 + 内描边。"""
        c0 = QColor(*_GLOW[0])
        c1 = QColor(*_GLOW[1])
        c2 = QColor(c1.red(), c1.green(), c1.blue(), 18)
        inner = QColor(c1.red(), c1.green(), c1.blue(), 40)
        glow = QRadialGradient(QPointF(pill.left() + pill.width() * 0.28, pill.top() + pill.height() * 0.26), max(pill.width(), pill.height()) * 0.78)
        glow.setColorAt(0.0, c0)
        glow.setColorAt(0.45, c1)
        glow.setColorAt(1.0, c2)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(glow))
        painter.drawRoundedRect(pill.adjusted(2, 2, -2, -2), pill.height() / 2, pill.height() / 2)

        painter.setPen(QPen(QColor(255, 255, 255, 86), 1.2))
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(pill.adjusted(7, 6, -7, -7), 42 * 16, 92 * 16)
        painter.setPen(QPen(inner, 1))
        painter.drawRoundedRect(pill.adjusted(3, 3, -3, -3), pill.height() / 2 - 3, pill.height() / 2 - 3)

    def _color(self, key, alpha=None):
        """按 key 取内联配色；三元素元组补充 alpha。"""
        values = _COLORS[key]
        if len(values) == 3:
            values = (*values, 255 if alpha is None else alpha)
        return QColor(*values)

    def _background_colors(self):
        """按状态返回 (背景色, 边框色)：错误和输入态使用特殊边框色提醒用户。"""
        if self.state == 'error':
            return QColor(255, 244, 244, 245), QColor(255, 150, 140, 235)
        if self.state == 'typing':
            return self._color('bg'), QColor(255, 130, 110, 235)
        return self._color('bg'), self._color('border')

    def _paint_text(self, painter):
        """绘制文本：多行自动换行，单行超出宽度时右侧省略。"""
        if not self.text or self.width() <= self.icon_area_width + 10:
            return
        text_rect = QRectF(self.icon_area_width, 0, self.width() - self.icon_area_width - self.text_right_padding, self.height())
        if text_rect.width() <= 8:
            return
        painter.setPen(self._color('text'))
        font = self._text_font()
        painter.setFont(font)
        if self.multiline:
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft | Qt.TextWordWrap, self.text)
        else:
            text = QFontMetrics(font).elidedText(self.text, Qt.ElideRight, int(text_rect.width()))
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)

    def _paint_typing(self, painter, rect):
        """语音输入态：3 根红色系音柱随正弦波起伏，模拟拾音动效。"""
        center_y = rect.center().y()
        bar_count = 3
        bar_w = 3.5
        gap = 3.5
        total_w = bar_count * bar_w + (bar_count - 1) * gap
        start_x = rect.center().x() - total_w / 2
        painter.setPen(Qt.NoPen)
        for i in range(bar_count):
            wave = (math.sin((self.phase + i * 3) * 0.65) + 1) / 2
            height = 6 + wave * 12
            alpha = 180 + int(wave * 55)
            painter.setBrush(QBrush(QColor(255, 85, 75, alpha)))
            x = start_x + i * (bar_w + gap)
            y = center_y - height / 2
            painter.drawRoundedRect(QRectF(x, y, bar_w, height), 1.8, 1.8)

    def _paint_connecting(self, painter, rect):
        """连接中态：琥珀色旋转弧线 + 呼吸圆点，表示握手进行中、还不能识别。"""
        center = rect.center()
        color = QColor(255, 170, 60)
        painter.setPen(QPen(color, 2.3, Qt.SolidLine, Qt.RoundCap))
        painter.setBrush(Qt.NoBrush)
        arc_rect = QRectF(center.x() - 8.5, center.y() - 8.5, 17, 17)
        start = int((self.phase * 30) % 360) * 16
        painter.drawArc(arc_rect, start, 260 * 16)
        pulse = (math.sin(self.phase * 0.5) + 1) / 2
        dot = QColor(color)
        dot.setAlpha(120 + int(pulse * 110))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(dot))
        radius = 3.0 + pulse * 1.2
        painter.drawEllipse(QRectF(center.x() - radius, center.y() - radius, radius * 2, radius * 2))

    def _paint_status_dot(self, painter, rect, color):
        """通用状态圆点：错误态画红色实心点。"""
        center = rect.center()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(QRectF(center.x() - 5, center.y() - 5, 10, 10))


class InputBar(QWidget):
    """语音输入悬浮胶囊窗口：无焦点置顶显示，跟随热键按下位置。"""

    def __init__(self, parent=None):
        """初始化窗口标志、内部绘制组件与动画定时器。"""
        super().__init__(parent)
        self._anchor = None
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # 禁止系统背景：避免首帧未自绘时闪现不透明方块
        self.setAttribute(Qt.WA_NoSystemBackground, True)

        self.orb = OrbWidget(self)
        self.orb.set_initial_content('typing', '')
        self.orb.width_changed.connect(self._sync_geometry)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self.orb.tick)
        # flash_message 的自动隐藏定时器：新一轮录音开始时必须取消，
        # 否则提示到期会把正在录音的胶囊藏掉
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self.hide_bar)
        self._sync_geometry()

    def _sync_geometry(self):
        """根据球体宽度调整独立窗口尺寸，并保持在点击点上方。"""
        height = 64 if self.orb.multiline else 40
        self.setFixedSize(self.orb.width(), height)
        self.orb.setFixedHeight(height)
        self._reposition()

    def _reposition(self):
        """把胶囊定位到触发位置上方，并限制在屏幕范围内。"""
        screen_point = QPoint(*self._anchor) if self._anchor is not None else QApplication.primaryScreen().availableGeometry().center()
        screen = QApplication.screenAt(screen_point) or QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        if self._anchor is None:
            x = geo.left() + (geo.width() - self.width()) // 2
            y = geo.bottom() - self.height() - 48
        else:
            anchor_x, anchor_y = self._anchor
            x = int(anchor_x - self.width() / 2)
            y = int(anchor_y - self.height() - 18)
            x = max(geo.left() + 4, min(x, geo.right() - self.width() - 4))
            y = max(geo.top() + 4, y)
        self.move(x, y)

    def update_text(self, text, connecting=False):
        """更新识别文字并复用球体宽度动画；connecting 态显示握手中的旋转弧线。"""
        self.orb.set_state('connecting' if connecting else 'typing')
        self.orb.set_text(text)
        self._sync_geometry()

    def flash_message(self, text, duration_ms=1600):
        """以错误样式显示一条提示，超时后自动隐藏（用于超时/错误提示）。"""
        self.orb.set_state('error')
        self.orb.set_text(text)
        self._sync_geometry()
        self.show()
        self.raise_()
        # 半透明窗口重show时 DWM 可能先呈现隐藏前的旧缓冲（宽胶囊残留），
        # show 后立即强制重绘，保证首帧就是本次内容，消除"先方后圆"闪烁
        self.repaint()
        self._anim_timer.start(120)
        self._flash_timer.start(duration_ms)

    def show_listening(self, anchor=None):
        """在指定触发坐标上方显示录音胶囊。"""
        self._anchor = anchor
        # 取消挂起的 flash 隐藏：用户已开始新一轮录音，胶囊要持续显示
        self._flash_timer.stop()
        self.orb.set_initial_content('typing', '')
        self._sync_geometry()
        self.show()
        self.raise_()
        self.repaint()
        self._anim_timer.start(120)
        self._reposition()

    def hide_bar(self):
        """隐藏语音输入胶囊并停止动画。"""
        self._anim_timer.stop()
        self.hide()
