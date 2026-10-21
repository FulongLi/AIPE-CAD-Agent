"""Pure-Python parameter models, validation and derived-geometry rules.

Everything here is standard-library only so that it can be imported from the
Python interpreter embedded in ``freecadcmd`` as well as from the system
Python that orchestrates the workers.
"""
from .base import ParameterError, load_json, resolve_refs
from .transformer import TransformerParams, resolve_transformer
from .heatsink import HeatSinkParams, resolve_heatsink, fin_count_from_pitch, fin_positions
from .coldplate import ColdPlateParams, resolve_coldplate
from .assembly import AssemblyParams, resolve_assembly

RESOLVERS = {
    "transformer": resolve_transformer,
    "heatsink": resolve_heatsink,
    "coldplate": resolve_coldplate,
    "assembly": resolve_assembly,
}


def resolve(kind: str, params: dict, base_dir=None) -> dict:
    """Validate ``params`` of ``kind`` and return the resolved geometry dictionary."""
    if kind not in RESOLVERS:
        raise ParameterError([f"unknown kind '{kind}'; expected one of {', '.join(RESOLVERS)}"])
    if kind == "assembly":
        return resolve_assembly(params, base_dir=base_dir)
    return RESOLVERS[kind](params)


__all__ = [
    "ParameterError", "load_json", "resolve_refs", "resolve", "RESOLVERS",
    "TransformerParams", "resolve_transformer",
    "HeatSinkParams", "resolve_heatsink", "fin_count_from_pitch", "fin_positions",
    "ColdPlateParams", "resolve_coldplate",
    "AssemblyParams", "resolve_assembly",
]
