"""Application preferences stored independently from certificate databases."""

import json
import os
import sqlite3
from pathlib import Path

from platformdirs import user_data_path


def default_settings_path() -> Path:
    return user_data_path("CertScope", "CertScope") / "settings.json"


class AppSettings:
    """Persist simple string preferences as an atomic JSON file."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_settings_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.values = {}
        if self.path.is_file():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.values = {key: value for key, value in data.items()
                                   if isinstance(key, str) and isinstance(value, str)}
            except (OSError, ValueError):
                # Keep the invalid source intact until an explicit settings change.
                pass

    def get_preference(self, key: str, default: str = "") -> str:
        return self.values.get(key, default)

    def _save(self, values: dict[str, str]):
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_text(
                json.dumps(values, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.values = values

    def set_preference(self, key: str, value: str):
        self._save({**self.values, key: value})

    def delete_preference(self, key: str):
        if key in self.values:
            values = dict(self.values)
            del values[key]
            self._save(values)

    def migrate_legacy(self, database: Path):
        """Move the old SQLite preferences to JSON without altering saved certificates."""
        if not database.is_file():
            return
        with sqlite3.connect(database) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='preferences'"
            ).fetchone()
            if not exists:
                return
            old = dict(db.execute("SELECT key, value FROM preferences").fetchall())
            merged = {**old, **self.values}
            if merged != self.values:
                self._save(merged)
            # Remove obsolete settings only after the new file has been written.
            db.execute("DROP TABLE preferences")
