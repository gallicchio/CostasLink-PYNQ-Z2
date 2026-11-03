# What the rev A bring-up found (2026-10-28 to 2026-11-02): the results

The digest of [`BRINGUP_LOG.md`](BRINGUP_LOG.md) (stages 1-3 on the bench, 4.0-4.33 over the air), written 2026-11-02 for
Jason's write-up request and for whoever picks the board up next ([`HANDOFF.md`](HANDOFF.md)).  Each claim names its
log row; the numbers are the measured ones.  What rev B should change from them is [`REVB.md`](REVB.md); the
platform question is [`../docs/REVB_DESIGN_SPACE.md`](../docs/REVB_DESIGN_SPACE.md).

## 1. The board works, and the link holds itself up with nobody there

* **Board A came up on the first power** (10-28/10-29, stages 1-3): every rail, all five I2C parts, both MAX2871
  synthesizers lock, the TX carrier, the receive chain, the Costas loop locked in loopback and then over the air.  One
  fault needed hands: the loop locked 90 degrees round with the default sign jumpers (REVB 9; JP101/JP102 moved
  2026-10-30 08:03, 3.6).  Total draw about 0.9 A at 5.3 V (1.37 A with everything on, REVB 2).
* **The link sets itself up from power-up** (4.17): `linkd.py` in the board server reads `link.json`, tunes both
  synthesizers, puts the carrier null in, measures the arms' middles and the window comparators' centres with no
  carrier, steps the attenuation down until the loop locks with the I leg at its target (15.75 dB, 171-178 mV at the
  bench), sets the windows, and keeps it.  About 25 s.
* **Every loss of lock is recovered**: 171 of 171 forced losses from the PC (4.15, 1.7-3.0 s each), 18 of 18 in the
  first unattended night (4.18), every one of soak14's and soak15's (4.24, 4.33: 92 of 328 disturbances lost the lock
  in soak15, all 92 recovered, the slowest 11.1 s after a far CW ended, none failed).  The recovery (`linkd.recover`,
  about 2-3 s): hold the loop, mute the TX, both synthesizers to 5.8 GHz, re-centre the integrator from its rail by
  I2C trims (about 1 s of the 2-3: REVB U4 asks rev B for an integrator reset), synthesizers back, VC 20 kHz above the
  learned lock, release: from above the loop always comes down into the lock (the pull-in map, 4.12).  A loss is
  judged on VC (8 kHz off for 0.5 s), so bursts that only make the comparators chatter cost nothing.
* **The page** (http://192.168.8.142:8080/) says what the link is doing in words and pictures, keeps its history
  across restarts, and was checked against the logs by 528 randomized disturbances (4.20-4.24, 4.33): 'as before',
  'back', 'no silent loss', 'slip shown' and the rest passed every time but the ten explained in 4.33.

## 2. Data on the link

| modulation | rate | result (quiet, the B210 silent) | where |
|---|---|---|---|
| BPSK PRBS15, the bits checked with the timing recovered on the board (`ber_cdr.v`) | 2-50 Mbaud | **0 errors in 8.9e10 bits** in soak15's last 4.2 h alone; 0 in 7.5e10 the night before (4.24) | 4.7, 4.11, 4.24, 4.33 |
| OOK (the carrier or its null), read on the I window | 2-25 Mbaud | 0 errors (4e-7 at 25 Mbaud until the window was moved to half the leg, 4.29) | 4.27-4.29 |
| QPSK: A3's four corners at 2.5 M a second, the idle carrier as the pilot between them, every symbol decided against what was sent | 2.5 Msym/s (5 Mb/s) | **3 044 999 898 of 3.045e9 right** (102 undecided or missed, none wrong) in those 4.2 h; 1 065 000 000 of 1.065e9 in one quiet hour after | 4.29, 4.32, 4.33 |
| FSK (ID 13: the TX turns its four points, one turn a bit, the direction the bit) | 25 kbaud-2.5 Mbaud | 1.4e6 bits, no error, received by the B210 (the board's own Costas receiver cannot read FSK: REVB 36) | 4.29 |
| the B210 as the other end: board to B210, B210 to board, both ways | BPSK 1-2 Mbaud; OOK; QPSK | no error over 60 M bits; the two clocks' offset +5.3 ppm agreed by two independent recoveries | 4.4, 4.7, 4.28-4.29 |

* **Every error ever counted with the loop locked was the timing recovery's frame lottery or a false lock of it**, both
  gateware bugs now fixed (4.6, 4.10: the check's frame started at a register write, not at the TX's symbol; then it
  locked between CMP_I's two edge clusters); since ID 6 no random segment at any carrier.  **Loss of lock is the link's
  only failure mode** (REVB 21).
* **CMP_I's duty-cycle distortion is measured in service**: the falling edges 2.2-4.4 ns after the rising ones
  (RX_CDR_SKEW, 4.10-4.11: a threshold offset on the 10-13 ns edge; REVB 20, 30).  The edge is the end-to-end limit:
  100 Mbaud closed at every phase, 50 open at 13 of 16.

## 3. Single symbols: 'idle to one of N' and their latency

* **Every scheme decides every symbol right when quiet**: A1 (BPSK flip), A1w (the flip beside the idle), A2 (the Q
  step, 1 of 2), A3 (the QPSK corners, 1 of 4): 199 999 of 199 999 in each run, hundreds of runs (4.24-4.33).  From
  ID 10 the counts add up exactly (sent = right + wrong + undecided + missed; false decisions apart).
* **Latency, from the symbol's start at the TX to the decision in the FPGA, on this board's own loopback over the
  air**: A1 58-61 ns, A1w 56-58, A2 57, A3 63-64 ns, QPSK 64 ns, with the settled decision of ID 11 (each symbol
  decided once its comparator pattern has held k samples: 2 for A1/A1w/A2, 6 for A3; 4.25, 4.32); 76-90 ns at the
  fixed delay before it.  The spread: 99.9 % within 61-69 ns.  Of the 57-64 ns, the FPGA's own part (comparator pin to
  register) is 2.7-13 ns (the fast path's pin-to-pin, 3.4g); the rest is the TX ladder's edge, the modulator, the air,
  the demodulator, the ~94 MHz arms (the 10-13 ns rise) and the settling.
* **The learning step** (plan 'learn', 11 minutes quiet, 4.32) chooses, per scheme and per lock point, the decision
  table ('all', 'info' or learned) and the timing (fixed delay or settled k) with the lowest latency that decides every
  symbol right, confirms it over 500 000 symbols, and keeps it in `learned.json` with each scheme's `rx_config` for
  the physics run's own code.  'info' (only the comparators that carry the bits) ties 'all' on latency and is the more
  robust under interference.
* **A tail**: on lock point - only, 2-3e-7 of QPSK decisions come 80-214 ns after the symbol (right, but late), with
  every table and delay; none on + in 1e9 (4.33, IMPROVEMENTS 18).  The learning step's 99.9 % does not see it.
* **The two lock points differ**: the loop locks at 0 or 180 degrees (BPSK's ambiguity), and the receiver's levels are
  not the same on each (I 171 against 174 mV, the calibrated windows QP 57 / QN 58 against 50 / 61 mV, A1 and A1w
  swap by 2.4 ns: CMP_I's rising against falling edge).  So every calibration and the learned profile are kept per
  lock point (4.25, 4.33).  A half-cycle slip (the loop moving to the other point without a loss) inverts BPSK data and
  is listed by the page (4.21-4.22).

## 4. The receiver and the transmitter, measured against an exact source (4.31)

* **The receiver is accurate to about 1-2 %**: with the B210 sending exact states, I and Q's gains alike within about
  2 %, the quadrature about 1 degree.  A second-order error of about 10 % in the corners (Q 7-15 % smaller on the
  idle's side of I; I x Q terms of about 8 mV in I and 14 mV in Q) is the board's own, in the demodulator or the arms
  (REVB 38).
* **The transmitter is saturated** (REVB 35): heard by the B210, every ladder state comes out at the idle's amplitude;
  the QPSK corners land at 40 degrees instead of 45 and A1's flip at 190 degrees instead of 180, which is why A1 moves
  Q by 30 mV (Jason's question of 2026-11-01).  The ADL5375 is driven past its linear range by the ladders.  The
  receiver's decision windows were calibrated to the states as they are, so nothing is lost today; rev B drives the
  modulator linearly.
* **The TX chain makes +3.8 dBm at 5.8 GHz against +9.8 planned**, falling 11 dB from 3 to 6 GHz (REVB 6), and the
  **receive chain's gain falls to about 7 dB at 5.7-5.8 GHz** from 37-44 at 3-4.4 GHz (REVB 8): C102, a 0.5 pF shunt at
  the LNA's input, resonates with its branch near 5.8 GHz.  The model predicts +24-25 dB back when it is lifted
  (MONDAY.md 2-3: the VNA tests A and F, then the lift).  Every result above is at 5.2 GHz for that reason (5.0 and
  5.5 as well in the weekend's rounds).
* **The loop is a hard-limited Costas loop** (sign(I) x Q): a state on the Q axis half the time pulls it 48 degrees,
  one A3 corner alone at 2.5 M a second pulls it 27 (4.29, 4.31).  QPSK therefore runs with the idle carrier as a
  pilot between the symbols, over which the four corners' pull averages to nothing.

## 5. Levels: the windows, the calibration, and what the level does to the decisions

* **The receiver's windows are absolute voltages** set by DACs (REVB 33).  Set by the plain rule (half the I leg from
  each comparator's centre) they left A3's corners 2-12 mV of margin; **calibrated from the states' own levels** (each
  window's threshold swept with the loop closed, set at `window_bias` 0.6 of the way across the plateau between the
  states that should read low and high; 4.25, 4.30) the margins are 40-48 mV.  The calibration is per lock point and
  is kept across restarts and changes of point (`windows.json`, 4.33).
* **The level matters more than anything else once the loop is locked**: a weaker carrier leaves symbols *missed* until
  linkd lowers the windows with it (it follows down, never up: raised with a stronger carrier they lost A3's corners,
  since the corners' excursions do not grow with the idle's leg; REVB 33); a **stronger carrier makes QPSK decide
  *wrong***, steeply: 19-235 wrong in 7.5 M at 2-3.75 dB stronger, 526 at 4 dB, 4 489 at 5 dB, 20 390 at 5.75 dB
  (soak15 #195, #275, #201).  Single symbols at 20 us spacing are unaffected; QPSK's corners at 0.4 us are, because
  a passing corner holds another's comparator pattern longer at a higher level.  IMPROVEMENTS 19 proposes holding the
  level with the DSA (an AGC).
* **A calibration is good to about 2 % of its level.**  Put back from `windows.json` and scaled to a leg 1.8 % lower
  (170.6 to 167.6 mV), the windows lost QPSK 1.0-1.6e-6 undecided or missed for two hours; calibrated afresh at that
  level, 1e-8 (2026-11-03 01:08).  The self-test now calibrates again at 2 % off, not 15 %.
* **`window_bias`**: at 0.5 (the plateau's middle) a CW 10 dB down made 150 times more false events than at 0.7; at 0.7
  quiet QPSK lost 3e-5; **0.6** loses nothing quiet and keeps most of the robustness (4.30).

## 6. Interference and the carrier's absence (the B210 as the world)

* **A CW near the carrier (within 80 kHz) at or above the carrier's own power captures the loop** (4.11, 4.13: VC
  dragged 39-91 kHz); the loop comes back by itself from above when it ends, and linkd brings it back otherwise.
* **A CW 1-40 MHz off at +1 dB and more drags the VCO off the carrier** (REVB 27, 4.5): every loss below the carrier
  stays lost by itself (the free loop's own push is downward, REVB 18), every one above comes back.  linkd recovers
  all of them (4.11: 280 of 280 pulls with the hold, 4.33: every drag).
* **Noise bursts (10 us-3 ms every 1-200 ms, WiFi-like) never cost the lock** (4.14, 4.18, 4.33: 70 of 70 'rode it
  out' or 'interfered' and back within a second); they cost false events and wrong decisions while they last.
* **The signal holdover** (ihold.v, the loop held while no carrier is seen) rides through carrier gaps up to about
  100 s (4.22: 33 of 33 to 53.6 s), half of them coming back a half-cycle over; it is off in deployment so far
  (Jason's call).  **The interference hold** (the loop held while the windows are busy) saved every dragging CW but is
  a net loss under bursts (it holds the loop while the symbols are missed, 4.14): off.  Free, a carrier gap of
  32-57 ms already loses the lock (4.21, 4.33); under that it rides through.
* **Where the loop lands when released** (4.12's map): from above, always the carrier; from below, a false lock 36-61
  kHz under it or the rail.  Every start is therefore from above (linkd's +20, 40, 70, 120 kHz).

## 7. Timing, clocks, and what the link can give the experiment

* The two ends' clocks (the board's TCXO against the B210) differ by 5.3 ppm and the board's timing recovery tracks it
  at every rate (4.7).  The TCXO itself: -1.006 ppm, 0.008 ppm rms reading to reading over 14 h (3.5).  TX_DIS pushes
  the TCXO by 35-80 Hz at RF (REVB 24): a carrier gap of our own moves the held phase.
* The symbol decisions time events to the 1.25 ns sampling grid (+-0.36 ns rms); a carry-chain TDC would make it
  +-0.07 ns (docs/HOSTS.md).  The recovered carrier (the locked VCXO) is a frequency reference for the receiving site:
  the basis of the verifiers' synchronization (docs/SYSTEM.md 4).

## 8. The PYNQ-Z2 and the host

* **The PYNQ hung once and nothing on the board could bring it back** (4.27, REVB 37): a `systemctl reboot` after an
  FPGA-manager DMA failure left it dead until its 12 V was cycled by hand.  It now runs from the bench supply's output
  2 so the PC can cycle it; the watchdog does so at most 3 times.
* **The image's `boot.py` loads the base overlay at every boot** 30-90 s after ours; the service now starts after it.
* **The header's 200 ohm series resistors** cost 3.7 ns of the latency (docs/HOSTS.md), and **the I2C ADC at 860 S/s**
  is the only slow readout: the page, linkd and the tests contend for it (REVB 29, U3).
* The fast path meets 100 MHz with 0.07-0.2 ns to spare on every build; the pin-to-pin fast path is 12.8-13.3 ns worst.

## 9. What is open

1. A stronger carrier's wrong QPSK decisions (section 5): the AGC (IMPROVEMENTS 19).
2. QPSK's latency tail on one lock point (section 3; IMPROVEMENTS 18): which corner, and a calibration that maximises
   the least margin.
3. 5.8 GHz: C102 (section 4; MONDAY.md 2-3).
4. Two boards, the turnaround across them, and the long lab (MONDAY.md 5-6).
5. The holdover on or off in deployment (section 6).
