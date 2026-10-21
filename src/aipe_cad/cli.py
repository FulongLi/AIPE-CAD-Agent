"""``aipe-cad`` command line interface.

Exit codes: 0 success, 1 parameter/schema error, 2 FreeCAD/worker error,
3 checks reported a failure (``check`` and ``build --fail-on-check``), 4 usage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import KINDS, __version__
from .materials import MATERIALS
from .params import ParameterError, load_json, resolve, resolve_refs
from .runner import FreeCADNotFoundError, WorkerError, find_freecadcmd, freecad_version, run_job
from .schema import get_schema, validate_params

EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"


def _print(obj) -> None:
    text = json.dumps(obj, indent=2, default=str) if not isinstance(obj, str) else obj
    sys.stdout.write(text.encode("ascii", "replace").decode("ascii") + "\n")


def _load_and_validate(kind: str, path: Path, skip_schema: bool = False) -> dict:
    params = resolve_refs(load_json(path), path.parent)
    if not skip_schema:
        problems = validate_params(kind, params)
        if problems:
            raise ParameterError([f"schema: {p}" for p in problems])
    return params


def cmd_validate(args) -> int:
    path = Path(args.params)
    try:
        params = _load_and_validate(args.kind, path, args.no_schema)
        resolved = resolve(args.kind, params, base_dir=path.parent)
    except ParameterError as exc:
        _print({"valid": False, "errors": exc.messages})
        return 1
    _print({"valid": True, "kind": args.kind, "name": resolved["name"], "warnings": resolved.get("warnings", [])})
    return 0


def cmd_resolve(args) -> int:
    path = Path(args.params)
    try:
        params = _load_and_validate(args.kind, path, args.no_schema)
        resolved = resolve(args.kind, params, base_dir=path.parent)
    except ParameterError as exc:
        _print({"valid": False, "errors": exc.messages})
        return 1
    if args.output:
        Path(args.output).write_text(json.dumps(resolved, indent=2, default=str), encoding="utf-8")
        _print(f"wrote {args.output}")
    else:
        _print(resolved)
    return 0


def cmd_schema(args) -> int:
    _print(get_schema(args.kind))
    return 0


def _build(kind: str, path: Path, out_dir: Path, name: Optional[str], freecadcmd: Optional[str], outputs: dict,
           timeout: float, no_schema: bool) -> int:
    try:
        params = _load_and_validate(kind, path, no_schema)
        result = run_job(kind, params, out_dir, name=name, base_dir=path.parent, freecadcmd=freecadcmd, outputs=outputs, timeout=timeout)
    except ParameterError as exc:
        _print({"status": "parameter_error", "errors": exc.messages})
        return 1
    except FreeCADNotFoundError as exc:
        _print({"status": "freecad_not_found", "error": str(exc)})
        return 2
    except WorkerError as exc:
        _print({"status": "worker_error", "error": str(exc), "log": str(exc.log_path)})
        return 2
    _print({"status": "ok", "kind": kind, "name": result.name, "files": result.files, "duration_s": round(result.duration_s, 2),
            "totals": result.totals, "check_summary": result.check_summary, "warnings": result.result.get("warnings", [])})
    return 0 if not result.check_summary or result.check_summary.get("status") != "fail" else 3


def cmd_build(args) -> int:
    outputs = {"render": not args.no_render, "svg": args.svg, "checks": not args.no_checks, "step": not args.no_step, "fcstd": not args.no_fcstd}
    rc = _build(args.kind, Path(args.params), Path(args.out_dir), args.name, args.freecadcmd, outputs, args.timeout, args.no_schema)
    if rc == 3 and not args.fail_on_check:
        return 0
    return rc


def cmd_check(args) -> int:
    outputs = {"render": False, "svg": False, "checks": True, "step": False, "fcstd": args.keep_fcstd, "metadata": True}
    return _build(args.kind, Path(args.params), Path(args.out_dir), args.name, args.freecadcmd, outputs, args.timeout, args.no_schema)


def cmd_example(args) -> int:
    params_dir = (Path(args.params_dir) if args.params_dir else EXAMPLES_DIR / args.example / "params").resolve()
    out_dir = (Path(args.out_dir) if args.out_dir else EXAMPLES_DIR / args.example).resolve()
    if not params_dir.is_dir():
        _print({"status": "error", "error": f"parameter directory not found: {params_dir}"})
        return 4
    kinds = args.kinds or [k for k in KINDS if (params_dir / f"{k}.json").is_file()]
    summary = {"example": args.example, "units": "SI (m, m^3, kg); file paths relative to this directory",
               "params_dir": str(params_dir.relative_to(out_dir)) if params_dir.is_relative_to(out_dir) else str(params_dir),
               "components": {}}
    exe = find_freecadcmd(args.freecadcmd)
    summary["freecad"] = {"executable": str(exe) if exe else None, "version": freecad_version(exe) if exe else None}
    worst = 0
    for kind in kinds:
        path = params_dir / f"{kind}.json"
        outputs = {"render": not args.no_render, "svg": args.svg}
        try:
            params = _load_and_validate(kind, path)
            result = run_job(kind, params, out_dir, base_dir=path.parent, freecadcmd=args.freecadcmd, outputs=outputs, timeout=args.timeout)
            entry = {"status": "ok", "params": str(path.relative_to(out_dir)) if path.is_relative_to(out_dir.resolve()) else str(path),
                     "files": result.result.get("files", {}),  # relative to out_dir
                     "duration_s": round(result.duration_s, 2), "totals": result.totals,
                     "check_summary": result.check_summary, "warnings": result.result.get("warnings", [])}
            _print(f"[{kind}] ok in {result.duration_s:.1f} s -> {result.files.get('step', result.files.get('metadata'))}")
        except ParameterError as exc:
            entry = {"status": "parameter_error", "errors": exc.messages}
            worst = max(worst, 1)
            _print(f"[{kind}] parameter error: {exc.messages}")
        except (FreeCADNotFoundError, WorkerError) as exc:
            entry = {"status": "worker_error", "error": str(exc)}
            worst = max(worst, 2)
            _print(f"[{kind}] worker error: {exc}")
        summary["components"][kind] = entry
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    _print(f"summary written to {out_dir / 'summary.json'}")
    return worst


def cmd_find_freecad(args) -> int:
    exe = find_freecadcmd(args.freecadcmd)
    if exe is None:
        _print({"found": False, "hint": "install FreeCAD 1.x and/or set AIPE_CAD_FREECADCMD to the freecadcmd executable"})
        return 2
    _print({"found": True, "executable": str(exe), "version": freecad_version(exe)})
    return 0


def cmd_materials(_args) -> int:
    _print({name: {"density_kg_m3": m["density"], "conductive": m["conductive"], "category": m["category"]} for name, m in MATERIALS.items()})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aipe-cad", description="AIPE CAD Agent: parametric FreeCAD geometry and checks for power converters")
    parser.add_argument("--version", action="version", version=f"aipe-cad {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common_build(p):
        p.add_argument("kind", choices=KINDS)
        p.add_argument("params", help="parameter JSON file (SI units)")
        p.add_argument("--out-dir", default="out", help="output directory")
        p.add_argument("--name", help="override the model/output name")
        p.add_argument("--freecadcmd", help="path to freecadcmd (default: auto-detect)")
        p.add_argument("--timeout", type=float, default=1800.0, help="worker timeout in seconds")
        p.add_argument("--no-schema", action="store_true", help="skip JSON-Schema validation (pure-Python rules still apply)")

    p = sub.add_parser("validate", help="validate a parameter file (schema + derived rules)")
    p.add_argument("kind", choices=KINDS)
    p.add_argument("params")
    p.add_argument("--no-schema", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("resolve", help="print the resolved (derived) geometry dictionary")
    p.add_argument("kind", choices=KINDS)
    p.add_argument("params")
    p.add_argument("-o", "--output")
    p.add_argument("--no-schema", action="store_true")
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("schema", help="print the JSON Schema of a kind")
    p.add_argument("kind", choices=KINDS)
    p.set_defaults(func=cmd_schema)

    p = sub.add_parser("build", help="build geometry with FreeCAD: FCStd, STEP, metadata, checks, render")
    common_build(p)
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--svg", action="store_true", help="also write TechDraw hidden-line SVG views (slow for assemblies)")
    p.add_argument("--no-checks", action="store_true")
    p.add_argument("--no-step", action="store_true")
    p.add_argument("--no-fcstd", action="store_true")
    p.add_argument("--fail-on-check", action="store_true", help="exit 3 when the checks report a failure")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("check", help="build in memory and run the interference/clearance checks only")
    common_build(p)
    p.add_argument("--keep-fcstd", action="store_true")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("example", help="run a bundled example (all component kinds) and write summary.json")
    p.add_argument("example", nargs="?", default="dab-10kw")
    p.add_argument("--params-dir")
    p.add_argument("--out-dir")
    p.add_argument("--kinds", nargs="*", choices=KINDS)
    p.add_argument("--freecadcmd")
    p.add_argument("--timeout", type=float, default=1800.0)
    p.add_argument("--no-render", action="store_true")
    p.add_argument("--svg", action="store_true")
    p.set_defaults(func=cmd_example)

    p = sub.add_parser("find-freecad", help="show the freecadcmd executable that would be used")
    p.add_argument("--freecadcmd")
    p.set_defaults(func=cmd_find_freecad)

    p = sub.add_parser("materials", help="list the material table")
    p.set_defaults(func=cmd_materials)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
