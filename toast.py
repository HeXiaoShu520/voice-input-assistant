# coding:utf-8
"""应用自绘的通知气泡。

Windows 系统通知被关闭时（ToastEnabled=0），托盘 showMessage 会静默失效，
所以所有提示统一走本模块的悬浮胶囊：置顶、不抢焦点、超时自动消失，
视觉上与输入胶囊（input_bar）同一套极光配色。
"""

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

_BG = QColor(248, 246, 255, 246)
_BORDER = QColor(168, 148, 255, 238)
_TEXT = QColor(35, 28, 62, 235)
_ACCENT = QColor(130, 100, 255)
_WARN_BG = QColor(255, 244, 244, 245)
_WARN_BORDER = QColor(255, 150, 140, 235)
_WARN_ACCENT = QColor(255, 90, 80, 220)

_ICON_AREA = 24      # 左侧状态圆点占宽
_PADDING_H = 16      # 左右内边距
_HEIGHT = 40
_MAX_WIDTH = 460     # 单行超宽时省略，避免横贯整个屏幕
_BOTTOM_GAP = 56     # 距屏幕底边（任务栏上方）的距离
_EDGE_MARGIN = 12


class _ToastWindow(QWidget):
    """无边框置顶胶囊：显示一条通知，超时后自动隐藏。"""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint |
            Qt.Tool | Qt.WindowDoesNotAcceptFocus | Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self._text = ''
        self._warning = False
        self._font = self.font()
        self._font.setFamily('Microsoft YaHei UI')
        self._font.setPointSize(10)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_message(self, text, warning=False, duration_ms=3000):
        """显示一条通知；重复调用会替换内容并重新计时。"""
        self._text = str(text or '').strip()
        self._warning = bool(warning)
        fm = QFontMetrics(self._font)
        width = _ICON_AREA + _PADDING_H * 2 + min(fm.horizontalAdvance(self._text), _MAX_WIDTH)
        self.setFixedSize(max(width, 120), _HEIGHT)
        self._reposition()
        self.show()
        self.raise_()
        self.repaint()  # 强制首帧即新内容，避免 DWM 呈现旧缓冲
        self._hide_timer.start(duration_ms)

    def _reposition(self):
        """固定在主屏幕底部居中（任务栏上方），视线更容易注意到。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(geo.center().x() - self.width() // 2,
                  geo.bottom() - self.height() - _BOTTOM_GAP)

    def paintEvent(self, event):
        """绘制胶囊底色、左侧状态圆点与文本。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        pill = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = _WARN_BG if self._warning else _BG
        border = _WARN_BORDER if self._warning else _BORDER
        painter.setPen(QPen(border, 1))
        painter.setBrush(QBrush(bg))
        painter.drawRoundedRect(pill, pill.height() / 2, pill.height() / 2)

        # 左侧状态圆点：普通=紫色点缀，警告=红色
        dot_center = pill.center()
        dot_center.setX(pill.left() + _PADDING_H + 4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(_WARN_ACCENT if self._warning else _ACCENT))
        painter.drawEllipse(dot_center, 4.5, 4.5)

        text_rect = QRectF(pill.left() + _ICON_AREA, 0,
                           pill.width() - _ICON_AREA - _PADDING_H, pill.height())
        painter.setPen(_TEXT)
        painter.setFont(self._font)
        text = QFontMetrics(self._font).elidedText(self._text, Qt.ElideRight, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)


_toast = None


def show_toast(text, warning=False, duration_ms=3000):
    """模块级入口：在主屏幕右下角弹出一条自绘通知。"""
    global _toast
    if _toast is None:
        _toast = _ToastWindow()
    _toast.show_message(text, warning=warning, duration_ms=duration_ms)
