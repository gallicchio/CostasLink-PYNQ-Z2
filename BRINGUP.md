# CostasLink-PYNQ-Z2: bring-up and the experiments, from the bench to the mountain

Written for Prompt 8 (2026-10-09).  Every number here is from `sim/budget.py` and `sim/link_rates.py`
(`build/budget.json`, `build/link_rates.md`); the plan's sections are in `PLAN.md`.  The rule of the
bench (CLAUDE_PCB.md section 9): plug in, do not solder or hold a probe.  Every node worth looking at
has a U.FL tap or a test pad, and every stage below says which one to plug the scope into.

The stages are in order; each one has a *pass* condition, and the dead-on-arrival list of PLAN.md
section 10 is folded in: the table at the end says which stage retires which risk.

## What to have on the bench

| thing | why | have / buy |
|---|---|---|
| bench supply, **5.1-5.25 V**, current limit 1.5 A, into a short USB-A-to-C cable (or a USB-C PD supply rated 3 A) | stage 1; the board draws 1.37 A with both synthesizers running; the PTC, the FET and the bead drop up to 0.21 V at their maximum resistances, and the ADL53xx and ADL5611 want 4.75 V: 5.10 V at the plug leaves 4.89 V.  A laptop's port or a thin cable is not enough (the design review; sim/budget.py section 9) | have |
| the 6 GHz scope (or a spectrum analyser, or the B210 at 5.8 GHz) | the LO and TX monitors; the loop's analog nodes | have |
| U.FL-to-SMA pigtails, 6 or more (Hirose U.FL-LP-088 leads, 100-200 mm) | twelve monitors are U.FL, rated for 30 matings, so leave the leads on the taps you use most; five are MMCX (REF OUT, ERR, VC, TRIG IN and I SLOW MON): 5 MMCX-to-SMA leads too | buy, about $15 for 10 |
| SMA attenuators: **40 dB** (board-to-board loopback: the LNA's absolute maximum input is +1 dBm and the transmitter gives +9.8; 30 dB leaves the receiver 7 dB above the top of its regulated range, Prompt 31's review C; never under 20), **20 dB x 2** (in front of each PA module, and one in the TX lead for the two-whip test), 1 W rating is plenty | stages 3 and 5 | buy if not in the drawer, $10-20 each |
| SMA male-male leads, 3 x 150 mm (the switch block's jumpers; loopback) and 2 x 1 m | stages 3 and 4 | have / buy |
| 50 ohm SMA terminations x 2 | an unused SMA (RX ANT when the switch block is cabled) | have |
| 2 dBi 5.8 GHz whips, SMA male, x 4 | the lab antennas | buy, $5 each |
| the four 24 dBi panels with their 10 m cables (N at the panel, SMA at the board), N-to-SMA adapters | stage 5 | have |
| the two 30 dBi dishes | stage 6 | have |
| the two USB-C modules: SBB5089+SE5004 2 W PA, SAW filter + LNA (5.8 GHz) | stages 5 and 6; a second PA and LNA for the far end as the tests demand | have one each |
| USB-C PD power banks, 5 V / 3 A, x 2, and a small heatsink or fan for the PA (it dissipates about 9 W) | the amplifiers in the field | buy |
| two PYNQ-Z2 (or one PYNQ and one Icepi Zero), their supplies, a laptop | both ends | have |
| an IR thermometer or camera | stage 1 (heat) | have |
| the 2x20 socket J302 (LCSC C2977589, 2.54 mm, about 8.5 mm tall) and 2.54 mm jumper shunts (C5305), from `mfg/release/hand_solder_bom.csv` | J302 is soldered at home (Prompt 15: fitting it made JLCPCB's order two-sided, about $51 with duty); the shunts set JP101-JP103 and JP201 | buy with the order |

## Stage 0: before the order (the gates)

1. The pin audit of every generated symbol against the datasheet pin figures is done (Response 8,
   `build/scratch/pin_audit.md`): it found and fixed nine missing ground pins on the PE43711, the
   HMC536's paddle, and two switch-polarity notes that read backwards.  Nothing else.
2. The gateware top builds from the generated constraints: CLAUDE_PCB.md section 9 ("firmware is part
   of the design").  **Done** (Response 9 for the first firmware; Response 15 for the experiments,
   `gateware/README.md`): one core on both boards, the PYNQ-Z2's overlay from Vivado 2024.1 (PYNQ 3.1),
   800 Ms/s through the ISERDESE2s, AXI-Lite, timing met; the Icepi Zero at 100 MHz and 200 Ms/s through
   IDDRX1F, the UART at 1 Mbaud; the Python driver (`gateware/driver/costaslink.py`) runs every operation
   of these stages, and its tests run it against the RTL with a loopback model (`make sim-driver`).
3. The release passes its gates (DRC, parts, CPL, placement preview); nothing is consigned unless JLCPCB's shelf
   is short on the day, in which case `mfg/release/CONSIGNMENT.md` says what to buy (PLAN.md section 17: the cost).
4. The DAC EEPROMs: nothing to do before the board exists, but the first gateware writes all eight DAC
   channels' EEPROM defaults to mid-scale (1.65 V) once, so a power-up injects no offset into the arms.
5. The Icepi's sampler, with the Icepi alone: the ECP5's IDDRX1F hands over two samples a clock, and
   which is the earlier is from Lattice's TN1265, not simulated (the ISERDESE2's order is: Vivado's
   model).  A jumper on the Icepi's own header from TRIG A (pin 37) to TRIG IN (pin 26), then
   `cl.triggers(width=3, a="symbol")` and a hundred times `cl.capture("trig_in", post=64, start=lambda:
   cl.wr("TXSYM", k))` with k alternating 0x7 and 0x4 (a write that changes the point pulses TRIG A): every
   rising edge must read 0 ... 0 1 ... 1 across the samples, never 1 0 inside a word.  A swap is one line
   in `fast_sampler_ecp5.v`.

## Stage 1: first power, no RF (one board, an afternoon)

Nothing plugged into the header yet; the board alone on the bench supply through USB-C.

0. Before power: solder J302 on the back (pin 1 at the right-hand end of the bottom edge, as the silk
   shows; square to the board: it carries the board 8 mm above the PYNQ), and fit the shunts:
   JP101 SIGN B1 on Q-, JP102 SIGN B2 on Q+, JP103 SEL on CMP, JP201 REF on TCXO; JP202 (50R) and JP301
   (HDR 5V) open; JP302 / JP303 (the I2C pull-ups) open for the PYNQ-Z2, fitted for the Icepi Zero (Prompt 35).
   The modulator is off until a gateware drives TX_EN high (Response 15).  The back silkscreen repeats these.
   If the five 5.8 GHz SMAs' centre pins stand proud of the back (JLCPCB leaves through-hole pins as they come,
   1.9 mm), clip them to within 0.3 mm of the solder: the stub is a capacitor against the back pour, worth 3 points
   of reflection per launch in the field solve (docs/LAUNCH.md section 4.2).  REF IN and the triggers do not care.

1. 5 V at a 0.1 A limit first, for a few seconds: the supply goes straight into its limit (the ADL5380 and the
   three ADL5611 have no enable), so read its voltage: a short holds it near 0 V, a sound board settles at a volt
   or two where its chips start to draw.  Then raise the limit to 1.5 A.
2. Rails at the test pads (bottom-right strip; the same rails on the U.FL row under the TX chain, through 1 k, for a
   logger): +5V_IN within 0.15 V of the supply, +5V_RF at least
   4.85 V (measure it again at 1.37 A in stage 2; if it is lower, raise the supply toward 5.25 V),
   +3V3_PLL_TX / +3V3_PLL_RX / +3V3_ANA / +3V3_DIG / +3V3_OSC 3.30 +-0.05.  Both LEDs lit.
3. Current: 0.89 A plus up to 0.4 A for the two MAX2871 before they are programmed (CE is pulled high and
   their registers are undefined at power-up).  The ADL5380 and the three ADL5611 run from power-up; the
   ADL5375 idles at 126 mA instead of 194 with its output disabled, because TX_EN rests low until a gateware
   drives it (Response 15).  1.37 A once both MAX2871 run at full output and the gateware enables the
   transmitter (stage 2).
4. Heat: the IR camera on the ADL5380, ADL5375, the three ADL5611 and the two MAX2871 after ten
   minutes.  Expect 50-70 C on the QFN tops at 1.37 A; the PLL regulators' 2.2 ohm resistors warm.
   Nothing above 85 C, or the pours and the exposed-pad vias are not doing their job.
   *Pass:* every rail in range, nothing hot, the current within 10 % of the budget.
5. Plug onto the PYNQ-Z2 (the board rides 8 mm above it on the socket; the slot takes the shared
   standoff).  **From here on, power the PYNQ first (or both at once) and this board last, and take it
   off in the reverse order.**  The comparators drive the header through 33 + 200 ohm: into an
   unpowered Zynq that is about 11.6 mA a pin into its clamp diodes, and the four window comparators
   rest high from power-up until the gateware writes the AD5696R (its outputs start at 1.25 V, under
   the arms' 1.65 V).  For the same reason the window comparators' event counts mean nothing until
   that write: write all four (`CostasLink.threshold`) before `rx_config` enables the receiver (the
   design review).  From a Jupyter cell: I2C scan finds 0x0C (the windows' AD5696R), 0x48 (ADC), 0x49 (the detectors' ADC),
   0x60 (DAC 1), 0x61 (DAC 2); write the
   DAC EEPROM defaults to 1.65 V; read the ADC's four channels (I, Q, VC, ERR) with nothing on the air:
   I and Q near the demodulator's common mode as the arms shift it, VC at 1.65 V (V_MID with the loop
   open: LOOP_HOLD high).
   *Pass:* five I2C acknowledges, sensible ADC readings (`detectors()`: V5_MON = +5V_RF / 2, TEMP near 1.65 V at 25 C).
   *Retires:* heat (DOA 7), the power path (DOA 10 in part), the I2C pull-ups on the Icepi (DOA 11).

## Stage 2: the synthesizers and the transmitter (one board)

1. SPI: write the MAX2871 register words from `gateware/max2871_regs.py` (5.800 GHz on the TX
   synthesizer from its TCXO, 5.800 on the RX one from the VCXO with the loop open).  The MUX pins
   (header 23/35) read lock detect; the LD RX / LD TX jacks (U.FL, /10 into 50 ohm) beside each chip show it too.
2. LO TX MON and LO RX MON (U.FL) on the spectrum analyser: 5.800 GHz, -4 to +5 dBm as programmed,
   the 25 MHz reference spurs 60 dB down or better, and the RX one moves +-580 kHz as the FPGA writes
   VC_OFF through the DAC across its range (loop open, HOLD high: VC follows VC_OFF).  REF OUT on the
   scope: 25 MHz, 3.3 V CMOS.
3. TX MON on the analyser: -10 dBm at the U.FL (the carrier, +9.8 dBm at the SMA, through the
   -20 dB coupler) with the ladders idle; the carrier feedthrough null with VR_I / VR_Q (OOK test:
   both ladders at 0: the carrier should drop by 15-20 dB; trim the two references for the deepest
   null).  TX_DIS high mutes it.
4. REF IN: a 25 MHz source from the generator at 1 V p-p into REF IN with JP201 moved: the TX
   synthesizer locks to it (the first check of the coherent-transponder lead).
   *Pass:* both synthesizers lock at 5.8 GHz within 3 dB of the programmed level; the VCXO pulls
   +-500 kHz or more at 5.8 GHz.
   *Retires:* the LO (DOA 5), the register words, the loop filter's stability (a lock that chirps or
   a VCO that will not settle shows here), the TX chain's gain (DOA 4 in part).

## Stage 3: loopback, one board (the day the loop locks)

TX ANT through a **40 dB attenuator** into RX ANT (30 dB works but leaves the receiver 7 dB above the top of
`received_dBm()`'s range, the DSA pinned at 31.75 dB and the slow path saturated: Prompt 31).  Never a bare
cable: the LNA dies at +1 dBm.  Before the gateware holds the loop, VC sits at a rail (0 or 3.3 V), not at
1.65 V: the closed loop integrates the arm's offset with no carrier; that is normal.

1. RX MON: -20 dBm at the demodulator's input minus 20 dB of coupling = -40 dBm at the U.FL, with the
   DSA set so (the budget's regulated level).  Walk the DSA through its 0.25 dB steps and watch RX MON
   follow.  That measures the chain's gain (LNA + 2 x ADL5611 - DSA) against the budget's 39.2 dB (the DSA at 0 dB: subtract its setting).
2. The arms with the loop open (HOLD high): I MON and Q MON show the beat between the two
   synthesizers (the TCXO against the VCXO, up to 29 kHz, as a slow sinusoid at +-250 mV); the ADC
   reads it too.  Measure the arms' DC offsets here: the mean of I and Q over a beat cycle, read by
   the ADC.  Set I_OFF_F (DAC 2 D) to null the fast I arm, Q_OFF_F (DAC 1 C) the fast Q arm (the
   loop's lock point moves by the Q arm's offset over the carrier's slope: PLAN.md section 18), I_OFF / Q_OFF to null the slow stages
   (watch each slow comparator's duty cycle go to 50 % with no carrier: the TX_DIS mute).
3. Close the loop (HOLD low, JP103 SEL on CMP, SIGN B1 (JP101) on Q-, SIGN B2 (JP102) on Q+: the
   defaults, as the silkscreen names the pins): VC MON
   settles to a steady voltage inside 0.3-3.0 V, Q MON goes to zero (plus the offset), I MON to
   +-120 mV steady, ERR MON to zero.  If VC runs to a rail instead, move BOTH sign jumpers to their
   other positions (the loop had positive feedback).  If it locks and unlocks, step the DSA (the
   loop gain follows the level) and look at ERR MON for oscillation at a few kHz (f_n 3 kHz).
   Then: lift the carrier frequency by 100 kHz in the TX register and watch VC move by 0.23 V (430 kHz/V; a 100 kHz step needs the fractional-N mode, not written yet:
   REVA_CHANGES.md 20) and the
   loop stay locked; pull-in from 300 kHz off takes 0.38 s (section 6 of the budget).  **Set the DSA
   first** (step 1): it powers up at 31.75 dB, and the loop gain follows the level, so a loop judged
   before the DSA is set runs at a fraction of its 3 kHz and is underdamped (the design review).
   While the loop is locked: the fast arms' summing nodes (each THS4541's pins 2 and 3, a DMM)
   should read under 1.94 V.  Over 2.0 V the FDA is outside its guaranteed input range: fit the DNP
   1.5 k on the ADL5380's ADJ (sim/budget.py section 7).  The carrier null (VR_I, VR_Q, stage 2)
   lands within a few mV of the printed Vr: the N inputs' divider now carries the ADL5375's own
   2 x 41 uA (sim/budget.py section 1).
4. BPSK: the FPGA flips the I ladder; CMP I MON (the comparator's output, /10) on one scope channel
   against TRIG OUT A (the FPGA's mark of the flip) on the other: the edge comes **15 ns + the cable**
   after the mark (the receive half of the 23.5 ns; the transmit half is in the mark's own path).
   The slow path's CMP I S edge (header pin 40) about 27 ns behind it, and a QPSK corner's CMP QP S about
   7 ns behind its CMP QP (docs/TRAJECTORIES.md: the clipped slow stage drives its RC with the full
   swing).  I SLOW MON now taps the stage's output ahead of its 1 k / 33 pF pole, so a 50 ohm scope
   there does not move the comparator.  The FPGA's own counters then give the same numbers to the sample (1.25 ns on the PYNQ-Z2).
5. QPSK: the four points; CMP QP / CMP QN fire with their thresholds (sheet 7's AD5696R, channels A and B)
   set at a/2 to begin with; V_T2 for the slow Q
   window above x20 the static error.  FSK: the ladders rotate; the edge order on CMP I / CMP QP gives
   the direction.  OOK: both ladders at 0 and back.
6. The confirm-or-veto counters: with the attenuator raised to 60 dB (two pads) the fast path is near
   its floor (-81 dBm at the antenna): count fast flags, slow confirmations and vetoes over 10^6 trials.
7. The window thresholds by counting (sheet 7; PLAN.md section 18): the loop locked on the idle, step
   each window threshold across the idle in 16-bit codes and read its comparator's edge count a second
   (EDGE_CNT1, 2, 6, 7 at 0x23, 0x24, 0x2C, 0x2D).  ln(rate) against the threshold is a downward parabola
   (Rice: nu0 exp(-u^2 / 2 sigma^2)): its width is sigma at the comparator, its peak the comparator's
   offset.  Set each threshold for one false event a minute; the parabola gives the threshold for one an
   hour.  Repeat on one comparator with its LE/HYS options (0 ohm fitted: 0 mV; both empty: 3 mV; 150 k:
   30 mV) and compare the edge's jitter on its MON jack.
8. The hold: REF OUT -> REF IN (no frequency offset), the loop locked, then HOLD high for 1, 10 and 100 ms;
   the phase step on Q MON at release against PLAN.md section 18's 0.1 rad after about 13 ms (typical).
   *Pass:* lock within 1 s from power-up, the latency numbers within 3 ns of the budget, every
   modulation decoded, the veto rate below 1 % at the regulated level, each window comparator's sigma
   within 20 % of the budget's.
   *Retires:* the loop (DOA 1), the fast comparators' offsets (DOA 2: the trims reach), the level
   shift (DOA 3: if an arm clips or the FDA misbehaves, fit the DNP 1.5 k on ADJ), the slow path's
   nulling (DOA 8), the ladder drive (DOA 9), the generated symbols (DOA 12: nothing works at all
   if a pin is wrong).

## Stage 4: two boards across the lab (whips, 3 to 30 m)

Two boards on two PYNQ-Z2s, whips on both SMAs of each.  Frequencies: board A transmits at 5.80 GHz and
receives at 5.20 GHz, board B the other way round (two antennas each, both carriers on all the time: the
600 MHz split the fast arm rejects by 31 dB).  The budget wants 42 dB of isolation between a board's own
two whips 600 MHz apart; two whips on one board's SMAs 32 mm apart give about 15 dB (stage 5), so **put each
board's transmit whip on a 1 m lead**, a metre from its receive whip, or run the first tests with
the switch block cabled in and time division (stage 4.4).

1. Lock at 3 m: each receiver locks on the other's carrier (VC MON steady on both).  The RX synthesizer
   is re-centred by the FPGA when VC nears an end of its range (the two TCXOs may differ by 29 kHz).
2. Latency: TRIG OUT A on board A (the mark of the flip) against TRIG OUT B on board B (the mark of the decode),
   both leads to one scope: 23.5 ns of electronics plus 3.34 ns per metre.  Repeat at 3, 10, 30 m: the
   slope is the speed of light, the intercept the electronics.  This is the experiment's calibration.
3. Error rates: continuous BPSK at 100 Mbaud for the BER; then the idle-carrier events at 1 MHz trial
   rate for the false-event rate (the "quiet" threshold: the slow path's veto rate says how quiet).
   All four schemes and the whitened stream, at 10 m and at 30 m with and without 20 dB of attenuator
   in the receive lead to stand in for distance (the fast path's quiet reach is 69 m, the slow one's
   251 m: build/link_rates.md, with the receive chain's NF by Friis since Response 18).
4. One antenna by time division: the switch block cabled (TX ANT -> SW TX, SW RX -> RX ANT, one whip on
   ANT), REF OUT -> REF IN on the prover with JP201 to REF IN, the T/R sequencer in the gateware:
   measure the 30 ns on TR A (MMCX, /10 into 50 ohm) against TX MON, and the prover's reply coherent with the
   verifier's carrier (the verifier's loop holds through the exchange and is still locked after).
5. Interference: a 5 GHz WiFi scan at the bench (the laptop); the loop's 3 kHz bandwidth should not
   notice a -40 dBm WiFi channel, the fast comparators will (false flags vetoed by the slow path).
   The detectors (Prompt 28): `cl.detectors()` with the far end off reads the floor (log_dbm), the bursts
   (peak_dbm), +5V_RF (v5_rf) and the board's temperature; a scope on the LOG Q pad
   shows the frames.  Calibrate cal_db against a known carrier (a generator at RX ANT, the loop held).
   Then the board's own survey with both far transmitters off (PLAN.md section 19, Prompt 26):
   `cl.survey(range(5650, 5926, 5))`, the slow window's noise fit at 5 MHz steps, beside the laptop's
   scan and an SDR on RX MON.  Calibrate its `cal_db` against a known carrier (`received_dBm()` locked,
   then the same level from a generator with the loop held).
6. The schemes against each other (PLAN.md section 18), each edge on the scope at both ends and its
   jitter over 10^4 events: the BPSK flip decided by sign(I) against the same flip decided by IN set
   beside the idle; the plan's corners (QP/QN and CMP I); the pilot at 45 degrees with the four corners
   (about -14 dBc, the four window comparators).  TRIG OUT A here against the MON jacks there.
7. The link without either FPGA: TRIG IN is the Q ladder's third leg (Prompt 35), so with the transmitting board's
   gateware holding its Q bits at 01 (idle) a pulse on TRIG IN is +Q on the air by itself: TRIG IN MON there
   against QP MON on the far board is the radio link's own latency (nothing to solder, no CTRL[8]).  With JP202
   fitted (50 ohm at the jack) set the
   generator's load to 50 ohm and its amplitude to 3.3 V there: in Hi-Z mode it delivers half, 1.65 V,
   under the Schmitt buffer's 2.19 V upper threshold (the design review).
8. The FPGA on the link's clock, and two-way time transfer (docs/SYSTEM.md section 4, Prompt 27): a
   REF OUT (MMCX) to TRIG IN (SMA) lead on each board, TRIG IN's 50 ohm jumper off, puts its VCXO's 25 MHz
   on header pin 26, clock-capable on both hosts; the gateware's MMCM makes the fabric clock from it.
   Board B transponds (REF OUT -> REF IN), so both fabrics run at board A's TCXO frequency once both
   loops lock: a counter on each, compared over Ethernet, must not drift.  Then A sends an event at t1,
   B time-stamps it (t2, CMP_I on clock-capable pin 18) and answers at t3, A time-stamps the answer (t4):
   offset = ((t2 - t1) - (t4 - t3)) / 2.  Repeat at 3, 10, 30 m: the offset must not move with the
   distance (the air cancels), and its scatter over 100 exchanges is the synchronization's precision.
   Calibrate the boards' own asymmetry side by side with a 1 m cable and a 40 dB pad first.  Start RX_TIMING's
   confirm delay at 80 ns (the slow I stage's 20 ns overdrive recovery is not in the 37 ns model) and shorten it
   from the measurement; expect the bench's CFAR windows near 0.2 a, set by the oscillators' phase noise.
   *Pass:* the latency line's intercept within 2 ns of the budget at both ends; BPSK quiet at 30 m
   with 20 dB in the lead; the T/R exchange works at 10 m.
   *Retires:* own-transmitter leakage (DOA 6: at the bench level), the switch (DOA 10's HMC536), the
   Icepi Zero if one end is an Icepi (DOA 11).

## Stage 5: across campus (panels, 300 m to 3 km)

Outdoors the link runs in the 5 cm amateur band (5.650-5.925 GHz), W3JQ, with the gateware's Morse
identification every ten minutes; the ISM band's Part 15 rules do not cover a bare carrier at this
EIRP.  The identification keys the carrier off and on: the far end's loop coasts through the gaps
(LOOP_HOLD across the identification, or expect a re-lock after it).

**The received level, in operation** (Prompt 18).  The board has no detector chip.  With the loop
locked, `received_dBm(ext_db=...)` reads the carrier's level from the DSA's setting and the I arm's
amplitude on the ADC: at RX ANT, or at the antenna when `ext_db` is the gain of what sits between
them (+15 for the LNA module, −30 for a pad).  `agc()` steps the DSA until the demodulator is back at
its regulated −20 dBm, which also restores the loop's gain.  Together they cover about −99 to
−27 dBm at RX ANT: 31.75 dB of DSA, plus about 40 dB of the arm read by the ADC below the regulated
level (ten ADC steps at the bottom; sim/budget.py section 3).  For setup:
* The DSA pinned at 0 dB with the level still low says to add the LNA module.
* The DSA pinned at 31.75 dB with the arm still high says to add a pad (or leave the PA out).
* Calibrate once on the bench: `rssi_zero()` with the far end muted, then a known level from the
  generator into RX ANT.  Unlocked (no carrier tracked), read RX MON on the analyser instead: I is
  then a beat, not an amplitude.

Before the first field day (the design review):

* **The PA never goes through the HMC536 (SW TX) above +25 dBm without a limiter ahead of the LNA:**
  the switch isolates 27 dB (its minimum at 5-6 GHz), and the LNA dies at +1 dBm.  Nor on whips on
  one board: TX ANT and RX ANT are 32 mm apart, and a +30 dBm whip couples about +15 dBm into the
  other.  With the PA, the receive antenna is another panel, pointed elsewhere.
* **RF exposure:** the FCC's general-public limit at 5.8 GHz is 1 mW/cm^2.  With the PA at +30 dBm the
  far-field distance to it is 1.4 m for a 24 dBi panel (+54 dBm EIRP) and 2.8 m for a 30 dBi dish
  (+60 dBm), but both antennas are still in their near field there (about 6 m and 14 m, 2D^2/lambda),
  where the beam's column carries up to 4P/A, about 3 mW/cm^2 in front of the panel.  So: **nobody in
  front of a live panel or dish, at any distance along its beam within 15 m**, and the transmitter
  muted (TX_EN low) while anyone works at the antenna (the reviewers' numbers differed; Grok4.7's
  near-field frame is the right one).
* **A coax lightning and ESD arrestor** at the mast end of each 10 m cable, grounded to the mast.
* **Heat:** in a closed box in the sun the input PTC holds only about 1.3 A at 85 C against the
  board's 1.37 A: ventilate the box, or the PTC trips.
* **The second harmonic** (11.6 GHz) on TX MON, if a 12 GHz analyser can be borrowed, before the PA
  amplifies it; the PA module's own filter is not specified.  Choose the two frequencies after a scan with the B210 at both ends (UNII-2C 5.47-5.725 GHz is the
quiet one for the 5.2 GHz direction if it is empty; 5.70 and 5.80 GHz keep both inside the amateur band and the LNA's 5.9 GHz rating).

1. Board alone, panels on the 10 m cables at both ends, 300 m: the budget says -49 dBm at the receiver
   and 43 dB of SNR: lock, latency and error rates as in stage 4.  Reach (quiet, BPSK): 3.1 km on the
   fast path, 11 km on the slow one, with the 5 dB cables at the board (build/link_rates.md).
2. The LNA module at the panel: first measure it on the bench (TX MON as a -10 dBm source into it, the
   analyser on its output: gain, and its passband edges by stepping the TX synthesizer 5.5-6.0 GHz;
   its noise figure from the receiver's noise floor with and without it).  Then at the panel's N
   connector, powered by a PD bank: the DSA absorbs its 15 dB.  Reach grows by the cable's 5 dB and
   the noise-figure difference; its filter adds 30 dB (assumed, measured in this step) of rejection of
   the own transmitter 600 MHz away, which is what lets both panels sit on one mast.
3. The PA module: **20 dB attenuator between TX ANT and the module** (the module's 40 dB would be
   driven 17 dB into compression without it); +30 dBm out, 2 A from the PD bank, the heatsink on.
   TX MON before the pad reads the board's own level; at the far end `CostasLink.received_dBm()`
   reads the received level for pointing the panels (next paragraph).  EIRP with the 24 dBi panel is +54 dBm: aim it away from
   people and buildings as any amateur microwave station does.  Reach (quiet, BPSK, PA and LNA at the
   panels): beyond 100 km on either path; power is not the limit on campus, line of sight is.
4. Measurements: the latency line over 300 m, 1 km, 3 km (ground truth from GPS coordinates); error
   rates for each scheme at each distance with 10, 20, 30 dB of attenuator in the receive lead to walk
   down to each path's floor; the T/R mode at 1 km (the 30 ns turnaround against the 6.7 us round trip).
   *Pass:* lock and quiet BPSK at 3 km with the board alone; the PA and LNA each give the budget's
   gain within 3 dB.
   *Retires:* own-transmitter leakage at PA levels (DOA 6: the demodulator must not compress; if it
   does, the DSA and the LNA module's filter are the knobs), the amplifier modules' real numbers (the
   budget's section 2c assumptions become measurements).

## Stage 6: into the mountains (dishes, 20 to 70 km)

1. Choose the two sites from a terrain profile: line of sight with the first Fresnel zone clear (at
   5.8 GHz over 50 km the first zone's radius is 25 m at mid-path).
2. Each end: the dish on a tripod, the LNA module and the PA module at the dish's feed (short SMA leads),
   the 20 dB pad on the PA's input, the board on its PYNQ in a box with the PD banks, the laptop.
   Pointing: the far end transmits its idle carrier; the near end's ADC reads I^2+Q^2 while the dish
   is swept; 30 dBi is about a 5 degree beam.
3. The experiment: lock; the latency line's last points (20 km is 66.7 us of flight: the electronics'
   23.5 ns is the quantity the whole project is about, and it is measured against the flight time);
   error rates per scheme; the whitened stream against the idle carrier; the slow path's veto counts.
   The budget's reach for this arrangement is beyond 100 km on both paths; the margin at 50 km is
   what the weather and the pointing eat.
   *Pass:* a locked link with quiet BPSK at the chosen distance and a latency intercept that agrees
   with the lab's.

## The dead-on-arrival list against the stages

| # | risk (PLAN.md section 10) | guard on the board | stage that retires it | if it bites |
|---|---|---|---|---|
| 1 | the Costas loop does not lock, or runs away | JP101/JP102 flip the sign; LOOP_SEL = FPGA gives a plain PLL on Q; VC_OFF sweeps; VC / ERR / I / Q monitors; HOLD; the ADC | 3.3 | move both sign jumpers; lower the DSA; a plain PLL on Q first |
| 2 | demodulator DC offsets eat the fast comparators' 20 mV | **I_OFF_F** (DAC 2 D) and **Q_OFF_F** (DAC 1 C) trim the fast arms (Responses 8, 14); the window thresholds adjustable; the ADC reads the offsets | 3.2 | re-trim both arms, then the thresholds |
| 3 | the 3.8 V level shift into a 3.3 V FDA (the summing nodes 128 mV under the guaranteed 2.0 V; 61 mV at the worst corner) | the DNP 1.5 k on ADJ drops the common mode to 2.5 V; each arm's PD is separate | 3.2 | fit the 1.5 k (an 0402: JLCPCB's job, or a rework) |
| 4 | 5.8 GHz layout: 28 dB of cascaded gain, the balun, the LO pairs, the LNA match, the couplers | CPWG with via fences, the vendors' layouts, the DSA between the stages, four RF monitors | 2.3, 3.1 | the DSA tames an oscillation; the TX pi pad; the couplers' real coupling is calibrated once |
| 5 | the LO is wrong (registers, lock-detect polarity, Kvco, level) | MUX = lock detect; LO MON taps; every register is a write; REF IN | 2 | software; the loop filter values are 0402s |
| 6 | own transmitter into own receiver | two antennas 600 MHz apart (31 dB from the arm), the DSA, the LNA module's filter, time division with the switch | 4.1, 5.3 | separate the whips; the switch block; the filter module |
| 7 | heat: 6.8 W | the PLL regulators' 2.2 ohm; exposed-pad vias; +5V_RF pour | 1.4 | a fan; TX_DIS and the DSA idle parts |
| 8 | the slow path's offsets or saturation | I_OFF / Q_OFF, V_T2; the nulling routine | 3.2 | the fast path works without it |
| 9 | the single-ended ladder drive wobbles the modulator's common mode | VR_I / VR_Q trims; the receiver cares about sign | 2.3, 3.5 | accept the -15 dBc feedthrough as a fixed vector |
| 10 | parts and the order: five HMC536 at JLCPCB, the ADL5375's thin shelf (4 on 2026-10-14; Digi-Key fallback), two DACs by address, CPL rotations | PLACEMENT_CHECKS.txt, the preview, the HMC427A as a second-source switch | 0 | order the day the stock is checked |
| 11 | the Icepi Zero: no pull-ups, 5 V from its own USB-C, no gateware | DNP 4.7 k; JP301 open; the same Verilog top | 1.5, 4 | fit the 4.7 k |
| 12 | a generated symbol with pins swapped | the pin audit (done: two incomplete symbols found and fixed) | 0, 3 | a rework is unlikely to save a QFN with a swapped pair; order one board first if in doubt |
| 13 | **new:** the TCXO's pin 1 is undocumented in its datasheet text (control or NC); the symbol leaves it open | nothing | 2.1 | if the TX synthesizer's reference is off frequency, pin 1 wants 1.65 V: a rework wire to the VCXO's divider |
| 14 | **new:** the HMC536's control sense (A high = receive) and the mux's select sense (S low = B1) were written backwards in two notes | the notes and the jumper default corrected; the switch rests in receive by its pull-ups | 3.3, 4.4 | the gateware's T/R table is one line |
