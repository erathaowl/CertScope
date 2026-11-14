"""Measure Windows onefile sizes and inspect PyInstaller archive contents."""

import argparse
import statistics
import subprocess
import time
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

ARCHIVES = {
    "GUI": ("certscope-windows.zip", "certscope.exe"),
    "CLI": ("certscope-cli-windows.zip", "certscope-cli.exe"),
}


def mb(size: int) -> str:
    return f"{size / 1024 / 1024:.2f}"


def metrics(folder: Path) -> dict:
    sizes = {}
    for label, (archive_name, exe_name) in ARCHIVES.items():
        archive_path = folder / archive_name
        with ZipFile(archive_path) as archive:
            if archive.namelist() != [exe_name]:
                raise ValueError(f"Unexpected contents in {archive_path}")
            exe_size = archive.getinfo(exe_name).file_size
        sizes[label] = {"exe": exe_size, "zip": archive_path.stat().st_size}
    return sizes


def analyze(exe: Path) -> list[tuple[str, int]]:
    """Group compressed PyInstaller CArchive entries by their top-level path."""
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(exe))
    components = Counter()
    for name, data in reader.toc.items():
        compressed = data[1]
        normalized = name.replace("\\", "/")
        group = normalized.split("/", maxsplit=1)[0]
        if group.lower().startswith("qt6"):
            group = "Qt shared libraries"
        elif group.startswith("PySide6"):
            group = "PySide6"
        elif group.startswith("pkilint"):
            group = "PKILint"
        elif group.startswith("pyasn1"):
            group = "ASN.1"
        components[group] += compressed
    return components.most_common(18)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--current-dir", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    old = metrics(args.baseline_dir)
    new = metrics(args.current_dir) if args.current_dir else None
    lines = [
        "## Windows executable sizes (MiB)",
        "",
        "| Executable | v1.3.0 EXE | v1.3.0 ZIP | Current EXE | Current ZIP | Saved EXE | Saved ZIP |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label in ARCHIVES:
        a = old[label]
        b = new[label] if new else a
        percent = 100 * (a["exe"] - b["exe"]) / a["exe"]
        lines.append(
            f"| {label} | {mb(a['exe'])} | {mb(a['zip'])} | "
            f"{mb(b['exe'])} | {mb(b['zip'])} | "
            f"{mb(a['exe'] - b['exe'])} ({percent:.1f}%) | "
            f"{mb(a['zip'] - b['zip'])} ({100 * (a['zip'] - b['zip']) / a['zip']:.1f}%) |"
        )
        print(f"SIZE {label} baseline_exe={a['exe']} baseline_zip={a['zip']} "
              f"current_exe={b['exe']} current_zip={b['zip']}")

    with TemporaryDirectory() as temp:
        for title, source in (("Baseline", args.baseline_dir), ("Current", args.current_dir)):
            if source is None:
                continue
            for label, (archive_name, exe_name) in ARCHIVES.items():
                destination = Path(temp) / f"{title.lower()}-{exe_name}"
                with ZipFile(source / archive_name) as archive:
                    with destination.open("wb") as output:
                        output.write(archive.read(exe_name))
                parts = analyze(destination)
                print(f"ARCHIVE {title} {label}: {parts}")
                lines.extend([
                    "",
                    f"### {title} {label} archive entries (compressed)",
                    "",
                    "| Component | MiB |",
                    "|---|---:|",
                    *(f"| {name} | {mb(size)} |" for name, size in parts),
                ])

    report = "\n".join(lines) + "\n"
    print(report)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as output:
            output.write(report)


if __name__ == "__main__":
    main()
