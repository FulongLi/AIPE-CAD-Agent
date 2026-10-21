import math

import pytest

from aipe_cad import geometry2d as g2
from aipe_cad import materials, units


def test_length_conversions_round_trip():
    assert units.m_to_mm(0.0652) == pytest.approx(65.2)
    assert units.mm_to_m(65.2) == pytest.approx(0.0652)
    assert units.mm_to_m(units.m_to_mm(0.123456)) == pytest.approx(0.123456)


def test_area_volume_conversions():
    assert units.mm2_to_m2(1.0e6) == pytest.approx(1.0)
    assert units.mm3_to_m3(1.0e9) == pytest.approx(1.0)
    assert units.m3_to_mm3(2.5e-9) == pytest.approx(2.5)
    assert units.bbox_mm_to_m([0, -10, 5, 100, 10, 15]) == pytest.approx([0, -0.01, 0.005, 0.1, 0.01, 0.015])


def test_material_table_consistency():
    for name, m in materials.MATERIALS.items():
        assert m["density"] > 0, name
        assert isinstance(m["conductive"], bool), name
        assert materials.density(name) == m["density"]
        assert materials.is_conductive(name) == m["conductive"]
    assert materials.is_conductive("copper")
    assert not materials.is_conductive("kapton")


def test_material_density_override_and_errors():
    assert materials.density("copper", 8000.0) == 8000.0
    with pytest.raises(ValueError):
        materials.density("copper", -1.0)
    with pytest.raises(materials.UnknownMaterialError):
        materials.material("unobtainium")


def test_winding_effective_density_bounds():
    rho = materials.winding_effective_density(0.4)
    assert materials.RHO_INSULATION_POLYMER < rho < materials.RHO_COPPER
    assert materials.winding_effective_density(1.0) == pytest.approx(materials.RHO_COPPER)
    with pytest.raises(ValueError):
        materials.winding_effective_density(0.0)


def test_rounded_rectangle_formulas():
    # r = 0 degenerates to the plain rectangle
    assert g2.rounded_rect_area(4, 2, 0) == pytest.approx(8.0)
    assert g2.rounded_rect_perimeter(4, 2, 0) == pytest.approx(12.0)
    # full rounding of a square gives a circle
    assert g2.rounded_rect_area(2, 2, 1) == pytest.approx(math.pi)
    assert g2.rounded_rect_perimeter(2, 2, 1) == pytest.approx(2 * math.pi)
    # annulus = outer - inner
    inner = g2.rounded_rect_area(4, 2, 0.5)
    outer = g2.rounded_rect_area(6, 4, 1.5)
    assert g2.rounded_annulus_area(4, 2, 0.5, 1.0) == pytest.approx(outer - inner)
    assert g2.half_annulus_area(2, 1) == pytest.approx(0.5 * math.pi * 3)
    with pytest.raises(ValueError):
        g2.rounded_rect_area(2, 2, 1.5)
    with pytest.raises(ValueError):
        g2.half_annulus_area(1, 2)
