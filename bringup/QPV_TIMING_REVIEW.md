# QPV timing on rev A: a review of the boards, the tests and the plan (2026-11-04, 19:45 PST)

Jason: "step back and do a full review of the situation: the current state of rev A, the current set of tests, the
current list for rev B ... tests of the speed and latency of data transmission (PRBS) and the latency and timing accuracy of
'idle to 1-in-N' ... each board as Verifier 0 and the other as the Prover: how fast can the Prover turn around and reply
to the Verifier some simple function of its 'one of 4' challenge?  How accurate and repeatable is all of the timing? ...
How low can you push the latency?  How consistent?  Related, but separately, how low latency is communication of
bitstreams? ... a thorough plan for testing with the current hardware setup until tomorrow afternoon, and then a plan for
other tests we can do."

Every number here is measured unless marked *est*; its BRINGUP_LOG row is given.  The files: `twoboard.py` (the
two-board tests), `twoboard_report.py`, `data/twoboard/` (the records, not committed), `LATENCY.md` (board A's turnaround
budget, 10-29), `docs/SYSTEM.md` section 1 (the prover's turnaround in the QPV chain), `REVB.md`, `IMPROVEMENTS.md`.

## 0. The questions, and the answers as they stand

| question | answer tonight | how sure | what settles it |
|---|---|---|---|
| **The prover's turnaround** (a one-of-4 challenge in at RX ANT to a function of it out at TX ANT) | **24-28 ns on the fast path** (comparator pins through LUTs to the ladder pins, no clock) on both boards, in loopback through each board's own switch block: A2 25.6 ns mean, max 26 (B) and 24.5 (A); B2 24.1 (A, max 26.2, no false events); A3 25-30 by reply function (B), 26.5-28 (A); B1 24.6-26.1 (A).  **72-75 ns on the clocked reply**, 51-53 with first-edge decisions (A2, B1, B2), 59-62 at a short decision delay (4.60, 4.61) | the loopback is a real RX ANT to TX ANT path (the switch block's leak, 25 dB), but it is not the air: the level is 38 dB higher than the dish link's and the far board is not involved | **the over-the-air round trip** (section 6, item 1: 10 minutes of hands) |
| **Every challenge-to-reply combination** | all 9 reply functions without a fixed point (3 XOR masks, 6 other derangements) on A3 and B1 / B2, every reply decoded right as received on A (696 of 716 captures), 4.61 | the captures are few (2-4 a point); correctness is judged by the same board | tonight: 20 000 PRBS-chosen challenges per reply map, the confusion matrix (section 5, T4) |
| **Consistency of the turnaround** | within a setting the captures spread by about 5 ns (A3: 22.5-37.5 across challenges and maps; A2's counter max - mean 0.4 ns); the spread is the FPGA's pin-to-pin share, 3.75-15 ns, which depends on which comparator edge lands first and which ladder bits change | the counter's minimum (13.75 ns in every row) is an artifact (the stimulus's own two-bit change read as two arrivals); the mean is biased by it | tonight: distributions from hundreds of captures per challenge, the counter's guard swept (T3) |
| **The timing resolution** at the verifier | the sampler's 1.25 ns (800 MS/s); the comparators' dispersion 0.6 ns over 12 dB of level (LATENCY.md) | | tomorrow: the hardware reference across the boards (item 2), the scope (item 3) |
| **Idle-to-1-in-N: detection latency and its jitter** | not measured on the dish link (the receiver has no time reference for the sender's events); on one board: single symbols decided 59-63 ns after the event once settled (ID 11), 76-90 with a fixed delay; a tail of 2-3e-7 at 80-214 ns on one lock point (REVB 40) | | tonight: the RX latency counters and 1.25 ns histograms in loopback per scheme and setting (T1); tomorrow: one cable, B's TRIG OUT A to A's TRIG IN (item 2) |
| **Idle-to-1-in-N: right decisions over the dishes** | with the windows placed from the received constellation: A2 / A3 / B1 / B2 all working in loopback; across the dishes A3 98 / 100 / 10 / 96 % by message and A2 98 / 100 % with the earlier windows (4.60); the constellation windows across the dishes are in the campaign now | | the campaign's events step (running) |
| **Bitstream latency** | not measured.  *est* 17.5 ns from the ladder pins to the comparators (the captures' loop time) + half a symbol (the timing recovery samples mid-symbol) + the decision; over the dishes + 139.75 ns of cable and air | | tonight: the lag of CMP_I against the ladder's I bit in one capture during PRBS, per rate and level (T2); tomorrow: on the scope (item 3) |
| **Bitstream rate** | 0 errors at 2 MBd (A -> B, 20 Mbit) and 2e-7 (B -> A); 0 at 0.5 MBd; 20 MBd and more are in the campaign.  On one board at the bench: 50 MBd open at 13 of 16 sampling phases, 100 MBd closed (REVB 20: the end-to-end edge is 10-13 ns) | | the campaign (periods 5-1000 clocks); tonight's T2 adds periods 1-4 with the phase swept |

**The one structural fact:** with the cabling as it is (one dish per board behind its T/R switch), **no round trip over the
air is possible at speed** (REVB 55): each switch block passes the board's own TX to its own RX 25 dB down in either state
(about -17 dBm against the far board's -55), and rev A has no mute that is both fast and quiet (DSOP takes 112-126 ns to
come back on; the baseband null leaves the 25 MHz sidebands).  The prover needs its TX and RX on separate antennas.
Section 6, item 1 does that with two FPV antennas on the bench and ten minutes.

## 1. Rev A as it stands (both boards, 2026-11-04 evening)

**Hardware.**  Boards A and B, both with C102 lifted (A 11-03, 4.44; B by Jason), the same shunts (JP101 Q+, JP102 Q-,
JP103 CMP, JP201 TCXO, JP203 TRIG>Q), on PYNQ A (`pynq-a`, 192.168.2.99) and PYNQ B (`pynq-b`, .98), overlay ID 13, the
drivers identical.  TX +8.5 / +8.3 dBm at TX ANT at 5.2 GHz (A / B), +3.8 / +3.2 at 5.8 (REVB 6); the output nulls at 5200
MHz -61 / -69 dBc (4.55, 4.58); the 25 MHz sidebands -38 dBc on both (REVB 5); each board's RX synthesizer puts sidebands on
its own carrier at the two synthesizers' offset (REVB 57: -40 dBc at 166 kHz), so a sender's RX synthesizer is parked 700
MHz away.  Each board: TX ANT -> SW TX, SW RX -> RX ANT, ANT -> 10 m cable -> a 24 dBi dish; the dishes across the RACON
room (139.75 ns SMA to SMA, 4.43).  The DSA875 on an FPV antenna near the beam; the SDS1104X-E on board A's monitors.

**The link.**  -54.4 to -55.3 dBm at RX ANT both ways, steady to 0.2 dB; linkd's setup locks 4 of 4 (B -> A) and 1 of 1
(A -> B) in 59-112 s, 113 of 113 looks locked over 60 s each way (4.59).  Setup stops at its 6 dB floor (DSA 7.75) with the
I leg at 82-90 mV, under its 150 mV target: the link is **5-9 dB weaker than the VNA predicts** (A's +8.5 dBm - 50.3 dB -
4.4 dB of switch arms = -46 dBm expected; by the legs against 4.45's one-board run, about 6 dB).  Unexplained (section 6,
items 4-5).  The ripple test (4.61): the link is dish to dish, with a direct board-to-board path 18 dB under it (B -> A).

**What works.**  Lock both ways; BPSK, on-off and the I flip on a window at 0 errors in 2 Mbit; the Q bit 3e-4; A2 / A3 /
B1 / B2 events with the windows from the received constellation (in loopback; across the dishes running now); the prover
in loopback on both boards, every reply function; both switches isolate 24-28 dB; the two PYNQs, the watchdog, the
campaign running unattended.

**What is open** (each with where it is being chased):
1. The 5-9 dB of link loss (tomorrow: the VNA, the aim).
2. B -> A errors in bursts, 25 of 841 one-second windows at BER 2.1e-7, every 25-30 s with gaps, and after the analyzer's
   wide sweeps (4.60); the hourly soak halves with the analyzer sweeping and paused are in the campaign.
3. Q on-off at 3.6 % (the Q step on QP is 39 mV against I's 85: the receiver's Q leg is smaller at this level); the
   constellation levels now recorded per point will say whether it is the TX's saturation (REVB 35) or the receiver.
4. The lock sits turned against the arms' middles (B's Q 19 mV off at the idle); I = -1 points land 60 mV off in Q (4.61).
   Firmware places the windows round it; rev B should remove it (section 4).
5. The window comparators' offsets, tens of mV, and linkd's centres falling back to V_MID (IMPROVEMENTS, across two boards).
6. The pilot schemes' idle is pulled round by the events themselves (B1's (1, 0) read on -I at 4 % duty): measured at 0.4 %.
7. The counter's 13.75 ns artifact; A3's first-edge decisions wrong; the QPSK latency tail (REVB 40).
8. REVB 56 (the held loop's frame), 55 (the mute), 49 / 54 (the leaks), 57 (the RX synthesizer's beat).

## 2. What QPV asks of the radio, restated

From `docs/SYSTEM.md` section 1: the prover's clock starts when the challenge reaches its receive antenna and stops when
the answer leaves its transmit antenna; the verifier's own delays are calibrated out; the answer has four messages (click
A, click B, no click, invalid) that must all leave at the same time after the detection window; the radio's share of the
prover's chain is 23-39 ns of 113-225 (the Pockels driver 25-55, the detector 10-60).  c t / 2 of the turnaround's
uncertainty is the position's slack.  So the figures to establish, in order:

1. **The prover's turnaround distribution** per scheme and reply function: mean, p99.9 and worst, and what the worst is
   (the FPGA's path, a late comparator, a false event).  A constant-time reply is worth more than a fast one.
2. **The verifier's timing of the reply**: resolution (1.25 ns samples), jitter, and its dependence on level (the
   comparators' dispersion) and on which message came back.
3. **The one-way latency of the link** and its stability over hours (temperature, WiFi, the loop's state): the calibration
   the verifier subtracts.
4. **The bitstream**: for an n-bit challenge, the time to the last bit (half a symbol plus the fixed path), the rate the
   receiver's edge allows (10-13 ns end to end), and whether a bitstream and a single-symbol reply can share one link.
5. **Robustness**: false events at the idle (an attacker's room), lock loss, interference.

## 3. The tests with fresh eyes: what each measures, and what it cannot

| test (file, row) | measures | cannot | gap, and what fills it |
|---|---|---|---|
| `loopback_turnaround` (the RT counter: `twoboard.py prover`, 4.60-4.61) | over 5000 stimuli: the stimulus's echo to the reply's echo, min / mean / max, misses; both paths; every reply map; each factor | which challenge got which reply; the counter's minimum is the stimulus's own two-bit change (13.75 ns), which biases the mean; nothing about the far board | T3: the guard swept (8-24 samples) so a stimulus is one arrival; the captures for the per-challenge truth |
| the captures (`loop_captures`, `check_capture`) | sample by sample (1.25 ns): the ladder pins and the five comparators; the stimulus's and the reply's codes; the reply as received; the FPGA's share (pins to pins) and the RF loop's (17.5 ns) | few (1.9 s each: 2-4 a point) | T3: 32 a challenge at the best settings for a distribution |
| the reply maps (9 derangements) | every function of a one-of-4 challenge that changes the point | the map is fixed per run: a per-challenge random function needs a reload | T4: PRBS-chosen challenges against each map, 20 000 at a time, the confusion matrix [challenge][decoded reply] |
| `events` across the boards (4.60) | right decisions per message, extra events, the idle's false rate, the event-to-event histogram | **any timing**: the receiver has no reference for the sender's event (the latency counters count from this board's own TX event) | T1 in loopback (the board's own reference); tomorrow the hardware reference (item 2) |
| `prbs` across the boards | BER per comparator, rate, polynomial, timing-recovery gain and mode, sampling phase, threshold, CMP_I's trim, level | latency; rates above 20 MBd (periods under 5 not in the plan) | T2: periods 1-4 with the phase swept; the latency by capture |
| the soak (4.59-4.60) | BER against time at 2 MBd; the looks' level | the cause of the bursts | the campaign's hourly soak halves; the WiFi records on the same clock |
| the ripple (4.61) | the paths' delay differences | the absolute loss | tomorrow's VNA |
| the nulls on the FPV antenna (4.61) | B's nulls over the band (within 1.5 mV of TX ANT at 5200) | A's (3.7 mV off: its own radiation) | TX MON into the analyzer (item 6) |
| the one-factor sweeps | each knob's own effect about a baseline | interactions | the campaign's random phase (every parameter drawn jointly) |

**Assumptions to challenge.**
* *The loopback stands in for the air.*  The leak is 38 dB stronger than the dish link (DSA 29.75 against 7.75), the leg
  170 mV against 85: the comparators' overdrive and the windows' absolute place both differ.  LATENCY.md found 0.6 ns over
  12 dB of level and tonight's DSA sweep (16-31.75) moved A2 by nothing, so the turnaround should carry over; the
  *decisions* (false events, the Q steps) may not.  Only the over-the-air round trip settles it.
* *A reply is "right" when the same board decodes it.*  True for the loopback; the verifier's decoding of the prover's reply
  over the air is the real test (item 1).
* *The windows at 0.1-0.3 of the gap give sub-20 ns means.*  They do not: 14-29 false events in 5000 and maxima of 35-42 ns;
  the early arrivals are false.  Every latency figure must be quoted with its false-event count.
* *The sampler's 1.25 ns is the floor.*  For a one-board measurement yes; across the boards the sender's clock and the
  receiver's sampler are unrelated, so the reference itself jitters by up to 1.25 ns: the hardware reference (TRIG IN) is
  sampled the same way, but the scope (1 GSa/s, averaging) is independent.
* *The dish link is the link.*  The ripple says so (a direct path 18 dB down), but the 5-9 dB of missing loss is not
  explained, and a partly cancelling path would look like loss.

## 4. The rev B list, as it bears on timing

Rows already in `REVB.md` that set the floor or the spread: 9 (the I arm inverted: every Q-carrying scheme sent by name has
its Q the wrong way; the mirror is handled in `twoboard.py` and listed for linkd), 15-17 (the trims and mid-points), 20 (the
10-13 ns edge: 100 MBd closed), 25 (no lock detector), 29 (the loop's state reaches the FPGA only through comparators and
I2C), 30 (CMP_I's edges asymmetric by 2-4 ns), 32 (the fixed decision delay), 33 / 36 (the windows absolute and shared),
35 (the TX saturated), 38 / 48 (I/Q gain and the bilinear corner error), 40 (the QPSK tail), 42 (1 of 8), 45 (REF OUT),
49 / 54 / 55 / 56 / 57 (the leaks, the mute, the held loop, the RX synthesizer's beat), and LATENCY.md's knobs (rows 1, 3,
6, 9, 13).  **New from tonight:**

| what tonight showed | evidence | rev B | now, in firmware |
|---|---|---|---|
| each window comparator's offset is tens of mV, and linkd's centres (a Rice fit on noise edges at DSA 31.75) find none on a real link | 4.60-4.61: every centre 1.65 V; A2 / A3 decided nothing until the windows came from the carrier | auto-zeroed comparators, or the thresholds' DAC with a calibration pin; comparators read back by the FPGA | the windows from the received constellation (`scheme_windows`), to go into linkd |
| the lock sits turned against the arms' middles: I = -1 points 60 mV off in Q | 4.61 (1) | the Costas error from the comparators or a digital loop, so the lock point is where the decisions are made; or a DC servo on each arm | the per-scheme windows (done); a rotation term in the learned profile |
| a pilot idle (0.2 of a point) is pulled round by the events themselves | 4.61 (1): B1's (1, 0) read on -I at 4 % duty | a pilot the loop sees but the decisions do not (a separate tone, or the loop on the data's symmetry) | the pilot measured at 0.4 % duty; B1 / B2 kept for the bench |
| the stimulus's own two-bit change counts as two arrivals in the turnaround counter | the counter's 13.75 ns minimum in every row | gateware: the guard long enough for a two-bit change, or arrivals on the vector's settled change | T3's guard sweep; the captures |
| A3's first-edge decisions are wrong, A2 / B1 / B2's right (51-53 ns) | 4.61 (2) | B2's alphabet for the answer (SYSTEM.md): each message moves one comparator | use B2 / A2 for the fast reply; A3 settled |
| the TX's Q step reads smaller than its I step on the receiver (39 against 85 mV) | 4.60 (6) | the TX's saturation (REVB 35) and the receiver's I/Q balance (38) measured per point | the constellation levels per record say which |
| the windows at 0.1-0.3 of the gap buy nothing: false events, not speed | 4.61 (2) | the CFAR window place needs the noise, not the leg: a noise measurement per comparator in gateware | quote latency with its false count |

## 5. The plan until tomorrow 13:00 (no hands)

**Running** (`twoboard.py campaign`, since 19:22; PID in `data/twoboard/campaign.pid`): the nulls over the band (B done to
5200; the rest after the restart), a WiFi monitor on the same clock, events and prbs both ways at 5200 (518 and 532 points
a direction), the band (22 frequencies 4400-6000 both ways, the loopback prover at each), full sweeps at 5400 / 4800 /
5800, then random sessions drawing every parameter jointly, with a 10-minute soak at 5200 each hour (5 minutes with the
analyzer sweeping, 5 paused).

**To add tonight** (a `timing` step, before the band, both boards):

* **T1. Idle-to-1-in-N timing in loopback.**  Per scheme (A1, A1w, A2, A3, B1, B2) and per setting (the decision delay
  2-48 samples, settle 0-8, first edge, the window place, the level over 16 dB, the event width): the RX engine's
  reference-to-event and reference-to-decision counters (min / mean / max) and their 1.25 ns histograms over 20 000
  events, the idle's false rate alongside.  Output: each scheme's detection latency, its jitter, its tail, and what moves
  them.  This is the verifier's side of the round trip, measured on the board's own clock.
* **T2. Bitstream latency and rate in loopback.**  Per symbol period (1, 2, 3, 4, 5, 8, 10, 20, 50, 200 clocks: 100 to
  0.5 MBd) and level: a capture during PRBS, the lag of CMP_I against the ladder's I bit (both in the same capture) by
  cross-correlation in 1.25 ns samples; the BER at each period with the sampling phase swept (the eye's open fraction).
  Output: latency against rate, the highest open rate at this level, and the fixed part (the 17.5 ns loop plus the
  comparator).  Across the dishes add 139.75 ns.
* **T3. The prover's distributions.**  At the best settings (A2, A3, B1, B2; fast and sync; the three XOR masks): 32
  captures per challenge, the turnaround and the FPGA's share per (challenge, reply) pair, as histograms; the counter's
  guard swept 8 / 12 / 16 / 24 samples to settle its artifact.  Output: mean, p99 and worst per challenge, and whether
  the FPGA's share is the whole spread.
* **T4. Every challenge against every reply, by PRBS.**  The challenges chosen by the TX's PRBS (`source='prbs'`, 4
  messages), the reply map fixed per run (each of the 9), the receiver's decision delayed to land on the reply (the reply
  held 8 clocks on the fast path, 40 on sync): the confusion matrix [challenge][decoded] over 20 000 challenges per map
  gives the wrong-reply fraction per combination.  Output: a 4 x 4 table per map and path.
* **T5. The level's effect on timing** (inside T1-T3): the DSA on the receiver 16-31.75 in loopback (the dish link's level
  is reached only over the air, item 1).
* **T6.** The rest of the campaign as planned; the report tool extended for T1-T4; a written summary in BRINGUP_LOG by
  morning, and the numbers for section 0's table filled in.

## 6. Tomorrow, with hands (by value per minute)

1. **The over-the-air round trip, 10 minutes.**  A as Verifier 0, B as the Prover.  A's RX ANT off its switch onto an
   FPV antenna on the bench; B's TX ANT off its switch onto a second FPV antenna 10-20 cm from A's; A's switch left on TX
   (its TX ANT -> SW TX -> ANT -> cable A -> dish A), B's left on RX (dish B -> cable B -> ANT -> SW RX -> RX ANT).  The
   challenge goes dish to dish (-55 dBm, 140 ns), the reply FPV to FPV across the bench (about -15 to -25 dBm; RX ANT's
   limit is +1 dBm; a pad if closer).  Each board's own TX reaches its own RX only by radiation (A's at its bench FPV, B's
   at its dish 16 m away: both well under the wanted signal, *est*).  Then A sends challenges (A3 or B2, one of 4), B's
   fast path answers with a reply map, and A's RX engine, referenced to its own TX event, measures the reply's arrival and
   decision: the round trip's distribution at 1.25 ns, every challenge and map, with the turnaround = round trip - 139.75
   ns - the bench path.  Swap the roles (another 10 minutes) for B as the verifier.  **This is the measurement the
   project is for; everything tonight is its rehearsal.**
2. **The hardware time reference, 2 minutes.**  One SMA lead from B's TRIG OUT A (J205, the mark of B's symbol change)
   to A's TRIG IN (J207): A's RX engine takes TRIG IN's rise as its reference (`ref='trig_in'`) and the LAT register
   counts TRIG IN to CMP_I in clocks: the one-way latency and jitter of B's events over the dishes in 1.25 ns samples,
   per scheme and setting (T1's measurement, but across the boards).  JP203 sums TRIG IN into A's Q ladder, harmless while
   A's TX is muted.  The lead's own delay is fixed; the scope calibrates it (J208 TRIG IN MON).
3. **The scope cross-check, 5 minutes.**  B's J205 to scope ch1, A's CMP I MON (J103) to ch4 (the SDS1104X-E, 1 GSa/s,
   averaging): the one-way latency independent of either board's sampler; against 139.75 ns known to 0.1 ns, the
   electronics' latency to about a nanosecond.
4. **The VNA, 10 minutes.**  Both cables' SMA ends onto the 8720ES (register 29's calibration, as 4.43): the link's S21 now
   against 11-03's -50.3 dB.  If it reads -50, the loss is in the boards' cabling (the switch leads, a connector); if -56 to
   -59, the dishes moved.
5. **The dishes' aim**, 5 minutes, with the link's level on the page: a degree is a dB on an 8-degree beam.
6. **A's nulls exactly**: A's TX MON (J201, U.FL) into the analyzer (a pigtail; the FPV antenna off, or through a 3-way
   combiner with it and B's TX MON so the link stays up): `twoboard.py nulls --board A --redo` over the band.
7. **The prover without an FPGA, 5 minutes** (BRINGUP.md stage 4, step 7): a short lead from B's QP MON (or CMP I MON) to
   B's own TRIG IN: the received event keys +Q on the air about 20 ns after the jack: the radio's own turnaround floor on
   one scope, with no gateware in it.
8. **Later, in order:** two antennas per board for both directions at once (the full-duplex frequency plan, stage 4);
   latency against distance (one dish moved: the slope c, the intercept the electronics); the PYNQ's 200 ohm bypassed on
   the four ladder lines (LATENCY row 6, an hour, 1.35-2.7 ns); REF OUT to TRIG IN clocking and two-way time transfer
   (stage 4, step 8); the reply lane at 200 MHz (gateware, LATENCY row 3: 13-15 ns off the clocked reply).

## 7. Beyond this hardware

* **Gateware and firmware on rev A** (IMPROVEMENTS.md): the per-scheme windows and the mirror into linkd and the learning
  step; the counter's guard; the clocked reply's two clocks merged or the lane at 200 MHz; the learning step recording each
  choice's worst latency (REVB 40's tail); differential encoding against the 180-degree slip; the holdover tuned.
* **Rev B** (section 4 and REVB.md): LVDS comparators into a LUT on the board (LATENCY row 9: ~9 ns), the fast path out of
  the FPGA (row 13: ~2.4 ns), the leaks and the mute with requirements (REVB 54-55), the loop's lock point where the
  decisions are made, the comparators' offsets handled, a pilot the decisions do not see, the RX synthesizer's beat kept
  off the carrier (REVB 57), the box behind the antenna (SYSTEM.md: 10 m of cable each way is 78 ns, more than the radio).
