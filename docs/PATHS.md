# Every signal path, traced by hand (Prompt 32, 2026-10-14)

Jason: "trace the signal paths by hand and make sure that all series and shunt components make sense, and that
everything makes sense going into and out of the ICs along the way, including DC bias levels, power levels, and
AC vs DC coupling."  Done on build 35's netlist (`hardware/checks/netlist.net`, walked with `tools/path_walk.py`
so that no hop is from memory), with the levels from `sim/budget.py` (`build/budget.json`) and the pin facts from
the datasheet texts in `build/txt/`.  Each hop is: **pin → part → next pin**, with what the part is for, the DC
on the node, the signal level, and whether the coupling is right for both ends.  "✓" means the datasheet's
requirement and the circuit agree.  The 10 m, two-whips case sets the receive levels (RX −53.9 dBm at the jack).

The one rule behind most hops: **a 5.8 GHz port that carries or forbids DC gets a 1.5 pF C0G 0402 in the line**
(C1552; series-resonant near 6 GHz, about 8 Ω at 4.9 GHz, 18 Ω of reactance at 5.8 before the resonance helps),
and every RF node's shunt to ground is a part whose ground pad joins the pour solidly (no thermal spokes, since
Prompt 32).

## 1. Receive chain: RX ANT to the demodulator (sheet 3, the left column of the board)

| hop | part | why | DC | level | coupling |
|---|---|---|---|---|---|
| J101 RX ANT centre | — | the jack; +1 dBm absolute maximum at the LNA behind it (SKY65404 Table 2) | 0 V | −53.9 dBm (10 m, whips) to −27 dBm (the top of the regulated range) | — |
| J101 → L101 6.8 nH → GND | shunt | ESD and a DC path for the jack: 6.8 nH is −j250 Ω at 5.8 GHz, on the jack side of the block so no bias reaches it (LQW15AN6N8, self-resonant at 6 GHz) | 0 V | 0.07 dB | ✓ |
| J101 → C101 1.5 pF → U101.3 RF_IN | series block | the LNA's input is internally matched; nothing on the jack may reach its bias | 0 V both sides | — | ✓ |
| U101.3 → C102 0.5 pF → GND | shunt | the input match from the SKY65404's own application circuit (Figure 10) | — | — | ✓ |
| U101 SKY65404-31 | LNA | 13 dB, NF 1.0, 15 mA from +3V3_ANA; V_ENABLE through R101 100 Ω from +3V3_ANA (3 V = enabled; abs max 5 V); VCC pin 6 with its 100 nF and the 0.6 nH + 100 nF of the application circuit | out: the output pin carries the drain bias | −40.9 dBm | — |
| U101.4 RF_OUT → C104 1.5 pF → U102.5 RF1 | series block | the LNA's output bias stays off the DSA; the PE43711 "requires no blocking capacitors if 0 V DC is present on the RF ports" (its p. 2), so both its ports are blocked | 0 V on the DSA side | — | ✓ |
| U102 PE43711 | DSA | 0-31.75 dB in 0.25 dB steps; 2.4 dB loss; powers up at 31.75 dB (P/S high through R102 10 k = serial mode, the parallel pins grounded, LE_DSA 100 k down); the loop's level regulator holds the demodulator at −20 dBm from 3 m to about 300 m | 0 V on the ports | −48.5 dBm at the 10 m setting (5.25 dB) | ✓ |
| U102.14 RF2 → C106 1.5 pF → U103.1 RFIN | series block | "RFIN: this pin requires a dc blocking capacitor" (ADL5611 pin table) | — | — | ✓ |
| U103 ADL5611 | gain block 1 | +14.3 dB at 5.8 GHz, P1dB +12.8 dBm, NF 6; the 5 V bias enters its RFOUT pin through L103 43 nH (Table 6: 43 nH for 500 MHz-6 GHz) with 68 pF / 1 nF / 1 µF on the supply side of the choke | RFOUT at 5 V DC | −34.2 dBm | — |
| U103.3 RFOUT → C110 1.5 pF → U117.1 RFIN | series block | the 5 V on RFOUT must not reach the next RFIN ("the RF path requires a dc blocking capacitor") | 5 V → 0 V | — | ✓ |
| U117 ADL5611 | gain block 2 | the same; L104 43 nH bias | RFOUT at 5 V | −19.9 dBm | — |
| U117.3 → C114 1.5 pF → CP101.1 | series block | the coupler is copper and would pass the 5 V on to the balun | 5 V → 0 V | — | ✓ |
| CP101 −20 dB coupler | copper | two quarter-wave CPWG lines (7.30 mm); through-port loss 0.3 dB; CPL (pin 3) → J102 RX MON (U.FL, −40 dBm); ISO (pin 4) → R103 49.9 Ω → GND | 0 V | main line −20.2 dBm; RX MON −40 dBm | ✓ (the ISO load is a thick-film 0402: about 0.5 nH, so the directivity is ~15 dB, fine for a monitor) |
| CP101.2 → T101.1 unbalanced | balun TDK HHM1907B1 | 50:50, 4.9-5.95 GHz, 0.8 dB; pin 4 to the pour solidly; the balanced pair leaves pins 2/3 | 0 V (the balun has a DC path to its ground pin) | −20.5 dBm | — |
| T101.2 → C159 1.5 pF → U104.22 RFIP; T101.3 → C160 → U104.21 RFIN | series blocks | "both the LO and RF ports should be ac-coupled" (ADL5380 p. 23; its evaluation board's C2x/C3x): the demodulator's RF inputs are biased on chip, and the balun would have grounded them | 0 V → the ADL5380's own bias | −20 dBm = the design's regulated level, 28 dB under the 5.8 GHz IP1dB of 8.2 dBm | ✓ (added in Prompt 31) |
| U104 ADL5380 | I/Q demodulator | gain 5.8 dB into 450 Ω, 390 MHz baseband; ENBL grounded = enabled; ADJ open (the 5.8 GHz spec condition; R104 1.5 k to +5V_RF is DNP: it would lower the output common mode to 2.5 V at the cost of the 5.8 GHz gain and 245 mA); 100 nF at each of VCC1-3 (pins 6/13/24) + 1 µF | outputs IHI/ILO/QHI/QLO at VS − 1.2 = 3.8 V, 25 Ω each | 0.249 V peak differential at the arms' outputs (after the FDA) | — |

The LO into the demodulator (section 4) and the I/Q arms (section 2) continue from here.

## 2. The I and Q arms: demodulator to comparators (sheet 3)

| hop | part | why | DC | level | coupling |
|---|---|---|---|---|---|
| U104.3 IHI → R107 1 k → I_SUM (U105.3 IN−); U104.4 ILO → R105 1 k → U105.2 IN+ | Rg | the gain-setting input resistors; with Rs they divide the 3.8 V common mode down to what the THS4541 accepts | 3.8 V → 1.87 V at the summing nodes (guaranteed limit 2.0 V = Vs+ − 1.3; 61 mV of margin, 1.94 V at a 5.15 V supply) | — | DC coupled by design: a Costas loop needs the DC |
| I_SUM → R108 1 k → GND; U105.2 → R106 1 k → GND | Rs | the level shift (the other leg of the divider) | — | — | ✓ |
| U105.4 FB+ → R110 4.02 k → I_SUM; U105.1 FB− → R109 4.02 k → IN+ | Rf | gain 4.02 (noise gain 9: 94 MHz with the 850 MHz GBW: the arm's own pole) | — | — | ✓ |
| I_SUM ← R522 100 k ← I_OFF_F (U506 D) | trim | the fast I arm's offset trim: ±66 mV at the output for 0-3.3 V at the DAC | 1.65 V nominal | — | ✓ |
| U105 THS4541 | FDA | Vocm pin open = mid-supply 1.65 V (= V_MID) with 100 nF; PD 10 k up; 3.3 V | out 1.65 V ± 0.125 V a leg | ±249 mV differential at −20 dBm | — |
| U105.10 OUT+ = I_P → U107.3 (TLV3601 IN+), U603.3 (TLV3603 IN+), R122 1 k → J104 I MON, R501 1 k → the slow stage, R141 10 k → the ADC (C154 100 nF at the ADC pin) | fan-out | the sign comparator (I_P against I_N), the I+ window comparator, a /10 tap, the slow confirm path, the averaged level | 1.65 V | — | DC; the ADC's 10 k / 100 nF = 160 Hz, capacitor at the pin since Prompt 31 |
| U105.11 OUT− = I_N → U107.4 (IN−), U604.3, R502 1 k → the slow stage | fan-out | | 1.65 V | | ✓ |
| the Q arm, mirror image: U104.16 QHI → R112 → U106.2 IN+ (R113 Rs, R117 Rf); U104.15 QLO → R114 → U106.3 IN− (R115 Rs, R118 Rf, R116 100 k ← Q_OFF_F from U113 C) | | the Q arm is not inverted (the I arm is: IHI into IN−, harmless, the loop re-locks 180° round) | 1.87 V nodes, 1.65 V outputs | ±249 mV | ✓ |
| Q_P → U601.3 (TLV3603 IN+ against V_TQP), JP101.1 / JP102.1, R123 1 k → J105 Q MON, R510 1 k → the slow stage, R523 1 k → C515 10 nF → U507.8 AD8310 INHI, R142 10 k → the ADC | fan-out | | 1.65 V | | the log amp is AC-coupled through 10 nF (its inputs are internally biased at VPOS/2; 1 k + 10 nF = 16 kHz corner) ✓ |
| Q_N → U602.3, JP101.3 / JP102.3, R511 → the slow stage, R524 → C516 → U507.1 INLO | fan-out | | | | ✓ |
| U107 TLV3601 (CMP_I) | the sign comparator | IN+ I_P, IN− I_N: a true differential decision at the crossing; rail-to-rail inputs (−0.2 to VCC + 0.2) take 1.65 ± 0.5 V; 3 mV typical hysteresis, 5 mV offset (I_OFF_F trims it); 2.5 ns at 50 mV of overdrive | out 0 / 3.3 V | | — |
| U107.1 → R120 33 Ω → header pin 18 (CMP_I); → R121 453 Ω → J103 CMP I MON | series | 33 Ω + the driver's ~20 Ω ≈ 50 Ω source termination into the header's line (the PYNQ adds 200 Ω of its own); 453 Ω into a 50 Ω scope = a /10 tap | | about 1.7 V into 50 Ω at the tap | ✓ |
| U601-U604 TLV3603 | window comparators | IN+ = Q_P / Q_N / I_P / I_N against V_TQP / V_TQN / V_TIP / V_TIN from the AD5696R (0-2.5 V, 16 bits, internal reference: no supply dependence); LE/HYS pin: DNP 0 R to the rail (0 mV) or DNP 150 k to ground (30 mV), open = 3 mV | thresholds 1.65 ± 0.3 V in use | | DC; the thresholds come straight from the DAC pins (no RC: the DAC is quiet; an RC at each pin is a rev B nicety) |

## 3. The Costas loop (sheet 3)

| hop | part | why | DC | coupling |
|---|---|---|---|---|
| Q_P / Q_N → JP101 (pin 1 Q+, pin 3 Q−, pin 2 → U110.3 B1); JP102 (→ U110.1 B2) | sign jumpers | which polarity of Q each switch input gets; default JP101 right (Q− to B1), JP102 left (Q+ to B2); both the other way = −sign(I) × Q | 1.65 V ± 0.125 | ✓ inside the 74LVC1G3157's 0-VCC analog range |
| U107.1 CMP_I → JP103 pin 1; LOOP_SEL (header) → pin 3; pin 2 → U110.6 S; R145 100 k S → GND (Prompt 32) | select | sign(I) steers the switch; with JP103 unfitted S no longer floats (low = B1) | 0/3.3 V | ✓ |
| U110.4 A = ERR → U111.3 (TS5A3159 NC), R124 1 k → J106 ERR MON, R144 10 k → the ADC | the error | ERR = sign(I) × Q as one leg of Q: Kd = a/2 = 0.124 V/rad at the regulated level | 1.65 V ± 0.125 | ✓ |
| U111 TS5A3159: IN (6) = LOOP_HOLD (header 19, R125 100 k down) low → COM = NC = ERR; high → COM = NO = V_MID | hold | the loop opens onto its own mid-point (leakage 0.1 rad in 6 ms) | | ✓ analog range 0-V+ |
| COM → R126 10 k → U112A IN− (2); R127 750 Ω + C130 100 nF from IN− to OUT (1); IN+ (3) = V_MID | PI filter | fn 2.9 kHz, ζ 0.69 as fitted (R1 10 k, R2 750, C 100 nF) | around 1.65 V | ✓ |
| U112A OUT → R130 10 k → U112B IN− (6); R131 10 k ← VC_OFF (U113 D); R132 10 k OUT (7) → IN−; IN+ (5) = V_MID | inverting summer | the FPGA adds an offset or a sweep to the loop's output, about the mid-point | | ✓ |
| U112B OUT (7) = VC → Y101.1 (the VCXO's control, 0.3-3.0 V, 5 MΩ), R133 1 k → J107 VC MON, R143 10 k → the ADC | | the OPA2388 on 3.3 V swings 0.02-3.28 V: covers the VCXO's range; before the gateware holds the loop VC walks to a rail (no carrier: the integrator sees only offset) | 1.65 V locked | ✓ DC |
| V_MID: R128 / R129 10 k / 10 k from +3V3_ANA with C131 1 µF | reference | the arms' and the loop's common mid-point | 1.65 V | ✓ |

## 4. References, synthesizers, LO (sheets 3 and 4)

| hop | part | why | DC / level | coupling |
|---|---|---|---|---|
| Y101 SX3V25 VCXO OUT (3) → C142 100 nF → U115.29 REF_IN; → U116.2 (74LVC1G17) | reference | 3.3 V CMOS, ±100 ppm over 0.3-3.0 V on VC (430 kHz/V at 5.8 GHz); "AC-couple to reference signal" (MAX2871 pin 29); REF_IN wants ≥ 0.7 V p-p and gets 3.3 | 1.65 V average → the MAX2871's own bias | ✓ |
| U116.4 → R134 33 Ω → J108 REF OUT (MMCX) | buffer | the VCXO to the other board's REF IN for a coherent transponder; 33 Ω + the LVC's ~20 Ω: about 1.7 V into 50 Ω (its 32 mA) | 0/3.3 V | ✓ |
| Y201 TC32H4 TCXO OUT (3) → JP201.1; J203 REF IN (R214 49.9 Ω DNP) → JP201.3; JP201.2 → C222 100 nF → U203.29 REF_IN | the TX reference | the jumper picks the TCXO (default) or an external 10-210 MHz reference; TCXO pad 1 (E/D or N.C.) floats, R228 10 k DNP to +3V3_OSC if a unit wants it | 3.3 V CMOS | ✓ AC |
| U115 / U203 MAX2871 | synthesizers | 3.3 V on six VCC pins (100 nF + 10 µF each) from their own LDOs behind 2.2 Ω; 1 µF on NOISE_FILT, BIAS_FILT, REG; RSET 5.1 k (ICP 2.56 mA at CP = 7); CE and RFOUT_EN 10 k up to the rail; LE 100 k down; loop filter 390 pF / 820 Ω + 6.8 nF / 2 k / 160 pF: 81 kHz, 49.7° as fitted, stable from Kvco 40 to 130 MHz/V | | — |
| U115.12/13 RFOUTA_P/N → L105 / L106 27 nH → +3V3_PLL_RX; → C149 / C150 1.5 pF → LO_RX_P/N → C119 / C120 1.5 pF → U104.10 LOIN / U104.9 LOIP | LO pair | open-collector outputs pulled up through 27 nH (−j980 Ω at 5.8 GHz); the pair P → LOIN, N → LOIP so the legs run straight and equal (10.76 / 10.76 mm); "LOIP, LOIN: pins must be ac-coupled" | 3.3 V at the pins → 0 V on the pair → the ADL5380's bias | ✓; two 1.5 pF in series a leg = 0.75 pF (36 Ω): about 0.5 dB a pair, inside the LO window (−6 to +6 dBm; the MAX2871 gives up to +5 dBm) |
| U115.14/15 RFOUTB_P/N → L107 / L108 27 nH; _P → C151 1.5 pF → J109 LO RX MON (U.FL); _N → C152 1.5 pF → R140 49.9 Ω → GND | the LO monitor | the second output pair: one leg to a tap, the other terminated so the output stays balanced | 3.3 V → 0 V | ✓ |
| U203.12/13 → L203 / L204 → C229 / C230 → LO_TX_P/N → C204 / C205 → U201.4 LOIN / U201.3 LOIP; U203.14/15 → C231 → J204 LO TX MON, C232 → R220 49.9 Ω | the TX LO, the same | | | ✓ |

## 5. Transmit chain: the header to TX ANT (sheet 4, the middle column)

| hop | part | why | DC / level | coupling |
|---|---|---|---|---|
| header TX_I0 / TX_I1 → R201 / R202 2.2 k → TX_I; VR_I (U113 A) → R203 300 Ω → TX_I; C201 1 µF on VR_I | ladder | two bits of 3.3 V LVCMOS summed into the modulator's high-impedance (60 k, 41 µA) IBBP with the DAC's 0.213 V reference setting the amplitude and the carrier null; levels 0.17 / 0.50 / 0.83 V, inside the −05's 0-1 V pin range | 0.5 V centre | ✓ DC: the ADL5375-05 wants a 500 mV bias on each baseband pin |
| VN_0V5: R207 4.7 k from +5V_RF, R208 750 Ω to GND, C203 1 µF → U201.22 IBBN and U201.9 QBBN | bias | the other leg of each pair at 0.507 V (loaded by 2 × 41 µA): the ladder's mid-point | 0.507 V | ✓ |
| TX_Q0 / TX_Q1 → R204 / R205 → TX_Q → U201.10 QBBP; VR_Q (U113 B) → R206 | the Q ladder | | | ✓ |
| TX_EN (header 24, R227 1 k down) → U206 74LVC1G04 → TX_DIS → U201.1 DSOP; R209 100 k up on DSOP | enable | an absent host leaves DSOP high = output disabled (VIH 2.0 V met by 3.3 V) | | ✓ |
| U201 ADL5375-05 | modulator | 203 mA from +5V_RF (VPS pins 18/24 with 100 nF each + 1 µF); 127 mA disabled | out −4.5 dBm at 5.8 GHz with this drive, feedthrough −19.5 dBm | — |
| U201.16 RFOUT → C209 1.5 pF → U202.1 RFIN | series block | "RFOUT must be ac-coupled"; the ADL5611's RFIN "requires a dc blocking capacitor" | — | ✓ |
| U202 ADL5611 | gain block | +14.3 dB → +9.8 dBm, 3 dB under its P1dB at the idle (a QPSK corner is +3 dB: at P1dB, count 1 dB); L201 43 nH bias from +5V_RF | RFOUT at 5 V | +9.8 dBm | — |
| U202.3 → C213 1.5 pF → (R210 DNP shunt) → R212 0 Ω → (R211 DNP shunt) → CP201.1 | series block, pi pad | the block keeps the 5 V off the coupler; the pad is a placeholder (0 Ω through, shunts DNP) for a few dB of attenuation if a test wants it | 5 V → 0 V | ✓ |
| CP201 coupler: CPL → J201 TX MON (−10 dBm); ISO → R213 49.9 Ω; OUT → J202 TX ANT with L202 6.8 nH to GND | | the ESD shunt on the jack side: no DC on this node | 0 V | ✓ |

## 6. The antenna switch block (sheet 5)

| hop | part | why | coupling |
|---|---|---|---|
| J401 ANT (L401 6.8 nH to GND) → C401 1.5 pF → U401.3 RFC; J402 SW TX → C402 → U401.5 RF1; J403 SW RX → C403 → U401.8 RF2 | blocks on all three ports | "DC blocks are required at ports RFC, RF1, RF2" (HMC536 p. 7); no supply pin; 27 dB of isolation, +27 dBm at 0.1 dB | ✓ |
| TR_A (header 27, R402 10 k up, J303.1, R490 453 Ω → J490 TR A MMCX) → R401 100 Ω → U401.1 A; TR_A → U402 74LVC1G04 → TR_B (R404 10 k down, J303.2) → R403 100 Ω → U401.2 B | control | 0/3.3 V logic (the HMC536 takes 3-5 V); at rest A high, B low = RF2 = SW RX: the receiver is connected when no host drives it | ✓ |

## 7. The slow path and the detectors (sheet 6)

| hop | part | why | DC / level | coupling |
|---|---|---|---|---|
| I_P → R501 1 k → U501.2 IN+ (R504 20 k from FB−); I_N → R502 1 k → U501.3 IN− (R505 20 k; R503 100 k ← I_OFF from U506 B) | the slow I stage | gain 20 on the fast arm's ±249 mV: ±5 V asked of a 2.9 V swing, so it idles 1.7× overdriven (the THS4541's 20 ns overdrive recovery adds to the 37 ns: start the confirm delay at 80 ns); the offset trim ±0.33 V | 1.65 V | ✓ DC |
| U501.10 Is_P → R507 1 k → J501 I SLOW MON; → R508 1 k → U503.3 (C504 33 pF to GND); Is_N → R509 → U503.4 (C505 33 pF) | the slow pole | 1 k / 33 pF = 4.8 MHz on each leg ahead of the comparator; the tap before the pole | | ✓ |
| U503 TLV3601 (CMP_I_S); U504 / U505 (CMP_QP_S / CMP_QN_S) with IN− = V_T2 (U506 A) | the slow comparators | the Q window on the slow path against one threshold (V_T2 needs a servo at the floor: its 0.1 a is 3.8 σ of the LO phase noise) | | ✓ |
| Q_P → R523 1 k → C515 10 nF → U507.8 INHI; Q_N → R524 → C516 → U507.1 INLO | the log amp's input | AC-coupled, differential, 1 k series as the arm's load; the AD8310's inputs sit at VPOS/2 internally; its ENBL = VPOS | 1.65 V → the AD8310's bias | ✓ |
| U507.4 VOUT = LOG_Q → R530 10 k → C524 100 nF → U510 AIN0; R590 1 k → J590 LOG Q (U.FL); → U508A IN+ (3) | the interference level | 24 mV/dB; 100 pF of capacitive load allowed ("stable with capacitive loads of 100 pF"): the 100 nF is behind the 10 k since Prompt 31 | 0.4-2.5 V | ✓ |
| U508A → D501 → PEAK_HOLD (C522 10 nF, R527 4.7 M bleed, R526 100 Ω) → U508B unity → PEAK_Q → R531 10 k → C525 → U510 AIN1 | peak hold | 47 ms decay | | ✓ |
| +5V_RF / 2 → V5_MON; NTC 10 k (TH501) from +3V3_DIG over 10 k → TEMP; both through 10 k / 100 nF to U510 | monitors | 1.65 V at 25 °C, 0.77 V at 60 °C | | ✓ |

## 8. Triggers (sheet 4)

| hop | part | why | coupling |
|---|---|---|---|
| TRIG_A / TRIG_B (header 37/35, R317/R318 100 k down) → U204 74LVC2G34 → R221 / R222 33 Ω → J205 / J206 (SMA, TRIG OUT A / B) | outputs | source-terminated LVCMOS marks: about 1.7 V into 50 Ω, 2.2 ns | ✓ |
| J207 TRIG IN (SMA) → R222 1 k (JP202 49.9 Ω to ground; R226 100 k down) → U205 74LVC1G17 → header 26 TRIG_IN; R225 453 Ω → J208 TRIG IN MON; **R291 2.2 k → the Q ladder node** (Prompt 35) | input, and the Q ladder's third leg | a 3.3 V pulse is +Q on the air with no FPGA (0.36 V at the node, one step); the 100 k keeps the Schmitt input low with nothing plugged in; R292 348 Ω is the Q reference so the node's conductance equals the I ladder's | ✓ |
| J207 TRIG IN (JP202 50 Ω option) → R223 1 k → U205.2 (74LVC1G17 Schmitt); U205.4 → header 26 TRIG_IN, R225 453 Ω → J208 TRIG IN MON, R226 0 R DNP → TX_Q1 (the bypass that skips the FPGA) | input | 1 k limits what a hot source can push into the buffer (5 V tolerant inputs); the Schmitt cleans a slow edge | ✓ |

## 9. Power (sheet 2), as the current flows

USB-C 5 V (CC 5.1 k × 2) → F301 2 A PTC → Q301 AO3401A (on only with VBUS: Q303 pulls its gate down; R303 holds it
off from the header's 5 V) → +5V_IN (D303 SMAJ5.0A, C320 100 µF polymer); the header's 5 V (JP301) → F302 → Q302
(off when VBUS is present) → +5V_IN.  +5V_IN → FB301 BLM21PG221 (220 Ω at 100 MHz, 2 A) → +5V_RF: the ADL5380,
ADL5375, three ADL5611 (828 mA; each chip's 100 nF + 1 µF after the bead).  +5V_IN → the LDOs: TPS7A2033 × 4
(+3V3_ANA 62 mA: the LNA, FDAs, OPA2388, V_MID; +3V3_PLL_RX and +3V3_PLL_TX 200 mA each behind 2.2 Ω; +3V3_DIG
60 mA: comparators, DACs, ADCs, logic, the DSA) and LP5907 (+3V3_OSC 15 mA: the two oscillators and the buffer).
1.37 A in all, 6.8 W; 5.10 V at the plug leaves 4.89 V on +5V_RF at the parts' maxima (the ADL53xx want 4.75).
Every rail has its own 2.2 µF in / 2.2 + 10 µF out at the regulator and 100 nF at every supply pin (3-8 mm away
on the board because of the placer's fan band: review B's open item for rev B).

**Power-up order with the PYNQ-Z2** (from the SyzygyRadioBoard checklist, checked here): the comparators and
buffers drive the header through 33 Ω; the PYNQ adds 200 Ω.  With the PYNQ unpowered and this board powered, a
high output pushes (3.3 − 0.6) / 233 Ω ≈ 12 mA through the Zynq's clamp diode on that pin, above the 10 mA
absolute maximum, on up to a dozen pins.  So: **PYNQ first (or both at once), this board last; this board off
first** (BRINGUP.md stage 1.5 already says so).  The other way round is safe: an unpowered board's outputs are
dead, and the PL's pins are tri-stated until the overlay loads; the TX bits reach the modulator's inputs through
2.2 k, and the SPI and LE lines go to unpowered chips only if someone loads the overlay before the board is
powered (don't).

## 10. What the checklist asked that this board does differently, and why

- **Decoupling pairs at every RF pin**: present (100 nF + 1 µF per chip, 68 pF / 1 nF / 1 µF at the ADL5611 chokes)
  but 3-8 mm from the pins (review B, S3): the pours are what the chips see at 5.8 GHz.  Rev B.
- **Thin-film 0201 terminations**: the 49.9 Ω loads are 0402 thick-film (C25120, Basic).  They terminate monitors
  and the couplers' isolated ports at −40 dBm: a 15 dB return loss there costs nothing that matters.
- **Mitred corners on RF lines**: the chains are straight; the pairs' jogs are L corners of 0.29 mm line (about
  0.05 pF each).  Rev B.
- **Anti-pads under wide RF pads**: none (the ADL5611's 1.3 × 0.9 mm pads: 0.17 pF, 16 dB RL each; review B, M5).
- **A pad for comparator hysteresis**: the TLV3603s have their LE/HYS footprints (0 / 3 / 30 / 60 mV); the
  TLV3601s have 3 mV built in.
- **RC on each DAC threshold at the comparator pin**: not fitted (the AD5696R and MCP4728 outputs drive the pins
  directly); the 16-bit DAC is quiet and the servo absorbs the rest.  Rev B if the windows chatter.
- **Shield cans**: no provision; the board has via fences along the chains and the switch lines instead.
- **Solder mask cleared over RF traces, impedance control at the fab**: not requested (ORDER_SETTINGS.md: the
  stack-up is pinned, the lines are short; a few ohms of mismatch is a tenth of a dB).

## 11. Every port's impedance and limits, against what the circuit presents

(Jason, Prompt 32: "look at voltage levels, power levels, input and output impedances, and specs of all of the
ICs and other interfaces.")  Z = impedance; "presents" is what the board puts on the port at the 10 m, two-whips
case unless said; the datasheet line is in `build/txt/<part>.txt`.

| port | Z in / out | operating range | absolute maximum | the circuit presents | margin |
|---|---|---|---|---|---|
| J101 RX ANT, J202 TX ANT, J401-J403, J203 REF IN, J205-J207 (SMA) | 50 Ω | — | the part behind each: see below | 0.29 mm CPWG, 49.8 Ω; the centre pin's inner rings removed, a 4 mm antipad (Prompt 31) | — |
| SKY65404-31 RF_IN (3) | 50 Ω (S11 −10 dB typ) | IP1dB −4 dBm typ (−5 min) | **+1 dBm enabled** (Table 2; +10 disabled) | −54 dBm (10 m); −30 dBm with the 40 dB loopback pad; a bare cable from the other board = +9.8 dBm: **never** | 55 dB; 31 dB; the own TX on two whips 32 mm apart: about −4 dBm, at P1dB and 5 dB from the maximum (use the switch block or a pad) |
| SKY65404-31 RF_OUT (4) | 50 Ω (S22 −12 typ) | P1dB out +9 dBm | — | −40.9 dBm | — |
| PE43711 RF1 / RF2 (5 / 14) | 50 Ω (RL 15 dB typ) | 0 V DC on the ports (else blocks: fitted anyway); input P0.1dB +31 dBm | +23 dBm CW | −40.9 dBm | 64 dB |
| PE43711 digital (P/S, LE, CLK, SI) | CMOS | 0-3.3 V | −0.3 to 3.6 V | 3.3 V LVCMOS; P/S 10 k to the rail | ✓ |
| ADL5611 RFIN (1) / RFOUT (3) | 50 Ω (RL ~15 dB), 5.8 GHz row | P1dB out +12.8 dBm at 5.8 GHz; +20 dBm input abs max | 20 dBm in | GB1 in −48.5, out −34.2; GB2 in −34.2, out −19.9; TX: in −4.5, out +9.8 (a QPSK corner +3 dB: at P1dB) | RX 47 dB under P1dB; TX 3 dB at the idle, 0 at a corner (counted) |
| coupler CP101 / CP201 | 50 Ω copper, λ/4 at 5.8 GHz | — | — | −20 dB coupled to U.FL taps; ISO into 49.9 Ω thick-film 0402 (~0.5 nH: RL ~15 dB, directivity ~15 dB) | monitors only |
| TDK HHM1907B1 | 50:50 Ω, RL ≥ 10 dB, 4.9-5.95 GHz | 0.8 dB max loss | 3 W-class ceramic | −20.2 dBm | — |
| ADL5380 RFIP / RFIN (22 / 21) | 50 Ω differential (RL −7.5 dB at 5.8 GHz through a balun) | IP1dB +8.2 dBm at 5.8 GHz; AC-coupled | **+15 dBm** | −20 dBm regulated (−27 at the top of `received_dBm()`'s range; +4 dBm if the DSA were at 0 dB with −30 at the jack) | 28 dB to IP1dB; 11 dB to the maximum even at DSA 0 |
| ADL5380 LOIP / LOIN (9 / 10) | 50 Ω differential, AC-coupled | −6 to +6 dBm (0 typ) | **13 dBm** | the MAX2871's −4 to +5 dBm per the output-power setting, less 0.5 dB in the two blocks | inside the window at every setting |
| ADL5380 IHI/ILO/QHI/QLO (3/4/16/15) | 25 Ω series per pin, out | 2 V p-p differential into 200 Ω; VS − 1.2 = 3.8 V common mode with ADJ open | — | 1 k + 1 k||4.02 k each leg (the 1.87 V summing nodes): 1.9 mA a pin; 0.25 V peak differential | ✓ |
| THS4541 IN+ / IN− (2 / 3) | high-Z (the 1 k Rg sets the input) | common mode up to Vs+ − 1.3 = **2.0 V guaranteed** (1.2 typ) | (Vs−) − 0.5 to (Vs+) + 0.5 | 1.87 V (1.94 at a 5.15 V supply) | 61 mV guaranteed; the DNP 1.5 k on ADJ drops it to 2.5 V at the ADL5380 if a unit needs it |
| THS4541 OUT+ / OUT− (10 / 11) | low-Z; ±75 mA; swing (Vs−)+0.2 to (Vs+)−0.25 = 0.2-3.05 V | capacitive load: a series R or ≤ ~20 pF (its Figure 7-11) | — | 1.65 ± 0.125 V into: two comparator inputs (5 MΩ || ~2 pF each), 1 k taps, 1 k slow stage, 10 k ADC; the 100 nF now behind the 10 k (Prompt 31) | ✓ |
| THS4541 Vocm (9) | 47 kΩ || 1.2 pF, defaults to mid-supply | — | — | open + 100 nF: 1.65 V ± 40 mV | ✓ |
| TLV3601 / TLV3603 IN+ / IN− | 5 MΩ common mode, ~2 pF | VEE − 0.2 to VCC + 0.2 (rail-to-rail) | VEE − 0.3 to VCC + 0.3 | 1.65 ± 0.125 V (fast), ±2.5 V asked of the slow stage but clipped at 0.2-3.05 by the FDA; thresholds 0-2.5 V from the AD5696R | ✓ |
| TLV3601 / 3603 OUT | push-pull, ~20 Ω; 325 MHz toggle | — | — | 33 Ω series into the header (+ the PYNQ's 200 Ω) or 453 Ω into a 50 Ω tap | source-terminated ~50 Ω |
| 74LVC1G3157 B1 / B2 / A (3 / 1 / 4) | 6-9 Ω on | 0 to VCC analog | −0.5 to 6.5 V | 1.65 ± 0.125 V | ✓ |
| TS5A3159 NC / NO / COM | 1 Ω on | 0 to V+ analog | −0.5 to V+ + 0.5 | 1.65 ± 0.125 V | ✓ |
| OPA2388 (both) | rail-to-rail in and out; ZO 100 Ω open loop at 1 MHz; ISC ±30 mA at 2.5 V | out to 5-20 mV of the rails (10 kΩ) | — | A: 10 k + 750 Ω / 100 nF PI; B: 10 k summer driving the VCXO's 5 MΩ and a 10 k + 1 k tap; U508A/B: the peak detector and a unity buffer (10 nF behind 100 Ω) | ✓ (the 100 nF no longer sits on an output: Prompt 31) |
| SX3V25 VCXO VC (1) | 5 MΩ min | 0.3-3.0 V, centre 1.65, ±100 ppm, 15 kHz modulation bandwidth | — | the OPA2388's 0.02-3.28 V | the loop's margin loses 15° to the 15 kHz pole: 46° left |
| MAX2871 REF_IN (29) | AC-coupled, internal bias | 0.7 V p-p to VCC; 10-210 MHz | — | 3.3 V CMOS through 100 nF | ✓ |
| MAX2871 RFOUTA/B (12-15) | open collector: 27 nH chokes to 3.3 V; "50 Ω" with the pull-up | −4 to +5 dBm per the register's setting (3 GHz row; +8 dBm differential) | — | into the ADL5380/ADL5375 LO ports and the taps' 50 Ω | ✓ |
| MAX2871 digital (CE, LE, CLK, DATA, RFOUT_EN, MUX) | CMOS | 0-3.3 V | −0.3 to 3.9 V | 3.3 V LVCMOS; CE / RFOUT_EN 10 k up; LE 100 k down | ✓ |
| ADL5375-05 IBBP/N, QBBP/N (21/22, 10/9) | 60 kΩ differential, 41 µA sourced per pin | **0-1 V absolute on each pin** at the −05 (bias 0.5 V) | — | the ladder's 0.17 / 0.50 / 0.83 V; VN 0.507 V | ✓ |
| ADL5375 LOIP / LOIN (4 / 3) | 50 Ω differential, AC-coupled | −6 to +6 dBm | — | the TX MAX2871 through two blocks | ✓ |
| ADL5375 RFOUT (16) | 50 Ω, must be AC-coupled | −4.5 dBm with this drive; feedthrough −19.5 dBm | — | into the ADL5611 through 1.5 pF | ✓ |
| ADL5375 DSOP (1) | CMOS | VIH 2.0 V = output disabled | — | the inverter's 3.3 V, 100 k up | ✓ |
| HMC536 RFC / RF1 / RF2 (3 / 5 / 8) | 50 Ω (RL 20 dB), DC blocks required | +27 dBm min (29 typ) at 0.1 dB | +27 dBm (SW TX takes +25 without a limiter) | +9.8 dBm (TX); −54 dBm (RX) | 17 dB |
| HMC536 A / B (1 / 2) | logic, 3-5 V | 0 / 3-5 V | — | 0 / 3.3 V through 100 Ω; rest A high (10 k up), B low (10 k down) = RX | ✓ |
| AD8310 INHI / INLO (8 / 1) | ~1 kΩ differential, biased at VPOS/2 | −91 dBV to +4 dBV, 24 mV/dB | — | the Q arm through 1 k + 10 nF: −21 dBV at the regulated level, 38 dB over its floor | ✓ |
| AD8310 VOUT (4) | low-Z; stable into 100 pF | 0.4-2.5 V | — | 10 k then 100 nF (the ADC), the OPA2388 peak detector's 5 MΩ, a test pad | ✓ |
| AD5696R VOUTA-D | 0.04 Ω; 1 kΩ load min; 2 nF stable | 0-2.5 V (gain 1, internal reference) | — | the TLV3603s' IN− (5 MΩ) | ✓ |
| MCP4728 / MCP4728A1 VOUTA-D | rail-to-rail; 5 kΩ load; 1 nF stable | 0-2.048 / 4.096 V internal, 0-VDD external reference | — | 300 Ω + 1 µF (the TX references: 0.213 V), 100 k trims, the slow V_T2 straight into TLV3601s' IN− | ✓ |
| ADS1115 AIN0-3 | 4.9 MΩ differential at ±2.048 V (6 MΩ at ±4.096) | ±FSR, single-ended 0-3.3 V here | VDD + 0.3 | 1.65 V class levels through 10 k / 100 nF | ✓ |
| 74LVC1G04/1G17/2G34 inputs; outputs | 5.5 V tolerant inputs; 32 mA outputs | 0-3.3 V | 6.5 V in | TRIG IN through 1 k from an SMA; outputs through 33 Ω into 50 Ω (1.7 V) | ✓ |
| PYNQ-Z2 header pins (Zynq LVCMOS33, 200 Ω series on the PYNQ) | ~10 pF seen from here | 0-3.3 V | VCCO + 0.55 V; **10 mA** through a clamp with VCCO = 0 | our 33 Ω + their 200 Ω: 12 mA per high output with the PYNQ off | the power-up order in section 9 |
| USB-C J301 | 5 V, CC 5.1 k × 2 (1.5 A ask) | 5.10-5.25 V at the plug for 4.89 V on +5V_RF | SMAJ5.0A clamps at 6.4 V; 2 A PTC | 1.37 A | a bench supply with a short lead; not a laptop port |
