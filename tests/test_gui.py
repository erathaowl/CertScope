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

    app = QApplication.instance() or QApplication([])
    yield app
    app.closeAllWindows()
    app.processEvents()


@pytest.mark.skipif(sys.platform.startswith('linux'), reason='Qt offscreen teardown is unstable in CI')
def test_gui_window_can_be_constructed(tmp_path, monkeypatch, qt_app):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from certscope.gui import MainWindow
    from certscope.storage import Storage

    monkeypatch.setattr("certscope.gui.Storage", lambda: Storage(tmp_path / "gui.sqlite3"))
    assert qt_app is not None
    window = MainWindow()
    assert window.cert_edit is not None
    assert window.ca_edit is not None
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


@pytest.mark.skipif(sys.platform.startswith("linux"), reason="Qt offscreen teardown is unstable in CI")
def test_tree_copy_and_color_contrast(qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtWidgets import QPushButton
    from certscope.json_viewer import JsonViewer
    from certscope.preferences import apply_theme

    viewer = JsonViewer()
    long_value = "long data " * 30
    viewer.set_data({"name": long_value, "nested": {"count": 2}})
    root = viewer.tree.topLevelItem(0)
    item = root.child(0)
    assert len(item.text(1)) < len(long_value)
    assert viewer.tree.copy_item(item, "field") == "name"
    assert qt_app.clipboard().text() == "name"
    assert viewer.tree.copy_item(item, "value") == long_value
    assert qt_app.clipboard().text() == long_value
    assert viewer.tree.copy_item(root.child(1), "element") == (
        '{\n  "nested": {\n    "count": 2\n  }\n}'
    )
    viewer.tree.setCurrentItem(item, 1)
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    viewer.tree.keyPressEvent(event)
    assert qt_app.clipboard().text() == long_value

    for theme in ("light", "dark"):
        apply_theme(theme)
        viewer.configure("Consolas", 11, theme == "dark")
        button = QPushButton("Visible")
        assert "QPushButton" in qt_app.styleSheet()
        assert button.palette().buttonText().color().lightness() != (
            button.palette().button().color().lightness()
        )
        field_color = item.foreground(0).color()
        assert field_color.isValid()
        assert field_color != item.foreground(1).color()
        button.close()
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
