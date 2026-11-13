"""Tests for the Windows release ZIP packaging."""

from zipfile import ZipFile

import pytest

from certscope.windows_package import EXECUTABLES, create_archives


def test_archive_names_and_original_content(tmp_path):
    samples = {
        "certscope.exe": b"MZgui-data",
        "certscope-cli.exe": b"MZcli-data",
    }
    for filename, content in samples.items():
        (tmp_path / filename).write_bytes(content)
    archives = create_archives(tmp_path)
    assert {path.name for path in archives} == set(EXECUTABLES)
    for name, executable in EXECUTABLES.items():
        with ZipFile(tmp_path / name) as package:
            assert package.namelist() == [executable]
            assert package.read(executable) == samples[executable]


def test_package_requires_both_executables(tmp_path):
    (tmp_path / "certscope.exe").write_bytes(b"MZ")
    with pytest.raises(FileNotFoundError, match="certscope-cli.exe"):
        create_archives(tmp_path)
