// seq_gate: the T/R sequencer and the counting gate (Response 15; registers 0x60-0x6D).
//
// THE SEQUENCER: up to eight steps, each a length in clocks and four outputs {TX gate, TX_DIS,
// LOOP_HOLD, TR_A}.  While SEQ_CTRL[11] is set and the sequence runs, the steps own those pins
// (costaslink_core.v gives them CTRL's values otherwise) and the TX gate lets tx_engine's events out
// (TX_MODE[12]).  Once, or looping.  It serves:
//   * the hold (BRINGUP stage 3.8): LOOP_HOLD high for 1, 10, 100 ms, then low, the loop's recovery
//     watched on VC MON and in the capture buffer;
//   * one antenna by time division (stage 4.4): receive (TR_A high, the loop closed), then hold the loop
//     and transmit (TR_A low, LOOP_HOLD high, TX_DIS low, the TX gate open), then back, with the
//     switch's 30 ns and the loop's settling as the steps' lengths;
//   * a carrier keyed on and off for the spectrum analyser.
//
// THE GATE: GATE_CTRL[0] opens it for GATE_LEN clocks.  Meanwhile it counts, for each of the nine
// comparator inputs, the edges (both directions, between consecutive samples) and the samples it was
// high (fast inputs SER a clock, slow ones one).  Those two numbers set every threshold by counting
// (stage 3.7: the false-event rate of each window comparator against its DAC code) and null the slow
// stages' offsets (I_OFF / Q_OFF until the slow comparator is high half the time with no carrier).
// It counts the receiver's events too.

module seq_gate #(
    parameter integer SER = 8
) (
    input  wire             clk,
    input  wire             rst,
    input  wire [7:0]       bus_addr,
    input  wire [31:0]      bus_wdata,
    input  wire             bus_we,
    output reg  [31:0]      bus_rdata,
    input  wire [6*SER-1:0] fs,
    input  wire [2:0]       slow,               // {CMP_QN_S, CMP_QP_S, CMP_I_S}, synchronised
    input  wire             rx_event,
    output reg              seq_active,
    output reg  [3:0]       seq_out,            // {TX gate, TX_DIS, LOOP_HOLD, TR_A}
    output reg              seq_step            // one clock: a step's outputs begin (with seq_out)
);
`include "regmap.vh"
    // ---- the sequencer ------------------------------------------------------------------------------
    reg [3:0]  outs [0:7];
    reg [31:0] durs [0:7];
    reg [2:0]  sel, nsteps_m1, step, step_d;
    reg        run_d;
    reg        enable, loop, running;
    reg [31:0] cnt;
    integer    k;

    // registered (both alike, a clock after the step): the step's table lookup and the TX gate's logic
    // downstream are a clock each (the Icepi's 100 MHz)
    always @(posedge clk) begin
        seq_active <= enable && running && !rst;
        seq_out    <= outs[step];
        step_d     <= step;
        run_d      <= running;
        seq_step   <= running && !rst && (!run_d || step != step_d);
    end
    wire [3:0]  out_sel = outs[sel];
    wire [31:0] dur_sel = durs[sel];

    // ---- the gate -----------------------------------------------------------------------------------
    reg        g_open, g_done;
    reg [31:0] g_len, g_left;
    reg [3:0]  g_sel;
    reg [31:0] g_edges [0:8];
    reg [31:0] g_high  [0:8];
    reg [31:0] g_events;
    reg [5:0]  fprev;
    reg [2:0]  sprev;

    // per fast input: edges and high samples this clock (input j in [4j+3:4j])
    reg [23:0] f_edges, f_high;
    integer    s, j;
    reg        pb;
    always @* begin
        f_edges = 24'd0; f_high = 24'd0;
        for (j = 0; j < 6; j = j + 1) begin
            for (s = 0; s < SER; s = s + 1) begin
                if (s == 0) pb = fprev[j];
                else        pb = fs[6*s - 6 + j];
                if (fs[6*s + j] != pb) f_edges[4*j +: 4] = f_edges[4*j +: 4] + 4'd1;
                if (fs[6*s + j])       f_high[4*j +: 4]  = f_high[4*j +: 4] + 4'd1;
            end
        end
    end

    always @(posedge clk) begin
        if (rst) begin
            for (k = 0; k < 8; k = k + 1) begin
                outs[k] <= 4'b1111;                 // TR_A, LOOP_HOLD, TX_DIS high (safe), gate open
                durs[k] <= 32'd1000;
            end
            for (k = 0; k < 9; k = k + 1) begin g_edges[k] <= 32'd0; g_high[k] <= 32'd0; end
            sel <= 3'd0; nsteps_m1 <= 3'd0; step <= 3'd0; enable <= 1'b0; loop <= 1'b0; running <= 1'b0; cnt <= 32'd0;
            g_open <= 1'b0; g_done <= 1'b0; g_len <= 32'd100_000; g_left <= 32'd0; g_sel <= 4'd0; g_events <= 32'd0;
            fprev <= 6'd0; sprev <= 3'd0;
        end else begin
            fprev <= fs[6*(SER-1) +: 6];
            sprev <= slow;
            // the steps
            if (running) begin
                if (|cnt[31:1]) cnt <= cnt - 1'b1;
                else if (step == nsteps_m1) begin
                    if (loop) begin step <= 3'd0; cnt <= durs[0]; end
                    else running <= 1'b0;
                end else begin
                    step <= step + 1'b1; cnt <= durs[step + 1'b1];
                end
            end
            // the gate
            if (g_open) begin
                for (k = 0; k < 6; k = k + 1) begin
                    g_edges[k] <= g_edges[k] + {28'd0, f_edges[4*k +: 4]};
                    g_high[k]  <= g_high[k] + {28'd0, f_high[4*k +: 4]};
                end
                for (k = 0; k < 3; k = k + 1) begin
                    g_edges[6 + k] <= g_edges[6 + k] + {31'd0, slow[k] != sprev[k]};
                    g_high[6 + k]  <= g_high[6 + k] + {31'd0, slow[k]};
                end
                if (rx_event) g_events <= g_events + 1'b1;
                if (~|g_left[31:1]) begin g_open <= 1'b0; g_done <= 1'b1; end
                else g_left <= g_left - 1'b1;
            end
            // the bus last: a write wins over the steps and the gate in its clock
            if (bus_we) begin
                case (bus_addr)
                R_SEQ_CTRL: begin
                    loop <= bus_wdata[1]; nsteps_m1 <= bus_wdata[10:8]; enable <= bus_wdata[11];
                    if (bus_wdata[2]) running <= 1'b0;
                    else if (bus_wdata[0]) begin running <= 1'b1; step <= 3'd0; cnt <= durs[0]; end
                end
                R_SEQ_SEL:  sel <= bus_wdata[2:0];
                R_SEQ_OUT:  outs[sel] <= bus_wdata[3:0];
                R_SEQ_DUR:  durs[sel] <= (bus_wdata == 32'd0) ? 32'd1 : bus_wdata;
                R_GATE_CTRL: if (bus_wdata[0]) begin
                    g_open <= 1'b1; g_done <= 1'b0; g_left <= g_len; g_events <= 32'd0;
                    for (k = 0; k < 9; k = k + 1) begin g_edges[k] <= 32'd0; g_high[k] <= 32'd0; end
                end
                R_GATE_LEN: g_len <= bus_wdata;
                R_GATE_SEL: g_sel <= bus_wdata[3:0];
                default: ;
                endcase
            end
        end
    end

    // GATE_SEL's order: 0 CMP_I, 1 CMP_QP, 2 CMP_QN, 3 CMP_IP, 4 CMP_IN, 5 TRIG_IN (the fast vector's), 6-8 slow
    wire [3:0]  gs = (g_sel > 4'd8) ? 4'd8 : g_sel;
    wire [31:0] edges_sel = g_edges[gs];
    wire [31:0] high_sel  = g_high[gs];
    always @* begin
        case (bus_addr)
        R_SEQ_CTRL:    bus_rdata = {20'd0, enable, step, 7'd0, running};
        R_SEQ_SEL:     bus_rdata = {29'd0, sel};
        R_SEQ_OUT:     bus_rdata = {28'd0, out_sel};
        R_SEQ_DUR:     bus_rdata = dur_sel;
        R_GATE_CTRL:   bus_rdata = {30'd0, g_done, g_open};
        R_GATE_LEN:    bus_rdata = g_len;
        R_GATE_SEL:    bus_rdata = {28'd0, g_sel};
        R_GATE_EDGES:  bus_rdata = edges_sel;
        R_GATE_HIGH:   bus_rdata = high_sel;
        R_GATE_EVENTS: bus_rdata = g_events;
        default:       bus_rdata = 32'hDEAD_0000 | {24'd0, bus_addr};
        endcase
    end
endmodule
