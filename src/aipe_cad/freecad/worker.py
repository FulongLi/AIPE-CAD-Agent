"""FreeCAD worker entry point.

Run by the system Python as::

    freecadcmd worker.py --pass <job.json>

(the job path may also be given through the ``AIPE_CAD_JOB`` environment
variable).  The job file names the parameter kind, the parameters (SI), the
output directory and which artefacts to produce.  The worker re-resolves the
parameters with :mod:`aipe_cad.params` (single source of truth for derived
geometry), builds the solids in millimetres, exports FCStd + STEP, computes the
metadata, runs the checks and writes ``<name>.result.json``.

``freecadcmd`` exits with code 0 even after an uncaught Python exception, so the
worker always writes a result file and calls ``sys.exit`` explicitly.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _job_path(argv) -> Path:
    if "--pass" in argv:
        rest = argv[argv.index("--pass") + 1:]
        if rest:
            return Path(rest[0])
    env = os.environ.get("AIPE_CAD_JOB")
    if env:
        return Path(env)
    for arg in reversed(argv):
        if arg.lower().endswith(".json"):
            return Path(arg)
    raise SystemExit("usage: freecadcmd worker.py --pass <job.json>")


def run(job: dict) -> dict:
    import FreeCAD

    from aipe_cad.params import resolve
    from aipe_cad.freecad import _doc
    from aipe_cad.freecad.checks import run_checks
    from aipe_cad.freecad.build_transformer import build_transformer
    from aipe_cad.freecad.build_heatsink import build_coldplate, build_heatsink
    from aipe_cad.freecad.build_assembly import build_assembly

    builders = {"transformer": build_transformer, "heatsink": build_heatsink, "coldplate": build_coldplate, "assembly": build_assembly}
    kind = job["kind"]
    params = job["params"]
    out_dir = Path(job["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = {"fcstd": True, "step": True, "metadata": True, "checks": True, "render": True, "svg": False}
    outputs.update(job.get("outputs", {}))
    timings = {}
    t0 = time.time()
    resolved = resolve(kind, params, base_dir=job.get("base_dir"))
    name = job.get("name") or resolved["name"]
    timings["resolve_s"] = time.time() - t0

    t0 = time.time()
    bodies = builders[kind](resolved)
    timings["build_s"] = time.time() - t0
    invalid = [b.name for b in bodies if not b.shape.isValid()]

    files = {}  # paths relative to out_dir (the runner absolutises them for callers)

    def rel(path) -> str:
        return Path(path).relative_to(out_dir).as_posix()

    t0 = time.time()
    summary_keys = {k: v for k, v in resolved.items() if k in ("name", "kind", "warnings", "analytic", "analytic_masses", "envelope")}
    doc, objects = _doc.build_document(name, bodies, params, summary_keys)
    phys_objects = [o for o, b in zip(objects, bodies) if b.role in _doc.PHYSICAL_ROLES]
    if outputs["fcstd"]:
        files["fcstd"] = rel(_doc.save_fcstd(doc, out_dir / f"{name}.FCStd"))
    step_check = None
    if outputs["step"]:
        step_path = _doc.export_step(phys_objects, out_dir / f"{name}.step")
        files["step"] = rel(step_path)
        expected = sum(b.shape.Volume for b in bodies if b.role in _doc.PHYSICAL_ROLES)
        step_check = _doc.step_reimport_check(step_path, expected)
        step_check["path"] = rel(step_path)
        keepouts = [o for o, b in zip(objects, bodies) if b.role not in _doc.PHYSICAL_ROLES]
        if keepouts:
            files["step_keepouts"] = rel(_doc.export_step(keepouts, out_dir / f"{name}.keepouts.step"))
    timings["export_s"] = time.time() - t0

    report = None
    if outputs["checks"]:
        t0 = time.time()
        config = dict(resolved.get("checks", {}) or {})
        if kind != "assembly" and resolved.get("fit_pairs"):
            config["fit_pairs"] = list(config.get("fit_pairs", [])) + list(resolved["fit_pairs"])
        report = run_checks(bodies, config)
        report["kind"], report["name"] = kind, name
        path = out_dir / f"{name}.checks.json"
        path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        files["checks"] = rel(path)
        timings["checks_s"] = time.time() - t0

    if outputs["render"]:
        t0 = time.time()
        try:
            from aipe_cad.freecad._render import render_png
            files["render_png"] = rel(render_png(bodies, out_dir / "renders" / f"{name}.png",
                                                 title=f"{name} ({kind}) - AIPE CAD Agent, FreeCAD {'.'.join(FreeCAD.Version()[0:3])}"))
        except Exception as exc:  # rendering is best effort
            files["render_error"] = f"{type(exc).__name__}: {exc}"
        timings["render_s"] = time.time() - t0
    if outputs["svg"]:
        try:
            from aipe_cad.freecad._render import render_svg_views
            files["render_svg"] = rel(render_svg_views(bodies, out_dir / "renders" / f"{name}.svg"))
        except Exception as exc:
            files["svg_error"] = f"{type(exc).__name__}: {exc}"

    metadata = None
    if outputs["metadata"]:
        metadata = _doc.compute_metadata(kind, name, bodies, resolved, params, files,
                                         contacts=report.get("contacts") if report else None, step_check=step_check,
                                         freecad_version=".".join(FreeCAD.Version()[0:3]))
        metadata["timings_s"] = timings
        metadata["invalid_shapes"] = invalid
        if report:
            metadata["check_summary"] = report["summary"]
        path = out_dir / f"{name}.metadata.json"
        files["metadata"] = rel(path)
        metadata["files"] = dict(files)
        path.write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
    return {
        "status": "ok", "kind": kind, "name": name, "files": files, "timings_s": timings,
        "freecad_version": FreeCAD.Version()[0:3], "python_version": sys.version.split()[0],
        "body_count": len(bodies), "invalid_shapes": invalid,
        "check_summary": report["summary"] if report else None,
        "totals": metadata["totals"] if metadata else None,
        "warnings": resolved.get("warnings", []),
    }


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    job_path = _job_path(argv)
    job = json.loads(Path(job_path).read_text(encoding="utf-8"))
    result_path = Path(job.get("result_path") or (Path(job["out_dir"]) / f"{job.get('name', 'job')}.result.json"))
    started = time.time()
    try:
        result = run(job)
    except Exception as exc:  # report every failure through the result file
        result = {"status": "error", "kind": job.get("kind"), "name": job.get("name"),
                  "error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()}
    result["duration_s"] = time.time() - started
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"AIPE_RESULT_JSON {result_path}")
    print(f"AIPE_STATUS {result['status']}")
    return 0 if result["status"] == "ok" else 2


if __name__ in ("__main__", "worker"):
    sys.exit(main())
