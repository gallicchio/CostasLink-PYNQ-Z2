# CostasLink-PYNQ-Z2 rev A: red-team review C (RF / communications systems), 2026-10-14

Read-only review of the tree as of 2026-10-14 16:53 (PLAN.md Prompt 31 state; `build/budget.json` from
`sim/budget.py`).  Every number below says where it came from.  "budget.json: X" means the key X in
`build/budget.json`; "budget.py:N" a line of `sim/budget.py`; datasheet texts are `build/txt/<part>.txt`
with the line.  My own arithmetic is in `numbers.py` and `pll.py` beside this file.

**Verdict in one paragraph.**  The architecture is sound and the loop arithmetic is right where it has
already been corrected (Kd = A/2, fn 2.9 kHz, zeta 0.69).  The PLL-inside-the-loop question is a non-issue
(section 1).  I disagree with the project on four numbers, two of which matter on the first day: (i) the
own-transmitter rejection at 600 MHz is about 21 dB, not 31 dB, and the compression criterion was computed
with one gain block and the 900 MHz IP1dB, so frequency-division duplex needs about 52-58 dB of
antenna-to-antenna isolation, not 42 (section 2); (ii) the receiver's phase noise outside the 3 kHz loop is
about 1.3-1.8 degrees rms, two to two-and-a-half times the thermal phase noise at the bench, so the bench's
CFAR windows will sit at about 0.2 a, not 0.1 a, and the slow Q window at 0.1 a will chatter (section 1,
3); (iii) the static phase error from the ADL5380's offset is 9 degrees, not 4.6, because PLAN.md section
18 divides a one-leg offset by the differential slope (section 1); (iv) the slow path's I confirmation
needs the THS4541's 20 ns overdrive recovery added to the 37 ns (section 3).  None of these blocks the
order; (i) and the WiFi exposure of a receiver with no selectivity inside +-94 MHz are the two things most
likely to make the first over-the-air test fail, and both have remedies that are already on the board
(the HMC536 time-division block, the DSA, the survey) or in a drawer (pads, a second mast).

---

## 1. Will the Costas loop lock and hold?

**The loop as fitted.**  Kd = 0.124 V/rad (budget.json: loop_Kd; one leg of Q against V_MID at the
regulated -20 dBm, a = 249 mV differential), Ko = 2.70 Mrad/s/V (loop_Ko: +-100 ppm over 2.7 V, x232),
R1 10 k, R2 750, C 100 nF: fn = 2916 Hz, zeta = 0.687, 21 % overshoot to a phase step (budget.json:
loop_fn_fit_Hz, loop_zeta_fit, loop_overshoot_fit).  I re-derived these from the fitted parts and agree.
A PI loop at zeta 0.69 has about 64 degrees of phase margin at its ~4 kHz crossover (numbers.py).

**The MAX2871 inside the loop.**  Its PLL is a low-pass from the VCXO's phase to the LO's phase: fitted
filter 81 kHz, 49.7 degrees (budget.json: pll_fc_fit, pll_pm_fit).  At the Costas crossover (4 kHz) that
is a lag of about 3-4 degrees and a gain of 1.0; the assertion `fn * 10 < 80e3` (budget.py:451) is the
right test and it holds.  Two more lags the budget does not model: the VCXO's modulation bandwidth is
"15 kHz min" (SX3V25 datasheet item 13), a pole that costs 15 degrees at 4 kHz; and the OPA2388 (10 MHz GBW)
costs nothing.  About 46 degrees of margin remain: stable, overshoot nearer 30 % than 21 %.  No change
needed; if the loop ever rings, R2 up, not R1.

The MAX2871 loop filter is robust to its own uncertainty.  The datasheet's table says "VCO Sensitivity
100 MHz/V" (MAX2871.txt:152), the budget uses 60 (budget.py:81, "40-80 across the band").  With the fitted
390 p / 6.8 n / 160 p / 820 / 2 k (pll.py): Kvco 40 -> 58 kHz, 49 degrees; 60 -> 81 kHz, 50; 100 -> 124 kHz,
46; 130 -> 153 kHz, 42.  Any of those locks.  (The early Claude review's "Low" finding on Kvco stands and
does not matter.)

**Loop gain follows the level.**  Kd is proportional to a.  DSA at its power-up 31.75 dB with the 10 m
signal: Kd x0.047, fn 630 Hz, zeta 0.15.  At the fast floor (-81 dBm at the antenna, DSA 0): Kd x0.08,
fn 830 Hz, zeta 0.20.  In the stage-3 loopback with a 30 dB pad and the DSA at its maximum: Kd x2.4,
fn 4.5 kHz, zeta 1.06.  All lock; the underdamped cases ring for tens of ms.  BRINGUP.md stage 3.3's
"set the DSA first" is the right instruction.  The loop still locks at the floor because its noise
bandwidth is ~1 kHz against the arm's 100 MHz: loop SNR about 11 + 50 = 61 dB, 1 mrad of jitter.

**Phase noise at 5.8 GHz (the part the project has not integrated).**  x232 is +47.3 dB on everything
the reference does.

| source | figure | at 5.8 GHz, outside the 3 kHz loop | integrated, rms |
|---|---|---|---|
| MAX2871 in-band floor | -230 dBc/Hz normalised (MAX2871.txt:181): -108.7 dBc/Hz to 80 kHz (budget.json: pll_pn_inband_dBc) | 3-80 kHz | 0.07 deg |
| MAX2871 VCO, 6 GHz, open loop | -71 / -101 / -128 / -144 dBc/Hz at 10 k / 100 k / 1 M / 5 M (MAX2871.txt:173-180) | above the 80 kHz loop | **0.8 deg per synthesizer** (numbers.py: 2e-4 rad^2; cross-check: the datasheet's "integrated RMS jitter 0.2 ps" at 4.4 GHz with a 65 kHz loop, MAX2871.txt:184, is 0.32 deg; the 6 GHz VCO is 6 dB noisier and 5.8/4.4 higher: 0.84 deg) |
| TX TCXO TC32H4 | -110 / -130 / -145 dBc/Hz at 100 Hz / 1 k / 10 k (26 MHz example, its datasheet) -> -63 / -83 / -98 at 5.8 GHz: 10 dB above the MAX2871 floor at 10 kHz | 3-80 kHz, through the TX PLL untouched | 0.13 deg |
| RX VCXO SX3V25 | **no phase-noise figure in its datasheet at all** (SCTF spec SCTF2022LC926, 6 pages) | 3-80 kHz | 0.4 deg if 10 dB worse than the TCXO, 1.3 deg if 20 dB worse |
| total, two synthesizers + both references | | | **1.3-1.8 deg rms = 23-31 mrad** |

Thermal phase noise in the Q arm: sigma/a = 1/sqrt(SNR) = 0.70 deg at the bench (38.2 dB, budget.json
link_rows[1]) and 4.25 deg at 3 km (22.6 dB).  So **at the bench the idle Q arm's noise is the
oscillators', not the receiver's**, by a factor of 2-2.5: sigma_Q about 6.5-8 mV instead of 3.0 mV.
Consequences: no effect on lock (the loop tracks everything below 3 kHz, and the rest is 30 mrad);
docs/TRAJECTORIES.md's bench window of 0.10 a (5.2 ns) becomes about 0.2 a (about 6.2 ns on its own
curve): one nanosecond, which the threshold servo will find by itself.  At 3 km it adds 10 % to sigma:
nothing.  The 25 MHz PFD spur (-88 dBc with a 50 kHz loop, MAX2871.txt:198; perhaps -80 with 80 kHz) lands at
+-25 MHz in the arms at -80 dBc of a 249 mV carrier: 25 uV, nothing.  Gemini's "negligible" (its 3.1) was
right for the loop and wrong for the bench windows; nobody integrated it.

**Static phase error from DC offsets.**  The loop forces ONE leg of Q to V_MID.  Any DC difference
between that leg and V_MID is an error, on a slope of a/2 = 124 mV/rad:

| offset on one Q leg | source | static phase |
|---|---|---|
| 20 mV | ADL5380 "+-10 mV differential" (ADL5380.txt:134, specified at 900 MHz with 0 dBm LO; **no 5.8 GHz figure**; expect worse from LO self-mixing at 5.8 GHz) x4, one side | **9.3 deg** |
| 5.8 mV | THS4541 common-mode offset, max (THS4541.txt:440) | 2.7 deg |
| 2.5 mV | THS4541 Vos 0.5 mV x noise gain 5 | 1.2 deg |
| 28 mV | worst-case sum | 13 deg |

PLAN.md section 18's table says 4.6 deg for "a 20 mV offset": it divides a one-leg 20 mV by the
differential slope 249 mV/rad.  The right figure is 9.3 deg (40 mV differential over 249 mV/rad, the same
thing).  Q_OFF_F (DAC1 C through 100 k) reaches +-66 mV at the arm output = +-33 mV a leg = +-15 deg
(budget.json: fast_trim_V): it covers the typical case with room and the worst case barely.  Untrimmed,
9 deg rotates the corners: a corner at 45 deg lands at 36 or 54, so one Q-window pair loses 1.5 dB of
margin and the other gains it; I = a cos 9 deg = 0.99 a.  BRINGUP.md stage 3.2 trims it; fine.  Note
that the TLV3601's own 5 mV offset on CMP_I moves the sign(I) crossing by 5/124 = 4 % of the rise (0.2
ns), and I_OFF_F trims that.

**Pull-in and frequency difference.**  TC32H4: +-2 ppm initial, +-2.5 over temperature, +-1/year
(its datasheet) = +-5.5 ppm = +-32 kHz at 5.8 GHz per TCXO.  The VCXO's "frequency stability overall
+-50 ppm" (item 6) includes tolerance, temperature, voltage and the first year, and its APR is +-50 ppm min
(item 9): nominal +-290 kHz is always reachable, so a TCXO at +-32 kHz is inside it with 9x to spare.
I agree with the author's rejection of KimiK3's APR argument.  Pull-in (type-2 loop, Delta-omega >> omega-n):
4 ms from 29 kHz, 17 ms from 61 kHz (both TCXOs at their limits), 0.39 s from 290 kHz (numbers.py; budget.json
loop_pullin_fit_ms agrees).  Conditions: the OPA2388 output (0.02-3.28 V on 3.3 V) covers the VCXO's 0.3-3.0 V,
and the beat (up to 300 kHz) passes the 94 MHz arms, so the formula applies.  A unit at the VCXO's +-50 ppm edge
on a hot day with a TCXO at +5.5 ppm has no margin, and the only re-centre is 25 MHz integer-N steps
(REVA_CHANGES.md 20, open): write the fractional-N re-centre before the field, not after.

**Polarity before power-up.**  Determinable on paper but with five sign conventions in series: the
ADL5380's Q sense for a positive phase error, the LO pair inversion (P to LOIN since REVA_CHANGES 8: it
inverts I and Q together, and sign(I)*Q is invariant to that, agreed), the mux select sense (already
corrected once, PLAN.md 10.14), two inverting OPA2388 stages, and the VCXO's pull slope, which its datasheet
does not state (positive on nearly every 3225 VCXO).  I give a first-guess 70 %; the cost of being wrong is
moving JP101/JP102, minutes.  Right design: the jumpers exist.

**A modulated carrier.**  A 180 deg flip: Q = 0 at both ends; the error is non-zero only during the
~5 ns transit (Q peaks at a/2 on the leg while sign(I) is undefined near I = 0): the integrator moves
<= 0.124 V x 5 ns / (10 k x 100 nF) = 0.6 uV, the proportional term 9 mV for 5 ns: nothing.  A 90 deg
departure (the corners): e = 88 mV on the leg for 10-100 ns: proportional 6.6 mV on VC = 2.8 kHz
(430 kHz/V, budget.json vc_kHz_per_V) for 100 ns = 0.1 deg; integral 9 uV.  The mean matters only if the
corners are all of one sign: at 1 % duty (10 ns corners at 1 MHz) a 0.45 deg rotation; random corners,
zero.  Continuous 100 Mbaud BPSK: the hard-limited Costas S-curve, textbook, with the usual squaring loss.
The plan's "the loop only ever sees the idle carrier" (PLAN.md section 1) is right.

**Where the loop is not untroubled: interference.**  PLAN.md section 13 says "a 20 MHz WiFi signal at
-40 dBm is -78 dBm in the loop's 3 kHz".  That is the linear picture; the detector is sign(I) x Q.  While
the interferer is >= 10 dB under the carrier at the arms, sign(I) is the carrier's and the product's mean
is unchanged.  Once the interferer dominates I, sign(I) is the interferer's, the mean of sign(I)*Q no longer
contains the carrier, and the loop's effective Kd collapses: the loop goes open and drifts.  At 10 m with
whips the carrier is -54 dBm at the antenna; a WiFi AP on channels 149-165 (5735-5835 MHz, i.e. inside
+-94 MHz of a 5.8 GHz carrier) is -40 dBm or more within 10 m indoors.  That is a lost lock, not a false
event.  The remedies in the tree (survey, 5775 MHz null, UNII-2C, panels) are the right ones; the sentence
is wrong.

**Answer:** it will lock and hold over a cable (section 6 gives the number).  Over the air it holds
whenever the carrier dominates the arms, which is a channel choice.

## 2. Self-interference

**The arm filter's rejection at 600 MHz is 21 dB, not 31.**  budget.py:338-340 models "two poles at
100 MHz": 10 x 2 x log10(1 + 36) = 31.4 dB (budget.json: iso_table[4].reject_dB).  The two real poles are
the ADL5380's 390 MHz demodulation bandwidth (ADL5380.txt:131; budget.py:66 dem_bw_MHz) and the THS4541's
94.4 MHz (budget.json: fda_bw_MHz): 4.3 + 17.1 = **21.4 dB** (numbers.py).  docs/TRAJECTORIES.md and
sim/trajectories.py already use the 390 + 94 pair for the step response; the isolation table did not.

**The compression criterion has two errors.**  budget.py:343 `leak_max = ... (dem_ip1db - 10) - (lna - il
- dsa + gb_gain)` counts ONE ADL5611 where N_GB = 2 (budget.py:282), and dem_ip1db_dBm = 11.6 (budget.py:64,
commented "5.8 GHz column") is the 900 MHz row; the 5800 MHz row is **8.2 dBm** (ADL5380.txt:208).  The
compression limit at RX ANT is -35.8 dBm, not -18.

**Isolation needed (own TX +9.8 dBm, budget.json tx_out_dBm):**

| scenario | wanted at RX ANT | leak must be below (wanted - 10 + 21.4 dB) | isolation needed | budget says |
|---|---|---|---|---|
| 10 m, whips | -53.9 dBm | -42.4 dBm | **52 dB** | 42 |
| 300 m, panels, 10 m cables | -49.4 | -38.0 | **48 dB** | 42 |
| 3 km, panels | -59.4 | -48.0 | **58 dB** | 42 |
| compression, any scenario | | -35.8 dBm | 46 dB | (32 as computed) |

PLAN.md section 3 gives "two patches side by side 30-40 dB".  So FDD with both panels on one mast is
10-20 dB short, and the 2nd ADL5611's output P1dB (12.8 dBm, ADL5611.txt:187-194) is not the limit (the
leak there is 13 dB under it).  What closes the gap, in order of cost: time division with the HMC536
block (27 dB min isolation, HMC536.txt:46-51, and the own leak at -17 dBm is then at zero IF: DC in the arms,
which LOOP_HOLD handles); cross-polarised panels (20-30 dB); 3-5 m between the masts (the free-space term
alone: 53 dB at 3 m for whips); the SAW-LNA module's filter (30 dB **assumed**, PLAN.md 2c, unmeasured).
On the bench: two whips on the board's own SMAs (32 mm) give about 14 dB (Gemini's 15-20; numbers.py 14 by
Friis) -> -4 dBm at the LNA = its input P1dB (-4 dBm typ, SKY65404 Table 4) and 5 dB under its +1 dBm absolute
maximum (Table 2): with the QPSK corners 3 dB hotter and a cable mis-plugged it is a dead LNA.  BRINGUP.md
stage 4's "transmit whip on a 1 m lead" gives about 44 dB -> -34 dBm at RX ANT: meets compression by 2 dB,
8 dB short of the wanted-signal criterion at 10 m.  **Use 3 m, or put a 10-20 dB pad in the TX lead for
the bench** (the 10 m link has 38 dB of SNR: 20 dB of pad costs nothing), or start with the switch block.

What the leak does when it is only 8 dB short: a 600 MHz tone at -8 dB of the wanted at the comparators.
It does not move the loop (section 1: sign(I) stays the carrier's).  It does smear every window by the
tone's amplitude, which the CFAR servo pays for in threshold, and it sits above the TLV3601's 325 MHz
toggle rate, so the comparators average it rather than follow it.  Degrades, does not kill.

**LO leakage out of the RX antenna:** ADL5380 LO-to-RF -47 dBm at 5.8 GHz (ADL5380.txt:212), then
backwards through the balun (-1), two ADL5611 (S12 -26.7 dB each at 5800, ADL5611.txt:284), the DSA (-2.4
- setting) and the LNA (S12 -26 dB typ): about -135 dBm.  Nothing.  Board radiation from the LO pair
(+5 dBm differential, MAX2871.txt:159) coupling to the RX line is the real path and is unknowable before
the board; -60 to -80 dBm at the jack would be typical and is irrelevant 600 MHz from the far receiver.

**The far board's transmitter into this receiver on the bench.**  Stage 3 loopback with a 30 dB pad:
-20.2 dBm at RX ANT.  That is 7 dB above the top of `received_dBm()`'s range (-27 dBm, budget.json
rssi_range_dBm): the DSA pins at 31.75 dB and the demodulator sits at -12.7 dBm (21 dB under its 5.8 GHz
IP1dB: fine), the fast arms at +-570 mV differential (the THS4541 swings +-2.9 V: fine), the slow path
saturated either way.  Kd x2.4 (above).  The LNA at -20 dBm is 16 dB under its P1dB.  **Make the loopback
pad 40 dB** so the regulated level is reachable, and never under 20 dB (a bare cable is +9.8 dBm into a
+1 dBm part).  BRINGUP.md says 30 dB; it works, but the numbers in its stage 3 assume the regulated level.

## 3. Decision margins

Noise floor -92.0 dBm in 100 MHz with NF 1.96 dB by Friis (budget.json noise_floor_dBm, nf_chain_dB;
I re-did the cascade: 1.0 dB LNA, 2.4 dB DSA, 6.0 dB ADL5611 at 5.8 GHz twice, 15 dB ADL5380 (the datasheet
says 15.5, ADL5380.txt:216): 1.96 dB, agreed).  a = 249 mV differential at the regulated level, sigma per
quadrature = a / sqrt(SNR); CFAR window for one false event an hour on two comparators at Rice's nu0 =
183 MHz (docs/TRAJECTORIES.md): u = 7.5 sigma.  End-to-end rise 6.6 ns 10-90 (TRAJECTORIES, the PYNQ header
included), so the slope g'(t) is about 0.08/ns at g = 0.1 and 0.12/ns at mid-rise.

| case | RX at ANT | SNR (100 MHz) | sigma (thermal) | window | fast event at the FPGA | jitter (thermal / with 1.5 deg of LO noise) |
|---|---|---|---|---|---|---|
| bench, 10 m, whips | -53.9 dBm | 38.2 dB | 3.0 mV | 0.09 a thermal; **~0.2 a with LO phase noise** | 9.9 ns (TRAJECTORIES) -> ~10.9 ns | 0.15 ns / 0.35 ns, plus the 1.25 ns grid's 0.36 ns rms |
| 100 m, whips | -73.9 | 18.2 | 30 mV | 0.92 a: **does not fit** (TRAJECTORIES section 4: below 19.2 dB the fast path cannot be quiet) | slow path only, +37 ns (+20, below) | -- |
| 100 m, panels, 10 m cables | -39.9 | 52.2 | 0.6 mV | 0.02 a, i.e. the comparator's own 5 mV offset and 3 mV hysteresis set it | ~9.5 ns | grid-limited, 0.36 ns |
| 1 km, panels, 10 m cables | -59.9 | 32.2 | 6.1 mV | 0.18 a | ~10.9 ns | 0.25 ns / 0.3 ns |
| 1 km, whips | -93.9 | -1.8 | -- | nothing | nothing | -- |
| 3 km, panels (the project's "range" case) | -69.4 | 22.6 | 18-20 mV | 0.60 a | 13.1 ns (TRAJECTORIES) | 0.6 ns (agreed) |

So the stated latency (23.5 ns electronics, budget.json latency_ns; 15.0 ns on the receive side) holds
at the bench and with panels to 1 km within about 1 ns; with whips the useful fast range is tens of metres
(PLAN.md 13's 69 m quiet is the 1e-4 standard, not the one-an-hour one; section 18's 21-35 m is the honest
figure).  False-alarm rate: Rice's formula with 7.5 sigma is 1/h on thermal noise (agreed), but the bench
sigma is the oscillators' (section 1), and neither includes WiFi: a 100 us WiFi frame inside +-94 MHz is an
event the slow path confirms (it lasts far longer than the 60 ns confirm delay), so the veto does not help
against it.  The real false-event rate across a room will be the WiFi duty cycle on the chosen channel,
not 1/h.  Gating the windows to the round's schedule (docs/SYSTEM.md 2) is the right fix.

**Comparator input against its requirement.**  Each window comparator sees one leg, V_MID +- a/2 =
+-123 mV at the regulated level, against an AD5696R threshold; the TLV3601/3603 is rail-to-rail with
+-5 mV max offset and 1.5-5 mV hysteresis (TLV3601.txt:333, 342): adequate, and the servo calibrates the
offset out (constellations.txt section 7: 5 mV = 1.6 sigma at the bench, 0.3 sigma at 3 km).  Two
things the trajectory model leaves out and that cost time at the bench: tpd 2.5 ns is at 50 mV overdrive,
with 600 ps of dispersion from 10 to 125 mV (TLV3601.txt:391, 416).  At a window at 0.1-0.2 a the signal
passes the threshold with a slope of (a/2) x g' = 123 mV x 0.08/ns = 10 mV/ns, so 50 mV of overdrive
arrives about 4-5 ns after the crossing: the comparator will fire roughly 0.5-1 ns later than the model's
2.5 ns.  Not at range (slope at 0.6 a is 15 mV/ns, but the window is far from the idle so the overdrive
grows into the settled a/2 - 0.6 a/2 = 50 mV anyway).  Expect the bench event at 11-12 ns at the FPGA,
not 9.9.

**The header's 800 Ms/s.**  ISERDESE2 in DDR at 400 MHz on an XC7Z020-1: inside the -1 HR bank's 600 MHz
BUFIO limit, and the overlay met timing with 0.35 ns of pulse-width slack (REVA_CHANGES 7; gateware/README
line 17: WNS +1.66, WHS +0.03 ns).  The physical limit is the header: 233 ohm into ~10 pF (budget.json
cmp_series_rc_ns, hdr_C_pF estimated) is a 2.3 ns time constant, 1.6 ns to 50 % and ~5 ns 10-90: the
1.25 ns grid oversamples a 5 ns edge, which is what you want for a time stamp (0.36 ns rms from the grid),
but the shortest pulse the header passes cleanly is about 5 ns, the same as the 4-sample decision delay.
Any faster is the Icepi or rev B.  No issue for rev A; the 10 pF should be measured (BRINGUP 3) because
every latency figure scales with it.

**The slow path.**  The slow I stage idles at 20 x 249 mV = 5 V differential against a 2.9 V swing: 1.7x
overdriven.  The THS4541's "overdrive recovery time, 2x output overdrive: 20 ns" (THS4541.txt:317, 522) is not
in sim/trajectories.py (its clip is instantaneous).  The modelled 36.7 ns for CMP_I_S becomes up to
~55 ns.  The Q stage is not saturated at idle, so its 17.7 ns stands.  RX_TIMING's 60 ns confirm delay still
covers it with a few ns to spare; set it to 80 ns on the first day and shorten it from the measurement.
And the slow Q window V_T2 = 0.1 x 20 a / 2 (TRAJECTORIES) is 3.8 sigma of the 1.5 deg LO phase noise:
CMP_QP_S / CMP_QN_S will toggle at hundreds a second on the bench with nothing sent.  Harmless for the veto
(the chance that the phase is beyond 0.1 rad at the one instant the slow comparators are read is 1e-4),
but the "slow path alone as the data path" at -92 dBm needs V_T2 servoed like V_T.

## 4. Power and thermal

1.365 A at 5 V = 6.8 W (budget.json I_total_mA), 828 mA of it on +5V_RF.  The input path at its maxima
drops 0.215 V (vdrop_in_max_V): the ADL53xx's 4.75 V minimum needs **5.10 V at the plug** (supply_min_V;
4.89 V at the chips).  A USB-C source must hold 5.1 V at 1.4 A at the connector: a bench supply with a
short lead does; most 5 V/3 A chargers deliver 4.9-5.0 V at the far end of a 1 m cable (0.1-0.2 ohm x
1.4 A); a laptop port does not.  V5_MON (Prompt 28) reads it, and the first thing to check is that it says
>= 4.85 at full load.  Agreed with Gemini's and Grok's finding and the author's gate.

**The PYNQ's 5 V header.**  The PYNQ-Z2's 5 V rail is the output of its on-board regulator from the 7-15 V
jack (GPSDO-PYNQ-Z2/README.md section 8: TPS65400, "hundreds of mA of headroom", judged for a 100 mA load);
the PYNQ itself takes 1-1.5 A of it (Zynq, DDR, Ethernet, USB host).  Nobody has measured 1.37 A more
through two 0.1" pins (1-3 A each) and that regulator.  PLAN.md line 327 already makes USB-C the default
and allows the header only on the barrel supply; I would go further: **do not use JP301 until the PYNQ's
5 V has been measured under this load**; a brown-out of the PYNQ mid-session (GPSDO review item 32 saw
exactly that with a 100 mA load on USB power) is a lost afternoon.

**Heat, by part** (power x theta-JA from the datasheets; junction at 25 C ambient / in a 60 C box):

| part | W | theta-JA | rise | junction at 25 / 60 C |
|---|---|---|---|---|
| ADL5380 (245 mA worst, budget.py:67; ADJ open draws less) | 1.23 | 53 C/W (ADL5380.txt:232) | +65 | 90 / **125** |
| ADL5375 | 1.02 | 54 (ADL5375.txt:325) | +55 | 80 / 115 |
| ADL5611, each of three | 0.62 | 52 (ADL5611.txt:302) | +32 | 57 / 92 |
| MAX2871, each (200 mA max) | 0.66 | 29 (MAX2871.txt:93) | +19 | 44 / 79 |
| PLL LDO after 2.2 ohm | 0.25 | 187 (budget.py:88) | +47 | 72 / 107 |

Bench: fine (BRINGUP 1.4's "50-70 C on the QFN tops" is consistent).  A roof box at 60 C puts the
ADL5380 at its 125 C junction limit and the LDOs at 107: shade, vents, and the NTC's reading before every
session (docs/SYSTEM.md 3 says so).  The PTC derates to 1.3 A at 85 C (Grok 7): the same box.  Two
remarks: theta-JA 53 C/W assumes the datasheet's 4-layer board with the paddle soldered and its 3 x 3 via
grid (REVA 10, done); and the DNP 1.5 k on ADJ, the remedy for the FDA common-mode margin (PLAN.md 10.3),
raises the ADL5380 to the full 245 mA and changes its 5.8 GHz gain and IP1dB (the 5800 MHz spec row is
"ADJ pin left open", ADL5380.txt:206; Figure 41 gives the RBIAS dependence): the remedy costs heat and
some gain at exactly the frequency that matters.  Measure the summing nodes first (BRINGUP 3.3 does).

## 5. Top ten failure modes, probability, salvage

| # | failure mode | my P | what is still measurable |
|---|---|---|---|
| 1 | **Own-transmitter leak in FDD** (section 2): the 1 m whip lead or two panels on one mast leaves the 600 MHz tone within 10 dB of the wanted at the arms, or compresses the chain | 0.6 that the first two-antenna test shows it as described | Everything: TDD with the HMC536 block, a pad in the TX lead, 3 m between whips, cross-pol panels.  Not a board defect |
| 2 | **WiFi inside +-94 MHz** captures sign(I) and unlocks the loop, or floods the windows (section 1, 3) | 0.5 across a room at 5.8 GHz on an unsurveyed channel | The survey (Prompt 26), channel choice (UNII-2C, 5775 null), the window gate; the detectors measure the interference itself, which is a result |
| 3 | **LO phase noise exceeds the thermal sigma at the bench** (section 1): windows at 0.2 a, slow Q window chatters, bench latency 1 ns later than TRAJECTORIES, and the VCXO is unspecified | 0.7 | The threshold servo finds the window; ERR MON / the ADC spectrum measures the phase noise (a result in itself); the VCXO is a 3225 footprint, swappable for a specified one |
| 4 | **DC offset / static phase beyond the trim** at 5.8 GHz (the +-10 mV is a 900 MHz figure; the worst-case sum is 13 deg against a 15 deg trim) | 0.2 | The ADC reads the offset; Q_OFF_F and I_OFF_F; constellations with a known rotation are still constellations |
| 5 | **The 5.8 GHz chain oscillates or is low** (LNA + DSA + 2 x ADL5611: 39 dB in a row; balun, LO pairs, couplers never built) | 0.15 | The DSA between the stages; the TX side alone through a cable; the four RF monitors; the loop on a generator |
| 6 | **The THS4541 summing nodes over 2.0 V** (61 mV margin at 3.95 V, budget.json fda_vn_cases) distort an arm | 0.25 | Fit the DNP 1.5 k on ADJ (with the heat and gain cost above); each arm has its own PD, so one arm can be tried alone |
| 7 | **Loop sign wrong on the first try** | 0.3 (no lock at all with either jumper setting: 0.05) | JP101/JP102; LOOP_SEL = FPGA for a plain PLL on Q; open-loop beat on I/Q MON measures the whole chain anyway |
| 8 | **Slow path: saturation recovery and offsets** make the 37 ns confirmation 55-80 ns and the slow windows noisy | 0.5 | RX_TIMING's confirm delay is a register; the fast path works alone; the slow path's statistics are a measurement |
| 9 | **Power source sag or the header path** (section 4) | 0.3 that someone powers it from the wrong thing once | V5_MON says so; a bench supply at 5.2 V |
| 10 | **Parts and placement**: five HMC536 at JLCPCB, the ADL5375's thin shelf, a QFN rotation, a pin figure misread (PLAN.md 10.10, 10.12) | 0.2 that one part comes back wrong | Everything that does not use that part; the switch block is separable; the TX side and RX side are separate chains |

Not in the ten, because the earlier reviews fixed them: the LO pairs, Kd, the 5 V maxima, the paddle vias.
The MAX2871 Kvco is not a failure mode (section 1).

## 6. Probabilities

| | event | P | one line |
|---|---|---|---|
| a | powers up, rails correct | **0.85** | 349 placed parts from a generated pipeline with a pin-by-pin audit, net_check on every pad, two review rounds on the power path; the ECP5 board precedent.  The 15 % is a swapped pin figure or a rotation |
| b | both synthesizers lock | **0.75** | given (a) 0.9: register words from the datasheet example, a loop filter stable from Kvco 40 to 130, REF_IN wants 0.7 V p-p to VCC (MAX2871.txt:124) and gets 3.3 V CMOS; the 10 % is lock-detect polarity, the VCO band select on a first write, or a dead LO pair |
| c | the Costas loop locks over a cable | **0.65** | given (b) 0.85: textbook structure, the sign is a jumper, the gain is a DSA write, the offsets are trimmed; the 15 % is an oscillating RF chain or a distorted arm (modes 5, 6) |
| d | a bit through on the bench at the stated latency | **0.55** | given (c) 0.85: the comparators and the gateware are the mature part (simulated against the RTL); "stated latency within 3 ns" I put at 0.7 of that because the 10 pF, the comparator's overdrive and the phase-noise window each cost about a nanosecond at the bench |
| e | over the air across a room | **0.45** | given (d) 0.8: modes 1 and 2 are the whole gap; both are set-up and channel choice, not hardware |
| f | over 100 m line of sight | **0.35** | given (e) 0.75: panels and 10 m cables make the SNR trivial (52 dB); the isolation (48 dB needed, two masts or cross-pol), the amateur-band identification and the roof logistics are what fail |
| g | the rev A measurement programme yields useful data even if (c)-(f) partly fail | **0.9** | The comparator statistics (EDGE_CNT on muted-carrier noise, the Rice parabola), the arms on the ADC, the loop's step response through VC_OFF, latency histograms and constellations in a cabled loopback (stage 3) all survive anything short of (a) failing or the RF chain being dead.  Even a dead loop leaves the open-loop beat, which measures I/Q balance, the DC offsets and the chain's gain |

## What this review adds to the earlier ones (read last, as instructed)

DESIGN_REVIEW_RESPONSE.md and the five reports (Claude 10-09, Gemini, GPT-5.6Terra, Grok, KimiK3) covered
the LO pairs, Kd, the 5 V path, the paddles, the switch-with-PA limit, the FDA common mode and the power-up
states; I checked those closures against the datasheet lines and they hold.  New here:

1. The 600 MHz rejection is 21 dB (the real poles are 390 and 94 MHz, not 2 x 100) and the compression
   criterion in budget.py:343 counts one of two gain blocks with the 900 MHz IP1dB: FDD needs 48-58 dB of
   isolation, not 42.  Gemini repeated the 32 dB; KimiK3 called the question unanswerable.  Both missed the
   model error.
2. The integrated phase noise of two x232 synthesizers (about 1.3-1.8 deg rms outside the loop, the VCXO
   unspecified) exceeds the bench's thermal phase sigma (0.7 deg).  Gemini said "negligible" without
   integrating; nobody looked at the VCXO's datasheet for a phase-noise figure (there is none).
3. The static phase error from the ADL5380's offset is 9.3 deg, not PLAN.md section 18's 4.6 (a one-leg
   offset over the differential slope); the THS4541's Vocm offset adds 2.7; the trim covers it.
4. The THS4541's 20 ns overdrive recovery in the saturated slow I stage (the 37 ns is 55+).
5. The WiFi mechanism against the loop is capture of sign(I), not the loop's 3 kHz.
6. The 30 dB loopback pad leaves the receiver 7 dB above the regulated level; 40 dB.
7. The MAX2871 loop filter's robustness to the datasheet's 100 MHz/V (Claude 10-09 raised it; now
   quantified: 124 kHz, 46 deg, fine).
8. The two whips on the board's own SMAs put the own transmitter at the LNA's P1dB, 5 dB from its absolute
   maximum: a bench accident waiting for a corner symbol.

Nothing here needs a copper change before the order.  Two software items should precede the field: the
fractional-N re-centre (REVA 20) and a servo on V_T2.
