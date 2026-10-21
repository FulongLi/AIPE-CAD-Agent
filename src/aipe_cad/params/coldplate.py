"""Liquid cold plate parameters and derived serpentine-channel geometry (SI, metres).

Local coordinate system
-----------------------
* Plate centred on the XY origin.  The channel face (plate underside) is
  ``z = 0``; the plate occupies ``0 <= z <= plate.thickness``; the cover plate
  closes the channel at ``-cover.thickness <= z <= 0``; devices sit on top.
* Channel passes run along X (``plate.length``) and are distributed along Y.
  Pass 0 starts at the -X end (inlet); 180-degree turns alternate between the
  +X and -X ends.  With an even number of passes both ports are on the -X face.

The resolver produces the full centre-line description (straights, half-
annulus turns, port bores, boss positions), analytic coolant volume, plate and
cover volumes, collision checks for mounting holes/screw holes against the
channel, and mesh hints including the fluid region.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from .. import geometry2d as g2
from ..materials import density
from .base import (Errors, ParameterError, check_known_keys, get_int, get_number, get_str, sub)
from .devices import device_placement
from .heatsink import _circle_rect_distance, _rect_overlap, resolve_device


@dataclass
class ColdPlateParams:
    name: str
    length: float
    width: float
    thickness: float
    material: str
    density_override: Optional[float]
    channel_width: float
    channel_depth: float
    passes: int
    pitch: Optional[float]
    edge_margin: float
    end_margin: float
    min_wall: float
    cover_thickness: Optional[float]
    cover_material: str
    port_outer_diameter: float
    port_bore: float
    port_length: float
    port_material: str
    coolant_material: str
    devices: List[dict]
    screw_hole_depth: float
    mounting_holes: Optional[dict]
    net: str = "pe"
    clearance_envelope_margin: float = 3.0e-3
    checks: dict = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "ColdPlateParams":
        errors = Errors()
        if not isinstance(d, dict):
            raise ParameterError(["cold plate parameters must be a JSON object"])
        check_known_keys(d, {"kind", "name", "description", "plate", "channel", "cover", "ports", "coolant", "devices",
                             "screw_hole_depth", "mounting_holes", "net", "clearance_envelope_margin", "checks"}, errors)
        get_str(d, "kind", "coldplate", errors, choices=["coldplate"])
        plate = sub(d, "plate", errors)
        pctx = Errors("plate")
        check_known_keys(plate, {"length", "width", "thickness", "material", "density"}, pctx)
        chan = sub(d, "channel", errors)
        cctx = Errors("channel")
        check_known_keys(chan, {"width", "depth", "passes", "pitch", "edge_margin", "end_margin", "min_wall"}, cctx)
        cover = d.get("cover", {})
        vctx = Errors("cover")
        cover_thickness = None
        cover_material = "aluminium_6063"
        if cover is not None:
            if not isinstance(cover, dict):
                vctx.add("cover must be an object or null")
                cover = {}
            check_known_keys(cover, {"thickness", "material"}, vctx)
            cover_thickness = get_number(cover, "thickness", 3.0e-3, vctx, positive=True)
            cover_material = get_str(cover, "material", "aluminium_6063", vctx)
        ports = sub(d, "ports", errors)
        octx = Errors("ports")
        check_known_keys(ports, {"outer_diameter", "bore", "length", "material", "style"}, octx)
        get_str(ports, "style", "boss", octx, choices=["boss"])
        coolant = sub(d, "coolant", errors)
        check_known_keys(coolant, {"material"}, Errors("coolant"))
        devices_raw = d.get("devices", [])
        if not isinstance(devices_raw, list):
            errors.add("devices must be a list")
            devices_raw = []
        devices = [device_placement(dev if isinstance(dev, dict) else {}, i, errors) for i, dev in enumerate(devices_raw)]
        names = [dev["name"] for dev in devices]
        if len(set(names)) != len(names):
            errors.add("device names must be unique")
        mh = d.get("mounting_holes", {"diameter": 5.5e-3, "inset": 6.0e-3})
        if mh is not None:
            if not isinstance(mh, dict):
                errors.add("mounting_holes must be an object or null")
                mh = {}
            mctx = Errors("mounting_holes")
            check_known_keys(mh, {"diameter", "inset"}, mctx)
            mh = {"diameter": get_number(mh, "diameter", 5.5e-3, mctx, positive=True),
                  "inset": get_number(mh, "inset", 6.0e-3, mctx, positive=True)}
            errors.extend(mctx)
        params = cls(
            name=get_str(d, "name", "coldplate", errors),
            length=get_number(plate, "length", None, pctx, positive=True, required=True) or 0.2,
            width=get_number(plate, "width", None, pctx, positive=True, required=True) or 0.1,
            thickness=get_number(plate, "thickness", None, pctx, positive=True, required=True) or 0.012,
            material=get_str(plate, "material", "aluminium_6063", pctx),
            density_override=get_number(plate, "density", None, pctx, positive=True),
            channel_width=get_number(chan, "width", None, cctx, positive=True, required=True) or 8e-3,
            channel_depth=get_number(chan, "depth", None, cctx, positive=True, required=True) or 6e-3,
            passes=get_int(chan, "passes", 4, cctx, minimum=1) or 4,
            pitch=get_number(chan, "pitch", None, cctx, positive=True),
            edge_margin=get_number(chan, "edge_margin", 12e-3, cctx, positive=True),
            end_margin=get_number(chan, "end_margin", 15e-3, cctx, positive=True),
            min_wall=get_number(chan, "min_wall", 2e-3, cctx, positive=True),
            cover_thickness=cover_thickness,
            cover_material=cover_material,
            port_outer_diameter=get_number(ports, "outer_diameter", 12e-3, octx, positive=True),
            port_bore=get_number(ports, "bore", 6e-3, octx, positive=True),
            port_length=get_number(ports, "length", 20e-3, octx, positive=True),
            port_material=get_str(ports, "material", "brass", octx),
            coolant_material=get_str(coolant, "material", "water_glycol_50", errors),
            devices=devices,
            screw_hole_depth=get_number(d, "screw_hole_depth", 6e-3, errors, positive=True),
            mounting_holes=mh,
            net=get_str(d, "net", "pe", errors),
            clearance_envelope_margin=get_number(d, "clearance_envelope_margin", 3.0e-3, errors, non_negative=True),
            checks=sub(d, "checks", errors),
            description=get_str(d, "description", "", errors),
        )
        for ctx in (pctx, cctx, vctx, octx):
            errors.extend(ctx)
        errors.raise_if_any()
        return params


def resolve_coldplate(d: dict) -> dict:
    p = ColdPlateParams.from_dict(d)
    errors = Errors()
    warnings: List[str] = []
    L, W, T = p.length, p.width, p.thickness
    wc, dc, n = p.channel_width, p.channel_depth, p.passes

    errors.check(T - dc >= p.min_wall, f"channel depth {dc:.4g} m leaves less than min_wall {p.min_wall:.4g} m above the channel")
    avail = W - 2 * p.edge_margin
    if n > 1:
        pitch = p.pitch if p.pitch is not None else (avail - wc) / (n - 1)
        errors.check(pitch - wc >= p.min_wall, f"web between passes {pitch - wc:.4g} m is below min_wall {p.min_wall:.4g} m")
    else:
        pitch = 0.0
    span = (n - 1) * pitch + wc
    errors.check(span <= avail + 1e-12, f"{n} passes at pitch {pitch:.4g} m need {span:.4g} m; available width {avail:.4g} m")
    errors.raise_if_any()

    ys = [-0.5 * (n - 1) * pitch + k * pitch for k in range(n)]
    x_min, x_max = -0.5 * L + p.end_margin, 0.5 * L - p.end_margin
    r_o = 0.5 * pitch + 0.5 * wc
    r_i = 0.5 * pitch - 0.5 * wc
    straights, turns = [], []
    for k in range(n):
        turn_pos = (k % 2 == 0 and k < n - 1) or (k % 2 == 1)
        turn_neg = (k % 2 == 1 and k < n - 1) or (k % 2 == 0 and k > 0)
        xa = x_min + r_o if turn_neg else x_min
        xb = x_max - r_o if turn_pos else x_max
        errors.check(xb - xa > 0, f"pass {k}: plate too short for the turn radius (straight length {xb - xa:.4g} m)")
        straights.append({"index": k, "x": [xa, xb], "y_centre": ys[k], "y": [ys[k] - 0.5 * wc, ys[k] + 0.5 * wc]})
        if k < n - 1:
            side = "+x" if k % 2 == 0 else "-x"
            cx = x_max - r_o if side == "+x" else x_min + r_o
            turns.append({"between": [k, k + 1], "side": side, "centre": [cx, 0.5 * (ys[k] + ys[k + 1])],
                          "outer_radius": r_o, "inner_radius": r_i})
    errors.raise_if_any()
    inlet_side = "-x"
    outlet_side = "+x" if (n - 1) % 2 == 0 else "-x"
    z_c = 0.5 * dc
    ports = []
    for tag, side, y in (("inlet", inlet_side, ys[0]), ("outlet", outlet_side, ys[-1])):
        sgn = -1.0 if side == "-x" else 1.0
        x_face = sgn * 0.5 * L
        x_chan = x_min if side == "-x" else x_max
        ports.append({"name": tag, "side": side, "y": y, "z": z_c, "x_face": x_face,
                      "bore": {"x": sorted([x_chan, x_face]), "diameter": p.port_bore},
                      "boss": {"x": sorted([x_face, x_face + sgn * p.port_length]), "outer_diameter": p.port_outer_diameter,
                               "length": p.port_length, "material": p.port_material}})
    cover_t = p.cover_thickness or 0.0
    r_boss = 0.5 * p.port_outer_diameter
    errors.check(p.port_bore < p.port_outer_diameter, "port bore must be smaller than the boss outer diameter")
    errors.check(p.port_bore <= min(wc, dc) + 1e-12, "port bore must not exceed the channel width/depth")
    errors.check(r_boss <= z_c + cover_t + 1e-12 and r_boss <= T - z_c + 1e-12,
                 f"port boss radius {r_boss:.4g} m does not fit on the end face (plate {T:.4g} m + cover {cover_t:.4g} m)")
    errors.check(abs(ys[0]) + r_boss <= 0.5 * W and abs(ys[-1]) + r_boss <= 0.5 * W, "port boss leaves the plate width")

    channel_rect = [x_min, ys[0] - 0.5 * wc, x_max, ys[-1] + 0.5 * wc]
    mounting = None
    if p.mounting_holes:
        dia, inset = p.mounting_holes["diameter"], p.mounting_holes["inset"]
        errors.check(inset > 0.5 * dia, "mounting hole inset must exceed the hole radius")
        holes = [[sx * (0.5 * L - inset), sy * (0.5 * W - inset)] for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
        for hx, hy in holes:
            if _circle_rect_distance(hx, hy, channel_rect) < 0.5 * dia + p.min_wall:
                errors.add(f"mounting hole at ({hx:.4g}, {hy:.4g}) m is within min_wall of the channel")
            for port in ports:
                bx = port["bore"]["x"]
                rect = [bx[0], port["y"] - 0.5 * p.port_bore, bx[1], port["y"] + 0.5 * p.port_bore]
                if _circle_rect_distance(hx, hy, rect) < 0.5 * dia + p.min_wall:
                    errors.add(f"mounting hole at ({hx:.4g}, {hy:.4g}) m is within min_wall of the {port['name']} bore")
        mounting = {"diameter": dia, "inset": inset, "holes": holes}

    devices = [resolve_device(dev, T, L, W, errors, warnings, screw_depth=p.screw_hole_depth, plate_net=p.net) for dev in p.devices]
    for i in range(len(devices)):
        for j in range(i + 1, len(devices)):
            if _rect_overlap(devices[i]["body_footprint"], devices[j]["body_footprint"]) or \
                    _rect_overlap(devices[i]["pad_footprint"] or devices[i]["tab_footprint"],
                                  devices[j]["pad_footprint"] or devices[j]["tab_footprint"]):
                errors.add(f"devices {devices[i]['name']} and {devices[j]['name']} overlap")
    for dev in devices:
        hx, hy = dev["hole_xy"]
        r = 0.5 * dev["screw_hole_diameter"]
        depth = p.screw_hole_depth
        errors.check(depth < T, f"device {dev['name']}: screw hole depth {depth:.4g} m exceeds the plate thickness")
        over_channel = _circle_rect_distance(hx, hy, channel_rect) < r + p.min_wall
        if not over_channel:
            for turn in turns:  # turns bulge beyond the straight channel rectangle in X
                cx, cy = turn["centre"]
                if math.hypot(hx - cx, hy - cy) < turn["outer_radius"] + r + p.min_wall:
                    over_channel = True
        if over_channel and depth > T - dc - p.min_wall + 1e-12:
            errors.add(f"device {dev['name']}: screw hole (depth {depth:.4g} m) would break into the coolant channel; "
                       f"max depth over the channel is {T - dc - p.min_wall:.4g} m")
        if mounting:
            for hx2, hy2 in mounting["holes"]:
                fp = dev["pad_footprint"] or dev["tab_footprint"]
                if _circle_rect_distance(hx2, hy2, fp) < 0.5 * mounting["diameter"] or \
                        _circle_rect_distance(hx2, hy2, dev["body_footprint"]) < 0.5 * mounting["diameter"]:
                    errors.add(f"mounting hole at ({hx2:.4g}, {hy2:.4g}) m intersects device {dev['name']}")
    errors.raise_if_any()

    # analytic volumes
    straight_vol = sum((s["x"][1] - s["x"][0]) * wc * dc for s in straights)
    turn_vol = sum(g2.half_annulus_area(r_o, max(r_i, 0.0)) * dc for _ in turns)
    bore_vol = sum(math.pi * (0.5 * p.port_bore) ** 2 * (port["bore"]["x"][1] - port["bore"]["x"][0]) for port in ports)
    channel_vol = straight_vol + turn_vol
    rho = density(p.material, p.density_override)
    plate_gross = L * W * T
    mount_vol_plate = 4 * math.pi * (0.5 * mounting["diameter"]) ** 2 * T if mounting else 0.0
    screw_vol = sum(math.pi * (0.5 * dev["screw_hole_diameter"]) ** 2 * p.screw_hole_depth for dev in devices)
    plate_vol = plate_gross - channel_vol - bore_vol - mount_vol_plate - screw_vol
    cover_vol = (L * W * cover_t - (4 * math.pi * (0.5 * mounting["diameter"]) ** 2 * cover_t if mounting else 0.0)) if cover_t else 0.0
    boss_vol = sum(0.25 * math.pi * (p.port_outer_diameter ** 2 - p.port_bore ** 2) * p.port_length for _ in ports)
    z_top_devices = max([T] + [dev["top_z"] for dev in devices])
    env = {"margin": p.clearance_envelope_margin,
           "bbox": [-0.5 * L - (p.port_length if inlet_side == "-x" or outlet_side == "-x" else 0.0), -0.5 * W, -cover_t,
                    0.5 * L + (p.port_length if outlet_side == "+x" else 0.0), 0.5 * W, z_top_devices]}
    mesh_hints = {
        "target": "gmsh", "units": "m",
        "import_note": "Import the STEP with gmsh.model.occ.importShapes; the 'coolant' solid is the fluid domain; map other solids by STEP product names.",
        "regions": [
            {"bodies": ["plate"], "group": "coldplate", "material": p.material, "element_size": max(T / 3.0, 1.0e-3)},
            {"bodies": ["coolant"], "group": "fluid", "material": p.coolant_material, "element_size": max(wc / 6.0, 0.5e-3),
             "note": "fluid domain; add boundary layers at the channel walls; inlet/outlet faces at the port bore ends"},
        ] + ([{"bodies": ["cover"], "group": "coldplate_cover", "material": p.cover_material, "element_size": max(cover_t / 2.0, 0.75e-3)}] if cover_t else [])
        + [{"bodies": [f"{port['name']}_boss"], "group": "ports", "material": p.port_material, "element_size": 1.5e-3} for port in ports]
        + [{"bodies": [f"{dev['name']}.tab", f"{dev['name']}.body"], "group": f"device_{dev['name']}", "material": dev["materials"]["tab"],
            "element_size": 1.0e-3, "note": "heat source: tab/die region"} for dev in devices]
        + [{"bodies": [f"{dev['name']}.pad"], "group": "isolation_pads", "material": dev["materials"]["pad"],
            "element_size": max(dev["pad"]["thickness"], 0.1e-3)} for dev in devices if dev["pad"]],
        "refinement_zones": [{"name": f"turn_{t_['between'][0]}_{t_['between'][1]}", "element_size": max(wc / 8.0, 0.4e-3),
                              "bbox": [t_["centre"][0] - r_o, t_["centre"][1] - r_o, 0.0, t_["centre"][0] + r_o, t_["centre"][1] + r_o, dc]}
                             for t_ in turns],
    }
    return {
        "kind": "coldplate", "name": p.name, "description": p.description, "units": "SI (m, kg)",
        "plate": {"length": L, "width": W, "thickness": T, "material": p.material, "density": rho, "net": p.net, "z_top": T},
        "channel": {"width": wc, "depth": dc, "passes": n, "pitch": pitch, "span": span, "edge_margin": p.edge_margin,
                    "end_margin": p.end_margin, "min_wall": p.min_wall, "pass_y": ys, "x_range": [x_min, x_max],
                    "turn_outer_radius": r_o, "turn_inner_radius": r_i, "straights": straights, "turns": turns,
                    "inlet_side": inlet_side, "outlet_side": outlet_side, "rect": channel_rect,
                    "coolant_material": p.coolant_material, "coolant_density": density(p.coolant_material),
                    "wetted_length_centreline": sum(s["x"][1] - s["x"][0] for s in straights) + len(turns) * math.pi * 0.5 * pitch},
        "cover": {"thickness": cover_t, "material": p.cover_material, "z": [-cover_t, 0.0]} if cover_t else None,
        "ports": ports, "devices": devices, "mounting_holes": mounting, "screw_hole_depth": p.screw_hole_depth,
        "envelope": env, "warnings": warnings,
        "analytic": {"plate_gross_volume": plate_gross, "channel_volume": channel_vol, "port_bore_volume": bore_vol,
                     "coolant_volume": channel_vol + bore_vol, "coolant_mass": (channel_vol + bore_vol) * density(p.coolant_material),
                     "plate_volume": plate_vol, "plate_mass": plate_vol * rho, "cover_volume": cover_vol,
                     "cover_mass": cover_vol * density(p.cover_material), "boss_volume": boss_vol,
                     "boss_mass": boss_vol * density(p.port_material)},
        "checks": p.checks, "mesh_hints": mesh_hints,
    }
