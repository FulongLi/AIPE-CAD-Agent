"""Transformer solids from a resolved parameter dictionary (inside FreeCAD, mm)."""
from __future__ import annotations

from typing import List

from ._doc import ROLE_ENVELOPE, Body
from ._shapes import (annular_rounded_prism, bbox_of, box, box_centred, cut_all, cylinder_z, fuse_all, mirror_z, mm,
                      rect_ring_xz, rounded_box_centred)


def e_core_half(core: dict, gap_half_m: float, upper: bool):
    A, B, F = mm(core["total_width"]), mm(core["half_height"]), mm(core["depth"])
    D, C, E = mm(core["window_height"]), mm(core["inner_width"]), mm(core["centre_leg_width"])
    w = 0.5 * (C - E)
    half = box(A, F, B, (-0.5 * A, -0.5 * F, -B))
    win_neg = box(w, F + 2.0, D + 1.0, (-0.5 * C, -0.5 * F - 1.0, -D))
    win_pos = box(w, F + 2.0, D + 1.0, (0.5 * E, -0.5 * F - 1.0, -D))
    half = half.cut(win_neg).cut(win_pos)
    gap_half = mm(gap_half_m)
    if gap_half > 1e-9:
        tool = box(C - 0.02, F + 2.0, gap_half + 1.0, (-0.5 * C + 0.01, -0.5 * F - 1.0, -gap_half))
        half = half.cut(tool)
    return mirror_z(half) if upper else half


def bobbin_solid(bob: dict):
    ti, to = [mm(v) for v in bob["tube_inner"]], [mm(v) for v in bob["tube_outer"]]
    h = mm(bob["tube_height"])
    r_out, r_in = mm(bob["corner_radius_outer"]), mm(bob["corner_radius_inner"])
    fx, fy, tf = [mm(v) for v in bob["flange_size"]]
    tube = annular_rounded_prism(ti[0], ti[1], r_in, 0.5 * (to[0] - ti[0]), -0.5 * h, 0.5 * h)
    rings = []
    for z0, z1 in bob["flange_z"]:
        plate = box_centred(fx, fy, mm(z1) - mm(z0), (0.0, 0.0, 0.5 * (mm(z0) + mm(z1))))
        hole = rounded_box_centred(to[0], to[1], mm(z0) - 1.0, mm(z1) + 1.0, r_out)
        rings.append(plate.cut(hole))
    return fuse_all([tube] + rings)


def annular_body(item: dict):
    inner = [mm(v) for v in item["inner_dims"]]
    return annular_rounded_prism(inner[0], inner[1], mm(item["corner_radius_inner"]), mm(item["thickness"]),
                                 mm(item["z0"]), mm(item["z1"]))


def build_transformer(res: dict) -> List[Body]:
    core = res["core_params"]
    core_mat, core_net = res["core"]["material"], res["core"]["net"]
    bodies: List[Body] = []
    half_vol = res["core"]["half_volume"]
    bodies.append(Body("core_lower", e_core_half(core, 0.5 * core["air_gap"], upper=False), core_mat, net=core_net,
                       meta={"analytic_volume_m3": half_vol}))
    bodies.append(Body("core_upper", e_core_half(core, 0.5 * core["air_gap"], upper=True), core_mat, net=core_net,
                       meta={"analytic_volume_m3": half_vol}))
    bob = res["bobbin"]
    bodies.append(Body("bobbin", bobbin_solid(bob), bob["material"], meta={"analytic_volume_m3": bob["volume"]}))
    for w in res["windings"]:
        bodies.append(Body(w["name"], annular_body(w), w["material"], net=w["net"], density_override=w["effective_density"],
                           meta={"analytic_volume_m3": w["volume"], "note": f"homogenised {w['conductor_type']} winding body, "
                                                                            f"{w['turns']} turns in {w['layers']} layer(s)"}))
    for b in res["barriers"]:
        bodies.append(Body(b["name"], annular_body(b), b["material"], meta={"analytic_volume_m3": b["volume"]}))
    for m in res["margin_fills"]:
        bodies.append(Body(m["name"], annular_body(m), m["material"], meta={"analytic_volume_m3": m["volume"]}))
    for t in res["terminals"]:
        bodies.append(Body(t["name"], cylinder_z(mm(t["diameter"]), mm(t["z0"]), mm(t["z1"]), mm(t["x"]), mm(t["y"])),
                           t["material"], net=t["net"], meta={"analytic_volume_m3": t["volume"], "connection": True}))
    mnt = res["mounting"]
    for clip in mnt["clips"]:
        ring = rect_ring_xz(mm(clip["inner_x"]), mm(clip["inner_z"]), mm(clip["thickness"]), mm(clip["width"]), mm(clip["y_centre"]))
        bodies.append(Body(clip["name"], ring, clip["material"], net=clip["net"], meta={"analytic_volume_m3": clip["volume"]}))
    if mnt["base_plate"]:
        bp = mnt["base_plate"]
        lx, ly, t = [mm(v) for v in bp["size"]]
        plate = box_centred(lx, ly, t, (0.0, 0.0, 0.5 * (mm(bp["z_top"]) + mm(bp["z_bottom"]))))
        holes = [cylinder_z(mm(bp["hole_diameter"]), mm(bp["z_bottom"]) - 1.0, mm(bp["z_top"]) + 1.0, mm(hx), mm(hy)) for hx, hy in bp["holes"]]
        bodies.append(Body(bp["name"], cut_all(plate, holes), bp["material"], net=bp["net"], meta={"analytic_volume_m3": bp["volume"]}))
    # clearance envelope around the structural bodies (terminal pins excluded: they connect to other parts)
    margin = mm(res["envelope"]["margin"])
    if margin > 0:
        bb = bbox_of([b.shape for b in bodies if not b.meta.get("connection")])
        env = box(bb[3] - bb[0] + 2 * margin, bb[4] - bb[1] + 2 * margin, bb[5] - bb[2] + 2 * margin,
                  (bb[0] - margin, bb[1] - margin, bb[2] - margin))
        bodies.append(Body("clearance_envelope", env, "air", role=ROLE_ENVELOPE,
                           meta={"note": f"bounding box of the transformer structure (pins excluded) expanded by {res['envelope']['margin']} m"}))
    for b in bodies:
        b.group = res["name"]
    return bodies
