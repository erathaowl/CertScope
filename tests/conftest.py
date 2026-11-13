"""Generate offline X.509 chains for repeatable tests."""

from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


@pytest.fixture
def chain():
    now = datetime.now(timezone.utc)

    def key():
        return rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def name(common_name):
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])

    root_key, intermediate_key, leaf_key = key(), key(), key()

    def issue(subject, issuer, public_key, issuer_key, *, ca, expires=30, san=None):
        builder = (x509.CertificateBuilder()
                   .subject_name(name(subject)).issuer_name(name(issuer))
                   .public_key(public_key).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(days=1))
                   .not_valid_after(now + timedelta(days=expires))
                   .add_extension(x509.BasicConstraints(ca=ca, path_length=1 if ca else None), True)
                   .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                       key_encipherment=not ca, data_encipherment=False, key_agreement=False,
                       key_cert_sign=ca, crl_sign=ca, encipher_only=False, decipher_only=False), True)
                   .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), False))
        if san:
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(san)]), False)
            builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), False)
        return builder.sign(issuer_key, hashes.SHA256())

    root = issue("CertScope Test Root", "CertScope Test Root", root_key.public_key(), root_key, ca=True)
    intermediate = issue("Test Intermediate", "CertScope Test Root", intermediate_key.public_key(), root_key, ca=True)
    leaf = issue("test.example", "Test Intermediate", leaf_key.public_key(), intermediate_key,
                 ca=False, san="test.example")
    expired = issue("expired.example", "Test Intermediate", leaf_key.public_key(), intermediate_key,
                    ca=False, expires=-1, san="expired.example")

    def pem(certificate):
        return certificate.public_bytes(serialization.Encoding.PEM).decode("ascii")

    return {"root": pem(root), "intermediate": pem(intermediate), "leaf": pem(leaf),
            "expired": pem(expired), "chain": pem(leaf) + pem(intermediate),
            "root_cert": root, "leaf_cert": leaf}
