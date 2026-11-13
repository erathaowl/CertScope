"""Package the Windows GUI and CLI into separate lowercase-named ZIP assets."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXECUTABLES = {
    "certscope-windows.zip": "certscope.exe",
    "certscope-cli-windows.zip": "certscope-cli.exe",
}


def create_archives(directory: Path) -> list[Path]:
    """Include one matching executable per archive, without changing its bytes."""
    archives = []
    for archive_name, executable_name in EXECUTABLES.items():
        executable = directory / executable_name
        if not executable.is_file() or executable.stat().st_size == 0:
            raise FileNotFoundError(f"Missing Windows executable: {executable}")
        destination = directory / archive_name
        with ZipFile(destination, "w", compression=ZIP_DEFLATED, compresslevel=9) as package:
            package.write(executable, arcname=executable_name)
        with ZipFile(destination) as package:
            if package.namelist() != [executable_name]:
                raise ValueError(f"Unexpected ZIP contents: {destination}")
            if package.getinfo(executable_name).file_size != executable.stat().st_size:
                raise ValueError(f"Incorrect ZIP size: {destination}")
        archives.append(destination)
    return archives


if __name__ == "__main__":
    for archive in create_archives(Path("dist")):
        print(f"Created {archive}")
