"""Low-level Part shape helpers (millimetres).  Runs only inside FreeCAD."""
from __future__ import annotations

import math

import FreeCAD  # noqa: F401  (import check)
import Part
from FreeCAD import Vector

from ..units import m_to_mm

EPS = 1e-7
OVERCUT = 1.0  # mm extension of cutting tools beyond the faces they open


def mm(value_m: float) -> float:
    return m_to_mm(value_m)


def box(lx: float, ly: float, lz: float, origin=(0.0, 0.0, 0.0)) -> "Part.Shape":
    """Axis-aligned box with its minimum corner at ``origin`` (mm)."""
    return Part.makeBox(lx, ly, lz, Vector(*origin))


def box_centred(lx: float, ly: float, lz: float, centre=(0.0, 0.0, 0.0)) -> "Part.Shape":
    cx, cy, cz = centre
    return Part.makeBox(lx, ly, lz, Vector(cx - 0.5 * lx, cy - 0.5 * ly, cz - 0.5 * lz))


def box_ranges(x, y, z) -> "Part.Shape":
    """Box from coordinate ranges ``x=(x0, x1)`` etc. (mm)."""
    return Part.makeBox(x[1] - x[0], y[1] - y[0], z[1] - z[0], Vector(x[0], y[0], z[0]))


def cylinder_z(diameter: float, z0: float, z1: float, x: float, y: float) -> "Part.Shape":
    return Part.makeCylinder(0.5 * diameter, z1 - z0, Vector(x, y, z0), Vector(0, 0, 1))


def cylinder_x(diameter: float, x0: float, x1: float, y: float, z: float) -> "Part.Shape":
    return Part.makeCylinder(0.5 * diameter, x1 - x0, Vector(x0, y, z), Vector(1, 0, 0))


def _is_vertical_edge(edge) -> bool:
    vs = edge.Vertexes
    if len(vs) != 2:
        return False
    return abs(vs[0].X - vs[1].X) < 1e-9 and abs(vs[0].Y - vs[1].Y) < 1e-9


def rounded_box(lx: float, ly: float, lz: float, radius: float, origin=(0.0, 0.0, 0.0)) -> "Part.Shape":
    """Box whose four vertical edges are filleted with ``radius`` (0 = sharp)."""
    b = box(lx, ly, lz, origin)
    if radius > EPS:
        if 2 * radius > min(lx, ly) + 1e-9:
            raise ValueError("corner radius too large for the box footprint")
        edges = [e for e in b.Edges if _is_vertical_edge(e)]
        b = b.makeFillet(radius, edges)
    return b


def rounded_box_centred(lx: float, ly: float, z0: float, z1: float, radius: float) -> "Part.Shape":
    return rounded_box(lx, ly, z1 - z0, radius, (-0.5 * lx, -0.5 * ly, z0))


def annular_rounded_prism(inner_lx: float, inner_ly: float, inner_radius: float, thickness: float,
                          z0: float, z1: float) -> "Part.Shape":
    """Prism between two concentric rounded rectangles (centred on the Z axis)."""
    outer = rounded_box_centred(inner_lx + 2 * thickness, inner_ly + 2 * thickness, z0, z1, inner_radius + thickness)
    inner = rounded_box_centred(inner_lx, inner_ly, z0 - OVERCUT, z1 + OVERCUT, inner_radius)
    return outer.cut(inner)


def rect_ring_xz(inner_lx: float, inner_lz: float, thickness: float, width_y: float, y_centre: float,
                 z_centre: float = 0.0) -> "Part.Shape":
    """Rectangular ring in the XZ plane (core clip) of strip ``thickness`` and ``width_y`` along Y."""
    outer = box_centred(inner_lx + 2 * thickness, width_y, inner_lz + 2 * thickness, (0.0, y_centre, z_centre))
    inner = box_centred(inner_lx, width_y + 2 * OVERCUT, inner_lz, (0.0, y_centre, z_centre))
    return outer.cut(inner)


def half_annulus_z(centre, outer_radius: float, inner_radius: float, z0: float, z1: float, side: str) -> "Part.Shape":
    """Half of an annulus (ring) in the XY plane on the ``+x`` or ``-x`` side of ``centre``."""
    cx, cy = centre
    ring = Part.makeCylinder(outer_radius, z1 - z0, Vector(cx, cy, z0), Vector(0, 0, 1))
    if inner_radius > EPS:
        ring = ring.cut(Part.makeCylinder(inner_radius, z1 - z0 + 2 * OVERCUT, Vector(cx, cy, z0 - OVERCUT), Vector(0, 0, 1)))
    if side == "+x":
        half = box((outer_radius + OVERCUT), 2 * (outer_radius + OVERCUT), z1 - z0 + 2 * OVERCUT,
                   (cx, cy - outer_radius - OVERCUT, z0 - OVERCUT))
    else:
        half = box((outer_radius + OVERCUT), 2 * (outer_radius + OVERCUT), z1 - z0 + 2 * OVERCUT,
                   (cx - outer_radius - OVERCUT, cy - outer_radius - OVERCUT, z0 - OVERCUT))
    return ring.common(half)


def fuse_all(shapes) -> "Part.Shape":
    shapes = [s for s in shapes if s is not None]
    if not shapes:
        raise ValueError("nothing to fuse")
    result = shapes[0]
    if len(shapes) > 1:
        result = result.fuse(shapes[1:])
    try:
        result = result.removeSplitter()
    except Exception:  # pragma: no cover - cosmetic clean-up only
        pass
    return result


def cut_all(base, tools) -> "Part.Shape":
    tools = [t for t in tools if t is not None]
    if not tools:
        return base
    return base.cut(tools) if len(tools) > 1 else base.cut(tools[0])


def mirror_z(shape) -> "Part.Shape":
    return shape.mirror(Vector(0, 0, 0), Vector(0, 0, 1))


def place(shape, position_mm, rotation_deg: float = 0.0, rotation_centre=(0.0, 0.0, 0.0)) -> "Part.Shape":
    """Copy ``shape``, rotate it about Z (through ``rotation_centre``) and translate it (mm)."""
    s = shape.copy()
    if abs(rotation_deg) > 1e-12:
        s.rotate(Vector(*rotation_centre), Vector(0, 0, 1), rotation_deg)
    s.translate(Vector(*position_mm))
    return s


def bbox_of(shapes):
    """Union bounding box [xmin, ymin, zmin, xmax, ymax, zmax] in mm."""
    bb = None
    for s in shapes:
        b = s.BoundBox
        if bb is None:
            bb = [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]
        else:
            bb = [min(bb[0], b.XMin), min(bb[1], b.YMin), min(bb[2], b.ZMin),
                  max(bb[3], b.XMax), max(bb[4], b.YMax), max(bb[5], b.ZMax)]
    return bb


def centre_of_mass(shape):
    """Volume-weighted centre of mass over the solids of a shape (mm)."""
    total = 0.0
    acc = Vector(0, 0, 0)
    for solid in shape.Solids:
        v = solid.Volume
        if v > 0:
            acc = acc + solid.CenterOfMass * v
            total += v
    if total <= 0:
        return None
    c = acc * (1.0 / total)
    return [c.x, c.y, c.z]


def rotate_xy(x: float, y: float, deg: float):
    a = math.radians(deg)
    return math.cos(a) * x - math.sin(a) * y, math.sin(a) * x + math.cos(a) * y
