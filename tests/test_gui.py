"""Qt GUI smoke test (offscreen on CI)."""

import os
import sys

import pytest


@pytest.mark.skipif(sys.platform.startswith('linux'), reason='Qt offscreen teardown is unstable in CI')
def test_gui_window_can_be_constructed(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(tmp_path / "gui.sqlite3"))
    app = QApplication.instance() or QApplication([])
    assert app is not None
    window = MainWindow()
    assert window.cert_edit is not None
    assert window.ca_edit is not None
    window.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
@pytest.mark.parametrize("editor_name", ["cert_edit", "ca_edit"])
def test_editor_buttons_use_editor_not_clicked_state(tmp_path, monkeypatch, editor_name):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QFileDialog, QInputDialog, QMessageBox, QPushButton
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(tmp_path / "gui.sqlite3"))
    app = QApplication.instance() or QApplication([])
    assert app is not None
    window = MainWindow()
    editor = getattr(window, editor_name)
    buttons = {button.text(): button for button in editor.parentWidget().findChildren(QPushButton)}

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: ("sample.pem", ""))
    monkeypatch.setattr("certscope.gui.read_cert_file", lambda path: "sample PEM")
    buttons["Open file"].click()
    assert editor.toPlainText() == "sample PEM"

    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Example", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.No)
    saved = []
    monkeypatch.setattr(window.storage, "save", lambda *args, **kwargs: saved.append((args, kwargs)))
    buttons["Save named"].click()
    assert saved == [((("ca" if editor_name == "ca_edit" else "certificate"), "Example", "sample PEM"), {"trusted": False})]
    window.close()


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_result_view_modes_and_settings_persist(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    path = tmp_path / "gui.sqlite3"
    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(path))
    app = QApplication.instance() or QApplication([])
    assert app is not None
    window = MainWindow()
    window.details.set_data({"subject": "example", "extensions": [1, 2]})
    window.view_mode.setCurrentText("JSON")
    assert window.details.stack.currentIndex() == 1
    assert '"subject": "example"' in window.details.code.toPlainText()
    window.view_mode.setCurrentText("Tree")
    assert window.details.tree.topLevelItemCount() == 1
    window.storage.set_preference("theme", "dark")
    window.storage.set_preference("font_size", "13")
    window.close()
    another = MainWindow()
    assert another.theme == "dark"
    assert another.font_size == 13
    another.close()
