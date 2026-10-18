# coding:utf-8
"""识别历史主窗口：列表展示每条识别文字和时间，点击行复制文字到剪贴板。"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

import history_store


class HistoryWindow(QWidget):
    """识别历史窗口，单例：重复调用 show_and_raise 只会激活已有窗口。"""

    def __init__(self, parent=None):
        """构建列表界面：顶部标题栏、中间列表、底部清空按钮。"""
        super().__init__(parent)
        self.setWindowTitle('识别历史')
        self.setMinimumSize(460, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # 顶部：标题 + 刷新按钮
        top = QHBoxLayout()
        title = QLabel('识别历史')
        font = QFont()
        font.setPointSize(11)
        font.setBold(True)
        title.setFont(font)
        top.addWidget(title)
        top.addStretch()
        refresh_btn = QPushButton('刷新')
        refresh_btn.setFixedWidth(56)
        refresh_btn.clicked.connect(self._load)
        top.addWidget(refresh_btn)
        layout.addLayout(top)

        # 提示文字
        self._hint = QLabel('点击任意一条可复制文字')
        self._hint.setStyleSheet('color: #888; font-size: 12px;')
        layout.addWidget(self._hint)

        # 列表
        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.setStyleSheet('''
            QListWidget {
                border: 1px solid #e6e0f5; border-radius: 8px;
                background: #ffffff; color: #2b2350; font-size: 13px;
            }
            QListWidget::item { padding: 6px 8px; border-radius: 6px; }
            QListWidget::item:selected { background: #ece7ff; color: #2b2350; }
            QListWidget::item:hover { background: #f7f4ff; }
        ''')
        self._list.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._list)

        # 底部：清空按钮
        bottom = QHBoxLayout()
        bottom.addStretch()
        clear_btn = QPushButton('清空历史')
        clear_btn.setStyleSheet('QPushButton { color: #c0392b; }')
        clear_btn.clicked.connect(self._clear)
        bottom.addWidget(clear_btn)
        layout.addLayout(bottom)

        self._load()

    def _load(self):
        """从存储加载历史并刷新列表。"""
        self._list.clear()
        entries = history_store.load()
        if not entries:
            placeholder = QListWidgetItem('暂无识别记录')
            placeholder.setForeground(Qt.gray)
            placeholder.setFlags(Qt.NoItemFlags)
            self._list.addItem(placeholder)
            return
        for entry in entries:
            text = entry.get('text', '')
            time_str = entry.get('time', '')
            # 列表项：主文字 + 右对齐时间
            display = text[:60] + ('…' if len(text) > 60 else '')
            item = QListWidgetItem()
            item.setText(display)
            item.setToolTip(text)
            item.setData(Qt.UserRole, text)          # 完整文字用于复制
            item.setData(Qt.UserRole + 1, time_str)
            self._list.addItem(item)
            # 时间标签用 setItemWidget 叠加在右侧
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 4, 0)
            row_layout.addStretch()
            time_label = QLabel(time_str)
            time_label.setStyleSheet('color: #aaa; font-size: 11px;')
            time_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            row_layout.addWidget(time_label)
            self._list.setItemWidget(item, row_widget)

    def _on_item_clicked(self, item):
        """复制完整文字到剪贴板，并短暂显示提示。"""
        text = item.data(Qt.UserRole)
        if not text:
            return
        QApplication.clipboard().setText(text)
        self._hint.setText('已复制！')
        self._hint.setStyleSheet('color: #5b6ef5; font-size: 12px;')
        QTimer.singleShot(1500, lambda: (
            self._hint.setText('点击任意一条可复制文字'),
            self._hint.setStyleSheet('color: #888; font-size: 12px;'),
        ))

    def _clear(self):
        """清空历史文件并刷新列表。"""
        import os
        path = history_store._history_file
        try:
            if os.path.isfile(path):
                os.remove(path)
        except Exception:
            pass
        self._load()

    def show_and_raise(self):
        """显示并激活窗口（已显示时只是置前）。"""
        self.show()
        self.activateWindow()
        self.raise_()
