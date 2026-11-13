"""CertScope application entry point."""

import sys


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    gui_command = not args or args[0] == "gui"
    single_input = len(args) == 1 and (not args[0].startswith("-") or "-----BEGIN CERTIFICATE-----" in args[0]) and args[0] not in (
        "inspect", "verify", "db"
    )
    if gui_command or single_input:
        from certscope.gui import run

        if gui_command and len(args) > 2:
            print("GUI mode accepts at most one certificate file, TLS URL or PEM string",
                  file=sys.stderr)
            return 2
        initial_input = (args[1] if len(args) == 2 else None) if gui_command else args[0]
        return run(initial_input)

    from certscope.cli import main as cli_main

    return cli_main(args)
