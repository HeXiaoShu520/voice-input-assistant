# coding:utf-8
"""应用界面主题：全局 QSS 样式表与自绘控件（极光紫，与录音胶囊同一配色）。"""

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    """iOS 风格滑动开关：圆角滑轨 + 滑动圆钮，点击整行切换，带滑动动画。"""

    _TRACK_W, _TRACK_H, _KNOB_D, _PAD = 44.0, 22.0, 18.0, 2.0

    def __init__(self, text='', parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setText(text)
        self._knob = 0.0  # 0=关 1=开
        self._anim = QPropertyAnimation(self, b'knob', self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._slide)

    def _slide(self, checked):
        self._anim.stop()
        self._anim.setStartValue(self._knob)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_knob(self):
        return self._knob

    def set_knob(self, value):
        self._knob = float(value)
        self.update()

    knob = Property(float, get_knob, set_knob)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QSize(int(self._TRACK_W + 10 + fm.horizontalAdvance(self.text()) + 4),
                     max(26, fm.height() + 10))

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        h, tw, th, kd, pad = self.height(), self._TRACK_W, self._TRACK_H, self._KNOB_D, self._PAD
        if not self.isEnabled():
            track, knob, text = QColor('#e8e5f2'), QColor('#c9c4dd'), QColor('#b0abc4')
        elif self.isChecked():
            track, knob, text = QColor('#6c5ce7'), QColor('#ffffff'), QColor('#2b2350')
        else:
            track, knob, text = QColor('#d5d0e6'), QColor('#ffffff'), QColor('#2b2350')
        p.setPen(Qt.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(QRectF(0, (h - th) / 2, tw, th), th / 2, th / 2)
        x = pad + self._knob * (tw - kd - 2 * pad)
        p.setBrush(knob)
        p.drawEllipse(QRectF(x, (h - th) / 2 + pad, kd, kd))
        if self.text():
            p.setPen(text)
            p.drawText(QRectF(tw + 10, 0, self.width() - tw - 10, h),
                       Qt.AlignVCenter | Qt.AlignLeft, self.text())


APP_QSS = """
#MainWindow {
    background-color: #f4f2fa;
    font-family: 'Microsoft YaHei UI';
    font-size: 13px;
    color: #2b2350;
}

QLabel { background: transparent; }
QLabel#appTitle { font-size: 17px; font-weight: 600; color: #2b2350; }
QLabel#appSubtitle { color: #8a84a8; font-size: 12px; }
QLabel#sectionTitle { color: #6f6890; font-weight: 600; }

QFrame#card {
    background-color: #ffffff;
    border: 1px solid #e6e0f5;
    border-radius: 12px;
}
QFrame#card QLabel { background: transparent; }

QLabel#statusPill {
    border-radius: 15px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 13px;
}

QComboBox {
    background: #ffffff;
    border: 1px solid #d9d2ee;
    border-radius: 8px;
    padding: 5px 10px;
    min-height: 22px;
    color: #2b2350;
}
QComboBox:hover { border-color: #a99cf0; }
QComboBox:focus { border-color: #7b68ee; }
QComboBox::drop-down { border: none; width: 24px; }
QComboBox QAbstractItemView {
    background: #ffffff;
    border: 1px solid #d9d2ee;
    border-radius: 8px;
    selection-background-color: #ece7ff;
    selection-color: #2b2350;
    outline: 0;
}

QLineEdit {
    background: #ffffff;
    border: 1px solid #d9d2ee;
    border-radius: 8px;
    padding: 6px 10px;
    color: #2b2350;
}
QLineEdit:hover { border-color: #a99cf0; }
QLineEdit:focus { border-color: #7b68ee; }

QPushButton {
    background: #ffffff;
    border: 1px solid #d9d2ee;
    border-radius: 8px;
    padding: 6px 16px;
    color: #2b2350;
}
QPushButton:hover { border-color: #a99cf0; background: #f7f4ff; }
QPushButton:pressed { background: #efe9ff; }
QPushButton:disabled { color: #b0abc4; background: #f2f0f7; border-color: #e6e2f0; }

QPushButton#primary {
    background: #6c5ce7;
    color: #ffffff;
    border: none;
    font-weight: 600;
}
QPushButton#primary:hover { background: #5a4bd1; }
QPushButton#primary:pressed { background: #4d3fc0; }
QPushButton#primary:disabled { background: #c9c2f0; color: #f0edff; }

QPushButton#danger { color: #d63031; }
QPushButton#danger:hover { border-color: #f0a4a4; background: #fff3f3; }

QPushButton#seg { padding: 5px 18px; color: #6f6890; }
QPushButton#seg:checked {
    background: #6c5ce7;
    color: #ffffff;
    border-color: #6c5ce7;
    font-weight: 600;
}
QPushButton#seg:hover:!checked { background: #f7f4ff; }

QCheckBox { spacing: 8px; color: #2b2350; }
QCheckBox::indicator {
    width: 36px;
    height: 20px;
    border-radius: 10px;
    background: #d5d0e6;
}
QCheckBox::indicator:hover { background: #c4bcee; }
QCheckBox::indicator:checked { background: #6c5ce7; }
QCheckBox::indicator:checked:hover { background: #5a4bd1; }
QCheckBox::indicator:disabled { background: #e8e5f2; }

QMenu {
    background: #ffffff;
    border: 1px solid #e0daff;
    border-radius: 10px;
    padding: 6px;
}
QMenu::item { padding: 7px 28px 7px 14px; border-radius: 6px; color: #2b2350; }
QMenu::item:selected { background: #ece7ff; color: #4b3f9e; }
QMenu::separator { height: 1px; background: #eee9fb; margin: 5px 10px; }

QMessageBox { background: #ffffff; }
QMessageBox QLabel { color: #2b2350; }

QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #d5d0e6; border-radius: 4px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""
