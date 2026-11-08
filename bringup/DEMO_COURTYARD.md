# The courtyard demo (Thursday 2026-11-12): two stations, no cable between them

Written 2026-11-07 (Sat) from the bench results to date, rewritten 11-08 (Sun) after the demo's software ran on the
bench (section 9); the build list below is what has to happen by Thursday.
Jason's brief: the pair of antennas outside across a courtyard the size of the lab (15-20 m), for trustees and
donors; each board with its own laptop, power and oscilloscope; the long cable coiled between each board and its
antenna; nothing between the boards but air.  They should see a random bitstream over QPSK on the scopes, see the
received signal fall when someone stands in the beam, and see a delay number rise when a dish is moved.

## 1. The story in one breath

A bit leaves station A, crosses the courtyard at the speed of light (3.3 ns a metre), and is decided at station B
about 100 ns after it arrives, by two comparators and a phase-locked radio that recovers the carrier with no clock
sent along.  The audience sees the bits themselves on an oscilloscope, sees them die when a body blocks the beam and
come back when it moves away, and sees the round-trip time grow by a measurable few nanoseconds when a dish is carried
a metre further off.  The physics purpose (settings for a Bell test chosen and delivered faster than light can carry
news of them between the stations) is told with the delay number on the screen: the courtyard is 50 ns wide and the
electronics decide in 100.

## 2. What exists and is measured (nothing below is a hope)

* **The dish link across the room, both directions, at every carrier 4600-5800** (4.61-4.72): -45 to -47 dBm at
  4800 MHz into RX ANT, a 180-190 mV leg at DSA 10-16; the A family and the PRBS 100 % / error-free over cable, by day
  over the dishes 2e-7 to 5e-6 BER at 2-5 Mb/s with the errors in WiFi bursts (4.60, 4.66, 4.67).
* **The round trip over the air with no cable between the boards** (4.70, `qpvtests.py roundtrip`, the `Duplex`
  class): A's challenge over the dishes at 4800, B's reply over a pair of FPV antennas at 5400 (the lollipop omnis,
  one on each board, 30 cm apart on the bench: Jason, 11-07), both loops locked to the other's carrier at once.  20 000 challenges, 20 000 replies, 0 missed, the reply **217.5 ns
  after the challenge's own TX event, p99.9 220, max 221**, 99.99 % right for one-of-2; one-of-4 99.4 %.  Of the
  217.5 ns: 139.75 the dish path (54.5 ns of air and dishes plus the two 42.5 ns cables, 4.43), 25 the Prover's fast
  path, about 45 the two receive engines' detection, 3 the RF.  That spread is the resolution of the delay demo:
  **a metre more of dish path is 3.3 ns, three of the sampler's 1.25 ns steps, and the mean over a second of
  challenges resolves a few centimetres.**
* **The one-way latency to a decision pin, measured today** (4.88, 4.89): mark to decision 95-105 ns at N = 8,
  of which the analog is a few ns and the gateware's pipeline about 80.
* **Three bits an event (A8) 100 % at delay 8, 16 million events a receiver** (4.87-4.89), over cable; over the
  dishes the A family decodes at 99-100 % (4.65).
* **The random symbol stream**: TX_MODE 'prbs' with 4 points sends a 2-bit random symbol a period (`tx_engine`
  kbits), the receiver's BER checker (`ber_config`, `ber_run`) counts one comparator's bit against the same PRBS
  with its own timing recovery; 25 M bits in 5 s at P20 with 0 errors over cable all through the 11-07 night.
* **The dashboard** (port 8080 on each PYNQ): the lock, the level, the BER panel, the single-symbol decisions, the
  latency histogram, a constellation fed from the bench scope (POST /api/scope), notes and history.
* **linkd** sets a link up unattended from `link.json` at boot (tx_mhz / rx_mhz apart for two boards on two
  carriers), recovers a lost lock, tracks the windows.  `Duplex`'s recovery still mutes the recovering board's own TX
  (4.71, open): item B1 below.

## 3. The one rule: it runs all the time

Jason (11-07 evening): nothing is switched by hand during the demo.  Whatever runs, runs continuously; if the beam
carries different things in turn, it is the software that turns them, every few seconds, forever, and a visitor who
blocks the beam while standing at either scope sees the link die there within a second and come back when they move.

With one pair of dishes there are two ways to run, and they do not combine:

* **Full duplex, the beam's direction fixed** (4.70's arrangement, measured): A's TX on dish A, B's RX on dish B, the
  return from B's TX to A's RX on the FPV pair at a second carrier.  Each board transmits on one antenna and receives
  on the other, so both loops stay locked at once and the round trip runs continuously: **the delay demo works.**  The
  beam's content alternates by itself (section 4).  Blocking the beam kills the stream's constellation on scope B and
  the reply pulses on scope A, so both scopes react, but only scope B ever shows the beam's own bits.
* **Half duplex through the T/R switch blocks, the direction alternating every few seconds**: both scopes take turns
  showing the beam.  But the switch block passes the board's own TX into its own RX 25 dB down (REVB 55), so a board
  cannot receive while it transmits: no return path, no round trip, **no delay number**, and nothing on this hardware
  measures a one-way delay without a cable or a shared clock between the boards (the loops lock the phase, not the
  time; a VCXO in holdover drifts far more than 3 ns in a second).  The constellation and the blocking still work.

This plan takes the first; Jason (11-07 late) agreed: full duplex, the return on the FPV antennas, which have less gain
but a much shorter cable.  **11-08: nothing alternates any more, not even the beam's content.**  Every symbol of the
random QPSK stream is a challenge that B answers at once on the return, so the stream, the exchange and the delay
number are one continuous thing (section 5), and a visitor at either scope sees the beam's effect at every moment.

## 4. The two stations (full duplex)

```
   STATION A ("the sender")                                 STATION B ("the receiver")
   board A + PYNQ + laptop A + scope A + 5 V                board B + PYNQ + laptop B + scope B + 5 V
   TX ANT --- long cable (coiled) --- dish A  ))))))))))))  dish B --- long cable (coiled) --- RX ANT
                                        the beam at 4800 MHz (the one people block)
   RX ANT --- TFP-1 patch  ((((((((((((((((((((((((((((((((((((((  TFP-1 patch --- TX ANT
                                   the return at 5400 or 5800 MHz (the reply; nobody needs to see it)
```

* No T/R switch anywhere.  Every board-to-board FPV measurement (4.70, 4.72, 4.73, 4.80) was the two lollipop omnis
  30 cm apart on the bench, the boards side by side (Jason, 11-08), not across the room: 4.72's 182-191 mV leg at
  DSA 11.75 at 5400 is that 30 cm.  (The first days' tests of one board against the B210 in Jason's office, 4.0,
  used the directional patches; nothing from them bears on the pair.)  Each FPV antenna sits on its own board's RX ANT / TX ANT jack with a short lead.
  **The antennas (Jason, 11-07, photos for the record):** lollipop omnis (about 2 dBi, circular), and
  the "Triple Feed Patch" family by Maarten Baert and Robin Theunis (open-source hardware, CC BY-SA, 5.8 GHz designs):
  the small black **TFP-1, 9.4 dBi** (a 75 mm round board, one patch, three feeds through a hybrid) and the large red
  **TFPA-1 array, 14 dBi** (seven patches on a 200 mm board).  Each has two SMA jacks on the back, **LHCP** and
  **RHCP**, and ships with an SMA plug-to-plug lead, a 50 ohm SMA load and an RP-SMA adapter.  Its silkscreen says
  it: "Do not connect RX and TX to the same antenna!  Terminate unused connectors with 50 ohm terminator for optimal
  axial ratio" (the two ports are the two hands of one radiator, isolated by the axial ratio only).
  **The return uses the two small TFP-1s** (Jason: they hang off the board on a stiff SMA lead, pointing at their
  twin), **RHCP port to RHCP port**: a circular link between two antennas of the same hand facing each other works,
  and a wall's reflection flips the hand and is rejected, which helps outdoors.  Each antenna carries one direction
  only (A's RX, B's TX), as the silkscreen asks; the LHCP ports get the supplied 50 ohm loads; the RP-SMA adapters
  stay in the bag (the boards' jacks are SMA, the supplied lead mates directly).  The lollipops are the spare, the
  array the reserve if the small pair runs short of margin.
  **The return's budget at 15 m**, from two measurements at 5400 that agree within 1 dB: the lollipops 30 cm apart
  (4.72: 185 mV at DSA 11.75; the free-space loss at 30 cm is 37 dB, less 4 dB of omni gain) and the dishes across
  the room (4.65: -57.5 dBm into RX ANT gave a 61 mV leg, so the design leg of 150 mV needs -50 dBm at 5400, and
  the board's TX at 5400 comes out near -5 dBm, 10 dB under its 4800 output).  At 15 m the free-space loss is 71 dB
  and two TFP-1s leave 52 dB of path: about -57 dBm into A's RX ANT, **a 65-80 mV leg at DSA 0**.  Enough for the
  one-of-2 replies (A2 decodes down to 22-35 mV, 4.89: 6-9 dB of margin) but no DSA headroom and nothing for rain, a
  misaim or a hand in the way.  The array pair would give 190-230 mV; one array at either end (+4.6 dB) 110-135 mV.
  5800 is the patch's own band while 5400 is 7 % below it, where a patch's gain and axial ratio are off by an amount
  only a measurement gives; the TX chain at 5800 is 11 dB under 4800 (4.65), about 1 dB under 5400.  So R1 across
  the room (the courtyard's size) measures the small pair at 5400 and at 5800, the stronger lock wins, and if A's
  leg is under about 100 mV an array on a stand replaces one small patch.  The beam's budget is separate and
  comfortable (4800 over the dishes: -45.5 dBm, 180-190 mV at DSA 10-16).
* Two carriers, 4800 for the beam and 5400 for the return, as in 4.70 (the receivers are homodyne: a board's own TX
  at the other carrier is 600 MHz out of its arms' band).  5400 sits in the WiFi gap; 4800 is below the WiFi channels.
  The 5 GHz unlicensed bands are 5150-5350 and 5470-5850 MHz: radiating 4800 outdoors with +4 dBm into an 18 dBi dish
  is Jason's call; the alternatives are 5800 (the ISM band's top, where the TX chain is 11 dB down and the dish link was
  the band's weakest, 4.65) or 5500-5700 (WiFi's DFS channels, usually empty outdoors).  Item O1.
* Each laptop talks to its own PYNQ over Ethernet (192.168.2.99 / .98 today); the laptops need not see each other.
  **Both laptops' WiFi off**: the laptop's radio was the 5200-5400 interferer in the lab (4.80, 4.82).
* Power: each station needs mains for the PYNQ (12 V), the board (5 V), the scope and the laptop: one extension cord
  a station.  The laptops' screens are the demo's screens, so shade.
* Dish B on something that can be carried a metre or two along the courtyard for the delay demo (a tripod, a cart);
  the coiled cable stays by the board.  Both dish cables are 42.5 ns (about 9 m) each: 85 ns of the round trip is
  cable, calibrated out (item B4).

## 5. What runs, and what the audience sees

One continuous mode (built and run on the bench 11-08, `bringup/demo.py`, the numbers in section 9):

```
  station A, the sender, for ever:    A3's four corners at random, one every 500 ns (2 bits a symbol, 4 Mbit/s), the
                                      idle (1, 0) between: the random QPSK stream on scope B.  Every symbol is also a
                                      challenge: A's receiver, on the return path, decodes B's echo of it and pairs it
                                      with A's own TX event (the gateware's reference), so the round trip's histogram
                                      and the replies right / missed / false come out of the FPGA at 2 million a second
  station B, the receiver, for ever:  decodes every symbol (the decision 20 ns after its first edge) and the fast path
                                      answers it within about 25 ns on the return carrier: a corner comes back as its
                                      neighbour (the reply map xor1), so a reply is never the challenge itself
  each station's keeper:              linkd's own code in duplex mode (the board's TX never muted, parked or retuned:
                                      the other station's loop hangs on it); the loop from nothing in about 60 s, a
                                      lost lock back in 1-2 s; the decoder's windows measured from the data itself and
                                      armed again after every recovery; each laptop talks only to its own board
```

`demo.py A` and `demo.py B`, one a laptop, started once (`python3 demo.py A`; the carriers, the port and the symbol
period are arguments), serve their tiles at `http://localhost:8090/` (`demo.html` beside it, `/api/demo` the numbers)
and log a line a second to `data/twoboard/demo_<station>_<stamp>.jsonl`.

### Scope B (the receiver, by the dish that gets blocked): the bits and the lock

Section 5a's view: I and Q as two random waveforms (a symbol every 500 ns, the corner 200 ns of it), the recovered
bit under them, the VCXO's control voltage as a flat line while the loop holds.  A hand in the beam: the levels
shrink, the traces smear as the loop lets go, the green line leaves its place; the hand away: all of it back within a
second or two.

### Scope A (the sender): the ping and the pong

Section 5a's view: A's own TRIG A (the challenge leaving) and TRIG B (the echo recognised) on one baseline, 50 ns/div,
the trigger a division from the left: **a pulse pair every 500 ns, the gap between them the round trip** (120 ns on
the bench's 3 m of cable; the courtyard adds 6.7 ns a metre of dish spacing), the scope's own first-rise-to-first-rise
measurement printing its mean in ns.  Block the beam and the pong is gone; carry dish B a metre and the mean moves.

### Laptop B's page

* **RECEIVED SIGNAL**: the I arm's level in mV as a bar, dBm at RX ANT, the band's power from the log detector, the DSA.
* **THE LOCK**: locked / lost / waiting for the carrier, VC, how often lost and recovered, the last recovery's time,
  and while the beam is blocked: "the beam has been gone for N s".
* **SYMBOLS DECODED**: per second (2 000 000), arriving, undecided, false; the four messages' shares (25 % each).
* **THE ECHO**: the fast path armed and answering.

### Laptop A's page

* **ROUND TRIP, THIS SECOND**: the median in ns in large type, p99.9, max, min, the histogram in 1.25 ns bins.
* **PATH**: metres from the median less the zero-path time (B4's calibration), "1 m of courtyard is 6.7 ns".
* **CHALLENGES ANSWERED**: % right in large type; sent, answered, missed and wrong a second; the totals since the
  start; the 4 x 4 matrix of sent against heard with the expected diagonal marked.
* **THE RETURN PATH**: A's own receiver: signal, dBm, the loop's state, VC, DSA, losses, the lock's side.
* A footer with the board's temperature and the uptime.

### Things a visitor can do, with nobody at a keyboard

1. **Stand in the beam, step out.**  Scope B: the stream dies, the lock line walks away.  Laptop B: the signal bar
   falls, "the beam has been gone for 3 s", symbols a second 0.  Laptop A: answered 0, **missed 2 000 000 a second**,
   the histogram empty.  Scope A: the pong vanishes.  Step out: B's loop back in 1-2 s, A's replies the same second,
   everything counting again (measured 11-08, section 9).
2. **Carry dish B along the courtyard**: the round trip and the metres follow; carry it back.
3. **Turn dish B 90 degrees** (polarization) or point it off: the signal falls by 20 dB and the loop lets go.
4. **Hold a phone's hotspot near a dish** (if B6 is built): the band panel lights the channel and the errors tick.

## 5a. The scopes' views: I and Q and two more things, readable in a few seconds

Jason (11-07): each scope shows I and Q and up to two other interesting things, scaled and shifted so a trustee who
looks for a few seconds sees what is going on.  Both scopes keep one fixed view; nothing is switched.  The channels'
colours are the Siglent's own (ch1 yellow, ch2 pink, ch3 cyan, ch4 green) and this firmware has no channel labels,
so a printed card by each scope names the four traces.  All four inputs through 50 ohm feed-throughs, as on the
bench.  `bringup/demoscope.py preset A|B` sets each view once; `demoscope.py shot A|B` saves the screen.

### Scope B, by the dish that gets blocked: "the bits, and the lock"

| trace | jack | what the trustee sees | scale, place |
|---|---|---|---|
| ch2 pink, **I** | J104 I MON | the in-phase arm: a random waveform, one level a symbol | 10 mV/div, centred 3 div up |
| ch3 cyan, **Q** | J105 Q MON | the quadrature arm: a second random waveform, independent of the first (the two bits of each QPSK symbol) | 10 mV/div, centred 1 div up |
| ch1 yellow, **the bit** | J103 CMP I MON | the comparator's clean 0 / 1 under I: the analog wiggle above becomes a digital bit here; the scope triggers on its edges | 0.2 V/div, centred 1 div down |
| ch4 green, **the lock** | J107 VC MON | the VCXO's control voltage: a flat line at 1.65 V while the loop holds the carrier; block the beam and the line walks away to a rail, unblock and it slides back | 1 V/div, centred 3 div down |

Timebase 100 ns/div (two 500 ns symbols across, each corner 200 ns of it), trigger on ch1 rising at 0.15 V, normal mode,
**persistence 1 s**:
with the trigger on the bit's edge the frames pile up into an eye diagram on I and Q, open while the link is clean;
a hand in the beam closes the eye (the levels shrink, then the traces smear as the loop lets go), and the green line
leaves its place.  Blocking the beam thus moves every trace at once.  The level: a 150-180 mV leg is 7-9 mV at the
scope through the 1 k tap, 0.7-0.9 div at 10 mV/div in a 2-division band; if the eye wants to be bigger, the ch2 /
ch3 feed-throughs come off (1 Mohm: x21 larger, the edges rounded by the lead's capacitance, 50 mV/div) and the
decision is made at R1 by looking.

### Scope A, the sender: "the ping and the pong"

| trace | jack | what the trustee sees | scale, place |
|---|---|---|---|
| ch2 pink, **I** | J104 I MON | A's own receiver: the return path's random stream most of the time, the reply's blip during an exchange | 10 mV/div, centred 3 div up |
| ch3 cyan, **Q** | J105 Q MON | the same for Q | 10 mV/div, centred 1 div up |
| ch1 yellow, **ping** | J205 TRIG A | the challenge leaving the board: a pulse at the left of the screen | 1 V/div, baseline 2.5 div down |
| ch4 green, **pong** | J206 TRIG B | the reply recognised by A's FPGA: a pulse to the right of the ping, on the same baseline, **the gap between them is the courtyard** | 1 V/div, the same baseline |

Timebase 50 ns/div with the trigger 1 div from the left (the pong lands 2.4 div right at the bench's 120 ns, 4-5 div
across the courtyard), trigger on ch1 rising at 0.85 V: a pair every 500 ns, the previous pair's pong off the screen
to the left.  The scope's own delay measurement, first rising edge of ch1 to first rising
edge of ch4 (`MEAD FRR,C1-C4`) with statistics on, prints the mean in ns at the bottom and holds it between
looks; carry dish B a metre and the mean moves 6.7 ns (there and back).  Blocking the beam removes the pong and the
mean stops updating.  On the bench (11-08, `plots/demoscope_bench_A_20261108_1014.png`, `_B_`) ch1 is the far
board's TRIG A, so the presets were tried with the trigger on ch4 (`demoscope.py preset A --trig 4`); the demo's own
cabling (ch1 = the board's own TRIG A on A, CMP I MON on B) is R1's.

## 6. The build list, in order

| | what | why | where | state |
|---|---|---|---|---|
| B1 | **Duplex unattended and self-healing**: each board's loop kept by linkd's code in duplex mode (its TX never muted, parked or retuned; the no-carrier work on a parked RX synthesizer; the sequencer's centring steps with the TX kept on; the recovery's releases +10 / +16 / -10 kHz first) | the demo must survive a hand in the beam and a restart with nobody typing | `linkd.py` (72b3314), `duplex_up.py` | **done on the laptop side 11-08** (both keepers from nothing at once in about 60 s, a 3 s block recovered in 1.5 s with the other loop untouched, the far board gone and back re-locked by itself); `link.json` with `"duplex": true` on each PYNQ for the unattended boot: to deploy and try |
| B2 | **The demo driver** `bringup/demo.py` + `demo.html`: the continuous mode of section 5, the keeper, the windows from the data, the tiles | the numbers in section 5 | `demo.py`, `demo.html`, `demo_bench.sh` | **done on the bench 11-08** (section 9) |
| B3 | **Scope presets** `demoscope.py preset A|B` (section 5a) | the scopes are half the show | `demoscope.py` | written; the mechanics tried on the bench with the trigger on ch4; the real views need R1's cabling |
| B4 | **The metres calibration**: T0 from one round trip at a tape-measured dish spacing (`--t0_ns` on A, or a file); the page then shows metres | the delay number must read as a distance | `demo.py` | R1, 15 min with the dishes |
| B5 | **The adopt path**: a restarted `demo.py` takes over a running loop without the 60 s setup (the middles and centres from the PYNQ's linkd) | a restart during the demo costs a minute now | `demo.py`, `dashboard.py`'s `/api/now` | if time |
| B6 | **The band panel** (optional): the receiver's survey as a bar chart on laptop B, taken in the gaps | interference is part of the story | `survey()` exists | Tue if time |
| R1 | **Rehearsal 1, Mon**: the dishes across the room, the two TFP-1s on their boards across the room too (the first time the return crosses more than 30 cm): A's leg at 5400 and at 5800, RHCP to RHCP, LHCP loaded, the carrier and the antenna size decided on it (section 4); **the scopes cabled for section 5a** (A: ch1 its own TRIG A, ch4 TRIG B; B: ch1 CMP I MON, ch4 VC MON; no TRIG IN leads anywhere); both laptops; then the full loop for an hour with nobody touching anything, then the blocking and the carrying; B4 | find what breaks; the return's real leg | | Mon pm |
| R2 | **Rehearsal 2, Tue or Wed**: the courtyard itself, power from the building, the laptops' WiFi off, the sun on the screens, the survey of the outdoor band; the carrier choice (O1) settled by it | the outdoors | | Wed |

Not for Thursday: the gateware's pipeline (REVB 68), the TRIG IN pairing (REVB 69).  Nothing in the demo needs a
gateware change.

## 7. What can go wrong, and the answer

* **WiFi outdoors** at 5150-5350 / 5470-5850: the beam at 4800 avoids it, the return at 5400 sits in the gap; the
  survey at R2 confirms; the errors a phone causes become a demo (section 5, item 5).
* **The loops when the beam is blocked** (measured 11-08): B's loop loses the beam and waits for the carrier, A's loop
  keeps the return; the beam back, B re-locks in 1-2 s and arms its decoder again, A's replies return the same second
  (A's own windows untouched).  The return blocked: A the same, B untouched.  Through a 3 s block nothing needs a key.
* **While the beam is blocked**: laptop B shows the signal gone and counts the seconds; laptop A shows 2 million
  challenges a second missed and an empty histogram: both are the demo working.
* **The two carriers must be 600 MHz apart or more** (4800 / 5400 as planned; 4800 / 5000 on the bench put each board's
  own TX events into its own receiver through the demodulator's 390 MHz baseband: a false 'reply' 85 ns after every
  challenge, 11-08 09:22).  5800 for the return (if R1 prefers it) is 1000 from 4800: fine.
* **No TRIG IN lead anywhere in the courtyard**: with JP203 fitted TRIG IN drives the Q ladder, and the bench's
  TRIG A -> tee -> TRIG IN cross-wiring put every TX event of one board into the other's Q (09:22).  `demo.py`'s
  `--trig_a off` is for the bench only; in the courtyard A's TRIG A is the ping on scope A.
* **The (-1, +1) corner at a weak return**: its I arm lags its Q (REVB 66), so at delay 8 A left that echo undecided on
  its 75 mV return; delay 24 and the I windows at 0.4 of the swing decode 98 % of it (the other three 100 %); the
  missing 2 % show as 'answered' without 'decided' and cost nothing else.  A stronger return (section 4) will help.
* **The keeper's leg under the stream**: linkd learns the leg from the idle carrier; under the stream I's mean is 0.6 of
  it, so B's setup stopped two DSA steps high (13.75 for a 127 mV leg instead of 150).  Harmless for the demo (the
  windows come from the data), noted for linkd.
* **Alignment outdoors**: the power tile is the alignment tool; an 18 dBi dish is about 8 degrees wide; a 9.4 dBi
  patch is about 60 degrees wide (the 14 dBi array 35), pointed by eye at its twin.  Polarization: both dishes the
  same way up; the patches are circular and do not care how they are turned.
* **The second laptop**: needs the repo, python3 with numpy and the lab driver for the scope, the bench config for its
  PYNQ; set up and tested at R1.
* **Power and weather**: section 4; a dry run at R2.
* **Someone handles a dish cable while the metres readout is on**: the cable's delay is in T0; coiling changes it by
  nothing measurable (4.43's cables repeated to 5 ps).

## 8. Open questions (Jason)

* O1: the beam's carrier outdoors: 4800 as measured, or inside an unlicensed band (5800, or 5500-5700)?
* O2 (settled 11-07): full duplex with the beam's direction fixed; the return on the FPV patches.
* O3: a TV or projector for the laptops' pages, or the laptops' own screens?
* O4: who carries dish B, and on what (tripod, cart)?  The metres readout wants a straight walk of 2-3 m.
* O5: two independent stations (this plan; nothing needed of the venue), or one page showing both (a network between
  the laptops at the courtyard)?

## 9. The bench rehearsal (11-08, 09:53-10:15): the demo's software over the cables

The bench as the night's (A -> B on the 2 m cable, B -> A on the 1 m, 50 dB of pads each), A sending at 4800 and
receiving at 5400, B the mirror; `demo_bench.sh start` ran both stations from this laptop (A's TRIG A off: the bench's
TRIG IN wiring).  What it did:

* **From nothing**: both keepers set up at once, A locked in 58 s (a 76 mV leg on the 5400 return, DSA 7.75), B in 62 s
  (4800, 127 mV at DSA 13.75); A streaming within a second of its lock, B decoding within two of its.
* **Steady**: A 1.9-2.0 million challenges a second, **replies 100 %, missed 0, false 0-1 a second, wrong 0** (the
  four challenges 1.000 each over 540 000 of each a second); B 2.0 million symbols a second decoded, the four messages
  25.0 % each; **the round trip 120 ns median, 112.5-125 ns min to max** (A's decision 30 ns after the echo's first
  edge, B's 20 ns after the symbol's; the 12 ns spread is the word clock's phase on both boards).
* **The beam blocked 3 s** (A's TX muted): B 'waiting for the carrier' within 0.5 s, A's replies 0 and missed 1.9 M/s
  for the 3 s; the carrier back, **B locked again after 1 s** and decoding after 3 (its windows measured again), A's
  replies back the same second at 100 %.  **The return blocked 3 s**: A waiting, then locked 2 s after the carrier
  returned, armed 2 s later; B never noticed.
* The earlier runs found the pieces this depends on: the carriers 600 MHz apart (4800 / 5000 gave false replies at
  85 ns); the recovery's releases near the lock (B at 4800 captures within +16 / -8 kHz and has false locks at -31
  and +43-49 kHz: `recov_probe.py`); the sequencer's centring steps muting the TX by default (A's lock flickered at
  every one of B's releases); the windows from the keeper's leg while the stream runs sat too low (B decided the
  (-1, +1) corner as (+1, +1) and vetoed it 27 % of the time) and the fast path's 40 ns echo too short for A's I arm:
  the windows now come from the data's own duty staircase, the echo lasts 80 ns, A decides at 30 ns.
* Records: `data/twoboard/demo_A_20261108_101227.jsonl`, `demo_B_20261108_101228.jsonl` (a line a second),
  `duplex_up_20261108_094918.json`, `contrun_20261108_091739.json`; the bench screens
  `plots/demoscope_bench_A_20261108_1014.png`, `_B_`.
