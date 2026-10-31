// tb_engines: the experiment engines of costaslink_core.v against a loopback model (Response 15).
//
//     make sim-engines      (Icarus; ends with PASS)
//
// The model: the ladder point on the pins comes back on the five fast comparators LAT samples later
// (CMP_I = I > 0; CMP_IP / CMP_IN = I at +a / -a; CMP_QP / CMP_QN = Q at +a / -a), and on the three slow
// ones LAT_SLOW samples later (CMP_I_S = I > 0, CMP_QP_S = Q > 0, CMP_QN_S = Q < 0), as a link that works
// would.  The bus is driven directly (the bridges have their own tests: tb_costaslink.v for the UART).
// SER = 4 samples a clock at 100 MHz.  Checked: events, decisions and the confusion matrix (the settled
// vector and the first-fired set), the latency to the sample (min = max = LAT + delay) and the histogram,
// false and missed events, confirm and veto, the capture buffer, the sequencer, the gate's counts, TX
// events on TRIG_IN with TRIG_IN as the reference, and a PRBS through the loop with errors injected.
// The core as the PYNQ-Z2 has it otherwise (Prompt 36): the reply lane early, the fast path, the ladder
// pins read back into the capture; then the synchronous reply (first-edge and settled decisions, once per
// stimulus, the composed table's latency to the sample), the fast path one shot and as a ring, and the
// turnaround counter on each.
`timescale 1ns/1ps
module tb_engines;
`include "regmap.vh"
    localparam integer SER = 4;
    localparam integer LAT = 13;          // samples, pins -> fast comparators
    localparam integer LAT_SLOW = 40;     // samples, pins -> slow comparators
    parameter  integer RP_REG = 0;        // the core's: 0 the PYNQ-Z2's reply lane, 1 the Icepi's (a clock later)

    reg clk = 1'b0;
    always #5 clk = ~clk;                  // 100 MHz
    reg rst = 1'b1;

    reg  [7:0]  bus_addr = 8'd0;
    reg  [31:0] bus_wdata = 32'd0;
    reg         bus_we = 1'b0, bus_re = 1'b0;
    wire [31:0] bus_rdata;

    wire tx_i1, tx_i0, tx_q1, tx_q1_hiz, tx_q0, spi_sclk, spi_sdata, le_pll_tx, le_pll_rx, le_dsa;
    wire loop_hold, loop_sel, tx_dis, trig_a, trig_b, tr_a, scl_o, sda_o;

    integer lat = LAT, lat_slow = LAT_SLOW;
`include "tb_loopback.vh"

    costaslink_core #(.CLK_HZ(100_000_000), .SER(SER), .CAP_AW(10), .BOARD(0), .ID_INTERVAL_S(600),
                      .EARLY(1), .FAST_PATH(1), .TXFB(1), .RP_REG(RP_REG)) dut (
        .clk(clk), .rst(rst),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata),
        .fs(fs), .fs_lane(fs_early), .cmp_async(cmp_async), .fs_tx(fs_tx), .cmp_i_s(slow[0]), .cmp_qp_s(slow[1]), .cmp_qn_s(slow[2]), .mux_tx(1'b1), .mux_rx(1'b1),
        .i2c_scl_i(scl_o), .i2c_sda_i(sda_o), .i2c_scl_o(scl_o), .i2c_sda_o(sda_o),
        .tx_i1(tx_i1), .tx_i0(tx_i0), .tx_q1(tx_q1), .tx_q1_hiz(tx_q1_hiz), .tx_q0(tx_q0),
        .spi_sclk(spi_sclk), .spi_sdata(spi_sdata), .le_pll_tx(le_pll_tx), .le_pll_rx(le_pll_rx), .le_dsa(le_dsa),
        .loop_hold(loop_hold), .loop_sel(loop_sel), .tx_dis(tx_dis), .trig_a(trig_a), .trig_b(trig_b), .tr_a(tr_a));

    // ---- the bus ------------------------------------------------------------------------------------------
    task wr;
        input [7:0] a;
        input [31:0] d;
        begin
            @(negedge clk); bus_addr = a; bus_wdata = d; bus_we = 1'b1;
            @(negedge clk); bus_we = 1'b0;
        end
    endtask
    task rd;
        input  [7:0] a;
        output [31:0] d;
        begin
            @(negedge clk); bus_addr = a; bus_re = 1'b1;
            @(negedge clk); bus_re = 1'b0;
            @(negedge clk);
            @(negedge clk); d = bus_rdata;                  // the core's last read register, as axil_bridge.v
            @(negedge clk);
        end
    endtask
    integer errors = 0;
    task expect;
        input [8*24-1:0] what;
        input [31:0] got, want;
        begin
            if (got !== want) begin
                $display("FAIL %0s: got %0d (0x%08x), want %0d (0x%08x)", what, got, got, want, want);
                errors = errors + 1;
            end
        end
    endtask
    task idle_clocks;
        input integer n;
        begin
            repeat (n) @(posedge clk);
        end
    endtask

    // the scheme: idle (I +a, Q 0) and the four corners as messages 0-3
    localparam [3:0] P_IDLE = 4'b0111, P0 = 4'b1111, P1 = 4'b0011, P2 = 4'b1100, P3 = 4'b0000;
    localparam [4:0] V_IDLE = 5'b01001;
    // the settled vectors and the first-fired sets of the four corners
    localparam [4:0] V0 = 5'b01011, V1 = 5'b01101, V2 = 5'b10010, V3 = 5'b10100;
    localparam [4:0] F0 = V0 ^ V_IDLE, F1 = V1 ^ V_IDLE, F2 = V2 ^ V_IDLE, F3 = V3 ^ V_IDLE;

    reg [127:0] lut;
    task set_lut;
        input [4:0] a, b, c, d;
        begin
            lut = 128'd0;
            lut[{a, 2'b00} +: 4] = 4'b1000;
            lut[{b, 2'b00} +: 4] = 4'b1001;
            lut[{c, 2'b00} +: 4] = 4'b1010;
            lut[{d, 2'b00} +: 4] = 4'b1011;
            wr(R_RX_LUT0, lut[31:0]); wr(R_RX_LUT1, lut[63:32]); wr(R_RX_LUT2, lut[95:64]); wr(R_RX_LUT3, lut[127:96]);
        end
    endtask

    reg [31:0] v, v2;
    integer    n, i, j, bin, sumcm;

    // the pins' changes, sample by sample (the model's samples), for the reply tests
    reg        log_on = 1'b0;
    integer    n_log = 0;
    integer    log_t [0:63];
    reg  [3:0] log_p [0:63];
    reg  [3:0] log_last = 4'b0111;
    always @(sample_ev) begin
        if (log_on && pins != log_last && n_log < 64) begin log_t[n_log] = samp; log_p[n_log] = pins; n_log = n_log + 1; end
        log_last = pins;
    end
    // the reply's samples after the comparators' change: the lane takes the word the change is in (EARLY)
    // and the point is on the pins at the next edge, so SER - (LAT mod SER) in this model; a settled
    // decision whose sample is two words on waits a clock more
    localparam integer RP_LAT = (LAT / SER + 1) * SER - LAT + ((RP_REG != 0) ? SER : 0);
    reg [127:0] fpm;
    reg [31:0]  fpu;
    task check_pairs;               // each stimulus P[k] at 4c, its answer P[k+1] `d` samples later
        input integer d;
        input integer nstim;
        integer a, b, found;
        begin
            found = 0;
            for (a = 0; a + 1 < n_log; a = a + 1)
                if (log_p[a] != P_IDLE) begin
                    for (b = 0; b < 4; b = b + 1)
                        if (log_p[a] == pt_of(b) && log_p[a + 1] == pt_of((b + 1) % 4) && log_t[a + 1] - log_t[a] == d)
                            found = found + 1;
                end
            expect("stimulus -> reply pairs in the pins' log", found, nstim);
        end
    endtask
    function [3:0] pt_of;
        input integer k;
        begin
            pt_of = (k == 0) ? P0 : (k == 1) ? P1 : (k == 2) ? P2 : P3;
        end
    endfunction

    initial begin
        for (k = 0; k < 256; k = k + 1) hist_pt[k] = P_IDLE;
        for (k = 0; k < SER; k = k + 1) trig_samp[k] = 1'b0;
        fs = {SER{6'b001001}}; fs_early = {SER{6'b001001}}; fs_tx = {SER{4'b0111}}; cmp_async = 5'b01001;
        slow = 3'b001;
        repeat (5) @(posedge clk);
        rst = 1'b0;
        repeat (5) @(posedge clk);

        // ---- identification ----
        rd(R_ID, v); expect("ID", v, 32'h434C0005);
        rd(R_BUILD, v); expect("BUILD", v, {16'd100, RP_REG != 0, 3'b111, 4'd0, 8'd4});   // early lane, read-back, fast path
        rd(R_RX_INFO, v); expect("RX_INFO", v, {16'd100, 8'd6, 8'd4});

        // ---- events: the four corners, counted 0..3, 40 of them; the settled vector 2 samples in ----
        wr(R_TX_IDLE, {28'd0, P_IDLE});
        wr(R_TX_POINTS, {16'd0, P3, P2, P1, P0});
        wr(R_TX_MODE, {21'd0, 3'd3, 2'd0, 2'd1, 1'b0, 3'd1});       // N = 4, source = count, mode 1
        wr(R_TX_PERIOD, 32'd60); wr(R_TX_WIDTH, 32'd20); wr(R_TX_COUNT, 32'd40);
        set_lut(V0, V1, V2, V3);
        wr(R_RX_IDLE, {19'd0, 5'b11111, 3'd0, V_IDLE});
        wr(R_RX_TIMING, {8'd0, 8'd12, 8'd4, 8'd2});                  // confirm 12 clocks after, quiet 4, delay 2
        wr(R_RX_WINDOW, 32'd30);
        wr(R_RX_SLOW_EXP, {16'd0, 4'b1100, 4'b1010, 4'b1101, 4'b1011});
        wr(R_RX_HIST_CFG, {24'd0, 4'd0, 2'd0, 2'd1});                // ref -> decision, 1-sample bins
        wr(R_RX_CTRL, {12'd0, 1'b1, 3'd0, 11'd0, 1'b0, 1'b0, 1'b0, 1'b1, 1'b1});   // clear, enable, row = TX message
        idle_clocks(1100);                                          // the clear walks the histogram
        wr(R_TX_GO, 32'd1);
        idle_clocks(40 * 60 + 200);
        rd(R_TX_STAT, v); expect("TX events sent", v[31:8], 40);
        rd(R_RX_REFS, v); expect("RX references", v, 40);
        rd(R_RX_EVENTS, v); expect("RX events", v, 40);
        rd(R_RX_DECIDED, v); expect("RX decisions", v, 40);
        rd(R_RX_FALSE, v); expect("RX false", v, 0);
        rd(R_RX_MISSED, v); expect("RX missed", v, 0);
        rd(R_RX_CONFIRM, v); expect("RX confirmed", v, 40);
        rd(R_RX_VETO, v); expect("RX vetoed", v, 0);
        rd(R_RX_LAT_MIN, v); expect("latency min", v, LAT + 2);
        rd(R_RX_LAT_MAX, v); expect("latency max", v, LAT + 2);
        rd(R_RX_LAT_N, v); expect("latency count", v, 40);
        rd(R_RX_LAT_SUM, v); expect("latency sum", v, 40 * (LAT + 2));
        // the confusion matrix: the diagonal, ten each
        wr(R_RX_CM_ADDR, 32'd0); idle_clocks(3);
        sumcm = 0;
        for (i = 0; i < 8; i = i + 1)
            for (j = 0; j < 8; j = j + 1) begin
                rd(R_RX_CM_DATA, v);
                sumcm = sumcm + v;
                if (i < 4 && i == j) expect("CM diagonal", v, 10);
                else if (v != 0) expect("CM off-diagonal", v, 0);
            end
        expect("CM total", sumcm, 40);
        // the histogram: everything in bin LAT + 2
        wr(R_RX_HIST_ADDR, LAT + 2); idle_clocks(3);
        rd(R_RX_HIST_DATA, v); expect("histogram bin", v, 40);
        rd(R_RX_HIST_DATA, v); expect("histogram next bin", v, 0);

        // ---- first-edge decoding: the set that fired first ----
        set_lut(F0, F1, F2, F3);
        wr(R_RX_TIMING, {8'd0, 8'd12, 8'd4, 8'd0});
        wr(R_RX_CTRL, {12'd0, 1'b1, 3'd0, 11'd0, 1'b0, 1'b0, 1'b1, 1'b1, 1'b1});
        idle_clocks(1100);
        wr(R_TX_GO, 32'd1);
        idle_clocks(40 * 60 + 200);
        rd(R_RX_DECIDED, v); expect("first-fired decisions", v, 40);
        rd(R_RX_LAT_MIN, v); expect("first-fired latency", v, LAT);
        rd(R_RX_LAST, v); expect("RX_LAST message", v[2:0], 3); expect("RX_LAST valid", v[3], 1);

        // ---- veto: expect the wrong slow pattern for message 0 ----
        set_lut(V0, V1, V2, V3);
        wr(R_RX_TIMING, {8'd0, 8'd12, 8'd4, 8'd2});
        wr(R_RX_SLOW_EXP, {16'd0, 4'b1100, 4'b1010, 4'b1101, 4'b1100});
        wr(R_RX_CTRL, {12'd0, 1'b1, 3'd0, 11'd0, 1'b0, 1'b0, 1'b0, 1'b1, 1'b1});
        idle_clocks(100);
        wr(R_TX_GO, 32'd1);
        idle_clocks(40 * 60 + 200);
        rd(R_RX_VETO, v); expect("vetoed (message 0)", v, 10);
        rd(R_RX_CONFIRM, v); expect("confirmed (1-3)", v, 30);

        // ---- false and missed: a glitch with nothing sent; events the link drops ----
        wr(R_RX_IDLE, {19'd0, 5'b11111, 3'd0, V_IDLE});
        wr(R_RX_CTRL, {12'd0, 1'b1, 3'd0, 11'd0, 1'b0, 1'b0, 1'b0, 1'b1, 1'b1});
        idle_clocks(100);
        @(negedge clk); glitch = 1'b1; @(negedge clk); glitch = 1'b0;
        idle_clocks(50);
        rd(R_RX_FALSE, v); expect("false event", v, 1);
        mute = 1'b1;
        wr(R_TX_COUNT, 32'd5); wr(R_TX_GO, 32'd1);
        idle_clocks(5 * 60 + 100);
        mute = 1'b0;
        rd(R_RX_MISSED, v); expect("missed", v, 5);

        // ---- the capture buffer: trigger on a TX event, 64 words after ----
        wr(R_CAP_POST, 32'd64);
        wr(R_CAP_CTRL, {25'd0, 3'd1, 3'd0, 1'b1});
        idle_clocks(1100);                                          // fill the 1024-word buffer once
        wr(R_TX_COUNT, 32'd1); wr(R_TX_GO, 32'd1);
        idle_clocks(200);
        rd(R_CAP_CTRL, v); expect("capture done", v[3:0], 4'b1110);
        rd(R_CAP_TRIG, v); expect("capture trigger word", v[15:0], 1024 - 64 - 1);
        expect("capture: words since the arming", v[31:16], 1024);
        rd(R_CAP_INFO, v); expect("capture info", v, {7'd0, 1'b1, 8'd10, 8'd56, 8'd4});   // + the read-back
        // the trigger word has the TX event bit (24 + 12 = bit 36: chunk 1, bit 4); the first fast change of
        // CMP_QP comes LAT samples after the pins moved
        wr(R_CAP_ADDR, 1024 - 64 - 1); idle_clocks(3);
        rd(R_CAP_DATA, v); rd(R_CAP_DATA, v2);
        expect("capture: TX event in the trigger word", v2[4], 1);
        wr(R_CAP_ADDR, 1024 - 64 - 2); idle_clocks(3);
        rd(R_CAP_DATA, v); rd(R_CAP_DATA, v2);
        expect("capture: no TX event in the word before", v2[4], 0);
        n = -1;
        wr(R_CAP_ADDR, 1024 - 64 - 1); idle_clocks(3);
        for (i = 0; i < 8; i = i + 1) begin
            rd(R_CAP_DATA, v); rd(R_CAP_DATA, v2);
            for (s = 0; s < SER; s = s + 1)
                if (n < 0 && v[6*s + 1]) n = i * SER + s;           // CMP_QP of the first message (P0: Q +a)
        end
        expect("capture: CMP_QP rises LAT samples after the pins", n, LAT);
        // the read-back (TXFB: bits 40 + 4s + p, chunk 1 from bit 8): the pins' register's point P0 in every
        // sample of the word after the trigger's (the model reads the pins back a clock late)
        wr(R_CAP_ADDR, 1024 - 64 - 1); idle_clocks(3);
        rd(R_CAP_DATA, v); rd(R_CAP_DATA, v2);
        expect("read-back in the trigger word: the idle", v2[23:8], {SER{P_IDLE}});
        rd(R_CAP_DATA, v); rd(R_CAP_DATA, v2);
        expect("read-back a word later: P0", v2[23:8], {SER{P0}});
        expect("context: the pins' register", v2[3:0], P0);
        wr(R_CAP_ADDR, {14'd0, 2'd1, 16'd960}); idle_clocks(3);       // start at chunk 1
        rd(R_CAP_ADDR, v); expect("CAP_ADDR chunk", v[17:16], 1);
        rd(R_CAP_DATA, v2); rd(R_CAP_ADDR, v); expect("chunk 1 is a word's last: the next word", v, 961);

        // ---- the sequencer: TR_A low for 50 clocks, then high, looping off ----
        wr(R_SEQ_SEL, 0); wr(R_SEQ_OUT, 4'b1110); wr(R_SEQ_DUR, 50);
        wr(R_SEQ_SEL, 1); wr(R_SEQ_OUT, 4'b1111); wr(R_SEQ_DUR, 30);
        wr(R_SEQ_CTRL, {20'd0, 1'b1, 3'd1, 7'd0, 1'b1});
        n = 0;
        for (i = 0; i < 120; i = i + 1) begin @(posedge clk); if (!tr_a) n = n + 1; end
        expect("sequencer: TR_A low clocks", n, 50);
        wr(R_SEQ_CTRL, 32'd0);

        // ---- the gate: a CMP_I square wave from TX_MODE 4 (rotation of +a, -a), counted for 1000 clocks ----
        wr(R_TX_POINTS, {24'd0, 4'b0100, 4'b0111});                 // I -a, I +a
        wr(R_TX_MODE, {21'd0, 3'd1, 2'd0, 2'd0, 1'b0, 3'd4});       // N = 2, rotate
        wr(R_TX_PERIOD, 32'd10); wr(R_TX_GO, 32'd1);
        idle_clocks(50);
        wr(R_GATE_LEN, 32'd1000); wr(R_GATE_SEL, 32'd0); wr(R_GATE_CTRL, 32'd1);
        idle_clocks(1050);
        rd(R_GATE_CTRL, v); expect("gate done", v[1:0], 2'b10);
        rd(R_GATE_EDGES, v); expect("gate: CMP_I edges", v, 100);
        rd(R_GATE_HIGH, v); expect("gate: CMP_I high samples", v, 2000);
        wr(R_TX_GO, 32'd2);

        // ---- a PRBS15 BPSK through the loop: 2 clocks a symbol, sampled mid-symbol ----
        wr(R_TX_POINTS, {24'd0, 4'b0111, 4'b0100});                 // bit 0 -> I -a, bit 1 -> I +a
        wr(R_TX_MODE, {21'd0, 3'd1, 2'd0, 2'd0, 1'b0, 3'd3});
        wr(R_TX_PERIOD, 32'd2); wr(R_TX_PRBS, {23'd0, 1'b1, 5'd0, 3'd2});
        wr(R_TX_GO, 32'd1);
        wr(R_RX_BER_CFG, {8'd0, 16'd3, 1'b0, 3'd2, 2'd0, 1'b0, 1'b1});   // phase 3 samples: (LAT + 3) mod 8 = 0 ... mid
        idle_clocks(2000);
        rd(R_RX_BER_BITS, v); rd(R_RX_BER_ERR, v2);
        if (v < 900) begin $display("FAIL BER: only %0d bits checked", v); errors = errors + 1; end
        expect("BER: errors with a clean loop", v2, 0);
        // one bit flipped: a self-synchronising check counts it three times
        @(negedge clk); flip_next = 1'b1; @(negedge clk); @(negedge clk); flip_next = 1'b0;
        idle_clocks(200);
        rd(R_RX_BER_ERR, v2); expect("BER: one flipped symbol", v2, 3);
        // the same through the timing recovery (ber_cdr.v; one clock here, so it finds the phase and holds it):
        // no errors, the edges seen, the corrections no more than the first acquisition's
        wr(R_RX_BER_CFG, {3'd0, 4'd4, 1'b1, 16'd4, 1'b0, 3'd2, 2'd0, 1'b0, 1'b1});
        idle_clocks(2000);
        rd(R_RX_BER_BITS, v); rd(R_RX_BER_ERR, v2);
        if (v < 900) begin $display("FAIL BER (timing recovered): only %0d bits checked", v); errors = errors + 1; end
        expect("BER (timing recovered)", v2, 0);
        rd(R_RX_CDR_EDGES, v);
        if (v < 400) begin $display("FAIL CDR: only %0d edges", v); errors = errors + 1; end
        rd(R_RX_CDR_SUM, v);
        if ($signed(v) > 2048 || $signed(v) < -2048) begin
            $display("FAIL CDR: corrections %0d / 256 samples with one clock", $signed(v)); errors = errors + 1;
        end
        rd(R_RX_BER_CFG, v); expect("RX_BER_CFG read back", v, {3'd0, 4'd4, 1'b1, 16'd4, 1'b0, 3'd2, 2'd0, 1'b0, 1'b1});
        wr(R_TX_GO, 32'd2); wr(R_RX_BER_CFG, 32'd0);

        // ---- the interference hold (ihold.v): the loop released by CTRL, the PRBS put on Q, (+1, +1) / (+1, -1), so
        //      QP and QN chatter: LOOP_HOLD comes up; the TX stopped (the idle on I), it goes down RX_IHOLD_HOLD later
        rd(R_CTRL, v2);
        wr(R_CTRL, v2 & ~32'h82);                                   // LOOP_HOLD off (and not the ID pulse)
        wr(R_RX_IHOLD_HOLD, 32'd200);
        wr(R_RX_IHOLD_CFG, {11'd0, 5'b00110, 8'd8, 3'd0, 1'b0, 3'd2, 1'b1});   // QP, QN; 32 clocks; 8; on
        idle_clocks(100);
        expect("LOOP_HOLD before the chatter", loop_hold, 0);
        wr(R_TX_POINTS, {24'd0, 4'b0011, 4'b1111});                // bit 0 -> (+1, +1), bit 1 -> (+1, -1)
        wr(R_TX_GO, 32'd1);
        idle_clocks(200);
        expect("LOOP_HOLD under the Q windows' chatter", loop_hold, 1);
        wr(R_TX_GO, 32'd2);
        idle_clocks(400);
        expect("LOOP_HOLD 400 clocks after the chatter", loop_hold, 0);
        rd(R_RX_IHOLD_N, v); expect("RX_IHOLD_N", v, 1);
        rd(R_RX_IHOLD_CLK, v);
        if (v < 200) begin $display("FAIL RX_IHOLD_CLK: %0d clocks held", v); errors = errors + 1; end
        wr(R_RX_IHOLD_CFG, 32'd0);
        // ---- the signal holdover: the idle at (0, 0), the windows all quiet (the carrier gone), holds the loop; the
        //      idle back at (+1, 0), it lets go RX_SHOLD_HOLD later
        wr(R_RX_SHOLD_HOLD, 32'd200);
        wr(R_RX_SHOLD_CFG, {11'd0, 5'b11110, 8'd8, 3'd0, 1'b0, 3'd2, 1'b1});   // IP, IN, QP, QN; 32 clocks; under 8; on
        idle_clocks(100);
        expect("LOOP_HOLD with the carrier", loop_hold, 0);
        wr(R_TX_IDLE, {28'd0, 4'b0101});                            // (0, 0): nothing on the windows
        idle_clocks(200);
        expect("LOOP_HOLD with the carrier gone", loop_hold, 1);
        wr(R_TX_IDLE, {28'd0, P_IDLE});
        idle_clocks(400);
        expect("LOOP_HOLD 400 clocks after the carrier is back", loop_hold, 0);
        rd(R_RX_SHOLD_N, v); expect("RX_SHOLD_N", v, 1);
        wr(R_RX_SHOLD_CFG, 32'd0);
        wr(R_CTRL, v2 & ~32'h80);

        // ---- events on TRIG_IN, TRIG_IN the reference: the latency from TRIG_IN's rising sample ----
        wr(R_TX_IDLE, {28'd0, P_IDLE});
        wr(R_TX_POINTS, {16'd0, P3, P2, P1, P0});
        wr(R_TX_MODE, {21'd0, 3'd3, 2'd0, 2'd0, 1'b0, 3'd2});       // fixed message 0, mode 2
        wr(R_TX_MSG, 32'd0); wr(R_TX_PERIOD, 32'd30); wr(R_TX_WIDTH, 32'd20); wr(R_TX_COUNT, 32'd0);
        wr(R_TX_GO, 32'd1);
        wr(R_RX_IDLE, {19'd0, 5'b11111, 3'd0, V_IDLE});
        wr(R_RX_TIMING, {8'd0, 8'd12, 8'd4, 8'd2});
        wr(R_RX_CTRL, {12'd0, 1'b0, 3'd0, 11'd0, 1'b0, 1'b1, 1'b0, 1'b1, 1'b1});  // reference = TRIG_IN
        idle_clocks(100);
        @(negedge clk); trig_samp[2] = 1'b1; trig_samp[3] = 1'b1;   // rises at sample 2 of this clock
        @(negedge clk); trig_samp[0] = 1'b1; trig_samp[1] = 1'b1;
        @(negedge clk); for (k = 0; k < SER; k = k + 1) trig_samp[k] = 1'b0;
        idle_clocks(100);
        rd(R_RX_LAST_LAT, v);
        // TRIG_IN rose at sample 2; the event goes out on the pins three clocks later (rx_engine's stage 1,
        // tx_engine's start, the pins' register), so the latency is (3 x SER - 2) + LAT samples
        expect("TRIG_IN -> event latency", v[15:0], 3 * SER - 2 + LAT);
        rd(R_TX_STAT, v); expect("one TRIG_IN event", v[31:8], 1);
        wr(R_TX_GO, 32'd2);

        // ---- the synchronous reply: on the decision of k the pins take TX_POINTS[RP_MAP[k]] ----------------
        // first-edge decisions; k -> k+1 mod 4; each stimulus answered once (re-armed by each TX event)
        set_lut(F0, F1, F2, F3);
        wr(R_RX_IDLE, {19'd0, 5'b11111, 3'd0, V_IDLE});
        wr(R_RX_TIMING, {8'd0, 8'd12, 8'd4, 8'd0});
        wr(R_RX_WINDOW, 32'd30);
        wr(R_RX_SLOW_EXP, 32'd0);
        wr(R_TX_IDLE, {28'd0, P_IDLE});
        wr(R_TX_POINTS, {16'd0, P3, P2, P1, P0});
        wr(R_TX_MODE, {21'd0, 3'd3, 2'd0, 2'd1, 1'b0, 3'd1});       // N = 4, count, events
        wr(R_TX_PERIOD, 32'd80); wr(R_TX_WIDTH, 32'd20); wr(R_TX_COUNT, 32'd8);
        wr(R_RP_MAP, {16'd0, 4'd0, 4'd3, 4'd2, 4'd1});              // 0 -> 1, 1 -> 2, 2 -> 3, 3 -> 0
        wr(R_RP_CTRL, {16'd30, 12'd0, 1'b0, 1'b1, 1'b1, 1'b1});      // 30 clocks; re-arm on TX; once; enable
        rd(R_RP_CTRL, v); expect("RP_CTRL armed", v[8], 1); expect("RP_CTRL width", v[31:16], 30);
        wr(R_RT_CFG, {8'd50, 8'd8, 3'd0, 5'h1F, 5'd0, 1'b0, 1'b1, 1'b1});   // window 50, guard 8, all five
        wr(R_RX_CTRL, {12'd0, 1'b1, 3'd0, 11'd0, 1'b0, 1'b0, 1'b1, 1'b1, 1'b1});   // first edge
        idle_clocks(1100);
        log_on = 1'b1; n_log = 0;
        wr(R_TX_GO, 32'd1);
        idle_clocks(8 * 80 + 200);
        log_on = 1'b0;
        rd(R_RP_STAT, v); expect("replies", v[31:8], 8);
        expect("the last message answered", v[2:0], 3); expect("its reply", v[6:4], 0);
        check_pairs(LAT + RP_LAT, 8);
        rd(R_RX_EVENTS, v); expect("RX events with replies", v, 8);
        rd(R_RX_DECIDED, v); expect("RX decisions with replies", v, 8);
        rd(R_RX_MISSED, v); expect("RX missed with replies", v, 0);
        rd(R_RX_FALSE, v); expect("RX false with replies", v, 0);
        rd(R_RT_N, v); expect("turnarounds", v, 8);
        rd(R_RT_MIN, v); expect("turnaround min: the loop + the lane", v, LAT + RP_LAT);
        rd(R_RT_MAX, v); expect("turnaround max", v, LAT + RP_LAT);
        rd(R_RT_SUM, v); expect("turnaround sum", v, 8 * (LAT + RP_LAT));
        rd(R_RT_LAST, v); expect("reference -> first arrival", v[31:16], LAT);
        rd(R_RT_MISS, v); expect("turnarounds missed", v, 0);

        // settled decisions: 2 samples after the event (in its word: the same clock), then 2 SER (its sample
        // two words on: a clock later each, SER x ((LAT mod SER + 2 SER) / SER) samples)
        set_lut(V0, V1, V2, V3);
        wr(R_RX_TIMING, {8'd0, 8'd12, 8'd4, 8'd2});
        wr(R_RX_CTRL, {12'd0, 1'b1, 3'd0, 11'd0, 1'b0, 1'b0, 1'b0, 1'b1, 1'b1});
        wr(R_RT_CFG, {8'd50, 8'd8, 3'd0, 5'h1F, 5'd0, 1'b0, 1'b1, 1'b1});
        wr(R_RP_CTRL, {16'd30, 12'd0, 1'b0, 1'b1, 1'b1, 1'b1});
        idle_clocks(100);
        log_on = 1'b1; n_log = 0;
        wr(R_TX_COUNT, 32'd4); wr(R_TX_GO, 32'd1);
        idle_clocks(4 * 80 + 200);
        log_on = 1'b0;
        check_pairs(LAT + RP_LAT, 4);
        rd(R_RT_MIN, v); expect("settled (2): turnaround", v, LAT + RP_LAT);
        rd(R_RT_MAX, v); expect("settled (2): turnaround max", v, LAT + RP_LAT);
        wr(R_RX_TIMING, {8'd0, 8'd12, 8'd4, 8'd2 * SER});
        wr(R_RT_CFG, {8'd50, 8'd8, 3'd0, 5'h1F, 5'd0, 1'b0, 1'b1, 1'b1});
        idle_clocks(100);
        log_on = 1'b1; n_log = 0;
        wr(R_TX_GO, 32'd1);
        idle_clocks(4 * 80 + 200);
        log_on = 1'b0;
        check_pairs(LAT + RP_LAT + SER * ((LAT % SER + 2 * SER) / SER), 4);
        rd(R_RT_MIN, v); expect("settled (2 SER): turnaround", v, LAT + RP_LAT + SER * ((LAT % SER + 2 * SER) / SER));
        rd(R_RX_DECIDED, v); expect("settled: RX decisions", v, 8);
        // once, not re-armed: the first stimulus only
        wr(R_RP_CTRL, {16'd30, 12'd0, 1'b0, 1'b0, 1'b1, 1'b1});
        wr(R_TX_COUNT, 32'd3); wr(R_TX_GO, 32'd1);
        idle_clocks(3 * 80 + 200);
        rd(R_RP_STAT, v); expect("once: one reply", v[31:8], 1);
        rd(R_RP_CTRL, v); expect("once: disarmed", v[8], 0);
        // once, re-armed when RX re-arms (the link quiet at its idle): every stimulus, whatever made it
        wr(R_RP_CTRL, {16'd30, 10'd0, 1'b1, 2'b00, 1'b0, 1'b1, 1'b1});
        rd(R_RP_CTRL, v); expect("RP_CTRL re-arm on RX", v[5], 1);
        wr(R_TX_COUNT, 32'd4); wr(R_TX_GO, 32'd1);
        idle_clocks(4 * 80 + 200);
        rd(R_RP_STAT, v); expect("re-armed by RX: four replies", v[31:8], 4);
        wr(R_RP_CTRL, 32'd0);

        // ---- the fast path, one shot: the corners' vectors -> the next corner, the idle passes ---------------
        fpm = 128'd0; fpu = 32'd0;
        fpu[V0] = 1'b1; fpm[{V0, 2'b00} +: 4] = P1;
        fpu[V1] = 1'b1; fpm[{V1, 2'b00} +: 4] = P2;
        fpu[V2] = 1'b1; fpm[{V2, 2'b00} +: 4] = P3;
        fpu[V3] = 1'b1; fpm[{V3, 2'b00} +: 4] = P0;
        wr(R_FP_MAP0, fpm[31:0]); wr(R_FP_MAP1, fpm[63:32]); wr(R_FP_MAP2, fpm[95:64]); wr(R_FP_MAP3, fpm[127:96]);
        wr(R_FP_USE, fpu);
        wr(R_FP_TIME, 32'd2);
        wr(R_FP_CTRL, {28'd0, 1'b1, 1'b0, 1'b0, 1'b0});               // arm on each TX event, one shot
        rd(R_FP_CTRL, v); expect("FP built", v[8], 1); expect("FP not armed yet", v[0], 0);
        wr(R_RT_CFG, {8'd50, 8'd8, 3'd0, 5'h1F, 5'd0, 1'b0, 1'b1, 1'b1});
        idle_clocks(100);
        log_on = 1'b1; n_log = 0;
        wr(R_TX_COUNT, 32'd8); wr(R_TX_GO, 32'd1);
        idle_clocks(8 * 80 + 200);
        log_on = 1'b0;
        check_pairs(LAT, 8);
        n = 0;
        for (i = 0; i + 1 < n_log; i = i + 1)
            if (log_p[i] != P_IDLE && log_t[i + 1] - log_t[i] == LAT) n = n + 1;
        expect("fast path: the answer LAT samples after the stimulus", n, 8);
        rd(R_RT_N, v); expect("fast path: turnarounds", v, 8);
        rd(R_RT_MIN, v); expect("fast path: turnaround (no delay of its own here)", v, LAT);
        rd(R_RT_MAX, v); expect("fast path: turnaround max", v, LAT);
        rd(R_FP_CTRL, v); expect("fast path: disarmed", v[0], 0); expect("fast path: it drove", v[1], 1);
        // armed now and again whenever RX re-arms, instead of on the TX event
        wr(R_FP_CTRL, {27'd0, 1'b1, 1'b0, 1'b0, 1'b0, 1'b1});
        rd(R_FP_CTRL, v); expect("fast path: armed, arm on RX", v[4:0], 5'b10001);
        wr(R_RT_CFG, {8'd50, 8'd8, 3'd0, 5'h1F, 5'd0, 1'b0, 1'b1, 1'b1});
        wr(R_TX_COUNT, 32'd4); wr(R_TX_GO, 32'd1);
        idle_clocks(4 * 80 + 200);
        rd(R_RT_N, v); expect("fast path, armed by RX: turnarounds", v, 4);
        rd(R_RT_MAX, v); expect("fast path, armed by RX: turnaround", v, LAT);
        wr(R_FP_CTRL, 32'd2);

        // ---- the ring: the idle starts it, each corner -> the next, armed 200 clocks --------------------------
        fpu[V_IDLE] = 1'b1; fpm[{V_IDLE, 2'b00} +: 4] = P0;
        wr(R_FP_MAP0, fpm[31:0]); wr(R_FP_MAP1, fpm[63:32]); wr(R_FP_MAP2, fpm[95:64]); wr(R_FP_MAP3, fpm[127:96]);
        wr(R_FP_USE, fpu);
        wr(R_FP_TIME, 32'd200);
        wr(R_RT_CFG, {8'd0, 8'd8, 3'd0, 5'h1F, 5'd0, 1'b1, 1'b1, 1'b1});    // ring: arrivals while armed
        idle_clocks(20);
        wr(R_FP_CTRL, {28'd0, 1'b0, 1'b1, 1'b0, 1'b1});               // timed, arm now
        idle_clocks(260);
        rd(R_RT_MARKS, v); rd(R_RT_SPAN, v2);
        if (v < 50) begin $display("FAIL ring: only %0d hops", v); errors = errors + 1; end
        expect("ring: span = hops x LAT", v2, (v - 1) * LAT);
        expect("ring: hops in 200 clocks", v, (200 * SER - 1) / LAT);
        rd(R_FP_CTRL, v); expect("ring: disarmed", v[0], 0);
        wr(R_FP_USE, 32'd0); wr(R_FP_CTRL, 32'd0); wr(R_RT_CFG, 32'd0);

        if (errors == 0) $display("PASS: tb_engines (RP_REG %0d)", RP_REG);
        else $display("FAIL: tb_engines (RP_REG %0d), %0d errors", RP_REG, errors);
        $finish;
    end
endmodule
