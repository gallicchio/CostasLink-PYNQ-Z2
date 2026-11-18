// cmp_monitor: the receiver's comparator inputs brought into the clock domain, counted and
// time-stamped, and the two trigger outputs.
//
// Board signals read: CMP_I (header 18, the data: sign(I)), CMP_QP / CMP_QN (10 / 8, the Q window),
// the slow path's CMP_I_S / CMP_QP_S / CMP_QN_S (33 / 40 / 37), TRIG_IN (26, the detector pulse
// through the Schmitt buffer), MUX_TX / MUX_RX (36 / 38, the synthesizers' lock detect).
// Board signals driven: TRIG_A (29): a pulse when the transmitted symbol changes; TRIG_B (31): a
// pulse when CMP_I has an edge (every edge, or rising edges only).  Both go to U.FL through buffers.
//
// Everything here is sampled at the fabric clock (8 ns on the PYNQ-Z2, 20 ns on the Icepi Zero):
// enough for BRINGUP.md stages 1-3.  The 400+ MHz ISERDES / GDDRX2 sampling and the event decoder of
// PLAN.md section 8 come later and sit beside this, not in it.
//
// Counters: a free-running clock counter; one toggle counter per comparator (both edges); the free
// counter's value at the last CMP_I edge; and the latency from TRIG_IN's rising edge to the next
// CMP_I edge (clocks; valid or timed out after 65535).  `clear` zeroes them all.

module cmp_monitor (
    input  wire         clk,
    input  wire         rst,
    // asynchronous pins
    input  wire         cmp_i,
    input  wire         cmp_qp,
    input  wire         cmp_qn,
    input  wire         cmp_i_s,
    input  wire         cmp_qp_s,
    input  wire         cmp_qn_s,
    input  wire         trig_in,
    input  wire         mux_tx,
    input  wire         mux_rx,
    input  wire         cmp_ip,           // the I window (sheet 7, Response 14): I_P above V_TIP
    input  wire         cmp_in,           //                                     I_N above V_TIN
    // control
    input  wire         clear,
    input  wire         sym_change,       // from tx_symbol
    input  wire [7:0]   trig_width,       // pulse width in clocks (0 behaves as 1)
    input  wire         trig_a_en,
    input  wire         trig_b_en,
    input  wire         trig_b_rise_only,
    // results
    output wire [10:0]  state,            // {cmp_in, cmp_ip, mux_rx, mux_tx, trig_in, cmp_qn_s, cmp_qp_s, cmp_i_s, cmp_qn, cmp_qp, cmp_i}
    output reg  [31:0]  free_cnt,
    output wire [255:0] edge_cnts,        // eight 32-bit toggle counters: cmp_i, cmp_qp, cmp_qn, cmp_i_s, cmp_qp_s, cmp_qn_s, cmp_ip, cmp_in
    output reg  [31:0]  cmp_i_ts,
    output reg  [17:0]  latency,          // {timeout, valid, clocks[15:0]}
    output wire         trig_a,
    output wire         trig_b
);
    // ---- synchronisers ------------------------------------------------------------------------
    wire [10:0] raw = {cmp_in, cmp_ip, mux_rx, mux_tx, trig_in, cmp_qn_s, cmp_qp_s, cmp_i_s, cmp_qn, cmp_qp, cmp_i};
    reg  [10:0] s1, s2;
    /* verilator lint_off UNUSEDSIGNAL */
    reg  [10:0] s3;                       // the lock-detect bits [8:7] need no edge detection
    /* verilator lint_on UNUSEDSIGNAL */
    always @(posedge clk) begin
        s1 <= raw;
        s2 <= s1;
        s3 <= s2;
    end
    assign state = s2;
    wire       rose_cmp_i = s2[0] & ~s3[0];
    wire       rose_trig  = s2[6] & ~s3[6];

    // ---- counters -----------------------------------------------------------------------------
    // the false-event counters (PLAN.md section 18): every comparator's toggles, counted while the link idles
    reg [31:0] ecnt [0:7];
    wire [7:0] counted = {s2[10:9] ^ s3[10:9], s2[5:0] ^ s3[5:0]};    // the six comparators, then the I window
    integer k;
    always @(posedge clk) begin
        if (rst || clear) begin
            free_cnt <= 32'd0;
            for (k = 0; k < 8; k = k + 1) ecnt[k] <= 32'd0;
        end else begin
            free_cnt <= free_cnt + 1'b1;
            for (k = 0; k < 8; k = k + 1)
                if (counted[k]) ecnt[k] <= ecnt[k] + 1'b1;
        end
    end
    assign edge_cnts = {ecnt[7], ecnt[6], ecnt[5], ecnt[4], ecnt[3], ecnt[2], ecnt[1], ecnt[0]};

    // ---- CMP_I time stamp and the TRIG_IN -> CMP_I latency ------------------------------------
    reg        lat_run;
    reg [15:0] lat_cnt;
    always @(posedge clk) begin
        if (rst || clear) begin
            cmp_i_ts <= 32'd0;
            latency  <= 18'd0;
            lat_run  <= 1'b0;
            lat_cnt  <= 16'd0;
        end else begin
            if (counted[0]) cmp_i_ts <= free_cnt;
            if (rose_trig) begin                        // TRIG_IN rose: start (restarts a stale one)
                lat_run <= 1'b1;
                lat_cnt <= 16'd0;
                latency <= 18'd0;
            end else if (lat_run) begin
                if (counted[0]) begin
                    latency <= {1'b0, 1'b1, lat_cnt};
                    lat_run <= 1'b0;
                end else if (lat_cnt == 16'hFFFF) begin
                    latency <= {1'b1, 1'b0, lat_cnt};
                    lat_run <= 1'b0;
                end else begin
                    lat_cnt <= lat_cnt + 1'b1;
                end
            end
        end
    end

    // ---- the trigger pulses -------------------------------------------------------------------
    wire b_event = trig_b_rise_only ? rose_cmp_i : counted[0];
    reg [7:0] a_cnt, b_cnt;
    always @(posedge clk) begin
        if (rst) begin
            a_cnt <= 8'd0;
            b_cnt <= 8'd0;
        end else begin
            if (trig_a_en && sym_change) a_cnt <= (trig_width == 8'd0) ? 8'd1 : trig_width;
            else if (a_cnt != 8'd0)      a_cnt <= a_cnt - 1'b1;
            if (trig_b_en && b_event)    b_cnt <= (trig_width == 8'd0) ? 8'd1 : trig_width;
            else if (b_cnt != 8'd0)      b_cnt <= b_cnt - 1'b1;
        end
    end
    assign trig_a = (a_cnt != 8'd0);
    assign trig_b = (b_cnt != 8'd0);
endmodule
