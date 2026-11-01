// tx_engine: what the transmitter's ladders send (Response 15; registers 0x30-0x3A, regmap.py).
//
// The ladders take a point {Q1 Q0 I1 I0} per clock (tx_symbol.v has the code: 00 = -a, 01/10 = 0, 11 = +a).
// Modes (TX_MODE[2:0]), each built to serve an experiment of BRINGUP.md and PLAN.md section 18:
//   0  the first firmware: TXSYM's point and its BPSK flip pattern (tx_symbol.v), unchanged
//   1  events: every TX_PERIOD clocks a message point for TX_WIDTH clocks, the idle point between; the
//      message from TX_MSG, a count 0..N-1, or the PRBS (TX_MODE[5:4]).  Any scheme of section 18 is a
//      choice of the idle point and the message points.  TX_COUNT events, or until stopped; TX_GO[2] sends
//      one now.  With TX_MODE[12] events only while the sequencer's TX gate is high (time division).
//   2  events on TRIG_IN: the message point goes out the clock after TRIG_IN's rising edge is seen, so the
//      FPGA path's latency can be set against the board's bypass (CTRL[8]); TX_PERIOD clocks hold-off.
//   3  PRBS symbols: every TX_PERIOD clocks the next log2(N) bits of the PRBS choose message point
//      0..N-1: N = 2 with points (-a, 0), (+a, 0) is BPSK for the BER (stage 4.3), N = 4 the corners.
//   4  rotation: points 0..N-1 in turn every TX_PERIOD clocks (backwards with TX_MODE[11]): with the four
//      quadrant points, FSK at +-1 / (4 TX_PERIOD) of the clock.
//   5  one message point, TX_MSG's, held: a constellation point for the arms' offsets and the scope.
// `tx_event` is high for the clock in which an event's point reaches the pins' registers: the time
// reference of the receiver's latency (rx_engine.v, RX_CTRL[3] clear).  A synchronous reply
// (turnaround.v, `ovr_en`) takes the pins' register over for its clocks in any mode; it is not an event.

module tx_engine (
    input  wire        clk,
    input  wire        rst,
    // the register bus (this block answers 0x30-0x3F)
    input  wire [7:0]  bus_addr,
    input  wire [31:0] bus_wdata,
    input  wire        bus_we,
    output reg  [31:0] bus_rdata,
    // the first firmware's TXSYM and pattern (from costaslink_regs.v)
    input  wire        sym_we,
    input  wire [3:0]  sym_wdata,
    input  wire [31:0] pat_period,
    input  wire [31:0] pat_width,
    input  wire [15:0] pat_count,
    input  wire        pat_start,
    input  wire        pat_stop,
    output wire        pat_running,
    // time, triggers, gate
    input  wire [31:0] free_cnt,
    input  wire        trig_in_rise,      // one clock, at TRIG_IN's rising edge (fast sampler)
    input  wire        seq_gate,          // the sequencer's TX gate (seq_gate.v)
    // the synchronous reply (turnaround.v): its point into the pins' register instead, ahead of every mode
    input  wire        ovr_en,
    input  wire [3:0]  ovr_pt,
    output wire [31:0] points_o,          // TX_POINTS, for the reply's table
    // the ladders and what happened
    output reg  [1:0]  tx_i,
    output reg  [1:0]  tx_q,
    output wire        sym_change,        // the four pins changed this clock
    output reg         tx_event,          // an event's point is on the pins from this clock
    output reg  [2:0]  tx_msg,            // the message of the last event (or PRBS / rotation symbol)
    output reg         tx_busy            // an event's point is out
);
`include "regmap.vh"
    // ---- registers ---------------------------------------------------------------------------------
    reg [2:0]  mode;
    reg [1:0]  src;
    reg [2:0]  nm1;                       // messages less one
    reg        rot_back, gated;
    reg [3:0]  idle;
    reg [31:0] points;
    reg [2:0]  msg_fixed;
    reg [31:0] period, width, count;
    reg [2:0]  poly;
    reg [31:0] evt_ts;
    reg        running, forever_;
    reg [31:0] left, pcnt, wcnt;
    reg [23:0] sent;
    reg [2:0]  rot_idx, ctr;
    reg        go_start, go_stop, go_one, reseed;
    reg        ev_int;                    // an event's point chosen this clock: on the pins the next

    // ---- the first firmware's pattern, mode 0 ---------------------------------------------------------
    wire [1:0] l_i, l_q;
    /* verilator lint_off UNUSEDSIGNAL */
    wire       l_change;                   // the pins' own register below finds every change, in every mode
    /* verilator lint_on UNUSEDSIGNAL */
    tx_symbol u_legacy (
        .clk(clk), .rst(rst), .sym_we(sym_we), .sym_wdata(sym_wdata),
        .period(pat_period), .width(pat_width), .count(pat_count), .pat_start(pat_start), .pat_stop(pat_stop),
        .tx_i(l_i), .tx_q(l_q), .sym_change(l_change), .running(pat_running));

    // ---- the PRBS: up to three bits a clock (prbs_multi: five fixed-tap registers) ----------------------
    reg  [1:0] adv;
    wire [2:0] rnd3;
    prbs_multi u_prbs (.clk(clk), .rst(rst), .reseed(reseed), .adv(adv), .poly(poly), .bits(rnd3));

    // bits a PRBS symbol takes: N 2 -> 1, 3-4 -> 2, 5-8 -> 3 (N = 1: none)
    wire [1:0] kbits = (nm1 == 3'd0) ? 2'd0 : (nm1 == 3'd1) ? 2'd1 : (nm1 <= 3'd3) ? 2'd2 : 2'd3;

    // a number 0..7 reduced modulo N (N = nm1 + 1)
    function [2:0] modn;
        input [2:0] r;
        input [2:0] m1;
        reg [3:0] n;
        begin
            n = {1'b0, m1} + 4'd1;
            if ({1'b0, r} < n) modn = r;
            else if ({1'b0, r} - n < n) modn = r - n[2:0];
            else modn = r - n[2:0] - n[2:0];
        end
    endfunction

    function [3:0] pt;
        input [31:0] p;
        input [2:0]  k;
        begin
            pt = p[{k, 2'b00} +: 4];
        end
    endfunction

    // the random message: only the bits a message takes (as the PRBS symbols below), so the two subtractions of modn
    // always reach 0..N-1 (unmasked, N = 2 sent messages 2 and 3 a quarter of the time: REVB 22, ID version 9)
    wire [2:0] next_msg = (src == 2'd0) ? msg_fixed :
                          (src == 2'd1) ? ctr :
                          modn(rnd3 & ((3'd1 << kbits) - 3'd1), nm1);

    // ---- the engine -------------------------------------------------------------------------------------
    // what modes 1-5 put out: the idle point or message p_msg's point, looked up in the pins' stage (the
    // lookup behind the PRBS and the modulo-N closed the Icepi at 87 MHz in the drawing clock)
    reg        p_idle;
    reg  [2:0] p_msg;
    wire [3:0] point = p_idle ? idle : pt(points, p_msg);
    reg  [31:0] hold;                      // mode 2 hold-off
    // pcnt == 0 and hold == 0 as registers, kept with the counters: the 32-bit zero tests sat at the head
    // of the event's path into the PRBS (the Icepi closed at 93 MHz with them there)
    reg         pz, hz;
    wire gate_ok = !gated || seq_gate;

    // the PRBS bits taken this clock: three for a random message, log2(N) for a PRBS symbol
    wire ev_go  = go_one || (mode == 3'd1 && running && pz && gate_ok) ||
                  (mode == 3'd2 && running && trig_in_rise && hz && gate_ok);
    wire sym_go = (mode == 3'd3) && running && !go_start && pz;
    always @* begin
        if ((mode == 3'd1 || mode == 3'd2) && ev_go && src == 2'd2) adv = 2'd3;
        else if (sym_go) adv = kbits;
        else adv = 2'd0;
    end


    always @(posedge clk) begin
        if (rst) begin
            mode <= 3'd0; src <= 2'd0; nm1 <= 3'd0; rot_back <= 1'b0; gated <= 1'b0;
            idle <= 4'b0111; points <= 32'd0; msg_fixed <= 3'd0;
            period <= 32'd1000; width <= 32'd10; count <= 32'd0; poly <= 3'd2;
            running <= 1'b0; forever_ <= 1'b0; left <= 32'd0; pcnt <= 32'd0; wcnt <= 32'd0;
            sent <= 24'd0; rot_idx <= 3'd0; ctr <= 3'd0;
            go_start <= 1'b0; go_stop <= 1'b0; go_one <= 1'b0; reseed <= 1'b0;
            p_idle <= 1'b1; p_msg <= 3'd0; ev_int <= 1'b0; tx_msg <= 3'd0; tx_busy <= 1'b0; hold <= 32'd0;
            pz <= 1'b1; hz <= 1'b1;
        end else begin
            go_start <= 1'b0; go_stop <= 1'b0; go_one <= 1'b0; reseed <= 1'b0;
            ev_int <= 1'b0;
            if (bus_we) begin
                case (bus_addr)
                R_TX_MODE:   begin mode <= bus_wdata[2:0]; src <= bus_wdata[5:4]; nm1 <= bus_wdata[10:8];
                                   rot_back <= bus_wdata[11]; gated <= bus_wdata[12]; end
                R_TX_IDLE:   idle <= bus_wdata[3:0];
                R_TX_POINTS: points <= bus_wdata;
                R_TX_MSG:    msg_fixed <= bus_wdata[2:0];
                R_TX_PERIOD: period <= (bus_wdata == 32'd0) ? 32'd1 : bus_wdata;
                R_TX_WIDTH:  width <= (bus_wdata == 32'd0) ? 32'd1 : bus_wdata;
                R_TX_COUNT:  count <= bus_wdata;
                R_TX_GO:     begin go_start <= bus_wdata[0]; go_stop <= bus_wdata[1]; go_one <= bus_wdata[2]; end
                R_TX_PRBS:   begin poly <= bus_wdata[2:0]; reseed <= bus_wdata[8]; end
                default: ;
                endcase
            end

            // an event's point ends after `width` clocks
            if (tx_busy) begin
                if (wcnt != 32'd0) wcnt <= wcnt - 1'b1;
                else begin tx_busy <= 1'b0; p_idle <= 1'b1; end
            end else if (mode == 3'd1 || mode == 3'd2) begin
                p_idle <= 1'b1;              // the idle point follows TX_IDLE between events
            end

            if (go_stop) running <= 1'b0;
            else if (go_start) begin
                running <= 1'b1; pcnt <= 32'd0; pz <= 1'b1; left <= count; forever_ <= (count == 32'd0);
                sent <= 24'd0; ctr <= 3'd0; rot_idx <= 3'd0;
            end

            case (mode)
            3'd1, 3'd2: begin
                // an event: periodic (1), on TRIG_IN (2), or one now (TX_GO[2])
                if (!hz) begin hold <= hold - 1'b1; hz <= (hold == 32'd1); end
                if (ev_go) begin
                    p_idle   <= 1'b0; p_msg <= next_msg;
                    tx_msg   <= next_msg;
                    ev_int   <= 1'b1;
                    tx_busy  <= 1'b1;
                    wcnt     <= width - 1'b1;
                    sent     <= sent + 1'b1;
                    ctr      <= (ctr == nm1) ? 3'd0 : ctr + 1'b1;
                    if (mode == 3'd2) begin hold <= period; hz <= 1'b0; end
                    if (!go_one && running && !forever_) begin
                        if (~|left[31:1]) running <= 1'b0;
                        left <= left - 1'b1;
                    end
                end
                if (mode == 3'd1 && running && !go_start) begin
                    pcnt <= pz ? period - 1'b1 : pcnt - 1'b1;
                    pz   <= pz ? (period == 32'd1) : (pcnt == 32'd1);
                end
            end
            3'd3, 3'd4: begin
                // a symbol every `period` clocks while running
                if (running && !go_start) begin
                    if (pz) begin
                        pcnt <= period - 1'b1; pz <= (period == 32'd1);
                        if (mode == 3'd3) begin
                            p_idle <= 1'b0;
                            p_msg  <= (kbits == 2'd0) ? 3'd0 : modn(rnd3 & ((3'd1 << kbits) - 3'd1), nm1);
                            tx_msg <= rnd3 & ((3'd1 << kbits) - 3'd1);
                        end else begin
                            p_idle  <= 1'b0; p_msg <= rot_idx;
                            tx_msg  <= rot_idx;
                            rot_idx <= rot_back ? ((rot_idx == 3'd0) ? nm1 : rot_idx - 1'b1)
                                                : ((rot_idx == nm1) ? 3'd0 : rot_idx + 1'b1);
                        end
                    end else begin pcnt <= pcnt - 1'b1; pz <= (pcnt == 32'd1); end
                end else if (!running) p_idle <= 1'b1;
            end
            3'd5: begin
                p_idle <= 1'b0; p_msg <= msg_fixed;
                tx_msg <= msg_fixed;
            end
            default: ;
            endcase
        end
    end

    // ---- the pins: registered, so the ladders and tx_event move together --------------------------------
    wire [3:0] want = ovr_en ? ovr_pt : (mode == 3'd0) ? {l_q, l_i} : point;
    assign points_o = points;
    // the change from the pins' register and its copy a clock behind (compared after the register, not
    // before it: the reply's decision came into the pins' D through it, and the Icepi closed at 87 MHz)
    reg  [3:0] last;
    assign sym_change = ({tx_q, tx_i} != last);
    always @(posedge clk) begin
        if (rst) begin
            tx_i <= 2'b11; tx_q <= 2'b01; last <= 4'b0111; tx_event <= 1'b0; evt_ts <= 32'd0;
        end else begin
            {tx_q, tx_i} <= want;
            last         <= {tx_q, tx_i};
            tx_event     <= ev_int;                  // with the pins: the receiver's time reference
            if (ev_int) evt_ts <= free_cnt + 1'b1;   // FREE_CNT in the clock the pins change
        end
    end

    // ---- reads ------------------------------------------------------------------------------------------
    always @* begin
        case (bus_addr)
        R_TX_MODE:   bus_rdata = {19'd0, gated, rot_back, nm1, 2'd0, src, 1'b0, mode};
        R_TX_IDLE:   bus_rdata = {28'd0, idle};
        R_TX_POINTS: bus_rdata = points;
        R_TX_MSG:    bus_rdata = {29'd0, msg_fixed};
        R_TX_PERIOD: bus_rdata = period;
        R_TX_WIDTH:  bus_rdata = width;
        R_TX_COUNT:  bus_rdata = count;
        R_TX_GO:     bus_rdata = {30'd0, tx_busy, running};
        R_TX_STAT:   bus_rdata = {sent, 5'd0, tx_msg};
        R_TX_PRBS:   bus_rdata = {29'd0, poly};
        R_TX_EVT_TS: bus_rdata = evt_ts;
        default:     bus_rdata = 32'hDEAD_0000 | {24'd0, bus_addr};
        endcase
    end
endmodule
