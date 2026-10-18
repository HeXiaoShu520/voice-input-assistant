# coding:utf-8
"""应用界面主题：全局 QSS 样式表（极光紫，与录音胶囊/通知气泡同一配色）。"""

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
