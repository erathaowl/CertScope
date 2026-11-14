"""Qt GUI smoke test (offscreen on CI)."""

import os
import sys

import pytest


@pytest.fixture(scope="session")
def qt_app():
    """Keep one QApplication alive across every GUI test on Windows."""
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from PySide6.QtCore import QCoreApplication, QEvent

    app = QApplication.instance() or QApplication([])
    yield app
    for widget in app.topLevelWidgets():
        widget.close()
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    app.quit()


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    """Avoid touching the real application settings and default database."""
    from certscope.app_settings import AppSettings

    monkeypatch.setattr(
        "certscope.gui.AppSettings", lambda: AppSettings(tmp_path / "settings.yaml")
    )
    monkeypatch.setattr(
        "certscope.gui.default_database_path", lambda: tmp_path / "default.sqlite3"
    )
    from certscope.storage import Storage

    monkeypatch.setattr(
        "certscope.gui.Storage",
        lambda path=None: Storage(path or tmp_path / "default.sqlite3"),
    )


@pytest.mark.skipif(sys.platform.startswith('linux'), reason='Qt offscreen teardown is unstable in CI')
def test_gui_window_can_be_constructed(tmp_path, monkeypatch, qt_app, chain):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from certscope.gui import AboutDialog, MainWindow
    from certscope import __version__
    from certscope.app_info import APP_LICENSE, APP_NAME, APP_URL
    from certscope.storage import Storage

    path = tmp_path / "gui.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or path))
    assert qt_app is not None
    window = MainWindow()
    assert window.cert_edit is not None
    assert window.ca_edit is not None
    assert window.vertical_splitter.count() == 2
    assert window.url_input is not None
    assert window.trust_indicator.isHidden()
    window.set_trust_indicator(True)
    assert window.trust_indicator.toolTip() == "Trusted"
    window.set_trust_indicator(False)
    assert window.trust_indicator.toolTip() == "Untrusted"

    about = AboutDialog(window)
    assert about.identity.text() == f"{APP_NAME} - {__version__} ({APP_LICENSE})"
    assert APP_URL in about.repository.text()
    assert about.findChildren(type(about.identity))[0].pixmap() is not None
    about.close()

    storage = Storage(path)
    storage.save("ca", "Trusted Root", chain["root"], trusted=True)
    storage.save("ca", "Untrusted Root", chain["root"], trusted=False)
    window.saved_panel.refresh()
    table = window.saved_panel.table
    assert table.columnCount() == 2
    assert [table.horizontalHeaderItem(i).text() for i in range(2)] == [
        "Name", "Trusted"
    ]
    states = {
        table.item(i, 0).text(): table.item(i, 1)
        for i in range(table.rowCount())
    }
    assert states["Trusted Root"].text() == "✓"
    assert states["Untrusted Root"].text() == "✗"
    assert states["Trusted Root"].foreground().color() != (
        states["Untrusted Root"].foreground().color()
    )
    assert window.main_splitter.widget(0) is window.saved_panel
    window.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_saved_ca_context_menu_trust_untrust(tmp_path, monkeypatch, qt_app, chain):
    from certscope.gui import MainWindow

    window = MainWindow()
    window.storage.save("ca", "Root", chain["root"], trusted=False)
    window.storage.save("certificate", "Leaf", chain["leaf"])
    window.saved_panel.refresh()
    window.show()
    qt_app.processEvents()
    panel = window.saved_panel
    actions_seen = []
    desired = []

    class FakeMenu:
        def __init__(self, *_):
            self.actions = []

        def addAction(self, text):
            self.actions.append(text)
            return text

        def addSeparator(self):
            pass

        def exec(self, _position):
            actions_seen.append(self.actions.copy())
            return desired[0] if desired else None

    monkeypatch.setattr("certscope.saved_entries.QMenu", FakeMenu)

    def context_for(name):
        table = panel.table
        row = next(
            index for index in range(table.rowCount())
            if table.item(index, 0).text() == name
        )
        panel.show_context_menu(table.visualItemRect(table.item(row, 0)).center())
        return table.item(row, 1)

    desired[:] = ["Trust"]
    item = context_for("Root")
    assert "Trust" in actions_seen[-1]
    assert "Untrust" not in actions_seen[-1]
    assert window.storage.get("ca", "Root").trusted
    assert item.text() == "✓"
    trusted_color = item.foreground().color()
    assert trusted_color.green() > trusted_color.red()

    desired[:] = ["Untrust"]
    item = context_for("Root")
    assert "Untrust" in actions_seen[-1]
    assert "Trust" not in actions_seen[-1]
    assert not window.storage.get("ca", "Root").trusted
    assert item.text() == "✗"
    untrusted_color = item.foreground().color()
    assert untrusted_color.red() > untrusted_color.green()

    desired.clear()
    context_for("Leaf")
    assert "Trust" not in actions_seen[-1]
    assert "Untrust" not in actions_seen[-1]
    window.close()



@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
@pytest.mark.parametrize("editor_name", ["cert_edit", "ca_edit"])
def test_editor_buttons_use_editor_not_clicked_state(tmp_path, monkeypatch, editor_name, qt_app):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QPushButton
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or tmp_path / "gui.sqlite3"))
    assert qt_app is not None
    window = MainWindow()
    editor = getattr(window, editor_name)
    buttons = {button.text(): button for button in editor.parentWidget().findChildren(QPushButton)}

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("sample.pem", ""))
    monkeypatch.setattr("certscope.gui.read_cert_file", lambda path: "sample PEM")
    buttons["Open file"].click()
    assert editor.toPlainText() == "sample PEM"

    output = tmp_path / "saved.pem"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(output), ""))
    buttons["Save as"].click()
    assert output.read_text(encoding="utf-8") == "sample PEM"

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Example", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    saved = []
    monkeypatch.setattr(window.storage, "save", lambda *args, **kwargs: saved.append((args, kwargs)))
    buttons["Save named"].click()
    assert saved == [((("ca" if editor_name == "ca_edit" else "certificate"), "Example", "sample PEM"), {"trusted": False})]
    window.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_result_view_modes_and_settings_persist(tmp_path, monkeypatch, qt_app):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    path = tmp_path / "gui.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or path))
    assert qt_app is not None
    window = MainWindow()
    window.details.set_data({"subject": "example", "extensions": [1, 2]})
    window.show_report({
        "status": "trusted", "chain_status": "trusted", "trust_source": "database",
        "certificates": [{"subject": "CN=Leaf", "pem": "leaf"}],
        "verified_chain": [
            {"subject": "CN=Leaf", "pem": "leaf", "origin": "input"},
            {"subject": "CN=Root", "pem": "root", "origin": "database",
             "saved_name": "Office CA"},
        ],
        "trust_anchor": {"subject": "CN=Root"},
    })
    assert window.trust_indicator.toolTip() == "Trusted"
    verified_item = window.tree.topLevelItem(1).child(1)
    assert verified_item.text(0).startswith("[Office CA] CN=Root")
    assert verified_item.foreground(0).color().isValid()
    window.view_mode.setCurrentText("JSON")
    assert window.details.stack.currentIndex() == 1
    assert '"subject": "CN=Leaf"' in window.details.code.toPlainText()
    window.view_mode.setCurrentText("Tree")
    assert window.details.tree.topLevelItemCount() == 1
    window.settings.set_preference("theme", "dark")
    window.settings.set_preference("font_size", "13")
    window.close()
    another = MainWindow()
    assert another.theme == "dark"
    assert another.font_size == 13
    another.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_tree_copy_actions(qt_app, monkeypatch):
    from certscope.json_viewer import JsonViewer

    viewer = JsonViewer()
    viewer.setParent(qt_app.activeWindow())
    copied = []
    monkeypatch.setattr(viewer.tree, "copy_text", copied.append)
    long_value = "long data " * 30
    viewer.set_data({"name": long_value, "nested": {"count": 2}})
    root = viewer.tree.topLevelItem(0)
    item = root.child(0)
    assert len(item.text(1)) < len(long_value)
    assert viewer.tree.copy_item(item, "field") == "name"
    assert copied[-1] == "name"
    assert viewer.tree.copy_item(item, "value") == long_value
    assert copied[-1] == long_value
    viewer.configure("Consolas", 11, True)
    assert item.foreground(1).color().isValid()
    assert root.child(1).font(1).italic()
    assert item.foreground(1).color() != root.child(1).foreground(1).color()
    viewer.configure("Consolas", 11, False)
    assert root.child(1).font(1).italic()
    assert viewer.tree.copy_item(root.child(1), "element") == (
        '{\n  "nested": {\n    "count": 2\n  }\n}'
    )
    viewer.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_result_view_preference_restored(tmp_path, monkeypatch, qt_app):
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    path = tmp_path / "prefs.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or path))
    first = MainWindow()
    first.view_mode.setCurrentText("JSON")
    assert first.settings.get_preference("result_view") == "JSON"
    first.close()

    second = MainWindow()
    assert second.view_mode.currentText() == "JSON"
    assert second.details.stack.currentIndex() == 1
    second.view_mode.setCurrentText("Tree")
    second.close()
    assert second.settings.get_preference("result_view") == "Tree"


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_lint_panel_and_profile_selection(tmp_path, monkeypatch, qt_app):
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    path = tmp_path / "lint.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or path))
    window = MainWindow()
    assert window.lint_profile.currentData() == "rfc5280"
    assert window.tabs.tabText(window.tabs.indexOf(window.lint_panel)) == "Lint"
    window.lint_profile.setCurrentIndex(1)
    assert window.settings.get_preference("lint_profile") == "cabf-tls"

    window.report = {
        "lint": {
            "profile": "cabf-tls",
            "status": "findings",
            "summary": {"FATAL": 0, "ERROR": 1, "WARNING": 0, "NOTICE": 0, "INFO": 0},
            "certificates": [
                {"subject": "CN=test", "status": "findings",
                 "findings": [{"severity": "ERROR", "code": "test.finding"}]},
            ],
        }
    }
    window.show_lint_report()
    assert window.lint_certificate.count() == 2
    assert "1 errors" in window.lint_summary.text()
    window.lint_certificate.setCurrentIndex(1)
    assert window.lint_view.tree.topLevelItemCount() == 1
    window.close()

    again = MainWindow()
    assert again.lint_profile.currentData() == "cabf-tls"
    again.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_ctrl_wheel_zoom_is_independent_and_persistent(tmp_path, monkeypatch, qt_app):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication, QAbstractScrollArea

    from certscope.gui import MainWindow
    from certscope.storage import Storage

    path = tmp_path / "font_zoom.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or path))
    window = MainWindow()
    window.show()
    qt_app.processEvents()

    def zoom(widget, direction):
        widget.setFocus(Qt.FocusReason.OtherFocusReason)
        qt_app.processEvents()
        assert widget.hasFocus() or (
            isinstance(widget, QAbstractScrollArea) and widget.viewport().hasFocus()
        )
        event = QWheelEvent(
            QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120 * direction),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        )
        recipient = widget.viewport() if isinstance(widget, QAbstractScrollArea) else widget
        QApplication.sendEvent(recipient, event)
        qt_app.processEvents()
        assert event.isAccepted()

    zoom(window.cert_edit, 1)
    zoom(window.cert_edit, 1)
    assert window.cert_edit.font().pointSize() == 13
    assert window.ca_edit.font().pointSize() == 11

    zoom(window.ca_edit, -1)
    assert window.ca_edit.font().pointSize() == 10
    assert window.raw.font().pointSize() == 11

    zoom(window.tree, 1)
    assert window.tree.font().pointSize() == 12

    window.tabs.setCurrentWidget(window.details)
    window.view_mode.setCurrentText("Tree")
    qt_app.processEvents()
    zoom(window.details.tree, 1)
    assert window.details.tree.font().pointSize() == 12
    assert window.details.code.font().pointSize() == 11

    window.view_mode.setCurrentText("JSON")
    qt_app.processEvents()
    zoom(window.details.code, -1)
    assert window.details.code.font().pointSize() == 10
    assert window.details.tree.font().pointSize() == 12

    assert "tls_url" not in window.font_zoom._widgets
    assert "hostname" not in window.font_zoom._widgets

    assert window.settings.get_preference("font_size_overrides") == {
        "certificate_pem": 13,
        "ca_pem": 10,
        "certificates_tree": 12,
        "details_tree": 12,
        "details_json": 10,
    }
    window.close()

    restored = MainWindow()
    assert restored.cert_edit.font().pointSize() == 13
    assert restored.ca_edit.font().pointSize() == 10
    assert restored.tree.font().pointSize() == 12
    assert restored.details.tree.font().pointSize() == 12
    assert restored.details.code.font().pointSize() == 10
    assert restored.diagnostics.tree.font().pointSize() == 11
    restored.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_settings_reset_clears_all_font_overrides(tmp_path, monkeypatch, qt_app):
    from PySide6.QtWidgets import QDialog
    from certscope.gui import MainWindow
    from certscope.preferences import SettingsDialog
    from certscope.storage import Storage

    path = tmp_path / "font_settings.sqlite3"
    from certscope.app_settings import AppSettings

    settings = AppSettings(tmp_path / "settings.yaml")
    settings.set_preference("font_size_overrides", {
        "certificate_pem": 19,
        "details_tree": 8,
        "details_json": 28,
        "saved_entries_table": 25,
    })
    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or path))
    window = MainWindow()
    assert window.cert_edit.font().pointSize() == 19
    assert window.details.tree.font().pointSize() == 8

    dialog = SettingsDialog(window.font_family, window.font_size, window.theme, window)
    dialog.size.setValue(15)
    dialog.reset_font_button.click()
    assert dialog.reset_font_sizes_requested
    assert window.cert_edit.font().pointSize() == 19
    dialog.close()

    def accept_reset(self):
        self.size.setValue(15)
        self.reset_font_button.click()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(SettingsDialog, "exec", accept_reset)
    window.open_settings()
    assert window.font_size == 15
    assert window.settings.get_preference("font_size") == "15"
    assert window.settings.get_preference("font_size_overrides", "missing") == "missing"
    assert window.cert_edit.font().pointSize() == 15
    assert window.ca_edit.font().pointSize() == 15
    assert window.details.tree.font().pointSize() == 15
    assert window.details.code.font().pointSize() == 15
    assert window.tree.font().pointSize() == 15
    window.close()
    reopened = MainWindow()
    assert reopened.cert_edit.font().pointSize() == 15
    assert reopened.details.tree.font().pointSize() == 15
    reopened.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_saved_sidebar_font_zoom_persists(tmp_path, monkeypatch, qt_app):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    from certscope.gui import MainWindow
    from certscope.storage import Storage

    path = tmp_path / "entries_font.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or path))
    window = MainWindow()
    window.show()
    qt_app.processEvents()

    table = window.saved_panel.table
    table.setFocus()
    qt_app.processEvents()
    assert table.hasFocus()
    event = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    )
    QApplication.sendEvent(table.viewport(), event)
    assert table.font().pointSize() == 12
    assert window.settings.get_preference("font_size_overrides")[
        "saved_entries_table"
    ] == 12
    window.close()

    second = MainWindow()
    assert second.saved_panel.table.font().pointSize() == 12
    second.close()

@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_ctrl_wheel_does_not_zoom_without_control(tmp_path, monkeypatch, qt_app):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    from certscope.gui import MainWindow
    from certscope.storage import Storage

    path = tmp_path / "wheel_normal.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda db=None: Storage(db or path))
    window = MainWindow()
    window.show()
    window.cert_edit.setFocus()
    qt_app.processEvents()
    event = QWheelEvent(
        QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollUpdate, False,
    )
    QApplication.sendEvent(window.cert_edit.viewport(), event)
    assert window.cert_edit.font().pointSize() == 11
    assert window.settings.get_preference("font_size_overrides", "missing") == "missing"
    window.close()



@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_database_sidebar_switch_and_restore(tmp_path, monkeypatch, qt_app, chain):
    from PySide6.QtWidgets import QFileDialog

    from certscope.app_settings import AppSettings
    from certscope.gui import MainWindow

    default_path = tmp_path / "default.sqlite3"
    secondary_path = tmp_path / "secondary.sqlite3"
    window = MainWindow()
    window.storage.save("ca", "Default Root", chain["root"], trusted=True)
    window.saved_panel.refresh()
    assert window.saved_panel.table.rowCount() == 1
    assert window.storage.path == default_path

    monkeypatch.setattr(
        QFileDialog, "getSaveFileName",
        lambda *args, **kwargs: (str(secondary_path), ""),
    )
    window.saved_panel.new_database_button.click()
    assert secondary_path.is_file()
    assert window.storage.path == secondary_path
    assert window.saved_panel.table.rowCount() == 0
    assert window.settings.get_preference("last_database") == str(secondary_path)
    window.storage.save("certificate", "Secondary", chain["leaf"])
    window.saved_panel.refresh()
    assert window.saved_panel.table.rowCount() == 1

    monkeypatch.setattr(
        QFileDialog, "getOpenFileName",
        lambda *args, **kwargs: (str(default_path), ""),
    )
    window.saved_panel.open_database_button.click()
    assert window.storage.path == default_path
    assert window.saved_panel.table.item(0, 0).text() == "Default Root"
    window.close()

    reopened = MainWindow()
    assert reopened.storage.path == default_path
    assert reopened.storage.get("ca", "Default Root").trusted
    assert AppSettings(tmp_path / "settings.yaml").get_preference(
        "last_database"
    ) == str(default_path)
    reopened.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_missing_database_is_reported_and_falls_back(tmp_path, monkeypatch, qt_app):
    from PySide6.QtWidgets import QMessageBox

    from certscope.app_settings import AppSettings
    from certscope.gui import MainWindow

    missing = tmp_path / "unavailable.sqlite3"
    AppSettings(tmp_path / "settings.yaml").set_preference(
        "last_database", str(missing)
    )
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning",
        lambda *args, **kwargs: warnings.append((args, kwargs)),
    )
    window = MainWindow()
    qt_app.processEvents()
    assert window.storage.path == tmp_path / "default.sqlite3"
    assert window.storage.path.is_file()
    assert window.settings.get_preference("last_database") == str(window.storage.path)
    assert warnings
    assert str(missing) in warnings[0][0][2]
    window.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_saved_entry_context_actions_and_raw_autosave(
    tmp_path, monkeypatch, qt_app, chain
):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    from certscope.gui import MainWindow
    from certscope.saved_entries import RawEntryDialog

    window = MainWindow()
    window.storage.save("certificate", "Leaf", chain["leaf"])
    window.storage.save("ca", "CA Root", chain["root"], trusted=True)
    panel = window.saved_panel
    panel.refresh()
    assert panel.table.columnCount() == 2

    certificate = window.storage.get("certificate", "Leaf")
    panel.load_requested.emit("ca", certificate.pem_bundle)
    assert window.ca_edit.toPlainText() == certificate.pem_bundle
    panel.load_requested.emit("certificate", certificate.pem_bundle)
    assert window.cert_edit.toPlainText() == certificate.pem_bundle

    dialog = RawEntryDialog(
        certificate, window.storage, window.settings,
        window.font_family, window.font_size, window.theme, window
    )
    dialog.editor.setPlainText(chain["root"])
    dialog.reject()
    assert window.storage.get("certificate", "Leaf").pem_bundle == (
        window.storage.get("ca", "CA Root").pem_bundle
    )

    monkeypatch.setattr(
        QInputDialog, "getText",
        lambda *args, **kwargs: ("Renamed Leaf", True),
    )
    panel.rename_entry(window.storage.get("certificate", "Leaf"))
    assert window.storage.get("certificate", "Renamed Leaf")

    root = window.storage.get("ca", "CA Root")
    panel.toggle_trust(root)
    assert not window.storage.get("ca", "CA Root").trusted
    panel.toggle_trust(window.storage.get("ca", "CA Root"))
    assert window.storage.get("ca", "CA Root").trusted

    monkeypatch.setattr(
        QMessageBox, "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    panel.delete_entry(window.storage.get("certificate", "Renamed Leaf"))
    assert [entry.name for entry in window.storage.list()] == ["CA Root"]
    window.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_simple_line_edits_do_not_zoom(tmp_path, qt_app):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication

    from certscope.gui import MainWindow

    window = MainWindow()
    window.show()
    qt_app.processEvents()
    for editor in (window.url_input, window.hostname):
        size = editor.font().pointSize()
        editor.setFocus()
        qt_app.processEvents()
        event = QWheelEvent(
            QPointF(10, 10), QPointF(10, 10), QPoint(0, 0), QPoint(0, 120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.ControlModifier,
            Qt.ScrollPhase.ScrollUpdate, False,
        )
        QApplication.sendEvent(editor, event)
        assert editor.font().pointSize() == size
    assert "tls_url" not in window.font_zoom.overrides
    assert "hostname" not in window.font_zoom.overrides
    window.close()
