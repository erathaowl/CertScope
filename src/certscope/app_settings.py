"""Application preferences stored in YAML, separately from certificate databases."""

import json
import os
import sqlite3
from pathlib import Path

import yaml
from platformdirs import user_data_path


def default_settings_path() -> Path:
    return user_data_path("CertScope", "CertScope") / "settings.yaml"


class AppSettings:
    """Persist application preferences atomically in a YAML file."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else default_settings_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.values = {}
        if self.path.is_file():
            try:
                data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self.values = self._normalize(data)
            except (OSError, yaml.YAMLError):
                # Leave invalid files intact until the user changes a setting.
                pass
        elif self.path.name == "settings.yaml":
            legacy = self.path.with_name("settings.json")
            if legacy.is_file():
                try:
                    data = json.loads(legacy.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self._save(self._normalize(data))
                except (OSError, ValueError):
                    pass

    @staticmethod
    def _normalize(values: dict) -> dict:
        normalized = {}
        for key, value in values.items():
            if not isinstance(key, str):
                continue
            if key == "font_size_overrides":
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except ValueError:
                        value = {}
                if isinstance(value, dict):
                    normalized[key] = value
            elif isinstance(value, (str, int, float, bool)):
                normalized[key] = str(value)
        return normalized

    def get_preference(self, key: str, default=""):
        return self.values.get(key, default)

    def _save(self, values: dict):
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            temporary.write_text(
                yaml.safe_dump(values, allow_unicode=True, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        self.values = values

    def set_preference(self, key: str, value):
        self._save({**self.values, key: value})

    def delete_preference(self, key: str):
        if key in self.values:
            values = dict(self.values)
            del values[key]
            self._save(values)

    def migrate_legacy(self, database: Path):
        """Move legacy SQLite preferences to YAML without touching saved certificates."""
        if not database.is_file():
            return
        with sqlite3.connect(database) as db:
            exists = db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='preferences'"
            ).fetchone()
            if not exists:
                return
            old = self._normalize(dict(db.execute(
                "SELECT key, value FROM preferences"
            ).fetchall()))
            merged = {**old, **self.values}
            if merged != self.values or not self.path.is_file():
                self._save(merged)
            # Drop obsolete preferences only after the YAML file has been written.
            db.execute("DROP TABLE preferences")
