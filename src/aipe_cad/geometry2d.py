"""Closed-form 2-D helpers shared by the parameter layer and the FreeCAD workers.

Used both for analytic cross-checks of FreeCAD volumes and for mean-length-of-
turn estimates.  Pure Python, SI or any consistent unit system.
"""
from __future__ import annotations

import math


def rounded_rect_area(width: float, height: float, radius: float) -> float:
    """Area of a rectangle with four quarter-circle corners of ``radius``."""
    _check_rounded(width, height, radius)
    return width * height - (4.0 - math.pi) * radius * radius


def rounded_rect_perimeter(width: float, height: float, radius: float) -> float:
    _check_rounded(width, height, radius)
    return 2.0 * (width + height) - 8.0 * radius + 2.0 * math.pi * radius


def rounded_annulus_area(inner_width: float, inner_height: float, inner_radius: float, thickness: float) -> float:
    """Area between two concentric rounded rectangles offset by ``thickness``."""
    if thickness < 0:
        raise ValueError("thickness must be non-negative")
    outer = rounded_rect_area(inner_width + 2 * thickness, inner_height + 2 * thickness, inner_radius + thickness)
    return outer - rounded_rect_area(inner_width, inner_height, inner_radius)


def half_annulus_area(outer_radius: float, inner_radius: float) -> float:
    if not 0 <= inner_radius < outer_radius:
        raise ValueError("require 0 <= inner_radius < outer_radius")
    return 0.5 * math.pi * (outer_radius ** 2 - inner_radius ** 2)


def _check_rounded(width: float, height: float, radius: float) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("width and height must be positive")
    if radius < 0 or 2 * radius > min(width, height) + 1e-12:
        raise ValueError("corner radius must satisfy 0 <= r <= min(width, height)/2")
