# Outputs, checks and limitations

## Build outputs

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

All lengths in the parameter files are metres and masses kilograms; FreeCAD works in millimetres and the workers
convert at the boundary. Each kind has a JSON Schema in `src/aipe_cad/schemas/` (generated from `aipe_cad/schema.py`,
kept in sync by a test) and a pure-Python resolver in `aipe_cad/params/` that validates the input, applies the
derived-geometry rules (see `parameters.md`) and returns the dictionary consumed by the FreeCAD worker, the tests and
any optimiser. The assembly file references component files with `{"$ref": "heatsink.json"}` (sibling keys override).

## Checks

* **Interference** – for every pair of physical solids with intersecting bounding boxes, `Part.Shape.common` is
  computed; a common volume above `min_overlap_volume` (default 1e-12 m³) is an interference unless the pair matches
  `allowed_overlaps`. Touching bodies are listed as `contacts`.
* **Keep-outs / envelopes** – board keep-out volumes and component clearance envelopes must not be entered by other
  components (`ignore_pairs` available).
* **Fit** – `distToShape` between two named bodies versus an expected gap; the transformer adds bobbin-to-core and
  stack-to-core pairs automatically.
* **Clearance** – for each `(net_a, net_b)` pair the straight-line distance between every conductive body of the two
  nets is measured with `Part.Shape.distToShape`. The segment is sampled: if it passes through insulating solids (or
  along an interface between two solids) it is not an air path. For such pairs a one-bend path around the edges of the
  blocking insulator is searched (the "stretched string" clearance); if none exists the pair is reported for **review**
  with the solid-insulation thickness. Pair status: `pass` (all evaluated air paths ≥ required), `fail` (an air path is
  shorter or conductors of different nets touch), `review` (conductors separated only by thin solid insulation, e.g.
  windings behind a barrier, device tab to screw through the bushing). Creepage is only compared against the measured
  air path (`satisfied_by_clearance`) and is otherwise `not_evaluated`; surface paths are not traced.

## Limitations

* Illustrative models: no manufacturability, tolerance, thermal or electromagnetic claims; the geometry exists to
  support layout, mass, interference and clearance studies and FEA/CFD meshing. Nothing asserts IEC/UL compliance:
  required clearance/creepage values are caller inputs.
* Windings are homogenised annular bodies (one solid per winding section) with the layer thickness from the wire
  data; individual turns, lead-outs, bends, solder joints and cable routing are not modelled; terminals are plain pins.
* Clearance uses straight or one-bend air paths; multi-bend paths and creepage along insulating surfaces are not
  traced, so encapsulated conductors end in `review`, never in `pass`.
* Data-sheet dimensions used by the example are nominal transcriptions (TDK E 65/32/27 core B66387,
  https://www.tdk-electronics.tdk.com/inf/80/db/fer/e_65_32_27.pdf: Ae 535 mm², le 147 mm, Ve 78 650 mm³, ≈394 g/set,
  outline letters A=65.2, B=32.6, C=44.2, D=22.2, E=20.0, F=27.4 mm; Wolfspeed C3M0032120K TO-247-4L outline,
  https://assets.wolfspeed.com/uploads/2024/01/Wolfspeed_C3M0032120K_data_sheet.pdf, mid-tolerance values, tab
  thickness assumed). Verify against the current revisions.
* Console-mode FreeCAD writes no colours/appearance to FCStd or STEP; renders are matplotlib projections, not
  ray-traced views.
* The CadQuery backend (`aipe_cad.cadquery_backend`) is experimental and covers only the heat-sink body (STEP, volume,
  mass); FreeCAD is the required path.
* Integration with the AIPE Engineering State is done by the AIPE-Workflows adapter (`adapters/cad_agent.py`), which
  derives the transformer parameters from the selected magnetics candidate and catalogue core record and the heat-sink
  parameters from the thermal screening candidate; this repository itself has no Core adapter.
