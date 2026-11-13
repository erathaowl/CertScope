"""Isolated system and user trust anchors; never trust inspected input certificates."""

import ssl
import sys
from dataclasses import dataclass

from OpenSSL import crypto
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from certscope.parser import Certificate, parse_bundle
from certscope.storage import Storage


@dataclass
class TrustSource:
    name: str
    anchors: list[Certificate]
    names: dict[str, str]
    path_locations: tuple[str | None, str | None] = (None, None)
    intermediates: list[Certificate] | None = None
    error: str | None = None


def system_source(purpose: str = "generic") -> TrustSource:
    """Read current OS trust; exported anchors do not fully emulate Windows chain policy."""
    items: list[Certificate] = []
    helpers: list[Certificate] = []
    paths: tuple[str | None, str | None] = (None, None)
    errors: list[str] = []
    if sys.platform == "win32":
        required_oid = {"tls-server": "1.3.6.1.5.5.7.3.1",
                        "tls-client": "1.3.6.1.5.5.7.3.2"}.get(purpose)
        for store_name, dest in (("ROOT", items), ("CA", helpers)):
            try:
                for raw, encoding, trust in ssl.enum_certificates(store_name):
                    if encoding != "x509_asn" or (required_oid and trust is not True and required_oid not in trust):
                        continue
                    cert = x509.load_der_x509_certificate(raw)
                    pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
                    dest.append(Certificate(cert, pem, 0))
            except (OSError, ValueError) as exc:
                errors.append(f"Windows {store_name} store: {exc}")
    else:
        p = ssl.get_default_verify_paths()
        paths = (p.cafile, p.capath)
        try:
            context = ssl.create_default_context()
            for raw in context.get_ca_certs(binary_form=True):
                cert = x509.load_der_x509_certificate(raw)
                pem = cert.public_bytes(serialization.Encoding.PEM).decode("ascii")
                items.append(Certificate(cert, pem, 0))
        except (OSError, ssl.SSLError, ValueError) as exc:
            errors.append(str(exc))
    # Exported OS anchors are loaded directly. Avoid adding the same CA twice
    # from both the effective SSL default store and OpenSSL's CA file.
    if items:
        paths = (None, None)
    return TrustSource("system", items, {}, paths, helpers, "; ".join(errors) or None)


def database_source(storage: Storage) -> TrustSource:
    items: list[Certificate] = []
    names: dict[str, str] = {}
    for entry in storage.list("ca"):
        if not (entry.enabled and entry.trusted):
            continue
        for item in parse_bundle(entry.pem_bundle):
            items.append(item)
            names[item.fingerprint] = entry.name
    return TrustSource("database", items, names)


def custom_source(pem: str | None) -> TrustSource:
    if not pem or not pem.strip():
        return TrustSource("custom", [], {})
    certs = parse_bundle(pem)
    if any(not item.is_ca for item in certs):
        raise ValueError("The custom trust store may contain only CA:TRUE certificates")
    return TrustSource("custom", certs, {item.fingerprint: "Temporary custom CA" for item in certs})


def create_store(source: TrustSource) -> crypto.X509Store:
    store = crypto.X509Store()
    cafile, capath = source.path_locations
    if cafile or capath:
        store.load_locations(cafile, capath)
    known = set()
    for item in source.anchors:
        if item.fingerprint in known:
            continue
        known.add(item.fingerprint)
        try:
            store.add_cert(crypto.X509.from_cryptography(item.value))
        except crypto.Error as exc:
            raise RuntimeError(f"Unable to load trust anchor {item.fingerprint}: {exc}") from exc
    return store
