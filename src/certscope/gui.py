"""Qt desktop interface with independent certificate and trust-anchor inputs."""

import sqlite3
import sys
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal, QTimer, QSize
from PySide6.QtGui import QBrush, QColor, QIcon, QFont
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget, QDialogButtonBox,
)

from certscope import __version__
from certscope.app_info import APP_LICENSE, APP_NAME, APP_URL
from certscope.app_settings import AppSettings
from certscope.code_editor import CodeEditor
from certscope.font_zoom import FontZoomController
from certscope.json_viewer import JsonViewer
from certscope.input_source import classify_input
from certscope.remote import fetch_certificate, parse_tls_target
from certscope.preferences import SettingsDialog, apply_theme, is_dark, register_font
from certscope.parser import leaf_candidates, parse_bundle
from certscope.reporting import render
from certscope.saved_entries import SavedEntriesPanel
from certscope.storage import Storage, default_database_path
from certscope.verification import verify_bundle


def application_icon() -> QIcon:
    """Load the bundled application icon in the source tree and frozen EXEs."""
    from importlib.resources import as_file, files

    resource = files("certscope").joinpath("assets", "certscope.png")
    if resource.is_file():
        with as_file(resource) as path:
            return QIcon(str(path))
    return QIcon()


class AboutDialog(QDialog):
    """Display the application identity and repository link."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setFixedWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(12)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setPixmap(application_icon().pixmap(QSize(96, 96)))
        layout.addWidget(image)

        self.identity = QLabel(f"{APP_NAME} - {__version__} ({APP_LICENSE})")
        self.identity.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_font = QFont(self.identity.font())
        title_font.setBold(True)
        self.identity.setFont(title_font)
        layout.addWidget(self.identity)

        self.repository = QLabel(f'<a href="{APP_URL}">{APP_URL}</a>')
        self.repository.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.repository.setOpenExternalLinks(True)
        layout.addWidget(self.repository)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


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
                 hostname: str | None, fingerprint: str, lint_profile: str):
        super().__init__()
        self.pem, self.ca, self.storage = pem, ca, storage
        self.purpose, self.hostname, self.fingerprint = purpose, hostname, fingerprint
        self.lint_profile = lint_profile

    def run(self):
        try:
            from certscope.linting import lint_bundle

            result = verify_bundle(self.pem, self.storage, self.ca, self.purpose,
                                   self.hostname, self.fingerprint)
            result["lint"] = lint_bundle(parse_bundle(self.pem), self.lint_profile)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class FetchWorker(QThread):
    """Perform the untrusted network handshake without blocking the UI."""

    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            self.completed.emit(fetch_certificate(self.url))
        except Exception as exc:
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = AppSettings()
        self.settings.migrate_legacy(default_database_path())
        self._missing_database = None
        saved_db = self.settings.get_preference("last_database")
        if saved_db and not Path(saved_db).is_file():
            self._missing_database = saved_db
            saved_db = None
        try:
            self.storage = Storage(saved_db) if saved_db else Storage()
        except (OSError, sqlite3.DatabaseError, RuntimeError) as exc:
            self._missing_database = f"{saved_db}: {exc}"
            self.storage = Storage()
        current_db = str(self.storage.path.resolve())
        if self.settings.get_preference("last_database") != current_db:
            self.settings.set_preference("last_database", current_db)
        self.report = None
        self.worker = None
        self.fetch_worker = None
        self.certificate_data = []
        self.font_family = self.settings.get_preference("font_family", register_font())
        try:
            self.font_size = max(8, min(32, int(self.settings.get_preference("font_size", "11"))))
        except ValueError:
            self.font_size = 11
        self.font_zoom = FontZoomController(
            self.settings, lambda: self.font_size, self.apply_appearance, self
        )
        self.theme = self.settings.get_preference("theme", "system")
        if self.theme not in ("system", "light", "dark"):
            self.theme = "system"
        apply_theme(self.theme)
        self.setWindowTitle("CertScope - X.509 Certificate Inspector")
        self.setWindowIcon(application_icon())
        self.resize(1280, 840)
        self._create_ui()
        if self._missing_database:
            QTimer.singleShot(0, self.notify_missing_database)

    def notify_missing_database(self):
        QMessageBox.warning(
            self, "Saved database unavailable",
            f"The previously selected database is unavailable:\n{self._missing_database}\n\n"
            f"Using the default database:\n{self.storage.path}",
        )

    def _create_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        toolbar = QHBoxLayout()
        settings = QPushButton("Settings")
        settings.clicked.connect(self.open_settings)
        toolbar.addWidget(settings)
        about = QPushButton("About")
        about.clicked.connect(self.open_about)
        toolbar.addWidget(about)
        toolbar.addStretch()
        toolbar.addWidget(QLabel("Certificates and CA bundles stay on this computer"))
        layout.addLayout(toolbar)

        remote = QHBoxLayout()
        remote.addWidget(QLabel("TLS URL"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com:443 or host:port")
        self.url_input.returnPressed.connect(self.start_remote_fetch)
        remote.addWidget(self.url_input, 1)
        self.fetch_button = QPushButton("Fetch and analyze")
        self.fetch_button.clicked.connect(self.start_remote_fetch)
        remote.addWidget(self.fetch_button)
        layout.addLayout(remote)

        editors = QSplitter(Qt.Orientation.Horizontal)
        self.cert_edit, self.ca_edit = PemEditor(), PemEditor()
        for title, editor, kind in (("Certificate / chain PEM", self.cert_edit, "certificate"),
                                    ("Temporary custom CA PEM", self.ca_edit, "ca")):
            widget = QWidget()
            box = QVBoxLayout(widget)
            box.addWidget(QLabel(title))
            actions = QHBoxLayout()
            for label, action in (("Open file", lambda checked=False, e=editor: self.open_file(e)),
                                  ("Save as", lambda checked=False, e=editor, k=kind: self.save_as(k, e)),
                                  ("Save named", lambda checked=False, e=editor, k=kind: self.save_entry(k, e)),
                                  ("Clear", editor.clear)):
                button = QPushButton(label)
                button.clicked.connect(action)
                actions.addWidget(button)
            box.addLayout(actions)
            box.addWidget(editor)
            editors.addWidget(widget)
        self.vertical_splitter = QSplitter(Qt.Orientation.Vertical)
        self.vertical_splitter.setChildrenCollapsible(False)
        self.vertical_splitter.addWidget(editors)
        lower = QWidget()
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 0, 0, 0)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Purpose"))
        self.purpose = QComboBox()
        self.purpose.addItems(["generic", "tls-server", "tls-client"])
        controls.addWidget(self.purpose)
        controls.addWidget(QLabel("Hostname / IP"))
        self.hostname = QLineEdit()
        self.hostname.setPlaceholderText("Required for TLS server")
        controls.addWidget(self.hostname, 1)
        controls.addWidget(QLabel("Lint profile"))
        self.lint_profile = QComboBox()
        self.lint_profile.addItem("RFC 5280", "rfc5280")
        self.lint_profile.addItem("CA/B Forum TLS", "cabf-tls")
        self.lint_profile.setToolTip(
            "CA/B Forum TLS requirements apply to publicly trusted TLS certificates"
        )
        saved_lint_profile = self.settings.get_preference("lint_profile", "rfc5280")
        self.lint_profile.setCurrentIndex(1 if saved_lint_profile == "cabf-tls" else 0)
        self.lint_profile.currentIndexChanged.connect(
            lambda _: self.settings.set_preference(
                "lint_profile", self.lint_profile.currentData()
            )
        )
        controls.addWidget(self.lint_profile)
        self.analyze_btn = QPushButton("Analyze and verify")
        self.analyze_btn.clicked.connect(self.analyze)
        controls.addWidget(self.analyze_btn)
        lower_layout.addLayout(controls)

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

        self.lint_panel = QWidget()
        lint_layout = QVBoxLayout(self.lint_panel)
        lint_header = QHBoxLayout()
        self.lint_summary = QLabel("Linting has not run")
        lint_header.addWidget(self.lint_summary, 1)
        self.lint_certificate = QComboBox()
        self.lint_certificate.addItem("All certificates")
        self.lint_certificate.currentIndexChanged.connect(self.show_lint_details)
        lint_header.addWidget(self.lint_certificate)
        lint_layout.addLayout(lint_header)
        self.lint_view = JsonViewer()
        lint_layout.addWidget(self.lint_view)
        self.tabs.addTab(self.lint_panel, "Lint")
        result_panel = QWidget()
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Result view"))
        self.view_mode = QComboBox()
        self.view_mode.addItems(["Tree", "JSON"])
        saved_mode = self.settings.get_preference("result_view", "Tree")
        self.view_mode.setCurrentText(saved_mode if saved_mode in ("Tree", "JSON") else "Tree")
        self.view_mode.currentTextChanged.connect(self.set_result_mode)
        mode_row.addWidget(self.view_mode)
        mode_row.addStretch()
        result_layout.addLayout(mode_row)
        result_layout.addWidget(self.tabs)
        results.addWidget(result_panel)
        results.setStretchFactor(1, 3)
        lower_layout.addWidget(results, 1)

        bottom = QHBoxLayout()
        self.trust_indicator = QLabel("●")
        self.trust_indicator.setToolTip("Verification not completed")
        self.trust_indicator.hide()
        bottom.addWidget(self.trust_indicator)
        self.status = QLabel("Paste a certificate or open a file to begin")
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        bottom.addWidget(self.status, 1)
        for label, callback in (("Copy report", self.copy_report), ("Export report", self.export_report)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            bottom.addWidget(button)
        lower_layout.addLayout(bottom)
        self.vertical_splitter.addWidget(lower)
        self.vertical_splitter.setStretchFactor(0, 1)
        self.vertical_splitter.setStretchFactor(1, 2)
        self.vertical_splitter.setSizes([300, 450])
        layout.addWidget(self.vertical_splitter, 1)
        self.saved_panel = SavedEntriesPanel(self.storage, self.settings, self)
        self.saved_panel.new_database_requested.connect(self.new_database)
        self.saved_panel.open_database_requested.connect(self.open_database)
        self.saved_panel.load_requested.connect(self.load_saved_entry)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self.saved_panel)
        self.main_splitter.addWidget(root)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([275, 1005])
        self.setCentralWidget(self.main_splitter)
        for key, widget in (
            ("certificate_pem", self.cert_edit),
            ("ca_pem", self.ca_edit),
            ("raw_pem", self.raw),
            ("certificates_tree", self.tree),
            ("saved_entries_table", self.saved_panel.table),
        ):
            self.font_zoom.register(key, widget)
        for key, viewer in (
            ("details", self.details),
            ("verified_path", self.path_details),
            ("diagnostics", self.diagnostics),
            ("lint", self.lint_view),
        ):
            self.font_zoom.register(f"{key}_tree", viewer.tree)
            self.font_zoom.register(f"{key}_json", viewer.code)
        self.set_result_mode(self.view_mode.currentText(), save=False)
        self.apply_appearance()
        QApplication.styleHints().colorSchemeChanged.connect(self.on_system_theme_changed)

    def closeEvent(self, event):
        # Avoid keeping closed windows alive through the application-wide signal.
        try:
            QApplication.styleHints().colorSchemeChanged.disconnect(self.on_system_theme_changed)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)

    def open_about(self):
        AboutDialog(self).exec()

    def open_settings(self):
        dialog = SettingsDialog(self.font_family, self.font_size, self.theme, self,
                                db_path=self.storage.path)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            values = dialog.values()
            for key, value in values.items():
                self.settings.set_preference(key, value)
            self.font_family = values["font_family"]
            self.font_size = int(values["font_size"])
            self.theme = values["theme"]
            if dialog.reset_font_sizes_requested:
                self.font_zoom.reset()
            self.apply_appearance()

    def on_system_theme_changed(self, scheme):
        if self.theme == "system":
            self.apply_appearance()

    def apply_appearance(self):
        apply_theme(self.theme)
        dark = is_dark(self.theme)
        for key, editor in (
            ("certificate_pem", self.cert_edit),
            ("ca_pem", self.ca_edit),
            ("raw_pem", self.raw),
        ):
            editor.configure(self.font_family, self.font_zoom.size(key), dark)
        for key, viewer in (
            ("details", self.details),
            ("verified_path", self.path_details),
            ("diagnostics", self.diagnostics),
            ("lint", self.lint_view),
        ):
            viewer.configure(
                self.font_family, self.font_size, dark,
                tree_size=self.font_zoom.size(f"{key}_tree"),
                code_size=self.font_zoom.size(f"{key}_json"),
            )
        tree_font = QFont(self.font_family, self.font_zoom.size("certificates_tree"))
        tree_font.setStyleHint(QFont.StyleHint.Monospace)
        self.tree.setFont(tree_font)
        self.saved_panel.configure(self.font_family, self.font_size, self.theme)
        saved_font = QFont(self.font_family, self.font_zoom.size("saved_entries_table"))
        saved_font.setStyleHint(QFont.StyleHint.Monospace)
        self.saved_panel.table.setFont(saved_font)
        self.saved_panel.refresh()
        self.style_certificate_tree()
        if self.report:
            self.set_trust_indicator(self.report["status"] == "trusted")

    def set_trust_indicator(self, trusted: bool | None):
        if trusted is None:
            self.trust_indicator.hide()
            return
        dark = is_dark(self.theme)
        color = ("#56c38b" if dark else "#16834c") if trusted else (
            "#ff7070" if dark else "#c92b2b"
        )
        self.trust_indicator.setStyleSheet(f"color: {color}; font-size: 19px;")
        self.trust_indicator.setToolTip("Trusted" if trusted else "Untrusted")
        self.trust_indicator.show()

    def style_certificate_tree(self):
        if not self.report:
            return
        path = self.tree.topLevelItem(1)
        if path is None:
            return
        dark = is_dark(self.theme)
        colors = {
            "system": "#86c5ff" if dark else "#216aab",
            "database": "#d2a8ff" if dark else "#7746ad",
        }
        for index, cert in enumerate(self.report["verified_chain"]):
            item = path.child(index)
            if item is None:
                continue
            origin = cert.get("origin", "input")
            item.setForeground(0, QBrush(QColor(colors[origin])) if origin in colors
                               else QBrush())
            if origin == "system":
                item.setToolTip(0, "Certificate from the system trust store")
            elif origin == "database":
                item.setToolTip(0, f"Certificate from the local database: {cert.get('saved_name', '')}")

    def set_result_mode(self, mode, save=True):
        for viewer in (self.details, self.path_details, self.diagnostics, self.lint_view):
            viewer.set_mode(mode)
        if save:
            self.settings.set_preference("result_view", mode)

    def load_input(self, value: str):
        """Populate and analyze a startup PEM string, certificate file or URL."""
        try:
            kind, content = classify_input(value)
            if kind == "url":
                self.url_input.setText(content)
                self.start_remote_fetch()
                return
            pem = read_cert_file(content) if kind == "file" else content
            self.cert_edit.setPlainText(pem)
            self.analyze()
        except (OSError, ValueError, UnicodeError) as exc:
            self.show_error(f"Cannot load initial input: {exc}")

    def start_remote_fetch(self):
        """Fetch the peer chain without trusting its signer, then verify it normally."""
        if self.fetch_worker is not None and self.fetch_worker.isRunning():
            return
        self.set_trust_indicator(None)
        url = self.url_input.text().strip()
        try:
            host, port = parse_tls_target(url)
        except ValueError as exc:
            self.show_error(str(exc))
            return
        self.fetch_button.setEnabled(False)
        self.status.setText(f"Fetching presented TLS chain from {host}:{port}...")
        self.fetch_worker = FetchWorker(url)
        self.fetch_worker.completed.connect(self.on_remote_fetched)
        self.fetch_worker.failed.connect(self.on_remote_error)
        self.fetch_worker.finished.connect(self.on_remote_finished)
        self.fetch_worker.start()

    def on_remote_fetched(self, result):
        self.cert_edit.setPlainText(result.pem)
        self.hostname.setText(result.hostname)
        self.purpose.setCurrentText("tls-server")
        self.analyze()

    def on_remote_error(self, message: str):
        self.show_error(f"TLS retrieval failed: {message}")

    def on_remote_finished(self):
        self.fetch_button.setEnabled(True)

    def open_file(self, editor):
        path, _ = QFileDialog.getOpenFileName(self, "Open certificate", "",
                                              "Certificates (*.pem *.crt *.cer *.chain *.der);;All files (*)")
        if path:
            try:
                editor.setPlainText(read_cert_file(path))
            except Exception as exc:
                QMessageBox.warning(self, "Open failed", str(exc))

    def save_as(self, kind, editor):
        filename = "certificate.pem" if kind == "certificate" else "custom-ca.pem"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PEM to file", filename,
            "PEM certificate (*.pem);;All files (*)"
        )
        if not path:
            return
        try:
            Path(path).write_text(editor.toPlainText(), encoding="utf-8")
            self.status.setText(f"Saved PEM to {path}")
        except OSError as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

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
            self.saved_panel.refresh()
            self.status.setText(f"Saved {kind}: {name.strip()}")
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", str(exc))

    def load_saved_entry(self, kind: str, pem: str):
        editor = self.ca_edit if kind == "ca" else self.cert_edit
        editor.setPlainText(pem)
        self.status.setText(f"Loaded saved entry into {kind} editor")

    def database_busy(self) -> bool:
        for worker in (self.worker, self.fetch_worker):
            if worker is not None and worker.isRunning():
                QMessageBox.information(
                    self, "Database in use",
                    "Finish the current certificate analysis before switching databases.",
                )
                return True
        return False

    def switch_database(self, path: str | Path) -> bool:
        if self.database_busy():
            return False
        try:
            storage = Storage(path)
        except (OSError, sqlite3.DatabaseError, RuntimeError) as exc:
            QMessageBox.warning(self, "Cannot open database", str(exc))
            return False
        self.storage = storage
        self.settings.set_preference("last_database", str(storage.path.resolve()))
        self.saved_panel.set_database(storage)
        self.report = None
        self.certificate_data = []
        self.tree.clear()
        for viewer in (self.details, self.path_details, self.diagnostics, self.lint_view):
            viewer.set_data({})
        self.raw.clear()
        self.lint_certificate.clear()
        self.lint_certificate.addItem("All certificates")
        self.lint_summary.setText("Linting has not run")
        self.set_trust_indicator(None)
        self.status.setText(f"Using certificate database: {storage.path}")
        return True

    def new_database(self):
        if self.database_busy():
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Create certificate database", str(default_database_path().parent),
            "SQLite databases (*.sqlite3 *.db);;All files (*)",
        )
        if not path:
            return
        destination = Path(path)
        if destination.exists():
            QMessageBox.warning(
                self, "Database already exists",
                "Choose a new filename or use Open DB for an existing database.",
            )
            return
        self.switch_database(destination)

    def open_database(self):
        if self.database_busy():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open certificate database", str(self.storage.path.parent),
            "SQLite databases (*.sqlite3 *.sqlite *.db);;All files (*)",
        )
        if path:
            self.switch_database(path)

    def analyze(self):
        self.set_trust_indicator(None)
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
        self.status.setText("Analyzing certificates, verifying trust and linting...")
        self.analyze_btn.setEnabled(False)
        self.worker = AnalysisWorker(pem, self.ca_edit.toPlainText(), self.storage,
                                     purpose, hostname, fingerprint,
                                     self.lint_profile.currentData())
        self.worker.completed.connect(self.show_report)
        self.worker.failed.connect(self.show_error)
        self.worker.finished.connect(lambda: self.analyze_btn.setEnabled(True))
        self.worker.start()

    def show_error(self, message):
        self.report = None
        self.set_trust_indicator(None)
        self.status.setText(f"Analysis failed: {message}")
        self.lint_summary.setText("Linting has not run")
        self.lint_view.set_data({})
        self.diagnostics.set_data({"error": message})
        self.tabs.setCurrentWidget(self.diagnostics)

    def show_lint_details(self, *_):
        lint = (self.report or {}).get("lint")
        if lint is None:
            self.lint_view.set_data({"status": "not_run"})
            return
        index = self.lint_certificate.currentIndex()
        self.lint_view.set_data(lint if index <= 0 else lint["certificates"][index - 1])

    def show_lint_report(self):
        lint = (self.report or {}).get("lint")
        self.lint_certificate.blockSignals(True)
        self.lint_certificate.clear()
        self.lint_certificate.addItem("All certificates")
        if lint:
            for certificate in lint["certificates"]:
                self.lint_certificate.addItem(certificate["subject"])
            summary = lint["summary"]
            self.lint_summary.setText(
                f"{lint['profile']} | {lint['status']} | "
                f"{summary['FATAL']} fatal, {summary['ERROR']} errors, "
                f"{summary['WARNING']} warnings"
            )
        else:
            self.lint_summary.setText("Linting has not run")
        self.lint_certificate.blockSignals(False)
        self.show_lint_details()

    def show_report(self, report):
        self.report = report
        self.show_lint_report()
        self.set_trust_indicator(report["status"] == "trusted")
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
            name = cert.get("saved_name")
            label = (f"[{name}] " if name else "") + cert["subject"]
            if index == len(report["verified_chain"]) - 1:
                label += " [trust anchor]"
            entry = QTreeWidgetItem([label])
            entry.setData(0, Qt.ItemDataRole.UserRole, ("verified", index))
            path.addChild(entry)
        self.tree.expandAll()
        self.style_certificate_tree()
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


def run(initial_input: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    register_font()
    window = MainWindow()
    window.show()
    if initial_input is not None:
        QTimer.singleShot(0, lambda: window.load_input(initial_input))
    return app.exec()
