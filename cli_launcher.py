"""Headless entry point for the standalone Windows command-line executable."""

from certscope.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
