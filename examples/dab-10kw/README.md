# Example: 10 kW DAB converter (800 V -> 400 V, 100 kHz)

Generated with `aipe-cad example dab-10kw --out-dir examples/dab-10kw` using
FreeCAD 1.1.4 (`freecadcmd`, headless) on Windows 11. The parameter files in
`params/` are the single source; every other file here is a generated artefact
and can be regenerated with the command above (about 100 s on a laptop, the
assembly checks dominate).

| kind | parameters | outputs |
| --- | --- | --- |
| transformer | `params/transformer.json` | `dab_transformer.{FCStd,step,keepouts.step,metadata.json,checks.json}`, `renders/dab_transformer.png` |
| heat sink | `params/heatsink.json` | `dab_heatsink.*`, `renders/dab_heatsink.png` |
| cold plate | `params/coldplate.json` | `dab_coldplate.*`, `renders/dab_coldplate.png` |
| assembly | `params/assembly.json` (references the files above) | `dab_10kw_assembly.*`, `renders/dab_10kw_assembly.png` |
| all | | `summary.json` (status, totals and check summary per kind) |

All numbers below are copied from the generated metadata and check reports
(SI units converted to mm, cm^3 and g for readability). The models are
illustrative parametric geometry, not a manufacturable converter; required
clearance/creepage values in the parameter files are illustrative caller
inputs, not standard requirements.

## Transformer `dab_transformer`

E65/32/27 pair (TDK B66387 data sheet cited in the parameter file), N87,
21 turns litz 420 x 0.1 mm (2 layers, 5.85 mm build) : 10 turns copper foil
0.2 mm x 32.4 mm (2.5 mm build), 0.5 mm polyimide barrier, 4 mm margins,
0.3 mm outer wrap, 0.65 mm spare radial build, brass pins on the top flange,
stainless clips, aluminium base plate.

* bodies: 18; bounding box x -44.6..44.6, y -31.3..31.3, z -35.4..33.7 mm (89.2 x 62.6 x 69.1 mm)
* volume 159.02 cm^3, mass 708.6 g (ferrite 422.1, windings 199.2, clips 33.8, bobbin 20.1, insulation 19.8, plate 12.9, pins 0.7)
* core half: 43.519 cm^3 / 211.1 g each (data sheet: approx. 394 g/set, i.e. the sharp-cornered model is about 7 % heavy)
* primary winding body 23.856 cm^3 / 105.5 g (copper 78.1 g, MLT 125.9 mm, R_dc(20 degC) 13.8 mOhm); secondary 12.574 cm^3 / 93.7 g (copper 90.1 g, MLT 155.2 mm, 4.1 mOhm)
* STEP re-import: 18 solids, relative volume error 2e-16; FreeCAD volumes match the closed-form values to < 1e-14 except the fused bobbin (0.37 %)
* checks: interference 0, contacts 31, fit pairs 3/3 pass (bobbin-to-core 0.300 mm, wrap-to-leg 1.150 mm as expected)
  * primary/pe: **pass**, 15.85 mm air (pin to clip) >= 2.0 mm required
  * secondary/pe: **pass**, 15.85 mm
  * primary/secondary: **review** - the windings are separated only by the 0.5 mm barrier plus margins and bobbin (no air path), pins are 55.1 mm apart; the creepage along the barrier/flange is not traced by the tool

## Heat sink `dab_heatsink`

80 x 80 x 8 mm aluminium base, 12 fins 1.5 x 35 x 60 mm at 5 mm pitch (the
pitch rule alone would give 16 fins; 12 shorter fins leave a chassis rim), two
TO-247-4L devices on 0.25 mm alumina pads with 2.5 mm overhang, nylon shoulder
bushings and M3 screws, four M4 corner holes.

* bodies: 19; bounding box 83.3 x 80.0 x 59.5 mm (z -35.0..24.5 mm, leads included)
* volume 92.74 cm^3, mass 254.6 g (aluminium 238.6 g); convective area 0.0581 m^2
* STEP re-import relative error 1e-15; all body volumes match the closed-form values to < 1e-15
* checks: interference 0, contacts 26
  * primary/pe: **review** - governing air path 2.75 mm (tab -> pad edge -> base, one bend) >= 2.0 mm required, leads 2.48 mm above the base; the tab-to-screw pairs are separated only by the 0.29 mm bushing sleeve and are listed for review

## Cold plate `dab_coldplate`

240 x 120 x 12 mm aluminium plate, four-pass serpentine channel 8 x 6 mm at
26 mm pitch cut from the underside and closed by a 3 mm cover, brass hose
bosses (both on the -x face because the pass count is even), eight devices in
two rows (primary +y, secondary -y) with 2.5 mm tapped holes 4 mm deep.

* bodies: 77 (incl. the `coolant` fluid body); bounding box 260 x 120 x 31.5 mm (bosses included)
* volume 451.04 cm^3, mass 1184.0 g (aluminium 1048.3, coolant 45.1, brass 28.8, devices/hardware 61.7)
* coolant volume 42.15 cm^3 (channel 41.31 + bores 0.85) - FreeCAD and closed form agree to < 1e-14
* checks: interference 0, contacts 121
  * primary/secondary: **pass**, 36.53 mm between the device rows
  * primary/pe and secondary/pe: **review** - straight air path 2.46 mm (lead to plate) >= 2.0 mm, tab-to-screw through the bushing listed for review

## Assembly `dab_10kw_assembly`

440 x 240 x 3 mm chassis with airflow cut-outs under four heat sinks
(fins down, device nets primary/secondary), 160 x 200 mm primary and secondary
power boards 22.5 mm above the chassis on nylon standoffs with HV/LV copper
planes, keep-outs for DC-link/output capacitors and gate drivers and 16 lead
holes each, the transformer resting on the chassis between them, an 80 x 120 mm
control board at z = 80 mm, DC input/output terminal blocks.

* bodies: 119; bounding box x -220..220, y -120..120, z -35.0..81.6 mm (440 x 240 x 116.6 mm)
* volume 967.46 cm^3, mass 2.789 kg (aluminium 1697.7 g, ferrite 422.1, copper 265.8, FR4 217.3, nylon 48.2, stainless 33.8, brass 27.6, mould compound 22.8, bobbin 20.1, polyimide 19.8, steel 10.5, alumina 3.1)
* STEP re-import: 119 solids, relative volume error 2e-15
* checks (54 s): interference 0, keep-out violations 0, envelope intrusions 0 (chassis-under-fins pairs ignored by configuration), fit pairs 3/3 pass, contacts 177
  * primary/control: **pass**, 10.83 mm (transformer pin to control-board ground zone) >= 5.5 mm
  * secondary/control: **pass**, 10.83 mm >= 3.0 mm
  * primary/secondary: **review** - 34.35 mm air between the HV plane and the transformer secondary; the transformer windings themselves are behind the 0.5 mm barrier (see above)
  * primary/pe, secondary/pe: **review** - 2.75 mm pad-edge path at the heat sinks (>= 2.0 mm); tab-to-screw pairs through the bushings listed for review
* warnings: 8 x "plastic body overhangs the plate edge (allowed)" for the heat-sink devices

## Renders

`renders/*.png` are headless matplotlib projections of the tessellated solids
(shaded isometric view plus top/front/side views with a painter's algorithm;
keep-out and envelope volumes drawn translucent). They are illustrative only.
