"""Smoke-test the frozen Windows CLI with PKILint on an offline certificate."""

import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


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
        path = Path(tmp) / "certificate.pem"
        path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        for profile in ("rfc5280", "cabf-tls"):
            result = subprocess.run(
                ["dist/certscope-cli.exe", "inspect", "--cert", str(path),
                 "--lint-profile", profile, "--format", "json"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode:
                raise RuntimeError(result.stderr)
            lint = json.loads(result.stdout)["lint"]
            if lint["profile"] != profile or lint["status"] == "error":
                raise RuntimeError(f"Frozen lint failed for {profile}: {lint}")
            print(f"Frozen CLI PKILint {profile}: {lint['status']}")


if __name__ == "__main__":
    main()
