"""Vendor one fixed-width JetBrains Mono Nerd Font from the pinned v3.5.1 release."""

from io import BytesIO
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

FONT_URL = (
    "https://github.com/ryanoasis/nerd-fonts/releases/download/"
    "v3.5.1/JetBrainsMono.zip"
)
FONT_NAME = "JetBrainsMonoNerdFontMono-Regular.ttf"
DESTINATION = Path(__file__).resolve().parents[1] / "src" / "certscope" / "assets"


def main():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    target = DESTINATION / FONT_NAME
    license_target = DESTINATION / "OFL.txt"
    if target.is_file() and license_target.is_file():
        print(f"Bundled font already present: {target}")
        return

    with urlopen(FONT_URL, timeout=180) as response:
        archive = BytesIO(response.read())
    with ZipFile(archive) as fonts:
        candidates = {Path(name).name.lower(): name for name in fonts.namelist()}
        font_name = candidates.get(FONT_NAME.lower())
        license_name = next(
            (candidates[name] for name in ("ofl.txt", "license.txt", "license", "license.md")
             if name in candidates), None
        )
        if font_name is None or license_name is None:
            raise RuntimeError("The pinned archive is missing the mono font or its license")
        target.write_bytes(fonts.read(font_name))
        license_target.write_bytes(fonts.read(license_name))
    print(f"Installed {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
