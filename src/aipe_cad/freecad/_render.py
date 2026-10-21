"""Headless PNG renders from tessellated shapes using matplotlib (bundled with FreeCAD).

FreeCAD's Coin3D offscreen renderer needs an OpenGL context that ``freecadcmd``
does not provide, so the shapes are tessellated with Part and drawn with
matplotlib's Agg backend: a shaded isometric view plus three orthographic
projections (painter's algorithm, no true hidden-surface removal).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import List

from ._doc import PHYSICAL_ROLES, Body

LIGHT = (0.4, -0.6, 0.7)


def _triangles(body: Body, tolerance_mm: float):
    verts, facets = body.shape.tessellate(tolerance_mm)
    tris = []
    for a, b, c in facets:
        tris.append(((verts[a].x, verts[a].y, verts[a].z), (verts[b].x, verts[b].y, verts[b].z), (verts[c].x, verts[c].y, verts[c].z)))
    return tris


def _normal(tri):
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri
    ux, uy, uz = x1 - x0, y1 - y0, z1 - z0
    vx, vy, vz = x2 - x0, y2 - y0, z2 - z0
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return nx / n, ny / n, nz / n


def _shade(color, normal):
    lx, ly, lz = LIGHT
    ln = math.sqrt(lx * lx + ly * ly + lz * lz)
    intensity = 0.45 + 0.55 * abs((normal[0] * lx + normal[1] * ly + normal[2] * lz) / ln)
    return tuple(min(1.0, c * intensity) for c in color)


def render_png(bodies: List[Body], path: Path, title: str = "", tolerance_mm: float = 0.6, dpi: int = 110) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    faces, colors, alphas = [], [], []
    for body in bodies:
        if body.shape.isNull():
            continue
        translucent = body.role not in PHYSICAL_ROLES
        base = (0.9, 0.3, 0.3) if body.role == "keepout" else ((0.3, 0.5, 0.9) if body.role == "envelope" else body.color)
        for tri in _triangles(body, tolerance_mm):
            faces.append(tri)
            colors.append(base if translucent else _shade(base, _normal(tri)))
            alphas.append(0.10 if translucent else 1.0)
    if not faces:
        raise ValueError("nothing to render")
    xs = [p[0] for tri in faces for p in tri]
    ys = [p[1] for tri in faces for p in tri]
    zs = [p[2] for tri in faces for p in tri]
    lo = [min(xs), min(ys), min(zs)]
    hi = [max(xs), max(ys), max(zs)]
    span = max(hi[i] - lo[i] for i in range(3)) or 1.0
    mid = [(lo[i] + hi[i]) / 2 for i in range(3)]

    fig = plt.figure(figsize=(14, 10), dpi=dpi)
    ax3 = fig.add_subplot(2, 2, 1, projection="3d")
    rgba = [(*c, a) for c, a in zip(colors, alphas)]
    coll = Poly3DCollection(faces, facecolors=rgba, edgecolors="none", zsort="average")
    ax3.add_collection3d(coll)
    for setter, m in zip((ax3.set_xlim, ax3.set_ylim, ax3.set_zlim), mid):
        setter(m - 0.55 * span, m + 0.55 * span)
    try:
        ax3.set_box_aspect((1, 1, 1))
    except Exception:  # pragma: no cover
        pass
    ax3.view_init(elev=28, azim=-55)
    ax3.set_xlabel("x [mm]")
    ax3.set_ylabel("y [mm]")
    ax3.set_zlabel("z [mm]")
    ax3.set_title("isometric (shaded, painter's algorithm)")

    views = [("top view (XY)", 0, 1, 2, 1), ("front view (XZ)", 0, 2, 1, -1), ("side view (YZ)", 1, 2, 0, 1)]
    for idx, (name, i, j, depth_axis, sign) in enumerate(views, start=2):
        ax = fig.add_subplot(2, 2, idx)
        order = sorted(range(len(faces)), key=lambda k: sign * sum(p[depth_axis] for p in faces[k]) / 3.0)
        polys = [[(faces[k][v][i], faces[k][v][j]) for v in range(3)] for k in order]
        pc = PolyCollection(polys, facecolors=[rgba[k] for k in order], edgecolors="none")
        ax.add_collection(pc)
        ax.set_xlim(mid[i] - 0.55 * span, mid[i] + 0.55 * span)
        ax.set_ylim(mid[j] - 0.55 * span, mid[j] + 0.55 * span)
        ax.set_aspect("equal")
        ax.set_title(name)
        ax.set_xlabel("xyz"[i] + " [mm]")
        ax.set_ylabel("xyz"[j] + " [mm]")
        ax.grid(True, alpha=0.3)
    fig.suptitle(title or "AIPE CAD render", fontsize=13)
    fig.tight_layout()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(path))
    plt.close(fig)
    return path


def render_svg_views(bodies: List[Body], path: Path) -> Path:
    """Hidden-line orthographic projections via TechDraw.projectToSVG (slow for many solids)."""
    import Part
    import TechDraw
    from FreeCAD import Vector

    compound = Part.makeCompound([b.shape for b in bodies if b.role in PHYSICAL_ROLES])
    parts = []
    bb = compound.BoundBox
    size = max(bb.XLength, bb.YLength, bb.ZLength) or 1.0
    for idx, (label, direction) in enumerate((("top", Vector(0, 0, 1)), ("front", Vector(0, -1, 0)), ("side", Vector(1, 0, 0)),
                                              ("iso", Vector(1, -1, 1)))):
        svg = TechDraw.projectToSVG(compound, direction, "ShowHiddenLines")
        offset_x = (idx % 2) * size * 1.4
        offset_y = (idx // 2) * size * 1.4
        parts.append(f'<g transform="translate({offset_x:.2f},{offset_y:.2f})"><text x="0" y="-5" font-size="{size / 25:.1f}">{label}</text>{svg}</g>')
    width = size * 2.8
    content = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{-size * 0.7:.2f} {-size * 0.7:.2f} {width:.2f} {width:.2f}" '
               f'width="1200" height="1200">{"".join(parts)}</svg>')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path
