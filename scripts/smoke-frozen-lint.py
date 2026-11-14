"""Exercise the frozen CLI's certificate, PKI lint, trust and database workflows."""

import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


def run_cli(*args: str) -> str:
    result = subprocess.run(
        ["dist/certscope-cli.exe", *args],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode:
        raise RuntimeError(f"CLI failed ({result.returncode}): {result.stderr}")
    return result.stdout


def main():
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "certscope-smoke")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
            .sign(key, hashes.SHA256()))

    with tempfile.TemporaryDirectory() as tmp:
        certificate = Path(tmp) / "certificate.pem"
        database = Path(tmp) / "certificates.sqlite3"
        certificate.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        assert run_cli("--version").strip().startswith("CertScope ")
        assert "--lint-profile" in run_cli("inspect", "--help")
        for profile in ("rfc5280", "cabf-tls"):
            result = json.loads(run_cli(
                "inspect", "--cert", str(certificate),
                "--lint-profile", profile, "--format", "json",
            ))
            lint = result["lint"]
            if lint["profile"] != profile or lint["status"] == "error":
                raise RuntimeError(f"Frozen PKILint failure for {profile}: {lint}")
            print(f"Frozen CLI PKILint {profile}: {lint['status']}")

        verified = json.loads(run_cli(
            "verify", "--cert", str(certificate), "--ca", str(certificate),
            "--format", "json",
        ))
        if verified["status"] != "trusted":
            raise RuntimeError(f"Frozen chain verification failed: {verified}")

        db = ("--db", str(database), "db")
        run_cli(*db, "add", "--type", "ca", "--name", "Test Root",
                "--file", str(certificate), "--trust")
        entries = json.loads(run_cli(*db, "list", "--format", "json"))
        if len(entries) != 1 or not entries[0]["trusted"]:
            raise RuntimeError(f"Frozen database roundtrip failed: {entries}")
        run_cli(*db, "trust", "--name", "Test Root", "--disable")
        run_cli(*db, "rename", "--type", "ca", "--name", "Test Root", "--to", "Renamed")
        run_cli(*db, "delete", "--type", "ca", "--name", "Renamed")
        if json.loads(run_cli(*db, "list", "--format", "json")):
            raise RuntimeError("Frozen database cleanup failed")
        print("Frozen CLI verification and SQLite workflows: passed")


if __name__ == "__main__":
    main()
