"""OpenSSL-backed path verification with independent trust sources."""

import ipaddress
from datetime import datetime, timezone

from OpenSSL import crypto
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509.verification import DNSName, IPAddress, PolicyBuilder, Store

from certscope.inspector import inspect_certificate
from certscope.parser import Certificate, leaf_candidates, parse_bundle, unique
from certscope.storage import Storage
from certscope.trust_stores import TrustSource, create_store, custom_source, database_source, system_source


class VerificationError(RuntimeError):
    pass


def _openssl_result(leaf: Certificate, others: list[Certificate], source: TrustSource) -> dict:
    """Keep the original error code/depth even if an additional hint is available."""
    row = {"source": source.name, "status": "failed", "error": None, "code": None,
           "depth": None, "certificate": None, "verified_chain": [], "anchor": None}
    if not source.anchors and not any(source.path_locations):
        row.update(status="skipped", error=source.error or "No enabled trust anchors")
        return row
    try:
        store = create_store(source)
        extra = unique(others + (source.intermediates or []))
        ctx = crypto.X509StoreContext(
            store, crypto.X509.from_cryptography(leaf.value),
            [crypto.X509.from_cryptography(item.value) for item in extra]
        )
        ctx.verify_certificate()
        verified = [c.to_cryptography() for c in ctx.get_verified_chain()]
        chain = [Certificate(c, c.public_bytes(serialization.Encoding.PEM).decode("ascii"), 0)
                 for c in verified]
        anchor = chain[-1]
        provided = {leaf.fingerprint, *(item.fingerprint for item in others)}
        verified_chain = []
        for certificate in chain:
            details = inspect_certificate(certificate)
            fingerprint = certificate.fingerprint
            if fingerprint == anchor.fingerprint:
                origin = source.name
            elif fingerprint in provided:
                origin = "input"
            else:
                origin = source.name
            details["origin"] = origin
            if fingerprint in source.names and source.name == "database":
                details["saved_name"] = source.names[fingerprint]
            verified_chain.append(details)
        row.update(status="passed", verified_chain=verified_chain,
                   anchor={**inspect_certificate(anchor), "saved_name": source.names.get(anchor.fingerprint),
                           "trust_source": source.name})
    except crypto.X509StoreContextError as exc:
        row["error"] = str(exc)
        errors = getattr(exc, "errors", [])
        if errors:
            # pyOpenSSL 25.x provides [code, depth, message].
            e = errors[0] if isinstance(errors[0], (tuple, list)) else errors
            if len(e) >= 3:
                row.update(code=e[0], depth=e[1], error=str(e[2]))
        failing = getattr(exc, "certificate", None)
        if failing is not None:
            value = failing.to_cryptography()
            row["certificate"] = {"subject": value.subject.rfc4514_string(),
                                  "fingerprint_sha256": value.fingerprint(
                                      hashes.SHA256()).hex().upper()}
    except (crypto.Error, OSError, RuntimeError, ValueError) as exc:
        row.update(status="unavailable", error=str(exc))
    if row["status"] == "failed":
        hints = []
        now = datetime.now(timezone.utc)
        for item in [leaf, *others]:
            cert = item.value
            if cert.not_valid_after_utc < now:
                hints.append(f"Expired: {cert.subject.rfc4514_string()} on {cert.not_valid_after_utc.isoformat()}")
            elif cert.not_valid_before_utc > now:
                hints.append(f"Not yet valid: {cert.subject.rfc4514_string()} until {cert.not_valid_before_utc.isoformat()}")
        if row["code"] in (2, 20, 21):
            hints.append("Issuer certificate may be missing or untrusted")
        row["diagnostic_hints"] = hints
    return row


def _tls_policy(chain: list[dict], purpose: str, hostname: str | None) -> dict:
    if purpose == "generic":
        return {"status": "not_checked", "message": "Generic chain validation"}
    if purpose == "tls-server" and not hostname:
        return {"status": "failed", "message": "A hostname or IP address is required"}
    try:
        certs = [x509.load_pem_x509_certificate(item["pem"].encode("ascii")) for item in chain]
        trust = Store([certs[-1]])
        builder = PolicyBuilder().store(trust)
        if purpose == "tls-server":
            try:
                subject = IPAddress(ipaddress.ip_address(hostname))
            except ValueError:
                subject = DNSName(hostname)
            verifier = builder.build_server_verifier(subject)
        else:
            verifier = builder.build_client_verifier()
        verifier.verify(certs[0], certs[1:-1])
        return {"status": "passed", "message": f"{purpose} identity and purpose validated"}
    except Exception as exc:
        return {"status": "failed", "message": str(exc)}


def verify_bundle(pem: str, storage: Storage, custom_ca: str | None = None,
                  purpose: str = "generic", hostname: str | None = None,
                  leaf_fingerprint: str | None = None,
                  sources: list[TrustSource] | None = None) -> dict:
    if purpose not in ("generic", "tls-server", "tls-client"):
        raise ValueError("Invalid verification purpose")
    if hostname and purpose != "tls-server":
        raise ValueError("Hostname requires tls-server purpose")
    certs = parse_bundle(pem)
    leafs = leaf_candidates(certs)
    if not leafs:
        raise ValueError("No leaf candidates found")
    if leaf_fingerprint:
        matches = [c for c in leafs if c.fingerprint == leaf_fingerprint]
        if not matches:
            raise ValueError("Selected leaf fingerprint is absent or not a leaf candidate")
        leaf = matches[0]
    elif len(leafs) > 1:
        raise ValueError("Multiple leaf candidates; select --leaf SHA256 fingerprint")
    else:
        leaf = leafs[0]

    attempts: list[dict] = []
    # Load each trust source only when reached, avoiding unnecessary parsing and
    # ensuring database/custom failures cannot preempt a successful system check.
    if sources is None:
        factories = [
            ("system", lambda: system_source(purpose)),
            ("database", lambda: database_source(storage)),
            ("custom", lambda: custom_source(custom_ca)),
        ]
    else:
        factories = [(source.name, lambda value=source: value) for source in sources]
    for name, load in factories:
        try:
            source = load()
            attempt = _openssl_result(
                leaf, [c for c in certs if c.fingerprint != leaf.fingerprint], source
            )
        except (OSError, ValueError, RuntimeError) as exc:
            attempt = {"source": name, "status": "unavailable", "error": str(exc),
                       "code": None, "depth": None, "certificate": None,
                       "verified_chain": [], "anchor": None}
        attempts.append(attempt)
        if attempt["status"] == "passed":
            break
    successful = next((a for a in attempts if a["status"] == "passed"), None)
    policy = _tls_policy(successful["verified_chain"], purpose, hostname) if successful else {
        "status": "not_checked", "message": "Chain has not been verified"}
    trusted = bool(successful and policy["status"] in ("passed", "not_checked"))
    return {
        "status": "trusted" if trusted else ("untrusted" if successful or
                  any(a["status"] == "failed" for a in attempts) else "unavailable"),
        "chain_status": "trusted" if successful else "untrusted",
        "purpose": purpose, "hostname": hostname,
        "identity_and_purpose": policy,
        "revocation": {"status": "not_checked", "message": "Offline mode: no CRL/OCSP requests"},
        "verification_time": datetime.now(timezone.utc).isoformat(),
        "leaf_fingerprint": leaf.fingerprint,
        "certificates": [inspect_certificate(c) for c in certs],
        "leaf_candidates": [c.fingerprint for c in leafs],
        "attempts": attempts,
        "trust_source": successful["source"] if successful else None,
        "trust_anchor": successful["anchor"] if successful else None,
        "verified_chain": successful["verified_chain"] if successful else [],
    }
