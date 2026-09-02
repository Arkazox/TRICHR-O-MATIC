"""A small speech-bubble style popup for contextual help, anchored to a widget.

Unlike QMessageBox this is a lightweight, non-modal Qt::Popup: it appears next
to the widget that triggered it and closes as soon as the user clicks away.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class InfoBubble(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        label = QLabel(text)
        label.setWordWrap(True)
        label.setMaximumWidth(320)
        label.setStyleSheet("color: #f0f0f0; font-size: 12px; background: transparent;")
        layout.addWidget(label)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor(40, 42, 48, 235))
        painter.setPen(QPen(QColor(100, 104, 112), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)

    def show_near(self, anchor: QWidget) -> None:
        self.adjustSize()
        pos = anchor.mapToGlobal(anchor.rect().bottomLeft())
        pos.setX(pos.x() - 10)
        pos.setY(pos.y() + 6)
        self.move(pos)
        self.show()


def show_info_bubble(text: str, anchor: QWidget) -> InfoBubble:
    bubble = InfoBubble(text, anchor)
    bubble.show_near(anchor)
    return bubble
