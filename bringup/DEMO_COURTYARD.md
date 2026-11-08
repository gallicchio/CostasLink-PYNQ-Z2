# The courtyard demo (Thursday 2026-11-12): two stations, no cable between them

Written 2026-11-07 (Sat) from the bench results to date; the build list below is what has to happen by Thursday.
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
  class): A's challenge over the dishes at 4800, B's reply over a pair of FPV antennas at 5400 (one on each board),
  both loops locked to the other's carrier at once.  20 000 challenges, 20 000 replies, 0 missed, the reply **217.5 ns
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

This plan takes the first; the second is the fallback if the delay demo is dropped (O2).

## 4. The two stations (full duplex)

```
   STATION A ("the sender")                                 STATION B ("the receiver")
   board A + PYNQ + laptop A + scope A + 5 V                board B + PYNQ + laptop B + scope B + 5 V
   TX ANT --- long cable (coiled) --- dish A  ))))))))))))  dish B --- long cable (coiled) --- RX ANT
                                        the beam at 4800 MHz (the one people block)
   RX ANT --- FPV antenna  ((((((((((((((((((((((((((((((((((((((  FPV antenna --- TX ANT
                                        the return at 5400 MHz (the reply; nobody needs to see it)
```

* No T/R switch anywhere.  The FPV pair carried 5400 across the room with 12 dB of DSA to spare (4.72: a 182-191 mV
  leg at DSA 11.75), so it carries the courtyard; each FPV antenna sits on its own board's RX ANT / TX ANT jack with
  a short lead.
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

The demo driver (`bringup/demo.py`, one instance a laptop, started once) keeps both loops up through linkd and
cycles the beam's content by itself:

```
  on the beam (A -> B), repeating forever:
     4 s   the random QPSK stream: TX_MODE prbs with the four corners, 5-10 M symbols a second
     1 s   the exchange: 20 000 one-of-2 challenges at 1 in 1000 clocks; B replies on the return path
  on the return (B -> A), all the time:
     B's fast-path reply to each challenge (24 ns turnaround), and between exchanges B's own random stream
```

Nothing changes on the scopes between the two phases: scope B stays in XY and the constellation simply changes
shape (four dots during the stream, two during the exchange); scope A stays in the time view triggered on its own
challenge mark, in normal trigger mode, so the last exchange's two pulses and the delay number stay on screen through
the stream phase and refresh every 5 s.  The tiles on the laptops refresh from whichever phase last ran.

### Scope B (the receiver, by the dish that gets blocked)

* ch2 = I MON, ch3 = Q MON of board B's receiver, **XY mode with persistence**: four dots for the QPSK stream, two
  during the exchange, the dots' size the noise.  A hand in the beam shrinks the dots toward the centre (the level),
  then the lock drops and the dots smear into a ring (the loop running free); the hand away, the dots snap back
  within a second or two (linkd's recovery).
* ch4 = TRIG B: the receiver's decision pulses (one per challenge during the exchange, the stream's symbol decisions
  otherwise), for anyone who asks what the FPGA is doing.

### Scope A (the sender, the delay on screen)

* ch1 = board A's own TRIG A (the challenge leaving), ch4 = board A's TRIG B (the reply arriving, detected):
  **two pulses about 220 ns apart on one screen, with the scope's own delay measurement (ch1 rise to ch4 rise)
  printed in ns at the bottom**.  Carry dish B a metre further: the ch4 pulse walks right by 3.3 ns and the number
  follows; carry station B a metre (dish and FPV antenna both): 6.7 ns.  Block the beam: the ch4 pulse vanishes (no
  challenge gets through, so no reply), and returns with the beam.
* ch2 / ch3 = A's own arms: the return path's constellation during B's stream, for the curious.

### Laptop B (the receiver's page, big tiles)

* **RECEIVED POWER**: dBm at RX ANT from the log detector (`received_dBm`), a bar, and the last 60 s as a strip
  chart; the leg in mV beside it.  Amber below -55 dBm, red when the lock is lost.
* **LOCK**: locked / searching, the VCXO's VC, time since the last loss, how many recoveries today.
* **DATA**: the stream's bits counted since the last reset (running up at 5-10 million a second during the stream
  phases), the errors, the BER over the last phase and overall.  Blocking the beam makes errors appear; the counter
  keeps the history ("2.4 billion bits, 31 errors, all while someone stood in the beam").
* **MESSAGES**: the 8 x 8 grid of the gateware's confusion matrix (sent against decoded) from the exchange, and
  item B5's one-of-8 key.
* The constellation mirrored from the scope through /api/scope, as the bench page already does.

### Laptop A (the sender's page)

* **ROUND TRIP**: the last exchange's 20 000 challenges as a histogram in 1.25 ns bins, p50 / p99.9 / max in large
  type; **PATH**: (p50 - T0) x c / 2 in metres, T0 calibrated once at a tape-measured spacing (item B4), so moving the
  dish reads out in metres to a decimal, refreshed every 5 s.
* **THE BUDGET**: a fixed strip with the measured pieces: cable 5 ns a metre, air 3.3 ns a metre, the boards' RF 1-3 ns,
  the sampler's path 65 ns, the decision 10 ns, the whole 100 ns, with the date measured.
* **CHALLENGES**: sent, replied, right (%), the reply's latency p50, as counters since the last reset.
* **THE BAND** (optional, item B6): the receiver's survey of 4.4-6.0 GHz, what WiFi is around the courtyard.

### Things a visitor can do, with nobody at a keyboard

1. Stand in the beam, step out: at scope B the constellation collapses and the lock drops, at scope A the reply pulse
   vanishes; laptop B's power bar falls and errors tick; everything comes back within two seconds of stepping out.
2. Carry dish B along the courtyard: the round trip and the metres follow; carry it back.
3. Turn dish B 90 degrees (polarization) or point it off: the power falls by 20 dB and the loop lets go.
4. Press a key on laptop A (item B5): a message (one of 8) appears on laptop B's grid, with its latency.
5. Hold a phone's hotspot near a dish (item B6): the band panel lights the channel and the errors tick.

## 6. The build list, in order

| | what | why | where | estimate |
|---|---|---|---|---|
| B1 | **Duplex unattended and self-healing**: both PYNQs bring the exchange up from `link.json` (A: tx 4800 / rx 5400, B: tx 5400 / rx 4800), each loop recovers without muting its own TX (4.71's open item), a blocked beam re-locks within 2 s of clearing, and a lost return path (unlikely: it is not blockable) the same | the demo must survive a hand in the beam and a restart with nobody typing | `linkd.py` (the duplex release_at from `qpvtests.Duplex` folded in), `link.json` on each PYNQ, `deploy_pynq.sh` | Sun |
| B2 | **The demo driver** (`bringup/demo.py`, one a laptop, started once): on A the 4 s / 1 s cycle of section 5 (prbs mode with the four corners, then the A2 exchange with the fast path on B) and the tiles' numbers at 2-5 Hz to the page; on B the BER checker on the stream, the reply armed, the tiles | the numbers in section 5 | `demo.py`, `dashboard.py` (a `/api/demo` route and the tile page `demo.html`) | Sun-Mon |
| B3 | **Scope presets**, set once at the start by `demo.py`: scope B in XY with persistence on ch2 / ch3; scope A in the time view at 50 ns/div, normal trigger on ch1, the ch1 -> ch4 delay measurement on screen; nothing changes afterwards | the scopes are half the show | `scope_e` with raw `XYDS`, `PESU`, `PACU` commands | Mon |
| B4 | **The metres calibration**: T0 from one round trip at a tape-measured dish spacing, and the cables' 85 ns from 4.43; the page shows ns and metres | the delay number must read as a distance | `demo.py` | Mon, 15 min with the dishes |
| B5 | **The message key**: a key on laptop A sends one of 8 (TX_MSG + a single event) in the next exchange phase, laptop B shows which arrived; ten a second is plenty | the 3-bit scheme made tangible | `demo.py` | Tue |
| B6 | **The band panel** (optional): the receiver's survey as a bar chart on laptop B, taken in the gaps | interference is part of the story | `survey()` exists | Tue if time |
| R1 | **Rehearsal 1, Mon**: the dishes across the room as 4.70, both laptops, the full loop of section 5 for an hour with nobody touching anything, then the blocking and the carrying | find what breaks | | Mon pm |
| R2 | **Rehearsal 2, Tue or Wed**: the courtyard itself, power from the building, the laptops' WiFi off, the sun on the screens, the survey of the outdoor band; the carrier choice (O1) settled by it | the outdoors | | Wed |

Not for Thursday: the gateware's pipeline (REVB 68), the settled decision as the default (tonight's cycle says
whether it is right), the TRIG IN pairing (REVB 69), a stream with challenges embedded in it (which would remove
the 4 s / 1 s alternation: a gateware item for later).  Nothing in the demo needs a gateware change.

## 7. What can go wrong, and the answer

* **WiFi outdoors** at 5150-5350 / 5470-5850: the beam at 4800 avoids it, the return at 5400 sits in the gap; the
  survey at R2 confirms; the errors a phone causes become a demo (section 5, item 5).
* **The loops when the beam is blocked**: B's loop loses the beam, A's loop keeps the return (the FPV pair is not
  blocked), B recovers alone when the beam returns; with B1 done this is the 1-2 s linkd already shows on the bench.
  Without B1 a lost lock needs a keypress: the fallback is `demo.py` calling `recover` itself.
* **The exchange phase while the beam is blocked**: no replies, the histogram empty, the PATH tile shows "no path";
  the stream phase then shows the errors: both are the demo working.
* **Alignment outdoors**: the power tile is the alignment tool; an 18 dBi dish is about 8 degrees wide, the FPV pair
  does not care.  Polarization: both dishes the same way up.
* **The second laptop**: needs the repo, python3 with numpy and the lab driver for the scope, the bench config for its
  PYNQ; set up and tested at R1.
* **Power and weather**: section 4; a dry run at R2.
* **Someone handles a dish cable while the metres readout is on**: the cable's delay is in T0; coiling changes it by
  nothing measurable (4.43's cables repeated to 5 ps).

## 8. Open questions (Jason)

* O1: the beam's carrier outdoors: 4800 as measured, or inside an unlicensed band (5800, or 5500-5700)?
* O2: full duplex with the beam's direction fixed (this plan: the delay demo works, scope B shows the beam, scope A
  the round trip), or half duplex on the switches with the direction alternating (both scopes show the beam in turn,
  no delay demo)?  A second dish pair would give both.
* O3: a TV or projector for the laptops' pages, or the laptops' own screens?
* O4: who carries dish B, and on what (tripod, cart)?  The metres readout wants a straight walk of 2-3 m.
* O5: two independent stations (this plan; nothing needed of the venue), or one page showing both (a network between
  the laptops at the courtyard)?
