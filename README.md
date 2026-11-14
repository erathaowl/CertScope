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
.\dist\certscope-cli.exe --help
.\dist\certscope-cli.exe verify --cert .\server-chain.pem --format json
```

A Windows GitHub Actions workflow builds and uploads the EXE artifact. The workflow produces two independent single-file executables: **certscope.exe** is a windowed GUI without a background console; **certscope-cli.exe** provides stdout, stderr and exit codes for headless terminal use. This separation avoids Windows GUI-subsystem limitations when redirecting console output.

## License and redistribution

Licensed under the [MIT License](LICENSE). Packaged PySide6/Qt and other dependencies retain their respective licenses and redistribution requirements. Review the bundled Qt license notices before distributing binaries.

## Appearance

Choose **Settings** to configure a monospace font, font size (8–32 pt), and light/dark/system-auto appearance. Preferences persist in the local SQLite database. Input PEM and structured output use a shared syntax-highlighted Qt editor; **Tree** and **JSON** modes are available for certificate details, verification diagnostics and validated paths. The default font is JetBrains Mono Nerd Font Mono v3.5.1 (see `scripts/vendor-font.py` and bundled license).

The structured tree supports cell selection, Ctrl+C (field or value according to the selected column), and right-click actions **Copy field**, **Copy value**, and **Copy element**. Copying a value uses the complete source data, including text truncated on screen. The Tree/JSON selection is restored from SQLite on startup. Both color themes explicitly style buttons, menus, and the subtle alternate tree rows.

## Fetch a certificate from a TLS server

Enter `https://example.com:443`, `tls://host:8443` or `host:port` into the **TLS URL** field and press **Fetch and analyze**. CertScope establishes a TLS connection **without validating the server during retrieval**, extracts the presented unverified certificate chain (on supported Python/OpenSSL builds) and immediately runs normal verification against system, trusted SQLite and custom CAs. The hostname is populated automatically and the TLS-server purpose checks identity. The connection does not send an HTTP request or download the page. Certificate retrieval has an eight-second timeout, and the UI remains responsive.

A vertical splitter below the certificate and custom-CA editors lets you resize the input area and the inspection results independently.

To launch the GUI with automatic analysis from one parameter:

```powershell
.\dist\certscope.exe .\server.pem
.\dist\certscope.exe https://example.com:443
.\dist\certscope.exe '-----BEGIN CERTIFICATE-----...'
```

The same behavior is available with `uv run certscope <input>` or `uv run certscope gui <input>`. PEM strings must be passed as one quoted argument, including actual line breaks. The explicit CLI commands (`inspect`, `verify`, `db`) remain unchanged.

The verification status bar now shows a green/red indicator. Verified path entries from system trust or trusted SQLite CAs use distinct theme-aware colors; database CA names appear before the subject in square brackets. The Settings dialog can open the database directory. Both PEM input editors have **Save as** to write their contents to a file. Structured tree summaries are dimmed and italic; strings, numbers, booleans and null values use the matching JSON syntax-highlighter colors.

## Release artifacts

GitHub releases include `certscope-windows.zip` (containing `certscope.exe`) and `certscope-cli-windows.zip` (containing `certscope-cli.exe`), an explicit `CertScope-vX.Y.Z-source.zip` archive containing the **unchanged Git tag**, and a versioned `certscope-X.Y.Z-py3-none-any.whl` Python wheel built from that tag. The historical tagged `pyproject.toml` declared version `0.1.0`; the release workflow updates only the temporary build checkout's package metadata to match the tag, after archiving the original sources. No historical tag is changed.

The project maintains three workflows: [Test and build](.github/workflows/build.yml), [Release](.github/workflows/release.yml), and [Vendor pinned editor font](.github/workflows/vendor-font.yml). The release workflow reuses the exact-tag Windows/Linux tests and Windows executable build. It then creates the unchanged source ZIP, builds a versioned wheel, and publishes the two Windows ZIP archives, source ZIP, and wheel in a single GitHub release. Existing releases v1.0.0, v1.1.0, and v1.2.0 remain unchanged.

To publish a new version, push its tag (for example, `git tag v1.3.0 && git push origin v1.3.0`). Alternatively, run **Actions → Release → Run workflow** with an existing `vX.Y.Z` tag. The release is published only after tests, lint, and the Windows EXE build pass. Re-running for an already published tag leaves its assets untouched.

The CLI supports `--version` to print `CertScope <current version>`. Its `--help` output includes `CertScope - <version> (MIT)` and the GitHub repository URL. The Windows EXE filenames and release ZIP filenames use lowercase. Historical release assets have also been repackaged without changing the original executable bytes.

## Certificate linting (PKILint)

CertScope uses [DigiCert PKILint](https://github.com/digicert/pkilint) for offline certificate compliance checks. **Lint results are independent from trust-chain verification**: a trusted certificate may still violate RFC/policy requirements. The GUI lints all provided certificates when you select **Analyze and verify** and displays findings in the **Lint** tab, with a per-certificate selector and severity counts. The selected profile is remembered.

- **RFC 5280** is the default and is suitable for private PKIs.
- **CA/B Forum TLS** applies the TLS Baseline Requirements for public Web PKI certificates. PKILint detects the certificate type automatically; the detected type may need manual interpretation.

For CLI certificate inspection or verification, use `--lint` for RFC 5280 or `--lint-profile cabf-tls` for CA/B Forum TLS:

```bash
uv run certscope inspect --cert chain.pem --lint --format json
uv run certscope verify --cert chain.pem --ca root.pem --lint-profile cabf-tls --format json
```

The JSON report contains a separate `lint` object with the profile, status, per-certificate SHA-256 fingerprints, findings (severity, code, validator, ASN.1 path and message), and severity counts. Text output prints the summary and actionable findings. Lint failures do not change verification exit codes or certificate trust status. CertScope passes original DER bytes when available, preserving ASN.1 encoding details; it does not contact network services.

## Independent Windows executables

The Windows GUI and CLI are built from separate PyInstaller analyses and entry points.
`certscope.exe` retains the original PySide6 Qt Widgets interface and accepts an
optional certificate file, PEM string or TLS URL. `certscope-cli.exe` includes
only the headless inspection, verification, PKILint and database modules, without Qt.
Both binaries remain single-file EXEs with the existing Windows icon and version metadata.
The CI build publishes size comparisons against the unchanged v1.3.0 release.


## Nuitka branch

The [`nuitka` branch](https://github.com/erathaowl/CertScope/tree/nuitka) builds two standalone Windows executables using Nuitka 4.3.5 and Python 3.14, preserving the existing Qt Widgets GUI, CLI, PKILint and Windows icons/version metadata. Run `scripts/build-windows.ps1` on Windows to create `dist/certscope.exe`, `dist/certscope-cli.exe` and their release-format ZIP archives. GitHub Actions validates the branch on every push and compares build sizes to the PyInstaller v1.3.1 release. The `main` branch continues to use PyInstaller.
