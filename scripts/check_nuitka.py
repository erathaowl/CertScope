"""Validate the Nuitka Windows executables and their metadata."""

import tomllib
from pathlib import Path

import pefile


def metadata(path: Path):
    pe = pefile.PE(str(path))
    fields = {}
    for group in pe.FileInfo:
        for item in group:
            for table in getattr(item, "StringTable", []):
                fields.update({
                    key.decode(errors="replace"): value.decode(errors="replace")
                    for key, value in table.entries.items()
                })
    return pe, fields


def main() -> None:
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    for name, subsystem in (("certscope", 2), ("certscope-cli", 3)):
        path = Path("dist") / f"{name}.exe"
        pe, fields = metadata(path)
        assert pe.OPTIONAL_HEADER.Subsystem == subsystem, name
        assert fields["ProductName"] == "CertScope", fields
        assert fields["CompanyName"] == "erathaowl", fields
        assert fields["FileVersion"].startswith(version), fields
        assert fields["ProductVersion"].startswith(version), fields
        assert "MIT" in fields["LegalCopyright"], fields
        assert "github.com/erathaowl/CertScope" in fields["LegalCopyright"], fields
        assert any(
            entry.id == pefile.RESOURCE_TYPE["RT_GROUP_ICON"]
            for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries
        ), f"Missing icon in {name}"
        print(f"Verified version, author, license, URL and icon: {name}.exe")

    cli = Path("dist/cli_launcher.dist")
    assert cli.is_dir(), "Nuitka CLI distribution is missing"
    qt_files = [
        str(path) for path in cli.rglob("*")
        if path.is_file() and (
            "pyside6" in path.as_posix().lower()
            or "shiboken6" in path.as_posix().lower()
            or path.name.lower().startswith("qt6")
        )
    ]
    assert not qt_files, f"Qt libraries in CLI: {qt_files[:8]}"
    print("Verified headless CLI contains no Qt or PySide6")


if __name__ == "__main__":
    main()
