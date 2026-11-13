"""Human-readable and machine-readable X.509 metadata."""

from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, ed448, rsa

from certscope.parser import Certificate


def inspect_certificate(item: Certificate) -> dict:
    cert = item.value
    now = datetime.now(timezone.utc)
    key = cert.public_key()
    if isinstance(key, rsa.RSAPublicKey):
        public_key = f"RSA {key.key_size} bits"
    elif isinstance(key, ec.EllipticCurvePublicKey):
        public_key = f"EC {key.curve.name} ({key.key_size} bits)"
    elif isinstance(key, dsa.DSAPublicKey):
        public_key = f"DSA {key.key_size} bits"
    elif isinstance(key, ed25519.Ed25519PublicKey):
        public_key = "Ed25519"
    elif isinstance(key, ed448.Ed448PublicKey):
        public_key = "Ed448"
    else:
        public_key = key.__class__.__name__

    extensions = []
    for ext in cert.extensions:
        value = ext.value
        details = str(value)
        if isinstance(value, x509.UnrecognizedExtension):
            details = value.value.hex()
        extensions.append({
            "name": ext.oid._name or ext.oid.dotted_string,
            "oid": ext.oid.dotted_string,
            "critical": ext.critical,
            "value": details,
        })
    sans = {"dns": [], "ip": [], "uri": [], "email": []}
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        for typ, name in ((x509.DNSName, "dns"), (x509.IPAddress, "ip"),
                          (x509.UniformResourceIdentifier, "uri"),
                          (x509.RFC822Name, "email")):
            sans[name] = [str(v) for v in san.get_values_for_type(typ)]
    except x509.ExtensionNotFound:
        pass

    try:
        self_signed = cert.subject == cert.issuer
        if self_signed:
            cert.verify_directly_issued_by(cert)
    except (ValueError, TypeError, x509.InvalidVersion):
        self_signed = False
    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "subject_attributes": [{"oid": attr.oid.dotted_string, "name": attr.oid._name,
                                "value": str(attr.value)} for attr in cert.subject],
        "issuer_attributes": [{"oid": attr.oid.dotted_string, "name": attr.oid._name,
                               "value": str(attr.value)} for attr in cert.issuer],
        "version": cert.version.name,
        "serial_hex": format(cert.serial_number, "X"),
        "serial_decimal": str(cert.serial_number),
        "not_before": cert.not_valid_before_utc.isoformat(),
        "not_after": cert.not_valid_after_utc.isoformat(),
        "remaining_days": (cert.not_valid_after_utc - now).days,
        "valid_now": cert.not_valid_before_utc <= now <= cert.not_valid_after_utc,
        "self_issued": cert.subject == cert.issuer,
        "self_signed": self_signed,
        "is_ca": item.is_ca,
        "public_key": public_key,
        "signature_algorithm_oid": cert.signature_algorithm_oid.dotted_string,
        "signature_algorithm_name": cert.signature_algorithm_oid._name,
        "fingerprint_sha256": item.fingerprint,
        "fingerprint_sha1": cert.fingerprint(hashes.SHA1()).hex().upper(),
        "san": sans,
        "extensions": extensions,
        "pem": item.pem,
        "input_line": item.position,
    }
