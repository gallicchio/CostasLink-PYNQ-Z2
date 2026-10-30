# Board A's turnaround: where it goes, and what each knob would buy (2026-10-29, 23:50)

Jason: "Make a table of how much could be gained (in terms of reduced latency) by tweaking the FPGA clock, the 200 ohm
resistors, the comparators, the modulator, etc., along with how much each improvement would cost in terms of money and
complexity ... Could the Icepi Zero FPGA go faster because it has no 200 resistors, or would it go slower because of the
FPGA turnaround?"

The turnaround runs from one of the four non-idle states arriving at RX ANT to the reply leaving TX ANT. All figures are
single-board loopback: TX ANT, 10 cm of RG-316 and two 20 dB pads (about 0.7 ns), then RX ANT. Each is labelled with how
it is known:
- **measured:** board A tonight (BRINGUP_LOG 3.4h-i);
- **Vivado / nextpnr:** a timing report;
- **model:** `sim/latency_roadmap.py`, `sim/hosts.py` or `docs/TRAJECTORIES.md`;
- **datasheet;**
- **est:** an estimate.

## 1. What board A does now (measured)

| path | RX ANT to TX ANT | the FPGA's share |
|---|---|---|
| fast path (comparator pins, CFGLUT5, ladder pins), windows at 0.4 of the leg | 23.3-25.3 ns a hop (A3r ring 23.5) | 5.0-6.25 ns (capture) |
| the same, windows at 0.2 of the leg | **20.4-20.8 ns** (A3r ring, DSA 14-20) | |
| clocked reply, first-edge decision | about 51 ns | 31 ns |
| clocked reply, decision settled 4 samples | 59-60 ns | 40-42.5 ns |

`linktests.py turnsweep` (`data/board_A/link/turnsweep_5000_20261029_233838.json`, `plots/link_turn_sweep.png`) found
two things:
- **Window placement matters (A3r ring).** Each A3r hop enters a window. Moving the windows from 0.4 to 0.2 of the leg
  saves 3 ns at every level that held clean rings (DSA 14, 17 and 20). Above 0.4 the ring stalls.
- **Received level matters little.** In A1q2, half the hops enter a window and half leave one, so their sum barely depends
  on the window. At 0.7 of the leg A1q2 gives 24.0 ns at DSA 14 and 24.6 at DSA 26: 0.6 ns over 12 dB. That is the
  TLV3603's quoted overdrive dispersion (600 ps over 10-125 mV).

## 2. Where the fast path's 23.5 ns goes

| piece | ns | how known |
|---|---|---|
| FPGA, pad to pad: input buffer, CFGLUT5 and routing, output buffer | 5.0-6.25 | measured (the capture reads back the ladder pads) |
| PYNQ's 200 ohm into the ladder (~10 pF), the ladder's node, the ADL5375's 750 MHz baseband, to 50 % | ~2.4 | model |
| TX RF: modulator out, gain block, coupler, T/R switch, lines | ~0.5 | model |
| the lead and two pads | ~0.7 | est (0.5 ns of RG-316) |
| RX RF: LNA, DSA, two ADL5611s, coupler, balun | ~1.1 | model (`sim/budget.py` section 5) |
| ADL5380's 390 MHz and the arm's 94 MHz, to the window | ~1-3, depending on the window | model; the sweep moves this by 3 ns |
| TLV3603 window comparator | 2.5-3.1 | datasheet (2.5 typical at 50 mV of overdrive, 0.6 of dispersion); the sweep agrees |
| 33 ohm + PYNQ's 200 ohm into the Zynq pin (~10 pF), to 50 % | ~1.6 | model |
| baseband traces and the header, both ways (~15-20 cm) | ~1-1.5 | est |
| **sum of the above** | **~16-19** | |
| **not accounted for** | **~4-7** | the measured total less the sum |

The missing 4-7 ns is probably slow edges. The sweep's 3 ns for a 0.2-of-the-leg move needs an end-to-end edge about
1.5-2 times slower than the model's 6.6 ns from 10 to 90 %. Likely causes, each tested in section 5:
- more than 10 pF behind the PYNQ's 200 ohm on the ladder pins;
- an arm slower than 94 MHz;
- the TX_I1 and CMP_IP pins crossing the die (REVB 16).

## 3. The knobs

"Fast" and "clocked" are the savings on the fast path (23.5 ns) and on the clocked reply (51 ns). Money is for the two
nodes of a link.

| # | knob | fast saves | clocked saves | how known | money | work and risk |
|---|---|---|---|---|---|---|
| 1 | **Windows lower on the edge:** 0.2 of the leg instead of 0.4 (the bench's CFAR place is 0.1) | **3 ns** | ~3 ns | measured | $0 | None. Less margin against false events, so the threshold servo must hold the idle at one false event an hour. At 3 km the CFAR place moves out to 0.6 of the leg, and the gain goes with it |
| 2 | More received signal (overdrive) | ≤0.6 ns | ≤0.6 ns | measured, datasheet | $0 (the $29 PA at range) | None; not worth chasing at the bench |
| 3 | **FPGA fabric clock 100 to 200 MHz** for the reply lane (ISERDES 4:1, the rest of the core left at 100 MHz) | **0** (no clock in it) | **13-15 ns** (51 to ~37) | est from `gateware/README.md`'s table: the word's wait halves, L1 and L2 become 5 ns each | $0 | 2-4 days of gateware. Closing 200 MHz on the -1 part takes pipelining, and the lane needs a clock crossing. Low risk: a rebuild, with the old overlay kept |
| 3b | Or at 100 MHz, merge L1 and L2 into one clock | 0 | 10 ns | est | $0 | 1-2 days; the first-fired priority and the table must fit in 10 ns |
| 4 | Fast-path placement: pblock the CFGLUT5s by the pins | ≤1 ns, only on hops through CMP_IP or TX_I1 | ≤1 ns | Vivado: 9.3 ns same bank, 13.1 across the die, at the slow corner | $0 | An XDC line and a 40 min rebuild. The real fix is REVB 16's pinout |
| 5 | Ladder pins at DRIVE 16 instead of 8 (SLEW is FAST already) | ≤0.2 ns | ≤0.2 ns | est: the 200 ohm swamps the driver's 25-40 ohm | $0 | A rebuild |
| 6 | **Bypass the PYNQ-Z2's 200 ohm on the 9 fast lines** (5 comparator inputs, 4 ladder outputs), 0 ohm | **~2.7 ns** (1.35 TX, 1.4 RX), more if the edges are slow (section 2) | ~2.7 ns | model (`sim/latency_roadmap.py` step 2) | $0 in parts | About an hour of 0402 rework on the PYNQ, not on board A. **The risk is the comparator lines.** With board A powered and the PYNQ off, each high comparator output would push ~50 mA into a Zynq clamp, instead of ~12 mA through the 200 ohm. So the rule becomes "PYNQ first, always". 47 ohm instead of 0 keeps ~1.9 ns of the 2.7 but still lets ~27 mA through. The ladder's levels move, and VR_I / VR_Q re-trim them from software. **The 4 ladder outputs alone save ~1.35 ns, at almost no risk** |
| 7 | Ladder node 240 to 100 ohm on board A | 0.3 ns | 0.3 ns | model (`sim/hosts.py`) | ~$1 | 8-16 0402 swaps on the board you'd rather not rework; ~10 mA a pin. Not worth it |
| 8 | Arm gain 4 to 2 (170 MHz) | 0.1 ns | 0.1 ns | model (`docs/HOSTS.md`) | ~$0 | Worse at range: the CFAR window moves out with the noise. Not worth it |
| 9 | **Comparators:** TLV3603 (2.5 ns, CMOS out) to TLV3604 (0.8 ns, LVDS) | ~3 ns (1.7 the part, 1.4 the RC it removes) | ~3 ns | model, datasheet | +$2-4 a board, **but a re-spin** (~$1k for two) | LVDS needs pairs to the FPGA without series resistors. The PYNQ's header can't carry them: the 200 ohm sits in each leg. That means rev B, with an ECP5 on the board or a SYZYGY port. No CMOS-output comparator is much faster than 2.5 ns |
| 10 | The modulator: ADL5375 (750 MHz baseband) | ≤0.3 ns from a faster part | same | model: its pole is 0.2 ns | a re-spin | Not worth it. The TX's cost is the 200 ohm into the ladder (row 6), not the modulator |
| 11 | The demodulator and arm: ADL5380 (390 MHz), THS4541 at 94 MHz | ≤0.7 ns | same | model (PLAN.md section 19 row 5) | a re-spin, plus ~2 GHz of air (not in ISM or the 5 cm band) | Not worth it |
| 12 | RF chips and lines (1.6 ns both ways) | ~0.3 ns | same | model | a re-spin | Not worth it |
| 13 | **The fast path out of the FPGA:** ADCMP572 CML comparators into a CML answer gate on the modulator's baseband; the FPGA only arms and time-stamps | **~20 ns** (to ~2.4 ns) | n/a | model (PLAN.md section 19 row 4) | +$430-960 for two nodes, and a new board | High: CML levels into the ADL5375's 0.5 V baseband, the answer table in gates. The one big on-board lever |
| 14 | **Icepi Zero instead of the PYNQ** (board A unchanged) | **~2-3 ns** (row 6's resistors), if the ECP5's table is one level | today **slower** (see section 4) | nextpnr, model | $69-129 a board | 1-2 days: `top_icepi.v` builds no fast path yet. The host link is a 1 Mbaud UART |
| 15 | Antenna cables (off the board) | ~10 ns for 1 m of RG-316 each way | same | 4.8 ns/m | $0 | Put the box behind the antennas. Bigger than every on-board knob except row 13 |

**In order of value:**
- **Free now:** row 1 (−3 ns, settings only), then row 6's four ladder outputs (−1.35 ns, an hour on the PYNQ).
- **For the clocked reply:** row 3 (−13 to −15 ns, gateware only).
- Everything else on rev A is under a nanosecond, or needs a re-spin.
- **On a re-spin:** row 9 (LVDS comparators, with a host that has pairs), then row 13 (CML out of the FPGA), the only
  step change.

## 4. The Icepi Zero: faster or slower?

**On the fast path, faster by about 2-3 ns,** provided its table is built as one level of logic. The two FPGAs cost about
the same; the Icepi saves the PYNQ's resistors.
- **Its FPGA share:** nextpnr routed the fast path alone on the Icepi's pins (`bringup/latency/ecp5_fast_path.sh`,
  `ecp5_fast_path.txt`), at speed grade 6 (the Icepi's) and 8. nextpnr times from the input's I/O cell to the output's,
  so the pad buffers are not included.
  - **Generic** `fp_lut5.v` (a 5-input table): 6.4 ns at -6, 5.3 at -8. Yosys makes it a 32:1 mux of flip-flops, four
    LUT levels.
  - **One 16x4 distributed RAM** on the four windows (CMP_I left out, as B2 and A3r do): **3.9 ns at -6**, 3.0 at -8.
  - **The pad buffers:** about 4-5 ns more at -6 (the datasheet's 4.1 ns clock-to-output with the PLL, plus an input
    buffer).
- **The ECP5 against the Zynq:**
  - One level gives ~8.4 ns pin to pin at the slow corner. Vivado gives the Zynq 8.5-9.3 ns there, and board A measures
    5.0-6.25 at room temperature. So the ECP5 should land about where the Zynq does.
  - The generic table costs ~2.5 ns more, which eats most of the resistors' gain.
  - Lattice's own pin-to-pin table (32:1 mux, 4.85 ns at -8) is faster than nextpnr's figure, so nextpnr may be
    pessimistic.
- **What the missing resistors save:** ~2.7 ns by the model (row 6), and more if the edges are as slow as section 2
  suggests. The board was laid out for the Icepi: the comparators drive the header through their own 33 ohm.
- **On the clocked reply, slower today:**
  - its sampler is IDDRX1F at 200 Ms/s (5 ns steps, not 1.25);
  - its reply is registered once more (RP_REG, one clock);
  - its 100 MHz closes only on some placement seeds.
- **What would fix the clocked reply:** GDDRX2 on banks 6 and 7, which the pinout allows. The -6 part's limit is
  **624 Mb/s** (datasheet: 800 / 700 / 624 for -8 / -7 / -6), so `docs/HOSTS.md`'s 656 Ms/s is over the Icepi's grade.
  At 624 Ms/s (1.6 ns), the clocked reply would be close to the PYNQ's.

**What the Icepi does not change:** the comparators (2.5 ns), the arm, the modulator, the RF. With the windows low (row 1)
and the Icepi (row 14), the fast path would be ~18 ns. The next step is rows 9 and 13, on a new board.

## 5. Checks for board A (tomorrow, or as you pop in)

| check | needs | hands | then, remotely | answers |
|---|---|---|---|---|
| a. Repeat the sweep with A1 (sign(I) on CMP_I) and B2, counting idle false events at each window place | TODO step 1 (the sign jumpers) | none | 15 min | row 1's cost in false events; A1's turnaround |
| b. I MON and Q MON at the scope's 50 ohm inputs (each tap is 1 k into 50 ohm: /21, fast): the arm's 10-90 % rise on a TX toggle | nothing (the cables are on ch2 / ch3 already) | none | 10 min | whether the slow edge is before the comparator (section 2); the scope's own bandwidth sets the floor. The 50 ohm loads each leg with 1.05 k, so the window centres are re-measured after |
| c. TRIG OUT A (J205) to scope ch1 and CMP I MON (J103) to ch4, both at 50 ohm: from the TX event's mark to the sign comparator's output edge | step 1; moves REF OUT and VC MON off the scope | **2 min** | 15 min | splits the analog loop at the comparator output: the TX half plus RF plus arm, against the comparator plus RC plus FPGA |
| d. Rebuild with DRIVE 16 and a pblock on the fast path (rows 4-5) | Vivado | none | 40 min build, 10 min test | rows 4 and 5, measured |
| e. Optional: the PYNQ's 200 ohm to 0 ohm on the 4 ladder outputs only (row 6) | your call; the PYNQ, not board A | ~1 h | 10 min (ring before and after, VR re-trim) | row 6's TX half, measured |
