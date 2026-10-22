"""Shared validation plumbing for the parameter models."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence


class ParameterError(ValueError):
    """One or more parameter problems; ``messages`` lists all of them."""

    def __init__(self, messages: Sequence[str]):
        self.messages: List[str] = list(messages)
        super().__init__("; ".join(self.messages))


class Errors:
    """Collects validation messages so that a caller sees every problem at once."""

    def __init__(self, context: str = ""):
        self.context = context
        self.messages: List[str] = []

    def add(self, message: str) -> None:
        self.messages.append(f"{self.context}: {message}" if self.context else message)

    def check(self, condition: bool, message: str) -> bool:
        if not condition:
            self.add(message)
        return bool(condition)

    def extend(self, other: "Errors") -> None:
        self.messages.extend(other.messages)

    def raise_if_any(self) -> None:
        if self.messages:
            raise ParameterError(self.messages)


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def get_number(d: dict, key: str, default: Optional[float], errors: Errors, *, positive: bool = False,
               non_negative: bool = False, required: bool = False) -> Optional[float]:
    """Fetch a numeric field with range checks; returns ``default`` when absent."""
    if key not in d or d[key] is None:
        if required:
            errors.add(f"missing required field '{key}'")
        return default
    value = d[key]
    if not is_number(value):
        errors.add(f"field '{key}' must be a finite number, got {value!r}")
        return default
    value = float(value)
    if positive and value <= 0:
        errors.add(f"field '{key}' must be > 0, got {value}")
    if non_negative and value < 0:
        errors.add(f"field '{key}' must be >= 0, got {value}")
    return value


def get_int(d: dict, key: str, default: Optional[int], errors: Errors, *, minimum: Optional[int] = None,
            required: bool = False) -> Optional[int]:
    if key not in d or d[key] is None:
        if required:
            errors.add(f"missing required field '{key}'")
        return default
    value = d[key]
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        else:
            errors.add(f"field '{key}' must be an integer, got {value!r}")
            return default
    if minimum is not None and value < minimum:
        errors.add(f"field '{key}' must be >= {minimum}, got {value}")
    return value


def get_str(d: dict, key: str, default: Optional[str], errors: Errors, *, choices: Optional[Iterable[str]] = None,
            required: bool = False) -> Optional[str]:
    if key not in d or d[key] is None:
        if required:
            errors.add(f"missing required field '{key}'")
        return default
    value = d[key]
    if not isinstance(value, str):
        errors.add(f"field '{key}' must be a string, got {value!r}")
        return default
    if choices is not None and value not in set(choices):
        errors.add(f"field '{key}' must be one of {sorted(choices)}, got {value!r}")
    return value


def get_bool(d: dict, key: str, default: bool, errors: Errors) -> bool:
    if key not in d or d[key] is None:
        return default
    value = d[key]
    if not isinstance(value, bool):
        errors.add(f"field '{key}' must be a boolean, got {value!r}")
        return default
    return value


def get_vector(d: dict, key: str, default: Optional[Sequence[float]], errors: Errors, length: int = 3,
               required: bool = False) -> Optional[list]:
    if key not in d or d[key] is None:
        if required:
            errors.add(f"missing required field '{key}'")
        return list(default) if default is not None else None
    value = d[key]
    if not isinstance(value, (list, tuple)) or len(value) != length or not all(is_number(v) for v in value):
        errors.add(f"field '{key}' must be a list of {length} finite numbers, got {value!r}")
        return list(default) if default is not None else None
    return [float(v) for v in value]


def check_known_keys(d: dict, known: Iterable[str], errors: Errors) -> None:
    unknown = sorted(set(d) - set(known))
    if unknown:
        errors.add(f"unknown field(s): {', '.join(unknown)}")


def sub(d: dict, key: str, errors: Errors) -> dict:
    """Return a nested object or an empty dict (reporting non-objects)."""
    value = d.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        errors.add(f"field '{key}' must be an object")
        return {}
    return value


def load_json(path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_refs(obj: Any, base_dir: Optional[Path]) -> Any:
    """Inline ``{"$ref": "relative/file.json"}`` objects.

    The assembly parameter file references the component parameter files this
    way so that one set of transformer/heat-sink parameters is shared between
    the stand-alone builds and the assembly.  Sibling keys next to ``$ref``
    override the loaded document (shallow merge).
    """
    if isinstance(obj, dict):
        if "$ref" in obj and isinstance(obj["$ref"], str):
            if base_dir is None:
                raise ParameterError([f"cannot resolve $ref '{obj['$ref']}' without a base directory"])
            target = Path(base_dir) / obj["$ref"]
            if not target.is_file():
                raise ParameterError([f"$ref target not found: {target}"])
            loaded = resolve_refs(load_json(target), target.parent)
            overrides = {k: v for k, v in obj.items() if k != "$ref"}
            if overrides:
                loaded = dict(loaded)
                loaded.update(resolve_refs(overrides, base_dir))
            return loaded
        return {k: resolve_refs(v, base_dir) for k, v in obj.items()}
    if isinstance(obj, list):
        return [resolve_refs(v, base_dir) for v in obj]
    return obj


def round_sig(value: float, digits: int = 9) -> float:
    """Round for stable JSON output without hiding engineering precision."""
    if value == 0 or not math.isfinite(value):
        return value
    return float(f"{value:.{digits}g}")
