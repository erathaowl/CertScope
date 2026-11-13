"""Dual tree and syntax-highlighted JSON presentation of structured reports."""

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QMenu, QStackedWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from certscope.code_editor import CodeEditor


def format_value(value) -> str:
    """Copy strings as text and complex values as complete, formatted JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value, indent=2, ensure_ascii=False, default=str)


class CopyableTree(QTreeWidget):
    """Selectable JSON cells with keyboard and context-menu copy operations."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def copy_item(self, item: QTreeWidgetItem, action: str) -> str:
        key = item.text(0)
        value = item.data(0, Qt.ItemDataRole.UserRole)
        if action == "field":
            result = key
        elif action == "value":
            result = format_value(value)
        elif action == "element":
            result = json.dumps({key: value}, indent=2, ensure_ascii=False, default=str)
        else:
            raise ValueError(f"Unknown copy action: {action}")
        self.copy_text(result)
        return result

    def copy_text(self, text: str):
        QApplication.clipboard().setText(text)

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Copy) and self.currentItem():
            action = "field" if self.currentColumn() == 0 else "value"
            self.copy_item(self.currentItem(), action)
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if item is None:
            return
        column = max(0, self.columnAt(event.pos().x()))
        self.setCurrentItem(item, column)
        menu = QMenu(self)
        actions = {
            menu.addAction("Copy field"): "field",
            menu.addAction("Copy value"): "value",
            menu.addAction("Copy element"): "element",
        }
        selected = menu.exec(event.globalPos())
        if selected in actions:
            self.copy_item(item, actions[selected])


class JsonViewer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        self.tree = CopyableTree()
        self.tree.setHeaderLabels(["Field", "Value"])
        self.tree.setAlternatingRowColors(True)
        self.tree.header().setStretchLastSection(True)
        self.code = CodeEditor("json", read_only=True)
        self._dark = False
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.code)
        layout.addWidget(self.stack)

    def set_mode(self, mode: str):
        self.stack.setCurrentIndex(0 if mode == "Tree" else 1)

    def configure(self, family: str, size: int, dark: bool):
        self.code.configure(family, size, dark)
        self.tree.setFont(self.code.font())
        self._dark = dark
        self._style_fields()

    def _style_fields(self):
        color = QColor("#aab5c2" if self._dark else "#5c6877")

        def visit(item):
            item.setForeground(0, color)
            for index in range(item.childCount()):
                visit(item.child(index))

        for index in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(index))

    def set_data(self, data):
        self.code.setPlainText(json.dumps(data, indent=2, ensure_ascii=False, default=str))
        self.tree.clear()
        self._insert(None, "Result", data)
        self._style_fields()
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
        item.setData(0, Qt.ItemDataRole.UserRole, value)
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
