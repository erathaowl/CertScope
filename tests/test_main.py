"""Check that the CLI does not require the optional Qt interface."""

import sys
import tomllib
from pathlib import Path
from types import ModuleType

from certscope.main import main


def test_core_dependencies_exclude_gui():
    project_file = Path(__file__).resolve().parents[1] / "pyproject.toml"
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
    core = " ".join(project["dependencies"]).lower()
    gui = " ".join(project["optional-dependencies"]["gui"]).lower()

    assert "pyside6" not in core
    assert "pyyaml" not in core
    assert "pyside6-essentials" in gui
    assert "pyyaml" in gui
    assert project["scripts"]["certscope"] == "certscope.main:main"


def test_headless_default_shows_cli_help(monkeypatch, capsys):
    monkeypatch.setattr("certscope.main.find_spec", lambda name: None)
    assert main([]) == 0
    output = capsys.readouterr()
    assert "usage: certscope" in output.out
    assert "inspect" in output.out
    assert not output.err


def test_headless_explicit_gui_reports_optional_extra(monkeypatch, capsys):
    monkeypatch.setattr("certscope.main.find_spec", lambda name: None)
    for args in (["gui"], ["server.pem"], ["gui", "server.pem"]):
        assert main(args) == 2
        assert 'pip install "certscope[gui]"' in capsys.readouterr().err


def test_cli_does_not_inspect_gui_dependencies(monkeypatch, capsys):
    def unexpected_gui_probe(name):
        raise AssertionError(f"Unexpected GUI dependency check: {name}")

    monkeypatch.setattr("certscope.main.find_spec", unexpected_gui_probe)
    assert main(["--version"]) == 0
    assert "CertScope" in capsys.readouterr().out


def test_gui_is_loaded_only_for_gui_mode(monkeypatch):
    monkeypatch.setattr("certscope.main.find_spec", lambda name: object())
    gui = ModuleType("certscope.gui")
    inputs = []

    def run(initial_input=None):
        inputs.append(initial_input)
        return 0

    gui.run = run
    monkeypatch.setitem(sys.modules, "certscope.gui", gui)

    assert main([]) == 0
    assert main(["gui", "server.pem"]) == 0
    assert main(["server.pem"]) == 0
    assert inputs == [None, "server.pem", "server.pem"]
