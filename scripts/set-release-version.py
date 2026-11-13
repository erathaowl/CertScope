"""Set the temporary tagged-checkout package version before building a release EXE."""

import re
import sys
from pathlib import Path


def update_version(version: str, project: Path = Path("pyproject.toml")) -> None:
    version = version.removeprefix("v")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a vMAJOR.MINOR.PATCH release tag")
    original = project.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'(?m)^version = "[^"]+"$',
        f'version = "{version}"',
        original,
        count=1,
    )
    if count != 1:
        raise ValueError("Expected exactly one project version")
    project.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    update_version(sys.argv[1])
