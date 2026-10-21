# Parameters and derived rules

All lengths are metres, masses kilograms. The authoritative definitions are the
JSON Schemas in `src/aipe_cad/schemas/` (`aipe-cad schema <kind>`) and the
resolvers in `src/aipe_cad/params/`. This page summarises the main inputs and
the rules that turn them into geometry so that an optimiser knows which knobs
exist and which constraints it must respect.

Materials: `aipe-cad materials` lists the density table (`aipe_cad/materials.py`);
every body may override its density. Conductive materials (metals) take part in
clearance checks when a `net` is assigned; polymers/ceramics/ferrite are
insulators; fluids (coolant) are neither.

## Transformer (`kind: transformer`)

Local frame: centre-leg axis = Z, mating plane of the two E halves at z = 0,
core width along X, depth along Y (windows open towards +/-Y).

| group | parameters | derived rule |
| --- | --- | --- |
| `core` | `total_width` A, `half_height` B, `depth` F, `window_height` D, `inner_width` C, `centre_leg_width` E, `air_gap`, `material`, `net`, `reference` | window width `(C-E)/2`, outer-leg width `(A-C)/2`, yoke `B-D`, half volume `A*F*B - 2*w*F*D - E*F*gap/2`; the air gap is split between the halves at the centre leg |
| `bobbin` | `wall_thickness`, `flange_thickness`, `core_clearance`, `window_clearance`, `pin_strip_width`, `corner_radius`, `material`, `tube_wrap` | tube inner = leg + 2*core_clearance; tube height = 2D - 2*window_clearance; winding width = tube height - 2*flange; max radial build = (C - 2*window_clearance)/2 - tube outer/2; flange Y extent = tube outer + 2*(max build + pin strip) |
| `windings[]` | `turns`, `conductor` (`litz`/`round`: `outer_diameter`, `strand_count`, `strand_diameter`; `foil`: `foil_thickness`, `foil_width`), `insulation_thickness`, `fill_factor`, `margin`, `parallel`, `net`, `terminal_count`, `terminal_side` | litz/round: turns per layer `floor(width_avail / OD)`, layers `ceil(turns*parallel / tpl)`, thickness `layers*OD + (layers-1)*ins`; foil: thickness `turns*(t_foil + ins)`; mean length of turn from the rounded-rectangle perimeter at mid build; copper mass and 20 degC DC resistance; homogenised density `ff*rho_cu + (1-ff)*rho_ins` |
| `insulation` | `inter_winding_barrier`, `outer_wrap`, `fill_margins`, `material` | barriers span the full winding width between successive windings, wrap outside the last; margin blocks fill the ends of each winding |
| `terminals` | `diameter`, `length`, `pitch`, `flange`, `direction`, `material` | pins on the flange overhang at `y = +/-(tube_outer_y/2 + max build + pin_strip/2)`; direction must point away from the bobbin |
| `mounting` | clips: `clip_thickness`, `clip_width`, `clip_inset`; base plate: `plate_thickness`, `plate_margin_x`, `hole_diameter`, `hole_inset` | rectangular clip rings around the core at `y = +/-(F/2 - inset - width/2)`; plate under the clips with four holes outside the core footprint |
| `clearance_envelope_margin` | | bounding box of the structural bodies (pins excluded) expanded by the margin, exported as a keep-out body |
| `checks` | `interference`, `clearance_pairs[]` (`net_a`, `net_b`, `required_clearance`, `required_creepage`), `fit_pairs[]` | fit pairs bobbin/core and outer wrap/core are added automatically |

Hard constraints (errors): total radial build <= max build; conductor fits the
available width; margins leave positive width; pins clear the core and the
base plate; clips fit on the core depth; base-plate holes outside the core.

## Heat sink (`kind: heatsink`)

Local frame: base underside (fin roots) at z = 0, base `0..thickness`, fins at
z < 0, devices on the top face. Fins run along X and are spaced along Y.

| group | parameters | derived rule |
| --- | --- | --- |
| `base` | `length`, `width`, `thickness`, `material` | |
| `fins` | `thickness` t, `height`, `pitch` p, optional `count`, optional `length` | `count = floor((W - t)/p) + 1` unless given (must fit); fins centred across the width; fin length defaults to the base length (shorter fins leave rims for chassis mounting) |
| `devices[]` | `name`, `package` (library key `to247_4l`/`to247_3` or inline overrides), `position`, `rotation_deg`, `net`, `lead_nets`, `pad` (`thickness`, `oversize`, `material`), `screw_hole_diameter`, `lead_form` (`horizontal`, `vertical`), `fastener` (`screw`, `screw_diameter`, `head_diameter`, `head_height`, `bushing`, `shoulder_diameter`, `shoulder_thickness`, materials) | body on pad on plate; exposed tab region flush with the hole end; pad = tab footprint + oversize (must stay on the plate, the plastic body may overhang); L-shaped leads (horizontal + vertical <= lead length); bushing sleeve fills the package and pad holes, shoulder on the body top, screw head on the shoulder, shank into the plate hole (engaged part at the hole diameter) |
| `mounting_holes` | `diameter`, `inset` | four corner holes; collisions with devices are errors, intersections with fins warnings |
| `checks` | as above | |

Analytic outputs: base and fin volumes, hole volumes, convective area
`L*W - n*l*t + 2*n*h*l + n*t*l + 2*n*t*h`, envelope box.

## Cold plate (`kind: coldplate`)

Local frame: channel face (plate underside) at z = 0, plate `0..thickness`,
cover `-cover..0`, devices on top. Passes run along X.

| group | parameters | derived rule |
| --- | --- | --- |
| `plate` | `length`, `width`, `thickness`, `material` | |
| `channel` | `width`, `depth`, `passes`, optional `pitch`, `edge_margin`, `end_margin`, `min_wall` | pitch defaults to spread the passes evenly inside the edge margins; pass centres `y_k = -(n-1)p/2 + k p`; 180-degree turns alternate +X/-X with outer radius `p/2 + w/2`, inner `p/2 - w/2`; even pass count puts inlet and outlet on the -X face |
| `cover`, `ports` | `thickness`; `outer_diameter`, `bore`, `length` | boss radius must fit on the end face (`<= depth/2 + cover`, `<= thickness - depth/2`); bores connect the channel ends to the faces |
| `devices[]`, `screw_hole_depth`, `mounting_holes` | as for the heat sink | blind screw holes may not break into the channel (`depth <= thickness - channel depth - min_wall` over the channel); mounting holes keep `min_wall` from the channel and bores |

Analytic outputs: channel, bore and coolant volumes/mass, plate and cover
volumes, boss volume; the `coolant` body is exported as a fluid domain.

## Assembly (`kind: assembly`)

Common frame: origin at the chassis top-face centre, X long axis, Z up.

| group | parameters | derived rule |
| --- | --- | --- |
| `chassis` | `length`, `width`, `thickness`, `cutouts_under_heatsinks`, `cutout_clearance`, `min_rim` | cut-out = fin footprint + clearance under each heat sink (base rim >= `min_rim` required, mounting holes must land on the rim); holes for heat-sink/cold-plate/transformer mounting and chassis-supported standoffs |
| `cooling` | `variant` (`heatsinks`/`coldplate`/`none`), component parameters (`$ref`), `placements[]` (`position`, `rotation_deg`, `device_net`, `params` overrides) | heat sinks rest on the chassis (fins down), the cold plate rests on its cover (`z: "on_chassis"`); device leads are collected for board holes |
| `transformer` | `params`, `position` (`z: "on_chassis"` supported), `rotation_deg` | lowest point placed on the chassis |
| `boards[]` | `size`, `thickness`, `position` (bottom face z), `copper_zones[]` (`net`, `thickness`, `side`), `keepouts[]`, `mounting_holes`, `standoffs`, `lead_holes` | standoffs from the chassis or a cooling component top to the board bottom; clearance holes for device leads that pass through the board (warnings when leads end inside or below); copper zones keep back from holes, standoffs and connector footprints |
| `connectors[]` | `type` (`dc_terminal_block`), `position` (`z: "on_board:<name>"`), `body_size`, `poles`, `pole_pitch`, `pin_diameter`, `pin_length`, `net` | housing on the board with pins through it |
| `checks` | `interference` (`allowed_overlaps`), `keepouts`, `envelopes` (`ignore_pairs`), `clearance_pairs`, `fit_pairs` | component fit pairs are prefixed with the instance name |

Mass estimate: component analytic masses plus boards, standoffs, connectors
and chassis (`analytic_masses.total_estimate`).
