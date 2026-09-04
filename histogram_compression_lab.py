"""TEMPORARY experiment window - not part of the app, safe to delete.

Lets you load a real photo, compute its real Y/R/G/B histogram (via the
same trichrome.imaging.compute_channel_histograms the real app uses), and
compare 3 ways of scaling bin height for display: Linear, Log, and Sqrt.
The Log mode's compression strength ("log factor" k) is a live slider -
the exact formula being applied is shown on screen, updating as you move
it.

Run with:  python3 histogram_compression_lab.py
(uses the project's own venv - activate it first, or run via
./venv/bin/python3 histogram_compression_lab.py)

Formulas (applied per-bin to the raw pixel count `x`, then the whole
channel is divided by its own tallest resulting bin so it always fills
the chart height - same "normalize to the max" step the real app uses):
    Linear:  f(x) = x
    Log:     f(x) = ln(1 + k*x)          (k = the slider's "log factor")
    Sqrt:    f(x) = sqrt(x)
"""
from __future__ import annotations

import sys

import numpy as np
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QFileDialog, QHBoxLayout, QLabel,
    QMainWindow, QPushButton, QRadioButton, QSlider, QVBoxLayout, QWidget,
)

from trichrome import imaging  # the script's own directory (project root) is on sys.path automatically

_CHANNELS = ("Y", "R", "G", "B")
_CHANNEL_COLORS = {
    "Y": QColor(220, 220, 220),
    "R": QColor("#e05555"),
    "G": QColor("#3fae4a"),
    "B": QColor("#4a7fe0"),
}


def _compress(counts: np.ndarray, mode: str, log_factor: float) -> np.ndarray:
    if mode == "linear":
        return counts.astype(np.float64)
    if mode == "log":
        return np.log1p(log_factor * counts)
    if mode == "sqrt":
        return np.sqrt(counts)
    raise ValueError(mode)


class HistogramChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(500, 320)
        self._histograms: dict[str, np.ndarray] | None = None
        self._visible = set(_CHANNELS)
        self.mode = "log"
        self.log_factor = 1.0

    def set_histograms(self, histograms) -> None:
        self._histograms = histograms
        self.update()

    def set_visible(self, channel: str, visible: bool) -> None:
        if visible:
            self._visible.add(channel)
        else:
            self._visible.discard(channel)
        self.update()

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self.update()

    def set_log_factor(self, factor: float) -> None:
        self.log_factor = factor
        if self.mode == "log":
            self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(4, 4, self.width() - 8, self.height() - 8)
        painter.fillRect(rect, QColor(24, 24, 24))
        painter.setPen(QPen(QColor(70, 70, 70)))
        painter.drawRect(rect.adjusted(0, 0, -1, -1))

        if not self._histograms:
            painter.end()
            return

        shown = [ch for ch in _CHANNELS if ch in self._visible]
        if not shown:
            painter.end()
            return

        w, h = rect.width(), rect.height()
        compressed = {ch: _compress(self._histograms[ch], self.mode, self.log_factor) for ch in shown}
        max_val = max(float(c.max()) for c in compressed.values()) or 1.0

        for ch in shown:
            c = compressed[ch]
            n = len(c)
            fill = QPainterPath()
            fill.moveTo(rect.left(), rect.bottom())
            for i, v in enumerate(c):
                x = rect.left() + (i / (n - 1)) * w
                y = rect.bottom() - min(1.0, float(v) / max_val) * (h - 4)
                fill.lineTo(x, y)
            fill.lineTo(rect.right(), rect.bottom())
            fill.closeSubpath()
            color = QColor(_CHANNEL_COLORS[ch])
            color.setAlpha(60)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawPath(fill)

            outline_color = QColor(_CHANNEL_COLORS[ch])
            outline_color.setAlpha(230)
            painter.setPen(QPen(outline_color, 1.3))
            painter.setBrush(Qt.NoBrush)
            outline = QPainterPath()
            for i, v in enumerate(c):
                x = rect.left() + (i / (n - 1)) * w
                y = rect.bottom() - min(1.0, float(v) / max_val) * (h - 4)
                if i == 0:
                    outline.moveTo(x, y)
                else:
                    outline.lineTo(x, y)
            painter.drawPath(outline)

        painter.end()


class LabWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Histogram Compression Lab (temporary)")
        self.resize(760, 620)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        load_row = QHBoxLayout()
        self.load_btn = QPushButton("Load Image...")
        self.load_btn.clicked.connect(self._on_load_clicked)
        load_row.addWidget(self.load_btn)
        self.filename_label = QLabel("No image loaded - using synthetic test data")
        self.filename_label.setStyleSheet("color: #999;")
        load_row.addWidget(self.filename_label, stretch=1)
        layout.addLayout(load_row)

        self.chart = HistogramChart()
        layout.addWidget(self.chart, stretch=1)

        channel_row = QHBoxLayout()
        channel_row.addWidget(QLabel("Channels:"))
        self._channel_checks: dict[str, QCheckBox] = {}
        for ch in _CHANNELS:
            box = QCheckBox(ch)
            box.setChecked(True)
            box.toggled.connect(lambda checked, c=ch: self.chart.set_visible(c, checked))
            channel_row.addWidget(box)
            self._channel_checks[ch] = box
        channel_row.addStretch(1)
        layout.addLayout(channel_row)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Compression:"))
        self.mode_group = QButtonGroup(self)
        self._mode_buttons: dict[str, QRadioButton] = {}
        for mode, text in (("linear", "Linear"), ("log", "Log"), ("sqrt", "Sqrt")):
            btn = QRadioButton(text)
            btn.setChecked(mode == "log")
            btn.toggled.connect(lambda checked, m=mode: self._on_mode_toggled(m, checked))
            self.mode_group.addButton(btn)
            mode_row.addWidget(btn)
            self._mode_buttons[mode] = btn
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        slider_row = QHBoxLayout()
        slider_row.addWidget(QLabel("Log factor (k):"))
        self.factor_slider = QSlider(Qt.Horizontal)
        # Log-scaled slider: raw steps 0..300 map to k = 10^(step/100 - 2),
        # i.e. k spans ~0.01 to ~10 - a linear slider would be unusable
        # since useful k values span orders of magnitude. step=200 -> k=1.0,
        # exactly matching the app's current fixed log1p(x) as a reference point.
        self.factor_slider.setRange(0, 300)
        self.factor_slider.setValue(200)
        self.factor_slider.valueChanged.connect(self._on_factor_slider_changed)
        slider_row.addWidget(self.factor_slider, stretch=1)
        self.factor_value_label = QLabel()
        self.factor_value_label.setFixedWidth(70)
        slider_row.addWidget(self.factor_value_label)
        layout.addLayout(slider_row)

        self.formula_label = QLabel()
        formula_font = QFont("Menlo")
        formula_font.setStyleHint(QFont.Monospace)
        formula_font.setPointSize(13)
        self.formula_label.setFont(formula_font)
        self.formula_label.setStyleSheet("color: #7a90c2; padding: 6px 0;")
        layout.addWidget(self.formula_label)

        note = QLabel(
            "After compression, each channel is divided by its own tallest bin "
            "so it always fills the chart height (same normalization the real "
            "app applies) - the base of a log doesn't matter for the shape "
            "since it cancels out in that division; the factor k multiplying x "
            "*inside* the log does change the shape, which is what this slider "
            "controls."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(note)

        self._log_factor = 1.0
        self._update_slider_enabled()
        self._update_factor_label()
        self._update_formula_label()
        self._load_synthetic_histograms()

    # -- data -------------------------------------------------------------
    def _load_synthetic_histograms(self) -> None:
        """A reasonably realistic-shaped synthetic histogram (a few peaks
        plus a dominant near-black spike) so the window shows something
        useful before you load a real photo."""
        rng = np.random.default_rng(0)
        h, w = 400, 600
        base = rng.normal(0.45, 0.18, size=(h, w))
        base = np.clip(base, 0, 1)
        base[: h // 6, :] = np.clip(rng.normal(0.03, 0.02, size=(h // 6, w)), 0, 1)  # a dark band, big spike near 0
        rgb = np.stack([base, base * 0.9, base * 0.8], axis=-1)
        rgb_u8 = (np.clip(rgb, 0, 1) * 255).astype(np.uint8)
        self.chart.set_histograms(imaging.compute_channel_histograms(rgb_u8))

    def _on_load_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Image", "", "Images (*.jpg *.jpeg *.png *.tif *.tiff *.bmp)")
        if not path:
            return
        qimg = QImage(path)
        if qimg.isNull():
            self.filename_label.setText(f"Failed to load: {path}")
            return
        qimg = qimg.convertToFormat(QImage.Format_RGB888)
        w, h = qimg.width(), qimg.height()
        ptr = qimg.constBits()
        arr = np.frombuffer(ptr, dtype=np.uint8, count=h * qimg.bytesPerLine()).reshape(h, qimg.bytesPerLine())
        rgb_u8 = np.ascontiguousarray(arr[:, : w * 3].reshape(h, w, 3))
        self.filename_label.setText(path)
        self.chart.set_histograms(imaging.compute_channel_histograms(rgb_u8))

    # -- controls -----------------------------------------------------------
    def _on_mode_toggled(self, mode: str, checked: bool) -> None:
        if checked:
            self.chart.set_mode(mode)
            self._update_slider_enabled()
            self._update_formula_label()

    def _on_factor_slider_changed(self, _value: int) -> None:
        exponent = self.factor_slider.value() / 100.0 - 2.0
        self._log_factor = 10.0 ** exponent
        self.chart.set_log_factor(self._log_factor)
        self._update_factor_label()
        self._update_formula_label()

    def _update_slider_enabled(self) -> None:
        self.factor_slider.setEnabled(self.chart.mode == "log")

    def _update_factor_label(self) -> None:
        self.factor_value_label.setText(f"{self._log_factor:.3g}")

    def _update_formula_label(self) -> None:
        if self.chart.mode == "linear":
            self.formula_label.setText("f(x) = x")
        elif self.chart.mode == "log":
            self.formula_label.setText(f"f(x) = ln(1 + {self._log_factor:.3g}·x)")
        else:
            self.formula_label.setText("f(x) = √x")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = LabWindow()
    win.show()
    sys.exit(app.exec())
