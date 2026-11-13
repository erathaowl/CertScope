"""CertScope: inspect and verify X.509 certificates offline."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("certscope")
except PackageNotFoundError:
    __version__ = "1.2.0"
