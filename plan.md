# CertScope: Development Plan

## 1. Objective

Build a local, offline-first X.509 certificate inspector and verifier with a desktop GUI and a fully usable command-line interface. Users can paste or load a PEM certificate or certificate chain, inspect every certificate, validate a chain against prioritized trust sources, manage named certificates and trusted CA bundles in SQLite, and obtain actionable verification diagnostics.

**Target:** Python 3.14+, `uv`, Windows and Linux development/runtime, a Windows single-file `.exe` built with PyInstaller, and English/Italian documentation.

## 2. Key architectural decisions

- **Project name:** `CertScope` (working name). Keep the application name configurable.
- **GUI:** PySide6 / Qt Widgets. Use `QPlainTextEdit` for the two PEM editors, `QTreeWidget` or `QTreeView` for the chain, a detail panel, and a results panel. Keep the UI responsive by running analysis in a `QThread` worker.
- **Parsing and certificate details:** `cryptography.x509`. Do not implement ASN.1, signature verification, or certificate-path building manually.
- **Offline verification:** a small, replaceable `pyOpenSSL.crypto.X509StoreContext` adapter for generic chain validation and OpenSSL verification error codes/depth. Use the verified chain returned by `get_verified_chain()` to identify the actual trust anchor. The `OpenSSL.crypto` API is marked for future deprecation; isolate it, pin tested dependencies, and add a compatibility test before upgrading.
- **TLS identity:** when a hostname/IP is supplied, perform an explicit server-identity and purpose check as an additional verification step, using a suitable `cryptography` server verifier and/or standards-based hostname matching; never treat a valid chain alone as proof of hostname identity. Clearly distinguish *chain trusted* from *TLS server validated*.
- **Persistence:** built-in `sqlite3` with parameterized SQL and a small repository layer. No ORM.
- **Paths:** `platformdirs` for a writable per-user database and logs. Never write mutable files into the PyInstaller extraction directory.
- **Application entry point:** one `main()` dispatcher. Without CLI arguments, open the GUI; when given subcommands, run headlessly without importing Qt unless necessary.
- **Network:** no outbound requests in the MVP. AIA fetching, CRL download, and OCSP queries are deferred and must never occur implicitly.

### 2.1 Verification semantics

A supplied PEM bundle contains a leaf certificate and zero or more *untrusted* intermediates. Certificates included in the inspected chain must **never** become trusted solely because they were pasted or loaded. Saved certificate entries likewise must not become trust anchors.

A saved CA entry becomes a local trust anchor only when explicitly marked **trusted and enabled**. A custom CA supplied in the second editor is a temporary, user-authorized trust source for the third stage and is not persisted automatically.

Default verification order, using **three separate trust stores**, must be:

1. **System CA trust**: system-provided CA certificates for the current machine and configured purpose.
2. **Local SQLite trust**: all enabled, explicitly trusted CA entries in the application database.
3. **Custom CA trust**: CA certificates currently pasted or loaded in the second editor, or supplied with the CLI.

Stop at the first valid chain and record the successful source. Preserve failure results for earlier attempts. When no stage succeeds, display errors from every attempted stage. Skip empty or unavailable sources with a specific diagnostic. Never merge local or custom roots into the system store before evaluating stage 1.

**Trust-anchor accuracy:** load system CA material through Python's `ssl` facilities, recording its origin. On Windows, use the system `ROOT` store for trust anchors and treat any `CA`-store intermediates as *untrusted chain-building candidates*; respect the certificate trust-purpose metadata where exposed. On Linux, use the effective OpenSSL default CA locations. Test the behavior on both platforms. A trust store assembled from exported certificates does not necessarily reproduce every native OS policy, especially Windows disallowed-certificate policy and other chain-engine rules. Report the selected verifier and these limitations in the documentation; do not describe the result as identical to Windows CryptoAPI verification without implementing and testing a native Windows adapter.

**Verification modes:**

- **Generic X.509 chain** (default): checks path-building, certificate signatures, validity dates, issuer constraints, critical extensions, and trust anchor. Report `Chain trusted` when successful; hostname and revocation remain `Not checked`.
- **TLS server** (`--purpose tls-server` plus `--hostname`): also checks DNS/IP SAN identity, applicable extended key usage, and relevant TLS-server policies. Require a hostname/IP for a conclusive `TLS server validated` result.
- **TLS client** (`--purpose tls-client`, optional follow-up if practical): verify the client-authentication purpose independently of the generic path result.

Every result must have a specific policy, verification timestamp (UTC), trust source, and clear status for chain, identity, purpose, and revocation. Do not claim certificate revocation was checked when CRL/OCSP processing is disabled.

## 3. Functional requirements

### 3.1 Certificate and CA input

- Main editor: paste/edit PEM certificate or concatenated PEM chain, open `.pem`, `.crt`, `.cer`, and `.chain` files, clear content, and select a previously saved entry.
- Secondary editor: paste/edit a PEM CA certificate or CA bundle, open a file, clear content, and select a stored CA entry. Custom content is used only at verification stage 3.
- Accept arbitrary PEM order. Detect likely leaf candidates by CA/basic-constraints status and issuer relationships; display all parsed certificates. If multiple independent leaves are present, allow selecting a leaf or analyzing each one separately rather than silently choosing the wrong target.
- Preserve every certificate in the inspected bundle for display. Deduplicate identical certificates by SHA-256 fingerprint for path building.
- Validate PEM boundaries; identify the malformed block and give its position. Reject private-key blocks with a clear warning; never store or log private keys.
- Apply sensible input limits (initially 2 MiB and 100 certificates), configurable in one place. File loads must use explicit decoding/error handling.
- DER input may be supported for single-certificate files as a convenience. The main contract remains PEM.

### 3.2 Certificate inspection

For every supplied certificate, show at least:

- Subject and issuer: full distinguished names, plus individual RDN fields.
- Version, serial number (hex/decimal), validity interval (UTC), remaining days, expiration status, and self-issued/self-signed indicators where verifiable.
- Subject Alternative Names: DNS names, IP addresses, URI, email, and other recognized general names.
- Public key algorithm, curve or key length, signature algorithm and parameters when available.
- SHA-256 and SHA-1 certificate fingerprints; Subject Key Identifier and Authority Key Identifier.
- Basic Constraints, Key Usage, Extended Key Usage, certificate policies and policy qualifiers, Name Constraints, AIA issuer/OCSP URLs, CRL Distribution Points, and all other available X.509 extensions.
- Critical flags; recognized fields decoded for readability; unknown extensions shown with OID and raw value in hex.
- Raw PEM, with copy and export actions. Do not display private keys.

Use a certificate tree showing `leaf -> intermediates -> trusted root` for successful verifications. Distinguish the *provided bundle* from the *verified path* because chain building may select a different cross-signed intermediate/root.

### 3.3 Verification outcome and diagnostics

- A concise final state: `Trusted`, `Untrusted`, `Invalid input`, or `Verification unavailable`, with additional identity/purpose/revocation statuses.
- A separate attempt row for `System`, `Local database`, and `Custom`, ordered exactly as executed.
- On success: the actual verified chain, selected trust source, root/trust-anchor subject, issuer, SHA-256 fingerprint, serial number, validity, and all other inspected CA details. Match the anchor's fingerprint to the corresponding system-store item or saved database CA name when available.
- On failure: OpenSSL error number, error depth, error message, failing certificate subject and fingerprint, and UTC verification time. Preserve the original diagnostic.
- Add *supplemental* diagnostic hints where safely determinable: expired/not-yet-valid certificates, missing issuer candidates, mismatched issuer/subject names, AKI/SKI mismatch, absent `CA:TRUE`, disallowed key usage, invalid/missing intermediate, hostname mismatch, or unsupported critical extensions. Label these as diagnostic checks, not as additional verified OpenSSL failures.
- Identify network-dependent checks as `Not checked (offline)`; never silently treat their absence as success.
- Allow a copyable textual report and JSON export containing all attempts and certificate details. The JSON schema must be the same for the GUI and CLI.

### 3.4 Local database

Use SQLite with a minimal schema:

```sql
CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('certificate', 'ca')),
    pem_bundle TEXT NOT NULL,
    bundle_sha256 TEXT NOT NULL,
    trusted INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (kind, name)
);
```

Business rules:

- `certificate` entries must always have `trusted = 0`.
- `ca` entries must be checked for valid CA properties before they can be enabled as trusted anchors; present an explicit trust-confirmation control. Retain named untrusted CA entries for inspection.
- Support create, list/filter, load, rename, update, delete, and enable/disable trust. Confirm destructive operations and trust changes.
- Store the exact normalized PEM bundle and its SHA-256 digest. Compute individual certificate fingerprints at inspection time; no separate certificate table is required for the MVP.
- Maintain a `PRAGMA user_version` schema version for later migrations.
- Use the same DB path for GUI and CLI, with optional `--db PATH` override. Initialize on first use; handle DB corruption and permission errors without data loss.
- Permit backup/export of named entries. Do not persist temporary custom CA input without an explicit save operation.

## 4. Desktop GUI

Use one window with resizable split panes:

```text
+--------------------------------------------------------------------------+
| CertScope        Open Certificate   Saved Entries   Settings             |
+-----------------------------------+--------------------------------------+
| Certificate / Chain PEM           | Custom CA PEM                        |
| [Open] [Save as...] [Clear]       | [Open] [Save as...] [Clear]         |
| [multiline editor]                | [multiline editor]                   |
+-----------------------------------+--------------------------------------+
| Verify purpose: [Generic v]   Hostname/IP: [________________] [Analyze]   |
+-------------------+------------------------------------------------------+
| Certificates      | Details / Verified Path / Diagnostics / Raw PEM      |
| [tree/list]       | [tabbed, selectable content]                         |
+-------------------+------------------------------------------------------+
| System: Failed  | Database: Passed | Custom: Not attempted              |
| Trust anchor: Example Internal Root CA  [View CA]  [Export report]       |
+--------------------------------------------------------------------------+
```

Interaction details:

- `Analyze` parses and displays every certificate, then runs verification in a background worker; disable duplicate runs during analysis.
- Select a tree item to show all of its details. Selecting the verified trust anchor shows the full CA certificate, even when it was absent from the input bundle.
- Show database entries through a searchable management dialog, with separate certificates and CA tabs and trusted/enabled indicators.
- Use inline, selectable/copyable error text, rather than a modal dialog with truncated errors.
- Provide English GUI text initially; structure UI strings for optional Italian localization later. The required bilingual deliverable is the README documentation.
- Support high-DPI layouts, standard keyboard shortcuts, file drag-and-drop, and a clear empty-state message.

## 5. CLI design

Use `argparse` and the same parsing, verification, storage, and report services as the GUI. Proposed interface:

```text
certscope                           # launch GUI
certscope gui
certscope inspect --cert server-chain.pem
certscope verify --cert server-chain.pem
certscope verify --cert server-chain.pem --ca custom-root.pem
certscope verify --cert server-chain.pem --purpose tls-server --hostname example.com
certscope verify --cert - --format json
certscope verify --entry "Production Server" --format json
certscope db list
certscope db list --type ca
certscope db add --type certificate --name "Production Server" --file server-chain.pem
certscope db add --type ca --name "Internal Root" --file internal-root.pem --trust
certscope db show --type ca --name "Internal Root"
certscope db trust --name "Internal Root" --enable
certscope db trust --name "Internal Root" --disable
certscope db rename --type ca --name "Internal Root" --to "Company Root"
certscope db delete --type ca --name "Company Root"
```

CLI requirements:

- `--cert FILE` and `--ca FILE`; `-` means stdin, with an explicit error if both arguments attempt to consume stdin simultaneously.
- `--entry NAME` loads a saved certificate/chain. Provide `--db PATH` as a global option.
- `--purpose generic|tls-server|tls-client` and `--hostname HOST`; reject invalid combinations clearly.
- `--format text|json`, with `text` as the default. Keep JSON on stdout free of progress messages, warnings, and Qt output; put diagnostics on stderr.
- Always execute trust checks in the required order unless an explicitly documented diagnostic flag narrows the requested source.
- Exit statuses: `0` valid for the requested policy, `1` verification failed, `2` invalid input/arguments, `3` runtime/DB/store error. All failures must have structured error output in JSON mode.
- Ensure GUI import has no side effects and CLI execution works on a headless machine.

## 6. Proposed repository layout

```text
certscope/
├── .python-version
├── .gitignore
├── pyproject.toml
├── uv.lock
├── launcher.py
├── certscope.spec
├── plan.md
├── README.md
├── README.it.md
├── assets/
│   ├── certscope.svg
│   ├── certscope.ico
│   └── certscope.png
├── src/certscope/
│   ├── __init__.py
│   ├── __main__.py
│   ├── main.py
│   ├── cli.py
│   ├── gui.py
│   ├── models.py
│   ├── parser.py
│   ├── inspector.py
│   ├── verification.py
│   ├── trust_stores.py
│   ├── storage.py
│   └── reporting.py
├── tests/
│   ├── fixtures/
│   ├── test_parser.py
│   ├── test_inspector.py
│   ├── test_verification.py
│   ├── test_trust_priority.py
│   ├── test_storage.py
│   ├── test_cli.py
│   └── test_packaging.py
└── scripts/
    └── build-windows.ps1
```

Keep modules small. `verification.py` owns the OpenSSL adapter and uniform result objects. `trust_stores.py` owns extraction and labeling of OS, DB, and custom anchors. No duplication between GUI and CLI.

## 7. Implementation tasks

### Phase 1: Project bootstrap

- [ ] Initialize the repository with `uv init --package certscope` and set `.python-version` to `3.14` and `requires-python = ">=3.14"` (select a tested upper bound for dependency compatibility if needed).
- [ ] Add runtime dependencies: `cryptography`, `pyOpenSSL`, `PySide6`, `platformdirs`.
- [ ] Add development dependencies: `pytest`, `pytest-cov`, `ruff`, `pyinstaller`.
- [ ] Pin compatible versions in `uv.lock` and verify `pyOpenSSL` / `cryptography` version constraints.
- [ ] Implement an import-safe application entry point, global error handling, and a per-user data directory.

### Phase 2: Parsing and inspection

- [ ] Parse one or more PEM certificates, retaining source positions and surfacing malformed blocks.
- [ ] Identify candidate leafs and issuer relationships; support multiple candidate leaves.
- [ ] Produce normalized, typed certificate-detail records with all extensions and fingerprints.
- [ ] Add unit tests for PEM order, duplicate certificates, unsupported extensions, and malformed input.

### Phase 3: Trust loading and verification

- [ ] Implement system CA loading for Windows and Linux and record trust-source provenance.
- [ ] Implement separate `system`, `database`, and `custom` anchor providers; never trust PEMs from the inspected bundle.
- [ ] Implement ordered verification attempts and return the full verified chain on success.
- [ ] Map OpenSSL error code/depth/failing certificate to a structured diagnostic; add supplemental explanatory checks.
- [ ] Implement TLS-server hostname/IP and purpose checking as a separate conclusive status.
- [ ] Add synthetic, reproducible certificates for success and failure tests.

### Phase 4: SQLite repository

- [ ] Create schema and migrations with `sqlite3`.
- [ ] Implement entry CRUD, unique names, trust enable/disable, and fingerprint-based reporting.
- [ ] Add transactions, DB-path override, and schema-version tests.

### Phase 5: CLI

- [ ] Add `inspect`, `verify`, and `db` subcommands with help, stdin support, and deterministic exit codes.
- [ ] Add text/JSON reporting using shared result models.
- [ ] Test commands with `subprocess` without importing or starting Qt.

### Phase 6: Desktop GUI

- [ ] Implement the dual PEM editors, file pickers, and entry selectors.
- [ ] Add analysis controls, results tree, all certificate-detail tabs, verified-chain display, and copy/export.
- [ ] Add local entry/CA management, explicit trust controls, and background analysis worker.
- [ ] Verify responsiveness and error presentation with large but bounded bundles.

### Phase 7: Branding and Windows executable

- [ ] Create an original, minimal app icon: **certificate sheet + shield/check mark**, with a simple geometric silhouette and readable appearance at 16, 32, 48, and 256 px. Avoid third-party logos and visually busy micro-details.
- [ ] Keep an editable `assets/certscope.svg`; export `certscope.ico` (multi-resolution) and `certscope.png` for runtime Qt UI.
- [ ] Create a PyInstaller `.spec` file and Windows build script. Include Qt resources and required `cryptography`/OpenSSL libraries.
- [ ] Build a **single console-capable `.exe`**, since CLI stdout and exit codes must work. Use PyInstaller's Windows `--hide-console hide-early` setting for GUI launches when appropriate, then verify interactive terminal behavior. Do **not** use `--windowed` for the only executable because it suppresses ordinary console I/O on Windows.
- [ ] Build on Windows for Windows (PyInstaller is not a general cross-compiler). Confirm GUI opens from Explorer and CLI commands work from PowerShell.
- [ ] Verify the EXE on a clean Windows VM without Python, OpenSSL CLI, `uv`, or Qt installed.
- [ ] Check extraction/startup behavior and user-writable database location; verify that certificate validation is still based on host OS stores instead of a packaged development CA bundle.

### Phase 8: Docs, tests, release

- [ ] Write `README.md` in English and `README.it.md` in Italian, with cross-links.
- [ ] Cover installation with `uv`, GUI usage, CLI examples, database trust management, exact trust-order semantics, security limitations, supported formats, packaging, and troubleshooting.
- [ ] Add automated test coverage for all verification decisions and report generation.
- [ ] Test the lockfile, linting, GUI smoke test, EXE packaging, and version metadata before release.
- [ ] Review the redistribution obligations of PySide6/Qt, PyInstaller, and all bundled third-party libraries; include notices and any legally required materials.

## 8. Reproducible test matrix

Test certificates should be generated in test fixtures with `cryptography`, without downloading production certificates or depending on an external network.

| Scenario | Expected behavior |
|---|---|
| Single valid leaf, matching system root | Stage 1 succeeds; display system anchor |
| Single valid leaf, matching enabled SQLite CA | Stage 1 fails; stage 2 succeeds; display saved CA name |
| Single valid leaf, matching custom CA only | Stages 1/2 fail; stage 3 succeeds; display custom anchor |
| Same root available in all three sources | System wins; later stages not attempted |
| Intermediate present in PEM bundle, root absent from all stores | Untrusted; never implicitly trust bundled root/intermediate |
| Included root in input but absent from trust stores | Untrusted |
| Missing intermediate | Explicit chain-building failure and likely missing issuer |
| Expired leaf or intermediate | Failure with certificate identification and date |
| Not-yet-valid leaf | Failure with date explanation |
| Tampered signature | Signature/path failure |
| Non-CA intermediate or invalid key usage | Failure with offending certificate details |
| Untrusted or disabled DB CA | Must not be used as an anchor |
| Cross-signed intermediate / alternative paths | Display actual selected verified path |
| Multiple leaf candidates | Each is selectable or individually analyzed |
| Valid chain with incorrect hostname | Chain status and identity failure shown separately |
| Valid chain without hostname | Chain trusted; identity not checked |
| Certificate with CRL/OCSP URLs | Revocation explicitly marked not checked |
| Invalid PEM, private key input, oversized file | Safe, actionable error, no private key persisted |
| Corrupt or unwritable SQLite DB | Diagnostic error; never silently reset data |
| `--format json` from the Windows EXE | Valid JSON stdout and correct exit code |
| Explorer launch of Windows EXE | GUI opens without an unwanted persistent terminal |

## 9. Definition of done

1. Both GUI and CLI can inspect every certificate in a PEM bundle and present the same structured details.
2. The verifier strictly follows **system -> enabled SQLite CAs -> temporary custom CA**, keeping stores isolated and identifying the successful source.
3. A positive result includes the actual verified certificate path and trust-anchor certificate details, including fingerprint.
4. A negative result retains every attempted store's diagnostics, including error code, depth, message, and affected certificate where available.
5. The application never silently conflates chain trust, hostname verification, and revocation status.
6. Certificates and CAs can be saved, named, loaded, updated, and deleted from persistent per-user SQLite storage; trusting a CA requires explicit consent.
7. Headless CLI works without the GUI; text and JSON reporting and documented exit codes work identically in the packaged EXE.
8. Tests pass with Python 3.14, including Windows trust-store behavior, and the one-file Windows EXE passes a clean-machine smoke test.
9. English and Italian README files describe usage, limitations, verification modes, and building.
10. A custom, original multi-resolution icon is embedded in the executable and appears in the GUI.

## 10. Suggested commands (for README and contributors)

```bash
uv python install 3.14
uv sync
uv run certscope
uv run certscope verify --cert tests/fixtures/server-chain.pem --format json
uv run pytest
uv run ruff check .
```

For a Windows one-file executable, use a maintained `certscope.spec` invoked on Windows:

```powershell
uv run pyinstaller --noconfirm --clean certscope.spec
.\dist\CertScope.exe --help
.\dist\CertScope.exe verify --cert .\tests\fixtures\server-chain.pem --format json
```

## 11. Technical references

- Python `ssl` system CA handling and Windows certificate stores: https://docs.python.org/3/library/ssl.html
- X.509 parsing and chain validation: https://cryptography.io/en/latest/x509/verification/
- OpenSSL-backed `X509StoreContext` and verified chain API: https://pyopenssl.org/en/latest/api/crypto.html
- Qt for Python release notes and Python 3.14 support: https://doc.qt.io/qtforpython-6/release_notes/pyside6_release_notes.html
- PyInstaller Windows console/windowed and icon options: https://pyinstaller.org/en/stable/man/pyinstaller.html
- `uv` project management and Python versions: https://docs.astral.sh/uv/guides/projects/
- OpenSSL verification flags and CRL/OCSP behavior: https://docs.openssl.org/master/man3/X509_VERIFY_PARAM_set_flags/
