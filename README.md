# CertScope

[Italiano](README.it.md)

CertScope is an offline X.509 certificate inspector and verifier. It accepts PEM bundles or single DER certificates, displays certificate metadata, verifies chains against isolated trust stores in order, and keeps named certificates and explicitly trusted CA certificates in a local SQLite database.

## Requirements

- Python 3.14 or newer
- `uv` for dependency management
- Windows or Linux (Qt for GUI)

## Install and launch

```bash
uv python install 3.14
uv sync
uv run certscope
```

Opening without arguments starts the GUI. Paste a certificate or concatenated chain in the left editor, optionally paste a custom CA in the right editor, select a validation purpose and click **Analyze and verify**. Choose certificates in the tree to view their attributes or PEM. The result tabs show the validated chain and error diagnostics. Use **Saved entries** to load, rename, delete or change the trust status of local entries. New CA entries require explicit trust approval.

## CLI examples

```bash
uv run certscope inspect --cert server.pem --format json
uv run certscope verify --cert server-chain.pem
uv run certscope verify --cert server-chain.pem --ca private-root.pem --format json
uv run certscope verify --cert server-chain.pem --purpose tls-server --hostname example.com
uv run certscope db add --type certificate --name MyServer --file server-chain.pem
uv run certscope db add --type ca --name OfficeRoot --file root.pem --trust
uv run certscope db list
uv run certscope db trust --name OfficeRoot --disable
uv run certscope db show --type ca --name OfficeRoot --format pem
uv run certscope --db ./local.sqlite3 verify --entry MyServer
```

Use `-` for standard input on one file argument. A `--leaf` SHA-256 fingerprint selects one of several independent leaf certificates. Exit codes: 0 verified (or inspection/DB success), 1 untrusted, 2 invalid input, 3 runtime error. For script use, select `--format json`.

## Verification and security

Trust checks run sequentially in isolated stores: **system CA certificates → trusted and enabled SQLite CAs → temporarily supplied custom CAs**. A successful check stops the sequence and reports its trust source, complete verified path, and anchor details. Certificate bundles provided for inspection are only untrusted path candidates. Saving a certificate does not make it trusted. Only explicitly trusted, enabled CA records participate in the database stage.

`generic` checks certificate path validity, signatures, validity periods and X.509 constraints. `tls-server` additionally requires `--hostname` and checks TLS server identity and purpose, using cryptography's verifier. `tls-client` checks client authentication policy. All checks run without network access. **Revocation status is not checked**: no OCSP, CRL or AIA requests are made. Linux trust is taken from available OpenSSL/Python system CA material; Windows trust certificates are exported from native ROOT store for OpenSSL validation. This **does not replicate every Windows CryptoAPI trust or distrust rule**. The certificate path verification backend currently uses pyOpenSSL's deprecated crypto API behind a replaceable module boundary.

The application stores public certificates and CA PEM only. Private keys are rejected and are not saved. A 2 MiB, 100-certificate limit applies to PEM input. SQLite data is written under your per-user application directory (override with `--db` on CLI). Do not load unknown roots into trusted local storage.

## Test

```bash
uv run pytest -q
uv run ruff check .
```

## Build Windows single-file EXE

Run on Windows (cross-compilation from Linux is not supported):

```powershell
uv sync --group dev
uv run pyinstaller --noconfirm --clean certscope.spec
.\dist\CertScope.exe --help
.\dist\CertScope.exe verify --cert .\server-chain.pem --format json
```

A Windows GitHub Actions workflow builds and uploads the EXE artifact. The bundled executable is console-capable for stdout, stderr and exit codes. A console window may appear when launched by double click, depending on the PyInstaller and Windows version.

## License and redistribution

MIT licensed project code. Packaged PySide6/Qt and other dependencies retain their respective licenses and redistribution requirements. Review the bundled Qt license notices before distributing binaries.
