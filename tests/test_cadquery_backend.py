import copy

import pytest

from aipe_cad.params import resolve_heatsink

pytestmark = pytest.mark.cadquery


def test_cadquery_heatsink_volume_matches_analytic(tmp_path, example_params):
    from aipe_cad import cadquery_backend
    params = copy.deepcopy(example_params("heatsink"))
    params["devices"] = []
    params["mounting_holes"] = None
    res = resolve_heatsink(params)
    out = cadquery_backend.export_heatsink(res, tmp_path, name="cq_plain")
    assert out["volume_m3"] == pytest.approx(res["analytic"]["volume_without_holes"], rel=1e-6)
    assert out["mass_kg"] == pytest.approx(res["analytic"]["mass_without_holes"], rel=1e-6)
    assert (tmp_path / "cq_plain.cadquery.step").stat().st_size > 1000


def test_cadquery_heatsink_with_holes_is_smaller(tmp_path, example_params):
    from aipe_cad import cadquery_backend
    res = resolve_heatsink(example_params("heatsink"))
    out = cadquery_backend.export_heatsink(res, tmp_path, name="cq_holes")
    assert out["volume_m3"] < res["analytic"]["volume_without_holes"]
    assert out["volume_m3"] == pytest.approx(res["analytic"]["volume_without_holes"] - res["analytic"]["hole_volume_in_base"], rel=1e-3)
