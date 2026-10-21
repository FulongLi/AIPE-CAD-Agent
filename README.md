# AIPE CAD Agent

Parametric engineering geometry for power-electronics converters, built with
[FreeCAD](https://www.freecad.org/) (headless `freecadcmd`) and driven by JSON
parameter files in SI units:

* **Transformer** - E-core pair, bobbin, winding bodies whose layer count and
  radial build follow from the wire data, insulation barriers and margins,
  terminal pins, core clips, base plate and a clearance envelope.
* **Heat sink** - plate-fin aluminium body (fin count from pitch), TO-247
  device footprints with isolation pads, shoulder bushings and screws, mounting
  holes.
* **Cold plate** - boolean-cut serpentine channel, cover plate, hose bosses,
  blind screw holes, coolant (fluid) body for CFD/thermal meshing.
* **Converter assembly** - chassis with airflow cut-outs, four heat sinks or one
  cold plate, primary/secondary/control boards with copper zones and keep-outs,
  transformer, standoffs and DC terminal blocks in one coordinate system.

Every build exports an editable **FCStd**, a **STEP** file, a **metadata JSON**
(bounding box, volume, surface area and mass per solid, mass per material,
contacts, Gmsh mesh hints) and a **check report** (pairwise interference by
boolean common volume, keep-out/envelope intrusions, fit distances and
net-to-net clearance measurements against caller-supplied requirements).
PNG renders are produced headless with matplotlib.

> The models are illustrative parametric geometry for layout, mass and
> clearance studies. They are **not manufacturable designs**, make **no DFM
> claims** and assert **no compliance with any standard**: required clearance
> and creepage values are inputs supplied by the caller and are only compared
> with geometric measurements.

## Installation

Requirements: Python >= 3.10 (orchestration, tests, CLI) and FreeCAD 1.x with
`freecadcmd`. FreeCAD bundles its own Python (3.11 in FreeCAD 1.1); the
geometry workers run inside it, the CLI and tests run in the system Python and
spawn `freecadcmd` as a subprocess. No FreeCAD Python modules are imported in
the system interpreter.

```bash
git clone https://github.com/FulongLi/AIPE-CAD-Agent
cd AIPE-CAD-Agent
python -m pip install -e .[dev]          # jsonschema, pytest, pyyaml
python -m pip install -e .[cadquery]     # optional: experimental CadQuery backend
aipe-cad find-freecad                    # shows the freecadcmd that will be used
```

FreeCAD is located from (in order) `--freecadcmd PATH`, the environment
variables `AIPE_CAD_FREECADCMD` / `AIPE_FREECADCMD`, `PATH`, and the standard
install folders (`%LOCALAPPDATA%\Programs\FreeCAD*\bin\freecadcmd.exe`,
`C:\Program Files\FreeCAD*\bin\...`, `/Applications/FreeCAD.app`, `/usr/bin`).
Install FreeCAD from https://www.freecad.org/downloads.php (on Windows e.g.
`winget install FreeCAD.FreeCAD --scope user`). Tested with FreeCAD 1.1.4 on
Windows 11 and system Python 3.10.11.

## Quick start

```bash
# validate a parameter file (JSON Schema + derived-geometry rules) and print warnings
aipe-cad validate transformer examples/dab-10kw/params/transformer.json

# print the resolved geometry (layer counts, build, masses, mesh hints, ...)
aipe-cad resolve heatsink examples/dab-10kw/params/heatsink.json -o resolved.json

# build with FreeCAD: FCStd + STEP + metadata + checks + PNG render
aipe-cad build transformer examples/dab-10kw/params/transformer.json --out-dir out/transformer
aipe-cad build assembly    examples/dab-10kw/params/assembly.json    --out-dir out/assembly

# checks only (no STEP/render), exit code 3 when a check fails
aipe-cad check assembly examples/dab-10kw/params/assembly.json --out-dir out/check

# run the complete 10 kW DAB example (all four kinds) and write summary.json
aipe-cad example dab-10kw --out-dir examples/dab-10kw

aipe-cad schema coldplate            # JSON Schema of a kind
aipe-cad materials                   # density table used for masses
```

Python API (for optimisers): the parameter layer is pure Python and cheap, the
FreeCAD build is only needed for the final geometry and checks.

```python
from aipe_cad.params import resolve, load_json, ParameterError
from aipe_cad.runner import run_job

params = load_json("examples/dab-10kw/params/heatsink.json")
params["fins"]["pitch"] = 0.0045           # metres
res = resolve("heatsink", params)         # raises ParameterError if the rules are violated
print(res["fins"]["count"], res["analytic"]["mass_without_holes"], res["analytic"]["convective_area"])

job = run_job("heatsink", params, "out/hs_opt")   # spawns freecadcmd
print(job.files["step"], job.totals["mass_kg"], job.check_summary["status"])
```

## Parameter files

All lengths are **metres**, masses kilograms (FreeCAD works in millimetres;
the workers convert at the boundary and the metadata is converted back). Each
kind has a JSON Schema in `src/aipe_cad/schemas/` (generated from
`aipe_cad/schema.py`, kept in sync by a test) and a pure-Python resolver in
`aipe_cad/params/` that validates the input, applies the derived-geometry
rules and returns a JSON-serialisable dictionary consumed by the FreeCAD
worker, the tests and any optimiser. The assembly file references the
component files with `{"$ref": "heatsink.json"}` (sibling keys override).
`docs/parameters.md` lists the parameters and derived rules.

Derived rules include: window width, outer-leg width and yoke thickness from
the E-core letters; bobbin tube/flange sizes from clearances; turns per layer,
layer count and radial build from the conductor outer diameter or foil
thickness; total build versus the window (error when it does not fit); mean
length of turn, copper mass and DC resistance; fin count
`floor((W - t) / pitch) + 1`; serpentine pass positions, turn radii and
port sides from the pass count; standoff heights from the supporting surface;
device lead holes in the boards above them; chassis cut-outs and holes.

## Outputs

For a build named `NAME` in `--out-dir`:

| file | content |
| --- | --- |
| `NAME.FCStd` | editable FreeCAD document; one `Part::Feature` per body grouped by component, custom properties `AipeMaterial`, `AipeNet`, `AipeRole`, `AipeGroup`, `AipeDensity`; full parameter JSON on the `Parameters` object |
| `NAME.step` | all physical solids, STEP product names = body names |
| `NAME.keepouts.step` | keep-out and clearance-envelope volumes (when present) |
| `NAME.metadata.json` | per body: volume, surface area, mass (density per material), bounding box, centre of mass, analytic cross-check; totals; mass per material; contacts; STEP re-import check; Gmsh mesh hints (regions, material tags, element sizes, air/fluid regions) |
| `NAME.checks.json` | interference, contacts, keep-out/envelope intrusions, fit pairs, clearance pairs, summary |
| `renders/NAME.png` | shaded isometric view and three orthographic projections (matplotlib, painter's algorithm) |
| `_work/` | job file, worker result and FreeCAD log (ignored by git) |

## Checks

* **Interference** - for every pair of physical solids with intersecting
  bounding boxes, `Part.Shape.common` is computed; a common volume above
  `min_overlap_volume` (default 1e-12 m^3) is an interference unless the pair
  matches `allowed_overlaps`. Touching bodies are listed as `contacts`.
* **Keep-outs / envelopes** - board keep-out volumes and component clearance
  envelopes must not be entered by other components (`ignore_pairs` available).
* **Fit** - `distToShape` between two named bodies versus an expected gap; the
  transformer adds bobbin-to-core and stack-to-core pairs automatically.
* **Clearance** - for each `(net_a, net_b)` pair the straight-line distance
  between every conductive body of the two nets is measured with
  `Part.Shape.distToShape`. The segment is sampled: if it passes through
  insulating solids (or along an interface between two solids) it is not an
  air path. For such pairs a one-bend path around the edges of the blocking
  insulator is searched (the "stretched string" clearance); if none exists the
  pair is reported for **review** with the solid-insulation thickness. Pair
  status: `pass` (all evaluated air paths >= required), `fail` (an air path is
  shorter or conductors of different nets touch), `review` (conductors
  separated only by thin solid insulation, e.g. windings behind a barrier,
  device tab to screw through the bushing). Creepage is only compared against
  the measured air path (`satisfied_by_clearance`) and is otherwise
  `not_evaluated`; surface paths are not traced.

## Example: 10 kW DAB (800 V -> 400 V, 100 kHz)

`examples/dab-10kw/` contains the parameter files, the generated STEP/FCStd/
metadata/check reports/renders and `summary.json`; see
`examples/dab-10kw/README.md` for the resulting volumes, masses, bounding boxes
and check results. Data-sheet references used for the defaults:

* TDK E 65/32/27 core (B66387) - https://www.tdk-electronics.tdk.com/inf/80/db/fer/e_65_32_27.pdf
  (Ae 535 mm^2, le 147 mm, Ve 78650 mm^3, approx. 394 g/set; nominal outline
  letters A=65.2, B=32.6, C=44.2, D=22.2, E=20.0, F=27.4 mm transcribed from the
  IEC 62317-8 outline shown in the drawing - verify against the current revision).
* Wolfspeed C3M0032120K TO-247-4L package outline drawing -
  https://assets.wolfspeed.com/uploads/2024/01/Wolfspeed_C3M0032120K_data_sheet.pdf
  (A 4.83-5.21, E 15.75-16.13, D 23.30-23.63, P 3.51-3.65, L 17.31-17.82 mm,
  e1 5.08 BSC; mid-tolerance values are used, the tab thickness is an assumption).

## Tests

```bash
python -m pytest                       # pure-Python tests + FreeCAD tests (skipped if freecadcmd is missing)
python -m pytest -m "not freecad"      # parameter rules, schemas, CLI, manifest only
python -m pytest -m freecad            # volumes vs analytic formulas, STEP re-import, deliberate interference/clearance cases
AIPE_CAD_SKIP_FREECAD=1 python -m pytest   # force-skip the FreeCAD tests
```

`freecad`-marked tests spawn `freecadcmd` and build each example component
once per session; `cadquery`-marked tests need the optional package.

## Limitations

* Illustrative models: no manufacturability, tolerance, thermal or
  electromagnetic claims; the geometry exists to support layout, mass,
  interference and clearance studies and FEA/CFD meshing.
* Windings are homogenised annular bodies (one solid per winding) with the
  layer thickness from the wire data; individual turns, lead-outs, bends,
  solder joints and cable routing are not modelled; terminals are plain pins.
* Clearance uses straight or one-bend air paths; multi-bend paths and creepage
  along insulating surfaces are not traced, so encapsulated conductors end in
  `review`, never in `pass`.
* Required clearance/creepage values are caller inputs; nothing asserts IEC/UL
  compliance.
* Data-sheet dimensions are nominal transcriptions (see above); verify them.
* Console-mode FreeCAD writes no colours/appearance to FCStd or STEP; renders
  are matplotlib projections with a painter's algorithm, not ray-traced views.
* The CadQuery backend (`aipe_cad.cadquery_backend`) is experimental and covers
  only the heat-sink body (STEP, volume, mass); FreeCAD is the required path.
* No AIPE Core Engineering State adapter yet (`compatibility.integration: none`).

## Licence

MIT (see `LICENSE`). FreeCAD is LGPL-2.1-or-later and is used as an external
executable; CadQuery is Apache-2.0 and optional.
