# Rev B for the QPV experiment at UIUC: the design space (the night of 2026-11-02)

Prompt 43 (2026-11-02, `../CLAUDE_CODE_CHAT.md`).  Jason: one prover and three verifiers; the radios are the only
low-latency, timing-accurate links in the experiment; the rev B board should combine what the CostasLink and the
SyzygyRadioBoard each taught; is the Brain-1 the right platform, or an UltraScale+ board with an FMC "beast", or the
FPGA's own transceivers through SFP/QSFP; compare the alternatives on latency, price, complexity, the chance of a
working first JLCPCB run and of a working first deployment.  Prices and stock below were looked up on 2026-11-02
(sources at the end); they move.

This builds on three earlier answers, which it does not repeat: [`SYSTEM.md`](SYSTEM.md) (Prompt 27: the prover's
turnaround budget, the verifiers' synchronization over the links, the frequency plan, "one universal radio on SYZYGY,
a Brain-1 at every node"), [`HOSTS.md`](HOSTS.md) (Prompt 20: the latency by host: the PYNQ's 200 ohm resistors cost
3.7 ns, LVDS comparators into a SYZYGY port reach 7.0 ns per event, a carry-chain TDC 6.4 +-0.07 ns), and the bench's
results ([`../bringup/FINDINGS.md`](../bringup/FINDINGS.md), [`../bringup/REVB.md`](../bringup/REVB.md)).

## 0. The short answer

1. **Keep the radio as a SYZYGY pod and buy the FPGA.**  Ten identical radios, any one a spare for any node, is the
   right shape, and the bench just showed that the radio core (two MAX2871s, the I/Q modulator and demodulator, the
   analog Costas loop, five comparators) works and holds itself up unattended.  What the pod changes is in section 3.
2. **The carrier is a separate decision, and it can change later without touching the radios.**  For the first
   deployment the Brain-1 ($450, three Standard ports, Linux, in stock) does the job with 7.0 ns events (HOSTS.md).
   The better carrier when the Brain-1's age bites is **a small custom carrier for the Kria K26 SOM with three SYZYGY
   sockets** ($351-550 for the SOM, a modest board with no RF and no DDR on it, PYNQ supported on Kria): one
   UltraScale+ box per site, rugged, cheap, and the radios unchanged.  Section 5 compares all the options.
3. **FMC buys no sourcing advantage.**  The FMC connectors are Samtec parts too (ASP-134486/134488), not in JLCPCB's
   own library; JLCPCB's Global Sourcing service buys from the distributors for assembly in 9-20 business days,
   which is how to get a Samtec QTE (SYZYGY) or ASP (FMC) onto an assembled board without consigning it.  What FMC
   does buy is 160 I/O and GT lanes on one connector, at the price of one large board per site with no spare except
   another whole board, hanging off a $1,800-3,600 evaluation board.
4. **The FPGA's transceivers do not replace the Costas receiver for rev B.**  They are NRZ serializers with a clock
   recovery; they could in principle carry PSK at an IF by patterns (section 4), with about 20-30 ns of their own
   latency, but nothing of that is proven, the comparator receiver's windows and calibration would have to be
   reinvented inside a CDR we cannot tune, and the RF board is needed anyway.  **Where they do belong is the fibre
   between V0's optics lab and its roof**: the radio and its FPGA go on the roof behind the dishes, and the lab's
   digital signals (the basis, the herald, the detector pulses) travel as bits over fibre or as pulses over coax, not
   as 5.8 GHz over 30 m of coax (10 dB).  A cheap experiment to settle the transceiver-modem question is in 4.4.
5. **Design the receiver for 1 of 8 and the transmitter linear; use 1 of 4.**  Four more window comparators on the
   diagonals cost a few dollars and ten pins; the saturated transmitter (REVB 35) is what has to go.

## 1. What the experiment asks of the radios

**The sites and the links** (Jason's description, with SYSTEM.md 4):

| site | radios | links | what each carries |
|---|---|---|---|
| P, the prover | 3 | P <-> V0, P <-> V1, P <-> V2 | in: three "1 of 4" messages (1 of 8 wanted) at the same instant; out: the result (click A, click B, no click, invalid) as fast as possible |
| V0, the source and first verifier | 3 | V0 <-> P; V0 -> V1; V0 -> V2 | its share of the basis to P; the time and frequency reference to V1 and V2 (the herald and the round's schedule may be slow: a fibre coil absorbs microseconds, SYSTEM.md 4) |
| V1, V2 | 2 each | Vk <-> P; V0 -> Vk | its share to P at the agreed time; the reference in |

Ten radio ends, six one-way links whose latency counts (Vk -> P and P -> Vk), two that need precision and not speed
(V0 -> Vk).  **One radio design does every role**: each is a transmitter and a receiver on its own frequencies.

**Latency.**  Only the prover's turnaround counts (SYSTEM.md 1: the verifiers' delays are calibrated out, and the
photon can wait in a coil).  Jason accepts about 20 ns of FPGA turnaround.  The bench's numbers: 57-64 ns from a
symbol's start at the far transmitter to its decision in the FPGA, of which the FPGA's own pin-to-pin is 2.7-13 ns on
the PYNQ, the rest the TX edge, the air, the demodulator, the ~94 MHz arms and the settling (FINDINGS 3).  HOSTS.md's
rev B estimate: 7.0 ns per event with LVDS comparators into a SYZYGY port, 6.4 +-0.07 ns with a TDC; the floor is the
FPGA's buffers, the RF chips and the arm's rise, none of which depends on the host.  The chain around the radio (the
BME driver and cell 25-55 ns, the SNSPD's amplifiers and cable 10-20 ns) is the larger part (SYSTEM.md 1).

**Timing.**  GNSS is not good enough and there is no fibre between the sites, so **the links are the clock**: V0's
carrier gives every site its frequency (the receiving Costas loop's VCXO locks to it), and two-way exchanges give the
offset (SYSTEM.md 4).  The bench decides symbols on a 1.25 ns grid (+-0.36 ns); a carry-chain TDC makes it +-0.07 ns.
Rev B brings the locked reference out as a clean 10 MHz and a PPS for the site's other instruments.

**The channel plan.**  Three radios at P and at V0, each on its own frequency within 5.15-5.85 GHz (or 4.9-5.9 under a
Part 5 licence), the three transmitters a metre from the three receivers, plus the campus's WiFi.  Rev A has no
channel selectivity after the LNA (the loop is narrow, but the LNA and the demodulator see everything): a transmitter
at +20 dBm a metre away would saturate the neighbouring receiver.  This is the one new hardware requirement (3.3).

**Operations.**  Boxes on roofs and parking structures, weather, nobody who knows a PLL: lock and level on LEDs, the
page, the survey of every channel before a run, the frequencies and the constellation chosen from a menu, the
learning step, every calibration kept and restored (all of that exists in software today; rev B gives it the
instrumentation: section 3.4).

**Power to the antennas.**  FCC 15.407 for U-NII-3 (5.725-5.850 GHz), fixed point-to-point: 1 W conducted, antennas up
to 23 dBi with no reduction, 1 dB less conducted power per dB of gain above that.  A 24 dBi grid and +20-27 dBm are
well inside.  The link budget with +20 dBm and two 24 dBi dishes (1 dB of cable each end):

| distance | free-space loss at 5.8 GHz | at RX ANT | the bench's -40 dBm is |
|---|---|---|---|
| 100 m | 87.7 dB | -22 dBm | 18 dB weaker: the DSA (31.75 dB) absorbs it |
| 300 m | 97.3 dB | -31 dBm | |
| 1 km | 107.7 dB | **-42 dBm** | the bench's level: everything measured holds |
| 3 km | 117.3 dB | -51 dBm | 10 dB below; +27 dBm or 28 dBi dishes bring it back |

Rev A's own +3.8 dBm at 5.8 GHz (REVB 6) would be -58 dBm at 1 km: **rev B needs a PA** (3.1).

## 2. What the bench taught that shapes rev B

Four things, in order of weight (the rest is in REVB.md's 43 rows):

1. **The architecture is right.**  A hardware Costas loop with a comparator receiver locks over the air, recovers from
   every loss by itself (92 of 92 in the last soak), carries BPSK at 50 Mbaud and QPSK at 2.5 Msym/s with 1e-10 and
   1e-8 lost, decides 1-of-N symbols in about 60 ns, and the host sees all of it through five comparators and a slow
   ADC.  Rev B does not change the radio chips (HOSTS.md 5).
2. **The level is everything once locked**, and the receiver's windows are absolute voltages: a 4 dB stronger carrier
   makes QPSK decide wrong (FINDINGS 5).  Rev B gives the level to the FPGA fast (a dual ADC on the arms, a detector
   on the RF) and lets the FPGA hold it (the DSA, and a baseband gain step).
3. **The transmitter saturates** (the corners at 40 degrees, the flip at 190: REVB 35) and **the receiver has a 10 %
   second-order error in the corners** (REVB 38).  For 1 of 4 the calibration absorbs both; for 1 of 8 (22.5 degrees of
   margin) they must go: a linear modulator drive, and the arms' intermodulation found.
4. **The host is the slow part of the instrumentation**: a 860 S/s ADC on a shared I2C, the 200 ohm series resistors,
   a PYNQ that hangs.  Rev B's FPGA owns every sensor (REVB U3), the comparators are LVDS, and the carrier is one the
   box can power-cycle.

## 3. The radio pod: what rev B is, whatever the carrier

**Kept**: MAX2871 x2 (TX and RX synthesizers, the TCXO and the VCXO), ADL5375 modulator, ADL5380 demodulator, the
LNA, the PE43711 DSA, the ADL5611 gain blocks, the THS4541 arms at ~94 MHz, the analog Costas loop (the sign-mux, the
integrator, VC to the VCXO), the 2-bit ladders for the fast symbols (a DAC is slower to a step: HOSTS.md 4), the
HMC536 T/R switch, REF IN / REF OUT, the detectors.

### 3.1 Changed in the RF and analog (from REVB.md, in order of consequence)

| # | change | why | cost / risk |
|---|---|---|---|
| 1 | **A PA stage after the modulator**: a 5 GHz WiFi FEM or PA (Qorvo QPF4519: PA + SP2T + LNA, +23 dBm; Skyworks SKY85402 PA +25 dBm; both on LCSC in small stock) or a connectorized PA module outside the box | the link budget (section 1); rev A makes +3.8 dBm at 5.8 GHz | the FEM also brings a switch and an LNA in one small part, but ties the band to 5.15-5.85 GHz; a Part 5 licence at 4.9-5.9 would want a discrete PA.  +1 dB of noise figure if its switch sits before the LNA.  Risk: moderate (a new RF part, its matching) |
| 2 | **Channel selectivity** (3.3) | three radios a metre apart | see 3.3 |
| 3 | **Fix the LNA input** (C102 lifted, the match redone for 5.15-5.9 GHz: REVB 8), the TX chain's roll-off (REVB 6), LO TX MON's 116 mm trace (REVB 4), the DC blocks' pad capacitance and the bias chokes (REVB 11-13), the FDA mid-points (REVB 17), the decoupling in the fan band (R2) | the receive chain's gain at 5.8 GHz is 7 dB instead of 37; the TX is 6 dB short | the VNA tests of 2026-11-03 (tests A and F, then C102 lifted) decide how much of this is layout and how much the parts: low risk, it is the same chips laid out as the models say |
| 4 | **The transmitter linear**: the ladders' drive attenuated into the ADL5375's linear range (its baseband input wants ~0.5-1 V p-p differential about 500 mV; the 3.3 V ladders through 300/348 ohm overdrive it: REVB 1, 35), VR_I/VR_Q from a DAC with the right range | the corners at 45 degrees and 1.41 of the idle; 1 of 8 possible | low risk: resistors and a DAC range; the levels at the comparators then change and the calibration follows |
| 5 | **Four more window comparators on the diagonals** ((I+Q) and (I-Q), a resistive sum/difference into two more THS4541 stages or the comparators' own differential inputs), all nine fast comparators **TLV3604 (LVDS, 0.8 ns)**, 100 ohm terminations at the connector | 1 of 8; HOSTS.md 3 (LVDS saves 1.7 ns + the RC) | 9 pairs = 18 pins (3.5 on the pin budget).  Low risk in parts; the diagonal windows' margins depend on the second-order error (REVB 38) being found |
| 6 | **The windows' hysteresis from software** (REVB Q6) and an RC at each threshold pin (R5) | the latency tail on one lock point looks like a comparator chattering near a window (IMPROVEMENTS 18) | nothing |
| 7 | **An integrator reset switch** across C130 and VC_OFF covering the VCXO's whole range (REVB U4) | the recovery's 1 s of I2C trims becomes gateware alone: a loss recovered in well under a second | an analog switch |
| 8 | **A dual ADC on I and Q into the FPGA** (12 bits, 20-65 MS/s: AD9248 / LTC2292 / AD9238 class, $5-15, 26 pins, or an SPI/serial-LVDS one at 10-20 MS/s on fewer pins) and the RF detectors (log and peak) into it | the live constellation, the eye, an RSSI that works unlocked, a digital AGC, a digital confirm (REVB U2, U3) | pins (3.5); an ADC's pipeline (~100 ns) keeps it out of the fast decision |
| 9 | **The FPGA owns the slow sensors**: the ADS1115 and the DACs on an I2C/SPI bus the FPGA drives round-robin into registers; the page reads registers (REVB U3) | no bus contention; the dashboard never waits for a test | gateware |
| 10 | **A locked reference out**: the VCXO's 25 MHz (or a 10 MHz derived from it) and a PPS on SMAs, and the carrier's clock to the FPGA's clock pins (SYZYGY P2C_CLK) | the verifiers' synchronization (SYSTEM.md 4): V1's and V2's instruments run on V0's frequency | a clock buffer and a divider |
| 11 | **GPS PPS and 10 MHz in** (the coarse alignment; the Pockels timing between rounds) | SYSTEM.md 4 | two SMAs, a mux into the PLL reference (REVB Q3) |
| 12 | **The field I/O from the SyzygyRadioBoard**: four BME outputs (SN74ACT04 x6 in parallel through 10 ohm: 3.5-4.0 V into 50 ohm, 4-7 ns edges, an Ioff hold so On and Off never rise together), two to four detector inputs as comparators (50 ohm or Hi-Z, a DAC threshold, polarity by jumper or switch; LVTTL from ID Qube/ID120, NIM, or an SNSPD amplifier's few hundred mV), pull-downs on every jack | SYSTEM.md 5; Jason: rev B is the combination of both boards | that board's three reviews already settled the circuits; copy them |
| 13 | **Everything set from software** (REVB Q1-Q11: the loop sign, the LNA enable, the reference mux, the RF loopback switches, a monitor mux, the DVM taps, current monitors) and **LEDs** (lock, searching, no carrier, interference; a signal-strength bar in hardware: REVB U1) | unattended operation; "no laptop balanced on a roof" | an I2C expander and switches: a few dollars |
| 14 | **Power**: PoE+ or 9-24 V in, the pod's own regulators sized (REVB 2, 3: the 5 V path's 192 mohm, U104's hot spot), temperature sensors read by the FPGA | a roof box: one cable | a few parts |

### 3.2 The constellation: 1 of 4 now, 1 of 8 ready

The receiver decides a symbol from which windows its comparators cross (FINDINGS 3).  Four points (the QPSK corners)
need windows on I and Q: five comparators (CMP_I, QP, QN, IP, IN).  Eight points at 45 degrees need the two
diagonals as well: four more windows on (I+Q)/sqrt 2 and (I-Q)/sqrt 2, nine comparators.  The decision logic is the
same table lookup (32 entries today, 512 with nine inputs), the latency the same class (the diagonal arms are copies
of the I and Q arms).  What 1 of 8 costs:

* **The transmitter must be linear** (3.1 item 4): with the corners at 40 degrees today, the eight points would be
  unequally spaced and the margins 10-25 degrees instead of 22.5.  Eight points also need five levels per axis (0,
  +-0.707, +-1) from the ladders: a 3-bit ladder per axis (one more pin each), or a small fast DAC for the slow symbols
  and the ladder for the fast ones.
* **The second-order error** (REVB 38, about 10 % in the corners) halves the diagonal margins unless found and fixed
  (it is in the demodulator or the arms; the VNA and a B210 test on rev A can locate it before rev B's layout).
* **Pins**: four more LVDS pairs (3.5).
* **Money**: four comparators and two FDAs, under $15.

So: lay out the nine windows and the linear drive, run the experiment on four, and have eight when the margins are
measured.  The slow path (the 7.5 MHz veto) stays on I and Q.

### 3.3 Selectivity: three ways, from cheapest to best

| option | what | selectivity | latency cost | money and risk |
|---|---|---|---|---|
| S1: **spatial, polarization and spacing** | the dishes point in different directions (20-30 dB), TX and RX dishes at a site cross-polarized (20-30 dB), the links 100-300 MHz apart, the DSA for the rest | 40-60 dB between a site's own radios; none against WiFi in the band | none | nothing on the board; it is the deployment's geometry.  Rev A's bench already runs three antennas within 40 cm |
| S2: **a fixed RF band-pass per radio** (a ceramic or cavity filter at RX ANT: 5.725-5.850 GHz, or 5.15-5.35, 1-2 dB, 50-100 MHz wide; Johanson/Taoglas/Mini-Circuits parts on LCSC and Digikey) | the radio hears its sub-band only; U-NII-1 radios deaf to U-NII-3 and the reverse | a filter's group delay: 5-15 ns for 100 MHz wide | $3-30; a part to choose and a footprint; the frequency menu shrinks to the filter's sub-band per radio (two board variants, or a switched pair of filters) |
| S3: **a superheterodyne receiver**: a second LO (one more MAX2871 or the RX synthesizer's second output) mixing the RF to an IF of about 1 GHz, a 100 MHz-wide IF filter (LC or SAW), the demodulator and the Costas loop at the IF | sharp, and tunable: the LO moves, the filter stays; any channel from a menu | 10-20 ns in the filter and the extra mixer | $20-40 and a redesigned chain; the loop's frequency plan changes; highest risk on a first run |

**For rev B: S1 always, S2 on the prover's three links (two fixed sub-bands, which the three links share with the
geometry), S3 only if the survey of UIUC's roofs says the band is crowded.**  S2's filter also protects the LNA from
the site's own transmitters.  The sync links (V0 -> V1, V2) can be as narrow as a 20-40 MHz filter lets them, since
their latency does not count.

### 3.4 Instrumentation and operations (the software exists; rev B feeds it)

Everything the page, linkd, the self-test and the learning step do today carries over: the ADC and the detectors in
the FPGA (3.1 items 8-9) give them a live constellation, an unlocked RSSI, a survey of every channel (the RX
synthesizer stepped across the band with the detector read: `survey()` in minutes, no B210), the level held by an
AGC, the eye without a scope.  The menu before a run: frequency per link from the survey, constellation (1 of 4 or 8,
BPSK or QPSK data), the learning step's tables and timings.  A fleet page shows the four sites.

### 3.5 The pin budget on one SYZYGY Standard port (28 signals)

| pins | signals |
|---|---|
| 18 | nine LVDS pairs: CMP_I, QP, QN, IP, IN, D1P, D1N, D2P, D2N |
| 6 | TX_I1, TX_I0, TX_Q1, TX_Q0 (the ladders; a third bit each for 1 of 8 would be 2 more), TRIG_IN, TX_EN |
| 3 | SPI (SCLK, SDATA) and one LE, the others through the expander |
| 1 | LOOP_HOLD |
| **28** | |

Everything slow (the three slow comparators, the mux controls, LOOP_SEL, the LEs, the ADC's serial data, the DACs) goes
through the port's I2C (the DNA bus, with the pod's own devices on it, if the specification allows: check first, as
HOSTS.md 3 says) or through the pod's DNA microcontroller.  **The ADC's parallel bus does not fit** on a Standard port
beside nine LVDS pairs: use a serial-LVDS ADC (2 pairs), or put the diagonal comparators' decision through a small
on-pod encoder, or accept a second port for the instrumentation, or (the K26 carrier's advantage) give each socket
more than 28.  The field I/O (four BME outputs, four detector inputs) needs 8 more pins: on the Brain-1 that is a
second port's worth, which is why SYSTEM.md 5 suggests two pod variants (one with the field I/O per node) or the
expander.  **This budget is the Brain-1 option's real weakness** (5.1).

## 4. The FPGA's transceivers: what they could do, and what they should do

### 4.1 What a transceiver is

A GT (GTP on Zynq-7000S, GTH on UltraScale+, GTY on the larger parts) is a serializer and a deserializer with a clock
recovery (CDR) on the receive side: it sends and receives NRZ bits at 0.5-16 Gb/s (GTP 3.75 Gb/s at the Brain-1's -1
grade; GTH 16.3), AC-coupled, with a PCS that can do 8b/10b, 64b/66b or nothing (raw).  Its latency with the buffers
bypassed is small: AMD measured a TX + RX round trip of about 18.4 ns (20-bit datapath) to 27.8 ns (32-bit) on an
UltraScale+ GTY, buffer bypass, fixed overhead subtracted; the Ethernet gearboxes add about 30 ns each way when used.
An SFP+ cage is a GT lane with a slow 2-wire I2C for the module's diagnostics, and TX_DISABLE / RX_LOS pins: no fast
control channel; anything fast goes in-band.

### 4.2 Could it be the modem?

**Transmit**: yes, by patterns.  A GT running at 4 x f_IF sends `1100 1100 ...` as a square wave at f_IF; inverting
the pattern is a 180 degree step (BPSK), shifting it one bit is 90 degrees (QPSK); 8 bits a cycle give 45 degrees
(8-PSK): at a 1.45 GHz IF that is 5.8 Gb/s for 4 points and 11.6 Gb/s for 8 (a GTH, not a GTP).  The square wave's
harmonics are filtered; a mixer and the PA take it to 5.8 GHz.  Amplitude is binary, so no QAM and no OOK depth:
only phases.  "Idle to 1 of N" is then N patterns, any of which the TX can switch to on a clock.

**Receive**: the unproven half.  After the LNA, a mixer to the same IF and a limiting amplifier, the GT's RX sees a
square wave at f_IF with phase steps: to its CDR that is a perfect clock with data that suddenly shifts.  The CDR's
loop (a bang-bang phase detector with a bandwidth around a few MHz, not adjustable from the fabric) *is* a
hard-limited PLL, like the Costas loop; a phase step shows up as a change in the deserialized word that persists until
the CDR has re-tracked (hundreds of ns to microseconds), which the fabric can read in one clock.  So "1 of N" by
phase is readable in principle, with the GT's ~10-15 ns of RX latency plus the limiter.  What nobody has shown (no
precedent turned up; the published uses of GTs as RF are transmit-only, pulse-density modulators driving PAs):

* whether a given CDR stays locked through 90 and 180 degree steps at the symbol rates we want, or declares a loss and
  re-acquires;
* how it behaves against the 5 ppm offset between the two ends' carriers (within a CDR's capture) and against
  interference (a CW beat on a limited square wave is pulse-width jitter the CDR will follow);
* the windows: the comparator receiver's margins and false-event rate are set by DAC thresholds the self-test
  calibrates; a CDR has one implicit threshold (the limiter's) and nothing to calibrate.

**And the RF board stays**: synthesizers, mixers, LNA, DSA, PA, filters, the detectors, the field I/O.  What the GT
would remove is the Costas loop, the VCXO, the arms, the comparators, the ladders and the modulator's I/Q drive: about
a third of rev A's parts, in exchange for a CDR whose behaviour we would have to measure.

### 4.3 What they should do: the fibre to the roof

At V0 the Pockels cell, the detectors and the source are in the optics lab; the dishes are on the roof with coax
between.  At 5.8 GHz LMR-400 loses about 0.35 dB/m: 30 m is 10 dB each way, more than the whole link budget's margin
at 1 km.  The alternative: **the radio and its FPGA on the roof behind the dishes, and only digital signals between the
lab and the roof** - the basis share (a few bits, scheduled), the herald, the detector pulses.  Two ways, which can
share one cable tray:

* **as bits over fibre, SFP+ to SFP+** (a GT each end: ~20-30 ns of transceiver latency plus 4.9 ns/m, galvanically
  isolated, lightning-safe, 10 Gb/s of telemetry on the same fibre).  V0's latency does not count (SYSTEM.md 1), so
  this is right for V0;
* **as logic pulses over coax** (a 1 V edge down 30 m of RG-223 arrives in 150 ns with no electronics: right at the
  prover if its optics are indoors, where every ns counts; or put the prover's whole chain on the roof).

So the SFP cage belongs on the **carrier** (the K26 carrier of 5.4 has one; the Brain-1's TXR4 port can take a
SYZYGY SFP pod, at 3.75 Gb/s), not on the radio.

### 4.4 A cheap experiment, if the modem idea is worth settling

A Kria KR260 ($372, two SFP+ cages, PYNQ) and an SFP+-to-SMA breakout: the GT sends the 1.45 GHz pattern out of one
cage into a limiter and back into the other; the fabric steps the phase and measures how the deserialized words move
and how long the CDR takes to re-track; then a mixer pair takes it to 5.8 GHz over the air against rev A.  Two weeks
of someone's time and $500 answer 4.2's questions.  Not on rev B's path.

## 5. The carrier: the options, with prices and stock (2026-11-02)

| option | carrier | FPGA | ports for radios | host | price each | in stock | per 3-radio site (carrier + radios) |
|---|---|---|---|---|---|---|---|
| **A** | Opal Kelly Brain-1 (SZG-BRAIN1) | Zynq XC7Z012S-1 (7-series fabric, 1 A9, 1 GiB DDR3, GbE) | 3 SYZYGY Standard + 1 TXR4 (4 GTP) | Linux on the Zynq | $449.95 | 31 (Digikey marketplace, from Opal Kelly) | $450 + 3 pods |
| **B** | Opal Kelly XEM8320-AU25P | Artix UltraScale+ AU25P-2 (1 GiB DDR4) | 4 Standard + 2 TXR4 | USB 3 to a host PC (FrontPanel; no processor on board) | $1,499.95 | Opal Kelly, Digikey | $1,500 + a small Linux host + 3 pods |
| **C1** | ZCU104 (EK-U1-ZCU104-G) | ZU7EV | 1 FMC LPC (34 LVDS pairs, 1 GT) | PetaLinux / PYNQ | $1,791 (Avnet, 8); £1,457 UK | yes, thin | $1,800 + one FMC board with 3 radios |
| **C2** | ZCU102 | ZU9EG | 2 FMC HPC, 4 SFP+ | PetaLinux / PYNQ | $3,570 (Digikey, 205) | yes | $3,600 + the FMC board |
| **C3** | ZCU106 | ZU7EV | 1 HPC + 1 LPC, SFP+ | PetaLinux / PYNQ | $3,451 (Avnet, 6) | thin | |
| **C4** | Digilent Genesys ZU-5EV | ZU5EV | FMC LPC, SFP+, (1 SYZYGY on the 3EG variant) | PetaLinux / PYNQ | $1,995 | out of stock at several distributors | |
| **C5** | Alinx AXU5EV-P / AXU9EG | ZU5EV / ZU9EG | FMC HPC | PetaLinux | $1,660 / £1,832 | Alinx direct | Chinese documentation; no PYNQ |
| **D** | **a custom carrier for the Kria K26 SOM** | XCK26 (ZU5EV-class; GTH lanes on its second connector, four to check in DS987; DDR4 on the SOM) | **our choice: 3 SYZYGY Standard sockets + 1 SFP+ + the field I/O** | Ubuntu + PYNQ for Kria | SOM $351 commercial (205 in stock) / $434-550 industrial (2,485 in stock, UK); the two Samtec ADM6-60 connectors about $15-18 each (3,789 in stock) | yes | SOM + a modest board (no RF, no DDR: est. $300-500 each in a run of 6) + 3 pods |
| **E** | Kria KR260 / KV260 as sold | XCK26 | RPi header (26 I/O), 4 Pmods, 2 SFP+ (KR260) | Ubuntu + PYNQ | $372 / $245 (240-456 in stock) | yes | one radio through an adapter: 26 + 32 single-ended pins, no LVDS pairs guaranteed: **not enough for a 3-radio node**, enough for 4.4's experiment and a one-radio test node |
| **F** | RFSoC 4x2 | ZU48DR, 4 ADC 5 GS/s, 2 DAC 9.85 GS/s | direct RF (plus LNA, filter, PA) | PYNQ | $2,149-2,499 academic | Real Digital, AUP | no pods; **its converters' 90-117 ns rule it out as the prover** (SYSTEM.md 5); the lab's reference instrument |
| **G** | an FPGA on the radio board (an Artix-7 / ECP5 / small Zynq) | | none: the radio is the carrier | a UART or Ethernet | the chips | | one board per link, no connector at all (HOSTS.md 4); the most work per board |

### 5.1 A: the Brain-1 with two or three pods

* **For it**: cheap, small (fits a box with three pods), Linux and Ethernet on board, SYZYGY's SmartVIO and DNA, 7.0 ns
  events with LVDS comparators (HOSTS.md 3), exactly SYSTEM.md 5's plan, and nothing new to learn about the carrier.
* **Against it**: a 2017-class fabric at the -1 grade (fine for 100-200 MHz gateware; an 800 Ms/s ISERDES and a TDC
  fit); **28 pins a port** (3.5: the nine LVDS pairs plus the field I/O do not fit on one port, so the field I/O takes
  the node's third port or an expander); 4 GTP at 3.75 Gb/s (an SFP for the fibre, not 10G); one A9 core (the page
  and linkd are light; fine); no PYNQ (the driver's MMIO and the overlay loading move to PetaLinux's `/dev/mem` and
  `fpgautil`: a few days); the per-port power is not published (a pod draws 1.4 A at 5 V: check with Opal Kelly);
  Opal Kelly is one small vendor, 31 boards in stock today.
* **First-run likelihood**: the pod high (rev A came up first time, the pod is smaller and better understood); the
  deployment medium-high (the carrier is bought; the risk is the software port and the pin budget's compromises).

### 5.2 B: the XEM8320

An UltraScale+ fabric and six SYZYGY ports for $1,500, but **no processor**: the host is a PC over USB 3, so a roof box
needs a small Linux computer and Opal Kelly's FrontPanel on it (supported on Linux; check ARM).  For the lab, or as the
central node, it is the best SYZYGY carrier sold; for V1 and V2 in a box it is an odd shape.  Five of them are $7,500.

### 5.3 C: an FMC board on an UltraScale+ evaluation board

* **For it**: 160 I/O and 10 GT lanes on an HPC (34 LVDS pairs on an LPC), VADJ, the fastest fabrics, PYNQ.
* **Against it**: **one large board per site** (three radios, nine LVDS pairs each, the field I/O, 8-10 layers, 400
  pins at 1.27 mm: a first-run risk of its own), **no spare but a whole board**, the evaluation board ($1,800-3,600, 20
  x 20 cm, 20-40 W) in a weatherproof box with a board hanging off its FMC: Jason's fragility concern is right.  The
  LPC boards (ZCU104, Genesys) have 34 pairs: three radios' 27 LVDS pairs fit, the rest does not.  Nothing is easier to
  source: the FMC connector is a Samtec part like the QTE.
* **Where it makes sense**: nowhere in the field.  As a lab test bed for three radios at once, a ZCU102 with an
  FMC-to-3-SYZYGY adapter (a passive board: the FMC connector and three QSE sockets) is cheaper and keeps the pods.

### 5.4 D: a custom Kria K26 carrier with SYZYGY sockets (the recommended second step)

* **What it is**: a board of about 120 x 160 mm carrying the K26 SOM (two 240-pin Samtec ADM6 sockets, 0.635 mm
  pitch), its power sequencing (UG1091, the carrier design guide: a few regulators and a reset supervisor; the DDR,
  flash and eMMC are on the SOM), Gigabit Ethernet (a PHY), USB, an SFP+ cage on one GTH, three SYZYGY Standard sockets
  with SmartVIO (the SOM's PL I/O, about a hundred on the two connectors per DS987, cover three ports' 84 with room for the field I/O), a PoE+ or 12-24 V input, the
  LEDs, the PPS and 10 MHz, a temperature sensor.  No RF, no high-speed memory: the hard parts of a carrier are on the
  SOM already.  PYNQ runs on Kria (the KV260 and KR260 images), so the board server moves as it is.
* **For it**: an UltraScale+ fabric (2-3 ns faster paths, an 800 Ms/s ISERDES with margin, GTH at 10 Gb/s for the
  fibre), 4 GB DDR4 and a quad A53 for the page and the fleet, the industrial SOM (-40 to +100 C junction) for a roof,
  **one rugged board per site with the radios as swappable pods**, $351-550 for the computer, in stock in thousands.
* **Against it**: a board to design and to get right once (the SOM's power-up sequence, the PHY, the SmartVIO):
  medium risk on a first run, lower than an FMC beast's because there is no RF on it and every interface is one the
  K26's own carriers show (KV260's schematics are public).  The Samtec ADM6 sockets go through JLCPCB's Global
  Sourcing (as the QTE/QSE and the FMC would).
* **First-run likelihood**: medium-high for the carrier (no RF, a known SOM), high for the pods; deployment
  medium-high.  **And it decouples**: the pods are designed now for the Brain-1 and run on this carrier later.

### 5.5 E, F, G

* **E, KR260 as sold**: 26 single-ended I/O on the RPi header and four Pmods: one radio through an adapter with no LVDS,
  i.e. the PYNQ's situation with a faster fabric; fine for the transceiver experiment (4.4) and as a one-radio test
  node, not for a site.
* **F, RFSoC 4x2**: the right instrument for the lab (samples every radio's RF, times edges to ps, calibrates the
  two-way time transfer: SYSTEM.md 5); its converters' latency rules it out at the prover, and it carries no pods.
* **G, the FPGA on the radio**: the lowest latency (no connector) and the most board (an FPGA, its rails, its flash,
  Ethernet) per radio, times ten, with the DDR-less small parts (an Artix-7 15T/35T, an ECP5-25) lacking a processor
  for the page: a later board, if the pods' connector ever shows as the limit.

### 5.6 The comparison

| | A: Brain-1 + pods | B: XEM8320 + pods | C: FMC beast on ZCU104 | D: K26 carrier + pods | F: RFSoC 4x2 |
|---|---|---|---|---|---|
| event latency, RF in to the FPGA's register (HOSTS.md model) | 7.0 ns (LVDS, 800 Ms/s) | 6.4-7.0 | 6.4-7.0 | 6.4-7.0 (TDC) | 90-117 ns (the converters) |
| FPGA turnaround, pin to pin | 5-13 ns (7-series) | 3-8 | 3-8 | 3-8 | n/a |
| 4 sites + spares (5 carriers, 12 radios), est. | **$5,300-7,000** | $11,000-13,000 | $14,000-16,000 (5 beasts, no radio spares) | $6,500-9,800 | $10,000 + front ends |
| board complexity | one small pod | one small pod | one large RF board with everything | one medium carrier (no RF) + the pod | front-end boards only |
| JLCPCB first-run likelihood | pod: high | pod: high | medium | carrier: medium-high; pod: high | high (simple boards) |
| deployment first-run likelihood | medium-high (the software port; the pin budget) | medium (a host PC in the box) | medium (fragile; a bug stops a whole site) | medium-high (a new carrier, but PYNQ and the pods as before) | low for the prover (latency); fine for a lab verifier |
| ruggedness in a roof box | good: small, few connectors | fair | poor: an eval board plus a hanging board | **good: one board, pods on standoffs** | poor |
| spares | any pod, any carrier | any pod | a whole board | any pod, any SOM, a carrier | a whole kit |
| software | PetaLinux: port the server (days) | FrontPanel on a host | PYNQ | **PYNQ as today** | PYNQ |
| the pin budget per radio | 28 (tight: 3.5) | 28 | 160+ | our choice (SYZYGY's 28, or wider sockets) | n/a |
| selectivity, 1 of 8, the PA, the field I/O | all on the pod | same | same | same | the FEM only |

**My ranking: D's pods first (designed to run on A today), A as the first carrier, D's carrier as the second, F for
the lab, C not at all, B only as a lab carrier.**  The one thing to settle before the pod's layout is the pin budget
(3.5): whether the pod's slow devices may hang on the SYZYGY DNA I2C bus, and whether the instrumentation ADC rides on
two LVDS pairs.  If the 28 pins truly cannot hold nine LVDS pairs plus the ladders and the field I/O, the fallback is
a pod that uses a **Standard port plus the adjacent TXR4 port's spare pins**, or D's carrier with a wider socket
(SYZYGY's TXR4 has 18 more signals), at the cost of the Brain-1's third radio.

## 6. What to do first (in order), and what each settles

1. **2026-11-03, rev A on the VNA and C102 lifted** (MONDAY.md 2-3): the receive chain at 5.8 GHz, and how much of
   REVB 4-13 is layout.  Then the dishes across the long lab: the first real-distance numbers for section 1's budget.
2. **Two rev A boards over the air** (MONDAY.md 5): the turnaround across boards, the two-way time transfer (REF OUT to
   TRIG IN: SYSTEM.md 4), the frequency plan with two carriers.  This is the experiment's link, end to end, on rev A.
3. **The pin-budget question to Opal Kelly / the SYZYGY specification** (devices on the DNA bus; per-port power on the
   Brain-1), one email.
4. **Find REVB 38's second-order error** on rev A (the B210 against the demodulator's output directly, bypassing the
   arms: an afternoon): it decides whether 1 of 8 is a layout change or a part change.
5. **The pod's schematic**: rev A's with 3.1's fourteen changes, the SyzygyRadioBoard's field I/O sheets, on the
   SYZYGY template (`../SyzygyRadioDrivers/pcb-templates/`), the DNA microcontroller as that board has it.  A first
   layout in the pod's form factor at 4-6 layers.  JLCPCB assembly with Global Sourcing for the QTE, the TLV3604s and
   the FEM if LCSC's stock is thin (9-20 business days, plan for it).
6. **Order a Brain-1 now** ($450, in stock): the software port (PetaLinux, `/dev/mem`, `fpgautil`) and the pod's
   gateware target can start on it with rev A through an adapter (SYZYGY to rev A's 2x20 header: single-ended, so the
   PYNQ's latency, but every register and every test runs).
7. **The K26 carrier** after the pods are back: a KV260 ($245) meanwhile runs PYNQ and one pod through an adapter for
   the fabric's timing.

## 7. Decisions for Jason

1. Pods on SYZYGY (10 + spares) with the carrier bought: yes or no.  (Everything below assumes yes.)
2. The first carrier: the Brain-1 ($450 each, order 5), or go straight to the K26 carrier (one more board design before
   anything is deployed, 2-3 months later).
3. 1 of 8 in the receiver's hardware now (nine comparators, the linear TX): yes (my recommendation) or 1 of 4 only.
4. Selectivity: S2's fixed sub-band filters on the prover links (two pod variants, or a switched pair), or S1 alone
   until the UIUC survey.
5. The PA: a WiFi FEM on the pod (+23 dBm, the band fixed at 5.15-5.85) or a connectorized PA outside (any band under
   a Part 5 licence).
6. The field I/O on every pod (simplest; pins) or on one pod variant per node.
7. The V0 lab-to-roof link: fibre + SFP (the radio on the roof) or RF over coax.
8. The transceiver-modem experiment (4.4): fund two weeks and a KR260, or shelve it.

## Sources (looked up 2026-11-02)

Brain-1: [Opal Kelly, $449.95, XC7Z012S-1, 3 Standard + 1 transceiver port, Linux](https://opalkelly.com/products/brain-1/),
[Digikey marketplace listing, 31 in stock](https://www.digikey.co.nz/en/products/detail/opal-kelly/SZG-BRAIN1/26735591).
XEM8320: [Opal Kelly, $1,499.95, AU25P, 4 Standard + 2 TXR4, USB 3 FrontPanel](https://opalkelly.com/products/xem8320/).
SYZYGY connectors: [the specification's parts: QSE-020 carrier / QTE-020 peripheral; QSH/QTH-020-DP for TXR4](https://syzygyfpga.io/specification/),
[QTE-020-02-L-D-A about $4-8, Samtec in production](https://octopart.com/part/samtec/QTE-020-02-L-D-A).
FMC: [ASP-134486-01 about $23-31 at Digikey, 2,140 in stock (aggregator snapshots)](https://origin-www.findchips.com/search/asp-134486-01).
JLCPCB Global Sourcing: [review 1-3 business days, purchasing 9-20, assembly only, fees for connectors](https://jlcpcb.com/help/article/How-to-use-JLCPCB-Global-Sourcing-Parts-Service).
ZCU102: [Digikey $3,570, 205 in stock](https://www.digikey.com/en/product-highlight/x/xilinx/zynq-ultrascale-mpsoc-zcu102-evaluation-kit);
ZCU104: [Avnet $1,791, 8](https://www.avnet.com/americas/manufacturers/m/c/amd/kits-and-tools), [Digikey UK £1,457](https://www.digikey.co.uk/en/products/detail/amd/EK-U1-ZCU104-G/9380242);
ZCU106: [Avnet $3,451](https://www.avnet.com/americas/manufacturers/m/c/amd/kits-and-tools).
Kria: [KR260 $372, 240-262 in stock](https://www.digikey.de/en/product-highlight/a/amd-xilinx/kria-kr260-robotics-starter-kit),
[K26 SOM commercial $351 / industrial £434](https://www.digikey.co.uk/en/products/detail/amd/SM-K26-XCL2GI/13985243),
[KV260 $223-284](https://www.digikey.nl/nl/product-highlight/x/xilinx/kv260-vision-ai-starter-kit),
[the SOM's connectors: ADM6-60-01.5-L-4-2-A, GTH on SOM240_2 (UG1091)](https://docs.amd.com/r/en-US/ug1091-carrier-card-design/SOM-Connector-Overview),
[ADM6-60 about $12-18, 3,789 in stock](https://www.digikey.co.nz/en/products/detail/samtec-inc/ADM6-60-01-5-L-4-2-A-TR/11688975),
[KR260's ports: 4 Pmod, a 40-pin header with 26 I/O, SFP+ (UG1092, the product brief)](https://www.avnet.com/opasdata/d120001/medias/docus/205/kr260-product-brief.pdf).
RFSoC 4x2: [AMD University Program, $2,499](https://www.amd.com/en/corporate/university-program/aup-boards/rfsoc4x2.html),
[the earlier academic price $2,149](https://discuss.pynq.io/t/rfsoc-4x2-board-and-kit/4392).
Genesys ZU: [$1,995, FMC, SFP+ on the 5EV; SYZYGY on the 3EG](https://reference.digilentinc.com/programmable-logic/genesys-zu/reference-manual).
Alinx: [AXU5EV-P $1,660, AXU9EG £1,832](https://boards.fpgadeveloper.com/boards/AXU9EG).
Trenz: [TE0820 £318-395 at Digikey UK, thin stock; its transceivers are the PS GTR, the PL GTH not brought out](https://wiki.trenz-electronic.de/display/PD/TE0820+TRM).
Transceiver latency: [AMD, low-latency transceiver designs: GTY buffer bypass round trip about 18.4 ns (20-bit) to 27.8 ns (32-bit)](https://www.amd.com/en/blogs/2019/low-latency-transceiver-designs-for-fintech.html),
[a 10G Ethernet core's gearboxes about 30 ns each way](https://ttchisholm.github.io/ethernet/2023/05/07/designing-10g-eth-5.html).
GTs as RF: [a SerDes as a pulse-density modulator driving a PA (Maynooth, transmit only)](https://mural.maynoothuniversity.ie/id/eprint/6315/1/RF-FPGA.pdf).
Zynq 7012S: [four GTP (UG585)](https://docs.amd.com/r/en-US/ug585-zynq-7000-SoC-TRM/GTP-Low-Power-Serial-Transceivers).
5 GHz PAs on LCSC: [Qorvo QPF4519 PA/SP2T/LNA, +23 dBm](https://www.lcsc.com/product-detail/C471156.html),
[Skyworks SKY85735-11 FEM](https://www.lcsc.com/product-detail/C2654426.html), [SKY85402-11 PA, +25 dBm](https://www.skyworksinc.com/en/Products/Amplifiers/SKY85402-11).
SFP+ cages at LCSC: [JLCPCB's optical-module connector library](https://jlcpcb.com/parts/2nd/Connectors/Optical_Module_Connector_2051).
FCC 15.407: [eCFR: fixed point-to-point, 23 dBi without reduction](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-15/subpart-E/section-15.407).
