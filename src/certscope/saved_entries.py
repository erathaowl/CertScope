"""Saved certificate database panel and editable raw PEM viewer."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHeaderView,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from certscope.code_editor import CodeEditor
from certscope.font_zoom import FontZoomController
from certscope.preferences import is_dark


class RawEntryDialog(QDialog):
    """Edit a stored PEM bundle, saving valid changes when the dialog closes."""

    def __init__(self, entry, storage, settings, family, size, theme, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.storage = storage
        self.theme = theme
        self.font_family = family
        self.default_size = size
        self.setWindowTitle(f"Saved PEM: {entry.name}")
        self.resize(760, 560)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Changes are saved automatically when this window closes."))
        self.editor = CodeEditor("pem")
        self.editor.setPlainText(entry.pem_bundle)
        layout.addWidget(self.editor)
        self.font_zoom = FontZoomController(
            settings, lambda: self.default_size, self.apply_font, self
        )
        self.font_zoom.register("saved_entry_raw", self.editor)
        self.apply_font()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_font(self):
        self.editor.configure(
            self.font_family, self.font_zoom.size("saved_entry_raw"), is_dark(self.theme)
        )

    def reject(self):
        updated = self.editor.toPlainText()
        if updated != self.entry.pem_bundle:
            try:
                self.storage.save(
                    self.entry.kind, self.entry.name, updated,
                    trusted=self.entry.trusted, enabled=self.entry.enabled, replace=True,
                )
            except Exception as exc:
                QMessageBox.warning(self, "Cannot save certificate", str(exc))
                return
        super().accept()


class SavedEntriesPanel(QWidget):
    """Full-height sidebar for persisted certificates and CA entries."""

    load_requested = Signal(str, str)
    new_database_requested = Signal()
    open_database_requested = Signal()

    def __init__(self, storage, settings, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.settings = settings
        self.entries = []
        self.font_family = ""
        self.font_size = 11
        self.theme = "system"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.addWidget(QLabel("Saved certificates / CAs"))

        self.database_label = QLabel()
        layout.addWidget(self.database_label)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter saved entries")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Name", "Trusted"])
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(1, 78)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.itemDoubleClicked.connect(self.edit_raw)
        layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.new_database_button = QPushButton("New DB")
        self.open_database_button = QPushButton("Open DB")
        self.new_database_button.clicked.connect(self.new_database_requested.emit)
        self.open_database_button.clicked.connect(self.open_database_requested.emit)
        buttons.addWidget(self.new_database_button)
        buttons.addWidget(self.open_database_button)
        layout.addLayout(buttons)

        self.refresh()

    def set_database(self, storage):
        self.storage = storage
        self.refresh()

    def configure(self, family, size, theme):
        self.font_family = family
        self.font_size = size
        self.theme = theme

    def refresh(self):
        self.database_label.setText(self.storage.path.name)
        self.database_label.setToolTip(str(self.storage.path.resolve()))
        selected = self.selected_entry()
        identity = (selected.kind, selected.name) if selected else None
        needle = self.search.text().casefold()
        self.entries = [
            entry for entry in self.storage.list()
            if needle in entry.name.casefold()
        ]
        self.table.setRowCount(len(self.entries))
        dark = is_dark(self.theme)
        for row, entry in enumerate(self.entries):
            name = QTableWidgetItem(entry.name)
            name.setToolTip(f"{entry.kind.capitalize()}: {entry.name}")
            self.table.setItem(row, 0, name)
            trust = QTableWidgetItem("✓" if entry.trusted else "✗")
            trust.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            trust.setForeground(QColor(
                "#56c38b" if dark else "#16834c"
            ) if entry.trusted else QColor("#ff7070" if dark else "#c92b2b"))
            trust.setToolTip("Trusted CA" if entry.trusted else "Not trusted")
            self.table.setItem(row, 1, trust)
            if identity == (entry.kind, entry.name):
                self.table.selectRow(row)

    def selected_entry(self):
        row = self.table.currentRow()
        return self.entries[row] if 0 <= row < len(self.entries) else None

    def edit_raw(self, *_):
        entry = self.selected_entry()
        if entry is None:
            return
        dialog = RawEntryDialog(
            entry, self.storage, self.settings,
            self.font_family, self.font_size, self.theme, self,
        )
        dialog.exec()
        self.refresh()

    def show_context_menu(self, position):
        row = self.table.rowAt(position.y())
        if row < 0:
            return
        self.table.selectRow(row)
        entry = self.entries[row]
        menu = QMenu(self)
        rename = menu.addAction("Rename")
        delete = menu.addAction("Delete")
        menu.addSeparator()
        load_cert = menu.addAction("Load as certificate")
        load_ca = menu.addAction("Load as CA")
        trust = None
        if entry.kind == "ca":
            menu.addSeparator()
            trust = menu.addAction("Untrust" if entry.trusted else "Trust")
        selected = menu.exec(self.table.viewport().mapToGlobal(position))
        if selected == rename:
            self.rename_entry(entry)
        elif selected == delete:
            self.delete_entry(entry)
        elif selected == load_cert:
            self.load_requested.emit("certificate", entry.pem_bundle)
        elif selected == load_ca:
            self.load_requested.emit("ca", entry.pem_bundle)
        elif selected == trust:
            self.toggle_trust(entry)

    def rename_entry(self, entry):
        name, accepted = QInputDialog.getText(
            self, "Rename saved entry", "New name:", text=entry.name
        )
        if accepted and name.strip() and name.strip() != entry.name:
            try:
                self.storage.rename(entry.kind, entry.name, name.strip())
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Rename failed", str(exc))

    def delete_entry(self, entry):
        if QMessageBox.question(
            self, "Delete entry", f"Delete '{entry.name}' permanently?"
        ) != QMessageBox.StandardButton.Yes:
            return
        try:
            self.storage.delete(entry.kind, entry.name)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Delete failed", str(exc))

    def toggle_trust(self, entry):
        if entry.kind != "ca":
            return
        try:
            self.storage.trust(entry.name, not entry.trusted)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "Trust update failed", str(exc))
