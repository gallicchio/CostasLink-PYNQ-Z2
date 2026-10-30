# CostasLink gateware

One board-independent core, `costaslink_core.v` (Verilog-2005), for both FPGA boards the CostasLink plugs
onto, with every experiment of `BRINGUP.md` in it: the transmitter's event, PRBS and rotation modes, the
receiver's event decoder at the fast sampler's resolution with confirm-or-veto, references, latencies, a
confusion matrix and a latency histogram, a PRBS bit-error check, the T/R sequencer, a counting gate for the
thresholds and the offsets, a block-RAM logic analyser, and the prover's answer: a synchronous reply to
each decision, a combinational pin-to-pin fast path, and a counter of the turnaround they make (Prompt 36,
[below](#the-turnaround-the-receive-to-transmit-paths-prompt-36)).  Around it, per board, only a sampler,
the clocks and a way in to its register bus:

| | PYNQ-Z2 (Zynq-7020) | Icepi Zero (ECP5-25) | simulation |
|---|---|---|---|
| top | `costaslink_pynq.v`, a module reference in a Vivado 2024.1 block design (`pynq/build.tcl`) | `top_icepi.v` | `costaslink_top.v`, `tb_*.v` |
| fabric clock | 100 MHz from the PS's FCLK0 through a clock wizard | 100 MHz from the 50 MHz oscillator through an EHXPLLL | any |
| fast sampler | `fast_sampler_7series.v`: ISERDESE2 8:1 DDR at 400 MHz, **800 Ms/s** (1.25 ns), SER = 8 | `fast_sampler_ecp5.v`: IDDRX1F, **200 Ms/s** (5 ns), SER = 2 | `fast_sampler_flop.v`, SER = 1 |
| register bus from | the PS: AXI-Lite at 0x43C00000 (`axil_bridge.v`) | the FTDI's UART at 1 Mbaud (`uart_cmd.v`) | the testbench |
| capture depth | 4096 words of 64 bits | 2048 words of 28 bits | 1024 |
| builds (2026-10-29) | 6423 LUTs, 7164 flip-flops, 12.5 BRAM tiles, 10 ISERDES; WNS +0.20 ns (the fast path's; 100 MHz +0.68 ns), WHS +0.03 ns | 12040 LUT4s, 6196 flip-flops, 7 DP16KD; 100.3 MHz (seed 1) | |
| reply paths (Prompt 36) | the synchronous reply 2 clocks after the ISERDESE2's word (1 after `fs`); the fast path pin to pin; the ladder pins read back | the synchronous reply 3 clocks after `fs` (RP_REG, no early word); no fast path | the PYNQ-Z2's |

Vivado 2024.1 is the version PYNQ 3.1 (the latest image for the PYNQ-Z2) is built with.  Plain Verilog, not
SystemVerilog: a block design's module reference cannot have a SystemVerilog top, and Yosys reads the same
files.  The register map is written once, in `regmap.py`: it generates `regmap.vh` for the RTL, the table
below, and the Python driver imports it.

## Files

| file | what |
|---|---|
| `costaslink_core.v` | the core: the bus stages, the five blocks below, the pins' sources (control bits or the sequencer), TRIG A / B, the read pipeline, BUILD |
| `bus_stage.v` | the bus and the reset registered once beside each block (keep_hierarchy: Yosys would merge the copies) |
| `costaslink_regs.v` | 0x00-0x2F, the first firmware's registers: control pins, SPI (synthesizers, DSA), the MAX2871 power-up, I2C (DACs, ADC, thresholds), counters |
| `tx_engine.v` | 0x30-0x3F: modes 0 (TXSYM, the BPSK pattern), 1 (events), 2 (events on TRIG_IN), 3 (PRBS symbols), 4 (rotation / FSK), 5 (one point held) |
| `rx_engine.v` | 0x40-0x5F: the event decoder, references, latencies, statistics, confusion matrix, histogram, BER check |
| `seq_gate.v` | 0x60-0x6F: the eight-step T/R sequencer and the counting gate |
| `capture.v` | 0x78-0x7D: the logic analyser (on the PYNQ-Z2 with the ladder pads read back, sample by sample) |
| `turnaround.v` | 0x90-0xA8: the synchronous reply, the fast path, the turnaround counter (Prompt 36) |
| `fp_lut5.v`, `fp_lut5_7series.v` | the fast path's reloadable 5-input table: plain Verilog (simulation, Yosys), a CFGLUT5 (the PYNQ-Z2) |
| `count_ram.v` | block-RAM counters (the confusion matrix, the histogram) |
| `prbs.v` | the PRBS polynomials, the self-synchronising checker's expectation, `prbs_multi` (up to three bits a clock, with look-ahead) |
| `cmp_monitor.v`, `tx_symbol.v`, `spi_master.v`, `i2c_master.v`, `max2871_init.v`, `morse_keyer.v` | the first firmware's blocks, unchanged in purpose |
| `costaslink_pynq.v`, `axil_bridge.v`, `fast_sampler_7series.v` | the PYNQ-Z2's top, AXI-Lite slave and sampler |
| `top_icepi.v`, `fast_sampler_ecp5.v`, `uart_rx.v`, `uart_tx.v`, `uart_cmd.v` | the Icepi Zero's top, sampler and UART bridge |
| `costaslink_top.v`, `fast_sampler_flop.v` | the generic top (UART at 115200, one sample a clock): simulation and `make synth` |
| `pynq/build.tcl`, `pynq/board_files/`, `pynq/bd_diagram.tcl`, `pynq/costaslink_pynq.xdc` | the Vivado project, block design, the diagram of it, the overlay's pins |
| `pynq/costaslink_fast_path.xdc`, `pynq/fast_path_report.tcl` | the receive-to-transmit paths' timing (by hand: no pin in it), and their report (`../build/pynq/fast_path.rpt`) |
| `pynq/sim_sampler.tcl`, `tb_sampler_7series.v`, `tb_fp_lut5_7series.v` | the ISERDESE2's sample order and latency, and the CFGLUT5's load, in Vivado's simulator (the UNISIM models) |
| `regmap.py` → `regmap.vh` | the register map |
| `max2871_regs.py` → `max2871_words.vh` | the synthesizers' words (RSET and CP from `board_constants.py`) |
| `gen_constants.py` → `board_constants.py` | the board's numbers the driver needs, from `build/budget.json` (do not edit) |
| `gen_xdc.py` | `pynq_z2.xdc`, `icepi_zero.lpf`, `pynq/costaslink_pynq.xdc` from `gen/pins.py` |
| `tb_costaslink.v`, `tb_engines.v`, `tb_loopback.vh`, `tb_axil.v`, `tb_pipe.v` | the testbenches (below) |
| `driver/costaslink.py`, `driver/sim_pipe.py`, `driver/test_sim.py` | the Python driver, its simulator bus, its tests against the RTL |

## Building and checking

```
make lint         # Verilator -Wall, the generic top and the core as the PYNQ-Z2 builds it: "lint: clean"
make sim          # tb_costaslink.v: the UART, SPI words, I2C transactions, TXSYM, counters, the keyer
make sim-engines  # tb_engines.v: every engine against the loopback model (twice: RP_REG 0 and 1)
make sim-axil     # tb_axil.v: AXI-Lite in every order SmartConnect may use, against the core
make sim-driver   # driver/test_sim.py: the Python driver's operations against the RTL
make pnr-icepi    # yosys + nextpnr-ecp5 + ecppack -> ../build/gateware_scratch/top_icepi.bit
```

Tools: an OSS CAD Suite on `PATH` (or `make BIN=...`); Python 3 for the driver.  Everything is written
under `../build/gateware_scratch/`.

**PYNQ-Z2.**  `source <Vivado 2024.1>/settings64.sh; cd gateware; vivado -mode batch -nojournal -log
../build/pynq_build.log -source pynq/build.tcl` builds the project in `../build/pynq/costaslink/` and, if
timing is met (it refuses otherwise), writes `../build/pynq/overlay/costaslink_top.{bit,hwh,xsa}` and the
block diagram's PDF, and `../build/pynq/fast_path.rpt`: the fast path's pin-to-pin delays, every comparator to
every ladder pin, max (slow corner) and min (fast corner), and the ladder pins' clock-to-pad.  About five
minutes.  `-tclargs -bench` adds a JTAG-to-AXI master for bring-up
without the PS; `-tclargs -synth_only` stops after synthesis.  Do not edit the sources while it runs: the
module reference's out-of-context run goes stale and the core comes out a black box.  On the board (PYNQ
3.1): copy `costaslink_top.bit`, `.hwh`, `driver/costaslink.py`, `regmap.py`, `max2871_regs.py` and `board_constants.py` into
one directory (the driver finds them beside it or one level up).

**Icepi Zero.**  `make pnr-icepi`; 100 MHz closes on some placements and not others, so the target tries
seeds 1-8 and keeps the first that meets it (`ICEPI_SEEDS`).  `openFPGALoader -b icepi-zero
../build/gateware_scratch/top_icepi.bit`.  The UART is the Icepi's FTDI at 1 Mbaud.  Fit R3xx (the DNP
4.7 k I2C pull-ups): the Icepi has none.

## The register bus

8-bit register numbers, 32-bit data; on AXI-Lite register n is at byte offset 4 n.  A write takes effect
two clocks after the bridge's `bus_we` (the block's bus stage, then its register).  A read returns the
register as it was three clocks after `bus_re`'s address went out (the bus stage, the block's read mux
registered, the choice among the blocks registered); a read's side effect (the confusion matrix's and the
histogram's next cell, the capture's next word) happens at the same edge as the block's register takes the
data, so a read returns the state before its own step.  `axil_bridge.v` takes the data on the fourth edge;
`uart_cmd.v` in `bus_re`'s clock, from an address that has stood since the line's hex digits.  Every
response is OKAY; an unlisted register reads 0xDEAD00nn.

## Time, and the pipeline's constants

Every time stamp and latency is in **samples** (RX_INFO and BUILD give SER and the clock): FREE_CNT x SER +
the sample's index.  The pipeline adds constants that the loopback calibration (BRINGUP stage 3.4) absorbs:
the ISERDESE2's word starts 4 samples after the fabric clock's edge (Vivado's simulator, with the MMCM's
phase: Prompt 36; the first testbench's misaligned clocks read 3); the
receiver's priority encoders are registered (one clock) before the decoder; the decision is a clock after
its sample is chosen; the reference's time is its own clock's.  So a latency is exact in samples, and
only the moments things happen move: TRIG_IN to a TX event on the pins is three clocks (rx_engine's stage
1, tx_engine's start, the pins' register); RX_TIMING's confirm delay counts from the decision, at least
three clocks after the event's clock; TRIG B marks the decision a few clocks after it.

## The turnaround: the receive-to-transmit paths (Prompt 36)

The prover's figure of merit is its turnaround: a state arrives at RX ANT, and the answer that depends on it
leaves TX ANT (PLAN.md section 19).  `turnaround.v` (0x90-0xA8) has two ways to answer and one way to
measure either on this board alone, in loopback (TX ANT to RX ANT through a cable and an attenuator).  The
numbers below are the 2026-10-29 build's (Vivado's slow-corner maximum and fast-corner minimum; the
ISERDESE2 from its UNISIM model).

**The synchronous reply (RP_CTRL, RP_MAP).**  On RX's valid decision of message k the ladders take
TX_POINTS[RP_MAP[k]] for RP_CTRL[31:16] clocks, over whatever tx_engine sends.  It is rx_engine's decision
(its table, its first-edge or settled rule, its arming), made in a lane of its own that reads the
ISERDESE2's word a clock before the sampler's register hands it to the rest of the core, and looks it up in
one composed table, comp[v] = {valid, TX_POINTS[RP_MAP[RX_LUT[v]]]}, straight into tx_engine's pins
register:

| step | clocks | ns |
|---|---|---|
| comparator pad -> the ISERDESE2's D (the input buffer) | | 0.3-1.5 |
| -> the next sample (800 Ms/s) | | 0-1.25 |
| the sample -> its word on the ISERDESE2's Q (its slot of eight) | | 6.25-15.0 |
| L1: the event, its first-fired set, its settled sample (a select set from RX_TIMING beforehand) | 1 | 10 |
| L2: the composed table into tx_engine's pins register | 1 | 10 |
| the pins register -> the ladder pad (clock-to-pad) | | 2.2-7.0 |
| **comparator pad -> ladder pad** | **2 after the word** | **28.7-44.7: 33.7 (fast corner) to 39.7 (slow) on average over the phase** |

rx_engine's own valid decision, and a TX event made from it, would come seven clocks after the word (the
sampler's register, its stage 1, S_DECIDE, the lookup, the decision, tx_engine's start, the pins'
register): 50 ns more.  A settled decision whose sample (RX_TIMING[7:0] after the event's) is in a later
word waits a clock for each (RX_TIMING 4: half the events, 5 ns on average); a first-edge decision never
waits.  `once` (RP_CTRL[1]) disarms the lane after a reply, and it re-arms on each of this board's TX
events (RP_CTRL[2]) or when RX re-arms (RP_CTRL[5]: the link quiet at its idle, whatever made the
stimulus), so in loopback the stimulus is answered and the answer's own echo is not.  The Icepi Zero
(RP_REG = 1, BUILD[15]) registers the point once more, a clock later: its LUT4s do not close L2 into the
pins at 100 MHz.

**The fast path (FP_USE, FP_MAP0-3, FP_CTRL, FP_TIME; the PYNQ-Z2).**  The five comparators, from their
ISERDESE2s' combinational O (IOBDELAY "NONE": O is D, the input buffer, while D feeds the deserialiser:
UG471, and the UNISIM model), choose FP_MAP[v] for the four ladder pins wherever FP_USE[v] is set, else the
pins' register passes: pin to pin through LUTs, no clock.  Per ladder bit, "force 1" and "force 0" are two
CFGLUT5s of the five comparators (`fp_lut5_7series.v`; Vivado places them as SRLC32E), then one LUT with
the arm and the pins' register: two LUT levels, each bit's by its own pad.  A write of FP_USE or FP_MAP
shifts the tables into them over 32 clocks (FP_CTRL[5]; disarmed meanwhile, an arming waits for it).  The
arm is synchronous: by FP_CTRL[0], on each TX event (FP_CTRL[3]) or when RX re-arms (FP_CTRL[4]); one
shot, it disarms FP_TIME clocks after the first change it causes (a sample whose vector it drives), or
timed (FP_CTRL[2]), FP_TIME clocks after the arming.  Pin to pin, ns, max (slow corner) / min (fast):

| from | TX_I0 | TX_I1 | TX_Q0 | TX_Q1 |
|---|---|---|---|---|
| CMP_I  | 8.91 / 2.98 | 12.51 / 4.17 | 8.81 / 2.86 | 9.09 / 2.87 |
| CMP_QP | 8.71 / 2.90 | 12.32 / 4.15 | 8.50 / 2.75 | 8.78 / 2.81 |
| CMP_QN | 9.15 / 3.05 | 12.60 / 4.03 | 8.98 / 2.91 | 9.27 / 2.93 |
| CMP_IP | 12.92 / 4.72 | 10.50 / 3.10 | 12.83 / 4.68 | 13.10 / 4.61 |
| CMP_IN | 8.93 / 2.94 | 12.26 / 4.28 | 8.76 / 2.84 | 9.04 / 2.83 |

* Of a same-side path's 8.5-9.3 ns, 4.9 are the buffers (the input 1.6, the LVCMOS33 8 mA FAST output 3.3)
  and 3.6-4.4 the fabric (O to the reloadable LUTs by the pads, the gate, the output buffer's tile).
* CMP_IP (bank 35) and TX_I1 (bank 34) are on the die's right side, everything else (bank 13) on its left:
  3.5-4 ns of routing across that no placement removes.  An answer decided without CMP_IP whose changes
  are on TX_I0, TX_Q0, TX_Q1 is the fast one (I = 0 coded 10 next to +a, 01 next to -a, moves only I0).
* The constraint (`pynq/costaslink_fast_path.xdc`): the generated XDC makes every path from an input port
  and to an output port false, a false path outranks set_max_delay, and Vivado 2024.1 has no reset_path,
  so set_max_delay goes on the fabric's segment, the ISERDESE2s' O to the OBUFTs' I (path segmentation:
  critical warnings 18-514 and 18-515, expected), one number per side of the die (with one for all the
  placer balanced every bit's LUTs mid-die and every path came out ~12 ns).  `pynq/fast_path_report.tcl`
  adds the buffers back and writes `../build/pynq/fast_path.rpt` every build.
* The ladder pins came from fabric flip-flops already (no IOB flip-flop in the 2026-10-11 build), so the
  gate LUT sits between tx_engine's pins register and the output buffer.  Its cost is only in the pads'
  time: that LUT and its route in every registered mode's clock-to-pad, which is now constrained (it had
  nothing: any route at all), 6.3-7.0 ns slow, 2.2-2.6 ns fast.  No 100 MHz path goes through it (they
  close at +0.68 ns; +1.66 before the reply lane).

**The counter (RT_CFG, RT_LAST ... RT_SPAN).**  An arrival is the first change of the watched comparators
(RT_CFG[12:8]) after RT_CFG[23:16] samples of quiet (8: 10 ns, more than a stimulus's own comparators take
to settle, A3's sign(I) 7.5 ns after its window; less than any turnaround).  After each of RX's references
(this board's TX event, or TRIG_IN's rise with RX_CTRL[3]) the first arrival is the stimulus's echo and
the second the answer's; their difference is the turnaround from RX ANT to TX ANT plus the cable: RT_LAST,
RT_MIN, RT_MAX, RT_SUM / RT_N, RT_MISS (no second arrival within RT_CFG[31:24] clocks).  Every arrival is
also counted, the first and the last kept (RT_MARKS, RT_SPAN; with RT_CFG[2] only inside the fast path's
armed window): a ring's hops.

**The capture.**  The PYNQ-Z2's ladder pins are IOBUFs, driving always (TX_Q1 released by CTRL[8] as
before), whose input buffers feed ISERDESE2s of their own (TXFB): 32 bits more a word (96, three chunks),
so a capture holds the fast path's output, which no register holds, and every pad's time, at 1.25 ns,
beside the comparators; context bit 15 (REPLY) marks a synchronous reply's first clock and the fast
path's armed window.  The pins and their standards are gen/pins.py's; only TX_I1, TX_I0 and TX_Q0 are now
inout, to be read back.

**The turnaround they make**, RX ANT to TX ANT, with PLAN.md section 19's and docs/TRAJECTORIES.md's
halves (the receive half ~15 ns, the transmit half ~8.5 ns with the PYNQ header's 200 ohm RC):

| path | FPGA pin to pin | RX ANT -> TX ANT |
|---|---|---|
| synchronous reply | 28.7-44.7 ns (34-40 on average) | ~52-68 ns (~58-63) |
| fast path, bank 13's pins | 2.7-9.3 ns | ~26-33 ns |
| fast path, CMP_IP or TX_I1 | 3.1-13.1 ns | ~27-37 ns |

**On the bench** (single-board loopback: TX ANT to RX ANT through ~40-60 dB, the link up as BRINGUP stage 3
leaves it):

```python
st = cl.loopback_turnaround("B1", path="sync", count=10000, period=1000)  # st["min_ns"], ["mean_ns"], ["max_ns"]
st = cl.loopback_turnaround("B1", path="fast", count=10000, period=1000)  # st["n"], ["miss"], st["rx"], st["reply"]
r = cl.ring_run("B1", clocks=100000)            # r["hops"], r["turnaround_ns"]: the span over hops - 1
r = cl.turnaround_capture("B1", path="fast")    # t1, t2, t3 from one capture: fpga_ns, loop_ns, turnaround_ns
st = cl.loopback_turnaround("A2", path="sync", stimulus="trig_in", seconds=10)   # a generator on TRIG IN
```

* A TX event is on the clock's grid, so in loopback the synchronous reply waits for its word at one fixed
  phase: one value of its 10 ns spread (which one, the loop's length sets).  A free-running pulse
  generator on TRIG IN (it sums into the Q ladder on the board: a short pulse, a scheme whose message is
  that Q step, RX's reference TRIG_IN) or a second board gives the spread.
* The arrivals are 1.25 ns samples at both ends, and with the phase fixed the error does not average from
  one stimulus to the next; the ring's span over its hops does (1.25 ns over hops - 1).
* `turnaround_capture` reads the pads back too: t2 - t1 is the FPGA's pin to pin (both pads through
  ISERDESE2s alike), t3 - t2 the RF loop.
* In the simulator (tb_loopback.vh: 13 samples of loop, a fast path of no delay) the counter reads 16
  samples for the synchronous reply (13 + the 3 to the next edge) and 13 for the fast path: the tests check
  those to the sample.

## The register map

Generated by `python3 regmap.py --md`.

| addr | name | R/W | bits |
|---|---|---|---|
| 0x00 | ID | R | 0x434C0003: 'CL', version 3 (Prompt 36: the reply paths and the turnaround counter; 2 was Response 15's engines) |
| 0x01 | CTRL | RW | [0] TX_DIS (reset 1: muted; header pin 24 carries its inverse, TX_EN), [1] LOOP_HOLD (reset 1), [2] LOOP_SEL, [3] TR_A (reset 1: receive), [6] ID enable, [7] pulse: ID now, [8] TX_Q1 high-impedance (unused since Prompt 35: TRIG IN sums into the Q ladder on the board) |
| 0x02 | TXSYM | RW | [3:0] {Q1 Q0 I1 I0} ladder point in TX_MODE 0; a write pulses TRIG_A; R [7:4] the pins now |
| 0x03 | PAT_PERIOD | RW | TX_MODE 0: clocks between BPSK flips (>= 2) |
| 0x04 | PAT_WIDTH | RW | TX_MODE 0: clocks a flip lasts; 0 = toggle |
| 0x05 | PAT_CTRL | RW | TX_MODE 0: W [0] start / stop, [31:16] flips (0 = forever); R [0] running |
| 0x06 | TRIG_CFG | RW | [7:0] trigger pulse width (clocks), [8] TRIG_A on symbol change, [9] TRIG_B on CMP_I edge, [10] TRIG_B rising only, [12:11] TRIG_A source (0 symbol change, 1 TX event start, 2 a reply: RP's first clock or FP's first change), [14:13] TRIG_B source (0 CMP_I edge, 1 RX event, 2 RX decision, 3 RX valid decision) |
| 0x08 | SPI_DATA | RW | the word to send |
| 0x09 | SPI_CTRL | RW | W [1:0] slave (0 TX PLL, 1 RX PLL, 2 DSA) and go; R [0] busy, [1] init busy |
| 0x0A | PLL_INIT | RW | W: both synthesizers' power-up sequence; R [0] busy, [1] done |
| 0x0B | STATUS | R | [0] MUX_TX, [1] MUX_RX, [2] SPI busy, [3] I2C busy, [4] ID active, [5] key down |
| 0x0C | BUS_COUNT | R | [15:0] reads, [31:16] writes |
| 0x10 | I2C_CTRL | RW | W [6:0] address, [11:8] bytes to write, [13:12] to read, go; R + [16] busy, [17] NACK, [18] done |
| 0x11 | I2C_WDATA0 | RW | bytes 0-3, byte 0 in [31:24] |
| 0x12 | I2C_WDATA1 | RW | bytes 4-7 |
| 0x13 | I2C_WDATA2 | RW | byte 8 in [31:24] |
| 0x14 | I2C_RDATA | R | [15:8] first byte read, [7:0] second |
| 0x18 | DAC_AB | RW | MCP4728 [27:16] A, [11:0] B |
| 0x19 | DAC_CD | RW | MCP4728 [27:16] C, [11:0] D |
| 0x1A | DAC_GO | RW | W [0] 0 = DAC 0x60, 1 = DAC 0x61: fast write of A-D |
| 0x1B | ADC_CFG | RW | W [1:0] ADS1115 channel |
| 0x1C | ADC_READ | RW | W: read; R [15:0] the conversion, [16] valid |
| 0x20 | CMP_STATE | R | synchronised pins: [0] CMP_I [1] CMP_QP [2] CMP_QN [3] CMP_I_S [4] CMP_QP_S [5] CMP_QN_S [6] TRIG_IN [7] MUX_TX [8] MUX_RX [9] CMP_IP [10] CMP_IN |
| 0x21 | FREE_CNT | R | the free-running clock counter (the time base of every time stamp) |
| 0x22 | EDGE_CNT0 | R | toggles of CMP_I |
| 0x23 | EDGE_CNT1 | R | toggles of CMP_QP |
| 0x24 | EDGE_CNT2 | R | toggles of CMP_QN |
| 0x25 | EDGE_CNT3 | R | toggles of CMP_I_S |
| 0x26 | EDGE_CNT4 | R | toggles of CMP_QP_S |
| 0x27 | EDGE_CNT5 | R | toggles of CMP_QN_S |
| 0x28 | CMP_I_TS | R | FREE_CNT at the last CMP_I edge |
| 0x29 | LAT | R | [15:0] clocks TRIG_IN -> CMP_I, [16] valid, [17] timed out |
| 0x2A | CNT_CTRL | W | [0] pulse: clear FREE_CNT and the edge counters |
| 0x2B | MORSE | R | [0] ID active, [1] key down, [31:16] seconds to the next ID |
| 0x2C | EDGE_CNT6 | R | toggles of CMP_IP |
| 0x2D | EDGE_CNT7 | R | toggles of CMP_IN |
| 0x30 | TX_MODE | RW | [2:0] 0 TXSYM / BPSK pattern (the first firmware), 1 events, 2 events on TRIG_IN, 3 PRBS symbols, 4 rotate (FSK), 5 hold one message point; [5:4] message source (0 TX_MSG, 1 count 0..N-1, 2 PRBS); [10:8] N-1, the number of messages (1-8) less one; [11] FSK direction (rotate backwards); [12] events only while the sequencer's TX gate is high |
| 0x31 | TX_IDLE | RW | [3:0] the idle point {Q1 Q0 I1 I0} (reset 0x7: I +a, Q 0) |
| 0x32 | TX_POINTS | RW | the eight message points, message k in [4k+3:4k] (reset: 0, the BPSK flip I -a, Q 0) |
| 0x33 | TX_MSG | RW | [2:0] the message in source 0; also the row of the RX confusion matrix when RX_CTRL[19] is clear |
| 0x34 | TX_PERIOD | RW | clocks from one event (or PRBS / rotation symbol) to the next (>= 1) |
| 0x35 | TX_WIDTH | RW | clocks an event's message point is held before the idle returns (>= 1) |
| 0x36 | TX_COUNT | RW | events to send (0 = until stopped) |
| 0x37 | TX_GO | RW | W [0] pulse: start, [1] pulse: stop, [2] pulse: one event now; R [0] running, [1] in an event |
| 0x38 | TX_STAT | R | [2:0] the last message sent, [31:8] events sent since the last start |
| 0x39 | TX_PRBS | RW | [2:0] polynomial (0 PRBS7, 1 PRBS9, 2 PRBS15, 3 PRBS23, 4 PRBS31), [8] reseed (pulse) |
| 0x3A | TX_EVT_TS | R | FREE_CNT at the last event's start |
| 0x40 | RX_CTRL | RW | [0] enable, [1] pulse: clear the counters, the confusion matrix and the histogram, [2] decide on the first comparators to fire instead of the vector after RX_DELAY, [3] reference = TRIG_IN's rising edge (else this board's TX event), [4] stop after one event, [18:16] the confusion row when [19] is clear, [19] row = the message this board's TX sent |
| 0x41 | RX_IDLE | RW | [4:0] the idle comparator vector {CMP_IN CMP_IP CMP_QN CMP_QP CMP_I}, [12:8] the event mask |
| 0x42 | RX_TIMING | RW | [7:0] decision delay (samples after the event), [15:8] quiet clocks to re-arm, [23:16] slow-comparator confirm delay (clocks after the decision) |
| 0x43 | RX_WINDOW | RW | clocks after a reference in which an event belongs to it (else false); a reference with no event in it is missed |
| 0x44 | RX_LUT0 | RW | the decoder table, vectors 0-7: entry v in [4v+3:4v] = {valid, message[2:0]} |
| 0x45 | RX_LUT1 | RW | vectors 8-15 |
| 0x46 | RX_LUT2 | RW | vectors 16-23 |
| 0x47 | RX_LUT3 | RW | vectors 24-31 |
| 0x48 | RX_SLOW_EXP | RW | message k in [4k+3:4k]: {care, CMP_QN_S CMP_QP_S CMP_I_S} expected at confirm time |
| 0x49 | RX_EVENTS | R | events |
| 0x4A | RX_DECIDED | R | decisions with a valid table entry |
| 0x4B | RX_CONFIRM | R | decisions the slow comparators confirmed |
| 0x4C | RX_VETO | R | decisions the slow comparators vetoed |
| 0x4D | RX_FALSE | R | events with no reference in the window before them |
| 0x4E | RX_MISSED | R | references with no event in the window after them |
| 0x4F | RX_REFS | R | references seen |
| 0x50 | RX_LAST | R | [2:0] message, [3] valid, [8:4] vector at the decision, [13:9] first fired, [14] confirmed, [15] vetoed, [16] had a reference |
| 0x51 | RX_LAST_LAT | R | [15:0] reference -> event, [31:16] reference -> decision (samples, saturating) |
| 0x52 | RX_LAT_MIN | R | [15:0] the least reference -> decision since the clear |
| 0x53 | RX_LAT_MAX | R | [15:0] the most |
| 0x54 | RX_LAT_SUM | R | the sum of reference -> decision (samples), for the mean (with RX_LAT_N) |
| 0x55 | RX_LAT_N | R | the number summed |
| 0x56 | RX_CM_ADDR | RW | [5:0] confusion-matrix cell row*8 + message (row = TX message, column = decoded) |
| 0x57 | RX_CM_DATA | R | the cell's count; the address steps on by one after each read |
| 0x58 | RX_HIST_CFG | RW | [1:0] what: 0 ref -> event, 1 ref -> decision, 2 event -> the next event; [7:4] bin = 2^n samples |
| 0x59 | RX_HIST_ADDR | RW | [9:0] the bin to read |
| 0x5A | RX_HIST_DATA | R | the bin's count; the address steps on after each read (1024 bins, the last holds overflow) |
| 0x5B | RX_EVT_TS | R | FREE_CNT at the last event |
| 0x5C | RX_BER_CFG | RW | [0] check a PRBS on CMP_I (a write that sets it starts a new count; one that clears it keeps the count), [1] invert, [6:4] the polynomial as TX_PRBS, [23:8] the sampling phase (samples into each symbol), symbol length = TX_PERIOD |
| 0x5D | RX_BER_BITS | R | bits checked |
| 0x5E | RX_BER_ERR | R | mismatches (a self-synchronising check counts each bit error three times) |
| 0x5F | RX_INFO | R | [7:0] samples a clock (SER), [15:8] fast inputs, [31:16] the clock in MHz |
| 0x60 | SEQ_CTRL | RW | W [0] pulse: run, [1] loop, [2] pulse: stop, [10:8] steps less one, [11] enable (the steps own TR_A, LOOP_HOLD, TX_DIS and the TX gate while running); R [0] running, [10:8] the step now |
| 0x61 | SEQ_SEL | RW | [2:0] the step SEQ_OUT and SEQ_DUR read and write |
| 0x62 | SEQ_OUT | RW | [0] TR_A, [1] LOOP_HOLD, [2] TX_DIS, [3] TX gate, during the step |
| 0x63 | SEQ_DUR | RW | the step's length in clocks (>= 1) |
| 0x68 | GATE_CTRL | RW | W [0] pulse: open the gate for GATE_LEN clocks; R [0] open, [1] done |
| 0x69 | GATE_LEN | RW | the gate's length in clocks |
| 0x6A | GATE_SEL | RW | [3:0] the input GATE_EDGES and GATE_HIGH read: 0 CMP_I 1 CMP_QP 2 CMP_QN 3 CMP_IP 4 CMP_IN 5 TRIG_IN 6 CMP_I_S 7 CMP_QP_S 8 CMP_QN_S |
| 0x6B | GATE_EDGES | R | the selected input's edges (both directions) while the gate was open |
| 0x6C | GATE_HIGH | R | samples the selected input was high while the gate was open (fast inputs: SER a clock) |
| 0x6D | GATE_EVENTS | R | RX events while the gate was open |
| 0x78 | CAP_CTRL | RW | W [0] pulse: arm, [1] pulse: trigger now, [6:4] trigger (0 none, 1 TX event, 2 RX event, 3 TRIG_IN rising, 4 any fast comparator change, 5 RX decision, 6 a sequencer step begins, 7 a reply); R [0] armed, [1] triggered, [2] done, [3] a whole buffer was written since the arming |
| 0x79 | CAP_POST | RW | words written after the trigger (the rest of the buffer is before it) |
| 0x7A | CAP_ADDR | RW | [15:0] the word, counted from the oldest, [17:16] its 32-bit chunk (words over 32 bits: 0 the lowest) |
| 0x7B | CAP_DATA | R | the chunk; reading the last chunk of a word steps on to the next word |
| 0x7C | CAP_INFO | R | [7:0] samples a clock, [15:8] the word's width in bits, [23:16] log2 of the depth, [24] the ladder pins' read-back samples follow the context (4 x SER bits) |
| 0x7D | CAP_TRIG | R | [15:0] the trigger's word, counted from the oldest; [31:16] the words written since the arming (only the newest that many are this capture's) |
| 0x80 | BUILD | R | [7:0] SER, [11:8] board (0 simulation, 1 PYNQ-Z2, 2 Icepi Zero), [12] the fast path is built, [13] the ladder pins are read back into the capture, [14] the reply lane reads the sampler's word a clock early, [15] the synchronous reply registered once more (a clock later), [31:16] clock in MHz |
| 0x90 | RP_CTRL | RW | the synchronous reply: [0] enable (a write that sets it arms), [1] once: disarm after a reply, [2] re-arm on each of this board's TX events (the stimulus), [3] pulse: arm, [4] pulse: disarm, [5] re-arm when RX re-arms (the link quiet at its idle: any stimulus), [31:16] clocks the reply's point is held (0 = 1); R + [8] armed |
| 0x91 | RP_MAP | RW | the reply to message k in [4k+2:4k]: on RX's valid decision of k the pins take TX_POINTS[RP_MAP[k]] (the composed table follows a write of RX_LUT, TX_POINTS or RP_MAP in 32 clocks) |
| 0x92 | RP_STAT | R | [2:0] the last message answered, [6:4] its reply, [31:8] replies since RP_CTRL was written |
| 0x94 | FP_CTRL | RW | the fast path: W [0] pulse: arm, [1] pulse: disarm, [2] timed (the ring: armed FP_TIME clocks) instead of one shot (disarmed FP_TIME clocks after the first change it causes), [3] arm on each of this board's TX events, [4] arm when RX re-arms; R [0] armed, [1] it drove the pins since the arming, [2] timed, [3] arm on TX, [4] arm on RX, [5] the tables loading (32 clocks after a write of FP_USE or FP_MAP: disarmed, an arming waits), [8] built |
| 0x95 | FP_TIME | RW | clocks: after the first change (one shot) or after the arming (timed) to the disarm (>= 1) |
| 0x96 | FP_USE | RW | bit v: comparator vector v drives the pins with FP_MAP[v] while armed (else the pins' register passes) |
| 0x98 | FP_MAP0 | RW | the fast path's points, vectors 0-7: entry v in [4v+3:4v] = {Q1 Q0 I1 I0} |
| 0x99 | FP_MAP1 | RW | vectors 8-15 |
| 0x9A | FP_MAP2 | RW | vectors 16-23 |
| 0x9B | FP_MAP3 | RW | vectors 24-31 |
| 0xA0 | RT_CFG | RW | the turnaround counter: [0] enable, [1] pulse: clear, [2] count arrivals only while the fast path is armed (the ring), [12:8] the comparators watched (reset 0x1F), [23:16] guard: samples of quiet before a change is an arrival (reset 8), [31:24] clocks after the first arrival the second may take (0 = no limit) |
| 0xA1 | RT_LAST | R | [15:0] the last turnaround: the reference's first arrival -> its second (samples), [31:16] reference (RX's: this board's TX event, or TRIG_IN's rise with RX_CTRL[3]) -> first arrival |
| 0xA2 | RT_MIN | R | [15:0] the least turnaround since the clear |
| 0xA3 | RT_MAX | R | [15:0] the most |
| 0xA4 | RT_SUM | R | the turnarounds' sum (samples), for the mean (with RT_N) |
| 0xA5 | RT_N | R | turnarounds measured |
| 0xA6 | RT_MISS | R | references whose second arrival did not come (a new reference first, or the window ran out) |
| 0xA7 | RT_MARKS | R | arrivals since the clear (with RT_CFG[2] inside the fast path's armed window: the ring's hops) |
| 0xA8 | RT_SPAN | R | samples from the first of those arrivals to the last |

## The Python driver (`driver/costaslink.py`)

```python
from costaslink import CostasLink, PynqBus, UartBus, SCHEMES
cl = CostasLink(PynqBus("costaslink_top.bit"))      # PYNQ-Z2, as root;  Icepi: CostasLink(UartBus("/dev/ttyUSB0"))
cl.info()                                           # board, clock, SER, the capture's size
cl.bringup_stage1(eeprom=True)                      # I2C scan, DAC EEPROM defaults, the ADC's four channels
cl.pll_init()                                       # both synthesizers (stage 2.1)
cl.scheme("A3")                                     # TX points and the RX table for the plan's corners
st = cl.loopback_latency("A3", period=2000, count=10000)   # stage 3.4-3.5: statistics + confusion matrix
cl.threshold_scan("QP", volts); CostasLink.rice_fit(points) # stage 3.7: sigma and offset by counting
cl.threshold_servo("QP", rate_hz=1/60)              # one false event a minute
cl.null_slow_offsets()                              # stage 3.2: the slow comparators to 50 % duty
cl.agc(); cl.received_dBm(ext_db=15)                # the DSA to the regulated level; the level at the antenna
                                                    # (locked; +15 for an LNA module ahead of RX ANT): the RSSI
cap = cl.capture("tx_event", post=256, start=cl.tx_one)    # the in-FPGA scope
cl.ber_run(seconds=1, poly=15, period=1, invert=True)      # stage 4.3: BPSK PRBS at the clock rate
cl.time_division(rx_clocks, tx_clocks)              # stage 4.4: the T/R sequence
st = cl.loopback_turnaround("B1", path="sync")      # the turnaround, single-board loopback (Prompt 36, below)
st = cl.loopback_turnaround("B1", path="fast")      # the same through the combinational fast path
r = cl.ring_run("B1", clocks=100000)                # the fast path as a ring: r["turnaround_ns"] a hop
r = cl.turnaround_capture("B1", path="fast")        # one stimulus captured: t1, t2, t3, fpga_ns, loop_ns
```

`SCHEMES` holds PLAN.md section 18's rev-A schemes (A1, A1w, A2, A3, A4, B1, B2) in the transmitter's frame
with the receiver's rotation (the pilot at 45 degrees lands on +I), and computes from the comparator model
the idle vector, the event mask, the 32-entry table for the settled vector or for the first-fired set (a
vector one message alone can make decides it; one two can make stays invalid) and the slow comparators'
expectations; `Scheme.twin()` is the Costas loop's 180-degree lock point.  The I2C parts and their channels
(AD5696R 0x0C: V_TQP, V_TQN, V_TIP, V_TIN; MCP4728 0x60: VR_I, VR_Q, Q_OFF_F, VC_OFF; 0x61: V_T2, I_OFF,
Q_OFF, I_OFF_F; ADS1115 0x48: I, Q, VC, ERR; ADS1115 0x49: LOG_Q, PEAK_Q, V5_MON, TEMP) are the schematic
generator's; the board's numbers are `board_constants.py`'s, which the build generates from `sim/budget.py`.

## The testbenches

* `tb_costaslink.v` (`make sim`): the generic top through its UART: the 16 MAX2871 words against
  `max2871_regs.py --hex`, the DSA word, the I2C transactions against a slave model, TXSYM and TRIG A, the
  counters and the TRIG_IN latency, the keyer's elements to the unit.
* `tb_engines.v` (`make sim-engines`): the core at SER = 4 against `tb_loopback.vh` (the pins come back on
  the fast comparators 13 samples later and on the slow ones 40): events and decisions (settled and
  first-edge), the confusion matrix, the latency to the sample and the histogram, false and missed events,
  confirm and veto, the capture buffer (the trigger word, the words since the arming, the latency inside
  it, the ladder pins' read-back, a chunk address), the sequencer, the gate's counts, TX on TRIG_IN with
  TRIG_IN as the reference, and a PRBS through the loop with an error injected.  Then (Prompt 36: the core
  with the PYNQ-Z2's EARLY, FAST_PATH and TXFB) the synchronous reply: every stimulus answered with the
  next corner, in the pins' log and in RX's statistics, first-edge, settled two samples on (the same
  clock) and two words on (two clocks later), once without and with the re-arms (TX event, RX); the
  fast path one shot (armed by the TX event, and by RX's re-arm) and as a ring started from the idle
  (hops x LAT = the span); the turnaround counter exact to the sample on each.
* `tb_loopback.vh` runs sample by sample (Prompt 36), so the fast path's combinational loop closes in it:
  the pins recorded each sample, the comparators driven each sample on `cmp_async`, the next clock's word
  ready a quarter sample before its edge (`fs_early`, the ISERDESE2's word a clock before its register).
  The fast path has no delay of its own there (RTL), so a turnaround through it is the model's LAT; the
  ladder pins' read-back is a clock late in the model (on the PYNQ-Z2 both go through ISERDESE2s alike).
* `tb_axil.v` (`make sim-axil`): writes with the address and data together, either first, a late RREADY,
  back-to-back reads of different registers, read after write, and the AXI rules (VALID held until READY,
  one response per request).  Taking the data one clock early fails it.
* `tb_sampler_7series.v` (`pynq/sim_sampler.tcl`, Vivado's xsim with UNISIM and secure-IP): the ISERDESE2's
  bit order (Q8 is the earliest), the word's offset and its latency, with clk_fast's rising edges on clk's
  as the MMCM makes them (Prompt 36: the testbench had clk_fast's falling edge there and read 3 samples;
  the MMCM's phase gives 4: a word holds the samples from E(n-1) + 5 ns to E(n) + 3.75 ns and is on Q at
  E(n+1), in the sampler's register at E(n+2); a sample is on Q 6.25-15 ns after it is taken).
  `tb_fp_lut5_7series.v` (the same script): fp_lut5_7series.v's CFGLUT5 loads and reads as fp_lut5.v.
* `driver/test_sim.py` (`make sim-driver`): the driver through `tb_pipe.v` (the core at SER = 8 and the
  loopback model behind two named pipes): the scheme tables against tb_engines' proven constants, A3 and
  B1 (first-edge) through the loop, false events from injected noise counted by the gate and the decoder,
  a capture on a TX event and on a sequencer step, the BER check with its polarity and a flipped symbol,
  the sequencer on TR_A, the TRIG_IN reference; and the turnaround's operations (Prompt 36): the
  synchronous reply on B1 (first edge) and A3 (settled, the same clock and two words on), the fast path,
  `turnaround_capture`'s t1 / t2 / t3 from a capture with the pads read back, the ring on A3 from the
  idle and on B1 from a stimulus, the ring's table (no fixed point).

## Timing closure (what the Icepi's 100 MHz taught; the PYNQ gains the same margin)

The first full core closed at 44 MHz on the ECP5.  Each step below moved the worst path and kept every
latency in samples: the fine time as an OR (SER a power of two) instead of an add; the decision a clock
after the event; the PRBS as five fixed-tap registers with three bits of look-ahead, then with its advance
a clock late behind two flip-flops; the read data registered, then the blocks' read muxes too, then the bus
registered beside each block; the capture's trigger and word through one register; the counter RAMs' read
through a register (the DP16KD's clock-to-out is 5.6 ns); the sequencer's outputs registered; the bus write
last in its block instead of a decode in front of every counter; the TX period's and hold's zero tests as
registers; the receiver's priority encoders registered; the table lookup a clock after the sample's
choice; the latency sum a stage of its own; the point lookup in the pins' stage.  What remains on the
ECP5 is the TX event's fan-out to ~150 flip-flops (91-99 MHz on the placements that miss).

## Not here yet

* The whitened stream (scrambler, Gardner timing): PRBS symbols and the check on CMP_I stand in.
* The Q bit's error rate: the BER check reads CMP_I only; the confusion matrix counts symbol errors.
* A synchronous reply in one clock after the ISERDESE2's word instead of two (the encoder, the table and
  the pins' register in one clock): the far bank's route (CMP_IP on bank 35, the rest on bank 13) leaves
  too little of the 10 ns.  And a synchronous ring: rx_engine decides only from its idle.
* The fast path's turnaround as a sample-exact distribution: the counter's arrivals are quantised to 1.25 ns
  at both ends, and in single-board loopback the phase is fixed, so one stimulus after another reads the
  same value; the ring averages it over its hops.
* The sample clock from the radio's reference: TRIG_IN is on a clock-capable pin on both boards (U19
  MRCC, G1 PCLK), so REF OUT cabled to TRIG IN could clock the MMCM and make two boards' time stamps
  coherent (one-way time transfer); the clock wizard takes FCLK0 now.
* IDDRX2F on the Icepi (the fast inputs are on banks 6 / 7, which have the gearing): 400 Ms/s from the 100 MHz
  fabric clock, 656 Ms/s with a 164 MHz one (docs/HOSTS.md's figure).
* The ECP5 IDDRX1F's sample order is from TN1265, not simulated: BRINGUP stage 0 checks it on the bench.
* Re-centring the RX synthesizer (stage 4.1) is the host's: `CostasLink.pll_tune`.

## The window thresholds (Response 14)

The four window comparators (sheet 7) take their thresholds from an AD5696R at I2C address 0x0C, written
through the generic I2C registers (0x10-0x14; `CostasLink.threshold`): three bytes, a command byte `0x3n` (write and update DAC
channel n: 1 = A = V_TQP, 2 = B = V_TQN, 4 = C = V_TIP, 8 = D = V_TIN) and the 16-bit code, high byte
first.  Code = V / 2.5 V x 65536.  The thresholds want setting from the idle by counting: hold the link idle,
open the counting gate (0x68-0x6D: `CostasLink.gate`) and move each threshold until its comparator's count
meets the target (PLAN.md section 18; `CostasLink.threshold_servo`).

