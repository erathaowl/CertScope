"""CertScope entry point with optional desktop GUI support."""

import sys
from importlib.util import find_spec


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    gui_command = not args or args[0] == "gui"
    single_input = (
        len(args) == 1
        and args[0] not in ("inspect", "verify", "db")
        and (
            not args[0].startswith("-")
            or "-----BEGIN CERTIFICATE-----" in args[0]
        )
    )

    if gui_command or single_input:
        if gui_command and len(args) > 2:
            print(
                "GUI mode accepts at most one certificate file, TLS URL or PEM string",
                file=sys.stderr,
            )
            return 2

        if find_spec("PySide6") is None or find_spec("yaml") is None:
            if not args:
                from certscope.cli import parser

                parser().print_help()
                return 0
            print(
                'GUI support is not installed. Install with: pip install "certscope[gui]"',
                file=sys.stderr,
            )
            return 2

        from certscope.gui import run

        initial_input = (args[1] if len(args) == 2 else None) if gui_command else args[0]
        return run(initial_input)

    from certscope.cli import main as cli_main

    return cli_main(args)
