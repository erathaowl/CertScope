"""Shared report rendering for desktop GUI and CLI."""

import json


def render(result: dict, fmt: str = "text") -> str:
    if fmt == "json":
        return json.dumps(result, indent=2, ensure_ascii=False)
    lines = [f"Status: {result['status']}"]
    if "chain_status" in result:
        lines += [f"Chain: {result['chain_status']}", f"Purpose: {result['purpose']}",
                  f"Identity/purpose: {result['identity_and_purpose']['status']}",
                  f"Revocation: {result['revocation']['status']}",
                  f"Time: {result['verification_time']}"]
        for item in result.get("attempts", []):
            error = f" - {item['error']}" if item.get("error") else ""
            context = f" (OpenSSL {item['code']}, depth {item['depth']})" if item.get("code") is not None else ""
            lines.append(f"{item['source']}: {item['status']}{context}{error}")
        if result.get("trust_anchor"):
            anchor = result["trust_anchor"]
            lines.extend((f"Trust anchor: {anchor['subject']}",
                          f"Trust anchor SHA256: {anchor['fingerprint_sha256']}"))
        if result["identity_and_purpose"]["status"] == "failed":
            lines.append(f"Identity/purpose error: {result['identity_and_purpose']['message']}")
    for n, cert in enumerate(result.get("certificates", []), 1):
        lines.extend((f"", f"Certificate {n}: {cert['subject']}", f"  Issuer: {cert['issuer']}",
                      f"  SHA256: {cert['fingerprint_sha256']}",
                      f"  Expires: {cert['not_after']}", f"  Public key: {cert['public_key']}"))
    return "\n".join(lines)
