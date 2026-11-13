"""Dual tree and syntax-highlighted JSON presentation of structured reports."""

import json

from PySide6.QtWidgets import QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from certscope.code_editor import CodeEditor


class JsonViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Field", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setStretchLastSection(True)
        self.code = CodeEditor("json", read_only=True)
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.code)
        layout.addWidget(self.stack)

    def set_mode(self, mode: str):
        self.stack.setCurrentIndex(0 if mode == "Tree" else 1)

    def configure(self, family: str, size: int, dark: bool):
        self.code.configure(family, size, dark)
        self.tree.setFont(self.code.font())

    def set_data(self, data):
        self.code.setPlainText(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        self.tree.clear()
        self._insert(None, "Result", data)
        self.tree.expandToDepth(1)
        self.tree.resizeColumnToContents(0)

    def _insert(self, parent, key: str, value):
        if isinstance(value, dict):
            label = f"{{{len(value)} fields}}"
        elif isinstance(value, list):
            label = f"[{len(value)} items]"
        else:
            label = json.dumps(value, ensure_ascii=False, default=str)
        item = QTreeWidgetItem([str(key), label if len(label) <= 160 else label[:157] + "..."])
        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                self._insert(item, str(child_key), child_value)
        elif isinstance(value, list):
            for index, child_value in enumerate(value):
                self._insert(item, f"[{index}]", child_value)
        elif len(label) > 160:
            item.setToolTip(1, label)
