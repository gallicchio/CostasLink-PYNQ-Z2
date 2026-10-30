# Board A: what to do next (written 2026-10-29 21:30; refreshed at 08:00 with the night's results)

Jason can pop in for a few seconds at a time between classes. Moving everything down to the 8720ES (and the grids, in the
same lab) takes one to two hours, so that waits for Monday. "Hands" is Jason's time at the bench. "Unattended" is the
bench running remotely afterwards; the chat says when each step is done, so the next pop-in can wait for it. Nothing here
desolders a part until step 9, and that one only after test A agrees.

The cabling now: TX ANT, 10 cm RG-316, two 20 dB pads, RX ANT. The DSA875 on RX MON's pigtail. The scope: ch1 REF OUT,
ch2 I MON, ch3 Q MON, ch4 VC MON. 50 ohm on TX MON's pigtail. JP201 on TCXO.

| # | when | hands | unattended | what | benefits from | helps |
|---|---|---|---|---|---|---|
| 0 | **done 22:00** | none | | Deployed the reply overlay (ID 0x434C0003; the old overlay and driver backed up on the PYNQ in `~/costaslink_backup_20261029_2150_pdt/`). Turnaround in loopback, RX ANT to TX ANT:<ul><li>**fast path (LUTs pin to pin): 22-25 ns**; ring of the four A3r states 23.5 / 24.3 ns a hop at 5.0 / 5.2 GHz;</li><li>**clocked reply: about 51 ns** first-edge, 59-71 ns settled;</li><li>the FPGA's own share is 5-6 ns on the fast path, 31-42 ns on the clocked one.</li></ul>BRINGUP_LOG 3.4g-h, `plots/link_turnaround.png` | | 1, 5, 8 |
| 1 | first pop-in | **10 s** | 2-2.5 h | **Move both sign jumpers to their other positions**: SIGN B1 (JP101) onto Q+, SIGN B2 (JP102) onto Q-. No soldering. Then, remotely:<ul><li>the lock: pull-in, hold-in, f_n and damping from a VC_OFF step, the attenuator range, the hold test;</li><li>A1 (BPSK by sign(I)), A3 as drawn, the PRBS bit-error rate on CMP_I up to 100 Mbaud;</li><li>the thresholds by counting and the idle false-event rates;</li><li>FSK both ways.</li></ul> | none | 3, 6, 7, 8 |
| 2 | any pop-in after 1's runs | **2 min**, then 2 min to restore | 20 min | **Test B, the leak:** take the lead and pads off. Put a 50 ohm terminator on TX ANT and one on RX ANT, and leave the analyzer on RX MON. Then RX MON and I/Q with TX on and off, at DSA 31.75 and 0, over 4.9-6.0 GHz. If the leak stays, it is on the board; if it falls 20 dB or more, it was the lead, jacks and pads | none (best after 1, which needs the loopback) | 6, 7, rev B |
| 3 | the same pop-in as 2 | **1 min**, then 1 min back | 15 min | **Test C:** the analyzer's SMA from RX MON's pigtail to LO RX MON's. Sweep 3-6.5 GHz with RFOUTB on (the model predicts a peak near 3.8 GHz and a null near 4.3) | none | rev B row 12 |
| 4 | the same pop-in | **1 min** | none | Back to the loopback (lead and two 20 dB pads), the analyzer back on RX MON, unless going straight on to 5 | | |
| 5 | a longer visit | **15 min** | 1-2 h | **Over the air in the office, FPV antennas, about 5.2 GHz:**<ul><li>one antenna on TX ANT and one on RX ANT, each on a lead of a metre or more;</li><li>1-3 m apart, same handedness;</li><li>a 20 dB pad on RX ANT if they are closer than about 30 cm. Never TX ANT to RX ANT on a bare lead.</li></ul>Then, remotely: the map (the antennas' band, the chain divided out), the lock, A3r and A1, the turnaround over the air | 1 (a reliable lock), 2 (the leak's floor), 0 (the overlay) | the lab link |
| 6 | Monday, the trip down (1-2 h to move) | 15 min | none | **Test A:** RX ANT's S11 on the 8720ES, powered and unpowered. The model predicts above -2 dB over 5.5-6.1 GHz, with a sharp feature near 5.9 GHz. This confirms C102 without touching it | none | 9 |
| 7 | Monday, after 6 | 20 min | none | **Test F:** S21 from RX ANT to RX MON at DSA 0 and 31.75: the chain without the leak, at -40 dBm in. The same for TX ANT to TX MON | 6 (the same calibration) | 9, rev B |
| 8 | Monday, in the same lab | 30 min to set up, 30 min to move a grid | 1-2 h | **Over the air with the VV 24 dBi grids at 5.15-5.2 GHz:** TX ANT to one grid's 10 m cable, the other grid's cable to RX ANT, no pads. The VNA's link is -48.2 dB, so RX ANT sees about -39 dBm. Measure the lock, the schemes and the turnaround (subtract 135.6 ns of flight). Then the latency line: move one grid to two more distances; the slope is c, the intercept the electronics | 1, 0, 5 | |
| 9 | Monday, last | **15 min** (the only rework) | 1 h | **Lift C102**, the 0.5 pF shunt from the LNA's input to ground; leave its pads empty, or lift only its ground end. Then repeat A, F and the night's map. The prediction is +25 dB at 5.8 GHz, and RX ANT's S11 from about -0.8 to -7 dB. If it misbehaves, a 0.5 pF goes back on the same pads | 6 (A first) | everything at 5.8 GHz |

Latency checks that fit around these (`bringup/LATENCY.md` section 5): a and b are remote; c is a 2 min recabling after step 1 (TRIG OUT A to ch1, CMP I MON to ch4, both at 50 ohm); d is a rebuild; e (the PYNQ's 200 ohm on the 4 ladder outputs) is your call.

Optional, ten seconds each: JP103 to FPGA with LOOP_SEL held, for a plain PLL on Q. It is a cross-check of the loop's
sign, and not needed once step 1 is done.
