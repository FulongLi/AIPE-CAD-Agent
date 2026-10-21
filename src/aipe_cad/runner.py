"""Spawn ``freecadcmd`` from the system Python and collect worker results."""
from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .params import ParameterError, resolve, resolve_refs

ENV_VARS = ("AIPE_CAD_FREECADCMD", "AIPE_FREECADCMD", "FREECADCMD")
DEFAULT_TIMEOUT_S = 1800.0


class FreeCADNotFoundError(RuntimeError):
    pass


class WorkerError(RuntimeError):
    def __init__(self, message: str, result: Optional[dict] = None, log_path: Optional[Path] = None):
        super().__init__(message)
        self.result = result or {}
        self.log_path = log_path


@dataclass
class JobResult:
    ok: bool
    kind: str
    name: str
    files: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)
    log_path: Optional[Path] = None
    job_path: Optional[Path] = None
    duration_s: float = 0.0
    returncode: int = 0

    @property
    def check_summary(self) -> Optional[dict]:
        return self.result.get("check_summary")

    @property
    def totals(self) -> Optional[dict]:
        return self.result.get("totals")


def _candidates():
    yield from (os.environ.get(v) for v in ENV_VARS if os.environ.get(v))
    for name in ("freecadcmd", "FreeCADCmd", "freecadcmd.exe", "FreeCADCmd.exe"):
        found = shutil.which(name)
        if found:
            yield found
    system = platform.system()
    if system == "Windows":
        roots = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
        patterns = []
        for root in roots:
            if root:
                patterns.append(os.path.join(root, "Programs", "FreeCAD*", "bin", "freecadcmd.exe"))
                patterns.append(os.path.join(root, "FreeCAD*", "bin", "freecadcmd.exe"))
                patterns.append(os.path.join(root, "FreeCAD*", "bin", "FreeCADCmd.exe"))
        for pattern in patterns:
            for hit in sorted(glob.glob(pattern), reverse=True):
                yield hit
    elif system == "Darwin":
        yield "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"
        for hit in sorted(glob.glob("/Applications/FreeCAD*.app/Contents/MacOS/FreeCADCmd"), reverse=True):
            yield hit
    else:
        for hit in ("/usr/bin/freecadcmd", "/usr/local/bin/freecadcmd", "/usr/bin/FreeCADCmd", "/snap/bin/freecad.cmd"):
            yield hit


def find_freecadcmd(explicit: Optional[str] = None) -> Optional[Path]:
    """Locate the FreeCAD console executable (explicit path, env vars, PATH, standard install locations)."""
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for cand in _candidates():
        if cand and Path(cand).is_file():
            return Path(cand)
    return None


def freecad_version(exe: Path, timeout: float = 120.0) -> str:
    out = subprocess.run([str(exe), "--version"], capture_output=True, text=True, errors="replace", timeout=timeout)
    text = (out.stdout or "") + (out.stderr or "")
    return text.strip().splitlines()[0] if text.strip() else "unknown"


def worker_script() -> Path:
    return Path(__file__).resolve().parent / "freecad" / "worker.py"


def package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_job(kind: str, params: dict, out_dir, name: Optional[str] = None, *, base_dir=None, freecadcmd=None,
            outputs: Optional[dict] = None, timeout: float = DEFAULT_TIMEOUT_S, keep_work: bool = True) -> JobResult:
    """Validate ``params`` in this interpreter, then build them with ``freecadcmd``.

    Raises :class:`ParameterError` for invalid parameters before FreeCAD is
    started, :class:`FreeCADNotFoundError` when no executable is found and
    :class:`WorkerError` when the worker reports a failure.
    """
    exe = find_freecadcmd(freecadcmd)
    if exe is None:
        raise FreeCADNotFoundError("freecadcmd not found; set AIPE_CAD_FREECADCMD or pass --freecadcmd")
    params = resolve_refs(params, Path(base_dir) if base_dir else None)
    resolved = resolve(kind, params, base_dir=base_dir)  # raises ParameterError
    name = name or resolved["name"]
    out_dir = Path(out_dir).resolve()
    work = out_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    job_path = work / f"{name}.job.json"
    result_path = work / f"{name}.result.json"
    log_path = work / f"{name}.freecad.log"
    job = {"kind": kind, "name": name, "params": params, "base_dir": str(base_dir) if base_dir else None,
           "out_dir": str(out_dir), "outputs": outputs or {}, "result_path": str(result_path),
           "package_root": str(package_root()), "resolved_preview": {k: resolved[k] for k in ("name", "warnings") if k in resolved}}
    job_path.write_text(json.dumps(job, indent=1, default=str), encoding="utf-8")
    if result_path.exists():
        result_path.unlink()
    env = dict(os.environ)
    env["AIPE_CAD_JOB"] = str(job_path)
    env["PYTHONIOENCODING"] = "utf-8"
    cmd = [str(exe), str(worker_script()), "--pass", str(job_path)]
    started = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(work), env=env, capture_output=True, text=True, errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        log_path.write_text(f"TIMEOUT after {timeout} s\n{exc.stdout or ''}\n{exc.stderr or ''}", encoding="utf-8")
        raise WorkerError(f"freecadcmd timed out after {timeout} s (log: {log_path})", log_path=log_path) from exc
    duration = time.time() - started
    log_path.write_text(f"$ {' '.join(cmd)}\n--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n--- exit {proc.returncode} ---\n",
                        encoding="utf-8")
    if not result_path.exists():
        tail = (proc.stdout + proc.stderr)[-3000:]
        raise WorkerError(f"worker produced no result file (exit {proc.returncode}); log: {log_path}\n{tail}", log_path=log_path)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("status") != "ok":
        raise WorkerError(f"worker failed: {result.get('error')}\n{result.get('traceback', '')}", result=result, log_path=log_path)
    # the worker records paths relative to out_dir; hand absolute paths to callers
    files = {k: (str(out_dir / v) if not k.endswith("_error") else v) for k, v in result.get("files", {}).items()}
    return JobResult(ok=True, kind=kind, name=name, files=files, result=result, log_path=log_path,
                     job_path=job_path, duration_s=duration, returncode=proc.returncode)
