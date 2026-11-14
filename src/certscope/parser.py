"""Bounded parsing of PEM certificate bundles."""

import base64
import hashlib
import re
from dataclasses import dataclass

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization

MAX_BYTES = 2 * 1024 * 1024
MAX_CERTIFICATES = 100
BEGIN = re.compile(rb"-----BEGIN ([A-Z0-9 _-]+)-----")


class InputError(ValueError):
    """Invalid or unsupported user-supplied certificate material."""


@dataclass(frozen=True)
class Certificate:
    value: x509.Certificate
    pem: str
    position: int
    raw_der: bytes | None = None

    @property
    def fingerprint(self) -> str:
        return self.value.fingerprint(hashes.SHA256()).hex().upper()

    @property
    def is_ca(self) -> bool:
        try:
            return self.value.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
        except x509.ExtensionNotFound:
            return False


def parse_bundle(data: str | bytes, *, allow_der: bool = False) -> list[Certificate]:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    if len(raw) > MAX_BYTES:
        raise InputError(f"Input exceeds the {MAX_BYTES} byte limit")
    if not raw.strip():
        raise InputError("No certificate data provided")
    if allow_der and b"-----BEGIN" not in raw:
        try:
            cert = x509.load_der_x509_certificate(raw)
            pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
            return [Certificate(cert, pem, 1, raw)]
        except ValueError as exc:
            raise InputError("Input is not a valid DER certificate") from exc

    certificates: list[Certificate] = []
    offset = 0
    while match := BEGIN.search(raw, offset):
        if raw[offset:match.start()].strip():
            raise InputError(f"Unexpected text before PEM block at byte {offset}")
        label = match.group(1)
        if label != b"CERTIFICATE":
            raise InputError(f"Unsupported PEM block '{label.decode('ascii')}' at byte {match.start()}")
        end = b"-----END CERTIFICATE-----"
        end_pos = raw.find(end, match.end())
        if end_pos == -1:
            raise InputError(f"Unterminated PEM certificate at byte {match.start()}")
        block_end = end_pos + len(end)
        block = raw[match.start():block_end]
        if BEGIN.search(block, match.end() - match.start()):
            raise InputError(f"Nested or malformed PEM certificate at byte {match.start()}")
        try:
            cert = x509.load_pem_x509_certificate(block)
        except ValueError as exc:
            raise InputError(f"Invalid PEM certificate at byte {match.start()}: {exc}") from exc
        der = base64.b64decode(re.sub(
            rb"\s+", b"", block[len(b"-----BEGIN CERTIFICATE-----"):-len(end)]
        ), validate=True)
        certificates.append(Certificate(
            cert, cert.public_bytes(serialization.Encoding.PEM).decode("ascii"),
            raw.count(b"\n", 0, match.start()) + 1, der,
        ))
        if len(certificates) > MAX_CERTIFICATES:
            raise InputError(f"Too many certificates (limit {MAX_CERTIFICATES})")
        offset = block_end
    if not certificates:
        raise InputError("No PEM CERTIFICATE blocks found")
    if raw[offset:].strip():
        raise InputError(f"Unexpected text after PEM block at byte {offset}")
    return certificates


def unique(certificates: list[Certificate]) -> list[Certificate]:
    return list({item.fingerprint: item for item in reversed(certificates)}.values())[::-1]


def leaf_candidates(certificates: list[Certificate]) -> list[Certificate]:
    """Find independent non-CA leafs; CA-only bundles remain inspectable."""
    unique_items = unique(certificates)
    non_ca = [cert for cert in unique_items if not cert.is_ca]
    return non_ca if non_ca else [cert for cert in unique_items if not any(
        other.value.issuer == cert.value.subject and other.fingerprint != cert.fingerprint
        for other in unique_items
    )]


def normalize_bundle(certificates: list[Certificate]) -> str:
    return "".join(c.pem for c in certificates)


def bundle_digest(pem: str) -> str:
    return hashlib.sha256(pem.encode("utf-8")).hexdigest()
