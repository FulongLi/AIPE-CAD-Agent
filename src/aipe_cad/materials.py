"""Material table used for mass estimates and conductor/insulator classification.

Densities are typical handbook values in kg/m^3.  They are deliberately kept
in one place so that an optimiser or a user can override them per body through
the ``density`` parameter where offered.  No supplier data is implied unless a
``source`` is given.
"""
from __future__ import annotations

from typing import Dict, Optional

RHO_COPPER = 8960.0
RHO_INSULATION_POLYMER = 1400.0
COPPER_RESISTIVITY_20C = 1.72e-8  # ohm*m, annealed copper, 20 degC

MATERIALS: Dict[str, dict] = {
    "ferrite_n87": {"density": 4850.0, "conductive": False, "category": "ferrite",
                    "description": "MnZn power ferrite, typical density 4.85 g/cm^3 (verify with TDK N87 material data)"},
    "ferrite_generic": {"density": 4800.0, "conductive": False, "category": "ferrite",
                        "description": "Generic MnZn ferrite"},
    "copper": {"density": RHO_COPPER, "conductive": True, "category": "metal",
               "description": "Annealed copper"},
    "aluminium_6063": {"density": 2700.0, "conductive": True, "category": "metal",
                       "description": "Extruded aluminium alloy (heat sinks, cold plates)"},
    "aluminium_generic": {"density": 2700.0, "conductive": True, "category": "metal",
                          "description": "Generic aluminium"},
    "steel": {"density": 7850.0, "conductive": True, "category": "metal", "description": "Carbon steel"},
    "stainless_steel": {"density": 8000.0, "conductive": True, "category": "metal",
                        "description": "Austenitic stainless steel (core clips)"},
    "brass": {"density": 8500.0, "conductive": True, "category": "metal", "description": "Brass (fittings, pins)"},
    "fr4": {"density": 1850.0, "conductive": False, "category": "laminate",
            "description": "Glass-epoxy PCB laminate (dielectric only; copper modelled separately)"},
    "bobbin_pet_gf": {"density": 1600.0, "conductive": False, "category": "polymer",
                      "description": "Glass-fibre reinforced polyterephthalate coil former (UL 94 V-0 class material)"},
    "kapton": {"density": 1420.0, "conductive": False, "category": "polymer",
               "description": "Polyimide film (barriers, wraps)"},
    "insulation_polymer": {"density": RHO_INSULATION_POLYMER, "conductive": False, "category": "polymer",
                           "description": "Generic winding insulation (enamel, serving, tape)"},
    "alumina": {"density": 3900.0, "conductive": False, "category": "ceramic",
                "description": "Al2O3 isolation pad"},
    "thermal_pad": {"density": 2000.0, "conductive": False, "category": "polymer",
                    "description": "Filled silicone isolation pad (typical)"},
    "epoxy_mold_compound": {"density": 1900.0, "conductive": False, "category": "polymer",
                            "description": "Semiconductor package mould compound"},
    "nylon_pa66": {"density": 1140.0, "conductive": False, "category": "polymer",
                   "description": "Polyamide (standoffs, connector housings)"},
    "ptfe": {"density": 2200.0, "conductive": False, "category": "polymer", "description": "PTFE"},
    "water_glycol_50": {"density": 1070.0, "conductive": False, "category": "fluid",
                        "description": "50/50 water-glycol coolant"},
    "air": {"density": 1.2, "conductive": False, "category": "fluid",
            "description": "Air (clearance volumes, keep-outs); excluded from mass totals"},
}


class UnknownMaterialError(KeyError):
    pass


def material(name: str) -> dict:
    try:
        return MATERIALS[name]
    except KeyError:
        raise UnknownMaterialError(f"unknown material '{name}'; known: {', '.join(sorted(MATERIALS))}") from None


def density(name: str, override: Optional[float] = None) -> float:
    if override is not None:
        if override <= 0:
            raise ValueError("density override must be positive")
        return float(override)
    return float(material(name)["density"])


def is_conductive(name: str) -> bool:
    return bool(material(name)["conductive"])


def winding_effective_density(fill_factor: float, conductor: str = "copper",
                              insulation: str = "insulation_polymer") -> float:
    """Homogenised density of a winding body.

    ``fill_factor`` is the copper fraction of the winding body volume.  The
    remainder is treated as insulation polymer (enamel, serving, tape); air
    pockets are neglected, which slightly over-estimates the mass.
    """
    if not 0.0 < fill_factor <= 1.0:
        raise ValueError("fill_factor must be in (0, 1]")
    return fill_factor * density(conductor) + (1.0 - fill_factor) * density(insulation)
