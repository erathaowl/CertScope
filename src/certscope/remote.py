"""Read the certificate chain presented during an untrusted TLS handshake."""

import socket
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RemoteCertificate:
    url: str
    hostname: str
    port: int
    pem: str


def parse_tls_target(value: str) -> tuple[str, int]:
    """Accept HTTPS/TLS URLs or bare host[:port], without making an HTTP request."""
    address = value.strip()
    if not address or any(char.isspace() for char in address):
        raise ValueError("Enter a valid HTTPS URL or host[:port]")
    target = address if "://" in address else f"https://{address}"
    parsed = urlsplit(target)
    if parsed.scheme.lower() not in ("https", "tls"):
        raise ValueError("Only HTTPS or TLS connections can provide a certificate")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Credentials are not permitted in the target URL")
    if not parsed.hostname:
        raise ValueError("The TLS target must contain a hostname or IP address")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("Invalid TLS port") from exc
    if not 1 <= port <= 65535:
        raise ValueError("TLS port must be between 1 and 65535")
    return parsed.hostname, port


def _untrusted_context() -> ssl.SSLContext:
    """Create a client context that allows retrieval of untrusted certificates."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def fetch_certificate(value: str, timeout: float = 8.0) -> RemoteCertificate:
    """Connect without verifying trust, returning the server's unverified chain.

    Does not issue an HTTP request or modify the system trust store. The chain is
    subsequently verified by CertScope's existing separate verification logic.
    """
    host, port = parse_tls_target(value)
    context = _untrusted_context()

    with socket.create_connection((host, port), timeout=timeout) as connection:
        with context.wrap_socket(connection, server_hostname=host) as tls:
            tls.settimeout(timeout)
            if hasattr(tls, "get_unverified_chain"):
                der_chain = tls.get_unverified_chain()
            else:
                der_chain = [tls.getpeercert(binary_form=True)]
    if not der_chain or not all(isinstance(cert, bytes) and cert for cert in der_chain):
        raise ValueError("The TLS server did not provide usable X.509 certificates")
    pem = "".join(ssl.DER_cert_to_PEM_cert(cert) for cert in der_chain)
    return RemoteCertificate(value.strip(), host, port, pem)
