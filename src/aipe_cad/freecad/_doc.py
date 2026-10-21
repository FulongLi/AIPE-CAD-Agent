"""Body container, FreeCAD document assembly, STEP/FCStd export and metadata (inside FreeCAD)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import FreeCAD
import Part

from ..materials import MATERIALS, density, is_conductive
from ..units import bbox_mm_to_m, mm2_to_m2, mm3_to_m3, mm_to_m
from ._shapes import bbox_of, centre_of_mass

ROLE_SOLID = "solid"
ROLE_FLUID = "fluid"
ROLE_KEEPOUT = "keepout"
ROLE_ENVELOPE = "envelope"
PHYSICAL_ROLES = (ROLE_SOLID, ROLE_FLUID)

MATERIAL_COLORS = {
    "ferrite": (0.30, 0.30, 0.32), "metal": (0.72, 0.74, 0.78), "laminate": (0.20, 0.55, 0.30),
    "polymer": (0.85, 0.70, 0.30), "ceramic": (0.95, 0.93, 0.88), "fluid": (0.30, 0.55, 0.90),
}
SPECIAL_COLORS = {"copper": (0.80, 0.50, 0.25), "brass": (0.78, 0.65, 0.30), "kapton": (0.85, 0.55, 0.15),
                  "fr4": (0.20, 0.55, 0.30), "alumina": (0.95, 0.93, 0.88)}


@dataclass
class Body:
    """One named solid of a model.  ``shape`` is in millimetres; everything else is SI."""

    name: str
    shape: object
    material: str
    role: str = ROLE_SOLID
    net: Optional[str] = None
    group: str = ""
    density_override: Optional[float] = None
    meta: dict = field(default_factory=dict)

    @property
    def conductive(self) -> bool:
        return self.role in PHYSICAL_ROLES and is_conductive(self.material)

    @property
    def insulator(self) -> bool:
        return self.role in PHYSICAL_ROLES and not is_conductive(self.material)

    @property
    def counts_mass(self) -> bool:
        return self.role in PHYSICAL_ROLES and self.material != "air"

    @property
    def density(self) -> float:
        return density(self.material, self.density_override)

    @property
    def color(self):
        if self.material in SPECIAL_COLORS:
            return SPECIAL_COLORS[self.material]
        return MATERIAL_COLORS.get(MATERIALS[self.material]["category"], (0.6, 0.6, 0.6))


def prefixed(bodies: List[Body], prefix: str) -> List[Body]:
    for b in bodies:
        b.name = f"{prefix}.{b.name}"
        b.group = prefix
    return bodies


def _internal_name(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", label)


def build_document(doc_name: str, bodies: List[Body], params: dict, resolved_summary: Optional[dict] = None):
    """Create a FreeCAD document with one Part::Feature per body, grouped by component.

    Material, net and role are stored as custom properties so that the FCStd
    stays editable and traceable; the full parameter JSON is kept on a
    ``Parameters`` object.
    """
    doc = FreeCAD.newDocument(_internal_name(doc_name))
    groups: Dict[str, object] = {}
    objects = []
    for body in bodies:
        obj = doc.addObject("Part::Feature", _internal_name(body.name))
        obj.Label = body.name
        obj.Shape = body.shape
        obj.addProperty("App::PropertyString", "AipeMaterial", "AIPE", "material name (aipe_cad.materials)")
        obj.addProperty("App::PropertyString", "AipeNet", "AIPE", "electrical net / potential group")
        obj.addProperty("App::PropertyString", "AipeRole", "AIPE", "solid | fluid | keepout | envelope")
        obj.addProperty("App::PropertyString", "AipeGroup", "AIPE", "component instance")
        obj.addProperty("App::PropertyFloat", "AipeDensity", "AIPE", "density used for the mass estimate [kg/m^3]")
        obj.AipeMaterial = body.material
        obj.AipeNet = body.net or ""
        obj.AipeRole = body.role
        obj.AipeGroup = body.group
        obj.AipeDensity = float(body.density)
        if body.group:
            grp = groups.get(body.group)
            if grp is None:
                grp = doc.addObject("App::DocumentObjectGroup", _internal_name(body.group))
                grp.Label = body.group
                groups[body.group] = grp
            grp.addObject(obj)
        objects.append(obj)
    meta_obj = doc.addObject("App::DocumentObjectGroup", "AIPE_Parameters")
    meta_obj.Label = "Parameters"
    meta_obj.addProperty("App::PropertyString", "AipeParametersJSON", "AIPE", "parameter JSON (SI units)")
    meta_obj.AipeParametersJSON = json.dumps(params, indent=1)
    meta_obj.addProperty("App::PropertyString", "AipeUnits", "AIPE", "unit note")
    meta_obj.AipeUnits = "Geometry in millimetres (FreeCAD); parameters, metadata and reports in SI metres/kilograms."
    if resolved_summary is not None:
        meta_obj.addProperty("App::PropertyString", "AipeResolvedJSON", "AIPE", "resolved geometry summary (SI)")
        meta_obj.AipeResolvedJSON = json.dumps(resolved_summary, indent=1, default=str)
    doc.recompute()
    return doc, objects


def export_step(objects, path: Path) -> Path:
    import Import
    Import.export(list(objects), str(path))
    return Path(path)


def save_fcstd(doc, path: Path) -> Path:
    doc.saveAs(str(path))
    return Path(path)


def step_reimport_check(path: Path, expected_volume_mm3: float) -> dict:
    shape = Part.Shape()
    shape.read(str(path))
    vol = shape.Volume
    rel = abs(vol - expected_volume_mm3) / expected_volume_mm3 if expected_volume_mm3 else None
    return {"path": str(path), "solids": len(shape.Solids), "volume_m3": mm3_to_m3(vol),
            "expected_volume_m3": mm3_to_m3(expected_volume_mm3), "relative_error": rel,
            "valid": bool(shape.isValid())}


def body_record(body: Body) -> dict:
    s = body.shape
    vol_mm3 = s.Volume
    rec = {
        "name": body.name, "group": body.group, "role": body.role, "material": body.material,
        "net": body.net, "conductive": body.conductive, "density_kg_m3": body.density if body.counts_mass else None,
        "volume_m3": mm3_to_m3(vol_mm3), "surface_area_m2": mm2_to_m2(s.Area),
        "mass_kg": mm3_to_m3(vol_mm3) * body.density if body.counts_mass else 0.0,
        "bbox_m": bbox_mm_to_m([s.BoundBox.XMin, s.BoundBox.YMin, s.BoundBox.ZMin, s.BoundBox.XMax, s.BoundBox.YMax, s.BoundBox.ZMax]),
        "centre_of_mass_m": [mm_to_m(v) for v in centre_of_mass(s)] if centre_of_mass(s) else None,
        "solid_count": len(s.Solids), "is_valid": bool(s.isValid()),
    }
    analytic = body.meta.get("analytic_volume_m3")
    if analytic is not None:
        rec["analytic_volume_m3"] = analytic
        rec["analytic_relative_error"] = abs(rec["volume_m3"] - analytic) / analytic if analytic else None
    for key in ("note", "owner"):
        if key in body.meta:
            rec[key] = body.meta[key]
    return rec


def _element_size_default(rec: dict) -> float:
    bb = rec["bbox_m"]
    dims = sorted([bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]])
    size = max(dims[0] / 2.0, dims[2] / 20.0)
    return float(min(max(size, 0.2e-3), 5e-3))


def compute_metadata(kind: str, name: str, bodies: List[Body], resolved: dict, params: dict,
                     files: dict, contacts: Optional[list] = None, step_check: Optional[dict] = None,
                     freecad_version: Optional[str] = None) -> dict:
    records = [body_record(b) for b in bodies]
    physical = [r for r, b in zip(records, bodies) if b.role in PHYSICAL_ROLES]
    mass_by_material: Dict[str, float] = {}
    for rec in physical:
        mass_by_material[rec["material"]] = mass_by_material.get(rec["material"], 0.0) + rec["mass_kg"]
    phys_shapes = [b.shape for b in bodies if b.role in PHYSICAL_ROLES]
    bb = bbox_of(phys_shapes) if phys_shapes else [0] * 6
    # mesh hints: map resolved region hints to the actual bodies, default for the rest
    hints = dict(resolved.get("mesh_hints", {}))
    regions = []
    covered = set()
    for region in hints.get("regions", []):
        names = []
        for pattern in region.get("bodies", []):
            for rec in records:
                short = rec["name"].split(".", 1)[1] if (rec["group"] and rec["name"].startswith(rec["group"] + ".")) else rec["name"]
                if short == pattern or rec["name"] == pattern or rec["name"].endswith("." + pattern):
                    names.append(rec["name"])
                    covered.add(rec["name"])
        if names:
            regions.append(dict(region, bodies=sorted(set(names))))
    for rec in records:
        if rec["name"] not in covered and rec["role"] in PHYSICAL_ROLES:
            regions.append({"bodies": [rec["name"]], "group": rec["group"] or rec["name"], "material": rec["material"],
                            "element_size": _element_size_default(rec), "note": "default size from the body bounding box"})
    hints["regions"] = regions
    hints["material_tags"] = sorted({r["material"] for r in physical})
    hints["net_tags"] = sorted({r["net"] for r in physical if r["net"]})
    hints["body_count"] = len(physical)
    return {
        "schema": "aipe-cad-metadata/0.1", "kind": kind, "name": name,
        "units": {"length": "m", "area": "m^2", "volume": "m^3", "mass": "kg", "note": "FreeCAD geometry is in mm; converted here"},
        "generator": {"package": "aipe_cad", "freecad_version": freecad_version},
        "files": files,
        "totals": {"bbox_m": bbox_mm_to_m(bb), "size_m": [mm_to_m(bb[3] - bb[0]), mm_to_m(bb[4] - bb[1]), mm_to_m(bb[5] - bb[2])],
                   "volume_m3": sum(r["volume_m3"] for r in physical), "mass_kg": sum(r["mass_kg"] for r in physical),
                   "surface_area_m2": sum(r["surface_area_m2"] for r in physical), "body_count": len(physical),
                   "mass_by_material_kg": mass_by_material},
        "bodies": records,
        "contacts": contacts or [],
        "step_reimport": step_check,
        "analytic": {k: v for k, v in resolved.items() if k in ("analytic", "analytic_masses")},
        "warnings": resolved.get("warnings", []),
        "mesh_hints": hints,
        "parameters": params,
    }
