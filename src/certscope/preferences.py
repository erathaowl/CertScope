"""Per-user appearance preferences and the bundled editor font."""

from importlib.resources import as_file, files

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFontComboBox,
    QFormLayout, QSpinBox,
)

FONT_FILE = "JetBrainsMonoNerdFontMono-Regular.ttf"
DEFAULT_FONT = "JetBrainsMono Nerd Font Mono"
DEFAULT_SIZE = 11
THEMES = ("system", "light", "dark")


def register_font() -> str:
    """Load the vendored font once; use a system monospace font as fallback."""
    if not hasattr(register_font, "_family"):
        resource = files("certscope").joinpath("assets", FONT_FILE)
        font_id = -1
        if resource.is_file():
            with as_file(resource) as path:
                font_id = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        register_font._family = (
            families[0] if families else QFontDatabase.systemFont(
                QFontDatabase.SystemFont.FixedFont).family()
        )
    return register_font._family


def is_dark(theme: str) -> bool:
    if theme == "system":
        return QApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return theme == "dark"


def apply_theme(theme: str):
    """Apply an application palette while respecting system-auto appearance."""
    app = QApplication.instance()
    if app is None:
        return
    dark = is_dark(theme)
    # Explicit control colors keep text legible with the native Qt style.
    palette = QPalette()
    colors = {
        QPalette.ColorRole.Window: "#25272b" if dark else "#f4f5f7",
        QPalette.ColorRole.WindowText: "#e7eaf0" if dark else "#20252a",
        QPalette.ColorRole.Base: "#1a1c20" if dark else "#ffffff",
        QPalette.ColorRole.AlternateBase: "#30333a" if dark else "#f0f3f7",
        QPalette.ColorRole.ToolTipBase: "#353940" if dark else "#ffffee",
        QPalette.ColorRole.ToolTipText: "#f3f3f3" if dark else "#20252a",
        QPalette.ColorRole.Text: "#e7eaf0" if dark else "#20252a",
        QPalette.ColorRole.Button: "#343840" if dark else "#eef0f3",
        QPalette.ColorRole.ButtonText: "#e7eaf0" if dark else "#20252a",
        QPalette.ColorRole.Highlight: "#246bad" if dark else "#3788d5",
        QPalette.ColorRole.HighlightedText: "#ffffff",
        QPalette.ColorRole.Link: "#86c5ff" if dark else "#1858b5",
        QPalette.ColorRole.PlaceholderText: "#9299a5" if dark else "#747e89",
    }
    for role, color in colors.items():
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,
                     QColor("#858a94" if dark else "#9ba0a8"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText,
                     QColor("#858a94" if dark else "#9ba0a8"))
    app.setPalette(palette)
    foreground = "#e7eaf0" if dark else "#20252a"
    button = "#343840" if dark else "#e7ebf0"
    hover = "#424854" if dark else "#d7e0eb"
    border = "#505661" if dark else "#aeb8c4"
    base = "#1a1c20" if dark else "#ffffff"
    alternate = "#202226" if dark else "#f5f7fa"
    highlight = "#294e70" if dark else "#d5e8fb"
    selected_text = "#ffffff" if dark else "#172b42"
    app.setStyleSheet(f"""
        QPushButton, QToolButton {{
            color: {foreground};
            background-color: {button};
            border: 1px solid {border};
            border-radius: 5px;
            padding: 5px 10px;
        }}
        QPushButton:hover, QToolButton:hover {{
            background-color: {hover};
        }}
        QPushButton:pressed, QToolButton:pressed {{
            background-color: {highlight};
        }}
        QPushButton:disabled {{
            color: {"#858a94" if dark else "#87929f"};
            background-color: {"#2b2f35" if dark else "#f0f1f3"};
        }}
        QComboBox, QSpinBox, QFontComboBox, QLineEdit {{
            color: {foreground};
            background-color: {base};
            border: 1px solid {border};
            border-radius: 3px;
            padding: 4px;
        }}
        QComboBox QAbstractItemView {{
            color: {foreground};
            background-color: {base};
            selection-background-color: {highlight};
            selection-color: {selected_text};
        }}
        QTreeWidget, QTableWidget {{
            color: {foreground};
            background-color: {base};
            alternate-background-color: {alternate};
            selection-background-color: {highlight};
            selection-color: {selected_text};
            border: 1px solid {border};
        }}
        QTreeWidget::item:selected, QTableWidget::item:selected {{
            background-color: {highlight};
            color: {selected_text};
        }}
        QHeaderView::section {{
            color: {foreground};
            background-color: {button};
            border: 1px solid {border};
            padding: 4px;
        }}
        QMenu {{
            color: {foreground};
            background-color: {base};
            border: 1px solid {border};
        }}
        QMenu::item:selected {{
            color: {selected_text};
            background-color: {highlight};
        }}
        QTabBar::tab {{
            color: {foreground};
            background-color: {button};
            border: 1px solid {border};
            padding: 5px 12px;
        }}
        QTabBar::tab:selected {{
            background-color: {base};
        }}
    """)


class SettingsDialog(QDialog):
    """Edit font family, point size and theme before saving to SQLite."""

    def __init__(self, family: str, size: int, theme: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(390)
        layout = QFormLayout(self)

        self.font = QFontComboBox()
        self.font.setFontFilters(QFontComboBox.FontFilter.MonospacedFonts)
        self.font.setCurrentFont(QFont(family))
        layout.addRow("Editor font", self.font)

        self.size = QSpinBox()
        self.size.setRange(8, 32)
        self.size.setValue(size)
        layout.addRow("Font size (pt)", self.size)

        self.theme = QComboBox()
        for value, label in (("system", "System (auto)"), ("light", "Light"), ("dark", "Dark")):
            self.theme.addItem(label, value)
        self.theme.setCurrentIndex(max(0, self.theme.findData(theme)))
        layout.addRow("Appearance", self.theme)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, str]:
        return {
            "font_family": self.font.currentFont().family(),
            "font_size": str(self.size.value()),
            "theme": self.theme.currentData(),
        }
