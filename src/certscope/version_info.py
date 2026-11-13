"""Generate Windows VERSIONINFO resources for both PyInstaller executables."""

import argparse
import re
import tomllib
from pathlib import Path

from certscope.app_info import APP_AUTHOR, APP_DESCRIPTION, APP_LICENSE, APP_NAME, APP_URL


def current_version(project: Path = Path("pyproject.toml")) -> str:
    return tomllib.loads(project.read_text(encoding="utf-8"))["project"]["version"]


def version_text(version: str, executable: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        raise ValueError("Version must follow MAJOR.MINOR.PATCH")
    numbers = (*[int(part) for part in match.groups()], 0)
    strings = {
        "CompanyName": APP_AUTHOR,
        "FileDescription": f"{APP_NAME} - {APP_DESCRIPTION}",
        "FileVersion": f"{version}.0",
        "InternalName": executable.removesuffix(".exe"),
        "LegalCopyright": f"Copyright (c) 2026 {APP_AUTHOR}. {APP_LICENSE} License.",
        "OriginalFilename": executable,
        "ProductName": APP_NAME,
        "ProductVersion": version,
        "Comments": f"{APP_LICENSE} License | {APP_URL}",
        "Authors": APP_AUTHOR,
        "License": APP_LICENSE,
        "URL": APP_URL,
    }
    fields = ",\n                    ".join(
        f"StringStruct({key!r}, {value!r})" for key, value in strings.items()
    )
    return (
        "VSVersionInfo(\n"
        f"    ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r},\n"
        "        mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,\n"
        "        subtype=0x0, date=(0, 0)),\n"
        "    kids=[\n"
        "        StringFileInfo([StringTable('040904B0', [\n"
        f"                    {fields}\n"
        "        ])]),\n"
        "        VarFileInfo([VarStruct('Translation', [1033, 1200])])\n"
        "    ]\n"
        ")\n"
    )


def write_version_files(version: str, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for executable in ("certscope.exe", "certscope-cli.exe"):
        resource = destination / f"{executable.removesuffix('.exe')}-version.txt"
        resource.write_text(version_text(version, executable), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("build"))
    args = parser.parse_args()
    write_version_files(current_version(), args.output)


if __name__ == "__main__":
    main()
