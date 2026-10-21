"""JSON Schema (draft 2020-12) definitions for every parameter kind.

The schemas are defined once here, written to ``aipe_cad/schemas/*.json`` by
:func:`write_schema_files` (committed for external tools) and used by
:func:`validate_params` through ``jsonschema``.  All lengths are SI metres.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from . import KINDS
from .materials import MATERIALS
from .params.devices import PACKAGE_LIBRARY

SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
BASE_ID = "https://raw.githubusercontent.com/FulongLi/AIPE-CAD-Agent/main/src/aipe_cad/schemas/"


def _len(desc: str, positive: bool = True, default=None) -> dict:
    s: Dict[str, Any] = {"type": "number", "description": f"{desc} [m]"}
    s["exclusiveMinimum" if positive else "minimum"] = 0
    if default is not None:
        s["default"] = default
    return s


def _num(desc: str, default=None, **extra) -> dict:
    s: Dict[str, Any] = {"type": "number", "description": desc}
    s.update(extra)
    if default is not None:
        s["default"] = default
    return s


def _int(desc: str, minimum: int = 1, default=None) -> dict:
    s: Dict[str, Any] = {"type": "integer", "minimum": minimum, "description": desc}
    if default is not None:
        s["default"] = default
    return s


def _str(desc: str, default=None, enum=None) -> dict:
    s: Dict[str, Any] = {"type": "string", "description": desc}
    if enum is not None:
        s["enum"] = list(enum)
    if default is not None:
        s["default"] = default
    return s


def _bool(desc: str, default: bool) -> dict:
    return {"type": "boolean", "description": desc, "default": default}


def _obj(properties: dict, required: List[str] = (), desc: str = "", **extra) -> dict:
    s: Dict[str, Any] = {"type": "object", "additionalProperties": False, "properties": properties}
    if required:
        s["required"] = list(required)
    if desc:
        s["description"] = desc
    s.update(extra)
    return s


def _nullable(schema: dict) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


MATERIAL = _str("material name from aipe_cad.materials.MATERIALS", enum=sorted(MATERIALS))
NET = _str("electrical net / potential group used by the clearance checks (e.g. primary, secondary, pe)")
DENSITY = _nullable(_num("density override [kg/m^3]", exclusiveMinimum=0))

PAD = _nullable(_obj({
    "thickness": _len("isolation pad thickness", default=0.25e-3),
    "oversize": _len("pad overhang beyond the device tab footprint, all round", positive=False, default=1.5e-3),
    "material": dict(MATERIAL, default="alumina"),
    "density": DENSITY,
}, desc="electrical isolation pad between the device tab and the plate (null = none)"))

PACKAGE_INLINE = _obj({
    "base": _str("library package to start from", default="to247_4l", enum=sorted(PACKAGE_LIBRARY)),
    "description": _str("free text"), "reference": _str("drawing URL"),
    "body_length": _len("plastic body length without leads"), "body_width": _len("body width"),
    "body_thickness": _len("body thickness"), "hole_diameter": _len("mounting hole diameter"),
    "hole_offset_from_top": _len("hole centre from the top (lead-free) body edge"),
    "tab_length": _len("exposed metal tab length"), "tab_width": _len("exposed metal tab width"),
    "tab_thickness": _len("metal tab thickness (assumption, not dimensioned on drawings)"),
    "lead_width": _len("lead width"), "lead_thickness": _len("lead thickness"), "lead_length": _len("straight lead length"),
    "lead_offsets": {"type": "array", "minItems": 1, "items": {"type": "number"}, "description": "lead centre offsets across the body width [m]"},
    "lead_names": {"type": "array", "items": {"type": "string"}},
    "body_material": MATERIAL, "tab_material": MATERIAL, "lead_material": MATERIAL,
})

DEVICE = _obj({
    "name": _str("device instance name (unique)"),
    "package": {"anyOf": [_str("library package", enum=sorted(PACKAGE_LIBRARY)), PACKAGE_INLINE], "default": "to247_4l"},
    "position": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"},
                 "description": "body centre on the plate top face [m, m]"},
    "rotation_deg": _num("rotation about the device centre (0 = leads towards +X)", default=0.0),
    "net": NET,
    "lead_nets": _nullable({"type": "array", "items": {"type": "string"}, "description": "one net per lead (default: device net)"}),
    "pad": PAD,
    "screw_hole_diameter": _len("screw hole in the plate under the device mounting hole", default=3.2e-3),
    "lead_form": _obj({"horizontal": _len("straight run from the body before the bend", positive=False, default=3e-3),
                       "vertical": _len("vertical run after the bend", positive=False, default=12e-3)}),
    "overhang_allowed": _bool("allow the plastic body to overhang the plate edge", True),
    "fastener": _nullable(_obj({
        "enabled": _bool("model the fastener", True),
        "screw": _bool("model the metal screw (head on the bushing shoulder, shank into the plate hole)", True),
        "screw_diameter": _len("screw nominal diameter", default=3e-3),
        "head_diameter": _len("screw head diameter", default=5.5e-3),
        "head_height": _len("screw head height", default=3e-3),
        "screw_material": dict(MATERIAL, default="steel"),
        "screw_net": _nullable(dict(NET, description="net of the screw (default: plate net)")),
        "bushing": _bool("model an insulating shoulder bushing filling the package and pad holes", True),
        "shoulder_diameter": _len("bushing shoulder (flange) diameter on the body top", default=7e-3),
        "shoulder_thickness": _len("bushing shoulder thickness", default=1e-3),
        "bushing_material": dict(MATERIAL, default="nylon_pa66"),
    }, desc="isolation hardware of the device mounting (null = not modelled)")),
}, required=["position"])

CLEARANCE_PAIR = _obj({
    "net_a": NET, "net_b": NET,
    "required_clearance": _len("caller-supplied minimum air clearance", positive=False),
    "required_creepage": _len("caller-supplied minimum creepage (only compared against clearance; surface paths are not traced)", positive=False),
    "note": _str("free text"),
}, required=["net_a", "net_b", "required_clearance"])

FIT_PAIR = _obj({
    "a": _str("body name (component builds) or instance.body (assemblies)"), "b": _str("body name"),
    "expected_gap": _len("expected distance", positive=False), "tolerance": _len("tolerance on expected_gap", positive=False),
    "min_gap": _len("minimum acceptable distance", positive=False), "max_gap": _len("maximum acceptable distance", positive=False),
    "note": _str("free text"),
}, required=["a", "b"])

CHECKS = _obj({
    "interference": _obj({"enabled": _bool("pairwise common-volume check of all solids", True),
                          "min_overlap_volume": _num("common volume above which two solids are reported as interfering [m^3]", default=1e-12, minimum=0),
                          "allowed_overlaps": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}},
                                               "description": "pairs of fnmatch name patterns whose overlap is intentional"}}),
    "keepouts": _obj({"enabled": _bool("report solids intruding into keep-out volumes", True),
                      "ignore_pairs": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}},
                                       "description": "pairs of fnmatch patterns [keepout, body] to ignore"}}),
    "envelopes": _obj({"report_intrusions": _bool("report solids of other components intruding into clearance envelopes", True),
                       "ignore_pairs": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}},
                                        "description": "pairs of fnmatch patterns [envelope, body] to ignore (e.g. chassis under fins)"}}),
    "clearance_pairs": {"type": "array", "items": CLEARANCE_PAIR},
    "fit_pairs": {"type": "array", "items": FIT_PAIR},
}, desc="check configuration; required values are inputs supplied by the caller, no standard compliance is asserted")

MOUNTING_HOLES = _nullable(_obj({"diameter": _len("hole diameter"), "inset": _len("hole centre inset from the plate corner edges"),
                                 "enabled": _bool("set false to omit", True)}))


def transformer_schema() -> dict:
    conductor = _obj({
        "type": _str("conductor construction", enum=["litz", "round", "foil"]),
        "outer_diameter": _len("litz/round: overall diameter including serving or enamel"),
        "strand_count": _int("litz: number of strands (round: 1)", default=1),
        "strand_diameter": _len("litz: bare strand diameter; round: bare conductor diameter"),
        "foil_thickness": _len("foil: copper thickness"),
        "foil_width": _len("foil: width (default: full available winding width)"),
        "insulation_thickness": _len("inter-layer (litz/round) or inter-turn (foil) insulation", positive=False, default=0.0),
        "fill_factor": _num("copper fraction of the winding body volume for mass estimates (default 0.40 litz, 0.75 round, foil ratio)",
                            exclusiveMinimum=0, maximum=1),
    }, required=["type"])
    winding = _obj({
        "name": _str("winding name (unique)"), "turns": _int("number of turns"),
        "conductor": conductor,
        "margin": _len("margin (creepage distance) between the winding ends and the bobbin flanges", positive=False, default=0.0),
        "parallel": _int("parallel conductors wound side by side", default=1),
        "net": NET, "terminal_count": _int("pins for this winding", minimum=0, default=2),
        "terminal_side": _str("which flange overhang carries the pins", enum=["-y", "+y"]),
        "material": dict(MATERIAL, default="copper"),
    }, required=["turns", "conductor"])
    return {
        "$schema": DRAFT, "$id": BASE_ID + "transformer.schema.json",
        "title": "AIPE CAD transformer parameters",
        "description": "E-core transformer with bobbin, windings, insulation barriers, terminals and mounting. SI units (metres, kilograms). "
                       "Local frame: centre-leg axis = Z, mating plane z = 0, core width along X, depth along Y.",
        **_obj({
            "kind": _str("parameter kind", enum=["transformer"]),
            "name": _str("model name used for output files", default="transformer"),
            "description": _str("free text"),
            "core": _obj({
                "shape": _str("core family", default="E", enum=["E"]),
                "total_width": _len("A: overall core width"), "half_height": _len("B: height of one E half"),
                "depth": _len("F: core depth"), "window_height": _len("D: window height of one half"),
                "inner_width": _len("C: distance between the inner faces of the outer legs"),
                "centre_leg_width": _len("E: centre leg width"),
                "air_gap": _len("total centre-leg air gap, split between the halves", positive=False, default=0.0),
                "material": dict(MATERIAL, default="ferrite_n87"), "density": DENSITY,
                "net": dict(NET, default="pe"), "reference": _str("data sheet / drawing citation"),
            }, required=["total_width", "half_height", "depth", "window_height", "inner_width", "centre_leg_width"]),
            "bobbin": _obj({
                "wall_thickness": _len("tube wall", default=1.5e-3), "flange_thickness": _len("flange thickness", default=1.5e-3),
                "core_clearance": _len("centre leg to tube inner surface", positive=False, default=0.3e-3),
                "window_clearance": _len("flange/stack to core clearance", positive=False, default=0.5e-3),
                "pin_strip_width": _len("flange overhang beyond the maximum build carrying the pins", default=6e-3),
                "corner_radius": _len("tube outer corner radius", positive=False, default=1e-3),
                "material": dict(MATERIAL, default="bobbin_pet_gf"), "density": DENSITY,
                "tube_wrap": _len("insulation on the tube before the first winding", positive=False, default=0.0),
            }),
            "windings": {"type": "array", "minItems": 1, "items": winding, "description": "inner to outer"},
            "insulation": _obj({
                "inter_winding_barrier": _len("barrier thickness between successive windings", positive=False, default=0.5e-3),
                "outer_wrap": _len("wrap outside the last winding", positive=False, default=0.3e-3),
                "fill_margins": _bool("model the margins as insulating blocks", True),
                "material": dict(MATERIAL, default="kapton"), "density": DENSITY,
            }),
            "terminals": _obj({
                "style": _str("terminal style", default="pin", enum=["pin"]),
                "diameter": _len("pin diameter", default=1.5e-3), "length": _len("pin length", default=12e-3),
                "pitch": _len("pin pitch", default=5e-3),
                "flange": _str("flange carrying the pins", default="top", enum=["top", "bottom"]),
                "direction": _str("pin direction (must point away from the bobbin)", default="+z", enum=["+z", "-z"]),
                "material": dict(MATERIAL, default="brass"),
            }),
            "mounting": _obj({
                "clips": _bool("two core clips", True), "clip_thickness": _len("clip strip thickness", default=0.8e-3),
                "clip_width": _len("clip width along Y", default=10e-3), "clip_inset": _len("clip inset from the core depth faces", positive=False, default=2e-3),
                "clip_material": dict(MATERIAL, default="stainless_steel"),
                "base_plate": _bool("base plate under the core", True), "plate_thickness": _len("base plate thickness", default=2e-3),
                "plate_margin_x": _len("plate extension beyond the core width per side", positive=False, default=12e-3),
                "hole_diameter": _len("base plate hole diameter", default=4.5e-3), "hole_inset": _len("hole inset from the plate corners", default=6e-3),
                "plate_material": dict(MATERIAL, default="aluminium_6063"), "net": dict(NET, default="pe"),
            }),
            "clearance_envelope_margin": _len("margin of the clearance envelope around the transformer", positive=False, default=5e-3),
            "checks": CHECKS,
        }, required=["core", "windings"]),
    }


def heatsink_body() -> dict:
    return _obj({
        "kind": _str("parameter kind", enum=["heatsink"]),
        "name": _str("model name", default="heatsink"), "description": _str("free text"),
        "base": _obj({"length": _len("base length along X (fin direction)"), "width": _len("base width along Y"),
                      "thickness": _len("base thickness"), "material": dict(MATERIAL, default="aluminium_6063"), "density": DENSITY},
                     required=["length", "width", "thickness"]),
        "fins": _obj({"thickness": _len("fin thickness"), "height": _len("fin height below the base"),
                      "pitch": _len("fin pitch (count = floor((W - t) / pitch) + 1 unless given)"),
                      "count": _nullable(_int("explicit fin count (must fit)")),
                      "length": _nullable(_len("fin length along X (default: full base length)"))},
                     required=["thickness", "height", "pitch"]),
        "devices": {"type": "array", "items": DEVICE},
        "mounting_holes": MOUNTING_HOLES,
        "net": dict(NET, default="pe"),
        "clearance_envelope_margin": _len("envelope margin", positive=False, default=3e-3),
        "checks": CHECKS,
    }, required=["base", "fins"])


def heatsink_schema() -> dict:
    return {"$schema": DRAFT, "$id": BASE_ID + "heatsink.schema.json", "title": "AIPE CAD plate-fin heat sink parameters",
            "description": "Plate-fin heat sink with device footprints, isolation pads and mounting holes. SI units. Local frame: base underside z = 0, fins at z < 0, devices on top.",
            **heatsink_body()}


def coldplate_body() -> dict:
    return _obj({
        "kind": _str("parameter kind", enum=["coldplate"]),
        "name": _str("model name", default="coldplate"), "description": _str("free text"),
        "plate": _obj({"length": _len("plate length along X (channel pass direction)"), "width": _len("plate width along Y"),
                       "thickness": _len("plate thickness"), "material": dict(MATERIAL, default="aluminium_6063"), "density": DENSITY},
                      required=["length", "width", "thickness"]),
        "channel": _obj({"width": _len("channel width"), "depth": _len("channel depth from the underside"),
                         "passes": _int("number of serpentine passes", default=4),
                         "pitch": _nullable(_len("pass pitch (default: spread evenly inside the edge margins)")),
                         "edge_margin": _len("minimum distance from the channel to the long edges", default=12e-3),
                         "end_margin": _len("distance from the channel extents to the end faces", default=15e-3),
                         "min_wall": _len("minimum wall thickness (webs, above the channel)", default=2e-3)},
                        required=["width", "depth"]),
        "cover": _nullable(_obj({"thickness": _len("cover plate thickness", default=3e-3), "material": dict(MATERIAL, default="aluminium_6063")})),
        "ports": _obj({"style": _str("port style", default="boss", enum=["boss"]), "outer_diameter": _len("boss outer diameter", default=12e-3),
                       "bore": _len("bore diameter", default=6e-3), "length": _len("boss length beyond the end face", default=20e-3),
                       "material": dict(MATERIAL, default="brass")}),
        "coolant": _obj({"material": dict(MATERIAL, default="water_glycol_50")}),
        "devices": {"type": "array", "items": DEVICE},
        "screw_hole_depth": _len("blind screw hole depth from the top", default=6e-3),
        "mounting_holes": _nullable(_obj({"diameter": _len("hole diameter"), "inset": _len("inset from the corners")})),
        "net": dict(NET, default="pe"),
        "clearance_envelope_margin": _len("envelope margin", positive=False, default=3e-3),
        "checks": CHECKS,
    }, required=["plate", "channel"])


def coldplate_schema() -> dict:
    return {"$schema": DRAFT, "$id": BASE_ID + "coldplate.schema.json", "title": "AIPE CAD liquid cold plate parameters",
            "description": "Cold plate with a boolean-cut serpentine channel, cover, hose bosses and device footprints. SI units. Local frame: channel face z = 0, plate above, cover below.",
            **coldplate_body()}


def assembly_schema() -> dict:
    ref_obj = _obj({"$ref": _str("relative path to a component parameter JSON file")}, required=["$ref"],
                   desc="external parameter file; sibling keys override the loaded document", additionalProperties=True)
    ref_obj["additionalProperties"] = True
    position = {"type": "array", "minItems": 3, "maxItems": 3, "description": "[x, y, z] in metres; z may be a placement keyword",
                "prefixItems": [{"type": "number"}, {"type": "number"}, {"anyOf": [{"type": "number"}, {"type": "string"}]}]}
    tr = transformer_schema()
    tr_body = {k: v for k, v in tr.items() if k in ("type", "additionalProperties", "properties", "required")}
    board = _obj({
        "name": _str("board name (unique)"),
        "size": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number", "exclusiveMinimum": 0}, "description": "outline [lx, ly] [m]"},
        "thickness": _len("laminate thickness", default=1.6e-3),
        "position": position, "rotation_deg": _num("rotation about Z", default=0.0),
        "material": dict(MATERIAL, default="fr4"),
        "copper_zones": {"type": "array", "items": _obj({"name": _str("zone name"),
                                                           "offset": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
                                                           "size": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number", "exclusiveMinimum": 0}},
                                                           "net": NET, "thickness": _len("copper thickness", default=70e-6),
                                                           "side": _str("board side", default="top", enum=["top", "bottom"])})},
        "keepouts": {"type": "array", "items": _obj({"name": _str("keep-out name"),
                                                       "offset": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "number"}},
                                                       "size": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number", "exclusiveMinimum": 0},
                                                                "description": "[lx, ly, height] [m]"},
                                                       "side": _str("board side", default="top", enum=["top", "bottom"])})},
        "mounting_holes": _nullable(_obj({"diameter": _len("hole diameter", default=3.2e-3), "inset": _len("inset from corners", default=5e-3)})),
        "standoffs": _obj({"enabled": _bool("standoffs from the support surface below each mounting hole", True),
                           "diameter": _len("standoff diameter", default=6e-3), "material": dict(MATERIAL, default="nylon_pa66"),
                           "net": _nullable(NET)}),
        "lead_holes": _obj({"enabled": _bool("cut clearance holes for device leads passing through the board", True),
                            "clearance": _len("radial clearance around the lead", positive=False, default=0.4e-3)}),
    }, required=["name", "size", "position"])
    connector = _obj({
        "name": _str("connector name"), "type": _str("connector type", default="dc_terminal_block", enum=["dc_terminal_block"]),
        "position": position, "rotation_deg": _num("rotation about Z", default=0.0),
        "body_size": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number", "exclusiveMinimum": 0}, "description": "housing [lx, ly, lz] [m]"},
        "poles": _int("number of poles", default=2), "pole_pitch": _len("pole pitch", default=12.5e-3),
        "pin_diameter": _len("terminal pin/screw diameter", default=6e-3), "pin_length": _len("pin length above the housing", default=8e-3),
        "net": NET, "housing_material": dict(MATERIAL, default="nylon_pa66"), "pin_material": dict(MATERIAL, default="brass"),
    }, required=["name", "position"])
    return {
        "$schema": DRAFT, "$id": BASE_ID + "assembly.schema.json", "title": "AIPE CAD converter assembly parameters",
        "description": "Converter assembly in one coordinate system (origin at the chassis top-face centre, X long axis, Z up). SI units.",
        "$defs": {"heatsink": heatsink_body(), "coldplate": coldplate_body(), "transformer": tr_body},
        **_obj({
            "kind": _str("parameter kind", enum=["assembly"]),
            "name": _str("model name", default="assembly"), "description": _str("free text"),
            "chassis": _nullable(_obj({"length": _len("chassis length along X", default=0.4), "width": _len("chassis width along Y", default=0.25),
                                       "thickness": _len("chassis plate thickness", default=3e-3), "material": dict(MATERIAL, default="aluminium_6063"),
                                       "net": dict(NET, default="pe"), "cutouts_under_heatsinks": _bool("cut airflow openings under the fin regions", True),
                                       "cutout_clearance": _len("clearance around the fin region", positive=False, default=2e-3),
                                       "min_rim": _len("minimum base rim resting on the chassis around a cut-out", positive=False, default=3e-3)})),
            "cooling": _obj({"variant": _str("cooling variant", default="heatsinks", enum=["heatsinks", "coldplate", "none"]),
                             "heatsink": {"anyOf": [ref_obj, {"$ref": "#/$defs/heatsink"}]},
                             "coldplate": {"anyOf": [ref_obj, {"$ref": "#/$defs/coldplate"}]},
                             "placements": {"type": "array", "items": _obj({"name": _str("instance name"), "position": position,
                                                                              "rotation_deg": _num("rotation about Z", default=0.0),
                                                                              "device_net": _nullable(NET),
                                                                              "params": {"type": "object", "description": "shallow overrides of the component parameters"}})}}),
            "transformer": _nullable(_obj({"name": _str("instance name", default="transformer"),
                                           "params": {"anyOf": [ref_obj, {"$ref": "#/$defs/transformer"}]},
                                           "position": position, "rotation_deg": _num("rotation about Z", default=0.0)})),
            "boards": {"type": "array", "items": board},
            "connectors": {"type": "array", "items": connector},
            "clearance_envelope_margin": _len("assembly-level envelope margin (0 = none)", positive=False, default=0.0),
            "checks": CHECKS,
        }),
    }


SCHEMA_BUILDERS = {
    "transformer": transformer_schema,
    "heatsink": heatsink_schema,
    "coldplate": coldplate_schema,
    "assembly": assembly_schema,
}


def get_schema(kind: str) -> dict:
    if kind not in SCHEMA_BUILDERS:
        raise KeyError(f"unknown kind '{kind}'; expected one of {', '.join(KINDS)}")
    return SCHEMA_BUILDERS[kind]()


def write_schema_files(directory: Path = SCHEMA_DIR) -> List[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for kind in KINDS:
        path = directory / f"{kind}.schema.json"
        path.write_text(json.dumps(get_schema(kind), indent=2, sort_keys=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def validate_params(kind: str, data: dict) -> List[str]:
    """Return a list of JSON-Schema violation messages (empty when valid).

    ``$ref`` objects must be inlined first (see ``params.resolve_refs``).
    Requires ``jsonschema``; raises ImportError otherwise.
    """
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(get_schema(kind))
    messages = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        pointer = "/" + "/".join(str(p) for p in error.absolute_path)
        messages.append(f"{pointer or '/'}: {error.message}")
    return messages


def check_schema_files_in_sync(directory: Path = SCHEMA_DIR) -> List[str]:
    """Names of schema files whose content differs from the Python definition."""
    stale = []
    for kind in KINDS:
        path = Path(directory) / f"{kind}.schema.json"
        if not path.is_file() or json.loads(path.read_text(encoding="utf-8")) != get_schema(kind):
            stale.append(path.name)
    return stale
