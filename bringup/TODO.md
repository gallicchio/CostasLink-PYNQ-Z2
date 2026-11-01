# Board A: what to do next (written 2026-10-29 21:30; refreshed 2026-10-30 08:00 with the night's results)

Jason can pop in for a few seconds at a time between classes. Moving everything down to the 8720ES (and the grids, in the
same lab) takes one to two hours, so that waits for Monday. "Hands" is Jason's time at the bench. "Unattended" is the
bench running remotely afterwards; the chat says when each step is done, so the next pop-in can wait for it. Nothing here
desolders a part until step 9, and that one only after test A agrees.

The cabling now: TX ANT, 10 cm RG-316, two 20 dB pads, RX ANT. The DSA875 on RX MON's pigtail. The scope: ch1 REF OUT,
ch2 I MON, ch3 Q MON, ch4 VC MON. 50 ohm on TX MON's pigtail. JP201 on TCXO.

| # | when | hands | unattended | what | benefits from | helps |
|---|---|---|---|---|---|---|
| 0 | **done 22:00** | none | | Deployed the reply overlay (ID 0x434C0003; the old overlay and driver backed up on the PYNQ in `~/costaslink_backup_20261029_2150_pdt/`). Turnaround in loopback, RX ANT to TX ANT:<ul><li>**fast path (LUTs pin to pin): 22-25 ns**; ring of the four A3r states 23.5 / 24.3 ns a hop at 5.0 / 5.2 GHz;</li><li>**clocked reply: about 51 ns** first-edge, 59-71 ns settled;</li><li>the FPGA's own share is 5-6 ns on the fast path, 31-42 ns on the clocked one.</li></ul>BRINGUP_LOG 3.4g-h, `plots/link_turnaround.png` | | 1, 5, 8 |
| 0b | **done 07:30** | none | | The night (BRINGUP_LOG 3.5): the TCXO -1.006 ppm, 0.008 ppm rms reading to reading over 14 h; the coarse maps repeat the 16:30 map within +-0.3 dB; the 5.0 GHz lock check the same all three times; the PYNQ up all night, 0.947-1.041 A. Nothing drifted that matters. `plots/night_drift.png`, `plots/night_maps.png` | | |
| 1 | **done 08:03-08:40** | | | **The sign jumpers moved** (JP101 on Q+, JP102 on Q-). The loop locks at 0 / 180 degrees, sign(I) steady (BRINGUP_LOG 3.6-3.6c, `plots/lock0.png`, `plots/schemes0.png`):<ul><li>A1, A1w, A2, A3 each 20 000 of 20 000 at 5.0 GHz, none false or missed, 66-78 ns;</li><li>the BER with the loop closed: no errors to 50 Mbaud (under 2e-8), 0.12 at 100;</li><li>f_n 2.8-3.1 kHz, damping 0.5-0.8 (5.0 GHz); hold-in to the integrator's range; pull-in one-sided at 5.0 GHz;</li><li>no idle false events at 0.3-0.8 a;</li><li>the slow path vetoes A1: the TX carrier feedthrough (~-14 dBc at 5.0 GHz) turns the flip to 146-164 degrees. Not hardware.</li></ul>Still open from step 1: FSK's sense, and LATENCY.md check a | | 3, 6, 7, 8 |
| 2 | **done 10:20** (BRINGUP_LOG 3.7: on the board) | **2 min**, then 2 min to restore | 20 min | **Test B, the leak** (`podtests.py leak`, about 5 min): take the lead and pads off. Put a 50 ohm terminator on TX ANT (J202) and one on RX ANT (J101), and leave the analyzer on RX MON (J102). Then RX MON and I/Q with TX on and off, at DSA 31.75 and 0, over 4.9-6.0 GHz. If the leak stays, it is on the board; if it falls 20 dB or more, it was the lead, jacks and pads | none (best after 1, which needs the loopback) | 6, 7, rev B |
| 3 | **done 10:31** (the model's peak and dip confirmed) | **1 min**, then 1 min back | 15 min | **Test C** (`podtests.py lomon`, about 5 min): the analyzer's pigtail from RX MON (J102) to LO RX MON (J109). Sweep 3-6.0 GHz (the MAX2871's top) with RFOUTB on (the model predicts a peak near 3.8 GHz and a null near 4.3) | none | rev B row 12 |
| 3b | **done 10:25** (V_ENABLE 3.033 V, 2.37 mA: enabled; V_MID 13.7 mV above the arms' Vocm) | **3 min** | none | **The LNA's DC, on the Fluke 45 (DC volts, black on an SMA shell):** U101's VCC on its pin 6 / 100 nF, and V_ENABLE at R101's U101 end. Both should read 3.25-3.30 V (+3V3_ANA; R101 100 ohm carries almost nothing). The 3.0-4.4 GHz gain is already as planned, so the LNA is almost certainly on; this closes the question in two touches. **Then three more touches for REVB 17:** V_MID at C131, the I arm's Vocm at C121, the Q arm's Vocm at C124 (all near 1.65 V; the question is their differences, to a millivolt) | none | 9 |
| 4 | **done 10:33** | **1 min** | none | Back to the loopback (lead and two 20 dB pads), the analyzer back on RX MON, unless going straight on to 5 | | |
| 5 | **done 13:30-15:00** (BRINGUP_LOG 4.0-4.2: four antennas within 30-40 cm; the B210 as interferer to +11 dB; the weekend's rounds running, `weekend.py`) | **15 min** | 1-2 h | **Over the air in the office, FPV antennas, about 5.2 GHz:**<ul><li>one antenna on TX ANT and one on RX ANT, each on a lead of a metre or more;</li><li>1-3 m apart, same handedness;</li><li>a 20 dB pad on RX ANT if they are closer than about 30 cm. Never TX ANT to RX ANT on a bare lead.</li></ul>Then, remotely: the map (the antennas' band, the chain divided out), the lock, A3r and A1, the turnaround over the air | 1 (a reliable lock), 2 (the leak's floor), 0 (the overlay) | the lab link |
| 6 | Monday, the trip down (1-2 h to move) | 15 min | none | **Test A:** RX ANT's S11 on the 8720ES, powered and unpowered. The model predicts above -2 dB over 5.5-6.1 GHz, with a sharp feature near 5.9 GHz. This confirms C102 without touching it | none | 9 |
| 7 | Monday, after 6 | 20 min | none | **Test F:** S21 from RX ANT to RX MON at DSA 0 and 31.75: the chain without the leak, at -40 dBm in. The same for TX ANT to TX MON | 6 (the same calibration) | 9, rev B |
| 8 | Monday, in the same lab | 30 min to set up, 30 min to move a grid | 1-2 h | **Over the air with the VV 24 dBi grids at 5.15-5.2 GHz:** TX ANT to one grid's 10 m cable, the other grid's cable to RX ANT, no pads. The VNA's link is -48.2 dB, so RX ANT sees about -39 dBm. Measure the lock, the schemes and the turnaround (subtract 135.6 ns of flight). Then the latency line: move one grid to two more distances; the slope is c, the intercept the electronics | 1, 0, 5 | |
| 9 | Monday, last | **15 min** (the only rework) | 1 h | **Lift C102**, the 0.5 pF shunt from the LNA's input to ground; leave its pads empty, or lift only its ground end. Then repeat A, F and the night's map. The prediction is +25 dB at 5.8 GHz, and RX ANT's S11 from about -0.8 to -7 dB. If it misbehaves, a 0.5 pF goes back on the same pads | 6 (A first) | everything at 5.8 GHz |
| 10 | only if needed, after 9 | 15-30 min | 1 h | **Bias-choke bodge capacitors**: a small 0402 tacked from an RF IC's supply pin to its nearest ground pad (the gates' finding: no 1 nF or smaller within 2 mm of any RF supply pin, and every choke reaches a plane via first). Only if the chain still falls short after C102, or test B puts the leak on the board. I model the value first (`sim/aslaid`), so none goes on blind | 9, 2 | rev B 13 |

**Unattended operation (Jason, 2026-10-31: the boards run unattended, operated by physicists who do not know PLLs;
"this part just needs to work reliably without intervention"; a live dashboard that survives new firmware, tests and
experiments; pictures, not one-word states, each with what led to it and how to improve it):**
   **Status 2026-10-31 noon:** 1 done (BRINGUP_LOG 4.15: 0 of 171 forced losses unrecovered, 1.7-3.0 s, the loss
   judged on VC so bursts draw nothing); the recovery runs on the board in `linkd.py` (in the board server, since
   11:40: recovering on rev A needs the integrator re-centred, which needs the synthesizers retuned: software's job;
   REVB U4 asks rev B for an integrator reset so gateware alone could do it), its end-to-end test running; 2's lock
   monitor and the PYNQ-Z2's LEDs in ID 8 (`lockmon.v`, building); 3's page v1 at http://192.168.8.142:8080/ (since
   11:07).  Next: `bringup/unattended.py` overnight (the B210 throwing random interference, nothing touching the
   board, linkd and the page doing the work); the page's eye, latency and history plots.
   **Status 2026-11-01 01:30:** the board runs ID 0x434C000A (`~/costaslink_id10/`: the single symbols' counts add
   up, sent = right + wrong + undecided + missed); linkd moves the receiver's windows with the level; the page shows each
   symbol run's table of states sent and decided.  The night's rehearsal (BRINGUP_LOG 4.24): 98 random disturbances
   through 01:25 beside the self-test, every loss recovered, 470 data runs with the B210 quiet and no bit error in
   7.5e10; what it found is fixed (REVB 32-33 new).  Running: soak14 (`--world`, to about 10:40), the scope watcher,
   the 10-minute photographs.  Open, for the demo: the holdover on or off (Jason's call, 4.22); ID 11's decision on
   the settled pattern (IMPROVEMENTS 3).
   **Status 2026-10-31 23:00:** the board runs ID 0x434C0009 (REVB 22 fixed, the lock monitor blind to its own
   symbols) and its own self-test beside linkd (`selftest.py`: the carrier's level, single symbols A3/A1/A2/A1w with
   their decisions and latency, BPSK data at 2-50 Mbaud with every bit checked and the level read in a gap each
   second); the page shows what the link and the B210 are doing, bit errors, symbols, latency, and the bench scope's
   I/Q raw, aligned and as an eye; `soak.py` audits every random disturbance against the page's log, API and photos
   (BRINGUP_LOG 4.20-4.23: about 200 disturbances, every loss recovered by linkd).  Monday's demonstration and the day's
   plan: `MONDAY.md`; the lists of improvements: `IMPROVEMENTS.md`.  Open, for the demo: the holdover on or off
   (Jason's call, 4.22); a fleet page for ten links (IMPROVEMENTS.md section 3).
   **Status 2026-10-31 14:50:** 1 and 2 done on the board (linkd in the boot service, ID 8's lock monitor and LEDs;
   BRINGUP_LOG 4.16-4.18: 58 random disturbances overnight-style, 18 losses, 18 recovered by linkd).  3 and 4: the
   page's third version (`gateware/driver/dashboard.html`, re-read at every request): the state from the gateware's
   judgement and VC ('Interference' apart from 'Lost'), the measured pull-in map with the live loop on it, the S-curve
   (a model) with the live phase, the slow constellation, the carrier's level at RX ANT and at the demodulator with the
   band's strongest other power beside it, announced interventions (POST /api/note) on every plot, its history and
   notes kept across restarts; checked against deliberate disturbances by `bringup/pagecheck.py` (4.19: 11 of 12, the
   miss the check's own expectation).  Open:
   * the eye, latency and bit errors need data on the link: the idle link carries none, so those plots stay empty
     unless a data check runs (rev A's timing recovery and RX_CDR_SKEW); decide whether the deployed link should run a
     low-duty data check for them
   * an S-curve measured, not modelled: a slow beat (the loop held, the B210 locked to the board's reference, or the
     SDS2104X on I, Q and ERR at once)
   * ~~the page's log on the PYNQ's SD card grows about 150 MB a day: rotate it~~ done 16:13: the day logs older than
     14 days are deleted (and the oldest while under 1 GB is free)
   * the carrier gone with the holdover off costs the lock after 40-60 ms (4.21: off 57 ms the loop came back in the
     false lock; REVB 31), so every interruption costs a recovery; measure the signal holdover (shold) with linkd and
     the carrier interrupted at random (`soak.py --kinds carrier_off` with the holdover on), and decide whether
     deployment turns it on.  **Measured 20:47 (4.22): 33 of 33 gaps of 23 ms-53.6 s held, no loss; 14 slipped half a
     cycle.**  Left: the overnight mixed soak with it on (`soak9_hold.log`, no harm under interference?), then
     Jason's decision; and the slips between two boards (here our own TX_DIS pushes the shared TCXO)
   * the board's lock monitor (`lockmon.v`, the LEDs) judges from the comparators alone and calls strong interference
     'lost' while the oscillator sits on the carrier (4.20): give it VC (REVB U3, the FPGA reading the ADC itself) or
     say on the LEDs 'interference', not 'lost'
   * the standing test: `soak.py run` (randomized disturbances, every one checked against the page's log, its API,
     linkd's counts and its photographs, 4.20); run it after every change to the board's firmware or server
1. The recovery algorithm proven from the PC first: a lock detector from the comparators, and on a loss the downward
   VC_OFF search from above the carrier (3.9j: 52 of 52); then every failure the bench can make, unattended and
   repeated: parked in the false lock and on the rail, dragged by full-power CWs above and below, the carrier blocked
   for seconds and minutes, WiFi-like bursts, the far end restarted; each with its time to recover.
2. The lock supervisor in gateware (ID version 8, with 7's persistence): on at reset in every overlay built from this
   repo, no software needed; its state and counts in registers (losses, recoveries, time locked, the last
   recovery's time, failed searches); a lease for any script that needs the loop itself (refreshed every few seconds,
   or the supervisor takes over again); the PYNQ-Z2's LD0-LD3 and RGB LEDs showing its state (REVB U1, until rev B's
   own LEDs).
3. The dashboard: a service on the PYNQ, started at boot, read-only for now, that re-attaches after any overlay load
   and says so when the loaded bitstream is not CostasLink's.  Live and rolling plots: signal strength, lock state and
   its history, VC (how far from the carrier), the eye from the timing recovery's edge statistics and RX_CDR_SKEW, the
   window comparators' occupancy (a coarse constellation; the real one needs REVB U2 or the B210 as a monitor), the
   interference hold's activity, latency; each state with its cause and the remedy in words.  Every reader of the
   board goes through one owner (the netbus server), so the page never contends with a test (REVB U3); later, control
   from the page through the same owner, which shows who is driving.
4. No separate guide: a help button (?) on every plot opening a short pop-up: what it shows, what good and bad look
   like, what pushes it bad, what to do about it (Jason, 2026-10-31).  Every live plot carries an arrow on its axis
   pointing the good way and bands behind the trace: green good, yellow marginal, red bad, set from the bench's
   measurements and said so in its help.  Two-sided where both ends are bad: the signal strength (more is better up
   to overload), VC's distance from the lock, the latency.  For the physicists brought in at the last minute, the
   colours carry the judgement; the help says why.  First set (from the bench; to be refined):
   * received level (the I leg, and the dBm it means): red below 50 mV, yellow 50-100, green 100-250, yellow
     250-350, red above (overload; the arms clip near 0.5 V); arrow up, capped
   * the loop's offset from the lock (VC, kHz): green within 5 kHz, yellow inside the capture window, red beyond the
     watershed (13-16 kHz below, BRINGUP_LOG 4.12) or past +60 kHz; arrow to the middle
   * the eye (samples open of the symbol, CMP_I's skew from RX_CDR_SKEW): green 13 or more of 16 at 50 Mbaud,
     yellow 10-12, red under 10; the skew green under 1.5 ns, yellow to 3.5, red beyond
   * bit errors (log): green none seen, yellow up to 1e-5, red beyond; arrow down
   * the interference hold's share of time held: green under 1 %, yellow to 10 %, red beyond; and losses and
     recoveries an hour: green 0, yellow 1-3, red more
   * the window comparators' occupancy as a coarse constellation, with the good points' places drawn in

**Gateware next (no hands needed; from the weekend's findings, BRINGUP_LOG 4.3-4.9):**
- **Interference hold and signal holdover: done** (`ihold.v`, ID version 5 on; BRINGUP_LOG 4.8-4.10; `docs/LOCK.md`
  section 7): off at reset, `cl.protect(True)` once locked.  160 of 160 dragging CWs (three carriers) and 4 of 4 blocked
  carriers come back at the 20 ms release (154 of 160 at 1 ms); no hold on the link's own traffic.  RX_IHOLD_HOLD
  resets to 20 ms from ID version 6.
- **The timing recovery's false lock: fixed** (ID 0x434C0006, `8521517`, BRINGUP_LOG 4.10, REVB 30): it tracks the
  rising edges and centres on the measured skew (RX_CDR_SKEW).  The trim tried (BRINGUP_LOG 4.12): I_OFF_F at 3.3 V
  opens the 50 Mbaud eye from 10-12 to 14-15 of 16, so a servo of I_OFF_F on RX_CDR_SKEW during BPSK data is worth
  building (A3's idle wants the no-carrier null instead: switch per mode; the defaults are Jason's call).  It does not
  touch the unlocked loop's push, which is the mid-point of REVB 17 (REVB 18 corrected).
- **Lock detector and search in gateware** (REVB 21, 25, 26): the edge-count lock state as a register, and the downward
  VC_OFF sweep from above the carrier when it reads lost (52 of 52 offsets recovered from the PC, 3.9j).  The measured
  map of the unlocked loop (4.12, `docs/LOCK.md` section 6) says why from above: everything above comes down to the
  lock, while 16-129 kHz below ends in the false lock.  The interference hold cannot cover a CW inside the capture
  window (the loop locks onto it; `captureauto`, 4.12): only this recovers it.
- Build with Vivado 2022.1 for PYNQ 3.0.1 (`build.tcl -strategy Performance_ExplorePostRoutePhysOpt`: the default
  misses the fast path's 6 ns by picoseconds).  The server runs from `~/costaslink_current/`, a symlink to `~/costaslink_lockmon/` (ID 0x434C0008,
  `97a9d8f`, with `link.json`: linkd sets the link up at 5.2 GHz itself), as the boot service `costaslink-netbus`
  since 2026-10-31 12:55 (installed by `install_service.sh`; it starts at power-up and restarts on failure; to deploy
  a new overlay: a new directory, repoint the symlink, `sudo systemctl restart costaslink-netbus`; to hand the PL back
  to notebooks: `sudo systemctl disable --now costaslink-netbus`); `~/costaslink_persist/` (ID 7), `~/costaslink_cdrpol/` (ID 6), `~/costaslink_holds3/` (ID 5) and the
  older directories are kept.  Whenever `gateware/driver/` changes, copy it there and restart the server: the client now warns when
  the server's driver differs from its own (`netbus.driver_id`); `~/costaslink_cdr/`, `~/costaslink_holds*/`
  and `~/costaslink/` (the 2024.1 turnaround overlay) are kept.

Latency checks that fit around these (`bringup/LATENCY.md` section 5): a and b are remote; c is a 2 min recabling after step 1 (TRIG OUT A to ch1, CMP I MON to ch4, both at 50 ohm); d is a rebuild; e (the PYNQ's 200 ohm on the 4 ladder outputs) is your call.

Optional, ten seconds each: JP103 to FPGA with LOOP_SEL held, for a plain PLL on Q. It is a cross-check of the loop's
sign, and not needed once step 1 is done.
