import pytest

from certscope.parser import InputError, leaf_candidates, parse_bundle, unique


def test_parses_chain_and_selects_leaf(chain):
    parsed = parse_bundle(chain["intermediate"] + chain["leaf"])
    assert len(parsed) == 2
    assert leaf_candidates(parsed)[0].value.subject.rfc4514_string() == "CN=test.example"


def test_duplicate_is_removed_only_for_verification(chain):
    parsed = parse_bundle(chain["leaf"] * 2)
    assert len(parsed) == 2
    assert len(unique(parsed)) == 1


@pytest.mark.parametrize("data", ["", "random text", "-----BEGIN PRIVATE KEY-----\na\n-----END PRIVATE KEY-----",
                                 "-----BEGIN CERTIFICATE-----\nabc"])
def test_invalid_input_is_rejected(data):
    with pytest.raises(InputError):
        parse_bundle(data)


def test_der_conversion(chain):
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    cert = x509.load_pem_x509_certificate(chain["root"].encode())
    assert len(parse_bundle(cert.public_bytes(serialization.Encoding.DER), allow_der=True)) == 1
