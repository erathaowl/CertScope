"""Report Nuitka Windows size and startup against the v1.3.1 release."""

import argparse
import statistics
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

TARGETS = {
    "GUI": ("certscope-windows.zip", "certscope.exe"),
    "CLI": ("certscope-cli-windows.zip", "certscope-cli.exe"),
}


def archive_sizes(folder: Path) -> dict:
    sizes = {}
    for label, (archive_name, exe_name) in TARGETS.items():
        archive = folder / archive_name
        with ZipFile(archive) as package:
            assert package.namelist() == [exe_name]
            sizes[label] = (package.getinfo(exe_name).file_size, archive.stat().st_size)
    return sizes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--current-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    baseline = archive_sizes(args.baseline_dir)
    current = archive_sizes(args.current_dir)
    lines = [
        "## Nuitka versus PyInstaller release v1.3.1 (bytes)",
        "",
        "| Target | PyInstaller EXE | Nuitka EXE | EXE saved | PyInstaller ZIP | Nuitka ZIP | ZIP saved |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for label in TARGETS:
        old_exe, old_zip = baseline[label]
        new_exe, new_zip = current[label]
        lines.append(
            f"| {label} | {old_exe:,} | {new_exe:,} | "
            f"{old_exe - new_exe:,} ({(old_exe - new_exe) / old_exe:.1%}) | "
            f"{old_zip:,} | {new_zip:,} | "
            f"{old_zip - new_zip:,} ({(old_zip - new_zip) / old_zip:.1%}) |"
        )
        print(f"SIZE {label} baseline_exe={old_exe} baseline_zip={old_zip} "
              f"nuitka_exe={new_exe} nuitka_zip={new_zip}")

    with TemporaryDirectory() as temp:
        for label, folder in (("PyInstaller", args.baseline_dir), ("Nuitka", args.current_dir)):
            archive, executable = TARGETS["CLI"]
            output = Path(temp) / f"{label}-{executable}"
            with ZipFile(folder / archive) as package:
                output.write_bytes(package.read(executable))
            times = []
            for _ in range(3):
                started = time.perf_counter()
                result = subprocess.run(
                    [str(output), "--version"], capture_output=True, text=True,
                    check=True, timeout=60,
                )
                assert "1.3.1" in result.stdout
                times.append((time.perf_counter() - started) * 1000)
            median = statistics.median(times)
            print(f"STARTUP {label} CLI median_ms={median:.0f}")
            lines.append(f"\n{label} CLI warm startup median: {median:.0f} ms")

    summary = "\n".join(lines) + "\n"
    print(summary)
    if args.summary:
        with args.summary.open("a", encoding="utf-8") as file:
            file.write(summary)


if __name__ == "__main__":
    main()
