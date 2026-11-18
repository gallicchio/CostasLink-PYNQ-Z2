# Design review: CostasLink-PYNQ-Z2 rev A

Reviewer: Grok4.7
Date: 2026-10-11
Build under review: 2026-10-10 20:01, as stated in `DESIGN_REVIEW_PROMPT.md`
Directory: `design_review_Grok4.7/`
Coordinates below are millimetres from the board's top-left corner, as `build/placement.json` gives them (KiCad's absolute origin is 25 mm down and right of that corner).

## Verdict

**Do not order it as the USB-C radio the sheets describe.** The one number that decides it: the ADL5380, the ADL5375 and the ADL5611 are specified from 4.75 V, and the input path cannot deliver that from a USB source that is itself only guaranteed to 4.75 V. Bourns' MF-MSMF200 R1max is 70 mΩ and the AO3401A's RDS(on) maximum at VGS = −4.5 V is 60 mΩ, so at 1.34 A the on-board drop is already 174 mV before the cable and before the ferrite. A source at 4.75 V therefore arrives at the chips at 4.58 V or lower. A stiff 5.25 V bench supply on a short lead still clears 4.75 V, so the copper is not scrap and a respin is not required for a bench bring-up. It is required before anyone plugs in a laptop port or a power bank and expects the numbers in PLAN.md §3. Write that limit into BRINGUP, or change the input, before paying for assembly.

Nothing else I checked kills the board by itself. The Costas sign is jumper-selectable. The loop bandwidth is not what the plan says: the detector only sees one side of the Q pair, so the fitted loop is 2.05 kHz and zeta 0.48, not 3 kHz and 0.7. That is two resistors, or a corrected sentence, not a respin. The transmitter mute is real, the 5.8 GHz lines are the width the stack formula asked for, and DRC and ERC are actually zero. The next things that would cost a respin if the bring-up goes badly are the demodulator and modulator paddles (4 vias where the ADL5380 datasheet asks for 9) and the FDA common-mode margin (130 mV at the nominal point, about 17 mV at the supply corners).

## Findings

| # | Severity | Finding | Where | Evidence | Confirmed by | Fix |
|---|----------|---------|-------|----------|--------------|-----|
| 1 | would cost a respin if USB-C is the supply; a day if the bench supply is written down first | The 5 V path does not keep the RF chips inside 4.75 V from the USB source the board is built around. | `gen/sch_pwr.py` note at the +5V_RF flag; F301, Q301, FB301; ADL5380 U104 (24.85, 60), ADL5375 U201 (56, 38), ADL5611 U103/U117/U202 | ADL5380 Table 1, ADL5375 p.1, ADL5611 Table: 4.75–5.25 V. MF-MSMF200 R1max 70 mΩ, Ihold 2.00 A at 23 °C, 1.29 A at 85 °C (`design_review_Grok4.7/ds/mf-msmf.txt`). AO3401A RDS(on) max 60 mΩ at VGS=−4.5 V (`ds/ao3401a.txt`). (70+60) mΩ × 1.34 A = 174 mV. | Read the sheet note, `sim/budget.py` §9, both datasheets, and the placed parts. Did not get the Murata bead PDF (the URL returned HTML); the bead is extra drop, not required for the conclusion. | Before ordering: either strike USB-C as a power source and require a 5.15–5.25 V stiff supply on a short lead, with +5V_RF measured above 4.85 V in BRINGUP stage 1, or change the input (lower-drop FET, PTC off the RF path, or a boost to a regulated 5.1 V). Do not discover this on two assembled boards. |
| 2 | would cost a day, or a respin if the arms are already distorted and the DNP pad is not the cure | The fast-arm summing nodes sit 130 mV under the THS4541's guaranteed common-mode limit, and 17 mV under it if the demodulator's common mode tracks VS−1.2 at VS = 5.25 V. The sheet note quotes the other datasheet number. | `gen/sch_rx.py` ADL5380 note and the DNP 1.5 k on ADJ; `sim/budget.py` §7, Rs = Rf/4 = 1 k; U105, U106 | ADL5380 Table 1, ADJ open: common mode VS−1.2 (3.8 V at 5 V), typical, no min/max. Table 4 says ~3.2 V for ADJ open. THS4541 3 V table: common-mode input high, <3 dB CMRR degradation, minimum (Vs+)−1.3 V over −40 to +125 °C. At 3.3 V that limit is 2.00 V. Calculated node is 1.87 V at 3.8 V common mode. | Ran `sim/budget.py` (it asserts 1.87 V against 2.1−0.12, i.e. the typical limit, not the guaranteed one) and read both tables. | At first power, measure the THS4541 input pins (needle on the 1 k shunt). If they are above about 1.95 V, fit the DNP 1.5 k from ADJ to +5V_RF and accept that 5.8 GHz gain and IP1dB leave the characterized condition (ADJ open). Do not trust the sheet's "3.2 V". |
| 3 | would cost a respin if the LNA oscillates or the demodulator overheats in a box; a day to measure | ADL5380 and ADL5375 paddles have 4 vias. The ADL5380 datasheet asks for nine. The SKY65404 paddle has none under it; the nearest ground via is 1.1 mm from the die centre. | U104 (24.85, 60) and U201 (56, 38): four 0.25 mm vias at ±0.5 mm. U101 (24.5, 15): paddle 1.3 × 0.8 mm, no via inside it. | ADL5380 applications text: stitch the paddle with nine vias. Counted on the shipped board with pcbnew (`pcb_audit2` / a via-distance script in this directory). | pcbnew on `hardware/CostasLink-PYNQ-Z2.kicad_pcb`, read-only. | Bring-up: feel the demodulator and look for 5.8 GHz oscillation on RX MON with the antenna terminated. If either fails, the fix is a respin of the paddle vias, not a jumper. |
| 4 | would cost a day | The budget's TX compression check uses 16.0 dBm. The ADL5611 row at 5800 MHz is 12.8 dBm. The QPSK corners land on that point. | `sim/budget.py` `gb_p1db_dBm=16.0`; `build/txt/ADL5611.txt` FREQUENCY = 5800 MHz, P1dB 12.8 dBm, gain 14.3 dB. Pi pad R210/R211/R213 area, TX chain at x = 56. | Axis point +9.8 dBm is 3.0 dB below 12.8. A corner is +3 dB on the baseband vector, so +12.8 dBm, on the compression point. CLAUDE_PCB.md §14 already says this; the assertion does not, because it was given the 6 GHz-band figure. | Read the 5800 MHz row and the assertion. `budget.py` exits 0, which is the problem. | If the constellation shape matters, fit the pi pad for 3 dB before trusting corner amplitudes. Fix the 16.0 in `budget.py` so the gate can fail. Sign decisions still work. |
| 5 | would cost a day | The ladder is centred on 0.500 V. The N inputs sit near 0.61 V, not 0.50 V, so the printed Vr of 0.213 V leaves about 100 mV of differential offset at the "zero" code. Still inside the DAC. | `gen/sch_tx.py` VN_0V5 divider (5.1 k / 1 k); `sim/budget.py` §1 applies the 41 µA bias only to the ladder node | Unloaded divider: 3.3 × 1/6.1 = 0.541 V, Thevenin 836 Ω. Both N pins source 41 µA each (ADL5375), 82 µA × 836 Ω = 69 mV, so VN_0V5 ≈ 0.610 V. The P node lifts only 10 mV. Offset ≈ 100 mV. Vr = 0.34 V recentres it; the MCP4728 can do that. | Recomputed after reading Gemini's bias-current note and checking it against the budget's own 41 µA. | Null the carrier. Do not load 0.213 V and expect a null. Say so in BRINGUP stage 2. |
| 6 | would cost a day | Every window comparator reads high from power-up until the FPGA writes the AD5696R. That is safe for the transmitter and unsafe for any event count taken before that write. | Sheet 7, U605; `gen/sch_win.py` note; `gateware/costaslink_regs.v` reset `ctrl_tx_dis <= 1` | AD5696R: RSTSEL high powers up at midscale. GAIN low, VREF 2.5 V, midscale 1.25 V. Arms sit at 1.65 V. Comparators are I_P > V_TIP, so both sides of each window are high. TX_EN is held low by R227 (1 k) and the core resets TX_DIS to 1, and the top inverts that to TX_EN. | Read the straps, the AD5696R pin table, and the reset assignment. The testbench asserts TX_DIS comes up high. | Bring-up and the driver must write the four thresholds, and read them back, before enabling the decoder or TX_EN. The hardware already refuses to transmit. |
| 7 | cosmetic for the bench; would cost a day in a hot box | The PTC's hold current falls to 1.29 A at 85 °C (MF-MSMF200/8X). The board draws 1.34 A, and the PTC dissipates about 0.13 W at R1max, so it heats itself. | F301, F302, `ds/mf-msmf.txt` thermal derating table | Ihold 2.00 A at 23 °C, 1.78 A at 40 °C, 1.50 A at 60 °C, 1.45 A at 70 °C, 1.29 A at 85 °C. | Read the Bourns table. The JLCPCB code is MF-MSMF200-2; the /8X, /12X and /16X rows share R1max 70 mΩ and Ihold 2.00 A. | On the bench, fine. In an enclosure in the sun, measure the PTC and do not enclose the board until +5V_RF is known at temperature. |
| 8 | would cost a day (two 0402s), not a respin | The Costas detector gain in the budget is the differential arm amplitude. The loop only sees one side of that pair. Fitted fn is 2.05 kHz and zeta is 0.48, not 3 kHz and 0.7. | `sim/budget.py` §6, `Kd = A_bb` with `A_bb = vcmp_rms * 1.414` (0.249 V). U110 selects Q_P or Q_N. Fitted R1 is 20 k, R2 750 Ω, C 100 nF. | Each leg is V_MID ± v/2. ERR, relative to V_MID, is v/2, so Kd is 0.124 V/rad, not 0.249. With the fitted 20 k: wn = sqrt(Kd·Ko/R1·C) gives fn = 2.05 kHz, zeta = τ2·wn/2 = 0.48. The loop is stable. Pull-in stretches by about 2.8×. | Re-derived from the budget equations and the switch wiring after GPT-5.6Terra's note. Their `costas_gain_check.txt` matches (2.053 kHz, 0.484). | Change R1 from 20 k to 10 k (calculated 9.4 k) if 3 kHz and zeta 0.7 are required. Or leave it and stop quoting 3 kHz. Not a reason to hold the boards. |
| 9 | would kill the LNA in one advertised configuration; not a bare-board fault | A +30 dBm PA through the HMC536, with no limiter, exceeds the SKY65404's +1 dBm absolute maximum on the off-port leak, and exceeds the switch's guaranteed P0.1 dB. | U401, J401–J403; `sim/budget.py` §2b already says a +27 dBm PA "wants a limiter" | HMC536 isolation minimum 26 dB at 5–6 GHz, P0.1 dB minimum +27 dBm at 3 V control. +29.8 dBm − 26 dB = +3.8 dBm at the LNA. Abs max is +1 dBm. Bare board: +9.8 − 26 = −16 dBm, fine. | Read the HMC536 electrical table and the budget's own leak line. GPT-5.6Terra has the same arithmetic. | Do not combine the PA module with the one-antenna switch until a limiter is ahead of U101, or keep the PA at the panel on its own antenna. Write that in BRINGUP before the hill, not as a respin of this order. |

## 1. The 5 V path, in numbers

The sheet note (`gen/sch_pwr.py`, the +5V_RF paragraph) says 80 mV in the FET and 100 mV in the PTC leave 4.8 V from a 5.0 V source. That is a typical-case sentence. The parts' maxima, at the budget's 1.34 A:

| drop | resistance | at 1.34 A |
|---|---|---|
| F301, MF-MSMF200 R1max | 70 mΩ | 94 mV |
| Q301, AO3401A max at VGS=−4.5 V, 25 °C | 60 mΩ | 80 mV |
| sum, before cable and bead | 130 mΩ | 174 mV |

A USB-C source's vSafe5V minimum is 4.75 V at the source receptacle. 4.75 − 0.174 = 4.58 V at +5V_IN, and the RF chips are after FB301. A 1 m cable is more. 24 AWG VBUS is about 84 mΩ/m; a round trip of 2 m is 0.17 Ω and another 0.23 V at 1.34 A, which puts the chips near 4.3 V. Cheap 28 AWG cables are worse. The ADL5380 Table 1, the ADL5375, and the ADL5611 all stop at 4.75 V. Below that the gain, the output power and the noise figure are no longer the numbers PLAN.md quotes.

The same path from a bench supply set to 5.25 V, through 15 cm of cable (about 30 mΩ, 40 mV), is 5.25 − 0.04 − 0.17 = 5.04 V before the bead. That works. So this is not "the boards will come back dead." It is "the power input drawn on the sheet does not do what the note says."

Two smaller errors sit on the same note. It says "both ADL5611 (124 mA each)." There are three (U103, U117, U202); the budget's 372 mA is the right count, and the 2 A bead still has room. And the 60 mΩ is a 25 °C maximum. RDS(on) rises with temperature; the 174 mV is not the hot number.

The ideal-diode orientation is the right one (drain toward the connector, source toward the board), and the Q303 / 1 k gate lift that stops header power from running back onto VBUS is the circuit the note describes. I did not find a second back-feed path through the power FETs. Signal back-feed into an unpowered PYNQ is limited by the header's 200 Ω and by R227; it is not what decides the order.

CC 5.1 k on both CC pins is the correct sink advertisement. It asks for 5 V. It does not reserve 1.5 A or 3 A; the source's Rp does that. A default USB port may legally collapse or disconnect at 1.34 A. A PD-only power bank may not turn on at all.

## 2. The fast arms' common mode

`sim/budget.py` sets `dem_out_cm_V=3.8` and comments that Table 1 says VS−1.2 while Table 4 says 3.2, and that the review took the worse. The sheet note still says 3.2 V. The resistors were changed for 3.8 V (Rs from 1.2 k to 1 k). The two documents disagree, and the arithmetic follows Table 1.

Node voltage, ignoring the 9–12 µA input bias (about 5 mV on the 444 Ω node, negligible):

Vn = (Vcm/Rg + Vocm/Rf) / (1/Rg + 1/Rf + 1/Rs)

Rg = Rf/4 = Rs = 1 k, Vocm = 1.65 V:

| Vcm | Vn | limit, 3.3 − 1.3 |
|---|---|---|
| 3.2 V (Table 4) | 1.61 V | 0.39 V of margin |
| 3.8 V (Table 1 at VS = 5.0) | 1.87 V | 0.13 V |
| 4.05 V (VS−1.2 at VS = 5.25) | 1.98 V | 0.02 V |

The THS4541 number is the guaranteed minimum of the common-mode-high limit, not the typical (Vs+)−1.2. The budget's assertion uses the typical. Differential swing does not move the input pins much; a common-mode excursion of the demodulator outputs does, at 0.44 V per volt. The DNP 1.5 k to +5V_RF is the escape hatch, and the datasheet's 5–6 GHz table is taken with ADJ open, so fitting it is a gain change, not a free fix. There is no test point on the summing node. That is the pin to needle on stage 1, before blaming the loop.

At the DSA's regulated level the comparators see ±249 mV peak differential against about 20 mV of offset plus hysteresis. That margin is real if the FDA is still linear. It is not real if the input stage has already given up.

## 3. Paddles and the 5.8 GHz copper

What I measured on the shipped board, with KiCad 10.0.6's pcbnew, not from the generator:

- Sixteen top-layer tracks near 0.29 mm and longer than 3 mm have L2 ground under every midpoint I sampled. The "unbroken L2" claim holds on the RF paths.
- The ground pour starts 0.205 mm from the edge of those tracks, not the 0.25 mm the CPWG formula was solved at. `sim/rf_lines.py` gives 49.8 Ω at a 0.25 mm gap and 47.7 Ω at 0.20 mm. That is a 1.05:1 VSWR. Not a reason to stop.
- No near-90° corner on those tracks.
- CP101 (24.0, 49.6) and CP201 (56.0, 15.5) are 7.30 mm lines, 0.29 mm wide, 0.25 mm apart edge to edge. The ground fill does not cover the graphical copper and does not enter the gap. They are not shorted. I did not compute even/odd-mode impedances to better than the author's ±5 dB. An open −20 dB monitor port is acceptable; an open −6 dB port would not be. Nothing I measured says they are −6 dB.
- SMA centre pads are 2.0 mm and have no L2 under them (J101 at 24, 7; J202 at 56, 7). That is what CLAUDE_PCB.md §14 asks for wide pads. The launch is still unmeasured. The TX pi pad can tune one of them. The RX SMA has no pi, only the SKY65404's 0.5 pF shunt.
- The Johanson 5400BL15B050 drawing (rendered in this directory) has pin 1, the unbalanced port, at the brown-mark corner, pins 3 and 4 the balanced pair, pins 2 and 5 ground, pin 6 NC. The schematic wires it that way, and the placed part has pin 1 facing the incoming RF. A 180° swap of the balanced pair would only invert I and Q, which the loop jumpers and the idle measurement already absorb.
- MAX2871 Note 4 is "measured single ended with 27 nH to VCC into 50 Ω." That is the network on the board. The 1.5 pF series caps are 18 Ω at 5.8 GHz, about 0.5 dB, not a short and not a match disaster.
- LQW18AN43NG00D, the ADL5611 choke, has a minimum SRF of 2.7 GHz. Coilcraft 0603HP-43N, the part the ADL5611 datasheet names, is in the same place (SRF near 2.5 GHz). ADI still specifies 43 nH for 500 MHz–6 GHz. I do not call the choke wrong.

The paddle via counts are the part of the RF layout I would not sign. Four 0.25 mm vias in a 1 mm square under a 2.6 mm paddle is a connection. It is not the nine the demodulator datasheet asks for, and it is the thermal path for about 1.2 W (ADL5380, 245 mA at 5 V). A 0.3 mm via is on the order of 100 °C/W; four in parallel are about 25–30 °C/W before spreading. That can be fine in open air and tight in a box. The LNA is the sharper one: no via under the paddle, nearest ground via 1.1 mm from the centre, just outside a 1.5 mm body. At 5.8 GHz that is a ground return of a few tenths of a nanohenry. Two ADL5611s after it are 28 dB of gain. Oscillation is the failure the author's own dead-on-arrival list already ranks fourth. The missing vias are the concrete version of that risk.

## 4. Transmitter levels and the mute

The 2-bit ladder does include the PYNQ's 200 Ω. With Rb = 2.2 k and Rr = 300 Ω, the budget's levels on a PYNQ are 0.170 / 0.500 / 0.830 V. On an Icepi, with the same resistors and the same Vr, they are 0.167 / 0.521 / 0.874 V. Close enough to trim. The N-side bias is the ~100 mV offset in finding 5, and it is a software trim, not a cut trace.

TX_EN is the right way around. U206 is a 74LVC1G04. R227 is 1 k to ground on TX_EN. R209 is 100 k to +3V3_DIG on TX_DIS, which is the ADL5375 DSOP, high = mute. The core resets `ctrl_tx_dis` to 1 (`gateware/costaslink_regs.v`), and both tops assign `tx_en = ~tx_dis`. A host that is off, unconfigured, or loading another overlay does not transmit. I agree with that change. The 1 k against a 10 k configuration pull-up is 0.3 V, under the inverter's 0.8 V Vil. Driven high through 200 Ω it still clears 2.0 V if the Zynq's VOH is 2.9 V at 4 mA. The arithmetic in the sheet note holds.

What the mute does not do is pick a frequency. There is no low-pass on the TX SMA. A wrong register word can put +10 dBm anywhere the MAX2871 can tune, from 23.5 MHz to 6 GHz. The helper in `gateware/max2871_regs.py` refuses anything outside 3–6 GHz and only builds integer-N multiples of 25 MHz. The SPI hardware will send any 32 bits. For a bench with the author watching, that is a procedure. For unattended operation it is not a lock.

## 5. Answers to §3

**1. Concept.** I would not change the architecture before this board is measured. A carrier that is on all the time is the right way to have a phase reference when the data are rare events, and comparators are the right way to keep software out of the decision. An ADC and a matched filter would timestamp better and reject multipath better, and they would add the filter's delay, which is the thing this experiment is trying not to add. OOK is simpler and is already on the board as a comparison mode. An off-the-shelf 5.8 GHz modem will not give a 25 ns electronics number you can defend.

The PYNQ-Z2 is the wrong host for a published latency, and the author already says so. 8.8 ns of the 22.7 ns is two passes through 200 Ω. The Icepi path at 13.9 ns is the number I would quote, and only after it is measured. Multipath is the experiment's real enemy: a 100 MHz arm does not resolve a reflection 3 m longer (10 ns), and a comparator has no equalizer. Dishes on a hill may be clean enough. A campus path may not. The board can show which. That is what rev A is for. Do not start over.

**2. 5.8 GHz layout.** The lines are 0.29 mm CPWG over continuous L2, with a measured ground gap of 0.205 mm (47.7 Ω, not 49.8). No 90° corners. The couplers are not shorted to the pour. The balun pinout matches the Johanson drawing. The LO network matches MAX2871 Note 4. The things I would not sign are finding 3 (paddles) and the unmeasured SMA launches. Isolation of 42 dB at 600 MHz spacing is a property of the antennas, not of this layout; the board cannot create it. Two panels side by side at 30–40 dB, as the plan says, is not 42 dB. The slow path cannot repair a compressed demodulator. Use two antennas and the DSA, or the switch, and do not believe FDD on one antenna.

**3. Costas loop.** The 74LVC1G3157 datasheet says S low selects B1 and S high selects B2. The sheet note and the jumper default match that. JP101/JP102 swap the sign, so a wrong guess about which way Q moves is one shunt moved, not a respin. I did not derive the ADL5380's Q polarity from first principles; I would not bet the first power-up on the silk. BRINGUP stage 3 should show runaway in one position and lock in the other. If both positions run away, the loop filter's second inversion or the VCXO slope is wrong, and that is the measurement.

The bandwidth claim is wrong, and I missed it until GPT-5.6Terra's note. `sim/budget.py` sets Kd to the differential peak, 0.249 V/rad. U110 selects one leg, so the voltage at ERR relative to V_MID is half of that, 0.124 V/rad. With the fitted 20 k / 750 Ω / 100 nF the loop is 2.05 kHz and zeta 0.48. It will still lock. It will ring more, and pull-in from 30 kHz is a few times the quoted 4 ms. Change R1 to 10 k if the 3 kHz number is a requirement. Do not hold the order for it.

The hold switch is wired correctly: TS5A3159 pin 6 high connects COM to NO. LOOP_HOLD rests low on 100 k, so the loop rests closed (NC = ERR). Leakage of the open port goes into V_MID, as the note says. Off leakage is a few nanoamps; it will not wind the integrator while held.

The VCXO pulls ±100 ppm minimum over 0.3–3.0 V, ±580 kHz at 5.8 GHz, against at most 29 kHz between two ±2.5 ppm TCXOs. Its modulation bandwidth is 15 kHz minimum, and the loop is 3 kHz. Those fit. The loop will not lock until the RX synthesizer is programmed and the LO is up. That is software, and the MUX lock-detect pins are brought out. The "1 Hz steps" in the plan are not in `max2871_regs.py`: the modulus field is 12 bits, so the finest fractional step at 25 MHz PFD is about 6 kHz. Integer-N at 5800 and 5200 is exact (N = 232 and 208). 6 kHz is fine inside a ±580 kHz pull. Do not write a bring-up step that needs 1 Hz.

**4. Fast path.** At the regulated level, yes, each comparator sees about ±249 mV peak differential, and 20 mV is a fair decision threshold, if finding 2 has not already folded the FDA. The 33 Ω on the board plus the PYNQ's 200 Ω is 233 Ω, not the 200 Ω in the 4.4 ns term; that is about 0.7 ns, not a new architecture. The 453 Ω taps are open unless a scope is on them. Window comparators: finding 6. I would not enable the decoder until the DAC read-back matches.

**5. Slow path.** The 37 ns is half of a 73 ns 10–90 % rise. τ of a 4.8 MHz pole is 33 ns; 2.2 τ is 73 ns; half of that is 36 ns. The delay claim holds. The sensitivity claim does not, at the quoted floor. The budget's own line is slow-path comparator floor −107 dBm and noise floor −92.3 dBm in 7.5 MHz. Below about −92 dBm the slow path is voting on noise. "Confirm or veto" is meaningful between the fast floor (−81 dBm) and that noise floor, not at −107 dBm. Offsets of two THS4541s times 20 are tens of millivolts and are inside the 100 k trim. The trim has to be done, or the veto is an offset.

**6. Transmitter.** Levels: §4 above and finding 5. The 41 mV I first computed from the divider alone is incomplete: both N pins dump 41 µA into an 836 Ω Thevenin, another 69 mV, so the offset at the printed Vr is about 100 mV. Still a trim. TX_EN: right, and it is the one recent change I would keep exactly as drawn. Station identification: the keyer drives the same TX_DIS the top inverts, and the testbench checks that an ID returns to muted. I did not re-run the sims (`make` writes `build/gateware_scratch/`, which is not mine). I would not transmit unattended until that ID has been seen on a spectrum analyser, not just in a testbench. Do not put the 2 W module through the HMC536 (finding 9).

**7. Power.** Finding 1 and finding 7. Regulator dissipation matches the budget at the currents given (0.25 W and +47 °C in the PLL LDOs after 2.2 Ω). I did not re-derive the SOT-23-5 thermal resistance; 187 °C/W is the number the repository already uses. Back-feed through the power FETs: the gate circuit does what the note says. I did not find a path from +5V_IN onto VBUS or onto +5V_HDR when the other source is the one that is on.

**8. Gateware.** The register map, the DSA bit order (LSB first, D7 clear), the AD5696R channel map (A = QP, B = QN, C = IP, D = IN, command 0x3n write-and-update), and the TX_DIS reset are what BRINGUP needs. The shipped Vivado report meets timing: WNS 1.661 ns, WHS 0.031 ns, pulse-width slack 0.345 ns, on a 400 MHz DDR clock (`build/pynq/timing_summary.rpt`). I would not trust a latency to the sample. 31 ps of hold slack has not seen a board, a hot day, or a slow corner, and the Icepi sample order is documentation, not a simulation. The 22.7 ns figure is a sum of datasheet delays plus a −1.7 ns correction for double-counting the arm rise. It is a budget, not a measurement.

**9. Manufacturing.** I re-ran DRC and ERC with KiCad 10.0.6 on the shipped files, output in this directory: 0 violations, 0 unconnected, schematic parity 0, ERC clean. `tools/net_check.py`: 382 parts, 267 nets, 0 problems. The balun and the SMA pin-1 renumber are consistent with the drawings I opened. I did not re-check the 30 CPL rotations. Thin stock and the stale consignment note are as the brief says. The sheet note that says two ADL5611s is wrong; the BOM has three.

**10. Method.** Reading the Python is how this board has to be reviewed, and it worked: every strap I cared about was a line I could point at. The cost showed up once. `budget.py` exits 0 while the TX compression check is aimed at the wrong datasheet row. An assertion that cannot fail is not a gate. I would not throw the generator out. I would make the datasheet row, not a remembered band figure, the input.

## 6. What nobody asked

**RF exposure, if the 2 W module is used.** The board alone is about +10 dBm. Into a 30 dBi dish that is 40 dBm EIRP, and at 1 m the far-field density is about 0.08 mW/cm², under the FCC general-population 1 mW/cm² limit. The 2 W module (33 dBm) into the same dish is 63 dBm, about 2000 W EIRP. The far field of a 0.6 m dish at 5.8 GHz starts near 14 m (2D²/λ). A rough near-field on-axis density is 4P/A ≈ 2.8 mW/cm², about three times the uncontrolled limit and under the occupational 5 mW/cm² limit. A 24 dBi panel is a smaller aperture: 4P/A is about 6.7 mW/cm², over both. Nobody stands in that beam. This does not change the order. It changes the hill procedure, and it is not in BRINGUP as a distance.

**No harmonic filter, and no frequency interlock.** Covered above. FCC §15.247 harmonic limits are not met by a hope that the ADL5611 has rolled off at 11.6 GHz. Measure the second harmonic on TX MON before the PA module goes on. The mute does not check the band.

**ESD and a hill.** The SKY65404's absolute maximum RF input is +1 dBm enabled (`sim/budget.py`, from its Table 2). A DC block does not stop a fast ESD edge. A 10 m cable to a panel is an antenna for lightning as well as for the link. There is no gas discharge tube and no series element that can survive a strike. For the bench, a whip on the SMA is fine. For the hill, an external protector at the panel is the difference between a measured link and a dead LNA. The LNA is not a part you will enjoy replacing.

**The summing node is unprobeable without a needle.** I MON, Q MON, VC MON and ERR MON exist. The voltage that finding 2 cares about does not have a pad. Add one on the next spin if the needle measurement is ambiguous. Do not add it as a reason to hold this order by itself.

**SMA cables on a board 8 mm above the PYNQ.** Five field SMAs along the top edge, the board registered only by the header and one slotted standoff. A stiff cable on J101 or J202 is a lever on the 2×20 socket. Strain-relief the cables to the enclosure, not to the board, or the header will be the thing that fails after the RF works.

**WiFi.** 5.8 GHz ISM is occupied. The fast comparators will false-trigger on a strong burst even when the loop is locked, because a 100 MHz arm does not reject a WiFi channel 20 MHz away. The slow path can veto some of that between −81 and −92 dBm and cannot veto it when the demodulator is compressed. A channel scan before the latency runs is not optional. PLAN.md §11 already has it open.

**What the latency number means.** 22.7 ns is FPGA pin to FPGA register, electronics only, with a −1.7 ns bookkeeping term in the budget. It is not "the bit arrives 22.7 ns after it was sent," and it is not constant if the DSA setting or the SNR changes the fraction of the arm rise at which the comparator trips. Three distances give a slope of c only if that electronics delay does not change between the three. Hold the DSA's regulated level, use the same symbol, and the slope method is sound. Change the level and it is not.

**Power banks.** A bank that sags to 4.7 V at 1.3 A, or that wants a PD contract before it gives more than 500 mA, will not run this board inside spec. Finding 1 is that sentence with the resistances filled in.

## 7. CLAUDE_PCB.md

Rules this board breaks, or meets only on a generous reading:

- **§14, exposed-pad vias.** "Many vias in an RF chip's exposed pad." ADL5380 asks for nine; the board has four. SKY65404 has none under the paddle. This is the rule I would not waive.
- **§14, P1dB at the operating frequency.** The rule states the 12.8 dBm figure and says the corners land on it. The budget still asserts against 16.0 dBm. The rule is right; the gate is aimed at the wrong row.
- **§14, a tuning network between radio and antenna.** The TX pi exists and is fitted 0 Ω. The RX SMA does not have one.
- **§14, a low-pass at the PA output.** There is no low-pass. The ADL5611 is not a PA with a reference filter, so the rule's premise is a bit off, but the harmonic measurement is still owed.
- **§14, self-resonance well above the band.** The 43 nH choke is below the band. The vendor's own recommendation is in the same place, so I would amend the rule: follow the vendor's part when the two conflict, and say so.
- **§14, CPWG gap constant, fence at λ/10.** Gap is 0.205 mm rather than 0.25 mm, constant on the tracks I measured. Fence pitch in the generator is 1.2 mm; λ/10 in this dielectric is about 2.5 mm. I did not re-measure every fence via. No 90° corners.
- **§15, width for current.** IPC-2221, 1 A wants about 0.30 mm of 1 oz outer copper for a 10 °C rise. +5V_RF has 62 mm of 0.30 mm and 19 mm of 0.80 mm, plus the L3 pour. The 0.15 mm segments are short fan-outs (the narrowest +5V_RF segment is 0.22 mm long, at the bead). I do not call that a violation. The drop that matters is the PTC and the FET, which §15's copper-square arithmetic does not see.
- **§10 gates I re-ran:** DRC with schematic parity, ERC, both severity-all, KiCad 10.0.6, on the shipped files. Both clean. Net check clean. Budget script exits 0, and one of its inputs is wrong (finding 4), so that gate is not doing what §10.14 asks. I did not re-run `build.py` or `make_release.py`; they write the tree, and the brief forbids that outside a copy. I did not build a copy; the shipped DRC matches the one I ran.
- **§10.16, current capacity of every high-current net.** I measured +5V_IN, +5V_RF and +5V_HDR track widths. I did not count squares of the ground return. At 1.34 A on a solid L2 that return is not the risk.
- **A rule I would add.** For any rail whose minimum is within 0.3 V of the source's minimum, the gate should subtract the maximum RDS(on), the PTC R1max, the bead DCR, and a stated cable resistance, and fail if the load is under its minimum. The present note subtracts typical drops from a perfect 5.0 V.

## 8. What I checked and found right

- DRC 0, ERC 0, schematic parity 0, on the files that would be ordered, re-run here, not taken from the brief.
- `tools/net_check.py`: the RX chain, both arms, the slow path, the loop, both LOs, the TX chain, and 5 V from VBUS through the PTC and the FET to +5V_RF. 0 problems.
- TX_EN mute, including the reset value and the top-level inversion.
- PE43711 powers up at 31.75 dB (its datasheet, serial and latched-parallel). A strong signal at first power hits a fully attenuated DSA, not the demodulator.
- SKY65404: V_ENABLE high enables, low shuts down. The 100 Ω pull-up to 3.3 V enables it. Enable current is 2.3 mA typical, so the pin sits near 3.0 V, inside the 2.5–3.5 V high range. Supply is 3.3 V, inside 2.8–5.0 V.
- HMC536 control range in the electrical-spec header is 0/+3 V to +5 V. 3.3 V is inside that. A high, B low is receive, and TR_A rests high on 10 k, so the switch rests in receive while the host is running and unconfigured. A powered-off host clamps TR_A to about 0.6 V, which is not a legal low (the control tolerance is ±0.2 V), and the switch can sit between states. The modulator is muted then. I agree with leaving it.
- AD5696R straps: RESET and RSTSEL high, LDAC and GAIN and A0 and A1 low. Midscale power-up, 0–2.5 V span, address 0x0C. Matches the pin table.
- TS5A3159 hold switch and 74LVC1G3157 sign switch match their truth tables.
- Integer-N at 5800 and 5200 MHz is exact from 25 MHz.
- The coupler copper is not eaten by the ground pour.
- The balun's terminal functions match the drawing, and pin 1 faces the RF input on the placed board.

## 9. Other reviewers

Read after the draft above, not before. KimiK3's file was still a stub. Claude's directory is the author's earlier self-review; I did not use it to set this list.

**Agree**

- GPT-5.6Terra on the Costas gain. The switch selects one FDA output. Kd is half the differential peak. Fitted loop: 2.05 kHz, zeta 0.48. Their `costas_gain_check.txt` matches a re-derivation from `sim/budget.py` §6 and U110. I dispute the severity. Two 0402s, or a corrected sentence. Not a respin, and not what decides the order.
- GPT-5.6Terra on the PA through the HMC536. +29.8 dBm minus 26 dB minimum isolation is +3.8 dBm at a LNA whose absolute maximum is +1 dBm, and +29.8 dBm is past the switch's +27 dBm minimum P0.1 dB at 3 V. The budget already says a +27 dBm PA wants a limiter. The bare board at +9.8 dBm leaks −16 dBm. Agree, and it is an operating rule, not a copper change.
- Gemini 3.8 Flash on the 5 V drop as the supply question, and on the measured CPWG gap of 0.20 mm giving 47.7 Ω. I measured the same gap (0.205 mm) before reading them. Their S11 of −33 dB is the right conclusion: that gap is not a stop.
- Gemini on the N-side bias. I had only the unloaded 0.541 V. Adding 82 µA into 836 Ω is the rest of finding 5. Still trimmable.
- GPT's lint log. I did not re-run `make lint`. Their log shows Verilator exiting on `SIMILARNAME` in `uart_cmd.v` and a shared loop index in `rx_engine.v`. That breaks the "lint is clean" claim. It does not break the board. Vivado already met timing on the overlay.

**Dispute**

- GPT-5.6Terra's verdict, that waived impedance control is why not to order. The order pins JLC04161H-7628 and declines the impedance-control fee. A ±20 % geometry window, which is wider than JLCPCB's usual etch, is 44–57 Ω on this stack. Mismatch loss at 50 Ω is under 0.1 dB. The couplers are monitor taps. I agree the fee was waived. I do not agree it is a respin. Gemini's dispute of the same finding is the one I would sign.
- Gemini's 4.0 m standoff for the 2 W dish, if it is read as the distance at which the beam becomes safe. That 4 m is the far-field formula for 1 mW/cm². The far field of a 0.6 m dish at 5.8 GHz starts near 14 m (2D²/λ), and a near-field estimate 4P/A is about 2.8 mW/cm² on axis the whole way. Stay out of the beam. Do not treat 4 m as the clearance.
- Gemini's TCXO pin-1 conclusion. The text extract has no pin table. They say a drawing shows E/D or NC with an internal pull-up. I did not re-open that drawing after reading them, and I will not adopt a pin function I did not see. The author's bring-up watch (LO TX MON, stage 2) still stands until someone photographs the drawing into the note.

**What was easy to miss, and who caught it**

- The factor-of-two on Kd. GPT. I had read the switch and still used the budget's Kd.
- The 82 µA into the shared N bias. Gemini. The budget applies that current only to the ladder node.
- The paddle via counts and the FDA guaranteed common-mode limit (Vs+)−1.3 rather than the typical (Vs+)−1.2. I do not see either in the other tables I read. The 5 V conclusion we share; the 17 mV corner and the four vias are the part I would not drop.
