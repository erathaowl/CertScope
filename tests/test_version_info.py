"""Windows version-resource and package identity tests."""

import pytest

from certscope import __version__
from certscope.app_info import APP_AUTHOR, APP_LICENSE, APP_NAME, APP_URL
from certscope.version_info import current_version, version_text, write_version_files


def test_current_package_identity():
    assert APP_NAME == "CertScope"
    assert APP_AUTHOR == "erathaowl"
    assert APP_LICENSE == "MIT"
    assert APP_URL == "https://github.com/erathaowl/CertScope"
    assert current_version() == __version__


@pytest.mark.parametrize("executable", ["certscope.exe", "certscope-cli.exe"])
def test_windows_file_version_contains_expected_details(executable):
    details = version_text("1.2.1", executable)
    assert "filevers=(1, 2, 1, 0)" in details
    assert "'CompanyName', 'erathaowl'" in details
    assert "'LegalCopyright'" in details
    assert "MIT License" in details
    assert "'URL', 'https://github.com/erathaowl/CertScope'" in details
    assert f"'OriginalFilename', '{executable}'" in details


def test_resource_writer(tmp_path):
    write_version_files("1.2.1", tmp_path)
    assert (tmp_path / "certscope-version.txt").is_file()
    assert (tmp_path / "certscope-cli-version.txt").is_file()


def test_invalid_versions():
    with pytest.raises(ValueError):
        version_text("v1.2", "CertScope.exe")
