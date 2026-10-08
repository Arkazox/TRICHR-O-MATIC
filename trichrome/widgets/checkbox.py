"""Custom-painted QCheckBox and QRadioButton whose indicators read clearly
against a dark panel. The native indicator (flat single-colour fill, thin
border, the system accent colour) is low-contrast, easy to miss next to its
own label and ignores the app's accent; this fixes that without an SVG asset:

- The indicator's size follows its label's text size (QFontMetrics
  capHeight), so a smaller label font gets a smaller indicator, and the gap
  between indicator and label (about 0.7 cap height) scales with it.
- The fill is a subtle top-to-bottom qlineargradient: a muted grey when
  unchecked, a shade lighter than ACCENT fading down to ACCENT when checked.
- The drop shadow QSS can't draw (no box-shadow) is hand-painted: a few
  translucent black shapes, offset a touch down, painted *before* the real
  indicator so only their edges show past it.
- The mark is painted at fixed fractions of the indicator rect, so it scales
  with it: a two-line checkmark for CheckBox, a centred dot for RadioButton.
  Both share everything else; the radio is just round.

The indicator QSS lives in each instance's own stylesheet (there is no
app-wide one). setStyleSheet() is overridden so a caller's own rules (label
colour, font size) are kept and the indicator rules appended to them.
Radios styled as framed tiles (hidden indicator) stay plain QRadioButtons."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QCheckBox, QRadioButton, QStyle, QStyleOptionButton

ACCENT = "#5b9bd5"
ACCENT_LIGHT = "#6fa9de"  # a shade lighter than ACCENT, the checked gradient's top stop

_INDICATOR_QSS = (
    "{cls} {{ spacing: {spacing}px; }} "
    "{cls}::indicator {{ width: {size}px; height: {size}px; border-radius: {radius}px; border: none;"
    " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
    " stop:0 rgba(127, 127, 127, 100), stop:1 rgba(127, 127, 127, 60)); }}"
    " {cls}::indicator:checked {{"
    " background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
    " stop:0 {light}, stop:1 {accent}); }}"
    " {cls}::indicator:disabled {{ background: rgba(127, 127, 127, 40); }}"
    " {cls}::indicator:checked:disabled {{ background: rgba(91, 155, 213, 90); }}"
)


class _AccentIndicatorMixin:
    """Shared by CheckBox and RadioButton. Subclasses set _QSS_CLASS,
    _INDICATOR_ELEMENT, _ROUND, and implement _paint_mark()."""

    _QSS_CLASS = "QCheckBox"
    _INDICATOR_ELEMENT = QStyle.SE_CheckBoxIndicator
    _ROUND = False

    def _init_indicator(self) -> None:
        self._own_qss = ""
        self._indicator_size = 0
        self._apply_qss()

    def setStyleSheet(self, qss: str) -> None:
        self._own_qss = qss
        self._apply_qss()

    def _size_for_font(self) -> int:
        return max(12, self.fontMetrics().capHeight() + 4)

    def _apply_qss(self) -> None:
        # Our own stylesheet can change the font (font-size), so the size is
        # measured after applying it; FontChange then re-enters here once.
        size = self._indicator_size = self._size_for_font()
        super().setStyleSheet(self._own_qss + " " + _INDICATOR_QSS.format(
            cls=self._QSS_CLASS, light=ACCENT_LIGHT, accent=ACCENT,
            size=size, radius=size // 2 if self._ROUND else 3,
            spacing=max(5, round(self.fontMetrics().capHeight() * 0.7))))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.FontChange and self._size_for_font() != self._indicator_size:
            self._apply_qss()

    def _indicator_rect(self):
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        return self.style().subElementRect(self._INDICATOR_ELEMENT, opt, self)

    def paintEvent(self, event) -> None:
        rect = self._indicator_rect()

        if self.isEnabled():
            shadow = QPainter(self)
            shadow.setRenderHint(QPainter.Antialiasing, True)
            shadow.setPen(Qt.NoPen)
            for dy, alpha in ((3, 14), (2, 24), (1, 40)):
                shadow.setBrush(QColor(0, 0, 0, alpha))
                if self._ROUND:
                    shadow.drawEllipse(rect.translated(0, dy))
                else:
                    shadow.drawRoundedRect(rect.translated(0, dy), 3, 3)
            shadow.end()

        super().paintEvent(event)  # the QSS gradient indicator and the label

        if not self.isChecked():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        self._paint_mark(painter, rect, QColor(255, 255, 255, 255 if self.isEnabled() else 140))
        painter.end()


class CheckBox(_AccentIndicatorMixin, QCheckBox):
    _QSS_CLASS = "QCheckBox"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_indicator()

    def _paint_mark(self, painter: QPainter, rect, color: QColor) -> None:
        pen = QPen(color, 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        painter.drawLine(QPointF(x + w * 0.22, y + h * 0.52), QPointF(x + w * 0.42, y + h * 0.74))
        painter.drawLine(QPointF(x + w * 0.42, y + h * 0.74), QPointF(x + w * 0.80, y + h * 0.26))


class RadioButton(_AccentIndicatorMixin, QRadioButton):
    _QSS_CLASS = "QRadioButton"
    _INDICATOR_ELEMENT = QStyle.SE_RadioButtonIndicator
    _ROUND = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_indicator()

    def _paint_mark(self, painter: QPainter, rect, color: QColor) -> None:
        d = rect.width() * 0.4
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(rect.center().x() + 0.5 - d / 2, rect.center().y() + 0.5 - d / 2, d, d))
