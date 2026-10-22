"""Heat sink, cold plate and device solids from resolved dictionaries (inside FreeCAD, mm)."""
from __future__ import annotations

from typing import List

from ._doc import ROLE_ENVELOPE, ROLE_FLUID, Body
from ._shapes import (bbox_of, box, box_centred, box_ranges, cut_all, cylinder_x, cylinder_z, fuse_all, half_annulus_z,
                      mm, place)


def device_bodies(dev: dict, prefix: str) -> List[Body]:
    """Body, tab, pad and leads of one device placed on its plate (plate frame, mm)."""
    pk = dev["package"]
    L, Wb, A = mm(pk["body_length"]), mm(pk["body_width"]), mm(pk["body_thickness"])
    z_pad_top = mm(dev["z_pad_top"])
    tab_t = mm(pk["tab_thickness"])
    full = box_centred(L, Wb, A, (0.0, 0.0, z_pad_top + 0.5 * A))
    tl = dev["tab_local"]
    tab = box_ranges((mm(tl[0]), mm(tl[1])), (mm(tl[2]), mm(tl[3])), (z_pad_top, z_pad_top + tab_t))
    body = full.cut(tab)
    hx, hy = mm(dev["hole_local"][0]), mm(dev["hole_local"][1])
    hole = cylinder_z(mm(pk["hole_diameter"]), z_pad_top - 5.0, z_pad_top + A + 1.0, hx, hy)
    body = body.cut(hole)
    tab = tab.cut(hole)
    pos = (mm(dev["position"][0]), mm(dev["position"][1]), 0.0)
    rot = dev["rotation_deg"]
    out = [
        Body(f"{prefix}.body", place(body, pos, rot), pk["body_material"], meta={"analytic_volume_m3": dev["analytic"]["body_volume"]}),
        Body(f"{prefix}.tab", place(tab, pos, rot), pk["tab_material"], net=dev["net"], meta={"analytic_volume_m3": dev["analytic"]["tab_volume"]}),
    ]
    if dev["pad"]:
        pl = dev["pad_local"]
        pad = box_ranges((mm(pl[0]), mm(pl[1])), (mm(pl[2]), mm(pl[3])), (mm(dev["z_surface"]), z_pad_top)).cut(hole)
        out.append(Body(f"{prefix}.pad", place(pad, pos, rot), dev["pad"]["material"], density_override=dev["pad"].get("density"),
                        meta={"analytic_volume_m3": dev["analytic"]["pad_volume"], "note": "electrical isolation pad"}))
    for ld in dev["leads"]:
        h = ld["horizontal_local"]
        parts = [box_ranges((mm(h["x"][0]), mm(h["x"][1])), (mm(h["y"][0]), mm(h["y"][1])), (mm(h["z"][0]), mm(h["z"][1])))]
        v = ld["vertical_local"]
        if v:
            parts.append(box_ranges((mm(v["x"][0]), mm(v["x"][1])), (mm(v["y"][0]), mm(v["y"][1])), (mm(v["z"][0]), mm(v["z"][1]))))
        lead = fuse_all(parts)
        out.append(Body(f"{prefix}.lead_{ld['name']}", place(lead, pos, rot), ld["material"], net=ld["net"], meta={"connection": True}))
    fx = dev.get("fastener")
    if fx:
        if fx.get("bushing"):
            sl, sh = fx["sleeve"], fx["shoulder"]
            bore = mm(fx["screw_diameter"])
            sleeve = cylinder_z(mm(sl["outer_diameter"]), mm(sl["z"][0]), mm(sl["z"][1]), hx, hy)
            shoulder = cylinder_z(mm(sh["outer_diameter"]), mm(sh["z"][0]), mm(sh["z"][1]), hx, hy)
            bushing = fuse_all([sleeve, shoulder]).cut(cylinder_z(bore, mm(sl["z"][0]) - 1.0, mm(sh["z"][1]) + 1.0, hx, hy))
            out.append(Body(f"{prefix}.bushing", place(bushing, pos, rot), fx["bushing_material"],
                            meta={"analytic_volume_m3": fx["bushing_volume"], "note": "insulating shoulder bushing"}))
        if fx.get("screw"):
            hd, sk, en = fx["head"], fx["shank"], fx["engaged"]
            parts = [cylinder_z(mm(hd["diameter"]), mm(hd["z"][0]), mm(hd["z"][1]), hx, hy),
                     cylinder_z(mm(sk["diameter"]), mm(sk["z"][0]), mm(sk["z"][1]), hx, hy)]
            if en["z"][1] - en["z"][0] > 1e-9:
                parts.append(cylinder_z(mm(en["diameter"]), mm(en["z"][0]), mm(en["z"][1]), hx, hy))
            screw = fuse_all(parts)
            out.append(Body(f"{prefix}.screw", place(screw, pos, rot), fx["screw_material"], net=fx["screw_net"],
                            meta={"analytic_volume_m3": fx["screw_volume"], "note": "mounting screw (thread engagement not modelled)"}))
    return out


def plate_holes(dev: dict, z0: float, z1: float):
    """Screw hole cylinder for one device in the plate frame (mm)."""
    hx, hy = mm(dev["hole_xy"][0]), mm(dev["hole_xy"][1])
    return cylinder_z(mm(dev["screw_hole_diameter"]), z0, z1, hx, hy)


def _envelope(bodies: List[Body], margin_m: float, name_prefix: str, group: str) -> List[Body]:
    """Clearance envelope around the structural bodies (device leads excluded: they connect to a board)."""
    margin = mm(margin_m)
    if margin <= 0:
        return []
    bb = bbox_of([b.shape for b in bodies if not b.meta.get("connection")])
    env = box(bb[3] - bb[0] + 2 * margin, bb[4] - bb[1] + 2 * margin, bb[5] - bb[2] + 2 * margin,
              (bb[0] - margin, bb[1] - margin, bb[2] - margin))
    return [Body("clearance_envelope", env, "air", role=ROLE_ENVELOPE, group=group,
                 meta={"note": f"bounding box of {name_prefix} (leads excluded) expanded by {margin_m} m"})]


def build_heatsink(res: dict) -> List[Body]:
    base = res["base"]
    fins = res["fins"]
    L, W, tb = mm(base["length"]), mm(base["width"]), mm(base["thickness"])
    h, t = mm(fins["height"]), mm(fins["thickness"])
    solid = box_centred(L, W, tb, (0.0, 0.0, 0.5 * tb))
    fin_x = (mm(fins["x"][0]), mm(fins["x"][1]))
    fin_shapes = [box_ranges(fin_x, (mm(y) - 0.5 * t, mm(y) + 0.5 * t), (-h, 0.0)) for y in fins["positions"]]
    solid = fuse_all([solid] + fin_shapes)
    tools = []
    if res["mounting_holes"]:
        for hx, hy in res["mounting_holes"]["holes"]:
            tools.append(cylinder_z(mm(res["mounting_holes"]["diameter"]), -h - 1.0, tb + 1.0, mm(hx), mm(hy)))
    for dev in res["devices"]:
        tools.append(plate_holes(dev, -h - 1.0, tb + 1.0))
    solid = cut_all(solid, tools)
    bodies = [Body("body", solid, base["material"], net=base["net"], density_override=base.get("density"),
                   meta={"note": f"base plate with {fins['count']} fins (one extruded solid)"})]
    for dev in res["devices"]:
        bodies.extend(device_bodies(dev, dev["name"]))
    bodies.extend(_envelope(bodies, res["envelope"]["margin"], res["name"], res["name"]))
    for b in bodies:
        b.group = res["name"]
    return bodies


def channel_solid(ch: dict):
    d = mm(ch["depth"])
    parts = []
    for s in ch["straights"]:
        parts.append(box_ranges((mm(s["x"][0]), mm(s["x"][1])), (mm(s["y"][0]), mm(s["y"][1])), (0.0, d)))
    for turn in ch["turns"]:
        parts.append(half_annulus_z((mm(turn["centre"][0]), mm(turn["centre"][1])), mm(turn["outer_radius"]),
                                    mm(turn["inner_radius"]), 0.0, d, turn["side"]))
    return fuse_all(parts)


def build_coldplate(res: dict) -> List[Body]:
    plate = res["plate"]
    ch = res["channel"]
    L, W, T = mm(plate["length"]), mm(plate["width"]), mm(plate["thickness"])
    solid = box_centred(L, W, T, (0.0, 0.0, 0.5 * T))
    channel = channel_solid(ch)
    bores = [cylinder_x(mm(p["bore"]["diameter"]), mm(p["bore"]["x"][0]) - 0.5, mm(p["bore"]["x"][1]) + 0.5, mm(p["y"]), mm(p["z"]))
             for p in res["ports"]]
    coolant_parts = [channel] + [cylinder_x(mm(p["bore"]["diameter"]), mm(p["bore"]["x"][0]), mm(p["bore"]["x"][1]), mm(p["y"]), mm(p["z"]))
                                 for p in res["ports"]]
    tools = [channel] + bores
    cover_t = mm(res["cover"]["thickness"]) if res["cover"] else 0.0
    mount_tools = []
    if res["mounting_holes"]:
        for hx, hy in res["mounting_holes"]["holes"]:
            mount_tools.append(cylinder_z(mm(res["mounting_holes"]["diameter"]), -cover_t - 1.0, T + 1.0, mm(hx), mm(hy)))
    tools += mount_tools
    depth = mm(res["screw_hole_depth"])
    for dev in res["devices"]:
        tools.append(plate_holes(dev, T - depth, T + 1.0))
    solid = cut_all(solid, tools)
    bodies = [Body("plate", solid, plate["material"], net=plate["net"], density_override=plate.get("density"),
                   meta={"analytic_volume_m3": res["analytic"]["plate_volume"], "note": "cold plate with boolean-cut serpentine channel"})]
    coolant = fuse_all(coolant_parts)
    bodies.append(Body("coolant", coolant, ch["coolant_material"], role=ROLE_FLUID,
                       meta={"analytic_volume_m3": res["analytic"]["coolant_volume"], "note": "fluid domain (channel + port bores)"}))
    if res["cover"]:
        cover = box_centred(L, W, cover_t, (0.0, 0.0, -0.5 * cover_t))
        cover = cut_all(cover, mount_tools)
        bodies.append(Body("cover", cover, res["cover"]["material"], net=plate["net"],
                           meta={"analytic_volume_m3": res["analytic"]["cover_volume"]}))
    for p in res["ports"]:
        bx = p["boss"]["x"]
        boss = cylinder_x(mm(p["boss"]["outer_diameter"]), mm(bx[0]), mm(bx[1]), mm(p["y"]), mm(p["z"]))
        boss = boss.cut(cylinder_x(mm(p["bore"]["diameter"]), mm(bx[0]) - 1.0, mm(bx[1]) + 1.0, mm(p["y"]), mm(p["z"])))
        bodies.append(Body(f"{p['name']}_boss", boss, p["boss"]["material"], net=plate["net"],
                           meta={"analytic_volume_m3": res["analytic"]["boss_volume"] / len(res["ports"])}))
    for dev in res["devices"]:
        bodies.extend(device_bodies(dev, dev["name"]))
    bodies.extend(_envelope([b for b in bodies if b.role != ROLE_FLUID], res["envelope"]["margin"], res["name"], res["name"]))
    for b in bodies:
        b.group = res["name"]
    return bodies
