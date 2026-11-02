# Improvements: done, by hand on rev A, and for rev B

Jason (2026-10-31): keep lists of the improvements made (and to make) in the gateware and firmware, of those he might
easily make to this board's hardware, and of those for rev B: for latency and bit errors, and the instrumentation that
lets ten of these links be run remotely in the quantum position verification experiments.  Jason (2026-11-01): the
plans must include the best that gateware and firmware can do on rev A, and everything rev B should do, with its
options and their trade-offs.  Each item says what showed it (a BRINGUP_LOG row, a REVB row).  The version table in
BRINGUP_LOG ('What runs on the board') has every deploy; REVB.md is the list of defects these answer.

## 1. Gateware and firmware on rev A

### Done

| what | where | shown by |
|---|---|---|
| the I2C pins' tristates kept (no I2C worked on any earlier overlay), a stuck SCL abandoned after 10 ms | overlay of 10-29 | the software header of BRINGUP_LOG |
| the receive-to-transmit paths (synchronous reply, fast path, ring, turnaround counter) | ID 3 | 3.4g-h: 22-25 ns RX ANT to TX ANT by the fast path |
| the BER check's timing recovered from CMP_I's own edges (a remote transmitter's clock) | ID 4, `ber_cdr.v` | 4.6-4.7 (REVB 28 fixed) |
| the interference hold and the signal holdover, off at reset | ID 5, `ihold.v` | 4.8-4.10 |
| the timing recovery on one edge polarity, centred on the measured skew | ID 6 | 4.10 (REVB 30 fixed) |
| the hold's persistence | ID 7 | 4.13-4.14 |
| the lock judged in gateware every 10 ms, the PYNQ-Z2's LEDs from it; the hold's release scaled | ID 8, `lockmon.v` | 4.17 |
| **the random message reduced right for N = 2** (A2 sent messages 2 and 3 a quarter of the time: 75 % decided) | ID 9, `tx_engine.v` | the self-test's A2, 149 974 of 199 999 (REVB 22 fixed) |
| **the lock monitor blind to the board's own events' Q moves** (its LEDs read the self-test's A2 / A3 as lost) | ID 9, `lockmon.v` | the page's photographs, 2026-10-31 22:03; `tb_lockmon.v` |
| **the single symbols' counts add up**: undecided symbols counted (RX_UNDEC), false decisions kept out of right and wrong, no reference both paired and missed; the page's 'sent' the references, the self-test's counts read with the receiver stopped | ID 10, `rx_engine.v`; `selftest.py`, `dashboard.*` | 4.24: 'right' and 'wrong' ran to millions for 200 000 sent under a CW; after, every run closes |
| linkd: the automatic recovery in the board server, from above, VC-judged (no needless recoveries under bursts) | `linkd.py` | 4.15-4.16, 4.18, 4.20-4.21: 67 of 67 losses recovered |
| the link set up from `link.json` at power-up, the server a boot service | `linkd.py`, `costaslink-netbus` | 4.17 |
| requests that only look do not pause linkd; requests flagged 'nodrive' (tests standing in for the world) neither | `netbus.py` | 4.16, 4.18 |
| the status page: state, cause, remedy in words; the levels; the pull-in map, S-curve, constellations; what the link and the B210 are doing; bit errors, single symbols' decisions and latency; the bench scope's I/Q raw, aligned and as an eye; notes; history across restarts; log pruning | `dashboard.py`, `dashboard.html` | 4.15, 4.18-4.21 and the version table's 20 deploys |
| the link's own self-test: rounds of the carrier's level, single symbols (A3, A1, A2, A1w) and BPSK data at 2-50 Mbaud with the bits checked, beside linkd, which clears its data before recovering | `selftest.py` | 2026-10-31 22:02 |
| the carrier's level independent of the lock point (the middles from linkd's measurement, the lock points' offset learned) | `dashboard.py` | 4.21 |
| half-cycle slips detected and listed (and a recovery between two looks not mistaken for one) | `dashboard.py` | 4.21; 2026-11-01 00:02 |
| linkd waits for the carrier when the lock monitor sees none (no tries holding the board, no back-off), and starts the moment it returns: a 52.8 s cut recovered 3 s after the carrier came back, where before 11 s of tries and a 5 s back-off made it 7 s | `linkd.py` | soak13 #12, #25 |
| a dragged loop no longer called locked (20 kHz or more off), the offset from linkd's lock VC (the page learned a dragged VC and showed a false 10 kHz for a minute) | `dashboard.py` | soak12 #26 |
| the page's history sent from the looks as already encoded (0.18 s, not 2.3 s, for 10 minutes; the looks fell late while it encoded), the scope API the latest capture of each kind, the scope's captures thinned in the log | `dashboard.py` | 2026-10-31 22:39 |
| **single symbols decided once their pattern has settled** (k samples one state's, RX_DELAY the longest wait): A1 59-62 ns against 76, A3 63 against 80-90, none wrong at A3's k = 6 | ID 11, `rx_engine.v`; `selftest.py` (its default) | 4.25, REVB 32 |
| **the receiver's windows from the states' own levels** (each window's threshold swept with the loop closed, set in the middle of the plateau between the states that should read low and high, per lock point): margins 41-48 mV where they were 2-12 | `selftest.py` ('calibrate'), `linkd.py` | 4.25, REVB 33 |
| linkd: a lock far from the learned one is not a lock (a CW's capture had pulled the learned VC 70 kHz) | `linkd.py` | soak14 #50 |
| linkd lowers the receiver's windows with a weaker carrier (set at setup for the level then: 2-4 dB more attenuation lost 70-74 % of A2's and A3's symbols), never above setup's (raised with a stronger one they lost A3's corners) | `linkd.py`, `dashboard.py` ('What happened' says so) | REVB 33, 4.24 |
| the netbus client connects again after a server restart | `netbus.py` | soak12 #12 |
| the latency's spread per symbol run (a histogram), the level read in gaps of the data, the demonstration's controls and order | `selftest.py`, `dashboard.*` | 2026-10-31 22:57-23:24 |
| on-off keying checked on the I window on the carrier's side (RX_BER_CFG[31:30]), the self-test's OOK and QPSK data in each round; OOK read at half the leg during its step (the calibration's quarter gave 4e-7 at 25 Mbaud) | ID 12, `selftest.py` | 4.27-4.29 |
| **FSK data**: TX mode 4 with the PRBS as source, a turn of the N points a bit, its direction the bit (continuous phase, the tones +-1 / (N TX_PERIOD)); received by the B210 only | ID 13, `tx_engine.v` | 4.29: 25 kbaud-2.5 Mbaud, 1.4e6 bits, no error |
| the PYNQ on the bench supply's output 2, the board switched by its own output's voltage, on only with the PYNQ's server up; `bench.py psu up / cycle`; the watchdog power-cycles a silent PYNQ at most 3 times, then switches both off and leaves them off | `bench.py`, `stages.py` | 4.27 (a reboot that hung) |
| the board's service after the image's `bootpy.service` (its boot.py loaded the base overlay over ours on a cold boot) | `install_service.sh` | 4.27 |
| linkd learns the carrier's level only while the self-test is not sending (OOK's nulls passed for the idle: the windows moved and the calibration was dropped, a quarter of a 103 mV leg for a 173 mV carrier) | `linkd.py` | 4.29's day log, 11:23 and 11:41 |
| the page: the live counts read with the matrix first (never more right than sent), the eye's caption from the capture's own levels | `dashboard.*` | the photographs of 11:44 and 11:54 |
| the B210 as a full link partner: BPSK, OOK, QPSK and FSK received in software (`sdr_rx.py`), its own loop (`b210link.py self`), its stream's buffers long enough not to underflow | `bringup/` | 4.29 |
| the calibration's place in each window's plateau a setting (`window_bias`, 0.6: under a CW 10 dB down far fewer false events and wrong decisions than the plateau's middle, every symbol right when quiet) | `selftest.py` | 4.30 |
| the calibration not while an intervention is announced and only at the level the windows are kept for (one taken during an attenuator step left A2, A3 and QPSK 60 % missed); a quiet run that loses over 1 % calls for a new one; the soak checks the self-test's symbols after each disturbance | `selftest.py`, `soak.py` | 2026-11-01 13:41-13:44 |
| **the learning step before physics runs** (plan 'learn'): the decision table learned from the vectors each state makes, every table and timing tried for A1, A1w, A2, A3 and the QPSK rate, the lowest-latency choice that decides every symbol right kept with its `rx_config`; the data's timing recovery per rate; `learned.json`, `GET /api/learned` | `selftest.py`, `dashboard.py` | 4.32 |

### Next: the best rev A can do in gateware and firmware

Grouped by what each buys; within a group, in order.  None needs new hardware.

**Before every physics run (QPV)**
1. **Run the learning step** (`{"plan": "learn"}`, about 10 minutes quiet): the windows, each scheme's table and timing,
   the data's timing recovery, all on this lock point at this level; the run's code reads `GET /api/learned` and applies
   each scheme's `rx_config` as it stands.  Learn again after any change of carrier, antenna, attenuator or lock point
   (the profile is used only on the lock point and within 15 % of the level it was learned at).
2. **Learn the latency floor per scheme with the windows lower on the edge** (LATENCY.md row 1: 0.2 of the leg where
   0.4 gave 3 ns more on the fast path): the learning step could also try lower thresholds where the quiet false rate
   allows it (the trade: false events against latency).
3. **The turnaround learned too**: the fast path's and the clocked reply's latency and errors across the two boards
   (board B answers, board A times the round trip), with the same table-and-timing search.

**Latency (gateware)**
4. **The reply lane at 200 MHz** (ISERDES 4:1, the rest of the core at 100 MHz): the clocked reply 51 to about 37 ns
   (LATENCY.md row 3).  Or, at 100 MHz, the decision's two clocks merged into one (row 3b: 10 ns).
5. **The fast path's tables placed by its pins** (a pblock: up to 1 ns on hops through CMP_IP or TX_I1; row 4) and the
   ladder pins at DRIVE 16 (row 5, 0.2 ns).

**Sensitivity at range (gateware)**
6. **An integrating decision as an option**: the sampler sees each comparator 8 times a clock; counting each window's
   high samples over a set time (a majority vote, the hard-limited matched filter) gains up to about 10 log(B T) on
   noise (about 13 dB over a 200 ns symbol in the arms' 100 MHz) at the cost of that time in latency.  A mode per run:
   'fast' (today's settled decision) or 'sensitive' (integrated), chosen by the physics' needs; the learning step can
   find each scheme's shortest integration that decides every symbol right at the link's level.
7. **The learned table under the run's own conditions** (done for quiet): learned again with the interference the run
   expects (a B210 setting, or the lab's own), since 'info' and 'learned' differ only when the vectors are disturbed.

**Robustness (gateware and firmware)**
8. **Turn the signal holdover on in deployment** (Jason's call): every carrier gap up to about 100 s rides through
   instead of costing a 2-3 s recovery after 44 ms (4.21-4.22).  With it, half the gaps come back half a cycle over:
   the data needs to carry its sign (item 9).
9. **The 180-degree ambiguity in the data**: differential encoding of BPSK (and of A3's I bit), or a known preamble
   word the receiver checks after every gap; today a slip inverts every bit until software notices (REVB 24, 4.21).
10. **The re-acquisition in gateware** (REVB 18, 26, U4): linkd's recovery from above in milliseconds instead of 2-3 s
    (most of it is re-centring the integrator at 5.8 GHz over I2C).
11. **The FPGA reads the ADS1115 itself** (REVB U3): VC, I, Q and the detectors round-robin into registers at the
    ADC's 860 S/s, so the lock monitor can use VC and the page gets VC and the level at 100 S/s without contending for
    the I2C bus; the level read in the data's gaps by gateware.
12. **The calibrations kept across a restart**: linkd's per-lock-point windows (and the learned profile, kept already)
    saved beside the server and put back after setup when the level is within 15 %; today a restart runs on the plain
    windows until the self-test calibrates again (QPSK lost 2.2 % a run for a minute after a deploy, soak15 17:47).
13. **The carrier null per carrier** (REVB 19, 23): VR_I / VR_Q from a table in `link.json`, and the arms' offsets
    (I_OFF_F) likewise (REVB 15).
14. **The TX's I and Q swing trimmed against the receiver's measured corners**: not possible on rev A (the ladders' swing
    is fixed by the logic levels and resistors; VR_I / VR_Q set the null), so the calibration's per-window thresholds
    stay the compensation for the TX's saturation (REVB 35) and the receiver's corner error (REVB 38).

**Visibility and operations (firmware)**
15. **A fast constellation from the board itself**: the capture (`capture.v`) records the five comparators at 800 Ms/s;
    a 3 x 3 grid of where the signal spends its samples from a capture each look, for a deployed page with no scope.
16. **The learning step's choices on the page** (each scheme's table, timing, latency, and when it was learned).
17. **Authentication on the page's actions** (`POST /api/selftest`, notes, scope captures) before the boards leave the
    lab network; the page is read-only otherwise.
18. **Time**: NTP on every PYNQ (the page's logs and the PC's records are compared by time).

## 2. Rev A hardware: rework by hand

| # | rework | expected | then measure | REVB |
|---|---|---|---|---|
| 1 | **Lift C102** (0.5 pF from U101's RF_IN to ground at the end of a 1.8 mm branch: series-resonant near 5-6.5 GHz, a short across the LNA's input at 5.8 GHz) | **+24-25 dB at 5.8 GHz**; RX ANT's S11 from -0.8 to about -7 dB | the VNA before and after (MONDAY.md 2-3), `overnight.py map` | 8 |
| 2 | **About 1.2 MOhm across R129** (V_MID to ground, 10 k): V_MID down about 7 mV, to the Q arm's common mode, so ERR with no carrier or a beat averages to the integrator's own reference | the free loop no longer runs away with no carrier (today: past the watershed in 44-57 ms, on the rail from 0.37 s), and the common -4.3..-5.5 V/s push gone from the pull-in map (it may capture from much further out) | the pull-in map (`weekend.py pullin`), `soak.py --kinds carrier_off` (the gap threshold), `soak.py` (linkd's recovery from above must still come down) | 17, 18, 31 |
| 3 | the power LEDs' resistors up (or a yellow-green LED) | 'all is well', not 'error' | by eye | 7 |
| 4 | the TCXO's supply on the scope while TX_DIS toggles; if it moves, a separate filter for it | fewer half-cycle slips across our own TX gaps | `soak.py --kinds carrier_off --holdover` (14 of 33 slipped) | 24 |
| 5 | a few pF (series-resonant near 5.8 GHz) and 68 pF on the RX chokes' cold pads, only if test F puts the TX leak on the board | the leak under the DSA's floor | RX MON with both ports terminated (REVB 10's test) | 10, R2 |
| 6 | bias-choke bodge capacitors at the RF ICs' supply pins (modelled first, `sim/aslaid`) | only if the chain still falls short after C102 | the map | 13, R2 |
| 7 | **Bypass the PYNQ-Z2's 200 ohm on the nine fast lines** (the PYNQ's own series resistors; 0 ohm) | about 2.7 ns off the fast path, more if the edges are slow | the A3r ring's hop | LATENCY row 6, REVB 20 |
| 8 | the ladder's series resistors up (a 3-6 dB smaller swing at the modulator) | the TX out of saturation: the corners at 1.41 and 45 degrees (REVB 35), at the cost of 3-6 dB of TX level that is already 6 dB short | the B210's `b210link.py pattern` | 35, 6 |
| done | the loop's sign jumpers moved (JP101 Q+, JP102 Q-) | the lock at 0 / 180 degrees | 3.6 | 9 |

## 3. Rev B: everything, with its options

Each part lists what rev A showed, the change, and where there is a choice, the options and what each costs.  The
last table ranks them for what the experiments need most: range, a low signal to noise ratio, and latency.

### The receive chain (sensitivity)
* **The LNA's input as Skyworks lays it** (REVB 8, 13): no C102 branch, the VCC pin decoupled at the pin; rev A is
  28-32 dB under plan at 5.7-5.8 GHz and 10-20 dB at 5.0-5.35.  The single largest gain anywhere.
* **The RF passives' pads voided underneath** (REVB 11: 2 dB at 5.8 GHz, 8 at 5.0 through the gain blocks' poor match),
  the CPWG drawn at 50 ohm by a field solve (REVB 14), anti-pads and mitred corners (R4).
* **The TX's leak into the receiver** found and blocked (REVB 10: about -53 dBm at RX MON, capping the DSA at 23 dB).
* Options: **a second LNA stage** (more gain at the cost of power and a little noise figure; no latency to speak of);
  **a band filter** (SAW / BAW at the band: rejects the WiFi channels the self-test found at 5.2-5.25 GHz, but adds
  1-2 dB of loss and a few ns of group delay); **the DSA kept** (it is the bench's level control and the only AGC).

### The transmitter
* **The level** (REVB 6: +3.8 dBm at TX ANT at 5.8 GHz against +9.8 planned): find the stage, then the gain blocks and
  their match.
* **Linear, or PSK on purpose** (REVB 35): rev A's TX is saturated, every state at the idle's amplitude and turned by
  AM-PM (the flip at 190 degrees, the corners at 40).  Options: **(a) linear**: the baseband swing and gain chosen so
  the corners sit 3 dB or more under the first compression point; the corners at 1.41 and 45 degrees, square windows,
  ASK possible; costs 3 dB of peak power or a bigger final stage.  **(b) PSK by design**: keep the constant envelope (the
  most power per peak), place the states on the circle at the angles wanted (the ladders' points chosen for it), and
  the windows for a circle; no ASK, no OOK at full depth.  **(c) an I / Q DAC** (two channels at 1 GS/s or more) with
  digital correction of gain, quadrature and AM-PM, any constellation: costs a DAC's pipeline (about 5-10 ns) in
  every transmitted symbol, against the ladders' none, and the fast path would bypass it.
* **The ladders' references divided down at the DAC** (REVB 1: a reference above 1.6 V takes the modulator's inputs
  past their maximum), the ladder buffered beside the modulator (REVB 20).
* **The 25 MHz sidebands** (REVB 5: the TCXO on the modulator's baseband) and **the LO's routing** (REVB 4, 12).
* **The carrier null**: a per-frequency trim kept, or a modulator with a better native null (REVB 19, 23).

### The demodulator and the arms
* **One mid-point** for the integrator and every arm's common mode (REVB 17, 18, 31): no drift with no carrier or a
  beat, no static Q error at the lock.
* **The receiver's corner error** (REVB 38: Q 7-15 % short on the idle's side, an I x Q term of about 14 mV, the board's
  own): find the stage on rev A first (the demodulator fed alone, the arms fed alone); then the operating points
  (LO level, common modes, baseband swing) set for second-order linearity.  The quadrature (1 degree) and gain match
  (2 %) need nothing.
* **Faster, matched arms** (REVB 20: the end-to-end edge 10-13 ns; REVB 27, 30: sign(I) and Q's delays, CMP_I's
  duty-cycle distortion): the corners settle together, so the settled decision needs fewer samples (5-10 ns on A3).
  Options: a faster FDA (a little noise and power); the gain of 4 kept (lower gain moves the window out at range).
* **Real I and Q monitors** (REVB 34): a 50 ohm back-terminated buffer per arm, as fast as the arms.
* **A data slicer of its own** (REVB 36): a comparator and a DAC channel per arm for the data, the four windows left to
  the symbols, so OOK and the corners stop sharing thresholds.
* **The thresholds filtered** (R5: an RC at each comparator's threshold pin).

### Carrier recovery (the loop)
Rev A's loop is a hard-limited Costas loop (sign of I times Q, 4.31): simple and fast, but it is a BPSK loop, and
states with I near zero or a corner sent alone at a high duty pull it (-48 and 27 degrees).
* **Options**: **(a) keep it**, with the idle as a pilot between states (today's QPSK) and the patterns balanced;
  **(b) a QPSK (fourth-power or decision-directed) loop** for dense QPSK data, at more parts and a slower pull-in;
  **(c) a digital loop**: the arms digitised (U2) and the phase detector in the FPGA, the VCXO steered by a fast DAC:
  any modulation, and the holdover, lock detection and re-acquisition in gateware, at an ADC's latency in the loop
  (not in the symbols' path, which stays on the comparators).
* **The loop's detector behind a narrower low-pass** (REVB 27): a CW 5-20 MHz away no longer drags the VCO (the soaks'
  only losses under interference).
* **An integrator reset and a fast, FPGA-driven VC** (REVB U4, 29): re-acquisition in microseconds; a capture range wider
  and not one-sided (REVB 26).
* **The TCXO and the synthesizers' supplies isolated from the TX's switched load** (REVB 24): no half-cycle slips across
  our own TX gaps; the 180-degree ambiguity carried in the protocol all the same.

### Decisions and latency
* **All fast comparators and ladder pins in one bank** (REVB 16: the fast path's crossing of the die, 3.5-4 ns).
* **No series resistors on the fast lines** (the PYNQ's 200 ohm: 2.7 ns; LATENCY row 6), or a host without them.
* **Faster comparators** (TLV3604, LVDS: about 3 ns; row 9): pairs to the FPGA, a re-spin.
* **The fast path out of the FPGA** (row 13: CML comparators into an answer gate on the modulator's baseband, the FPGA
  only arming and time-stamping): about 20 ns off the turnaround, at the cost of the table's flexibility (the answer
  wired, not programmed).
* **Decisions from an ADC** (U2, options): every scheme and a matched filter (several dB at range), at the ADC's
  pipeline (10-20 ns) in the decision; or the comparators kept for the fast path and the ADC beside them for
  monitoring, calibration and the 'sensitive' mode.
* **The host**: the PYNQ-Z2 (today; its 200 ohm and its banks), the Icepi Zero (2-3 ns faster on the fast path with a
  one-level table; LATENCY section 4), or an FPGA on the board (the shortest paths, the most work).

### The board as a deployed instrument
* **The PYNQ's power under the board's control** (REVB 37): a load switch on its 12 V with a hardware watchdog it must
  kick, so a hung PYNQ is cycled without a person; R3's output enables, so the order of power-up stops mattering.
* **The 5 V path** (REVB 2: 0.26 V dropped at 1.37 A), **the hot spot near U104** (REVB 3), **the LEDs** (REVB 7).
* The instrumentation list below.

### What matters most, for range, signal to noise and latency
| change | range / low SNR | latency | effort |
|---|---|---|---|
| the LNA's input (C102, layout, decoupling) | **+10-30 dB** in band | none | rev A: lift C102; rev B: the layout |
| the TX's level | **+6 dB** | none | find the stage |
| an integrating decision (gateware, rev A) or an ADC's matched filter (rev B) | **+3-13 dB** (rate-dependent) | adds the integration time | gateware; rev B parts |
| the loop: narrower detector, reset, one mid-point, a QPSK or digital loop | fewer losses at low SNR and under interference (loss of lock is the failure mode, REVB 21) | re-acquisition from seconds to microseconds | rev B |
| the fast path out of the FPGA | none | **about -20 ns** | rev B, less flexible |
| the reply lane at 200 MHz | none | **-13-15 ns** (clocked reply) | gateware, rev A |
| comparators, one bank, no 200 ohm, faster arms | none | **-3 to -9 ns** together | rev A (resistors), rev B |
| linear or PSK-by-design TX | about +1 dB on QPSK corners | none | rev B |
| the receiver's I / Q errors (1 degree, 2 %, the corner term) | under 1 dB (absorbed by the calibration) | none | rev B, after finding the stage |
| antenna cables | the cable's loss | 4.8 ns a metre | the box behind the antennas |

### Instrumentation for ten links in the field
Each link is a pair of boards, left alone for weeks, judged remotely by people who do not know PLLs.  What the bench
had to supply by hand this week, each board should have:
* **Its own level meter**: an RF log detector on the RX MON coupler (REVB U1), read by the FPGA, locked or not; the
  slow I arm read the level 0.5 dB apart on the two lock points and not at all during data (4.21).
* **Its own constellation and eye**: a dual 8-12 bit ADC on I and Q into the FPGA (REVB U2), so the page shows what
  the bench scope showed (the fast constellation, the aligned symbols, the eye) on every board, all the time.
* **LEDs a person can read from across the room**: LOCKED, SEARCHING, NO CARRIER, INTERFERENCE and a signal bar
  (REVB U1), driven from a supervisor that sees VC as well as the comparators.
* **The slow readings owned by the FPGA** (REVB U3), the integrator reset (U4), supply voltage and current monitors per
  rail (Q10, Q11), temperature at the hot parts and at the TCXO (REVB 3).
* **Self-test without hands**: RF switches for loopback and termination (Q7) and a monitor mux (Q8), so the self-test
  can check each board's own TX and RX with the far board off.
* **Time**: a PPS input (GPS or the experiment's clock) and a timestamp counter in the FPGA on every TX event,
  decision, loss and recovery, so the ten links' records line up to the nanosecond the protocol needs; the events'
  latency as a histogram per link, streamed, not only the mean.
* **Recovery from anything remotely**: a hardware watchdog, power over Ethernet through a managed switch (a remote
  power cycle), dual firmware images (a bad update falls back), the board's identity and calibration in its EEPROM.
* **The fleet's page**: one page for the ten links (a tile each: state, level, bit errors, latency, the last loss,
  slips, what is being done to it) with each board's own page behind it; alerts on unexplained losses; every
  board's looks and events in one time-synchronized store; configuration (`link.json`, the null tables) in version
  control; every request authenticated.
