"""Input classification and server certificate retrieval tests."""

import ssl

import pytest

from certscope.input_source import classify_input
from certscope.remote import _untrusted_context, fetch_certificate, parse_tls_target


@pytest.mark.parametrize(
    ("target", "host", "port"),
    [
        ("example.com", "example.com", 443),
        ("example.com:8443", "example.com", 8443),
        ("https://example.com/anything?query=yes", "example.com", 443),
        ("tls://localhost:9443", "localhost", 9443),
        ("https://[::1]:8443", "::1", 8443),
    ],
)
def test_tls_target(target, host, port):
    assert parse_tls_target(target) == (host, port)


@pytest.mark.parametrize("target", ["http://example.com", "https://user:pass@example.com", "ftp://host", "https://host:0"])
def test_tls_rejects_unsupported_target(target):
    with pytest.raises(ValueError):
        parse_tls_target(target)


def test_classify_startup_input(tmp_path):
    cert_file = tmp_path / "server.pem"
    cert_file.write_text("test", encoding="utf-8")
    assert classify_input(str(cert_file)) == ("file", str(cert_file))
    assert classify_input("https://example.com") == ("url", "https://example.com")
    assert classify_input("server.local:443") == ("url", "server.local:443")
    pem = "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"
    assert classify_input(pem) == ("pem", pem)
    with pytest.raises(ValueError):
        classify_input(str(tmp_path / "missing.pem"))


def test_untrusted_ssl_context():
    context = _untrusted_context()
    assert context.check_hostname is False
    assert context.verify_mode == ssl.CERT_NONE


def test_fetch_disables_validation_and_preserves_chain(monkeypatch):
    raw = bytes.fromhex("3003020101")
    another = bytes.fromhex("3003020102")
    calls = {}

    class Socket:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class TLS(Socket):
        def settimeout(self, seconds):
            calls["timeout"] = seconds

        def get_unverified_chain(self):
            return [raw, another]

    class Context:
        check_hostname = False
        verify_mode = ssl.CERT_NONE

        def wrap_socket(self, sock, server_hostname):
            calls["sni"] = server_hostname
            assert self.check_hostname is False
            assert self.verify_mode == ssl.CERT_NONE
            return TLS()

    monkeypatch.setattr("certscope.remote._untrusted_context", lambda: Context())
    monkeypatch.setattr("certscope.remote.socket.create_connection",
                        lambda target, timeout: calls.update(target=target) or Socket())
    response = fetch_certificate("https://example.com:9443/path", timeout=5)
    assert calls["target"] == ("example.com", 9443)
    assert calls["sni"] == "example.com"
    assert calls["timeout"] == 5
    assert response.pem == (
        ssl.DER_cert_to_PEM_cert(raw) + ssl.DER_cert_to_PEM_cert(another)
    )


def test_entrypoint_routes_single_input_to_gui(monkeypatch):
    from certscope.main import main

    received = []
    from certscope import gui

    monkeypatch.setattr(gui, "run",
                        lambda initial_input=None: received.append(initial_input) or 0)
    assert main(["server.pem"]) == 0
    assert main(["https://example.com:443"]) == 0
    assert main(["-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----"]) == 0
    assert main(["gui", "localhost:443"]) == 0
    assert received == [
        "server.pem",
        "https://example.com:443",
        "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----",
        "localhost:443",
    ]
