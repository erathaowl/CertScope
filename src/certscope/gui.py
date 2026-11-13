"""Qt desktop interface with independent certificate and trust-anchor inputs."""

import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from certscope.code_editor import CodeEditor
from certscope.json_viewer import JsonViewer
from certscope.preferences import SettingsDialog, apply_theme, is_dark, register_font
from certscope.parser import leaf_candidates, parse_bundle
from certscope.reporting import render
from certscope.storage import Storage
from certscope.verification import verify_bundle


def read_cert_file(path: str) -> str:
    raw = Path(path).read_bytes()
    if b"-----BEGIN" not in raw:
        return "".join(cert.pem for cert in parse_bundle(raw, allow_der=True))
    return raw.decode("utf-8-sig")


class PemEditor(CodeEditor):
    """Plain text editor that accepts dragged certificate files."""

    def __init__(self):
        super().__init__("pem")
        self.setAcceptDrops(True)
        self.setPlaceholderText("Paste one or more PEM CERTIFICATE blocks here, or drop a file")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls() and event.mimeData().urls()[0].isLocalFile():
            try:
                self.setPlainText(read_cert_file(event.mimeData().urls()[0].toLocalFile()))
                event.acceptProposedAction()
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, "Cannot open file", str(exc))
        else:
            super().dropEvent(event)


class AnalysisWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, pem: str, ca: str, storage: Storage, purpose: str,
                 hostname: str | None, fingerprint: str):
        super().__init__()
        self.pem, self.ca, self.storage = pem, ca, storage
        self.purpose, self.hostname, self.fingerprint = purpose, hostname, fingerprint

    def run(self):
        try:
            result = verify_bundle(self.pem, self.storage, self.ca, self.purpose,
                                   self.hostname, self.fingerprint)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class EntriesDialog(QDialog):
    def __init__(self, storage: Storage, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.selected = None
        self.setWindowTitle("Saved entries")
        self.resize(780, 430)
        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter by name")
        layout.addWidget(self.search)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Type", "Name", "Trusted", "Enabled"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        buttons = QHBoxLayout()
        for label, callback in (("Load", self.load), ("Rename", self.rename),
                                ("Delete", self.delete), ("Toggle trust", self.toggle_trust)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.search.textChanged.connect(self.refresh)
        self.table.itemDoubleClicked.connect(lambda _: self.load())
        self.refresh()

    def refresh(self):
        query = self.search.text().casefold()
        self.entries = [e for e in self.storage.list() if query in e.name.casefold()]
        self.table.setRowCount(len(self.entries))
        for row, item in enumerate(self.entries):
            for column, text in enumerate((item.kind, item.name, "Yes" if item.trusted else "No",
                                           "Yes" if item.enabled else "No")):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.table.resizeColumnsToContents()

    def current(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.entries):
            QMessageBox.information(self, "Select entry", "Select an entry first")
            return None
        return self.entries[row]

    def load(self):
        if entry := self.current():
            self.selected = entry
            self.accept()

    def rename(self):
        if entry := self.current():
            name, accepted = QInputDialog.getText(self, "Rename entry", "New name:", text=entry.name)
            if accepted and name.strip():
                try:
                    self.storage.rename(entry.kind, entry.name, name.strip())
                    self.refresh()
                except Exception as exc:
                    QMessageBox.warning(self, "Rename failed", str(exc))

    def delete(self):
        if entry := self.current():
            if QMessageBox.question(self, "Delete entry", f"Delete {entry.name} permanently?") == QMessageBox.StandardButton.Yes:
                try:
                    self.storage.delete(entry.kind, entry.name)
                    self.refresh()
                except Exception as exc:
                    QMessageBox.warning(self, "Delete failed", str(exc))

    def toggle_trust(self):
        entry = self.current()
        if not entry or entry.kind != "ca":
            QMessageBox.information(self, "CA trust", "Select a CA entry to change its trust")
            return
        state = not entry.trusted
        question = (f"Trust '{entry.name}' as a local CA for certificate validation?"
                    if state else f"Disable trust for '{entry.name}'?")
        if QMessageBox.question(self, "Confirm trust change", question) == QMessageBox.StandardButton.Yes:
            try:
                self.storage.trust(entry.name, state)
                self.refresh()
            except Exception as exc:
                QMessageBox.warning(self, "Trust update failed", str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.storage = Storage()
        self.report = None
        self.worker = None
        self.certificate_data = []
        self.font_family = self.storage.get_preference("font_family", register_font())
        try:
            self.font_size = max(8, min(32, int(self.storage.get_preference("font_size", "11"))))
        except ValueError:
            self.font_size = 11
        self.theme = self.storage.get_preference("theme", "system")
        if self.theme not in ("system", "light", "dark"):
            self.theme = "system"
        apply_theme(self.theme)
        self.setWindowTitle("CertScope - X.509 Certificate Inspector")
        self.resize(1280, 840)
        self._create_ui()

    def _create_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        toolbar = QHBoxLayout()
        stored = QPushButton("Saved entries")
        stored.clicked.connect(self.manage)
        toolbar.addWidget(stored)
        settings = QPushButton("Settings")
        settings.clicked.connect(self.open_settings)
        toolbar.addWidget(settings)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("Certificates and CA bundles stay on this computer"))
        layout.addLayout(toolbar)

        editors = QSplitter(Qt.Orientation.Horizontal)
        self.cert_edit, self.ca_edit = PemEditor(), PemEditor()
        for title, editor, kind in (("Certificate / chain PEM", self.cert_edit, "certificate"),
                                    ("Temporary custom CA PEM", self.ca_edit, "ca")):
            widget = QWidget()
            box = QVBoxLayout(widget)
            box.addWidget(QLabel(title))
            actions = QHBoxLayout()
            for label, action in (("Open file", lambda checked=False, e=editor: self.open_file(e)),
                                  ("Save named", lambda checked=False, e=editor, k=kind: self.save_entry(k, e)),
                                  ("Clear", editor.clear)):
                button = QPushButton(label)
                button.clicked.connect(action)
                actions.addWidget(button)
            box.addLayout(actions)
            box.addWidget(editor)
            editors.addWidget(widget)
        layout.addWidget(editors, 2)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Purpose"))
        self.purpose = QComboBox()
        self.purpose.addItems(["generic", "tls-server", "tls-client"])
        controls.addWidget(self.purpose)
        controls.addWidget(QLabel("Hostname / IP"))
        self.hostname = QLineEdit()
        self.hostname.setPlaceholderText("Required for TLS server")
        controls.addWidget(self.hostname, 1)
        self.analyze_btn = QPushButton("Analyze and verify")
        self.analyze_btn.clicked.connect(self.analyze)
        controls.addWidget(self.analyze_btn)
        layout.addLayout(controls)

        results = QSplitter(Qt.Orientation.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Certificates / verified path"])
        self.tree.itemSelectionChanged.connect(self.show_details)
        results.addWidget(self.tree)
        self.tabs = QTabWidget()
        self.details = JsonViewer()
        self.path_details = JsonViewer()
        self.diagnostics = JsonViewer()
        self.raw = CodeEditor("pem", read_only=True)
        for name, edit in (("Details", self.details), ("Verified path", self.path_details),
                           ("Diagnostics", self.diagnostics), ("Raw PEM", self.raw)):
            self.tabs.addTab(edit, name)
        result_panel = QWidget()
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Result view"))
        self.view_mode = QComboBox()
        self.view_mode.addItems(["Tree", "JSON"])
        self.view_mode.currentTextChanged.connect(self.set_result_mode)
        mode_row.addWidget(self.view_mode)
        mode_row.addStretch()
        result_layout.addLayout(mode_row)
        result_layout.addWidget(self.tabs)
        results.addWidget(result_panel)
        results.setStretchFactor(1, 3)
        layout.addWidget(results, 3)

        bottom = QHBoxLayout()
        self.status = QLabel("Paste a certificate or open a file to begin")
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bottom.addWidget(self.status, 1)
        for label, callback in (("Copy report", self.copy_report), ("Export report", self.export_report)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            bottom.addWidget(button)
        layout.addLayout(bottom)
        self.setCentralWidget(root)
        self.apply_appearance()
        QApplication.styleHints().colorSchemeChanged.connect(self.on_system_theme_changed)

    def open_settings(self):
        dialog = SettingsDialog(self.font_family, self.font_size, self.theme, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            for key, value in values.items():
                self.storage.set_preference(key, value)
            self.font_family = values["font_family"]
            self.font_size = int(values["font_size"])
            self.theme = values["theme"]
            self.apply_appearance()

    def on_system_theme_changed(self, scheme):
        if self.theme == "system":
            self.apply_appearance()

    def apply_appearance(self):
        apply_theme(self.theme)
        dark = is_dark(self.theme)
        for editor in (self.cert_edit, self.ca_edit, self.raw):
            editor.configure(self.font_family, self.font_size, dark)
        for viewer in (self.details, self.path_details, self.diagnostics):
            viewer.configure(self.font_family, self.font_size, dark)
        self.tree.setFont(self.cert_edit.font())

    def set_result_mode(self, mode):
        for viewer in (self.details, self.path_details, self.diagnostics):
            viewer.set_mode(mode)

    def open_file(self, editor):
        path, _ = QFileDialog.getOpenFileName(self, "Open certificate", "",
                                              "Certificates (*.pem *.crt *.cer *.chain *.der);;All files (*)")
        if path:
            try:
                editor.setPlainText(read_cert_file(path))
            except Exception as exc:
                QMessageBox.warning(self, "Open failed", str(exc))

    def save_entry(self, kind, editor):
        name, accepted = QInputDialog.getText(self, "Save named entry", "Entry name:")
        if not accepted or not name.strip():
            return
        trusted = False
        if kind == "ca":
            trusted = QMessageBox.question(self, "Trust CA?",
                                           "Explicitly trust these CA certificates in local verification?"
                                           ) == QMessageBox.StandardButton.Yes
        try:
            self.storage.save(kind, name.strip(), editor.toPlainText(), trusted=trusted)
            self.status.setText(f"Saved {kind}: {name.strip()}")
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def manage(self):
        dialog = EntriesDialog(self.storage, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected:
            entry = dialog.selected
            if entry.kind == "ca":
                self.ca_edit.setPlainText(entry.pem_bundle)
            else:
                self.cert_edit.setPlainText(entry.pem_bundle)

    def analyze(self):
        pem = self.cert_edit.toPlainText()
        purpose = self.purpose.currentText()
        hostname = self.hostname.text().strip() or None
        if purpose == "tls-server" and not hostname:
            QMessageBox.warning(self, "Hostname required", "TLS server verification requires a hostname or IP")
            return
        try:
            candidates = leaf_candidates(parse_bundle(pem))
            fingerprint = candidates[0].fingerprint
            if len(candidates) > 1:
                choices = [f"{c.value.subject.rfc4514_string()} [{c.fingerprint[:16]}]" for c in candidates]
                selection, ok = QInputDialog.getItem(self, "Select leaf", "Certificate to verify:",
                                                     choices, 0, False)
                if not ok:
                    return
                fingerprint = candidates[choices.index(selection)].fingerprint
        except Exception as exc:
            self.status.setText(f"Invalid certificate input: {exc}")
            self.diagnostics.set_data({"error": str(exc)})
            return
        self.status.setText("Analyzing certificates and verifying trust...")
        self.analyze_btn.setEnabled(False)
        self.worker = AnalysisWorker(pem, self.ca_edit.toPlainText(), self.storage,
                                     purpose, hostname, fingerprint)
        self.worker.completed.connect(self.show_report)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(lambda: self.analyze_btn.setEnabled(True))
        self.worker.start()

    def show_error(self, message):
        self.status.setText(f"Analysis failed: {message}")
        self.diagnostics.set_data({"error": message})
        self.tabs.setCurrentWidget(self.diagnostics)

    def show_report(self, report):
        self.report = report
        self.certificate_data = report["certificates"]
        self.tree.clear()
        provided = QTreeWidgetItem(["Provided certificates"])
        self.tree.addTopLevelItem(provided)
        for index, cert in enumerate(self.certificate_data):
            entry = QTreeWidgetItem([cert["subject"]])
            entry.setData(0, Qt.ItemDataRole.UserRole, ("provided", index))
            provided.addChild(entry)
        path = QTreeWidgetItem(["Verified chain"])
        self.tree.addTopLevelItem(path)
        for index, cert in enumerate(report["verified_chain"]):
            label = cert["subject"] + (" [trust anchor]" if index == len(report["verified_chain"]) - 1 else "")
            entry = QTreeWidgetItem([label])
            entry.setData(0, Qt.ItemDataRole.UserRole, ("verified", index))
            path.addChild(entry)
        self.tree.expandAll()
        self.path_details.set_data({"source": report["trust_source"],
            "trust_anchor": report["trust_anchor"],
            "verified_chain": report["verified_chain"]})
        self.diagnostics.set_data(report)
        self.status.setText(f"Status: {report['status'].upper()} | Chain: {report['chain_status']} | "
                            f"Trust source: {report['trust_source'] or 'none'} | "
                            "Revocation: not checked")
        self.tabs.setCurrentWidget(self.diagnostics)
        if self.certificate_data:
            self.tree.setCurrentItem(provided.child(0))

    def show_details(self):
        selected = self.tree.selectedItems()
        if not selected or not self.report:
            return
        data = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, index = data
        cert = self.certificate_data[index] if kind == "provided" else self.report["verified_chain"][index]
        self.details.set_data({k: v for k, v in cert.items() if k != "pem"})
        self.raw.setPlainText(cert["pem"])
        self.tabs.setCurrentWidget(self.details)

    def copy_report(self):
        if self.report:
            QApplication.clipboard().setText(render(self.report))

    def export_report(self):
        if not self.report:
            return
        path, selected = QFileDialog.getSaveFileName(self, "Export verification report", "report.json",
                                                      "JSON (*.json);;Text (*.txt)")
        if path:
            try:
                fmt = "json" if path.lower().endswith(".json") or "JSON" in selected else "text"
                Path(path).write_text(render(self.report, fmt) + "\n", encoding="utf-8")
            except OSError as exc:
                QMessageBox.warning(self, "Export failed", str(exc))


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    register_font()
    window = MainWindow()
    icon = Path(__file__).resolve().parents[2] / "assets" / "certscope.png"
    if not icon.is_file() and hasattr(sys, "_MEIPASS"):
        icon = Path(sys._MEIPASS) / "assets" / "certscope.png"
    if icon.is_file():
        window.setWindowIcon(QIcon(str(icon)))
    window.show()
    return app.exec()
