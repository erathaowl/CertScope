import json
import os
import subprocess
import sys
from pathlib import Path


def invoke(tmp_path, *args):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    return subprocess.run([sys.executable, "-m", "certscope", "--db",
                           str(tmp_path / "cli.sqlite3"), *args],
                          capture_output=True, text=True, env=env)


def test_cli_inspect_and_verify(tmp_path, chain):
    leaf = tmp_path / "chain.pem"
    root = tmp_path / "root.pem"
    leaf.write_text(chain["chain"])
    root.write_text(chain["root"])
    result = invoke(tmp_path, "inspect", "--cert", str(leaf), "--format", "json")
    assert result.returncode == 0, result.stderr
    assert len(json.loads(result.stdout)["certificates"]) == 2
    result = invoke(tmp_path, "verify", "--cert", str(leaf), "--ca", str(root), "--format", "json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["trust_source"] == "custom"


def test_cli_db_and_invalid_stdin(tmp_path, chain):
    cert = tmp_path / "ca.pem"
    cert.write_text(chain["root"])
    assert invoke(tmp_path, "db", "add", "--type", "ca", "--name", "Root",
                  "--file", str(cert), "--trust").returncode == 0
    result = invoke(tmp_path, "db", "list", "--format", "json")
    assert json.loads(result.stdout)[0]["trusted"] is True
    failed = invoke(tmp_path, "verify", "--cert", "-", "--ca", "-", "--format", "json")
    assert failed.returncode == 2
    assert json.loads(failed.stdout)["status"] == "invalid_input"
