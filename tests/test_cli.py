import json
import re
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


def test_cli_version_and_help(tmp_path):
    from certscope import __version__
    from certscope.app_info import APP_LICENSE, APP_NAME, APP_URL

    version = invoke(tmp_path, "--version")
    assert version.returncode == 0, version.stderr
    assert version.stdout.strip() == f"{APP_NAME} {__version__}"

    help_result = invoke(tmp_path, "--help")
    assert help_result.returncode == 0, help_result.stderr
    assert f"{APP_NAME} - {__version__} ({APP_LICENSE})" in help_result.stdout
    assert APP_URL in help_result.stdout
    assert re.search(r"--version\s+", help_result.stdout)


def test_cli_lint_json_and_text(tmp_path, chain):
    from certscope.parser import parse_bundle

    pem = tmp_path / "chain.pem"
    root = tmp_path / "root.pem"
    pem.write_text(chain["chain"], encoding="ascii")
    root.write_text(chain["root"], encoding="ascii")

    result = invoke(tmp_path, "inspect", "--cert", str(pem), "--lint", "--format", "json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["lint"]["profile"] == "rfc5280"
    assert len(report["lint"]["certificates"]) == len(parse_bundle(chain["chain"]))

    result = invoke(tmp_path, "verify", "--cert", str(pem), "--ca", str(root),
                    "--lint-profile", "cabf-tls", "--format", "json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["status"] == "trusted"
    assert report["lint"]["profile"] == "cabf-tls"

    text = invoke(tmp_path, "inspect", "--cert", str(pem), "--lint")
    assert text.returncode == 0
    assert "Lint (rfc5280):" in text.stdout
