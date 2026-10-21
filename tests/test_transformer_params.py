import copy
import math

import pytest

from aipe_cad import geometry2d as g2
from aipe_cad.params import ParameterError, resolve_transformer
from aipe_cad.params.transformer import ECoreParams


def test_e65_derived_letters(example_params):
    res = resolve_transformer(example_params("transformer"))
    core = res["core"]
    assert core["window_width"] == pytest.approx(0.5 * (0.0442 - 0.020))      # (C - E) / 2 = 12.1 mm
    assert core["outer_leg_width"] == pytest.approx(0.5 * (0.0652 - 0.0442))  # (A - C) / 2 = 10.5 mm
    assert core["yoke_thickness"] == pytest.approx(0.0326 - 0.0222)           # B - D = 10.4 mm
    assert core["window_total_height"] == pytest.approx(0.0444)


def test_core_half_volume_formula(example_params):
    p = example_params("transformer")["core"]
    res = resolve_transformer(example_params("transformer"))
    a, b, f, d = p["total_width"], p["half_height"], p["depth"], p["window_height"]
    w = 0.5 * (p["inner_width"] - p["centre_leg_width"])
    expected = a * f * b - 2 * w * f * d
    assert res["core"]["half_volume"] == pytest.approx(expected)
    assert res["core"]["half_volume"] == pytest.approx(43.5189e-6, rel=1e-4)
    # geometric pair mass is ~7 % above the data-sheet 394 g/set (chamfers, tolerances): sanity band only
    assert 0.38 < res["core"]["mass"] < 0.45


def test_air_gap_reduces_half_volume(example_params):
    params = copy.deepcopy(example_params("transformer"))
    base = resolve_transformer(params)["core"]["half_volume"]
    params["core"]["air_gap"] = 0.001
    gapped = resolve_transformer(params)["core"]["half_volume"]
    assert base - gapped == pytest.approx(params["core"]["centre_leg_width"] * params["core"]["depth"] * 0.0005)


def test_winding_layer_rules(example_params):
    res = resolve_transformer(example_params("transformer"))
    prim, sec = res["windings"]
    # width available = 44.4 - 2*0.5 - 2*1.5 - 2*4 = 32.4 mm; 2.9 mm litz -> 11 turns/layer -> 2 layers
    assert res["bobbin"]["winding_width"] == pytest.approx(0.0404)
    assert prim["turns_per_layer"] == 11 and prim["layers"] == 2
    assert prim["thickness"] == pytest.approx(2 * 0.0029 + 0.00005)
    # foil: one turn per layer, thickness = turns * (foil + insulation)
    assert sec["layers"] == 10 and sec["turns_per_layer"] == 1
    assert sec["thickness"] == pytest.approx(10 * (0.0002 + 0.00005))
    assert sec["foil_width"] == pytest.approx(0.0324)
    # radial stack: primary, barrier, secondary, wrap
    assert res["bobbin"]["total_build"] == pytest.approx(prim["thickness"] + 0.0005 + sec["thickness"] + 0.0003)
    assert res["bobbin"]["max_build"] == pytest.approx(0.0098)
    assert res["bobbin"]["spare_build"] > 0


def test_winding_analytic_volume_and_copper(example_params):
    res = resolve_transformer(example_params("transformer"))
    prim = res["windings"][0]
    inner = prim["inner_dims"]
    expected = g2.rounded_annulus_area(inner[0], inner[1], prim["corner_radius_inner"], prim["thickness"]) * prim["width"]
    assert prim["volume"] == pytest.approx(expected)
    area = 420 * math.pi * (0.0001 / 2) ** 2
    assert prim["copper_area_per_conductor"] == pytest.approx(area)
    assert prim["copper_mass"] == pytest.approx(8960 * 21 * prim["mean_length_of_turn"] * area)
    assert prim["dc_resistance_20c_ohm"] == pytest.approx(1.72e-8 * 21 * prim["mean_length_of_turn"] / area)
    assert prim["mass"] == pytest.approx(prim["volume"] * prim["effective_density"])


def test_build_overflow_is_rejected(example_params):
    params = copy.deepcopy(example_params("transformer"))
    params["windings"][0]["turns"] = 60  # 6 layers of litz no longer fit radially
    with pytest.raises(ParameterError) as info:
        resolve_transformer(params)
    assert any("exceeds the available build" in m for m in info.value.messages)


def test_conductor_too_wide_is_rejected(example_params):
    params = copy.deepcopy(example_params("transformer"))
    params["windings"][0]["conductor"]["outer_diameter"] = 0.05
    with pytest.raises(ParameterError):
        resolve_transformer(params)


def test_unknown_keys_and_types_are_reported(example_params):
    params = copy.deepcopy(example_params("transformer"))
    params["core"]["typo_field"] = 1
    params["bobbin"]["wall_thickness"] = "thick"
    with pytest.raises(ParameterError) as info:
        resolve_transformer(params)
    joined = " ".join(info.value.messages)
    assert "typo_field" in joined and "wall_thickness" in joined


def test_terminal_direction_consistency(example_params):
    params = copy.deepcopy(example_params("transformer"))
    params["terminals"]["flange"] = "bottom"  # with direction +z this points into the bobbin
    with pytest.raises(ParameterError) as info:
        resolve_transformer(params)
    assert any("point away from the bobbin" in m for m in info.value.messages)


def test_terminals_and_mounting_geometry(example_params):
    res = resolve_transformer(example_params("transformer"))
    pins = res["terminals"]
    assert len(pins) == 4
    assert {p["net"] for p in pins} == {"primary", "secondary"}
    assert all(p["y"] < 0 for p in pins if p["net"] == "primary")
    assert all(p["y"] > 0 for p in pins if p["net"] == "secondary")
    assert all(p["z1"] - p["z0"] == pytest.approx(0.012) for p in pins)
    bp = res["mounting"]["base_plate"]
    assert len(bp["holes"]) == 4 and bp["size"][0] == pytest.approx(0.0652 + 2 * 0.012)
    assert res["mounting"]["clips"][0]["volume"] == pytest.approx(res["mounting"]["clips"][1]["volume"])
    assert res["analytic_masses"]["total"] == pytest.approx(sum(v for k, v in res["analytic_masses"].items() if k not in ("total", "copper")))


def test_fit_pairs_and_mesh_hints_present(example_params):
    res = resolve_transformer(example_params("transformer"))
    names = {(fp["a"], fp["b"]) for fp in res["fit_pairs"]}
    assert ("bobbin", "core_lower") in names
    assert res["mesh_hints"]["target"] == "gmsh"
    assert any(r["group"] == "core" for r in res["mesh_hints"]["regions"])
    assert res["mesh_hints"]["air_region"]["element_size"] > 0


def test_ecore_dataclass_rejects_inconsistent_letters():
    from aipe_cad.params.base import Errors
    errors = Errors()
    ECoreParams.from_dict({"total_width": 0.05, "half_height": 0.03, "depth": 0.02, "window_height": 0.035,
                           "inner_width": 0.06, "centre_leg_width": 0.07}, errors)
    joined = " ".join(errors.messages)
    assert "inner_width" in joined and "window_height" in joined and "centre_leg_width" in joined
