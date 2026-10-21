"""Explicit unit conversions.

All parameter files, metadata and check reports use SI units (metres, square
metres, cubic metres, kilograms).  FreeCAD's geometry kernel works in
millimetres, so the FreeCAD workers convert at the boundary with the helpers
below and never mix the two systems inside one function.
"""
from __future__ import annotations

from typing import Iterable, Sequence

MM_PER_M = 1000.0


def m_to_mm(value_m: float) -> float:
    """Convert a length in metres to millimetres (FreeCAD internal unit)."""
    return float(value_m) * MM_PER_M


def mm_to_m(value_mm: float) -> float:
    """Convert a length in millimetres (FreeCAD) to metres (SI)."""
    return float(value_mm) / MM_PER_M


def mm2_to_m2(area_mm2: float) -> float:
    """Convert an area reported by FreeCAD (mm^2) to m^2."""
    return float(area_mm2) * 1e-6


def mm3_to_m3(volume_mm3: float) -> float:
    """Convert a volume reported by FreeCAD (mm^3) to m^3."""
    return float(volume_mm3) * 1e-9


def m3_to_mm3(volume_m3: float) -> float:
    return float(volume_m3) * 1e9


def vec_m_to_mm(values: Iterable[float]) -> tuple:
    return tuple(m_to_mm(v) for v in values)


def vec_mm_to_m(values: Iterable[float]) -> tuple:
    return tuple(mm_to_m(v) for v in values)


def bbox_mm_to_m(bbox_mm: Sequence[float]) -> list:
    """Convert a [xmin, ymin, zmin, xmax, ymax, zmax] bounding box to metres."""
    return [mm_to_m(v) for v in bbox_mm]
