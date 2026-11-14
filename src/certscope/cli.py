"""Headless command-line interface for certificate inspection and verification."""

import argparse
import json
import sys
from pathlib import Path

from certscope import __version__
from certscope.app_info import APP_LICENSE, APP_NAME, APP_URL
from certscope.inspector import inspect_certificate
from certscope.linting import lint_bundle
from certscope.parser import InputError, leaf_candidates, parse_bundle
from certscope.reporting import render
from certscope.storage import Storage
from certscope.verification import verify_bundle


def _read(path: str) -> str:
    raw = sys.stdin.buffer.read() if path == "-" else Path(path).read_bytes()
    if b"-----BEGIN" not in raw:
        return "".join(cert.pem for cert in parse_bundle(raw, allow_der=True))
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputError(f"File must contain UTF-8 PEM certificates: {path}") from exc


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="certscope",
        description=f"{APP_NAME} - {__version__} ({APP_LICENSE})",
        epilog=APP_URL,
    )
    p.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    p.add_argument("--db", metavar="PATH", help="Custom SQLite database path")
    commands = p.add_subparsers(dest="command", required=True)

    for operation in ("inspect", "verify"):
        sub = commands.add_parser(operation, help=f"{operation.title()} a certificate or PEM chain")
        inputs = sub.add_mutually_exclusive_group(required=True)
        inputs.add_argument("--cert", metavar="FILE", help="PEM/DER certificate, chain, or - for stdin")
        inputs.add_argument("--entry", metavar="NAME", help="Saved certificate name")
        sub.add_argument("--format", choices=("text", "json"), default="text")
        sub.add_argument("--lint", action="store_true", help="Run RFC 5280 compliance linting")
        sub.add_argument("--lint-profile", choices=("rfc5280", "cabf-tls"),
                         help="Lint profile (also enables linting)")
        if operation == "verify":
            sub.add_argument("--ca", metavar="FILE", help="Temporary custom CA bundle or - for stdin")
            sub.add_argument("--purpose", choices=("generic", "tls-server", "tls-client"), default="generic")
            sub.add_argument("--hostname", help="DNS name or IP for tls-server verification")
            sub.add_argument("--leaf", help="SHA-256 fingerprint of the leaf to verify")

    db = commands.add_parser("db", help="Manage named local certificates and CA bundles")
    sub = db.add_subparsers(dest="db_command", required=True)
    list_cmd = sub.add_parser("list", help="List stored entries")
    list_cmd.add_argument("--type", choices=("certificate", "ca"))
    list_cmd.add_argument("--format", choices=("text", "json"), default="text")
    for action in ("add", "show", "rename", "delete", "trust"):
        cmd = sub.add_parser(action)
        if action != "trust":
            cmd.add_argument("--type", choices=("certificate", "ca"), required=True)
        cmd.add_argument("--name", required=True)
        if action == "add":
            cmd.add_argument("--file", required=True)
            cmd.add_argument("--trust", action="store_true", help="Explicitly trust this CA as an anchor")
            cmd.add_argument("--replace", action="store_true")
        if action == "show":
            cmd.add_argument("--format", choices=("text", "json", "pem"), default="text")
        if action == "rename":
            cmd.add_argument("--to", required=True)
        if action == "trust":
            toggles = cmd.add_mutually_exclusive_group(required=True)
            toggles.add_argument("--enable", action="store_true")
            toggles.add_argument("--disable", action="store_true")
    return p


def _entry_data(entry) -> dict:
    return {"name": entry.name, "type": entry.kind, "trusted": entry.trusted,
            "enabled": entry.enabled, "sha256": entry.bundle_sha256,
            "created_at": entry.created_at, "updated_at": entry.updated_at}


def _database(args, storage: Storage) -> int:
    operation = args.db_command
    if operation == "list":
        entries = [_entry_data(e) for e in storage.list(args.type)]
        if args.format == "json":
            print(json.dumps(entries, indent=2))
        else:
            for entry in entries:
                print(f"{entry['type']:12} {entry['name']} (trusted={entry['trusted']}, enabled={entry['enabled']})")
        return 0
    if operation == "add":
        if args.trust and args.type != "ca":
            raise InputError("Only CA entries may be trusted")
        storage.save(args.type, args.name, _read(args.file), trusted=args.trust, replace=args.replace)
    elif operation == "show":
        item = storage.get(args.type, args.name)
        if args.format == "pem":
            print(item.pem_bundle, end="")
        elif args.format == "json":
            print(json.dumps({**_entry_data(item), "pem_bundle": item.pem_bundle}, indent=2))
        else:
            print(json.dumps(_entry_data(item), indent=2))
    elif operation == "rename":
        storage.rename(args.type, args.name, args.to)
    elif operation == "trust":
        storage.trust(args.name, args.enable)
    elif operation == "delete":
        storage.delete(args.type, args.name)
    if operation != "show":
        print("OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    output_format = getattr(args, "format", "text")
    try:
        if args.command == "verify":
            if args.hostname and args.purpose != "tls-server":
                raise InputError("--hostname requires --purpose tls-server")
            if args.purpose == "tls-server" and not args.hostname:
                raise InputError("TLS server verification requires --hostname")
            if args.ca == "-" and args.cert == "-":
                raise InputError("Certificate and custom CA cannot both read from stdin")
        storage = Storage(args.db)
        if args.command == "db":
            return _database(args, storage)
        pem = _read(args.cert) if args.cert else storage.get("certificate", args.entry).pem_bundle
        certs = parse_bundle(pem)
        if args.command == "inspect":
            result = {"status": "inspected", "certificates": [inspect_certificate(c) for c in certs],
                      "leaf_candidates": [c.fingerprint for c in leaf_candidates(certs)]}
            if args.lint or args.lint_profile:
                result["lint"] = lint_bundle(certs, args.lint_profile or "rfc5280")
            print(render(result, args.format))
            return 0
        ca = _read(args.ca) if args.ca else None
        result = verify_bundle(pem, storage, ca, args.purpose, args.hostname, args.leaf)
        if args.lint or args.lint_profile:
            result["lint"] = lint_bundle(parse_bundle(pem), args.lint_profile or "rfc5280")
        print(render(result, args.format))
        return 0 if result["status"] == "trusted" else (3 if result["status"] == "unavailable" else 1)
    except (InputError, ValueError, KeyError, UnicodeError) as exc:
        message = str(exc)
        if output_format == "json":
            print(json.dumps({"status": "invalid_input", "error": message}))
        else:
            print(f"Error: {message}", file=sys.stderr)
        return 2
    except (OSError, RuntimeError, __import__("sqlite3").DatabaseError) as exc:
        message = str(exc)
        if output_format == "json":
            print(json.dumps({"status": "error", "error": message}))
        else:
            print(f"Runtime error: {message}", file=sys.stderr)
        return 3
