# Monday 2026-11-02: the plan

Jason's list (2026-10-31 22:00), each step with what it needs, what to do, and what it tells us.  The state at the
start: board A on the bench in the office, over the air at 5.2 GHz (FPV antennas 30-40 cm apart, the B210 beside
them), the board server with linkd and the self-test (`selftest.py`), the status page at http://192.168.8.142:8080/.
Board B has never been powered (stage 0).

## 1. Show the students the setup (the office, about 30-45 min)

Before they arrive (5 min, from the bench PC):

    # the board's own rounds: the carrier's level, single symbols, data at 10/20/25/50 Mbaud
    curl -X POST -d '{"on": true, "plan": "cycle"}' http://192.168.8.142:8080/api/selftest
    # the bench scope photographed in each symbols and data step, posted to the page
    python3 bringup/scopewatch.py &

Open the page full screen; with **http://192.168.8.142:8080/?controls=1** it has buttons for the self-test's plan
(off, rounds, single symbols, data, carrier alone) and the holdover (on, off), in place of the `curl` commands below
(the plain address stays read-only for anyone else watching).  What to show, in order:
1. **The status card's 'Now' line and the lanes 'What is being done'**: the link alternates the carrier alone, single
   symbols (orange: 'idle to one of N', N = 1, 2, 4: A1, A1w, A2, A3) and data (blue: BPSK PRBS15, every bit checked).
2. **Single symbols**: 'how each was decided' (right / wrong / false / missed each second), 'latency' (about 70-80 ns,
   the receiver's settling included), and the scope's raw and aligned views of the symbols' I and Q.
3. **Data**: 'Data: bit errors' (green ticks: seconds without an error), the timing recovery's 'comparator skew'
   (judged against the bit), the scope's raw data and its eye.
4. **Interference** from the B210, one at a time, each shown on the page's B210 lane:

       python3 bringup/b210demo.py bursts --on-ms 1 --per-ms 20 --gain 85 --seconds 20   # bit errors, false symbols
       python3 bringup/b210demo.py near -20 --gain 89.75 --seconds 5                     # can capture the loop
       python3 bringup/b210demo.py cw +6 --gain 88 --seconds 8                           # drags it off: linkd recovers
       python3 bringup/b210demo.py beacons --gain 89.75                                   # WiFi beacons' rhythm

5. **The physical path**, the B210 quiet: a metal plate between the antennas, then moving an antenna.  For a live
   level every second switch the self-test to the carrier alone (`{"plan": "carrier"}`: RX ANT and the demodulator in
   dBm each second); for live bit errors to `{"plan": "data"}` (BPSK at 25 Mbaud, a 2 s look at the level every 30 s).
   A short block (under 44 ms) rides through; a longer one loses the lock and linkd brings it back in 2-3 s after the
   path clears ('Lost', 'Recovering', 'Locked' on the card, a red stretch in 'Lock, over time').  With the holdover
   on, every block up to about 100 s rides through as 'Carrier interrupted: holding' (BRINGUP_LOG 4.22; half of them
   come back half a cycle over, listed as a slip): turning it on is your call, and the demo can show both:

       curl -X POST -d '{"holdover": true}' http://192.168.8.142:8080/api/selftest     # and false to turn it off

   (from inside the board's server, so linkd is not paused; a server restart also turns it off).
6. Afterwards: `{"on": false}` (or leave it on: it pauses whenever a bench program drives the board).

## 2. Board A to the VNA (the RACON room, 1-2 h with the move)

Needs: the 8720ES calibrated (full 2-port, 3-6.5 GHz, -30 dBm or less into the board), the board's E3646A and the
PYNQ moved with it (or a lab supply at 5.3 V, 1.2 A limit), the U.FL pigtails on.  TODO steps 6-7:
* **Test A: RX ANT's S11**, the board powered and unpowered.  The model (`sim/aslaid/REPORT.md`) predicts -0.8 dB at
  5.8 GHz (above -2 dB over 5.5-6.1 GHz, a sharp feature near 5.9) from C102's branch resonating.
* **Test F: S21 RX ANT -> RX MON** at DSA 0 and 31.75 (-40 dBm in): the chain without the TX leak (REVB 10); the bench
  map read 37-44 dB at 3.0-4.4 GHz, 30 at 5.0, about 7 at 5.7-5.8 (REVB 8).  **TX ANT -> TX MON** as well (REVB 4, 6).
* Save every trace as touchstone into `bringup/data/board_A/vna/` (not committed); the plots into BRINGUP_LOG.

## 3. Lift C102 (15 min at the iron)

C102 is the 0.5 pF shunt from the LNA's input (U101 RF_IN) to ground at the end of a 1.8 mm branch; with its own and its
ground's inductance it is series-resonant near 5-6.5 GHz, a short across the input at 5.8 GHz (REVB 8;
`layout/lna_input_model.py`).  Lift it (or only its ground end) and leave the pads empty.  The prediction: **+24-25 dB
at 5.8 GHz**, RX ANT's S11 from about -0.8 to about -7 dB.  Then repeat tests A and F at once (the VNA is calibrated
already).  If it misbehaves, a 0.5 pF goes back on the same pads.

## 4. The link again with one board (back in the office, 1 h and the night)

* The map over 3-6 GHz (`overnight.py map`) to see the chain's new gain; the carrier null and the arms' offsets at the
  new carrier (`campaign.py cal`), and a `link.json` for 5.8 GHz if the antennas favour it (5.2 GHz's still works).
* Then the standing test: `python3 bringup/soak.py run` (randomized disturbances, single symbols, data, each checked
  against the page's log, its API, linkd and its photographs; BRINGUP_LOG 4.20-4.23) at both carriers overnight.

## 5. Two boards (the office)

Needs: **board B brought up first** (never powered: stages 1-3 of BRINGUP.md, as board A took on 10-28/10-29:
first power with the current limit, the rails, the synthesizers, the TX, the receive chain; `stages.py` does them with
verdicts, a few hours), and **a second PYNQ-Z2** with the PYNQ 3.0.1 image and the overlay (ID 8) deployed beside a
second board server (its own IP; bench.py's config names the host).  Then:
* each board's TX to the other's RX over the air (A's TX antenna toward B's RX antenna and back; the two TCXOs differ by
  about 1 ppm, 5 kHz at 5.2 GHz: inside linkd's starts from above);
* each board locks to the other's carrier; the BER check works across boards (`ber_cdr.v` recovers the remote TX's
  timing); latency across boards needs the turnaround (board B answers, board A times the round trip: the fast path
  and the synchronous reply, BRINGUP_LOG 3.4g-h) since 'ref_to_decision' times only this board's own TX.
* Two status pages (one per PYNQ): a fleet page that shows both side by side is on the list (IMPROVEMENTS.md).

## 6. Across the long lab (TODO step 8)

The VV 24 dBi grids at 5.15-5.2 GHz (5.15-5.85 GHz band), each on its 10 m cable to TX ANT / RX ANT, no pads: the VNA's
link was -48.2 dB, so RX ANT sees about -39 dBm.  Measure the lock, the schemes, the turnaround (subtract 135.6 ns of
flight), then the latency line: move one grid to two more distances; the slope is c, the intercept the electronics.
With two boards, one at each end, each with its own PYNQ and its own page.
