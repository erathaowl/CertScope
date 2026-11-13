from certscope.storage import Storage
from certscope.trust_stores import TrustSource
from certscope.verification import verify_bundle
from certscope.parser import parse_bundle


def test_explicit_custom_anchor_succeeds(tmp_path, chain):
    storage = Storage(tmp_path / "db.sqlite3")
    result = verify_bundle(chain["chain"], storage, chain["root"])
    assert result["status"] == "trusted", result["attempts"]
    assert result["trust_source"] == "custom"
    assert result["trust_anchor"]["subject"] == "CN=CertScope Test Root"
    assert [a["source"] for a in result["attempts"]] == ["system", "database", "custom"]


def test_local_database_anchor_wins_over_custom(tmp_path, chain):
    storage = Storage(tmp_path / "db.sqlite3")
    storage.save("ca", "My Test Root", chain["root"], trusted=True)
    result = verify_bundle(chain["chain"], storage, chain["root"])
    assert result["trust_source"] == "database", result["attempts"]
    assert result["trust_anchor"]["saved_name"] == "My Test Root"
    assert result["verified_chain"][-1]["origin"] == "database"
    assert result["verified_chain"][-1]["saved_name"] == "My Test Root"
    assert result["verified_chain"][0]["origin"] == "input"
    assert len(result["attempts"]) == 2


def test_disabled_db_anchor_is_not_trusted(tmp_path, chain):
    storage = Storage(tmp_path / "db.sqlite3")
    storage.save("ca", "Root", chain["root"], trusted=True)
    storage.trust("Root", False)
    result = verify_bundle(chain["chain"], storage)
    assert result["status"] == "untrusted"


def test_included_root_never_becomes_trusted(tmp_path, chain):
    result = verify_bundle(chain["chain"] + chain["root"], Storage(tmp_path / "db.sqlite3"))
    assert result["status"] == "untrusted"


def test_expired_certificate_reports_openssl_error(tmp_path, chain):
    result = verify_bundle(chain["expired"] + chain["intermediate"],
                           Storage(tmp_path / "db.sqlite3"), chain["root"])
    assert result["status"] == "untrusted"
    assert result["attempts"][-1]["status"] == "failed"
    assert result["attempts"][-1]["code"] is not None


def test_hostname_mismatch_preserves_chain_status(tmp_path, chain):
    result = verify_bundle(chain["chain"], Storage(tmp_path / "db.sqlite3"), chain["root"],
                           purpose="tls-server", hostname="incorrect.example")
    assert result["chain_status"] == "trusted"
    assert result["status"] == "untrusted"
    assert result["identity_and_purpose"]["status"] == "failed"


def test_same_anchor_system_takes_priority(tmp_path, chain):
    storage = Storage(tmp_path / "db.sqlite3")
    source = TrustSource("system", parse_bundle(chain["root"]), {})
    result = verify_bundle(chain["chain"], storage, chain["root"], sources=[source])
    assert result["status"] == "trusted"
    assert result["trust_source"] == "system"
    assert result["verified_chain"][-1]["origin"] == "system"
    assert result["verified_chain"][0]["origin"] == "input"
    assert len(result["attempts"]) == 1
