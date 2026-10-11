# Pin-numbering audit of the CostasLink custom symbols against the datasheets

Audited 2026-10-09 against `gen/symbols.py` (every symbol in `CUSTOM`), the committed library
`hardware/lib/CostasLink.kicad_sym` (parsed back: identical to the generator), the footprints in
`hardware/lib/CostasLink.pretty/`, the netlist `hardware/checks/netlist.net`, and the pdftotext
datasheets in `build/txt/`.  There is no `.kicad_pcb` yet, so "pad with no net" means a footprint
pad that no symbol pin drives in the netlist.  Line numbers below are `grep -n` into `build/txt/<file>`.

## Verdict

**Every pin that is drawn has the right number and the right name on all 14 datasheet-backed
symbols, and every schematic use of a pin number matches that pin's datasheet function.  Two symbols
are INCOMPLETE and leave footprint pads with no net: the PE43711 omits nine GND pins (6-13 and 15),
and the HMC536MS8G omits its exposed ground paddle (footprint pad 9), which the datasheet says "must
also be connected to RF/DC ground".  Two polarity statements written next to correct pin numbers
contradict the datasheets: the SN74LVC1G3157's keyword/comment says "S high connects A to B1" (the
datasheet: S high selects B2), and the antenna sheet's notes say "A low = receive (ANT to SW RX)"
(the datasheet: A low routes RFC to RF1, which the sheet wires to the SW TX jack).  Two things could
not be verified from text: the TC32H4 TCXO's pin 1 function (its text has no pin table) and the
balun's physical terminal positions (a picture).**

Summary of mismatches and doubts (details in section 3):

| # | Severity | Part | What |
|---|----------|------|------|
| 1 | MISMATCH (incomplete symbol) | PE43711 | GND pins 6, 7, 8, 9, 10, 11, 12, 13, 15 absent from the symbol; footprint pads carry no net |
| 2 | MISMATCH (incomplete symbol) | HMC536MS8G | exposed paddle (footprint pad 9) absent from the symbol; carries no net; datasheet requires ground |
| 3 | MISMATCH (polarity text) | SN74LVC1G3157 | symbol keyword and generator comment invert the select sense (datasheet: S low = B1, S high = B2) |
| 4 | MISMATCH (polarity text) | HMC536 / sch_ant.py | notes state A low = ANT-SW RX; datasheet: A low = RFC-RF1 = the SW TX jack.  PLAN.md's "pull-up on A, pull-down on B (rests in receive)" agrees with the datasheet; the notes do not |
| 5 | could not verify | TCXO_3225 pin 1 | TC32H4 text has no pin table; symbol leaves pin 1 no-connect |
| 6 | could not verify | Balun_5400 pad positions | numbering/function verified; the terminal figure is a picture |
| 7 | cosmetic | ADL5380 | symbol names pins 1/2/5/8 GND1-GND4; the datasheet figure names them GND3/GND1/GND1/GND4 (all ground) |
| 8 | cosmetic | MAX2871 | pin 32 is VCC_SD in the table, VDD_SD in the figure; symbol says VCC_SD |

## 1. Per-chip tables

Columns: pin | symbol says (gen/symbols.py) | datasheet says | how the schematic uses it | verdict.

### 1.1 ADL5380 (U104, QFN-24-1EP, EP = pad 25) -- `adl5380()`; datasheet Table 3, ADL5380.txt 299-324; Figure 2, 250-295

| pin | symbol | datasheet | schematic (sch_rx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | GND1 | GND (fig: "GND3 1", 262; table: "1, 2, 5, 8, 11, 14, GND1, GND2, GND3, GND4 Ground", 301) | bottom_gnd -> GND | OK (name cosmetic) |
| 2 | GND2 | GND (fig: "GND1 2", 263) | GND | OK (name cosmetic) |
| 3 | IHI (out) | "3, 4, 15, 16 IHI, ILO, QLO, QHI" (303); fig "IHI 3" (264) | `dem.pin("3")` -> I arm IN+ (hp) | OK |
| 4 | ILO (out) | ILO (303; fig "ILO 4", 265) | `dem.pin("4")` -> I arm IN- (lp) | OK |
| 5 | GND3 | GND (fig "GND1 5", 266) | GND | OK (name cosmetic) |
| 6 | VCC1 | "6, 13, 24 VCC1, VCC2, VCC3 Supply" (306) | supply_bar +5V_RF | OK |
| 7 | ENBL (in) | "7 ENBL Enable Control. When pulled low, the part is fully enabled; when pulled high ... disabled" (308-309) | bottom_gnd -> GND = enabled | OK |
| 8 | GND4 | GND (fig "GND4 8", 285) | GND | OK |
| 9 | LOIP (in) | "9, 10 LOIP, LOIN Local Oscillator Input. Pins must be ac-coupled" (310); fig "LOIP 9" (283) | `dem.pin("9")` <- LO_RX_P via 1.5 pF | OK |
| 10 | LOIN (in) | LOIN (310; fig "LOIN 10", 280) | `dem.pin("10")` <- LO_RX_N via 1.5 pF | OK |
| 11 | GND | GND (301; fig "GND4 11", 281) | GND | OK |
| 12 | NC (no_connect) | "12 NC No Connect. Do not connect to this pin." (315) | `S.nc(*dem.pin("12"))` | OK |
| 13 | VCC2 | VCC2 (306) | +5V_RF | OK |
| 14 | GND | GND (301; fig "GND2 14") | GND | OK |
| 15 | QLO (out) | QLO (303; fig "15 QLO", 265) | `dem.pin("15")` -> Q arm IN- (lp) | OK |
| 16 | QHI (out) | QHI (303; fig "16 QHI", 264) | `dem.pin("16")` -> Q arm IN+ (hp) | OK |
| 17 | GND | GND (301; fig "17 GND2") | GND | OK |
| 18 | GND | GND (301; fig "18 GND3") | GND | OK |
| 19 | ADJ (passive) | "19 ADJ A resistor to VS ... For operation >5 GHz, RADJ = open" (316-318); fig "19 ADJ" (260) | DNP 1.5k to +5V_RF (open as fitted) | OK |
| 20 | GND | GND (301; fig "20 GND3", 256) | GND | OK |
| 21 | RFIN (in) | "21, 22 RFIN, RFIP RF Input" (319); fig "21 RFIN" (258) | `dem.pin("21")` <- balun BAL- (T101-4) | OK |
| 22 | RFIP (in) | RFIP (319; fig "22 RFIP", 259) | `dem.pin("22")` <- balun BAL+ (T101-3) | OK |
| 23 | GND | GND (301; fig "23 GND3", 254) | GND | OK |
| 24 | VCC3 | VCC3 (306; fig "24 VCC3", 257) | +5V_RF | OK |
| 25 | EP | "EP Exposed Pad ... connected to a low impedance thermal and electrical ground plane" (324) | GND; footprint pad 25 exists | OK |

Netlist: all 25 footprint pads have a net.

### 1.2 ADL5375-05 (U201, QFN-24-1EP, EP = pad 25) -- `adl5375()`; Table 3, ADL5375.txt 381-402; Figure 2, 340-378

| pin | symbol | datasheet | schematic (sch_tx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | DSOP (in) | "1 DSOP Output Disable. A logic high on this pin disables the RF output. Connect this pin to ground or leave it floating to enable" (383-384); fig "DSOP 1" (347) | TX_DIS with 100k pull-down | OK |
| 2 | COMM | "2, 5, 8, 11, 12, 14, 17, 19, 20, 23 COMM Input Common Pins" (385-386) | GND | OK |
| 3 | LOIP (in) | "3, 4 LOIP, LOIN Local Oscillator Inputs" (387); fig "LOIP 3" (349) | `mod.pin("3")` <- LO_TX_P via 1.5 pF | OK |
| 4 | LOIN (in) | LOIN (387; fig "LOIN 4", 350) | `mod.pin("4")` <- LO_TX_N via 1.5 pF | OK |
| 5 | COMM | COMM (385) | GND | OK |
| 6 | NC | "6, 7, 13, 15, NC No Connect. These pins can be left open or tied to ground." (392) | `S.nc` | OK |
| 7 | NC | NC (392; fig "NC 7") | `S.nc` | OK |
| 8 | COMM | COMM (385; fig "COMM 8") | GND | OK |
| 9 | QBBN (in) | "9, 10, 21, 22 QBBN, QBBP, IBBP, IBBN" (393-394); fig "QBBN 9" (364) | `mod.pin("9")` <- VN_0V5 (0.5 V bias) | OK |
| 10 | QBBP (in) | QBBP (393; fig "QBBP 10", 365) | `mod.pin("10")` <- Q ladder node | OK |
| 11 | COMM | COMM (385; fig "COMM 11") | GND | OK |
| 12 | COMM | COMM (385; fig "COMM 12") | GND | OK |
| 13 | NC | NC (392; fig "13 NC") | `S.nc` | OK |
| 14 | COMM | COMM (385; fig "14 COMM") | GND | OK |
| 15 | NC | NC (392; fig "15 NC") | `S.nc` | OK |
| 16 | RFOUT (out) | "16 RFOUT RF Output. Single-ended, 50 Ohm internally biased ... must be ac-coupled" (400); fig "16 RFOUT" | `mod.pin("16")` -> 1.5 pF -> ADL5611 | OK |
| 17 | COMM | COMM (385; fig "17 COMM") | GND | OK |
| 18 | VPS1 | "18, 24 VPS1, VPS2 Positive Supply Voltage Pins" (401) | +5V_RF | OK |
| 19 | COMM | COMM (385; fig "19 COMM") | GND | OK |
| 20 | COMM | COMM (385; fig "20 COMM") | GND | OK |
| 21 | IBBP (in) | IBBP (393-394; fig "21 IBBP", 351) | `mod.pin("21")` <- I ladder node | OK |
| 22 | IBBN (in) | IBBN (393-394; fig "22 IBBN", 350) | `mod.pin("22")` <- VN_0V5 | OK |
| 23 | COMM | COMM (385; fig "23 COMM") | GND | OK |
| 24 | VPS2 | VPS2 (401; fig "24 VPS2") | +5V_RF | OK |
| 25 | EP | "EP Exposed Paddle. Connect to the ground plane" (402) | GND | OK |

Note on the pdftotext column scramble: Table 3 line 393-394 lists "9, 10, 21, 22" against "QBBN, QBBP, IBBP, IBBN"
in order, i.e. 9 = QBBN, 10 = QBBP, 21 = IBBP, 22 = IBBN; Figure 2 (lines 350, 351, 364, 365) confirms each
individually.  Netlist: all 25 pads have a net.

### 1.3 MAX2871 (U115, U203, QFN-32-1EP, EP = pad 33) -- `max2871()`; Pin Description, MAX2871.txt 789-861; figure 725-787

| pin | symbol | datasheet | schematic (sch_blocks.synthesizer) | verdict |
|-----|--------|-----------|------------------------------------|---------|
| 1 | CLK (in) | "1 CLK Serial Clock Input" (791-792) | SPI_SCLK | OK |
| 2 | DATA (in) | "2 DATA Serial Data Input" (794) | SPI_SDATA | OK |
| 3 | LE (in) | "3 LE Load Enable Input" (795-796) | LE_PLL_RX / LE_PLL_TX | OK |
| 4 | CE (in) | "4 CE Chip Enable. A logic-low powers the part down" (798) | 10k pull-up to the rail | OK |
| 5 | SW (passive) | "5 SW Fast-Lock Switch ... No connect in Normal mode" (799-801) | `S.nc` | OK |
| 6 | VCC_CP | "6 VCC_CP Power Supply for Charge Pump" (802) | supply bar | OK |
| 7 | CP_OUT (out) | "7 CP_OUT Charge-Pump Output. Connect to external loop filter input." (803) | `pl.pin("7")` -> loop filter | OK |
| 8 | GND_CP | "8 GND_CP" (804) | GND | OK |
| 9 | GND_PLL | "9 GND_PLL" (805) | GND | OK |
| 10 | VCC_PLL | "10 VCC_PLL" (806) | supply bar | OK |
| 11 | GND_RF | "11 GND_RF" (807) | GND | OK |
| 12 | RFOUTA_P (out) | "12 RFOUTA_P Open Collector Positive RF Output A" (808-809) | 27 nH to rail, 1.5 pF -> LO_x_P | OK |
| 13 | RFOUTA_N (out) | "13 RFOUTA_N" (811-812) | -> LO_x_N | OK |
| 14 | RFOUTB_P (out) | "14 RFOUTB_P" (824-825) | -> monitor U.FL | OK |
| 15 | RFOUTB_N (out) | "15 RFOUTB_N" (827-828) | -> 49.9 ohm load | OK |
| 16 | VCC_RF | "16 VCC_RF" (830-831) | supply bar | OK |
| 17 | VCC_VCO | "17 VCC_VCO" (833) | supply bar | OK |
| 18 | GND_VCO | "18 GND_VCO" (834) | GND | OK |
| 19 | NOISE_FILT (passive) | "19 NOISE_FILT VCO Noise Decoupling. Place a 1uF capacitor to ground." (835) | 1 uF to GND | OK |
| 20 | TUNE (in) | "20 TUNE Control Input to the VCO. Connect to external loop filter." (836) | `pl.pin("20")` <- R3/C3 | OK |
| 21 | GND_TUNE | "21 GND_TUNE" (837-838) | GND | OK |
| 22 | RSET (passive) | "22 RSET ... external resistor to ground" (840-841) | 5.1k to GND | OK |
| 23 | BIAS_FILT (passive) | "23 BIAS_FILT ... 1uF capacitor to ground" (843) | 1 uF to GND | OK |
| 24 | REG (passive) | "24 REG Reference Voltage Compensation. Place a 1uF capacitor to ground." (844) | 1 uF to GND | OK |
| 25 | LD (out) | "25 LD Lock Detect Output" (845-846) | test point | OK |
| 26 | RFOUT_EN (in) | "26 RFOUT_EN RF Output Enable. A logic-low disables" (848) | 10k pull-up | OK |
| 27 | GND_DIG | "27 GND_DIG" (849) | GND | OK |
| 28 | VCC_DIG | "28 VCC_DIG" (850) | supply bar | OK |
| 29 | REF_IN (in) | "29 REF_IN Reference Frequency Input ... AC-couple" (851-853) | 100 nF from the reference | OK |
| 30 | MUX (bidir) | "30 MUX Multiplexed I/Os. See Table 5." (854) | hlabel MUX_RX / MUX_TX (output) | OK |
| 31 | GND_SD | "31 GND_SD" (855-856) | GND | OK |
| 32 | VCC_SD | "32 VCC_SD" (858-859); figure says "VDD_SD 32" (766) | supply bar | OK (cosmetic) |
| 33 | EP | "- EP Exposed Pad. Connect to board ground." (861) | GND; KiCad QFN-32-1EP pad 33 | OK |

Netlist: all 33 pads have a net on both U115 and U203.

### 1.4 PE43711 (U102, QFN-24-1EP, EP = pad 25) -- `pe43711()`; Table 9, PE43711.txt 1584-1677; Figure 35 inline

| pin | symbol | datasheet | schematic (sch_rx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | D0 (in) | "1 C0.25 (D0) Attenuation control bit, 0.25 dB" (1588) | GND | OK |
| 2 | VDD | "2 VDD Supply voltage" (1589) | +3V3_ANA | OK |
| 3 | P/S (in) | "3 P/S Serial/parallel mode select" (1591); "P/S = HIGH selects the serial interface" (338) | 10k to +3V3_DIG (high = serial) | OK |
| 4 | GND | "4, 6-13, 15 GND Ground" (1599) | GND | OK |
| 5 | RF1 (passive) | "5 RF1(2) RF1 port (RF input)" (1607) | `dsa.pin("5")` <- LNA via 1.5 pF | OK |
| 6 | **absent** | GND (1599; fig "GND 6", 1632) | footprint pad 6 has no net | **MISMATCH** |
| 7 | **absent** | GND (1599; fig row 1651) | no net | **MISMATCH** |
| 8 | **absent** | GND (1599) | no net | **MISMATCH** |
| 9 | **absent** | GND (1599) | no net | **MISMATCH** |
| 10 | **absent** | GND (1599) | no net | **MISMATCH** |
| 11 | **absent** | GND (1599) | no net | **MISMATCH** |
| 12 | **absent** | GND (1599) | no net | **MISMATCH** |
| 13 | **absent** | GND (1599; fig "13 GND", 1632) | no net | **MISMATCH** |
| 14 | RF2 (passive) | "14 RF2(2) RF2 port (RF output)" (1620) | `dsa.pin("14")` -> 1.5 pF -> ADL5611 | OK |
| 15 | **absent** | GND (1599; fig "15 GND", 1628) | no net | **MISMATCH** |
| 16 | LE (in) | "16 LE Serial interface Latch Enable input" (1623) | LE_DSA | OK |
| 17 | CLK (in) | "17 CLK Serial interface Clock input" (1625) | SPI_SCLK | OK |
| 18 | SI (in) | "18 SI Serial interface Data input" (1627) | SPI_SDATA | OK |
| 19 | D6 (in) | "19 C16 (D6) Parallel control bit, 16 dB" (1629) | GND | OK |
| 20 | D5 (in) | "20 C8 (D5)" (1631) | GND | OK |
| 21 | D4 (in) | "21 C4 (D4)" (1633) | GND | OK |
| 22 | D3 (in) | "22 C2 (D3)" (1650) | GND | OK |
| 23 | D2 (in) | "23 C1 (D2)" (1666) | GND | OK |
| 24 | D1 (in) | "24 C0.5 (D1)" (1668) | GND | OK |
| 25 | EP | "Pad GND Exposed pad. Ground for proper operation." (1670-1671) | GND | OK |

Parallel bits: the datasheet asks "1) Ground C0.25, C0.5, C1, C2, C4, C8, and C16 if not in use." (1675) and
"When using the DSA in serial mode, ground all parallel control inputs." (331-332); the schematic grounds all seven.  OK.
Netlist: footprint pads 6, 7, 8, 9, 10, 11, 12, 13, 15 of U102 have NO net (16 of 25 pads are driven).

### 1.5 ADL5611 (U103, U117, U202, SOT-89-3; pad 2 is the tab) -- `adl5611()`; Table 5, ADL5611.txt 348-355

| pin | symbol | datasheet | schematic | verdict |
|-----|--------|-----------|-----------|---------|
| 1 | RFIN (in) | "1 RFIN RF Input. This pin requires a dc blocking capacitor." (350) | `gb.pin("1")` <- 1.5 pF | OK |
| 2 | GND | "2 GND Ground" (351); "EPAD ... encompasses Pin 2 and the tab" (354; note 335) | GND; KiCad SOT-89-3 pad 2 is the custom tab pad | OK |
| 3 | RFOUT (out) | "3 RFOUT RF Output and Supply Voltage. DC bias is provided to this pin through an inductor" (352) | `gb.pin("3")` -> bias tee (43 nH to +5V_RF) and 1.5 pF out | OK |

### 1.6 SKY65404-31 (U101, generated QFN-6 footprint, pad 7 = paddle) -- `sky65404()`; Table 1, SKY65404-31.txt 66-70; Figure 2, 41-47

| pin | symbol | datasheet | schematic (sch_rx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | V_ENABLE (in) | "1 V_ENABLE Enable control input" (68); fig "V_ENABLE 1" (41) | 100 ohm to +3V3_ANA (Table 5: 3 V = enabled, 158-160) | OK |
| 2 | GND | "2 GND Ground" (69) | GND | OK |
| 3 | RF_IN (in) | "3 RF_IN LNA input" (70) | `lna.pin("3")` <- SMA via 1.5 pF, 0.5 pF shunt | OK |
| 4 | RF_OUT (out) | "4 RF_OUT LNA output" (68) | `lna.pin("4")` -> 1.5 pF -> DSA | OK |
| 5 | GND | "5 GND Ground" (69) | GND | OK |
| 6 | VCC | "6 VCC Supply voltage for LNA" (70) | 0.6 nH to +3V3_ANA | OK |
| 7 | EP | not in Table 1; the package drawing has an exposed pad ("Exposed Pad", C210262.txt 414; "exposed heat sink slug", 438; "7X Exposed Solder", SKY65404-31.txt 366) | GND | OK |

Footprint check (gen/footprints.py vs. the datasheet): Skyworks' Figure 2 (top view) runs 1-2-3 down the LEFT side and
4-5-6 up the RIGHT side.  The generated footprint puts 1-2-3 along the lower row left to right (y = +0.704 in KiCad, y down)
and 4-5-6 along the upper row right to left: the same counter-clockwise sequence rotated 90 degrees, pin 1 dot at the
pad-1 corner.  JLCPCB's EasyEDA pattern for C210262 (mfg/jlc_footprint_cache.json) has pads 1, 2, 3 at x = -0.5, 0, +0.5 on
the larger-y row, 4, 5, 6 at x = +0.5, 0, -0.5 on the smaller-y row, 7 centred: identical to the generated footprint.  OK.

### 1.7 THS4541 (U105, U106, U501, U502, VQFN-16-1EP, EP = pad 17) -- `ths4541()`; Table 5-1, THS4541.txt 178-195; Figure 5-1, 148-174

| pin | symbol | datasheet | schematic (sch_blocks.arm) | verdict |
|-----|--------|-----------|-----------------------------|---------|
| 1 | FB- (passive) | "FB- 1 Output Inverted (negative) output feedback" (183); fig "FB- 1" (150) | Rf between pin 1 and pin 2 ("connect external resistors from the FB- pin to the IN+ pins, and the FB+ pin to the IN- pins", 2878-2879) | OK |
| 2 | IN+ (in) | "IN+ 2" (184) | `fda.pin("2")` <- Rg from the P input | OK |
| 3 | IN- (in) | "IN- 3" (185) | `fda.pin("3")` <- Rg from the N input | OK |
| 4 | FB+ (passive) | "FB+ 4" (182) | Rf between pin 4 and pin 3 | OK |
| 5-8 | Vs+ | "Vs+ 5, 6, 7, 8" (191) | supply bar +3V3_ANA | OK |
| 9 | Vocm (in) | "Vocm 9 Input Common-mode voltage input" (190) | 100 nF to GND, otherwise open (defaults midsupply, 270) | OK |
| 10 | OUT+ (out) | "OUT+ 10" (187) | `fda.pin("10")` -> X_P | OK |
| 11 | OUT- (out) | "OUT- 11" (188) | `fda.pin("11")` -> X_N | OK |
| 12 | PD (in) | "PD 12 ... PD = logic high = normal operation" (189) | 10k to the +3V3_ANA bar | OK |
| 13-16 | Vs- | "Vs- 13, 14, 15, 16" (192) | GND | OK |
| 17 | EP | "(1) Solder the exposed thermal pad to a heat-spreading power or ground plane ... must be connected ... and not floated" (194-195) | GND | OK |

### 1.8 TLV3601 (U107-U109, U503-U505, SC-70-5) -- `tlv3601()`; Table 5-1, TLV3601.txt 165-175; Figure 5-1, 137-149

| pin | symbol | datasheet | schematic (sch_blocks.comparator + sheets) | verdict |
|-----|--------|-----------|---------------------------------------------|---------|
| 1 | OUT (out) | "OUT 1 1 O Output (Push-pull)" (171-173); fig "OUT 1" (137) | `c.pin("1")` -> 33 ohm -> CMP_x | OK |
| 2 | VEE | "VEE 2 2 I Negative power supply" (174); fig "VEE 2" (139) | GND | OK |
| 3 | IN+ (in) | "IN+ 3 3 I Non-inverting input" (169) | `c.pin("3")` <- I_P / Q_P / Q_N | OK |
| 4 | IN- (in) | "IN- 4 4 I Inverting input" (170) | `c.pin("4")` <- I_N or V_T / V_T2 | OK |
| 5 | VCC | "VCC 5 6 I Positive power supply" (175: 5 for the TLV3601, 6 for the TLV3603) | +3V3_DIG | OK |

### 1.9 SN74LVC1G3157 (U110, SC-70-6) -- `lvc1g3157()`; Table 4-1, SN74LVC1G3157.txt 133-143; Figure 4-2, 95-106

| pin | symbol | datasheet | schematic (sch_rx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | B2 (passive) | "B2 1 I/O Switch I/O. Set S high to enable." (138) | `mux.pin("1")` <- JP102 pin 2 | OK (number) |
| 2 | GND | "GND 2" (139) | GND | OK |
| 3 | B1 (passive) | "B1 3 I/O Switch I/O. Set S low to enable." (140) | `mux.pin("3")` <- JP101 pin 2 | OK (number) |
| 4 | A (passive) | "A 4 I/O Common terminal" (141) | `mux.pin("4")` -> ERR | OK |
| 5 | VCC | "VCC 5" (142) | +3V3_DIG | OK |
| 6 | S (in) | "S 6 I Select" (143) | `mux.pin("6")` <- JP103 (CMP_I or LOOP_SEL) | OK (number) |

Polarity: the symbol's keyword ("S high connects A to B1") and the generator comment ("S high: A = B1") are the reverse of
the datasheet: "If the control input is low, B1 channel is selected. If the control input is high, B2 channel is selected."
(1049-1050) and Table 7-1 "L B1 / H B2" (1053-1057).  See section 3.3.

### 1.10 TS5A3159 (U111, SC-70-6) -- `ts5a3159()`; Pin Functions, TS5A3159.txt 142-151

| pin | symbol | datasheet | schematic (sch_rx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | NO (passive) | "1 NO I/O Normally open switch port" (146) | `S.nc` (open) | OK |
| 2 | GND | "2 GND" (147) | GND | OK |
| 3 | NC (passive) | "3 NC I/O Normally closed switch port" (148) | `hold.pin("3")` -> R1 -> integrator | OK |
| 4 | COM (passive) | "4 COM I/O Common switch port" (149) | `hold.pin("4")` <- ERR | OK |
| 5 | V+ | "5 V+ Power supply" (150) | +3V3_DIG | OK |
| 6 | IN (in) | "6 IN I Switch select. High = COM connected to NO; Low = COM connected to NC." (151) | LOOP_HOLD, 100k pull-down | OK: LOOP_HOLD high -> COM to the open NO pin = integrator input opened, as the note says |

### 1.11 HMC536MS8G (U401, MSOP-8-1EP, EP = pad 9) -- `hmc536()`; Pin Descriptions, HMC536.txt 313-334; truth table 229-237

| pin | symbol | datasheet | schematic (sch_ant.py) | verdict |
|-----|--------|-----------|-------------------------|---------|
| 1 | A (in) | "1 A See truth and control voltage tables." (320) | TR_A via 100 ohm, 10k pull-up to +3V3_DIG | OK (number) |
| 2 | B (in) | "2 B" (323) | TR_B via 100 ohm, 10k pull-down | OK (number) |
| 3 | RFC (passive) | "3, 5, 8 RFC, RF1, RF2 These pins are DC coupled and matched to 50 Ohms. Blocking capacitors are required." (326-327) | `sw.pin("3")` <- ANT via 1.5 pF | OK |
| 4 | NC (no_connect) | "4 N/C No connection required. This pin may be connected to RF/DC ground" (328-329) | `S.nc` | OK |
| 5 | RF1 (passive) | RF1 (326) | `sw.pin("5")` -> 1.5 pF -> J402 "SW TX" | OK (number) |
| 6 | GND | "6, 7 GND" (333) | GND | OK |
| 7 | GND | GND (333) | GND | OK |
| 8 | RF2 (passive) | RF2 (326) | `sw.pin("8")` -> 1.5 pF -> J403 "SW RX" | OK (number) |
| 9 (EP) | **absent** | "Package bottom has exposed metal paddle that must also be connected to RF/DC ground." (332-334); "8 lead MSOP8G ... with an exposed ground paddle" (26-28) | footprint pad 9 has no net | **MISMATCH** |

### 1.12 Balun_5400 (T101, generated footprint) -- `balun_5400()`; Terminal Configuration, 5400BL15B050E.txt 14-23

| pin | symbol | datasheet | schematic (sch_rx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | UNBAL | "1 Unbalanced Port" (16) | `t.pin("1")` <- coupler OUT | OK |
| 2 | GND | "2 GND" (17) | GND | OK |
| 3 | BAL+ | "3 Balanced Port" (18) | `t.pin("3")` -> ADL5380 RFIP (22) | OK |
| 4 | BAL- | "4 Balanced Port" (19) | `t.pin("4")` -> ADL5380 RFIN (21) | OK |
| 5 | GND | "5 GND" (21) | GND | OK |
| 6 | NC | "6 NC" (23) | `S.nc` | OK |

The terminal POSITIONS that gen/footprints.py encodes ("3, 2, 1 along the top row left to right, 4, 5, 6 along the bottom
row", brown mark at pin 1) are a picture in the PDF; the text only says "Mount these devices with brown mark facing up." (33).
Could not verify from text.  Which balanced terminal is "+" is arbitrary for a balun (the two are interchangeable; only
the I/Q sign convention moves).

### 1.13 VCXO_3225 (Y101, Crystal_SMD_3225-4Pin) -- `osc_3225("VC")`; Pad Functions, SX3V25.000B20100F30TNN_C5179998.txt 159-163

| pin | symbol | datasheet | schematic (sch_rx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | VC (in) | "1. Voltage control" (160) | `vc.pin("1")` <- VC from U112B | OK |
| 2 | GND | "2. GND" (161) | GND | OK |
| 3 | OUT (out) | "3. Output" (162) | `vc.pin("3")` -> MAX2871 REF_IN, REF OUT buffer | OK |
| 4 | VDD | "4. VDD" (163) | +3V3_OSC | OK |

The pad figure itself is a picture ("Buttom View", 168); the numbered function list is text and matches.  KiCad's
Crystal_SMD_3225-4Pin pattern numbers pads counter-clockwise from the pin-1 corner, the industry convention for this
package; the datasheet's pin-1 corner marking (213, "Pin 1 Location") cannot be read from text.

### 1.14 TCXO_3225 (Y201, same footprint) -- `osc_3225("VC/NC")`; TC32H4-25.000-33GNDTNL_C5119013.txt

| pin | symbol | datasheet | schematic (sch_tx.py) | verdict |
|-----|--------|-----------|------------------------|---------|
| 1 | VC/NC (in) | no pin table in the text (56 lines, specs and packaging only) | `S.nc` | could not verify |
| 2 | GND | - | GND | could not verify |
| 3 | OUT (out) | - | `tc.pin("3")` -> JP201 pin 1 | could not verify |
| 4 | VDD | - | +3V3_OSC | could not verify |

The 1 = control/NC, 2 = GND, 3 = OUT, 4 = VDD order is the usual 3225 oscillator convention and is what the SX3V uses on
the same pads, but the TC32H4's own text gives no pin table and no statement about pin 1 (VC, tri-state, or NC).  If pin 1
is a voltage-control input on this variant, leaving it open puts the TCXO at an undefined frequency offset within its pull
range; the PDF's drawing page (a picture) or the vendor must settle it.

### 1.15 Coupler_20dB and RPi_Header_40

No datasheet applies.  The coupler is a net tie (pads 1-2 and 3-4 joined by the footprint's own copper; `net_tie_pad_groups
"1,2" "3,4"`), used as IN=1, OUT=2, CPL=3, ISO=4 in `sch_blocks.coupler_mon` consistently with the footprint (3 at the input
end).  The header symbol's pin numbers are the header's own and are generated from `gen/pins.py` HEADER; sch_pwr.py uses
them by number from the same table.  Not audited further.

## 2. Schematic pin-number uses, checked against function

| use | file | datasheet function | matches? |
|-----|------|--------------------|----------|
| `dem.pin("22")` as RFIP, `("21")` as RFIN | sch_rx.py | ADL5380 22 RFIP, 21 RFIN (319) | yes |
| `dem.pin("9")/("10")` as LOIP/LOIN | sch_rx.py | 9 LOIP, 10 LOIN (310) | yes |
| `dem.pin("3")/("4")` I pair, `("16")/("15")` Q pair (HI to IN+, LO to IN-) | sch_rx.py | 3 IHI, 4 ILO, 16 QHI, 15 QLO (303) | yes |
| `dem.pin("19")` ADJ, `("12")` NC, `("7")` ENBL grounded | sch_rx.py | 19 ADJ, 12 NC, 7 ENBL low = enabled (308, 315, 316) | yes |
| `mod.pin("21")` IBBP, `("22")` IBBN, `("10")` QBBP, `("9")` QBBN | sch_tx.py | ADL5375 (393-394; fig 350, 351, 364, 365) | yes |
| `mod.pin("3")/("4")` LO, `("16")` RFOUT, `("1")` DSOP | sch_tx.py | 3/4 LOIP/LOIN, 16 RFOUT, 1 DSOP (383, 387, 400) | yes |
| MAX2871 `"12","13"` RFOUTA, `"14","15"` RFOUTB, `"7"` CP_OUT, `"20"` TUNE, `"29"` REF_IN, `"30"` MUX, `"25"` LD, `"4"` CE, `"26"` RFOUT_EN, `"19","23","24"` 1 uF, `"22"` RSET, `"5"` SW nc | sch_blocks.py | 792-861 as tabled above | yes, all |
| THS4541 `"1"` FB-, `"2"` IN+, `"3"` IN-, `"4"` FB+, `"9"` Vocm, `"10"` OUT+, `"11"` OUT-, `"12"` PD, `"5"-"8"` Vs+, `"13"-"17"` ground | sch_blocks.py | 182-194; Rf from FB- to IN+ and FB+ to IN- (2878) | yes |
| comparator `"1"` OUT, `"2"` VEE, `"3"` IN+, `"4"` IN-, `"5"` VCC | sch_blocks.py, sch_rx.py, sch_slow.py | TLV3601 169-175 | yes |
| LVC1G3157 `"3"` B1, `"1"` B2, `"4"` A, `"6"` S, `"5"` VCC, `"2"` GND | sch_rx.py | 138-143 | numbers yes; see 3.3 for the select sense |
| TS5A3159 `"4"` COM, `"3"` NC, `"1"` NO (open), `"6"` IN, `"5"` V+, `"2"` GND | sch_rx.py | 146-151 | yes |
| HMC536 `"3"` RFC, `"5"` RF1, `"8"` RF2, `"4"` nc, `"1"` A, `"2"` B, `"6","7"` GND | sch_ant.py | 320-333 | numbers yes; see 3.4 for the A/B sense; EP missing (3.2) |
| ADL5611 `"1"` in, `"3"` out + bias, `"2"` GND | sch_rx.py, sch_tx.py | 350-352 | yes |
| SKY65404 `"3"` in, `"4"` out, `"6"` VCC, `"1"` enable, `"2","5","7"` GND | sch_rx.py | 68-70 | yes |
| PE43711 `"5"` RF1 in, `"14"` RF2 out, `"17"` CLK, `"18"` SI, `"16"` LE, `"2"` VDD, `"3"` P/S high, `"1","24"-"19"` D0-D6 grounded, `"4","25"` GND | sch_rx.py | 1588-1671 | yes for the pins drawn; nine GND pins not drawn (3.1) |
| VCXO `"1"` VC, `"3"` OUT, `"4"` VDD, `"2"` GND; TCXO `"1"` nc | sch_rx.py, sch_tx.py | SX3V 160-163; TC32H4 none | VCXO yes; TCXO could not verify |
| balun `"1"` in, `"3"`/`"4"` to RFIP/RFIN, `"2","5"` GND, `"6"` nc | sch_rx.py | 16-23 | yes |

## 3. Mismatches and doubts, with evidence

### 3.1 PE43711: nine ground pins are missing from the symbol (MISMATCH)

`gen/symbols.py` `pe43711()` draws 16 pins: 5, 17, 18, 16 (left), 14 (right), 2, 3 (top), 1, 24, 23, 22, 21, 20, 19, 4, 25
(bottom).  The datasheet's Table 9:

    PE43711.txt:1599:    Marking                                                          4, 6–13, 15        GND         Ground
    PE43711.txt:1628:     GND        4                                         15   GND
    PE43711.txt:1632:     GND        6                                         13   GND
    PE43711.txt:1651-1661: GND GND GND GND GND GND   (the bottom row of Figure 35: pins 7, 8, 9, 10, 11, 12)

so pins 6, 7, 8, 9, 10, 11, 12, 13 and 15 are GND and the symbol has none of them.  The footprint
QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm has all 24 perimeter pads plus 25; the netlist (hardware/checks/netlist.net) shows
U102 pads 6, 7, 8, 9, 10, 11, 12, 13 and 15 with no net at all.  KiCad's ERC cannot see this (no symbol pin exists), and a
DRC will not complain about a padded-but-netless pad, so the board would be made with nine of the attenuator's ground
pins floating unless the layout happens to flood them.  Fix: add ("6".."13", "15", "GND", PI) to the symbol and extend
`B.bottom_gnd(dsa, [...])` in sch_rx.py.

### 3.2 HMC536MS8G: the exposed ground paddle is missing from the symbol (MISMATCH)

`hmc536()` draws pins 1-8 only.  The footprint MSOP-8-1EP_3x3mm_P0.65mm_EP1.73x1.85mm has pad 9 (the paddle); the netlist
shows U401 pad 9 with no net.  The datasheet:

    HMC536.txt:27:  surface mount packages with an exposed ground
    HMC536.txt:332: Package bottom has exposed metal paddle that
    HMC536.txt:333:  6, 7               GND
    HMC536.txt:334:   must also be connected to RF/DC ground.

The sheet's note already says "Exposed pad to ground" (sch_ant.py), but no pin carries it.  Fix: add ("9", "EP", PI) to the
symbol's bottom row and ground it in sch_ant.py.  (For comparison, the other EP-bearing symbols all carry their pad:
ADL5380/ADL5375/PE43711 25, MAX2871 33, THS4541 17, SKY65404 7.)

### 3.3 SN74LVC1G3157: the select sense in the symbol's text is inverted (MISMATCH in text, numbers correct)

`lvc1g3157()`: keyword "S high connects A to B1"; comment "S high: A = B1".  Datasheet:

    SN74LVC1G3157.txt:138:  B2                            1                        I/O        Switch I/O. Set S high to enable.
    SN74LVC1G3157.txt:140:  B1                            3                        I/O        Switch I/O. Set S low to enable.
    SN74LVC1G3157.txt:1049: depending upon the control input. If the control input is low, B1 channel is selected. If the control input is high, B2
    SN74LVC1G3157.txt:1056:                                               L                             B1
    SN74LVC1G3157.txt:1057:                                               H                             B2

So S high connects A to B2 (pin 1), S low to B1 (pin 3).  In sch_rx.py the JP101/JP102 note says "left = Q+ to B1, Q- to
B2"; with the datasheet's sense, sign(I) high then selects Q-, i.e. ERR = -sign(I) x Q rather than +sign(I) x Q as the
generator text implies.  The sign is recoverable by moving both jumpers (the note already anticipates "Move both if the loop
runs away"), so this is a documentation/default error, not a wiring error; the keyword, the comment and the jumper note
should be corrected so the documented default is the intended sign.

### 3.4 HMC536 / sch_ant.py: the A/B polarity in the notes contradicts the datasheet (MISMATCH in text)

sch_ant.py wires RF1 (pin 5) to J402 "SW TX" and RF2 (pin 8) to J403 "SW RX", and its notes say "A low = receive (ANT to
SW RX), A high = transmit" and "A low, B high: ANT-SW RX (receive).  A high, B low: ANT-SW TX (transmit)."  Datasheet:

    HMC536.txt:231:  A                   B                                  RFC to:
    HMC536.txt:233:  Low               High                                    RF1
    HMC536.txt:235:  High              Low                                     RF2

A low / B high routes RFC to RF1 = the SW TX jack (transmit); A high / B low routes RFC to RF2 = SW RX (receive).  The
symbol comment in gen/symbols.py ("A low / B high: RFC-RF1; A high / B low: RFC-RF2") is right, and PLAN.md line 690-691
("a pull-up on A and a pull-down on B (rests in receive)") is right given the pull-up on A and pull-down on B: the hardware
default is receive.  Only the two notes on the antenna sheet have it backwards; a gateware author who follows them will
drive the switch inverted.  (gateware/ has only the constraints for tr_a/tr_b so far, no sequencer.)  Either swap the two
jack names (RF1 = SW RX, RF2 = SW TX) or rewrite the notes to "A high = receive".

### 3.5 TCXO_3225 pin 1: could not verify

TC32H4-25.000-33GNDTNL_C5119013.txt is 56 lines: features, the spec table and packaging text.  There is no pin table and no
mention of what pin 1 is; the PDF's package drawing is a picture.  The symbol marks pin 1 "VC/NC" and sch_tx.py leaves it
no-connect.  Pins 2 (GND), 3 (OUT) and 4 (VDD) follow the 3225 convention and the SX3V's "Pad Functions" (160-163) on the
same footprint, but the TC32H4 itself is unverified.  Check the drawing page or the vendor before ordering: if the "GN"
in the part number denotes a voltage-control variant, pin 1 wants 1.65 V, not an open.

### 3.6 Balun terminal positions: could not verify

The "Terminal Configuration" list (5400BL15B050E.txt 15-23) is text and matches the symbol's numbering and functions.  The
figure that places terminals 1-6 on the body is a picture; gen/footprints.py's reading of it ("3, 2, 1 along the top row
left to right, 4, 5, 6 along the bottom row") cannot be checked from text.  The consequence of a wrong reading would be
GND and signal pads exchanged, so this deserves a look at the PDF page itself.

### 3.7 Cosmetic

* ADL5380: the symbol labels pins 1, 2, 5, 8 as GND1, GND2, GND3, GND4; the datasheet figure labels them GND3, GND1, GND1,
  GND4 (lines 262, 263, 266, 285) and the table lumps all ten grounds together (301).  All are ground; no effect.
* MAX2871: pin 32 is "VCC_SD" in the Pin Description (859) and "VDD_SD" in the figure (766); the symbol says VCC_SD.

## 4. Pins the schematic leaves unconnected, against what the datasheet requires

| part | pin(s) | state in the schematic | datasheet requirement | OK? |
|------|--------|------------------------|-----------------------|-----|
| PE43711 U102 | 6-13, 15 (GND) | no symbol pin, pads netless | "GND Ground" (1599) | **NO: must be grounded** |
| HMC536 U401 | paddle (pad 9) | no symbol pin, pad netless | "must also be connected to RF/DC ground" (332-334) | **NO: must be grounded** |
| PE43711 U102 | D0-D6 (1, 24, 23, 22, 21, 20, 19) | grounded | "Ground ... if not in use" (1675); "in serial mode, ground all parallel control inputs" (331-332) | yes |
| PE43711 U102 | P/S (3) | 10k to +3V3_DIG | HIGH = serial (338) | yes |
| ADL5380 U104 | 12 NC | no-connect flag | "Do not connect to this pin" (315) | yes |
| ADL5380 U104 | 19 ADJ | DNP 1.5k (open as fitted) | ">5 GHz, RADJ = open" (316-318) | yes |
| ADL5380 U104 | 7 ENBL | grounded | low = fully enabled (308) | yes |
| ADL5375 U201 | 6, 7, 13, 15 NC | no-connect flags | "can be left open or tied to ground" (392) | yes |
| ADL5375 U201 | 1 DSOP | TX_DIS + 100k pull-down | "ground or leave it floating to enable" (383-384) | yes |
| MAX2871 U115/U203 | 5 SW | no-connect flag | "No connect in Normal mode" (800-801) | yes |
| MAX2871 | 25 LD | test point only | output; no requirement | yes |
| THS4541 x4 | 9 Vocm | 100 nF to GND, no bias | open "defaults midsupply" (270) | yes |
| THS4541 x4 | 17 EP | GND | "must be connected to a power or ground plane and not floated" (194-195) | yes |
| TS5A3159 U111 | 1 NO | no-connect flag | none stated; the hold state parks ERR on this open port | acceptable |
| HMC536 U401 | 4 N/C | no-connect flag | "No connection required" (328) | yes |
| Balun T101 | 6 NC | no-connect flag | "NC" (23) | yes |
| TCXO Y201 | 1 | no-connect flag | unknown (no pin table) | could not verify (3.5) |
| SKY65404 U101 | 7 paddle | GND | exposed pad per the package drawing (414, 438) | yes |

## 5. Method notes

* `hardware/lib/CostasLink.kicad_sym` was parsed back pin by pin; it is exactly what `gen/symbols.py` emits (pin counts
  33, 25, 25, 16, 3, 7, 17, 5, 6, 6, 4, 4, 6, 8 for MAX2871, ADL5380, ADL5375, PE43711, ADL5611, SKY65404-31, THS4541,
  TLV3601, SN74LVC1G3157, TS5A3159DCK, VCXO_3225, TCXO_3225, Balun_5400, HMC536MS8G).
* Footprint pads were listed from `hardware/lib/CostasLink.pretty/*.kicad_mod` and compared with the netlist's nodes per
  reference; the two "pads with no net" findings come from that comparison, every other audited part has every pad on a net.
* Where pdftotext interleaved table columns (ADL5375 Table 3, PE43711 Table 9) the pin figures were read individually to
  confirm each number.
