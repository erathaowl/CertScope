from certscope.inspector import inspect_certificate
from certscope.parser import parse_bundle


def test_inspection_contains_extensions_and_san(chain):
    record = inspect_certificate(parse_bundle(chain["leaf"])[0])
    assert record["san"]["dns"] == ["test.example"]
    assert record["issuer"].startswith("CN=Test Intermediate")
    assert record["fingerprint_sha256"]
    assert record["extensions"]
    assert "BEGIN CERTIFICATE" in record["pem"]
