"""Optional CadQuery backend (experimental).

FreeCAD is the required and complete geometry path of this package.  CadQuery
(``pip install aipe-cad[cadquery]``) is offered only as an optional, in-process
alternative for the plate-fin heat sink body so that the same resolved
parameters can be exported to STEP without spawning ``freecadcmd``.  It does
not run the interference/clearance checks and does not write FCStd files.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .units import m_to_mm, mm3_to_m3


def available() -> bool:
    try:
        import cadquery  # noqa: F401
    except Exception:
        return False
    return True


def heatsink_body(resolved: dict):
    """CadQuery Workplane of the heat sink body (base + fins + holes), millimetres."""
    import cadquery as cq

    base, fins = resolved["base"], resolved["fins"]
    L, W, tb = m_to_mm(base["length"]), m_to_mm(base["width"]), m_to_mm(base["thickness"])
    t, h = m_to_mm(fins["thickness"]), m_to_mm(fins["height"])
    fin_len = m_to_mm(fins["length"])
    solid = cq.Workplane("XY").box(L, W, tb, centered=(True, True, False))
    for y in fins["positions"]:
        fin = cq.Workplane("XY").box(fin_len, t, h, centered=(True, True, False)).translate((0, m_to_mm(y), -h))
        solid = solid.union(fin)
    if resolved["mounting_holes"]:
        d = m_to_mm(resolved["mounting_holes"]["diameter"])
        for hx, hy in resolved["mounting_holes"]["holes"]:
            cutter = cq.Workplane("XY").circle(0.5 * d).extrude(h + tb + 2).translate((m_to_mm(hx), m_to_mm(hy), -h - 1))
            solid = solid.cut(cutter)
    for dev in resolved["devices"]:
        d = m_to_mm(dev["screw_hole_diameter"])
        hx, hy = dev["hole_xy"]
        cutter = cq.Workplane("XY").circle(0.5 * d).extrude(h + tb + 2).translate((m_to_mm(hx), m_to_mm(hy), -h - 1))
        solid = solid.cut(cutter)
    return solid


def export_heatsink(resolved: dict, out_dir, name: Optional[str] = None) -> dict:
    """Write ``<name>.cadquery.step`` and return volume/mass/bbox in SI units."""
    import cadquery as cq

    name = name or resolved["name"]
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wp = heatsink_body(resolved)
    shape = wp.val()
    path = out_dir / f"{name}.cadquery.step"
    cq.exporters.export(wp, str(path))
    bb = shape.BoundingBox()
    vol = mm3_to_m3(shape.Volume())
    return {"backend": "cadquery", "step": str(path), "volume_m3": vol,
            "mass_kg": vol * resolved["base"]["density"],
            "bbox_m": [v / 1000.0 for v in (bb.xmin, bb.ymin, bb.zmin, bb.xmax, bb.ymax, bb.zmax)],
            "note": "heat sink body only; no devices, checks or FCStd (use the FreeCAD backend for those)"}
