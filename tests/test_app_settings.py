"""Settings persist in JSON and migrate safely from historical SQLite databases."""

import json
import sqlite3

from certscope.app_settings import AppSettings
from certscope.storage import Storage


def test_settings_file_is_independent_from_certificate_database(tmp_path, chain):
    db_path = tmp_path / "certificates.sqlite3"
    settings_path = tmp_path / "settings.json"
    storage = Storage(db_path)
    storage.save("ca", "Root", chain["root"], trusted=True)

    settings = AppSettings(settings_path)
    assert settings.get_preference("theme", "system") == "system"
    settings.set_preference("theme", "dark")
    settings.set_preference("font_size", "15")
    settings.set_preference("last_database", str(db_path))
    assert json.loads(settings_path.read_text()) == {
        "font_size": "15", "last_database": str(db_path), "theme": "dark"
    }
    assert AppSettings(settings_path).get_preference("theme") == "dark"
    settings.delete_preference("font_size")
    assert AppSettings(settings_path).get_preference("font_size", "11") == "11"
    assert Storage(db_path).get("ca", "Root").trusted
    with sqlite3.connect(db_path) as db:
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='preferences'"
        ).fetchone() is None


def test_legacy_settings_migrate_and_leave_certificate_entries_intact(tmp_path, chain):
    path = tmp_path / "certscope.sqlite3"
    storage = Storage(path)
    storage.save("ca", "Legacy Root", chain["root"], trusted=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.executemany("INSERT INTO preferences VALUES (?, ?)", [
            ("theme", "dark"), ("font_size", "14"), ("result_view", "JSON"),
            ("font_size_overrides", '{"certificate_pem": 18}'),
        ])

    settings = AppSettings(tmp_path / "settings.json")
    settings.migrate_legacy(path)
    assert settings.get_preference("theme") == "dark"
    assert settings.get_preference("font_size") == "14"
    assert settings.get_preference("result_view") == "JSON"
    assert settings.get_preference("font_size_overrides") == '{"certificate_pem": 18}'
    assert Storage(path).get("ca", "Legacy Root").trusted
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='preferences'"
        ).fetchone() is None

    settings.migrate_legacy(path)
    assert settings.get_preference("font_size") == "14"


def test_existing_json_preferences_take_precedence_during_migration(tmp_path):
    database = tmp_path / "original.sqlite3"
    Storage(database)
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE preferences (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        db.execute("INSERT INTO preferences VALUES ('theme', 'dark')")
        db.execute("INSERT INTO preferences VALUES ('font_size', '12')")

    settings = AppSettings(tmp_path / "settings.json")
    settings.set_preference("theme", "light")
    settings.migrate_legacy(database)
    assert settings.get_preference("theme") == "light"
    assert settings.get_preference("font_size") == "12"


def test_invalid_settings_are_ignored_without_discarding_source(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{invalid JSON", encoding="utf-8")
    settings = AppSettings(path)
    assert settings.get_preference("theme", "system") == "system"
    assert path.read_text() == "{invalid JSON"
