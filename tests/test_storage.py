import pytest

from certscope.storage import Storage


def test_storage_crud(tmp_path, chain):
    storage = Storage(tmp_path / "test.sqlite3")
    entry = storage.save("certificate", "Server", chain["chain"])
    assert not entry.trusted
    storage.rename("certificate", "Server", "Production")
    assert storage.get("certificate", "Production").name == "Production"
    with pytest.raises(KeyError):
        storage.get("certificate", "Server")
    storage.delete("certificate", "Production")
    assert not storage.list()


def test_ca_requires_explicit_trust(tmp_path, chain):
    storage = Storage(tmp_path / "test.sqlite3")
    storage.save("ca", "Root", chain["root"])
    assert not storage.get("ca", "Root").trusted
    storage.trust("Root", True)
    assert storage.get("ca", "Root").trusted
    storage.trust("Root", False)
    assert not storage.get("ca", "Root").trusted
    with pytest.raises(ValueError):
        storage.save("certificate", "Unsafe", chain["leaf"], trusted=True)
    with pytest.raises(ValueError):
        storage.save("ca", "Not a CA", chain["leaf"], trusted=True)


def test_duplicate_name_is_not_replaced_silently(tmp_path, chain):
    import sqlite3
    storage = Storage(tmp_path / "test.sqlite3")
    storage.save("ca", "Root", chain["root"])
    with pytest.raises(sqlite3.IntegrityError):
        storage.save("ca", "Root", chain["root"])
