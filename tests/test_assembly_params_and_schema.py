import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from aipe_cad import KINDS
from aipe_cad.params import ParameterError, load_json, resolve, resolve_assembly, resolve_refs
from aipe_cad.schema import SCHEMA_DIR, check_schema_files_in_sync, get_schema, validate_params

ROOT = Path(__file__).resolve().parents[1]
PARAMS = ROOT / "examples" / "dab-10kw" / "params"


def test_ref_resolution_inlines_component_files():
    raw = load_json(PARAMS / "assembly.json")
    assert "$ref" in raw["cooling"]["heatsink"]
    data = resolve_refs(raw, PARAMS)
    assert data["cooling"]["heatsink"]["kind"] == "heatsink"
    assert data["transformer"]["params"]["kind"] == "transformer"
    with pytest.raises(ParameterError):
        resolve_refs({"x": {"$ref": "missing.json"}}, PARAMS)


def test_assembly_example_resolution(example_params):
    res = resolve_assembly(example_params("assembly"), base_dir=PARAMS)
    assert res["cooling_variant"] == "heatsinks" and len(res["cooling"]) == 4
    nets = {inst["resolved"]["devices"][0]["net"] for inst in res["cooling"]}
    assert nets == {"primary", "secondary"}
    # transformer rests on the chassis: its lowest point is at z = 0
    tr = res["transformer"]
    assert tr["position"][2] == pytest.approx(-tr["resolved"]["envelope"]["bbox"][2])
    # device leads pass through the power boards -> lead holes, none in the control board
    holes = {b["name"]: len(b["lead_holes"]) for b in res["boards"]}
    assert holes == {"primary_power_board": 16, "secondary_power_board": 16, "control_board": 0}
    assert all(s["z1"] - s["z0"] > 0 for b in res["boards"] for s in b["standoffs"])
    # chassis: one cut-out per heat sink, holes for sinks, transformer plate and board standoffs
    assert len(res["chassis"]["cutouts"]) == 4
    assert len(res["chassis"]["holes"]) == 4 * 4 + 4 + 3 * 4
    assert res["connectors"][0]["position"][2] == pytest.approx(res["boards"][0]["z_top"])
    assert res["analytic_masses"]["total_estimate"] > 2.0


def test_assembly_detects_fins_without_chassis_rim(example_params):
    params = copy.deepcopy(example_params("assembly"))
    params["cooling"]["heatsink"]["fins"]["length"] = params["cooling"]["heatsink"]["base"]["length"]
    with pytest.raises(ParameterError) as info:
        resolve_assembly(params)
    assert any("rim" in m for m in info.value.messages)


def test_assembly_standoff_height_and_unknown_board(example_params):
    params = copy.deepcopy(example_params("assembly"))
    params["boards"][0]["position"][2] = 0.004  # below the heat sink top -> negative standoff? no: chassis supports; make it negative
    params["boards"][0]["position"][2] = -0.001
    with pytest.raises(ParameterError) as info:
        resolve_assembly(params)
    assert any("standoff" in m for m in info.value.messages)
    params = copy.deepcopy(example_params("assembly"))
    params["connectors"][0]["position"][2] = "on_board:nonexistent"
    with pytest.raises(ParameterError) as info:
        resolve_assembly(params)
    assert any("unknown board" in m for m in info.value.messages)


def test_assembly_coldplate_variant(example_params):
    params = copy.deepcopy(example_params("assembly"))
    cp = example_params("coldplate")
    params["cooling"] = {"variant": "coldplate", "coldplate": cp,
                         "placements": [{"name": "cp_main", "position": [0.0, -0.05, "on_chassis"], "rotation_deg": 0}]}
    params["boards"] = []
    params["connectors"] = []
    res = resolve_assembly(params)
    inst = res["cooling"][0]
    assert inst["kind"] == "coldplate"
    assert inst["position"][2] == pytest.approx(cp["cover"]["thickness"])  # cover rests on the chassis
    assert len(res["chassis"]["holes"]) == 4 + 4


@pytest.mark.parametrize("kind", KINDS)
def test_schemas_are_valid_and_examples_conform(kind):
    schema = get_schema(kind)
    Draft202012Validator.check_schema(schema)
    path = PARAMS / f"{kind}.json"
    data = resolve_refs(load_json(path), path.parent)
    assert validate_params(kind, data) == []
    # the committed schema files match the Python definition
    committed = json.loads((SCHEMA_DIR / f"{kind}.schema.json").read_text(encoding="utf-8"))
    assert committed == schema


def test_schema_files_in_sync():
    assert check_schema_files_in_sync() == []


def test_schema_rejects_bad_values(example_params):
    data = copy.deepcopy(example_params("heatsink"))
    data["base"]["thickness"] = -1
    data["fins"]["bogus"] = 3
    problems = validate_params("heatsink", data)
    assert any("thickness" in p for p in problems) and any("bogus" in p for p in problems)


@pytest.mark.parametrize("kind", KINDS)
def test_resolve_dispatch_is_json_serialisable(kind, example_params):
    res = resolve(kind, example_params(kind), base_dir=PARAMS)
    json.dumps(res)
    assert res["kind"] == kind
