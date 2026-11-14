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


@pytest.mark.skipif(sys.platform.startswith('linux'), reason='Qt offscreen teardown is unstable in CI')
def test_gui_window_can_be_constructed(tmp_path, monkeypatch, qt_app, chain):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from certscope.gui import AboutDialog, EntriesDialog, MainWindow
    from certscope import __version__
    from certscope.app_info import APP_LICENSE, APP_NAME, APP_URL
    from certscope.storage import Storage

    path = tmp_path / "gui.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(path))
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
    entries = EntriesDialog(storage, window)
    states = {
        entries.table.item(i, 1).text(): entries.table.item(i, 2)
        for i in range(entries.table.rowCount())
    }
    assert states["Trusted Root"].text() == "✓"
    assert states["Untrusted Root"].text() == "✗"
    assert states["Trusted Root"].foreground().color() != (
        states["Untrusted Root"].foreground().color()
    )
    entries.close()
    window.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
@pytest.mark.parametrize("editor_name", ["cert_edit", "ca_edit"])
def test_editor_buttons_use_editor_not_clicked_state(tmp_path, monkeypatch, editor_name, qt_app):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QPushButton
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(tmp_path / "gui.sqlite3"))
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
    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(path))
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
    window.storage.set_preference("theme", "dark")
    window.storage.set_preference("font_size", "13")
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
    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(path))
    first = MainWindow()
    first.view_mode.setCurrentText("JSON")
    assert first.storage.get_preference("result_view") == "JSON"
    first.close()

    second = MainWindow()
    assert second.view_mode.currentText() == "JSON"
    assert second.details.stack.currentIndex() == 1
    second.view_mode.setCurrentText("Tree")
    second.close()
    assert Storage(path).get_preference("result_view") == "Tree"


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_lint_panel_and_profile_selection(tmp_path, monkeypatch, qt_app):
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    path = tmp_path / "lint.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(path))
    window = MainWindow()
    assert window.lint_profile.currentData() == "rfc5280"
    assert window.tabs.tabText(window.tabs.indexOf(window.lint_panel)) == "Lint"
    window.lint_profile.setCurrentIndex(1)
    assert Storage(path).get_preference("lint_profile") == "cabf-tls"

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
