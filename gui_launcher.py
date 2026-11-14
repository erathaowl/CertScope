"""GUI-only entry point for the standalone Windows executable."""

import sys

from certscope.gui import run


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "gui":
        args = args[1:]
    if len(args) > 1:
        print("GUI mode accepts at most one certificate file, TLS URL or PEM string",
              file=sys.stderr)
        return 2
    return run(args[0] if args else None)


if __name__ == "__main__":
    raise SystemExit(main())
