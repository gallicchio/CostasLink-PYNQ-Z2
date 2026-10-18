# Chat with Claude about CostasLink-PYNQ-Z2

Every prompt is recorded here as it was typed, with minor typos fixed, followed by the
response. The design files, scripts and documents in this directory are what the responses
produced. Times are US Pacific. The rules this board is held to are the repository's
`CLAUDE_PCB.md`.

## Prompt 1

My group has been working on an extremely low-latency link at 5.8 GHz to do Quantum Position
Verification. Ideally, the latency from toggling a bit on one FPGA to presenting that bit on the
other FPGA should be the speed of light travel time plus 10's of nanoseconds (the lower, the
better). Our first attempt was an OOK with a PLL and fast switch at the transmitter, and an
envelope detector at the receiver. We are pursuing this in the SyzygyRadioDrivers PCB, which you
should look at for details. The problem is that we don't know when various entangled photons will
arrive and the receiver doesn't know exactly when to look. Each FPGA is sending mostly nothing,
and only occasionally needs to send a bit (often two bits), which need to arrive with as little
additional latency as possible. Triggering on the threshold of envelope power is fine, but it
might not be scalable to multiple links in a noisy environment, since there's basically no
filtering on frequency.

I'd like to investigate two or three other schemes in the 5-8 GHz range (where we have antennas).
One is a PSK link with a hardware Costas loop. The other is an FSK link. The final one is QPSK,
where both bits can be sent "at once" such that the last bit arrives with the least total latency.

The phase recovery (of PSK) and timing recovery (of both) need to be done in *hardware* to get
such low latency. I want you to design a PCB to test both the PSK and FSK schemes, and possibly
the QPSK scheme if that's reasonable.

The board should talk to an FPGA. I think that the PYNQ-Z2's raspberry pi header like you did in
the GPSDO-PYNQ-Z2 is easier for prototyping than the SYZYGY connector on the Brain-1, but I could
be convinced otherwise if the Brain-1 is the appropriate platform. Each link needs to be
bi-directional. (A "prover" gets a 2-bit measurement basis, does a measurement, and sends one or
two bits of result.) This central prover station will be a central station that needs to have a
bidirectional link in 3 different directions. One question is whether we can achieve such low
latency with only a single antenna pointed at each recipient, or if we need separate TX and RX
antennas. Right now with OOK, we are planning on doing it with 1 with a fast switch, but it is
expensive and probably finicky. I don't know how much frequency multiplexing buys you within the
5-6 GHz WiFi+ISM band and at what point you need a very fast switch again.

I want you to make a board to do one bidirectional link using the two or three different
schemes. I'll have JLCPCB make at least two of these boards and have them talk to each other.
First they'll go across the room. Then, with power amplifiers, we'll see how far they can go
across campus or up into the mountains. This project is for the actual quantum position
verification research, but I also want it to educate me about hardware Costas and timing
recovery loops. I've been more of a software-defined-radio person, but that's totally out of the
question at these latency constraints. Adding more U.FL connectors to probe the chain would help
me get a sense for what's going on in the hardware implementation of these things.

Start a new directory here in OpticsPCBs. Be careful about committing and avoid making branches,
since other agents may be using OpticsPCBs in other sub-directories.

Most importantly, follow all of the relevant advice in ~/OpticsPCBs/CLAUDE_PCB.md. This includes
recording all prompts and responses in CLAUDE_CHAT.md

Unlike the simpler PCBs, I realize that I may end up having to consign some specialty parts. If I
have to consign anything, I might as well consign everything that makes sense to consign for cost
savings or to allow a wide selection of ideal parts. Check for Digi-Key and Mouser stock. Ideally
I'd order only from one or the other and have them ship it directly to JLCPCB. I expect that this
board will be less expensive than the SyzygyRadioDrivers board. Optimize a little on cost for
this early and educational prototype. When you write your reply, let me know why you chose the
parts you did and why you rejected other options. This will allow me to go back and possibly
change some choices to cheaper parts or fancier parts for reasons that you couldn't have known
about in advance.

If you need data sheets that you can't get, let me know and I'll download them. I might not get
to it until tomorrow morning, but do what you can with what you can get.

*(Added while the first response was in progress:)* Additional boards that follow similar design
techniques are in `~/mudd/pcbs/OWLternatingCurrent` and `~/mudd/other/GPiBridge`.

## Response 1  2026-10-09 00:30 - 02:50 PDT  Claude Fable 5.1

Everything below is in the new directory `CostasLink-PYNQ-Z2/` (nothing committed; the only files
touched outside it are two gitignore rules appended to the repository's `.gitignore` and a few
lessons appended to `CLAUDE_PCB.md`). `PLAN.md` is the full write-up; this response is the
decisions and why.

### 1. What the board is

A zero-IF quadrature receiver whose local oscillator is a 5.8 GHz synthesizer referenced to a
**voltage-controlled crystal oscillator**, and a quadrature modulator driven by four FPGA pins.
The Costas loop's error signal steers the VCXO, so the whole synthesizer (×232) is the loop's VCO.
With the loop locked, the demodulator's I output *is* the data and Q is the phase error; both go
through a differential amplifier to fast comparators and straight into the FPGA. The transmitter's
I and Q baseband inputs are 2-bit resistor ladders from the FPGA, so the constellation point changes
in a couple of nanoseconds.

The idea that makes PSK/QPSK/FSK fit QPV: **the carrier is on all the time**. While idle, the
transmitter sits at 0° and the receiver's loop (bandwidth 3 kHz) tracks it; a bit is a brief
departure from 0° that the loop does not even see:

| mode | idle | bit | what the FPGA sees | ambiguity |
|---|---|---|---|---|
| BPSK | 0° | 180° for the symbol time | the I comparator flips | the loop locks at 0° or 180°, so a *transition* is the bit |
| QPSK, 2 bits | (I +a, Q 0) | one of 45°, 135°, 225°, 315°, i.e. (±a, ±a) | the Q window comparator (\|Q\| > a/2) fires; sign(Q) is one bit, sign(I) the other | 4-fold, resolved once by a training symbol |
| FSK | 0° | the modulator steps round the circle at ±Δf | I and Q comparators toggle in quadrature; the order of the first two edges is the bit, the period a second bit (4-FSK) | none; ~5 ns at 100 MHz |

Same analog receiver for all three; the modes differ only in the TX pin patterns and the RX decode
logic. The textbook Costas multiplication sign(I)·Q is one analog switch (74LVC1G3157), kept so the
continuous-BPSK case also locks and so you can jumper between "Costas" and "plain PLL on Q" and
watch the difference.

### 2. The numbers (`sim/budget.py`, asserted; `build/budget.json`)

| quantity | value |
|---|---|
| TX at the SMA | +9.8 dBm (ADL5375 −4.5 dBm at this drive, ADL5611 +14.3 dB at 5.8 GHz: its headline 22 dB is at 1 GHz) |
| 10 m, 6 dBi antennas | RX −46 dBm, SNR 47 dB in 100 MHz; 1 km with 15 dBi dishes: −68 dBm, 25 dB. The PAs you plan are for the hill |
| comparator swing at 10 m | ±220 mV (ADL5380 ×1.95, THS4541 ×4); weakest decodable: −50 dBm at the antenna, 43 dB above the noise floor |
| **electronics latency** | **24.5 ns** pin to register (TX 8.5, RX 16.0); the two crossings of the PYNQ's 200 Ω header resistors are 8.8 ns of it |
| Costas loop | fn 3 kHz, ζ 0.7, R1 20 k, R2 750, C 100 nF C0G; pull-in 4 ms from 30 kHz, 0.4 s from 300 kHz; the VCXO reaches ±580 kHz, two TCXO-referenced transmitters differ by ≤ 29 kHz |
| MAX2871 loop filter | 80 kHz, 50°: 390 p, 6.8 n, 820 Ω, 2 k, 160 p (C0G); in-band floor ≈ −109 dBc/Hz |
| power | 1.2 A from 5 V (ADL5380 245 mA, ADL5375 203, two ADL5611 248, two MAX2871 ≤ 400); hottest LDO +47 °C |

### 3. One antenna or two

Simultaneous TX and RX on one antenna needs the local transmitter's leakage below the wanted signal
minus 10 dB *at the demodulator*, because nothing before it is frequency-selective, and the arm
filter rejects an offset Δf by only 10·2·log10(1+(Δf/100 MHz)²):

| TX/RX spacing | needed isolation at the port (10 m, +10 dBm TX) |
|---|---|
| 25 MHz | 65 dB |
| 200 MHz | 52 dB |
| 600 MHz (UNII vs ISM) | 34 dB |

A splitter gives 3 dB, a circulator ~20 dB (until the antenna's own −10 dB return eats it), two
patches side by side 30-40 dB. **FDD on one antenna does not work inside the ISM band**, so the board
has separate TX and RX SMAs. Two consolations: QPV is half duplex at the protocol level (the prover
cannot answer before the verifier has finished sending), so a one-antenna system is a *time-division*
switch whose turn-around only has to beat the prover's measurement time, not 10 ns: a $0.40 SKY13453
(~1 µs) may do, the HMC427A (10 ns) is overkill; that switch belongs outside this board, SMA to SMA,
so both arrangements can be tried. And the 100 MHz baseband that buys 10-ns-class latency means the
ISM band holds **one** link per direction, not six: three links from a central station need the
5.15-5.85 GHz UNII range (the parts cover 4.9-6 GHz) or 30 MHz arm filters at 70 MHz spacing (12 ns
slower). Every frequency is a register write.

### 4. PYNQ-Z2 or Brain-1

PYNQ-Z2 now: its 28 header pins through 200 Ω at 3.3 V cost 4.4 ns per crossing and limit nothing
else, and the GPSDO board's measured header geometry, socket and standoff scheme carry over. The
Brain-1 (Opal Kelly, XC7Z012S, three standard SYZYGY ports and one transceiver port) is the better
final platform: a SYZYGY standard port has 28 I/O at a chosen VIO with 8 LVDS pairs and no series
resistors, and its three ports are exactly a central station's three links. This board's 22 signals
fit a SYZYGY port, so that is a connector change for rev B, not a redesign.

### 5. Parts: chosen, why, rejected

Stock and prices: JLCPCB's parts API, 2026-10-09 00:36-01:11 PDT, cached with timestamps in
`tools/jlc_cache.json` (printouts in `build/stock_probe*.txt`); price at 10 pieces.

**Consigned** (JLCPCB has 6-8 pieces; Digi-Key/Mouser figures are aggregator snapshots because
Digi-Key refuses scripts: please confirm in a browser):

| part | JLCPCB | elsewhere | why | rejected |
|---|---|---|---|---|
| **ADL5380ACPZ-R7** IQ demodulator | C579152, 8, $23.6 | Newark 1746 ($7.6-12.4), ADI direct 2522, Rochester 1257, Richardson 450 | the only integrated 6 GHz IQ demodulator with 390 MHz DC-coupled buffered outputs at this price: exactly a Costas loop's phase detector | LTC5586 ($31-40, 3 in stock, 430 mA, has a DSA/VGA we do not need); LTC5594 ($48); HMC8193 passive IQ mixer ($75-125 plus baseband amplifiers); two mixers and a PCB hybrid (cheaper parts, worse balance, more layout risk) |
| **ADL5375-05ACPZ-R7** IQ modulator | C579150, 6, $16.0 | Digi-Key 2262 ($14.12), Mouser 726 ($14.31) | 750 MHz baseband, high-impedance inputs biased at 0.5 V that a resistor ladder from 3.3 V logic drives directly | HMC495 (3.5-7 GHz, unstocked); LTC5588-1 (unstocked); a bi-phase mixer modulator (BPSK only); ADL5375-15 (needs a level shifter) |
| **Johanson 5400BL15B0050001E** balun (legacy 5400BL15B050E) | C2837312, 0 | Digi-Key under the new number; Avnet 4000 of the K variant | the ADL5380's 5.8 GHz data are taken with it | single-ended drive (unbalanced at 5.8 GHz); TCW4-582+ (unstocked, $4.30) |

**Placed by JLCPCB** (deep stock unless noted):

| part | why | rejected |
|---|---|---|
| **MAX2871ETJ+T** ×2 (C7458627, 3175, $8.57): TX LO on the TCXO, RX LO on the VCXO | 23.5 MHz-6 GHz fundamental VCO (no doubler), 3.3 V, SPI with the ADF4351's register map (lots of existing code), differential open-collector outputs that feed the IQ chips directly, a second output for the LO monitor | ADF4355 ($37-48, 9 in stock, two supplies: the Syzygy board's part); LMX2572 ($11, 1741, 6.4 GHz, lower current: a good rev B alternative); LMX2592 ($31); HMC833 ($17, 113); ADF4351 (4.4 GHz max: cannot reach 5.8 GHz); MAX2870 (same chip, dearer) |
| **SX3V25.000** 25 MHz VCXO (C5179998, 418, $1.24) | pull ±100 ppm over 0.3-3.0 V, 15 kHz modulation bandwidth, CMOS out, 3225: the loop's VCO | a VCTCXO (±10 ppm, slower modulation); SiT3807 (unstocked); steering the synthesizer's fractional word digitally (writes glitch the VCO; no analog loop to learn from) |
| **TC32H4-25.000** TCXO ±2.5 ppm (C5119013, 498, $1.30): the TX reference | LVCMOS out (the MAX2871 wants ≥ 0.7 V p-p; clipped-sine TCXOs are marginal), same pads as the VCXO so either fits either position | TC80E (2949, $0.54: probably clipped sine); the VCXO itself (±50 ppm drift would eat the RX pull range) |
| **SKY65404-31** LNA (C210262, 1126, $0.73) | 1.0 dB NF, 13 dB, 4 external parts, 10 mA; absolute maximum input +1 dBm (never cable TX into RX) | QPL9547, BGA2869, SBB5089Z (unstocked or 3); HMC8410 ($30) |
| **PE43711B-Z** DSA (C470929, 1981, $3.44) | 0-31.75 dB in 0.25 dB, 9 kHz-6 GHz, serial on the shared SPI: keeps the demodulator in range and the Costas gain constant from 3 m to 3 km | HMC624A ($10-11); PE4312 (4 GHz); fixed pads (soldering to change range) |
| **ADL5611** ×2 (C208262, 3023, $5.21): RX before the demodulator, TX after the modulator | 14.3 dB at 5.8 GHz, 50 Ω in/out, SOT-89, one part number for both | SBB5089Z (3 in stock); a second SKY65404 as TX gain (+1 dBm input limit); the TOKMAS "ADL5611" clone ($1.26) |
| **THS4541** ×2 (C2058382, 427, $6.34), gain 4 on 3.3 V | 850 MHz GBW gives ~100 MHz; takes the demodulator's 3.2 V common mode through 1.2 k shunts at the summing nodes (the arithmetic caught that my first values put the nodes 20 mV from the input limit); on 3.3 V no node can exceed the comparators' rail | THS4522 (95 MHz); LMH6552 (17 in stock); ADA4932 ($17.5); no amplifier (±28 mV at 10 m: workable, no margin) |
| **TLV3601** ×3 (C2974371, 23776, $2.42) | 2.5 ns, rail-to-rail, push-pull 3.3 V output straight to the FPGA pin | ADCMP604 (LVDS: a receiver adds 1.7 ns and the Zynq's 3.3 V banks take no LVDS); ADCMP601 ($7.3, 3.5 ns); TLV3603 (adjustable hysteresis, 16 in stock) |
| **SN74LVC1G3157** (C38663, $0.08) as the Costas multiplier; **TS5A3159** (C46388) as the loop HOLD switch; **OPA2187** (C2863562, $1.92) zero-drift loop filter; **MCP4728** 4-ch DAC (C478093, $2.24: TX ladder references and carrier null, Q window threshold, VC offset); **ADS1115** 4-ch ADC (C37593, $1.06: I, Q averages, VC, loop error, so the FPGA can tell "locked" from "no signal") | each the cheapest well-stocked part that does the job | an analog multiplier (AD835, $15+); trimmers instead of the DAC; the PYNQ's XADC (it is on the Arduino header) |
| **TPS7A2033** ×4 (C2862740, $0.22: PLL TX, PLL RX, analog, digital), **LP5907** (C23380874, $0.14: the oscillators) | 10 µV / 6.5 µV rms, 65 dB PSRR; the PLL ones behind 2.2 Ω to share the heat (0.25 W each) | ADM7150 ($8-21, 1 µV: the Syzygy choice, overkill at ×232 where the MAX2871's own floor dominates) |
| **AO3401A** ×2 (Basic) ideal diodes on both 5 V inputs, 2 A PTCs, SMAJ5.0A, HRO USB-C (C165948), BWSMA-KWE-Z001 SMAs ×2, U.FL ×12, the GPSDO's 2x20 socket (C2977589, through-hole), PZ254V jumpers at their exact lengths | the earlier boards' known parts | a Schottky OR (350 mV the ADL53xx cannot spare); a barrel jack (12 V accidents) |
| 0402 C0G 1.5 pF (C1552, Preferred) as every 5.8 GHz DC block | series-resonant at 6.1 GHz with its 0.45 nH: a near-perfect block (the Syzygy review's 3.9 pF 0201 finding, redone for 0402) | 100 pF (+j20 Ω at 5.8 GHz) |

Not on the board, deliberately: a 5.8 GHz bandpass at the RX input (none stocked; an SMA filter in
the cable if needed), a log detector (I²+Q² from the ADC is the power once locked), an on-board
TX/RX switch (section 3), a bench barrel jack.

### 6. What exists now

* `PLAN.md` (the design), `README.md`, `QUESTIONS.md` (gitignored; answer in `ANSWERS.md`).
* `sim/budget.py` (nine sections of asserted arithmetic), `sim/rf_lines.py` (50 Ω CPWG on
  JLC04161H-7628: 0.29 mm with a 0.25 mm gap; λ/4 = 7.3 mm for the couplers).
* `gen/pins.py` (the header: 22 signals + 6 spares, clock-capable pairs for the comparators),
  `gen/parts.py` (76 part kinds, LCSC codes with the words their JLCPCB description must carry,
  the three consigned lines with distributor numbers), `gen/symbols.py` (14 drawn symbols, pins
  from the datasheet tables), `gen/footprints.py` (the LNA from JLCPCB's own land pattern, the
  balun from Johanson's drawing, the GPSDO's socket, the ECP5 board's SMA, the coupler as a
  net-tie footprint), `gen/library.py`, `gen/project.py` (net classes: RF, LO, Baseband, Power).
* `gen/schematic.py` + `sch_rx.py` / `sch_tx.py` / `sch_pwr.py` / `sch_blocks.py`: a root block
  diagram and three A2 sheets, 259 parts, 197 nets, **ERC 0 items**, every chip's supply pin with
  its own capacitor, notes at the nodes. `tools/net_check.py` walks nine signal paths end to end
  (RF chain, both arms, the loop through both op amps to the VCXO, both LOs, the 5 V path): all
  nine pass, no one-pin nets but no-connects.
* `gateware/pynq_z2.xdc` (from `gen/pins.py`) and `gateware/max2871_regs.py` (the six words for
  5800/5850 MHz, checked against the datasheet's own 6000 MHz example).
* `tools/`: `kienv.py`, `kisch.py` (the writer, now flattening KiCad's `extends` chains), the
  JLCPCB API, `sch_where.py` (what is drawn near a point), the checker with a wire-origin tracer.
* `build.py`: budget → library → project → schematic → ERC → net check → gateware → renders.
* Datasheets in `datasheets/` (gitignored): all 29 fetched (ADI with a browser user agent, TI,
  pSemi, Microchip, Skyworks, the LCSC-hosted oscillator and connector sheets, Johanson).
  **None blocks the design.** The TUL PYNQ-Z2 schematic would let me read the header's 5 V
  capacity rather than assume it (QUESTIONS.md item 6).

Not yet done, in order: the text-overlap pass on the sheets (the checker still lists about 190
label/note collisions, mostly capacitor designators beside each other; the structural checks are
clean), the board (`gen/placement.py`, `gen/board.py` on the GPiBridge/OWLternatingCurrent
pipeline: 120 × 90 mm, 4 layers, RX chain left, TX right, synthesizers between, power along the
bottom at the socket), DRC, the release with the consignment BOM, the silkscreen, the Verilog top.

### 7. If these came back and did not work

1. A synthesizer not locking at 5.8 GHz (registers, loop filter): the register words are checked
   against the datasheet's example, the filter comes from the script, and the MUX/LD pins and
   the LO MON jacks show it in minutes; both synthesizers are the same tile.
2. The Costas loop with the wrong sign: two 3-pin jumpers swap Q+/Q− into the multiplier.
3. Comparator inputs out of range: the FDA runs on 3.3 V, so it cannot exceed their rail.
4. The TX ladder levels off (my 200 Ω header assumption, 10 pF): Vr is a DAC channel.
5. Not enough signal: the budget uses the 5.8 GHz gains (14 dB, not 22); the DSA and the FDA's
   gain resistors give 30 dB of slack.
6. A JLCPCB rotation wrong on SOT-89/QFN/SC-70: predicted from EasyEDA drawings, listed for the
   preview, read before paying.
7. Consigned parts late: three lines, ordered the day the PCB is.

### 8. Questions (QUESTIONS.md)

1. Digi-Key or Mouser for the three consigned lines, and does Digi-Key show the ADL5380?
2. 5 PCBs, 2 assembled, as the ECP5 order?
3. May the campus tests use 5.15-5.85 GHz (UNII) as well as the ISM band?
4. What antennas do you have (gain, polarisation, connector)?
5. Do you want a footprint for an on-board SPDT between a third ANT SMA and the TX/RX paths, for
   the one-antenna time-division experiment, or an external switch module?

## Prompt 2

To test across the indoor lab, SKY13453 (~1 µs) is too slow. Another platform to test this on, other
than the PYNQ-Z2, would be the ECP5 Icepi Zero. I've done work with you on that in other PCBs. That has
no resistors, but I don't know if it can go as fast internally for this. Would this board also work on
the Icepi Zero? If minor modifications would allow it to work on both (probably paying closer attention
to which pins are clock pins), try to make it work for both.

Yes, at first 5 PCBs / 2 assembled.

Yes, campus tests will use 5.15-5.85 GHz (UNII) as well as ISM.

As for antennas, we have 4 of these. They are cheap, light, easy to use, and they work well in our
indoor tests. 24 dBi gain 40x30 cm rectangular aperture; buy the "with cable 10 m", Type N at the
antenna, SMA at the PCB (or amplifiers): https://www.aliexpress.us/item/2251832850920929.html

If we want a bigger one, we'd get a pair with dual polarization ("MIMO") and high gain, like this:
30 dBi gain 60 cm diameter 6 kg: https://www.aliexpress.us/item/3256811977245259.html

As for something like a switch, I'd either ask JLCPCB to solder it onto the board or I'd get an external
module. If it's smaller than an 0603 package, I'll have a hard time soldering it myself. The external
module is usually expensive and a pain to wire up and have dangling.

Digikey shows ADL5380ACPZ-R7 In-Stock: 4,527 for $17.96 up to 10.

In the $HOME/DroneSDR git repo, there is a directory with a markdown file where I took lots of notes,
eventually settling on the particular HMC switch and ADL5511 envelope detector. Find that markdown file
and see if anything in there is useful. It's old, so it might not represent my current understanding of
the problem.

Finally, I had a question about different ways of doing the protocol. One way to send a bit every so
often is to have what looks like a carrier and only occasionally flip the phase or change the frequency.
Another is to constantly be sending a whitening sequence, resulting from an LFSR type encoder being fed
zeros until the bit or pair of bits, and then being sent the bits. The timing recovery would be able to
lock onto the whitening sequence because of all of the transitions. For QPV's low latency radio comms,
for repeated trials, I don't have a sense for which is better: lower latency or more robust to typical
university noise in that band (down the hall for testing and between buildings outside). For all of
the schemes you described and these too, estimate the distance vs error rate for various price levels
of power amplifiers. (I have a cheap Aliexpress power amp and LNA, each of which is powered by USB-C
and seems to do pretty well, but we have not thoroughly tested it.) 1% and maybe even 5% errors can be
tolerated, but losing a measurement might bring us below the efficiency threshold that we need to close
various loopholes. Error correction is probably undesirable because of the added latency.

As usual, record this in the CLAUDE_CHAT.md and record your responses too.

*(Added while the second response was in progress:)* Keep going, but once you settle on a design, I
expect to see some clear block diagrams drawn, where you leave plenty of room so that you can annotate
signal levels, center frequency, bandwidths, DC offsets, and anything else of importance... and do it
for every arrow in the diagram. I'd like the major blocks to be in a big font so that I can understand
the overall structure at a glance, but I'm happy to open it and zoom in and scroll around to read the
details. This is better than having to look up lots of notes somewhere else. If there are little
illustrations or pictures of what the signals look like going down each arrow (in time and/or in
frequency), it's also nice to show those as little thumbnails associated with the arrows. This project
is also meant to educate my physics students and me on these things, so you should spend time making
the diagrams clear and pedagogical.

## Response 2 2026-10-09 03:10 - 04:10 PDT Claude Fable 5.1

Everything below is in the files; the chat is the summary.  `python3 build.py` runs clean: five sheets
(the antenna switch is new), ERC 0 items, net check 0 problems (278 parts, 214 nets), both constraint
files, the range model, the five block diagrams.  Nothing committed (your call; the changed paths are
listed at the end).

### 1. The Icepi Zero: yes, and the board now serves both

I joined the Icepi's header-to-ball map (`cheyao/icepi-zero` `gateware/icepi-zero.lpf`, whose
`gpio[BCM]` comments are header pin numbers) to Lattice's ECP5U-25 pinout CSV (both already in the
repository under ECP5-2ADC-2DAC) and put the result in `gen/pins.py` beside the Zynq column.

| | PYNQ-Z2 (Zynq) | Icepi Zero (ECP5 LFE5U-25F-6) |
|---|---|---|
| clock-capable header pins | 10, 11, 13, 18, 26, 31, 35, 40 (MRCC/SRCC) | 16, 18, 19, 21, 22, 26, 32 (PCLKT/C6_x, PCLKT/C7_1, GR_PCLK7_x) |
| on both | **18 and 26 only** | |
| series resistors | 200 Ω on every pin (4.4 ns per crossing) | none |
| sampling a 3.3 V input | ISERDES, up to 1.25 Gb/s | GDDRX2, 655.8 Mb/s in grade -6, left/right banks only (ours: 6 and 7; pins 35/37 are bank 0) |
| LVCMOS33 toggle | — | 150 MHz out, 200 MHz in: plenty, the pins carry events |
| electronics latency, pin to register | 24.1 ns | **15.3 ns** |
| 5 V on pins 2/4 | the PYNQ's barrel supply | USB VBUS: use this board's own USB-C |
| control | AXI-Lite + Jupyter | UART command set (no processor); same Verilog top |

So: `CMP_I` (the data) stays on 18, `TRIG_IN` moved from 16 to 26 (`LE_PLL_RX` took 16); the other
inputs are sampled, which is how they are read on both anyway.  `gateware/icepi_zero.lpf` is generated
beside the XDC with the same port names.  The missing 200 Ω shifts the ladder levels 9 % (0.167 / 0.521
/ 0.874 V instead of 0.17 / 0.50 / 0.83), which Vr (a DAC channel) re-centres; the three comparator
outputs now leave through 33 Ω as a source termination for the unterminated line (0.3 ns, the PYNQ's
200 Ω does not mind).  The Icepi ships without its header: fit a male vertical one, pin 1 in the Pi
corner, and the Icepi plugs onto this board's socket from above; section 7 of PLAN.md reserves the
65 × 30 mm it overhangs.  Is the ECP5 fast enough "internally"?  The timing resolution of the link is
the arm filter's 3.5 ns rise, not the sampler: 1.5 ns samples (ECP5) against 0.8 ns (Zynq) both resolve
it, and the ECP5 is 8.8 ns *faster* end to end for having no resistors.  PLAN.md section 12.

### 2. The switch: HMC536, 30 ns, on the board as its own three-SMA block

What the datasheets say (texts in `build/txt/`), after fetching ten of them:

| part | on/off | isolation at 5-6 GHz | power | control | price, stock (2026-10-09) | verdict |
|---|---|---|---|---|---|---|
| SKY13453 | 1 µs | 38 dB | +30 dBm | 3.3 V | $0.40, JLCPCB | 15 round trips of the lab: your objection stands |
| HMC8038 | 150 ns (170 ns settled) | 60 dB | **+36 dBm** | 3.3 V | $8.6, 282 at JLCPCB | the right switch for campus distances with a PA; useless in the lab |
| HMC849A | 150 ns | 50 dB | +33 dBm (5 V) | 3-5 V | $9, 0 at JLCPCB | same class |
| ADRF5019 | 150 ns | 45 dB | +39 dBm | needs −2.5 V | $9 | same class, worse |
| PE42423 / PE42422 | 500 ns / 2 µs | 43 / 15 dB | | 3.3 V | | no |
| SKY13350 | 45 ns | 20 dB | | 3 V | discontinued | no |
| **HMC536MS8G** | **30 ns (15 ns rise)** | 27 dB (32 typ.) | +29 dBm (0.1 dB) | **0 / 3.3 V from the FPGA, no supply pin** | **$9.91, 5 at JLCPCB** (Digi-Key 0 until 2027-01) | **chosen** |
| HMC427A | 10 ns (2 ns rise) | 40-45 dB | +26 dBm | +5 V complementary (two translators) | $62-75, 389 at Digi-Key | the upgrade if 30 ns ever matters |
| ADRF5020 | 10 ns | 60 dB | +28 dBm | needs −2.5 V | $41-75, 0 at JLCPCB | no |

Every switch with an integrated driver on a single positive supply is 150 ns or worse; the 10 ns ones
are GaAs with controls at the supply rail or SOI with a negative rail.  The HMC536 is GaAs with its
control circuitry on chip: the FPGA pin drives it directly, it has no supply pin at all, and it is an
MSOP-8 with a paddle, which you can hand-solder (it is JLCPCB-placed anyway).  Its 27 dB isolation is
enough for time division (the receiver is not listening while we transmit; our own +9.8 dBm leaks
−17 dBm into the RX jack, 0 dBm with a +27 dBm PA, so a PA with the switch wants the VLM-63-2W-S+
limiter from your notes ahead of the LNA) and useless for sharing an antenna in frequency, which the
first response already ruled out.  30 ns is 4 m of round trip: in the lab it is a fixed, calibrated
30 ns on the prover's answer, and the verifier is back in receive long before the reply (67 ns at
10 m).  JLCPCB's five pieces are the only source until January: say the word and I keep two on the
BOM for the two assembled boards.

The fifth sheet (`gen/sch_ant.py`, `hardware/ant.kicad_sch`) is self-contained: ANT, SW TX and SW RX
jacks, the switch, 1.5 pF blocks on all three RF pins (its datasheet), 100 Ω in each control line
(its evaluation board), a pull-up on A and a pull-down on B so it rests in receive, `TR_A`/`TR_B` from
header pins 27/28 (also on J303 for an external module), a test point on A.  You cable TX ANT → SW TX
and SW RX → RX ANT with two short leads (1 ns) when you want one antenna, and leave the block out of the
RF path when you want two.  I verified the pinout from the datasheet's pin figure (rendered as an image),
not the text table, which only says "3, 5, 8: RFC, RF1, RF2".

One thing the one-antenna mode needs that nobody had said: with time division the far loop sees our
carrier only while we transmit, so it HOLDs meanwhile (`LOOP_HOLD`, which the board had), **and our
reply carrier must already be on its frequency**, or its loop would need ~100 µs to re-acquire.  The
fix is a transponder: run the prover's TX synthesizer from the VCXO its Costas loop steers.  The RX
sheet now has a **REF OUT** U.FL (the VCXO's 25 MHz through a 74LVC1G17 and 33 Ω); a lead to the TX
sheet's REF IN with JP201 set to REF IN makes the two carriers coherent.  The verifier keeps its carrier
on between trials and is the master clock of the whole link.  Two antennas and two frequencies (the
default) need none of this: both carriers always on, both loops always locked, no turnaround.

### 3. Your DroneSDR notes (`pointToPointRF/README.md`, 2025)

Found.  They reach the same switch conclusion for the OOK link (HMC427A, with the −5 V / level-shifter
pain of the HMC270 and HMC547 behind it) and choose the ADL5511 detector.  What carries over here: the
limiter (VLM-63-2W-S+) ahead of a detector or LNA whenever a PA is in play; DC blocks on every GaAs
switch port; "don't buy a no-name terminator"; the ADCMP604 LVDS comparator idea (rejected on this board
because the Zynq's 3.3 V banks take no LVDS and the Icepi's header banks are 3.3 V too).  Their CDR and
BERT survey is the whitened-stream world of section 5 below, and their FSK remark ("not appropriate
above 20-30 Mbps because of VCO settling") does not apply here: this board's FSK is four phase steps of
the ladder, not a VCO.  The rest (eval boards, ADI-BERT, fibre, VTX) is history.  Nothing in them
changes the design.

### 4. Antennas and the numbers (sim/budget.py section 2, updated)

Four 24 dBi 40 × 30 cm panels with 10 m cables (N at the panel, SMA at the board), the 30 dBi 60 cm
dual-polarised dishes as the big option, 2 dBi stubs on the bench.  A 10 m cable at 5.8 GHz is 5 dB of
LMR-200 (12 dB of RG-58): the amplifier belongs at the panel, with the cable on its low-loss side.

| link | RX | SNR in 100 MHz |
|---|---|---|
| 10 m, stubs | −54 dBm | 39 dB |
| 30 m, stubs | −63 dBm | 29 dB |
| 300 m, panels, 10 m cables, no amplifier | −49 dBm | 43 dB |
| 3 km, panels, 10 m cables / amplifiers at the panel | −69 / −59 dBm | 23 / 33 dB |
| 20 km, panels, amplifiers at the panel, no PA | −76 dBm | 17 dB |
| 20 km, dishes | −64 dBm | 29 dB |

Side effect worth a decision: at 10 m with stubs the comparators see ±88 mV, below the 100 mV they
want for a clean decision (the first response assumed 6 dBi antennas).  Gain 8 on the THS4541 (one
feedback resistor, 8 k instead of 4 k; the budget's section 7 allows it) or the first tests at 3 m.

### 5. Idle carrier against a whitened stream

`sim/link_rates.py`, PLAN.md section 13, `docs/images/block_modulations.svg`.  The comparator sees I
(or Q) plus Gaussian noise in the 100 MHz arm; each scheme's decision error is the textbook function of
that SNR (BPSK Q(√2·snr), QPSK Q(√snr) per bit, FSK decided from the rotation direction ½e^(−snr/2),
OOK on an envelope detector with 500 MHz of noise ½e^(−snr/4) at 7 dB less SNR, the whitened stream
3 × BPSK for a self-synchronising descrambler).  **The threshold that matters is not your 1 %.**  A
receiver that listens always decides always, and every false decision is a bit nobody sent: to keep
false events to 1 in 100 trials at a 1 MHz trial rate the link must be *quiet*, ≤ 1e-4 per decision,
which costs BPSK 8.4 dB instead of 4.3.  (The gateware's dwell requirement, N samples before a flip
counts, buys quiet with latency.)

| scheme | 5 % wrong | 1 % wrong | quiet (1e-4 per decision) | lab, stubs, no amp: quiet to | campus, panels, amps at the panel, no PA |
|---|---|---|---|---|---|
| BPSK | 1.3 dB | 4.3 dB | 8.4 dB | 103 m | 24.3 km |
| QPSK | 4.3 dB | 7.3 dB | 11.4 dB | 73 m | 17.2 km |
| FSK | 6.6 dB | 8.9 dB | 12.3 dB | 65 m | 15.5 km |
| OOK | 16.6 dB | 18.9 dB | 22.3 dB | 21 m | 4.9 km |
| whitened | 3.5 dB | 5.7 dB | 9.0 dB | 96 m | 22.7 km |

Comparison of the two protocols on the same hardware (the FPGA drives the ladders either way):

* **Latency:** the stream waits for the next slot (5 ns average) and integrates a whole symbol (10 ns)
  before it can decide: **+13 ns**.  The idle carrier adds nothing beyond the 3.5 ns filter rise that
  is already in the 24 ns.
* **Sensitivity:** the same.  The arm filter already is a one-symbol matched filter, so integrating a
  10 ns symbol gains nothing; the self-synchronising descrambler then *triples* the errors (an additive
  scrambler with frame sync does not, but loses a frame when sync slips).
* **False events:** the same mechanism in both, and the stream makes 1e8 decisions a second whether or
  not anything was sent, so it is no quieter.
* **University-band interference:** whitening gives no spreading gain (chips = bits), and the stream is
  200 MHz wide all the time, so *we* become the interferer of every WiFi channel we overlap.  Robustness
  comes from the arm bandwidth (narrower = quieter = slower), the panels' directivity (20-30 dB
  off-axis), the channel (scan with the B210 first; UNII-2C 5.47-5.725 GHz is nearly empty indoors)
  and power.  The Costas loop itself does not care: in its 3 kHz a 20 MHz WiFi signal at −40 dBm is
  −118 dBm.
* **Where the stream wins:** a conventional slotted receiver that needs a clock (an SDR, a BERT), and a
  continuous link-quality estimate.  It is an experiment on this hardware, not a design decision.
* **Regulatory footnote:** §15.247 wants a digital transmitter ≥ 500 kHz wide; a bare idle carrier at
  +10 dBm is a §15.249 question (about −1 dBm EIRP CW in the ISM band).  The 5 cm amateur band
  (5.65-5.925 GHz) allows any mode and the PAs; otherwise the stream, or a slow dither of the carrier,
  is the compliant shape outdoors.

### 6. Distance against error rate, by amplifier

Range at which BPSK stays quiet (1e-4 per decision), with the old OOK link in brackets; free space plus
a margin (10 dB indoors, 6 dB outdoors); the USB-C amplifier is bracketed at +20 and +27 dBm until you
measure it (TX MON and the ADC read it):

| scenario | board alone | USB-C amp, if +20 dBm | USB-C amp, if +27 dBm | 2 W booster (+33) | 10 W amplifier (+40) |
|---|---|---|---|---|---|
| lab: 2 dBi stubs, no cables | 103 m (21 m) | 332 m (67 m) | 744 m (150 m) | 1.5 km (299 m) | 3.3 km (669 m) |
| campus: panels, 10 m cables, amplifiers at the board | 4.6 km (924 m) | 14.8 km (3.0 km) | 33.2 km (6.7 km) | 66.3 km (13.4 km) | >100 km (29.9 km) |
| campus: panels, PA and LNA at the panel | 24.3 km (4.9 km) | 78.8 km (15.9 km) | >100 km (35.5 km) | >100 km (70.9 km) | >100 km (>100 km) |
| mountain: 30 dBi dishes, PA and LNA at the dish | 96.9 km (19.5 km) | >100 km (63.2 km) | >100 km (>100 km) | >100 km (>100 km) | >100 km (>100 km) |

Through walls at 30 m with stubs and no amplifier there are 11 dB to spare: two drywalls, not a floor.
With the panels and no PA at all the board stays quiet to 24 km (15 km with the 10 m cables and the
amplifiers at the board); the campus is limited by line of sight long before this.  **Power is not the
limit of this link; line of sight and interference are**, and the PA tiers matter against obstructed
paths and the OOK comparison.  At 1 % message errors (your tolerance) multiply the BPSK distances by
1.6; at 5 % by 2.3.

### 7. The block diagrams (`docs/images/block_*.svg`, made by `docs/blockdiagram.py`)

Big block titles, every arrow with a box (level in dBm and mV, centre frequency, bandwidth, DC level
or common mode) and a thumbnail of the signal in time or frequency, a "how to read this" paragraph for
the students, and the numbers pulled from `build/budget.json` and `build/link_rates.json` at build
time so they cannot drift from the design.  Open the SVG in a browser and zoom; the PNGs are for a
glance.

* `block_system`: the two stations, the air (path loss, flight time), the round trip in nanoseconds as
  a bar, the three antenna arrangements, what frequency multiplexing buys.
* `block_rx`: antenna → LNA → DSA → gain block → ADL5380 → arm amplifiers → comparators → FPGA, with the
  synthesizer, VCXO and the Costas loop underneath (S-curve, settling, VC pulling in).
* `block_tx`: FPGA pins → ladders (the three DC levels) → ADL5375 → gain block → pad and coupler → SMA,
  with the TCXO and synthesizer, and the constellation with the points each scheme uses.
* `block_loop`: the Costas loop as a control system (K_d, F(s), K_o, ω_n, ζ) with the S-curve, the
  step response and the closed-loop Bode plot, and why a plain PLL would lose lock on BPSK.
* `block_modulations`: five rows (BPSK, QPSK, FSK, OOK, whitened stream) × what the transmitter does,
  the constellation path, RF in time, I and Q at the receiver, the comparators, the spectrum, the SNR
  each needs and how far it reaches; the protocol comparison and the range table under it.

### 8. State, and what could still bite

Done since Response 1: the Icepi column and LPF; the switch sheet; REF OUT; 33 Ω on the comparator
outputs; the budget's antenna, cable, switch and Icepi sections; `sim/link_rates.py`; the diagrams;
PLAN.md sections 11-14 and the header table; the ADL5380's Digi-Key figure in `gen/parts.py`.  Not
done: the ~200 cosmetic text overlaps on the sheets, the board (placement, copper, release, silkscreen),
the Verilog top, the consignment BOM.  Dead-on-arrival candidates added by this response: the HMC536
pin order (checked against the pin figure, not the table); the transponder mode's behaviour when both
ends are in receive with nobody transmitting (both loops hold; the protocol must keep the verifier's
carrier on between trials); the REF OUT lead's 3.3 V CMOS into REF IN (same as the TCXO's drive today);
the switch resting state behind the PYNQ's 2k2 pull-ups (both controls high until the gateware drives
them: undefined path, no damage).

Open questions (also PLAN.md section 11, QUESTIONS.md): gain 8 or 3 m for the bench; fit the HMC536 on
both boards; the USB-C PA/LNA model numbers; the campus channel scan and whether you hold an amateur
licence.

Changed paths (nothing committed): `CostasLink-PYNQ-Z2/` (gen/pins.py, parts.py, symbols.py,
sch_ant.py, sch_rx.py, sch_pwr.py, schematic.py; sim/budget.py, sim/link_rates.py;
gateware/gen_xdc.py → pynq_z2.xdc, icepi_zero.lpf; docs/blockdiagram.py → docs/images/block_*;
hardware/*.kicad_sch; PLAN.md, README.md, QUESTIONS.md, this file).  Four switch datasheet PDFs that
a shell reset dropped at the repository root were moved under `datasheets/` (ignored).

## Prompt 3

What does "panels, amps at the panel" mean? What is a panel here? What is a "stub" in your reply? You gave
distance numbers for things like with and without the PA. Do a side by side table for OOK and all of the
schemes here. What are the advantages and disadvantages of each scheme?

Put all of the diagrams' numbers on the schematic too, such that looking at the schematic, one can instantly
see what the levels, DC offset, frequency, and bandwidth are at every wire or pair of wires.

Is the Brain-1 able to go any faster (lower latency) than the Icepi Zero? I don't believe either have
resistors between the FPGA and their connector.

I don't have an amateur licence: W3JQ ("Whiskey 3 Jason Quantum"). Unless I'm remembering that incorrectly.

I don't know what "THS4541 gain 8 or test at 3 m?" means. Is this a choice of something that affects what's
soldered on the PCB?

## Response 3 2026-10-09 07:28 - 07:55 PDT Claude Fable 5.1

### Words

* **Panel** = your 24 dBi 40 × 30 cm flat-panel antenna (patches behind a radome, N connector, an 8-10°
  beam). **Dish** = the 30 dBi 60 cm one. **Whip** (I wrote "stub", a poor word) = a 2 dBi quarter-wave
  stick screwed straight onto the board's SMA: the bench antenna. Renamed everywhere.
* **Amplifiers at the panel** = the external PA and LNA mounted at the antenna's N connector, so the 10 m
  cable carries the PA's output on one side and the LNA's output on the other and its 5 dB costs nothing.
  **Amplifiers at the board** = the same boxes at the SMA end, so the cable's 5 dB comes off the transmit
  power and adds to the noise figure. The scenario column of the tables says which.

### Side by side: every scheme, every scenario, every amplifier

The threshold that matters for a listen-always link is *quiet* (≤ 1e-4 false decisions per decision; the
1 % and 5 % blocks are in `build/link_rates.md` and PLAN.md §13; at 1 % multiply BPSK by 1.6, at 5 % by
2.3). Board alone = +9.8 dBm; the USB-C amplifier is bracketed until you measure it.

**Range, quiet (1e-4)** (metres unless km; free space plus margin; '-' below 1 m)

| scenario | amplifier | BPSK | QPSK | FSK | OOK | whitened |
|---|---|---|---|---|---|---|
| lab: 2 dBi whips on the SMAs, no cables | board alone ($0) | 103 m | 73 m | 65 m | 21 m | 96 m |
| lab: 2 dBi whips on the SMAs, no cables | USB-C amp, if +20 dBm ($15-30) | 332 m | 235 m | 212 m | 67 m | 310 m |
| lab: 2 dBi whips on the SMAs, no cables | USB-C amp, if +27 dBm ($15-30) | 744 m | 526 m | 474 m | 150 m | 694 m |
| lab: 2 dBi whips on the SMAs, no cables | 2 W booster (+33) ($40-80) | 1.5 km | 1.0 km | 945 m | 299 m | 1.4 km |
| lab: 2 dBi whips on the SMAs, no cables | 10 W amplifier (+40) ($300+) | 3.3 km | 2.3 km | 2.1 km | 669 m | 3.1 km |
| campus: panels, 10 m cables, amplifiers at the board | board alone ($0) | 4.6 km | 3.2 km | 2.9 km | 924 m | 4.3 km |
| campus: panels, 10 m cables, amplifiers at the board | USB-C amp, if +20 dBm ($15-30) | 14.8 km | 10.5 km | 9.5 km | 3.0 km | 13.8 km |
| campus: panels, 10 m cables, amplifiers at the board | USB-C amp, if +27 dBm ($15-30) | 33.2 km | 23.5 km | 21.2 km | 6.7 km | 31.0 km |
| campus: panels, 10 m cables, amplifiers at the board | 2 W booster (+33) ($40-80) | 66.3 km | 46.9 km | 42.2 km | 13.4 km | 61.8 km |
| campus: panels, 10 m cables, amplifiers at the board | 10 W amplifier (+40) ($300+) | >100 km | >100 km | 94.5 km | 29.9 km | >100 km |
| campus: panels, PA and LNA at the panel | board alone ($0) | 24.3 km | 17.2 km | 15.5 km | 4.9 km | 22.7 km |
| campus: panels, PA and LNA at the panel | USB-C amp, if +20 dBm ($15-30) | 78.8 km | 55.7 km | 50.2 km | 15.9 km | 73.5 km |
| campus: panels, PA and LNA at the panel | USB-C amp, if +27 dBm ($15-30) | >100 km | >100 km | >100 km | 35.5 km | >100 km |
| campus: panels, PA and LNA at the panel | 2 W booster (+33) ($40-80) | >100 km | >100 km | >100 km | 70.9 km | >100 km |
| campus: panels, PA and LNA at the panel | 10 W amplifier (+40) ($300+) | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | board alone ($0) | 96.9 km | 68.5 km | 61.7 km | 19.5 km | 90.4 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | USB-C amp, if +20 dBm ($15-30) | >100 km | >100 km | >100 km | 63.2 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | USB-C amp, if +27 dBm ($15-30) | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 2 W booster (+33) ($40-80) | >100 km | >100 km | >100 km | >100 km | >100 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | 10 W amplifier (+40) ($300+) | >100 km | >100 km | >100 km | >100 km | >100 km |


| scheme | for | against |
|---|---|---|
| **BPSK** (idle carrier; a 180° flip is the bit) | the lowest SNR of all (8.4 dB quiet); one comparator, sign(I); no amplitude threshold; the textbook Costas case; the longest reach | one bit per event (two bits = two flips, +10 ns); the 0°/180° lock ambiguity, so a *transition* is the bit and the idle level is learned after lock |
| **QPSK** (one of four points at ±45°/±135°) | two bits in one event: the second bit lands 10 ns sooner than BPSK's; same hardware | 3 dB more SNR per bit (11.4 dB quiet); the Q-window threshold V_T to set (a DAC value); two more comparators; a 4-fold ambiguity resolved once per session by a training symbol |
| **FSK** (the phase steps round the four points at ±Δf) | the bit is the *direction* of rotation: no phase reference needed, survives a loop not quite locked, immune to the 180° ambiguity | 4 dB more SNR than BPSK (a noncoherent decision); the symbol is a whole rotation, 20-40 ns: the slowest to decode; edge-order logic on two comparators |
| **OOK** (carrier off/on into an envelope detector: the old board) | the cheapest receiver: no loop, no LO, nothing to lock | 14 dB worse than BPSK (noncoherent, and its noise bandwidth is the whole 500 MHz since nothing is frequency selective); no rejection of anything in the band, so WiFi is a false bit; an amplitude threshold to keep; idle = no carrier = nothing to track |
| **whitened stream** (continuous 100 Mbaud BPSK through an LFSR; the bit XORed in) | a symbol clock and a continuous quality estimate; the compliant spectral shape for §15.247; what an SDR or BERT expects | +13 ns (slot wait + full-symbol filter); 3 × the errors, or frame sync to lose; 200 MHz wide all the time, interfering with everything it overlaps; no spreading gain, no sensitivity gain |

Lowest latency and longest reach are the same choice: BPSK on an idle carrier; QPSK lands two bits at
once for 3 dB; FSK is the fallback if the loop will not hold; OOK is the comparison.

### The numbers on the schematic

Done: every signal wire or pair on all five sheets now has a **blue box** (yellow stays for explanation)
stating *frequency | level (dBm and mV p-p) | bandwidth | DC offset or common mode* for the bench link
(10 m, whips, DSA at 0 dB), with the 300 m panel figure where it matters: RX ANT, after the LNA, after
the DSA, into the demodulator, the LO pair, the I/Q pairs out of the demodulator, I_P/I_N and Q_P/Q_N
at the comparators, CMP_I, CMP_QP/QN, ERR, VC (with V_MID), VC_OFF, the DAC and ADC lines, the 25 MHz
references, REF OUT, the LO monitors; the FPGA bits, the ladder node (its three DC levels), the bias,
VR_I/VR_Q, the modulator's output, the gain block's output, TX ANT, TX MON, the triggers; ANT, SW TX,
SW RX, TR_A/TR_B; every rail with its current. The strings are made by one new module, `gen/levels.py`,
from `build/budget.json`, and `docs/blockdiagram.py` reads the same file, so the sheets, the diagrams
and the plan cannot disagree. Each sheet's header says so (the legend). The overlap checker, filtered
to the blue boxes, is clean; the sheets' other cosmetic overlaps are unchanged (~215). Found on the way:
a crash in the schematic generator exited with the same code as "overlaps reported" and the build went
on with stale sheets; it now exits 2 and the build stops.

### Brain-1 against Icepi Zero

Neither has series resistors: the SYZYGY standard connects the FPGA pins straight to the connector (the
SmartVIO resistors live on the pod in the DNA circuit, not in series with I/O). I have not seen the
Brain-1's own schematic (Opal Kelly publishes it on Aligni); drop it in `datasheets/` and I will check.
So both save the PYNQ-Z2's 8.8 ns. Between them: the XC7Z012S-1 samples a pin through ISERDES at up to
1.25 Gb/s (0.8 ns steps, IBUF about 1 ns); the LFE5U-25F-6 through GDDRX2 at 655.8 Mb/s (1.5 ns steps,
about 1.5 ns in). Average sampling latency is half a step, 0.4 against 0.75 ns, and the Artix fabric runs
the decoder faster. **The Brain-1 is about 1 ns ahead of the Icepi; both are about 9 ns ahead of the
PYNQ-Z2**; the arm filter's 3.5 ns rise is the real floor. The Brain-1's larger prize is what its SYZYGY
VIO allows: at 2.5 V its banks take true LVDS, so a rev B could use an LVDS comparator (TI TLV3604,
0.8 ns, or ADCMP604, 1.5 ns) instead of the TLV3601 (2.5 ns) and carry each comparator as an LVDS pair
through the connector: roughly 2 ns more and cleaner edges. The Icepi's header banks are 3.3 V
single-ended, so the TLV3601 stays there.

### The licence

Your sentence says both "I don't have" and gives a callsign, so I take it that you hold (or held) one as
W3JQ. A quick web lookup found no record for W3JQ; confirm it in the FCC ULS (wireless2.fcc.gov, amateur
licence search) before the first outdoor PA test. What it buys: with any class of licence (Technician has
full privileges above 50 MHz) the 5 cm band, 5.65-5.925 GHz, which contains ISM 5.725-5.875, allows the
PAs, the panels and any emission type, where Part 15 would not allow a bare +10 dBm carrier behind 24 dBi
antennas. Two rules bite: identify every 10 minutes (CW is always acceptable, so the gateware gets a
keyer that sends the callsign in Morse by switching the carrier; added to PLAN.md §8), and no messages
encoded to obscure their meaning (random measurement bits are the content, not a cipher; a scrambler
with a published polynomial is fine). Recorded as unverified in PLAN.md §11.

### "THS4541 gain 8 or test at 3 m"

My question was badly put, and it is withdrawn. The two arm amplifiers (THS4541) have a gain set by two
0402 resistors each (R_f 4.02 k / R_g 1 k = 4), soldered by JLCPCB. In Response 1 the bench link was
figured with 6 dBi antennas; with 2 dBi whips at 10 m the comparators see ±88 mV instead of ±220, and I
had set myself a rule of thumb of 100 mV (10 × the comparators' 10 mV of offset + hysteresis). 88 mV is
8.8 ×: fine. Doubling the gain (R_f 8 k) would double the level but halve the arm bandwidth (+3.5 ns of
latency), so the gain stays 4 and nothing changes on the board; with the panels the level is ±150 mV at
300 m anyway.

Changed this response: `gen/levels.py` (new), `gen/sch_util.py` (sig), all five sheet scripts,
`sim/budget.py` (rails, whip, chain levels), `sim/link_rates.py` (whip; writes `build/link_rates.md`),
`docs/blockdiagram.py` (whip), `gen/schematic.py` (exit 2 on a crash), PLAN.md §3/§8/§11/§13, README.md,
this file; `CLAUDE_PCB.md` got the "every wire states what is on it" lesson. Build: ERC 0, net check 0.
Nothing committed.

## Prompt 4

For the whitened stream, explain the "+13 ns; ×3 errors or frame sync" more here in the chat. The
Zynq-7012S's "1.25 Gb/s" is for the transceivers on the single TXRX SYZYGY connector or for the regular IO
pins on most of the SYZYGY connectors?

No, I *do* have the licence... unless it has expired.

## Response 4 2026-10-09 07:58 - 08:08 PDT Claude Fable 5.1

**+13 ns.** Two parts, both from the stream having a symbol clock. (1) *The slot:* at 100 Mbaud a symbol
starts every 10 ns; the bit arrives at the FPGA pin at a random moment and can only be put into the
next symbol, so it waits 0-10 ns, 5 ns on average. The idle carrier has no slots: the phase flips the
instant the pin moves. (2) *The decision:* a synchronous receiver integrates the whole 10 ns symbol
(the matched filter) and decides at its end; the idle-carrier comparator decides as soon as the 100 MHz
arm filter has carried I through zero, 1.7 ns after the flip arrives (the 2-pole filter's 50 % point;
90 % at 3.5 ns). Difference: 5 + (10 − 1.7) ≈ 13 ns on average, 18 ns worst case (just missed a slot).
Nothing else in the stream adds latency once it is locked: the descrambler is a pair of XORs and the
clock recovery runs in parallel. Honest footnote: a true integrate-and-dump has a noise bandwidth of
1/(2T) = 50 MHz against the arm filter's ~110 MHz, about 3 dB better per decision, which the model
ignores; the idle carrier buys the same 3 dB by setting the arm filter to 50 MHz for +3.5 ns, so it is a
knob both have.

**×3 errors or frame sync.** The whitening needs a scrambler, and there are two kinds. A
*self-synchronising* (multiplicative) scrambler sends y[n] = x[n] ⊕ y[n−a] ⊕ y[n−b], feeding back its
own *output*; the receiver undoes it with x[n] = y[n] ⊕ y[n−a] ⊕ y[n−b] on the *received* symbols. It
needs no synchronisation at all (after a+b symbols the receiver's shift register holds the same thing
the transmitter's did), which is why Ethernet and V.27-type modems use it; but every received symbol
is used three times, as y[n] and later as y[n−a] and y[n−b], so one channel error becomes **three**
output errors ("error multiplication", one plus the number of taps). An *additive* (frame-synchronous)
scrambler XORs the data with a free-running LFSR sequence and the receiver XORs it with an identical
LFSR: one error stays one error, but the receiver's LFSR must be in the same state as the transmitter's,
which needs **frame sync** (a preamble or a sync-word search at start-up), and a single slipped symbol,
from a timing-recovery hiccup, makes every following bit wrong (50 % errors) until the sync is found
again, typically after a sync word some microseconds later. For QPV, where every decision in idle time
is a potential false bit, ×3 means 3e4 false events a second at 1e-4 per decision; a slip means a burst
of them. Idle-carrier BPSK has no scrambler: a flip is a flip, one error is one error, there is nothing
to synchronise.

**The 1.25 Gb/s.** Regular I/O, not the transceivers, but with a caveat I should have made: it is the
ISERDES rate on the HR banks *with an LVDS input* (DS187, −1 speed grade). A 3.3 V LVCMOS single-ended
pin, which is what the comparators drive, is limited by its buffer to roughly half that, the same class
as the ECP5's 655.8 Mb/s. So on 3.3 V single-ended pins the Brain-1 and the Icepi are equals; the
Brain-1 pulls ahead only if its SYZYGY VIO is set to 2.5 V and the comparators go LVDS (then the
1.25 Gb/s applies, and a 0.8 ns LVDS comparator is available). The transceivers are the GTPs on the one
TXR port, 6.25 Gb/s serial lanes with clock recovery and AC coupling: no use for a comparator's edge.
PLAN.md §3 corrected.

**The licence.** Recorded: you hold it, callsign W3JQ. The quick web lookup found nothing, so the one
thing to check in the FCC ULS is the expiry date (ten-year term; in the two-year grace period after it
one may renew but not transmit). PLAN.md §11 updated.

## Prompt 5

What do you mean by "100 MHz arm filter"? Specifically, what is meant by "arm" here? Do you mean I arm vs
Q arm? Or something else.

With respect to "but the idle carrier buys the same 3 dB by setting the arm filter to 50 MHz for +3.5 ns.
It's a knob both have, not a property of the stream.", how much does it cost in terms of complexity to
actually make this adjustable? (Or to have two paths, one to really push latency and one to really push
distance?)

FCC site says: Call Sign: W3JQ, Previous Call Sign: KB9ZZU, Licensee ID: L00381553, Grant Date:
05/05/2020, Expiration Date: 05/05/2030, Certifier: Jason R Gallicchio, Registrant: Jason R Gallicchio,
301 Platt Blvd, Claremont, CA 91711. The address is Harvey Mudd physics department, so I'm good for a few
more years.

## Response 5 2026-10-09 08:10 - 08:20 PDT Claude Fable 5.1

**"Arm."** Yes: the I arm and the Q arm, the two baseband paths out of the quadrature demodulator,
each from one differential output pair of the ADL5380 through its THS4541 amplifier to its
comparator(s) (the I arm feeds the sign(I) comparator and the Costas switch's select; the Q arm feeds
the two window comparators and the Costas switch's signal). There is no filter *part* in either: the
"100 MHz arm filter" is the THS4541's closed-loop bandwidth, 850 MHz of gain-bandwidth over the noise
gain of 8.3 that the 4.02 k / 1 k / 1.2 k network sets (102 MHz, `sim/budget.py` section 7), behind the
demodulator's own 390 MHz; the budget models it as two poles at 100 MHz. The comparators (325 MHz) add
nothing. So "set the arm filter to 50 MHz" means a capacitor across each feedback resistor: 0.8 pF
across 4.02 k, four 0402 positions in all, which change both arms and the loop's Q path together.

**Making it adjustable, by cost.**

| way | what it costs | what you get |
|---|---|---|
| **gateware dwell** (free, already in the plan) | a register: a flip counts only if it persists N samples | averaging the comparator's 1-bit samples over 10 ns is a 50 MHz filter minus the 1.96 dB that hard limiting costs (2/π); set from software per trial; latency = N samples |
| **four DNP feedback capacitors** | four 0402 pads, nothing fitted; a soldering iron to change | the real analogue 50 MHz (or 25 MHz with 1.6 pF): the full 3 dB, +3.5 ns, both arms and the loop at once; not changeable at run time |
| **two paths at once** | three more TLV3601 ($7), six RC parts, spare header pins 33, 37, 40 (37 is bank 0 on the Icepi: fine for the slow path), a sheet change | the fast path unchanged (3.5 ns); a slow path through an RC (50 MHz or below) on its own comparators; the gateware reports the fast flag at once and lets the slow decision confirm or veto it ~10 ns later, so a false alarm becomes a *discarded* trial instead of a *wrong* bit, which is exactly your efficiency-versus-error distinction |

An analogue switch to change the capacitor at run time is the one thing I would not do: a switch good
enough not to spoil a 100 MHz path (6 Ω, 10 pF) spoils it. The first two are in (the capacitors are a
generator change I will make when you say so, or at the next pass); the third is offered, not drawn:
say the word and the slow trio goes on pins 33/37/40.

**The licence.** Settled: W3JQ, granted 2020-05-05, expires 2030-05-05. The 5 cm band is open to the
PAs and the panels; the gateware keys W3JQ in Morse every ten minutes when the amateur mode is on
(PLAN.md §8), and §11's question is closed.

## Prompt 6

I like the "two paths at once," and feel free to make them even more different to minimize latency and
maximize distance while keeping the wonderful "confirm or veto" property. Is this bit rate the right
choice, given all that we've learned? Would slightly faster or slightly slower be a better tradeoff?

## Response 6 2026-10-09 08:52 - 09:40 PDT Claude Fable 5.1

Done, and it changed more than the slow path, because working it out exposed a mistake in the earlier
range tables. All in the files: sheet 6 (`gen/sch_slow.py`), a second gain block on sheet 3, the
budget's sections 3, 5, 7, 7b and 9, `sim/link_rates.py` for two paths (it also writes
`build/link_rates.md`), `docs/images/block_rx.svg` and `block_modulations.svg`, PLAN.md section 15
and the sections it touches. Build: six sheets, ERC 0, net check 0 (328 parts, 247 nets, the slow
paths walked), 1.34 A from 5 V.

**The mistake.** A comparator is not an ideal sign detector: a TLV3601 needs about 20 mV peak (twice
its offset plus hysteresis) before it decides at all. Through the receiver's 25 dB of RF gain, the
demodulator's x1.95 and the arm's x4, that was -67 dBm at the antenna, **17 dB above** the
noise-limited quiet threshold of -84 dBm that Responses 2-5 quoted. The board as drawn would have
gone deaf 17 dB early, and the tables were optimistic for the fast path. The fix is part of the
two-path design: a **second ADL5611** in the receive chain (+14.3 dB, 0.3 ns, $5.21) and a slow
path with its own gain, so that each path's floor sits at or below its noise.

**The two paths**, both from the demodulator's I and Q pairs (PLAN.md section 15 has the full table):

| | fast path (sheet 3) | slow path (sheet 6, new) |
|---|---|---|
| amplifier | THS4541 at gain **2** (was 4): 180 MHz, 1.9 ns rise | the fast arm's output through a second THS4541 at gain **20**, then 1 k / 33 pF: a **4.8 MHz** pole, 73 ns rise |
| noise floor, quiet from | -89.9 dBm, -81.5 dBm | -103.7 dBm, -95.3 dBm |
| comparator floor | **-75 dBm** (floor-limited by 6 dB) | **-101 dBm** (noise-limited) |
| decides | 13.5 ns jack-to-register on the PYNQ, 9.1 on the Icepi (was 24.1 / 15.3) | **+37 ns** |
| comparators / pins | 3 x TLV3601 on 18, 10, 8 | 3 x TLV3601 on 33, 40, 37 (the spares; 37 is Icepi bank 0, fine here) |
| threshold | V_T from DAC 1 | V_T2 from a second MCP4728 at the preset address 0x61 (C627342, 50 in stock, $2.55) |
| offsets | nothing | two stages x20: up to 30 mV; DAC 2's I_OFF / Q_OFF trim them through 100 k (+-0.33 V); the gateware nulls them with no carrier by watching the comparators' duty cycle |

"Even more different": the fast path got faster (gain 2 / 180 MHz, 1.7 ns sooner than before, at a
6 dB cost that is now the slow path's business) and the slow path went to 4.8 MHz, 20 dB below the fast path's floor
(28 dB below the old single path's real floor). **Confirm or veto** survives exactly: the gateware acts on the fast flag at once and
reads the slow comparators 37 ns later; agreement keeps the trial, disagreement marks it discarded;
a bit below the fast floor is still seen by the slow path, which can carry the data alone when the
signal is that weak (+37 ns). The far end must hold a symbol at least 73 ns (BPSK: the flipped
phase simply persists).

**Reach, quiet (1e-4 per decision), the shorter of noise and the comparator floor:**

| scenario (board alone, +9.8 dBm) | path | BPSK | QPSK | FSK | OOK | whitened |
|---|---|---|---|---|---|---|
| lab: 2 dBi whips on the SMAs, no cables | fast | 36 m | 25 m | 36 m | 21 m | 36 m |
| lab: 2 dBi whips on the SMAs, no cables | slow | 375 m | 265 m | 239 m | 101 m | 350 m |
| campus: panels, 10 m cables, amplifiers at the board | fast | 2.9 km | 2.0 km | 2.2 km | 924 m | 2.9 km |
| campus: panels, 10 m cables, amplifiers at the board | slow | 16.7 km | 11.8 km | 10.7 km | 4.5 km | 15.6 km |
| campus: panels, PA and LNA at the panel | fast | 9.0 km | 6.4 km | 9.0 km | 4.9 km | 9.0 km |
| campus: panels, PA and LNA at the panel | slow | 88.9 km | 62.9 km | 56.6 km | 24.0 km | 82.9 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | fast | 36.0 km | 25.5 km | 36.0 km | 19.5 km | 36.0 km |
| mountain: 30 dBi dishes, PA and LNA at the dish | slow | >100 km | >100 km | >100 km | 95.7 km | >100 km |

| lab, whips, quiet BPSK | fast | slow |
|---|---|---|
| board alone | 36 m | 375 m |
| USB-C amp, if +20 dBm | 116 m | 1.2 km |
| USB-C amp, if +27 dBm | 261 m | 2.7 km |
| 2 W booster (+33) | 520 m | 5.4 km |
| 10 W amplifier (+40) | 1.2 km | 12.1 km |

Through walls at 30 m with whips the slow path has 22 dB to spare (a floor, or three brick walls).
The full tables for 5 % and 1 % and every amplifier are in `build/link_rates.md` and PLAN.md section 13.

**Is 100 MHz the right rate?** With one path it was a balanced compromise (its floor and its noise
within a few dB). With two paths the question splits: the fast path should be as fast as the parts
allow, since its job is latency and the slow path covers its deafness; the slow path as slow as the
protocol allows, since every halving of bandwidth is 3 dB of reach. Hence gain 2 / 180 MHz and
4.8 MHz. Both knobs are 0402 parts JLCPCB solders: 100 pF instead of 33 pF makes the slow pole
1.6 MHz for another 5 dB and 110 ns; R_f 4.02 k instead of 2 k returns the fast arms to gain 4 /
100 MHz / -81 dBm if the 6 dB ever matter more than 1.7 ns. The limits are the symbol hold time and
how soon the confirmation must come, not the circuit.

**Also found while doing it** (recorded in CLAUDE_PCB.md): adding five header signals pushed the root
sheet's wiring columns past the receiver sheet's edge and put two power-sheet rows on the
transmitter's rows, three silent shorts that only ERC and the net walk caught; the root now routes
the slow sheet through a corridor under the others and the columns stay clear. The spare pins
33/37/40 are used up (one spare left, on J303 with the switch controls).

## Prompt 7

Make sure that all of the signal path labels in the diagrams and schematics are updated for this
dual-path scheme and are correct. What are the top reasons why this board would not work as intended?

## Response 7 2026-10-09 10:09 - 12:05 PDT Claude Fable 5.1

### The label audit

Every string on the sheets and in the diagrams that carries a number now comes from one place
(`gen/levels.py`, fed by `build/budget.json`) or was checked against it. Found and fixed:

* **The fast arms are back at gain 4 / 100 MHz.** Response 6 had taken them to gain 2 / 180 MHz for
  1.7 ns. Checking the labels against the budget's isolation section showed what that costs: the arm's
  roll-off is the receiver's only frequency selectivity, and at 180 MHz it rejects the own transmitter
  600 MHz away by 11 dB instead of 31, so the two-antenna full-duplex arrangement would have needed 62 dB
  of antenna isolation instead of 42 (two panels side by side give about 40). The 1.7 ns are not worth
  20 dB. The fast path's comparator floor (−81 dBm) now sits 3 dB from its noise (−84): balanced. The slow
  path is unchanged (4.8 MHz, −95 dBm quiet, floor −107): **14 dB** beyond the fast path, not the "20 dB"
  I wrote before (that compared with the fast floor at gain 2).
* **The latency had counted the arm twice.** The old budget listed "THS4541 at gain 4, 1.6 ns" and "the
  arm filter, 1.7 ns" as two items; they are the same part. Fast path: **22.7 ns** on the PYNQ-Z2
  (TX 8.5 + RX 14.2), **13.9 ns** on the Icepi Zero; slow confirmation +37 ns.
* The TVS on the 5 V input was drawn lying on the rail with an R reference (KiCad's diode symbols are
  horizontal and my vertical-part helper did not know); it now stands with its cathode up and is D303.
  The netlist shows pin 1 (K) on +5V_IN.
* The Icepi Zero has no I2C pull-ups: two DNP 4.7 k now sit on the power sheet beside J303.
* Stale words: "stub" (whip), "gain 2 / 180 MHz", "24.1 ns", the THS4541 and HDR1x6 notes in the parts
  table, the slow sheet's title, the diagrams' "100 MHz" literals (now from the budget).

### The overlaps (your mid-turn message)

You were right and the counts said so: 161 / 32 / 27 / 5 text collisions on the receiver, transmitter,
power and slow sheets. The cause was structural: the generator had an overlap *checker* but no *placer*,
so every note sat where I had guessed. Fixed properly:

* **A placement pass** (`sch_util.flush_notes`, run after each sheet is drawn): every note and blue box
  is placed at the nearest clear spot (texts, symbol bodies, wires, the page edge) within 50 × 30 mm of
  where it was asked for, using the checker's own geometry. It reports anything it cannot clear.
* **The systematic collisions in the drawing routines:** capacitor rows at 7.62 mm (a label needs
  10.16), the ADL5611 bias tees, the synthesizers' six supply capacitors (now a row to the left with
  the flag at the far end; the right is the outputs' chokes), the FDA and MAX2871 pull-ups (a resistor
  up to the supply bar instead of a second rail flag beside the first), the comparators' rail flag
  height, the HOLD switch drawn backwards (its signal ran through its own body; now mirrored so COM is
  on the left), the ADC's four series resistors on 2.54 mm rows (staggered), the LED and TVS text
  offsets, the header's two 5 V flags, the VC monitor tap on the feedback column, a duplicated
  feedback segment.
* **Result:** every sheet 0 overlaps, 0 accidental touches, 0 net problems; ERC 0; net check 0
  (340 parts, 247 nets). I then looked at all six sheets and at zoomed crops of each spot the checker
  had flagged, and fixed what the crops showed that the numbers had not (a label 0.4 mm into a ground
  symbol, the switch's body). The root sheet's title overflowed its block; shortened.
* Recorded in CLAUDE_PCB.md: a checker is half of it; place, then check, then look.

### Why this board might not work as intended (PLAN.md §10, ranked)

1. **The Costas loop does not lock, or runs away.** The sign of sign(I)·Q through the two inverting
   stages; K_d scales with level, so f_n and ζ move with the DSA. Guards: JP101/JP102 flip Q's polarity,
   LOOP_SEL = FPGA gives a plain PLL on Q, VC_OFF sweeps, five taps and the ADC watch it, HOLD opens it.
2. **DC offsets at the demodulator eat the fast comparators' margin.** A few mV of ADL5380 I/Q offset
   ×4 is of the order of the 20 mV a TLV3601 needs; weak-signal decisions and the Q window are biased
   and the loop acquires a static phase error. The slow path has trims; the fast path does not. Guard:
   V_T is adjustable and the ADC reads the offset; if it bites, DAC2's spare channel into U105's
   summing node is a generator change.
3. **The 3.2 V level shift into a 3.3 V FDA.** Summing nodes at 1.73 V against a 2.1 V limit: 0.37 V
   of margin on a part- and temperature-dependent common mode, and 1.5 mA pulled from each demodulator
   pin. Guard: the DNP 1.5 k on ADJ drops the common mode to 2.5 V.
4. **5.8 GHz layout.** Two ADL5611 in a row are 28 dB that will oscillate with sloppy grounding; the
   balun, the LO pairs, the LNA match and the never-built copper coupler are single-chance structures.
   Guards: the DSA between, the pi pad, four LO/RF monitor jacks for the analyser.
5. **The LO is wrong**: register order, lock-detect polarity, a loop filter computed on a 60 MHz/V Kvco
   the part only promises as 40-80, 0 dBm that may be 3 dB low. Guards: lock detect on MUX, LO MON taps,
   every register a software write.
6. **Own transmitter into own receiver** with two antennas 600 MHz apart: 31 dB of arm rejection asks
   42 dB from the antennas; a PA or closer panels compress the demodulator. Guards: the DSA, time
   division instead, the slow path's veto (which cannot un-compress a demodulator).
7. **Heat**: 1.34 A from 5 V, 6.7 W, ADL5380/5375/3 × ADL5611/2 × MAX2871 on 1 oz copper. Guards: the
   PLL LDOs' series 2.2 Ω, exposed-pad vias, a measurement before any enclosure.
8. **The slow path's offsets or saturation** confuse its Q window. Guards: DAC2 trims (±0.33 V), V_T2
   above ×20 the loop's static error; the fast path works without it.
9. **Single-ended ladder drive** wobbles the modulator's common mode ±0.17 V and the −15 dBc feedthrough
   adds a fixed vector. Guards: VR_I/VR_Q trims; the receiver cares about sign.
10. **Parts and the order**: five HMC536 at JLCPCB, three consigned ADI lines, two DACs that differ only
    by address, JLCPCB rotations on SOT-89/QFN/SC-70. Guards: PLACEMENT_CHECKS.txt, the preview, the
    HMC427A as a second-source switch.
11. **The Icepi Zero**: no I2C pull-ups (now DNP on the board), 5 V from its own USB-C, no gateware yet.
12. **A generated symbol with two pins swapped** passes ERC and the net walk. A second pair of eyes on
    gen/symbols.py against the pin figures before ordering is cheap.

## Prompt 8 2026-10-09 12:15 PDT Jason

Make (or probably modify) a reasonable bring-up and testing plan that gets us from "across lab" to "up into the
mountains". Go through the reasons that the board would not work one by one and check that, to the best of
your knowledge, these have been sufficiently addressed. At the very least, de-risk them with some combination
of U.FL measurement taps and DNI components, but only do this to the extent that adding them won't adversely
affect the RF performance.

Once you are convinced that the series of experiments is worth doing and has a high chance of success, start
designing the PCB using the lessons learned from CLAUDE_PCB.md. If you learn new lessons, add them where
appropriate. What is your cost estimate to do my usual "5 PCBs, 2 assembled" new-board testing strategy? How
much goes to JLCPCB, how much goes to Digikey, and how much to other?

I have put PDFs of the AliExpress web pages with the power amplifier (SBB5089+SE5004-5.8G-2W +40dB) and the
filter+LNA (Active SAW Filter & LNA Low Noise Amplifier Module 5.8Ghz) that I happen to have (both powered by
USB-C). I would be willing to buy better ones as the tests demand.

Keep recording these prompts and your responses in CLAUDE_CHAT.md

## Response 8 2026-10-09 12:15 - 14:30 PDT Claude Fable 5.1

### The dead-on-arrival list, one by one

Each of PLAN.md section 10's twelve, with what was on the board already, what Response 8 added, and the
bring-up stage that retires it (the full table is the last section of `BRINGUP.md`).  "Enough" means I
would order with it as it is; "added" means a change made in this response.

| # | risk | enough? | what the board has / what was added |
|---|---|---|---|
| 1 | the loop does not lock or runs away | enough | sign jumpers (now with the right default: see the audit), plain-PLL mode, VC_OFF sweep, HOLD, five monitors and the ADC |
| 2 | demodulator offsets eat the fast comparators' 20 mV | **added** | DAC2's spare channel D now trims the fast I arm through 100 k (I_SUM leaves sheet 3, the resistor sits by DAC2 on sheet 6); the Q fast arm stays untrimmed: its offset shifts the loop's static phase by milliradians and the slow Q window confirms or vetoes it |
| 3 | the 3.2 V level shift into a 3.3 V FDA | enough | the DNP 1.5 k on ADJ; per-arm PD |
| 4 | 5.8 GHz layout | the board | the RF lines are laid by plan as coplanar tracks with via fences (gen/routes.py), the chains are straight lines by construction, the DSA sits between the LNA and the two gain blocks, four RF monitors.  No pad between the two ADL5611: a 0402 discontinuity in the 50 ohm line costs more than it de-risks (the DSA already breaks the chain) |
| 5 | the LO is wrong | enough | lock detect on MUX, LO monitors, REF IN, every register a write |
| 6 | own TX into own RX | **added, in the plan** | the LNA module's filter (assumed 30 dB 600 MHz away, measured in stage 5) sits in front of the receiver at the panel; the lab test keeps each board's two whips a metre apart or uses the switch |
| 7 | heat | enough | +5V_RF pour, exposed-pad vias, the PLL regulators' 2.2 ohm; stage 1 measures it |
| 8 | the slow path's offsets | enough | I_OFF / Q_OFF, V_T2, the nulling routine; all four DAC2 EEPROM defaults go to mid-scale so power-up injects nothing |
| 9 | the single-ended ladder drive | enough | VR_I / VR_Q |
| 10 | parts and the order | the cost | the HMC536 is the thin line (5 in stock, 2 needed); the consignment is needed for the balun whatever happens with the ADI chips (section 17 of the plan) |
| 11 | the Icepi Zero | enough | DNP pull-ups, JP301 open; the Icepi plugs up into the socket from below |
| 12 | a generated symbol with a wrong pin | **done** | a pin-by-pin audit of all fourteen custom symbols against the datasheet texts (`build/scratch/pin_audit.md`): every drawn pin right, every schematic use right, but two symbols INCOMPLETE (nine grounds missing on the PE43711, the HMC536's paddle) and, found by the new gate, the SMA footprint's centre pad was not the symbol's pin 1.  All fixed; `tools/net_check.py` now fails the build on any footprint pad without a net |
| 13 | **new:** the TCXO's pin 1 is undocumented in its datasheet text | noted | if it is a control input, a rework wire to V_MID; stage 2 sees it |
| 14 | **new:** two control senses were written backwards | **fixed** | the HMC536 truth table (A low, B high = RF1 = SW TX; the pull-ups rest it in receive) and the 74LVC1G3157's select (S low = B1): the notes and the sign jumpers' default (JP101 right, JP102 left: ERR = sign(I) x Q) are corrected |

What I did NOT add, and why: a pi pad between the gain blocks (above); a trim on the fast Q arm (no
DAC channel left, and the slow window covers it); a bandpass filter footprint (none stocked, and an
unfitted one needs a bridge); a limiter (it goes in the cable when a PA meets the switch).  Extra U.FL
taps: the sixteen are enough; each is 30 matings.

### The amplifier modules you have (`sim/budget.py` section 2c)

* **PA** SBB5089 + SE5004, 5-6 GHz, 40 dB, P1dB +33 dBm at 5.5 GHz, 2 A at 5 V.  To run at +30 dBm it
  wants -10 dBm in: **a 20 dB SMA attenuator** between TX ANT and the module (the board's +9.8 dBm alone
  drives it 17 dB into compression).  It dissipates about 9 W in a 45 x 30 x 14 mm shell: heatsink or
  fan, and a 5 V / 3 A source.
* **LNA** "SAW filter + LNA", 5.8 GHz version: the page's table stops at 2.4 GHz (17 dB, NF 1.6) and the
  5.8 GHz unit has NO published gain, noise figure or passband.  The budget assumes 15 dB, NF 2 dB,
  5725-5875 MHz and 30 dB of rejection 600 MHz away, and stage 5 of the bring-up measures all four.
* The range model's tiers are now the board alone, this module at +30 dBm, the same at its P1dB, and a
  10 W amplifier.  Lab with whips, quiet BPSK: 72 m fast / 847 m slow alone; 720 m / 8.5 km with the
  module.  Campus with panels, cables at the board, board alone: 5.7 km / 38 km.  With the LNA and PA at
  the panels, both paths are beyond 100 km; power is not the limit, line of sight is.

### The bring-up plan: `BRINGUP.md`

Six stages from the bench supply to two hills: 0 the gates before ordering (the pin audit done, the
gateware to write, the consignment); 1 first power (rails, 1.34 A, heat, I2C: an afternoon); 2 the
synthesizers and the transmitter on their monitors; 3 loopback through a 30 dB pad (never a bare cable:
the LNA dies at +1 dBm): offsets nulled, the loop locked, the latency on CMP I MON against TRIG A, every
modulation, the veto counters; 4 two boards across the lab on whips, the latency line against distance,
error rates, time division with the switch; 5 across campus on the panels, bare, then the LNA module at
the panel, then the PA through its pad, in the 5 cm amateur band with the Morse identification; 6 the
dishes.  Each stage has its connections, its measurement, its pass condition and what to do if it fails.
I am convinced the series is worth doing: nothing in stages 1-4 needs anything you do not own, and a
failure at any stage leaves a board that still teaches the next.

### The board (`gen/placement.py`, `gen/board.py`, `gen/routes.py`)

120 x 90 mm, four layers (F.Cu RF and signals, In1 solid ground, In2 the supply pours and leftover
routing, B.Cu signals under a ground fill), the socket on the back along the bottom edge on the PYNQ-Z2's
measured header (our left edge at its x = 72 as the GPSDO board, 11 mm of overlap), three desk standoffs
and a slot onto the PYNQ's hole.  Five SMAs along the top edge; the receive chain straight down x = 24,
the transmit chain straight up x = 56, the switch block top-right, the regulators in a column on the
right, the USB-C on the right edge, the loop under the TX synthesizer, the fast comparators over header
pins 8/10/18 and the slow ones over 33/37/40.  90 parts by hand, 250 by rule from the netlist (a shunt
perpendicular at its pin, a series part on the line between its pads, decoupling at the chip the
SCHEMATIC drew it beside, read from the sheets), pushed apart until no courtyards overlap, and drawn to
look at before KiCad (`build/view/placement.png`).  The board generator runs inside KiCad's Python and
reads pcbnew's own pads back before laying copper: that check found that **pcbnew's flip onto the back
mirrors y**, whatever its enum says (the socket footprint is now drawn for that), and that a USB-C at
rot 270 faces left (it is rot 90 on the right edge).  The RF paths are walked pad to pad through the
netlist and laid as straight 0.34 mm coplanar tracks with ground vias at 1.2 mm either side; the top
ground fill backs off 0.25 mm (the coplanar gap); +5V_RF, +3V3_ANA and +3V3_DIG are In2 pours; the
router (GPiBridge's A* grid) takes the rest, RF and baseband first.

**Where the routing stands (14:30 - 16:55, seven builds of about six minutes each):** 2406 tracks and 801 vias
(122 in the RF fences, 37 in the chips' exposed pads, 197 ground fan-outs); 206 of the 247 nets joined; **41
nets still in 74 pieces** and KiCad's DRC at **2 violations** (two dangling supply vias at the seam between
two pours) and 67 unconnected items.  What each build fixed,
in order: the inner supply pours forbade every via through them (the first run had 87 nets in pieces and no
ground fan-out: pours now let other nets' vias through); a 0.34 mm track cannot leave a 0.5 mm QFN pad (the LO
pairs go at 0.2); the router's widest obstacle class was 0.4 mm, so 0.8 mm rails overlapped neighbours (two
classes added); the SOT-89's tab is a custom pad the router sized as its anchor (bounding box now); the U.FL
footprints carry keep-out areas (honoured, with a via's margin); the RF chain's series parts were pushed
sideways off their lines (pushed along them now); the RF walk stepped through a DNP shunt onto ground
(shunts and DNP parts skipped); a straight RF track into a 0.4 mm pin in a 0.65 mm row touches the next pin
(necks); the SMA's vendored courtyard is smaller than its leg pads (pads count as obstacles); a test pad and the
switch's control resistors sat on its RF lines (moved); a ground via in
front of each QFN ground pin walled the signal pins beside it (vias go in the paddle instead, the pins are
tied to it by the router); the PLL rails and the 5 V input got pours of their own.  **What remains is one
cause:** the parts placed at a fine-pitch chip's pins wall the pins beside them in (the synthesizers' LE, MUX,
TUNE and filter pins, the FDAs' inputs, the demodulator's I pins, the coupler's coupled-port pads).  The cure
is the ECP5 board's: give every signal pin of every fine-pitch chip a stub to a via of its own, in a fan, BEFORE
the passives are placed (CLAUDE_PCB.md section 5), then the router starts each net from a via with every layer
free.  That is the next piece of work, about a session; after it the release script (still OWLternating
Current's) is adapted to one board, and the gateware top is written before anything is ordered.  Renders:
`docs/images/board_top.png`, `board_bottom.png`, `board_placement.png`.

### The cost of "5 PCBs, 2 assembled" (`mfg/cost_estimate.py`, `build/COST_ESTIMATE.md`)

| where | what | cost |
|---|---|--:|
| **JLCPCB** | 5 boards 120 x 90 mm, 4 layers, ENIG (a model: $28-63; the cart decides) | $46 |
| | assembly on both sides, Standard PCBA (setup, stencils, fixture, 41 Extended codes' feeders, 903 SMT pads and 86 through-hole joints a board) | $209 |
| | their parts: 65 BOM lines with attrition, at the day's prices | $246 |
| | US duty, 35 % under DDP | $175 |
| | shipping | $25-40 |
| | **JLCPCB total** | **$701-716** |
| **Digi-Key** | ADL5380 x 4, ADL5375-05 x 4, balun x 4, with tax and shipping | **$150** |
| | shipping the consignment to Shenzhen | $35-60 |
| **other** | attenuators (30 dB, 2 x 20 dB), pigtails, whips, leads, two PD banks, standoffs, a heatsink; a second PA and LNA when the far end needs them | **$129-251** |
| | **everything** | **$1015-1177** |

The duty is a third of JLCPCB's line.  Every chip is Extended, so the feeder fees stay.  Buying the two
ADI chips from JLCPCB's stock (8 and 6 on the day) would cost $15 more and save their handling, but the
balun is stocked nowhere at JLCPCB (5400BL15B050E, HHM1595A1, TCW4-582+: all 0), so the shipment to
Shenzhen happens either way.  Economic PCBA would save about $70 if the socket were hand-soldered;
CLAUDE_PCB.md says JLCPCB fits everything.

### Lessons recorded (CLAUDE_PCB.md)

A shunt hanging from the upper of two stacked rows runs through the lower (stand it on a loop above;
crop at 300 dpi); a symbol can be incomplete with every check passing (the pad-without-a-net gate);
adding pins must not widen a symbol (a side bar); placing three hundred passives by rule, with the
schematic's own positions deciding which chip a decoupling capacitor belongs to and connectors the
last thing to hang a part on; pcbnew's flip mirrors y, so read the pads back against the host's
measured header; a connector's rotation decides which way its pads face; the three cost buckets; a
bring-up plan as a table from the DOA list to the stages.

### Not done

The gateware top (CLAUDE_PCB.md section 9 wants it building before the order; BRINGUP.md stage 0);
the release script is still OWLternating Current's and must be adapted to one board before the
upload files exist; the RF nets are not yet named (the net classes in gen/project.py match RF_* names
the sheets do not give; the coplanar gap is held by the fill's clearance meanwhile); the silkscreen
has names and the identity but no section boxes; the CPL rotations wait for the day of ordering as
you asked.

---

## Prompt 9 (2026-10-09 16:57 PDT)

> Look through CLAUDE_PCB.md again. Finish the routing and make the schematics and silk screen clear
> and beautiful, with all relevant information that a user could want obvious (so as not to exceed
> inputs to this board or to the next-stage board). Once you think you'r done,  Look at the other
> projects in here and in ~/mudd/pcbs/ for design review files. Make a design review prompt. Then do
> that prompt to really be as sure as possible that this will work on first try. If all is good, maybe
> I can send this off to JLCPCB tomorrow.

## Response 9 (2026-10-09 16:57 - 21:20)

*(in progress, 17:00-17:45)* Re-read `CLAUDE_PCB.md`.  The routing's one cause (fine-pitch pins walled in by
the parts at their neighbours) is being cured the way the ECP5 and OWLternating Current lessons say: a
planned fan-out per chip (`gen/routes.fan`: each signal and supply pin a stub, a straight line and a via
of its own, the vias of a side evenly spaced, exact geometry against the copper already laid, patterns
tried cheapest first), the chip's short local nets routed before it, the chip's area a keep-out for every
other net on the top layer, the paddle's ground pins tied into the paddle by plan, the LO pairs and the
I/Q pairs laid straight by plan with a stub out of each pad, rip-up and reroute of what is still walled in
(`repair`), unused fan-out vias and loose tracks pruned, the rails widened afterwards where there is
room; the slow signals routed underneath (the top is the RF's and the eye's); and in the placement a
1.8 mm band round every fine-pitch chip that no part may stand in.  The RX synthesizer moved 2 mm down and
the VCXO with it (the two chips' bands met); the slow Q comparators moved under their stage (their 1 k
series resistors were stranded under the synthesizer, at the midpoint of a 32 mm line); the CMP I MON jack
moved beside them.  The two dangling vias had a cause: the pour-membership test used an L-shaped pour's
bounding box, so a via in its notch counted as joined; it now tests the polygon with a margin.  A table of
what every connector takes or gives (`gen/levels.LIMITS`) now feeds both the schematic's tap notes and the
silkscreen; the silkscreen gets section boxes computed from the placement's blocks and checked (nothing
of another block inside, no two boxes overlapping).  Two agents work in parallel: one adapting
`mfg/make_release.py` from the panel version to this one board, one writing the first gateware top.

*(about 17:55)* The two agents reported.  **The release** (`mfg/make_release.py`, rewritten for one board): on a
copy of the unfinished board with DRC skipped, every other gate passes: 68 BOM lines (3 consigned), 317
placements on both sides, 41 Extended parts, every code's JLCPCB description matched to the parts
table's words, value, package and MPN, stock covering the order with attrition, no land-pattern HOLE
finding, the CPL agreeing with KiCad's position export and JLCPCB's drawings landing pin for pin on 45
parts; 28 placements moved to JLCPCB's own origin (the U.FLs, the headers, the USB-C, the socket, the
SOT-89 gain blocks: 0.7 mm); 27 part numbers with rotations predicted but not yet read in a preview
(`PLACEMENT_CHECKS.txt`); JLCPCB goods $503, $704-719 with duty and shipping, Digi-Key $150, agreeing with
`build/COST_ESTIMATE.md` within $3.  It refuses the same board with DRC on (89 violations, 231 unconnected
at the time), as it must.  Two things it found: `mfg/footprint_check.py` crashed on the balun's EasyEDA
record (no drawing) and read the SOT-89's tab as a fourth pad; both fixed there.  **The gateware**
(`gateware/costaslink_top.v` and eleven modules): Verilator lint clean, Yosys 1167 flip-flops, the Icarus
testbench PASS (the sixteen synthesizer words in the datasheet's order with the 20 ms wait, the DSA's
eight bits LSB first, the DAC and ADC transactions, the latency counter, the Morse ID), and nextpnr places
and routes it for the Icepi at 114 MHz.  It changed the synthesizer power-up to the datasheet's own list
(register 4 first with the outputs off, then on) and found two things to check: the PYNQ's UART pins in
the XDC (Arduino D0/D1, from memory, not from a file) and that the ADS1115's default range would clip
the 0-3.3 V nodes (it uses +-4.096 V).

*(about 18:40)* Three builds of the new router found three bugs of mine, each with a lesson: the chip keep-out
covered the pads themselves, so a pin with no fan-out was walled in at once (it is now the region inside
the pin ring only); the widening pass asked the grid for the cells under an off-grid line with reach zero,
found none, and widened fan-out stubs at QFN pins to 0.8 mm (14 shorts; it samples with half a pitch now
and never touches a planned line or a pin's neighbourhood); and, the one that mattered most, the rule
that turns a shunt to stand at a pin had its sense inverted above and below a chip, so all 65 shunts on
chips' top and bottom rows faced their pins with the ground pad.  A measurement after placing (both
pads' distances to the pin) found 65 wrong, 0 after the one-character fix.  Also from the logs: a
decoupling capacitor had been pushed onto the TX RF line and the LNA's DC block sideways off the RX
line (the chains' corridors are now placement keep-outs and a part on a line moves only along it); the
two LO blocking capacitors at adjacent 0.5 mm pins cannot stand side by side (the second now stands
2.2 mm further out and 0.7 mm to the side); the pour-membership test is the real polygon.  You wrote,
while the fourth build ran, that the board may grow: the dense part is the strip between the demodulator's arms and the
socket, and the socket sits where the PYNQ's header is, so the board is now **120 x 100 mm** (10 mm
taller, the extra 10 mm between the arms and the socket; the slow stages, the comparators, the VCXO
and the loop block spread into it; about $3 more per board).  The size was mine from Response 8: just
enough to hold the two straight chains above the PYNQ's header edge.

*(about 20:40)* Five more builds, each seven to ten minutes now that the router's budgets are capped.  What
each found: the pruning of unused fan-out vias had removed copper that carried nets (it now verifies the
net's piece count before every removal, replaces a via used on one layer by a short track at the junction,
and leaves ground alone, whose fence and paddle vias carry no track by design); a U.FL's "no tracks"
rule area, grown for vias, had walled its own centre pad; a coupler's own coupled line, a foreign net
to the router, walled its coupled and isolated ports (its copper now carries the net of the pad it ends
in, and the isolated ports and every tap have a planned line); the LO monitor pins cannot keep their
blocks beside the LO pair's at 0.5 mm pitch, so they are fanned out like any signal; the TX LO MON jack
moved to the side the pins face; the trigger buffer was turned to face its jacks; a series part now hangs
off its chip pin whenever the line to its far end is not along that pin; the courtyard gap is 0.35 mm;
the two synthesizers moved down by the blocks' stagger (the TX PLL pour with them) and the RX chain's
parts spread by the same rule; a strip on the back is reserved for the identity block.  A KiCad abort
("malloc(): unaligned tcache chunk") that cost two builds was `bb.Merge(b) or bb` keeping a non-owning
proxy of a bounding box: lesson recorded.  The board is saved before the silkscreen stage now.

### The schematics and the silkscreen (what a user could want obvious)

Every connector now has one table behind it, `gen/levels.LIMITS`: what it takes or gives, as the short
line printed beside it on the board and the sentence beside it on the sheet (the tap notes read it).  RX
ANT says its +1 dBm absolute maximum and what the LNA module ahead of it may be fed; TX ANT says +10 dBm
out and that the PA module takes at most -7 dBm, so the 20 dB pad is the rule; ANT, SW TX and SW RX say
the switch's +29 dBm; REF IN its 10-210 MHz and 0.7-3.3 V p-p; TRIG IN its 5.5 V maximum; every monitor
its expected level and the 1 k or 50 ohm behind it; the header pins and jumpers their choices.  The
silkscreen gained the section names (a box is drawn only where its four sides are clear of parts; on a
board this dense most are the name alone), a reserved strip on the back for the identity block, and a
label placer that searches rings of spots and reports what it could not place.

### The design review

`DESIGN_REVIEW_PROMPT.md` is the brief, in the form of the ECP5 and GPS-adapter ones: ground rules,
what the board is for, the state and the claim to break, nine things to attack, the lessons file's
rules restated as checks with the author's belief in brackets, the read-only tools, what is already
known.  Then I did it myself, as you asked, through an independent agent that read only the generators,
the netlist, the datasheet PDFs (it converted them itself) and the sheets, and wrote
`design_review_Claude/DESIGN_REVIEW_Claude.md`.  Its verdict: do not order until two schematic faults are
fixed, then order.  Both are real and both were mine:

1. **The OPA2187 cannot work on 3.3 V.**  Its recommended supply starts at 4.5 V and its input common-mode
   range stops 2 V below the rail; the loop's PI filter and VC stage had both inputs at 1.65 V on
   +3V3_ANA.  Every number of the loop had been computed and asserted; the op amp's operating conditions
   had not been read.  **Fixed:** OPA2388IDGKR (zero-drift, rail-to-rail in and out, 2.5-5.5 V, the same
   VSSOP-8 pinout; JLCPCB C2059281, 2020 in stock, $2.29), one BOM line, no copper change.
2. **The header 5 V path could never deliver.**  The USB path's FET had its gate grounded, so once
   +5V_IN was up it conducted the header's 5 V back onto VBUS, which lifted the header FET's gate and
   turned it off: the board would have run on a body diode at 4.1 V with 4 V on the USB-C receptacle.
   **Fixed:** the USB FET's gate is held up by +5V_HDR and pulled down by a 2N7002 whenever VBUS is
   present, so USB wins when both are plugged and neither feeds the other; the header FET's gate lift is
   1 k against 100 k (its off-state Vgs was 0.45 V against a 0.5 V minimum threshold: the review's item 6).

The rest of its table: the ADL5380's output common mode is 3.8 V in one table of its datasheet and 3.2 V
in another, which put the FDAs' summing nodes at 2.02 V against the THS4541's 2.0 V minimum (fixed: the
budget now takes 3.8 V and the shunt is 1 k, 1.87 V); the SW RX rest state was printed backwards on the
switch sheet and the silkscreen (fixed); the bead's drop was missing from the 5 V margin (the bench supply
goes to 5.1 V; the sheet says so); the MAX2871's VCO gain is 100 MHz/V typical where the loop was
designed at 60 (it locks either way; noted); TR_B rests at 2.7 V behind the PYNQ's 2k2 pull-up until the
gateware drives it (noted on the sheet; harmless for the configuration time); two cosmetic items.  What
it verified and found right is the longer list: the HMC536 truth table and pads, the mux's select sense
and the SIGN jumpers' default, the HOLD switch's sense, the modulator's DSOP and the demodulator's ADJ,
the attenuator's serial mode and grounded parallel pins, every MAX2871 pin sense and the register words,
every connector's absolute maximum, the loop arithmetic, the ladders' levels, the rails, the polarities,
the capacitor ratings, every generated symbol's pins.  Two lessons from it are in CLAUDE_PCB.md: assert
every op amp's supply and common-mode range against its rail, and trace a two-supply ORing in both
directions with each gate written out.

### The board: where it stands at the end of the evening

The build that closes the evening (21:15): **3131 tracks and 776 vias; 241 of 248 nets whole; 7 nets
still in pieces** (I_OFF, the slow I comparator's IN-, SPI_SCLK in 3 pieces, MUX_TX, LOOP_HOLD, I_SUM in 3
pieces, the LO RX MON tap), **11 unconnected items; DRC 6 violations, all warnings about loose ends (4
tracks, 2 vias), 0 clearance, 0 shorts, 0 parity**; every planned RF line, the LO pairs, the paddle grids,
the fan-outs of all 33 chips and the In2 pours in; the slow signals underneath; ERC 0, net check 0 on the
revised sheets (343 parts, 248 nets).  The silkscreen placed 587 labels; 72 it could not (the back's
identity block, because the fan vias took its strip before the keep-out was declared, fixed for the next
build; a dozen chip names and section names in the densest parts).  Renders: `docs/images/board_top.png`,
`board_bottom.png`, `board_placement.png`.  The session's twelve builds went 41 -> 38 -> 19 -> 13 -> 12
-> 11 -> 10 -> 13 -> 11 -> 7 -> 2 -> 5 -> 7 nets in pieces: the last three builds shuffled the remaining
handful as the placement moved (the review's parts, the loop block spread), without a new cause.  The
cost for 5 boards, 2 assembled, re-run on the 120 x 100 board with the review's parts: JLCPCB $703-718
including duty, Digi-Key $150 plus $35-60 to ship the consignment, other $129-251 (`build/COST_ESTIMATE.md`).

### What is not done, and whether to order tomorrow

**Do not send it off tomorrow.**  Three things stand between this board and an order, in the order they
fall:

1. **Seven nets in pieces and six loose ends.**  Every remaining failure is a pad walled in by its own
   neighbours in the loop block and the slow stages, or a long header line that ran out of search
   budget; each build moves them.  The cure is one more placement pass by hand on that region with the
   board's own pictures (an hour), then builds of ten minutes until DRC reads 0 and 0.  The pipeline is
   now all there: the planner, the fan-outs, the verified cleanup, the stage counts.
2. **The release has not run on a clean board.**  `mfg/make_release.py` refuses the board as it stands
   (DRC), as it must; its other gates passed on the test copy (`build/release_test/out/` has the files
   it would write: gerbers, BOM, both CPLs, `PLACEMENT_CHECKS.txt`, `CONSIGNMENT.md`, `ORDER_SETTINGS.md`).
3. **The review's fixes are a day old.**  The OPA2388 and the new gate circuit went in tonight; the sheets,
   ERC, the net check and the budget pass on them, and the board was rebuilt with them, but nobody has
   looked at them with fresh eyes.  Send `DESIGN_REVIEW_PROMPT.md` to the other reviewers tomorrow morning
   while the routing finishes; my own review (`design_review_Claude/`) is the first round.

What is done: the schematics with every limit a user could want at the connector, the silkscreen's
names and limits, the bring-up plan, the first gateware, the release script, the review brief and one
review, the cost, and the lessons (nine new entries in CLAUDE_PCB.md).  Nothing is committed; the
GPSDO and ECP5 changes in the tree are other agents'.

*(Jason, mid-turn, about 21:05:)* "Are you still going? What are the advantages and disadvantages of MMCX vs
U.FL/IPEX for these debug ports? Which are easier to plug in and out? How much more space does the MMCX take
up on the PCB? How much more difficult is it to route the board with MMCX vs U.FL? Which, when unpopulated,
affects the signal integrity more? Which is more common for this kind of debugging situation? How many
insertions does SMA, MMCX, and U.FL have in their lifetime?"

**MMCX against U.FL for the sixteen taps**, in the order asked, from the makers' specifications (Hirose
U.FL series, Amphenol and Rosenberger MMCX, MIL-STD-348 / IEC 61169-15 for SMA):

| | U.FL (Hirose; I-PEX MHF1 is the compatible) | MMCX | SMA (the five RF ports here) |
|---|---|---|---|
| mating cycles, rated | **30** | **500** | **500** (stainless; brass bodies less) |
| plugging by hand | snaps on with a push; comes off with the Hirose U.FL-LP extraction tool or a careful fingernail lever, and a lead pulled by its cable is a dead lead | push on until it clicks, pull straight off; rotates freely; the easiest of the three | thread and tighten (a wrench for repeatable loss) |
| receptacle on the board | 2.6 x 2.6 mm, 1.2 mm tall (2 mm with a plug): one centre pad, two ground pads, about 3 x 3 mm of board | about 4.5 x 4.5 mm SMD body, 5 mm tall (8 with a plug): a centre pad and four ground pads, about 6 x 6 mm of board with its clearance | 9 x 9 mm body, 10 mm tall; five through-hole legs |
| board area, 16 taps | about 150 mm2 | about 580 mm2, four times as much: 5 % of this 120 x 100 board | - |
| routing | the centre pad has one way out, between the two ground pads, and the body's keep-out walled our own router off it tonight until the rule was fixed; otherwise a 1 mm pad on a 0.2 mm line | the four ground legs leave one or two open sides for the feed; the pad is bigger and the keep-out bigger, so the part is a larger obstacle but the tap itself is easier to reach | - |
| unpopulated, on the line | a 1 mm centre pad: about 0.1 pF of shunt | a larger pad and a larger plane cut-out: about 0.2-0.3 pF | - |
| cost at JLCPCB | about $0.30 (C88374, Basic-ish stock) | about $0.6-1.2 | $1-2 |
| cable | 1.13 or 1.37 mm micro-coax, U.FL-to-SMA leads about $2 | RG-178 / RG-316 or 1.37 mm, MMCX-to-SMA leads about $3 | - |
| frequency | DC-6 GHz (VSWR 1.4 at 6 GHz) | DC-6 GHz | DC-18 GHz |

Which matters here: every tap but five sits behind a series resistor (1 k, 453 or 33 ohm) or is a coupled
port with its own 50 ohm load, so an unpopulated receptacle of either kind is a tenth of a picofarad on
a node that already has a resistor in series with it: nothing at 100 MHz, and at 5.8 GHz only the two
coupled-port monitors and the two LO monitors see it, each already 20 dB down.  Leave the footprints
either way.  The five ports that will be plugged **every** time the board is used in the field are the
ones the 30 cycles bite: TRIG A, TRIG B, TRIG IN, REF IN and REF OUT.  U.FL is what dev boards and modules
use for taps (it is the common choice for exactly this: many points, each looked at a few times, with a
lead left on the busy ones, as BRINGUP.md's bench list says); MMCX is what GPS modules and some SDR
daughterboards use where the plug is made and broken often.

**My recommendation:** rev A stays as it is (sixteen U.FL; buy ten U.FL-to-SMA leads and leave them on
the taps in use), because the change is a footprint and a placement for five parts that would push the
left margin and the loop block apart, a few hours and another round of routing, the night before an
order.  For rev B, make the five field ports MMCX (or SMA along the bottom edge, where there is room
since the board grew), and keep U.FL for the eleven monitors.  If you would rather have the five on
MMCX now, say so and it is the first thing tomorrow; it does not touch the circuit.

---

## Prompt 10 (2026-10-09 21:25 PDT)

> Yes, move the five field ports (TRIG A, TRIG B, TRIG IN, REF IN, REF OUT) to MMCX, or even SMA if there
> is room on the layout. If others have enough space around them to go to MMCX on those too. For the
> tighter spaces, leave as is.
> Back in response 2, you said that "18 and 26" were clock-capable pins on both PYNQ-Z2 and Icepi Zero.
> But you didn't list 16 on the first row for the PYNQ-Z2.
>
> Did you keep the HMC536MS8G on the BOM for the board? At this point, can we hope to do 1 antenna to one
> other antenna in lab with this board? Across campus?
>
> All of these schemes assume that "idle" is positive real (+I). For OOK and BPSK, this makes sense. For
> QPSK, I'm confused why you've chosen the constellation points that you have, rather than, say an even
> circle of points or a "+" pattern in the constellation diagram, with the idle state being the right-most
> point of the "+"? More generally, if "idle" will be different from "send a 1", which is different from
> "send a 0", it seems that the BPSK needs 3 constellation points, not the 2 that you showed, unless the
> first non-idle state acts like a start bit, at which point you need to add that start-bit time to your
> latency. And for QPSK, if "idle" is a different state from states like "sending 00", "sending 01",
> "sending 10" and "sending 11", you'd need 5. For your PSK, you have 2, but your QPSK has 5. They are not
> 5 evenly spaced ones, and maybe that's fine to do it in hardware with comparators, but something seems
> inconsistent here. Given the comparators' offsets plus hysteresis, what are the best constellations to
> distinguish "idle" from 1 bit (either way), 2 bits (any of 4), or 1 of N in general (not necessarily a
> power of 2, where idle along with N=4 basis settings is what we're looking at actually needing). For a
> hardware Costas and decision loop, I don't have a sense for how different the circuit for each N is. I
> don't know at what point a flash ADC for each of I and Q becomes the right call. What are the ways this
> is done for such extreme low-latency links, where you want several bits of information to show up in
> the first symbol? Where are DAC trims helpful and not?
>
> With the TX/RX switch, how does a station's RX VCO remain relatively locked when that station is
> transmitting on a different frequency? Is this just held in a capacitor as a sample-and-hold? Or some
> digital configuration memory? I'd think the digital would be too slow and I don't have a sense for how
> much the analog would drift.
>
> As you route, are you taking advantage of the lesson from the ECP5_2ADC_2DAC board, where you don't
> assign FPGA pins (other than maybe clocks) until the river from the FPGA (in this case, the raspberry pi
> header) is approaching the river coming from the chip? This way you avoid mistakenly assigning header
> pins to chip pins that require unnecessary crossing and often lead to boxing in.

> **(22:40, while the connector work ran)** I asked how such low latency few-bit symbols are typically
> handled in hardware, but I'd be perfectly happy with a wonderful, perhaps even optimal, solution that
> was arrived at through first-principles thinking.
>
> **(22:45)** Keep going with my latest first-principles prompt.

## Response 10 (2026-10-09 21:25 - 2026-10-10 10:00)

The work stopped at about 22:40 and resumed at 08:45 on 2026-10-10; the times below are real.

> **(09:50, while the amplifiers' resistors were being placed)** Try again

I read that as "keep going on the board", which is where the turn stood; the board section below says
what that pass did.

### The answers, in brief

* **Field ports.** TRIG A, TRIG B and TRIG IN are SMAs off the left edge; REF IN is an SMA off the right
  edge. REF OUT is a vertical MMCX beside the VCXO, because the only edge near it belongs to the slow I
  stage and the socket. VC MON, ERR MON and I SLOW MON are MMCX too; the other eight taps stay U.FL.
* **Pin 16** is clock-capable only on the Icepi (PCLKC6_0). On the PYNQ-Z2 it is W6, IO_L22N_T3_13,
  neither MRCC nor SRCC, so Response 2's PYNQ list was right and 18 and 26 are the only pins clock-capable
  on both.
* **The HMC536** is on the BOM: U401, sheet 5, the antenna switch.
* **One antenna to another:** yes, in the lab and across campus, by time division through the HMC536.
  The reach at a strict standard is in the table below.
* **Constellations:** you were right. The BPSK row was idle plus one point: an event, no bit. The QPSK
  row was idle plus four, chosen by no rule. Worked out from first principles (`sim/constellations.py`,
  PLAN.md section 18), the best two-bit scheme on paper is a pilot sent at 45° with the four corners as
  the messages. The loop turns them onto the receiver's ±I and ±Q, and one window comparator per message
  gives the event and both bits on one edge. A tolerance check then showed the pilot must be about
  −14 dBc, not −26, with the Q arm's DC offset trimmed: that is rev B. Rev A keeps the plan's corners.
* **The RX loop while this station transmits** is a sample-and-hold on the PI integrator's capacitor, good
  for a few milliseconds; table below.
* **Late pin assignment:** I had not been doing it. It is done now (`gen/pin_swap.py`); 18 header pins
  moved.

### The field ports: which jack where

| port | was | now | where |
|---|---|---|---|
| TRIG A, TRIG B, TRIG IN | U.FL | SMA (the board's BWSMA-KWE-Z001) | left edge, x 7, y 25 / 36.5 / 48, barrels outward |
| REF IN | U.FL | SMA | right edge, x 113, y 49, level with JP201 (its line runs under the power column) |
| REF OUT | U.FL | MMCX, vertical | beside the VCXO's buffer, where the U.FL was |
| VC MON, ERR MON, I SLOW MON | U.FL | MMCX, vertical | where the U.FLs were |
| RX MON, TX MON, LO RX MON, LO TX MON | U.FL | U.FL | the 5.8 GHz taps: an SMT launch on the line, and tight |
| I MON, Q MON, Q SLOW MON, CMP I MON | U.FL | U.FL | boxed in by their stages |

The MMCX is Bat Wireless BWMMCX-KE (LCSC C5137198): vertical, through-hole, 0-6 GHz, 500 matings, a
3.6 mm square body, $0.58, 12,841 in stock. Its datasheet is in `datasheets/` and its land pattern is
JLCPCB's own: four 1.6 mm legs on a 2.5 mm square and a 0.92 mm centre drill, checked against the
drawing. The first candidate, BWMMCX-KEF (C5250057), turned out to be edge-mount: its EasyEDA footprint
carries Edge.Cuts lines that would have cut the board. One schematic table (`gen/sch_blocks.JACK`) now
says which jack each named port gets. The silk labels each jack by its kind, and an SMA's name sits inward
of its barrel on any edge.

### One antenna to one other: in the lab, across campus

The two stations take turns. The synthesizers never stop: the HMC536 only moves the antenna between the
transmitter and the receiver, in 30 ns. While a station transmits, its receive loop is held, so its VCXO
keeps the frequency it had locked to the far carrier. When the far station transmits again, its carrier
picks up the same phase, because its synthesizer kept running. The holder decodes the first symbol
coherently, as long as the hold is short (the hold table below). A verification round then goes: the
verifier transmits its idle carrier and the challenge; the prover, locked and listening, switches to
transmit (30 ns, a fixed part of its answer) and replies; the verifier, back on receive, decodes it with
its held loop. While transmitting, a station leaks −17 dBm into its own receiver (27 dB of switch
isolation), which is safe for the LNA; how fast the chain recovers is a bring-up measurement.

Two antennas per station with both carriers always on (frequency division) needs 60 to 73 dB of
isolation between a station's own antennas at 50-200 MHz of spacing (`sim/budget.py` section 4). That
is hard on a bench, so time division is the way.

The reach, at one false event an hour and one wrong message in 10⁴ (the standard derived below; free
space; the budget's antennas, cables and margins):

| scheme | lab, 2 dBi whips, 10 dB indoor margin | campus, 24 dBi panels, 10 m cables | campus, panels, the 2 W module |
|---|---|---|---|
| an event (the BPSK flip) | 37 m | 1.7 km | 16.5 km |
| one bit (A4, below) | 31 m | 1.4 km | 10.9 km |
| two bits, the plan's corners (A3) | 22 m | 968 m | 7.7 km |
| two bits, pilot at 45° + corners (B2) | 29 m | 1.3 km | 10.4 km |

Across campus needs line of sight: 5.8 GHz does not go through buildings.

### The constellation, from first principles

The whole argument is PLAN.md section 18; `sim/constellations.py` computes it and draws
`docs/images/constellations.png`. In five steps:

1. **The two error rates are not alike.** The link idles almost always, so noise that carries the idle
   point over a threshold is a false event. Rice's formula gives its rate: one an hour at the arm's
   94 MHz needs the threshold 7.3 σ from the idle point. A wrong message can only happen when a message
   is sent; one in 10⁴ needs 3.7 σ. So the idle must sit about 1.5 times farther from every message than
   the messages sit from each other, and the threshold between idle and a message belongs 7.3 σ from
   the idle, not halfway. The FPGA can find that place itself by counting each comparator's false
   events while the link is idle, as radar sets its thresholds (CFAR).
2. **Bits are known part-way up the arm's rise.** The filtered signal travels from the idle point to the
   message in a straight line. A threshold set from the idle point, or a line through it, is crossed at
   a fraction of the rise that shrinks as the SNR grows. A line through the origin, like sign(I), is
   crossed at a fixed fraction whatever the SNR: half the rise for a 180° flip, 2.4 ns in.
3. **What limits the transmitter decides the shape.** Against an amplifier's peak limit, the best
   four-message layout keeps the idle at full amplitude and puts the messages near ±90° and at
   180° ± 27°. That is your "+" with its centre point, the one nearest the idle, split in two on the far
   side. This board's ladders limit I and Q separately, so its corners are 3 dB stronger than its axis
   points, which changes the answer.
4. **A comparator per message is cheapest** when the messages are orthogonal: a window on an arm
   against a DAC threshold. Rotated lines need resistor pairs; lines through the idle point need
   AC-coupled arms.
5. **The bandwidth should follow the SNR.** In the lab a 400 MHz arm would decide at 0.3 ns instead of
   0.8 ns. That is too little to matter against 22.7 ns of fixed delay.

The schemes scored (SNR of the axis point in 100 MHz; a star adds 1 dB because the corners sit at the
ADL5611's 12.8 dBm compression point at 5.8 GHz; times are into the arm's rise when every bit is
reliable):

| | scheme | messages | SNR | comparators | lab | 3 km |
|---|---|---|---|---|---|---|
| A1 | BPSK flip, sign(I) | an event | 17.3 dB | 1 | 2.50 ns | 2.95 ns |
| A4 | pilot at 45°, two messages on the receiver's ±Q | 2 | 18.9 dB* | 2 | 0.81 ns | 2.61 ns |
| A3 | corners round a full idle (the plan's QPSK) | 4 | 21.9 dB* | 3 | 2.50 ns | 3.67 ns |
| J1 | your "+", the idle on its right arm | 4 | 20.8 dB | 4 | 3.63 ns | 4.32 ns |
| J2 | your even circle: five points, the idle one of them | 4 | 19.5 dB | 5 | 3.02 ns | 3.72 ns |
| B1 | weak pilot + the four axis points | 4 | 21.4 dB | 4 | 1.03 ns | 3.93 ns |
| **B2** | **weak pilot at 45° + the four corners** | **4** | **19.3 dB*** | **4** | **0.83 ns** | **2.71 ns** |

Your "+" and your even circle both beat the plan's corners on SNR. Both lose on latency, because their
far points are decided by boundaries the signal reaches late. B2 wins both on paper. It needs nothing
new in the transmitter: the pilot comes from nudging the VR_I and VR_Q trims. In the receiver it needs an
I window pair wired like the Q pair. Rev A as drawn does one bit on one edge (A4) or two bits the plan's
way (A3). Whether to add the I window pair before ordering is your call (PLAN.md section 11, question 6);
read the next section first.

### What hardware limits the scores include, and what the tolerance check changed

> **(09:57)** Are your first-principles constellation schemes for idle+2 and idle+4 and idle+N are still
> going, or you can show pictures and give explanations here in the chat? What hardware limitations (e.g.
> comparator threshold issues, analog-level tolerances, etc.) have you taken into account?

The scores include: the noise at the comparators in the arm's real bandwidth (94 MHz, two poles) and the
false-event rate it gives; thresholds set from the idle by counting, which absorbs each comparator's
offset (5 mV max) and hysteresis (3 mV), compared with σ at the comparator (2.9 mV in the lab, 17 mV at
3 km); the comparators rev A really has (sign(I) fixed at zero, QP and QN sharing one V_T, the fast I
arm's trim range); the arm's step response; the ladders' three levels per axis; and the ADL5611's 1 dB
compression at the corners.

Your question made me check what they left out: the angle between the pilot and the messages (section 9
of the script). The modulator's quadrature error is 0.2°, which is nothing. Its carrier feedthrough is
−15 dBc at 5.8 GHz before nulling; added to a weak pilot it turns it. The loop's static phase error is the
Q arm's DC offset over the pilot's slope, and the ADL5380's ±10 mV offset is ±20 mV at one arm output.

| pilot | static phase error, 20 mV offset | feedthrough must be nulled below | cost on one corner |
|---|---|---|---|
| −26 dBc | 58° | −47 dBc | 0.3 dB |
| −20 dBc | 39° | −41 dBc | 0.6 dB |
| −14 dBc | 22° | −35 dBc | 1.3 dB |
| the plan's full idle (A3) | 4.6° | — | — |

Decoding the first edge tolerates 19° at any SNR; decoding the settled states tolerates 1.8° in the
lab. So B2 needs the pilot at about −14 dBc, the feedthrough nulled to −35 dBc, first-edge decoding, and a
DAC trim on the fast Q arm (rev B). Then it needs about 20.6 dB against A3's 21.9 dB and still delivers
both bits on one edge, 1.7 ns sooner. On rev A, the plan's full idle is the robust choice. Still not
modelled: the comparator's longer delay at small overdrive, AM-PM in the compressed gain block, and
interference; the bench measures those.

**How the circuit changes with N.** The loop is identical for every N, because it only ever sees the
idle. Up to four orthogonal messages take one window comparator each. From five to eight round a pilot,
N comparators plus N lines through the pilot (a phase quantizer) cost no more SNR than four.

**When a flash ADC.** A comparator bank is already a one-bit flash with its thresholds on the decision
boundaries. A flash ADC per arm puts its thresholds on a grid instead, and an integrated one adds
pipeline and interface latency. It wins when the boundaries must move faster than a DAC can, at QAM-like
N of 16 and up, or beside the comparators as calibration data.

**What fast receivers do.** Radar sets thresholds from measured noise (CFAR). Electronic-warfare
frequency receivers digitise phase with comparator banks on weighted sums, the phase quantizer above.
Low-latency trading links drop error correction and use repeaters that do not demodulate. None decides
several bits on the first edge after an idle, so the answer here comes from the five steps, not from
precedent.

**DAC trims** help where a threshold must sit off zero or follow the noise (V_T, V_T2, the false-event
servo), where a comparator's 5 mV offset is a large fraction of σ (1.7 σ in the lab, 0.3 σ at 3 km), and
in the transmitter (pilot, carrier null, I/Q balance). They cannot act per symbol: an I2C write takes
about 0.1 ms.

**Two corrections this turned up.** `sim/link_rates.py` used Q(√(2·SNR)) for a sign decision. The right
form behind a 100 MHz low-pass is Q(√SNR): the I noise of a zero-IF arm is both sidebands' worth. An
RF-level simulation confirmed it to 0.5 %. Every coherent range in PLAN.md section 13 was 3 dB optimistic
and is corrected. Its "quiet" standard, 10⁻⁴ errors per decision, still means about 9000 false events a
second on an idle link; section 18's standard costs 6 dB more.

### Holding the receive loop while this station transmits

LOOP_HOLD opens the TS5A3159 in front of the PI integrator. The 100 nF C0G holds VC, the OPA2388 keeps
driving the VCXO, and the RX synthesizer stays locked to the VCXO; only the outer loop is held. The
switch's off leakage is the drift:

| TS5A3159 leakage | VC drift | at 5.8 GHz | phase off by 0.1 rad after |
|---|---|---|---|
| 0.2 nA typical, 25 °C | 2 mV/s | 860 Hz/s | 6.1 ms |
| 2 nA maximum, 25 °C | 20 mV/s | 8.6 kHz/s | 1.9 ms |
| 20 nA maximum, −40 to 85 °C | 200 mV/s | 86 kHz/s | 0.6 ms |

A digital hold would be exact and is not too slow, since the loop runs at 3 kHz and the data never pass
through it. It needs a fast SPI DAC and a faster ADC than the ADS1115, so it is a rev B idea.

### Late pin assignment

I had not done it: the header table was written before placement and kept. Now `gen/pin_swap.py`
reads the placed board and gives the sixteen interchangeable pins to the signals in the order their lines
arrive, right to left, so no two header lines cross. Fixed pins stay fixed: the I2C pair and TR_A/TR_B
(the PYNQ's pull-ups), 18 and 26 (clock-capable on both boards), the fast comparators and the TX ladders
(chosen for their banks, beside their parts), and the rails. Its first version took the 1 k series
resistors as destinations; the placer puts those wherever the pin pulls them, so the assignment chased
itself (14 moves, then 4). It now follows each line through series parts to the chip pin, and re-running
it after the rebuild proposes nothing. The slow comparators are now on pins 40, 32 and 24. PLAN.md
section 5's table is printed from `gen/pins.py`; it had still shown the pre-placement assignment.

### The board

The amplifiers' resistors first. The rules had put the I arm's 4.02 k feedback resistors 10 and 13 mm
from the THS4541's pins, a long summing node on an 850 MHz gain-bandwidth amplifier, which invites
peaking. The Q arm's input lines crossed beside the chip. Both arms now have their feedback resistors
standing against the FB/IN pin pairs, the shunts on the input lines and the gain resistors towards the
demodulator, in mirror image. The I arm's demodulator outputs reached the amplifier in the opposite
order, so ILO now drives the + input and IHI the − input. That inverts I, which nothing minds: the loop
locks 180° round and the idle reads the same sign as before. The slow path's DAC moved from the right
edge to the lower-left corner, beside the four stages it trims. The Q slow monitor's jack turned to face
its resistor.

| build (2026-10-10) | nets in pieces | DRC items | clearance / shorts |
|---|---|---|---|
| Response 9's last (21:15 the day before) | 7 | 6 + 11 unconnected | 0 / 0 |
| jacks + pin swap (08:56) | 5 | 25 + 10 (16 silk over the MMCX legs) | 0 / 0 |
| DAC moved, MMCX silk fixed (09:34) | 3 | 4 + 6 | 0 / 0 |
| amplifiers' resistors at the pins (09:54) | 2 | 5 + 3 | 0 / 0 |

The last build has 3239 tracks and 790 vias. Two nets are still in pieces: SPI_SDATA, walled in at the
RX synthesizer's pin 2, and the LO RX MON tap, walled in at the jack. Four loose track ends and one loose
via remain. ERC and the net check read 0; the schematic has 0 overlaps on every sheet. The board is not
orderable yet.

### What went wrong in this response

* My first version of the swap script doubled a quote in every description it rewrote, which broke
  `gen/pins.py` until I fixed the pattern.
* The swap's first proposal was wrong (destinations at the series resistors), as above.
* The new MMCX footprint's silk circle ran through its own legs; DRC caught 16 silk-over-copper items.
* A scripted refresh of PLAN.md section 13's tables ran to the next heading instead of the table's end
  and deleted 70 lines of prose. The project has never been committed. The text came back word for word
  from an earlier read in this session's transcript, after I checked that nothing had edited it since.
  The documents are now copied to a scratch folder before each scripted edit, and CLAUDE_PCB.md has the
  rule.
* The slow path's DAC (U506) had sat on the right edge since the first placement, and all four of its
  lines crossed the board to the left half. It is now in the lower-left corner beside its stages.
* My scoring script first rejected every scheme: numpy booleans fail an `is False` test.
* I first recommended the weak pilot at −26 dBc from the SNR scores alone. Your question about hardware
  limits made me check the pilot's angle, which showed it needs −14 dBc and a Q-arm offset trim.
* The I arm's feedback resistors had sat 10-13 mm from the amplifier since Response 8's placement rules;
  nobody, me included, had looked at that distance until this response.
* Section 13's claim that "the lowest latency and the longest reach are the same choice" was wrong, and
  the rates script had been 3 dB optimistic since Response 3.

### Decisions

| decision | chosen | why | rejected |
|---|---|---|---|
| trigger jacks | SMA on the left edge | room on the margin; 500 matings and a real cable | MMCX (Jason asked for SMA where there is room) |
| REF IN / REF OUT | SMA right edge / MMCX at the VCXO | REF OUT's nearest edge is taken | SMA at the left edge for REF OUT (pushed the VCXO's loop filter out) |
| MMCX part | BWMMCX-KE, vertical TH | taps are mid-board | BWMMCX-KEF (edge-mount, carries Edge.Cuts) |
| 5.8 GHz taps | stay U.FL | SMT launch on the CPWG; tight | MMCX (a through-hole pin at 5.8 GHz, no room) |
| header pins | bound from the placement | lines arrive in order, none cross | the pre-placement table |
| two-bit constellation | B2 for rev B (pilot −14 dBc, first-edge decoding, Q-arm trim); A3 stays rev A's | 1.3 dB better and both bits 1.7 ns sooner | J1, J2, B1 (worse SNR or late bits); B2 with a −26 dBc pilot (the lock point wanders 58°) |
| I arm input order | ILO to +, IHI to − (I inverted) | the pair arrives uncrossed; resistors at the pins | crossing beside the chip |
| false-alarm standard | one an hour, by counting | the link idles; Rice's law | 10⁻⁴ per decision (~9000 a second) |
| slow-path DAC | lower-left corner | its four outputs all serve the left half | beside DAC 1 (four lines across the board) |

### Next

Routing to DRC 0 (the board section above says what is left), then the real release, then the review
brief to the other reviewers. Your answer to question 6 (the I window pair on rev A) decides whether the
comparator row changes first.


## Prompt 11 (2026-10-10 10:20 PDT)

I don't need to fabricate this board in the next week. We can wait to make it a better test. Can these
different schemes use the same modulators and demodulators but just have different comparators configured
in different ways on the board? How many different configurations can we reasonably try on one board? If
the constraint is making it through the raspberry pi header, we might try integrating the ECP5 on the board
like we did with the ECP5_2ADC_2DAC project. If the limitation is analog signal quality or something else,
we should pick one. If the limitation is just cost (more comparators; more board area), I'd like to explore
how many different hardware schemes are worth trying. You have done a study of latency vs required SNR for
different comparator arrangements of the same idle+4 situation. Are there other design parameters to trade
off besides latency and SNR? If you think it's worth doing a JLCPCB run for revA today or tomorrow, I can do
that. but if it's worth doing a bigger board with more comparator arrangements to really push "how fast can
we get one of N triggers over a 5.8 GHz link as far as possible and with as low latency as possible," I'd be
willing to spend time and money to do the right set of hardware development experiments.

## Response 11 (2026-10-10 10:20 - 10:40)

An assessment; nothing in the design changed.

**Yes, every scheme shares the RF chain.** The LNA, DSA, gain blocks, demodulator, modulator, both
synthesizers and the loop are common to all of them. The schemes differ in four places only: which
signals the comparators look at (I, Q, a weighted sum of the two, or the arms with the idle's DC removed),
where their thresholds sit (DACs), how fast the arm in front of them is, and the decoding in the FPGA. One
thing outside the receiver also differs: rev A's three-level ladders can only make the 3 × 3 grid of
points. The best shapes under a peak limit (section 18) need a finer transmit DAC.

**The binding constraint is the Raspberry Pi header, not analog quality or cost.**

| constraint | what it does | verdict |
|---|---|---|
| the header's pins | 28 signals, 27 used; every fast comparator takes one | binding: rev A is about what fits |
| the header's latency | 200 Ω × 10 pF on the PYNQ, each way: 8.8 ns of the 22.7 ns budget | the largest single term, larger than any constellation gain (about 1.7 ns) |
| analog fan-out | each comparator loads an arm output and kicks charge back when it switches | manageable: one buffer per bank keeps the banks apart |
| cost and area | comparators and their passives are cheap; the ECP5 core (FPGA, power, flash, USB) and six layers are the real cost | acceptable |

So integrating the ECP5, as on ECP5-2ADC-2DAC, removes both header limits at once. The budget's Icepi
row (no header resistors) already shows the effect: 13.9 ns instead of 22.7.

**What one board can carry: about five comparator banks, 24 comparators, an ADC and a DAC.**

1. A window bank: four comparators on I and Q, each with its own DAC threshold. It runs every rev A
   scheme and both pilot schemes (A1-A4, B1, B2).
2. A phase bank: eight comparators on resistor-weighted sums of I and Q at 22.5° steps, with switchable AC
   coupling. It runs the five-point circle, N-PSK round a pilot up to 16 sectors, and the latency-aware
   optimum (lines through the idle).
3. Bandwidth tiers: the window bank repeated behind a wide arm (about 250 MHz) and a slow one (about
   5 MHz). It tests whether the decision bandwidth should follow the SNR, and extends the range at a
   latency cost.
4. A second comparator family: one window bank built with a faster, LVDS-output comparator into the
   ECP5's differential inputs, to measure what the TLV3601's 2.5 ns costs.
5. Two ADC channels on the arms, for calibration and for comparing every comparator bank against a
   digital detector in the FPGA. The fast DAC on the transmit side, with the ladders kept as the
   low-latency path, lets the transmitter make any constellation.

The FPGA time-stamps every comparator edge, which gives first-edge decoding and measures each scheme's
latency and jitter directly.

**Other parameters to trade besides latency and SNR.**

* Timing jitter. An early threshold decides sooner but on the shallow start of the rise, so it jitters
  more. For QPV, jitter widens the verifier's acceptance window.

  | decision-time jitter, 94 MHz arm | crosses at, lab | jitter, lab | jitter, 3 km |
  |---|---|---|---|
  | B2, threshold set from the idle | 0.65 ns | 48 ps | 183 ps |
  | A2, Q step, threshold from the idle | 0.79 ns | 60 ps | 274 ps |
  | A1, sign(I) | 2.42 ns | 23 ps | 135 ps |

* The false-event rate against the wrong-message rate, which section 18 already treats separately.
* Robustness to calibration errors: offsets, carrier feedthrough, I/Q imbalance and the loop's static
  phase (section 18: a weak pilot tolerates them badly).
* Calibration burden: how many DAC trims a scheme needs and how often they drift.
* Peak-to-average power: corners and peaks push the gain block and any PA into compression.
* Occupied bandwidth and regulatory shape, and interference and multipath. Indoor echoes arrive tens of ns
  after the first edge, so first-edge decoding helps there too.
* Dead time: how soon the next event can follow, set by the arm's settling and the comparators' recovery.
* TDD turnaround and the loop's hold time, for one-antenna operation.

**Rev A: worth ordering, but not today.** It needs one more routing pass (two nets, five loose ends) and
the real release, so tomorrow is plausible. Its value is the measurements rev B's banks depend on: the Q
arm's DC offset at 5.8 GHz, the carrier feedthrough, the loop's static phase, how fast the receive chain
recovers after this station transmits, multipath in the lab, and real SNR at range. It also runs four
schemes already, including the latency difference between a threshold set from the idle and sign(I). The
cost is about $1,040-1,210 for everything. Rev B, the comparator lab with the ECP5 on board, can be
designed meanwhile and finalised with rev A's numbers.

## Prompt 12 (2026-10-10 10:33 PDT)

Are there any changes to what should go on revA to better get the data that we need or to make the board
better at measuring these kinds of things in general?

## Response 12 (2026-10-10 10:33 - 10:40)

An assessment; nothing in the design changed. JLCPCB stock was checked at 10:35.

**What rev A already measures, unchanged.** The arms' DC offsets (the ADS1115 averages I and Q with no
signal). The carrier feedthrough (TX MON on a spectrum analyser; VR_I and VR_Q null it). The loop's static
phase (I MON and Q MON on a scope in XY mode while the far board steps through its points). Rice's law and
σ (the gateware's edge counters while V_T is stepped). The receive chain's recovery after its own
transmission (the switch and TX_DIS). The hold drift (LOOP_HOLD, with REF OUT to REF IN taking the
frequency offset out).

**What it cannot measure, and the change that would let it.** In order of value for the cost:

1. **An I window pair, a threshold per comparator, and a trim on the fast Q arm.** Without them rev A cannot
   run the pilot schemes or test section 18's main hardware claim: how the loop's static phase grows as
   the pilot shrinks. The pair is two TLV3601 wired like the Q pair. The thresholds and the trim want five
   DAC channels, and every MCP4728 channel is taken. A third MCP4728 at a new address is not stocked
   (A2 and A3: 0). An 8-channel 12-bit I2C DAC is: the DAC7578SPWR (C1520855, 236 in stock, $13.48).
   Its eight channels give QP, QN, IP and IN their own thresholds, the fast Q trim, and three spares;
   12 bits are 0.8 mV steps against σ = 2.9 mV in the lab. (The 8-bit DAC5578 steps 13 mV, too coarse.)
   Its I2C address must avoid the ADS1115's 0x48. The two header pins: SPARE3, and TR_B freed by
   making TR_B from TR_A with a 74LVC1G04 on the board (12,000 in stock, $0.06), which also ends the PYNQ's
   pull-up holding TR_B high at reset.
2. **A monitor jack on every fast comparator output.** Only sign(I) has one (CMP I MON, 453 Ω into a U.FL).
   The FPGA samples edges at 1-2 ns, but the jitter to be measured is 50-300 ps, so the scope has to see
   the comparators themselves. Four more taps: QP, QN, IP, IN.
3. **A trigger path that bypasses the FPGA.** A DNP 0 Ω from the TRIG IN buffer's output to the TX_Q1 ladder
   bit. With the FPGA holding that pin as an input, a pulse at TRIG IN steps the transmitter straight from
   idle to +Q, and the far board's QP comparator answers. A scope across TRIG IN and the far QP MON then
   reads the link's own latency, without either FPGA.
4. **A wider arm, by rework, with no layout change.** The four 4.02 k feedback resistors now sit at the
   amplifiers' pins. Swapping them for 2.0 k on one board halves the gain and roughly doubles the arm's
   bandwidth (noise gain 9 to 5, about 94 to 170 MHz), which tests whether the bandwidth should follow the
   SNR.

**What does not belong on rev A.** A fast ADC, a finer transmit DAC, a phase-comparator bank, more
bandwidth tiers, faster comparator families: each needs pins the header does not have. They are rev B's,
with the ECP5 on board. The adjustable-hysteresis TLV3603 is stocked 16 deep, too few for a bank.

**The cost.** About $20 more per board in parts. The comparator row and the I2C cluster get re-placed and
re-routed: one or two sessions, so the order moves by a few days.

## Prompt 13 (2026-10-10 10:50 PDT)

JLCBPC stock would be nice, but I think we need to consign anyway, at which point a Digikey or Mouser order
might as well include whatever is best and affordable.

## Response 13 (2026-10-10 10:50 - 11:10)

An assessment; nothing in the design changed. Two of Response 12's picks were made by JLCPCB's stock, and a
third improvement turned up while checking them.

1. **The threshold DAC: AD5696R, two of them, instead of the DAC7578.** A 16-bit quad I2C DAC with its own
   2.5 V, 2 ppm/°C reference and ±2 LSB INL. In the lab, where σ at a comparator is 2.9 mV and the threshold
   sits 7.3 σ from the idle, the false-event rate changes by this much per DAC step:

   | DAC | step | rate change per step |
   |---|---|---|
   | MCP4728 or DAC7578, 12 bits on the 3.3 V supply | 0.81 mV | × 7.6 |
   | MCP4728 on its 2.048 V reference | 0.50 mV | × 3.5 |
   | AD5696R, 16 bits on its 2.5 V reference | 0.038 mV | × 1.10 |

   Mapping Rice's law in the lab, and servoing a threshold to a false-event target, need the fine steps. Two
   AD5696R give eight channels: QP, QN, IP and IN thresholds, the fast Q arm's trim, and three spare. Their
   address pins must keep clear of 0x48, 0x60 and 0x61.
2. **The window comparators: TLV3603 instead of TLV3601.** The same 2.5 ns part with a sixth pin, LE/HYS
   (build/txt/TLV3601.txt, the TLV360x datasheet): driven high, 0 mV of hysteresis; floating, 3 mV; 150 kΩ to
   the negative rail, 30 mV; 56 kΩ, 60 mV; driven low, the output latches. A resistor footprint per
   comparator lets hysteresis be an experiment instead of a constant. For QP, QN, IP and IN.
3. **The hold switch, rewired, no new part.** Today LOOP_HOLD disconnects the error from the integrator's
   20 k input resistor and leaves that resistor's far end on the switch's open terminal, so the switch's
   leakage is integrated. With the switch's spare terminal tied to V_MID and the common pin on the resistor,
   a hold connects the resistor to the integrator's own reference instead. Only the OPA2388's offset and bias
   current remain (`datasheets/OPA2388.pdf`: 0.25 µV and 30 pA typical; 5 µV and 350 pA maximum).

   | case | drift current now | hold to 0.1 rad now | rewired | hold rewired |
   |---|---|---|---|---|
   | typical, 25 °C | 230 pA | 5.7 ms | 42 pA | 13 ms |
   | maximum, 25 °C | 2.35 nA | 1.8 ms | 0.60 nA | 3.5 ms |
   | maximum, −40 to 125 °C | 20.7 nA | 0.6 ms | 1.08 nA | 2.6 ms |

   (A "low-leakage" switch would not have done it: the TMUX1219 is specified at ±5 nA at 25 °C on 3.3 V,
   worse than the TS5A3159's ±2 nA.)

**Unchanged.** The other comparators stay TLV3601. The sub-nanosecond comparators I know of have PECL or CML
outputs, which need translating to reach the header and belong on the ECP5 board. The MMCX could become a
name-brand vertical jack on the consignment order; that is a small gain.

**Cost and logistics.** On the prices visible today (regional distributor pages, some out of stock or on
backorder; US stock is checked on the order day), roughly $40-50 more per assembled board than Response 12's
plan. The consignment grows from three lines to five.

## Prompt 14 (2026-10-10 11:15 PDT)

To put a scope across TRIG IN, I'd like a U.FL or MMCX connector for that.

## Response 14 (2026-10-10 11:15 - 13:08)

Added: **TRIG IN MON**, an MMCX (J208) on the TRIG IN Schmitt buffer's output through 453 Ω (R225), so a
50 Ω scope input sees a tenth of the swing, 0 / 0.33 V, like CMP I MON. The tap is on the buffer's output,
not at the SMA, because that is the edge the FPGA sees and the edge the proposed FPGA-free path (Response 12)
would put on the ladder. It sits in the trigger block above the buffer, at (15.5, 42.5). ERC 0, net check
0, schematic 0 overlaps; the board is being rebuilt.

> **(11:25)** Keep going. If it would unlock interesting tests, I don't mind a few 2-10% price increases.

I took that as the go-ahead for the whole measurement package of Responses 12 and 13, and built it.

**Sheet 7, the window comparators.** QP and QN left the receiver sheet; IP and IN joined them. All four are
TLV3603, each against its own threshold from an AD5696R (16 bits, 0.038 mV a step, I2C 0x0C). Each has two
DNP footprints on LE/HYS (0 ohm to the rail for 0 mV, 150 k to ground for 30 mV; both empty is 3 mV), a 33 ohm
line to the FPGA and a 453 ohm tap to a U.FL for the scope (IP, IN, QP, QN MON). A new sheet keeps the
receiver sheet legible; it connects at the root by net labels.

**The header.** TR_B left it: a 74LVC1G04 beside the antenna switch makes TR_B from TR_A, so the switch rests
in receive on both hosts. J303 moved to the antenna sheet (TR_A, TR_B, ground). The I window's two lines
joined the pin swap's pool, kept off the Icepi's bank 0: CMP_IP is on pin 22, CMP_IN on pin 16. Every
header signal pin is now used.

**The rest of the package.** The freed MCP4728 channel (DAC 1 C) trims the fast Q arm through 100 k
(Q_OFF_F). The hold switch is rewired: NC takes the error, NO ties the integrator's input resistor to
V_MID on a hold. A DNP 0 ohm from the trigger buffer's output to TX_Q1 gives the FPGA-free trigger path.

**The gateware.** Ports follow the pin table (cmp_ip and cmp_in in; tr_b and spare3 gone). The comparator
monitor counts all eight comparators' edges (EDGE_CNT6-7 at 0x2C-0x2D are the I window), CMP_STATE grew to
11 bits, CTRL[5:4] are retired and CTRL[8] makes TX_Q1 an input for the bypass. Lint is clean, the
testbench passes (it now checks TX_Q1's high-impedance state and the new counters), and the Icepi build
closes at 105 MHz against 50.

**Documents.** PLAN.md sections 4 (three parts), 5 (the header, regenerated from `gen/pins.py`), 11 and 18
(rev A now runs every window scheme, B2 included); BRINGUP.md stage 3 (the thresholds by counting, the
hold) and stage 4 (the schemes against each other, the link without either FPGA); the gateware README
(the registers and how to write the thresholds).

**The board.** Eight builds took it from 11 DRC items to none:

| build | end | nets in pieces | DRC items | what changed |
|---|---|---|---|---|
| r14 | 11:19 | 2 | 11 (6 violations, 5 unconnected) | the window comparators placed |
| r14b-c | 11:55, 12:07 | 5, 1 | 13, 10 | the I arm rewired at its pins; U402 clear of the RF2 line |
| r14d | 12:27 | 5 | 10 (1, 9) | `gen/tidy.py`, the last copper pass |
| r14e-f | 12:40, 12:52 | 1 | 2, 3 (unconnected) | tidy joins first, then trims stubs back to their last contact |
| r14g-h | 13:06, 13:20 | 0 | 0 | the SPI bus routed first of the signal nets |

`gen/tidy.py` lets KiCad's own connectivity decide what touches. A track end KiCad calls dangling is joined
to same-net copper within 0.45 mm, or trimmed back to where other copper meets it. A dead via is removed
only after every join is made: removing one first took a whole path with it. The final board has 3682
tracks and 931 vias; tidy joined 2 near misses and removed 3 dead pieces. SPI_SCLK had been walled in by
later nets in three builds running; routing the bus first ended that.

## Prompt 15 (2026-10-10 13:08 PDT)

Keep going, but the SMAs (and maybe the other test points, U.FL, and MMCX connectors) are not clearly labeled. There should be a bif-font silk screen right next to the connector, so it's obvious what it's for. For example, "TRIG A" seems fine, but "TRIG B" is between two SMAs and off to the side compared to the ""TRIG A" label. If there are SMAs in a row, their labels should all be in the same relative orientation: for example,  all above and closest to the thing they refer to or all Southwest and closest to the thing they label. This consistency requirement needs to be enforced and should be put in the CLAUDE_PCS.md silkscreen and schematic labeling sections.

## Response 15 (2026-10-10 13:08 - 20:10)

**You were right, and it was worse than TRIG B.** The silkscreen alone, rendered by KiCad, showed:

- **No name at all** on four of the five top-edge SMAs (RX ANT, TX ANT, SW TX, SW RX) or on TRIG IN. The
  labeller tried a list of spots, found the RF parts under each jack in the way, and dropped the label
  with one line in the build log.
- **TRIG IN MON's name under TRIG B**, where it read as a third line of TRIG B's label.
- **Mixed sides in rows.** The window monitors had three names above and one below. The rail pads
  alternated above and below.
- **A real bug.** JP101 and JP102 printed "Q-" at pin 1, but the netlist puts Q_P on pin 1. The jumpers
  were labelled backwards.

**The rule.** A row is connectors of one footprint in a line. The SMAs along one edge are one row however
far apart; taps or pads a few millimetres apart are one. Every name in a row stands on the same side of
its own connector, at the same gap, centred on its signal pin the same way, at the same angle and size.
Its limit follows the name the same way, or is printed once when the whole row shares it. Each name
must be unmistakably its own: from its near end, where a reader ties it to a part, no other connector or
header is nearly as near. Big means 1.5 mm for an SMA and 1.0-1.2 mm for a tap or a pad. The rule is
now in CLAUDE_PCB.md section 6 (silkscreen, under Connectors) and section 4 (schematics, "Labels in a row
stand alike"). Section 6's jumper rule gained the lesson of the reversed labels.

**How it is enforced.**

- **Planned.** `gen/placement.py` decides each row's side (`LABEL_ROWS`) and each header's label layout
  (`HEADER_LABELS`). It reserves those strips before the small parts are placed, so the passives keep
  out of them; a part placed by hand inside one is reported.
- **Placed.** `gen/silk_jacks.py` places each row as a unit: the planned side first, then the others,
  the biggest size first. A placement counts only if every member's label is free, is its own, and keeps
  0.8 mm from other connectors' labels. Labels placed later (chip names, designators) keep clear of
  connector names, by 2 mm along a name's own line.
- **Checked.** `tools/label_check.py` reads the written board with KiCad's own text boxes, independently
  of the placer. It checks that every name is present, big enough and its own, that each row holds one
  relation, and that every limit is present and in line. Every build runs it, and `mfg/make_release.py`
  refuses a board that fails it. One limit is left off on record: TRIG IN MON's, whose level is every
  /10 tap's.

**The rows as built** (all checked on the routed board):

| row | names | limits |
|---|---|---|
| top edge: RX ANT, TX ANT, SW TX, ANT, SW RX | left of each SMA, level with its pin, 1.5 mm | under each name, flush right |
| left edge: TRIG A, TRIG B, TRIG IN | right of each SMA, level with its pin, 1.5 mm | under each name, flush left |
| REF IN, alone on the right edge | under it, 1.5 mm | under the name |
| window monitors QP, QN, IP, IN MON | under each U.FL, 1.0 mm | once, under the row |
| the eight rail pads | above each pad, turned, 1.0 mm | - |
| the other taps, each alone | beside it, mostly under | beyond the name where it fits |

The headers get the guide's selector layout: the two choices beyond the outer pins and the function
above the middle ("Q+ [o o o] Q-" with "SIGN B1"). Where the room is above the pins instead, each pin's
name stands above itself (JP102, JP103, J303).

**What moved on the board to make room.**

- **Trigger column.** U205 and its 1k moved off TRIG IN's pin line, to just above it. TRIG A and TRIG B
  moved up 1 mm. J208 moved to (16.6, 40.2), between TRIG B's label and its own.
- **Window monitors.** The four U.FL moved up 1 mm, clear of JP301.
- **Test pads.** They moved 4.6 mm right, clear of F302, and J303 moved to x 103.2.
- **Loop block.** JP102 moved 2.5 mm right and J502 0.3 mm up, so J502's name fits between them.
- **Small parts.** The reserved strips pushed some passives. I measured each against the pin it
  serves. Where one got worse I pinned it back (C602, R605, R141, R142, R519). Where a better spot
  existed I took it: TX LO's BIAS_FILT cap went from 7.8 mm to 4.5 mm, its REG cap from 13.6 mm to 6.1 mm.

**Shorter limits on the silk** (the schematic notes keep the full text): SW TX "+29 dBm MAX", SW RX "to
RX ANT", TRIG IN "in: 5.5 V MAX", TRIG A and B "3.3 V, 2 V/50R", the /10 taps "0-0.3 V/50R", the slow
monitors "0-3.3 V, 1k", the LO monitors "0 dBm, 50R". Names may cross a via: every via is tented, so the
ink lands on solder mask. Never a pad or a hole.

**New tools.** `gen/board.py --silk` redoes only the silkscreen on the last build's copper in two seconds.
`gen/board.py --place --with-silk` shows whether labels fit before any routing. `LABEL_DEBUG=<ref>`
prints why a row's planned side fails.

The labels held through every build since: the label check gives 0 violations on each routed board, and `mfg/make_release.py` refuses a board that fails it.

**What went wrong in this response.** My first placement moves cascaded through the rule-based placer:
a cap went 18 mm from its pin and the ADC's input resistor 17 mm. I caught them by measuring every moved
part against its pin, then pinned or re-placed them. My first ownership test measured from the label's
box and failed a name centred right under its own jack. My second measured from the label's centre and
failed long vertical names. Measuring from the near end is what holds.

> **(15:33)** The CLAUDE_CODE_CHAT.md for this conversation should be in the CostasLink-PYNQ-Z2 directory,
> not in the top-level OpticsPCBs directory. This should be true of all such conversations. They are
> specific to the project or the board, not OpticsPCBs as a whole. Move it there and update it there.

Moved. Response 1 (2026-10-09 00:30 - 02:50) had been written to `OpticsPCBs/CLAUDE_CODE_CHAT.md` by
mistake; it now sits in this file between Prompt 1 and Prompt 2, word for word, and the top-level file
is gone. Every other prompt and response was already here, and this file is the one being updated.
CLAUDE_PCB.md section 1 ("Log everything") now says the log lives in the board's own directory, never at
the repository's top level.

> **(15:40)** Keep going on the routing. Make the board bigger if you need to. Hand route if you need to.
> Actually look at the problem and come up with a specific or a general fix for it. If the fix is general,
> document the problem and fix in CLAUDE_PCB.md

> **(16:12)** Whatever created the "875mm of unnecessary GND routing" should probably addressed in
> CLAUDE_PCB.md to prevent future agents from making a similar mistake.

**The routing (15:40), and what laid the 875 mm (16:12).** Four nets failed in every build of
Response 14 whatever the router did: eight net orders, a wider rip-up, smaller pours. So the router was
not the problem. I built the planned-copper stage alone and looked at it as the router receives it.

- **The cause.** The planned stage gives every chip pin a fan-out line, and a pin the fan-out could not
  serve was routed "whole" while the board was still empty. For a ground pin the whole net is GND, and
  this ran before the stage that drops a via beside each ground pad. So every bare ground pad was a piece
  of its own, and the router joined them all to each other on the top layer: 875 mm of track in 580
  segments, between U112's pin rows and along the comparator strip. The via stage then found every
  ground pad already joined and placed no vias. Its log had said "0 ground vias" in every build, and
  nobody read it. The loop block's top layer was fenced before the first signal: VC's 2 mm hop from U112
  pin 7 to its capacitor was walled into 48 cells.
- **The fixes** (`gen/routes.py`, `gen/tidy.py`):
  - Ground and the poured rails are never routed whole: each pad gets its own stub and via.
  - Every build prints each plane net's copper per layer and the vias the via stage placed. After the
    fix, GND on the signal layers is 288 mm in 550 stubs, with 173 ground vias.
  - Short connections go first: every pair of a signal net's pieces within 5 mm is joined before any
    long net is routed (72 of 95 joined that way).
  - The +3V3_DIG pour on In2 shrank to the comparator strip that needs it; it had closed 73 % of In2 to
    the signals. In2's cost for signals dropped from 6 to 3.
  - A track that ends inside its own via, off the via's centre, is joined to the centre by a segment no
    wider than 0.15 mm. KiCad does not count such an end on an inner layer as connected, and the cleanup
    pass had been removing the via as dangling.
- **The board after them:** DRC 0 at every severity with schematic parity, the label check 0, and the
  release passes all its gates.
- **CLAUDE_PCB.md section 5** gains five lessons:
  - never route ground or a poured rail whole (the 875 mm, with the check that would have caught it);
  - join a net's short connections before routing any net whole;
  - count what an inner layer's pours leave for the signals;
  - join off-centre track ends to their via's centre;
  - when the same nets fail whatever the router does, the wall was laid before the router ran: look at
    the planned stage alone, with no cleanup on it.

> **(16:35)** Keep going to finish the board. Then start writing the gateware.
>
> Where possible, keep SystemVerilog (or Verilog) generic enough to be used on both the PYNQ-Z2 and also
> the Icepi Zero. For the Icepi Zero, you've written "bare" systemverilog and used it to communicate
> results over a "bare" UART. You've also written wrappers for LiteX peripherals. Code and information
> about the history of that is in the CLAUDE_CHAT under $HOME/mudd/133electronics/icepi-zero-dac-adc.
>
> You've written other firmware for the PYNQ-Z2 and RFSoC in this repo and in ~/DroneSDR (probably under
> GPS* or GPSDO*). You  decided to start from .tcl files to generate the block designs that I can look at. I
> vaguely remember that Vivado prefers Verilog to SystemVerilog is some context (maybe double clicking a
> block in the GUI and editing). If it makes more sense to use Verilog for those reasons, do that. If
> SystemVerilog to be compatible with the tuorials, do that.  There are many versions of Vivado available
> under /home/jason/Downloads/Xilinx/. Pick the one that is most compatible with the latest version of
> PYNQ that runs on the PYNQ-Z2 board.
>
> As you write the gateware, the most important thing is to pay close attention to any bugs you find or
> improvements that we should make for revA of the schematic and the PCB. Make a list of such changes and
> either do them in parallel, or do them later from your list.

> **(16:45)** Keep going. Remember to keep the gateware generic enough to run all of the experiments that
> we'd want to do, including the ones in the bring-up plan.

**The gateware is written, tested and built for both boards, and writing it found a board bug that is now
fixed: the transmitter was on whenever no gateware drove it.** The details follow; `gateware/README.md` has the
full description and the register map.

**The choices.**

- **Verilog-2005, not SystemVerilog.** You remembered right: a Vivado block design takes a module
  reference only with a Verilog top. Yosys reads the same files, so one source serves both boards.
- **Vivado 2024.1.** PYNQ 3.1, the newest image for the PYNQ-Z2, is built with it. (The GPSDO's 2022.1
  bitstream also loaded on 3.1.1.)
- **Tcl, as before.** `gateware/pynq/build.tcl` makes the project, the block design (the PS, a clock
  wizard, a SmartConnect, the core as a module reference) and a PDF of the diagram. It refuses to
  publish a bitstream that misses timing.
- **The Icepi talks over a bare UART at 1 Mbaud** (`uart_cmd.v`'s "W aa dddddddd" / "R aa"). LiteX was not
  needed: no soft CPU is in the way of any experiment, and a LiteX CSR wrapper is a few lines if one is
  wanted later.

**The architecture: one core, three thin tops.** `costaslink_core.v` holds everything the experiments
need. A board contributes only a sampler, its clocks and a way in to the register bus:

| | PYNQ-Z2 | Icepi Zero |
|---|---|---|
| sampler | ISERDESE2 8:1 DDR at 400 MHz: **800 Ms/s** (1.25 ns) | IDDRX1F: **200 Ms/s** (5 ns) |
| fabric | 100 MHz from FCLK0 through a clock wizard | 100 MHz from the 50 MHz oscillator through an EHXPLLL |
| bus | AXI-Lite from the PS (`axil_bridge.v`) | UART (`uart_cmd.v`) |
| result | 4989 LUTs, 9 BRAM tiles; WNS +1.66 ns, WHS +0.03 ns | 9697 LUT4s, 7 DP16KD; 101.7 MHz |

`regmap.py` is the register map's one source: it generates `regmap.vh` for the RTL and the README's
table, and the Python driver imports it.

**What it does, for every experiment in BRINGUP.md.**

- **Transmitter** (`tx_engine.v`):
  - modes: the first firmware's TXSYM and BPSK pattern; events every period or on TRIG_IN; PRBS
    symbols (N = 2-8); rotation (FSK); one point held (the arms' offsets, the carrier null);
  - messages fixed, counted or from five PRBS polynomials;
  - a gate from the sequencer for time division.
- **Receiver** (`rx_engine.v`), at the sampler's resolution:
  - one decoder serves every scheme of PLAN.md section 18: an idle vector and an event mask; a
    32-entry table of the settled vector or of the first-fired set;
  - confirm or veto by the slow comparators;
  - references from this board's TX event or TRIG_IN; false and missed events;
  - latencies to the sample, with minimum, maximum and mean; an 8 x 8 confusion matrix; a 1024-bin
    latency histogram;
  - a self-synchronising PRBS check on CMP_I for the BER.
- **The T/R sequencer and the counting gate** (`seq_gate.v`):
  - the sequencer: eight steps of TR_A, LOOP_HOLD, TX_DIS and the TX gate, for the hold experiment
    and time division;
  - the gate counts edges and high samples of all nine comparators and the RX events: the
    false-event servo and the offset nulling run on it.
- **A logic analyser in block RAM** (`capture.v`):
  - stores every fast sample, with the pins, the slow comparators and the decoder's marks;
  - triggers on a TX event, an RX event, a decision, TRIG_IN, any comparator change, a sequencer
    step, or the bus.
- **The Python driver** (`gateware/driver/costaslink.py`):
  - one class over MMIO (PYNQ) or the UART (Icepi);
  - the schemes A1-B2 with their tables computed from a comparator model, including the Costas
    loop's 180-degree twin;
  - the I2C parts by name (the AD5696R thresholds, both MCP4728s, the ADS1115), the DAC EEPROM
    defaults, the synthesizers;
  - and the stages' operations: stage 1's scan, threshold scans with a Rice fit, the false-event
    servo, slow-offset nulling, loopback latency, BER, the hold and time division.

**How it is tested.**

- `make sim`: the UART top, the SPI and I2C words.
- `make sim-engines`: every engine against a loopback model.
- `make sim-axil`: AXI-Lite in every order SmartConnect may use. Taking the data one clock early fails
  it, so the test can fail.
- The ISERDESE2's bit order, in Vivado's simulator with the UNISIM model.
- `make sim-driver`: the Python driver's operations against the RTL, through two named pipes, 15 tests.
- The rewritten PRBS against the old one, clock for clock over 200 000 clocks.

The tests found real bugs:

- The capture buffer read its newest word as its oldest.
- Its "filled" flag lied: it was set whenever the write pointer wrapped. It now counts the words written
  since the arming.
- The BER count never restarted. Enabling the check now starts one.

**Timing.** The first full core closed at 44 MHz on the ECP5. It now makes 100 MHz on every rebuild:
`make pnr-icepi` tries seeds until one passes, and five of seven do. Each step kept every latency exact
in samples:

- fine times as an OR, not an add;
- the decision a clock after the event;
- the PRBS with look-ahead, its advance a clock late behind two flip-flops;
- the read path registered three times, with the bus registered beside each block;
- the capture trigger and the counter RAMs' reads through a register;
- the sequencer's outputs registered;
- bus writes last in their block;
- the zero tests as registers;
- the priority encoders registered;
- the table lookup and the latency sum a clock each.

The same work gave the PYNQ its margin; its worst path had been the reset's fan-out.

**Rev A: what the gateware found** (`REVA_CHANGES.md`, seven entries).

- **The transmitter was on whenever no gateware drove TX_DIS** (entry 2, fixed).
  - Why it happened: DSOP had a 100 k pull-down, and the ADL5375 transmits with DSOP low or floating.
    The board has its own USB-C supply, so a host that was off, unconfigured, booting PYNQ's base
    overlay or loading another one left the modulator running. The synthesizers stayed programmed from
    the last run, and nothing sent the identification.
  - Why a pull-up alone would not cure it: an unpowered host's pin clamps the line to about 0.6 V.
  - The fix: header pin 24 is now **TX_EN, high = transmit**. U206, a 74LVC1G04 beside the modulator,
    makes DSOP = not TX_EN. R227, 1 k, holds TX_EN low: the Zynq's configuration pull-ups reach 0.35 V
    at worst, and a high through the PYNQ's 200 ohm still reads 2.35 V or more. R209 is now a pull-up
    on DSOP.
  - The gateware's CTRL[0] keeps its meaning (TX_DIS, reset 1); the three tops drive tx_en = not tx_dis.
- **The latch enables floated** (entry 3, fixed). LE_PLL_TX, LE_PLL_RX, LE_DSA, TRIG_A and TRIG_B had no
  resistor, so a floating LE could load a word into a synthesizer. R314-R318 are 100 k to ground.
- **Checked, no change:**
  - LOOP_SEL floating (it matters only with JP103 on FPGA);
  - TR_A going to transmit when the host is off (the modulator is off then);
  - the radio's reference into the FPGA for coherent time stamps: TRIG_IN is clock-capable on both
    hosts, so it is a cable from REF OUT, no board change;
  - the samplers;
  - the ECP5's IDDRX2F banks (entry 1).

**The board with them** (20:01): 382 parts. Two rebuilds were needed.

- The first left LE_PLL_RX in pieces. The placer had hung R315 12 mm off U115's crowded LE side; it is
  now pinned above header pin 33.
- The next left TX_EN unjoined by KiCad's count. The router ran the line past R227's pad, 0.05 mm clear
  of its corner, and no cleanup pass looked for an isolated pad. `gen/tidy.py` now asks KiCad's
  connectivity which pads nothing reaches and joins each to its line (CLAUDE_PCB.md section 5).

The result: 3784 tracks, 1054 vias; DRC 0 items at every severity with schematic parity; the label check
0; the release passes every gate. The overlay and the Icepi's bitstream were rebuilt for TX_EN: WNS
+1.66 ns, and 101.7 MHz.

**Documents.**

- `gateware/README.md` is rewritten.
- PLAN.md section 8 says what exists; its header table has TX_EN.
- BRINGUP.md:
  - stage 0 has the gateware's status and a new item 5: the Icepi's sample order checked with one
    jumper before the board exists;
  - stage 1's current is now 0.85 A, the modulator idling disabled.

**Not here yet:**

- the Gardner loop and the whitened stream;
- the Q bit's BER;
- the sample clock from the radio's reference;
- IDDRX2F on the Icepi (400 Ms/s).

**What went wrong.**

- I edited sources while Vivado ran. Its out-of-context run of the module reference went stale, and
  the core came out a black box.
- Vivado 2024.1 crashed (exit 139) on morse_keyer's variable part-select of a parameter. I bisected it
  and rewrote it as a generate loop.
- Yosys merges duplicated registers even when they are marked keep, so the per-block bus copies did
  nothing on the Icepi until each was its own keep_hierarchy module.
- My first pipe testbench raced the model on TRIG_IN and on the knobs, so it reported a TRIG_IN latency
  2 samples long and missed a flipped bit. Every command now ends on a falling edge.
- I ran `gen_xdc.py --help`; the script takes no options, so it rewrote the three constraint files from
  the same table.
- The first rebuild with the rev-A parts left LE_PLL_RX in pieces. The placer had hung R315 12 mm off
  the RX synthesizer's crowded side. It is now pinned beside header pin 33.

> **(19:46)** Keep going. Just like in the latest GPSDO board, if it costs more than a few dollars to have
> JLCPCB solder the raspberry pi connectors,  I'll do thst myself. I'd like them to do SMAs and small-pin
> headers.

**It costs $38 before duty, $52 with it, so J302 is yours to solder.** J302 was the only part on the back,
so fitting it made the order two-sided:

| what fitting J302 added | cost |
|---|--:|
| a second Standard setup | $25.75 |
| a second stencil | $8.27 |
| its Extended feeder | $2.70 |
| 40 joints on each of two boards | $1.26 |

With J302 off, JLCPCB assembles the top only. The SMAs, the MMCX and U.FL jacks and the 2.54 mm headers
(JP101-JP103, JP201, JP202, JP301, J303) stay on JLCPCB's through-hole line, as you asked. That keeps
Standard PCBA (Economic takes no through-hole parts) and the fixture.

- **What to buy.** `mfg/release/hand_solder_bom.csv` lists:
  - J302: LCSC C2977589, the socket the GPSDO's J4001 uses; order it loose;
  - a new row for the jumper shunts: C5305, 6 a board, with each jumper's position. Nothing listed the
    shunts before, and the loop does not work without JP101-JP103 fitted.
- **The order.** Assembly Side is "Top Side", JLCPCB's default now, with one setup and one stencil.
  JLCPCB comes to $777-792 with duty and shipping (it was $829-844). COST_ESTIMATE.md,
  ORDER_SETTINGS.md, PLACEMENT_CHECKS.txt and PLAN.md section 17 all say so.
- **A cost bug.** `make_release.py` had charged the two-sided setup and stencil whatever the sides. It now
  charges per side, as the GPSDO's model does, and `cost_estimate.py` takes the sides from the placement.
- **BRINGUP.md** stage 1 now starts with soldering J302 (pin 1 at the right-hand end of the bottom edge,
  square to the board) and fitting the shunts. The bench list has both parts.
- **CLAUDE_PCB.md** section 8's "Nothing hand-soldered" now carries your exception, with the arithmetic to
  redo on every board.


## Prompt 16 (2026-10-10 22:50 PDT)

What is the order of operations if I want to consign parts from Digikey and have Digikey mail them directly to JLCPCB? When do I place the digikey order? On JLCPCB, do I do the board order and assembly together and somehow point it to the consigned tracking number or something?

## Response 16 (2026-10-10 22:50 - 22:58)

JLCPCB changed its overseas consignment process on 12 August 2026, so the order of steps matters more
than it used to. **Register with JLCPCB and get its approval first. Then have Digi-Key ship. Place the
board-plus-assembly order last, once the parts are in your JLCPCB stock.** Nothing in the board order
points at a tracking number.

**Order of operations**

1. **Register the parts at JLCPCB.** Go to Parts Manager > Consign Parts.
   - Add the three parts by JLCPCB code, 4 of each: C2837312 (the balun), C579150 (ADL5375-05) and
     C579152 (ADL5380).
   - Choose "Outside Mainland China".
   - Enter Digi-Key's unit prices (the declared value must equal what you pay), the HS code, country of
     origin and so on. Attach a Digi-Key quote or cart as pricing evidence.
   - They review the price within 2 business days.
2. **Pay once approved.** You pay a deposit for Chinese import duty and VAT, refunded after the parts are
   used. You also pay a handling fee of 2 % of the declared value, $10 minimum. For about $130 of parts
   that is $10.
3. **Then place the Digi-Key order.** Ship it to the Hong Kong warehouse address exactly as JLCPCB's flow
   shows it, by DHL, FedEx or UPS. Packages shipped before approval may be sent back.
   - If JLCPCB insists on an actual invoice at registration, place the Digi-Key order with a scheduled
     ship date a few business days out. You get the paperwork now, and it ships after approval.
   - Both ADI parts are listed as ECCN 5A991.b, so Digi-Key may ask for an end-use statement for Hong
     Kong. Answer it quickly ("university research") or the order sits on hold.
4. **Enter Digi-Key's tracking number** in the consignment record when it arrives by email.
5. **Wait for "in warehouse".** JLCPCB counts the parts against what you declared, the status reaches
   in-warehouse, and the parts sit in your consigned stock for up to three years.
6. **Then place the board and assembly together as one order.** That is a PCB order with PCB Assembly
   turned on. In the parts-matching step, the three consigned lines should show your consigned stock as
   the source. The link is the part code, not a tracking number. Their help pages do not say outright
   whether you can place the order before the parts arrive. For their own Global Sourcing parts they say
   a part can be used only once it reaches the warehouse, so I would wait.

Roughly: approval in 2 days, shipping 3-5 days, a few days to count them in. So place the board order
about 1.5-2 weeks after you start.

**Two alternatives**

- **JLCPCB Global Sourcing** (Parts Manager > Order Parts > Global Sourcing Parts). JLCPCB buys from
  global distributors for you, with free shipping and no consignment paperwork. It is slower: 1-3 days of
  review plus usually 9-20 business days of purchasing. It suits the 33-cent balun, where the $10 minimum
  fee and the shipping outweigh the part.
- **Buy the two ADI chips from JLCPCB's own stock.** On 9 October they had 4 ADL5375 (exactly the 4
  needed) and 18 ADL5380, about $15 more than Digi-Key. Then only the balun has to come from elsewhere.
  Stock can vanish before order day.

**The release's own instructions are now out of date.** `mfg/release/CONSIGNMENT.md` describes the old
process: a Shenzhen warehouse, posting by USPS, shipping before approval. Its $35-60 shipping estimate
also does not count the handling fee or the duty deposit. Following it as written could get the package
sent back. Shall I update the release's consignment section and cost line to this process?

Sources: jlcpcb.com/help/article/how-to-consign-parts-to-jlcpcb (the overseas user guide);
jlcpcb.com/news/jlcpcb-launches-compliant-overseas-component-consignment-service (12 August 2026);
jlcpcb.com/help/article/important-note-before-you-consign-the-part-to-jlcpcb (the older process);
jlcpcb.com/help/article/how-to-consign-parts-to-jlcpcb-from-mainland-china;
jlcpcb.com/help/article/how-to-use-jlcpcb-global-sourcing-parts-service; the ECCNs from JLCPCB's
C579152 and LCSC's C579150 listings.

## Prompt 17 (2026-10-11 01:27 PDT)

I want to do a design review like I did for the GPSDO-PYNQ-Z2 and ECP5-2ADC-2DAC and ~/mudd/OWLternatingCurrent boards. In fact, I've started by making empty design_review_* directories for the other LLMs to put their results in. I want you to make a version of the DESIGN_REVIEW_PROMPT.md that lives in these other projects, but adapted to this project. Point the LLMs at CLAUDE_PCB.md. Ask it to consider potential problems that we didn't even ask about. Make sure the other LLMs only work inside of their own directories, and only modify files in those directories. They should write their reports in those directories and not touch git (because others are using this directory). As usual, you should log this request for a prompt as its own prompt in our ongoing CLAUDE_CODE_CHAT.md. Let me know when I'm ready to set the other LLMs loose.

## Response 17 (2026-10-11 01:27 - 01:55)

**The brief is `DESIGN_REVIEW_PROMPT.md`, and the whole project is committed on `master` with a clean working tree:
the reviewers can start.**

**The brief.** It follows the ECP5 round-2 brief's structure (ground rules, the standard as checks, tools, known
items, what to send back) in the GPSDO brief's voice, with CostasLink's facts.

- **§0, ground rules.**
  - Each reviewer works only in its own directory: `design_review_Gemini3.8Flash/`, `design_review_GPT-5.6Terra/`,
    `design_review_Grok4.6/` or `design_review_KimiK3/` (a new one makes `design_review_<Name>/`).  The report is
    `DESIGN_REVIEW_<Name>.md`.
  - Nothing outside that directory may be modified.  Anything that writes runs in a copy made inside the directory
    (an rsync recipe, 50 MB).
  - No git commands that change anything.  The tree is committed and clean at the start, and `git status` must show
    only the reviewer's own directory at the end.
  - The writers are named one by one, including the gateware's `make`, `gen_xdc.py` (even its `--help`) and
    `jlc_query.py`, which writes its cache.
  - Each reviewer forms its own findings before reading the others', then adds a section on agreement and dispute.
  - The verdict and the findings table come first, written as it goes, because the chat is not kept.
- **§1-§2:** what the board is for, with the plan's numbers, and the build of 2026-10-10 20:01 with the claim to
  break: "ready to order, apart from the CPL rotations and the consignment".  It also lists what changed most
  recently and so is least reviewed: TX_EN, the pull-downs, J302, the gateware.
- **§3:** the author's ten least-confident points, from the concept against its purpose to the generated method
  ("look at the actual copper").
- **§4, the problems nobody asked about,** as you asked: RF exposure and the band's rules, the field (ESD and
  lightning on long cables, heat, power banks, cable strain), interference, the experiment's validity, bring-up
  blind spots, the documents, the order.  "Spend real time here."
- **§5:** `../CLAUDE_PCB.md` as the standard.  Every applicable rule is checked, quoted with its section; the gates
  the build does not run are run in the copy; rules that are wrong or missing are reported.
- **§6-§8:** where everything is, the read-only commands, the known open items, and the report's layout.

**The checks on the brief itself:**
- Every read-only command in §6 ran here with its output in the scratchpad.  Comparing the tree's file times before
  and after showed one write: `tools/jlc_query.py` adds to its cache.  So that query moved to the copy-only list.
- The copy recipe works.  A copy of 50 MB rebuilds everything in 9 minutes, giving the same 3784 tracks and 1054 vias
  and DRC 0, and the gateware's five test targets pass in it.  The shared tree was untouched throughout.  The brief
  now says "about 10 minutes", not 15-25.
- rsync does not create a missing parent directory, so the recipe now starts with `mkdir -p`.
- The brief had claimed that `CONSIGNMENT.md` was being rewritten, which nobody asked for.  It now says only that
  the file is out of date (Response 16).

> **(01:38)** If nothing about this CostasLink is checked in yet, check in all of the relevant files. Be sure to
> .gitignore what should be ignored. If the the LLMs do stuff, I want to be able to recover with git.

> **(01:39)** Keep gong on everything you're working on and on the checking. Also make sure CLAUDE_PCB.md is checked
> in. The other LLMs should start with a clean git repo on the main branch.

> **(01:47)** Keep going.  I would not be sure that other boards' gitignore rules are perfect. They grew up over time.
> There is a tradeoff when considering checking in "derived" products. We want some, like the gerbers, BOM, and any
> images that are in markdown files, so don't ignore something just because it can be rebuilt. On the other hand,
> don't dump everything in.

> **(01:48)** Some projects are meant to be public, in which case we avoid checking in copyrighted things like
> datasheets (usually gitignoring the whole datasheet directory) Others are private, and we have checked the
> datasheets in so others in the research group can get them. This one can be treated as private, but might turn
> public, in which case we can not check the datasheets into the public version.

**Committed: one commit on `master`, with CLAUDE_PCB.md (your uncommitted edits and Response 15's lessons), the
`.gitignore`, and CostasLink-PYNQ-Z2.**

What is tracked:
- every source: `gen/`, `tools/`, `sim/`, `mfg/*.py`, `gateware/` with the driver, the build scripts;
- the documents and this log;
- the board as built: the seven sheets, the board with its zones filled, `hardware/lib/`, and `hardware/checks/`
  (netlist, DRC, ERC, labels);
- the release: Gerbers as a folder and a zip, the BOM, the CPLs, the assembly drawings, the order and cost notes;
- `docs/images/`: the schematic PDF and PNGs, the block diagrams, and the board renders, refreshed from this build
  because PLAN.md says `docs/images/board_*.png` keep the last and they were from 9 October;
- the earlier self-review in `design_review_Claude/`;
- the datasheets: 48 PDFs, tracked while the repository is private.  The `.gitignore` says that a public version
  must drop `datasheets/`, and that nothing else depends on it, because `build/txt/` has their text.

From `build/`, only what the documents cite or a reviewer needs is tracked:
- the budget, link-rate, constellation and cost JSONs;
- `COST_ESTIMATE.md` and `link_rates.md` (PLAN.md section 17 and BRINGUP cite them), and `constellations.txt`;
- the placement and the route report;
- the datasheet texts;
- `scratch/pin_audit.md` (BRINGUP stage 0 cites it).

Left out:
- the rest of `build/`: logs, the KiCad and Vivado scratch, 15 MB of debugging renders, the simulation scratch;
- the Vivado reports, which name this machine's paths;
- the JLCPCB API caches, which are stamped and go stale by design;
- `QUESTIONS.md`, a working note by the old rule (PLAN.md section 11 carries its questions; the brief points
  there);
- the reviewers' private copies (`design_review_*/repo/`) and Vivado's strays (`gateware/NA/`, `.Xil/`, journals);
- the four empty review directories: git cannot track an empty directory.

**Absolute paths.**  The grep over everything tracked found:
- your own words in Prompt 15's quote (where the Vivado versions are), kept verbatim as the ECP5 log keeps its
  own;
- two vendor STEP models whose headers name their authors' machines: vendored files keep their headers;
- the Vivado reports, now left out.

**Ready.**  Start each LLM in `CostasLink-PYNQ-Z2/` with: "Read DESIGN_REVIEW_PROMPT.md and follow it.  You are
<Name>; your directory is design_review_<Name>/."

## Prompt 18 (2026-10-11 22:00 PDT)

The other LLM's reviews are in. Fix the legitimate schematic and PCB and other problems that they found. Summarize with a ranking of how useful and insightful each reviewer was

Then, simulate the trajectory from "idle" to each of the 4 states at the receiver. Show i and Q as function of time. Do this starting with your chosen component values and the chip's specs. In the plot, also show the threshold and outputs of Comparator. Somehow show both the fast and slow paths. It should be clear from these plots thst the I and Q signals themselves have some slower timescale, corresponding to a 100 MHz bandwidth (if that's correct), but that for high SNR, the decision of where it's going can be made early on in the trajectory.
Then show a second type of plot: the path on the I/Q plane, using dots of equal time with different dots every 10 nanoseconds (or whatever would help interpret the time scale in the plot). Draw the comparator regions on these plots, such that visually, one could see how long each trajectory would take to trigger the Comparator thresholds.
Do a few additional simulations with noise added to get a sense of that. Noise runs can be shown on these plots with very transparent alpha. These plots, along with the others, should all be presented in a very clear and pedagogical way in a markdown file describing the setups.

As usual, log this prompt and your response in the CHAT file. Be sure to show the plots in your response, including here in the chat, so I can comment on them from my phone.

## Response 18 (2026-10-11 22:00 - 2026-10-12 00:25)

**Build 18 fixes what the four reviewers found.  The worst was the LO pairs: they were crossed, and one leg
ran 4× the other.  The board routes completely (DRC 0 items), and the release passes every gate
(2026-10-12 00:19).  The trajectories are in [`docs/TRAJECTORIES.md`](docs/TRAJECTORIES.md); the plots were
sent to the chat.**

**The fixes** (DESIGN_REVIEW_RESPONSE.md reconciles every finding; REVA_CHANGES.md entries 8-21):

- **The LO pairs** (KimiK3, from the copper).  The MAX2871's RFOUTA_P faces the mixer's LOIN, so the P-to-LOIP
  pair had to cross.  One leg ran 10 mm, the other 42-44 mm round the chip.
  - Both sheets now take P to LOIN and N to LOIP.  Inverting the LO inverts I and Q together, which sign(I)·Q
    ignores.
  - The DC blocks and the chokes stand as mirror images, in a corridor.
  - A gate fails the build over 0.5 mm of skew.  Now 10.76 / 10.76 mm (RX) and 11.76 / 11.76 mm (TX).
- **The RF and LO net classes bound no net** (Gemini3.8Flash).  They are now bound by exact names from the
  router's own walks, with a zone rule for the 0.25 mm CPWG gap.  The board is refilled in a fresh KiCad
  process: in-process, KiCad had filled by a default project and written it over the .kicad_pro, which gave
  479 DRC errors on the first try.
- **Paddle vias** (Grok4.7): 3 × 3 at 0.8 mm in the 2.6 mm paddles.  Vias now also go in the SKY65404's paddle
  and the ADL5611 tabs (11 in all).
- **Kd was twice the real one** (GPT-5.6Terra): U110 passes one leg against V_MID.  R126 20 k → 10 k (fn
  2.9 kHz, ζ 0.68).
- **The ADL5375's N-side bias divider** carried the chip's own 2 × 41 µA: 0.61 V instead of 0.51 V.  Now
  4.7 k / 750 Ω, which gives 0.507 V.
- **I/Q SLOW MON** moved ahead of the 4.8 MHz pole (CLAUDE_PCB.md section 9).
- **C320**, a 100 µF polymer (0.1 Ω ESR), damps a hot plug on +5V_IN.
- **Three fiducials and the copper layer numbers**, as netless graphics.
- **The SW TX limit:** +29 → +25 dBm, from the HMC536's guaranteed numbers.
- **The budget:**
  - the ADL5611's 5.8 GHz row (P1dB 12.8 dBm, NF 6.0 dB);
  - NF by Friis (2.0 dB: every range shrinks about 6 %; PLAN.md's tables are refreshed);
  - the THS4541's guaranteed CM limit (61 mV of margin at the worst corner);
  - the 5 V path at its maxima (≥ 4.89 V from 5.10 V).
- **Gateware lint** under Verilator 5.051.  All testbenches pass; Vivado WNS +1.661 ns; the Icepi reaches
  105.7 MHz.
- **The documents:** PLAN.md and BRINGUP.md corrected and extended.  BRINGUP.md now covers the supply, the
  power order, setting the DSA before judging lock, the summing nodes, TRIG IN into 50 Ω, and the field list
  (the PA through the switch, exposure, arrestors, heat, the second harmonic).

**What I rejected, with reasons:**

- GPT's "impedance control = respin": a step costs about 0.1 dB.  Free standard impedance control is
  insurance for the order day.
- Gemini's "LO matched within 0.1 mm": false.
- Kimi's APR argument: the APR already includes the VCXO's own tolerance.
- Kimi's invented cross-references.

**The reviewers, most useful first:**

1. **KimiK3.**  It found the worst defect by parsing the copper, plus five more findings no one else had.
   Its citations are unreliable.
2. **Grok4.7.**  The most accurate, with the best-calibrated severities, and two findings no one else had
   (the window comparators at power-up, the PTC's derating).
3. **GPT-5.6Terra.**  The sharpest single catch (Kd), the narrowest review.
4. **Gemini3.8Flash.**  One important catch (the netclasses), but a confident false confirmation of the LO
   pairs.

**The trajectories** (`sim/trajectories.py`).  The chain is the board's own:
- the PYNQ header RC, the ladder node and the ADL5375 on the transmitter;
- the ADL5380 and the THS4541 at 94 MHz on the receiver;
- TLV3601s with 2.5 ns and 3 mV;
- the slow stage ×20, clipped, into 1 k / 33 pF;
- the gateware's own decoder table.

Noise is 40 runs per corner at the bench SNR (38.2 dB) and the 3 km SNR (22.6 dB).  The four time plots,
the I/Q plane, the slow plane and the latency against SNR are in the markdown file, explained panel by
panel.  What they show:

- **"100 MHz" is right for the receiver's arm** (3.9 ns rise).  End to end the rise is 6.6 ns, because the
  PYNQ's 200 Ω header resistors into about 10 pF add 4.4 ns at the transmitter.
- **High SNR buys early decisions.**  The CFAR window sits 7.5 σ from the idle: 0.60 a at 3 km, crossed at
  8.2 ns; 0.10 a on the bench, crossed at 5.2 ns, a tenth of the way into the rise.
- **sign(I) is crossed at mid-rise at any SNR** (A3's I bit).  B2 avoids that.
- **The slow path confirms Q about 6 ns after the fast event, and I about 25 ns after it.**  Its I starts
  saturated.
- **All 320 noisy decisions were right.**

> **(23:31)** Keep going, but don't forget to write any lessons learned, which would be valuable for future PCB work,
> into CLAUDE_PCB.md.

**Lessons in CLAUDE_PCB.md:**

- section 4: each equation's inputs at the guaranteed figure, the operating row, and the load the next stage
  really sees;
- section 5: check that a pair's pins face each other; build placement variants in parallel against a chaotic
  router; reserve every labelled connector's strip;
- section 10, gates 20-21: net classes must bind; paddle vias against the land pattern;
- section 11: LoadBoard's cached default project; the DRC and the connectivity API disagree on a dangling end;
  a clean-up pass must be idempotent (snap_to_vias had duplicated 786 segments);
- section 14: a link's rise time includes the transmitter's pins.

> **(23:42)** Keep going, but I had some questions about your trajectory plots. Maybe I'm misunderstanding what some
> of the signal names mean, but why aren't CMP_QP and CMP_QN always complementary? Also, is there a "data valid"
> signal so the FPGA knows when the comparators are valid and should be trusted? For example, if there is an idle
> state and also 00, 01, 10, and 11, how will the FPGA not accidentally think that it went from idle to 10 when it
> should have waited a tiny bit longer to see that it actually went from idle to 11?

**QP and QN are a window round Q = 0, not the sign of Q.**  At the idle (Q = 0) both are low; QP fires above
+t·a and QN below −t·a.  A sign comparator would sit on the idle, and the noise would toggle it into false
events.

**The "data valid" is made in time by the gateware, and the table refuses half-finished vectors:**

- The event is the first sample with QP or QN off its idle value.  The decision reads all five fast
  comparators 4 samples (5 ns) later.
- The decoder's table maps only the vector each message settles to.  A vector in transit (I between its
  windows) matches no message and counts as undecided, never as the nearer one.
- The time plots now carry a strip with the table's view at every instant: idle, then "in transit" from 8.4
  to 12.7 ns, then the message.  The decision lands well inside the message.
- The slow path then confirms or vetoes.  With B2, each message moves one comparator alone, and the first
  edge is the whole answer.

TRAJECTORIES.md has a section on this.

> **(23:56)** Keep going, but is the a received signal strength indicator, so that this can be monitored in operation
> and used during setup to insert our remove external amplification or attenuation stages?

**There is no detector chip** (PLAN.md section 4 left the AD8318 out).  But with the loop locked, I is the
carrier's amplitude, and the DSA's setting is what the level needed.

- The driver now has `received_dBm(ext_db)`: the DSA plus the I arm on the ADC, about −90 to −28 dBm at RX
  ANT, or referred to the antenna through an LNA module or pad.
- It also has `agc()`, which steps the DSA to the regulated −20 dBm and so restores the loop gain.  Both are
  tested (17 driver tests).
- BRINGUP.md stage 5 uses them:
  - the DSA pinned at 0 dB with the level low: add the LNA module;
  - pinned at 31.75 dB with the arm high: add a pad.
- Unlocked, RX MON on the analyser is the reading.
- A lock-independent detector on the RX coupler's monitor port is a rev B option (REVA_CHANGES 21).

**Found on the way:**

- The router is chaotic.  Moving the slow tap walled in DAC 2's pins, then a comparator input, then U305's
  ground, then the MAX2871's CE.  Four placement variants built in parallel copies settled it, twice.
- `snap_to_vias` duplicated its joining segments on every tidy pass; it is now idempotent, with a dedupe.
- KiCad's DRC and its connectivity disagree on a stub ending mid-track; the refill now asks kicad-cli.
- REF OUT's limit text lost its place to a re-placed resistor.  R121 is anchored, and REF OUT should join
  the label rows (a lesson).

**Not done:**

- CONSIGNMENT.md's procedure text: the release rewrote its table, not the process.
- The fractional-N re-centre in the driver.

## Prompt 19 (2026-10-12 01:05 PDT)

You should always be adding relevant files, .gitignore'ing files that you're sure should not be in the repo, and committing at the end of each reasonable step. You are running alone now, but in general, it's good to check for other LLMs working on this repo in this directory so that you can be conservative about what you do to git, so that you don't stomp on them.

Also, what does DSA mean? Define it when you use it in docs/TRAJECTORIES.md.

## Response 19 (2026-10-12 01:05 - 01:15)

**The DSA is the digital step attenuator: U102, a PE43711 between the LNA and the gain blocks, 0 to
31.75 dB in 0.25 dB steps, set by the FPGA over SPI.  It is the receiver's gain control.  TRAJECTORIES.md
now says so at its first use, and expands LNA, GBW, SNR, kTF and CFAR the same way.**

**Committed in two steps, after checking for other agents:**

- Nothing else was changing the tree.  The running Claude sessions in OpticsPCBs (GPSDO, ECP5, the top
  level) dated from September or early October, `git status` showed only this project's paths plus
  CLAUDE_PCB.md and .gitignore, and nothing outside it had been written in three hours.
- A stale `.git/index.lock` blocked the first `git add`.  It was empty, from 2026-10-11 02:14 (inside the
  review window), and no git process was running, so it went.
- `git fsck` finds two missing trees.  They belong only to three `refs/agents/.../checkpoints` refs that
  some agent host left; every object reachable from master, ecp5-2adc-2dac, icepi-maze-router and
  origin/master is present.  Those refs are not this project's to delete; they are left as they are.
- **1ba4b42**: the four reviews as received.  The machine paths in Grok4.7's run logs and scripts and in
  KimiK3's notes were made relative.  The `.gitignore` note now says a public version must also drop the
  datasheet PDFs and extracts the reviewers copied.  Their private tree copies (`repo/`) stay ignored.
- **The next commit**: build 18 (Responses 18-19): the fixes, the release, TRAJECTORIES.md and its
  script, the driver's RSSI, CLAUDE_PCB.md's lessons, this log.  `build/trajectories.json` joins the
  tracked build outputs, because the document cites it.

From now on each finished step is committed (memory: commit-each-step).

## Prompt 20 (2026-10-12 01:11 PDT)

If we used an Icepi Zero or redesigned the board to use a SYZYGY connector on a Brain-1 or added an ECP5 directly on the board like in the ECP5_2ADC_2DAC PCB, what could or should change about the architecture and chosen ICs? Or would the only change to the estimates in TRAJECTORIES.md be the lack of safety resistors and the faster TX and RX there?

## Response 20 (2026-10-12 01:11 - 01:25)

**For the Icepi Zero with this board, almost only the resistors change, but only if its gateware
samples at 656 Ms/s.  At today's 200 Ms/s the 5 ns grid gives all the gain back.  With a SYZYGY port or
an ECP5 on the board, more should change: LVDS comparators and a time-to-digital converter.  The radio
itself and its ~94 MHz arm stay.**  [`docs/HOSTS.md`](docs/HOSTS.md) has it in full (`sim/hosts.py`: the
trajectory model with each host's terms swapped in).  Below, the event times run from TX register to RX
register, at the bench and at 3 km.

| host | bench | 3 km |
|---|---|---|
| PYNQ-Z2 (rev A) | 10.9 ± 0.38 ns | 14.0 ns |
| Icepi, today's gateware | 10.7 ± 1.44 | 12.7 |
| Icepi, GDDRX2 (same board) | 8.9 ± 0.44 | 10.9 |
| SYZYGY with TLV3604 LVDS comparators (0.8 ns) | 7.0 | 9.0 |
| the same with a carry-chain TDC | 6.4 ± 0.07 | 8.4 |

- **Widening the arm buys 0.1 ns at the bench and loses range.**  The CFAR window moves out with the
  noise bandwidth, so the ~94 MHz arm stays right.
- **The floor is about 6 ns:** the FPGA's own buffers 2.5, the RF chips 1.6, the radio's rise 1.4, the
  comparator 0.8.
- **SYZYGY rev B.**  The 28 header signals exactly fill one Standard port as single-ended pins; five LVDS
  pairs need five more.
  - The pin plan keeps everything fast on one port and moves the I2C devices and three slow lines off it.
  - VIO stays 3.3 V, with 100 Ω terminations on the board (the SYZYGY radio board's conclusion).
  - The pod needs a DNA.  Keep the USB-C power: 1.34 A may exceed the port's budget.
  - The GTP transceivers are not for comparators.  PLAN.md's 6.25 Gb/s is corrected to 3.75 Gb/s on the
    XC7Z012S-1.
- **An ECP5 on the board** adds room for:
  - ADCs (an unlocked RSSI, a digital AGC, a digital confirm path; the AD9238's 7-clock pipeline keeps
    the analog slow path for latency);
  - a DAC for shaped waveforms (slower to a step than the ladder, which stays);
  - SPI threshold DACs;
  - the radio's reference as the sample clock.

  It is a new board, from the ECP5-2ADC-2DAC pipeline.
- **The cheapest win is gateware on any host, the PYNQ included:** a TDC (REVA_CHANGES 22-24).

CLAUDE_PCB.md section 13 has the lesson: add up every term host by host, sampling included, before
choosing a host.

## Prompt 21 (2026-10-12 01:30 PDT)

For a different, future project, if I wanted to push the latency even lower, what would be the knobs to change? How far could the current ICs be pushed by changing passives? Where is the first IC (or FPGA) bottleneck, and what would it be changed to? Would we widen the over-the-air bandwidth? Eventually would we need to change to a different (higher) center frequency? Go to a different architecture all together? As decision latency is lowered, how does cost balloon? Write up some results in PLAN.md as some far-future exploration. Make a table, where each row is a lower system latency. Columns include what would need to change and its approximate delta$ and total$. Show the table here too.

## Response 21 (2026-10-12 01:30 - 01:40)

**PLAN.md section 19.**  `sim/latency_roadmap.py` steps through the knobs with the trajectory model.  The
figure of merit is the prover's turnaround: an ideal step at the RX SMA to 50 % of the answer at the TX
SMA, electronics only (QPV bounds exactly this).

| # | turnaround, bench | at 3 km (with the PA) | what changes | Δ$ (two nodes) | total $ |
|---|---|---|---|---|---|
| 0 | ~71 ns | ~71 ns | rev A as built (A3 through the registered decoder at 100 MHz; an estimate) | — | ~$1.2-1.4k |
| 1 | 13.6 ns | 13.4 ns | gateware: B2's first edge through a combinational LUT path; a TDC alongside | $0 | ~$1.2-1.4k |
| 2 | 10.8 ns | 10.7 ns | a bare-pin host (Icepi Zero) | −$120 to $0 | ~$1.1-1.4k |
| 3 | 9.1 ns | 8.9 ns | rev B: TLV3604 LVDS comparators (SYZYGY or on-board ECP5) | ≈ +$1.5-2.5k | ≈ $2.6-3.9k |
| 4 | 2.4 ns | 2.3 ns | the fast path leaves the FPGA: SiGe comparators (ADCMP572) into a CML gate driving the modulator | ≈ +$1-2k | ≈ $3.6-5.9k |
| 5 | 1.7 ns | 1.7 ns | ~1 GHz baseband, ~2 GHz on the air (not in 5.8 GHz's ISM or amateur bands) | ≈ +$2-5k | ≈ $6-11k |
| 6 | 1.3 ns | (hundreds of m) | 60 GHz: HMC6300 / HMC6301, InP comparators, horns | ≈ +$15-30k | ≈ $20-40k |
| 7 | ~0.2-0.5 ns | — | optical free space, an InP / SiGe gate | ≈ +$50-100k | ≈ $70-140k |

**The answers:**

- **Passives on the current chips buy about 0.5 ns of ~11.**  The ladder node at 100 Ω saves 0.33 ns; the
  arm at gain 2 or 1 saves 0.09-0.14 ns and loses at 3 km.
- **The first bottleneck is gateware.**  Rev A's registered decoder would be ~59 of the ~71 ns.
- **The first chip bottlenecks are the FPGA's pin-to-pin path (~5 ns) and the TLV3601 (2.5 ns).**  The
  answer is LVDS comparators, then taking the fast path out of the FPGA into CML.  That last step has the
  best value: 3.8× for ~$1-2k.
- **The next bottleneck is the ADL5380's 390 MHz baseband.**
- **Widen the air bandwidth: only late.**  It buys ~0.7 ns, and the 5.8 GHz bands cannot hold it.
- **A higher centre frequency: only for the spectrum.**  60 GHz is short-range (oxygen at 15 dB/km);
  E-band (71-86 GHz) for kilometres.
- **A different architecture (optical) below ~1 ns.**
- **The energy bound: no decision comes sooner than t ≥ z²·N0/P.**  That is 85 ps at the bench but 3.1 ns
  at 3 km with the board alone.  So at range, power is a latency knob, and the $29 PA cuts the bound to
  31 ps.
- **Cost balloons after row 4:** each step costs several times the one before and buys less.

The HMC6300/6301, ADCMP572 and Brain-1 prices were not found in public listings (≈ in the table).  A
lesson went into CLAUDE_PCB.md section 14.

## Prompt 22 (2026-10-12 01:41 PDT, three messages pasted from Digi-Key)

````
Brain-1 is $450, 


16 LFCSP-VQ
ADCMP572BCPZ-RL7
IC COMPARATOR 1CH 16-LFCSP
Analog Devices Inc.
1,309
In Stock
1 : $30.18000
Cut Tape (CT)
1,500 : $19.55525
Tape & Reel (TR)
Tariff may apply if shipping to the United States
-
Tape & Reel (TR)
Cut Tape (CT)
Digi-Reel®
Active
with Latch
1
CML, Complementary
3.1V ~ 5.4V
2mV @ 3.3V
25µA @ 3.3V
20mA
52mA
65dB CMRR, 74dB PSRR
0.165ns
±1mV
-40°C ~ 85°C
16-WFQFN Exposed Pad, CSP
Surface Mount
16-LFCSP (3x3)

16 LFCSP-VQ
ADCMP572BCPZ-R2
IC COMPARATOR 1CH 16-LFCSP
Analog Devices Inc.
506
In Stock
1 : $34.29000
Cut Tape (CT)
250 : $23.55672
Tape & Reel (TR)
Tariff may apply if shipping to the United States
-
Tape & Reel (TR)
Cut Tape (CT)
Digi-Reel®
Active
with Latch
1
CML, Complementary
3.1V ~ 5.4V
2mV @ 3.3V
25µA @ 3.3V
20mA
52mA
65dB CMRR, 74dB PSRR
0.165ns
±1mV
-40°C ~ 85°C
16-WFQFN Exposed Pad, CSP
Surface Mount
16-LFCSP (3x3)

16 LFCSP-VQ
ADCMP572BCPZ-WP
IC COMPARATOR 1CH 16-LFCSP
Analog Devices Inc.
33
In Stock
1 : $30.18000
Tray
-
-
Tray
Active
with Latch
1
CML, Complementary
3.1V ~ 5.4V
2mV @ 3.3V
25µA @ 3.3V
20mA
52mA
65dB CMRR, 74dB PSRR
0.165ns
±1mV
-40°C ~ 85°C
16-WFQFN Exposed Pad, CSP
Surface Mount
16-LFCSP (3x3)


16 LFCSP-VQ
ADCMP580BCPZ-RL7
IC COMPARATOR 1CH 16-LFCSP
Analog Devices Inc.
1,235
In Stock
1 : $30.97000
Cut Tape (CT)
1,500 : $20.10601
Tape & Reel (TR)
Tariff may apply if shipping to the United States
-
Tape & Reel (TR)
Cut Tape (CT)
Digi-Reel®
Active
with Latch
1
CML, Complementary
±4.5V ~ 5.5V
10mV @ ±5V
30µA @ ±5V
44mA @ 5V
8mA
60dB CMRR, 75dB PSRR
0.18ns
1mV
-40°C ~ 125°C
16-WFQFN Exposed Pad, CSP
Surface Mount
16-LFCSP (3x3)

16 LFCSP-VQ
ADCMP580BCPZ-WP
IC COMPARATOR 1CH 16-LFCSP
Analog Devices Inc.
0
In Stock
Check Lead Time
1 : $30.97000
Tray
-
-
Tray
Active
with Latch
1
CML, Complementary
±4.5V ~ 5.5V
10mV @ ±5V
30µA @ ±5V
44mA @ 5V
8mA
60dB CMRR, 75dB PSRR
0.18ns
1mV
-40°C ~ 125°C
16-WFQFN Exposed Pad, CSP
Surface Mount
16-LFCSP (3x3)



Mfr Part #
Quantity Available

Price
Price by Quantity
Tariff Status

Series
Package
Product Status
Type
Frequency
Contents
Antenna Type
Utilized IC / Part

EK1HMC6350
EK1HMC6350
EVALUATION KIT ASSEMBLY
Analog Devices Inc.
1
In Stock
1 : $6,385.19000
Box
Tariff may apply if shipping to the United States
-
Box
Active
Transmitter, Receiver
60GHz
Board(s), Cable(s), Power Supply
-
HMC6300, HMC6301

EV1HMC6300BG46
EV1HMC6300BG46
HMC6300BG46 EVALUATION PCB
Analog Devices Inc.
1
In Stock
1 : $1,587.52000
Box
Tariff may apply if shipping to the United States
-
Box
Active
Transmitter
57GHz ~ 64GHz
Board(s)
-
HMC6300BG46
````

````
65 WLBGA
HMC6300BG46TR
V-BAND EWLB PKG TRANSMITTER
Analog Devices Inc.
357
In Stock
1 : $25.91000
Cut Tape (CT)
500 : $18.29462
Tape & Reel (TR)
-
-
Tape & Reel (TR)
Cut Tape (CT)
Digi-Reel®
Active
-
57GHz ~ 64GHz
General Purpose
FSK, ISM, OOK
-
13.9dBm ~ 17dBm
0.08mA ~ 56mA
Analog Signal, Digital Signal, SPI
Not Included
-
Multiple Channels, Analog and Digital Data
2.565V ~ 2.835V, 3.9V ~ 4.1V
-40°C ~ 85°C
-
-
Surface Mount
65-VFBGA, WLBGA
65-WLBGA (6x4)

65 WLBGA
HMC6300BG46
RF XMITTER ISM 57-64GHZ 65VFBGA
Analog Devices Inc.
0
In Stock
Check Lead Time
1 : $25.91000
Tray
Tariff may apply if shipping to the United States
-
Tray
Active
Not Verified
57GHz ~ 64GHz
General Purpose
ISM
-
15dBm
29mA
SPI
-
-
-
4V
-40°C ~ 85°C
-
-
Surface Mount
65-VFBGA, WLBGA
65-WLBGA (6x4)

65 WLBGA
HMC6300BG46P7
V-BAND EWLB PKG TRANSMITTER
Analog Devices Inc.
48
In Stock
1 : $25.91000
Strip
-
-
Strip
Active
-
57GHz ~ 64GHz
ISM
FSK, ISM, MSK, OOK
-
13.9dBm ~ 17dBm
0.08mA ~ 56mA
Analog Signal, Digital Signal, SPI
Not Included
-
Multiple Channels, Analog and Digital Data
2.565V ~ 2.835V, 3.9V ~ 4.1V
-40°C ~ 85°C
-
-
Surface Mount
65-VFBGA, WLBGA
65-WLBGA (6x4)
````

````
75 WLBGA
HMC6301BG46TR
V-BAND EWLB PKG RECEIVER
Analog Devices Inc.
303
In Stock
1 : $25.91000
Cut Tape (CT)
500 : $18.29462
Tape & Reel (TR)
-
-
Tape & Reel (TR)
Cut Tape (CT)
Digi-Reel®
Active
57GHz ~ 64GHz
-
-
AM, FM, FSK, ISM, MSK, OOK
ISM
-
SPI
-
Not Included
Image Reject Filter, On-Chip Temperature Sensor
1.3V ~ 1.48V, 2.565V ~ 2.835V
-40°C ~ 85°C
-
-
Surface Mount
75-VFBGA, WLBGA
75-WLBGA (6x4)

75 WLBGA
HMC6301BG46P7
V-BAND EWLB PKG RECEIVER
Analog Devices Inc.
12
In Stock
1 : $25.91000
Strip
-
-
Strip
Active
57GHz ~ 64GHz
-
-
AM, FM, ISM, OOK
ISM
-
SPI, USB
-
Not Included
SPI digital interface
1.3V ~ 1.48V, 2.565V ~ 2.835V
-40°C ~ 85°C
-
-
Surface Mount
75-VFBGA, WLBGA
75-WLBGA (6x4)


EK1HMC6350
EK1HMC6350
EVALUATION KIT ASSEMBLY
Analog Devices Inc.
1
In Stock
1 : $6,385.19000
Box
Tariff may apply if shipping to the United States
-
Box
Active
Transmitter, Receiver
60GHz
Board(s), Cable(s), Power Supply
-
HMC6300, HMC6301

EV1HMC6301BG46
EV1HMC6301BG46
HMC6301BG46 EVALUATION PCB
Analog Devices Inc.
1
In Stock
1 : $1,587.52000
Box
Tariff may apply if shipping to the United States
-
Box
Active
Receiver
57GHz ~ 64GHz
Board(s)
-
HMC6301BG46
````

## Response 22 (2026-10-12 01:42 - 01:50)

**The costs are now line items.**  `sim/latency_roadmap.py` builds each row's two-node link from
line items (`build/latency_roadmap.json` lists every one).  The total is what that row costs to build
directly; Δ is that total less the row before.  Jason's Digi-Key prices are exact; the rest are marked ≈.
The ADCMP572's delay is now Digi-Key's 165 ps; row 4 is 2.43 ns.

| # | bench | 3 km + PA | what changes | Δ$ | total $ |
|---|---|---|---|---|---|
| 0 | ~71 ns | ~71 ns | rev A as built | — | $1,220-1,260 |
| 1 | 13.6 ns | 13.4 ns | combinational gateware path | $0 | $1,220-1,260 |
| 2 | 10.8 ns | 10.7 ns | bare-pin host (Icepi Zero) | ≈ −$120 to $0 | ≈ $1,100-1,260 |
| 3 | 9.1 ns | 8.9 ns | TLV3604 LVDS into an ECP5 on the board (or two Brain-1 at $450: $1,900-2,000) | ≈ +$30-90 | ≈ $1,130-1,350 |
| 4 | 2.4 ns | 2.3 ns | 8 ADCMP572 at $30.18 into CML gates, outside the FPGA | ≈ +$430-960 | ≈ $1,560-2,300 |
| 5 | 1.7 ns | 1.7 ns | passive I/Q mixers, GHz FDAs, wideband antennas, ~2 GHz on the air | ≈ +$520-1,460 | ≈ $2,080-3,760 |
| 6 | 1.3 ns | (hundreds of m) | 60 GHz: four HMC6300/6301 at $25.91 ($104), a Rogers board (≈ $2k) or four eval PCBs ($6,350), horns, InP comparators | ≈ +$3-10k | ≈ $5-14k |
| 7 | ~0.2-0.5 ns | — | free-space optical (≈ $11-33k a node) | ≈ +$20-65k | ≈ $26-80k |

**What changed in the conclusions:**

- **The steps are cheaper than the first guesses.**
  - Row 3: the ECP5 on the board costs about what the hosts it replaces cost.
  - Row 4: still the best value, 3.8× for ≈ $0.4-1k, less than doubling the total.
  - Row 6: the 60 GHz chips are $104 for four.  The board and horns are the cost, and ADI's evaluation
    PCBs are the quick way in.
- **The shape stands:** past row 4 each step costs several times the one before and buys less.
- **The ADCMP572 over the ADCMP580:** one 3.3 V supply instead of ±5 V, and 2 mV of offset instead of
  10 mV, for less money and 15 ps less delay.

## Prompt 23 (2026-10-12 02:04 PDT)

I want you to add information about E-band (71–86 GHz, light-licensed) and more detailed options for free-space optical. We've played with free-space optical for the quantum photons. I don't know if we did it in the best or most economical way, but I bought used 80-100mm William Optics telescopes ($2-3k) and used Rainbow Astro and iOptron HAE series mounts ($2-4k). We made a slow pointing feedback system with a 90/10 beam splitter to a ZWO ASI camera and a dichroic beam splitter to inject a beacon laser or a classical TX path. Random thorlabs optics, stages, and 30 mm Cage Cube hardware was another very big expense, even for this simple system. We had no fast tip/tilt and just used multimode fibers, though this would probably need to change at very low latencies. For classical comms, we were using slow 50 MHz LED-based plastic-fiber links that were probably meant for factory-floor links. We were eventually planning on upgrading to a better fiber transceiver modules, but had no great way of coupling them in and out of the telescopes. We switched to RF because it was cheaper for the range of latencies we actually needed for the first few QPV demonstrations, but eventually we'll want to do other quantum networking, which will require lower latency RF or optical free-space heralding and control signals. Feel free to start over to start here with our "used gear + Thorlabs stuff" system and improve it. Write an optics version of table, whose rows I'd like you to put on the same plot in the same way as before.

### Interjection (02:07)

While you are doing that, also look into fancier FPGAs  with fancier transceivers. I've done work with the RFSoC 4x2 board and the ZCU102. Would either of these help, or do the transceivers, even in the most "raw" mode, still benefit throughput more than latency?

### Interjection (02:13)

Keep going, but I was talking about the 100G ethernet on the RFSoC in addition to the higher latency RFDC on board

### Interjection (02:20)

Also, if widening the RF bandwidth from 100 to 150 MHz doesn't help much at 5-6  GHz, does it make sense to narrow it a bit to 80 MHz or even 40 MHz to slot ourselves into the existing WiFi channel scheme to more easily avoid interference from (and interference to) WFi? What are the tradeoffs there?

## Response 23 (2026-10-12 02:04 - 02:27)

PLAN.md section 19 has four new subsections.  `sim/optics_roadmap.py` and `sim/wifi_channels.py` are
new, and `sim/latency_roadmap.py` gained an E-band row and plots the optical rows with the RF ones.  The
web lookups covered:
- the ADMV7310/7410 datasheets;
- the FCC's E-band licensing;
- QICK's RFSoC loopback;
- FSM prices;
- the ADMV evaluation boards at Richardson.

**E-band (row 6E of the RF table): 1.24 ns at the bench, 1.25 ns at 3 km, ≈ $5.7-20k.**
- ADMV7310 / ADMV7410: 71-76 GHz, I/Q to 2 GHz, 25 dBm P1dB, 5 dB NF.  The bare chips have no public
  price.  The evaluation boards are $2,606.81 and $2,053.22 at Richardson.
- Oxygen absorbs 0.3-0.4 dB/km.  The link budget is 51.6 dB in 100 MHz at 3 km with 43 dBi dishes.
  Rain at ~5 dB/km gives 1.38 ns; heavy rain (~10 dB/km) loses the window.
- The licence: a non-exclusive nationwide licence, then link registration with a database manager,
  with antennas of at least 43 dBi.

**The optical table, starting from the group's terminals, counted aperture to aperture.**

| # | 100 m | 3 km | what changes | beyond the gear owned | total $ |
|---|---|---|---|---|---|
| O0 | ~91 ns | no link | as built: 50 MBd POF at the focal planes, a registered FPGA path, the refractors | $0 | ≈ $15-31k |
| O1 | ~56 ns | no link | the FPGA path combinational | $0 | ≈ $15-31k |
| O2 | 12.4 ns | 12.4 ns | 1550 nm DFB + ~1 GHz receiver on 20 cm of 105 µm fibre behind an f/2.3 relay | ≈ $3.7-8.8k | ≈ $19-39k |
| O3 | 4.7 ns | 4.7 ns | CML fast path; a 10G PIN-TIA and a DFB at the focal planes; a booster SOA | ≈ $6-19k | ≈ $22-49k |
| O4 | 1.7 ns | 1.7 ns | short dedicated apertures (3.7 → 0.7 ns) and a fast steering mirror | ≈ $14-49k | ≈ $30-79k |
| O5 | 1.1 ns | 1.1 ns | 30 GHz receivers, InP logic, CW EDFA into a 40 GHz EAM | ≈ $28-87k | ≈ $44-117k |
| O6 | 0.47 ns | 0.47 ns | one InP photonic chip at a 50 mm focus | ≈ $54-190k | ≈ $69-220k |

**The optical physics:**
- Pointing sets the field.  The field sets the detector's size by étendue, d = θ·D/NA.  The size sets
  the bandwidth.
- The 1 mm POF's 1.8 mrad beam closes only ~100 m.
- The refractors' 0.55 m to focus is 3.7 ns in and out, the largest term from O3 on.
- Fibre is 4.9 ns/m.
- An EDFA after the modulation is 25-150 ns: amplify the CW light, or use an SOA.
- Optics beats RF only below ~1.2 ns, at several times the money.

**The RFSoC 4x2 and the ZCU102 are the verifiers' tools, not a faster prover.**
- Transceivers work in words.  Raw, with the buffers bypassed, a decision costs ≈ 15-25 ns (est).
- The CDR wants a running, balanced stream.
- The 100G CMAC with its mandatory RS-FEC costs hundreds of ns.
- The RFDC is 90-117 ns from DAC to ADC (QICK).
- What they are good for:
  - GTY receivers as 39 ps samplers;
  - two GTY lanes as an I/Q challenge generator;
  - the RF converters as a complete verifier radio;
  - the QSFP28 and SFP+ cages for heralding and time-tag streams.
- The ZCU102's LVDS pins save ~1-2 ns at row 3 only.

**WiFi channels: don't narrow the filters; place the carrier.**
- A real channel filter at both ends (4th-order Butterworth) costs ~17 ns for 80 MHz and ~33 ns for
  40 MHz.  Row 4's 2.4 ns becomes 20-36 ns.
- A one-pole filter costs 3-6 ns but rejects the neighbour by only 7.5 dB.
- Narrowing never speeds the decision, even at range.
- Immunity without latency comes from the panels (20-30 dB), the channel choice (UNII-2C), time gating
  and the settled-vector decoder.
- Interference to WiFi is the idle carrier.  Move it from 5800 to 5775 MHz, which should be a null in
  every WiFi channelization of UNII-3 (to be checked against the tone plans).

Lessons in CLAUDE_PCB.md section 14: selectivity costs delay; a SERDES buys throughput, not latency;
pointing and the terminal's length are latency in optics.

### Interjection (2026-10-12 02:27 PDT)

Keep going, but I guess I was thinking that, since each node will have a slow Ethernet control link, each antenna could be switched between a WiFi card or a tiny spectrum analyzer and our low latency link. After some spectral monitoring and WiFi monitoring, the node could instruct the other node that will transmit to it which frequency is best. Then the Low latency communications can be on quiet WiFi channels. I suspect that interference will be a bigger real-world problem than the more easily estimated wire noise. 

### Response (02:27 - 02:32)

**PLAN.md section 19, "Jason's frequency-agile plan".**  `sim/wifi_channels.py` now prices interference
too.

**Interference is first-order.**  The receiver's noise is −92 dBm in 100 MHz.
- Continuous WiFi at −82 dBm in our band moves the window from 0.10 a to 0.33 a.  Row 4 goes from 2.4
  to 3.1 ns.
- At −72 dBm (one access point a room away) the window no longer fits at the bench.

**Bursty WiFi costs rounds, not ns.**  The settled-vector veto discards the rounds a burst fakes.  So
each candidate frequency needs two numbers: the continuous floor (latency) and the burst airtime (lost
rounds).

**The best analyzer is the link's own receiver.**
- The floor: step the PLL and read the RSSI path with the far TX off.
- The bursts: count window crossings at the operating thresholds with the far TX off.
- A WiFi card adds who and why (`iw survey dump`).  Tap it through a 20 dB coupler (~0.2 dB) rather
  than switch it (0.5-1 dB, and 2 W on the TX side), with its transmitter off.

**The protocol.**
- Each receiver picks its own frequency and tells its transmitter over Ethernet.
- The score is weighted by our ±94 MHz filter.
- Prefer 5775 MHz among equals.  It is an integer-N channel.
- Retune between sessions (pull-in 3.8 ms to 0.38 s).
- Let the CFAR follow the measured false-event rate.

**How far it can move.**  The ISM band leaves no room; UNII-2C needs DFS under Part 15; the amateur
band gives ±40 MHz; an experimental licence would give the whole 4.9-6 GHz.

## Prompt 26 (2026-10-12 04:04 PDT)

You say "read the signal-strength path while stepping the frequency, to get the steady interference floor;" but I thought we didn't have signal strength information without a lock. Do we have a way of doing this spectrum analysis with the hardware on revA? How much more hardware would it take to do this?

## Response 26 (2026-10-12 04:04 - 04:20)

**Response 25 named the wrong path, and PLAN.md is corrected.**  `received_dBm()` needs the lock.
- The ADS1115 averages each reading over ~1.2 ms.  Unlocked interference is zero-mean on I and Q, so
  its average is zero whatever its power.
- There is no detector chip: the AD8318 was left off in section 4.

**Rev A can still survey, with no lock and no new hardware: the window comparators measure by
statistics.**
- A comparator's duty against its threshold traces the arm's amplitude distribution.  The counting
  gate already counts high samples, and the thresholds are DACs.
- So stepping the threshold and fitting the probit line gives the rms of the noise plus interference,
  and the arm's gain turns it into dBm at RX ANT.
- The slow path is the instrument: ~10 MHz of RF resolution (a 4.8 MHz pole, gain 80).  It is
  noise-limited (−103.3 dBm in 7.5 MHz ≈ 11 mV σ on the leg, against 0.8 mV DAC steps), with ~30 dB of
  range plus the DSA's 31.75 dB.
- The fast window scores the whole ±94 MHz band, above ~−81 dBm only.
- The RX synthesizer can step 5 MHz in integer-N with R = 5 (every WiFi centre).  ~0.14 s a frequency:
  the amateur band in ~8 s, 4.9-6.0 GHz in ~30 s.
- The duty past 4σ flags bursts (3e-5 for noise; a lower bound on WiFi's airtime).

**Code:** `noise_scan()`, `probit_fit()`, `sigma_to_dbm()`, `thermal_dbm()` and `survey()` in the
driver.  `pll_tune(f_pfd=5)` and `max2871_regs.regs(f_pfd, cp)`, with the 5800 MHz words unchanged.
`TestSurvey`; the driver's 18 tests pass.  BRINGUP.md stage 4.5 runs the survey beside the laptop's scan
and an SDR on RX MON.

**Without touching the board:** an SDR that reaches 6 GHz on RX MON (U.FL, antenna +19 dB), split
with a WiFi card in monitor mode.

**More hardware for rev B, in order of value:**
1. An RMS or log detector on the slow I and Q into a second ADS1115 (≈ $25-35 a board): power on the
   operating channel during operation.
2. A comparator on it into the FPGA as a burst "busy" flag.  It needs a pin, and rev A has none.
3. A dual 65-125 MS/s ADC and an FFT (≈ $20-40, rev B's LVDS host): kHz resolution, the sidebands
   told apart, WiFi recognised.
4. Not an RF detector at the input: it is broadband.

## Prompt 27 (2026-10-12 04:28 PDT)

Keep going. You hinted at different setups for the prover and the verifies. On the prover, we have not talked at all about how the incoming information from the 2 or 3 verifies needs to be hashed (or at least XORed) together to make a single measurement 1-of-N basis. This needs to go to BME Pockells Cells, whose driver and specs may be in the Syzygy Driver project's datasheets. Then the quantum photon needs to be detected with APDs or some fast SNSPD detector at 1550. And the "click in output A, click in output B, or no click" needs to be sent back (changing the prover transmitter's state from idle to one of these). This all has latency that I'd like you to look up or estimate. This means that for revA and this experiment, squeezing every last nanosecond is not as important as reliability and robustness to interference.  The push for the absolute lowest latency is for other quantum networking experiments. My goal with revA is to be as low latency as reasonably achievable while being reliable. I don't want the RF link to be what drives up the overall latency budget, and I don't want the deployed system on the roof to be flaky. Do a system analysis with all of this in mind and see if you can suggest improvements before we send revA off to JLCPCB.

Perhaps separately, discuss options for the verifies. One option is to use more copies of the same type of board (probably a revB with LVDS on a SYZYGY, three of which can be plugged into the three non-transceiver SYZYGY ports on a Brain-1.) If we do three or more verifies, all but one are pure RF. Those could be copies of the same Brain+PCB, or they could be something else involving RFSoC or ZCU102. The one we are calling Verifier0 needs optical detector inputs and, in some protocols, Pockells Cell outputs. All of these need to be synchronized while on the roof, with only an ethernet or 2.4 GHz WiFi. NTP can't get to Nanoseconds, and GPS's PPS is also probably not accurate enough to synchronize the experiment. This pushed us toward having these low-latency RF links from each of the Verifiers not only to the prover (who cannot be trusted with synchronization), but also back to Verifier0. The synchronization and the "a photon is coming down the slow coiled fiber, so get ready everyone" signals would all be handled over these links. This again pushed us towards multiple copies of the same Brain up to 3 SYZYGY PCBs. This can fit in a box on the roof behind the antenna, and would not be as expensive as an RFSoC board with enough DAC and ADC channels to be relevant. If the RF-only provers are best done with another FOGA platform, spell thst out in detail. If the Brain+revB SYZYGY boards are still the best way to do synchronization to Verifier0 and the whole QPV protocol, should we make any changes to revA to make sure we are testing everything that is relevant, such that revA can evolve into a board that can fulfill roles in a all links?

### Interjection (04:37)

Tp be clear, I'm not asking you to add the detector input and Pockells output to the Costas revA board. Thsr would be for revB. I just wanted you to survey the latency of doing this and factor it in as part of the "off board" latency budget, along with cables to the antennas on the roof and actual speed of light travel time. Here we'll still mostl focus on the on-board numbers, but they should be put into context. If a BME driver driving a Leysop Pockells cell takes 10s of Nanoseconds to switch anf settle into a new basis measurement state, neither revA nor revB need to go to heroic efforts to shave off an extra nanosecond.

## Response 27 (2026-10-12 04:28 - 04:50)

**docs/SYSTEM.md (new), `sim/system_budget.py`, PLAN.md section 20, BRINGUP.md stage 4.8.**
- The BME manual is in SyzygyRadioDrivers: 4-7 ns edges, ≥ 3 V (better 4 V) into 50 Ω, 50 ns minimum
  On-to-Off, four trigger lines; no trigger-to-output delay.
- The Leysop RTP-4-20 is 6 pF.
- Detector latencies are not published (ID Qube) or are assembled from parts (SNSPD readout).
- An agent summarized a colleague's SyzygyRadioBoard: OOK into an ADL5511, four BME outputs (SN74ACT04 ×6,
  15 Ω, 3.2-3.7 V into 50 Ω), four LVTTL detector inputs, GPS PPS and 10 MHz to the FPGA only, no clock
  on SYZYGY's P2C pins.

**The prover's turnaround, antennas to antennas, air excluded:**

| | total | the RF link's share |
|---|---|---|
| A: rev A's gateware as planned, InGaAs | 156-267 ns | 27-40 % |
| **B: rev A with a robust fast path (first edge, slow-path veto, "invalid")** | **113-225 ns** | **17-20 %** |
| C: rev B on a Brain-1, SNSPDs | 71-137 ns | 7-9 % |

- The BME and cell (25-55 ns) and the detector (10-60 ns) dominate.  No heroics.
- The prover's antenna cables are the biggest avoidable term: 8 ns at 1 m each way, 78 ns at 10 m.
- The photon's coil is 13-23 m.
- The answer is four messages (B2's alphabet), released at a constant time.

**For rev A:** configuration B in gateware, plus gating, the survey, lock watching and re-trims.  The
roof's protection goes around the board: a cavity BPF, a limiter, a DC-grounded antenna with an
arrestor, fibre Ethernet, no 2.4 GHz radio inside the box.

**The verifiers:**
- Only the prover links are latency-critical.  The V0 ↔ Vk links need precision, and a herald's µs
  waits in a 1 km coil for 0.2 dB.
- Frequency comes from the carrier lock, time from two-way exchanges (~10 ps statistical).
- Rev A tests it with a REF OUT → TRIG IN lead (BRINGUP 4.8).
- The frequency plan is the real constraint: up to 10 one-way links against 275 MHz.  80 MHz prover
  channels (+17 ns, ~10 %), time division, spatial reuse, narrow synchronization links, or a Part 5
  licence.

**The platform:**
- One universal rev B radio (the coherent core plus the SyzygyRadioBoard's field I/O, the clock to
  P2C_CLK) on Brain-1s: 10 radios and 4 Brain-1s.
- The RFSoC 4x2 is the lab's reference verifier and timing monitor.  The ZCU102 is a lab host.
- A colleague's boards: their I/O now, their RF only where the band is quiet.

**Before the order:** rev A as it is.  Optionally an RF ESD/DC shunt at the antenna jacks, or the same
outside the board; channel-filter footprints only for a 5 cm-band deployment.

## Prompt 28 (2026-10-12 05:02 PDT)

If we added an RMS or log detector, how would that information get to the FPGA? Do we need more pins? If it's just $25–35 per board, add it. If we have plenty of spare slow-ish ADC channels, add RMS, but maybe also add a more slowly-decaying peak detector as another channel to look for WiFi bursty activity in addition to a more "true" sample of current RMS levels.

### Interjection (05:12)

Assume an experimental licence will unlock 4.9–6 GHz. If you can add an ESD/DC path at the antenna jacks that works over this whole band, I'll consider it. Without any modification, what center frequency range can the current revA board be operated over now?

## Response 28 (2026-10-12 05:02 - 08:10)

**How it reaches the FPGA: no new pins.**  A second ADS1115 at 0x49 (ADDR to VDD) sits on the I2C bus
the DACs and the first ADC already use.  The driver reads it (`detectors()`, `det_adc()`;
`TestDetectors`, with all of the driver's tests passing).

**Added to rev A (sheet 6, now A2), placed in the free field above the Q arm:**
- **AIN0 LOG_Q:** an AD8310 log amp on the fast Q arm (the link's whole ±94 MHz band, 95 dB,
  24 mV/dB), averaged by the ADC's conversion.  This is the floor, the number that sets the CFAR
  window and so the latency.
- **AIN1 PEAK_Q:** LOG_Q peak-held.  OPA2388 A charges 10 nF through a 1N4148W inside its loop, B
  buffers it, and 4.7 M lets it decay in 47 ms.  These are the WiFi bursts.  The link's own events
  lift it too, so read it in a pause.
- **AIN2 V5_MON:** +5V_RF / 2.  The ADL53xx want 4.75-5.25 V.
- **AIN3 TEMP:** a 10 k NTC under 10 k, for the re-trims.
- **The LOG Q test pad** shows the frames on a scope.
- **The true RMS (an LTC1968 on the slow Q arm) was drawn and then left off.**  It took the block
  from ≈ $32 to ≈ $59 a board, over the $25-35.  And in the arms' corner every placement of it left
  the router a net it could not finish.  `survey()` measures that band from the slow comparator's
  statistics, and the converter stays a rev B option.
- **Cost:** JLCPCB $826-841 against $777-792, **+$50 an order, $25 a board**.  The BOM is 79 lines
  and 48 Extended codes.

**The ESD / DC path at the antenna jacks, unfitted:**
- L101 (RX ANT), L202 (TX ANT) and L401 (ANT) are an LQW15AN6N8, 6.8 nH wirewound, self-resonant at
  6.0 GHz or above.
- Across 4.9-6 GHz that is 400 Ω to more than 1.5 kΩ, about 0.05 dB as a shunt.
- Each sits on the jack side of its DC block, as near the line as the placer allows (a 1-1.6 mm
  stub).
- Fit them when the antennas are not DC-grounded: +$3 feeder and $0.07 each.
- The multilayer LQG15HS parts resonate at 3.4-4.5 GHz and would be capacitive in the band.

**The band rev A covers unmodified: 4.9-5.9 GHz.**
- The SKY65404 LNA and the 5400BL15B050 balun are both rated 4.9-5.9 GHz.  Every other RF part runs
  to 6 GHz.
- Carriers of 5.0-5.8 GHz keep the ±94 MHz receive band in spec.
- 5.9-6.0 GHz is out of the LNA's and the balun's rating: measure it before relying on it.

**The board:** ERC 0, net check 0, placement 0, DRC 0, labels 0; the release regenerated.  The way
there:
- the first placement left the RMS converter's inputs unroutable, then the I-window monitor's line,
  then the ground pours round U305, R125 and C317;
- route seeds were tried side by side;
- a new post-fill ground-rescue step gives an islanded ground pad its own via, in its own process
  pass;
- the 1 k inputs moved out of J105's label column;
- the MON taps' limit is shortened to "1.65V +-249mV 1k";
- seed 0 is the default again.

**Docs and lessons:** PLAN.md (section 4's table, section 17's cost, section 19's detectors, band and
ESD), REVA_CHANGES 25-26, BRINGUP 4.5, and two CLAUDE_PCB.md lessons (the inductive shunt, and that a
late block can break the board elsewhere).

## Prompt 29 (2026-10-12 08:43 PDT)

What is the difference between the RMS monitor that you could route to an ADC channel and the one you could not route? What are we missing now that you tried to get?

If the fancy inductor would prevent permanent damage for minimal risk, it's worth taking the very small hit. Why did you make it DNI? Because it was not in stock or Because I was hesitant in my last prompt? 

What sets the lower frequency of the range? The balun?

## Response 29 (2026-10-12 08:43 - 09:00)

**The two monitors measure different bands and different statistics.  Neither of the ones on the board
is an RMS.**
- **Kept:** the AD8310 is a log amp on the fast Q arm, the link's whole ±94 MHz.  The ADC averages its
  output in dB: the log-average, which behaves like a median.  It reads Gaussian noise ~2.5 dB under its
  rms (a fixed calibration) and barely moves for bursts.  Its peak hold shows the bursts, over 95 dB.
- **Dropped:** the LTC1968 was a true RMS of the slow Q arm, ~±5 MHz round the LO, the band the slow
  confirm/veto comparators see.  It averages power, so a burst counts by its energy, over ~34 dB.
- **What is missing now:**
  - a direct energy average.  Floor and peak bracket it, and the survey's tail gives an airtime bound;
  - a continuous reading of the slow band while the link runs (`survey()` borrows the slow comparators,
    so it measures only between sessions);
  - the 10 MHz-resolution survey in one reading instead of a ~0.14 s threshold scan per frequency.
  The latency-relevant number (the link band's floor) and the burst flag are both on the board.
- **Why it was dropped, with the cost corrected.**  It would take the block from the $25 a board measured
  to ≈ $52, not my earlier ≈ $59.  Two placements of it failed to route: one its own input, the other the
  I-window monitor's line.  It is not unroutable in principle; I stopped because of the cost.

**The inductor was unfitted because of your "I'll consider it", not stock.**  JLCPCB has 23,999.
- Now fitted on L101, L202, L401: $4.66 an order with the feeder and duty.
- It drains static from cables and from antennas that are not DC-grounded.  Below ~1 GHz, where most of
  a touch's ESD energy lies, it is a few ohms (4 Ω at 100 MHz), and with the 1.5 pF DC block it makes a
  high-pass in front of the LNA.
- It does nothing for lightning: that is the bulkhead arrestor's job.
- Rebuilt: ERC 0, nets 0, placement 0, DRC 0, labels 0; the release regenerated (80 BOM lines, JLCPCB
  $831-846).

**The lower edge is set by both the LNA and the balun.**  Each is rated 4.9-5.9 GHz.
- Their plots reach a little further: the LNA's from 4.8 GHz, the balun's from 4.4 GHz.  So 4.8-4.9 GHz
  is in their data but out of their guarantee.  Below 4.8 GHz the board has no data.
- The LNA's match is the narrower.
- Nothing else limits before ~4 GHz: the DC blocks are ~15 Ω there, the couplers −21 dB.
- The transmitter has no band part.

## Prompt 30 (2026-10-12 09:41 PDT)

Is the source of truth for the schematic,  PCB, and simulations duplicated or all in one place (one place for each parameter or passive value)? If that source of truth is changed, does everything downstream get updated and remade, so that everything is consistent? If there are hard coded things that cannot be traced to a single initial source of truth (often in markdown documetation), check that they are at least up to date. Make sure thst some version of this request is in CLAUDE_PCB.md

### Interjection (09:48)

When you are done, do another overall once over and make sure the "release " directory is good to make a consignment Digikey order and a JLCPCB order.

## Response 30 (2026-10-12 09:41 - 10:36)

**Before this prompt the answer was "mostly one place, not entirely".  Now every value is set once, one
command remakes everything from it, and a build step checks the numbers the documents quote.**

**Where each thing is set:**
- `sim/budget.py`: every computed value and design parameter.
- `gen/parts.py`: the parts and their stocked values, plus the consigned parts' distributor numbers and prices.
- `gen/pins.py`: the header.
- `gen/placement.py`: positions.

Everything else is derived from those four:
- `gen/levels.py` maps each computed value to the nearest stocked part (`VAL`); the schematic and its notes use it.
- The netlist and the board follow from the schematic.
- `gateware/board_constants.py`, new, carries the driver's and the register script's numbers.
- The studies, the block diagrams and the release are remade from the same sources.

**What was duplicated, and is now set once:**
- **23 passive values typed into five sheet generators:** the TX ladders, the MAX2871 loop filter and
  RSET, the Costas loop's C, the logic monitor taps, sheet 6's detector values, the trim and
  comparator-series resistors.  They matched the budget, but nothing tied them to it.
- **The driver's hand copies** of the gains, levels, noise bandwidths and the detectors' scales.
  `A_REG_V` was the 10 m case's level, 0.1 dB off the regulated one.  `test_sim.py` now fails if
  `board_constants.py` differs from the build.
- **RSET and the charge-pump code** were set separately in the budget and in `max2871_regs.py`.
- **The consigned parts' prices** were in three places.  The release's estimate and
  `cost_estimate.py`'s also differed by $4.49: each counted pads its own way, and only one charged
  the depanel fee.  They now agree to the cent.
- **The band appeared three different ways:** "5.15-5.875 usable" on the schematic, "parts 4.9-6"
  on the diagram, "4.9-5.9" in the plan.
- **Smaller ones:** the comparator hysteresis (3 vs 5 mV), the gain-2 bandwidth (189 vs 170 MHz),
  and rev A's cost hard-coded in the roadmap.

**Is everything remade?  Before, no:**
- Six studies were outside `build.py`, and `sim/wifi_channels.py` had been crashing unnoticed.
- The Verilog includes were remade only by `make`.
- The block diagrams changed on every run.

Now `build.py` has an `analyses` step.  Its `gateware` step writes the constants and the includes
and runs the driver's tests.  It ends with `docs`: `tools/doc_check.py`, 43 claims plus three tables
copied verbatim.  Reintroducing two old numbers makes it fail on their lines.  A full rebuild gave a
board file byte-identical to the last commit, a netlist changed only in the balun's description, and
DRC 0 / 0 / 0.

**What tracing the values back to their source exposed:**
- **Sheet 6's log-amp note** gave the demodulator's input noise (0.8 mV) as the log amp's.  The log
  amp sees 2.3 mV (−53 dBV), 38 dB over its floor.  The OFLT corner is 59 kHz by the datasheet's
  equation 12, not 65.
- **The Costas loop as fitted** (the budget had reported an "E24 9.1 k" the board never had):
  - with the 10 k fitted it is 2916 Hz, ζ 0.687;
  - a phase step overshoots 21 %, not the diagram's 2 %;
  - pull-in is 4.2 ms from 30 kHz.
- **The MAX2871 filter,** evaluated in full: 80.0 kHz and 49.6° as designed, 81.1 kHz and 49.7° as fitted.
- **The digital rail counted 6 comparators; the board has 8.**  The board draws 1.37 A (6.8 W), not 1.34.
- **BRINGUP stage 1.1 could not pass.**  It expected under 20 mA at a 0.1 A limit, but the RF chips
  have no enable.  It is now a short check.  Stage 1.3's current is now 0.89 A plus up to 0.4 A for
  the unprogrammed synthesizers.
- **The driver's bring-up never checked the detectors' ADC at 0x49.**
- **The balun under the number Digi-Key sells is rated 4.9-5.875 GHz.**  The legacy number's sheet
  said 5.9, so rev A's band is 4.9-5.875 GHz.
- **Sheet 3's DAC note** still named V_T; channel C has been Q_OFF_F since Response 14.  Three
  unused texts were deleted.

**The documents:**
- Two audit agents checked every number in them against the JSON.  About 110 stale figures are now
  fixed, among them:
  - the latency: 23.5 ns (8.5 + 15.0) and 14.7 ns on the Icepi;
  - the noise floors, the isolation table, the reaches and the constellation ranges;
  - the slow path's 11 dB (not 14 or 16);
  - the header pins and the parts counts;
  - the cost table and the roadmap's totals.
- §19's passive knobs came from no script.  `sim/hosts.py` now computes them.
- `CLAUDE_PCB.md` §2 has the rule, with your request quoted.  It also gains "evaluate the design as
  fitted", and §3 a lesson on reading consigned parts' numbers from the distributor's own page.

**The release, once over for the two orders** (regenerated with live JLCPCB stock; every gate passes):
- **Digi-Key fixes:**
  - The balun's number, 712-1363-1-ND, is no Digi-Key part.  It is **712-5400BL15B0050001ECT-ND**,
    $0.69, 6,874 in stock.
  - The ADI chips are now **505-ADL5380ACPZ-R7CT-ND** ($17.96) and **505-ADL5375-05ACPZ-R7CT-ND**
    ($17.26, not $14.12).
  - The cart is 4 of each, **$165.29** with tax and shipping.
  - CONSIGNMENT.md adds, for home in the same cart, three J302 sockets (Sullins PPTC202LFBN-RC,
    S6104-ND, the same 8.5 mm height) and 20 shunts (S9001-ND).
- **JLCPCB:**
  - $835.08-850.08.  BOM 80 lines (3 consigned), 384 designators, the same 384 in the CPL, all on top.
  - The Gerber zip is complete, and changed only in its creation dates.
  - Everything: $1,177-1,346.
- **Risks on the order day:**
  - The HMC536 has 5 in stock against 2 needed, and Digi-Key has none until 500 arrive on 2026-12-24.
  - The CPL rotations (33 part numbers predicted) are left to JLCPCB's preview, as planned.
- **The order:** buy the Digi-Key cart, register the three LCSC codes under Consigned Parts, post the
  parts, then upload the zip, the BOM and `*_cpl_jlcpcb_upload.csv` with ORDER_SETTINGS.md's 11
  non-default fields.

## Prompt 31

I have started the consignment process, but I have run into some issues. First, the two Analog Devices parts are in stock at JLCPCB, although with low quantities. If I can get it from them, it's cheaper than ordering 2 extras from digikey just for the consignment for the 2 test boards. I will almost certainly not use these extra ones. This means that the 5400BL15B0050001E is the only part that I'd need to consign. If there is a substitute balun that can save me an entire consignment order, I'd prefer to use that, even if it's slightly more expensive. In general, when you check if it's worth ordering from JLCPCB or digikey in terms of cost, factor in the spare "attrition on consigned parts", which I will probably not use. If I order more than 2 prototype boards, I'd be more willing to consign than just for the initial 2 quick prototypes.

Your digikey part numbers are wrong:

BALUN	5400BL15B0050001E   has the wrong digikey part number: 712-1363-1-ND is wrong. The correct part number is 
:DigiKey Part Number
712-5400BL15B0050001ETR-ND - Tape & Reel (TR)
712-5400BL15B0050001ECT-ND - Cut Tape (CT)
712-5400BL15B0050001EDKR-ND - Digi-Reel®

ADL5375-05ACPZ-R7
DigiKey Part Number
505-ADL5375-05ACPZ-R7TR-ND - Tape & Reel (TR)
505-ADL5375-05ACPZ-R7CT-ND - Cut Tape (CT)
505-ADL5375-05ACPZ-R7DKR-ND - Digi-Reel®


ADL5380ACPZ-R7
DigiKey Part Number
505-ADL5380ACPZ-R7TR-ND - Tape & Reel (TR)
505-ADL5380ACPZ-R7CT-ND - Cut Tape (CT)
505-ADL5380ACPZ-R7DKR-ND - Digi-Reel®
Manufacturer



## Response 31 (2026-10-14 16:30 - 18:45)

**The consignment is gone.**  Your Digi-Key numbers were already the ones in the tree (Response 30 had
fixed them: `712-5400BL15B0050001ECT-ND`, `505-ADL5380ACPZ-R7CT-ND`, `505-ADL5375-05ACPZ-R7CT-ND`; the
`712-1363-1-ND` you saw is in the older CONSIGNMENT.md copies under `design_review_*/repo/`).  What changed:

- **The balun is now a JLCPCB part.**  A sweep of JLCPCB's whole "balun" category (the earlier searches had
  tried three part numbers) found the **TDK HHM1907B1** (C531388, 7,884 in stock, $0.10): 50:50, 4.9-5.95 GHz,
  0.8 dB max loss, 10 dB return loss, 180 +-10 deg, +-2.5 dB; the Johanson 5400BL15B0050001E it replaces is
  1.0 dB, 9.5 dB, +-10 deg, 2 dB, 4.9-5.875 GHz.  Same ratio, same band, better on paper; 0402 with four
  0.30 x 0.35 pads (new symbol, footprint from TDK's land pattern, placed at 270 so pin 1 sits on the RX line).
  Mini-Circuits' 50:50 parts to 6 GHz were 1 and 5 in stock at $2-4; every other 5 GHz balun JLCPCB stocks is
  50:100.  The band is now the LNA's, 4.9-5.9 GHz.
- **The ADI chips come from JLCPCB's shelf** (18 ADL5380 at $21.62, 4 ADL5375-05 at $16.40 on 2026-10-14) and
  keep their Digi-Key numbers as a **fallback**: `gen/parts.py` has `consign=` beside `lcsc=`, and
  `mfg/make_release.py` consigns a line only when JLCPCB's live stock cannot cover the order on the day; the
  BOM then flags it and CONSIGNMENT.md says what to buy.  With nothing short, CONSIGNMENT.md says so.
- **Your rule, with the number:** a consignment's true cost is the pieces at Digi-Key plus two spares a line
  that are never used, tax, Digi-Key's shipping and the parcel to Shenzhen.  For the two ADI chips on two
  boards that is about $100 over buying the same four pieces on the shelf
  (`mfg/cost_estimate.py consignment_cost`; CONSIGNMENT.md prints it from the day's stock), so a shelf part
  up to about that much dearer wins, and the number shrinks with more boards.  CLAUDE_PCB.md section 3 has
  it, with your words.
- **Cost:** JLCPCB $943-958 (the ADI chips' $76 and two feeders moved onto its line with their duty), Digi-Key $0,
  no parcel; everything $1,085-1,230 against $1,177-1,346 before.  Thin lines on the order day: ADL5375-05 (4),
  HMC536 (5), AD5696R (2 against 2).

**A fresh look, by three independent reviews** (schematic against the datasheets, the board and the package,
the system; each wrote only to its own scratch directory; their findings are reconciled in REVA_CHANGES.md
rows 32-36).  Formed on build 33 before any of them read the earlier rounds.

1. **BLOCKING, and nobody had seen it: both ADS1115 input filters were drawn capacitor-first.**  The sheet's
   blue box said "10 k / 100 nF (160 Hz)", and the netlist had the 100 nF hanging from the source's end of each
   line and the 10 k between it and the ADC pin: **C154 and C155 (100 nF) sat straight on the fast I and Q
   arms' outputs** (I_P, Q_P: the THS4541 cannot drive 100 nF; the 100 MHz arms would have been shorted above
   a few kHz, with the comparators and the Costas error wrong), C156 on the VCXO's control line at the
   OPA2388's output, C157 on the loop error at the sign switch, and on sheet 6 C524 on the AD8310's output and
   C525 on the peak hold's.  **As committed, the receiver would not have worked.**  Five reviewers and I
   missed it in two rounds.  Fixed in one helper (`gen/sch_blocks.adc_inputs`: resistor between source and
   capacitor, capacitor at the pin, each line on its own vertical so nothing crosses), used by both sheets;
   the references did not move.  The netlist now has every 100 nF on its ADC pin's net.
2. **SERIOUS: no DC blocks between the balun and the ADL5380's RFIP/RFIN.**  The datasheet: "both the LO and
   RF ports should be ac-coupled"; its Figure 81 and evaluation board put 100 pF there; a lattice balun's
   balanced terminals have a DC path to its ground terminal, which would have pulled the demodulator's biased
   inputs to 0 V.  This was true of the Johanson too.  Two 1.5 pF blocks (the LO legs' part), C159/C160,
   drawn last on the sheet so no hand-anchored reference shifts; on the board the balun sits at y 55.0, the
   blocks at 57.2, the demodulator moved to 61.3 and the RX synthesizer to 77.3 for the room; the two legs
   are planned lines through the blocks (`routes.PAIR_PATHS` "RF +"/"RF -").
3. **The SMA launches** kept the centre pin's 2.0 mm pad ring on In1, In2 and B.Cu, where nothing connects
   to it, against 2.5 mm antipads: 0.41 pF excess, a 66 ohm shunt at 5.8 GHz, 9 dB return loss, 0.6 dB a
   launch.  Now `remove_unused_layers` on pin 1 and a design rule keeping the inner and back planes 1.35 mm
   from the hole (a 4 mm antipad): about 12 % reflection instead of 35 %.
4. **The budget was wrong in four places** (review C, each checked against the datasheet lines):
   - the own-transmitter rejection used two poles at 100 MHz (31 dB at 600 MHz); the real poles are the
     demodulator's 390 MHz and the arm's 94 MHz (21 dB), and the compression limit counted one of the two
     gain blocks with the ADL5380's 900 MHz IP1dB (11.6 dBm; 8.2 at 5.8 GHz).  **FDD needs 52 dB of
     antenna isolation, not 42**; two panels on one mast (30-40) are short; two whips on the board's own SMAs
     put the own transmitter at the LNA's P1dB.  Remedies already there: the switch block, a pad in the TX
     lead on the bench, cross-polarised panels, 3-5 m between masts.
   - the static phase error from the ADL5380's offset divided a one-leg offset by the differential slope:
     9.1 deg, not 4.6 (section 18's table redone); the trim still covers it.
   - the oscillators' phase noise was never integrated: two x232 synthesizers plus the references give
     1.3-1.8 deg rms outside the loop (the VCXO's datasheet has no phase-noise figure at all), two to
     two-and-a-half times the bench's thermal phase noise; the bench CFAR windows will sit near 0.2 a, not
     0.1 a (a nanosecond), and the slow Q window at 0.1 a will chatter.  No effect on lock or range.
   - "the loop is untroubled by WiFi in its 3 kHz" described a linear detector; sign(I) x Q is captured
     once an interferer dominates the arms: a lost lock, not a false event.  The survey and the channel
     choice are the remedies.
   Also: the slow I stage idles 1.7x overdriven and the THS4541's 20 ns overdrive recovery is not in the
   trajectory model (start the confirm delay at 80 ns); the 30 dB loopback pad leaves the receiver 7 dB above
   its regulated range (BRINGUP says 40 dB now); the trigger outputs give about 1.7 V into 50 ohm, not 2
   (the LVC's 32 mA); a DNP 10 k on the TCXO's "E/D or N.C." pad.
5. **Left for rev B (REVA_CHANGES 35):** the whole 5 V current crosses a single 0.25 mm via three times in
   series (works: 15 mV, under 1 K; one plating void opens the RF rail), and no decoupling capacitor is
   within 2.5 mm of any RF chip's supply pin because the placer's fan band keeps them out (expect spurs,
   not a dead board).  Both are the router's and the placer's structure, not a day's change.
6. **Checked and right** by the three: every hand-drawn symbol pin by pin, the control senses and safe
   idles, the RF levels against the absolute maxima, the MAX2871 filter (robust from Kvco 40 to 130 MHz/V),
   the Costas loop as fitted (fn 2.9 kHz, zeta 0.69, 46 deg of margin with the VCXO's 15 kHz pole; the PLL
   inside the loop costs 3-4 deg), the power ORing and LDOs, I2C addresses, the header; every net one copper
   cluster, the LO legs 0.00 mm apart, the couplers lambda/4, the CPWG gap 0.250 everywhere, BOM = CPL =
   board, the gerber set, ORDER_SETTINGS against the form.

**The board, after that.**  The new netlist (the balun's four pads, the two blocks, eight filter parts moved to
the ADC pins, the DNP pull-up) changed the router's luck: build 33's first pass left 3 nets in pieces and
crashed KiCad's refill (a SWIG quirk: one removal a process now); six route seeds side by side in scratch
copies all failed the same two nets, which is a placement fault, not luck: the shunt-at-pin rule had put the
four 100 nF hard against the ADS1115s' pins, boxing the resistors' far pads and the slow ADC's SCL pin.  With
the sixteen filter parts anchored a few millimetres out the board routed whole; one more pass fixed a
reference shift (drawing the TCXO's pull-up beside it had renumbered R220-R227 and the anchors then placed
the wrong parts: now drawn last, like the blocks) and taught the refill to drop a half-millimetre sliver the
widening leaves against a via.  **Build 34: 421 parts, 4,116 tracks, 1,110 vias, every net one piece, DRC
0 / 0 / 0, the LO legs 0.00 mm apart, labels 0, the schematic 0 overlaps on all seven sheets, the document
check 42 claims and 3 tables with 0 stale.  The release (`mfg/release/`, 2026-10-14) passes every gate: 80
BOM lines, 0 consigned, 386 placements a board, 52 Extended codes; JLCPCB $943-958 all in, Digi-Key $0.**
Bare-board rules and sources: `CLAUDE_PCB.md` sections 3, 4, 5 and 11 gained this round's lessons.

**My honest estimate** (my own numbers, with review C's beside them where they differ):

| | event | mine | review C | why |
|---|---|---|---|---|
| a | powers up, every rail right, nothing hot | **0.85** | 0.85 | the power path has now been audited three times by the numbers (ORing, LDOs, 1.37 A, 5.10 V at the plug); 349 placed parts from a pipeline whose symbols were checked pin by pin.  The 15 %: a pin figure misread somewhere nobody looked, a QFN rotation, a part that is not what its LCSC code says.  Today's blocking find (the ADC filters) is exactly the kind of drawing error that survives reviews, and there is no reason to think it was the last one |
| b | both synthesizers lock | **0.75** | 0.75 | register words from the datasheet's example; a loop filter stable from Kvco 40 to 130 MHz/V; 3.3 V CMOS into REF_IN.  Lock-detect polarity, the VCO band select on a first write, a dead LO pair |
| c | the Costas loop locks over a cable | **0.6** | 0.65 | textbook structure, the sign is a jumper, Kd follows the DSA.  The chain is 39 dB of gain in a row with a balun, two couplers and LO pairs never built; the FDA summing nodes have 61 mV of margin; the LO-pair blocks cost 0.5 dB nobody budgeted |
| d | a bit through on the bench, latency within 3 ns of 23.5 | **0.5** | 0.55 | the comparators and the gateware are simulated against the RTL; the header's 10 pF, the comparator's overdrive and the oscillators' phase noise each cost about a nanosecond, and the slow confirmation needs the 80 ns delay first |
| e | across a room, two antennas | **0.4** | 0.45 | the two things that fail here are set-up and channel: 52 dB of isolation for FDD (two whips on the board's own SMAs is a dead LNA waiting for a corner symbol; use the switch block or a pad) and WiFi inside +-94 MHz capturing sign(I) |
| f | 100 m line of sight | **0.3** | 0.35 | panels make the SNR trivial; the isolation (48 dB), the logistics, the licence |
| g | the rev A measurement programme yields useful data whatever (c)-(f) do | **0.9** | 0.9 | the comparator statistics on muted-carrier noise, the arms on the ADC, the loop's step response through VC_OFF, latency histograms and constellations in a cabled loopback survive anything short of (a) failing; even an unlocked loop leaves the open-loop beat, which measures I/Q balance, the offsets and the chain's gain |

**What is most likely to fail, in order, and what you still measure:**

1. **Own-transmitter leak in FDD** (0.6 that the first two-antenna test shows it): a 600 MHz tone within 10 dB
   of the wanted at the arms, or a compressed demodulator.  Not a board defect: TDD with the HMC536 block, a
   10-20 dB pad in the TX lead, 3 m between whips, cross-polarised panels.
2. **WiFi inside the arms' +-94 MHz** (0.5 across a room on an unsurveyed channel): a lost lock.  The survey,
   UNII-2C or the 5775 MHz null; the detectors measure the interference, which is a result.
3. **The oscillators' phase noise sets the bench windows** (0.7): CFAR at 0.2 a, the slow Q window chattering,
   a nanosecond later than TRAJECTORIES.  The servo finds it; ERR MON measures it; the VCXO is swappable.
4. **The slow path's saturation recovery and offsets** (0.5): a register and a trim.
5. **A loop sign wrong on the first try** (0.3; no lock with either jumper 0.05): minutes.
6. **DC offset beyond the Q_OFF_F trim at 5.8 GHz** (0.2): the ADC reads it; constellations with a known
   rotation are still constellations.
7. **A distorted arm from the THS4541's common mode** (0.25): the DNP 1.5 k on ADJ, at the cost of heat and gain.
8. **The RF chain oscillating or low** (0.15): the DSA between the stages, the four monitors, the TX side alone.
9. **Power source sag** (0.3 that someone powers it from the wrong thing once): V5_MON; a bench supply at 5.2 V.
10. **A wrong part or placement** (0.2): the switch block is separable, the TX and RX chains are separate.
And two that are now gone but would have been first: the ADC filters shorting the fast arms (a dead receiver),
and the balun's DC path into the demodulator's inputs (no gain).  That both lived through two review rounds is
the strongest argument for ordering now and measuring, rather than another round on paper: the next such fault,
if there is one, will be found in an afternoon on the bench with the monitors this board carries, and the
boards are $945 for two.

**What I would do before clicking order:** nothing on the copper.  Register nothing, consign nothing; buy the
J302 sockets and shunts anywhere.  On the day, run `mfg/make_release.py --refresh` (it reads the shelf and decides
the ADL5375-05 fallback: 4 in stock), look at the preview against PLACEMENT_CHECKS.txt, and order 5 boards with 2
assembled.

## Prompt 32 (2026-10-14 ~18:50 PDT)

A long conversation pasted from the "2026 Summer ToDo Quantum" Google Doc: Jason's checklist for a colleague's
SyzygyRadioBoard and her answers (AC coupling of every 5.8 GHz port, decoupling pairs at the pins, thermal
reliefs, terminations, ferrite isolation, power-up order and latch-up, test points, JLCPCB production notes,
parts selection), with the instruction: for the relevant things, check them in our design.  Then, mid-turn:
"trace the signal paths 'by hand' and make sure that all series and shunt components make sense, and that
everything makes sense going into and out of the ICs along the way, including DC bias levels, power levels, and
AC vs DC coupling"; and "look at voltage levels, power levels, input and output impedances, and specs of all of
the ICs and other interfaces"; and: do not put the paste in this log, cite the document, but keep the full
response.

## Response 32 (2026-10-14 18:50 - 20:35)

**The trace is `docs/PATHS.md`** (ten sections of hops and an eleventh of every port's impedance and limits),
built on `tools/path_walk.py`, a netlist walker that lists, from any pin, the two-terminal parts in its way to
the next active pin, so that no hop in the document is from memory.  Every hop quotes its part, its purpose,
the DC on the node, the level at the 10 m two-whips case, and whether the coupling suits both ends, with the
datasheet line it rests on.  What the trace says:

- **RF, jack to demodulator:** blocked at every port that carries or forbids DC: the LNA both sides, the DSA both
  sides (its sheet asks for 0 V DC on the ports), both ADL5611s (RFIN "requires a dc blocking capacitor",
  RFOUT carries the 5 V bias through 43 nH), the coupler's output (copper would pass the 5 V on), and now both
  ADL5380 RF pins behind the balun.  The ESD shunts sit on the jack side of the blocks.  Levels −53.9 → −40.9
  (LNA) → −48.5 (DSA at 5.25 dB) → −34.2 → −19.9 dBm at the demodulator: 28 dB under its 5.8 GHz IP1dB, 11 dB
  under its absolute maximum even with the DSA at 0.  The LNA's +1 dBm absolute maximum is the one limit a
  bench mistake can reach (a bare cable from the other board is +9.8 dBm).
- **Baseband:** the ADL5380's 3.8 V outputs through 1 k into summing nodes held at 1.87 V by the 1 k to ground
  (the THS4541's guaranteed 2.0 V limit: 61 mV), gain 4.02, outputs 1.65 ± 0.125 V into comparators whose
  rail-to-rail inputs take it, taps through 1 k, the slow stage through 1 k, the log amp through 1 k + 10 nF
  (AC, as its biased inputs want), the ADC through 10 k with the 100 nF at the pin.  DC-coupled by design
  everywhere a Costas loop needs DC, AC where a part is self-biased.
- **The loop:** Q through the sign jumpers into the 3157's 0-VCC analog range, ERR through the hold switch into
  the PI filter about V_MID, the summer, VC inside the VCXO's 0.3-3.0 V from an op amp that swings 0.02-3.28.
- **References and LO:** 3.3 V CMOS through 100 nF into REF_IN (0.7 V p-p to VCC wanted); open-collector
  RFOUTs pulled up through 27 nH, two 1.5 pF a leg (0.75 pF: half a dB, inside the −6 to +6 dBm LO window).
- **TX:** the ladders' 0.17 / 0.50 / 0.83 V inside the −05's 0-1 V pins, the 0.507 V other leg; −4.5 dBm out
  of the modulator, +9.8 after the ADL5611, 3 dB under its P1dB at the idle, at it on a corner; the pad
  placeholder, the coupler, the ESD shunt on the jack side.
- **Switch, slow path, detectors, triggers, power:** all as the budget has them; the slow I stage's 1.7×
  overdrive and the power-up order carry their numbers.

**The checklist against this board** (what it changed, what it confirmed, what it leaves for rev B):

1. **Thermal reliefs on RF grounds (changed).**  The pours joined every pad through four spokes, the router's
   default: the balun's ground pad, the three ESD shunts, the four 49.9 Ω loads, the LNA's ground pins and the
   SMA legs all returned RF through inductors.  The top, In1 and In2 ground zones now connect solidly; the back
   fill stays thermal and the socket's pads keep reliefs on every layer (it is soldered at home).
2. **A floating CMOS select (changed).**  JP103 unfitted left the sign switch's S input open; R145 100 k to
   ground (low = B1).
3. **Power-up order (documented with the number).**  This board powered with the PYNQ off pushes 12 mA per
   high output through the Zynq's clamps (3.3 − 0.6 V over 33 + 200 Ω), above its 10 mA absolute maximum.
   BRINGUP stage 1.5 already orders it right; PLAN §10 and the trace now say why.  The other way round is safe.
4. **Confirmed as is:** the AC-coupling table (every port, by the netlist); decoupling present (100 nF + 1 µF
   per chip, three values at the gain blocks' chokes) though 3-8 mm from the pins (review B's rev B item);
   ferrite isolation of +5V_RF (BLM21PG221) and the PLL rails behind 2.2 Ω and their own LDOs; source
   termination of the fast outputs (33 Ω + ~20 Ω); the unused RFOUTB legs terminated; the ESD shunts; via
   fences at λ/17 on the chains; three corner holes plus the middle slot; three fiducials; ENIG; no
   via-in-pad; every control pin with a resting state; the limits on the silk.
5. **Not done, noted in the trace's section 10:** thin-film 0201 loads (the thick-film 0402s terminate
   monitors at −40 dBm: a 15 dB return loss there costs nothing), mitred corners (the pairs' L corners are
   ~0.05 pF), anti-pads under the ADL5611's wide pads, an RC at each threshold pin, shield cans, mask cleared
   over RF, fab-side impedance control.

**The board after the changes (build 36).**  The solid pours and the new pull-down meant a re-route: the first
pass left R125's ground pad on a top-fill island with no room for a via (its 100 k pull-down now stands above
its own header pin, like the other pull-downs), the second left one 0.09 mm sliver the widening lays beside a
thin track and every tidy re-makes (snapped onto the track's centre line by hand this time; the refill pass
now does that itself).  **4,111 tracks, 1,137 vias, every net one piece, DRC 0 / 0 / 0, documents 0 stale;
the release passes every gate: 80 BOM lines, 0 consigned, 387 placements a board, 52 Extended, JLCPCB
$943-958 all in, Digi-Key $0.**  REVA_CHANGES.md rows 37-39; `CLAUDE_PCB.md` section 14 has the two rules
(RF grounds solid; trace every path by hand before an order, with the walker).

**What I would still do before ordering:** nothing on the copper.  The order-day run of
`mfg/make_release.py --refresh` decides the ADL5375-05 fallback (4 on the shelf) and the preview settles the
33 unseen rotations.


## Prompt 33 (2026-10-14 ~20:00 PDT)

"Are the connectors going to reflect 5.8 GHz?  We did a whole study in the SYZYGY board because some KiCAD
defaults were not right for this 6 layer board.  Make sure that all 5-6 GHz connectors have proper capacitance
and inductance *in the gerbers*."  Then: "There are several SMA test boards within the SYZYGY directory where we
did 3D EM simulations.  Make sure that these launches are not going to cause us issues like our test boards did.
In the end, your simulations matched the latest SMA test board well enough.  I'd rather spend design time and
simulation time here to get it right."

## Response 33 (2026-10-14 20:00 - 2026-10-15 00:36 PDT)

**In the gerbers, they were going to.**  I wrote `tools/launch_check.py`, which parses the plotted copper
layers rather than the board file, and build 36's release showed: the inner-layer rings at the SMA pins were
gone (Prompt 31's `remove_unused_layers` worked), but the In1 and In2 planes stood **0.90 mm** from each centre
pin, a 1.8 mm antipad, *smaller* than the 2.5 mm the board review had measured, because the DRC rule meant to
hold them 1.35 mm off had a property in its condition that never matched and DRC said nothing.  The 2.0 mm top
pad sat over In1 at 0.21 mm.  The 5.8 GHz U.FL taps and the ADL5611s' RF pads had In1 straight under them.

**What the gerbers now carry** (build 37): explicit rule areas in the generator (`gen/routes.rf_voids`,
`gen/rf_launch.py`): no copper fill within 2.2 mm of each 5.8 GHz SMA's pin on In1, In2 and B.Cu, and In1
relieved 0.2 mm beyond the taps' and gain blocks' RF pads; the DRC rule's condition fixed as well, but the
copper no longer depends on it.  `launch_check.py` is a release gate: no flash at the pins on the inner layers,
the planes the designed radius off them, the plane under each relieved pad clear, and (when a taper is
fitted) every line leaving the pin along the taper.  The committed gerbers fail it exactly as they should.

**The SYZYGY study, applied.**  `../SyzygyRadioDrivers/SMABridgeTestAnalysis/` (FIELD_SOLVER.md, the V1 and V3
test boards): on its 6-layer stack the as-built launch reflected 70 % and four free changes took it to 20 %
(pad on the outer layers only, the inner antipad opened to a 4.0-4.6 mm plateau, a 1.95 mm pad with a 1.0 mm
taper, 0.9 mm of pad clearance to the top pour; the B.Cu clearance 1.2 mm against the protruding pin's stub).
The principles carry over; the numbers do not: this is a 4-layer 7628 stack (0.21 mm prepreg over a 1.065 mm
core, two planes) and a different connector (BWSMA-KWE-Z001: a 0.9 mm pin in a 1.3 mm hole, 0.9 mm square legs
at ±2.55 mm, 1.9 mm of pin under the board).  So the study's openEMS model was re-targeted to this stack and
connector (`sim/launch/launch_cl.py`, nothing else changed), its rasterised-metal check passed on every
geometry (`check_cl.py`), and the study's own optimised point was re-run here with its own code as the anchor:
S11 −7.135 dB and insertion loss 0.426 dB at 5.8 GHz on 2.046 M cells, against the study's cached −7.13 dB / 0.43 dB on the same cell count (`sim/launch/anchor/anchor.json`): this machine and environment give the study's answer.  (Its 0.54 pF fit is on the raw port S-parameters; the 0.68 pF here is the same fit after de-embedding to the board's face, which is the convention the tables below use.)

**The numbers** (`docs/LAUNCH.md` §4; |S11| is what the study validated, the loss quoted is the mismatch loss
it implies, because openEMS's line port is not passive on the sweep mesh and its |S21| flatters every row):

| launch | S11 at 5.8 GHz | reflected | mismatch loss | shunt C | series L |
|---|---:|---:|---:|---:|---:|
| build 36 as its gerbers had it (planes 0.9 mm off the pin, pad over In1 at 0.21 mm) | **−0.7 dB** | **85 %** | 8.2 dB | 2.1 pF | 0.3 nH |
| build 37 (2.2 mm voids on In1/In2/B.Cu) | −5.4 dB | 29 % | 1.5 dB | 0.64 pF | 0.5 nH |
| build 38: + the centre pad 0.9 mm clear of the top pour | **−7.1 dB** | **19 %** | 0.9 dB | 0.49 pF | 0.5 nH |
| the same on the fine mesh (3.7 M cells) | −7.9 dB | 16 % | 0.8 dB | 0.45 pF | 0.2 nH |
| the study's optimised launch on its own stack, same model | −7.1 dB | 20-22 % | | 0.54 pF | |
| ... which its V3 test board then measured | −12.7 to −15.1 dB | 3-5 % | | | |

Build 36 would have lost 8 dB at *each* SMA: 16 dB on the TX chain, 16 dB on the receive chain, and the
antenna-switch block's three launches on top.  That is the "issue like our test boards had", only worse,
because this 4-layer stack puts the barrel through a 1.065 mm core 0.25 mm from the plane's edge.

The sweep round the candidate, one knob at a time (§4.2): the **antipad's knee is at 4.4 mm** (3.4 / 4.0 /
4.4 / 4.8 / 5.2 mm: 24 / 19 / 17 / 17 / 18 %), so the 2.2 mm voids already in the gerbers sit on the plateau;
**the top pour's clearance is the one lever left** (0.25 → 0.9 mm: 29 → 19 %; 1.3 mm: one more point, inside
the mesh error); the **B.Cu clearance** is on its plateau at 1.2 mm (0.6 mm: 23 %); the study's **smaller pad
is worth 2 points and its taper nothing** against a 0.29 mm line; **keeping the inner rings would cost 4**;
and with **no pin, legs or solder below the board the same launch reflects 13 %**, so what remains is the
connector's own 1.9 mm stub.  The fine mesh puts the candidate at 15 % against the sweep mesh's 17 %: the
model is pessimistic by about 0.7 dB, the same direction as against the study's measured board.
Clipping the centre pins to 0.3 mm under the board after assembly is worth 3 more points (16 %), so it is in
BRINGUP.md's step 0; the 1.85 mm pad without the taper 1 point, not taken.

**What went into the board (build 38):** `gen/rf_launch.LAUNCH_CLEAR = 0.9`, drawn as an F.Cu rule area of radius
1.9 mm round each of the five launch pins (`gen/routes.rf_voids`, beside the inner-layer voids), so it is in the
gerbers whatever the pour does.  My first try was KiCad's pad clearance property on the footprint: that applies to
every SMA, every layer and every track, the router does not know it, and DRC found 10 items at the trigger and
REF IN jacks' back-side tracks; the rule area touches only the pour and only the five launches, the 2.2 mm voids kept, the pad JLCPCB's
2.0 mm (1.85 mm would take the annulus on the 1.3 mm hole to 0.275 against JLCPCB's 0.25 floor for 2 points
the mesh cannot resolve), no taper.  Expected: −7.1 dB return loss per launch at 5.8 GHz by a model that
ran 5-8 dB pessimistic on the study's test board; the capacitance and inductance in the gerbers 0.5 pF and
0.5 nH.  `tools/launch_check.py` now also measures the top pour's distance from each pin (1.90 mm) and the
release gate holds it.  Build 38's release: DRC 0, every gate passing, and the launch gate's line for each of the five:
`In1_Cu 2.20 mm  In2_Cu 2.20 mm  B_Cu 2.20 mm  F_Cu 1.90 mm`; nothing but the pad flashes inside any void, and the
first ground fence vias start 2.65 mm from each pin.  Cost unchanged ($943-958, nothing consigned).

**Honestly, what is still not simulated:** the real board's neighbourhood (the ESD shunt and the DC block
0.5-2 mm from the pad, the fence vias where the router put them, the pour's exact outline) rather than the
model's straight CPWG line; the study's model was validated with the same simplification, and the test board
measured better than the model, not worse.  The five launches are the only through-hole RF on the board; the
U.FL taps and the gain blocks' pads got their In1 relief and no solve (0.2 pF each at most, against a 50 Ω
line that is a |Γ| of 0.05).
2026-10-15 00:36 PDT

## Prompt 34 (2026-10-15 ~01:00 PDT)

"A few things: The SMA connector labeled RX ant in the image that you pulled has a trace running around the pin,
within the ground pins.  Can you hand-route that trace so that it doesn't need to go around like that, especially
through the SMA connector?

My memory of the SYZYGY study was that the tiny pointy bit sticking off of the annular ring toward the trace ended
up not being necessary -- it got optimized to be so small that it was basically hidden under the ring.  If this is
true, just eliminate it so that the pad is symmetric under 90 degree rotations.  Make sure both simulate within a
reasonable error budget of each other.

In CLAUDE_PCB.md, note the problem with the default SMA pad in KiCAD.  We've had this problem twice and almost cost
us a huge reflection on $1k worth or boards.  Make checking these SMA launches standard practice in CLAUDE_PCB.md."

## Response 34 (2026-10-15 01:00 - 2026-10-15 04:58 PDT)

**The trace round RX ANT's pin.**  It was the LNA's VCC net: U101's VCC pin (6) is on the right of the receive
line and the choke that feeds it, L102, was rule-placed on the left, 3 mm away; the line and its fence vias wall
the two sides apart on every layer the router uses, and the one place the wall ends is the SMA's centre pin, so the
router took a 0.2 mm track 8 mm up, round the pin at 1.3 mm inside the legs, and 8 mm back down: a 20 mm loop for
a 3 mm connection, in the launch the field solve never saw (it is also what the first attempt at the pad clearance
flagged as a DRC item at 0.2 mm from the pad).  The fix is placement, not routing: L102 is anchored beside the VCC
pin on its own side (`gen/placement.py`), and so the net is a 1.3 mm stub.  And so it cannot happen at any of the
five again: `gen/routes.launch_keepout` closes a 6.2 mm square round each launch pin to the router on every layer,
tracks and vias, the planned line and the pin being the only copper inside the legs.  The first rebuild then showed the keep-out
is only as good as its place in the order: the DSA's P/S pull-up, R102, rule-placed on the left of the line with its
pin on the right, took exactly the same loop round the pin (the "local nets first" pass runs before the keep-out
was registered), then ran down the LNA's right side 0.5 mm from the VCC pin and walled it in (one unconnected).
So R102 is anchored beside its pin too, and the keep-out is registered after the planned fence vias (which belong
inside the square) and before any routed net.  The other four launches had nothing but their own line within
3.6 mm; J101 was the only case, twice.  Build 39: the VCC net is 1.6 mm, the P/S net 5.4 mm (it was 32 mm), DRC 0, the release passes with the
same gate line for all five launches (`In1_Cu 2.20  In2_Cu 2.20  B_Cu 2.20  F_Cu 1.90 mm`), the cost unchanged.

**The taper.**  Your memory is right, and the study's own text says so (FIELD_SOLVER.md, "a warning about reading
the taper number literally"): its `TAPER_LEN = 1.0` polygon started at the pad's centre with the pad's half-width,
so on a 1.95 mm pad it spent 0.975 mm of its 1.0 mm inside the disc and the optimised footprint had, in its words,
"in effect, no taper at all".  Here the taper was built the other way, from the pad's edge, so the comparison in
`docs/LAUNCH.md` 4.1 is between a real 1 mm taper and none: −7.11 against −7.14 dB at 5.8 GHz, −6.70 against −6.73
dB worst over 4-6 GHz, 19 % reflected both ways (the taper adds 0.3 nH of series inductance and 0.09 pF, which
cancel).  0.03 dB on a model whose mesh moves the answer by 0.7 dB: the same launch.  The taper code is gone from
the footprint, the constants and the gerber check (build 38 already had it switched off, so the copper does not
change): the pad is JLCPCB's plain 2.0 mm circle, symmetric under any rotation.

**CLAUDE_PCB.md.**  Section 14 opens its launch notes with "**The stock SMA footprint is wrong for a launch above a
GHz, and it has bitten twice**": the SYZYGY first test board's 70 % on the bench, CostasLink build 36's 85 % in the
gerbers a commit before an order of about $1,000; what the vendor's and KiCad's default pad does (the full ring on
every layer, the planes at the zone clearance, the top pour at the CPWG gap, DRC content with all of it: 2 pF at
5.8 GHz); then standard practice for every through-hole RF launch from now on, seven points: end layers only
(confirmed in the plotted layers), rule-area antipads on every inner and back layer (never a DRC rule, never the
pad's clearance property, and why), the top pour the solved distance off as a rule area, a plain round pad with no
taper and no sub-0.3 mm annulus, nothing else inside the legs (a router keep-out), the field solve re-run on the
actual stack with the anchor, and the gerber parser as a release gate, which is section 10's new gate 22.
2026-10-15 04:58 PDT

## Prompt 35 (2026-10-17 ~14:15 PDT)

"As you go through these suggestions and corrections, look around to make sure that everything that you come
across makes sense for this project and for the success of this PCB.

The description "A 5.8 GHz link that carries a bit (or two) FPGA to FPGA in the speed-of-light time plus about
25 ns. The receiver is a quadrature demodulator whose LO is a synthesizer on a VCXO; the Costas loop steers the
VCXO, so the LO stays on the far end's carrier and the demodulator's I output IS the data, Q the phase error. The
transmitter is a quadrature modulator driven by two 2-bit resistor ladders from FPGA pins. PLAN.md has the
arithmetic; sim/budget.py computes it." is old. For example "the demodulator's I output IS the data, Q the phase
error" is for PSK, but we're also doing other stuff. At least add "For example, for PSK,". In general, go through
the comments and make sure they actually reflect the current state of the project goals, the schematic, and the
PCB.

On page 1, many of the pins coming from "Power and FPGA header" have what look like double labels. CMP_IN and
CMP_IP for example. Similarly for the "Window comparators: I and Q" box.

Is the power system correct, with the PTC and P-FED ideal diode? Will there be issues powering this up from
either USB or the PYNQ-Z2's 5V (when running on its barrel) external 5V?

There are several test points that are still test pads rather than MMCX (if it fits) or surface-mount U.FL if it
does not. Examples include "TR A", "LOG Q", "LD U203", and an unlabeled one next to what looks like an IC
labelled "LD U115". Even the row of DC voltage test points along the bottom (from 5V_IN to 3V3_OSC) should be
surface mount U.FL, at least in addition to the existing test points. The test points are easy to probe with a
multimeter, but difficult to automatically monitor from computer-controlled lab instruments.

The corner of the board is labeled "RECEIVER 5.8 GHz", but it's both a transmitter and receiver. Maybe re-label
"TRANSCIEVER 5.8 GHz"

The SMA label "ANT" I think is for a single antenna that can be both in and out. Maybe label it on two lines
"ANT" and "TX+RX". The SMAs labeled "TRIG A" and "TRIG B" should indicate that they are outputs. If "TRIG OUT A"
and "TRIG OUT B" does not fit, add another line of small text above "3.3 V, 1.7 V/50R", shifting "TRIG A" and
"TRIG B" up a bit.

The set of regulators like TPS7A2033 are far away and seem only connected to power-hungry ICs by thin traces.
Is this sufficient? It seems like the traces get thin for no good reason. They could be thicker. Maybe they
could be moved a bit to avoid vias if that's what's keeping them thin. I'm also confused why they are
floorplanned so far away from everything. These are linear regulators, not switching regulators, right? In
general, the board is extremely crowed toward the SW corner and extremely sparse toward the NE. Maybe there is a
good reason for this, and maybe it's not worth changing, but if the reason for keeping it this way is not
sufficiently strong, feel free to spread things out more and move the power regulators closer to the place where
the power is used.

The 4-pin raspberry pi header appeared rotated 90 degrees in the underside of the 3D rendering.

I'm actually confused how I'm supposed to hook things up if I have a separate TX and RX antenna vs how I hook
them up with a single antenna. If I have a single antenna, do I have short SMA cables that go from "SW TX" to
"TX ANT" and "SW RX" to "RX ANT"? This is what the comment at the top of page 5 indicates: "Fit this block to
work with ONE antenna per direction: cable TX ANT -> SW TX and SW RX -> RX ANT" On the PCB, the same information
should be in the silkscreen. "If you want TX and RX to share a single antenna, connect that single antenna to ANT
and run short SMA cables from TX ANT -> SW TX and SW RX -> RX ANT." This info can be on the back.

In general, user instructions can be on the back silkscreen. Things like "You can give this board 5V_IN either
from a PYNQ-Z2, which is powered from a barrel connector, or from the USB-C plug, which is only to supply
external power (no data)."

You have a little info box in the schematic under the HMC536 switch. Add its switching time to that box and any
other relevant information.

The very first thing I see in the RX signal path is C101 right on top of the SMA connector. Why? Arrange the
schematic so that the SMA is first, then the inductor and capacitor. Look at these schematics to determine if
they make sense visually.

Neither I, nor a casual student reader, will be familiar with what each IC is. The SKY65404-31 LNA needs to be
labeled "LNA +13 dB" somewhere. The PE43711 needs to be more clearly labeled "RF Digital Step Attenuator" and
needs to have a negative in its dB range for attenuation, the ADL5611's need to be labeled "+14.3 dB gain @ 5.8
GHz", the THS4541 labeled "Fully differential amplifier", 74LVC1G3157 needs to be labeled "single-pole
double-throw analog switch", OPA2388 needs to say "Op amp", MCP4728 needs to say "DAC 12-Bit", the AD4113 needs
to say "ADC 16-bit", MAX2871 needs "PLL up to 6.0 GHz" etc. Maybe the only change needs to be that in your little
info boxes, the first thing you say about the IC is its function. Then you can give the details that you give
about being in the "the FAST arm" or whatever.

Have an info box above the "JP101 / JP102 SIGN" one that explains that "sign(I) x Q" is not computed with a
multiplier, instead comes from a switch either selecting +Q or -Q based on the sign of I, which come from CMP_I
above.

You have two boxes that start "THS4541, the FAST arm" with mostly identical information. Separate out the
identical information to a box in between the two THS4541's. Then talk about the I and Q specific information in
between I_P and I_N or between Q_P and Q_N.

It is too slow to have the I and Q come onto header pins and through a jumper before they go into the
74LVC1G3157? If it's fine, keep it, but I thought that these headers and jumpers were too slow for 100 MHz
signals.

Is it good, low-noise RF receiver design to have a modest +13 dB LNA followed by a step attenuator and then the
ADL5611 gain blocks?

Make an info box near where V_MID is made, which explains what V_MID is the mid-way point of the 3V3 analog
supply and used in many comparators to compute the "positive or negative" sign and in opamps where a ground
would be used in a dual-supply situation, since all analog levels are shifted to be between 0 and 3.3V.

The wire around C130 looks wrong. Take a look.

You can get rid of the comment that starts with "The OPA2187 first drawn here..."  The schematic does not need a
record of your mistakes. That's what the chat is for.

I am confused about how the one antenna scheme works and how it holds its frequency while not receiving. There
are some words about "An MMCX-to-SMA lead to the TX sheet's REF IN (JP201 to REF IN) locks our carrier to the one
we receive: the one-antenna T/R mode needs it".  But if both boards on both sides of the connection are
connecting their REF OUT to REF IN, how is this not just "the dog eating its tail," where the two VCOs will
wander away together until they reach some limit? Just to be clear, with one antenna, they need to share a
channel, and not just that, they'll actually try to share a phase-locked frequency (to the best of the PLL's
holdover ability). This scheme is better than each independently holding over its last-received tuning voltage
while it is transmitting? (Using a sample and hold capacitor or something like that?) This may be the best
scheme, but I don't think I read your justification of it.

Where on the MAX2871 does the error signal affect the PLL? It looks like it only affects the VCXO at its VC pin.
Maybe this is the right way to do it. But I thought that's what the PLL's TUNE pin was for. Why was the VCXO's VC
pin chosen to be the analog "nudge" to lock the phase of the incoming signal? Have you checked that this VCXO can
be nudged the right amount by our VC signal?

Some of the SMA symbols in the schematic have their ground awkwardly above the connector instead of below. Look
at them and make sure they all look ok. In general, look everywhere on the schematic and make sure that labels
are legible and the way that the wiring is drawn makes sense.

Would it be possible to "OR" the TRIG IN and the FPGA's trigger, which I think is on TX_Q1? This way I would not
need to solder or unsolder the R226 resistor? In the experiment, there will be one of N photon detections in one
of N detectors. Often N=2, but the signal will probably need to go through the FPGA before the FPGA tells the
transmitter which of N states to go to (instead of idle). For lab testing of the communication system itself,
I'm not exactly sure what the "TRIG IN" and "TRIG A" and "TRIG B" will be used for.

With the currently fitted FPGA outputs to the modulator and comparators from the demodulator back into the FPGA,
which of the TRAJECTORIES.md schemes can we do? Can we do a full idle+4? Or do we not have enough modulator
levels and comparators?

In the Window comparators sheet, move the DAC under the long incoming wires and actually connect signals like
V_TIP and V_TIN up to the inverting inputs (in addition to labeling the nets).

How are all of the I2C addresses handled? Can all of the chips be reached?

Make jumpers for the I2C pullup resistors, so that I can switch between the PYNQ-Z2 to the Icepi Zero without
soldering and unsoldering resistors."

## Response 35 (2026-10-17 14:15 - 17:29 PDT)

Everything below is in the generators, the documents and the board (build 40); the answers to the questions are
here and, where they belong on a sheet, in a box at the node.  REVA_CHANGES.md rows 43-50 list the hardware changes.

**The description.**  The root's box now says what the project is (one or two bits, both hosts, the window and the slow
paths, the T/R switch) and "for example, for BPSK, I is the data and Q the phase error"; PLAN.md section 1 and the README
say the same.  The title line says "transceiver ... for the PYNQ-Z2 and the Icepi Zero".  I went through every box on the
seven sheets while doing the rest: each IC's box now opens with what the part is (SKY65404-31, LNA; PE43711, RF digital
step attenuator: 0 to -31.75 dB; ADL5611, gain block; THS4541, fully differential amplifier; 74LVC1G3157, single-pole
double-throw analog switch; TS5A3159, SPDT analog switch; OPA2388, dual op amp; MCP4728, 12-bit quad DAC; AD5696R,
16-bit quad DAC; ADS1115, 16-bit 4-channel ADC; MAX2871, PLL frequency synthesizer 23.5 MHz-6.0 GHz; ADL5380, quadrature
demodulator; ADL5375-05, quadrature modulator; HMC536MS8G, T/R switch; TLV3601/3603, comparators; AD8310, logarithmic
amplifier; TC32H4 TCXO; SX3V VCXO; the LVC buffers and inverters; the LDOs) and then the detail.  The OPA2187 sentence
is gone.

**The double labels (page 1).**  kisch drew a sheet pin's name OUTSIDE its box (the justification was inverted against
KiCad's own convention), so the net label I put on the pin for the window sheet's nets printed on top of the pin's name.
The names now read inside the sheet boxes, as KiCad draws them, and the labels stand beside the pins.  The receiver
sheet moved down 12 mm so the longer description clears its wires.

**The power system.**  It is right, and both sources work: USB-C alone (Q303 sees VBUS, pulls Q301's gate down: Q301
on; Q302's gate is lifted to VBUS through the 1 k: off, its body diode reverse-biased by the board's own 5 V), the
header alone with JP301 fitted (VBUS absent: Q303 off, Q301's gate goes to +5V_HDR through the 100 k: off, body diode
reverse-biased; Q302's gate sits on its 100 k to ground: on), both at once (USB wins; the header's FET is off and its body
diode would conduct only if the PYNQ's 5 V were 0.6 V above a sagging VBUS, when it would just help).  The 2 A PTCs
carry the 1.37 A; the PYNQ-Z2's 5 V rail (its barrel regulator) has that to spare, the Icepi Zero does not, so on the
Icepi it is USB-C with JP301 open.  Power the PYNQ first (Prompt 32: its clamps).  The JP301 box on sheet 2 says all
this, and so does the back of the board now.

**Test points to jacks.**  LD RX (J190), LD TX (J290) and LOG Q (J590) are U.FL (their corners are full: a 5.5 mm MMCX
does not fit beside a QFN-32's loop filter), TR A (J490) is an MMCX in the switch corner, each through its series
resistor (453 ohm for the logic lines, /10 into 50 ohm; 1 k for LOG Q); the seven rails have a U.FL each through 1 k
(J390-J396, the "RAIL MONITORS" block between the TX chain and the regulators, two rows at a U.FL's 5.5 mm pitch), and
their test pads stay along the bottom edge for a meter.  Every one is drawn last on its sheet with explicit
references, so no hand anchor moved; BRINGUP.md, PATHS.md and the silk say the new names.

**"RECEIVER 5.8 GHz".**  It was the receive chain's block name, and at the corner it read as the board's.  The blocks
are "RX CHAIN 5.8 GHz" and "TX CHAIN 5.8 GHz" now; the board's name is the title between the SMAs.

**ANT, TRIG A/B.**  ANT prints "ANT" over "TX+RX" (its +27 dBm MAX did not fit between SW TX and ANT: SW TX's +25 dBm MAX,
which binds, is 8 mm away).  "TRIG OUT A" does not fit before the DSA, so TRIG A and B keep their names with "OUT" on
a small line above "3.3 V, 1.7 V/50R", as you suggested; the placer's strip reservation and tools/label_check.py now
take a two-line limit (KiCad prints the newline).  TRIG IN MON moved under TRIG IN's label to make the room.

**The regulators and the thin rails.**  Measured on build 39: +3V3_ANA had 157 of its 246 mm at 0.20 mm, +3V3_DIG 216 of
398, +3V3_OSC 104 of 138, the PLL rails 61-90 mm at 0.2 (they also have In2 pours).  The router lays every rail at 0.2 and
the widening afterwards found room for 0.4 on about a third of the length.  Electrically that is 5-15 mV at 40-60 mA
(sim/budget.py section 9's drop is in the 5 V path, not here), but thin for no reason, so I tried routing the rails at
0.3 mm.  Six builds later the verdict: every net routes at 0.3, but the widening and the tidy pass then leave a 0.2 mm
sliver at the DSA's VDD pin that each refill pass removes and the next tidy re-makes, forever (builds 40a-f).  So the
rails are routed at 0.2 as before and widened to 0.3 / 0.4 where the copper leaves room (measured on build 40: +3V3_ANA 95 of 253 mm at 0.4 and 97 at 0.2 (was 50 / 157), +3V3_DIG 137 of 423 mm at 0.4 (was 99), +3V3_OSC 33 at 0.4 and 95 at 0.2, the PLL rails 19-52 mm at 0.4 over their In2 pours); fixing the tidy is
a REVA_CHANGES row, not a day-before-the-order change.  The regulators themselves stay where they are, for a reason I
think is sufficient: they are linear (no switching noise), every chip has its own capacitors at its pins, and each
rail's loads are all over the board (ANA: the LNA at the top-left, the arms bottom-left, the loop in the middle; DIG:
comparators at the bottom, switches, buffers top-left, DACs on the right), so there is no "near the load" to move to;
the column sits where the 5 V comes in (USB-C on the right edge, the header's 5 V bottom-right) and the rails fan out.
What filled the empty north-east is the rail monitors (four in a row, three beside their regulators), the two
lock-detect jacks, TR A's MMCX, the I2C jumpers and the layer marks.  The south-west stays dense because everything
there (the chains, the arms, the slow path, the comparators) is tied to the RX SMA at the top-left and the header along
the bottom; spreading it would lengthen the 100 MHz pairs.

**The 2x20 socket's 3D model.**  KiCad's stock PinSocket model runs its rows along the footprint's y; the underside
socket is drawn with its rows along -x (the mirror the flip needs), so the render showed it turned 90 degrees across
the board.  The model has a 90-degree rotate in the footprint now (gen/footprints.MODEL_ROT), checked in a render.  The
footprint and the netlist were right all along: this was only the picture.

**One antenna: how to cable it, and the frequency question.**  Sheet 5's header box and the back of the board now say
it plainly: the antenna on ANT; short SMA leads TX ANT -> SW TX and SW RX -> RX ANT; the FPGA drives TR A; two antennas
means RX ANT and TX ANT with the switch block unused.  And the lead: **one board only**, the prover.  The verifier
transmits on its TCXO (JP201 on TCXO); the prover's Costas loop locks its VCXO to that carrier and, with REF OUT -> REF
IN (JP201 on REF IN), its own transmitter runs from that VCXO, so its reply is at the verifier's frequency and phase (a
transponder).  Both boards on the lead would be exactly your dog: two VCXOs locked to each other and to nothing else,
wandering together to a rail.  Your sample-and-hold is what LOOP_HOLD already is (the TS5A3159 opens the integrator's
input, the 100 nF keeps VC: 0.1 rad after 6 ms typical, PLAN section 18's table), on both boards while they transmit;
the lead is what makes the carrier that comes back the one the verifier's loop was holding on, so the loop resumes
instead of re-acquiring (3.8 ms from 30 kHz off).  Without it the prover would reply on its own TCXO, up to 29 kHz away,
and the verifier would re-acquire every slot.  The notes at REF OUT, at JP201 and on sheet 5 say which board, and
PLAN.md section 14 has the argument.

**VC, not TUNE.**  The MAX2871's TUNE pin is the node inside its own loop: its charge pump and 80 kHz loop would correct
any voltage added there as an error (and open-loop the VCO is 60 MHz/V and drifts).  The reference is the clean handle:
the synthesizer follows it x232 with its own loop, and the 3 kHz Costas loop sits well inside that (asserted in
sim/budget.py section 6).  The reach is checked there too: two TCXOs differ by at most 29 kHz, the VCXO's guaranteed
pull is +-290 kHz (+-100 ppm typical = +-580 kHz), VC spans 0.3-3.0 V and the OPA2388 swings rail to rail; Ko = 430
kHz/V of LO.  The VCXO's box says so now.

**The SMA symbols.**  Conn_Coaxial has its pin on the LEFT and its shield below.  An input drawn at rot 0 (RX ANT, ANT)
put its body under the first DC block, which is what you saw at C101; an output drawn at rot 180 (TX ANT, SW TX, SW RX,
TRIG IN) put the shield on top with the ground above.  Inputs are mirrored now (pin facing the line, the jack first),
outputs at rot 0, the couplers' monitor jacks upright, and every ground hangs below.  The wire round C130 was the PI
filter's feedback column standing left of the capacitor's end, so the wire ran back over it; the column is at the
capacitor's pin now.  The window DAC sits under the long input lines with its four outputs wired up their own columns
into the comparators' inverting inputs (the labels stay too).

**sign(I) x Q and the jumpers' speed.**  A box above JP101/JP102 explains the switch: +Q or -Q by the comparator's
sign, the product of a +-1 and Q, no multiplier.  The jumpers are fine where they are: only the AVERAGE of the product
feeds the 3 kHz loop, so a few pF and nH on the Q legs or on the select do nothing, and CMP_I (33 ohm source, then the
PYNQ's 200 ohm and 10 pF) does not notice the stub to JP103.  Said in JP103's box.

**LNA, then the attenuator, then the gain blocks.**  Yes, that is the textbook order: the LNA sets the noise figure
and everything after it counts divided by its 20 (13 dB); the DSA at 0 dB costs 1.5 dB / 20 = 0.1 dB of noise figure
and at short range it cuts the signal before the gain blocks and the demodulator can compress (it holds the demodulator
at -20 dBm from 3 m to 300 m); put after the gain blocks it would protect nothing, put before the LNA it would add its
whole loss to the noise figure.  The chain's NF is 2.0 dB by Friis (sim/budget.py).  The DSA's box says it.

**V_MID.**  A box at the divider: the midpoint of the 3.3 V analogue supply, standing in for the ground of a dual-supply
circuit since every level on the board lives between 0 and 3.3 V; the op amps' + inputs, the comparators' sign, the
arms' centre and the hold switch's park position all sit on it.

**TRIG IN OR the FPGA's bit.**  Done without a gate: the Schmitt buffer's output is now the Q ladder's THIRD LEG
(R291 2.2 k into the Q node).  A TRIG IN high adds one ladder step (+0.36 V at the node: +Q) to whatever the FPGA's two
Q bits set, an OR by summing currents, with no gate delay on the FPGA's bits and no contention (the old DNP 0 ohm put
the buffer's push-pull output on the FPGA's pin).  To keep the Q ladder's step, impedance and settling equal to the I
ladder's with the extra leg, its reference resistor is 348 ohm (C25107, in stock) instead of 300, and VR_Q becomes 0.246 V
(VR_I stays 0.21): sim/budget.py section 1 computes and asserts it, the driver gets VR_I_V / VR_Q_V / TRIG_STEP_V.  The
buffer's input has a 100 k to ground (R226, the reference the 0 ohm had) so a floating TRIG IN cannot key the
transmitter.  Keep TX_Q1 low while a trigger is in use: both high would put the node 0.19 V over the 1 V range (the
absolute maximum is 2 V).  For the lab: TRIG IN MON here against QP MON on the far board is still the link's own latency,
with nothing to solder and no CTRL[8]; in the experiment the FPGA keeps the four bits and a detector can also key +Q
directly.  BRINGUP.md stage 6.7, PATHS.md and the gateware README say so; CTRL[8] stays in the register map, unused.

**Which schemes rev A can run.**  Each ladder gives c - a, c, c + a with c set by VR_I / VR_Q and the receiver has
sign(I), the four windows IP / IN / QP / QN on 16-bit thresholds and the slow three.  So A1, A2, **A3 (the full idle + 4
corners)**, A4, B1 and B2 all run, and J1 now that the I window pair exists.  B1's pilot is c on I; B2's pilot at 45
degrees is c on both axes and its corners are then the square round the pilot, which the loop's -45 degree turn lands on
+-I and +-Q as the scheme wants.  Not possible: J2 (five levels) and R4 (weighted AC-coupled comparators).  PLAN.md
section 18 has the paragraph.

**I2C.**  Five parts, five addresses, all fixed by part or pin: 0x0C AD5696R (A0 = A1 = 0), 0x48 and 0x49 ADS1115 (ADDR
to ground / to VDD), 0x60 MCP4728 and 0x61 MCP4728A1 (the factory-preset variant).  One bus from header pins 3/5, all
reached (the driver's i2c_scan expects exactly those five).  The pull-ups: 4.7 k each behind a jumper now, JP302 (SDA)
and JP303 (SCL), open on the PYNQ-Z2 (2k2 on its header), fitted on the Icepi Zero; the addresses are listed in the box
beside them.

**The HMC536 box** has its switching now: 30 ns from the control's 50 % to the RF at 10/90 % (tON, tOFF), 15 ns RF rise
and fall, control 0 V (25 uA) / 3-5 V, -0.5 to +7.5 V absolute, 12 dB return loss at 4-6 GHz.

**The board.**  Build 40: 4304 tracks, 1159 vias, every net joined, DRC 0 items (0 violations, 0 unconnected, 0 parity), the label check 0 violations (the five exemptions on record), the launch gate as before, the documents' numbers 0 stale, and mfg/make_release.py passing every gate: 81 BOM lines, nothing consigned, JLCPCB $689 of goods, $955-970 with duty and shipping (up $12 for the eleven jacks, the two jumpers and the 348 ohm).  It took seven builds (40a-g): the new jacks fought for room in the arms' corner (LD RX's pad spot sat in the I_P corridor; the ADC's filter capacitor I had nudged 0.7 mm walled its resistor's pin in; the coupler's load wandered to the wrong side of the coupled line and the tidy trimmed the line), and the rail monitors' names needed the placer's strip rules extended (two-line limits, a column row's shared limit, exemptions).  Each is a lesson in CLAUDE_PCB.md section 5.  The user's instructions are on the back silkscreen in three blocks (one
antenna / two antennas; the 5 V sources; the jumpers' defaults).  Lessons in CLAUDE_PCB.md sections 4 (sheet-pin
names inside the box; a coaxial jack's pin faces the line; every IC box opens with its function; no history of
mistakes on a sheet), 6 (a two-line limit; instructions on the back), 9 (a pad an instrument will watch is a jack) and
11 (a stock 3D model's axes).

**Open, on record.**  The 0.3 mm rails (REVA_CHANGES 50: the tidy's sliver).  The silkscreen's own problem list has 98 entries, as build 39 had 72: block boxes that cannot be drawn as rectangles because a side would cross a part (their names are printed instead) and chip names that found no clear spot beside their chip (printed where there is room, else left to the fab layer); none of it is a connector, a limit or a jumper, which the label check covers.  The CPL rotations stay for the order day, as agreed.

## Prompt 36 (2026-10-17 ~17:40 PDT)

"Do one more design review, tracing the signal path and power paths visually in the schematic and PCB, at each point
asking yourself if this is the right way to do things for Quantum Position Verification and this pedagogical and
experimental test board. If it's ready to send to JLCPCB for manufacture and assembly, I will do that when your review
is done."

## Response 36 (2026-10-17 17:40 - 18:24 PDT): the design review before the order

I walked every path on the seven sheets and on the copper (tools/path_walk.py over build 40's netlist, the sheet
renders quarter by quarter, the top, In2 and back renders, the 3D views), asking at each hop whether this is right
for a quantum-position-verification test bed that students will read and that must deliver a bit with as little
electronics as possible in the way.  Three things changed (REVA_CHANGES 51-53, build 41); the rest is the
reasoning, kept short where the sheet already says it.

**The receive chain, hop by hop.**  RX ANT -> L101 6.8 nH to ground (static off the cable; 400 ohm-1.5 k at 5.8
GHz) -> C101 1.5 pF (series-resonant at 6.1 GHz: the best 0402 block there is) -> SKY65404 LNA with Skyworks' own
0.5 pF shunt, 0.6 nH + 100 nF on VCC, 100 ohm on the enable -> block -> PE43711 DSA (serial mode, P/S 10 k up, the
parallel pins grounded, powers up at -31.75 dB: the receiver wakes up deaf, which is the safe way) -> block ->
ADL5611 -> block -> ADL5611 (each with its 43 nH bias tee and 68 pF / 1 nF / 1 uF) -> block -> the copper coupler
(RX MON -20 dB, 49.9 ohm on the isolated port) -> the TDK balun -> two 1.5 pF blocks -> ADL5380 (ADJ open, the 5.8
GHz spec condition; the DNP 1.5 k to drop the common mode if ever needed).  Right for the job: the LNA first sets NF
2.0 dB, the attenuator between the LNA and the gain blocks is the only place it protects anything, 28.6 dB of gain
puts -20 dBm on the demodulator from 3 m to 300 m, and the demodulator's 390 MHz output is the widest thing in the
chain.  The one thing a student should be told, and the sheet says: +1 dBm absolute maximum at RX ANT, so the PA
module across the room is dangerous to this input (the limiter note).

**The arms and the decisions.**  Each pair through 1 k into the THS4541 with 1 k shunts holding the summing nodes
at 1.9 V (the demodulator sits at 3.2-3.8 V; the amplifier's inputs are good to 2.0 V, 61 mV of margin at the worst
corner), gain 4, VOCM open with its 100 nF (the THS4541 centres itself at mid-supply), outputs straight into the
comparators and the taps: nothing in series with the data but copper and the 33 ohm at the FPGA.  That is the
whole point of the board and it is intact: jack to FPGA register 15 ns on the PYNQ.  sign(I) on the clock-capable
pin 18; the four windows on their own 16-bit thresholds, LE/HYS with the two DNP options; the slow path x20 at 4.8
MHz with its own three comparators and its own DAC for the veto.  I looked for a place where a 100 nF or a 10 k had
crept onto a fast node (Prompt 31's fault) and found none: every ADC input has its 10 k between the node and the
capacitor, every tap its 1 k or 453 ohm.

**The loop.**  Q+ / Q- through the two SIGN jumpers into the 3157's B1 / B2, the sign from CMP_I through JP103 (100
k holding S low when the jumper is out), ERR through the TS5A3159's NC, V_MID on its NO, into the 10 k / 750 ohm /
100 nF PI integrator about V_MID, the summing stage adding VC_OFF, VC to the VCXO's pin 1 and to its jack and the
ADC.  3 kHz inside the synthesizer's 80 kHz; the VCXO's +-290 kHz guaranteed covers the 29 kHz between two TCXOs
with ten to spare.  For QPV this is the right loop: analogue, visible at ERR MON and VC MON, holdable by a pin, and
the data never passes through it.

**The transmitter.**  Four FPGA pins through 2.2 k into 300 / 348 ohm references at 0.21 / 0.246 V, +-0.33 V about
0.5 V on IBBP / QBBP, the N inputs on the 4.7 k / 750 divider that the pins' own 82 uA lands on 0.507 V; TX_DIS
from the inverter with its 1 k pull-down (off whenever no gateware drives it); LO through the same choke-and-block
tile as the receiver; RFOUT -> block -> ADL5611 -> bias tee -> block -> the 0 ohm pad (DNP shunts) -> coupler -> L202 to
ground -> TX ANT at +9.8 dBm, the corners at the gain block's P1dB and no further.  The TRIG IN leg into the Q
ladder is where the review changed something: with the leg always live, a detection on TRIG IN steps the air to +Q
at once, and in the experiment where the FPGA must choose which of N points a detection sends (your N = 2 case), the
FPGA could not stop it.  **JP203 TRIG>Q** is now in series with the leg: fitted (the default) for the lab's FPGA-free
keying, open when the FPGA alone sets the point.  Seven shunts a board.

**The one-antenna block, the triggers, the references.**  ANT -> L401 -> C401 -> HMC536 RFC; RF1 / RF2 through
their blocks to SW TX / SW RX; A from header 27 through 100 ohm with 10 k up (rests in receive), B = not A from the
inverter with 10 k down; J303 for an external switch.  TRIG A / B through 33 ohm; TRIG IN through 1 k into the
Schmitt buffer with the 50 ohm jumper and the 100 k; REF IN through the DNP 49.9 ohm to JP201; REF OUT from the
VCXO through its buffer and 33 ohm.  Here the review found the second change: **TR A's tap was 453 ohm**, and TR_A
reaches the board through the PYNQ's 200 ohm, so a 50 ohm scope input on that jack would have held the control at
2.4 V, under the HMC536's 3 V: watching the switch would have stopped it switching.  R490 is 4.7 k now (3.17 V at
the switch with a 50 ohm load, 35 mV at the jack, the full swing on a 1 M probe; the silk says "3.3 V hi-Z, 35
mV/50R").  The other logic taps (LD, TRIG IN MON, the comparators) sit on outputs that can source the 6.6 mA.

**Power.**  USB-C (Rd 5.1 k on both CC) -> 2 A PTC -> Q301 (gate pulled down by Q303 when VBUS is there, up to +5V_HDR
otherwise) and the header's 5 V -> JP301 -> PTC -> Q302 (gate lifted by VBUS through 1 k against 100 k): either
source alone works, both together USB wins, neither back-feeds (I walked both FETs' gates for all four cases).  22
uF x 2 + the 100 uF polymer damper + the TVS; the bead into +5V_RF with 22 uF + 10 uF; the five LDOs each with 2.2
uF in and 2.2 uF + 10 uF out, the PLL ones behind 2.2 ohm for the heat; every chip's 100 nF at its pin on the
sheet and (I checked the top render) within a few millimetres on the board, outside the fan band.  On the copper
+5V_RF is a pour on In2 and 0.8 mm on top; the 3.3 V rails are pours or 0.4 mm where there is room and 0.2 mm
where there is not (5-15 mV).  The one structural thing left for rev B is still row 35: 1.4 A through single 0.25
mm vias three times in series.  It works (15 mV, under a kelvin), and the bring-up measures V5_MON under load.

**The board.**  Both 5.8 GHz chains straight, their fences and launches as the field solve wanted (the release's
gate: planes 2.2 mm off every SMA pin, the top pour 1.9); the LO pairs equal; nothing but the planned line inside
any SMA's legs; the In2 pours for the five supplies where their chips are; the back bare but for the socket, the
instructions and the identity; the socket's model the right way.  DRC 0, every net joined, the label check 0, the
launch check as designed, the documents' numbers 0 stale, the release passing: 4285 tracks, 1157 vias, 81 BOM lines, nothing consigned, 416 placements a board, 7 shunts and the socket loose; JLCPCB $689 of goods, $955-970 with duty and shipping.

**Stock on the order day** (row 53): AD5696R C650158 has **2** in JLCPCB's stock for 2 boards (the release passes
because stock >= the order, but JLCPCB may ask for attrition on a TSSOP-16); HMC536 has 5 for 2; the ADL5380 18, the
ADL5375 654, the THS4541 262, the TLV3603 2844, the VCXO 408.  Re-run `python3 mfg/make_release.py` on the day: if
the AD5696R line comes up short, Digi-Key stocks AD5696RARUZ (add a `consign=` fallback in gen/parts.py as for the
ADI chips) or fit the second board's U605 at home.  And the CPL rotations off JLCPCB's preview, as agreed.

**A bonus the review turned up**, now in BRINGUP.md 6.7: a prover with no FPGA at all.  A short lead from a
board's QP MON (or CMP I MON) to its own TRIG IN with JP202 open: the tap's 453 ohm into the Schmitt input's 1 k +
100 k gives 3.2 V, over its 2.19 V threshold, so a received event keys the reply +Q about 20 ns after the jack.
The whole hardware round trip, verifier to prover and back, on one scope, with both FPGAs idle.

**Verdict.**  Ready to order.  Nothing I traced is wrong for what the board is for; the two things the review
changed were a measurement that would have disturbed the thing it measured and a leg the experiment needs to be
able to open.  What remains is on record and either rev B (the 5 V vias, the 0.3 mm rails, the header's RC) or the
order day (rotations, the AD5696R line).  My estimate of the first boards stands as in Response 31: they power up
0.85, the synthesizers lock 0.75, the Costas loop locks over a cable 0.6, a bit crosses the bench 0.5, the room 0.4,
and the board teaches something whatever happens 0.9.

## Prompt 37 (2026-10-17 ~22:10 PDT)

"There should be OpticsPCBs/CostasLink-PYNQ-Z2/mfg/release/CostasLink-PYNQ-Z2_gerbers_Y21.zip that JLCPCB wants
me to confirm. Check if there is any reason I should modify these. If not, I'll say, "Yes, proceed to production"."

## Response 37 (2026-10-17 22:10 - 22:35 PDT): JLCPCB's production files, layer by layer

The zip is JLCPCB's CAM output for order 13544840A_Y21 (their `ok/` layers, our upload echoed back byte for byte,
and the order record `4te.json` in GBK).  I rendered each of their layers over ours in one frame with gerbonara,
diffed them pixel by pixel at 20 px/mm, eroded the 0.1 mm slivers of polygon conversion, and matched every
difference that survived to a pad with pcbnew.  Written up as `mfg/PRODUCTION_FILE_CHECK.md`.

Nothing to change.  Outer copper, both masks, both silks, the outline and every hole position are the upload's.
JLCPCB changed three things, all standard: (1) non-functional pad removal on L2/L3: 62 / 59 through-hole pins
with no inner-layer connection (J302's signal pins, every jumper pin, J303, the U.FL jacks' signal pins) lost their
inner annulus, while every pad that does connect inside (SMA legs, the header's GND and +5V_HDR pins) is untouched;
(2) the 5 mm assembly rails above and below the board with V-cuts, tooling holes, fiducials and the SMT QR places,
left and right edges rail-free as the assembly remark asked; the five top-edge SMAs are right-angle through-hole
parts whose bodies sit on the top face, so they rest over the rail and the rail snaps away downward; (3) drills
0.13-0.15 mm over finished size for plated holes, 0.05 for non-plated, vias unchanged at 0.25, J301's 0.6 x 1.1
shield slots routed with a 0.553 mm bit.  The order record agrees with ORDER_SETTINGS.md (4 layers, 1.6 mm,
1 oz / 0.5 oz, ENIG, green, white, vias tented, no order number); it carries no stack-up field, so the order page is
where JLC04161H-7628 shows.

Bookkeeping: the 17 MB vendor zip stays on disk but is ignored by git (`*_gerbers_Y*.zip` in the repository's
.gitignore); the method is in CLAUDE_PCB.md section 8 so the next board's confirmation takes ten minutes.

## Prompt 38 (2026-10-17 ~22:45 PDT)

"Final notes on this revA board JLCPCB submission, which you might want to tweak and update CLAUDE_PCB:

JLCPCB does not allow a "Tented" via option for some boards. I hover over Tented and it says, "The Via Tented
option is upgraded to Via Plugged for free." so say "either Tented or Plugged" in the ORDER_SETTINGS.md when
either are ok.

Parts that I needed to rotate even with the jlcpcb specific CPL:
J101 and all SMAs has to rotate 90 degrees CW "to the right""

## Response 38 (2026-10-17 22:45 - 23:10 PDT): the order's two readings folded back into the generator

Via covering: ORDER_SETTINGS.md's row now reads "Tented or Plugged" with the form's own words and why either is fine
(plugged ink in the exposed pads' thermal vias stops the wicking, tented they wick a little); the defaults table
carries the same so the row is not flagged as a change.  The production record already said 过孔塞油, plugged.
CLAUDE_PCB.md section 8 says to write the field that way wherever either is fine.

The SMAs: the CPL carried +90 for C496551, predicted on 2026-10-09 from "JLCPCB's barrel along +x, KiCad's along
-y".  The footprint says otherwise: its body (F.Fab) runs from x 3.78 to 11.6 at 0, the barrel along +x, the same
as JLCPCB's drawing, so the right correction is 0, and a quarter turn clockwise from +90 in JLCPCB's viewer
(counter-clockwise positive, as KiCad) is exactly 0.  mfg/jlc_rotation.py now carries 0 "read" with the evidence;
the release regenerated (the SMAs' upload angle is KiCad's own; PLACEMENT_CHECKS.txt lists 32 unseen part numbers
instead of 33); CLAUDE_PCB.md's rotation table has the row and a rule above it: a prediction is a placeholder, and
when predicting, read the footprint's own body outline for its direction at 0, not a description of it.  The ECP5
board uses the same vendored footprint and its table had the same +90 (and a build 33 note that "+0 lay along the
edge", which this reading contradicts): its mfg/jlc_rotation.py entry is corrected to 0 "read" with a note to re-read
in its own preview and regenerate its release before ordering; nothing else of ECP5's was touched.  REVA_CHANGES
rows 54-55.  The uploaded Gerbers are kept as uploaded: the regenerated zip and gerbers/ were restored from git so
mfg/release/ still holds the files JLCPCB has.

## Prompt 39 (2026-10-18 ~07:30 PDT)

"Incorporate your recent changes into the bring up instructions."

## Response 39 (2026-10-18 07:30 - 07:50 PDT): the order folded into BRINGUP.md

BRINGUP.md was written before the order and still said stage 0 was ahead.  Now: a paragraph under the heading says
the boards were ordered 2026-10-17 (order 13544840A_Y21, 5 boards, 2 assembled, nothing consigned, ENIG, the vias
plugged, the rails taken off, the production files confirmed against mfg/PRODUCTION_FILE_CHECK.md); stage 0 is
marked done with the order-day facts (every line on the shelf, the two review changes, the SMAs' quarter turn
caught in the preview and corrected to 0 in jlc_rotation.py, the 32 predicted rotations never recorded as read).
Stage 1.0 gains the receiving inspection, before anything is soldered: the SMAs' barrels off the edges; the
polarities a preview cannot check (D303's cathode bar, C320's stripe, the LEDs, D501) with what each costs
backwards; pin 1 on every QFN and MSOP by reference; the SC-70s, the ADL5611s' tab, the oscillators, the U.FL
signal pads, the headers' square pads; a reversed part is a rework before power, and every reading goes into
mfg/jlc_rotation.py as read so the next order's PLACEMENT_CHECKS.txt is short; and the two normal CAM changes
(no inner rings on the unconnected through-hole pins, plugged vias) named so nobody worries about them.  Stage 4.4's
TR A line said "/10 into 50 ohm", which Prompt 36's 4.7 k made wrong: it now says the full swing on a 1 M probe
and 35 mV into 50 ohm, and why.  Risk row 10 (parts and the order) retires at stage 0 and 1.0 with the same facts;
the bench table lists the loupe, the assembly drawing and PLACEMENT_CHECKS.txt, and the shunts' count is seven.
README.md's "Nothing ordered" line now says ordered.

## Prompt 40 (2026-10-18 ~07:55 PDT)

"Everything look correct except the SMAs, which I already told you about."

## Response 40 (2026-10-18 07:55 - 08:20 PDT): the preview's 32 readings recorded

That closes the rotation question for this board.  The 32 part numbers (83 placements) the CPL carried as predicted
are recorded as read in mfg/jlc_rotation.py, each by LCSC code with the KiCad footprint named (a module constant
REVA_READ carries the reading); the four that were already in the table as predicted (the 1x2 header, the MMCX, the
U.FL, the ADL5611's SOT-89) are read now too, their datum moves included.  The CPL's numbers do not change, since
the predictions were the numbers: the regenerated upload is byte for byte the one before, and PLACEMENT_CHECKS.txt
lists nothing unseen.  The uploaded Gerbers and zip are kept as uploaded (restored from git after the regeneration,
as in Response 38).  REVA_CHANGES row 56; CLAUDE_PCB.md's table has the row and the headers' row says read; its
rule paragraph records the score: the predictions by pin number were right 32 for 32, the one from a description
of the footprint was the wrong one.  BRINGUP.md: stage 0.3 says every rotation is a reading; stage 1.0's inspection
is now a check that JLCPCB placed what the preview showed (the SMAs, the polarity marks, pin 1 on the QFNs that are
hardest to rework, the ADL5611s' tab, the U.FL pads), and a difference is JLCPCB's placement error rather than a
reading to record.
