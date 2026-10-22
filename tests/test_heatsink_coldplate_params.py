import copy
import math

import pytest

from aipe_cad import geometry2d as g2
from aipe_cad.params import ParameterError, fin_count_from_pitch, fin_positions, resolve_coldplate, resolve_heatsink
from aipe_cad.params.devices import PACKAGE_LIBRARY, package_profile
from aipe_cad.params.base import Errors


@pytest.mark.parametrize("width,thickness,pitch,expected", [
    (0.080, 0.0015, 0.005, 16),   # floor(78.5/5) + 1
    (0.080, 0.0015, 0.0045, 18),  # floor(78.5/4.5) + 1 = 17 + 1
    (0.0015, 0.0015, 0.005, 1),   # exactly one fin fits
    (0.050, 0.002, 0.004, 13),
])
def test_fin_count_from_pitch(width, thickness, pitch, expected):
    assert fin_count_from_pitch(width, thickness, pitch) == expected
    positions = fin_positions(width, thickness, pitch, expected)
    assert len(positions) == expected
    span = (expected - 1) * pitch + thickness
    assert span <= width + 1e-12
    assert positions[0] == pytest.approx(-0.5 * span + 0.5 * thickness)
    assert positions[-1] == pytest.approx(0.5 * span - 0.5 * thickness)


def test_fin_count_rejects_bad_pitch():
    with pytest.raises(ParameterError):
        fin_count_from_pitch(0.08, 0.002, 0.002)
    with pytest.raises(ParameterError):
        fin_count_from_pitch(0.001, 0.002, 0.005)


def test_heatsink_example_resolution(example_params):
    res = resolve_heatsink(example_params("heatsink"))
    fins = res["fins"]
    assert fins["count"] == 12 and fins["count_from_pitch"] == 16
    assert fins["span"] == pytest.approx(11 * 0.005 + 0.0015)
    assert fins["length"] == pytest.approx(0.060)
    assert res["analytic"]["fins_volume"] == pytest.approx(12 * 0.060 * 0.0015 * 0.035)
    assert res["analytic"]["base_volume"] == pytest.approx(0.080 * 0.080 * 0.008)
    assert res["analytic"]["mass_without_holes"] == pytest.approx((res["analytic"]["fins_volume"] + res["analytic"]["base_volume"]) * 2700)
    # device screw holes fall between fins (no fin-intersection warning)
    assert not any("screw hole intersects" in w for w in res["warnings"])
    assert len(res["devices"]) == 2
    dev = res["devices"][0]
    assert dev["pad"]["thickness"] == pytest.approx(0.00025)
    assert dev["z_pad_top"] == pytest.approx(0.008 + 0.00025)
    assert dev["fastener"]["sleeve"]["outer_diameter"] == pytest.approx(PACKAGE_LIBRARY["to247_4l"]["hole_diameter"])
    assert len(dev["leads"]) == 4 and dev["leads"][0]["name"] == "drain"


def test_heatsink_explicit_count_must_fit(example_params):
    params = copy.deepcopy(example_params("heatsink"))
    params["fins"]["count"] = 40
    with pytest.raises(ParameterError) as info:
        resolve_heatsink(params)
    assert any("fins at pitch" in m for m in info.value.messages)


def test_heatsink_device_overlap_and_hole_collisions(example_params):
    params = copy.deepcopy(example_params("heatsink"))
    params["devices"][1]["position"] = params["devices"][0]["position"]
    with pytest.raises(ParameterError) as info:
        resolve_heatsink(params)
    assert any("overlap" in m for m in info.value.messages)
    params = copy.deepcopy(example_params("heatsink"))
    params["devices"][0]["position"] = [0.0286, 0.034]  # pad reaches the corner mounting hole
    with pytest.raises(ParameterError) as info:
        resolve_heatsink(params)
    assert any("mounting hole" in m for m in info.value.messages)


def test_heatsink_pad_must_stay_on_plate(example_params):
    params = copy.deepcopy(example_params("heatsink"))
    params["devices"][0]["position"] = [0.045, 0.020]
    with pytest.raises(ParameterError) as info:
        resolve_heatsink(params)
    assert any("leaves the plate" in m for m in info.value.messages)


def test_package_profile_overrides_and_validation():
    errors = Errors()
    prof = package_profile({"base": "to247_4l", "body_thickness": 0.0048}, errors)
    assert not errors.messages and prof["body_thickness"] == 0.0048
    errors = Errors()
    package_profile({"base": "to247_4l", "tab_thickness": 0.01}, errors)
    assert errors.messages
    errors = Errors()
    package_profile("to220_not_in_library", errors)
    assert errors.messages


def test_coldplate_example_resolution(example_params):
    res = resolve_coldplate(example_params("coldplate"))
    ch = res["channel"]
    assert ch["passes"] == 4 and ch["pitch"] == pytest.approx(0.026)
    assert ch["pass_y"] == pytest.approx([-0.039, -0.013, 0.013, 0.039])
    assert ch["inlet_side"] == "-x" and ch["outlet_side"] == "-x"  # even pass count: both ports on -x
    assert [t["side"] for t in ch["turns"]] == ["+x", "-x", "+x"]
    r_o, r_i = ch["turn_outer_radius"], ch["turn_inner_radius"]
    assert r_o == pytest.approx(0.013 + 0.004) and r_i == pytest.approx(0.013 - 0.004)
    straight = sum((s["x"][1] - s["x"][0]) * 0.008 * 0.006 for s in ch["straights"])
    turns = 3 * g2.half_annulus_area(r_o, r_i) * 0.006
    assert res["analytic"]["channel_volume"] == pytest.approx(straight + turns)
    assert res["analytic"]["coolant_mass"] == pytest.approx((straight + turns + res["analytic"]["port_bore_volume"]) * 1070)
    assert res["analytic"]["plate_volume"] < res["analytic"]["plate_gross_volume"]
    assert len(res["devices"]) == 8 and len(res["ports"]) == 2


def test_coldplate_rules(example_params):
    params = copy.deepcopy(example_params("coldplate"))
    params["channel"]["depth"] = 0.011  # leaves < min_wall above the channel
    with pytest.raises(ParameterError):
        resolve_coldplate(params)
    params = copy.deepcopy(example_params("coldplate"))
    params["channel"]["pitch"] = 0.009  # web thinner than min_wall
    with pytest.raises(ParameterError) as info:
        resolve_coldplate(params)
    assert any("web between passes" in m for m in info.value.messages)
    params = copy.deepcopy(example_params("coldplate"))
    params["ports"]["outer_diameter"] = 0.030  # boss does not fit on the end face
    with pytest.raises(ParameterError) as info:
        resolve_coldplate(params)
    assert any("boss radius" in m for m in info.value.messages)
    params = copy.deepcopy(example_params("coldplate"))
    params["screw_hole_depth"] = 0.006  # breaks into the channel below the devices
    with pytest.raises(ParameterError) as info:
        resolve_coldplate(params)
    assert any("coolant channel" in m for m in info.value.messages)


def test_coldplate_odd_passes_put_outlet_on_other_end(example_params):
    params = copy.deepcopy(example_params("coldplate"))
    params["channel"]["passes"] = 3
    params["devices"] = []
    res = resolve_coldplate(params)
    assert res["channel"]["outlet_side"] == "+x"
    assert res["ports"][1]["boss"]["x"][0] == pytest.approx(0.120)


def test_coldplate_auto_pitch(example_params):
    params = copy.deepcopy(example_params("coldplate"))
    params["channel"]["pitch"] = None
    params["devices"] = []
    res = resolve_coldplate(params)
    avail = 0.120 - 2 * 0.012
    assert res["channel"]["pitch"] == pytest.approx((avail - 0.008) / 3)
    assert res["channel"]["span"] == pytest.approx(avail)
