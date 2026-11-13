"""SQLite storage for named certificates and explicitly trusted CA bundles."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from platformdirs import user_data_path

from certscope.parser import InputError, bundle_digest, normalize_bundle, parse_bundle

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Entry:
    id: int
    name: str
    kind: str
    pem_bundle: str
    bundle_sha256: str
    trusted: bool
    enabled: bool
    created_at: str
    updated_at: str


class Storage:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else user_data_path("CertScope", "CertScope") / "certscope.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise RuntimeError(f"Database version {version} is newer than supported version")
            if version == 0:
                db.executescript("""
                    CREATE TABLE IF NOT EXISTS entries (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        kind TEXT NOT NULL CHECK (kind IN ('certificate', 'ca')),
                        pem_bundle TEXT NOT NULL,
                        bundle_sha256 TEXT NOT NULL,
                        trusted INTEGER NOT NULL DEFAULT 0 CHECK (trusted IN (0, 1)),
                        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        UNIQUE (kind, name),
                        CHECK (kind = 'ca' OR trusted = 0)
                    );
                    PRAGMA user_version = 1;
                """)
            db.execute("CREATE TABLE IF NOT EXISTS preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("PRAGMA user_version = 2")

    def get_preference(self, key: str, default: str = "") -> str:
        with self.connect() as db:
            row = db.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_preference(self, key: str, value: str):
        with self.connect() as db:
            db.execute("""INSERT INTO preferences(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value""", (key, value))

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _entry(row):
        return Entry(**{**dict(row), "trusted": bool(row["trusted"]), "enabled": bool(row["enabled"])})

    def list(self, kind: str | None = None) -> list[Entry]:
        sql = "SELECT * FROM entries" + (" WHERE kind = ?" if kind else "") + " ORDER BY kind, name"
        with self.connect() as db:
            return [self._entry(r) for r in db.execute(sql, (kind,) if kind else ())]

    def get(self, kind: str, name: str) -> Entry:
        with self.connect() as db:
            row = db.execute("SELECT * FROM entries WHERE kind = ? AND name = ?", (kind, name)).fetchone()
        if row is None:
            raise KeyError(f"{kind} entry '{name}' not found")
        return self._entry(row)

    @staticmethod
    def _validate(kind: str, pem: str, trusted: bool):
        if kind not in ("certificate", "ca"):
            raise ValueError("Entry kind must be certificate or ca")
        certs = parse_bundle(pem)
        if trusted and (kind != "ca" or any(not c.is_ca for c in certs)):
            raise InputError("Trusted entries must contain CA:TRUE certificates only")
        if trusted:
            from cryptography import x509
            for cert in certs:
                try:
                    ku = cert.value.extensions.get_extension_for_class(x509.KeyUsage).value
                    if not ku.key_cert_sign:
                        raise InputError("Trusted CA must allow keyCertSign")
                except x509.ExtensionNotFound:
                    pass
        return normalize_bundle(certs)

    def save(self, kind: str, name: str, pem: str, *, trusted: bool = False,
             enabled: bool = True, replace: bool = False) -> Entry:
        if not name.strip():
            raise InputError("Name cannot be empty")
        pem = self._validate(kind, pem, trusted)
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            if replace:
                previous = db.execute("SELECT id, created_at FROM entries WHERE kind = ? AND name = ?",
                                      (kind, name)).fetchone()
                if previous:
                    db.execute("""UPDATE entries SET pem_bundle = ?, bundle_sha256 = ?, trusted = ?,
                        enabled = ?, updated_at = ? WHERE id = ?""",
                        (pem, bundle_digest(pem), int(trusted), int(enabled), now, previous["id"]))
                else:
                    db.execute("""INSERT INTO entries
                        (kind, name, pem_bundle, bundle_sha256, trusted, enabled, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (kind, name, pem, bundle_digest(pem), int(trusted), int(enabled), now, now))
            else:
                db.execute("""INSERT INTO entries
                    (kind, name, pem_bundle, bundle_sha256, trusted, enabled, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (kind, name, pem, bundle_digest(pem), int(trusted), int(enabled), now, now))
        return self.get(kind, name)

    def rename(self, kind: str, name: str, new_name: str):
        if not new_name.strip():
            raise InputError("Name cannot be empty")
        with self.connect() as db:
            cur = db.execute("UPDATE entries SET name = ?, updated_at = ? WHERE kind = ? AND name = ?",
                             (new_name, datetime.now(timezone.utc).isoformat(), kind, name))
            if not cur.rowcount:
                raise KeyError(f"{kind} entry '{name}' not found")

    def trust(self, name: str, enabled: bool):
        entry = self.get("ca", name)
        if enabled:
            self._validate("ca", entry.pem_bundle, True)
        with self.connect() as db:
            db.execute("UPDATE entries SET trusted = ?, enabled = ?, updated_at = ? WHERE id = ?",
                       (int(enabled), int(enabled), datetime.now(timezone.utc).isoformat(), entry.id))

    def set_enabled(self, kind: str, name: str, enabled: bool):
        entry = self.get(kind, name)
        with self.connect() as db:
            db.execute("UPDATE entries SET enabled = ?, updated_at = ? WHERE id = ?",
                       (int(enabled), datetime.now(timezone.utc).isoformat(), entry.id))

    def delete(self, kind: str, name: str):
        with self.connect() as db:
            cur = db.execute("DELETE FROM entries WHERE kind = ? AND name = ?", (kind, name))
            if not cur.rowcount:
                raise KeyError(f"{kind} entry '{name}' not found")
