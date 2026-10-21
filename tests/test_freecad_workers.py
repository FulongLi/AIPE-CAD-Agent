"""Tests that spawn freecadcmd (marker ``freecad``; skipped when FreeCAD is not installed).

Each component is built once per session (fixture ``build``) and several
assertions are made on the metadata / check report: FreeCAD volumes against
the closed-form values of the parameter layer, STEP export and re-import,
check-report structure, and deliberate interference / clearance cases.
"""
import copy
import math
from pathlib import Path

import pytest

pytestmark = pytest.mark.freecad

REL = 1e-6


def _body(meta, name):
    return next(b for b in meta["bodies"] if b["name"] == name)


def test_transformer_volumes_match_analytic(build, example_params):
    params = example_params("transformer")
    result, meta, checks = build("transformer", params, "t_transformer")
    assert result.ok and meta["invalid_shapes"] == []
    for name in ("core_lower", "core_upper", "primary", "secondary", "barrier_primary_secondary", "outer_wrap",
                 "pin_primary_1", "clip_neg_y", "base_plate"):
        rec = _body(meta, name)
        assert rec["volume_m3"] == pytest.approx(rec["analytic_volume_m3"], rel=REL), name
    # the fused bobbin (tube + two flange rings) is within 0.5 % of the closed form (fillet/overlap effects)
    bob = _body(meta, "bobbin")
    assert bob["volume_m3"] == pytest.approx(bob["analytic_volume_m3"], rel=5e-3)
    # total mass equals the sum over bodies and the analytic estimate of the parameter layer
    assert meta["totals"]["mass_kg"] == pytest.approx(sum(b["mass_kg"] for b in meta["bodies"]))
    from aipe_cad.params import resolve_transformer
    assert meta["totals"]["mass_kg"] == pytest.approx(resolve_transformer(params)["analytic_masses"]["total"], rel=5e-3)
    assert 0.6 < meta["totals"]["mass_kg"] < 0.8


def test_transformer_outputs_and_step_reimport(build, example_params):
    result, meta, checks = build("transformer", example_params("transformer"), "t_transformer")
    for key in ("fcstd", "step", "metadata", "checks"):
        assert Path(result.files[key]).is_file(), key
    assert Path(result.files["fcstd"]).stat().st_size > 1000
    step = meta["step_reimport"]
    assert step["valid"] and step["solids"] == meta["totals"]["body_count"]
    assert step["relative_error"] < 1e-9
    # units: bounding box reported in metres, consistent with the core size (65.2 mm wide core + plate margins)
    size = meta["totals"]["size_m"]
    assert size[0] == pytest.approx(0.0652 + 2 * 0.012, abs=1e-9)
    assert size[2] == pytest.approx(2 * 0.0326 + 0.0008 + 0.002 + (0.0337 - 0.0326), abs=1e-6)


def test_transformer_checks_report(build, example_params):
    result, meta, checks = build("transformer", example_params("transformer"), "t_transformer")
    assert checks["summary"]["interference_count"] == 0
    assert checks["summary"]["fit_failures"] == 0
    fit = {(f["a"], f["b"]): f for f in checks["fit"]}
    assert fit[("bobbin", "core_lower")]["distance_m"] == pytest.approx(0.0003, abs=1e-7)
    by_pair = {(c["net_a"], c["net_b"]): c for c in checks["clearance"]}
    # primary/secondary windings are fully enclosed by barrier + margins + bobbin -> review, pins 55 mm apart
    ps = by_pair[("primary", "secondary")]
    assert ps["status"] == "review"
    assert ps["solid_insulation_only"][0]["distance_m"] == pytest.approx(0.0005, abs=1e-7)
    assert ps["min_air_clearance_m"] == pytest.approx(2 * 0.0283 - 0.0015, abs=1e-6)
    pe = by_pair[("primary", "pe")]
    assert pe["status"] == "pass" and pe["min_air_clearance_m"] > 0.01
    assert checks["summary"]["status"] == "review"
    # contacts: bodies that touch (zero common volume) are listed for conformal meshing
    contacts = {frozenset((c["a"], c["b"])) for c in checks["contacts"]}
    assert frozenset(("bobbin", "primary")) in contacts


def test_heatsink_volume_matches_analytic_without_holes(build, example_params):
    params = copy.deepcopy(example_params("heatsink"))
    params["devices"] = []
    params["mounting_holes"] = None
    params["checks"] = {}
    result, meta, checks = build("heatsink", params, "t_heatsink_plain")
    body = _body(meta, "body")
    expected = 0.080 * 0.080 * 0.008 + 12 * 0.060 * 0.0015 * 0.035
    assert body["volume_m3"] == pytest.approx(expected, rel=REL)
    assert body["mass_kg"] == pytest.approx(expected * 2700, rel=REL)
    assert body["surface_area_m2"] > 2 * 12 * 0.060 * 0.035  # fins dominate the wetted area
    assert meta["step_reimport"]["relative_error"] < 1e-9


def test_heatsink_with_devices(build, example_params):
    result, meta, checks = build("heatsink", example_params("heatsink"), "t_heatsink")
    names = {b["name"] for b in meta["bodies"]}
    assert {"body", "Q1.body", "Q1.tab", "Q1.pad", "Q1.bushing", "Q1.screw", "Q1.lead_drain", "Q2.lead_gate"} <= names
    for n in ("Q1.tab", "Q1.pad", "Q1.body", "Q1.bushing", "Q1.screw"):
        rec = _body(meta, n)
        assert rec["volume_m3"] == pytest.approx(rec["analytic_volume_m3"], rel=1e-6), n
    assert checks["summary"]["interference_count"] == 0
    pair = checks["clearance"][0]
    # device tabs sit on 0.25 mm pads: the pad-edge air path and the leads govern; tab-to-screw stays encapsulated
    assert pair["status"] == "review"
    # pad-edge one-bend path: 2.5 mm pad overhang + 0.25 mm pad thickness
    governing = pair["governing_path"]
    assert governing["path"] == "around_insulator"
    assert governing["length_m"] == pytest.approx(0.0025 + 0.00025, abs=1e-6)
    assert all(s["insulators"] == [f"{s['a'].split('.')[0]}.bushing"] for s in pair["solid_insulation_only"])
    # the clearance envelope is exported as a keep-out body (zero mass) and excludes the leads
    env = _body(meta, "clearance_envelope")
    assert env["role"] == "envelope" and env["mass_kg"] == 0.0
    lead_top = max(b["bbox_m"][5] for b in meta["bodies"] if ".lead_" in b["name"])
    assert env["bbox_m"][5] < lead_top


def test_coldplate_coolant_volume_matches_analytic(build, example_params):
    params = copy.deepcopy(example_params("coldplate"))
    params["devices"] = []
    params["checks"] = {}
    result, meta, checks = build("coldplate", params, "t_coldplate_plain")
    from aipe_cad.params import resolve_coldplate
    res = resolve_coldplate(params)
    coolant = _body(meta, "coolant")
    assert coolant["role"] == "fluid"
    assert coolant["volume_m3"] == pytest.approx(res["analytic"]["coolant_volume"], rel=1e-6)
    plate = _body(meta, "plate")
    assert plate["volume_m3"] == pytest.approx(res["analytic"]["plate_volume"], rel=1e-6)
    cover = _body(meta, "cover")
    assert cover["volume_m3"] == pytest.approx(res["analytic"]["cover_volume"], rel=1e-6)
    # plate + coolant + bores fill the gross plate volume exactly (boolean cut consistency)
    assert plate["volume_m3"] + coolant["volume_m3"] == pytest.approx(
        res["analytic"]["plate_gross_volume"] - 4 * math.pi * (0.5 * 0.0055) ** 2 * 0.012, rel=1e-6)


def test_assembly_detects_deliberate_interference_and_measures_clearance(build, example_params):
    """Two boards: one sunk 1 mm into the chassis (interference), full-size copper zones 10 mm apart (clearance)."""
    params = {
        "kind": "assembly", "name": "t_assembly_overlap",
        "chassis": {"length": 0.2, "width": 0.1, "thickness": 0.003, "cutouts_under_heatsinks": False},
        "cooling": {"variant": "none", "placements": []},
        "transformer": None,
        "boards": [
            {"name": "board_a", "size": [0.05, 0.05], "thickness": 0.0016, "position": [-0.030, 0.0, -0.001],
             "mounting_holes": None, "standoffs": {"enabled": False},
             "copper_zones": [{"name": "cu_a", "offset": [0.0, 0.0], "size": [0.05, 0.05], "net": "n1", "thickness": 0.0001}]},
            {"name": "board_b", "size": [0.05, 0.05], "thickness": 0.0016, "position": [0.030, 0.0, 0.010],
             "mounting_holes": None, "standoffs": {"enabled": False},
             "copper_zones": [{"name": "cu_b", "offset": [0.0, 0.0], "size": [0.05, 0.05], "net": "n2", "thickness": 0.0001}]},
        ],
        "connectors": [],
        "checks": {"interference": {"enabled": True}, "clearance_pairs": [{"net_a": "n1", "net_b": "n2", "required_clearance": 0.005},
                                                                            {"net_a": "n1", "net_b": "n2", "required_clearance": 0.020}]},
    }
    result, meta, checks = build("assembly", params, "t_assembly_overlap")
    overlaps = [i for i in checks["interference"] if i["status"] == "overlap"]
    assert len(overlaps) == 1
    assert {overlaps[0]["a"], overlaps[0]["b"]} == {"chassis.plate", "board_a.board"}
    assert overlaps[0]["common_volume_m3"] == pytest.approx(0.05 * 0.05 * 0.001, rel=1e-6)
    # zone edges: cu_a top at z = 0.7 mm ends at x = -5 mm, cu_b bottom at z = 11.6 mm starts at x = +5 mm
    expected = math.hypot(0.010, 0.0109)
    ok, too_small = checks["clearance"]
    assert ok["status"] == "pass" and ok["governing_path"]["path"] == "straight"
    assert ok["min_air_clearance_m"] == pytest.approx(expected, rel=1e-6)
    assert too_small["status"] == "fail" and "below the required" in too_small["message"]
    assert checks["summary"]["status"] == "fail"


def test_full_assembly_example_builds(build, example_params):
    from aipe_cad.params import resolve_assembly
    params = example_params("assembly")
    result, meta, checks = build("assembly", params, "t_assembly_full")
    res = resolve_assembly(params)
    assert meta["totals"]["body_count"] > 100
    assert checks["summary"]["interference_count"] == 0
    assert checks["summary"]["keepout_violation_count"] == 0
    assert checks["summary"]["fit_failures"] == 0
    # chassis cut-outs/holes reduce its volume as computed by the parameter layer
    chassis = _body(meta, "chassis.plate")
    assert chassis["volume_m3"] == pytest.approx(res["chassis"]["analytic"]["volume"], rel=1e-6)
    # placed transformer core keeps its volume and rests on the chassis
    core = _body(meta, "transformer.core_lower")
    assert core["volume_m3"] == pytest.approx(res["transformer"]["resolved"]["core"]["half_volume"], rel=1e-6)
    plate = _body(meta, "transformer.base_plate")
    assert plate["bbox_m"][2] == pytest.approx(0.0, abs=1e-9)
    assert meta["step_reimport"]["relative_error"] < 1e-9
