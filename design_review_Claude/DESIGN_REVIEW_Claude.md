# Design review: CostasLink-PYNQ-Z2 rev A (Claude, 2026-10-09)

Scope, as instructed by the author: the brief's section 3 items 1, 2, 4, 5, 6, 7 and 9 and section 4a's
schematic checks.  The copper (items 3 and 8) was NOT reviewed: the board was being rebuilt while I worked,
and `hardware/CostasLink-PYNQ-Z2.kicad_pcb` and `mfg/release/` were not read (`mfg/release/` did not exist
at the time).  Everything below comes from the generators (`gen/*.py`), the committed netlist
(`hardware/checks/netlist.net`), `sim/budget.py` (run), `tools/net_check.py` (run), `gateware/`, the schematic
PNGs in `docs/images/`, and the datasheet PDFs in `datasheets/`, which I converted to text with `pdftotext
-layout` into `design_review_Claude/txt/` (`datasheets/txt/` held only the two AliExpress listings).  Line
numbers quoted as `txt/<part>.txt:N` refer to those files.  No other `design_review_*/` directory existed
when this was written (section 0 rule 6).

## Verdict

**Do not order yet; one evening of schematic edits, then order.**  Nothing I found is a fabrication or
assembly fault, and the RF chain, the header, the switch block, the synthesizers and the sign logic check
out against the datasheets.  But two things would stop the board doing what it is for:

1. **The Costas loop's op amp cannot work as drawn.**  The OPA2187 is a 4.5-36 V part (its own recommended
   operating conditions) with an input common-mode range that stops 2 V below its positive rail; the sheet
   runs it on +3V3_ANA with both non-inverting inputs at V_MID = 1.65 V, i.e. 1.2 V below the minimum supply
   and 0.35 V above the maximum input common mode.  The PI filter and the VC stage are the whole loop.  Swap
   the part for a 3.3 V-capable rail-to-rail zero-drift dual in the same VSSOP-8 (OPA2388 / OPA2333 class), or
   feed U112 from 5 V and bound VC.  Zero copper change, one BOM line.
2. **The "HDR 5V" supply path does not work.**  Q301 (USB-C) is a P-FET with its gate at ground: it conducts
   in both directions once +5V_IN is up, so when the board is powered from the PYNQ's header it drives
   +5V_IN back onto VBUS, which through R305 lifts Q302's gate to 0.91 x VBUS and switches the header FET
   OFF.  The header path then runs through Q302's body diode: about 4.1 V on +5V_IN (the ADL5380 and
   ADL5375 need 4.75 V), about 1 W in a SOT-23, and 4 V present on the USB-C receptacle.  The sheet's note
   ("neither supply ever feeds the other") is wrong in that direction.  Either fix the ORing (an ideal-diode
   controller on the USB path, or Q301's gate from the header side plus a small N-FET so USB still wins), or
   decide rev A is USB-C powered only and leave JP301 unfitted (the Icepi never uses the header 5 V anyway).

Everything else is a value, a note or a margin: the FDA level shift has no margin if one of the ADL5380
datasheet's two contradictory common-mode numbers is the right one (a resistor value fixes it), the SW RX
texts on the switch sheet and the silkscreen state the rest state backwards, the loop filter of the
MAX2871s was designed with 60 MHz/V where the datasheet says 100 MHz/V typical, and the USB-C 5 V margin at
the ADL53xx is 50 mV from a 5.00 V source and negative from a 4.9 V one.

## Findings table (ranked by what it costs to be wrong)

| # | Severity | Finding | Evidence | On the bench if right | Fix | Confirmed by |
|---|---|---|---|---|---|---|
| 1 | **Blocking** (the loop) | OPA2187 (U112) run on 3.3 V with inputs at 1.65 V: outside its 4.5 V minimum supply and its (V+)-2 V input common-mode limit | `txt/OPA2187.txt:338` "(V+) - (V-) Supply voltage 4.5 (+-2.25) ... 36 (+-18) V"; `:428/:507` "VCM Common-mode voltage range (V-) - 0.1 ... (V+) - 2 V"; `gen/sch_rx.py:309` flags +3V3_ANA on pin 8; netlist U112 8=+3V3_ANA, 3=V_MID, 5=V_MID | PI filter and VC stage undefined: VC stuck or wandering, no carrier lock, stage 3 of BRINGUP fails with no way to tell it from a sign error | Replace with OPA2388IDGK or OPA2333AIDGK (same VSSOP-8 pinout, 2.5/1.8-5.5 V, rail-to-rail inputs, zero drift) -- stock to check at JLCPCB; or power U112 from +5V_IN and clamp VC | datasheet text, netlist, sheet PNG |
| 2 | **Blocking** (one of the two supplies) | Header 5 V path (JP301/F302/Q302) cannot deliver: Q301's gate is grounded so it conducts +5V_IN back onto VBUS, R305 then lifts Q302's gate and turns it off; the board runs on Q302's body diode | `gen/sch_pwr.py:18-27` (gate to 100 k to ground only), `:112-117` (R305 10 k from Q302's gate to VBUS); netlist Q301 1=Net-(Q301-G) 2=+5V_IN 3=Net-(Q301-D), F301 1=VBUS | Powered from the PYNQ's header: +5V_IN about 4.1 V (5.0 - 0.08 PTC - 0.8 body diode), +5V_RF below the ADL5380/ADL5375's 4.75 V minimum, about 1 W in Q302 (SOT-23), 4 V on the USB-C receptacle | Rev A choice: (a) JP301 "do not fit", USB-C only; (b) Q301 gate from the header side (+5V_HDR via 10 k) with a 2N7002 from VBUS pulling that gate low so USB still wins; (c) an ideal-diode controller on the USB path | sheet generator, netlist, sheet PNG |
| 3 | High | FDA level shift has no margin if the ADL5380's output common mode is VS - 1.2 V = 3.8 V (its Table 1) instead of 3.2 V (its Table 4) | `txt/ADL5380.txt:138` "VADJ ~ 2.4 V (ADJ pin open)  VS - 1.2 V" vs `:2210` Table 4 "Open 2.5 3.2"; THS4541 `txt/THS4541.txt:366-369` common-mode input high "(Vs+) - 1.3 min, (Vs+) - 1.2 typ" = 2.0/2.1 V on 3.3 V | Summing nodes at 2.02 V against a 2.0 V minimum: the fast arms' CMRR/gain degrade, the comparators see a compressed, offset signal; the slow path is fed from it | Rs 1.2 k -> 1 k (node 1.87 V worst case, 1.61 typ, bandwidth 102 -> 94 MHz), both in parts.RES; or keep 1.2 k and fit R(ADJ) 1.5 k (CM 2.5 V) at the cost of 5.8 GHz gain | datasheet text, `sim/budget.py` section 7, arithmetic below |
| 4 | Medium | SW RX rest state printed backwards on the switch sheet's blue box and on the silkscreen limit | `gen/levels.py:269` `"SW_RX": "... the rest state (A low, B high)"`, `:292` LIMITS "Rest state (A low)."; the datasheet `txt/HMC536.txt:231-235` A High / B Low -> RF2 = SW RX and the pull-ups (`sch_ant.py:264`) rest A high, B low; sheet PNG shows both texts | A student reads the board and drives A low to receive: transmit path | Change the two strings in `gen/levels.py` to "(A high, B low)" | levels.py, datasheet, sheet PNG |
| 5 | Medium | USB-C 5 V margin at the ADL53xx is 50 mV from a 5.00 V source and -50 mV from 4.9 V; the budget forgets the bead's DCR | `sim/budget.py` section 9: "0.19 V, so the ADL53xx see >= 4.81 V"; BLM21PG221SN1D DCR 50 mOhm max x 0.82 A = 41 mV more | A laptop port or a thin cable: +5V_RF 4.6-4.7 V, the demodulator/modulator out of spec (not dead, gain and linearity drift) | BRINGUP: bench supply at 5.1-5.2 V and a short cable; or a USB-PD source; the budget line should include the bead | budget run, parts.py |
| 6 | Medium | Q302's "off" state relies on Vgs = -0.4 V against a threshold whose minimum is -0.5 V (AO3401A, from memory: datasheet not in the tree) | gate = 100 k / 10 k divider from VBUS = 0.91 x VBUS; with +5V_IN within 0.1 V of VBUS, Vgs = -0.4 V | Sub-threshold leakage from the board into the PYNQ's 5 V rail with both present; harmless but not the "blocked" the plan claims | Covered by the fix of #2 | arithmetic |
| 7 | Low | MAX2871 loop filter designed with Kvco 60 MHz/V; the datasheet's typical is 100 MHz/V | `txt/MAX2871.txt:152` "VCO Sensitivity 100 MHz/V"; `sim/budget.py` section 8 "Kvco 60 MHz/V" | Loop bandwidth about 100-130 kHz instead of 80 with less phase margin: locks, slightly more peaking; the 3 kHz Costas loop unaffected | Note it; re-run section 8 with 100 MHz/V for rev B | datasheet text, budget run |
| 8 | Low | TR_B's 10 k pull-down loses to the PYNQ's 2k2 pull-up: with the gateware not driving, B rests at 2.7 V, in the HMC536's undefined gap (High = 3 V +- 0.2) | `gen/sch_ant.py:264`, `gen/pins.py:68`; `txt/HMC536.txt:224` | The "rests in receive" claim holds only on the Icepi or an undriven socket; the author's note already says the path is undefined until driven | Drive TR_A/TR_B in the first clock of the gateware (already the plan); or 1 k pull-down | sheet generator, datasheet |
| 9 | Low | Cosmetic: `gen/symbols.py:180` comment says "S high: A = B1" (the keywords string and the sheet note say the opposite, correctly); HMC536 symbol's "RF2" pin name overlaps the "EP" label on the switch sheet | symbols.py; `docs/images/schematic_Antenna switch...png` | None | Fix the comment; move the EP pin | file read, PNG |

## 1. The two blocking findings

### 1.1 The OPA2187 on 3.3 V

`gen/sch_rx.py:306-312` draws U112's supply unit with `flag("+3V3_ANA", ...)` on pin 8 and ground on pin 4; the
netlist agrees (U112: 8=+3V3_ANA, 4=GND, 3=V_MID, 5=V_MID, 2 = the PI filter's summing node, 6 = the VC
summing node).  The OPA2187's datasheet (`txt/OPA2187.txt`):

* line 23: "Wide supply voltage: +-2.25 V to +-18 V ... range of 4.5 V to 36 V"
* line 338 (Recommended Operating Conditions): "(V+) - (V-)  Supply voltage  4.5 (+-2.25) ... 36 (+-18) V"
* lines 428 and 507 (both electrical tables): "VCM  Common-mode voltage range  (V-) - 0.1 ... (V+) - 2  V"
* line 1331: "...when the input is driven beyond the specified common-mode voltage range, causing the output to..."

On 3.3 V the input common mode must stay below 1.3 V; both op amps' non-inverting inputs sit at V_MID =
1.65 V (`sch_rx.py:264-276`, `:297-298`), and the inverting inputs follow them.  The part is 1.2 V below its
minimum supply AND 0.35 V above its input range.  Chopper amplifiers of this family run an internal clock
and charge pump from the supply; below the minimum nothing is promised.  PLAN.md section 4 chose it for
"zero-drift, 1 uV offset ... 550 kHz is plenty"; the supply range was not checked.  PLAN.md section 10
(the DOA list) does not list it; BRINGUP stage 3 would see "VC runs to a rail" and send the user to the
sign jumpers (item 1 of the DOA list), which would not help.

Fixes, cheapest first:

* **Same footprint, 3.3 V part.**  OPA2388IDGK (2.5-5.5 V, rail-to-rail in/out, 0.25 uV, 10 MHz) or
  OPA2333AIDGK (1.8-5.5 V, RRIO, 2 uV, 350 kHz; enough for a 3 kHz loop) are VSSOP-8 with the standard
  dual pinout (1 OUT A, 2 -IN A, 3 +IN A, 4 V-, 5 +IN B, 6 -IN B, 7 OUT B, 8 V+), i.e. a BOM-only change.
  `tools/jlc_cache.json` has no entry for either; the stock check is one `tools/jlc_api.py` call the author
  can make (it writes the cache, so I did not).
* **Keep the OPA2187, feed it from +5V_IN.**  Then VS = 4.8 V (above 4.5), VCM 1.65 V is inside 0..2.8 V.
  But the output can then reach 4.8 V on VC: the VCXO's control pin is rated 0.3-3 V (`txt/SX3V...txt:106`),
  and VC also enters the ADS1115 (abs max VDD + 0.3 = 3.6 V) through 10 k (0.12 mA into its clamp,
  survivable but out of spec).  A 3.3 V Zener or a divider on VC would be needed: more parts than the swap.

### 1.2 The header 5 V path

`gen/sch_pwr.py:18-27` (`pfet`): the AO3401A sits with its drain on the input, source on the board and gate
through 100 k to ground, nothing else.  For Q302 the gate is also pulled to VBUS through R305 10 k
(`:112-117`).  Netlist: Q301 1=Net-(Q301-G), 2=+5V_IN, 3=Net-(Q301-D); F301 1=VBUS, 2=Net-(Q301-D); Q302
likewise with F302 from JP301 pin 2.

A P-FET with its gate at ground and its source at +5 V has Vgs = -5 V whatever the drain is doing: it is a
switch that is on whenever the board has 5 V, not a diode.  Its body diode (drain to source) only matters
at start-up.  So:

* **USB-C only (JP301 open).**  Q301 on: +5V_IN = VBUS - 80 mV.  Works.  Q302 is off (gate at 0.91 x
  VBUS) and irrelevant.  This is the case the author tested in thought and BRINGUP stage 1 uses.
* **Header only (JP301 fitted, PYNQ on its barrel supply, no USB cable).**  Start: Q302's body diode lifts
  +5V_IN to VHDR - 0.8 V.  Q301's gate is at 0 V and its source at +5V_IN: Q301 turns fully on and drives
  VBUS = +5V_IN.  R305 lifts Q302's gate to 0.91 x VBUS, so Vgs(Q302) = -0.09 x +5V_IN = -0.37 V, below the
  AO3401A's threshold (Vgs(th) -0.5 to -1.3 V, quoted from memory; the AO3401A datasheet is not in the tree):
  Q302 never turns on.  The board runs through a body diode: +5V_IN = 5.0 - 0.08 - 0.8 = 4.1 V, +5V_RF
  about 4.05 V against the ADL5380's and ADL5375's 4.75 V minimum (`txt/ADL5380.txt:143`,
  `txt/ADL5375.txt:17`), 1.34 A x 0.8 V = 1.1 W in Q302's SOT-23, and 4 V on the USB-C receptacle's VBUS
  pins behind an Rd that announces a sink.
* **Both present.**  Q301 on, Q302 off (good: USB wins), but Q302's body diode conducts whenever the PYNQ's
  5 V exceeds VBUS - 80 mV + 0.7 V: fine.

The note on the sheet ("Q302 turns off whenever USB-C 5 V is present ... so neither supply ever feeds the
other", `sch_pwr.py:118-119`) and PLAN.md section 6 ("both inputs blocked from each other") describe the
USB-only case correctly and the header case not at all.  The plan's reason for the P-FET over a Schottky
(the ADL53xx's 4.75 V) is exactly what the header case loses.

Rev A options, cheapest first:

1. **Declare rev A USB-C powered.**  JP301 "do not fit" on the silkscreen and in the README; keep F302/Q302
   as placed (harmless unfitted jumper).  The Icepi case already uses USB-C (`gen/pins.py:22`).  Nothing else
   changes.
2. **Make Q301 block the reverse.**  Q301's gate from the header side (+5V_HDR after JP301 through 10 k, 100 k
   to ground stays) and a 2N7002 (Basic) whose gate is VBUS through 10 k and whose drain pulls Q301's gate low:
   USB present -> Q301 on, Q302 off (USB wins); header only -> Q301 off, VBUS stays 0, Q302 on (4.8 V);
   both -> USB.  Two parts, four nets, no RF copper touched.
3. **An ideal-diode controller** (LM66100-class, SC70-6, 1.5 A) on the USB path in place of Q301: cleanest,
   needs a stock check.

## 2. The control senses (brief section 3 item 1), each against the datasheet text

| Part | Claim on the sheet | Datasheet text | Verdict |
|---|---|---|---|
| HMC536 (U401) | A low, B high: ANT-RF1 = SW TX; A high, B low: ANT-RF2 = SW RX; pads 3/5/8 = RFC/RF1/RF2; pull-up on A, pull-down on B rests it in receive | `txt/HMC536.txt:229-235` Truth Table "A Low, B High -> RFC to RF1; A High, B Low -> RF2"; `:326` "3, 5, 8  RFC, RF1, RF2"; `:237` "DC blocks are required at ports RFC, RF1, RF2" | **Correct** (the note on sheet 5 and `sch_ant.py:241-244, 264`).  The blue box and the silkscreen limit say the opposite: finding 4.  Resting state on the PYNQ is undefined, not receive: finding 8.  Three DC blocks present (C401-C403). |
| SN74LVC1G3157 (U110) | S low: A-B1 (pin 3); S high: A-B2 (pin 1); JP101 right = Q- to B1, JP102 left = Q+ to B2 -> ERR = sign(I) x Q | `txt/SN74LVC1G3157.txt:138-140` "B2 pin 1 ... Set S high to enable; B1 pin 3 ... Set S low to enable"; `:1048-1049` "If the control input is low, B1 channel is selected. If high, B2" | **Correct.**  S = CMP_I = sign(I) (U107: IN+ = I_P, IN- = I_N, netlist): I > 0 -> B2 = Q+, I < 0 -> B1 = Q-.  Whether +sign(I).Q or -sign(I).Q locks depends on the ADL5380's Q sign convention, which the datasheet does not state as a sign; the two jumpers cover both cases (sheet note at `sch_rx.py:216-218`, BRINGUP stage 3 step 3).  U112A inverts, U112B inverts: net non-inverting, VC up = LO up (VCXO pull is positive: 0.3-3 V for -100..+100 ppm, `txt/SX3V...txt:96-106`). |
| TS5A3159 (U111) | LOOP_HOLD high opens the integrator's input; NC (pin 3) carries the signal, NO (pin 1) open | `txt/TS5A3159.txt:146-151` "1 NO Normally open; 3 NC Normally closed; 4 COM; 6 IN  High = COM connected to NO; Low = COM connected to NC" | **Correct.**  100 k pull-down on IN: loop closed by default; high parks COM on the floating NO pin = hold.  Netlist U111 1=unconnected, 3=Net-(U111-NC), 4=ERR, 6=LOOP_HOLD. |
| ADL5375-05 (U201) DSOP | TX_DIS high mutes in 100 ns; 100 k pull-down | `txt/ADL5375.txt:383` "DSOP  Output Disable. A logic high on this pin disables the RF output. Connect this pin to ground or leave it [open]"; `:293-296` turn-off 100 ns, turn-on 220 ns, high >= 2.0 V | **Correct** (sheet says 200 ns to restore; datasheet 220). |
| ADL5380 (U104) ADJ, ENBL | ADJ open at 5.8 GHz, DNP 1.5 k to +5V_RF; ENBL grounded | `:316-317` "For operation >5 GHz, RADJ = open"; `:308` "ENBL  When pulled low, the part is fully enabled; when pulled high, the part is [disabled]"; `:144-145` currents | **Correct.**  ENBL low = on (netlist U104 7=GND).  Common mode: finding 3. |
| PE43711 (U102) | serial mode P/S high (10 k to +3V3_DIG); D0-D6 grounded; LE/CLK/SI on 16/17/18; RF1 in (5), RF2 out (14); powers up at 31.75 dB | `txt/PE43711.txt:1585-1640` Table 9: 1 D0, 2 VDD, 3 P/S, 4/6-13/15 GND, 5 RF1 (input), 14 RF2 (output), 16 LE, 17 CLK, 18 SI, 19-24 D6..D1; `:336-338` "P/S = HIGH selects the serial interface"; `:331-332` "When using the DSA in serial mode, ground all parallel control inputs"; `:381` "Serial data is clocked in LSB first"; `:383-385` load with LE LOW, latch by LE HIGH then LOW; `:402` "Serial bit D[7] must be set to logic low"; `:338-340` 31.75 dB at power-up | **Correct**, including the gateware: `spi_master.v:7` "PE43711 DSA -- 8 bits LSB first (D0 first)", `costaslink_regs.v:100` `.nbits(m_dsa ? 8 : 32), .lsb_first(m_dsa)`.  Digital input abs max 3.6 V (`:74`): 3.3 V logic fine.  VDD on +3V3_ANA, P/S pulled to +3V3_DIG: two rails, harmless through 10 k. |
| MAX2871 (U115/U203) | CE and RFOUT_EN 10 k up; LE active on its rising edge; MUX = lock detect; RSET 5.1 k, CP = 7 -> 2.56 mA | `txt/MAX2871.txt:790-859` pin table matches `symbols.py:62-73` pin for pin (1 CLK, 2 DATA, 3 LE, 4 CE, 5 SW, ..., 29 REF_IN, 30 MUX); `:798` "CE  A logic-low powers the part down"; `:848` "RFOUT_EN  A logic-low disables the RF outputs"; `:795-796` LE high loads the register; `:842` "ICP = 1.63/RSET x (1 + CP[3:0])" = 1.63/5100 x 8 = 2.56 mA; `:124` REF_IN 0.7 V p-p to VCC p-p; `:250` 27 nH to VCC_RF | **Correct.**  Register words decoded by hand: R0 = 80740000 (INT, N = 232), R2 = 18004F42 (MUX 110 = digital LD, R = 1, CP = 7, LDF = 1 integer-N, PDP = 1 positive for a passive filter, `:1004-1007`), R4 = 618F426C (FB = 1, DIVA = 0, BS = 500 -> 50 kHz, RFA_EN, APWR 01 = -1 dBm), R5 = 61400005 (LD = 01 digital).  The budget's Kvco: finding 7. |

## 3. The loop arithmetic (brief section 3 item 2), re-derived

* ADL5380 at -20 dBm in: 22.4 mV rms; x1.95 -> 43.6 mV rms differential; THS4541 x4 -> 175 mV rms = 247 mV
  peak.  Budget says 176 mV rms / 249 mV: agrees.  K_d = 0.25 V/rad (ERR = A sin(phi) around lock): agrees.
* VCXO: +-100 ppm over 0.3-3.0 V = 1.16 MHz / 2.7 V = 430 kHz/V at 5.8 GHz -> K_o = 2.70e6 rad/s/V: agrees
  (`txt/SX3V25...txt:96-106`: pulling range +-100 ppm min, control 0.3-3 V, centre 1.65 V, CMOS output).
* PI filter: F(s) = (1 + s R2 C)/(s R1 C) after the second inversion; w_n = sqrt(K_d K_o / R1 C) -> R1 =
  0.25 x 2.7e6 / (18850^2 x 100 nF) = 19.0 k; zeta = w_n R2 C / 2 = 0.7 -> R2 = 743 ohm.  `gen/levels.VAL`
  maps 18.9 k to the parts table's nearest key, which is **20 k** (there is no 18 k in `parts.RES`): f_n
  becomes 2.9 kHz, zeta 0.68.  Fine, but the sheet note prints "R1 20k" next to "fn 3 kHz" from a 18.9 k
  computation; a reader will not reproduce it.  R2 = 750 present.  C = 100 nF C0G 1206 (C170182): right.
* Summing stage: VC = 3 V_MID - V_filter - VC_OFF = 3.3 - V_filter with VC_OFF at 1.65: non-inverting
  about V_MID, VC_OFF adds -1 V per +1 V as the blue box says.
* Acquisition: two TCXOs at +-2.5 ppm differ by at most 29 kHz; the VCXO reaches +-580 kHz; type-2 pull-in
  from 29 kHz ~ (dw)^2 / (2 zeta w_n^3) = 3.5 ms: agrees with the budget's 3.8 ms.  Lock range 2 zeta w_n =
  4.2 kHz; the FPGA re-steps the PLL when VC nears a rail (BRINGUP stage 4).
* Fast arm: Rg 1 k, Rf 4 k, Rs 1.2 k -> gain 4, noise gain 8.3, 850 MHz / 8.3 = 102 MHz, 3.4 ns rise:
  agrees.  Comparator floor 20 mV peak -> -81 dBm at the antenna with the DSA at 0: agrees with the chain
  (13 + 28.6 + 5.8 dB + 12 dB of FDA gain).
* Level shift: see finding 3 and the table of node voltages:

  | Rs | ADL5380 CM 3.2 V (Table 4) | CM 3.8 V (Table 1) | I per demod pin | noise gain -> BW |
  |---|---|---|---|---|
  | 1.2 k (as drawn) | 1.73 V | **2.02 V** (limit 2.0 min / 2.1 typ) | 1.5 / 1.8 mA | 8.3 -> 102 MHz |
  | 1 k | 1.61 V | 1.87 V | 1.6 / 1.9 mA | 9.0 -> 94 MHz |
  | 820 | 1.46 V | 1.71 V | 1.7 / 2.1 mA | 9.9 -> 86 MHz |

  Table 4 of the ADL5380 datasheet is internally consistent (a smooth 0.42 V per volt of VADJ through the
  "open" row at 3.2 V), so the author's 3.2 V is probably right and Table 1's "VS - 1.2" probably a typo for
  "VS - 1.8"; but the only evidence either way is the same datasheet, and 1 k costs 8 MHz of bandwidth.  The
  ADL5380's outputs can supply the DC: "Peak Output Current, each pin 12 mA" (`:141`).
* TX ladder: 2.2 k + 200 (PYNQ) x 2 and 300 to Vr = 0.213 V: 0.17 / 0.50 / 0.83 V, inside the ADL5375-05's
  "Absolute Voltage Level 0 to 1 V" (`txt/ADL5375.txt:283`) and the 0-2 V absolute maximum (`:317`); IBBN/QBBN
  at 3.3 x 1/6.1 = 0.54 V.  On the Icepi 0.167 / 0.521 / 0.874 V: still inside.  Agrees.
* DSA target -20 dBm at the demodulator: the second ADL5611 then runs 30 dB under its P1dB; the strongest
  bench input (3 m, -43 dBm) with the DSA at 0 dB gives -1.4 dBm at the demodulator (IP1dB 11.6): the FPGA
  has 31.75 dB to spend before anything compresses.

## 4. The header and the two FPGA boards (item 4)

* `gen/pins.py` self-checks pass (28 distinct Zynq pins, 8 grounds, CMP_I on 18 and TRIG_IN on 26 are the
  only pins clock-capable on both, fast inputs off the Icepi's bank 0).  Every FPGA signal's direction in
  OUTPUTS/INPUTS matches its use on the sheets (TX bits, SPI, LEs, LOOP_HOLD/SEL, TX_DIS, TRIG_A/B, TR_A/B
  out; CMP_*, TRIG_IN, MUX_* in; I2C bidirectional).
* 33 ohm series on all six comparator outputs (`sch_rx.py:143,176`, `sch_slow.py:281,307`) and on TRIG A/B and
  REF OUT.  TRIG IN: 1 k into a 74LVC1G17 (input abs max 6.5 V; silkscreen says 5.5 V: conservative), JP202
  50 ohm.  I2C pull-ups DNP 4.7 k, the PYNQ's 2k2 assumed.
* Back-feed: finding 2 (header -> USB-C receptacle), finding 6 (USB -> header leakage margin).
* The socket's pin 1 position and the silkscreen on the back are copper: not reviewed.

## 5. Power (item 5)

* Budget section 9 reproduced: 1.34 A total; LDOs 0.25 W (PLL, behind 2.2 ohm: 0.44 V dropped in a 1206
  rated 0.25 W, carrying 0.09 W), 0.03-0.10 W the rest; TPS7A20 input after the 2.2 ohm at 4.36 V (4.8 - 0.44)
  with 0.3 V of dropout margin, still fine at a 4.5 V source.
* The bead BLM21PG221SN1D is rated 2 A; DCR 50 mOhm max x 0.82 A = 41 mV: budget omits it (finding 5).
* +5V_RF after PTC + FET + bead: 4.80 V from exactly 5.00 V, 4.70 V from 4.90 V.  The ADL53xx's 4.75 V
  minimum is met only from a good source.  BRINGUP stage 1 uses a bench supply: set it to 5.1-5.2 V.
* Every supply pin has a 100 nF through `supply_bar`; the MAX2871s get 6 x 100 nF + 10 uF; the ADL5380/5375
  three/two 100 nF + 1 uF; the three MAX2871 filter pins 1 uF each (`:835,843,844`); REF_IN 100 nF; the
  SKY65404 0.6 nH + 100 nF (its application circuit, `txt/SKY65404-31.txt:307-319`).
* TVS D303 SMAJ5.0A: netlist pin 1 = +5V_IN, pin 2 = GND; KiCad's D_SMA pad 1 is the cathode: correct.
  LEDs D301/D302: pin 1 (cathode) = GND: correct.  Capacitor codes: 22 uF CL21A226MAQNNNE and 10 uF
  CL21A106KAYNNNE are 25 V, the 0603 2.2/4.7 uF 16 V, 100 nF 16 V: all fine on 5 V.  C0G/NP0 where it
  matters: 0.5 pF, 1.5 pF blocks, 68 pF, the five PLL filter values, the 100 nF 1206 integrator.
* In2 pours: copper, not reviewed.

## 6. The parts (item 6), what could be checked without the release

* The three consigned parts' numbers (ADL5380ACPZ-R7, ADL5375-05ACPZ-R7, 5400BL15B0050001E) are the ones the
  datasheets name; the balun is the ADL5380 datasheet's own 5.8 GHz part (`txt/ADL5380.txt:1215`) and its
  terminals (1 unbalanced, 2 GND, 3/4 balanced, 5 GND, 6 NC, `txt/5400BL15B050E.txt:14-23`) match the
  symbol and `sch_rx.py:92-96`.
* PE43711 pin table, HMC536 pin table, MAX2871 pin table, ADL5375 and ADL5380 pin tables, SKY65404 (1
  V_ENABLE, 2 GND, 3 RF_IN, 4 RF_OUT, 5 GND, 6 VCC), THS4541 (FB- 1, FB+ 4, Vocm 9, PD 12; "connect external
  resistors from the FB- pin to the IN+ pins, and the FB+ pin to the IN- pins", `txt/THS4541.txt:2878`),
  TLV3601 DCK (1 OUT, 2 VEE, 3 IN+, 4 IN-, 5 VCC), TS5A3159, SN74LVC1G3157: every number in `gen/symbols.py`
  matches the datasheet's table.  The ADL5611 choke value (43 nH, Table 6) I could not find in the text
  (the table did not survive pdftotext); its 5.8 GHz gain +14.8 dB (`txt/ADL5611.txt:284`) and 124 mA max
  (`:204`) agree with the budget.
* TCXO TC32H4: the text (`txt/TC32H4...txt`) is one page with no pin table, as the author says; LVCMOS
  output, 90 %/10 % Vcc levels, so it drives REF_IN directly through the 100 nF.  VCXO SX3V: CMOS output,
  centre 1.65 V, 0.3-3 V, +-100 ppm min, APR +-50 ppm.
* `mfg/release/` (BOM, CPL, FOOTPRINT_CHECK, CONSIGNMENT, COST) did not exist while I worked: not checked.
* KT-0603R is a red LED under the parts key "LED_G": cosmetic.

## 7. The sheets as claims (item 7)

Read on the PNGs and in `gen/levels.py`:

* Wrong: `SW_RX` box and `SW RX` limit (finding 4).
* `REF_RX` box: "through 100 nF into REF_IN (0.7 V p-p min)": right (`txt/MAX2871.txt:124`).  `REF IN` limit
  "0.7-3.3 Vpp": right (sensitivity 0.7 to VCC p-p).
* `RX ANT` "ABS MAX +1 dBm": right (`txt/SKY65404-31.txt:88-90`: +1 dBm enabled, +10 dBm disabled).
* `ANT` / `SW TX` "+29 dBm MAX": the datasheet's absolute-maximum "Hot Switch Power Level +29 dBm (Vctl =
  +3V)" (`txt/HMC536.txt:216-218`): right.
* `TRIG IN` 5.5 V MAX, `TRIG A/B` 2 V into 50 ohm, `CMP I MON` /10, `REF OUT` 1.6 V p-p into 50 ohm: right
  within 10 %.
* PI filter note prints R1 as the parts key (20 k) beside f_n 3 kHz computed with 18.9 k (section 3).
* Switch sheet title/note say "A HIGH, B low = receive": right.  "Both come up high behind the PYNQ's 2k2
  pull-ups": right, and it also defeats the 10 k pull-down's "rest in receive" (finding 8).
* USB-C note: "1.3 A at most" on the sheet, "1.5 A at most" in LIMITS: pick one.
* Nothing in the loop region, the DAC/ADC region or the power inputs overlaps or contradicts the netlist
  on the crops I looked at (`crop_pwr_inputs.png`, `crop_rx_loop.png`, `crop_ant.png` in this directory).

## 8. Section 4a's claims, tested

| Claim | Result |
|---|---|
| One-pin nets: none | `tools/net_check.py`: "340 parts, 247 nets, 0 problems"; eleven paths walked ok (`net_check_out.txt`) |
| One name per rail | GND 279, +5V_IN 21, +5V_RF 29, +5V_HDR 3, +3V3_ANA 41, _DIG 37, _OSC 8, _PLL_RX 23, _PLL_TX 23 pins; VBUS is a label net (USB A4/A9/B4/B9, F301, R305).  No stray `+3.3V`/`VCC` |
| One ground | GND only in the netlist |
| Copied blocks carry their names | I_P/I_N, Q_P/Q_N, Is_P/Is_N, Qs_P/Qs_N, V_T / V_T2, I_OFF / Q_OFF / I_OFF_F: no unsuffixed survivor |
| Fuse on every input | F301, F302 (MF-MSMF200-2, 2 A hold / 4 A trip) |
| Two supplies, two blocking elements | **Fails** in one direction: finding 2 |
| Series R on connector logic inputs | TRIG IN 1 k; REF IN AC-coupled |
| Polarized parts, ratings | TVS, LEDs, 10/22 uF 25 V: right (section 5) |
| No floating inputs | TS5A3159 NO open (an analog switch's unused port: fine); 74LVC2G34 both inputs driven; 74LVC1G17 x2 driven; MAX2871 SW no-connect (`:800`, optional); ADL5380 pin 12 NC; ADL5375 6/7/13/15 NC; PE43711 D0-D6 grounded as the datasheet asks; THS4541 PD 10 k up; TCXO pin 1 open (known) |
| Values asserted | budget runs clean; `levels.VAL` maps to parts keys (R1 18.9 k -> 20 k noted) |
| Blue boxes on every wire; limits at every connector | present; one wrong (finding 4) |
| Symbols vs datasheets | every pin number checked here (section 6) |

## 9. What would make it come back dead that the author has not listed (item 9)

1. The OPA2187's supply (finding 1): not in PLAN.md section 10; BRINGUP stage 3 would misdiagnose it as a
   sign error.
2. The header 5 V path (finding 2): section 10 has no power-path item; stage 1 is USB-only and would pass.
3. The ADL5380 common-mode ambiguity (finding 3) is item 3 of section 10 but with a 0.37 V margin that may
   be -0.02 V.

Not dead but worth a line in BRINGUP: stage 1's supply at 5.1-5.2 V (finding 5); stage 2's MAX2871 loop
response will be faster than the 80 kHz computed (finding 7).

## 10. Not reviewed, and why

The copper (section 3 items 3 and 8: line widths, the balun and demodulator pins, the couplers, the LO pairs,
the via grids, the socket's pin 1, the gerbers, CPL, order settings) at the author's instruction: the board
was being rebuilt during this review.  `mfg/release/` was absent.  The JLCPCB rotation question is deferred by
the author.  No other reviewer's directory existed to compare with.
