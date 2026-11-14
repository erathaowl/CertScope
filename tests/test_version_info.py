"""Test the version information supplied to Nuitka."""

import tomllib
from pathlib import Path

import pytest

from certscope import __version__
from certscope.app_info import APP_AUTHOR, APP_LICENSE, APP_NAME, APP_URL
from scripts.build_nuitka import build_options, project_version


def test_version_and_identity():
    assert APP_NAME == "CertScope"
    assert APP_AUTHOR == "erathaowl"
    assert APP_LICENSE == "MIT"
    assert APP_URL == "https://github.com/erathaowl/CertScope"
    assert project_version() == __version__
    assert tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"] == __version__


@pytest.mark.parametrize("name", ["certscope", "certscope-cli"])
def test_version_resource_options(name):
    args = build_options(name, "1.3.1")
    assert "--mode=onefile" in args
    assert "--product-name=CertScope" in args
    assert "--company-name=erathaowl" in args
    assert "--file-version=1.3.1.0" in args
    assert "--product-version=1.3.1" in args
    assert "--windows-icon-from-ico=assets/certscope.ico" in args
    assert any(value.startswith("--copyright=") and
               "MIT" in value and APP_URL in value for value in args)


def test_gui_and_cli_separation():
    gui = build_options("certscope", "1.3.1")
    cli = build_options("certscope-cli", "1.3.1")
    assert "--enable-plugin=pyside6" in gui
    assert "--enable-plugin=pyside6" not in cli
    assert "--nofollow-import-to=PySide6" in cli
    assert "gui_launcher.py" in gui
    assert "cli_launcher.py" in cli


def test_unknown_executable():
    with pytest.raises(ValueError, match="Unknown executable"):
        build_options("invalid", "1.3.1")
