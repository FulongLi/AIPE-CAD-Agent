# AIPE — CAD Agent

Parametric engineering geometry for power-electronics converters, generated headlessly with
[FreeCAD](https://www.freecad.org/) (`freecadcmd`) from JSON parameter files in SI units. It is the
mechanical-geometry specialist of the AIPE ecosystem: AIPE-Workflows derives its parameters from the
selected magnetics, thermal and electrical results and calls it through a documented adapter. The
models are illustrative geometry for layout, mass, interference and clearance studies — not
manufacturable designs, and nothing asserts compliance with any standard.

## Features

- Transformer: E-core pair, bobbin, winding sections sized from wire data, barriers, pins, clips, base plate
- Plate-fin heat sink with TO-247 devices on isolation pads, bushings, screws and mounting holes
- Liquid cold plate with serpentine channel, cover, ports and a fluid body for meshing
- Converter assembly: chassis, cooling, boards with copper zones and keep-outs, transformer, connectors
- Editable `.FCStd` and STEP export, per-body volume/mass/bounding-box metadata, Gmsh mesh hints
- Interference, keep-out, fit and net-to-net clearance checks against caller-supplied requirements
- Pure-Python parameter layer (schemas and derived rules) usable without FreeCAD, CLI and Python API

## Installation

Python ≥ 3.10 plus FreeCAD 1.x providing `freecadcmd` (found via `--freecadcmd`, `AIPE_CAD_FREECADCMD`,
`PATH` or the standard install folders; Windows: `winget install FreeCAD.FreeCAD --scope user`).

```bash
git clone https://github.com/FulongLi/AIPE-CAD-Agent
cd AIPE-CAD-Agent
python -m pip install -e .[dev]
aipe-cad find-freecad
```

## Usage

```bash
aipe-cad validate transformer examples/dab-10kw/params/transformer.json
aipe-cad build heatsink examples/dab-10kw/params/heatsink.json --out-dir out/heatsink
aipe-cad example dab-10kw --out-dir examples/dab-10kw      # all four kinds + summary.json
```

```python
from aipe_cad.params import resolve, load_json
from aipe_cad.runner import run_job

params = load_json("examples/dab-10kw/params/heatsink.json")
params["fins"]["pitch"] = 0.0045                       # metres
resolved = resolve("heatsink", params)                 # rules and derived geometry, no FreeCAD needed
job = run_job("heatsink", params, "out/hs")            # spawns freecadcmd: FCStd, STEP, metadata, checks
print(job.totals["mass_kg"], job.check_summary["status"])
```

## Project Information

- Version: 0.1.0
- Status: Prototype (geometry and checks executed with FreeCAD 1.1.4; illustrative models only)
- Developer: Fulong Li
- Organisation: Spirit Connect / AIPE Labs
- License: MIT (FreeCAD is used as an external LGPL executable; CadQuery is an optional Apache-2.0 backend)

## Documentation

- [Parameters and derived rules](docs/parameters.md)
- [Outputs, checks and limitations](docs/outputs-and-checks.md)
- [Validation record and test matrix](docs/validation.md)
- [10 kW DAB example](examples/dab-10kw/README.md)
