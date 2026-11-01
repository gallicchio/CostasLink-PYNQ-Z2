#!/usr/bin/env python3
"""The CostasLink register map: the one source of truth (Response 15).

    python3 regmap.py --vh     writes regmap.vh (the Verilog addresses, included by the RTL; committed)
    python3 regmap.py --md     prints the README's register table
    python3 regmap.py --check  checks the map: no address twice, every block inside its range

The Python drivers (driver/costaslink.py on the PYNQ, driver/uart_client.py for the Icepi and the bench)
import REGS from here, so a register's address and fields are written once.  8-bit register numbers,
32-bit data; on AXI-Lite (PYNQ) register n is at byte offset 4 n.
"""
import os, sys

# (address, name, access, block, description).  access: R, W, RW; "pulse" in the text = acts once.
REGS = [
    # ---- the first firmware (Response 9 and 14): costaslink_regs.v, cmp_monitor.v ------------------------
    (0x00, "ID", "R", "regs", "0x434C0005: 'CL', version 5 (2026-10-30: the interference hold and the signal holdover; 4 the BER check's timing recovery; 3 the reply paths and the turnaround counter, Prompt 36; 2 Response 15's engines)"),
    (0x01, "CTRL", "RW", "regs", "[0] TX_DIS (reset 1: muted; header pin 24 carries its inverse, TX_EN), [1] LOOP_HOLD (reset 1), [2] LOOP_SEL, [3] TR_A (reset 1: receive), "
                                 "[6] ID enable, [7] pulse: ID now, [8] TX_Q1 high-impedance (unused since Prompt 35: TRIG IN sums into the Q ladder on the board)"),
    (0x02, "TXSYM", "RW", "regs", "[3:0] {Q1 Q0 I1 I0} ladder point in TX_MODE 0; a write pulses TRIG_A; R [7:4] the pins now"),
    (0x03, "PAT_PERIOD", "RW", "regs", "TX_MODE 0: clocks between BPSK flips (>= 2)"),
    (0x04, "PAT_WIDTH", "RW", "regs", "TX_MODE 0: clocks a flip lasts; 0 = toggle"),
    (0x05, "PAT_CTRL", "RW", "regs", "TX_MODE 0: W [0] start / stop, [31:16] flips (0 = forever); R [0] running"),
    (0x06, "TRIG_CFG", "RW", "regs", "[7:0] trigger pulse width (clocks), [8] TRIG_A on symbol change, [9] TRIG_B on CMP_I edge, "
                                     "[10] TRIG_B rising only, [12:11] TRIG_A source (0 symbol change, 1 TX event start, 2 a reply: RP's first clock or FP's first change), "
                                     "[14:13] TRIG_B source (0 CMP_I edge, 1 RX event, 2 RX decision, 3 RX valid decision)"),
    (0x08, "SPI_DATA", "RW", "regs", "the word to send"),
    (0x09, "SPI_CTRL", "RW", "regs", "W [1:0] slave (0 TX PLL, 1 RX PLL, 2 DSA) and go; R [0] busy, [1] init busy"),
    (0x0A, "PLL_INIT", "RW", "regs", "W: both synthesizers' power-up sequence; R [0] busy, [1] done"),
    (0x0B, "STATUS", "R", "regs", "[0] MUX_TX, [1] MUX_RX, [2] SPI busy, [3] I2C busy, [4] ID active, [5] key down"),
    (0x0C, "BUS_COUNT", "R", "regs", "[15:0] reads, [31:16] writes"),
    (0x10, "I2C_CTRL", "RW", "regs", "W [6:0] address, [11:8] bytes to write, [13:12] to read, go; R + [16] busy, [17] NACK, [18] done, "
     "[19] timeout (SCL held low 10 ms: abandoned, NACK too), [20] SCL and [21] SDA as they are now"),
    (0x11, "I2C_WDATA0", "RW", "regs", "bytes 0-3, byte 0 in [31:24]"),
    (0x12, "I2C_WDATA1", "RW", "regs", "bytes 4-7"),
    (0x13, "I2C_WDATA2", "RW", "regs", "byte 8 in [31:24]"),
    (0x14, "I2C_RDATA", "R", "regs", "[15:8] first byte read, [7:0] second"),
    (0x18, "DAC_AB", "RW", "regs", "MCP4728 [27:16] A, [11:0] B"),
    (0x19, "DAC_CD", "RW", "regs", "MCP4728 [27:16] C, [11:0] D"),
    (0x1A, "DAC_GO", "RW", "regs", "W [0] 0 = DAC 0x60, 1 = DAC 0x61: fast write of A-D"),
    (0x1B, "ADC_CFG", "RW", "regs", "W [1:0] ADS1115 channel"),
    (0x1C, "ADC_READ", "RW", "regs", "W: read; R [15:0] the conversion, [16] valid"),
    (0x20, "CMP_STATE", "R", "regs", "synchronised pins: [0] CMP_I [1] CMP_QP [2] CMP_QN [3] CMP_I_S [4] CMP_QP_S [5] CMP_QN_S "
                                     "[6] TRIG_IN [7] MUX_TX [8] MUX_RX [9] CMP_IP [10] CMP_IN"),
    (0x21, "FREE_CNT", "R", "regs", "the free-running clock counter (the time base of every time stamp)"),
    (0x22, "EDGE_CNT0", "R", "regs", "toggles of CMP_I"),
    (0x23, "EDGE_CNT1", "R", "regs", "toggles of CMP_QP"),
    (0x24, "EDGE_CNT2", "R", "regs", "toggles of CMP_QN"),
    (0x25, "EDGE_CNT3", "R", "regs", "toggles of CMP_I_S"),
    (0x26, "EDGE_CNT4", "R", "regs", "toggles of CMP_QP_S"),
    (0x27, "EDGE_CNT5", "R", "regs", "toggles of CMP_QN_S"),
    (0x28, "CMP_I_TS", "R", "regs", "FREE_CNT at the last CMP_I edge"),
    (0x29, "LAT", "R", "regs", "[15:0] clocks TRIG_IN -> CMP_I, [16] valid, [17] timed out"),
    (0x2A, "CNT_CTRL", "W", "regs", "[0] pulse: clear FREE_CNT and the edge counters"),
    (0x2B, "MORSE", "R", "regs", "[0] ID active, [1] key down, [31:16] seconds to the next ID"),
    (0x2C, "EDGE_CNT6", "R", "regs", "toggles of CMP_IP"),
    (0x2D, "EDGE_CNT7", "R", "regs", "toggles of CMP_IN"),

    # ---- the transmitter: tx_engine.v --------------------------------------------------------------------
    (0x30, "TX_MODE", "RW", "tx", "[2:0] 0 TXSYM / BPSK pattern (the first firmware), 1 events, 2 events on TRIG_IN, "
                                  "3 PRBS symbols, 4 rotate (FSK), 5 hold one message point; [5:4] message source "
                                  "(0 TX_MSG, 1 count 0..N-1, 2 PRBS); [10:8] N-1, the number of messages (1-8) less one; "
                                  "[11] FSK direction (rotate backwards); [12] events only while the sequencer's TX gate is high"),
    (0x31, "TX_IDLE", "RW", "tx", "[3:0] the idle point {Q1 Q0 I1 I0} (reset 0x7: I +a, Q 0)"),
    (0x32, "TX_POINTS", "RW", "tx", "the eight message points, message k in [4k+3:4k] (reset: 0, the BPSK flip I -a, Q 0)"),
    (0x33, "TX_MSG", "RW", "tx", "[2:0] the message in source 0; also the row of the RX confusion matrix when RX_CTRL[19] is clear"),
    (0x34, "TX_PERIOD", "RW", "tx", "clocks from one event (or PRBS / rotation symbol) to the next (>= 1)"),
    (0x35, "TX_WIDTH", "RW", "tx", "clocks an event's message point is held before the idle returns (>= 1)"),
    (0x36, "TX_COUNT", "RW", "tx", "events to send (0 = until stopped)"),
    (0x37, "TX_GO", "RW", "tx", "W [0] pulse: start, [1] pulse: stop, [2] pulse: one event now; R [0] running, [1] in an event"),
    (0x38, "TX_STAT", "R", "tx", "[2:0] the last message sent, [31:8] events sent since the last start"),
    (0x39, "TX_PRBS", "RW", "tx", "[2:0] polynomial (0 PRBS7, 1 PRBS9, 2 PRBS15, 3 PRBS23, 4 PRBS31), [8] reseed (pulse)"),
    (0x3A, "TX_EVT_TS", "R", "tx", "FREE_CNT at the last event's start"),

    # ---- the receiver: rx_engine.v -------------------------------------------------------------------------
    (0x40, "RX_CTRL", "RW", "rx", "[0] enable, [1] pulse: clear the counters, the confusion matrix and the histogram, "
                                  "[2] decide on the first comparators to fire instead of the vector after RX_DELAY, "
                                  "[3] reference = TRIG_IN's rising edge (else this board's TX event), [4] stop after one event, "
                                  "[18:16] the confusion row when [19] is clear, [19] row = the message this board's TX sent"),
    (0x41, "RX_IDLE", "RW", "rx", "[4:0] the idle comparator vector {CMP_IN CMP_IP CMP_QN CMP_QP CMP_I}, [12:8] the event mask"),
    (0x42, "RX_TIMING", "RW", "rx", "[7:0] decision delay (samples after the event), [15:8] quiet clocks to re-arm, "
                                    "[23:16] slow-comparator confirm delay (clocks after the decision), [31:24] ID 11: "
                                    "settle k: decide on the first vector one state's that has held k samples, [7:0] the "
                                    "longest wait (0: always [7:0] after the event)"),
    (0x43, "RX_WINDOW", "RW", "rx", "clocks after a reference in which an event belongs to it (else false); a reference with "
                                    "no event in it is missed"),
    (0x44, "RX_LUT0", "RW", "rx", "the decoder table, vectors 0-7: entry v in [4v+3:4v] = {valid, message[2:0]}"),
    (0x45, "RX_LUT1", "RW", "rx", "vectors 8-15"),
    (0x46, "RX_LUT2", "RW", "rx", "vectors 16-23"),
    (0x47, "RX_LUT3", "RW", "rx", "vectors 24-31"),
    (0x48, "RX_SLOW_EXP", "RW", "rx", "message k in [4k+3:4k]: {care, CMP_QN_S CMP_QP_S CMP_I_S} expected at confirm time"),
    (0x49, "RX_EVENTS", "R", "rx", "events"),
    (0x4A, "RX_DECIDED", "R", "rx", "decisions with a valid table entry (false events' included)"),
    (0x4B, "RX_CONFIRM", "R", "rx", "decisions the slow comparators confirmed"),
    (0x4C, "RX_VETO", "R", "rx", "decisions the slow comparators vetoed"),
    (0x4D, "RX_FALSE", "R", "rx", "events with no reference in the window before them"),
    (0x4E, "RX_MISSED", "R", "rx", "references with no event in the window after them (from ID 10 an event on the clock a "
                                   "reference runs out is false, not also its pair)"),
    (0x4F, "RX_REFS", "R", "rx", "references seen"),
    (0x50, "RX_LAST", "R", "rx", "[2:0] message, [3] valid, [8:4] vector at the decision, [13:9] first fired, [14] confirmed, "
                                 "[15] vetoed, [16] had a reference"),
    (0x51, "RX_LAST_LAT", "R", "rx", "[15:0] reference -> event, [31:16] reference -> decision (samples, saturating)"),
    (0x52, "RX_LAT_MIN", "R", "rx", "[15:0] the least reference -> decision since the clear"),
    (0x53, "RX_LAT_MAX", "R", "rx", "[15:0] the most"),
    (0x54, "RX_LAT_SUM", "R", "rx", "the sum of reference -> decision (samples), for the mean (with RX_LAT_N)"),
    (0x55, "RX_LAT_N", "R", "rx", "the number summed"),
    (0x56, "RX_CM_ADDR", "RW", "rx", "[5:0] confusion-matrix cell row*8 + message (row = TX message, column = decoded); "
                                    "from ID 10, with RX_CTRL[19] (the row from this board's TX), only events with a "
                                    "reference are counted (before, a false event's decision counted against the last "
                                    "message sent)"),
    (0x57, "RX_CM_DATA", "R", "rx", "the cell's count; the address steps on by one after each read"),
    (0x58, "RX_HIST_CFG", "RW", "rx", "[1:0] what: 0 ref -> event, 1 ref -> decision, 2 event -> the next event; "
                                      "[7:4] bin = 2^n samples"),
    (0x59, "RX_HIST_ADDR", "RW", "rx", "[9:0] the bin to read"),
    (0x5A, "RX_HIST_DATA", "R", "rx", "the bin's count; the address steps on after each read (1024 bins, the last holds overflow)"),
    (0x5B, "RX_EVT_TS", "R", "rx", "FREE_CNT at the last event"),
    (0x5C, "RX_BER_CFG", "RW", "rx", "[0] check a PRBS on CMP_I (a write that sets it starts a new count; one that "
                                     "clears it keeps the count), [1] invert, [6:4] the polynomial as TX_PRBS, "
                                     "[23:8] the sampling phase (samples into each symbol), symbol length = TX_PERIOD; "
                                     "[24] the timing recovered from CMP_I's edges (ber_cdr.v: a transmitter on another "
                                     "clock), the phase then the sampling point's distance from the edge (period x SER / 2: "
                                     "mid-symbol), [28:25] the recovery's gain (2^-gain, 4 by default), [29] it tracks "
                                     "the rising edges alone and samples half RX_CDR_SKEW later (ID version 6: with "
                                     "the rising and falling edges apart, both together have a second, false lock "
                                     "between them)"),
    (0x5D, "RX_BER_BITS", "R", "rx", "bits checked"),
    (0x5E, "RX_BER_ERR", "R", "rx", "mismatches (a self-synchronising check counts each bit error three times)"),
    (0x5F, "RX_INFO", "R", "rx", "[7:0] samples a clock (SER), [15:8] fast inputs, [31:16] the clock in MHz"),
    (0x70, "RX_CDR_ERR", "R", "cdr", "the timing recovery's last edge error, signed, in 1/16 sample"),
    (0x71, "RX_CDR_SUM", "R", "cdr", "its corrections since RX_BER_CFG's write, signed, in 1/256 sample: the transmitter's "
                                     "clock against this one is -SUM / 256 / (samples elapsed)"),
    (0x72, "RX_CDR_EDGES", "R", "cdr", "CMP_I's transitions it has seen since that write"),
    (0x73, "RX_IHOLD_CFG", "RW", "cdr", "the interference hold (ihold.v): [0] on, [3:1] window 2^(3 + n) clocks, [15:8] the "
                                        "active comparator-clocks in a window that trigger, [20:16] the comparators "
                                        "{CMP_IN CMP_IP CMP_QN CMP_QP CMP_I} (reset: QP, QN, 256 clocks, 8, off); R [4] holding "
                                        "now, [31:24] the last window's count"),
    (0x74, "RX_IHOLD_HOLD", "RW", "cdr", "clocks the loop stays held after the last triggering window, and the guard after a "
                                         "release at RX_IHOLD_MAX (reset 20 ms; 1 ms before ID version 6)"),
    (0x75, "RX_IHOLD_MAX", "RW", "cdr", "the longest hold without a break, clocks (reset 5 s); a hold starts only after a quiet "
                                        "window, so a lost, beating loop is never held"),
    (0x76, "RX_IHOLD_N", "R", "cdr", "holds started since RX_CTRL[1]'s clear"),
    (0x77, "RX_IHOLD_CLK", "R", "cdr", "clocks held since then"),

    # ---- the sequencer and the counting gate: seq_gate.v -----------------------------------------------------
    (0x60, "SEQ_CTRL", "RW", "seq", "W [0] pulse: run, [1] loop, [2] pulse: stop, [10:8] steps less one, [11] enable "
                                    "(the steps own TR_A, LOOP_HOLD, TX_DIS and the TX gate while running); "
                                    "R [0] running, [10:8] the step now"),
    (0x61, "SEQ_SEL", "RW", "seq", "[2:0] the step SEQ_OUT and SEQ_DUR read and write"),
    (0x62, "SEQ_OUT", "RW", "seq", "[0] TR_A, [1] LOOP_HOLD, [2] TX_DIS, [3] TX gate, during the step"),
    (0x63, "SEQ_DUR", "RW", "seq", "the step's length in clocks (>= 1)"),
    (0x68, "GATE_CTRL", "RW", "seq", "W [0] pulse: open the gate for GATE_LEN clocks; R [0] open, [1] done"),
    (0x69, "GATE_LEN", "RW", "seq", "the gate's length in clocks"),
    (0x6A, "GATE_SEL", "RW", "seq", "[3:0] the input GATE_EDGES and GATE_HIGH read: 0 CMP_I 1 CMP_QP 2 CMP_QN 3 CMP_IP "
                                    "4 CMP_IN 5 TRIG_IN 6 CMP_I_S 7 CMP_QP_S 8 CMP_QN_S"),
    (0x6B, "GATE_EDGES", "R", "seq", "the selected input's edges (both directions) while the gate was open"),
    (0x6C, "GATE_HIGH", "R", "seq", "samples the selected input was high while the gate was open (fast inputs: SER a clock)"),
    (0x6D, "GATE_EVENTS", "R", "seq", "RX events while the gate was open"),

    # ---- the capture buffer: capture.v ----------------------------------------------------------------------
    (0x78, "CAP_CTRL", "RW", "cap", "W [0] pulse: arm, [1] pulse: trigger now, [6:4] trigger (0 none, 1 TX event, 2 RX event, "
                                    "3 TRIG_IN rising, 4 any fast comparator change, 5 RX decision, 6 a sequencer step begins, 7 a reply); "
                                    "R [0] armed, [1] triggered, [2] done, [3] a whole buffer was written since the arming"),
    (0x79, "CAP_POST", "RW", "cap", "words written after the trigger (the rest of the buffer is before it)"),
    (0x7A, "CAP_ADDR", "RW", "cap", "[15:0] the word, counted from the oldest, [17:16] its 32-bit chunk (words over 32 bits: 0 the lowest)"),
    (0x7B, "CAP_DATA", "R", "cap", "the chunk; reading the last chunk of a word steps on to the next word"),
    (0x7C, "CAP_INFO", "R", "cap", "[7:0] samples a clock, [15:8] the word's width in bits, [23:16] log2 of the depth, "
                                    "[24] the ladder pins' read-back samples follow the context (4 x SER bits)"),
    (0x7D, "CAP_TRIG", "R", "cap", "[15:0] the trigger's word, counted from the oldest; [31:16] the words written since "
                                    "the arming (only the newest that many are this capture's)"),

    # ---- build information --------------------------------------------------------------------------------------
    (0x81, "RX_SHOLD_CFG", "RW", "rx3", "the signal holdover (ihold.v, LEVEL 1): [0] on, [3:1] window 2^(3 + n) clocks, [15:8] "
                                        "fewer clocks than this with a window comparator high trigger (the carrier gone), "
                                        "[20:16] the comparators {CMP_IN CMP_IP CMP_QN CMP_QP CMP_I} (reset: IP, IN, QP, QN, 256 "
                                        "clocks, 64, off); R [4] holding now, [31:24] the last window's count"),
    (0x82, "RX_SHOLD_HOLD", "RW", "rx3", "clocks the loop stays held after the carrier is back, and the guard after a release "
                                         "at RX_SHOLD_MAX (reset 1 ms)"),
    (0x83, "RX_SHOLD_MAX", "RW", "rx3", "the longest holdover without a break, clocks (reset 10 s)"),
    (0x84, "RX_SHOLD_N", "R", "rx3", "holdovers started since RX_CTRL[1]'s clear"),
    (0x85, "RX_SHOLD_CLK", "R", "rx3", "clocks held since then"),
    (0x86, "RX_CDR_SKEW", "R", "rx3", "with RX_BER_CFG[29]: CMP_I's falling edges' mean place against its rising ones, "
                                      "signed, in 1/256 sample (the comparator's duty-cycle distortion; ID version 6)"),
    (0x87, "RX_IHOLD_PERSIST", "RW", "rx3", "[15:0] busy windows in a row before an interference hold starts (0 and 1: the "
                                            "first, the reset); bursts and a near CW's chatter then pass (ID version 7); "
                                            "[19:16] the release scaled: the lesser of RX_IHOLD_HOLD and the hold's busy "
                                            "span << n plus a window (0, the reset: RX_IHOLD_HOLD; ID version 8)"),
    (0x88, "RX_LOCK_STATE", "R", "rx3", "lockmon.v (ID version 8): [1:0] the lock, 0 no carrier, 1 locked, 2 lost, 3 unsure; "
                                        "[8:2] the last look's sub-windows (of 64) with both Q windows changing; [31:16] the "
                                        "clocks CMP_I changed in it"),
    (0x89, "RX_LOCK_CFG", "RW", "rx3", "[7:0] Q busy in fewer sub-windows than this: still (reset 24), [15:8] in this many "
                                       "or more: a beat, lost (reset 48)"),
    (0x8A, "RX_LOCK_WIN", "RW", "rx3", "clocks a look (reset 10 ms; at least 1000)"),
    (0x8B, "RX_LOCK_LOSSES", "R", "rx3", "losses since reset: a look locked, the next lost or no carrier"),
    (0x8C, "RX_LOCK_SECONDS", "R", "rx3", "seconds locked since reset"),
    (0x8D, "RX_LOCK_Q", "R", "rx3", "the last look: [15:0] the clocks CMP_QP changed, [31:16] CMP_QN"),
    (0x8E, "RX_LOCK_IHIGH", "R", "rx3", "the last look: the clocks an I window (CMP_IP or CMP_IN) was high"),
    (0x8F, "LED_CTRL", "RW", "rx3", "the PYNQ-Z2's LEDs: [0] LD0-LD4 from the lock's state (reset 1), [10:1] from "
                                    "software {LD5 R G B, LD4 R G B, LD3..LD0} (LD5 always from here)"),
    (0x80, "BUILD", "R", "core", "[7:0] SER, [11:8] board (0 simulation, 1 PYNQ-Z2, 2 Icepi Zero), [12] the fast path is built, "
                                 "[13] the ladder pins are read back into the capture, [14] the reply lane reads the sampler's "
                                 "word a clock early, [15] the synchronous reply registered once more (a clock later), "
                                 "[31:16] clock in MHz"),

    # ---- the receive-to-transmit paths and the turnaround counter: turnaround.v (Prompt 36) ------------------
    (0x90, "RP_CTRL", "RW", "lat", "the synchronous reply: [0] enable (a write that sets it arms), [1] once: disarm after a reply, "
                                   "[2] re-arm on each of this board's TX events (the stimulus), [3] pulse: arm, [4] pulse: disarm, "
                                   "[5] re-arm when RX re-arms (the link quiet at its idle: any stimulus), "
                                   "[31:16] clocks the reply's point is held (0 = 1); R + [8] armed"),
    (0x91, "RP_MAP", "RW", "lat", "the reply to message k in [4k+2:4k]: on RX's valid decision of k the pins take TX_POINTS[RP_MAP[k]] "
                                  "(the composed table follows a write of RX_LUT, TX_POINTS or RP_MAP in 32 clocks)"),
    (0x92, "RP_STAT", "R", "lat", "[2:0] the last message answered, [6:4] its reply, [31:8] replies since RP_CTRL was written"),
    (0x94, "FP_CTRL", "RW", "lat", "the fast path: W [0] pulse: arm, [1] pulse: disarm, [2] timed (the ring: armed FP_TIME clocks) "
                                   "instead of one shot (disarmed FP_TIME clocks after the first change it causes), [3] arm on each "
                                   "of this board's TX events, [4] arm when RX re-arms; R [0] armed, [1] it drove the pins since "
                                   "the arming, [2] timed, [3] arm on TX, [4] arm on RX, [5] the tables loading (32 clocks after a "
                                   "write of FP_USE or FP_MAP: disarmed, an arming waits), [8] built"),
    (0x95, "FP_TIME", "RW", "lat", "clocks: after the first change (one shot) or after the arming (timed) to the disarm (>= 1)"),
    (0x96, "FP_USE", "RW", "lat", "bit v: comparator vector v drives the pins with FP_MAP[v] while armed (else the pins' register passes)"),
    (0x98, "FP_MAP0", "RW", "lat", "the fast path's points, vectors 0-7: entry v in [4v+3:4v] = {Q1 Q0 I1 I0}"),
    (0x99, "FP_MAP1", "RW", "lat", "vectors 8-15"),
    (0x9A, "FP_MAP2", "RW", "lat", "vectors 16-23"),
    (0x9B, "FP_MAP3", "RW", "lat", "vectors 24-31"),
    (0xA0, "RT_CFG", "RW", "lat", "the turnaround counter: [0] enable, [1] pulse: clear, [2] count arrivals only while the fast path "
                                  "is armed (the ring), [12:8] the comparators watched (reset 0x1F), [23:16] guard: samples of quiet "
                                  "before a change is an arrival (reset 8), [31:24] clocks after the first arrival the second "
                                  "may take (0 = no limit)"),
    (0xA1, "RT_LAST", "R", "lat", "[15:0] the last turnaround: the reference's first arrival -> its second (samples), "
                                  "[31:16] reference (RX's: this board's TX event, or TRIG_IN's rise with RX_CTRL[3]) -> first arrival"),
    (0xA2, "RT_MIN", "R", "lat", "[15:0] the least turnaround since the clear"),
    (0xA3, "RT_MAX", "R", "lat", "[15:0] the most"),
    (0xA4, "RT_SUM", "R", "lat", "the turnarounds' sum (samples), for the mean (with RT_N)"),
    (0xA5, "RT_N", "R", "lat", "turnarounds measured"),
    (0xA6, "RT_MISS", "R", "lat", "references whose second arrival did not come (a new reference first, or the window ran out)"),
    (0xA7, "RT_MARKS", "R", "lat", "arrivals since the clear (with RT_CFG[2] inside the fast path's armed window: the ring's hops)"),
    (0xA8, "RT_SPAN", "R", "lat", "samples from the first of those arrivals to the last"),
    (0xB0, "RX_UNDEC", "R", "rx4", "ID 10: events with a reference whose vector no single message makes (no decision: "
                                  "references = the confusion matrix's count + RX_UNDEC + RX_MISSED)"),
]

BLOCKS = {"regs": (0x00, 0x2F), "tx": (0x30, 0x3F), "rx": (0x40, 0x5F), "seq": (0x60, 0x6F), "cdr": (0x70, 0x77),
          "cap": (0x78, 0x7F),
          "core": (0x80, 0x80), "rx3": (0x81, 0x8F), "lat": (0x90, 0xAF),
          "rx4": (0xB0, 0xBF)}

BY_NAME = {name: addr for addr, name, *_ in REGS}


def check():
    seen = {}
    for addr, name, acc, block, _ in REGS:
        assert addr not in seen, "0x%02X twice: %s and %s" % (addr, seen[addr], name)
        seen[addr] = name
        lo, hi = BLOCKS[block]
        assert lo <= addr <= hi, "%s at 0x%02X is outside block %s" % (name, addr, block)
        assert acc in ("R", "W", "RW")
    return True


def vh():
    out = ["// regmap.vh: GENERATED by regmap.py --vh (the register map's one source of truth).  Do not edit.",
           "// 8-bit register numbers; on AXI-Lite register n is at byte offset 4 n.  Each block uses a few of them.",
           "/* verilator lint_off UNUSEDPARAM */"]
    for addr, name, *_ in REGS:
        out.append("localparam [7:0] R_%-12s = 8'h%02X;" % (name, addr))
    out.append("/* verilator lint_on UNUSEDPARAM */")
    return "\n".join(out) + "\n"


def md():
    out = ["| addr | name | R/W | bits |", "|---|---|---|---|"]
    for addr, name, acc, block, text in REGS:
        out.append("| 0x%02X | %s | %s | %s |" % (addr, name, acc, text.replace("|", "/")))
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    check()
    if "--vh" in sys.argv:
        open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "regmap.vh"), "w").write(vh())
        print("regmap.vh: %d registers" % len(REGS))
    elif "--md" in sys.argv:
        sys.stdout.write(md())
    else:
        print("regmap: %d registers, no clashes" % len(REGS))
