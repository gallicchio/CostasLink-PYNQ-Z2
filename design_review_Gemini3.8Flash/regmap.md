| addr | name | R/W | bits |
|---|---|---|---|
| 0x00 | ID | R | 0x434C0002: 'CL', version 2 (Response 15: the experiment engines) |
| 0x01 | CTRL | RW | [0] TX_DIS (reset 1: muted; header pin 24 carries its inverse, TX_EN), [1] LOOP_HOLD (reset 1), [2] LOOP_SEL, [3] TR_A (reset 1: receive), [6] ID enable, [7] pulse: ID now, [8] TX_Q1 high-impedance (the board's TRIG IN bypass) |
| 0x02 | TXSYM | RW | [3:0] {Q1 Q0 I1 I0} ladder point in TX_MODE 0; a write pulses TRIG_A; R [7:4] the pins now |
| 0x03 | PAT_PERIOD | RW | TX_MODE 0: clocks between BPSK flips (>= 2) |
| 0x04 | PAT_WIDTH | RW | TX_MODE 0: clocks a flip lasts; 0 = toggle |
| 0x05 | PAT_CTRL | RW | TX_MODE 0: W [0] start / stop, [31:16] flips (0 = forever); R [0] running |
| 0x06 | TRIG_CFG | RW | [7:0] trigger pulse width (clocks), [8] TRIG_A on symbol change, [9] TRIG_B on CMP_I edge, [10] TRIG_B rising only, [12:11] TRIG_A source (0 symbol change, 1 TX event start), [14:13] TRIG_B source (0 CMP_I edge, 1 RX event, 2 RX decision, 3 RX valid decision) |
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
| 0x78 | CAP_CTRL | RW | W [0] pulse: arm, [1] pulse: trigger now, [6:4] trigger (0 none, 1 TX event, 2 RX event, 3 TRIG_IN rising, 4 any fast comparator change, 5 RX decision, 6 a sequencer step begins); R [0] armed, [1] triggered, [2] done, [3] a whole buffer was written since the arming |
| 0x79 | CAP_POST | RW | words written after the trigger (the rest of the buffer is before it) |
| 0x7A | CAP_ADDR | RW | [15:0] the word, counted from the oldest, [16] its high 32 bits (words over 32 bits) |
| 0x7B | CAP_DATA | R | the chunk; reading the last chunk of a word steps on to the next word |
| 0x7C | CAP_INFO | R | [7:0] samples a clock, [15:8] the word's width in bits, [23:16] log2 of the depth |
| 0x7D | CAP_TRIG | R | [15:0] the trigger's word, counted from the oldest; [31:16] the words written since the arming (only the newest that many are this capture's) |
| 0x80 | BUILD | R | [7:0] SER, [11:8] board (0 simulation, 1 PYNQ-Z2, 2 Icepi Zero), [31:16] clock in MHz |
