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
`timescale 1ns/1ps
module tb_engines;
`include "regmap.vh"
    localparam integer SER = 4;
    localparam integer LAT = 13;          // samples, pins -> fast comparators
    localparam integer LAT_SLOW = 40;     // samples, pins -> slow comparators

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

    costaslink_core #(.CLK_HZ(100_000_000), .SER(SER), .CAP_AW(10), .BOARD(0), .ID_INTERVAL_S(600)) dut (
        .clk(clk), .rst(rst),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata),
        .fs(fs), .cmp_i_s(slow[0]), .cmp_qp_s(slow[1]), .cmp_qn_s(slow[2]), .mux_tx(1'b1), .mux_rx(1'b1),
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

    initial begin
        for (k = 0; k < 256; k = k + 1) hist_pt[k] = P_IDLE;
        for (k = 0; k < SER; k = k + 1) trig_samp[k] = 1'b0;
        fs = {SER{6'b001001}}; slow = 3'b001;
        repeat (5) @(posedge clk);
        rst = 1'b0;
        repeat (5) @(posedge clk);

        // ---- identification ----
        rd(R_ID, v); expect("ID", v, 32'h434C0002);
        rd(R_BUILD, v); expect("BUILD", v, {16'd100, 4'd0, 4'd0, 8'd4});
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
        rd(R_CAP_INFO, v); expect("capture info", v, {8'd0, 8'd10, 8'd40, 8'd4});
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
        wr(R_TX_GO, 32'd2); wr(R_RX_BER_CFG, 32'd0);

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

        if (errors == 0) $display("PASS: tb_engines");
        else $display("FAIL: tb_engines, %0d errors", errors);
        $finish;
    end
endmodule
