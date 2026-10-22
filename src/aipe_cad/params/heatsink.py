"""Plate-fin heat sink parameters and derived geometry (SI, metres).

Local coordinate system
-----------------------
* Base plate centred on the XY origin.  The fin-root plane (base underside) is
  ``z = 0``; the base occupies ``0 <= z <= base.thickness``; fins hang down to
  ``z = -fins.height``.  Devices sit on the flat top face.
* Fins run along X (``base.length``) and are distributed along Y
  (``base.width``) with ``fins.pitch``.

Derived rules: fin count from pitch (``floor((W - t) / pitch) + 1``, the same
rule as the AIPE HeatSinkOptimisation study), fin positions, device/tab/lead/
pad/hole positions, mounting-hole and footprint collision checks, analytic
volumes and convective area, mesh hints.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from ..materials import density
from .base import (Errors, ParameterError, check_known_keys, get_bool, get_int, get_number, get_str, sub)
from .devices import device_placement


def fin_count_from_pitch(width: float, fin_thickness: float, pitch: float) -> int:
    """Number of fins that fit across ``width`` at ``pitch`` (fin thickness ``t``).

    ``n = floor((W - t) / p) + 1`` - the first fin needs ``t``, every further fin
    needs one pitch.  Requires ``W >= t`` and ``p > t``.
    """
    if width < fin_thickness:
        raise ParameterError([f"base width {width:.4g} m is smaller than one fin thickness {fin_thickness:.4g} m"])
    if pitch <= fin_thickness:
        raise ParameterError([f"fin pitch {pitch:.4g} m must exceed the fin thickness {fin_thickness:.4g} m"])
    return int(math.floor((width - fin_thickness) / pitch + 1e-9)) + 1


def fin_positions(width: float, fin_thickness: float, pitch: float, count: int) -> List[float]:
    """Y centres of ``count`` fins centred across ``width``."""
    span = (count - 1) * pitch + fin_thickness
    return [-0.5 * span + 0.5 * fin_thickness + k * pitch for k in range(count)]


def rot2d(x: float, y: float, deg: float):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return c * x - s * y, s * x + c * y


@dataclass
class HeatSinkParams:
    name: str
    base_length: float
    base_width: float
    base_thickness: float
    fin_thickness: float
    fin_height: float
    fin_pitch: float
    fin_count: Optional[int] = None
    fin_length: Optional[float] = None   # along X; None -> full base length
    material: str = "aluminium_6063"
    density_override: Optional[float] = None
    net: str = "pe"
    devices: List[dict] = field(default_factory=list)
    mounting_holes: Optional[dict] = None
    clearance_envelope_margin: float = 3.0e-3
    checks: dict = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "HeatSinkParams":
        errors = Errors()
        if not isinstance(d, dict):
            raise ParameterError(["heat sink parameters must be a JSON object"])
        check_known_keys(d, {"kind", "name", "description", "base", "fins", "devices", "mounting_holes", "net",
                             "clearance_envelope_margin", "checks"}, errors)
        get_str(d, "kind", "heatsink", errors, choices=["heatsink"])
        base = sub(d, "base", errors)
        check_known_keys(base, {"length", "width", "thickness", "material", "density"}, Errors("base"))
        fins = sub(d, "fins", errors)
        fctx = Errors("fins")
        check_known_keys(fins, {"thickness", "height", "pitch", "count", "length"}, fctx)
        errors.extend(fctx)
        devices_raw = d.get("devices", [])
        if not isinstance(devices_raw, list):
            errors.add("devices must be a list")
            devices_raw = []
        devices = [device_placement(dev if isinstance(dev, dict) else {}, i, errors, default_net="device")
                   for i, dev in enumerate(devices_raw)]
        names = [dev["name"] for dev in devices]
        if len(set(names)) != len(names):
            errors.add("device names must be unique")
        mh = d.get("mounting_holes", {"diameter": 4.5e-3, "inset": 6.0e-3})
        if mh is not None:
            if not isinstance(mh, dict):
                errors.add("mounting_holes must be an object or null")
                mh = {}
            mctx = Errors("mounting_holes")
            check_known_keys(mh, {"diameter", "inset", "enabled"}, mctx)
            enabled = get_bool(mh, "enabled", True, mctx)
            mh = {"diameter": get_number(mh, "diameter", 4.5e-3, mctx, positive=True),
                  "inset": get_number(mh, "inset", 6.0e-3, mctx, positive=True)} if enabled else None
            errors.extend(mctx)
        bctx = Errors("base")
        params = cls(
            name=get_str(d, "name", "heatsink", errors),
            base_length=get_number(base, "length", None, bctx, positive=True, required=True) or 0.1,
            base_width=get_number(base, "width", None, bctx, positive=True, required=True) or 0.1,
            base_thickness=get_number(base, "thickness", None, bctx, positive=True, required=True) or 0.01,
            fin_thickness=get_number(fins, "thickness", None, fctx, positive=True, required=True) or 1e-3,
            fin_height=get_number(fins, "height", None, fctx, positive=True, required=True) or 0.02,
            fin_pitch=get_number(fins, "pitch", None, fctx, positive=True, required=True) or 5e-3,
            fin_count=get_int(fins, "count", None, fctx, minimum=1),
            fin_length=get_number(fins, "length", None, fctx, positive=True),
            material=get_str(base, "material", "aluminium_6063", bctx),
            density_override=get_number(base, "density", None, bctx, positive=True),
            net=get_str(d, "net", "pe", errors),
            devices=devices,
            mounting_holes=mh,
            clearance_envelope_margin=get_number(d, "clearance_envelope_margin", 3.0e-3, errors, non_negative=True),
            checks=sub(d, "checks", errors),
            description=get_str(d, "description", "", errors),
        )
        errors.extend(bctx)
        errors.extend(fctx)
        errors.raise_if_any()
        return params


def resolve_device(dev: dict, z_surface: float, plate_length: float, plate_width: float, errors: Errors,
                   warnings: List[str], screw_depth: Optional[float] = None, plate_net: str = "pe") -> dict:
    """Place one device on the top surface ``z_surface`` of a plate centred at the origin.

    Device local frame: body centre at the origin, length axis along X with the
    leads exiting at +X, mounting hole towards -X.  ``rotation_deg`` rotates the
    device about its own centre.  Returns absolute positions in the plate frame.
    """
    pk = dev["package"]
    x0, y0 = dev["position"]
    rot = dev["rotation_deg"]
    L, Wb, A = pk["body_length"], pk["body_width"], pk["body_thickness"]
    pad = dev["pad"]
    z_pad_top = z_surface + (pad["thickness"] if pad else 0.0)

    def to_plate(lx, ly):
        rx, ry = rot2d(lx, ly, rot)
        return [x0 + rx, y0 + ry]

    # footprints in the local frame (x ranges, y ranges)
    body_local = [-0.5 * L, 0.5 * L, -0.5 * Wb, 0.5 * Wb]
    tab_local = [-0.5 * L, -0.5 * L + pk["tab_length"], -0.5 * pk["tab_width"], 0.5 * pk["tab_width"]]
    hole_local = [-0.5 * L + pk["hole_offset_from_top"], 0.0]
    pad_local = None
    if pad:
        os_ = pad["oversize"]
        pad_local = [tab_local[0] - os_, tab_local[1] + os_, tab_local[2] - os_, tab_local[3] + os_]
    leads = []
    form = dev["lead_form"]
    b, c = pk["lead_width"], pk["lead_thickness"]
    h_eff = max(form["horizontal"], c) if form["horizontal"] > 0 else c
    zc = z_pad_top + 0.5 * A
    lead_nets = dev["lead_nets"] or [dev["net"]] * len(pk["lead_offsets"])
    for k, off in enumerate(pk["lead_offsets"]):
        horizontal = {"x": [0.5 * L, 0.5 * L + h_eff], "y": [off - 0.5 * b, off + 0.5 * b], "z": [zc - 0.5 * c, zc + 0.5 * c]}
        vertical = None
        if form["vertical"] > 0:
            vertical = {"x": [0.5 * L + h_eff - c, 0.5 * L + h_eff], "y": [off - 0.5 * b, off + 0.5 * b],
                        "z": [zc - 0.5 * c, zc - 0.5 * c + form["vertical"]]}
        top_z = vertical["z"][1] if vertical else horizontal["z"][1]
        # absolute XY of the vertical lead axis (for board lead holes)
        axis_local = (0.5 * L + h_eff - 0.5 * c, off)
        leads.append({"name": pk["lead_names"][k] if k < len(pk["lead_names"]) else f"lead{k + 1}",
                      "net": lead_nets[k], "horizontal_local": horizontal, "vertical_local": vertical,
                      "top_z": top_z, "axis_xy": to_plate(*axis_local), "width": b, "thickness": c,
                      "material": pk["lead_material"]})

    def footprint_abs(rect):
        corners = [to_plate(rect[0], rect[2]), to_plate(rect[1], rect[2]), to_plate(rect[1], rect[3]), to_plate(rect[0], rect[3])]
        xs = [cxy[0] for cxy in corners]
        ys = [cxy[1] for cxy in corners]
        return [min(xs), min(ys), max(xs), max(ys)]

    body_abs = footprint_abs(body_local)
    tab_abs = footprint_abs(tab_local)
    pad_abs = footprint_abs(pad_local) if pad_local else None
    hole_abs = to_plate(*hole_local)
    half_l, half_w = 0.5 * plate_length, 0.5 * plate_width
    name = dev["name"]
    contact = pad_abs if pad_abs else tab_abs
    if not (contact[0] >= -half_l - 1e-9 and contact[2] <= half_l + 1e-9 and contact[1] >= -half_w - 1e-9 and contact[3] <= half_w + 1e-9):
        errors.add(f"device {name}: isolation pad / tab footprint {contact} m leaves the plate top face")
    if not (body_abs[0] >= -half_l - 1e-9 and body_abs[2] <= half_l + 1e-9 and body_abs[1] >= -half_w - 1e-9 and body_abs[3] <= half_w + 1e-9):
        if dev.get("overhang_allowed", True):
            warnings.append(f"device {name}: plastic body overhangs the plate edge (allowed; tab stays on the plate)")
        else:
            errors.add(f"device {name}: body overhangs the plate edge")
    r_screw = 0.5 * dev["screw_hole_diameter"]
    if not (abs(hole_abs[0]) + r_screw <= half_l and abs(hole_abs[1]) + r_screw <= half_w):
        errors.add(f"device {name}: screw hole at {hole_abs} m leaves the plate")
    tab_vol = pk["tab_length"] * pk["tab_width"] * pk["tab_thickness"]
    body_vol = L * Wb * A - tab_vol
    hole_area = math.pi * (0.5 * pk["hole_diameter"]) ** 2
    fastener = None
    if dev.get("fastener"):
        f = dev["fastener"]
        z_body_top = z_pad_top + A
        bore_area = math.pi * (0.5 * f["screw_diameter"]) ** 2
        fastener = {"screw_net": f["screw_net"] or plate_net, "screw_material": f["screw_material"],
                    "bushing_material": f["bushing_material"], "screw": f["screw"], "bushing": f["bushing"],
                    "screw_diameter": f["screw_diameter"], "hole_xy_local": hole_local}
        if f["bushing"]:
            sleeve_len = z_body_top - z_surface
            fastener["sleeve"] = {"outer_diameter": pk["hole_diameter"], "z": [z_surface, z_body_top]}
            fastener["shoulder"] = {"outer_diameter": f["shoulder_diameter"], "z": [z_body_top, z_body_top + f["shoulder_thickness"]]}
            fastener["bushing_volume"] = (hole_area - bore_area) * sleeve_len + \
                (math.pi * (0.5 * f["shoulder_diameter"]) ** 2 - bore_area) * f["shoulder_thickness"]
            z_head0 = z_body_top + f["shoulder_thickness"]
        else:
            z_head0 = z_body_top
        if f["screw"]:
            depth = screw_depth if screw_depth is not None else 0.0
            z_shank_bottom = z_surface - max(depth - 0.5e-3, 0.0)
            # inside the plate the engaged thread is represented at the hole diameter (tapped holes are smaller than the screw)
            engaged_d = min(f["screw_diameter"], dev["screw_hole_diameter"]) - 0.02e-3
            fastener["head"] = {"diameter": f["head_diameter"], "z": [z_head0, z_head0 + f["head_height"]]}
            fastener["shank"] = {"diameter": f["screw_diameter"], "z": [z_surface, z_head0]}
            fastener["engaged"] = {"diameter": engaged_d, "z": [z_shank_bottom, z_surface]}
            fastener["screw_volume"] = (math.pi * (0.5 * f["head_diameter"]) ** 2 * f["head_height"] + bore_area * (z_head0 - z_surface)
                                        + math.pi * (0.5 * engaged_d) ** 2 * (z_surface - z_shank_bottom))
            fastener["top_z"] = z_head0 + f["head_height"]
        else:
            fastener["top_z"] = z_head0
    return {
        "name": name, "net": dev["net"], "package": pk, "position": [x0, y0], "rotation_deg": rot,
        "z_surface": z_surface, "z_pad_top": z_pad_top, "z_body_top": z_pad_top + A,
        "body_local": body_local, "tab_local": tab_local, "pad_local": pad_local, "hole_local": hole_local,
        "body_footprint": body_abs, "tab_footprint": tab_abs, "pad_footprint": pad_abs, "hole_xy": hole_abs,
        "pad": pad, "screw_hole_diameter": dev["screw_hole_diameter"], "screw_hole_depth": screw_depth,
        "fastener": fastener,
        "leads": leads, "lead_top_z": max(ld["top_z"] for ld in leads) if leads else z_pad_top + A,
        "top_z": max([z_pad_top + A, fastener["top_z"] if fastener else 0.0] + [ld["top_z"] for ld in leads]),
        "analytic": {
            "body_volume": body_vol - hole_area * (A - pk["tab_thickness"]),
            "tab_volume": tab_vol - hole_area * pk["tab_thickness"],
            "pad_volume": ((pad_local[1] - pad_local[0]) * (pad_local[3] - pad_local[2]) * pad["thickness"]
                           - hole_area * pad["thickness"]) if pad else 0.0,
        },
        "materials": {"body": pk["body_material"], "tab": pk["tab_material"], "lead": pk["lead_material"],
                      "pad": pad["material"] if pad else None},
    }


def _rect_overlap(a, b, gap=0.0) -> bool:
    return not (a[2] + gap <= b[0] or b[2] + gap <= a[0] or a[3] + gap <= b[1] or b[3] + gap <= a[1])


def _circle_rect_distance(cx, cy, rect) -> float:
    dx = max(rect[0] - cx, 0.0, cx - rect[2])
    dy = max(rect[1] - cy, 0.0, cy - rect[3])
    return math.hypot(dx, dy)


def resolve_heatsink(d: dict) -> dict:
    p = HeatSinkParams.from_dict(d)
    errors = Errors()
    warnings: List[str] = []
    L, W, tb = p.base_length, p.base_width, p.base_thickness
    t, h, pitch = p.fin_thickness, p.fin_height, p.fin_pitch

    n_auto = fin_count_from_pitch(W, t, pitch)
    n = p.fin_count if p.fin_count is not None else n_auto
    span = (n - 1) * pitch + t
    errors.check(span <= W + 1e-12, f"{n} fins at pitch {pitch:.4g} m need {span:.4g} m but the base is {W:.4g} m wide")
    fin_len = p.fin_length if p.fin_length is not None else L
    errors.check(fin_len <= L + 1e-12, f"fin length {fin_len:.4g} m exceeds the base length {L:.4g} m")
    errors.raise_if_any()
    positions = fin_positions(W, t, pitch, n)
    fins = [{"name": f"fin_{k + 1}", "y_centre": y, "thickness": t, "height": h, "length": fin_len,
             "x": [-0.5 * fin_len, 0.5 * fin_len]} for k, y in enumerate(positions)]
    gap = pitch - t

    devices = [resolve_device(dev, tb, L, W, errors, warnings, screw_depth=tb, plate_net=p.net) for dev in p.devices]
    # device-device footprint overlap
    for i in range(len(devices)):
        for j in range(i + 1, len(devices)):
            fi = devices[i]["pad_footprint"] or devices[i]["body_footprint"]
            fj = devices[j]["pad_footprint"] or devices[j]["body_footprint"]
            if _rect_overlap(devices[i]["body_footprint"], devices[j]["body_footprint"]) or _rect_overlap(fi, fj):
                errors.add(f"devices {devices[i]['name']} and {devices[j]['name']} overlap")
    # screw holes versus fins
    for dev in devices:
        hx, hy = dev["hole_xy"]
        r = 0.5 * dev["screw_hole_diameter"]
        for fin in fins:
            if abs(hy - fin["y_centre"]) < 0.5 * t + r - 1e-12 and fin["x"][0] - r < hx < fin["x"][1] + r:
                warnings.append(f"device {dev['name']} screw hole intersects {fin['name']} (hole cut through the fin)")
                break
    mounting = None
    if p.mounting_holes:
        dia, inset = p.mounting_holes["diameter"], p.mounting_holes["inset"]
        errors.check(inset > 0.5 * dia, "mounting hole inset must exceed the hole radius")
        errors.check(2 * inset < min(L, W), "mounting holes do not fit on the base")
        holes = [[sx * (0.5 * L - inset), sy * (0.5 * W - inset)] for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
        for hx, hy in holes:
            for dev in devices:
                fp = dev["pad_footprint"] or dev["tab_footprint"]
                if _circle_rect_distance(hx, hy, fp) < 0.5 * dia:
                    errors.add(f"mounting hole at ({hx:.4g}, {hy:.4g}) m intersects device {dev['name']}")
                if _circle_rect_distance(hx, hy, dev["body_footprint"]) < 0.5 * dia:
                    errors.add(f"mounting hole at ({hx:.4g}, {hy:.4g}) m lies under the body of device {dev['name']}")
            for fin in fins:
                if abs(hy - fin["y_centre"]) < 0.5 * t + 0.5 * dia - 1e-12 and fin["x"][0] - 0.5 * dia < hx < fin["x"][1] + 0.5 * dia:
                    warnings.append(f"mounting hole at ({hx:.4g}, {hy:.4g}) m passes through {fin['name']}")
                    break
        mounting = {"diameter": dia, "inset": inset, "holes": holes}
    errors.raise_if_any()

    rho = density(p.material, p.density_override)
    base_vol = L * W * tb
    fins_vol = n * fin_len * t * h
    hole_vol_base = 0.0
    if mounting:
        hole_vol_base += 4 * math.pi * (0.5 * mounting["diameter"]) ** 2 * tb
    hole_vol_base += sum(math.pi * (0.5 * dev["screw_hole_diameter"]) ** 2 * tb for dev in devices)
    # base underside not covered by fin roots + both fin faces + fin tips + fin end faces
    convective_area = L * W - n * fin_len * t + 2 * n * h * fin_len + n * t * fin_len + 2 * n * t * h
    env = {"margin": p.clearance_envelope_margin,
           "bbox": [-0.5 * L, -0.5 * W, -h, 0.5 * L, 0.5 * W,
                    max([tb] + [dev["top_z"] for dev in devices])]}
    mesh_hints = {
        "target": "gmsh", "units": "m",
        "import_note": "Import the STEP with gmsh.model.occ.importShapes; map solids to regions by STEP product names.",
        "regions": [
            {"bodies": ["base"], "group": "heatsink_base", "material": p.material, "element_size": max(tb / 2.0, 0.5e-3)},
            {"bodies": [f["name"] for f in fins], "group": "heatsink_fins", "material": p.material,
             "element_size": max(t / 2.0, 0.3e-3), "note": "thin fins: 2 elements across the thickness; coarser along the length"},
        ] + [
            {"bodies": [f"{dev['name']}.tab", f"{dev['name']}.body"], "group": f"device_{dev['name']}",
             "material": dev['materials']['tab'], "element_size": 1.0e-3, "note": "heat source: tab/die region"}
            for dev in devices
        ] + [
            {"bodies": [f"{dev['name']}.pad"], "group": "isolation_pads", "material": dev["materials"]["pad"],
             "element_size": max(dev["pad"]["thickness"], 0.1e-3), "note": "thin isolation pad: one element across or thermal contact resistance"}
            for dev in devices if dev["pad"]
        ],
        "fluid_region": {"bbox": [-0.5 * fin_len - h, -0.5 * W - gap, -h - gap, 0.5 * fin_len + h, 0.5 * W + gap, 0.0],
                         "element_size": max(gap / 4.0, 0.5e-3),
                         "note": "suggested air domain around the fins for conjugate heat transfer (flow along X)"},
        "refinement_zones": [],
    }
    return {
        "kind": "heatsink", "name": p.name, "description": p.description, "units": "SI (m, kg)",
        "base": {"length": L, "width": W, "thickness": tb, "material": p.material, "density": rho, "net": p.net,
                 "z_top": tb},
        "fins": {"count": n, "count_from_pitch": n_auto, "thickness": t, "height": h, "pitch": pitch, "gap": gap,
                 "length": fin_len, "x": [-0.5 * fin_len, 0.5 * fin_len],
                 "span": span, "side_margin": 0.5 * (W - span), "positions": positions, "items": fins},
        "devices": devices, "mounting_holes": mounting, "envelope": env, "warnings": warnings,
        "analytic": {"base_volume": base_vol, "fins_volume": fins_vol, "volume_without_holes": base_vol + fins_vol,
                     "hole_volume_in_base": hole_vol_base, "mass_without_holes": (base_vol + fins_vol) * rho,
                     "convective_area": convective_area},
        "checks": p.checks, "mesh_hints": mesh_hints,
    }
