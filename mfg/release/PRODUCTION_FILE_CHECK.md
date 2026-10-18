# JLCPCB's production files for CostasLink-PYNQ-Z2 rev A, checked (2026-10-17)

JLCPCB's "Confirm Production file" step returned `CostasLink-PYNQ-Z2_gerbers_Y21.zip` (order
13544840A_Y21; the zip is kept beside this file but not in git, 17 MB).  It holds JLCPCB's CAM output
(`ok/`: `tl bl l2 l3` copper, `ts bs` solder mask, `to bo` silkscreen, `drl`, `ko` outline, `vcut`,
`sk` the tented vias, `qrt qrb` the QR-code places), the upload echoed back (`YG/`, byte-identical to
`CostasLink-PYNQ-Z2_gerbers.zip`) and the order record (`YG/4te.json`, GBK text).

Every one of their layers was rendered (gerbonara 1.5.0) over ours at 20 px/mm in the same frame and
diffed pixel by pixel; the 2 px (0.1 mm) edge slivers of polygon conversion were eroded away and what
remained was matched to pads with pcbnew.  **Verdict: nothing to change; confirm production.**

## What JLCPCB changed

| where | what | why it is fine |
|---|---|---|
| L2, L3 (inner) | 62 / 59 through-hole pads lost their inner-layer copper annulus: J302's 36 signal and unconnected pins (the GND and the two +5V_HDR pins keep theirs where they connect), every jumper pin (JP101-JP103, JP201-JP203, JP301-JP303), J303, and the signal pin of the U.FL jacks J106-J108, J208, J490, J501 | non-functional pad removal, JLCPCB's standard CAM step: a pad with no connection on that layer is copper for nothing; the drill registers more easily and the RF jacks' barrels see less capacitance.  Every pad that connects on an inner layer (SMA legs, GND and +5V header pins) is untouched |
| outside the outline | 5 mm assembly rails above and below the board (panel 120 x 110 mm), V-cut lines at y = 0 and y = 100 of the board, 1.5 mm corners on the rails, 2 mm tooling holes and 1 mm fiducials in the rails, the SMT QR-code places on the top rail (x 80.8-93 mm) | the rails are the ones ORDER_SETTINGS.md expects ("Added by JLCPCB", "Depanel ... Yes"); the five top-edge SMAs (J101, J202, J401, J402, J403, bodies 4.6 mm past the edge) are right-angle through-hole parts whose bodies sit on the board's top face, so they rest over the rail and the rail snaps downward and away; nothing hangs over the bottom edge; the left and right edges (J203, J301, J205-J207 over them) carry no rail, as the assembly remark asked.  The rail fiducial at x = 103 is 2 mm clear of J403's body |
| drills | plated holes drilled 0.13-0.15 mm over the finished size (0.92 to 1.05, 1.0 to 1.15, 1.1 to 1.25, 1.3 to 1.45, 1.6 to 1.75), non-plated 0.05 over (0.65 to 0.70, 3.2 to 3.25); the 1147 vias stay 0.25; J301's four 0.6 x 1.1 mm shield slots are drawn with a 0.553 mm tool | plating allowance and the usual via rule; the slots are routed with a smaller bit along the slot |
| order record | 4 layers, 1.6 mm, 1 oz outer / 0.5 oz inner, FR-4, green, white silk, ENIG, vias tented (过孔塞油), no order number ("不加客编"), SMT yes, overseas | matches ORDER_SETTINGS.md.  The record does not name the stack-up (its lamination list is empty, as for any order without impedance control); the order page is where JLC04161H-7628 shows |

## What is identical to the upload

Top and bottom copper (every pad, track and pour edge), both solder masks, both silkscreens (no order
number or anything else added on the board), the outline with its 2 mm corners and the M3 slot, every
hole position.  The silk inside the board is exactly the upload's, down to the back-side instruction
blocks.
