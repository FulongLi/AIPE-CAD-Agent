"""Interference, keep-out, fit and clearance checks on FreeCAD solids (inside FreeCAD).

* Interference: pairwise ``Part.Shape.common`` volume of all physical bodies
  whose bounding boxes intersect (touching bodies with zero common volume are
  reported as contacts, useful for conformal meshing / thermal contact).
* Keep-out / envelope: common volume of physical bodies with keep-out and
  clearance-envelope bodies.
* Fit: ``distToShape`` between two named bodies versus an expected gap.
* Clearance: for every pair of nets listed by the caller, ``distToShape``
  between each conductive body of net A and each conductive body of net B.
  The straight segment between the two closest points is sampled; if it does
  not pass through an insulating solid it is an air clearance.  If it does
  (pad, bobbin, barrier, bushing) and the straight distance is below the
  requirement, a one-bend air path around the edges of the blocking insulator
  is searched (the "stretched string" notion of clearance).  Pairs with no
  such path are reported for review with the solid-insulation thickness; the
  creepage along insulating surfaces is never traced.  Required values are
  caller inputs; nothing here asserts compliance with any standard.

All results are reported in SI units (metres, cubic metres).
"""
from __future__ import annotations

import fnmatch
from typing import Dict, List, Optional, Tuple

import Part
from FreeCAD import Vector

from ..units import mm3_to_m3, mm_to_m
from ._doc import PHYSICAL_ROLES, ROLE_ENVELOPE, ROLE_KEEPOUT, ROLE_SOLID, Body

CONTACT_TOL_MM = 1e-4
INSIDE_TOL_MM = 1e-6
SAMPLES = 9
MAX_LISTED = 25


def _bbox_intersect(a: Body, b: Body, margin_mm: float = 1e-3) -> bool:
    ba, bb = a.shape.BoundBox, b.shape.BoundBox
    return not (ba.XMax + margin_mm < bb.XMin or bb.XMax + margin_mm < ba.XMin or
                ba.YMax + margin_mm < bb.YMin or bb.YMax + margin_mm < ba.YMin or
                ba.ZMax + margin_mm < bb.ZMin or bb.ZMax + margin_mm < ba.ZMin)


def _pair_matches(name_a: str, name_b: str, patterns) -> bool:
    for pa, pb in patterns or []:
        if (fnmatch.fnmatch(name_a, pa) and fnmatch.fnmatch(name_b, pb)) or (fnmatch.fnmatch(name_b, pa) and fnmatch.fnmatch(name_a, pb)):
            return True
    return False


def _vec_m(v) -> list:
    return [mm_to_m(v.x), mm_to_m(v.y), mm_to_m(v.z)]


def _distance(a, b) -> Tuple[float, Vector, Vector]:
    d, pts, _info = a.distToShape(b)
    p1, p2 = pts[0] if pts else (Vector(), Vector())
    return d, p1, p2


def _blocking(p1: Vector, p2: Vector, solids: List[Body]) -> List[str]:
    """Solids that make the open segment p1-p2 a non-air path.

    A sample point is "not in air" when it lies strictly inside a solid, or on
    the faces of at least two solids (i.e. on an interface such as a pad hole
    wall against a bushing sleeve).  A point lying on a single face with air on
    the other side (a string hugging a surface) does not block.
    """
    seg = p2 - p1
    if seg.Length <= INSIDE_TOL_MM:
        return []
    names: List[str] = []
    for k in range(1, SAMPLES + 1):
        p = p1 + seg * (k / (SAMPLES + 1.0))
        on_faces, strict = [], []
        for s in solids:
            bb = s.shape.BoundBox
            bb.enlarge(1e-3)
            if not bb.isInside(p):
                continue
            if s.shape.isInside(p, INSIDE_TOL_MM, True):
                on_faces.append(s.name)
                if s.shape.isInside(p, INSIDE_TOL_MM, False):
                    strict.append(s.name)
        hits = strict if strict else (on_faces if len(on_faces) >= 2 else [])
        for name in hits:
            if name not in names:
                names.append(name)
    return names


def _detour(a: Body, b: Body, blockers: List[Body], solids: List[Body]) -> Optional[dict]:
    """Shortest one-bend path a -> point on an insulator edge -> b with both legs through air.

    For every edge of every blocking insulator two bend points are tried: the
    edge point closest to ``a`` and the edge point closest to ``b``.  Both legs
    are measured from the same bend point and must not pass through any solid.
    The result is a valid air path and therefore an upper bound of the true
    (possibly multi-bend) air clearance.
    """
    best = None
    best_total = None
    for ins in blockers:
        if not ins.insulator:
            continue
        for edge in ins.shape.Edges:
            try:
                da, pa, pe = _distance(a.shape, edge)
                db, pe2, pb = _distance(edge, b.shape)
            except Exception:  # pragma: no cover - degenerate edges
                continue
            if da <= INSIDE_TOL_MM or db <= INSIDE_TOL_MM:
                continue
            candidates = []
            try:
                d_pe_b, _v, pb1 = _distance(Part.Vertex(pe), b.shape)
                candidates.append((da + d_pe_b, pa, pe, pb1))
                d_a_pe2, pa2, _v2 = _distance(a.shape, Part.Vertex(pe2))
                candidates.append((d_a_pe2 + db, pa2, pe2, pb))
            except Exception:  # pragma: no cover
                continue
            for total, p_a, p_e, p_b in candidates:
                if best_total is not None and total >= best_total:
                    continue
                if _blocking(p_a, p_e, solids) or _blocking(p_e, p_b, solids):
                    continue
                best_total = total
                best = {"via_insulator": ins.name, "path_length_m": mm_to_m(total),
                        "points_m": [_vec_m(p_a), _vec_m(p_e), _vec_m(p_b)]}
    return best


def _clearance_pair(pair: dict, conductors: List[Body], solids: List[Body], by_name: Dict[str, Body]) -> dict:
    """Evaluate one net pair; ``solids`` are all physical solid bodies (conductors and insulators)."""
    net_a, net_b = pair.get("net_a"), pair.get("net_b")
    req_cl = float(pair.get("required_clearance", 0.0) or 0.0)
    req_cr = pair.get("required_creepage")
    bodies_a = [b for b in conductors if b.net == net_a]
    bodies_b = [b for b in conductors if b.net == net_b]
    entry = {"net_a": net_a, "net_b": net_b, "required_clearance_m": req_cl, "required_creepage_m": req_cr,
             "note": pair.get("note"), "bodies_a": len(bodies_a), "bodies_b": len(bodies_b)}
    if not bodies_a or not bodies_b:
        entry.update({"status": "no_bodies", "message": f"no conductive bodies for net '{net_a if not bodies_a else net_b}'"})
        return entry
    air_paths = []          # straight air segments or one-bend paths (valid clearance measurements)
    through_ok = []         # straight distance through insulation already >= requirement
    solid_only = []         # blocked, below requirement, no one-bend air path found -> review
    contacts = []
    min_direct = None
    for a in bodies_a:
        for b in bodies_b:
            if a is b:
                continue
            d, p1, p2 = _distance(a.shape, b.shape)
            d_m = mm_to_m(d)
            rec = {"a": a.name, "b": b.name, "distance_m": d_m, "points_m": [_vec_m(p1), _vec_m(p2)]}
            if min_direct is None or d_m < min_direct["distance_m"]:
                min_direct = rec
            if d <= CONTACT_TOL_MM:
                contacts.append(rec)
                continue
            blockers = [n for n in _blocking(p1, p2, solids) if n not in (a.name, b.name)]
            if not blockers:
                air_paths.append(dict(rec, path="straight", length_m=d_m))
            elif d_m >= req_cl:
                through_ok.append(dict(rec, insulators=blockers))
            else:
                detour = _detour(a, b, [by_name[n] for n in blockers], solids)
                if detour is not None:
                    air_paths.append(dict(rec, path="around_insulator", length_m=detour["path_length_m"], insulators=blockers, detour=detour))
                else:
                    solid_only.append(dict(rec, insulators=blockers))
    air_paths.sort(key=lambda r: r["length_m"])
    solid_only.sort(key=lambda r: r["distance_m"])
    through_ok.sort(key=lambda r: r["distance_m"])
    governing = air_paths[0] if air_paths else None
    if contacts:
        status = "fail"
        message = f"{len(contacts)} conductor pair(s) of different nets are in contact (short circuit)"
    elif governing is not None and governing["length_m"] < req_cl:
        status = "fail"
        if governing["path"] == "straight":
            message = (f"air clearance {governing['length_m'] * 1e3:.3f} mm between {governing['a']} and {governing['b']} "
                       f"is below the required {req_cl * 1e3:.3f} mm")
        else:
            message = (f"air path around insulator {governing['detour']['via_insulator']} between {governing['a']} and {governing['b']} "
                       f"is {governing['length_m'] * 1e3:.3f} mm (< required {req_cl * 1e3:.3f} mm); straight distance "
                       f"{governing['distance_m'] * 1e3:.3f} mm through solid insulation")
    elif solid_only:
        status = "review"
        it = solid_only[0]
        message = (f"{len(solid_only)} conductor pair(s) are separated only by solid insulation thinner than the requirement and no "
                   f"one-bend air path was found; thinnest: {it['distance_m'] * 1e3:.3f} mm between {it['a']} and {it['b']} through "
                   f"{', '.join(it['insulators'])}. The air/creepage path along the insulation surfaces is not traced - review manually")
        if governing is not None:
            message += f". Shortest evaluated air path: {governing['length_m'] * 1e3:.3f} mm ({governing['a']} - {governing['b']})"
    elif governing is not None:
        status = "pass"
        if governing["path"] == "straight":
            message = f"minimum air clearance {governing['length_m'] * 1e3:.3f} mm between {governing['a']} and {governing['b']}"
        else:
            message = (f"minimum air path {governing['length_m'] * 1e3:.3f} mm around insulator {governing['detour']['via_insulator']} "
                       f"between {governing['a']} and {governing['b']} (straight distance {governing['distance_m'] * 1e3:.3f} mm through solid insulation)")
    else:
        status = "pass"
        t0 = through_ok[0]
        message = (f"no air path shorter than the requirement exists; the closest conductors {t0['a']} and {t0['b']} are "
                   f"{t0['distance_m'] * 1e3:.3f} mm apart through solid insulation ({', '.join(t0['insulators'])})")
    creepage_status = None
    if req_cr is not None:
        if status == "pass" and governing is not None and governing["length_m"] >= float(req_cr) and not solid_only:
            creepage_status = "satisfied_by_clearance"
        elif status == "pass" and governing is None:
            creepage_status = "not_evaluated"
        else:
            creepage_status = "not_evaluated"
    entry.update({
        "status": status, "message": message,
        "min_air_clearance_m": governing["length_m"] if governing else None,
        "governing_path": governing,
        "min_direct_distance": min_direct,
        "min_through_insulation_m": through_ok[0]["distance_m"] if through_ok else None,
        "air_paths": air_paths[:MAX_LISTED],
        "through_insulation_ge_required": through_ok[:MAX_LISTED],
        "solid_insulation_only": solid_only[:MAX_LISTED],
        "contacts": contacts[:MAX_LISTED],
        "body_pairs_evaluated": len(bodies_a) * len(bodies_b),
        "creepage_status": creepage_status,
        "creepage_note": "creepage is only compared against the evaluated air path; surface paths along insulators are not traced",
    })
    return entry


def run_checks(bodies: List[Body], config: dict) -> dict:
    config = config or {}
    physical = [b for b in bodies if b.role in PHYSICAL_ROLES]
    solids = [b for b in physical if b.role == ROLE_SOLID]  # fluids are not solid insulation
    report: Dict[str, object] = {"units": "SI (m, m^3)", "config": config}

    # --- interference & contacts -------------------------------------------------------------
    inter_cfg = config.get("interference", {}) or {}
    interference, contacts = [], []
    if inter_cfg.get("enabled", True):
        min_vol_m3 = float(inter_cfg.get("min_overlap_volume", 1e-12))
        allowed = inter_cfg.get("allowed_overlaps", [])
        for i in range(len(physical)):
            for j in range(i + 1, len(physical)):
                a, b = physical[i], physical[j]
                if not _bbox_intersect(a, b):
                    continue
                try:
                    common = a.shape.common(b.shape)
                    vol = common.Volume if not common.isNull() else 0.0
                except Exception as exc:  # pragma: no cover - OCC failure on degenerate pair
                    interference.append({"a": a.name, "b": b.name, "status": "error", "message": str(exc)})
                    continue
                vol_m3 = mm3_to_m3(vol)
                if vol_m3 > min_vol_m3:
                    interference.append({"a": a.name, "b": b.name, "common_volume_m3": vol_m3,
                                         "status": "allowed" if _pair_matches(a.name, b.name, allowed) else "overlap"})
                else:
                    d, _p1, _p2 = _distance(a.shape, b.shape)
                    if d <= CONTACT_TOL_MM:
                        contacts.append({"a": a.name, "b": b.name})
    report["interference"] = interference
    report["contacts"] = contacts

    # --- keep-outs & envelopes ---------------------------------------------------------------------
    keepout_violations, envelope_intrusions = [], []
    ko_cfg = config.get("keepouts", {}) or {}
    if ko_cfg.get("enabled", True):
        for ko in [b for b in bodies if b.role == ROLE_KEEPOUT]:
            owner = ko.meta.get("owner")
            for s in physical:
                if (owner and s.group == owner) or _pair_matches(ko.name, s.name, ko_cfg.get("ignore_pairs")) or not _bbox_intersect(ko, s):
                    continue
                vol = mm3_to_m3(ko.shape.common(s.shape).Volume)
                if vol > 1e-12:
                    keepout_violations.append({"keepout": ko.name, "body": s.name, "common_volume_m3": vol})
    env_cfg = config.get("envelopes", {}) or {}
    if env_cfg.get("report_intrusions", True):
        for env in [b for b in bodies if b.role == ROLE_ENVELOPE]:
            for s in physical:
                if s.group == env.group or _pair_matches(env.name, s.name, env_cfg.get("ignore_pairs")) or not _bbox_intersect(env, s):
                    continue
                vol = mm3_to_m3(env.shape.common(s.shape).Volume)
                if vol > 1e-12:
                    envelope_intrusions.append({"envelope": env.name, "body": s.name, "common_volume_m3": vol})
    report["keepout_violations"] = keepout_violations
    report["envelope_intrusions"] = envelope_intrusions

    # --- fit pairs -------------------------------------------------------------------------------------
    by_name = {b.name: b for b in bodies}
    fit = []
    for fp in config.get("fit_pairs", []) or []:
        a, b = by_name.get(fp.get("a")), by_name.get(fp.get("b"))
        if a is None or b is None:
            fit.append({"a": fp.get("a"), "b": fp.get("b"), "status": "missing_body"})
            continue
        d, p1, p2 = _distance(a.shape, b.shape)
        dist_m = mm_to_m(d)
        status = "pass"
        if fp.get("expected_gap") is not None:
            tol = float(fp.get("tolerance", 1e-6))
            if abs(dist_m - float(fp["expected_gap"])) > tol:
                status = "fail"
        if fp.get("min_gap") is not None and dist_m < float(fp["min_gap"]):
            status = "fail"
        if fp.get("max_gap") is not None and dist_m > float(fp["max_gap"]):
            status = "fail"
        fit.append({"a": a.name, "b": b.name, "distance_m": dist_m, "expected_gap_m": fp.get("expected_gap"),
                    "tolerance_m": fp.get("tolerance"), "min_gap_m": fp.get("min_gap"), "max_gap_m": fp.get("max_gap"),
                    "points_m": [_vec_m(p1), _vec_m(p2)], "status": status, "note": fp.get("note")})
    report["fit"] = fit

    # --- clearance pairs ---------------------------------------------------------------------------------
    conductors = [b for b in physical if b.conductive]
    unassigned = [b.name for b in conductors if not b.net]
    clearance = [_clearance_pair(pair, conductors, solids, by_name) for pair in config.get("clearance_pairs", []) or []]
    report["clearance"] = clearance
    report["unassigned_conductors"] = unassigned

    # --- summary -----------------------------------------------------------------------------------------
    overlaps = [r for r in interference if r.get("status") == "overlap"]
    cl_status = {"pass": 0, "fail": 0, "review": 0, "no_bodies": 0}
    for c in clearance:
        cl_status[c["status"]] = cl_status.get(c["status"], 0) + 1
    fit_fail = sum(1 for f in fit if f["status"] != "pass")
    if overlaps or keepout_violations or cl_status["fail"] or fit_fail:
        overall = "fail"
    elif cl_status["review"] or envelope_intrusions or unassigned or cl_status["no_bodies"]:
        overall = "review"
    else:
        overall = "pass"
    report["summary"] = {
        "status": overall, "interference_count": len(overlaps), "allowed_overlap_count": len(interference) - len(overlaps),
        "contact_count": len(contacts), "keepout_violation_count": len(keepout_violations),
        "envelope_intrusion_count": len(envelope_intrusions), "fit_failures": fit_fail,
        "clearance_pairs": cl_status, "unassigned_conductor_count": len(unassigned),
        "bodies_checked": len(physical),
        "note": "required clearance/creepage values are caller inputs; no standard compliance is asserted",
    }
    return report
