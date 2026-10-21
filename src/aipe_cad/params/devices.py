"""Semiconductor package outlines (SI metres).

The built-in ``to247_4l`` profile uses nominal (mid-tolerance) values read from
the package outline drawing in the Wolfspeed C3M0032120K data sheet
(TO-247-4L, drawing rev. 02, 2024-03-04):
https://assets.wolfspeed.com/uploads/2024/01/Wolfspeed_C3M0032120K_data_sheet.pdf

Symbol mapping used here (drawing min/max in mm -> nominal):
  A  4.83-5.21  body thickness            -> 5.02
  E  15.75-16.13 body width               -> 15.94
  D  23.30-23.63 body length w/o leads    -> 23.47
  P  3.51-3.65  mounting hole diameter    -> 3.58
  Q  5.49-6.00  hole centre to body top   -> 5.75  (assumed meaning of Q)
  E1 13.1-14.15 exposed metal width       -> 13.6
  D1 16.25-17.65 exposed metal length     -> 16.95
  b  1.07-1.33  lead width                -> 1.20
  c  0.55-0.68  lead thickness            -> 0.60
  L  17.31-17.82 lead length              -> 17.6
  e1 5.08 BSC   drain-source lead pitch; remaining pitch 2.54 (standard TO-247 grid)
The metal tab thickness is *not* dimensioned on the drawing; 1.5 mm is an
assumption.  Verify every value against the current drawing before relying on
it; the outline is illustrative, not a qualified footprint.
"""
from __future__ import annotations

from typing import Optional

from .base import Errors, check_known_keys, get_bool, get_number, get_str, get_vector

PACKAGE_LIBRARY = {
    "to247_4l": {
        "description": "TO-247-4L (Wolfspeed drawing nominal values; see module docstring)",
        "reference": "https://assets.wolfspeed.com/uploads/2024/01/Wolfspeed_C3M0032120K_data_sheet.pdf",
        "body_length": 23.47e-3,
        "body_width": 15.94e-3,
        "body_thickness": 5.02e-3,
        "hole_diameter": 3.58e-3,
        "hole_offset_from_top": 5.75e-3,
        "tab_length": 16.95e-3,
        "tab_width": 13.6e-3,
        "tab_thickness": 1.5e-3,
        "lead_width": 1.20e-3,
        "lead_thickness": 0.60e-3,
        "lead_length": 17.6e-3,
        "lead_offsets": [-5.08e-3, 0.0, 2.54e-3, 5.08e-3],
        "lead_names": ["drain", "source", "driver_source", "gate"],
        "body_material": "epoxy_mold_compound",
        "tab_material": "copper",
        "lead_material": "copper",
    },
    "to247_3": {
        "description": "Generic 3-lead TO-247 envelope (approximate JEDEC TO-247 proportions; verify against the device drawing)",
        "reference": "",
        "body_length": 21.0e-3,
        "body_width": 15.9e-3,
        "body_thickness": 5.0e-3,
        "hole_diameter": 3.6e-3,
        "hole_offset_from_top": 5.9e-3,
        "tab_length": 15.0e-3,
        "tab_width": 13.0e-3,
        "tab_thickness": 1.5e-3,
        "lead_width": 1.2e-3,
        "lead_thickness": 0.6e-3,
        "lead_length": 20.0e-3,
        "lead_offsets": [-5.45e-3, 0.0, 5.45e-3],
        "lead_names": ["gate", "drain", "source"],
        "body_material": "epoxy_mold_compound",
        "tab_material": "copper",
        "lead_material": "copper",
    },
}

PACKAGE_KEYS = set(PACKAGE_LIBRARY["to247_4l"])


def package_profile(spec, errors: Errors) -> dict:
    """Return a complete package profile from a library name or an inline object.

    ``spec`` may be a string (library key) or an object with a ``base`` key plus
    overrides, or a fully specified object.
    """
    if isinstance(spec, str):
        if spec not in PACKAGE_LIBRARY:
            errors.add(f"unknown package '{spec}'; known: {', '.join(sorted(PACKAGE_LIBRARY))}")
            return dict(PACKAGE_LIBRARY["to247_4l"])
        return dict(PACKAGE_LIBRARY[spec])
    if not isinstance(spec, dict):
        errors.add("package must be a library name or an object")
        return dict(PACKAGE_LIBRARY["to247_4l"])
    base_name = get_str(spec, "base", "to247_4l", errors, choices=PACKAGE_LIBRARY)
    profile = dict(PACKAGE_LIBRARY.get(base_name, PACKAGE_LIBRARY["to247_4l"]))
    check_known_keys(spec, PACKAGE_KEYS | {"base"}, errors)
    for key in ("body_length", "body_width", "body_thickness", "hole_diameter", "hole_offset_from_top",
                "tab_length", "tab_width", "tab_thickness", "lead_width", "lead_thickness", "lead_length"):
        profile[key] = get_number(spec, key, profile[key], errors, positive=True)
    for key in ("description", "reference", "body_material", "tab_material", "lead_material"):
        profile[key] = get_str(spec, key, profile[key], errors)
    if "lead_offsets" in spec:
        offsets = spec["lead_offsets"]
        if not isinstance(offsets, list) or not offsets or not all(isinstance(v, (int, float)) for v in offsets):
            errors.add("lead_offsets must be a non-empty list of numbers")
        else:
            profile["lead_offsets"] = [float(v) for v in offsets]
    if "lead_names" in spec:
        names = spec["lead_names"]
        if not isinstance(names, list) or not all(isinstance(v, str) for v in names):
            errors.add("lead_names must be a list of strings")
        else:
            profile["lead_names"] = list(names)
    if len(profile["lead_names"]) != len(profile["lead_offsets"]):
        profile["lead_names"] = [f"lead{i + 1}" for i in range(len(profile["lead_offsets"]))]
    # Geometric consistency
    if profile["tab_length"] > profile["body_length"] or profile["tab_width"] > profile["body_width"]:
        errors.add("tab footprint must fit inside the body footprint")
    if profile["tab_thickness"] >= profile["body_thickness"]:
        errors.add("tab_thickness must be smaller than body_thickness")
    if profile["hole_offset_from_top"] + profile["hole_diameter"] / 2 >= profile["body_length"]:
        errors.add("mounting hole must lie inside the body length")
    span = max(abs(v) for v in profile["lead_offsets"]) * 2 + profile["lead_width"]
    if span > profile["body_width"]:
        errors.add("lead offsets exceed the body width")
    return profile


def lead_form(spec, profile: dict, errors: Errors) -> dict:
    """Lead bend geometry: horizontal run from the body then a vertical run (L-shape)."""
    spec = spec or {}
    if not isinstance(spec, dict):
        errors.add("lead_form must be an object")
        spec = {}
    check_known_keys(spec, {"horizontal", "vertical"}, errors)
    horizontal = get_number(spec, "horizontal", 3.0e-3, errors, non_negative=True)
    vertical = get_number(spec, "vertical", 12.0e-3, errors, non_negative=True)
    if horizontal + vertical > profile["lead_length"] + 1e-12:
        errors.add(f"lead form horizontal+vertical ({horizontal + vertical:.4g} m) exceeds the lead length "
                   f"({profile['lead_length']:.4g} m)")
    return {"horizontal": horizontal, "vertical": vertical}


def fastener_spec(spec, profile: dict, errors: Errors) -> Optional[dict]:
    """Insulating shoulder bushing plus metal screw holding the device on the plate (null = not modelled)."""
    if spec is None:
        return None
    if not isinstance(spec, dict):
        errors.add("fastener must be an object or null")
        spec = {}
    check_known_keys(spec, {"enabled", "screw", "screw_diameter", "head_diameter", "head_height", "screw_material", "screw_net",
                            "bushing", "shoulder_diameter", "shoulder_thickness", "bushing_material"}, errors)
    if not get_bool(spec, "enabled", True, errors):
        return None
    f = {
        "screw": get_bool(spec, "screw", True, errors),
        "screw_diameter": get_number(spec, "screw_diameter", 3.0e-3, errors, positive=True),
        "head_diameter": get_number(spec, "head_diameter", 5.5e-3, errors, positive=True),
        "head_height": get_number(spec, "head_height", 3.0e-3, errors, positive=True),
        "screw_material": get_str(spec, "screw_material", "steel", errors),
        "screw_net": get_str(spec, "screw_net", None, errors),
        "bushing": get_bool(spec, "bushing", True, errors),
        "shoulder_diameter": get_number(spec, "shoulder_diameter", 7.0e-3, errors, positive=True),
        "shoulder_thickness": get_number(spec, "shoulder_thickness", 1.0e-3, errors, positive=True),
        "bushing_material": get_str(spec, "bushing_material", "nylon_pa66", errors),
    }
    if f["bushing"]:
        errors.check(f["screw_diameter"] < profile["hole_diameter"], "fastener screw_diameter must be smaller than the package hole (bushing sleeve wall)")
        errors.check(f["shoulder_diameter"] <= profile["body_width"], "fastener shoulder_diameter exceeds the body width")
        errors.check(profile["hole_offset_from_top"] - 0.5 * f["shoulder_diameter"] >= -1e-12, "fastener shoulder extends beyond the body top edge")
    else:
        errors.check(f["screw_diameter"] <= profile["hole_diameter"], "fastener screw_diameter exceeds the package hole")
    return f


def device_placement(spec: dict, index: int, errors: Errors, default_net: str = "device") -> dict:
    """Validate one device entry of a heat sink / cold plate parameter object."""
    ctx = Errors(f"devices[{index}]")
    check_known_keys(spec, {"name", "package", "position", "rotation_deg", "net", "lead_nets", "pad", "screw_hole_diameter",
                            "lead_form", "overhang_allowed", "fastener"}, ctx)
    name = get_str(spec, "name", f"Q{index + 1}", ctx)
    profile = package_profile(spec.get("package", "to247_4l"), ctx)
    position = get_vector(spec, "position", [0.0, 0.0], ctx, length=2)
    rotation = get_number(spec, "rotation_deg", 0.0, ctx)
    net = get_str(spec, "net", default_net, ctx)
    lead_nets = spec.get("lead_nets")
    if lead_nets is not None:
        if not isinstance(lead_nets, list) or len(lead_nets) != len(profile["lead_offsets"]) \
                or not all(isinstance(v, str) for v in lead_nets):
            ctx.add("lead_nets must list one net name per lead")
            lead_nets = None
    pad = spec.get("pad", {})
    if pad is None:
        pad = None
    else:
        if not isinstance(pad, dict):
            ctx.add("pad must be an object or null")
            pad = {}
        check_known_keys(pad, {"thickness", "oversize", "material", "density"}, ctx)
        pad = {
            "thickness": get_number(pad, "thickness", 0.25e-3, ctx, positive=True),
            "oversize": get_number(pad, "oversize", 1.5e-3, ctx, non_negative=True),
            "material": get_str(pad, "material", "alumina", ctx),
            "density": get_number(pad, "density", None, ctx, positive=True),
        }
    screw = get_number(spec, "screw_hole_diameter", 3.2e-3, ctx, positive=True)
    form = lead_form(spec.get("lead_form"), profile, ctx)
    fastener = fastener_spec(spec.get("fastener", {}), profile, ctx)
    errors.extend(ctx)
    return {
        "name": name,
        "package": profile,
        "position": position,
        "rotation_deg": rotation,
        "net": net,
        "lead_nets": lead_nets,
        "pad": pad,
        "screw_hole_diameter": screw,
        "lead_form": form,
        "fastener": fastener,
        "overhang_allowed": get_bool(spec, "overhang_allowed", True, ctx),
    }
