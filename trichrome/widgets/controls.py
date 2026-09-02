"""Reusable slider + spinbox combo control."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QSizePolicy, QSlider,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import i18n

STEPS = 1000


class ArrowKeyScrollArea(QScrollArea):
    """A QScrollArea that only scrolls via wheel/trackpad/scrollbar - Left/Right
    are handed off to the parent (MainWindow) so they can navigate the
    filmstrip instead of being swallowed by whichever scroll area currently
    contains the focused widget."""

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            event.ignore()
            return
        super().keyPressEvent(event)


class ElidingLabel(QLabel):
    """A QLabel that middle-elides its text ("long_file…name.tif") to
    whatever width it's actually given, instead of growing its container to
    fit the full text - the layout's available space drives the display,
    not the content."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._full_text = ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def setText(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._apply_elided()

    def resizeEvent(self, event) -> None:
        self._apply_elided()
        super().resizeEvent(event)

    def _apply_elided(self) -> None:
        elided = self.fontMetrics().elidedText(self._full_text, Qt.ElideMiddle, self.width())
        super().setText(elided)


class _ResettableSlider(QSlider):
    """A QSlider that resets to a default value on double-click.

    Every ``SliderSpin`` now maps its default to this slider's exact
    midpoint step (see ``SliderSpin._value_to_slider``), so the fill drawn
    here can always grow from the geometric center outward - left in one
    direction, right in the other - instead of Qt's native sub-page style,
    which always fills from the track's left edge regardless of where the
    default sits. That native behavior is what made a neutral value look
    "half full" once its default wasn't at the minimum, which is the actual
    bug prompting this: a center-anchored fill is the only way to see which
    side of default the slider is actually on.

    The groove, fill, center tick and handle are now all painted here, in
    that order, instead of drawing an overlay on top of Qt's own native
    handle - the QSS below only sets the handle's hit-testing box (size/
    margin, `background: transparent`) so `QStyle`/`QAbstractSlider`'s own
    mouse handling still computes drag geometry correctly, but nothing
    native actually paints. Painting the handle myself, always last, is
    what guarantees it's fully opaque and never shows the groove/fill
    underneath it - the previous native-handle-then-overlay order could let
    the accent fill bar's antialiased edge peek past the native handle's
    own edge.
    """

    double_clicked = Signal()

    HANDLE_RADIUS = 5.5
    HANDLE_BORDER = 2.0

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event) -> None:
        # Left/Right normally step the slider's value - hand them off instead
        # so filmstrip navigation still works right after dragging a slider.
        if event.key() in (Qt.Key_Left, Qt.Key_Right):
            event.ignore()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        handle_radius = self.HANDLE_RADIUS
        groove_h = 3.0
        cy = self.height() / 2.0
        x0 = handle_radius
        x1 = max(x0, self.width() - handle_radius)
        usable = max(1.0, x1 - x0)

        span = max(1, self.maximum() - self.minimum())
        value_frac = (self.value() - self.minimum()) / span
        vx = x0 + usable * value_frac
        cx = x0 + usable * 0.5  # the default is always at the midpoint step

        enabled = self.isEnabled()

        groove_color = QColor(74, 74, 80) if enabled else QColor(58, 58, 62)
        painter.setPen(Qt.NoPen)
        painter.setBrush(groove_color)
        painter.drawRoundedRect(
            QRectF(x0, cy - groove_h / 2, usable, groove_h), groove_h / 2, groove_h / 2)

        fill_color = QColor(122, 144, 194) if enabled else QColor(90, 92, 98)
        left, right = sorted((cx, vx))
        if right - left > 0.5:
            painter.setBrush(fill_color)
            painter.drawRoundedRect(
                QRectF(left, cy - groove_h / 2, right - left, groove_h), groove_h / 2, groove_h / 2)

        tick_color = QColor(200, 200, 206, 190) if enabled else QColor(120, 120, 126, 140)
        painter.setPen(QPen(tick_color, 1.5))
        painter.drawLine(QPointF(cx, cy - 4), QPointF(cx, cy + 4))

        # Handle last, always fully opaque - a hollow ring at rest, filled
        # solid while actually held (Lightroom's own slider behavior).
        handle_color = QColor(232, 232, 232) if enabled else QColor(140, 140, 144)
        if self.isSliderDown():
            painter.setPen(Qt.NoPen)
            painter.setBrush(handle_color)
            painter.drawEllipse(QPointF(vx, cy), handle_radius, handle_radius)
        else:
            border = self.HANDLE_BORDER
            bg = self.palette().color(QPalette.Window)
            painter.setPen(QPen(handle_color, border))
            painter.setBrush(bg)
            painter.drawEllipse(QPointF(vx, cy), handle_radius - border / 2, handle_radius - border / 2)
        painter.end()


class _ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class _EscapableLineEdit(QLineEdit):
    escaped = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.escaped.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ClickToEditValue(QWidget):
    """A bare, borderless number - click it to type a new value, instead of
    a QDoubleSpinBox's boxed look with up/down arrows.

    Shows a plain right-aligned label; clicking swaps in a line edit
    (selected, focused) until Enter/focus-out commits it or Escape cancels.
    ``signed`` prefixes a positive value with "+" (and shows a bare "0" at
    exactly zero) so the number itself echoes which side of center/default
    the paired slider is on - only meaningful for a value whose neutral
    point is genuinely 0 (percent-mode display, or a real value whose own
    default is 0 - see ``SliderSpin``).
    """

    value_edited = Signal(float)

    def __init__(self, minimum: float, maximum: float, decimals: int = 0,
                 signed: bool = False, parent: QWidget | None = None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._decimals = decimals
        self._signed = signed
        self._value = 0.0
        self._editing = False

        self._label = _ClickableLabel()
        self._label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._label.setCursor(Qt.PointingHandCursor)
        self._label.clicked.connect(self._start_edit)

        self._edit = _EscapableLineEdit()
        self._edit.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._edit.setFrame(False)
        self._edit.setStyleSheet(
            "QLineEdit { background: transparent; border-bottom: 1px solid #7a90c2; }")
        self._edit.editingFinished.connect(self._commit_edit)
        self._edit.escaped.connect(self._cancel_edit)
        self._edit.hide()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        layout.addWidget(self._edit)
        self.setFixedWidth(70)

        self._refresh_enabled_style()
        self.set_value(0.0)

    def _start_edit(self) -> None:
        if not self.isEnabled():
            return
        self._editing = True
        self._edit.setText(f"{self._value:.{self._decimals}f}")
        self._label.hide()
        self._edit.show()
        self._edit.setFocus()
        self._edit.selectAll()

    def _end_edit(self) -> None:
        self._editing = False
        self._edit.hide()
        self._label.show()

    def _commit_edit(self) -> None:
        if not self._editing:
            return  # editingFinished can fire again after we already handled it
        text = self._edit.text().strip().replace(",", ".")
        try:
            value = float(text)
        except ValueError:
            value = self._value
        value = max(self._min, min(self._max, value))
        self._end_edit()
        self.set_value(value)
        self.value_edited.emit(value)

    def _cancel_edit(self) -> None:
        self._end_edit()

    def _format(self, value: float) -> str:
        rounded = round(value, self._decimals)
        if rounded == 0:
            rounded = 0.0  # avoid a stray "-0"
        text = f"{rounded:.{self._decimals}f}"
        if self._signed and rounded > 0:
            text = "+" + text
        return text

    def value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        self._value = value
        self._label.setText(self._format(value))

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.EnabledChange:
            self._refresh_enabled_style()

    def _refresh_enabled_style(self) -> None:
        color = "#d8d8dc" if self.isEnabled() else "#6a6a6e"
        self._label.setStyleSheet(f"QLabel {{ color: {color}; }}")


class SliderSpin(QWidget):
    """A labeled slider paired with a click-to-edit numeric value, kept in sync.

    Double-clicking the slider resets it to its default value. The slider
    always maps its default to its own exact midpoint step, regardless of
    where that default numerically sits between ``minimum`` and ``maximum``
    (piecewise: the [minimum, default) half and the (default, maximum] half
    are each stretched to fill their own side of the track) - so every
    slider's handle starts out dead-center, and the fill drawn by
    ``_ResettableSlider`` always reads as "how far from default, which
    direction" rather than "how far from minimum".

    With ``percent_mode=True`` the displayed/typed number is remapped the
    same way, to -100..100 (0 at the default) - the Lightroom-style relative
    scale, for a value whose real unit (a multiplier, an exponent, an
    additive tonal shift) isn't independently meaningful to read. With it
    left False (the default), the shown number is the real value in
    ``decimals`` precision - for a slider whose unit already means something
    on its own (pixels, degrees, a zoom ratio).
    """

    value_changed = Signal(float)

    def __init__(self, label: str, minimum: float, maximum: float,
                 default: float, decimals: int = 3, percent_mode: bool = False,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._default = default
        self._decimals = decimals
        self._percent_mode = percent_mode
        self._value = default
        self._updating = False

        self.label = QLabel(label)
        self.label.setToolTip(i18n.tr("double_click_reset_hint"))

        self.slider = _ResettableSlider(Qt.Horizontal)
        self.slider.setRange(0, STEPS)
        self.slider.setMinimumHeight(18)
        self.slider.setToolTip(i18n.tr("double_click_reset_hint"))
        # Groove/handle are fully custom-painted in _ResettableSlider.paintEvent
        # now - this QSS only sets the handle's hit-testing box (size/margin)
        # so drag/click geometry stays correct; background: transparent means
        # nothing native actually renders on top of the custom painting.
        self.slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 3px; background: transparent; }"
            "QSlider::handle:horizontal { background: transparent; width: 11px; height: 11px; "
            "margin: -4px 0; }"
        )
        self.slider.double_clicked.connect(self.reset_to_default)

        display_decimals = 0 if percent_mode else decimals
        display_min = -100.0 if percent_mode else minimum
        display_max = 100.0 if percent_mode else maximum
        signed = percent_mode or default == 0
        self.value_display = ClickToEditValue(
            display_min, display_max, decimals=display_decimals, signed=signed)
        self.value_display.value_edited.connect(self._on_display_edited)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addWidget(self.label, stretch=1)
        top_row.addWidget(self.value_display)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 6)
        layout.setSpacing(2)
        layout.addLayout(top_row)
        layout.addWidget(self.slider)

        self.set_value(default)

        self.slider.valueChanged.connect(self._on_slider_changed)

    # -- value <-> [-1, 1] fraction, 0 always at the default --------------
    def _value_to_fraction(self, value: float) -> float:
        if value >= self._default:
            span = self._max - self._default
            frac = (value - self._default) / span if span else 0.0
        else:
            span = self._default - self._min
            frac = (value - self._default) / span if span else 0.0
        return max(-1.0, min(1.0, frac))

    def _fraction_to_value(self, frac: float) -> float:
        frac = max(-1.0, min(1.0, frac))
        if frac >= 0:
            return self._default + frac * (self._max - self._default)
        return self._default + frac * (self._default - self._min)

    def _slider_to_value(self, slider_val: int) -> float:
        frac = (slider_val / STEPS) * 2.0 - 1.0
        return self._fraction_to_value(frac)

    def _value_to_slider(self, value: float) -> int:
        frac = self._value_to_fraction(value)
        return int(round((frac + 1.0) / 2.0 * STEPS))

    def _value_to_display(self, value: float) -> float:
        if self._percent_mode:
            return self._value_to_fraction(value) * 100.0
        return value

    def _display_to_value(self, display: float) -> float:
        if self._percent_mode:
            return round(self._fraction_to_value(display / 100.0), self._decimals)
        return display

    def _on_slider_changed(self, slider_val: int) -> None:
        if self._updating:
            return
        self._value = self._slider_to_value(slider_val)
        self._updating = True
        self.value_display.set_value(self._value_to_display(self._value))
        self._updating = False
        self.value_changed.emit(self._value)

    def _on_display_edited(self, display_value: float) -> None:
        if self._updating:
            return
        self._value = self._display_to_value(display_value)
        self._updating = True
        self.slider.setValue(self._value_to_slider(self._value))
        self.value_display.set_value(self._value_to_display(self._value))  # normalize rounding
        self._updating = False
        self.value_changed.emit(self._value)

    def value(self) -> float:
        return self._value

    def set_value(self, value: float) -> None:
        self._value = value
        self._updating = True
        self.slider.setValue(self._value_to_slider(value))
        self.value_display.set_value(self._value_to_display(value))
        self._updating = False

    def reset_to_default(self) -> None:
        self.set_value(self._default)
        self.value_changed.emit(self._default)

    def set_label_text(self, text: str) -> None:
        self.label.setText(text)

    def retranslate_ui(self) -> None:
        hint = i18n.tr("double_click_reset_hint")
        self.label.setToolTip(hint)
        self.slider.setToolTip(hint)


class CollapsibleSection(QFrame):
    """A bordered section with a disclosure-arrow header, collapsed by default.

    Add child widgets via ``content_layout`` rather than this widget's own
    layout; the content widget is what actually gets shown/hidden.
    """

    toggled = Signal(bool)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 6)
        outer.setSpacing(2)

        self.toggle_button = QToolButton()
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(False)
        self.toggle_button.setArrowType(Qt.RightArrow)
        self.toggle_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.toggle_button.setStyleSheet(
            "QToolButton { border: none; font-weight: bold; text-align: left; }"
        )
        self.toggle_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.toggle_button.clicked.connect(self._on_clicked)
        outer.addWidget(self.toggle_button)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(14, 2, 0, 0)
        outer.addWidget(self.content)
        self.content.setVisible(False)

    def _on_clicked(self, checked: bool) -> None:
        self.toggle_button.setArrowType(Qt.DownArrow if checked else Qt.RightArrow)
        self.content.setVisible(checked)
        self.toggled.emit(checked)

    def setTitle(self, text: str) -> None:
        self.toggle_button.setText(text)

    def isChecked(self) -> bool:
        return self.toggle_button.isChecked()

    def setChecked(self, checked: bool) -> None:
        self.toggle_button.setChecked(checked)
        self._on_clicked(checked)
