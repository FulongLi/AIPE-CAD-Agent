"""E-core transformer parameters, validation and derived geometry (SI, metres).

Local coordinate system
-----------------------
* Origin at the centre of the core pair; the mating plane of the two E halves
  is ``z = 0`` and the centre-leg axis is the Z axis.
* X spans the core width (``total_width`` = dimension A), Y the core depth
  (``depth`` = F).  The winding windows are open towards +/-Y.
* The lower E half has its yoke at negative z, the upper half is its mirror.

Derived rules implemented here (all closed-form, optimiser friendly):

* window width, outer-leg width and yoke thickness from the E-core letters;
* bobbin tube/flange sizes from core clearances and wall thicknesses;
* winding layer count and radial build from the conductor data (litz/round
  wire outer diameter or foil thickness) and the available winding width;
* barrier, margin and wrap positions, total radial build versus the window;
* terminal pin positions on the flange overhang; mounting clip and base plate
  geometry; analytic volumes/masses for cross-checking the FreeCAD solids;
* Gmsh mesh hints (regions, material tags, element sizes).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from .. import geometry2d as g2
from ..materials import COPPER_RESISTIVITY_20C, density, is_conductive, winding_effective_density
from .base import (Errors, check_known_keys, get_bool, get_int, get_number, get_str, sub)

DEFAULT_FILL_FACTOR = {"litz": 0.40, "round": 0.75, "foil": None}


@dataclass
class ECoreParams:
    total_width: float            # A
    half_height: float            # B (height of one E half)
    depth: float                  # F
    window_height: float          # D (window height of one half)
    inner_width: float            # C (distance between the outer legs' inner faces)
    centre_leg_width: float       # E
    air_gap: float = 0.0          # total centre-leg gap (split equally between halves)
    material: str = "ferrite_n87"
    density: Optional[float] = None
    net: str = "pe"
    reference: str = ""

    @classmethod
    def from_dict(cls, d: dict, errors: Errors) -> "ECoreParams":
        ctx = Errors("core")
        check_known_keys(d, {"shape", "total_width", "half_height", "depth", "window_height", "inner_width",
                             "centre_leg_width", "air_gap", "material", "density", "net", "reference"}, ctx)
        shape = get_str(d, "shape", "E", ctx, choices=["E"])
        core = cls(
            total_width=get_number(d, "total_width", 0.0652, ctx, positive=True, required=True),
            half_height=get_number(d, "half_height", 0.0326, ctx, positive=True, required=True),
            depth=get_number(d, "depth", 0.0274, ctx, positive=True, required=True),
            window_height=get_number(d, "window_height", 0.0222, ctx, positive=True, required=True),
            inner_width=get_number(d, "inner_width", 0.0442, ctx, positive=True, required=True),
            centre_leg_width=get_number(d, "centre_leg_width", 0.020, ctx, positive=True, required=True),
            air_gap=get_number(d, "air_gap", 0.0, ctx, non_negative=True),
            material=get_str(d, "material", "ferrite_n87", ctx),
            density=get_number(d, "density", None, ctx, positive=True),
            net=get_str(d, "net", "pe", ctx),
            reference=get_str(d, "reference", "", ctx),
        )
        del shape
        if not ctx.messages:
            ctx.check(core.inner_width < core.total_width, "inner_width (C) must be smaller than total_width (A)")
            ctx.check(core.centre_leg_width < core.inner_width, "centre_leg_width (E) must be smaller than inner_width (C)")
            ctx.check(core.window_height < core.half_height, "window_height (D) must be smaller than half_height (B)")
            ctx.check(core.air_gap < core.window_height, "air_gap must be smaller than the window height")
        errors.extend(ctx)
        return core

    # Derived E-core quantities
    @property
    def window_width(self) -> float:
        return 0.5 * (self.inner_width - self.centre_leg_width)

    @property
    def outer_leg_width(self) -> float:
        return 0.5 * (self.total_width - self.inner_width)

    @property
    def yoke_thickness(self) -> float:
        return self.half_height - self.window_height

    @property
    def window_total_height(self) -> float:
        return 2.0 * self.window_height

    def half_volume(self) -> float:
        a, b, f, d = self.total_width, self.half_height, self.depth, self.window_height
        return a * f * b - 2.0 * self.window_width * f * d - self.centre_leg_width * f * (self.air_gap / 2.0)


@dataclass
class BobbinParams:
    wall_thickness: float = 1.5e-3
    flange_thickness: float = 1.5e-3
    core_clearance: float = 0.3e-3      # between centre leg and tube inner surface
    window_clearance: float = 0.5e-3    # between flanges/stack and the core (axial and radial)
    pin_strip_width: float = 6.0e-3     # flange overhang (beyond the maximum build) carrying the terminals
    corner_radius: float = 1.0e-3       # outer corner radius of the tube
    material: str = "bobbin_pet_gf"
    density: Optional[float] = None
    tube_wrap: float = 0.0              # insulation on the tube before the first winding

    @classmethod
    def from_dict(cls, d: dict, errors: Errors) -> "BobbinParams":
        ctx = Errors("bobbin")
        check_known_keys(d, {"wall_thickness", "flange_thickness", "core_clearance", "window_clearance",
                             "pin_strip_width", "corner_radius", "material", "density", "tube_wrap"}, ctx)
        b = cls(
            wall_thickness=get_number(d, "wall_thickness", cls.wall_thickness, ctx, positive=True),
            flange_thickness=get_number(d, "flange_thickness", cls.flange_thickness, ctx, positive=True),
            core_clearance=get_number(d, "core_clearance", cls.core_clearance, ctx, non_negative=True),
            window_clearance=get_number(d, "window_clearance", cls.window_clearance, ctx, non_negative=True),
            pin_strip_width=get_number(d, "pin_strip_width", cls.pin_strip_width, ctx, positive=True),
            corner_radius=get_number(d, "corner_radius", cls.corner_radius, ctx, non_negative=True),
            material=get_str(d, "material", cls.material, ctx),
            density=get_number(d, "density", None, ctx, positive=True),
            tube_wrap=get_number(d, "tube_wrap", 0.0, ctx, non_negative=True),
        )
        errors.extend(ctx)
        return b


@dataclass
class ConductorParams:
    type: str                                # litz | round | foil
    outer_diameter: Optional[float] = None   # litz/round: overall diameter incl. serving/enamel
    strand_count: int = 1
    strand_diameter: Optional[float] = None  # litz: bare strand diameter; round: bare conductor diameter
    foil_thickness: Optional[float] = None
    foil_width: Optional[float] = None       # None -> use the available winding width
    insulation_thickness: float = 0.0        # inter-layer (litz/round) or inter-turn (foil) insulation
    fill_factor: Optional[float] = None      # copper fraction of the winding body (mass only)

    @classmethod
    def from_dict(cls, d: dict, errors: Errors, ctx_name: str) -> "ConductorParams":
        ctx = Errors(ctx_name)
        check_known_keys(d, {"type", "outer_diameter", "strand_count", "strand_diameter", "foil_thickness",
                             "foil_width", "insulation_thickness", "fill_factor"}, ctx)
        ctype = get_str(d, "type", None, ctx, choices=["litz", "round", "foil"], required=True) or "litz"
        c = cls(
            type=ctype,
            outer_diameter=get_number(d, "outer_diameter", None, ctx, positive=True),
            strand_count=get_int(d, "strand_count", 1, ctx, minimum=1),
            strand_diameter=get_number(d, "strand_diameter", None, ctx, positive=True),
            foil_thickness=get_number(d, "foil_thickness", None, ctx, positive=True),
            foil_width=get_number(d, "foil_width", None, ctx, positive=True),
            insulation_thickness=get_number(d, "insulation_thickness", 0.0, ctx, non_negative=True),
            fill_factor=get_number(d, "fill_factor", None, ctx, positive=True),
        )
        if ctype in ("litz", "round"):
            ctx.check(c.outer_diameter is not None, "outer_diameter is required for litz/round conductors")
            ctx.check(c.strand_diameter is not None, "strand_diameter is required for litz/round conductors")
            if c.outer_diameter and c.strand_diameter:
                copper_area = c.strand_count * math.pi * (c.strand_diameter / 2) ** 2
                envelope_area = math.pi * (c.outer_diameter / 2) ** 2
                ctx.check(copper_area < envelope_area,
                          f"copper area {copper_area:.3e} m^2 does not fit inside the outer diameter envelope {envelope_area:.3e} m^2")
        else:
            ctx.check(c.foil_thickness is not None, "foil_thickness is required for foil conductors")
        if c.fill_factor is not None:
            ctx.check(c.fill_factor <= 1.0, "fill_factor must be <= 1")
        errors.extend(ctx)
        return c

    def copper_area(self, foil_width: float) -> float:
        if self.type == "foil":
            return self.foil_thickness * foil_width
        return self.strand_count * math.pi * (self.strand_diameter / 2.0) ** 2


@dataclass
class WindingParams:
    name: str
    turns: int
    conductor: ConductorParams
    margin: float = 0.0
    parallel: int = 1
    net: Optional[str] = None
    terminal_count: int = 2
    terminal_side: Optional[str] = None      # '-y' | '+y'
    material: str = "copper"

    @classmethod
    def from_dict(cls, d: dict, index: int, errors: Errors) -> "WindingParams":
        ctx = Errors(f"windings[{index}]")
        check_known_keys(d, {"name", "turns", "conductor", "margin", "parallel", "net", "terminal_count",
                             "terminal_side", "material"}, ctx)
        name = get_str(d, "name", f"winding{index + 1}", ctx)
        w = cls(
            name=name,
            turns=get_int(d, "turns", None, ctx, minimum=1, required=True) or 1,
            conductor=ConductorParams.from_dict(sub(d, "conductor", ctx), ctx, f"windings[{index}].conductor"),
            margin=get_number(d, "margin", 0.0, ctx, non_negative=True),
            parallel=get_int(d, "parallel", 1, ctx, minimum=1),
            net=get_str(d, "net", None, ctx),
            terminal_count=get_int(d, "terminal_count", 2, ctx, minimum=0),
            terminal_side=get_str(d, "terminal_side", None, ctx, choices=["-y", "+y"]),
            material=get_str(d, "material", "copper", ctx),
        )
        if w.net is None:
            w.net = name
        errors.extend(ctx)
        return w


@dataclass
class InsulationParams:
    inter_winding_barrier: float = 0.5e-3
    outer_wrap: float = 0.3e-3
    fill_margins: bool = True
    material: str = "kapton"
    density: Optional[float] = None

    @classmethod
    def from_dict(cls, d: dict, errors: Errors) -> "InsulationParams":
        ctx = Errors("insulation")
        check_known_keys(d, {"inter_winding_barrier", "outer_wrap", "fill_margins", "material", "density"}, ctx)
        i = cls(
            inter_winding_barrier=get_number(d, "inter_winding_barrier", cls.inter_winding_barrier, ctx, non_negative=True),
            outer_wrap=get_number(d, "outer_wrap", cls.outer_wrap, ctx, non_negative=True),
            fill_margins=get_bool(d, "fill_margins", True, ctx),
            material=get_str(d, "material", cls.material, ctx),
            density=get_number(d, "density", None, ctx, positive=True),
        )
        errors.extend(ctx)
        return i


@dataclass
class TerminalParams:
    style: str = "pin"
    diameter: float = 1.5e-3
    length: float = 12.0e-3
    pitch: float = 5.0e-3
    flange: str = "top"          # top | bottom
    direction: str = "+z"        # +z | -z (must point away from the bobbin)
    material: str = "brass"

    @classmethod
    def from_dict(cls, d: dict, errors: Errors) -> "TerminalParams":
        ctx = Errors("terminals")
        check_known_keys(d, {"style", "diameter", "length", "pitch", "flange", "direction", "material"}, ctx)
        t = cls(
            style=get_str(d, "style", "pin", ctx, choices=["pin"]),
            diameter=get_number(d, "diameter", cls.diameter, ctx, positive=True),
            length=get_number(d, "length", cls.length, ctx, positive=True),
            pitch=get_number(d, "pitch", cls.pitch, ctx, positive=True),
            flange=get_str(d, "flange", "top", ctx, choices=["top", "bottom"]),
            direction=get_str(d, "direction", "+z", ctx, choices=["+z", "-z"]),
            material=get_str(d, "material", "brass", ctx),
        )
        if (t.flange == "top") != (t.direction == "+z"):
            ctx.add("terminal direction must point away from the bobbin (top/+z or bottom/-z)")
        ctx.check(t.pitch > t.diameter, "terminal pitch must exceed the pin diameter")
        errors.extend(ctx)
        return t


@dataclass
class MountingParams:
    clips: bool = True
    clip_thickness: float = 0.8e-3
    clip_width: float = 10.0e-3
    clip_inset: float = 2.0e-3
    clip_material: str = "stainless_steel"
    base_plate: bool = True
    plate_thickness: float = 2.0e-3
    plate_margin_x: float = 12.0e-3
    hole_diameter: float = 4.5e-3
    hole_inset: float = 6.0e-3
    plate_material: str = "aluminium_6063"
    net: str = "pe"

    @classmethod
    def from_dict(cls, d: dict, errors: Errors) -> "MountingParams":
        ctx = Errors("mounting")
        check_known_keys(d, {"clips", "clip_thickness", "clip_width", "clip_inset", "clip_material", "base_plate",
                             "plate_thickness", "plate_margin_x", "hole_diameter", "hole_inset", "plate_material", "net"}, ctx)
        m = cls(
            clips=get_bool(d, "clips", True, ctx),
            clip_thickness=get_number(d, "clip_thickness", cls.clip_thickness, ctx, positive=True),
            clip_width=get_number(d, "clip_width", cls.clip_width, ctx, positive=True),
            clip_inset=get_number(d, "clip_inset", cls.clip_inset, ctx, non_negative=True),
            clip_material=get_str(d, "clip_material", cls.clip_material, ctx),
            base_plate=get_bool(d, "base_plate", True, ctx),
            plate_thickness=get_number(d, "plate_thickness", cls.plate_thickness, ctx, positive=True),
            plate_margin_x=get_number(d, "plate_margin_x", cls.plate_margin_x, ctx, non_negative=True),
            hole_diameter=get_number(d, "hole_diameter", cls.hole_diameter, ctx, positive=True),
            hole_inset=get_number(d, "hole_inset", cls.hole_inset, ctx, positive=True),
            plate_material=get_str(d, "plate_material", cls.plate_material, ctx),
            net=get_str(d, "net", "pe", ctx),
        )
        errors.extend(ctx)
        return m


@dataclass
class TransformerParams:
    name: str
    core: ECoreParams
    bobbin: BobbinParams
    windings: List[WindingParams]
    insulation: InsulationParams
    terminals: TerminalParams
    mounting: MountingParams
    clearance_envelope_margin: float = 5.0e-3
    checks: dict = field(default_factory=dict)
    description: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> "TransformerParams":
        errors = Errors()
        if not isinstance(d, dict):
            raise_params(["transformer parameters must be a JSON object"])
        check_known_keys(d, {"kind", "name", "description", "core", "bobbin", "windings", "insulation", "terminals",
                             "mounting", "clearance_envelope_margin", "checks"}, errors)
        kind = get_str(d, "kind", "transformer", errors, choices=["transformer"])
        del kind
        windings_raw = d.get("windings")
        if not isinstance(windings_raw, list) or not windings_raw:
            errors.add("windings must be a non-empty list")
            windings_raw = []
        windings = [WindingParams.from_dict(w if isinstance(w, dict) else {}, i, errors) for i, w in enumerate(windings_raw)]
        names = [w.name for w in windings]
        if len(set(names)) != len(names):
            errors.add("winding names must be unique")
        params = cls(
            name=get_str(d, "name", "transformer", errors),
            core=ECoreParams.from_dict(sub(d, "core", errors), errors),
            bobbin=BobbinParams.from_dict(sub(d, "bobbin", errors), errors),
            windings=windings,
            insulation=InsulationParams.from_dict(sub(d, "insulation", errors), errors),
            terminals=TerminalParams.from_dict(sub(d, "terminals", errors), errors),
            mounting=MountingParams.from_dict(sub(d, "mounting", errors), errors),
            clearance_envelope_margin=get_number(d, "clearance_envelope_margin", 5.0e-3, errors, non_negative=True),
            checks=sub(d, "checks", errors),
            description=get_str(d, "description", "", errors),
        )
        errors.raise_if_any()
        return params


def raise_params(messages):
    from .base import ParameterError
    raise ParameterError(messages)


def resolve_transformer(d: dict) -> dict:
    """Validate the transformer parameters and derive every geometric quantity.

    Returns a JSON-serialisable dictionary (SI units) consumed by the FreeCAD
    worker, the tests and any optimiser.  Raises :class:`ParameterError` when
    the windings do not fit the window or any other rule is violated.
    """
    p = TransformerParams.from_dict(d)
    errors = Errors()
    warnings: List[str] = []
    core, bob, ins, term, mnt = p.core, p.bobbin, p.insulation, p.terminals, p.mounting

    # --- bobbin -----------------------------------------------------------------
    tube_inner = [core.centre_leg_width + 2 * bob.core_clearance, core.depth + 2 * bob.core_clearance]
    tube_outer = [tube_inner[0] + 2 * bob.wall_thickness, tube_inner[1] + 2 * bob.wall_thickness]
    tube_height = core.window_total_height - 2 * bob.window_clearance
    winding_width = tube_height - 2 * bob.flange_thickness
    r_tube = bob.corner_radius
    r_inner = max(r_tube - bob.wall_thickness, 0.0)
    errors.check(2 * r_tube <= min(tube_outer) , "bobbin corner_radius too large for the tube cross-section")
    flange_x = core.inner_width - 2 * bob.window_clearance
    max_build = 0.5 * flange_x - 0.5 * tube_outer[0]
    errors.check(max_build > 0, f"no radial room for windings: tube outer half-width {0.5 * tube_outer[0]:.4g} m "
                                f"exceeds window half extent {0.5 * flange_x:.4g} m")
    errors.check(winding_width > 0, "winding width is not positive: flanges/clearances consume the window height")
    flange_y = tube_outer[1] + 2 * (max(max_build, 0.0) + bob.pin_strip_width)
    errors.raise_if_any()

    # --- winding stack -------------------------------------------------------------
    stack = []
    barriers = []
    margin_fills = []
    r = bob.tube_wrap
    if bob.tube_wrap > 0:
        barriers.append(_barrier("tube_wrap", 0.0, bob.tube_wrap, winding_width, tube_outer, r_tube, ins))
    for i, w in enumerate(p.windings):
        wctx = Errors(f"windings[{i}] '{w.name}'")
        width_avail = winding_width - 2 * w.margin
        if not wctx.check(width_avail > 0, f"margins {w.margin:.4g} m leave no winding width (available {winding_width:.4g} m)"):
            errors.extend(wctx)
            continue
        c = w.conductor
        if c.type in ("litz", "round"):
            od = c.outer_diameter
            turns_per_layer = int(math.floor(width_avail / od + 1e-9))
            if not wctx.check(turns_per_layer >= 1, f"conductor outer diameter {od:.4g} m exceeds the available width {width_avail:.4g} m"):
                errors.extend(wctx)
                continue
            wires = w.turns * w.parallel
            layers = int(math.ceil(wires / turns_per_layer))
            thickness = layers * od + max(layers - 1, 0) * c.insulation_thickness
            used_width = min(wires, turns_per_layer) * od
            foil_width = None
            copper_fraction = c.fill_factor if c.fill_factor is not None else DEFAULT_FILL_FACTOR[c.type]
        else:
            foil_width = c.foil_width if c.foil_width is not None else width_avail
            if not wctx.check(foil_width <= width_avail + 1e-12, f"foil width {foil_width:.4g} m exceeds the available width {width_avail:.4g} m"):
                errors.extend(wctx)
                continue
            turns_per_layer = 1
            layers = w.turns
            thickness = w.turns * (c.foil_thickness + c.insulation_thickness)
            used_width = foil_width
            copper_fraction = c.fill_factor if c.fill_factor is not None else c.foil_thickness / (c.foil_thickness + c.insulation_thickness)
        r_start = r
        r_end = r_start + thickness
        inner_dims = [tube_outer[0] + 2 * r_start, tube_outer[1] + 2 * r_start]
        mid = r_start + 0.5 * thickness
        mlt = g2.rounded_rect_perimeter(tube_outer[0] + 2 * mid, tube_outer[1] + 2 * mid, r_tube + mid)
        area_cu = c.copper_area(foil_width if foil_width else 0.0)
        length = w.turns * mlt
        copper_mass = density(w.material) * length * area_cu * w.parallel
        resistance = COPPER_RESISTIVITY_20C * length / (area_cu * w.parallel) if w.material == "copper" else None
        eff_density = winding_effective_density(copper_fraction, conductor=w.material)
        body_width = used_width if c.type == "foil" else width_avail
        volume = g2.rounded_annulus_area(inner_dims[0], inner_dims[1], r_tube + r_start, thickness) * body_width
        side = w.terminal_side or ("-y" if i == 0 else "+y")
        stack.append({
            "name": w.name, "net": w.net, "material": w.material, "conductor_type": c.type,
            "turns": w.turns, "parallel": w.parallel, "turns_per_layer": turns_per_layer, "layers": layers,
            "radial_start": r_start, "thickness": thickness, "radial_end": r_end,
            "inner_dims": inner_dims, "outer_dims": [inner_dims[0] + 2 * thickness, inner_dims[1] + 2 * thickness],
            "corner_radius_inner": r_tube + r_start, "corner_radius_outer": r_tube + r_end,
            "width": body_width, "z0": -0.5 * body_width, "z1": 0.5 * body_width, "margin": w.margin,
            "foil_width": foil_width, "mean_length_of_turn": mlt, "conductor_length": length,
            "copper_area_per_conductor": area_cu, "copper_mass": copper_mass,
            "dc_resistance_20c_ohm": resistance, "copper_fraction": copper_fraction,
            "effective_density": eff_density, "volume": volume, "mass": volume * eff_density,
            "terminal_side": side, "terminal_count": w.terminal_count,
        })
        if ins.fill_margins and w.margin > 0:
            for tag, z0, z1 in (("lower", -0.5 * winding_width, -0.5 * body_width), ("upper", 0.5 * body_width, 0.5 * winding_width)):
                vol = g2.rounded_annulus_area(inner_dims[0], inner_dims[1], r_tube + r_start, thickness) * (z1 - z0)
                margin_fills.append({"name": f"margin_{w.name}_{tag}", "winding": w.name, "radial_start": r_start,
                                     "thickness": thickness, "z0": z0, "z1": z1, "inner_dims": inner_dims,
                                     "corner_radius_inner": r_tube + r_start, "material": ins.material,
                                     "volume": vol, "mass": vol * density(ins.material, ins.density)})
        r = r_end
        if i < len(p.windings) - 1 and ins.inter_winding_barrier > 0:
            barriers.append(_barrier(f"barrier_{w.name}_{p.windings[i + 1].name}", r, ins.inter_winding_barrier,
                                     winding_width, tube_outer, r_tube, ins))
            r += ins.inter_winding_barrier
    if ins.outer_wrap > 0:
        barriers.append(_barrier("outer_wrap", r, ins.outer_wrap, winding_width, tube_outer, r_tube, ins))
        r += ins.outer_wrap
    total_build = r
    spare_build = max_build - total_build
    errors.check(spare_build >= 0, f"total radial build {total_build:.4g} m exceeds the available build {max_build:.4g} m "
                                   f"(short by {-spare_build:.4g} m)")
    errors.raise_if_any()
    if spare_build < 0.2e-3:
        warnings.append(f"radial spare build is only {spare_build * 1e3:.2f} mm")

    # --- terminals ---------------------------------------------------------------------
    pin_y = 0.5 * tube_outer[1] + max_build + 0.5 * bob.pin_strip_width
    if term.flange == "top":
        z0, z1 = 0.5 * tube_height, 0.5 * tube_height + term.length
    else:
        z0, z1 = -0.5 * tube_height - term.length, -0.5 * tube_height
    terminals = []
    for wnd in stack:
        n = wnd["terminal_count"]
        sign = -1.0 if wnd["terminal_side"] == "-y" else 1.0
        for k in range(n):
            x = (k - 0.5 * (n - 1)) * term.pitch
            terminals.append({"name": f"pin_{wnd['name']}_{k + 1}", "winding": wnd["name"], "net": wnd["net"],
                              "x": x, "y": sign * pin_y, "z0": z0, "z1": z1, "diameter": term.diameter,
                              "material": term.material,
                              "volume": math.pi * (term.diameter / 2) ** 2 * term.length,
                              "mass": math.pi * (term.diameter / 2) ** 2 * term.length * density(term.material)})
    errors.check(pin_y - 0.5 * term.diameter > 0.5 * core.depth,
                 "terminal pins would collide with the core yoke; increase pin_strip_width")
    pins_span = (max(w["terminal_count"] for w in stack) - 1) * term.pitch + term.diameter if stack else 0.0
    errors.check(pins_span <= flange_x, "terminal row wider than the flange")

    # --- mounting -----------------------------------------------------------------------
    mounting = {"clips": [], "base_plate": None}
    clip_t = mnt.clip_thickness if mnt.clips else 0.0
    if mnt.clips:
        errors.check(2 * (mnt.clip_inset + mnt.clip_width) <= core.depth, "clips do not fit on the core depth")
        for sign in (-1.0, 1.0):
            y_c = sign * (0.5 * core.depth - mnt.clip_inset - 0.5 * mnt.clip_width)
            ring_area = (core.total_width + 2 * clip_t) * (2 * core.half_height + 2 * clip_t) - core.total_width * 2 * core.half_height
            mounting["clips"].append({"name": "clip_neg_y" if sign < 0 else "clip_pos_y", "y_centre": y_c,
                                      "width": mnt.clip_width, "thickness": clip_t,
                                      "inner_x": core.total_width, "inner_z": 2 * core.half_height,
                                      "material": mnt.clip_material, "net": mnt.net,
                                      "volume": ring_area * mnt.clip_width,
                                      "mass": ring_area * mnt.clip_width * density(mnt.clip_material)})
    if mnt.base_plate:
        z_top = -core.half_height - clip_t
        lx = core.total_width + 2 * mnt.plate_margin_x
        ly = core.depth
        hx = 0.5 * lx - mnt.hole_inset
        hy = 0.5 * ly - mnt.hole_inset
        errors.check(mnt.hole_inset > 0.5 * mnt.hole_diameter, "mounting hole_inset must exceed the hole radius")
        errors.check(hx - 0.5 * mnt.hole_diameter > 0.5 * core.total_width,
                     "base plate mounting holes lie under the core; increase plate_margin_x or hole_inset")
        errors.check(hy > 0.5 * mnt.hole_diameter, "base plate too narrow for the mounting holes")
        holes = [[sx * hx, sy * hy] for sx in (-1.0, 1.0) for sy in (-1.0, 1.0)]
        vol = lx * ly * mnt.plate_thickness - 4 * math.pi * (mnt.hole_diameter / 2) ** 2 * mnt.plate_thickness
        mounting["base_plate"] = {"name": "base_plate", "size": [lx, ly, mnt.plate_thickness], "z_top": z_top,
                                  "z_bottom": z_top - mnt.plate_thickness, "holes": holes,
                                  "hole_diameter": mnt.hole_diameter, "material": mnt.plate_material, "net": mnt.net,
                                  "volume": vol, "mass": vol * density(mnt.plate_material)}
        if term.direction == "-z":
            errors.check(pin_y - 0.5 * term.diameter > 0.5 * ly, "downward terminal pins collide with the base plate")
    errors.raise_if_any()

    # --- bobbin solid volume ---------------------------------------------------------------
    tube_area = g2.rounded_rect_area(tube_outer[0], tube_outer[1], r_tube) - g2.rounded_rect_area(tube_inner[0], tube_inner[1], r_inner)
    flange_ring_area = flange_x * flange_y - g2.rounded_rect_area(tube_outer[0], tube_outer[1], r_tube)
    bobbin_volume = tube_area * tube_height + 2 * flange_ring_area * bob.flange_thickness
    bobbin = {
        "tube_inner": tube_inner, "tube_outer": tube_outer, "tube_height": tube_height,
        "corner_radius_outer": r_tube, "corner_radius_inner": r_inner,
        "flange_size": [flange_x, flange_y, bob.flange_thickness],
        "flange_z": [[-0.5 * tube_height, -0.5 * tube_height + bob.flange_thickness],
                     [0.5 * tube_height - bob.flange_thickness, 0.5 * tube_height]],
        "winding_width": winding_width, "max_build": max_build, "total_build": total_build, "spare_build": spare_build,
        "material": bob.material, "volume": bobbin_volume, "mass": bobbin_volume * density(bob.material, bob.density),
        "pin_y": pin_y,
    }

    # --- core solids ------------------------------------------------------------------------
    half_volume = core.half_volume()
    core_res = {
        "window_width": core.window_width, "outer_leg_width": core.outer_leg_width,
        "yoke_thickness": core.yoke_thickness, "window_total_height": core.window_total_height,
        "half_volume": half_volume, "pair_volume": 2 * half_volume,
        "mass": 2 * half_volume * density(core.material, core.density), "material": core.material, "net": core.net,
        "gap_half": 0.5 * core.air_gap, "reference": core.reference,
        "centre_leg_area": core.centre_leg_width * core.depth,
    }

    # --- envelope and fit expectations ------------------------------------------------------
    z_min = mounting["base_plate"]["z_bottom"] if mounting["base_plate"] else -core.half_height - clip_t
    z_max = max(core.half_height + clip_t, max((t["z1"] for t in terminals), default=0.0))
    x_half = max(0.5 * core.total_width + clip_t, 0.5 * flange_x,
                 0.5 * mounting["base_plate"]["size"][0] if mounting["base_plate"] else 0.0)
    y_half = max(0.5 * core.depth, 0.5 * flange_y)
    envelope = {"margin": p.clearance_envelope_margin,
                "bbox": [-x_half, -y_half, z_min, x_half, y_half, z_max]}
    fit_pairs = [
        {"a": "bobbin", "b": "core_lower", "expected_gap": min(bob.core_clearance, bob.window_clearance), "tolerance": 1e-6,
         "note": "bobbin tube to centre leg / flange to outer leg clearance"},
        {"a": "bobbin", "b": "core_upper", "expected_gap": min(bob.core_clearance, bob.window_clearance), "tolerance": 1e-6},
    ]
    outermost = barriers[-1]["name"] if barriers and barriers[-1]["name"] == "outer_wrap" else (stack[-1]["name"] if stack else None)
    if outermost:
        # radial: spare build plus the flange-to-leg clearance; axial: flange thickness plus window clearance
        fit_pairs.append({"a": outermost, "b": "core_lower", "expected_gap": min(spare_build + bob.window_clearance,
                                                                                 bob.window_clearance + bob.flange_thickness),
                          "tolerance": 1e-6, "note": "outermost winding/wrap to the outer legs"})

    masses = {"core": core_res["mass"], "bobbin": bobbin["mass"],
              "windings": sum(w["mass"] for w in stack), "copper": sum(w["copper_mass"] for w in stack),
              "insulation": sum(b["mass"] for b in barriers) + sum(m["mass"] for m in margin_fills),
              "terminals": sum(t["mass"] for t in terminals),
              "mounting": sum(c["mass"] for c in mounting["clips"]) + (mounting["base_plate"]["mass"] if mounting["base_plate"] else 0.0)}
    masses["total"] = sum(v for k, v in masses.items() if k != "copper")

    mesh_hints = _mesh_hints(core, bob, stack, barriers, envelope)
    return {
        "kind": "transformer", "name": p.name, "description": p.description, "units": "SI (m, kg)",
        "core": core_res, "core_params": _core_dict(core), "bobbin": bobbin, "windings": stack, "barriers": barriers,
        "margin_fills": margin_fills, "terminals": terminals, "mounting": mounting, "envelope": envelope,
        "fit_pairs": fit_pairs, "analytic_masses": masses, "warnings": warnings, "checks": p.checks,
        "mesh_hints": mesh_hints,
    }


def _barrier(name, r_start, thickness, width, tube_outer, r_tube, ins: InsulationParams) -> dict:
    inner = [tube_outer[0] + 2 * r_start, tube_outer[1] + 2 * r_start]
    vol = g2.rounded_annulus_area(inner[0], inner[1], r_tube + r_start, thickness) * width
    return {"name": name, "radial_start": r_start, "thickness": thickness, "radial_end": r_start + thickness,
            "inner_dims": inner, "corner_radius_inner": r_tube + r_start, "width": width,
            "z0": -0.5 * width, "z1": 0.5 * width, "material": ins.material,
            "volume": vol, "mass": vol * density(ins.material, ins.density)}


def _core_dict(core: ECoreParams) -> dict:
    return {"total_width": core.total_width, "half_height": core.half_height, "depth": core.depth,
            "window_height": core.window_height, "inner_width": core.inner_width,
            "centre_leg_width": core.centre_leg_width, "air_gap": core.air_gap}


def _mesh_hints(core, bob, stack, barriers, envelope) -> dict:
    core_size = min(core.window_width, core.yoke_thickness, core.centre_leg_width) / 4.0
    regions = [
        {"bodies": ["core_lower", "core_upper"], "group": "core", "material": core.material, "element_size": core_size,
         "note": "magnetic core; refine towards the air gap if present"},
        {"bodies": ["bobbin"], "group": "structure", "material": bob.material, "element_size": max(bob.wall_thickness / 2, 0.25e-3)},
    ]
    for w in stack:
        regions.append({"bodies": [w["name"]], "group": f"winding_{w['name']}", "material": w["material"],
                        "element_size": max(min(w["thickness"] / 2.0, w["width"] / 10.0), 0.25e-3),
                        "note": "homogenised winding body; assign effective (anisotropic) material properties"})
    for b in barriers:
        regions.append({"bodies": [b["name"]], "group": "insulation", "material": b["material"],
                        "element_size": max(b["thickness"], 0.1e-3),
                        "note": "thin layer: one element across the thickness or a shell/thin-layer treatment"})
    bb = envelope["bbox"]
    size = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2])
    air = [bb[0] - size, bb[1] - size, bb[2] - size, bb[3] + size, bb[4] + size, bb[5] + size]
    refinement = []
    if core.air_gap > 0:
        refinement.append({"name": "air_gap", "bbox": [-core.centre_leg_width, -core.depth, -core.air_gap * 2,
                                                       core.centre_leg_width, core.depth, core.air_gap * 2],
                           "element_size": core.air_gap / 3.0})
    return {
        "target": "gmsh", "units": "m",
        "import_note": "Import the STEP with gmsh.model.occ.importShapes and map solids to regions by their STEP product names (body names below).",
        "regions": regions,
        "air_region": {"bbox": air, "element_size": size / 10.0, "note": "suggested far-field box for magnetostatic/thermal analysis"},
        "refinement_zones": refinement,
        "contact_pairs_note": "bodies listed in metadata 'contacts' touch (distance 0); mesh them conformally or define thermal contact",
    }
