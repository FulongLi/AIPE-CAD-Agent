# Validation record

## Test suites

| Marker | What it covers | Where it runs |
| --- | --- | --- |
| (none) | parameter rules, derived geometry, JSON Schemas (sync with `schema.py`), CLI, capability manifest against the vendored Registry schema — 53 tests | every push, GitHub Actions `Tests / pure-Python tests` on Python 3.10, 3.11, 3.12 |
| `freecad` | body volumes against closed-form formulas, STEP re-import volume check, a deliberate 1 mm interference (2.5e-6 m³) detected, clearance against an analytic 14.79 mm case, the full 10 kW DAB example build — 8 tests | locally with `freecadcmd`; the GitHub Actions job `FreeCAD geometry tests` tries `apt-get install freecad` and reports a warning when the runner has no FreeCAD (skipped tests are never counted as passed) |
| `cadquery` | optional CadQuery backend (heat-sink body) — 2 tests | locally when `cadquery` is installed |

Commands:

```bash
python -m pytest                        # everything; FreeCAD/CadQuery tests skip with a reason when the tool is absent
python -m pytest -m "not freecad and not cadquery"
python -m pytest -m freecad
AIPE_CAD_SKIP_FREECAD=1 python -m pytest
```

## Last validated local execution

2026-10-21, Windows 11, system Python 3.10.11, FreeCAD 1.1.4 (`freecadcmd`), cadquery 2.7.0:
`python -m pytest` → **63 passed** (53 pure-Python, 8 FreeCAD, 2 CadQuery) in 123 s.

Executed 10 kW DAB example (`aipe-cad example dab-10kw`, ≈100 s): all four kinds produced `.FCStd`, `.step`,
`.keepouts.step`, `.metadata.json`, `.checks.json`, renders and `summary.json`; STEP re-import volume errors
1e-15 … 1e-16; FreeCAD volumes match the closed-form values to < 1e-14 (fused bobbin 0.37 %).

| model | bodies | bbox (mm) | volume | mass | checks |
| --- | --- | --- | --- | --- | --- |
| transformer (E65/32/27, 21:10, litz/foil) | 18 | 89.2 × 62.6 × 69.1 | 159.0 cm³ | 708.6 g | 0 interference, fit 3/3 pass; pri/pe and sec/pe pass (15.85 mm); pri/sec review (0.5 mm barrier) |
| heat sink (12 fins, 2 × TO-247-4L) | 19 | 83.3 × 80.0 × 59.5 | 92.7 cm³ | 254.6 g | 0 interference; pri/pe review (one-bend path 2.75 mm ≥ 2.0 mm, tab-to-screw through bushing listed) |
| cold plate (4-pass serpentine, 8 devices) | 77 | 260 × 120 × 31.5 | 451.0 cm³ | 1184 g | pri/sec pass 36.5 mm; pri/pe, sec/pe review |
| assembly (chassis, 4 sinks, 3 boards, transformer, 2 DC blocks) | 119 | 440 × 240 × 116.6 | 967.5 cm³ | 2.789 kg | 0 interference/keep-out/envelope, fit 3/3; pri/control, sec/control pass (10.83 mm); pri/sec, pri/pe, sec/pe review |

In the AIPE-Workflows DAB reference run (2026-10-21) the adapter built the selected E 70/33/32 20:10 transformer
(0.864 kg, no interference, pri/sec review) and the Stage A heat-sink candidate (sink mass 0.275 kg, −1.3 % versus the
correlation model) from the Engineering State; see AIPE-Workflows `examples/dab-10kw/results/`.

These are geometry checks only: no manufacturability, thermal, electromagnetic or standards-compliance claim follows.
