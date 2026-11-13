"""CertScope application entry point."""

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if not args or args[0] == "gui":
        from certscope.gui import run

        if args and len(args) > 1:
            print("GUI mode takes no arguments", file=sys.stderr)
            return 2
        return run()

    from certscope.cli import main as cli_main

    return cli_main(args)
