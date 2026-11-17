# Pin audit: CostasLink-PYNQ-Z2 rev A (2026-11-16)

ECP5-2ADC-2DAC rev A went out with its USB port dead. Its FT2232H's VPHY/VPLL were fed 1.8 V against 3.0-3.6 V, and
its D+/D- were swapped. The author's pin audit and five reviews had passed both faults. This audit runs the two checks
of `CLAUDE_PCB.md` ("Two checks no board ships without", section 10 gates 2a-2c) and the brief
`tools/pin_audit/BRIEF.md` over this board, re-derived from the data sheets.

The board is rev A as ordered (2026-10-18), boards A and B in bring-up. The netlist is the project's own
`hardware/checks/netlist.net`. It and every `.kicad_sch` were last changed in 978075d (Prompt 36), before the order.
A re-export of the committed schematic with KiCad 10.0.7 (in the scratch area) is identical in parts, values, net
names, pin functions and connectivity.

**Result:** no new BLOCKER or HIGH. Every supply, ground, reference, bias and enable pin is inside its data sheet's
range on its derived rail (222 rows, 0 fail), and every IC pin number matches its data sheet name (442 pins,
0 mismatched). The pair walk fails on exactly one known fault: the I arm is wired inverted (REVB row 9). Two known
items are re-derived from the data sheets (REVB rows 1 and 2). Four items are new: two MEDIUM, two LOW.

## Red flags

| severity | board | finding | evidence (netlist; data sheet) | on the built board | workaround / rework |
|---|---|---|---|---|---|
| **HIGH** (known: REVB 9) | rev A | **The I arm is wired inverted and the Q arm is not, so the arms are a mirror of the constellation, not a rotation of it.** With the default sign jumpers the Costas loop locks 90 degrees off. | U104.3 IHI → R107 1k → I_SUM → **U105.3 IN-**; U104.4 ILO → R105 → **U105.2 IN+**. U104.16 QHI → R112 → U106.2 IN+; U104.15 QLO → R114 → U106.3 IN-. The THS4541 gives Vod = (Rf/Rg)(V at IN+'s Rg - V at IN-'s Rg), so I_P = -k·I and Q_P = +k·Q. Pins: ADL5380.txt:303 (3, 4, 15, 16 IHI, ILO, QLO, QHI), THS4541.txt:182-185. Pair lines "I arm IHI/ILO" FAIL in the `.out`. | Seen 2026-10-29 (BRINGUP 3.3). The I/Q phase fits agree. | Done on both boards: JP101 and JP102 moved (confirmed 10-30). Rev B: swap R105/R107's chip ends, or keep the inversion and flip the default jumpers and their silkscreen (REVB 9). |
| **HIGH** (known: REVB 1) | rev A | **The TX ladders' references come from 0-3.3 V DAC channels, so a DAC code can take IBBP/QBBP past their 0-2 V absolute maximum.** Only software prevents it. | TX_I: J302.7, .11 → R201/R202 2.2k, U113.6 VOUTA → R203 300R → U201.21 IBBP. TX_Q: R204/R205 2.2k, U113.7 → R206 348R, TRIG_IN → JP203 → R291 2.2k → U201.10 QBBP. ADL5375.txt:317 "IBBP, IBBN, QBBP, QBBN 0 V to 2 V"; :283 operating 0-1 V. Node = (Σ V/R + 41 µA)/ΣG: **2.0 V on IBBP at VR_I = 1.63 V**, and 2.0 V on QBBP at VR_Q = 1.37 V with TRIG IN high. The MCP4728 reaches 3.3 V. | Never exceeded: the driver refuses VR > 0.6 V (`VR_MAX_V`, BRINGUP_LOG "Before power" 1). | Keep the guard. Rev B: divide the reference at the DAC (REVB 1). |
| **MEDIUM** (known: REVB 2) | rev A | **+5V_RF meets the RF parts' 4.75 V minimum only with 5.1 V or more at the plug and a short lead.** A USB source at its own spec does not. | +5V_RF feeds U104.6/13/24 VCC, U201.18/24 VPS, and U103/U117/U202 pin 3 through L103/L104/L201. All need 4.75-5.25 V (ADL5380.txt:143, ADL5375.txt:298, ADL5611.txt:203). The path is VBUS → F301 → Q301 → FB301, 192 mΩ (REVB 2). At about 1.0 A, a 5.00 V source gives **4.81 V** with no lead and **4.63 V** with the bench's 0.18 Ω lead. A source at 4.75 V (USB's floor: MEMORY) gives 4.56 V. | Measured 4.823 V with the bench at 5.147 V (BRINGUP_LOG:219). The bench now runs 5.30 V: 4.94-5.00 V. | As now: a bench supply at 5.25-5.30 V on a short lead (docs/PATHS.md:205, "not a laptop port"). Rev B: REVB 2's lower-resistance path, or a 5.0 V LDO from a higher input. |
| **MEDIUM** (new) | rev A | **The cold start and linkd's retries write SPI into the MAX2871s while their 3.3 V is off.** CLK, DATA and LE are driven past "-0.3 V to VCC + 0.3 V". | SPI_SCLK (J302.31) → U115.1, U203.1. SPI_SDATA (J302.29) → U115.2, U203.2. LE_PLL_RX/TX → U115.3 / U203.3. MAX2871.txt:82 "All Other Pins to GND -0.3V to VCC_ + 0.3V". The documented start runs the PYNQs and their servers first, then the boards' 5 V (DEMO_COURTYARD.md:462). linkd's `step()` calls `setup()`, which starts with `cl.pll_init()` (gateware/driver/linkd.py:303) before anything checks that the board answers. So every retry while the board is off is a burst of SPI writes. docs/PATHS.md:139-142 said this only happens "if someone loads the overlay before the board is powered (don't)". Since e805682 (BRINGUP_LOG 4.94) it happens on every cold start and every outage. | No damage seen. Each high bit pushes up to about (3.3 - 0.6)/200 Ω ≈ 13 mA into an unpowered input's clamp. It also back-feeds +3V3_PLL_x, which is the TPS7A20's OUT with IN at 0 (TPS7A20.txt:202, "6.5 or VIN + 0.3"). *Uncertain:* the PYNQ-Z2's series resistance (taken as 200 Ω from REVB 20) and the burst duty. To settle it, scope SPI_SCLK and TP304 with the boards' 5 V off while linkd runs. | Software, no rework: in `setup()`, read the board's ADC (I2C) before `pll_init()`. If it does not answer, mark the board gone without touching SPI. Rev B: REVB R3's Ioff buffer on the header's lines into the board as well as out of it. The PE43711 (3.6 V absolute, PE43711.txt:76) and the 74LVC parts (Ioff) are safe. The MCP4728's I2C pins are also VDD + 0.3 (MCP4728.txt:126), but the pull-ups keep them under its ±2 mA input current (:127). |
| **LOW** (new) | rev A | **The Q ladder's top state sits at the edge of the -05's 0-1 V baseband window, and past it when TRIG IN is high.** | U201.10 QBBP at VR_Q = 0.2456 V (the driver's default): both Q bits high give **0.94-0.99 V** (with and without the PYNQ's 200 Ω). With JP203 fitted (BRINGUP.md:144, the default) and TRIG IN high it is **1.20-1.24 V**. The window is ADL5375.txt:283 "Absolute Voltage Level ... 0 1". The I ladder's top is 0.84-0.88 V. docs/PATHS.md:192's check ("0.17 / 0.50 / 0.83 V") leaves TRIG IN out. | Under the 2 V absolute maximum. The modulator's Q input runs over its window in that state; the TX is saturated anyway (REVB 35). | Take JP203 off when TRIG IN is not in use. Rev B: REVB 1's divided reference, with the ladder's top inside 1 V. |
| **LOW** (new) | rev A | **U301/U302 run warm.** These are the TPS7A2033s that feed each MAX2871 (165 mA typical, 200 mA maximum: MAX2871.txt:109). | Each dissipates (4.6-4.7 V - 3.3 V) × 0.165-0.2 A = 0.23-0.26 W. Its θJA is 187 °C/W (TPS7A20.txt:259, DBV), so it runs 43-49 °C above the board around it. | The board's NTC reads 55-60 °C (BRINGUP_LOG 3.5), so TJ is about 100-110 °C against 125 °C (TPS7A20.txt:237). Not measured. | To settle it, put the IR camera or a thermocouple on U301/U302. Rev B: drop more in R309/R310, or feed them from a lower rail. |
| INFO | rev A | **Both LO pairs are crossed on purpose**: RFOUTA_P → LOIN and RFOUTA_N → LOIP, on U104 and on U201 (gen/sch_rx.py:132-135, gen/sch_tx.py:133-135). This turns I and Q together by 180 degrees, which the Costas loop does not see. The note's claim checks out. | U115.12 → C149 → LO_RX_P → C119 → U104.10 LOIN. U203.12 → C229 → C204 → U201.4 LOIN. The pair lines expect it this way and pass. | | |
| INFO | rev A | **The balun T101 has no polarity mark** (HHM1907B1_C531388.txt:48-49). A swap would also be a 180-degree rotation. | T101.2 → C159 → U104.22 RFIP; T101.3 → C160 → U104.21 RFIN | | |
| INFO | rev A | **Y201 (TCXO): its VDD tolerance is not on the sheet.** The table's ±5 % is the one row from memory. Pin 1 ("E/D or N.C.") floats because R228 is DNP. | TC32H4 pdf page 1 drawing | The TCXO runs on both boards, so it is enabled. | Fit R228 (10k to +3V3_OSC) if a lot ever needs E/D high. |
| INFO | rev A | **D303's symbol is drawn as a bidirectional TVS (A1/A2), but the SMAJ5.0A is unidirectional.** Pad 1, the cathode in KiCad's D_SMA, is on +5V_IN, which is the right way round. | D303.1 +5V_IN, .2 GND | Confirmed: the rail is not clamped at 0.7 V. | Rev B: use a unidirectional symbol. |
| INFO | rev A | **Left open on purpose, and allowed:** AD5696R VREF (internal reference, AD5696R.txt:499), MCP4728 RDY/BSY, TLV3603 LE/HYS (both footprints DNP; "RHYST = Floating 3 mV", TLV3601.txt:445), ADL5380 ADJ (R104 DNP: open is its >5 GHz setting, ADL5380.txt:316). J301's D+/D-/SBU are unconnected (power-only USB-C), so there is no USB pair to check. | | | |

## What was covered

- **Power pins by voltage (gate 2a):**
  - 44 ICs (42 U and the two oscillators, 26 part types) tabled from their data sheets' pin tables.
  - 222 rows: 94 supply, reference, bias and enable pins checked against their rails, 108 ground and exposed pads, and 20 must-be-unconnected pins.
  - 0 fail. 139 data-sheet quotes were machine-checked against their cited lines.
  - **1 row from memory** (the TCXO's ±5 %).
- **Rails, each derived from its source:**
  - +5V_IN and +5V_RF from the bench measurements (4.86-5.30 V and 4.82-5.01 V).
  - The four +3V3 LDO rails from the TPS7A2033's 3.3 V ±1.5 % in DBV.
  - +3V3_OSC from the LP5907-3.3's ±2 %.
  - 11 pull-up or divider nodes from their resistors and pin currents. For example, VN_0V5 = 0.1376 × 3.3 V + 82 µA × 647 Ω = 0.50-0.51 V.
  - Every rail's name agrees with its derived voltage. Each LDO's OUT pin is checked against what that part makes.
  - The engine named the rails it inherited: R309/R310 2.2 Ω (U301/U302 IN), L102 (the LNA's VCC), L103/L104/L201 (the gain blocks' RFOUT).
- **Pair polarity (gate 2b): 55 lines walked through series parts and DC blocks.**

  | lines | what | result |
  |---|---|---|
  | 4 | the two LOs | pass |
  | 2 | the balun | pass |
  | 4 | the demodulator into the arms | **2 FAIL: the I arm** |
  | 16 | the arms into the sign comparator, the window comparators, the slow path and the log amp | pass |
  | 4 | the slow path's outputs | pass |
  | 4 | the window DAC channels to their comparators | pass |
  | 8 | the comparators to their header pins, by name | pass |
  | 4 | the TX ladder bits to IBBP/QBBP | pass |
  | 8 | the triggers and the T/R lines | pass |
  | 5 | the SPI latch enables and the MUX lines | pass |

  There are no LVDS, TMDS, Ethernet, CAN, RS-485 or differential clock pairs, and the USB-C carries power only.
- **The sign through the chain:**
  - RF and LO: each is one 180-degree rotation, the LO crossed on purpose.
  - The I arm inverts and the Q arm does not, so the arms are a mirror (REVB 9).
  - The slow path, the window comparators and the sign comparator keep the sign: P to IN+, N to IN-.
  - The TX ladder bits add positively on IBBP/QBBP against the 0.5 V on IBBN/QBBN.
  - The modulator's LO is crossed, so the carrier is inverted (a rotation).
- **Pin numbers by name (gate 2c):** 442 pins of 48 parts, read against their data sheets' tables: every IC, both oscillators, the balun and the three MOSFETs. 0 mismatched. The generator draws every symbol by number (gen/symbols.py). Unnamed buffer and op-amp output pins are checked by direction.
- **Discretes, by reading:**
  - Q301/Q302 AO3401A are G1, S2, D3 (the AOS sheet's SOT-23 top view, fetched). The body diode points input → +5V_IN, and the gate is pulled low to conduct. The bench confirms Q301 is on: 79 mV at 0.87 A, including copper.
  - Q303 2N7002 is G1, S2, D3. This pinout is from **memory**: LCSC refused the C8545 sheet.
  - The SOT-23, SOT-89, SC70, QFN-6 and 3225 land patterns run their pads in the makers' order. The ADL5611's tab is pin 2, GND. The TCXO's pad 1 is at the drawing's "PAD 1 ID".
  - LEDs D301/D302 and diodes D303/D501: pad 1 is the cathode in KiCad's footprints. D501 is the right way round for a positive peak detector (U508A OUT → A, K → 100 Ω → the hold capacitor).
  - Regulators: TPS7A2033 and LP5907 are IN 1, GND 2, EN 3, NC 4, OUT 5 (TPS7A20.txt:166-182, LP5907.txt:144-152).
- **Logic levels, by reading:**
  - All logic runs on 3.3 V rails and is fed by the PYNQ's 3.3 V.
  - MAX2871: VIH 1.5 V.
  - PE43711: 1.17-3.6 V.
  - ADL5375 DSOP: VIH 2.0 V, from a 74LVC1G04.
  - HMC536 A/B: 3-5 V ±0.2 V, at 3.3 V through 100 Ω.
  - SKY65404 V_ENABLE: 2.95-3.35 V against 2.5-3.5 V.
  - THS4541 PD: pulled to Vs+.
  - AD8310 ENBL: tied to VPOS.
  - ADL5380 ENBL: grounded, which enables it.
  - AD5696R RESET and RSTSEL: tied high.
  - ADS1115 inputs stay within VDD + 0.3. The AD8310's output tops out at 2.6 V.
  - The VCXO's VC runs 0.02-3.28 V against its 0.3-3.0 V control range. That is past the range but not an absolute maximum (docs/PATHS.md).
  - I2C addresses: 0x48, 0x49, 0x60, 0x61, 0x0C. No clash.
- **Regulators:**
  - Every input is in range: TPS7A20 1.6-6.0 V and LP5907 2.2-5.5 V, against 4.86-5.30 V. The LP5907 has 0.2 V of headroom at the bench's 5.30 V.
  - No dropout at the minimum input: at least 4.4 V in against 3.3 V + 0.145 V (TPS7A20.txt:314-316).
  - Each output feeds only 3.3 V parts whose ranges include 3.234-3.366 V.
  - The +5V_RF "rail" has no regulator; it is the MEDIUM above.

## Not checked, and why

- **The PYNQ-Z2's side of J302** (header pin → Zynq ball, its series resistors) is not re-derived from the PYNQ-Z2's schematic. Every header function has run on the bench. The 200 Ω in the MEDIUM above is REVB 20's figure.
- **The 2N7002, SMAJ5.0A, 1N4148W and KT-0603R sheets** could not be read: LCSC refuses scripted fetches. Their pinouts rest on KiCad's footprint convention and the working boards.
- **Footprint geometry against package drawings** is not re-measured beyond pad order. JLCPCB's placement preview (Prompt 40) and two working boards cover it.
- **Analog operating points inside the chain** (for example, the THS4541 input common mode against the ADL5380's 3.8 V output common mode) are design analysis, not pin limits. docs/PATHS.md section 2 covers them.
- The CPL rotation question (deferred project-wide).

## Where things are

- Config: `~/OpticsPCBs/tools/pin_audit/boards/CostasLink-PYNQ-Z2_revA.py` (RAILS with their derivations, PARTS, PAIRS, NAMES).
- Gates 2a/2b: `python3 ../pin_audit.py CostasLink-PYNQ-Z2_revA.py -v > CostasLink-PYNQ-Z2_revA.out`. It exits 1 on the two I-arm lines.
- Gate 2c: `python3 CostasLink-PYNQ-Z2_revA.py > CostasLink-PYNQ-Z2_revA_names.out`. It exits 0.
- Data sheet text: `build/txt/<part>.txt`, the committed `pdftotext -layout` of `datasheets/`. The two TI sheets the project lacks (SN74LVC1G17 SCES351Y, SN74LVC1G04 SCES214AF) were fetched from ti.com into a scratch area only. Fetch them again to re-check those four rows.

## Check 3: connectors against their drawings (2026-11-16)

Brief: `~/OpticsPCBs/tools/pin_audit/BRIEF_CONNECTORS.md` (CLAUDE_PCB.md top block item 3, gate 2d). Every row below is
computed from the placed pads of `hardware/CostasLink-PYNQ-Z2.kicad_pcb`, which is byte-identical to the tag
`CostasLink-PYNQ-Z2-revA` (the built boards). The script's own pad positions agree with KiCad's IPC-D-356 export to
0.002 mm on all 1356 pads, J302 on the underside included.

### Red flags

| severity | board | connector | finding | evidence | on a built board | workaround / fix |
|---|---|---|---|---|---|---|
| — | rev A | — | **No BLOCKER, HIGH, MEDIUM or LOW.** Every connector below agrees with its drawing. | `connectors/CostasLink-PYNQ-Z2.out` (0 FAIL) | — | — |
| INFO | (the PYNQ-Z2's docs) | J302's partner, the PYNQ's RPI_IDE | TUL's user manual and its schematic disagree on PYNQ pin 1. The manual's Table 22 (`GPSDO-PYNQ-Z2/datasheets/pynqz2_user_manual_v1_0.pdf` p.30) marks pin 1 "G". The schematic (`TUL_PYNQ_Schematic_R12.pdf` p.4, RPI_IDE) has VCC3V3 on pins 1 and 17, the Pi convention. | J302 pads 1 and 17 are unconnected. | None: either reading meets an open pad. | Believe the schematic. |

### What was checked (counts)

- **J302, the 2x20 socket on the underside, mated with the PYNQ-Z2's Raspberry Pi header.** Both patterns are taken
  from the top. Shield pad n is set on PYNQ pin n by a proper rotation plus a translation, with no mirror. The fit is
  exact: rotation 0°, translation (−47, +114) mm, worst pad-to-pin 0.000 mm. A mirrored footprint would leave 2.54 mm.
  - **Functions** (TUL schematic p.4): the PYNQ's 5 V pins 2 and 4 meet +5V_HDR. Its 3V3 pins 1 and 17 meet open
    pads. Its eight GND pins (6, 9, 14, 20, 25, 30, 34, 39) meet GND. The 28 RPIO pins meet shield signals. No shield
    signal lands on a PYNQ supply.
  - **Body:** the shield extends outward, beyond the PYNQ's header edge. It overlaps the PYNQ only in the 11 mm strip
    along that edge, as the PYNQ's silk asks ("RASPBERRY PI (BOARD CONNECTS OUTWARD)").
  - **Standoff:** the PYNQ's top-right hole lands exactly under slot H304.
  - **Silk:** the back silk "1" and "2" sit beside pads 1 and 2.
  - **The PYNQ-Z2's geometry**, used for the absolute frame and the hole:
    - the caliper measurements in `GPSDO-PYNQ-Z2/mechanical/make_mockup.py` L22-36 (pin 1 125.78 mm from the left;
      odd row 3.5 mm from the edge, even row 6.04 mm; top-right hole (133.3, 4.3));
    - which end is pin 1 and which row is at the edge: the PYNQ's own silk ("1" by the edge row and "2" by the inner
      row at the right end, "39 40" at the left), seen in DFRobot's photo `PYNQ-Z2_DFR0600_Dim_02.jpg`, and the
      manual's Table 22 drawn the same way.

    No dimensioned TUL drawing was found on disk. The chirality result does not depend on the absolute numbers.
  - **Measurement, as corroboration only:** boards A and B ran on their PYNQs over J302 (`bringup/BRINGUP_LOG.md`:
    I2C on pins 3/5, the links locking).
- **J301 USB-C** (HRO TYPE-C-31-M-12, C165948), against `datasheets/TYPE-C-31-M-12_C165948.pdf`, "RECOMMEND P.C.B
  LAYOUT (COMPONENT SIDE)".
  - Seen as HRO draws it, with the opening toward the viewer, our 12 contact positions run A1/B12, A4/B9, B8, A5, B7,
    A6, A7, B6, A8, B5, A9/B4, A12/B1. That is HRO's order.
  - The opening faces the east edge: the shell pegs are 1.4 mm inside it, and the body overhangs it by 1.2 mm.
  - GND is on A1/A12/B1/B12 and the shell; VBUS on A4/A9/B4/B9; CC1 and CC2 each through their own 5.1 k (R301, R302)
    to GND.
  - D+, D- and SBU are open: the port carries power only, so there is no data pair to swap.
- **J303 (TR header) and the 3-pin jumpers JP101, JP102, JP103, JP201:** 11 silk end labels, each beside the pad on the
  net it names: TR A/TR B/GND; Q+/Q−; CMP/FPGA; TCXO/REF IN.
- **The 2-pin shunts JP202, JP203, JP301, JP302, JP303:** no orientation; nets listed in the output.
- **28 coax jacks other than SMA** (22 U.FL, 6 MMCX): the centre contact carries the signal and every post or tab is
  on GND. The U.FL pads are the small centre pad between the two 2.2 mm tabs (Hirose's pattern); the MMCX centre is the
  centroid of its four posts (BAT Wireless drawing, p.6).

### Not checked, and why

- **The 9 SMAs:** out of scope by the request.
- **The PYNQ-Z2's Arduino headers:** this board does not use them, and it does not reach them. It overlaps the PYNQ
  only within 11 mm of the RPi header edge; by the photo, the Arduino rows are about 20 mm from that edge.
- **The mechanical clearance** under the overlap strip (heights of the PYNQ's parts against the 8.5 mm socket). This is
  not a pin question, and the built boards sit on their PYNQs.
- **The external T/R switch module on J303:** no module is named, so there is no pinout to compare.
- **No JTAG, debug, GPS, JST, barrel or IDC connector** is on this board.

### Where

- The script: `~/OpticsPCBs/tools/pin_audit/connectors/CostasLink-PYNQ-Z2.py`, with helpers and the PYNQ-Z2 model in
  `_CostasLink_PYNQ_Z2_lib.py`. Its output is `CostasLink-PYNQ-Z2.out` (exit 0).
- The IPC-D-356 export and the renders are in the session scratch area, `.../scratchpad/conn_icepi_pynq/pynq/`.
  The script re-exports the IPC-D-356 if it is missing.
