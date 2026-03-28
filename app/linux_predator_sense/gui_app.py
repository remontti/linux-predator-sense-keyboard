from __future__ import annotations

import os
import re
import subprocess
from contextlib import ExitStack
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QSignalBlocker, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .constants import (
    APP_DISPLAY_NAME,
    APP_SHORT_NAME,
    AUTHOR_LOGO_PATH,
    BUILTIN_PRESETS,
    ICON_PATH,
    SUPPORTED_EFFECTS_BY_DEVICE,
)
from .hid_backend import apply_keyboard_state, apply_lid_state, detect_rgb_device
from .i18n import LANGUAGE_OPTIONS, get_text
from .models import AppProfile, HidrawDevice, KeyboardState, LidState
from .profile_store import (
    delete_app_profile,
    list_app_profiles,
    load_app_profile,
    load_settings,
    save_app_profile,
    save_settings,
)


HEX_RE = re.compile(r"^[0-9a-fA-F]{6}$")
PAGE_IDS = ("colors", "effects", "logo", "profiles", "diagnostics")
PKEXEC_PATH = Path("/usr/bin/pkexec")
CLI_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "predator-rgb-hid.py"


def hex_to_qcolor(value: str) -> QColor:
    return QColor(f"#{value}")


def qcolor_to_hex(color: QColor) -> str:
    return color.name(QColor.NameFormat.HexRgb).lstrip("#").lower()


def readable_text(color: QColor) -> QColor:
    return QColor("#09121a") if color.lightness() > 150 else QColor("#f4fbff")


def mono_font() -> QFont:
    font = QFont("Monospace")
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def value_font() -> QFont:
    font = QFont()
    font.setPointSize(11)
    font.setBold(True)
    return font


def build_stylesheet() -> str:
    return """
    QWidget {
        background: #071019;
        color: #edf6ff;
        font-size: 13px;
        font-family: "Cantarell";
    }
    QMainWindow {
        background: #050c13;
    }
    QScrollArea, QScrollArea > QWidget > QWidget {
        background: transparent;
        border: none;
    }
    QFrame#sideRail {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #0a141f, stop:1 #0d1824);
        border: 1px solid #183248;
        border-radius: 28px;
    }
    QFrame#panelCard {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #0c141d, stop:1 #101b28);
        border: 1px solid #1d364b;
        border-radius: 22px;
    }
    QFrame#softCard {
        background: #0b141d;
        border: 1px solid #183042;
        border-radius: 18px;
    }
    QPushButton {
        background: #10212f;
        border: 1px solid #23435c;
        border-radius: 14px;
        padding: 10px 16px;
        min-height: 22px;
        font-weight: 600;
    }
    QPushButton:hover {
        background: #173247;
        border-color: #63d3ff;
    }
    QPushButton:pressed {
        background: #0f2434;
    }
    QPushButton#accentButton {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #58d1ff, stop:1 #1670b7);
        border-color: #7fe7ff;
        color: #06121a;
        font-weight: 700;
    }
    QPushButton#accentButton:hover {
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #82e2ff, stop:1 #2690df);
    }
    QPushButton#ghostButton {
        background: transparent;
        border-color: #2f526a;
        color: #9dc7de;
    }
    QPushButton#navButton {
        text-align: left;
        padding: 14px 16px;
        border-radius: 18px;
        background: transparent;
        border: 1px solid transparent;
        color: #9fb6c7;
    }
    QPushButton#navButton:hover {
        background: #0f1d29;
        border-color: #27465d;
        color: #f4fbff;
    }
    QPushButton#navButton:checked {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 #112739, stop:1 #194768);
        border-color: #63d4ff;
        color: #f6fcff;
    }
    QComboBox, QListWidget, QLineEdit {
        background: #08131b;
        border: 1px solid #1d3950;
        border-radius: 14px;
        padding: 9px 14px;
        selection-background-color: #183b59;
    }
    QComboBox {
        padding-right: 32px;
        min-height: 22px;
    }
    QComboBox::drop-down {
        border: none;
        width: 28px;
        subcontrol-origin: padding;
        subcontrol-position: top right;
    }
    QLineEdit:focus, QComboBox:focus, QListWidget:focus {
        border-color: #66d8ff;
    }
    QListWidget {
        padding: 10px;
    }
    QListWidget::item {
        margin: 4px 0;
        padding: 12px 14px;
        border-radius: 12px;
        background: #0d1822;
        border: 1px solid #172c3d;
    }
    QListWidget::item:selected {
        background: #18354e;
        border: 1px solid #66d8ff;
    }
    QSlider::groove:horizontal {
        background: #102130;
        height: 6px;
        border-radius: 3px;
    }
    QSlider::sub-page:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #1e86d0, stop:1 #6fe1ff);
        border-radius: 3px;
    }
    QSlider::handle:horizontal {
        background: #dff9ff;
        border: 2px solid #6fe1ff;
        width: 18px;
        margin: -8px 0;
        border-radius: 9px;
    }
    QLabel[eyebrow="true"] {
        color: #76dfff;
        font-weight: 700;
    }
    QLabel[brandTitle="true"] {
        font-size: 28px;
        font-weight: 700;
    }
    QLabel[pageTitle="true"] {
        color: #f4fbff;
        font-size: 26px;
        font-weight: 700;
    }
    QLabel[sectionTitle="true"] {
        color: #f2fbff;
        font-size: 18px;
        font-weight: 700;
    }
    QLabel[muted="true"] {
        color: #8ea7b8;
    }
    QLabel[pill="true"] {
        background: #102536;
        border: 1px solid #26506b;
        border-radius: 13px;
        padding: 7px 11px;
        color: #88e9ff;
        font-weight: 700;
    }
    QLabel[value="true"] {
        color: #eff8ff;
    }
    QLabel[mono="true"] {
        color: #b6d4e7;
    }
    """


def effect_label(language: str, effect: str) -> str:
    return get_text(language, f"effect_{effect}")


def direction_label(language: str, direction: str) -> str:
    return get_text(language, f"direction_{direction}")


def preset_label(language: str, name: str) -> str:
    return get_text(language, f"preset_{name}")


class ColorField(QWidget):
    color_changed = Signal(str)

    def __init__(self, label_text: str, initial: str) -> None:
        super().__init__()
        self._hex = initial.lower()
        self._label_text = label_text

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.swatch = QPushButton()
        self.swatch.setMinimumWidth(54)
        self.swatch.setMaximumWidth(54)
        self.swatch.setMinimumHeight(44)
        self.swatch.clicked.connect(self.pick_color)

        self.input = QLineEdit()
        self.input.setMaxLength(6)
        self.input.setPlaceholderText("RRGGBB")
        self.input.editingFinished.connect(self.commit_text)

        layout.addWidget(self.swatch)
        layout.addWidget(self.input, 1)

        self.set_value(initial, emit=False)

    def set_label_text(self, label_text: str) -> None:
        self._label_text = label_text

    def value(self) -> str:
        return self._hex

    def set_value(self, value: str, emit: bool = True) -> None:
        value = value.lower()
        if not HEX_RE.fullmatch(value):
            return
        self._hex = value
        self.input.setText(value.upper())
        self._refresh_style()
        if emit:
            self.color_changed.emit(self._hex)

    def _refresh_style(self) -> None:
        color = hex_to_qcolor(self._hex)
        text = readable_text(color).name()
        self.swatch.setStyleSheet(
            f"QPushButton {{ background: #{self._hex}; border: 1px solid #4b667a; border-radius: 14px; }}"
            f"QPushButton:hover {{ border-color: {text}; }}"
        )
        self.input.setStyleSheet(
            "QLineEdit { background: #08131b; border: 1px solid #1d3950; border-radius: 14px; "
            f"padding: 9px 12px; color: {text}; selection-background-color: #{self._hex}; }}"
        )

    def commit_text(self) -> None:
        value = self.input.text().strip().lower()
        if HEX_RE.fullmatch(value):
            self.set_value(value)
        else:
            self.input.setText(self._hex.upper())

    def pick_color(self) -> None:
        dialog = QColorDialog(hex_to_qcolor(self._hex), self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setWindowTitle(self._label_text)
        if dialog.exec():
            self.set_value(qcolor_to_hex(dialog.selectedColor()))


class PresetCard(QPushButton):
    def __init__(self, preset_name: str, preset: dict, language: str) -> None:
        super().__init__()
        self.preset_name = preset_name
        self.preset = preset
        self.language = language
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_language(self, language: str) -> None:
        self.language = language
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1.0, 1.0, -1.0, -1.0)
        hover = self.underMouse()
        checked = self.isChecked()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if checked:
            gradient.setColorAt(0.0, QColor("#14304a"))
            gradient.setColorAt(1.0, QColor("#194f73"))
            border = QColor("#73defd")
        elif hover:
            gradient.setColorAt(0.0, QColor("#0f1d29"))
            gradient.setColorAt(1.0, QColor("#153049"))
            border = QColor("#3c6887")
        else:
            gradient.setColorAt(0.0, QColor("#0b141c"))
            gradient.setColorAt(1.0, QColor("#0f1c28"))
            border = QColor("#1b3348")

        painter.setPen(QPen(border, 1.4))
        painter.setBrush(gradient)
        painter.drawRoundedRect(rect, 18, 18)

        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor("#f3fbff"))
        painter.drawText(
            rect.adjusted(14, 12, -80, -34),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            preset_label(self.language, self.preset_name),
        )

        painter.setPen(QColor("#8fa6b7"))
        painter.drawText(
            rect.adjusted(14, 32, -80, -18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            f"{self.preset['brightness']}%",
        )

        badge = QRectF(rect.right() - 58, rect.top() + 10, 44, 24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#0a1822"))
        painter.drawRoundedRect(badge, 10, 10)
        painter.setPen(QColor("#88e7ff"))
        badge_font = QFont()
        badge_font.setPointSize(8)
        badge_font.setBold(True)
        painter.setFont(badge_font)
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, "RGB")

        chip_width = (rect.width() - 38) / 4
        y = rect.bottom() - 24
        for index, color in enumerate(self.preset["zones"]):
            chip = QRectF(rect.left() + 14 + chip_width * index, y, chip_width - 6, 10)
            painter.setBrush(hex_to_qcolor(color))
            painter.drawRoundedRect(chip, 5, 5)


class ColorChip(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._color = "00AAFF"
        self.setMinimumHeight(32)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_value(self, color: str) -> None:
        self._color = color.upper()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        fill = hex_to_qcolor(self._color)
        painter.setPen(QPen(QColor("#315068"), 1.2))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, 12, 12)

        text_color = readable_text(fill)
        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(text_color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._color)


class KeyboardPreview(QWidget):
    def __init__(self, language: str, compact: bool = False) -> None:
        super().__init__()
        self.language = language
        self.compact = compact
        self.state = KeyboardState()
        if compact:
            self.setMinimumSize(320, 160)
        else:
            self.setMinimumSize(640, 330)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_state(self, state: KeyboardState) -> None:
        self.state = state
        self.update()

    def set_language(self, language: str) -> None:
        self.language = language
        self.update()

    def _draw_key(self, painter: QPainter, rect: QRectF, color: QColor) -> None:
        painter.setPen(QPen(QColor("#213c50"), 1.1))
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 8, 8)

        highlight = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        highlight.setColorAt(0.0, QColor(255, 255, 255, 58))
        highlight.setColorAt(1.0, QColor(255, 255, 255, 5))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(highlight)
        painter.drawRoundedRect(rect.adjusted(1.5, 1.5, -1.5, -rect.height() * 0.4), 6, 6)

    def _palette_for_state(self) -> list[QColor]:
        if self.state.effect == "static":
            return [hex_to_qcolor(color) for color in self.state.zones]
        return [
            QColor("#305cff"),
            QColor("#15a8ff"),
            QColor("#19d8ff"),
            QColor("#8df3ff"),
        ]

    def _paint_keyboard_rows(
        self,
        painter: QPainter,
        deck: QRectF,
        rows: list[list[float]],
        gap: float,
        top_padding: float,
        bottom_padding: float,
    ) -> None:
        key_height = (deck.height() - top_padding - bottom_padding - gap * (len(rows) - 1)) / len(rows)
        palette = self._palette_for_state()
        top = deck.top() + top_padding
        usable_width = deck.width() - 28

        for row_index, row in enumerate(rows):
            total_units = sum(row)
            unit_width = (usable_width - gap * (len(row) - 1)) / total_units
            x = deck.left() + 14
            y = top + row_index * (key_height + gap)
            for width_units in row:
                width = unit_width * width_units
                rect = QRectF(x, y, width, key_height)
                center_fraction = (rect.center().x() - deck.left()) / deck.width()
                zone_index = min(3, max(0, int(center_fraction * 4)))
                color = QColor(palette[zone_index])
                color = color.lighter(112 if row_index % 2 == 0 else 100)
                self._draw_key(painter, rect, color)
                x += width + gap

    def _draw_footer_chips(self, painter: QPainter, deck: QRectF, compact: bool) -> None:
        chip_width = (deck.width() - 44) / 4
        footer_y = deck.bottom() - (12 if compact else 16)
        chip_height = 9 if compact else 12
        footer_colors = self.state.zones if self.state.effect == "static" else [
            "305cff",
            "15a8ff",
            "19d8ff",
            "8df3ff",
        ]
        for index, color in enumerate(footer_colors):
            chip = QRectF(deck.left() + 10 + chip_width * index, footer_y, chip_width - 10, chip_height)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(hex_to_qcolor(color))
            painter.drawRoundedRect(chip, chip_height / 2, chip_height / 2)

    def _paint_compact(self, painter: QPainter) -> None:
        backdrop = QLinearGradient(0, 0, self.width(), self.height())
        backdrop.setColorAt(0.0, QColor("#07121b"))
        backdrop.setColorAt(1.0, QColor("#0d1b28"))
        painter.fillRect(self.rect(), backdrop)

        frame = QRectF(10, 10, self.width() - 20, self.height() - 20)
        painter.setPen(QPen(QColor("#224963"), 1.4))
        painter.setBrush(QColor("#09131c"))
        painter.drawRoundedRect(frame, 22, 22)

        deck = QRectF(frame.left() + 14, frame.top() + 14, frame.width() - 28, frame.height() - 28)
        painter.setPen(QPen(QColor("#17384c"), 1.1))
        painter.setBrush(QColor("#0d1924"))
        painter.drawRoundedRect(deck, 18, 18)

        accent = QPen(QColor("#74deff"), 1.8)
        accent.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(accent)
        painter.drawLine(deck.left() + 16, deck.top() + 10, deck.right() - 16, deck.top() + 10)

        rows = [
            [1.0] * 12,
            [1.5] + [1.0] * 10 + [1.6],
            [1.9] + [1.0] * 9 + [1.9],
            [2.2] + [1.0] * 8 + [2.4],
            [1.3, 1.0, 1.0, 1.0, 4.4, 1.0, 1.0, 1.0, 1.3],
        ]
        self._paint_keyboard_rows(painter, deck, rows, gap=5.0, top_padding=24.0, bottom_padding=28.0)
        self._draw_footer_chips(painter, deck, compact=True)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.compact:
            self._paint_compact(painter)
            return

        backdrop = QLinearGradient(0, 0, self.width(), self.height())
        backdrop.setColorAt(0.0, QColor("#07121b"))
        backdrop.setColorAt(1.0, QColor("#0d1b28"))
        painter.fillRect(self.rect(), backdrop)

        frame = QRectF(18, 18, self.width() - 36, self.height() - 36)
        painter.setPen(QPen(QColor("#224963"), 1.5))
        painter.setBrush(QColor("#09131c"))
        painter.drawRoundedRect(frame, 26, 26)

        painter.setPen(QColor("#7ce2ff"))
        label_font = QFont()
        label_font.setPointSize(10)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.drawText(
            frame.adjusted(16, 12, -16, -12),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            f"{get_text(self.language, 'label_keyboard')} | "
            f"{effect_label(self.language, self.state.effect).upper()} | "
            f"{get_text(self.language, 'label_brightness')} {self.state.brightness}",
        )

        deck = QRectF(frame.left() + 18, frame.top() + 40, frame.width() - 36, frame.height() - 74)
        painter.setPen(QPen(QColor("#17384c"), 1.2))
        painter.setBrush(QColor("#0d1924"))
        painter.drawRoundedRect(deck, 18, 18)

        accent = QPen(QColor("#74deff"), 2.2)
        accent.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(accent)
        painter.drawLine(deck.left() + 18, deck.top() + 12, deck.right() - 18, deck.top() + 12)

        rows = [
            [1.0] * 14,
            [1.4] + [1.0] * 12 + [1.6],
            [1.8] + [1.0] * 11 + [1.8],
            [2.2] + [1.0] * 10 + [2.2],
            [1.4, 1.0, 1.0, 1.0, 6.2, 1.0, 1.0, 1.0, 1.0, 1.4],
        ]
        self._paint_keyboard_rows(painter, deck, rows, gap=6.0, top_padding=26.0, bottom_padding=36.0)
        self._draw_footer_chips(painter, deck, compact=False)


class LidPreview(QWidget):
    def __init__(self, language: str, compact: bool = False) -> None:
        super().__init__()
        self.language = language
        self.compact = compact
        self.state = LidState()
        if compact:
            self.setMinimumSize(320, 160)
        else:
            self.setMinimumSize(640, 330)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_state(self, state: LidState) -> None:
        self.state = state
        self.update()

    def set_language(self, language: str) -> None:
        self.language = language
        self.update()

    def _draw_logo_bars(self, painter: QPainter, lid: QRectF) -> None:
        glow = hex_to_qcolor(self.state.color)
        logo_width = min(lid.width() * 0.42, 190.0)
        logo_height = min(lid.height() * 0.7, 170.0)
        logo_rect = QRectF(
            lid.center().x() - logo_width / 2,
            lid.center().y() - logo_height / 2,
            logo_width,
            logo_height,
        )
        bar_width = max(10.0, logo_rect.width() * 0.085)
        gap = bar_width * 0.65
        bottom = logo_rect.bottom()
        center_left = logo_rect.center().x() - gap / 2 - bar_width
        center_right = logo_rect.center().x() + gap / 2

        bar_specs = [
            (logo_rect.left() + 8, bottom - logo_rect.height() * 0.86, bar_width, logo_rect.height() * 0.86),
            (center_left - gap - bar_width, bottom - logo_rect.height() * 0.60, bar_width, logo_rect.height() * 0.60),
            (center_left, bottom - logo_rect.height() * 0.78, bar_width, logo_rect.height() * 0.78),
            (center_right, bottom - logo_rect.height() * 0.78, bar_width, logo_rect.height() * 0.78),
            (center_right + gap + bar_width, bottom - logo_rect.height() * 0.60, bar_width, logo_rect.height() * 0.60),
            (logo_rect.right() - 8 - bar_width, bottom - logo_rect.height() * 0.86, bar_width, logo_rect.height() * 0.86),
        ]

        painter.setOpacity(0.16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow.lighter(165))
        for x, y, width, height in bar_specs:
            painter.drawRoundedRect(QRectF(x - 4, y - 4, width + 8, height + 8), 8, 8)

        painter.setOpacity(1.0)
        painter.setPen(QPen(glow.lighter(180), 1.4))
        painter.setBrush(glow)
        for x, y, width, height in bar_specs:
            painter.drawRoundedRect(QRectF(x, y, width, height), 6, 6)

    def _paint_compact(self, painter: QPainter) -> None:
        backdrop = QLinearGradient(0, 0, self.width(), self.height())
        backdrop.setColorAt(0.0, QColor("#08111a"))
        backdrop.setColorAt(1.0, QColor("#0e1c29"))
        painter.fillRect(self.rect(), backdrop)

        frame = QRectF(10, 10, self.width() - 20, self.height() - 20)
        painter.setPen(QPen(QColor("#224963"), 1.4))
        painter.setBrush(QColor("#09131c"))
        painter.drawRoundedRect(frame, 22, 22)

        lid = QRectF(frame.left() + 18, frame.top() + 18, frame.width() - 36, frame.height() - 36)
        painter.setPen(QPen(QColor("#1d394d"), 1.3))
        painter.setBrush(QColor("#0d1822"))
        painter.drawRoundedRect(lid, 18, 18)
        self._draw_logo_bars(painter, lid)

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.compact:
            self._paint_compact(painter)
            return

        backdrop = QLinearGradient(0, 0, self.width(), self.height())
        backdrop.setColorAt(0.0, QColor("#08111a"))
        backdrop.setColorAt(1.0, QColor("#0e1c29"))
        painter.fillRect(self.rect(), backdrop)

        frame = QRectF(18, 18, self.width() - 36, self.height() - 36)
        painter.setPen(QPen(QColor("#224963"), 1.5))
        painter.setBrush(QColor("#09131c"))
        painter.drawRoundedRect(frame, 26, 26)

        painter.setPen(QColor("#7ce2ff"))
        header_font = QFont()
        header_font.setPointSize(10)
        header_font.setBold(True)
        painter.setFont(header_font)
        painter.drawText(
            frame.adjusted(16, 12, -16, -12),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            f"{get_text(self.language, 'label_logo')} | "
            f"{effect_label(self.language, self.state.effect).upper()} | "
            f"{get_text(self.language, 'label_brightness')} {self.state.brightness}",
        )

        lid = QRectF(frame.left() + 56, frame.top() + 48, frame.width() - 112, frame.height() - 92)
        painter.setPen(QPen(QColor("#1d394d"), 1.5))
        painter.setBrush(QColor("#0d1822"))
        painter.drawRoundedRect(lid, 22, 22)
        self._draw_logo_bars(painter, lid)


class AssetLogoWidget(QWidget):
    def __init__(self, asset_path: Path) -> None:
        super().__init__()
        self.asset_path = asset_path
        self.icon = QIcon(str(asset_path)) if asset_path.exists() else QIcon()
        self.link_url = QUrl("https://remontti.com.br")
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("https://remontti.com.br")

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        frame = QRectF(8, 8, self.width() - 16, self.height() - 16)
        painter.setPen(QPen(QColor("#17384c"), 1.2))
        painter.setBrush(QColor("#09131c"))
        painter.drawRoundedRect(frame, 20, 20)

        if self.icon.isNull():
            painter.setPen(QColor("#6d8798"))
            painter.drawText(frame, Qt.AlignmentFlag.AlignCenter, "logo-remontti.svg")
            return

        target_width = int(frame.width() * 0.72)
        target_height = int(frame.height() * 0.72)
        pixmap = self.icon.pixmap(target_width, target_height)
        x = int(frame.center().x() - pixmap.width() / 2)
        y = int(frame.center().y() - pixmap.height() / 2)
        painter.drawPixmap(x, y, pixmap)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and not self.link_url.isEmpty():
            QDesktopServices.openUrl(self.link_url)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.settings = load_settings()
        self.language = self.settings.get("language", "pt_BR")
        self.keyboard_state = KeyboardState()
        self.lid_state = LidState()
        self.detected_device: HidrawDevice | None = None
        self._syncing_ui = False
        self.page_status_badges: list[QLabel] = []

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.resize(1460, 900)

        self._build_ui()
        self._load_device_status()
        self._refresh_profiles(initial=True)
        self._sync_ui_from_state()
        self._apply_language(self.language, persist=False)
        self._navigate_to(0)

    def _t(self, key: str, **kwargs) -> str:
        return get_text(self.language, key, **kwargs)

    def _effect_label(self, effect: str) -> str:
        return effect_label(self.language, effect)

    def _direction_label(self, direction: str) -> str:
        return direction_label(self.language, direction)

    def _preset_label(self, name: str) -> str:
        return preset_label(self.language, name)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(18)

        root.addWidget(self._build_sidebar(), 0)

        self.page_stack = QStackedWidget()
        root.addWidget(self.page_stack, 1)

        self._build_colors_page()
        self._build_effects_page()
        self._build_logo_page()
        self._build_profiles_page()
        self._build_diagnostics_page()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sideRail")
        sidebar.setFixedWidth(290)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(16)

        self.brand_eyebrow = QLabel()
        self.brand_eyebrow.setProperty("eyebrow", True)

        self.brand_title = QLabel()
        self.brand_title.setProperty("brandTitle", True)
        self.brand_title.setTextFormat(Qt.TextFormat.RichText)

        self.brand_description = QLabel()
        self.brand_description.setWordWrap(True)
        self.brand_description.setProperty("muted", True)

        layout.addWidget(self.brand_eyebrow)
        layout.addWidget(self.brand_title)
        layout.addWidget(self.brand_description)

        self.sidebar_sections_label = QLabel()
        self.sidebar_sections_label.setProperty("sectionTitle", True)
        layout.addWidget(self.sidebar_sections_label)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for index, _page_id in enumerate(PAGE_IDS):
            button = QPushButton()
            button.setCheckable(True)
            button.setObjectName("navButton")
            button.setMinimumHeight(72)
            button.clicked.connect(lambda checked=False, idx=index: self._navigate_to(idx))
            self.nav_group.addButton(button, index)
            self.nav_buttons.append(button)
            layout.addWidget(button)

        layout.addStretch(1)

        status_card = QFrame()
        status_card.setObjectName("softCard")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(14, 14, 14, 14)
        status_layout.setSpacing(10)

        self.sidebar_status_title = QLabel()
        self.sidebar_status_title.setProperty("sectionTitle", True)
        status_layout.addWidget(self.sidebar_status_title)

        language_row = QHBoxLayout()
        language_row.setSpacing(10)
        self.language_combo = QComboBox()
        for code, label in LANGUAGE_OPTIONS:
            self.language_combo.addItem(label, userData=code)
        self.language_combo.currentIndexChanged.connect(self._language_changed)
        language_row.addWidget(self.language_combo, 1)
        status_layout.addLayout(language_row)

        self.sidebar_save_button = QPushButton()
        self.sidebar_save_button.clicked.connect(self._save_profile)
        status_layout.addWidget(self.sidebar_save_button)

        self.sidebar_apply_all_button = QPushButton()
        self.sidebar_apply_all_button.setObjectName("accentButton")
        self.sidebar_apply_all_button.clicked.connect(self._apply_all)
        status_layout.addWidget(self.sidebar_apply_all_button)

        layout.addWidget(status_card)
        return sidebar

    def _make_scroll_page(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(widget)
        return scroll

    def _make_page_header(self) -> tuple[QWidget, QLabel, QLabel, QLabel]:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(6)

        title = QLabel()
        title.setProperty("pageTitle", True)
        subtitle = QLabel()
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", True)
        left.addWidget(title)
        left.addWidget(subtitle)

        badge = QLabel()
        badge.setProperty("pill", True)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setMinimumWidth(138)
        badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.page_status_badges.append(badge)

        layout.addLayout(left, 1)
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        return wrapper, title, subtitle, badge

    def _make_card(self) -> tuple[QFrame, QVBoxLayout, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("panelCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QLabel()
        title.setProperty("sectionTitle", True)
        subtitle = QLabel()
        subtitle.setWordWrap(True)
        subtitle.setProperty("muted", True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return card, layout, title, subtitle

    def _add_slider_row(
        self,
        layout: QVBoxLayout,
        title_label: QLabel,
        slider: QSlider,
        value_label: QLabel,
    ) -> None:
        wrapper = QVBoxLayout()
        wrapper.setSpacing(6)

        header = QHBoxLayout()
        header.setSpacing(10)
        title_label.setMinimumWidth(86)
        value_label.setProperty("value", True)
        header.addWidget(title_label)
        header.addStretch(1)
        header.addWidget(value_label)

        wrapper.addLayout(header)
        wrapper.addWidget(slider)
        layout.addLayout(wrapper)

    def _build_colors_page(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(18)

        intro, self.colors_intro_title, self.colors_intro_subtitle, self.colors_status_badge = self._make_page_header()
        page_layout.addWidget(intro)

        body = QHBoxLayout()
        body.setSpacing(18)
        page_layout.addLayout(body)

        left = QVBoxLayout()
        left.setSpacing(18)
        body.addLayout(left, 5)

        preview_card, preview_layout, self.colors_preview_title, self.colors_preview_subtitle = self._make_card()
        self.keyboard_static_preview = KeyboardPreview(self.language)
        preview_layout.addWidget(self.keyboard_static_preview)
        left.addWidget(preview_card, 1)

        presets_card, presets_layout, self.colors_presets_title, self.colors_presets_subtitle = self._make_card()
        preset_grid = QGridLayout()
        preset_grid.setHorizontalSpacing(12)
        preset_grid.setVerticalSpacing(12)
        self.keyboard_preset_cards: dict[str, PresetCard] = {}
        self.keyboard_preset_group = QButtonGroup(self)
        self.keyboard_preset_group.setExclusive(True)

        visible_presets = [
            (preset_name, preset)
            for preset_name, preset in BUILTIN_PRESETS.items()
            if preset_name != "off"
        ]
        for index, (preset_name, preset) in enumerate(visible_presets):
            card = PresetCard(preset_name, preset, self.language)
            card.clicked.connect(
                lambda checked=False, name=preset_name: self._apply_keyboard_preset_ui(name)
            )
            self.keyboard_preset_group.addButton(card)
            self.keyboard_preset_cards[preset_name] = card
            preset_grid.addWidget(card, index // 2, index % 2)

        presets_layout.addLayout(preset_grid)
        left.addWidget(presets_card)

        right = QVBoxLayout()
        right.setSpacing(18)
        body.addLayout(right, 3)

        static_card, static_layout, self.colors_static_title, self.colors_static_subtitle = self._make_card()
        self.keyboard_static_brightness = QSlider(Qt.Orientation.Horizontal)
        self.keyboard_static_brightness.setRange(0, 100)
        self.keyboard_static_brightness_value = QLabel("70%")
        self.keyboard_static_brightness_value.setFont(value_font())
        self.keyboard_static_brightness_label = QLabel()
        self._add_slider_row(
            static_layout,
            self.keyboard_static_brightness_label,
            self.keyboard_static_brightness,
            self.keyboard_static_brightness_value,
        )

        self.keyboard_static_hint = QLabel()
        self.keyboard_static_hint.setWordWrap(True)
        self.keyboard_static_hint.setProperty("muted", True)
        static_layout.addWidget(self.keyboard_static_hint)
        right.addWidget(static_card)

        zones_card, zones_layout, self.colors_zones_title, self.colors_zones_subtitle = self._make_card()
        self.zone_labels: list[QLabel] = []
        self.keyboard_zone_fields: list[ColorField] = []
        for index in range(4):
            zone_label = QLabel()
            field = ColorField(f"Zone {index + 1}", self.keyboard_state.zones[index])
            field.color_changed.connect(self._sync_keyboard_static_editor)
            self.zone_labels.append(zone_label)
            self.keyboard_zone_fields.append(field)

            row = QHBoxLayout()
            row.setSpacing(10)
            zone_label.setMinimumWidth(86)
            row.addWidget(zone_label)
            row.addWidget(field, 1)
            zones_layout.addLayout(row)

        keyboard_actions = QHBoxLayout()
        keyboard_actions.setSpacing(10)
        self.keyboard_off_button = QPushButton()
        self.keyboard_off_button.setObjectName("ghostButton")
        self.keyboard_off_button.clicked.connect(self._turn_off_keyboard)
        self.keyboard_apply_button = QPushButton()
        self.keyboard_apply_button.setObjectName("accentButton")
        self.keyboard_apply_button.clicked.connect(self._apply_keyboard_static)
        keyboard_actions.addWidget(self.keyboard_off_button)
        keyboard_actions.addWidget(self.keyboard_apply_button, 1)
        zones_layout.addLayout(keyboard_actions)

        right.addWidget(zones_card)

        logo_card = QFrame()
        logo_card.setObjectName("panelCard")
        logo_layout = QVBoxLayout(logo_card)
        logo_layout.setContentsMargins(18, 18, 18, 18)
        logo_layout.setSpacing(0)
        self.author_logo_widget = AssetLogoWidget(AUTHOR_LOGO_PATH)
        logo_layout.addWidget(self.author_logo_widget, 1)
        right.addWidget(logo_card, 1)

        self.keyboard_static_brightness.valueChanged.connect(self._sync_keyboard_static_editor)
        self.page_stack.addWidget(self._make_scroll_page(page))

    def _build_effects_page(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(18)

        intro, self.effects_intro_title, self.effects_intro_subtitle, self.effects_status_badge = self._make_page_header()
        page_layout.addWidget(intro)

        body = QVBoxLayout()
        body.setSpacing(18)
        page_layout.addLayout(body)

        engine_card, engine_layout, self.effects_engine_title, self.effects_engine_subtitle = self._make_card()
        self.keyboard_effect_label = QLabel()
        self.keyboard_effect = QComboBox()
        self.keyboard_direction_label = QLabel()
        self.keyboard_direction = QComboBox()
        self.keyboard_effect_brightness = QSlider(Qt.Orientation.Horizontal)
        self.keyboard_effect_brightness.setRange(0, 100)
        self.keyboard_speed = QSlider(Qt.Orientation.Horizontal)
        self.keyboard_speed.setRange(0, 9)
        self.keyboard_effect_brightness_value = QLabel("70%")
        self.keyboard_speed_value = QLabel("5")
        self.keyboard_effect_brightness_value.setFont(value_font())
        self.keyboard_speed_value.setFont(value_font())
        self.keyboard_effect_brightness_label = QLabel()
        self.keyboard_speed_label = QLabel()

        effect_row = QHBoxLayout()
        effect_row.setSpacing(10)
        self.keyboard_effect_label.setMinimumWidth(86)
        effect_row.addWidget(self.keyboard_effect_label)
        effect_row.addWidget(self.keyboard_effect, 1)
        engine_layout.addLayout(effect_row)

        self._add_slider_row(
            engine_layout,
            self.keyboard_effect_brightness_label,
            self.keyboard_effect_brightness,
            self.keyboard_effect_brightness_value,
        )
        self._add_slider_row(
            engine_layout,
            self.keyboard_speed_label,
            self.keyboard_speed,
            self.keyboard_speed_value,
        )

        direction_row = QHBoxLayout()
        direction_row.setSpacing(10)
        self.keyboard_direction_label.setMinimumWidth(86)
        direction_row.addWidget(self.keyboard_direction_label)
        direction_row.addWidget(self.keyboard_direction, 1)
        engine_layout.addLayout(direction_row)

        self.keyboard_effect_hint = QLabel()
        self.keyboard_effect_hint.setWordWrap(True)
        self.keyboard_effect_hint.setProperty("muted", True)
        engine_layout.addWidget(self.keyboard_effect_hint)

        effect_actions = QHBoxLayout()
        effect_actions.setSpacing(10)
        self.keyboard_to_static_button = QPushButton()
        self.keyboard_to_static_button.setObjectName("ghostButton")
        self.keyboard_to_static_button.clicked.connect(self._return_keyboard_to_static)
        self.keyboard_effect_apply_button = QPushButton()
        self.keyboard_effect_apply_button.setObjectName("accentButton")
        self.keyboard_effect_apply_button.clicked.connect(self._apply_keyboard_effect)
        effect_actions.addWidget(self.keyboard_to_static_button)
        effect_actions.addWidget(self.keyboard_effect_apply_button, 1)
        engine_layout.addLayout(effect_actions)
        body.addWidget(engine_card)

        notes_card, notes_layout, self.effects_notes_title, self.effects_notes_subtitle = self._make_card()
        self.keyboard_effect_rules = QLabel()
        self.keyboard_effect_rules.setWordWrap(True)
        self.keyboard_effect_rules.setProperty("muted", True)
        notes_layout.addWidget(self.keyboard_effect_rules)
        body.addWidget(notes_card)
        body.addStretch(1)

        self.keyboard_effect.currentIndexChanged.connect(self._sync_keyboard_effect_editor)
        self.keyboard_effect_brightness.valueChanged.connect(self._sync_keyboard_effect_editor)
        self.keyboard_speed.valueChanged.connect(self._sync_keyboard_effect_editor)
        self.keyboard_direction.currentIndexChanged.connect(self._sync_keyboard_effect_editor)

        self.page_stack.addWidget(self._make_scroll_page(page))

    def _build_logo_page(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(18)

        intro, self.logo_intro_title, self.logo_intro_subtitle, self.logo_status_badge = self._make_page_header()
        page_layout.addWidget(intro)

        body = QHBoxLayout()
        body.setSpacing(18)
        page_layout.addLayout(body)

        preview_card, preview_layout, self.logo_preview_title, self.logo_preview_subtitle = self._make_card()
        self.lid_preview = LidPreview(self.language)
        preview_layout.addWidget(self.lid_preview)
        body.addWidget(preview_card, 5)

        right = QVBoxLayout()
        right.setSpacing(18)
        body.addLayout(right, 3)

        lid_card, lid_layout, self.logo_controls_title, self.logo_controls_subtitle = self._make_card()
        self.lid_effect_label = QLabel()
        self.lid_effect = QComboBox()
        self.lid_brightness = QSlider(Qt.Orientation.Horizontal)
        self.lid_brightness.setRange(0, 100)
        self.lid_speed = QSlider(Qt.Orientation.Horizontal)
        self.lid_speed.setRange(0, 9)
        self.lid_color = ColorField("Logo", self.lid_state.color)
        self.lid_brightness_value = QLabel("70%")
        self.lid_speed_value = QLabel("4")
        self.lid_brightness_value.setFont(value_font())
        self.lid_speed_value.setFont(value_font())
        self.lid_brightness_label = QLabel()
        self.lid_speed_label = QLabel()
        self.lid_color_label = QLabel()

        lid_effect_row = QHBoxLayout()
        lid_effect_row.setSpacing(10)
        self.lid_effect_label.setMinimumWidth(86)
        lid_effect_row.addWidget(self.lid_effect_label)
        lid_effect_row.addWidget(self.lid_effect, 1)
        lid_layout.addLayout(lid_effect_row)

        self._add_slider_row(lid_layout, self.lid_brightness_label, self.lid_brightness, self.lid_brightness_value)
        self._add_slider_row(lid_layout, self.lid_speed_label, self.lid_speed, self.lid_speed_value)

        lid_color_row = QHBoxLayout()
        lid_color_row.setSpacing(10)
        self.lid_color_label.setMinimumWidth(86)
        lid_color_row.addWidget(self.lid_color_label)
        lid_color_row.addWidget(self.lid_color, 1)
        lid_layout.addLayout(lid_color_row)

        self.lid_note = QLabel()
        self.lid_note.setWordWrap(True)
        self.lid_note.setProperty("muted", True)
        lid_layout.addWidget(self.lid_note)

        lid_actions = QHBoxLayout()
        lid_actions.setSpacing(10)
        self.lid_blue_button = QPushButton()
        self.lid_blue_button.setObjectName("ghostButton")
        self.lid_blue_button.clicked.connect(lambda: self.lid_color.set_value("00aaff"))
        self.lid_apply_button = QPushButton()
        self.lid_apply_button.setObjectName("accentButton")
        self.lid_apply_button.clicked.connect(self._apply_lid)
        lid_actions.addWidget(self.lid_blue_button)
        lid_actions.addWidget(self.lid_apply_button, 1)
        lid_layout.addLayout(lid_actions)
        right.addWidget(lid_card)

        supported_card, supported_layout, self.logo_supported_title, self.logo_supported_subtitle = self._make_card()
        self.diag_keyboard_effects_short = QLabel()
        self.diag_keyboard_effects_short.setWordWrap(True)
        self.diag_keyboard_effects_short.setProperty("mono", True)
        self.diag_keyboard_effects_short.setFont(mono_font())
        self.diag_lid_effects_short = QLabel()
        self.diag_lid_effects_short.setWordWrap(True)
        self.diag_lid_effects_short.setProperty("mono", True)
        self.diag_lid_effects_short.setFont(mono_font())
        self.logo_keyboard_label = QLabel()
        self.logo_logo_label = QLabel()
        supported_layout.addWidget(self.logo_keyboard_label)
        supported_layout.addWidget(self.diag_keyboard_effects_short)
        supported_layout.addWidget(self.logo_logo_label)
        supported_layout.addWidget(self.diag_lid_effects_short)
        right.addWidget(supported_card)
        right.addStretch(1)

        self.lid_effect.currentIndexChanged.connect(self._sync_lid_preview)
        self.lid_brightness.valueChanged.connect(self._sync_lid_preview)
        self.lid_speed.valueChanged.connect(self._sync_lid_preview)
        self.lid_color.color_changed.connect(self._sync_lid_preview)

        self.page_stack.addWidget(self._make_scroll_page(page))

    def _build_profiles_page(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(18)

        intro, self.profiles_intro_title, self.profiles_intro_subtitle, self.profiles_status_badge = self._make_page_header()
        page_layout.addWidget(intro)

        body = QHBoxLayout()
        body.setSpacing(18)
        page_layout.addLayout(body)

        left = QVBoxLayout()
        left.setSpacing(18)
        body.addLayout(left, 3)

        keyboard_card, keyboard_layout, self.profile_keyboard_title, self.profile_keyboard_subtitle = self._make_card()
        keyboard_meta_row = QHBoxLayout()
        keyboard_meta_row.setContentsMargins(0, 0, 0, 0)
        keyboard_meta_row.setSpacing(10)
        keyboard_meta_row.addStretch(1)
        self.profile_keyboard_brightness_badge = QLabel()
        self.profile_keyboard_brightness_badge.setProperty("pill", True)
        self.profile_keyboard_brightness_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keyboard_meta_row.addWidget(self.profile_keyboard_brightness_badge, 0, Qt.AlignmentFlag.AlignRight)
        keyboard_layout.addLayout(keyboard_meta_row)

        self.profile_keyboard_preview = KeyboardPreview(self.language, compact=True)
        self.profile_keyboard_preview.setMinimumHeight(180)
        self.profile_keyboard_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        keyboard_layout.addWidget(self.profile_keyboard_preview, 1)
        left.addWidget(keyboard_card, 1)

        logo_card, logo_layout, self.profile_logo_title, self.profile_logo_subtitle = self._make_card()
        logo_meta_row = QHBoxLayout()
        logo_meta_row.setContentsMargins(0, 0, 0, 0)
        logo_meta_row.setSpacing(10)
        logo_meta_row.addStretch(1)
        self.profile_logo_brightness_badge = QLabel()
        self.profile_logo_brightness_badge.setProperty("pill", True)
        self.profile_logo_brightness_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_meta_row.addWidget(self.profile_logo_brightness_badge, 0, Qt.AlignmentFlag.AlignRight)
        logo_layout.addLayout(logo_meta_row)

        self.profile_lid_preview = LidPreview(self.language, compact=True)
        self.profile_lid_preview.setMinimumHeight(180)
        self.profile_lid_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        logo_layout.addWidget(self.profile_lid_preview, 1)
        left.addWidget(logo_card, 1)

        library_card, library_layout, self.profiles_library_title, self.profiles_library_subtitle = self._make_card()
        self.profile_list = QListWidget()
        self.profile_list.itemClicked.connect(lambda item: self._load_selected_profile())
        library_layout.addWidget(self.profile_list, 1)

        self.profile_library_hint = QLabel()
        self.profile_library_hint.setWordWrap(True)
        self.profile_library_hint.setProperty("muted", True)
        library_layout.addWidget(self.profile_library_hint)

        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.profile_delete_button = QPushButton()
        self.profile_delete_button.setObjectName("ghostButton")
        self.profile_delete_button.clicked.connect(self._delete_selected_profile)
        action_row.addWidget(self.profile_delete_button)
        action_row.addStretch(1)
        self.profile_apply_button = QPushButton()
        self.profile_apply_button.setObjectName("accentButton")
        self.profile_apply_button.clicked.connect(self._apply_selected_profile)
        action_row.addWidget(self.profile_apply_button)
        library_layout.addLayout(action_row)
        body.addWidget(library_card, 4)

        self.page_stack.addWidget(self._make_scroll_page(page))

    def _build_diagnostics_page(self) -> None:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(18)

        intro, self.diag_intro_title, self.diag_intro_subtitle, self.diag_status_badge = self._make_page_header()
        page_layout.addWidget(intro)

        body = QVBoxLayout()
        body.setSpacing(18)
        page_layout.addLayout(body)

        hardware_card, hardware_layout, self.diag_controller_title, self.diag_controller_subtitle = self._make_card()
        self.diag_device_node_label = QLabel()
        self.diag_hid_name_label = QLabel()
        self.diag_path_label = QLabel()
        self.diag_device_label = QLabel()
        self.diag_device_label.setProperty("value", True)
        self.diag_device_label.setFont(value_font())
        self.diag_name_label = QLabel()
        self.diag_name_label.setProperty("mono", True)
        self.diag_name_label.setFont(mono_font())
        self.diag_phys_label = QLabel()
        self.diag_phys_label.setProperty("mono", True)
        self.diag_phys_label.setFont(mono_font())
        self.diag_permission_label = QLabel()
        self.diag_permission_label.setWordWrap(True)
        self.diag_permission_label.setProperty("muted", True)

        hardware_layout.addWidget(self.diag_device_node_label)
        hardware_layout.addWidget(self.diag_device_label)
        hardware_layout.addWidget(self.diag_hid_name_label)
        hardware_layout.addWidget(self.diag_name_label)
        hardware_layout.addWidget(self.diag_path_label)
        hardware_layout.addWidget(self.diag_phys_label)
        hardware_layout.addWidget(self.diag_permission_label)
        body.addWidget(hardware_card)

        capability_card, capability_layout, self.diag_caps_title, self.diag_caps_subtitle = self._make_card()
        self.diag_keyboard_effects_label_title = QLabel()
        self.diag_keyboard_effects_label = QLabel()
        self.diag_keyboard_effects_label.setWordWrap(True)
        self.diag_keyboard_effects_label.setProperty("mono", True)
        self.diag_keyboard_effects_label.setFont(mono_font())
        self.diag_lid_effects_label_title = QLabel()
        self.diag_lid_effects_label = QLabel()
        self.diag_lid_effects_label.setWordWrap(True)
        self.diag_lid_effects_label.setProperty("mono", True)
        self.diag_lid_effects_label.setFont(mono_font())
        capability_layout.addWidget(self.diag_keyboard_effects_label_title)
        capability_layout.addWidget(self.diag_keyboard_effects_label)
        capability_layout.addWidget(self.diag_lid_effects_label_title)
        capability_layout.addWidget(self.diag_lid_effects_label)
        body.addWidget(capability_card)

        runtime_card, runtime_layout, self.diag_runtime_title, self.diag_runtime_subtitle = self._make_card()
        self.diag_editor_label = QLabel()
        self.diag_editor_summary = QLabel()
        self.diag_editor_summary.setWordWrap(True)
        self.diag_editor_summary.setProperty("muted", True)
        self.diag_status_label = QLabel()
        self.diag_session_label = QLabel()
        self.diag_session_label.setWordWrap(True)
        self.diag_session_label.setProperty("muted", True)
        runtime_layout.addWidget(self.diag_editor_label)
        runtime_layout.addWidget(self.diag_editor_summary)
        runtime_layout.addWidget(self.diag_status_label)
        runtime_layout.addWidget(self.diag_session_label)
        body.addWidget(runtime_card)
        body.addStretch(1)

        self.page_stack.addWidget(self._make_scroll_page(page))

    def _language_changed(self) -> None:
        if self._syncing_ui:
            return
        code = self.language_combo.currentData()
        if isinstance(code, str):
            self._apply_language(code)

    def _apply_language(self, language: str, persist: bool = True) -> None:
        self.language = language
        self.settings["language"] = language
        if persist:
            save_settings(self.settings)

        self.setWindowTitle(APP_DISPLAY_NAME)
        self.brand_eyebrow.setText(self._t("brand_eyebrow"))
        self.brand_title.setText(f"{APP_SHORT_NAME} <span style='color:#ff4b3a'>Predator</span>")
        self.brand_description.setText(self._t("brand_description"))
        self.sidebar_sections_label.setText(self._t("sidebar_sections"))
        self.sidebar_status_title.setText(self._t("sidebar_status_title"))
        self.sidebar_save_button.setText(self._t("action_save_profile"))
        self.sidebar_apply_all_button.setText(self._t("action_apply_all"))

        with QSignalBlocker(self.language_combo):
            self._set_combo_by_data(self.language_combo, language)

        for page_id, button in zip(PAGE_IDS, self.nav_buttons):
            button.setText(
                f"{self._t(f'nav_{page_id}_title')}\n{self._t(f'nav_{page_id}_subtitle')}"
            )

        self.colors_intro_title.setText(self._t("page_colors_title"))
        self.colors_intro_subtitle.setText(self._t("page_colors_subtitle"))
        self.effects_intro_title.setText(self._t("page_effects_title"))
        self.effects_intro_subtitle.setText(self._t("page_effects_subtitle"))
        self.logo_intro_title.setText(self._t("page_logo_title"))
        self.logo_intro_subtitle.setText(self._t("page_logo_subtitle"))
        self.profiles_intro_title.setText(self._t("page_profiles_title"))
        self.profiles_intro_subtitle.setText(self._t("page_profiles_subtitle"))
        self.diag_intro_title.setText(self._t("page_diagnostics_title"))
        self.diag_intro_subtitle.setText(self._t("page_diagnostics_subtitle"))

        self.colors_preview_title.setText(self._t("card_keyboard_preview_title"))
        self.colors_preview_subtitle.setText(self._t("card_keyboard_preview_subtitle"))
        self.colors_presets_title.setText(self._t("card_preset_library_title"))
        self.colors_presets_subtitle.setText(self._t("card_preset_library_subtitle"))
        self.colors_static_title.setText(self._t("card_static_layout_title"))
        self.colors_static_subtitle.setText(self._t("card_static_layout_subtitle"))
        self.colors_zones_title.setText(self._t("card_zone_colors_title"))
        self.colors_zones_subtitle.setText(self._t("card_zone_colors_subtitle"))
        self.keyboard_static_brightness_label.setText(self._t("label_brightness"))
        self.keyboard_static_hint.setText(self._t("hint_static_page"))
        self.keyboard_off_button.setText(self._t("action_turn_off_key"))
        self.keyboard_apply_button.setText(self._t("action_apply_static"))

        for index, zone_label in enumerate(self.zone_labels, start=1):
            zone_text = self._t(f"label_zone_{index}")
            zone_label.setText(zone_text)
            self.keyboard_zone_fields[index - 1].set_label_text(zone_text)

        self.effects_engine_title.setText(self._t("card_effect_engine_title"))
        self.effects_engine_subtitle.setText(self._t("card_effect_engine_subtitle"))
        self.effects_notes_title.setText(self._t("card_effect_notes_title"))
        self.effects_notes_subtitle.setText(self._t("card_effect_notes_subtitle"))
        self.keyboard_effect_label.setText(self._t("label_effect"))
        self.keyboard_effect_brightness_label.setText(self._t("label_brightness"))
        self.keyboard_speed_label.setText(self._t("label_speed"))
        self.keyboard_direction_label.setText(self._t("label_direction"))
        self.keyboard_to_static_button.setText(self._t("action_back_to_colors"))
        self.keyboard_effect_apply_button.setText(self._t("action_apply_effect"))
        self.keyboard_effect_rules.setText(self._t("hint_effect_rules"))

        self.logo_preview_title.setText(self._t("card_logo_preview_title"))
        self.logo_preview_subtitle.setText(self._t("card_logo_preview_subtitle"))
        self.logo_controls_title.setText(self._t("card_logo_controls_title"))
        self.logo_controls_subtitle.setText(self._t("card_logo_controls_subtitle"))
        self.logo_supported_title.setText(self._t("card_logo_supported_title"))
        self.logo_supported_subtitle.setText(self._t("card_logo_supported_subtitle"))
        self.lid_effect_label.setText(self._t("label_effect"))
        self.lid_brightness_label.setText(self._t("label_brightness"))
        self.lid_speed_label.setText(self._t("label_speed"))
        self.lid_color_label.setText(self._t("label_color"))
        self.lid_note.setText(self._t("hint_logo_animated"))
        self.lid_blue_button.setText(self._t("action_predator_blue"))
        self.lid_apply_button.setText(self._t("action_apply_logo"))
        self.logo_keyboard_label.setText(self._t("label_keyboard"))
        self.logo_logo_label.setText(self._t("label_logo"))
        self.lid_color.set_label_text(self._t("label_color"))

        self.profiles_library_title.setText(self._t("card_profile_library_title"))
        self.profiles_library_subtitle.setText(self._t("card_profile_library_subtitle"))
        self.profile_keyboard_title.setText(self._t("label_keyboard"))
        self.profile_keyboard_subtitle.setText(self._t("profiles_keyboard_card_subtitle"))
        self.profile_logo_title.setText(self._t("label_logo"))
        self.profile_logo_subtitle.setText(self._t("profiles_logo_card_subtitle"))
        self.profile_keyboard_brightness_badge.setText(f"{self.keyboard_state.brightness}%")
        self.profile_logo_brightness_badge.setText(f"{self.lid_state.brightness}%")
        self.profile_delete_button.setText(self._t("action_delete_profile"))
        self.profile_apply_button.setText(self._t("action_apply_profile"))
        self.profile_library_hint.setText(self._t("profiles_library_hint"))

        self.diag_controller_title.setText(self._t("card_controller_title"))
        self.diag_controller_subtitle.setText(self._t("card_controller_subtitle"))
        self.diag_caps_title.setText(self._t("card_capabilities_title"))
        self.diag_caps_subtitle.setText(self._t("card_capabilities_subtitle"))
        self.diag_runtime_title.setText(self._t("card_runtime_title"))
        self.diag_runtime_subtitle.setText(self._t("card_runtime_subtitle"))
        self.diag_device_node_label.setText(self._t("label_device_node"))
        self.diag_hid_name_label.setText(self._t("label_hid_name"))
        self.diag_path_label.setText(self._t("label_physical_path"))
        self.diag_permission_label.setText(self._t("hint_permission"))
        self.diag_keyboard_effects_label_title.setText(self._t("label_keyboard_effects"))
        self.diag_lid_effects_label_title.setText(self._t("label_logo_effects"))
        self.diag_editor_label.setText(self._t("label_editor"))
        self.diag_status_label.setText(self._t("label_status"))

        for card in self.keyboard_preset_cards.values():
            card.set_language(language)

        self.keyboard_static_preview.set_language(language)
        self.lid_preview.set_language(language)
        self.profile_keyboard_preview.set_language(language)
        self.profile_lid_preview.set_language(language)

        self._populate_effect_combo(self.keyboard_effect, "keyboard", self.keyboard_state.effect)
        self._populate_effect_combo(self.lid_effect, "lid", self.lid_state.effect)
        self._populate_direction_combo(self.keyboard_direction, self.keyboard_state.direction)
        self._sync_keyboard_effect_editor()
        self._sync_keyboard_static_editor()
        self._sync_lid_preview()
        self._load_device_status()
        self._update_header_and_summaries()

    def _populate_effect_combo(self, combo: QComboBox, device: str, selected: str) -> None:
        with QSignalBlocker(combo):
            combo.clear()
            for effect in SUPPORTED_EFFECTS_BY_DEVICE[device]:
                combo.addItem(self._effect_label(effect), userData=effect)
            self._set_combo_by_data(combo, selected)

    def _populate_direction_combo(self, combo: QComboBox, selected: str) -> None:
        with QSignalBlocker(combo):
            combo.clear()
            for direction in ("none", "right", "left"):
                combo.addItem(self._direction_label(direction), userData=direction)
            self._set_combo_by_data(combo, selected)

    def _set_combo_by_data(self, combo: QComboBox, value: str) -> None:
        for index in range(combo.count()):
            if combo.itemData(index) == value:
                combo.setCurrentIndex(index)
                return

    def _navigate_to(self, index: int) -> None:
        self.page_stack.setCurrentIndex(index)
        button = self.nav_group.button(index)
        if button is not None:
            button.setChecked(True)

    def _set_session_text(self, text: str) -> None:
        self.diag_session_label.setText(text)

    def _set_status_ready(self) -> None:
        for badge in self.page_status_badges:
            badge.setText(self._t("status_ready"))

    def _set_status_offline(self, message: str) -> None:
        for badge in self.page_status_badges:
            badge.setText(self._t("status_offline"))
        self._set_session_text(message)

    def _load_device_status(self) -> None:
        try:
            self.detected_device = detect_rgb_device(None)
        except Exception as exc:  # pragma: no cover
            self.detected_device = None
            self._set_status_offline(f"{self._t('diagnostics_error_prefix')}: {exc}")
            self.diag_device_label.setText(self._t("diagnostics_pending"))
            self.diag_name_label.setText(str(exc))
            self.diag_phys_label.setText(self._t("diagnostics_path_pending"))
            return

        assert self.detected_device is not None
        self._set_status_ready()
        self.diag_device_label.setText(self.detected_device.devnode)
        self.diag_name_label.setText(self.detected_device.hid_name or self.detected_device.sysfs_name)
        self.diag_phys_label.setText(self.detected_device.hid_phys or self.detected_device.sysfs_name)

    def _keyboard_static_state_from_ui(self) -> KeyboardState:
        return KeyboardState(
            effect="static",
            brightness=self.keyboard_static_brightness.value(),
            speed=self.keyboard_state.speed,
            direction=self.keyboard_state.direction,
            zones=[field.value() for field in self.keyboard_zone_fields],
        )

    def _keyboard_effect_state_from_ui(self) -> KeyboardState:
        return KeyboardState(
            effect=self.keyboard_effect.currentData() or "static",
            brightness=self.keyboard_effect_brightness.value(),
            speed=self.keyboard_speed.value(),
            direction=self.keyboard_direction.currentData() or "right",
            zones=[field.value() for field in self.keyboard_zone_fields],
        )

    def _lid_state_from_ui(self) -> LidState:
        return LidState(
            effect=self.lid_effect.currentData() or "static",
            brightness=self.lid_brightness.value(),
            speed=self.lid_speed.value(),
            color=self.lid_color.value(),
        )

    def _matching_preset_name(self, state: KeyboardState) -> str | None:
        for preset_name, preset in BUILTIN_PRESETS.items():
            if preset_name == "off":
                continue
            if (
                preset["brightness"] == state.brightness
                and list(preset["zones"]) == list(state.zones)
            ):
                return preset_name
        return None

    def _set_active_preset_card(self, preset_name: str | None) -> None:
        for name, button in self.keyboard_preset_cards.items():
            button.blockSignals(True)
            button.setChecked(name == preset_name)
            button.blockSignals(False)
            button.update()

    def _sync_ui_from_state(self) -> None:
        self._syncing_ui = True
        with ExitStack() as stack:
            stack.enter_context(QSignalBlocker(self.keyboard_static_brightness))
            stack.enter_context(QSignalBlocker(self.keyboard_effect_brightness))
            stack.enter_context(QSignalBlocker(self.keyboard_speed))
            stack.enter_context(QSignalBlocker(self.keyboard_effect))
            stack.enter_context(QSignalBlocker(self.keyboard_direction))
            stack.enter_context(QSignalBlocker(self.lid_effect))
            stack.enter_context(QSignalBlocker(self.lid_brightness))
            stack.enter_context(QSignalBlocker(self.lid_speed))

            self.keyboard_static_brightness.setValue(self.keyboard_state.brightness)
            self.keyboard_effect_brightness.setValue(self.keyboard_state.brightness)
            self.keyboard_speed.setValue(self.keyboard_state.speed)
            self._set_combo_by_data(self.keyboard_effect, self.keyboard_state.effect)
            self._set_combo_by_data(self.keyboard_direction, self.keyboard_state.direction)

            for field, value in zip(self.keyboard_zone_fields, self.keyboard_state.zones):
                field.set_value(value, emit=False)

            self._set_combo_by_data(self.lid_effect, self.lid_state.effect)
            self.lid_brightness.setValue(self.lid_state.brightness)
            self.lid_speed.setValue(self.lid_state.speed)
            self.lid_color.set_value(self.lid_state.color, emit=False)

        self._syncing_ui = False
        self._sync_keyboard_static_editor()
        self._sync_keyboard_effect_editor()
        self._sync_lid_preview()

    def _update_header_and_summaries(self) -> None:
        self.profile_keyboard_brightness_badge.setText(f"{self.keyboard_state.brightness}%")
        self.profile_logo_brightness_badge.setText(f"{self.lid_state.brightness}%")
        self.profile_keyboard_preview.set_state(self.keyboard_state)
        self.profile_lid_preview.set_state(self.lid_state)

        self.diag_editor_summary.setText(
            f"{self._t('label_keyboard')}: {self._effect_label(self.keyboard_state.effect)} / "
            f"{self._t('label_brightness')}={self.keyboard_state.brightness}% / "
            f"{self._t('summary_zones')}={','.join(color.upper() for color in self.keyboard_state.zones)}\n"
            f"{self._t('label_logo')}: {self._effect_label(self.lid_state.effect)} / "
            f"{self._t('label_brightness')}={self.lid_state.brightness}% / "
            f"{self._t('summary_logo_color')}={self.lid_state.color.upper()}"
        )

        self.diag_keyboard_effects_label.setText(
            ", ".join(self._effect_label(effect) for effect in SUPPORTED_EFFECTS_BY_DEVICE["keyboard"])
        )
        self.diag_lid_effects_label.setText(
            ", ".join(self._effect_label(effect) for effect in SUPPORTED_EFFECTS_BY_DEVICE["lid"])
        )
        self.diag_keyboard_effects_short.setText(self.diag_keyboard_effects_label.text())
        self.diag_lid_effects_short.setText(self.diag_lid_effects_label.text())

    def _sync_keyboard_static_editor(self) -> None:
        if self._syncing_ui:
            return
        static_state = self._keyboard_static_state_from_ui()
        if self.keyboard_state.effect == "static":
            self.keyboard_state = static_state
        else:
            self.keyboard_state.zones = list(static_state.zones)
            self.keyboard_state.brightness = static_state.brightness

        with QSignalBlocker(self.keyboard_effect_brightness):
            self.keyboard_effect_brightness.setValue(static_state.brightness)

        self.keyboard_static_preview.set_state(static_state)
        self.keyboard_static_brightness_value.setText(f"{static_state.brightness}%")
        self.keyboard_effect_brightness_value.setText(f"{static_state.brightness}%")
        self._set_active_preset_card(self._matching_preset_name(static_state))
        self._update_header_and_summaries()

    def _sync_keyboard_effect_editor(self) -> None:
        if self._syncing_ui:
            return
        effect_state = self._keyboard_effect_state_from_ui()
        self.keyboard_state = effect_state

        with QSignalBlocker(self.keyboard_static_brightness):
            self.keyboard_static_brightness.setValue(effect_state.brightness)

        self.keyboard_effect_brightness_value.setText(f"{effect_state.brightness}%")
        self.keyboard_speed_value.setText(str(effect_state.speed))

        animated = effect_state.effect != "static"
        self.keyboard_speed.setEnabled(animated)
        self.keyboard_direction.setEnabled(animated)
        if animated:
            self.keyboard_effect_hint.setText(self._t("hint_effect_animated"))
        else:
            self.keyboard_effect_hint.setText(self._t("hint_effect_static"))

        static_preview_state = KeyboardState(
            effect="static",
            brightness=effect_state.brightness,
            speed=effect_state.speed,
            direction=effect_state.direction,
            zones=list(effect_state.zones),
        )
        self.keyboard_static_preview.set_state(static_preview_state)
        self.keyboard_static_brightness_value.setText(f"{static_preview_state.brightness}%")
        self._set_active_preset_card(self._matching_preset_name(static_preview_state))
        self._update_header_and_summaries()

    def _sync_lid_preview(self) -> None:
        if self._syncing_ui:
            return
        self.lid_state = self._lid_state_from_ui()
        self.lid_preview.set_state(self.lid_state)
        self.lid_brightness_value.setText(f"{self.lid_state.brightness}%")
        self.lid_speed_value.setText(str(self.lid_state.speed))

        animated = self.lid_state.effect != "static"
        self.lid_speed.setEnabled(animated)
        self.lid_color.setEnabled(not animated)
        self._update_header_and_summaries()

    def _apply_keyboard_preset_ui(self, preset_name: str) -> None:
        if preset_name not in BUILTIN_PRESETS:
            return
        preset = BUILTIN_PRESETS[preset_name]
        self.keyboard_state = KeyboardState(
            effect="static",
            brightness=preset["brightness"],
            speed=self.keyboard_state.speed,
            direction=self.keyboard_state.direction,
            zones=list(preset["zones"]),
        )
        self._sync_ui_from_state()
        self._set_active_preset_card(preset_name)
        self._set_session_text(self._t("session_preset_loaded", name=self._preset_label(preset_name)))

    def _turn_off_keyboard(self) -> None:
        self.keyboard_state = KeyboardState(
            effect="static",
            brightness=0,
            speed=self.keyboard_state.speed,
            direction=self.keyboard_state.direction,
            zones=["000000", "000000", "000000", "000000"],
        )
        self._sync_ui_from_state()
        self._apply_keyboard_static()
        self._set_session_text(self._t("session_keyboard_off"))

    def _return_keyboard_to_static(self) -> None:
        self.keyboard_state.effect = "static"
        self._sync_ui_from_state()
        self._navigate_to(0)
        self._set_session_text(self._t("session_keyboard_static"))

    def _pkexec_available(self) -> bool:
        return PKEXEC_PATH.exists()

    def _prefer_pkexec(self) -> bool:
        return os.environ.get("LPSK_USE_PKEXEC") == "1" and self._pkexec_available()

    def _run_cli_with_pkexec(self, args: list[str]) -> None:
        if not self._pkexec_available():
            raise RuntimeError("pkexec is not available on this system")
        result = subprocess.run(
            [str(PKEXEC_PATH), "python3", str(CLI_SCRIPT_PATH), *args],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "pkexec command failed"
            raise RuntimeError(message)

    def _keyboard_cli_args(self) -> list[str]:
        if self.keyboard_state.effect == "static":
            return [
                "set-zones",
                *self.keyboard_state.zones,
                str(self.keyboard_state.brightness),
            ]
        return [
            "effect",
            self.keyboard_state.effect,
            "--brightness",
            str(self.keyboard_state.brightness),
            "--speed",
            str(self.keyboard_state.speed),
            "--direction",
            self.keyboard_state.direction,
        ]

    def _lid_cli_args(self) -> list[str]:
        args = [
            "effect",
            self.lid_state.effect,
            "--device",
            "lid",
            "--brightness",
            str(self.lid_state.brightness),
        ]
        if self.lid_state.effect == "static":
            args.extend(["--color", self.lid_state.color])
        else:
            args.extend(["--speed", str(self.lid_state.speed)])
        return args

    def _apply_keyboard(self) -> None:
        try:
            if self._prefer_pkexec():
                self._run_cli_with_pkexec(self._keyboard_cli_args())
            else:
                apply_keyboard_state(None, self.keyboard_state)
            self._set_session_text(
                self._t("session_keyboard_applied", effect=self._effect_label(self.keyboard_state.effect))
            )
        except PermissionError:
            try:
                self._run_cli_with_pkexec(self._keyboard_cli_args())
                self._set_session_text(
                    self._t("session_keyboard_applied", effect=self._effect_label(self.keyboard_state.effect))
                )
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(self, self._t("dialog_apply_keyboard_failed"), str(exc))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, self._t("dialog_apply_keyboard_failed"), str(exc))

    def _apply_keyboard_static(self) -> None:
        self._sync_keyboard_static_editor()
        self.keyboard_state.effect = "static"
        self._sync_ui_from_state()
        self._apply_keyboard()

    def _apply_keyboard_effect(self) -> None:
        self._sync_keyboard_effect_editor()
        self._apply_keyboard()

    def _apply_lid(self) -> None:
        self._sync_lid_preview()
        try:
            if self._prefer_pkexec():
                self._run_cli_with_pkexec(self._lid_cli_args())
            else:
                apply_lid_state(None, self.lid_state)
            self._set_session_text(
                self._t("session_logo_applied", effect=self._effect_label(self.lid_state.effect))
            )
        except PermissionError:
            try:
                self._run_cli_with_pkexec(self._lid_cli_args())
                self._set_session_text(
                    self._t("session_logo_applied", effect=self._effect_label(self.lid_state.effect))
                )
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(self, self._t("dialog_apply_logo_failed"), str(exc))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, self._t("dialog_apply_logo_failed"), str(exc))

    def _apply_all(self) -> None:
        self._sync_keyboard_static_editor()
        self._sync_keyboard_effect_editor()
        self._sync_lid_preview()
        try:
            if self._prefer_pkexec():
                self._run_cli_with_pkexec(self._keyboard_cli_args())
                self._run_cli_with_pkexec(self._lid_cli_args())
            else:
                apply_keyboard_state(None, self.keyboard_state)
                apply_lid_state(None, self.lid_state)
            self._set_session_text(self._t("session_all_applied"))
        except PermissionError:
            try:
                self._run_cli_with_pkexec(self._keyboard_cli_args())
                self._run_cli_with_pkexec(self._lid_cli_args())
                self._set_session_text(self._t("session_all_applied"))
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(self, self._t("dialog_apply_failed"), str(exc))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, self._t("dialog_apply_failed"), str(exc))

    def _refresh_profiles(self, initial: bool = False) -> None:
        self.profile_list.clear()
        for path in list_app_profiles():
            self.profile_list.addItem(QListWidgetItem(path.stem))
        self._update_header_and_summaries()
        if initial and not self.diag_session_label.text():
            self._set_session_text(self._t("session_ready"))

    def _save_profile(self) -> None:
        self._sync_keyboard_static_editor()
        self._sync_keyboard_effect_editor()
        self._sync_lid_preview()
        name, accepted = QInputDialog.getText(
            self,
            self._t("dialog_save_profile_title"),
            self._t("dialog_save_profile_prompt"),
        )
        if not accepted or not name.strip():
            return
        profile = AppProfile(
            name=name.strip(),
            keyboard=self.keyboard_state,
            lid=self.lid_state,
        )
        try:
            path = save_app_profile(profile)
            self._refresh_profiles()
            self._set_session_text(self._t("session_profile_saved", name=path.stem))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, self._t("dialog_save_profile_failed"), str(exc))

    def _selected_profile_name(self) -> str | None:
        item = self.profile_list.currentItem()
        return item.text() if item is not None else None

    def _load_selected_profile(self) -> None:
        name = self._selected_profile_name()
        if name is None:
            QMessageBox.information(
                self,
                self._t("dialog_no_profile_title"),
                self._t("dialog_no_profile_text"),
            )
            return
        try:
            profile = load_app_profile(name)
            self.keyboard_state = profile.keyboard
            self.lid_state = profile.lid
            self._sync_ui_from_state()
            self._set_session_text(self._t("session_profile_loaded", name=profile.name))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, self._t("dialog_load_profile_failed"), str(exc))

    def _delete_selected_profile(self) -> None:
        name = self._selected_profile_name()
        if name is None:
            QMessageBox.information(
                self,
                self._t("dialog_no_profile_title"),
                self._t("dialog_no_profile_text"),
            )
            return

        answer = QMessageBox.question(
            self,
            self._t("dialog_delete_profile_title"),
            self._t("dialog_delete_profile_text", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            path = delete_app_profile(name)
            self._refresh_profiles()
            self._set_session_text(self._t("session_profile_deleted", name=path.stem))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, self._t("dialog_delete_profile_failed"), str(exc))

    def _apply_selected_profile(self) -> None:
        name = self._selected_profile_name()
        if name is None:
            QMessageBox.information(
                self,
                self._t("dialog_no_profile_title"),
                self._t("dialog_no_profile_text"),
            )
            return
        try:
            profile = load_app_profile(name)
            self.keyboard_state = profile.keyboard
            self.lid_state = profile.lid
            self._sync_ui_from_state()
            self._apply_all()
            self._set_session_text(self._t("session_profile_applied", name=profile.name))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, self._t("dialog_apply_profile_failed"), str(exc))


def main() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_DISPLAY_NAME)
    if ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyleSheet(build_stylesheet())
    window = MainWindow()
    if ICON_PATH.exists():
        window.setWindowIcon(QIcon(str(ICON_PATH)))
    window.show()
    return app.exec()
