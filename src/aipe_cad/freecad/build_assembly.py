"""Converter assembly solids: places component bodies in the common frame (inside FreeCAD, mm)."""
from __future__ import annotations

from typing import List

from ._doc import ROLE_KEEPOUT, Body, prefixed
from ._shapes import box, box_centred, box_ranges, cut_all, cylinder_z, mm, place
from .build_heatsink import build_coldplate, build_heatsink
from .build_transformer import build_transformer


def _place_bodies(bodies: List[Body], position_m, rotation_deg: float) -> List[Body]:
    pos = (mm(position_m[0]), mm(position_m[1]), mm(position_m[2]))
    for b in bodies:
        b.shape = place(b.shape, pos, rotation_deg)
    return bodies


def build_assembly(res: dict) -> List[Body]:
    bodies: List[Body] = []
    # chassis
    ch = res["chassis"]
    if ch:
        L, W, t = mm(ch["length"]), mm(ch["width"]), mm(ch["thickness"])
        plate = box_centred(L, W, t, (0.0, 0.0, -0.5 * t))
        tools = []
        for cut in ch["cutouts"]:
            r = cut["rect"]
            tools.append(box_ranges((mm(r[0]), mm(r[2])), (mm(r[1]), mm(r[3])), (-t - 1.0, 1.0)))
        for hole in ch["holes"]:
            tools.append(cylinder_z(mm(hole["diameter"]), -t - 1.0, 1.0, mm(hole["xy"][0]), mm(hole["xy"][1])))
        plate = cut_all(plate, tools)
        bodies.append(Body("chassis.plate", plate, ch["material"], net=ch["net"], group="chassis",
                           meta={"analytic_volume_m3": ch["analytic"]["volume"], "note": "chassis plate with airflow cut-outs and mounting holes"}))
    # cooling instances
    for inst in res["cooling"]:
        comp = inst["resolved"]
        parts = build_heatsink(comp) if comp["kind"] == "heatsink" else build_coldplate(comp)
        _place_bodies(parts, inst["position"], inst["rotation_deg"])
        bodies.extend(prefixed(parts, inst["name"]))
    # transformer
    tr = res["transformer"]
    if tr:
        parts = build_transformer(tr["resolved"])
        _place_bodies(parts, tr["position"], tr["rotation_deg"])
        bodies.extend(prefixed(parts, tr["name"]))
    # boards
    for b in res["boards"]:
        lx, ly, t = [mm(v) for v in b["size"]]
        x, y, z = [mm(v) for v in b["position"]]
        rot = b["rotation_deg"]
        slab = box_centred(lx, ly, t, (0.0, 0.0, 0.5 * t))
        slab = place(slab, (x, y, z), rot)
        tools = [cylinder_z(mm(h["diameter"]), z - 1.0, z + t + 1.0, mm(h["xy"][0]), mm(h["xy"][1])) for h in b["mounting_holes"]]
        tools += [cylinder_z(mm(h["diameter"]), z - 1.0, z + t + 1.0, mm(h["xy"][0]), mm(h["xy"][1])) for h in b["lead_holes"]]
        slab = cut_all(slab, tools)
        bodies.append(Body(f"{b['name']}.board", slab, b["material"], group=b["name"],
                           meta={"analytic_volume_m3": b["analytic"]["volume"], "note": "board outline (dielectric)"}))
        # copper zones keep back from every hole (and the standoff footprint), and from connector footprints
        kb = mm(b.get("copper_keepback", 0.5e-3))
        standoff_d = max([mm(s["diameter"]) for s in b["standoffs"]] + [0.0])
        zone_tools = [cylinder_z(max(mm(h["diameter"]), standoff_d) + 2 * kb, z - 5.0, z + t + 5.0, mm(h["xy"][0]), mm(h["xy"][1]))
                      for h in b["mounting_holes"]]
        zone_tools += [cylinder_z(mm(h["diameter"]) + 2 * kb, z - 5.0, z + t + 5.0, mm(h["xy"][0]), mm(h["xy"][1])) for h in b["lead_holes"]]
        for c in res["connectors"]:
            cx, cy, cz = [mm(v) for v in c["position"]]
            if abs(cz - (z + t)) < 1e-6 or abs(cz - z) < 1e-6:
                bx, by, bz = [mm(v) for v in c["body_size"]]
                foot = place(box_centred(bx + 2 * kb, by + 2 * kb, t + 10.0, (0.0, 0.0, 0.0)), (cx, cy, z + 0.5 * t), c["rotation_deg"])
                zone_tools.append(foot)
        for zn in b["copper_zones"]:
            zone = box_centred(mm(zn["size"][0]), mm(zn["size"][1]), mm(zn["z1"]) - mm(zn["z0"]), (0.0, 0.0, 0.5 * (mm(zn["z0"]) + mm(zn["z1"]))))
            zone = place(zone, (mm(zn["centre"][0]), mm(zn["centre"][1]), 0.0), rot)
            zone = cut_all(zone, zone_tools)
            bodies.append(Body(f"{b['name']}.{zn['name']}", zone, "copper", net=zn["net"], group=b["name"],
                               meta={"note": "copper zone (conductive region used by the clearance checks; keep-back around holes and connectors)"}))
        for ko in b["keepouts"]:
            vol = box_centred(mm(ko["size"][0]), mm(ko["size"][1]), mm(ko["z1"]) - mm(ko["z0"]), (0.0, 0.0, 0.5 * (mm(ko["z0"]) + mm(ko["z1"]))))
            vol = place(vol, (mm(ko["centre"][0]), mm(ko["centre"][1]), 0.0), rot)
            bodies.append(Body(f"{b['name']}.keepout_{ko['name']}", vol, "air", role=ROLE_KEEPOUT, group=b["name"],
                               meta={"owner": b["name"], "note": "component keep-out volume"}))
        for s in b["standoffs"]:
            cyl = cylinder_z(mm(s["diameter"]), mm(s["z0"]), mm(s["z1"]), mm(s["xy"][0]), mm(s["xy"][1]))
            bodies.append(Body(f"{b['name']}.{s['name']}", cyl, s["material"], net=s["net"], group=b["name"],
                               meta={"note": f"standoff on {s['support']}"}))
    # connectors
    for c in res["connectors"]:
        bx, by, bz = [mm(v) for v in c["body_size"]]
        x, y, z = [mm(v) for v in c["position"]]
        housing = place(box_centred(bx, by, bz, (0.0, 0.0, 0.5 * bz)), (x, y, z), c["rotation_deg"])
        pin_tools = [cylinder_z(mm(p["diameter"]), z - 1.0, z + bz + 1.0, mm(p["xy"][0]), mm(p["xy"][1])) for p in c["pins"]]
        housing = cut_all(housing, pin_tools)
        bodies.append(Body(f"{c['name']}.housing", housing, c["housing_material"], group=c["name"]))
        for p in c["pins"]:
            pin = cylinder_z(mm(p["diameter"]), z, mm(p["z1"]), mm(p["xy"][0]), mm(p["xy"][1]))
            bodies.append(Body(f"{c['name']}.{p['name']}", pin, c["pin_material"], net=c["net"], group=c["name"],
                               meta={"connection": True}))
    return bodies
