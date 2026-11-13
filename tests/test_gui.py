"""Qt GUI smoke test (offscreen on CI)."""

import os

import pytest


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
