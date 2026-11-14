"""Persistent Ctrl+mouse-wheel font sizes for individual editors and views."""

import json

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractScrollArea

MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 32
PREFERENCE_KEY = "font_size_overrides"


class FontZoomController(QObject):
    """Keep each view's font size independent of the global default."""

    def __init__(self, storage, default_size, refresh, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.default_size = default_size
        self.refresh = refresh
        self._targets = {}
        self._widgets = {}
        try:
            values = json.loads(storage.get_preference(PREFERENCE_KEY, "{}"))
        except (TypeError, ValueError):
            values = {}
        if not isinstance(values, dict):
            values = {}
        self.overrides = {
            key: value for key, value in values.items()
            if isinstance(key, str) and type(value) is int
            and MIN_FONT_SIZE <= value <= MAX_FONT_SIZE
        }

    def register(self, key, widget):
        self._widgets[key] = widget
        self._targets[widget] = key
        widget.installEventFilter(self)
        if isinstance(widget, QAbstractScrollArea):
            viewport = widget.viewport()
            self._targets[viewport] = key
            viewport.installEventFilter(self)

    def size(self, key):
        return self.overrides.get(key, self.default_size())

    def reset(self):
        self.overrides.clear()
        self.storage.delete_preference(PREFERENCE_KEY)

    def eventFilter(self, watched, event):
        key = self._targets.get(watched)
        if key is None or event.type() != QEvent.Type.Wheel:
            return super().eventFilter(watched, event)
        if not event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return super().eventFilter(watched, event)

        widget = self._widgets[key]
        if not widget.hasFocus() and (
            not isinstance(widget, QAbstractScrollArea) or not widget.viewport().hasFocus()
        ):
            return super().eventFilter(watched, event)

        delta = event.angleDelta().y() or event.pixelDelta().y()
        if not delta:
            return super().eventFilter(watched, event)

        updated = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, self.size(key) + (1 if delta > 0 else -1)))
        if updated != self.size(key):
            if updated == self.default_size():
                self.overrides.pop(key, None)
            else:
                self.overrides[key] = updated
            if self.overrides:
                self.storage.set_preference(PREFERENCE_KEY, json.dumps(self.overrides, sort_keys=True))
            else:
                self.storage.delete_preference(PREFERENCE_KEY)
            self.refresh()
        event.accept()
        return True
