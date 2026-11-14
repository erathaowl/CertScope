"""PKILint integration tests using real offline X.509 test certificates."""

import base64

from cryptography.hazmat.primitives import serialization

from certscope.linting import SEVERITIES, lint_bundle
from certscope.parser import parse_bundle


def test_lint_rfc5280_chain(chain):
    certificates = parse_bundle(chain["chain"])
    result = lint_bundle(certificates)
    assert result["engine"] == "PKILint"
    assert result["profile"] == "rfc5280"
    assert result["status"] != "error"
    assert len(result["certificates"]) == 2
    assert set(result["summary"]) == set(SEVERITIES)
    for item, entry in zip(certificates, result["certificates"]):
        assert entry["fingerprint_sha256"] == item.fingerprint
        assert entry["status"] != "error"
        assert all({"severity", "code", "message", "validator", "node_path"} <=
                   finding.keys() for finding in entry["findings"])
    assert sum(result["summary"].values()) == sum(
        len(entry["findings"]) for entry in result["certificates"]
    )


def test_lint_cabf_tls(chain):
    result = lint_bundle(parse_bundle(chain["leaf"]), "cabf-tls")
    assert result["profile"] == "cabf-tls"
    assert result["status"] != "error"
    assert len(result["certificates"]) == 1
    assert "certificate_type" in result["certificates"][0]


def test_original_der_is_preserved(chain):
    pem = chain["leaf"]
    original_der = base64.b64decode("".join(pem.splitlines()[1:-1]))
    item = parse_bundle(pem)[0]
    assert item.raw_der == original_der
    assert parse_bundle(original_der, allow_der=True)[0].raw_der == original_der
    assert item.value.public_bytes(serialization.Encoding.DER) == original_der


def test_invalid_lint_profile(chain):
    import pytest

    with pytest.raises(ValueError, match="Unsupported lint profile"):
        lint_bundle(parse_bundle(chain["leaf"]), "unknown")
