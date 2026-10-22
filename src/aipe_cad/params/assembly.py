"""Converter assembly parameters: boards, transformer, cooling, connectors, chassis (SI, metres).

Common coordinate system
------------------------
* Origin at the centre of the chassis top face; X along the long axis, Z up.
* Heat sinks are placed with their base underside on the chassis top
  (fins pointing down through optional chassis cut-outs); the cold plate rests
  on its cover.  ``position`` of a cooling instance is the location of the
  component's local origin.
* The transformer position may use ``"on_chassis"`` for z so that its lowest
  point (base plate) rests on the chassis regardless of the core size.
* Boards are FR4 slabs defined by their bottom-face z.  Optional copper zones
  (thin conductive slabs with a net) and keep-out volumes are attached to them.
* Connectors may use ``"on_board:<board>"`` for z.

The resolver inlines ``$ref`` component parameter files, resolves every
component through its own resolver, derives placements, standoffs, device
lead holes in boards, chassis cut-outs/holes and the check configuration.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional

from ..materials import density
from .base import (Errors, ParameterError, check_known_keys, get_bool, get_int, get_number, get_str, get_vector,
                   is_number, resolve_refs, sub)
from .coldplate import resolve_coldplate
from .heatsink import resolve_heatsink, rot2d
from .transformer import resolve_transformer


def _position(d: dict, key: str, errors: Errors, allow_strings=(), default=(0.0, 0.0, 0.0)):
    """Position [x, y, z] where z may be one of ``allow_strings`` (resolved later)."""
    value = d.get(key, list(default))
    if not isinstance(value, (list, tuple)) or len(value) != 3 or not all(is_number(v) for v in value[:2]):
        errors.add(f"field '{key}' must be [x, y, z] (z may be one of {list(allow_strings)})")
        return [0.0, 0.0, 0.0]
    z = value[2]
    if isinstance(z, str):
        if z not in allow_strings and not any(z.startswith(s) for s in allow_strings if s.endswith(":")):
            errors.add(f"field '{key}': unsupported z mode '{z}'")
        return [float(value[0]), float(value[1]), z]
    if not is_number(z):
        errors.add(f"field '{key}': z must be a number or one of {list(allow_strings)}")
        return [float(value[0]), float(value[1]), 0.0]
    return [float(value[0]), float(value[1]), float(z)]


def _rotated_rect(cx, cy, lx, ly, deg):
    """Axis-aligned bounding rectangle of a rotated rectangle [xmin, ymin, xmax, ymax]."""
    pts = [rot2d(sx * 0.5 * lx, sy * 0.5 * ly, deg) for sx in (-1, 1) for sy in (-1, 1)]
    xs = [cx + p[0] for p in pts]
    ys = [cy + p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


class AssemblyParams:
    """Thin validated container; see :func:`resolve_assembly` for the derived data."""

    def __init__(self, d: dict, base_dir: Optional[Path] = None):
        if not isinstance(d, dict):
            raise ParameterError(["assembly parameters must be a JSON object"])
        d = resolve_refs(d, base_dir)
        errors = Errors()
        check_known_keys(d, {"kind", "name", "description", "chassis", "cooling", "transformer", "boards", "connectors",
                             "checks", "clearance_envelope_margin"}, errors)
        get_str(d, "kind", "assembly", errors, choices=["assembly"])
        self.name = get_str(d, "name", "assembly", errors)
        self.description = get_str(d, "description", "", errors)
        self.clearance_envelope_margin = get_number(d, "clearance_envelope_margin", 0.0, errors, non_negative=True)
        self.checks = sub(d, "checks", errors)

        chassis = d.get("chassis", {})
        self.chassis = None
        if chassis is not None:
            cctx = Errors("chassis")
            if not isinstance(chassis, dict):
                cctx.add("must be an object or null")
                chassis = {}
            check_known_keys(chassis, {"length", "width", "thickness", "material", "net", "cutouts_under_heatsinks",
                                       "cutout_clearance", "min_rim"}, cctx)
            self.chassis = {
                "length": get_number(chassis, "length", 0.4, cctx, positive=True),
                "width": get_number(chassis, "width", 0.25, cctx, positive=True),
                "thickness": get_number(chassis, "thickness", 3e-3, cctx, positive=True),
                "material": get_str(chassis, "material", "aluminium_6063", cctx),
                "net": get_str(chassis, "net", "pe", cctx),
                "cutouts_under_heatsinks": get_bool(chassis, "cutouts_under_heatsinks", True, cctx),
                "cutout_clearance": get_number(chassis, "cutout_clearance", 2e-3, cctx, non_negative=True),
                "min_rim": get_number(chassis, "min_rim", 3e-3, cctx, non_negative=True),
            }
            errors.extend(cctx)

        cooling = sub(d, "cooling", errors)
        kctx = Errors("cooling")
        check_known_keys(cooling, {"variant", "heatsink", "coldplate", "placements"}, kctx)
        self.cooling_variant = get_str(cooling, "variant", "heatsinks", kctx, choices=["heatsinks", "coldplate", "none"])
        self.heatsink_params = cooling.get("heatsink")
        self.coldplate_params = cooling.get("coldplate")
        placements = cooling.get("placements", [])
        if not isinstance(placements, list):
            kctx.add("placements must be a list")
            placements = []
        self.cooling_placements = []
        for i, pl in enumerate(placements):
            pctx = Errors(f"cooling.placements[{i}]")
            if not isinstance(pl, dict):
                pctx.add("must be an object")
                pl = {}
            check_known_keys(pl, {"name", "position", "rotation_deg", "device_net", "params"}, pctx)
            self.cooling_placements.append({
                "name": get_str(pl, "name", f"cooling_{i + 1}", pctx),
                "position": _position(pl, "position", pctx, allow_strings=("on_chassis",)),
                "rotation_deg": get_number(pl, "rotation_deg", 0.0, pctx),
                "device_net": get_str(pl, "device_net", None, pctx),
                "params": sub(pl, "params", pctx),
            })
            kctx.extend(pctx)
        if self.cooling_variant == "heatsinks":
            kctx.check(isinstance(self.heatsink_params, dict), "cooling.heatsink parameters are required for the heatsinks variant")
        if self.cooling_variant == "coldplate":
            kctx.check(isinstance(self.coldplate_params, dict), "cooling.coldplate parameters are required for the coldplate variant")
        names = [pl["name"] for pl in self.cooling_placements]
        kctx.check(len(set(names)) == len(names), "cooling placement names must be unique")
        errors.extend(kctx)

        tr = d.get("transformer")
        self.transformer = None
        if tr is not None:
            tctx = Errors("transformer")
            if not isinstance(tr, dict):
                tctx.add("must be an object or null")
                tr = {}
            check_known_keys(tr, {"name", "params", "position", "rotation_deg"}, tctx)
            self.transformer = {
                "name": get_str(tr, "name", "transformer", tctx),
                "params": sub(tr, "params", tctx),
                "position": _position(tr, "position", tctx, allow_strings=("on_chassis",), default=(0.0, 0.0, "on_chassis")),
                "rotation_deg": get_number(tr, "rotation_deg", 0.0, tctx),
            }
            tctx.check(bool(self.transformer["params"]), "transformer.params are required (inline or $ref)")
            errors.extend(tctx)

        boards = d.get("boards", [])
        if not isinstance(boards, list):
            errors.add("boards must be a list")
            boards = []
        self.boards = []
        for i, b in enumerate(boards):
            bctx = Errors(f"boards[{i}]")
            if not isinstance(b, dict):
                bctx.add("must be an object")
                b = {}
            check_known_keys(b, {"name", "size", "thickness", "position", "rotation_deg", "material", "copper_zones",
                                 "keepouts", "mounting_holes", "standoffs", "lead_holes"}, bctx)
            size = get_vector(b, "size", [0.1, 0.1], bctx, length=2)
            zones = []
            for j, z in enumerate(b.get("copper_zones", []) or []):
                zctx = Errors(f"boards[{i}].copper_zones[{j}]")
                if not isinstance(z, dict):
                    zctx.add("must be an object")
                    z = {}
                check_known_keys(z, {"name", "offset", "size", "net", "thickness", "side"}, zctx)
                zones.append({"name": get_str(z, "name", f"zone{j + 1}", zctx),
                              "offset": get_vector(z, "offset", [0.0, 0.0], zctx, length=2),
                              "size": get_vector(z, "size", [0.05, 0.05], zctx, length=2),
                              "net": get_str(z, "net", "unassigned", zctx),
                              "thickness": get_number(z, "thickness", 70e-6, zctx, positive=True),
                              "side": get_str(z, "side", "top", zctx, choices=["top", "bottom"])})
                bctx.extend(zctx)
            keepouts = []
            for j, k in enumerate(b.get("keepouts", []) or []):
                kctx2 = Errors(f"boards[{i}].keepouts[{j}]")
                if not isinstance(k, dict):
                    kctx2.add("must be an object")
                    k = {}
                check_known_keys(k, {"name", "offset", "size", "side"}, kctx2)
                keepouts.append({"name": get_str(k, "name", f"keepout{j + 1}", kctx2),
                                 "offset": get_vector(k, "offset", [0.0, 0.0], kctx2, length=2),
                                 "size": get_vector(k, "size", [0.05, 0.05, 0.02], kctx2, length=3),
                                 "side": get_str(k, "side", "top", kctx2, choices=["top", "bottom"])})
                bctx.extend(kctx2)
            mh = b.get("mounting_holes", {})
            if mh is None:
                mh_res = None
            else:
                if not isinstance(mh, dict):
                    bctx.add("mounting_holes must be an object or null")
                    mh = {}
                check_known_keys(mh, {"diameter", "inset"}, bctx)
                mh_res = {"diameter": get_number(mh, "diameter", 3.2e-3, bctx, positive=True),
                          "inset": get_number(mh, "inset", 5e-3, bctx, positive=True)}
            so = sub(b, "standoffs", bctx)
            check_known_keys(so, {"enabled", "diameter", "material", "net"}, bctx)
            standoffs = {"enabled": get_bool(so, "enabled", True, bctx),
                         "diameter": get_number(so, "diameter", 6e-3, bctx, positive=True),
                         "material": get_str(so, "material", "nylon_pa66", bctx),
                         "net": get_str(so, "net", None, bctx)}
            lh = sub(b, "lead_holes", bctx)
            check_known_keys(lh, {"enabled", "clearance"}, bctx)
            lead_holes = {"enabled": get_bool(lh, "enabled", True, bctx),
                          "clearance": get_number(lh, "clearance", 0.4e-3, bctx, non_negative=True)}
            self.boards.append({
                "name": get_str(b, "name", f"board{i + 1}", bctx), "size": size,
                "thickness": get_number(b, "thickness", 1.6e-3, bctx, positive=True),
                "position": _position(b, "position", bctx),
                "rotation_deg": get_number(b, "rotation_deg", 0.0, bctx),
                "material": get_str(b, "material", "fr4", bctx),
                "copper_zones": zones, "keepouts": keepouts, "mounting_holes": mh_res, "standoffs": standoffs,
                "lead_holes": lead_holes,
            })
            errors.extend(bctx)
        names = [b["name"] for b in self.boards]
        errors.check(len(set(names)) == len(names), "board names must be unique")

        connectors = d.get("connectors", [])
        if not isinstance(connectors, list):
            errors.add("connectors must be a list")
            connectors = []
        self.connectors = []
        for i, c in enumerate(connectors):
            cctx = Errors(f"connectors[{i}]")
            if not isinstance(c, dict):
                cctx.add("must be an object")
                c = {}
            check_known_keys(c, {"name", "type", "position", "rotation_deg", "body_size", "poles", "pole_pitch",
                                 "pin_diameter", "pin_length", "net", "housing_material", "pin_material"}, cctx)
            self.connectors.append({
                "name": get_str(c, "name", f"connector{i + 1}", cctx),
                "type": get_str(c, "type", "dc_terminal_block", cctx, choices=["dc_terminal_block"]),
                "position": _position(c, "position", cctx, allow_strings=("on_board:",)),
                "rotation_deg": get_number(c, "rotation_deg", 0.0, cctx),
                "body_size": get_vector(c, "body_size", [0.03, 0.02, 0.02], cctx, length=3),
                "poles": get_int(c, "poles", 2, cctx, minimum=1),
                "pole_pitch": get_number(c, "pole_pitch", 12.5e-3, cctx, positive=True),
                "pin_diameter": get_number(c, "pin_diameter", 6e-3, cctx, positive=True),
                "pin_length": get_number(c, "pin_length", 8e-3, cctx, positive=True),
                "net": get_str(c, "net", "unassigned", cctx),
                "housing_material": get_str(c, "housing_material", "nylon_pa66", cctx),
                "pin_material": get_str(c, "pin_material", "brass", cctx),
            })
            errors.extend(cctx)
        errors.raise_if_any()


def resolve_assembly(d: dict, base_dir: Optional[Path] = None) -> dict:
    p = AssemblyParams(d, base_dir=base_dir)
    errors = Errors()
    warnings: List[str] = []
    chassis = p.chassis
    chassis_top = 0.0
    instances = []       # cooling instances
    supports = []        # (footprint rect, top z) surfaces that standoffs may rest on
    chassis_cutouts = []
    chassis_holes = []

    # --- cooling ---------------------------------------------------------------
    if p.cooling_variant != "none":
        base_params = p.heatsink_params if p.cooling_variant == "heatsinks" else p.coldplate_params
        resolver = resolve_heatsink if p.cooling_variant == "heatsinks" else resolve_coldplate
        for pl in p.cooling_placements:
            params = dict(base_params)
            params.update(pl["params"])
            params["name"] = pl["name"]
            if pl["device_net"] is not None:
                params["devices"] = [dict(dev, net=pl["device_net"], lead_nets=None) for dev in params.get("devices", [])]
            try:
                comp = resolver(params)
            except ParameterError as exc:
                errors.add(f"cooling instance '{pl['name']}': " + "; ".join(exc.messages))
                continue
            x, y, z = pl["position"]
            if z == "on_chassis":
                z = chassis_top - comp["envelope"]["bbox"][2] if p.cooling_variant == "coldplate" else chassis_top
            rot = pl["rotation_deg"]
            if p.cooling_variant == "heatsinks":
                L, W = comp["base"]["length"], comp["base"]["width"]
                top = z + comp["base"]["thickness"]
                fin_rect = _rotated_rect(x, y, comp["fins"]["length"], comp["fins"]["span"], rot)
                if chassis and chassis["cutouts_under_heatsinks"]:
                    cc = chassis["cutout_clearance"]
                    cut = [fin_rect[0] - cc, fin_rect[1] - cc, fin_rect[2] + cc, fin_rect[3] + cc]
                    base_rect = _rotated_rect(x, y, L, W, rot)
                    rim = min(cut[0] - base_rect[0], cut[1] - base_rect[1], base_rect[2] - cut[2], base_rect[3] - cut[3])
                    if rim < chassis["min_rim"]:
                        errors.add(f"heat sink '{pl['name']}': base rim around the chassis cut-out is {rim:.4g} m "
                                   f"(< min_rim {chassis['min_rim']:.4g} m); widen the base or reduce the fin span")
                    chassis_cutouts.append({"owner": pl["name"], "rect": cut})
                    if comp["mounting_holes"]:
                        for hx, hy in comp["mounting_holes"]["holes"]:
                            ax, ay = rot2d(hx, hy, rot)
                            gx, gy = x + ax, y + ay
                            inside = cut[0] - 0.5 * comp["mounting_holes"]["diameter"] < gx < cut[2] + 0.5 * comp["mounting_holes"]["diameter"] and \
                                cut[1] - 0.5 * comp["mounting_holes"]["diameter"] < gy < cut[3] + 0.5 * comp["mounting_holes"]["diameter"]
                            if inside:
                                errors.add(f"heat sink '{pl['name']}': mounting hole at ({gx:.4g}, {gy:.4g}) m falls in the chassis cut-out")
                            chassis_holes.append({"owner": pl["name"], "xy": [gx, gy], "diameter": comp["mounting_holes"]["diameter"]})
                elif comp["mounting_holes"]:
                    for hx, hy in comp["mounting_holes"]["holes"]:
                        ax, ay = rot2d(hx, hy, rot)
                        chassis_holes.append({"owner": pl["name"], "xy": [x + ax, y + ay], "diameter": comp["mounting_holes"]["diameter"]})
                supports.append({"rect": _rotated_rect(x, y, L, W, rot), "z_top": top, "owner": pl["name"]})
            else:
                L, W = comp["plate"]["length"], comp["plate"]["width"]
                top = z + comp["plate"]["thickness"]
                if comp["mounting_holes"]:
                    for hx, hy in comp["mounting_holes"]["holes"]:
                        ax, ay = rot2d(hx, hy, rot)
                        chassis_holes.append({"owner": pl["name"], "xy": [x + ax, y + ay], "diameter": comp["mounting_holes"]["diameter"]})
                supports.append({"rect": _rotated_rect(x, y, L, W, rot), "z_top": top, "owner": pl["name"]})
            # device lead tops in the assembly frame
            leads = []
            for dev in comp["devices"]:
                for ld in dev["leads"]:
                    lx, ly = ld["axis_xy"]
                    ax, ay = rot2d(lx, ly, rot)
                    z_root = ld["vertical_local"]["z"][0] if ld["vertical_local"] else ld["horizontal_local"]["z"][0]
                    leads.append({"device": dev["name"], "lead": ld["name"], "net": ld["net"], "xy": [x + ax, y + ay],
                                  "z_root": z + z_root, "z_top": z + ld["top_z"],
                                  "size": max(ld["width"], ld["thickness"])})
            instances.append({"name": pl["name"], "kind": comp["kind"], "position": [x, y, z], "rotation_deg": rot,
                              "resolved": comp, "device_leads": leads, "z_top": top})
            warnings.extend(f"{pl['name']}: {w}" for w in comp["warnings"])

    # --- transformer -----------------------------------------------------------
    transformer = None
    if p.transformer:
        try:
            comp = resolve_transformer(dict(p.transformer["params"], name=p.transformer["name"]))
            x, y, z = p.transformer["position"]
            if z == "on_chassis":
                z = chassis_top - comp["envelope"]["bbox"][2]
            transformer = {"name": p.transformer["name"], "position": [x, y, z], "rotation_deg": p.transformer["rotation_deg"],
                           "resolved": comp}
            warnings.extend(f"{p.transformer['name']}: {w}" for w in comp["warnings"])
            if comp["mounting"]["base_plate"]:
                bp = comp["mounting"]["base_plate"]
                for hx, hy in bp["holes"]:
                    ax, ay = rot2d(hx, hy, p.transformer["rotation_deg"])
                    chassis_holes.append({"owner": p.transformer["name"], "xy": [x + ax, y + ay], "diameter": bp["hole_diameter"]})
        except ParameterError as exc:
            errors.add("transformer: " + "; ".join(exc.messages))

    # --- boards --------------------------------------------------------------------
    boards = []
    all_leads = [ld for inst in instances for ld in inst["device_leads"]]
    for b in p.boards:
        x, y, z = b["position"]
        lx, ly, t = b["size"][0], b["size"][1], b["thickness"]
        rot = b["rotation_deg"]
        rect = _rotated_rect(x, y, lx, ly, rot)
        holes = []
        standoffs = []
        if b["mounting_holes"]:
            dia, inset = b["mounting_holes"]["diameter"], b["mounting_holes"]["inset"]
            errors.check(inset > 0.5 * dia, f"board '{b['name']}': mounting hole inset must exceed the hole radius")
            for sx in (-1.0, 1.0):
                for sy in (-1.0, 1.0):
                    ax, ay = rot2d(sx * (0.5 * lx - inset), sy * (0.5 * ly - inset), rot)
                    gx, gy = x + ax, y + ay
                    holes.append({"xy": [gx, gy], "diameter": dia})
                    if b["standoffs"]["enabled"]:
                        z_support = chassis_top
                        owner = "chassis"
                        for s in supports:
                            if s["rect"][0] <= gx <= s["rect"][2] and s["rect"][1] <= gy <= s["rect"][3]:
                                z_support, owner = s["z_top"], s["owner"]
                        height = z - z_support
                        if height <= 0:
                            errors.add(f"board '{b['name']}': standoff at ({gx:.4g}, {gy:.4g}) m has non-positive height "
                                       f"(board z {z:.4g} m, support {owner} top {z_support:.4g} m)")
                        standoffs.append({"name": f"standoff_{len(standoffs) + 1}", "xy": [gx, gy], "z0": z_support, "z1": z,
                                          "diameter": b["standoffs"]["diameter"], "material": b["standoffs"]["material"],
                                          "net": b["standoffs"]["net"], "support": owner, "hole_diameter": dia})
        lead_holes = []
        if b["lead_holes"]["enabled"]:
            for ld in all_leads:
                gx, gy = ld["xy"]
                if rect[0] <= gx <= rect[2] and rect[1] <= gy <= rect[3]:
                    if ld["z_root"] < z and ld["z_top"] > z:
                        if ld["z_top"] < z + t:
                            warnings.append(f"board '{b['name']}': lead {ld['device']}.{ld['lead']} ends inside the board "
                                            f"(top {ld['z_top']:.4g} m < board top {z + t:.4g} m)")
                        lead_holes.append({"xy": [gx, gy], "diameter": ld["size"] + 2 * b["lead_holes"]["clearance"],
                                           "device": ld["device"], "lead": ld["lead"]})
                    elif ld["z_root"] < z and ld["z_top"] <= z:
                        warnings.append(f"board '{b['name']}': lead {ld['device']}.{ld['lead']} does not reach the board "
                                        f"(top {ld['z_top']:.4g} m < board bottom {z:.4g} m)")
        zones = []
        for zn in b["copper_zones"]:
            zx, zy = rot2d(zn["offset"][0], zn["offset"][1], rot)
            z0 = z + t if zn["side"] == "top" else z - zn["thickness"]
            zones.append(dict(zn, centre=[x + zx, y + zy], z0=z0, z1=z0 + zn["thickness"]))
            zr = _rotated_rect(x + zx, y + zy, zn["size"][0], zn["size"][1], rot)
            if zr[0] < rect[0] - 1e-9 or zr[1] < rect[1] - 1e-9 or zr[2] > rect[2] + 1e-9 or zr[3] > rect[3] + 1e-9:
                errors.add(f"board '{b['name']}': copper zone '{zn['name']}' leaves the board outline")
        keepouts = []
        for ko in b["keepouts"]:
            kx, ky = rot2d(ko["offset"][0], ko["offset"][1], rot)
            z0 = z + t if ko["side"] == "top" else z - ko["size"][2]
            keepouts.append(dict(ko, centre=[x + kx, y + ky], z0=z0, z1=z0 + ko["size"][2], owner=b["name"]))
        vol = lx * ly * t - sum(math.pi * (0.5 * h["diameter"]) ** 2 * t for h in holes) \
            - sum(math.pi * (0.5 * h["diameter"]) ** 2 * t for h in lead_holes)
        boards.append({"name": b["name"], "size": [lx, ly, t], "position": [x, y, z], "rotation_deg": rot, "rect": rect,
                       "z_top": z + t, "material": b["material"], "mounting_holes": holes, "standoffs": standoffs,
                       "lead_holes": lead_holes, "copper_zones": zones, "keepouts": keepouts,
                       "analytic": {"volume": vol, "mass": vol * density(b["material"]),
                                    "standoff_mass": sum(math.pi * (0.5 * s["diameter"]) ** 2 * (s["z1"] - s["z0"]) * density(s["material"])
                                                         for s in standoffs)}})

    # --- connectors -------------------------------------------------------------------
    connectors = []
    for c in p.connectors:
        x, y, z = c["position"]
        if isinstance(z, str):
            bname = z.split(":", 1)[1]
            match = [b for b in boards if b["name"] == bname]
            if not match:
                errors.add(f"connector '{c['name']}': unknown board '{bname}' in position z")
                z = 0.0
            else:
                z = match[0]["z_top"]
        bx, by, bz = c["body_size"]
        pins = []
        for k in range(c["poles"]):
            px, py = rot2d((k - 0.5 * (c["poles"] - 1)) * c["pole_pitch"], 0.0, c["rotation_deg"])
            pins.append({"name": f"pin{k + 1}", "xy": [x + px, y + py], "z0": z + bz, "z1": z + bz + c["pin_length"],
                         "diameter": c["pin_diameter"]})
        span = (c["poles"] - 1) * c["pole_pitch"] + c["pin_diameter"]
        errors.check(span <= bx + 1e-12, f"connector '{c['name']}': pole row ({span:.4g} m) wider than the housing ({bx:.4g} m)")
        vol = bx * by * bz
        connectors.append(dict(c, position=[x, y, z], pins=pins, rect=_rotated_rect(x, y, bx, by, c["rotation_deg"]),
                               analytic={"housing_volume": vol, "housing_mass": vol * density(c["housing_material"]),
                                         "pin_mass": sum(math.pi * (0.5 * c["pin_diameter"]) ** 2 * c["pin_length"] * density(c["pin_material"]) for _ in pins)}))

    # --- chassis geometry -----------------------------------------------------------------
    chassis_res = None
    if chassis:
        L, W, t = chassis["length"], chassis["width"], chassis["thickness"]
        for cut in chassis_cutouts:
            r = cut["rect"]
            if r[0] < -0.5 * L or r[1] < -0.5 * W or r[2] > 0.5 * L or r[3] > 0.5 * W:
                errors.add(f"chassis cut-out for '{cut['owner']}' leaves the chassis outline")
        for h in chassis_holes:
            if abs(h["xy"][0]) + 0.5 * h["diameter"] > 0.5 * L or abs(h["xy"][1]) + 0.5 * h["diameter"] > 0.5 * W:
                errors.add(f"chassis hole for '{h['owner']}' at {h['xy']} m leaves the chassis outline")
        for b in boards:
            for s in b["standoffs"]:
                if s["support"] == "chassis":
                    chassis_holes.append({"owner": b["name"], "xy": s["xy"], "diameter": s["hole_diameter"]})
        cut_vol = sum((c["rect"][2] - c["rect"][0]) * (c["rect"][3] - c["rect"][1]) * t for c in chassis_cutouts)
        hole_vol = sum(math.pi * (0.5 * h["diameter"]) ** 2 * t for h in chassis_holes)
        vol = L * W * t - cut_vol - hole_vol
        chassis_res = {"length": L, "width": W, "thickness": t, "z": [-t, 0.0], "material": chassis["material"],
                       "net": chassis["net"], "cutouts": chassis_cutouts, "holes": chassis_holes,
                       "analytic": {"volume": vol, "mass": vol * density(chassis["material"])}}
    errors.raise_if_any()

    # --- checks configuration ---------------------------------------------------------------
    checks = dict(p.checks)
    fit_pairs = []
    if transformer:
        for fp in transformer["resolved"]["fit_pairs"]:
            fit_pairs.append(dict(fp, a=f"{transformer['name']}.{fp['a']}", b=f"{transformer['name']}.{fp['b']}"))
    checks.setdefault("fit_pairs", [])
    checks["fit_pairs"] = list(checks["fit_pairs"]) + fit_pairs

    # --- totals ---------------------------------------------------------------------------------
    masses = {}
    for inst in instances:
        comp = inst["resolved"]
        if comp["kind"] == "heatsink":
            masses[inst["name"]] = comp["analytic"]["mass_without_holes"]
        else:
            masses[inst["name"]] = comp["analytic"]["plate_mass"] + comp["analytic"]["cover_mass"] + comp["analytic"]["boss_mass"]
    if transformer:
        masses[transformer["name"]] = transformer["resolved"]["analytic_masses"]["total"]
    for b in boards:
        masses[b["name"]] = b["analytic"]["mass"] + b["analytic"]["standoff_mass"]
    for c in connectors:
        masses[c["name"]] = c["analytic"]["housing_mass"] + c["analytic"]["pin_mass"]
    if chassis_res:
        masses["chassis"] = chassis_res["analytic"]["mass"]
    masses["total_estimate"] = sum(masses.values())

    return {
        "kind": "assembly", "name": p.name, "description": p.description, "units": "SI (m, kg)",
        "coordinate_system": "origin at the chassis top-face centre; X long axis; Z up",
        "cooling_variant": p.cooling_variant, "cooling": instances, "transformer": transformer, "boards": boards,
        "connectors": connectors, "chassis": chassis_res, "clearance_envelope_margin": p.clearance_envelope_margin,
        "checks": checks, "warnings": warnings, "analytic_masses": masses,
        "mesh_hints": {"target": "gmsh", "units": "m",
                       "note": "Component-level mesh hints are nested under cooling[*].resolved.mesh_hints and transformer.resolved.mesh_hints; "
                               "body names in the assembly STEP are prefixed with the instance name."},
    }
