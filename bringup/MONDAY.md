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

If the PYNQ does not answer (it hung once on a reboot, 2026-11-01: BRINGUP_LOG 4.27), it is on the E3646A's output 2 and
the board on output 1: `python3 bringup/bench.py --board A psu cycle --volts 5.3 --amps 1.5` takes the board to 0 V,
switches both off, waits 10 s, and brings them back in order (the PYNQ, its server answering with our overlay, about
90 s, then the board).  Stop the watchdog first and start it again after (`bench.py --board A --stage watch run watch
--hours 64 --pynq-misses 6 --amps-hi 1.5 --pynq-cycles 3`).  The watchdog does the same by itself when the PYNQ has
not answered for a minute, at most 3 times; silent once more, or not back from a cycle, and it switches both off and
leaves them off (Jason: 'If you need to reboot the PYNQ more than a few times and don't know why, just keep things
powered off').  Before restarting the board's server on purpose: `bench.py pause --minutes 10`.

Open the page full screen; with **http://192.168.8.142:8080/?controls=1** it has buttons for the self-test's plan
(off, rounds, single symbols, data, carrier alone) and the holdover (on, off), in place of the `curl` commands below
(the plain address stays read-only for anyone else watching); add `&view=demo` (or `?view=demo`) to put the link's
activity, its signal, its bits and symbols and the scope's views first.  What to show, in order:
1. **The status card's 'Now' line and the lanes 'What is being done'**: the link alternates the carrier alone, single
   symbols (orange: 'idle to one of N', N = 1, 2, 4: A1, A1w, A2, A3) and data (blue: BPSK PRBS15, every bit checked).
2. **Single symbols**: 'how each was decided' (each symbol sent is right, wrong, undecided or missed; false decisions
   besides: from firmware ID 10 they add up exactly), 'latency' (about 56-63 ns since firmware ID 11 decides each symbol once its pattern has settled; 76-80 ns at a fixed delay), the
   last run's spread with its table of states sent against states decided, and the scope's raw and aligned views of the
   symbols' I and Q.  **Latency against certainty** (a minute, the B210 quiet): `{"plan": "a3delay"}` decides A3 at
   10, 15, 20, 25, 30, 40, 60 ns after its first comparator fires: the latency panel climbs a staircase 69-119 ns, and
   below 25 ns one corner of the four goes 'undecided' (its second comparator has not crossed yet; which corner depends
   on which of its two lock points the loop sits on: REVB 32).  `{"plan": "settle"}` shows ID 11's settled decision
   instead: A3 decided once its pattern has held 0-20 ns, the latency falling to 57 ns and, held too briefly (2 or 4
   samples), wrong decisions appearing in the table (a corner passing through another's pattern).  Back with
   `{"plan": "cycle"}`.
3. **Data**: 'Data: bit errors' (green ticks: seconds without an error), the timing recovery's 'comparator skew'
   (judged against the bit), the scope's raw data and its eye.  Three kinds in each round (firmware ID 12): **BPSK**
   (each bit the carrier or the carrier inverted, 2-50 Mbaud), **OOK** (each bit the carrier or its null, read on the
   I window, 2-25 Mbaud) and **QPSK** (A3's four corners with the idle carrier as a pilot between them, 2.5 M symbols a
   second, every symbol decided against what was sent: the single symbols' counts).  The scope is at 50 ohm since
   2026-11-01 (each monitor tap is 1 k into 50 ohm, scaled back by its probe factor of 21): the eye is open at 20
   Mbaud and the fast constellation shows the QPSK corners.  **A point to make**: the corners come out at about 40
   degrees and at the idle's own amplitude, not at 45 degrees and 1.41 times it: the board's transmitter is saturated
   (the B210, listening to it, measured every state at the idle's amplitude: BRINGUP_LOG 4.26, REVB 35).  'The board's
   own constellation, along each window' shows the same from the board's own comparators, no scope needed.  **FSK** (firmware
   ID 13: the transmitter turns its four axis points, one turn a bit, the direction the bit) the board can send but
   not receive (a Costas loop): the B210 decodes it (`python3 bringup/b210link.py from --mods fsk`, 25 kbaud-2.5
   Mbaud, no error).  **Every link** (BRINGUP_LOG 4.29): the board to itself, to the B210, from the B210, and the B210
   to itself all carry BPSK, OOK, QPSK and (but into the board) FSK, the timing recovered across unrelated clocks.
4. **Interference** from the B210, one at a time, each shown on the page's B210 lane:

       python3 bringup/b210demo.py bursts --on-ms 1 --per-ms 20 --gain 85 --seconds 20   # bit errors, false symbols
       python3 bringup/b210demo.py near -20 --gain 89.75 --seconds 5                     # can capture the loop
       python3 bringup/b210demo.py cw +6 --gain 88 --seconds 8                           # drags it off: linkd recovers
       python3 bringup/b210demo.py beacons --gain 89.75                                   # WiFi beacons' rhythm

5. **The physical path**, the B210 quiet: a metal plate between the antennas, then moving an antenna.  For a live
   level every second switch the self-test to the carrier alone (`{"plan": "carrier"}`: RX ANT and the demodulator in
   dBm each second); for live bit errors to `{"plan": "data"}` (BPSK at 25 Mbaud, a 2 s look at the level every 30 s).
   A weaker or stronger path moves the receiver's decision windows with it ('What happened': 'the receiver's decision
   windows followed it'), so single symbols keep being decided down to the noise.  A short block (under 44 ms) rides through; a longer one loses the lock and linkd brings it back in 2-3 s after the
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
* **the frequency plan: one one-way link each way, apart in frequency** (PLAN.md section on duplex, docs/SYSTEM.md:
  frequency-division duplex needs 52 dB of isolation, separate antennas give 30-40, so the split must be wide): A
  transmits at 5.2 GHz to B, B at 5.8 GHz to A, each board's RX on the other's TX frequency.  That needs C102 lifted on
  **both** boards (step 3: the RX at 5.8 GHz) and each board's two synthesizers on different frequencies; until then,
  one direction only (A to B at 5.2 GHz, B's TX muted);
* the software for it (to do before Monday where it can be tested on one board): `link.json` with separate `tx_mhz`
  and `rx_mhz` (linkd sets both synthesizers to one `mhz` today, and the TX's carrier null is per TX frequency); the
  self-test's roles across boards: one board sending data continuously, the other checking every bit (the check
  needs no local copy of the data: `ber_cdr.v` recovers the remote TX's timing); single symbols across boards count
  decisions but not right / wrong without the sender's sequence, so latency across boards is the turnaround's: B
  answers on the fast path, A times the round trip (BRINGUP_LOG 3.4g-h);
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
