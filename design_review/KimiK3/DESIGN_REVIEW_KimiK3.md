# Design review: CostasLink-PYNQ-Z2 rev A (build 2026-10-10 20:01) — KimiK3

## Verdict

**Order it, after two free fixes: reroute the LO pairs and change one resistor.** The schematic,
the power tree, the decision paths and the gateware survived a line-by-line pass against the
datasheets; the board-level checks the author claims (DRC 0 / ERC 0 / net check 0 / label check 0)
reproduce. Two findings rise above "would cost a day", and both are free before the order:

1. **The LO pairs** (finding 1). Both differential LO pairs (RX synthesizer → demodulator, TX
   synthesizer → modulator) are routed with one leg ~10 mm and the other ~44-46 mm, the long leg
   looping around the synthesizer/VCXO region at 0.2 mm width. The plan (PLAN.md §10.4) claims
   "matched lengths"; the copper contradicts it. The skew is ~200 ps, over one full cycle at
   5.8 GHz, i.e. ~50-70° of differential phase error plus a large common-mode component at the
   mixer LO ports, on the same nodes whose millivolt offsets the design otherwise fights with four
   DAC trims. I do not expect it to kill the board (the sign-decision schemes are robust to it, the
   LO level has 3 dB programmable steps and a −6..+6 dBm window at the mixers), but it undermines
   the weak-pilot experiments (settled-state decode tolerance is 1.8°) that sheet 7 was added for,
   it is invisible to every monitor tap (the LO MONs are at the synthesizer end), and it is free
   to fix now and expensive later.
2. **The loop resistor** (finding 2 — found by GPT-5.6Terra, verified here). The Costas error
   switch selects one leg of the differential Q pair, so Kd = 0.124 V/rad, half the budget's
   0.249; the fitted loop runs at fn ≈ 2.1 kHz, ζ ≈ 0.49 instead of the designed 3 kHz / 0.71.
   R126: 20k → 10k restores the design point. One 0402.

Worth the same pre-order editing pass: the netclass patterns that silently shrank the CPWG pour
gap to 0.20 mm (finding 8), the short paddle-via grids (finding 9), and the documentation fixes
(findings 13, 14, 17). If the author reroutes the two LO pairs short and symmetric, changes R126,
and fixes the netclass patterns (or demonstrates from the datasheets that any of the three is
harmless), nothing else I found blocks the order.

## Findings table (ranked by cost of being wrong)

| # | Severity | Finding | Where | Evidence | Confirmed by | Fix |
|---|----------|---------|-------|----------|--------------|-----|
| 1 | would cost a respin (probably works; kills the precision experiments) | LO differential pairs routed 10 mm vs 44-46 mm per leg, ~50-70° skew at 5.8 GHz, long leg not 50 Ω | board: RX LO N net loops through board rect (20.7-29.2, 62.0-80.3); `Net-(U104-LOIN)` 16 segs 41.95 mm vs `Net-(U104-LOIP)` 2.06 mm; TX same (`Net-(U201-LOIN)` 43.53 mm) | segment dump of the shipped `.kicad_pcb` (rf_copper.txt); PLAN.md §10.4 claims "matched lengths"; λ at 5.8 GHz in this stack = 29.3 mm/1.77 (sim/rf_lines.py) | my parse of `hardware/CostasLink-PYNQ-Z2.kicad_pcb`, all F.Cu segments of the four LO nets | reroute both pairs short, direct and symmetric before ordering; else quantify LO imbalance at the demodulator pads in bring-up (no tap exists there today) |
| 2 | would cost a respin of the loop's designed behaviour (it still locks, but at the wrong bandwidth and damping; every §18 pull-in/hold number shifts with it) | the Costas loop's Kd is half the budgeted value: the error switch (U110, LVC1G3157) selects ONE leg of the differential Q pair through JP101/JP102, so the error amplitude is the single-ended peak — Kd = 0.124 V/rad, not the differential 0.249 the budget used; with R1 (R126) fitted at 20k the loop runs fn ≈ 2.06 kHz, ζ ≈ 0.49 instead of the designed 3.0 kHz / 0.71 | `sim/budget.py:341-342` (Kd = vcmp_rms×1.414 = the differential peak) vs `gen/sch_rx.py` (U110's B1/B2 take one leg each); budget.json loop_R1 18.9k → fitted 20k (parts.RES has no 18k); R126 sits between U111 and U112 on the board | my recompute wn = √(Kd·Ko/(R1·C)): fn 2062 Hz, ζ 0.49 at the true Kd | found by GPT-5.6Terra, independently by Grok4.7; verified here from the shipped values (my first pass rubber-stamped the budget's Kd) | R126 20k → 10k (fn 2.9 kHz, ζ 0.69 at the true Kd): one 0402 before the order; re-check the §18 pull-in/hold table against Kd/2 |
| 3 | would cost a day (confusing measurements; the instrument changes the decision) | I SLOW MON / Q SLOW MON taps sit behind the 1 kΩ pole resistor, on the comparator input node — the exact pattern CLAUDE_PCB.md §9 forbids | sheet 6, `gen/sch_slow.py`: `B.arm(..., out_rc=(1k, 33pF))` then `B.tap(...)` on the post-RC node with the default 1 kΩ tap resistor | a 50 Ω scope input moves the pole 4.8 → 9.4 MHz (1k ∥ 1050) and drags the node DC from 1.65 V to 0.85 V while Is_N/Qs_N stay at 1.65 — the sign comparator (U503) and the Q window read wrong while watched | read of `gen/sch_slow.py` + `gen/sch_blocks.py` (tap default `rkey="R 1k"`), arithmetic | document "10× (1 MΩ) probe only" on the sheet and in BRINGUP; rev B: buffer or move the tap |
| 4 | would cost a day (a gate the author claims green is red) | `make lint` fails out of the box: Verilator 5.051 reports 2 warnings-as-errors (SIMILARNAME `uart_cmd.v:48`, MULTIDRIVENPROC `rx_engine.v:114` — loop variable `i` shared by two always blocks) | `gateware/uart_cmd.v:48`, `gateware/rx_engine.v:99,114` | ran `make lint sim sim-engines sim-axil sim-driver` in my copy: lint red, all sims green (tb_costaslink, tb_engines, tb_axil, 15 driver tests OK) | ran it (repo copy in this directory) | rename `rep_hex`; give each always block its own loop variable |
| 5 | would cost a day (reliability, out-of-spec but usually survivable) | board powered (USB-C) with the PYNQ off or unconfigured: the comparators drive 3.3 V through 33+200 Ω into the Zynq's clamp diodes, ~11.6 mA/pin; the four window comparators rest HIGH at power-up (AD5696R midscale 1.25 V < arms' 1.65 V), so this happens before any software runs | sheets 3/7 outputs to header pins 8,10,16,18,22,28,32,40; Xilinx 7-series injection guidance ±10 mA/pin | (3.3−0.6) V / 233 Ω = 11.6 mA; up to ~8 pins ≈ 90 mA into the PYNQ's 3V3 rail (phantom power) | datasheet thresholds + schematic topology; AD5696R datasheet (RSTSEL high → midscale; `design_review_KimiK3/ad5696r.txt` p.8 Table 6) | document "power the host before/with the board"; rev B: larger series R or a bus switch on the comparator lines |
| 6 | would cost a board (low probability, no respin) | input surge protection is ceramic-only: 2×22 µF MLCC + SMAJ5.0A (Vc 9.2 V) upstream of the ADL5380/ADL5375/ADL5611 whose abs max supply is 5.5 V; CLAUDE_PCB.md §15 wants a damped bulk electrolytic/polymer | sheet 5, J301→F301→Q301→+5V_IN; `build/txt/ADL5380.txt` Table 2 (5.5 V) | hot-plug tank: cable ~0.3 µH + 22 µF MLCC; the PTC+FET's ~110 mΩ damps to Q≈0.5-1, so the overshoot is ~5.5-6.5 V for µs — at or above the RF chips' 5.5 V abs max, below the TVS's effective clamp | datasheet abs-max numbers; AN88 tank arithmetic | rev B: 100 µF polymer on +5V_IN. Rev A: power the bank/supply before inserting the board's cable |
| 7 | would cost a day (a rare unit will not lock until someone writes the code) | "the FPGA re-centres the RX synthesizer (1 Hz steps)" is not implemented: `gateware/max2871_regs.py` asserts integer-N (25 MHz steps), which the ±580 kHz loop can never follow; and the VCXO's *guaranteed* pull (APR) is only ±50 ppm = ±290 kHz at 5.8 GHz against a worst-case needed pull of ~305 kHz (VCXO tolerance ±50 ppm + TX TCXO ±2.5 ppm) | PLAN.md §1, §3 table, BRINGUP stage 4.1 vs `max2871_regs.py:44` (`assert` on multiples of 25 MHz); `build/txt/SX3V25.000B20100F30TNN_C5179998.txt` lines 96-100 (pull ±100 ppm min, **APR ±50 ppm min**) | datasheet APR vs worst-case arithmetic; the driver's `pll_tune` steps whole channels | read both | add fractional-N re-centre to the driver (write words with the loop open, re-acquire); fix the PLAN/BRINGUP text to say 25 MHz steps |
| 8 | electrically minor (VSWR 1.05), but a silent design-rule break | the RF/LO netclass patterns in gen/project.py match zero nets (`/^RF_/` and `/^LO_/` against the real names `Net-(U101-RF_IN)`, `/Receiver and Costas loop/LO_RX_P`, …), so the RF class's 0.25 mm clearance binds to nothing and the GND pour's own 0.2 mm clearance sets the CPWG gap: the shipped gap is 0.20 mm and Z0 ≈ 47.7 Ω, not the designed 0.25 mm / 49.8 Ω (the track width is set explicitly by the router, so only the pour clearance fell through) | `gen/project.py` PATTERNS vs the shipped pcb's net names; the GND zone's clearance field | my net-name dump of the shipped `.kicad_pcb` + zone clearance measured 0.2 mm; Z0 from the geometry | found by Gemini3.8Flash, confirmed by Grok4.7; verified here | fix the patterns so the RF/LO classes bind and refill the zones; the gap moves 0.20 → 0.25 mm and Z0 to design |
| 9 | would cost thermal and ground-inductance margin at the two hottest chips; datasheet-asked, not fatal | exposed-pad via grids fall short on 6 of 9 paddled parts: U104/U201 (ADL5380/ADL5375) have 4 paddle vias where the datasheets draw 9 (3×3); U101 (SKY65404) has none under the paddle (nearest 1.1 mm) though its datasheet's land pattern shows them; the ADL5611 SOT-89 tabs have none (nearest ~1.35 mm); the two MAX2871 paddles have 9-10 | the shipped `.kicad_pcb` (via-under-pad query); PLAN.md §16 claims "a via grid in every paddle" — false for the demodulator, modulator, LNA and gain blocks | my pcbnew script's counts: U104/U201 = 4, U101 = 0, ADL5611 tabs = 0, MAX2871s = 9-10 | found by Grok4.7; verified here | add the vias to the four footprints and refill; free before the order |
| 10 | rule violation, low practical risk | no fiducials and no copper layer markers anywhere on the board; CLAUDE_PCB.md §10 gate 15 and §5 ("three board fiducials… layer numbers in copper on every copper layer") require them; `Fiducial_1mm_Mask2mm.kicad_mod` sits unused in the project library | the shipped `.kicad_pcb`: zero Fiducial footprints, zero copper text/graphics on In1/In2 | `grep` of the board file; ORDER_SETTINGS.md says fiducials are "Added by JLCPCB" (their rails) — fine for JLCPCB, against the rulebook | grep of the pcb | either place 3 fiducials + layer markers, or record the deviation in CLAUDE_PCB.md terms |
| 11 | would cost an hour of bench confusion (the trim range absorbs it) | the TX baseband N-side bias divider (5.1k/1k from +3V3_ANA → 0.541 V nominal, 836 Ω Thévenin) is lifted by the ADL5375's 41 µA/pin baseband bias current × 2 pins (IBBN, QBBN): +68.5 mV → VN_0V5 ≈ 0.610 V; the P sides sit on ~240 Ω ladder networks (+9.8 mV), so every code carries ~59 mV of differential offset and the printed carrier-null point moves | `gen/sch_tx.py` (the divider) + ADL5375 Table 1 (41 µA sourcing) | my arithmetic (0.541 + 0.082×0.836 = 0.610 V) | found by Gemini3.8Flash, confirmed by Grok4.7; my §3.6 verified the P-side 9.8 mV lift and missed the N-side network | nothing electrical — VR_I/VR_Q re-null it with range to spare; write the real null point in BRINGUP; rev B: lower the divider impedance or buffer it |
| 12 | would cost an hour (doc gap, first bench day) | TRIG IN's 50 Ω termination (JP202) sits at the jack, before the 1 kΩ into the Schmitt: a 50 Ω pulse source set to 3.3 V delivers 1.65 V — below the 74LVC1G17's VT+ max (2.19 V @ 3.3 V). BRINGUP stages 0.5/4.7 don't say to raise the amplitude | sheet 4, JP202/R(49.9)/1k/U205; TI SN74LVC1G17 thresholds | 50 Ω source into 50 Ω terminator halves the amplitude; 1.65 V < 2.19 V | `gen/sch_tx.py` topology + datasheet thresholds | document "≥ 4 V amplitude with JP202 fitted" (or move the terminator after a series R); not a board change |
| 13 | documentation / worst-case margin | the ADL5380's output common mode contradicts itself inside its own datasheet: Table 1 (ADJ open) says VS−1.2 = 3.8 V typ; Table 4 (the RADJ guide) says ~3.2 V for the same condition. The budget takes 3.8 V (the deliberate conservative choice, per the author's earlier review), so the sheet's blue box prints 3.8 V while the note beside the chip prints 3.2 V, and PLAN.md §10.3's summing-node number (1.73 V) is stale for the fitted Rs = 1k (actual 1.61 V at 3.2 V CM, 1.87 V at 3.8 V CM). The honest worst case: if CM tracks VS−1.2 at VS = 5.25 V, the node is 1.98 V against the THS4541's *guaranteed* input limit (Vs+)−1.3 = 2.00 V — 17 mV of margin (130 mV at the 5.0 V corner) | `build/txt/ADL5380.txt` Table 1 vs Table 4; `sim/budget.py` dem_out_cm_V = 3.8; THS4541 3 V table (the CM-high limit is a guaranteed minimum over temperature, 2.1 V is only the 25 °C typ) | both tables read; node arithmetic redone (1.61 V / 1.87 V / 1.98 V) | the author's Claude review documents the 3.8 V choice and the Rs 1.2k→1k fix (fitted in this build); margins recomputed here | first power: needle on the 1k shunt — if the THS4541 input pins exceed ~1.95 V, fit the DNP 1.5k on ADJ; make the sheet print one number; refresh PLAN.md §10.3 |
| 14 | cosmetic (an assertion that cannot fail; a wrong sheet note) | the TX gain-block compression check uses the wrong datasheet row: `sim/budget.py` asserts against gb_p1db_dBm = 16.0 (the ADL5611's 5 GHz value); the 5.8 GHz row is 12.8 dBm — PLAN.md §18 uses 12.8, but the TX sheet note prints "P1dB about +16 dBm" and the assertion would still pass if the chain exceeded the real 12.8 | `sim/budget.py` parts table vs `build/txt/ADL5611.txt` 5.8 GHz row (gain 14.3, P1dB 12.8) | datasheet read of the 5.8 GHz row | found by Grok4.7; verified here | change the parts entry to 12.8 and regenerate; fix the sheet note |
| 15 | cosmetic / expectation setting | order placed with Impedance Control "No requirement" on a 5.8 GHz board: JLCPCB holds width/spacing to ±20 %, so the 0.29/0.25 mm CPWG lands anywhere in ~45-55 Ω and the drawn −20 dB couplers' coupling moves a few dB; the lines are short and the taps are calibrated, so the cost is small — but it is a choice, not a fact | `mfg/release/ORDER_SETTINGS.md` (argued there); `sim/rf_lines.py` geometry | coupler geometry read off the footprint (`Coupler_20dB_5.8GHz_CPWG`: 7.30 mm, 0.29 mm, 0.25 mm gap) | footprint + order settings | accept (I would), or pay for ±10 % control on this RF board |
| 16 | cosmetic | monitor lines off the couplers are 0.2 mm (~57-60 Ω), 10-13 mm long, not the 0.29 mm CPWG used elsewhere; harmless for −20 dB measurement taps but undocumented | `Net-(CP101-CPL)` 12.89 mm, `Net-(CP201-CPL)` 10.20 mm, both 0.2 mm | segment dump | — | note it, or widen in the same reroute as #1 |
| 17 | cosmetic | doc drift: PLAN.md §17 "68 BOM lines" vs the release's 71; "382 parts" = 349 placed + 33 DNP/TP/holes (reconciles, but say so); QUESTIONS.md item 1 is stale (superseded by the second ADL5611); PLAN.md §10.4 "LO pairs, matched lengths" (see #1); `hardware/checks/` shipped root sheet is a KiCad-10 re-save of the generator's output (content identical — verified) | PLAN.md, QUESTIONS.md, README.md | regenerated all seven sheets in my copy: six byte-identical, root semantically identical (formatting) | ran `gen/schematic.py` in my copy and diffed | one editing pass |

## §3 answers, item by item

**1. The concept.** The architecture is right for the experiment, and the alternatives are
correctly rejected with numbers (PLAN.md §13): OOK has nothing to track while idle and is 14 dB
deafer; an ADC + matched filter adds pipeline latency the experiment is trying not to measure;
an off-the-shelf modem decides nothing in 10 ns. The always-on carrier is what lets a bit be a
*departure* seen in one arm-rise (0.8-3 ns into it, §18). The honest weak points: the analog
Costas loop is a single point of failure (mitigated: plain-PLL mode on Q via JP103, FSK needs no
lock, VC_OFF sweep, and every loop node is on a monitor jack or the ADC), and the PYNQ's 200 Ω
header resistors cost 8.8 ns of the 22.7 ns — but the same board fits the Icepi Zero (13.9 ns),
so rev A measures both and rev B's ECP5 decision is informed, not guessed. I would order the same
architecture. On "real multipath, real phase noise": the arm filter's 100 MHz integrates
multipath over 10 ns, so a 20 ns-delayed reflection at −20 dB perturbs the crossing by ~0.2 ns —
visible in the jitter histogram, not fatal; the loop's static phase error is the pilot-schemes'
problem and sheet 7 exists to measure it.

**2. 5.8 GHz on this layout.** I parsed the shipped copper, not the code that drew it.
- The main lines are as claimed: 0.29 mm tracks with 0.2/0.25 mm pad necks on all five RF paths
  (rf_copper.txt), L2 (In1.Cu) has **zero** tracks and one GND zone — unbroken as claimed.
- Via fences: no point on any RF path segment is farther than 2.54 mm from a ground via
  (λ/10 in the dielectric is 2.5 mm); typical spacing 1.2-1.8 mm. The wide spots are at pad
  entries where the chip's own ground vias serve. Acceptable.
- The couplers are a footprint: two 7.30 mm × 0.29 mm lines, 0.25 mm gap, net-tie pads, fp_line
  copper — matches the description; the physics (−20 dB from a λ/4 section at these gaps) is in
  the right class, and a wrong coupling coefficient is calibrated out on TX MON/RX MON.
- The SMA launches have ground voids under the centre pads (looked at the F.Cu plot), fence vias
  beside them.
- The balun: I rendered the Johanson datasheet's terminal figure and compared it with
  `Balun_Johanson_5400BL15B050.kicad_mod`: pad numbering and positions agree (1 unbalanced,
  2/5 GND, 3/4 balanced, 6 NC), and the schematic uses them consistently (2/5 GND, 6 NC, 3/4 to
  RFIP/RFIN — which leg is which only flips absolute phase, which the loop absorbs). The
  datasheet's recommended land adds φ0.3 through-holes (ground stitching) that the footprint
  omits — minor; and "mount with the brown mark facing up" belongs in the consignment note.
- Isolation own-TX/own-RX: unanswerable without the board; the plan's own table says 42 dB is
  needed at 600 MHz spacing and two whips give ~20 — hence the 1 m TX-whip lead in BRINGUP stage
  4 and the switch block. I flag one number: with the 2 W PA at +30 dBm *through* the HMC536,
  the switch is 1 dB past its +29 dBm P0.1dB; keep PA-through-switch operation at +27 dBm or put
  the PA after the switch.
- The LO pairs: **finding 1.** Also note both LO lines are 0.2 mm (~57-60 Ω CPWG), not 50 Ω.
- The ADL5611's own s2p (in its datasheet text) shows S11 = −4.8 dB at 5.8 GHz: the
  DSA→GB1→GB2→balun cascade will have a few dB of unbudgeted mismatch ripple. The DSA and the
  RX MON tap make this a calibration, not a failure — but the budget's 38.6 dB chain gain should
  be read as ±2 dB.

**3. The Costas loop.** I redid the arithmetic from the datasheet numbers, and my first pass got
the most important constant **wrong** — corrected after reconciliation (finding 2): Ko = 2.7e6
rad/s/V (±100 ppm over 2.7 V × 232) ✓, but Kd is 0.124 V/rad, not the budget's 0.249, because the
error switch (U110) selects ONE leg of the differential Q pair and the budget used the
differential peak. R1 is fitted at 20k (parts.RES has no 18k, so the computed 18.9k lands on 20k), so
the loop as shipped runs fn ≈ 2.06 kHz, ζ ≈ 0.49 — not the designed 3.0 kHz / 0.71. With R126
changed to 10k: fn = 2.9 kHz, ζ = 0.69 at the true Kd ✓. The pull-in and hold tables in PLAN.md
§18 scale with Kd (roughly ×2 in pull-in time) and should be re-run with the fix. The sign-jumper
logic (JP101/JP102 opposite, default ERR = sign(I)·Q) matches the 3157's S-low→B1 truth table ✓.
The Response-14 hold switch (NC = error, NO = V_MID) is wired per the TS5A3159's pinout (COM = pin
4 to the integrator's R1) and the leakage story checks out (0.2 nA typ / 20 nA max over temp → the
0.6-6 ms hold table in PLAN.md §18) ✓. The VCXO: pull ±100 ppm min ✓, 15 kHz modulation bandwidth
vs the 3 kHz loop ✓, 5 MΩ control input ✓ — but see finding 7 (APR ±50 ppm guaranteed, and the
1 Hz re-centre does not exist). First-power lock: plausible in ~0.4 s worst case with the sweep as
backstop; BRINGUP stage 3's "move both jumpers if it runs away" is the right instruction. The
180° ambiguity is handled as designed (a transition is the bit; the idle level is learned).

**4. The fast decision path.** All four sub-items check out, with one correction:
- Common-mode shift: the ADL5380's datasheet **contradicts itself** — Table 1 says ADJ open gives
  VS−1.2 = 3.8 V typ; Table 4's RADJ guide says ~3.2 V for the same condition (finding 13). The
  budget deliberately uses the conservative 3.8 V. Summing nodes land at 1.87 V (3.8 V CM) or
  1.61 V (3.2 V CM) with the fitted 1k/4k/1k network; the THS4541's input limit is Vs−1.3 =
  **2.0 V worst case over temperature** (2.1 V is only the 25 °C typical — PLAN.md's "0.37 V of
  margin" quotes the typical). So the guaranteed margin is 0.13 V at the 5.0 V corner and **17 mV**
  at the 5.25 V corner if CM tracks VS−1.2 — thin, and the DNP 1.5k on ADJ is the documented cure.
  If Table 4 is the truth, margin is a comfortable 0.39 V. First-power measurement decides.
- Current pulled from each demodulator pin: 1.9 mA at the conservative 3.8 V CM (the budget's
  1.93 mA ✓), 1.6 mA at 3.2 V. The output stage is characterized swinging 2 Vpp differential into
  200 Ω (±5 mA), and its peak output current is 12 mA/pin — fine either way.
- Thresholds/offsets/hysteresis: TLV3601 ±5 mV offset, 1.5-5 mV hysteresis ✓; the TLV3603's
  LE/HYS table (0/3/30/60 mV for high/float/150k/56k, low = latch) matches the sheet note ✓
  (TLV3601.txt lines 444-447). 249 mV of signal vs ~20 mV needed: 12× at the regulated level ✓.
- Window power-up state: confirmed from the AD5696R datasheet (RSTSEL → VLOGIC = midscale
  1.25 V; GAIN → GND = 0-2.5 V span; LDAC → GND = update on write; address 0x0C with A1=A0=0 ✓ —
  all four pin assignments verified against the TSSOP-16 pin table). All four comparators read
  high until the FPGA writes the thresholds; with 400 mV of margin to the arms' CM there is no
  chatter, only constant-high, which the gateware must simply ignore until then. ✓
- The 33 Ω series + 453 Ω taps: I redid the load math — with a 50 Ω scope on a MON jack the
  comparator node sits at ~3.14 V (the tap's 503 Ω against the comparator's ~25 Ω output), the
  FPGA sees the full node voltage (its path is high-Z), the scope sees ÷10 ✓. The one bad tap
  pair is on the slow path (finding 3).

**5. The slow path.** Gain 20 after 4 with a 4.8 MHz pole: 73 ns rise, crosses at 36.6 ns — the
"37 ns later" claim ✓ (`build/budget.json` `slow_t50_ns` = 36.63). Offsets: two THS4541s at
×20 → up to 50 mV at the comparators (offset is ±0.45 mV at 25 °C, ±0.85 over temp, plus 13 µA
bias over the unbalanced network — the 50 mV bound stands); the trim reach through 100 k is
±66 mV at the outputs ✓ covers it. Signal at the quiet threshold is ±77 mV — the offsets are
smaller but comparable: nulling (the driver's duty-cycle routine) is genuinely needed, and it
exists. The bad monitor taps are finding 3. Nothing else wrong.

**6. The transmitter.** Ladder arithmetic reproduces exactly: 0.170/0.500/0.830 V with the
PYNQ's 200 Ω included, 0.167/0.521/0.874 without it (the Icepi case, re-centred by VR) — inside
the ADL5375-05's 0-1 V absolute baseband range ✓; the 41 µA per-pin source current lifts the P-side node
9.8 mV, trimmed by VR ✓ (the N side sits on the 836 Ω VN_0V5 divider and lifts 68.5 mV — finding
11; the trim absorbs both); −4.5 dBm at 0.7 Vpp is consistent with the datasheet's −1.36 dBm at
1 Vpp/5.8 GHz ✓; carrier feedthrough −19.5 dBm ✓ (datasheet 5.8 GHz row). DSOP: VIH 2.0 / VIL
0.8 ✓, high = disable ✓, and the Response-15 chain (TX_EN high → U206 inverts → DSOP low =
transmit; R227 1k holds TX_EN at ≤0.35 V against the Zynq's configuration pull-ups) is correct
and is the right fix for "transmits whenever the host is off". I checked the other header-driven
controls for the same disease: LEs and trigger-buffer inputs got their 100 k pull-downs
(R314-R318) ✓; LOOP_SEL floats (harmless with JP103 on CMP) ✓; TR_A rests high = receive ✓;
the DSA powers up at 31.75 dB (its datasheet, PE43711.txt) ✓ — the receiver is deaf at power-up,
which is the safe end. One leftover: the Morse ID keys TX_DIS, i.e. mutes the carrier — the far
loop coasts through each element and re-acquires in ~ms; a few seconds' outage every 10 minutes.
Fine for scheduled trials; worth one line in BRINGUP.

**7. Power.** The ideal-diode steering is right: Q301's gate is pulled down by Q303 only when
VBUS is present and held up by +5V_HDR otherwise; Q302's gate rides VBUS through 1k/100k so the
header FET opens when USB is present (worst-case Vgs ≈ −0.05 V vs the −0.5 V threshold — thin but
as analysed in the sheet note, and the failure mode is two 5 V rails sharing through two PTCs,
not damage). Neither input can back-feed the other ✓. The drop budget is the thin point:
80 mV (FET) + ~100 mV (PTC) + bead + pour ≈ 0.19 V against the ADL53xx's 4.75 V floor — 50 mV
of margin from an ideal 5.00 V source. A PD power bank at 4.85-4.9 V under 1.3 A *will* run the
RF rail below spec; BRINGUP's "5.1 V bench supply" is the right answer on the bench, and the
field kit needs a "5 V sources must hold ≥ 4.95 V at the plug" note. Regulator heat: 0.25 W in
each PLL LDO → +47 °C at 187 °C/W ✓ (TPS7A20 thermal table). The PTCs: MF-MSMF200-2 holds 2 A at
23 °C but ~1.2-1.4 A at 60-70 °C — a closed box in the sun with 6.7 W inside can reach that;
venting or a note. Hot-plug surge: finding 6. Back-feeding the host through signal pins:
finding 5.

**8. The gateware and driver.** I ran everything in my copy: `make sim` (tb_costaslink: 17 SPI
words, 5 I2C transactions, init sequence, DSA, DAC, ADC, latency counter, Morse — PASS),
`sim-engines` PASS, `sim-axil` PASS (15 reads, 4 writes), `sim-driver` (15 tests) PASS. `make
lint` **fails** (finding 4) — trivially fixable, but the README implies it's green. I verified
against the datasheets, not just the testbench: the MAX2871 words decode right (INT bit 31 set,
N=232, R=1, CP=7 → 2.56 mA, LDF=1, MUX[3:0]=0110 = digital lock detect on the MUX pin, and the
power-up 5→4(off)→3→2→1→0→5→4(on) sequence with the 20 ms wait follows the datasheet's "clean
clock at start up" recipe); the MCP4728 fast-write frame {4'b0000, code} × 4 channels is byte-exact
against Figure 5-7 of the datasheet (a sub-check I'd asked for reported this wrong — the command
is 2 bytes/channel, and the RTL is correct); the AD5696R's 0x30|one-hot(channel) write-and-update
command is correct; the MCP4728's LDAC pin (pin 4) is grounded = update-on-write ✓ and RDY/BSY
(pin 5) NC is blessed by the datasheet's own note ("leave float if unused"); the PE43711 gets its
8 bits LSB-first with D7=0 ✓. The ISERDES word ordering was verified against Vivado's UNISIM
model in a dedicated testbench with a constant, calibrated pipeline offset — good practice. The
latency counter's `LATENCY` register is fabric-resolution (10 ns), not sample-resolution; the
sample-resolution path is in rx_engine — fine, but the driver docs should say which is which.
The slow-confirm delay (RX_TIMING[23:16]) is a raw clock count that software must program for the
real 100 MHz clock — no guard; a wrong value silently vetoes nothing or everything. The PYNQ
overlay closes timing (WNS 1.661 ns, WHS 0.031, pulse-width 0.345 ns spare;
build/pynq/timing_summary.rpt). I would trust the latency numbers to the sample *after* the
loopback calibration the design already does (TRIG A against CMP I MON), not before.

**9. Manufacturing.** BOM↔CPL are consistent (349 placements each, every designator once, no
dupes); the 382-part headline = 349 placed + 33 DNP/TP/hole items (cosmetic doc drift, finding
17). The three consigned lines are correctly identified and necessary (JLCPCB stock: balun 0,
ADL5375-05 4, ADL5380 18 — the consignment is not optional); CONSIGNMENT.md's "three reels" is
loose language for 3×4 pieces but the quantities (2+attrition per board) are right. J302 is
consistently out of the JLCPCB order and on the hand-solder list ✓. Gerbers complete (all
copper, mask, silk, paste, edge, drill, job file) ✓. Thin stock is real (HMC536 5 vs 2,
AD5696R 7 vs 2, TLV3603 16 vs 8 on 2026-10-10) — re-query on order day, as the author's own rule
says. Fiducials/layer markers: finding 10. Impedance control: finding 15. CPL rotations: deferred
per the brief, no effort spent.

**10. The method.** I am the reviewer who had to read the Python, and it reads well: the sheets'
generators are more informative than most hand-drawn schematics (every value traces to
`sim/budget.py`, every wire carries its levels box). The decisive guard — `gen/board.py`
checking pcbnew's own pads against the plan before copper, and the generator reproducing the
shipped sheets byte-for-byte (I regenerated all seven in my copy: six identical, the root
identical in content, re-saved by KiCad 10) — means the artifacts under review are the artifacts
the code describes. The method's real cost showed up once: the router's scenic LO-N detour
(finding 1) is exactly the kind of thing a hand-rounder would not have done and a code review of
routes.py doesn't see ("an L where the straight line is not clear; the router where neither is").
The rule to add: after routing, **print every planned pair's two leg lengths side by side and
gate on the skew** — the data was all there.

## §4: what nobody asked about

- **ESD/static at the antenna ports.** The RX input is a 1.5 pF block straight into the
  SKY65404 (abs max input +1 dBm; ESD class 1C parts elsewhere in the chain). A panel on a hill
  with 10 m of coax builds static; there is no DC path to ground and no protector anywhere in the
  RX or TX RF paths. On the bench with whips this is fine. For field work: a gas-discharge or
  quarter-wave stub protector at the panel (in the cable, like the planned limiter), and a note
  in BRINGUP stage 5. Not a board change; an unaddressed field risk.
- **RF exposure with the 2 W PA.** +30 dBm into a 24 dBi panel is +54 dBm EIRP. At the panel's
  face the average density is ~P/aperture ≈ 1 W / 0.12 m² ≈ 0.8 mW/cm² — at the FCC uncontrolled
  limit (1 mW/cm² at 5.8 GHz); it falls below it within ~1 m (near-field edge ~6 m for this
  aperture, so the fall-off is slower than 1/r² close in). For the 30 dBi dish the near field
  extends ~14 m (2D²/λ at D = 0.6 m), so there is no close-in "safe distance", only a safe angle —
  nobody in the beam, ever (my first draft's "4 m" was wrong; Grok4.7's near-field arithmetic is
  the right frame). "Aim away from people and buildings" (BRINGUP) is right; add the numbers:
  **no body parts within 1 m of a driven panel's face, and nobody in the dish's beam.**
- **Legal shape of the emission.** Settled in the plan (§15.23 five-unit homebuilt cover for the
  bench; amateur 5 cm with the gateware's Morse ID outdoors). One nuance nobody wrote down: a
  carrier that is *always on*, keyed with the callsign, is operationally a beacon; on 5 cm with a
  licensed control operator and ID every 10 minutes this is defensible, but the ID-every-10-min
  timer should not be a driver option the experimenter can leave off outdoors — make the amateur
  mode enforce it in gateware, not in the notebook.
- **25 MHz harmonic pickup lands exactly on the carrier.** 232 × 25 MHz = 5800 MHz: any pickup of
  the two references' harmonics into the RX chain is coherent with the carrier and adds a fixed
  I/Q vector (the trims absorb it), and any harmonic of the *other* board's 25 MHz lands on the
  same place. Unavoidable and harmless here (it's DC after the demod), but it means the REF OUT
  coax and the 25 MHz CMOS lines deserve their distance from the RX chain — the REF OUT buffer is
  right next to the VCXO, which is right behind the RX synthesizer. Watch it on RX MON if the
  I/Q offsets wander with the REF OUT cable attached.
- **The experiment's validity holds.** The calibration (intercept of latency vs distance, slope =
  c) is sound *because* the DSA holds the demodulator at −20 dBm across distances — the
  electronics delay (comparator overdrive, arm crossing fraction) is level-dependent and would
  otherwise fake a distance-dependent intercept. The residual: comparator delay still moves with
  overdrive at fixed level if the *waveform* changes (multipath); the histogram readout covers
  this. The 1.25 ns sample grid is fine for a 22.7 ns claim to ~1 ns once calibrated.
- **Sun/heat/condensation in the field box.** 6.7 W in a sealed box in the sun is 30-50 °C rise
  inside; the PTCs' hold current falls below the board's 1.34 A around 65-70 °C (finding §3.7);
  BRINGUP stage 1's IR check is on the open bench. The field kit needs a vented/shaded box note.
- **Two-driver hazard on the FPGA-free trigger path.** With the DNP 0 Ω fitted (TRIG IN → TX_Q1)
  any gateware that drives TX_Q1 as an output fights the 74LVC1G17 through 200 Ω (~16 mA — brown,
  not fatal). The note says to set CTRL[8]; a one-line "fitted?" checkbox in the driver would do.
- **Documents.** Finding 13's split-brain common mode is worse than one wrong entry in `parts`:
  the datasheet itself contradicts itself, and the sheet prints BOTH numbers as authoritative
  (3.8 V in the blue box, 3.2 V beside the chip) — the blue boxes exist to kill exactly this.
  Also finding 17's drift list. And `CONSIGNMENT.md` says "three reels" for 12 pieces total.

## §5: the CLAUDE_PCB.md check

Rules broken, quoted:

- **§10 gate 15 / §5: "Fiducials and layer markers present"; "Provide three board fiducials at
  three widely separated corners"; "Put layer numbers in copper on every copper layer."** None
  exist (finding 10). Deliberate (JLCPCB's rails), but the rulebook doesn't have the exception.
- **§9: "Never tap a node whose amplitude sets a timing, such as a comparator's or squarer's
  input behind a series resistor. Tap the low-impedance side."** The two slow-path MON taps are
  behind the 1 kΩ pole resistor on the comparator inputs (finding 3).
- **§15: "Hot-plugging a supply on a cable rings… Damp it with a bulk electrolytic or polymer
  capacitor (its ESR is the damping), and clamp with a TVS above the working voltage."** No
  bulk; the TVS clamps at 9.2 V against 5.5 V abs-max victims (finding 6). Partially rescued by
  the PTC+FET's 110 mΩ of series damping.
- **§14: "Always leave a tuning network and a test port: a pi footprint between radio and
  antenna."** The TX output has the pi pad ✓ and taps ✓; the RX input has neither — if the LNA's
  input match is off (its 0.5 pF shunt assumes the datasheet's evaluation conditions), nothing on
  the board can tune it. Minor, and a retrofit SMA filter/pad in the cable is the practical
  answer anyway.
- **§14 (RF ground): "many vias in an RF chip's exposed pad."** U104/U201 have 4 where the
  datasheets draw 9; the SKY65404 paddle and the ADL5611 tabs have none (finding 9). PLAN.md §16
  claims a via grid in every paddle; the board disagrees.
- **§14 fences "at no more than λ/10 in the dielectric":** met (worst 2.54 mm ≈ λ/10, typical
  1.2-1.8 mm — verified from the copper, finding-free).

Gates the build does not run (§10 list), with what I found:
- Gate 2 (pin audit against datasheet figures): run once by hand (build/scratch/pin_audit.md),
  not in the build. I re-did the two the audit itself flagged as picture-only: the balun
  (matches) and the TCXO pin 1 — the latter now resolved: the datasheet drawing says "PAD 1:
  E/D or N.C." with an internal pull-up (I viewed the rendered page Gemini3.8Flash captured), so
  floating pin 1 is correct and DOA 13's rework plan can be retired.
- Gate 11/16 (rail widths, copper balance, drop): partially in the release (widths reported);
  the +5V drop is hand-computed in the notes (0.19 V, matches my number). No formal gate.
- Gate 19 (clock-net lengths vs previous rev): N/A rev A — but the spirit (know your clock/LO
  lengths) is what finding 1 violates, and no gate caught it.
- No gate checks that the netclass patterns bind to any net (finding 8) or that the paddled
  parts got their via grids (finding 9) — both sat in plain sight next to gates that did run.
- The schematic-overlap gate (§10.4) runs but is non-fatal (`build.py` `ok=(0, 1)`); I ran the
  generator in my copy: 0 overlaps on all seven sheets.

Rules I would change or add:
- **Add: after routing, report every planned differential pair's leg lengths and gate on skew
  (e.g. >2 mm at 5.8 GHz).** Finding 1 sat in plain sight in `build/route_report.json`'s
  neighbourhood and no gate looked at it.
- **Add: the LO/clock lines' impedance is a design value too** — the LO pairs went out as
  0.2 mm "baseband" lines (~57-60 Ω); either deliberate (then say so in routes.py) or a bug.
- **§9 addition: a tap's DC path rule should name the divider case explicitly** — the slow taps
  fail not only the timing rule but the "follow the tap's DC path" rule (a 50 Ω scope drags the
  node to 0.85 V).
- **Add: a netclass pattern that matches zero nets fails the build.** The RF/LO classes'
  clearances silently applied to nothing (finding 8). Print each pattern's match count and gate
  on it — and treat the pour's clearance on the RF nets as what it is: the CPWG gap, a design
  value, deserving the same gate as the track width.
- **§10 addition to the upload-readiness pass: fiducials/layer markers, impedance-control
  decision, and stock re-query timestamp — all three already exist as text but two are not
  enforced.**

## What I checked and found right

- DRC 0/0/0 with schematic parity and ERC 0 reproduce from the shipped files (this directory's
  drc.json, erc.json). net_check 0, all 13 signal paths whole (net_check.txt). Label check
  (hardware/checks/labels.json) read: 0 violations with two documented omissions (J208, J502).
- The schematic generator reproduces the shipped sheets (six of seven byte-identical; root
  identical in content).
- The budget's arithmetic re-derived: TX levels, ladder levels, chain levels to the demodulator,
  ±249 mV at the comparators, the comparator floors (−81/−107 dBm), the loop's Ko and topology
  (but NOT its Kd — see finding 2, the budget's own constant is a factor of two high),
  the MAX2871 loop filter values, the latency stack (22.7/13.9 ns) — all consistent with the
  datasheet numbers I could verify (ADL5375 5.8 GHz table, ADL5611 5.8 GHz table, TLV3601/3
  tables, TS5A3159 leakage, TPS7A20 θJA, ADL5380 Table 4, MAX2871 register map, PE43711 serial
  format and power-up state, HMC536 truth table and control levels, AD5696R pinout/POR/address,
  SKY65404 pinout and limits, the VCXO's pull/MBW/impedance).
- MCP4728: fast-write frame byte-exact vs Figure 5-7; LDAC grounded (pin 4) — correct, despite
  looking alarming; RDY/BSY (pin 5) NC is the datasheet's own instruction.
- AD5696R: TSSOP-16 pin-by-pin against the board's use (VDD, VLOGIC, RESET high, RSTSEL high →
  midscale 1.25 V, GAIN low → 0-2.5 V, LDAC low, A1=A0=0 → 0x0C, VREF NC). All correct.
- The ideal-diode power steering (Q301/Q302/Q303) — the truth table works out in all four
  plug/unplug combinations; the old back-feed bug (Response 9) stays fixed.
- The TX_EN/DSOP chain and the six new pull-downs (Response 15): levels verified both directions.
- Gateware: sims all pass; the MAX2871 words and power-up sequence match the datasheet; the
  ISERDES ordering is simulation-verified; the driver/RTL register maps agree (regmap.py);
  PYNQ timing closes with margin.
- The balun footprint vs the datasheet's terminal figure (rendered the PDF page and compared).
- L2 is unbroken ground (zero non-GND copper on In1.Cu); the supply pours live on In2 with a
  ground fill; via drills all 0.25 mm (JLCPCB-ordinary, cheap).

## Other reviewers (added after my own draft)

Everything above this section was written before I read design_review_Gemini3.8Flash/,
design_review_GPT-5.6Terra/, design_review_Grok4.7/ or the author's design_review_Claude/. I then
read all four, and re-verified every adopted claim myself before letting it into the findings
table — the table above is the merged, re-verified set, with first-finder credit in each row.

**Adopted (they found it first; I confirmed it independently before adopting):**

- **The Kd factor-of-two** (GPT-5.6Terra, independently Grok4.7). I had written "Kd = 0.25 V/rad ✓"
  in my first pass of §3.3 — the one place I trusted the budget's own constant. Re-derived from
  the switch topology and the fitted R126 = 20k: Kd = 0.124 V/rad, loop at fn 2.06 kHz / ζ 0.49.
  Became finding 2 and changed the verdict.
- **The netclass regex / pour gap** (Gemini3.8Flash, confirmed Grok4.7). Verified: `/^RF_/` and
  `/^LO_/` match zero nets in the shipped pcb (the nets are `Net-(U101-RF_IN)`,
  `/Receiver and Costas loop/LO_RX_P`, …); the GND zone clearance measures 0.2 mm, so the CPWG
  gap is 0.20 mm and Z0 ≈ 47.7 Ω. Became finding 8.
- **The paddle via counts** (Grok4.7). Verified with pcbnew on the shipped board: 4 vias under
  U104/U201 (datasheets draw 9), none under U101 or the ADL5611 tabs, 9-10 under the MAX2871s.
  PLAN.md §16's "a via grid in every paddle" is false for 6 of 9 paddled parts. Became finding 9.
- **The VN_0V5 bias lift** (Gemini3.8Flash, confirmed Grok4.7). Arithmetic verified against the
  ADL5375's 41 µA/pin (I had checked the P-side 9.8 mV lift in §3.6 and missed the N-side
  network): VN_0V5 ≈ 0.610 V, ~59 mV differential offset, trim-absorbed. Became finding 11.
- **The budget's GB P1dB row** (Grok4.7). Verified: gb_p1db_dBm = 16.0 is the ADL5611's 5 GHz
  row; the 5.8 GHz row is 12.8. The assertion cannot fail and the TX sheet note is wrong.
  Became finding 14.
- **TCXO pin 1** (Gemini3.8Flash). I viewed his render of the datasheet drawing myself: "PAD 1:
  E/D or N.C." with an internal pull-up — floating pin 1 is correct, and the DOA-13
  rework-to-1.65 V advice is unnecessary. Grok4.7 declined to adopt this without seeing the
  drawing; having seen it, I adopt it. This closes the last open pin-audit item.
- **Fiducials and the lint failure** appear in all three; I had both independently (findings 10
  and 4). GPT-5.6Terra's worst-case 5 V rail drop (0.63 V at maximum datasheet currents) is
  consistent with my §3.7 (0.19 V at typical current): read together — fine at typ, below the
  4.75 V floor at max current from a 4.85 V bank; the BRINGUP bench-supply note is the right
  mitigation.

**Disputed, with the number that settles it:**

- **GPT-5.6Terra's "do not order" over impedance control.** I side with Gemini and Grok: 47.7 Ω
  vs 50 Ω on ≤ 14 mm lines is ~0.05 dB of mismatch loss and −33 dB return; the couplers are
  calibrated monitor taps (the DSA and the MON jacks absorb a wrong coupling coefficient).
  Finding 15 records the choice; it is not a stop.
- **Grok4.7's B3 / Gemini's 3.2 (PA power back through the off HMC536 killing the LNA).** Both
  chains sign-flip the LNA's reverse isolation in the last step. +23.7 dBm at the PA output
  − 28 dB switch isolation = −4.3 dBm backwards into the LNA's *output* pin; the SKY65404's S12
  at 5.8 GHz is −19.7 dB (its own datasheet table — I read it), so the LNA's *input* sees
  ≈ −24 dBm, 25 dB under its +1 dBm abs max — not 3-14 dB over it, as both reports claim.
  Reverse isolation attenuates; you subtract it. The power-sequencing concern underneath is real
  and already handled (TX_EN gates the PA supply via U207; my finding 5 covers the unpowered-host
  case). An operating note — "don't run the 2 W PA with the antenna cable open" — covers the rest.
- **Grok4.7's B4 (MAX2871 words missing bit 31).** Refuted: the generator sets INT (bit 31) for
  integer-N; I decoded all 17 SPI words in the simulation transcript against the register map.
- **Grok4.7's serial-flash-on-1.8 V / bank-0 finding.** Refuted: there is no serial flash on this
  board — not in the BOM, not in the generators, and there is no 1.8 V rail at all (the pcb's
  positive nets are +5V_IN/+5V_HDR/+5V_RF and the five 3.3 V rails; U503 is a TLV3601
  comparator). This looks like a transplant from the PYNQ-Z2 itself or another board in the repo.
- **GPT-5.6Terra's B3 (fink 2450 S11 at 5.8 GHz).** Plausible and honestly labelled a
  frequency-error hypothesis; unverifiable from the datasheet. The swept-S11 check on the bench
  is the answer. Not adopted, not refuted.
- **The author's design_review_Claude** reviewed an earlier build. Its two blockers are fixed in
  the build under review: U112 is now the OPA2388 (3.3 V-capable, rail-to-rail — I verified the
  part in the generator and the levels), and the power steering now switches Q301's gate through
  Q303 (my §3.7 checks all four plug/unplug combinations). Its item 3 is the common-mode question,
  and this build carries its fix (Rs 1.2k→1k is fitted; the 3.8 V budget entry is its deliberate
  conservative reading — finding 13 now records the residual: the datasheet contradicts itself,
  the sheet prints both numbers, and the guaranteed worst-case margin is 17 mV at the 5.25 V
  corner). Its low items (Kvco 60 vs 100 MHz/V in the MAX2871 filter; TR_B's 10k vs the PYNQ's
  2k2 pull-up) still stand as accepted notes.

**What this review adds that none of the others caught:**

- **Finding 1, the LO leg skew (10 mm vs 44-46 mm)** — the headline. No other reviewer parsed the
  shipped copper for the LO nets; several quoted PLAN.md §10.4's "matched lengths" as verified.
- **Finding 3** (slow-path MON taps behind the pole resistor — a named CLAUDE_PCB §9 violation).
- **Finding 5** (host back-feed through the comparator outputs when the PYNQ is off).
- **Finding 6** (the hot-plug surge tank arithmetic against the RF chips' 5.5 V abs max).
- **Finding 7** (the 1 Hz re-centre does not exist, and the VCXO's guaranteed APR ±50 ppm is short
  of the worst-case pull by ~15 kHz).
- **Finding 12** (TRIG IN's 50 Ω termination vs the Schmitt threshold: 1.65 V < 2.19 V).
- Smaller: the 33 Ω + 200 Ω = 233 Ω in the comparator-crossing latency (~0.7 ns the budget's
  200 Ω-only number misses); the Morse ID making the far loop coast; the 25 MHz × 232 harmonic
  landing exactly on the carrier (§4).
