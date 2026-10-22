import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from aipe_cad import cli

ROOT = Path(__file__).resolve().parents[1]
PARAMS = ROOT / "examples" / "dab-10kw" / "params"
LOCAL_SCHEMA = ROOT / "tests" / "data" / "capability-manifest.schema.json"
SIBLING_SCHEMA = ROOT.parent / "AIPE-Registry" / "schema" / "capability-manifest.schema.json"


def test_cli_help_and_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "aipe-cad" in capsys.readouterr().out


def test_cli_validate_and_resolve(capsys, tmp_path):
    assert cli.main(["validate", "transformer", str(PARAMS / "transformer.json")]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is True and out["name"] == "dab_transformer"
    target = tmp_path / "resolved.json"
    assert cli.main(["resolve", "heatsink", str(PARAMS / "heatsink.json"), "-o", str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["fins"]["count"] == 12


def test_cli_validate_reports_errors(capsys, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"kind": "heatsink", "base": {"length": 0.1, "width": 0.1, "thickness": 0.005},
                               "fins": {"thickness": 0.002, "height": 0.02, "pitch": 0.001}}), encoding="utf-8")
    assert cli.main(["validate", "heatsink", str(bad)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["valid"] is False and out["errors"]


def test_cli_schema_and_materials(capsys):
    assert cli.main(["schema", "coldplate"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["title"].startswith("AIPE CAD")
    assert cli.main(["materials"]) == 0
    assert "copper" in json.loads(capsys.readouterr().out)


def test_cli_find_freecad_does_not_crash(capsys):
    rc = cli.main(["find-freecad"])
    out = json.loads(capsys.readouterr().out)
    assert rc in (0, 2) and "found" in out


def _manifest_schema():
    path = SIBLING_SCHEMA if SIBLING_SCHEMA.is_file() else LOCAL_SCHEMA
    return json.loads(path.read_text(encoding="utf-8")), path


def test_aipe_manifest_valid_against_registry_schema():
    schema, source = _manifest_schema()
    manifest = yaml.safe_load((ROOT / "aipe.yaml").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = [f"/{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in validator.iter_errors(manifest)]
    assert errors == [], f"manifest violates {source}: {errors}"
    assert manifest["id"] == "aipe.cad-agent"
    assert manifest["type"] == "tool"
    assert manifest["status"] == "experimental" and manifest["maturity"] == "prototype"
    assert manifest["license"] == "MIT"
    tools = {t["id"]: t for t in manifest["tools"]}
    assert tools["freecad"]["licence_class"] == "open_source" and tools["freecad"]["optional"] is False
    assert tools["cadquery"]["optional"] is True
    # documentation and evidence references must exist in the checkout
    for ref in manifest["documentation"] + manifest["validation"]["evidence"]:
        if not ref.startswith("https://"):
            assert (ROOT / ref).exists(), ref
