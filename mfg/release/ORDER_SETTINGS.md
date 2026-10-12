# CostasLink-PYNQ-Z2 rev A: JLCPCB order settings

Written by `mfg/make_release.py` on 2026-10-12.  On jlcpcb.com, **Order now**, upload `CostasLink-PYNQ-Z2_gerbers.zip`, then set the form top to bottom; the fields are in the form's own order (as of 2026-10-09, CLAUDE_PCB.md section 8).  **A row marked `>>` with its value in bold is NOT JLCPCB's default: change it, and do not leave the default named beside it.**  11 fields differ from the defaults.  Every dialog the form raises has its own row.

## The PCB

### PCB

| field | choose | JLCPCB's default | why |
|---|---|---|---|
| Base Material | FR-4 |  |  |
| >> Layers | **4** | 2 | L1 RF and signals, L2 unbroken ground, L3 the supply pours, L4 signals under a ground fill (PLAN.md section 7) |
| Dimensions | 120 x 100 mm |  | the board's outline, read from the board file's Edge.Cuts |
| PCB Qty | 5 | 5 | JLCPCB's minimum; 2 of them assembled, the rest bare spares |
| Product Type | Industrial/Consumer electronics | Industrial/Consumer electronics | the true one of the three (Aerospace, Medical): a research radio; duty is 35 % whatever is chosen |

### PCB Specifications

| field | choose | JLCPCB's default | why |
|---|---|---|---|
| Different Design | 1 | 1 |  |
| Delivery Format | Single PCB | Single PCB | no panel; JLCPCB adds and removes its own assembly rails (Depanel below) |
| PCB Thickness | 1.6mm | 1.6mm | the stack-up below is JLCPCB's 1.6 mm 4-layer stack; if a Reminder dialog says its real thickness differs, answer Yes: nothing clamps the board's edge (the SMAs are through-hole, the socket is on the face) and the RF lines depend on the outer prepreg only |
| PCB Color | Green | Green | green, not purple: Economic-compatible colour and the cheapest; the choice does not change the assembly (Standard is needed for the through-hole parts anyway) |
| Silkscreen | White | White |  |
| Material Type | FR4 TG135 | FR4 TG135 | the 4-layer default; the board runs cool (about 7 W over 108 cm2) and nothing here needs TG155 |
| >> Surface Finish | **ENIG** | OSP | not OSP: flat pads for the 0.5 mm QFNs with exposed pads, the reflow and the through-hole soldering after it (and the socket soldered at home), and the test pads probe well for years (CLAUDE_PCB.md section 8) |
| Gold Thickness | 1 U" | 1 U" | appears under ENIG; 2 U" is for gold fingers and wearing contacts, and the board has none |

### High-spec Options

| field | choose | JLCPCB's default | why |
|---|---|---|---|
| Outer Copper Weight | 1 oz | 1 oz | the stack-up's; sim/rf_lines.py's line widths assume 35 um |
| Inner Copper Weight | 0.5 oz | 0.5 oz | the stack-up's |
| Specify Layer Sequence | No | No | the Gerber names and the job file give the order |
| >> Specify Stackup | **Yes: JLC04161H-7628** | No | the 50 ohm lines (sim/rf_lines.py: 0.29 mm CPWG with 0.25 mm gaps over the L2 ground) are drawn for its 0.2104 mm of 7628 prepreg under L1.  It is JLCPCB's standard 4-layer 1.6 mm stack (no stack-up fee; 'No' builds the same), so choosing it only pins the prepreg.  If it is not offered, STOP and ask |
| Impedance Control | No requirement | No requirement | appears once a stack-up is chosen.  +-10% obliges an impedance table in the zip or the order waits on an engineering question; 'No requirement' still holds width and spacing to +-20% and the stack-up fixes the dielectric.  The RF lines are short against their edges (each a few mm to about 20 mm of 0.29 mm CPWG with 0.25 mm gaps, sim/rf_lines.py; a quarter wave at 5.8 GHz is 7.3 mm in this dielectric, and JLCPCB's own tool gives 0.345 mm for a 50 ohm microstrip on this stack), so a few ohms of mismatch costs a tenth of a dB |
| Via Covering | Tented | Tented | the default for 4 layers; the exposed pads' thermal vias (0.45/0.25 mm) wick a little solder, as intended; no via-in-pad |
| >> Min via hole size/diameter | **0.25mm/(0.35/0.4mm)** | 0.3mm/(0.4/0.45mm) | the board's smallest via is 0.45 mm across, 0.25 mm drill: the option that covers a 0.25 mm drill.  The page may fill this in from the drill file; check that it agrees.  It may add a small charge for 4 layers; the cart says |
| Board Outline Tolerance | +-0.2mm (Regular) | +-0.2mm (Regular) |  |
| >> Confirm Production file | **Yes** | No | about $1: JLCPCB's production Gerbers come back to check before they make it |
| Mark on PCB | Remove Mark | Remove Mark | no order number printed; JLCPCB has added none by default since May 2026 and asks that JLCJLCJLCJLC not be put on the silkscreen; this board carries none |
| Electrical Test | Flying Probe Fully Test | Flying Probe Fully Test |  |
| Gold Fingers | No | No |  |
| Castellated Holes | No | No |  |
| Press-Fit Hole | No | No |  |
| Edge Plating | No | No |  |
| Blind Slots | No | No |  |
| UL Marking | No | No |  |
| Backdrill | No | No |  |
| Humidity Indicator Card | No | No |  |

## PCB Assembly

### PCB Assembly

| field | choose | JLCPCB's default | why |
|---|---|---|---|
| >> PCB Assembly | **On** | Off |  |
| >> PCBA Type | **Standard** | Economic | the through-hole parts (the SMAs, the 2.54 mm headers) and the consigned ones: Economic takes neither |
| Assembly Side | Top Side | Top Side | every part on one side |
| >> PCBA Qty | **2** | 5 | of the 5 boards; the other 3 are bare spares |
| Edge Rails/Fiducials | Added by JLCPCB | Added by JLCPCB | the board carries no rails of its own; its 3 fiducials (1 mm copper in 2 mm mask openings, at (11.0, 11.0), (115.5, 15.0), (116.5, 87.5) mm from the top-left corner) sit inside the outline; JLCPCB adds two rails with its fiducials, and Depanel below takes them off.  Parts hang over the edge (J101, J202, J401, J402, J403 4.6 mm past the top edge; J203, J301 1.7/4.6 mm past the right edge; J205, J206, J207 4.6 mm past the left edge): the Assembly remark below says so |
| >> Confirm Parts Placement | **Yes** | No | free: the placement preview, read against PLACEMENT_CHECKS.txt (33 part numbers have predicted, unseen rotations) |
| Stencil Storage | No | No |  |
| Fixture Storage | No | No |  |
| Parts Selection | By Customer (Self-Service) | By Customer (Self-Service) | the BOM carries every LCSC code; the 3 consigned lines are matched to the consigned stock registered beforehand (CONSIGNMENT.md) |

### Advanced Options

| field | choose | JLCPCB's default | why |
|---|---|---|---|
| Bake Components | No | No | the QFNs are MSL 3 and JLCPCB's parts come from its own dry storage; about $7.50 if ticked |
| Photo Confirmation | No | No |  |
| Board Cleaning | No | No |  |
| Conformal Coating | No | No |  |
| Special stencil | No | No |  |
| Packaging | Antistatic bubble film | Antistatic bubble film | the default |
| >> Depanel boards & edge rail before delivery | **Yes** | No | about $2.32: the boards come without JLCPCB's rails; the board plugs onto the PYNQ-Z2 and the SMAs hang over its top edge, so its edges must be clean |
| Solder Paste | High temp. | High temp. | the default, lead-free |
| Flying Probe Test | No | No | the bare boards are already flying-probe tested |
| Nitrogen reflow soldering | No | No | air reflow with SAC paste on ENIG wets 0.5 mm QFNs |
| Function test | No | No |  |
| >> Assembly remark | **"Parts hang over the board's edge: J101, J202, J401, J402, J403 4.6 mm past the top edge; J203, J301 1.7/4.6 mm past the right edge; J205, J206, J207 4.6 mm past the left edge.  Put the assembly rails on the other edges or leave a gap for them."** | No | the parts over the edge (PLACEMENT_CHECKS.txt) |

### Stencil

| field | choose | JLCPCB's default | why |
|---|---|---|---|
| Stencil | Off | Off | the assembly makes its own |

### Files

| field | choose | JLCPCB's default | why |
|---|---|---|---|
| BOM | BOM_JLCPCB.csv |  | one line per LCSC code; the Note column flags the consigned lines |
| CPL | CostasLink-PYNQ-Z2_cpl_jlcpcb_upload.csv |  | not CostasLink-PYNQ-Z2_cpl_kicad_native.csv, which is KiCad's own numbers for reference |

Then upload `BOM_JLCPCB.csv` and `CostasLink-PYNQ-Z2_cpl_jlcpcb_upload.csv` (not `CostasLink-PYNQ-Z2_cpl_kicad_native.csv`).  Every BOM line carries its LCSC code; the 3 consigned lines (Note column) must match the consigned stock registered beforehand (CONSIGNMENT.md), the rest JLCPCB's shelf stock; nothing should be left unmatched.  In the placement preview, go through `PLACEMENT_CHECKS.txt` before confirming.

**Shipping:** UPS Express Saver (DDP): a US individual must ship DDP, and JLCPCB collects the duty (35 % of the PCBs and assembly).  Lead time: 4-layer PCBs 2-5 days, Standard assembly at least 4 more (+1 for the through-hole parts), the consignment's post before that, then 4-5 business days to the door.

## Numbers behind the choices

- Board 120.0 x 100.0 mm, 4 copper layers, 1.6 mm; smallest track 0.150 mm; 1088 vias, all 0.45/0.25 mm.
- Assembly: 381 placements a board on 79 BOM lines (48 Extended, 3 consigned), 1094 SMD pads and 93 through-hole joints a board, on top.
- Mounting holes: H301 3.2 mm at (5.0, 5.0), H302 3.2 mm at (115.0, 5.0), H303 3.2 mm at (115.0, 94.0), H304 3.2 mm at (61.3, 93.3).
- Estimate: $597.02 of goods before duty and shipping, JLCPCB $830.98-$845.98 all in, Digi-Key $149.96 (COST_ESTIMATE.md).
- Checks passed: DRC 0 violations, 0 unconnected, 0 parity; the connectors' labels 38 connectors, 22 rows, 0 violations; 2 limit(s) left off on record; 213 filled zone polygons; every netlist part on the board; every code matched (gen/parts.py's words, the value, the package, the MPN) and in stock; no ordered part wants a hole; every part of three or more pads has a read or predicted rotation; the CPL agrees with KiCad's position export, and JLCPCB's drawings placed by it land on our pads (54 parts, top side).

Sources: the ECP5-2ADC-2DAC order of 2026-10-09 (the form's fields and defaults, its cart's fees), jlcpcb.com/help/article/pcb-assembly-price, /capabilities/pcb-assembly-capabilities, /help/article/How-to-mark-on-PCB (2026-05-22), /help/article/us-tariff-policy-faq (2026-09-09).  The form changes; when a screenshot shows it has, update the lists in mfg/make_release.py and this date.
