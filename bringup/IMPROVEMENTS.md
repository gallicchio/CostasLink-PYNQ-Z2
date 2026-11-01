# Improvements: done, by hand on rev A, and for rev B

Jason (2026-10-31): keep lists of the improvements made (and to make) in the gateware and firmware, of those he might
easily make to this board's hardware, and of those for rev B: for latency and bit errors, and the instrumentation that
lets ten of these links be run remotely in the quantum position verification experiments.  Each item says what showed
it (a BRINGUP_LOG row, a REVB row).  The version table in BRINGUP_LOG ('What runs on the board') has every deploy.

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
| linkd lowers the receiver's windows with a weaker carrier (set at setup for the level then: 2-4 dB more attenuation lost 70-74 % of A2's and A3's symbols), never above setup's (raised with a stronger one they lost A3's corners) | `linkd.py`, `dashboard.py` ('What happened' says so) | REVB 33, 4.24 |
| the netbus client connects again after a server restart | `netbus.py` | soak12 #12 |
| the latency's spread per symbol run (a histogram), the level read in gaps of the data, the demonstration's controls and order | `selftest.py`, `dashboard.*` | 2026-10-31 22:57-23:24 |

### Next (in order of what it would change)

1. **Turn the signal holdover on in deployment** (Jason's call): every carrier gap up to about 100 s rides through
   instead of costing a 2-3 s recovery after 44 ms (4.21-4.22).  With it, half the gaps come back half a cycle over:
   the data needs to carry its sign (item 2).
2. **The 180-degree ambiguity in the data**: differential encoding of BPSK (and of A3's I bit), or a known preamble
   word the receiver checks after every gap; today a slip inverts every bit until software notices (REVB 24, 4.21).
3. **Single symbols decided when their pattern settles** (REVB 32): today a fixed 16 samples (20 ns) after the first
   comparator fires, which leaves one A3 corner of four undecided 0.02-3 % of the time while its second comparator is
   still crossing, and 25-30 ns cures it for every corner at 5-10 ns of latency.  Instead: decide on the first vector
   that is one state's and has held for a few samples (with RX_DELAY as the longest wait), so each corner is decided as
   soon as it is settled.  `rx_engine.v`'s S_DECIDE; the self-test's plan 'a3delay' measures it.
4. **The FPGA reads the ADS1115 itself** (REVB U3): VC, I, Q and the detectors round-robin into registers at the
   ADC's 860 S/s, so the lock monitor can use VC (REVB U1's 'the supervisor must see VC') and the page gets VC and the
   level at 100 S/s without contending for the I2C bus.  Then the level can be read between data bursts (a gated
   conversion while TX is idle) so the page shows the carrier's level during continuous data.
5. **A fast constellation from the board itself**: the capture (`capture.v`) already records the five comparators at
   800 Ms/s; a 1-bit-per-arm picture (I sign, I and Q windows: a 3 x 3 grid of where the signal spends its samples)
   from a capture taken each look, for the deployed page with no scope.
6. **The re-acquisition in gateware** (REVB 18, 26, U4): linkd's recovery from above in milliseconds instead of 2-3 s
   (most of it is re-centring the integrator at 5.8 GHz over I2C).
7. **The carrier null per carrier in firmware** (REVB 19, 23): VR_I / VR_Q from a table in `link.json` (today one
   value for 5.2 GHz), and the arms' offsets (I_OFF_F) likewise (REVB 15).
8. **The turnaround across two boards in the self-test**: board B answers, board A times the round trip (the fast
   path and the reply), since 'ref_to_decision' times only this board's own TX.
9. **Authentication on the page's actions** (`POST /api/selftest`, notes, scope captures) before the boards leave the
   lab network; the page is read-only otherwise.
10. **Time**: NTP on every PYNQ (today the PYNQ's clock is whatever it was set to; the page's logs and the PC's records
   are compared by time).

## 2. Rev A hardware: rework by hand

| # | rework | expected | then measure | REVB |
|---|---|---|---|---|
| 1 | **Lift C102** (0.5 pF from U101's RF_IN to ground at the end of a 1.8 mm branch: series-resonant near 5-6.5 GHz, a short across the LNA's input at 5.8 GHz) | **+24-25 dB at 5.8 GHz**; RX ANT's S11 from -0.8 to about -7 dB | the VNA before and after (MONDAY.md 2-3), `overnight.py map` | 8 |
| 2 | **About 1.2 MOhm across R129** (V_MID to ground, 10 k): V_MID down about 7 mV, to the Q arm's common mode, so ERR with no carrier or a beat averages to the integrator's own reference | the free loop no longer runs away with no carrier (today: past the watershed in 44-57 ms, on the rail from 0.37 s), and the common -4.3..-5.5 V/s push gone from the pull-in map (it may capture from much further out) | the pull-in map (`weekend.py pullin`), `soak.py --kinds carrier_off` (the gap threshold), `soak.py` (linkd's recovery from above must still come down) | 17, 18, 31 |
| 3 | the power LEDs' resistors up (or a yellow-green LED) | 'all is well', not 'error' | by eye | 7 |
| 4 | the TCXO's supply on the scope while TX_DIS toggles; if it moves, a separate filter for it | fewer half-cycle slips across our own TX gaps | `soak.py --kinds carrier_off --holdover` (14 of 33 slipped) | 24 |
| 5 | a few pF (series-resonant near 5.8 GHz) and 68 pF on the RX chokes' cold pads, only if test F puts the TX leak on the board | the leak under the DSA's floor | RX MON with both ports terminated (REVB 10's test) | 10, R2 |
| 6 | bias-choke bodge capacitors at the RF ICs' supply pins (modelled first, `sim/aslaid`) | only if the chain still falls short after C102 | the map | 13, R2 |
| done | the loop's sign jumpers moved (JP101 Q+, JP102 Q-) | the lock at 0 / 180 degrees | 3.6 | 9 |

## 3. Rev B

### Latency
* All five fast comparators and the four ladder pins in one bank of the host (REVB 16): the fast path's skew between
  banks is a large part of its 23.5 ns (LATENCY.md).
* The ladder buffered on the board (LVC drivers beside it), a faster or lower-noise-gain FDA in the arms (REVB 20: the
  end-to-end edge is 10-13 ns, BPSK at 100 Mbaud closed, 50 Mbaud open at 13 of 16 phases).
* The delays from the arms to the loop's detector matched between sign(I) and Q (REVB 27), and CMP_I's duty-cycle
  distortion removed at its source (REVB 30: 2.2-3.5 samples of skew).
* An integrator reset switch (REVB U4) and a fast, FPGA-driven VC_OFF (REVB 29): re-acquisition in microseconds.

### Bit errors and robustness
* One mid-point for the integrator and every arm's common mode (REVB 17, 18, 31): no drift with no carrier or a beat.
* The LNA's input as Skyworks lays it (REVB 8, 13), the RF passives' pads voided under (REVB 11), the TX chain's level
  at 5.8 GHz (REVB 6), the TX leak (REVB 10), the 25 MHz sidebands (REVB 5).
* The loop's detector fed from a narrower I / Q low-pass so a strong CW 5-20 MHz away cannot drag the VCO (REVB 27:
  the drags were the soak's only losses under interference, 4.18, 4.20).
* The TCXO and the synthesizers' supplies isolated from the TX's switched load (REVB 24), and the 180-degree
  ambiguity carried in the protocol.
* The ladders' references divided down at the DAC (REVB 1), the window comparators' thresholds filtered (REVB R5).

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
