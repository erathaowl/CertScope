"""Identify a single startup argument as PEM text, a file or a TLS address."""

from pathlib import Path


CERTIFICATE_SUFFIXES = (".pem", ".crt", ".cer", ".der", ".chain", ".p7b", ".p7c")


def classify_input(value: str) -> tuple[str, str]:
    """Return (pem|file|url, payload) without accessing the network."""
    if not value.strip():
        raise ValueError("Certificate input cannot be empty")
    if "-----BEGIN CERTIFICATE-----" in value:
        return "pem", value
    if "://" in value:
        return "url", value

    path = Path(value).expanduser()
    try:
        if path.is_file():
            return "file", str(path)
    except (OSError, ValueError):
        pass

    if (
        "\n" in value
        or "\r" in value
        or any(char.isspace() for char in value)
        or value.lower().endswith(CERTIFICATE_SUFFIXES)
        or value.startswith(("/", ".", "~", "\\"))
        or "\\" in value
    ):
        raise ValueError(f"Input is not an existing certificate file or valid TLS target: {value[:120]}")
    return "url", value
