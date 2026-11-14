"""Build two independent, standalone Windows executables with Nuitka."""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

from certscope.app_info import APP_AUTHOR, APP_DESCRIPTION, APP_LICENSE, APP_NAME, APP_URL


def project_version() -> str:
    version = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"Invalid project version: {version}")
    return version


def build_options(name: str, version: str) -> list[str]:
    args = [
        "--mode=onefile",
        "--assume-yes-for-downloads",
        "--output-dir=dist",
        f"--output-filename={name}.exe",
        "--windows-icon-from-ico=assets/certscope.ico",
        f"--product-name={APP_NAME}",
        f"--company-name={APP_AUTHOR}",
        f"--product-version={version}",
        f"--file-version={version}.0",
        f"--file-description={APP_NAME} - {APP_DESCRIPTION}",
        f"--copyright=Copyright (c) 2026 {APP_AUTHOR}. {APP_LICENSE} License. {APP_URL}",
        "--include-module=pyasn1_fasder._native_helper",
        "--include-package-data=pkilint",
        "--include-package-data=iso4217",
        "--include-package-data=iso3166",
        "--include-package-data=iso639",
        "--include-package-data=publicsuffixlist",
    ]
    if name == "certscope":
        return args + [
            "--windows-console-mode=disable",
            "--enable-plugin=pyside6",
            "--include-data-dir=src/certscope/assets=certscope/assets",
            "--include-data-file=assets/certscope.png=assets/certscope.png",
            "gui_launcher.py",
        ]
    if name == "certscope-cli":
        return args + [
            "--nofollow-import-to=PySide6",
            "--nofollow-import-to=shiboken6",
            "cli_launcher.py",
        ]
    raise ValueError(f"Unknown executable: {name}")


def main() -> None:
    version = project_version()
    for name in ("certscope-cli", "certscope"):
        print(f"Building {name}.exe with Nuitka {version}", flush=True)
        subprocess.run([sys.executable, "-m", "nuitka", *build_options(name, version)], check=True)
        path = Path("dist") / f"{name}.exe"
        if not path.is_file() or path.stat().st_size == 0:
            raise RuntimeError(f"Missing executable: {path}")


if __name__ == "__main__":
    main()
