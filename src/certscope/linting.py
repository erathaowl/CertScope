"""Offline X.509 compliance linting using PKILint's native Python API."""

from cryptography.hazmat.primitives.serialization import Encoding
from pkilint import finding_filter, loader
from pkilint.cabf import serverauth
from pkilint.pkix import certificate, extension, name
from pkilint.validation import ValidationFindingSeverity

from certscope.parser import Certificate

PROFILES = ("rfc5280", "cabf-tls")
SEVERITIES = ("FATAL", "ERROR", "WARNING", "NOTICE", "INFO")


def _validator(profile, document):
    if profile == "rfc5280":
        decoding = certificate.create_decoding_validators(
            name.ATTRIBUTE_TYPE_MAPPINGS, extension.EXTENSION_MAPPINGS
        )
        validators = [
            certificate.create_issuer_validator_container([]),
            certificate.create_validity_validator_container(),
            certificate.create_subject_validator_container([]),
            certificate.create_extensions_validator_container([]),
            certificate.create_spki_validator_container([]),
        ]
        return certificate.create_pkix_certificate_validator_container(
            decoding, validators
        ), None

    certificate_type = serverauth.determine_certificate_type(document)
    validator = certificate.create_pkix_certificate_validator_container(
        serverauth.create_decoding_validators(),
        serverauth.create_validators(certificate_type),
    )
    return validator, certificate_type


def _status(counts, errors=False):
    if errors:
        return "error"
    return "findings" if any(counts[key] for key in ("FATAL", "ERROR", "WARNING")) else "passed"


def lint_bundle(certificates: list[Certificate], profile: str = "rfc5280") -> dict:
    """Lint each provided certificate, keeping findings separate from trust decisions."""
    if profile not in PROFILES:
        raise ValueError(f"Unsupported lint profile: {profile}")

    totals = dict.fromkeys(SEVERITIES, 0)
    entries = []
    has_errors = False
    for item in certificates:
        counts = dict.fromkeys(SEVERITIES, 0)
        entry = {
            "subject": item.value.subject.rfc4514_string(),
            "fingerprint_sha256": item.fingerprint,
            "findings": [],
            "summary": counts,
        }
        try:
            raw_der = item.raw_der or item.value.public_bytes(Encoding.DER)
            document = loader.load_der_certificate(raw_der)
            validator, certificate_type = _validator(profile, document)
            results = validator.validate(document.root)
            if certificate_type is not None:
                entry["certificate_type"] = str(certificate_type.to_option_str)
                results, _ = finding_filter.filter_results(
                    serverauth.create_serverauth_finding_filters(certificate_type),
                    results,
                )
            for result in results:
                for description in result.finding_descriptions:
                    finding = description.finding
                    if finding.severity > ValidationFindingSeverity.INFO:
                        continue
                    severity = finding.severity.name
                    entry["findings"].append({
                        "severity": severity,
                        "code": finding.code,
                        "message": description.message,
                        "validator": str(result.validator),
                        "node_path": result.node.path,
                    })
                    counts[severity] += 1
                    totals[severity] += 1
        except Exception as exc:
            entry["error"] = str(exc)
            has_errors = True
        entry["status"] = _status(counts, "error" in entry)
        entries.append(entry)

    return {
        "engine": "PKILint",
        "profile": profile,
        "status": _status(totals, has_errors),
        "summary": totals,
        "certificates": entries,
    }
