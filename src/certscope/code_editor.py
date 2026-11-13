"""Shared monospace code editor for PEM input and structured output."""

import re

from PySide6.QtGui import QColor, QFont, QFontMetricsF, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit


JSON_COLORS = {
    False: {"string": "#197b43", "key": "#1e5ea8", "literal": "#8836a9",
            "number": "#ac581a"},
    True: {"string": "#a8d6a3", "key": "#86c5ff", "literal": "#dbadff",
           "number": "#ffbf7c"},
}


class SyntaxHighlighter(QSyntaxHighlighter):
    """Highlight PEM delimiters or JSON tokens without modifying document text."""

    STRINGS = re.compile(r'"(?:\\.|[^"\\])*"')
    KEYS = re.compile(r'"(?:\\.|[^"\\])*"(?=\s*:)')
    LITERALS = re.compile(r'\b(?:true|false|null)\b')
    NUMBERS = re.compile(r'(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w.])')

    def __init__(self, document, language: str):
        super().__init__(document)
        self.language = language
        self.dark = False

    def set_dark(self, dark: bool):
        self.dark = dark
        self.rehighlight()

    def _format(self, color: str, bold: bool = False) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        return fmt

    def highlightBlock(self, text: str):
        if self.language == "pem":
            if text.startswith("-----BEGIN ") or text.startswith("-----END "):
                fmt = self._format("#7cb5ff" if self.dark else "#225eae", bold=True)
                self.setFormat(0, len(text), fmt)
            elif text and re.fullmatch(r"[A-Za-z0-9+/=]+", text):
                fmt = self._format("#b5c8df" if self.dark else "#53677e")
                self.setFormat(0, len(text), fmt)
            return

        if self.language != "json":
            return

        colors = JSON_COLORS[self.dark]

        occupied = []
        for match in self.STRINGS.finditer(text):
            occupied.append((match.start(), match.end()))
            self.setFormat(match.start(), match.end() - match.start(),
                           self._format(colors["string"]))

        for match in self.KEYS.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(),
                           self._format(colors["key"], bold=True))

        for pattern, color in ((self.LITERALS, colors["literal"]), (self.NUMBERS, colors["number"])):
            for match in pattern.finditer(text):
                if any(start <= match.start() < end for start, end in occupied):
                    continue
                self.setFormat(match.start(), match.end() - match.start(),
                               self._format(color))


class CodeEditor(QPlainTextEdit):
    """One editor component for editable PEM and read-only JSON/PEM."""

    def __init__(self, language: str = "pem", *, read_only: bool = False, parent=None):
        super().__init__(parent)
        self.setReadOnly(read_only)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabChangesFocus(False)
        self.highlighter = SyntaxHighlighter(self.document(), language)

    def configure(self, family: str, size: int, dark: bool):
        font = QFont(family, size)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.setFont(font)
        self.setTabStopDistance(QFontMetricsF(font).horizontalAdvance(" ") * 4)
        self.highlighter.set_dark(dark)
