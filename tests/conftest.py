"""Shared pytest fixtures.

Tests marked ``freecad`` spawn ``freecadcmd`` and are skipped automatically
when no FreeCAD installation is found (or when ``AIPE_CAD_SKIP_FREECAD=1``).
Tests marked ``cadquery`` are skipped when the optional package is missing.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aipe_cad.params import load_json, resolve_refs  # noqa: E402
from aipe_cad.runner import find_freecadcmd, run_job  # noqa: E402

EXAMPLE_PARAMS = ROOT / "examples" / "dab-10kw" / "params"


def _freecad_available() -> bool:
    return os.environ.get("AIPE_CAD_SKIP_FREECAD") != "1" and find_freecadcmd() is not None


def _cadquery_available() -> bool:
    try:
        import cadquery  # noqa: F401
    except Exception:
        return False
    return True


def pytest_collection_modifyitems(config, items):
    skip_fc = pytest.mark.skip(reason="freecadcmd not found (set AIPE_CAD_FREECADCMD) or AIPE_CAD_SKIP_FREECAD=1")
    skip_cq = pytest.mark.skip(reason="optional package cadquery is not installed")
    fc_ok, cq_ok = _freecad_available(), _cadquery_available()
    for item in items:
        if "freecad" in item.keywords and not fc_ok:
            item.add_marker(skip_fc)
        if "cadquery" in item.keywords and not cq_ok:
            item.add_marker(skip_cq)


@pytest.fixture(scope="session")
def example_params():
    def _load(kind: str) -> dict:
        path = EXAMPLE_PARAMS / f"{kind}.json"
        return resolve_refs(load_json(path), path.parent)
    return _load


@pytest.fixture(scope="session")
def freecadcmd():
    exe = find_freecadcmd()
    if exe is None:
        pytest.skip("freecadcmd not found")
    return exe


@pytest.fixture(scope="session")
def freecad_out(tmp_path_factory):
    return tmp_path_factory.mktemp("freecad_out")


@pytest.fixture(scope="session")
def build(freecadcmd, freecad_out):
    """Build a parameter dict with FreeCAD once per (kind, name) and return (result, metadata, checks)."""
    cache = {}

    def _build(kind: str, params: dict, name: str, outputs=None):
        key = (kind, name)
        if key not in cache:
            outputs = outputs or {"render": False}
            result = run_job(kind, params, freecad_out / name, name=name, freecadcmd=freecadcmd, outputs=outputs, timeout=900)
            metadata = json.loads(Path(result.files["metadata"]).read_text(encoding="utf-8"))
            checks = json.loads(Path(result.files["checks"]).read_text(encoding="utf-8")) if "checks" in result.files else None
            cache[key] = (result, metadata, checks)
        return cache[key]
    return _build
