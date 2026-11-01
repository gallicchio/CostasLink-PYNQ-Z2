// rx_engine: the receiver's event decoder, at the fast sampler's resolution (Response 15; 0x40-0x5F).
//
// The fast inputs arrive SER samples a clock, sample 0 the earliest: per sample a vector
// {TRIG_IN, CMP_IN, CMP_IP, CMP_QN, CMP_QP, CMP_I} (bits 5..0).  A time is counted in samples:
// FREE_CNT x SER + the sample's index, so every latency below is in samples (1.25 ns at 800 Ms/s on the
// PYNQ-Z2, 5 ns at 200 Ms/s on the Icepi Zero's first sampler).
//
// One decoder serves every comparator scheme of PLAN.md section 18 (A1-A4, B1, B2, R4, the windows):
//  * an EVENT is the first sample in which any comparator of RX_IDLE's mask differs from its idle value;
//  * the DECISION is a table lookup, RX_LUT[v] = {valid, message}, of either the five comparators'
//    vector RX_TIMING[7:0] samples after the event (the settled point) or, with RX_CTRL[2], of the set
//    that changed in the event's own sample (first-edge decoding, which tolerates 19 degrees of angle);
//  * the slow comparators then CONFIRM or VETO it (RX_SLOW_EXP, RX_TIMING[23:16] clocks later: the
//    37-80 ns of PLAN.md section 8, plus the two-clock synchroniser);
//  * the decoder re-arms after RX_TIMING[15:8] clocks with every masked comparator at idle.
// A REFERENCE is this board's TX event (loopback, the pins' clock) or TRIG_IN's rising edge (RX_CTRL[3]):
// an event within RX_WINDOW clocks after it gets its latency; one with none is FALSE; a reference
// with no event is MISSED.  Counters, the last event, min / max / sum of the latency, an 8 x 8
// confusion matrix (row: the message sent, column: the message decoded) and a 1024-bin histogram are
// kept until RX_CTRL[1].  RX_BER_CFG checks a PRBS on CMP_I sampled once a symbol at a set phase
// (self-synchronising: needs no alignment with the transmitter; TX_PERIOD sets the symbol length), or with
// RX_BER_CFG[24] at the phase ber_cdr.v recovers from CMP_I's own edges (a transmitter on another clock:
// the B210, a second board), the phase then the sampling point's distance from the tracked edge.
// RX_IHOLD_CFG holds the loop (ihold.v) while the comparators chatter: an interferer strong enough to drag it;
// RX_SHOLD_CFG while the windows say the carrier is gone (the signal holdover).

module rx_engine #(
    parameter integer SER    = 8,               // samples a clock: 1, 2, 4 or 8
    parameter integer CLK_HZ = 100_000_000
) (
    input  wire              clk,
    input  wire              rst,
    input  wire [7:0]        bus_addr,
    input  wire [31:0]       bus_wdata,
    input  wire              bus_we,
    input  wire              bus_re,
    output reg  [31:0]       bus_rdata,
    input  wire [6*SER-1:0]  fs,                // the fast samples, sample s in [6s+5:6s]
    input  wire [2:0]        slow,              // {CMP_QN_S, CMP_QP_S, CMP_I_S}, synchronised
    input  wire [31:0]       free_cnt,
    input  wire              tx_event,          // tx_engine: an event's point is on the pins this clock
    input  wire [2:0]        tx_msg,
    input  wire [31:0]       sym_period,        // TX_PERIOD: the PRBS symbol length in clocks
    input  wire              tx_busy,           // tx_engine: an event's point is out (lockmon.v masks its own Q moves)
    output reg               ev_pulse,          // one clock: an event
    output reg               dec_pulse,         // one clock: a decision
    output reg               valid_pulse,       // one clock: a decision with a valid table entry
    output wire              trig_in_rise,      // one clock: TRIG_IN rose (for tx_engine mode 2)
    // the decoder as it is set, for turnaround.v's reply lane (the same decision, earlier)
    output wire [4:0]        cfg_idle,
    output wire [4:0]        cfg_mask,
    output wire [127:0]      cfg_lut,
    output wire              cfg_first,
    output wire [7:0]        cfg_dly,
    output wire              arm_now,           // armed, enabled, not stopped: takes an event in stage 1 now
    output wire              arm_next,          // the same next clock, with no event in stage 1 now
    output wire              ref_now_o,         // one clock: a reference (this board's TX event, or TRIG_IN's rise)
    output wire [31:0]       t_ref_o,           // its time in samples
    output wire              ihold_o,           // the interference hold or the signal holdover (ihold.v), to LOOP_HOLD
    output wire [3:0]        led_o,             // the PYNQ-Z2's LD0..LD3 (lockmon.v)
    output wire [5:0]        rgb_o              // its LD4 and LD5, {LD5 R G B, LD4 R G B}
);
`include "regmap.vh"
    localparam integer LS = (SER >= 8) ? 3 : (SER >= 4) ? 2 : (SER >= 2) ? 1 : 0;
    localparam integer CLK_MHZ = CLK_HZ / 1_000_000;
    localparam integer SER_M1I = SER - 1;
    localparam [15:0] CLK_HZ_MHZ = CLK_MHZ[15:0];
    localparam [7:0]  SER_W  = SER[7:0];
    localparam [7:0]  SER_M1 = SER_M1I[7:0];
    localparam [8:0]  SER9   = SER[8:0];

    // ---- registers --------------------------------------------------------------------------------
    reg        en, first_mode, ref_trig, single;
    reg [2:0]  cm_row_reg;
    reg        cm_row_tx;
    reg [4:0]  idle, mask;
    reg [7:0]  dly, quiet;
    reg [7:0]  cdly;
    reg [7:0]  settle;                           // ID 11: decide once the vector is one state's and has held this
                                                 // many samples (RX_TIMING[31:24]; 0: always RX_DELAY after the event)
    reg [31:0] window;
    reg [127:0] lut;                            // 32 entries x {valid, msg[2:0]}
    reg [31:0] slow_exp;
    reg [1:0]  hist_what;
    reg [3:0]  hist_shift;
    reg [9:0]  hist_addr;
    reg [5:0]  cm_addr;
    reg        ber_en, ber_inv;
    reg [2:0]  ber_poly;
    reg [15:0] ber_phase;
    reg        ber_cdr;                         // RX_BER_CFG[24]: the timing recovered (ber_cdr.v)
    reg [3:0]  ber_gain;                        // [28:25]: its loop's gain, 2^-gain
    reg        ber_pol;                         // [29]: it tracks the rising edges and centres on the skew (one_pol)
    reg [1:0]  ber_src;                         // [31:30], ID 12: the comparator checked: CMP_I, CMP_IP, CMP_IN, CMP_QP
    reg        ih_en;                           // RX_IHOLD_CFG: the interference hold (ihold.v)
    reg [2:0]  ih_wlog;
    reg [7:0]  ih_th;
    reg [4:0]  ih_mask;
    reg [31:0] ih_hold, ih_max;
    reg [15:0] ih_persist;
    reg [3:0]  ih_prop;
    reg [31:0] lk_win;
    reg [7:0]  lk_below, lk_at;
    reg        led_auto;
    reg [9:0]  led_sw;
    reg        sh_en;                           // RX_SHOLD_CFG: the signal holdover (ihold.v, LEVEL 1)
    reg [2:0]  sh_wlog;
    reg [7:0]  sh_th;
    reg [4:0]  sh_mask;
    reg [31:0] sh_hold, sh_max;
    reg        clr;

    reg [31:0] n_events, n_decided, n_confirm, n_veto, n_false, n_missed, n_refs;
    reg [31:0] n_undec;                          // events with a reference that decided nothing (ID 10)
    reg [31:0] lat_sum, lat_n, ber_bits, ber_err;
    reg [15:0] lat_min, lat_max;
    reg [14:0] last;                             // {had a reference, fired[4:0], vector[4:0], {valid, msg}}: RX_LAST
    reg [31:0] last_lat;
    reg [31:0] evt_ts;

    // ---- the samples, the time base ---------------------------------------------------------------------
    function [5:0] vec;
        input [6*SER-1:0] f;
        input [8:0] s;
        begin
            vec = f[6*s +: 6];
        end
    endfunction

    wire [31:0] t0 = free_cnt << LS;            // the time of this clock's sample 0

    // TRIG_IN's first rising sample this clock (the previous clock's last sample counts)
    reg        trig_prev;
    reg        tr_found;
    reg [3:0]  tr_s;
    integer    i;
    reg        tr_before;
    always @* begin
        tr_found = 1'b0; tr_s = 4'd0;
        for (i = SER - 1; i >= 0; i = i - 1) begin
            if (i == 0) tr_before = trig_prev;
            else        tr_before = fs[6*i - 1];          // sample i-1's TRIG_IN (bit 5 of it)
            if (fs[6*i + 5] && !tr_before) begin
                tr_found = 1'b1; tr_s = i[3:0];
            end
        end
    end

    // the first sample with a masked comparator off its idle value
    reg        out_found;
    reg [3:0]  out_s;
    reg        all_idle;
    integer    j;                                     // its own loop variable: one shared by two always @*
    always @* begin                                       // blocks is a multi-driven signal (Verilator 5.051)
        out_found = 1'b0; out_s = 4'd0;
        for (j = SER - 1; j >= 0; j = j - 1) begin
            if (|((vec(fs, j[8:0]) ^ {1'b0, idle}) & {1'b0, mask})) begin
                out_found = 1'b1; out_s = j[3:0];
            end
        end
        all_idle = !out_found;
    end
    /* verilator lint_off UNUSEDSIGNAL */
    wire [5:0] v_out     = vec(fs, {5'd0, out_s});
    /* verilator lint_on UNUSEDSIGNAL */

    // Stage 1: the priority encoders' results, registered with the time and the TX event of their clock,
    // so the decoder below starts from registers (the Icepi's encoder -> event -> counters path closed at
    // 83 MHz in one clock).  Everything downstream is a clock late alike: the time stamps are in samples
    // and carry their own clock's time, so no latency moves; TRIG_B, the counters and TX_MODE 2's start
    // happen a clock later.
    reg [6*SER-1:0] fs1;
    reg        out_found1, all_idle1, tr_found1, tx_event1;
    reg [3:0]  out_s1, tr_s1;
    reg [4:0]  fired1;
    reg [2:0]  tx_msg1;
    reg [31:0] t01, free_cnt1;
    always @(posedge clk) begin
        fs1 <= fs;
        out_found1 <= out_found; all_idle1 <= all_idle; out_s1 <= out_s;
        fired1     <= (v_out[4:0] ^ idle) & mask;
        tr_found1  <= tr_found; tr_s1 <= tr_s;
        tx_event1  <= tx_event && !rst; tx_msg1 <= tx_msg;
        t01        <= t0; free_cnt1 <= free_cnt;
    end
    assign trig_in_rise = tr_found1;

    // ---- references --------------------------------------------------------------------------------------
    reg        ref_pend;
    reg [31:0] t_ref;
    reg [31:0] ref_age;
    reg [2:0]  ref_msg;
    wire       ref_now  = ref_trig ? tr_found1 : tx_event1;
    wire       ref_live = ref_pend && !ref_now && ref_age < window;   // an event now takes this reference
    // a fine time is FREE_CNT x SER + the sample: SER a power of two, so the sample index ORs into the low bits
    // (no carry chain behind the priority encoder: the Icepi's first build closed at 44 MHz with an adder here)
    wire [31:0] t_ref_now = t01 | (ref_trig ? {28'd0, tr_s1} : 32'd0);
    wire [31:0] tf_out    = t01 | {28'd0, out_s1};

    // ---- the decoder -----------------------------------------------------------------------------------------
    localparam [1:0] S_ARMED = 2'd0, S_DECIDE = 2'd1, S_CONFIRM = 2'd2, S_QUIET = 2'd3;
    reg [1:0]  st;
    reg [31:0] t_ev;
    reg [4:0]  fired;
    reg [8:0]  remain;                           // samples still to wait for the decision
    reg [7:0]  ccnt, qcnt;
    reg [2:0]  dmsg;
    reg        dvalid;
    reg        ev_has_ref;
    reg [31:0] ev_tref, ev_tprev, t_last;        // the event's reference, the previous event, the last event
    reg [1:0]  last_cv;                          // {vetoed, confirmed} of the last decision
    // the record pipeline after a decision: p1 the times, p2 the latencies, pq the latency to the decision,
    // p3 the statistics and the bins
    reg        p1_v, p1_hr, p2_v, p2_hr, p3_v;
    reg [31:0] p1_tev, p1_tref, p1_tprev;
    reg [3:0]  p1_e, p2_e;
    reg [4:0]  p1_vec, p1_fired, p2_vec, p2_fired;
    reg [2:0]  p1_row, p2_row;
    reg [15:0] p2_le, p2_dt;
    // pq: the latency plus the decision delay, a clock of its own (sat16 of a sum, then the sum, the minimum
    // and the maximum behind it closed some Icepi placements at 95-99 MHz)
    reg        pq_v, pq_hr;
    reg [3:0]  pq_e;
    reg [4:0]  pq_vec, pq_fired;
    reg [2:0]  pq_row;
    reg [15:0] pq_le, pq_dt, pq_ld;
    reg [31:0] p3_hv;
    reg        stopped;

    // the decision, always at least a clock after the event: its sample is read from the samples one clock
    // late (fs_d: stage 1's, a clock later), `remain` samples into them.  Deciding in the event's own clock put the priority encoder,
    // the delay's add, the compare and the sample's mux in one path: the Icepi closed at 61 MHz (Response 15).
    // The time stamps are in samples, so this moves no latency; only TRIG_B goes out a clock later.
    reg  [6*SER-1:0] fs_d;
    always @(posedge clk) fs_d <= fs1;
    // ID 11, the settled decision (settle = k > 0, the vector mode): the first sample from the event on, and no later
    // than RX_DELAY after it, whose vector the table holds as one state's and which has held k samples (each corner
    // decided as soon as it has settled; RX_DELAY the longest wait).  k must outlast the comparators' skew: a corner on
    // its way can pass through another state's vector (Q crossed, I not yet: the corner that moves Q alone), and a k
    // shorter than that decides it wrong (test_sim's test_settled_decision).  Pipelined (the first build's serial run
    // count was 22 levels, 8 ns over the 100 MHz clock): each sample's table bit and whether it equals the sample before
    // are worked out from stage 1's samples a clock ahead and registered beside fs_d, with the last two clocks' 'same'
    // bits behind them (k up to 2 SER + 1); the event's bounds are masks set a clock ahead (lo_m from the event's
    // sample on, hi_m up to RX_DELAY after it).
    reg  [SER-1:0]   vld_d, same_d, same_p1, same_p2, lo_m, hi_m;
    reg  [2*SER-1:0] kmask;                            // the k - 1 newest 'same' bits that must hold
    integer          m;
    always @(posedge clk) begin
        vld_d[0]  <= lut[{fs1[4:0], 2'b11}];
        same_d[0] <= fs1[4:0] == fs_d[6*(SER-1) +: 5];
        for (m = 1; m < SER; m = m + 1) begin
            vld_d[m]  <= lut[{fs1[6*m +: 5], 2'b11}];
            same_d[m] <= fs1[6*m +: 5] == fs1[6*(m-1) +: 5];
        end
        same_p1 <= same_d;
        same_p2 <= same_p1;
    end
    wire [3*SER-1:0] same_h = {same_d, same_p1, same_p2};     // the newest at the top
    reg              set_found;
    reg  [3:0]       set_s;
    reg  [2*SER-1:0] run_w;
    integer          m2, rb;
    always @* begin
        set_found = 1'b0; set_s = 4'd0; run_w = {2*SER{1'b0}};
        for (m2 = SER - 1; m2 >= 0; m2 = m2 - 1) begin       // the earliest qualifying sample wins
            for (rb = 0; rb < 2*SER; rb = rb + 1) run_w[rb] = same_h[2*SER + m2 - rb];
            if (vld_d[m2] && lo_m[m2] && hi_m[m2] && &(run_w | ~kmask)) begin
                set_found = 1'b1; set_s = m2[3:0];
            end
        end
        if (settle == 8'd0 || first_mode || st != S_DECIDE) set_found = 1'b0;
    end
    function [SER-1:0] ge_mask;                               // samples j >= s
        input [8:0] s_;
        integer q;
        begin
            for (q = 0; q < SER; q = q + 1) ge_mask[q] = q[8:0] >= s_;
        end
    endfunction
    function [SER-1:0] le_mask;                               // samples j <= r
        input [8:0] r_;
        integer q;
        begin
            for (q = 0; q < SER; q = q + 1) le_mask[q] = q[8:0] <= r_;
        end
    endfunction
    function [2*SER-1:0] kmask_of;                            // k - 1 low bits set (k = 0 or 1: none)
        input [7:0] k_;
        integer q;
        begin
            for (q = 0; q < 2*SER; q = q + 1) kmask_of[q] = (k_ > 8'd1) && (q[7:0] < k_ - 8'd1);
        end
    endfunction
    wire       dec_now = (st == S_DECIDE) && (set_found || remain < SER9);
    wire [8:0] dec_s   = set_found ? {5'd0, set_s} : remain;
    /* verilator lint_off UNUSEDSIGNAL */
    wire [5:0] tv      = vec(fs_d, dec_s);       // bit 5 (TRIG_IN) is not a comparator
    /* verilator lint_on UNUSEDSIGNAL */
    wire [4:0] dec_vec   = tv[4:0];
    wire [4:0] lut_idx   = first_mode ? fired : dec_vec;
    // the table lookup a clock after the sample's choice (dec1): the sample mux, the table's 32:1 mux and the
    // counters behind it closed at 87 MHz on the Icepi in one clock
    reg        dec1;
    reg [4:0]  li_q, dv_q;
    reg [8:0]  d_q, p1_d, p2_d;                  // the samples from the event to the decision (RX_DELAY, or fewer settled)
    reg [2:0]  row_q;
    wire [3:0] lut_e     = lut[{li_q, 2'b00} +: 4];

    function [15:0] sat16;
        input [31:0] v;
        begin
            sat16 = (v > 32'hFFFF) ? 16'hFFFF : v[15:0];
        end
    endfunction

    // ---- the counter RAMs ------------------------------------------------------------------------------------
    reg        cm_inc, h_inc;
    reg [5:0]  cm_iaddr;
    reg [9:0]  h_iaddr;
    wire [31:0] cm_rdata, h_rdata;
    wire       cm_clearing, h_clearing;
    count_ram #(.AW(6), .DW(32)) u_cm (.clk(clk), .rst(rst), .clear(clr), .clearing(cm_clearing),
        .inc(cm_inc), .inc_addr(cm_iaddr), .rd_addr(cm_addr), .rd_data(cm_rdata));
    count_ram #(.AW(10), .DW(32)) u_hist (.clk(clk), .rst(rst), .clear(clr), .clearing(h_clearing),
        .inc(h_inc), .inc_addr(h_iaddr), .rd_addr(hist_addr), .rd_data(h_rdata));

    function [9:0] hbin;
        input [31:0] v;
        input [3:0]  sh;
        reg [31:0] b;
        begin
            b = v >> sh;
            hbin = (b > 32'd1023) ? 10'd1023 : b[9:0];
        end
    endfunction

    // ---- the BER check ----------------------------------------------------------------------------------------
    reg [31:0] scnt;
    reg [30:0] rbits;
    reg [4:0]  nfill;
    wire       ber_exp;
    prbs_expect u_exp (.r(rbits), .poly(ber_poly), .e(ber_exp));
    wire [15:0] ph_clk = ber_phase >> LS;
    wire [3:0]  ph_s   = ber_phase[3:0] & SER_M1[3:0];
    /* verilator lint_off UNUSEDSIGNAL */
    wire [5:0]  v_ph   = vec(fs, {5'd0, ph_s});
    /* verilator lint_on UNUSEDSIGNAL */
    // the comparator checked (ID 12): CMP_I (BPSK), CMP_IP or CMP_IN (on-off keying: the carrier there or nulled),
    // CMP_QP (a bit on Q); the vector is {CMP_IN, CMP_IP, CMP_QN, CMP_QP, CMP_I}
    wire [2:0]  src_k  = (ber_src == 2'd1) ? 3'd3 : (ber_src == 2'd2) ? 3'd4 : (ber_src == 2'd3) ? 3'd1 : 3'd0;
    wire        ber_bit = v_ph[src_k] ^ ber_inv;

    // the timing recovery: the checked comparator's samples this clock; restarted by every write of RX_BER_CFG
    wire [SER-1:0] cmp_i_s;
    genvar g;
    generate
        for (g = 0; g < SER; g = g + 1) begin : g_cmpi
            assign cmp_i_s[g] = fs[6*g + src_k];
        end
    endgenerate
    wire               cdr_v, cdr_raw;
    wire signed [15:0] cdr_err;
    wire signed [31:0] cdr_sum;
    wire [31:0]        cdr_edges;
    wire signed [31:0] cdr_skew;
    ber_cdr #(.SER(SER)) u_cdr (
        .clk(clk), .rst(rst), .restart(bus_we && bus_addr == R_RX_BER_CFG), .track(1'b1), .one_pol(ber_pol),
        .d(cmp_i_s), .period(sym_period[15:0]), .offset(ber_phase), .gain(ber_gain),
        .bit_v(cdr_v), .bit_o(cdr_raw), .err_o(cdr_err), .corr_sum(cdr_sum), .edges(cdr_edges), .skew(cdr_skew));
    wire        cdr_bit = cdr_raw ^ ber_inv;

    // the interference hold: LOOP_HOLD while the chosen comparators chatter (a strong interferer), its counts
    // cleared with the others (RX_CTRL[1])
    wire [31:0] ih_n, ih_clk, sh_n, sh_clk;
    wire [7:0]  ih_last, sh_last;
    wire        ih_act, sh_act;
    ihold #(.SER(SER)) u_ihold (
        .clk(clk), .rst(rst), .clr(clr), .en(ih_en), .fs(fs), .mask(ih_mask), .wlog(ih_wlog), .thresh(ih_th),
        .hold(ih_hold), .max(ih_max), .persist(ih_persist), .prop(ih_prop), .active(ih_act), .n_holds(ih_n), .n_clocks(ih_clk),
        .last_count(ih_last));
    // and the signal holdover: the loop held while the carrier is too weak for the windows (someone in front of the
    // antenna), so it is still on the carrier's frequency when the carrier is back
    ihold #(.SER(SER), .LEVEL(1)) u_shold (
        .clk(clk), .rst(rst), .clr(clr), .en(sh_en), .fs(fs), .mask(sh_mask), .wlog(sh_wlog), .thresh(sh_th),
        .hold(sh_hold), .max(sh_max), .persist(16'd0), .prop(4'd0), .active(sh_act), .n_holds(sh_n), .n_clocks(sh_clk),
        .last_count(sh_last));
    assign ihold_o = ih_act | sh_act;

    // the lock's state in gateware (lockmon.v): the status registers and the PYNQ-Z2's LEDs
    wire [1:0]  lk_state;
    wire [31:0] lk_losses, lk_secs, lk_ihigh;
    wire [15:0] lk_qp, lk_qn, lk_i;
    wire [6:0]  lk_busy;
    lockmon #(.SER(SER), .CLK_HZ(CLK_HZ)) u_lock (
        .clk(clk), .rst(rst), .fs(fs), .window(lk_win), .locked_below(lk_below), .lost_at(lk_at), .hold(ih_act | sh_act), .own(tx_busy),
        .auto(led_auto), .led_sw(led_sw), .state(lk_state), .n_losses(lk_losses), .n_locked_s(lk_secs),
        .last_qp(lk_qp), .last_qn(lk_qn), .last_i(lk_i), .last_ihigh(lk_ihigh), .last_busy(lk_busy), .led(led_o),
        .rgb(rgb_o));

    // ---- the state ------------------------------------------------------------------------------------------
    always @(posedge clk) begin
        if (rst) begin
            en <= 1'b0; first_mode <= 1'b0; ref_trig <= 1'b0; single <= 1'b0; cm_row_reg <= 3'd0; cm_row_tx <= 1'b1;
            idle <= 5'b00001; mask <= 5'b00001; dly <= 8'd4; quiet <= 8'd4; cdly <= 8'd6; settle <= 8'd0;
            kmask <= {2*SER{1'b0}}; lo_m <= {SER{1'b1}}; hi_m <= {SER{1'b1}}; window <= 32'd100;
            lut <= 128'd0; slow_exp <= 32'd0; hist_what <= 2'd1; hist_shift <= 4'd0; hist_addr <= 10'd0; cm_addr <= 6'd0;
            ber_en <= 1'b0; ber_inv <= 1'b0; ber_poly <= 3'd2; ber_phase <= 16'd0; clr <= 1'b0;
            ber_cdr <= 1'b0; ber_gain <= 4'd4; ber_pol <= 1'b0; ber_src <= 2'd0;
            ih_en <= 1'b0; ih_wlog <= 3'd5; ih_th <= 8'd8; ih_mask <= 5'b00110;
            ih_hold <= CLK_HZ / 50; ih_max <= 5 * CLK_HZ;  // released 20 ms after the last busy window (BRINGUP_LOG 4.8b, 4.9)
            ih_persist <= 16'd0;                           // the first busy window holds, as before ID version 7
            ih_prop <= 4'd0;                               // the release always ih_hold, as before ID version 8
            lk_win <= CLK_HZ / 100; lk_below <= 8'd24; lk_at <= 8'd48;          // lockmon.v: 10 ms looks, of 64
            led_auto <= 1'b1; led_sw <= 10'd0;
            sh_en <= 1'b0; sh_wlog <= 3'd5; sh_th <= 8'd64; sh_mask <= 5'b11110;
            sh_hold <= CLK_HZ / 1000; sh_max <= 10 * CLK_HZ;
            n_events <= 32'd0; n_decided <= 32'd0; n_confirm <= 32'd0; n_veto <= 32'd0; n_false <= 32'd0;
            n_missed <= 32'd0; n_refs <= 32'd0; n_undec <= 32'd0; lat_sum <= 32'd0; lat_n <= 32'd0; ber_bits <= 32'd0; ber_err <= 32'd0;
            lat_min <= 16'hFFFF; lat_max <= 16'd0; last <= 15'd0; last_lat <= 32'd0; evt_ts <= 32'd0;
            ref_pend <= 1'b0; t_ref <= 32'd0; ref_age <= 32'd0; ref_msg <= 3'd0;
            st <= S_ARMED; t_ev <= 32'd0; fired <= 5'd0; remain <= 9'd0; ccnt <= 8'd0; qcnt <= 8'd0;
            dmsg <= 3'd0; dvalid <= 1'b0; ev_has_ref <= 1'b0; stopped <= 1'b0;
            dec1 <= 1'b0; li_q <= 5'd0; dv_q <= 5'd0; row_q <= 3'd0;
            ev_tref <= 32'd0; ev_tprev <= 32'd0; t_last <= 32'd0; last_cv <= 2'd0;
            p1_v <= 1'b0; p1_hr <= 1'b0; p2_v <= 1'b0; p2_hr <= 1'b0; p3_v <= 1'b0;
            p1_tev <= 32'd0; p1_tref <= 32'd0; p1_tprev <= 32'd0; p1_e <= 4'd0; p2_e <= 4'd0;
            p1_vec <= 5'd0; p1_fired <= 5'd0; p2_vec <= 5'd0; p2_fired <= 5'd0; p1_row <= 3'd0; p2_row <= 3'd0;
            p2_le <= 16'd0; p2_dt <= 16'd0; p3_hv <= 32'd0;
            pq_v <= 1'b0; pq_hr <= 1'b0; pq_e <= 4'd0; pq_vec <= 5'd0; pq_fired <= 5'd0; pq_row <= 3'd0;
            pq_le <= 16'd0; pq_dt <= 16'd0; pq_ld <= 16'd0;
            ev_pulse <= 1'b0; dec_pulse <= 1'b0; valid_pulse <= 1'b0; trig_prev <= 1'b0;
            cm_inc <= 1'b0; h_inc <= 1'b0; cm_iaddr <= 6'd0; h_iaddr <= 10'd0;
            scnt <= 32'd0; rbits <= 31'd0; nfill <= 5'd0;
        end else begin
            clr <= 1'b0; ev_pulse <= 1'b0; dec_pulse <= 1'b0; valid_pulse <= 1'b0; cm_inc <= 1'b0; h_inc <= 1'b0;
            trig_prev <= fs[6*(SER-1) + 5];

            // ---- the bus ----
            if (bus_we) begin
                case (bus_addr)
                R_RX_CTRL:     begin en <= bus_wdata[0]; clr <= bus_wdata[1]; first_mode <= bus_wdata[2];
                                     ref_trig <= bus_wdata[3]; single <= bus_wdata[4];
                                     cm_row_reg <= bus_wdata[18:16]; cm_row_tx <= bus_wdata[19];
                                     stopped <= 1'b0; end
                R_RX_IDLE:     begin idle <= bus_wdata[4:0]; mask <= bus_wdata[12:8]; end
                R_RX_TIMING:   begin dly <= bus_wdata[7:0]; quiet <= bus_wdata[15:8]; cdly <= bus_wdata[23:16];
                                     settle <= bus_wdata[31:24]; kmask <= kmask_of(bus_wdata[31:24]); end
                R_RX_WINDOW:   window <= bus_wdata;
                R_RX_LUT0:     lut[31:0]   <= bus_wdata;
                R_RX_LUT1:     lut[63:32]  <= bus_wdata;
                R_RX_LUT2:     lut[95:64]  <= bus_wdata;
                R_RX_LUT3:     lut[127:96] <= bus_wdata;
                R_RX_SLOW_EXP: slow_exp <= bus_wdata;
                R_RX_CM_ADDR:  cm_addr <= bus_wdata[5:0];
                R_RX_HIST_CFG: begin hist_what <= bus_wdata[1:0]; hist_shift <= bus_wdata[7:4]; end
                R_RX_HIST_ADDR: hist_addr <= bus_wdata[9:0];
                R_RX_BER_CFG:  begin ber_en <= bus_wdata[0]; ber_inv <= bus_wdata[1]; ber_poly <= bus_wdata[6:4];
                                     ber_phase <= bus_wdata[23:8]; ber_cdr <= bus_wdata[24];
                                     ber_gain <= bus_wdata[28:25]; ber_pol <= bus_wdata[29]; ber_src <= bus_wdata[31:30]; end
                R_RX_IHOLD_CFG: begin ih_en <= bus_wdata[0]; ih_wlog <= bus_wdata[3:1]; ih_th <= bus_wdata[15:8];
                                      ih_mask <= bus_wdata[20:16]; end
                R_RX_IHOLD_HOLD: ih_hold <= bus_wdata;
                R_RX_IHOLD_MAX:  ih_max <= bus_wdata;
                R_RX_IHOLD_PERSIST: begin ih_persist <= bus_wdata[15:0]; ih_prop <= bus_wdata[19:16]; end
                R_RX_LOCK_CFG:  begin lk_below <= bus_wdata[7:0]; lk_at <= bus_wdata[15:8]; end
                R_RX_LOCK_WIN:  lk_win <= (bus_wdata < 32'd1000) ? 32'd1000 : bus_wdata;
                R_LED_CTRL:     begin led_auto <= bus_wdata[0]; led_sw <= bus_wdata[10:1]; end
                R_RX_SHOLD_CFG: begin sh_en <= bus_wdata[0]; sh_wlog <= bus_wdata[3:1]; sh_th <= bus_wdata[15:8];
                                      sh_mask <= bus_wdata[20:16]; end
                R_RX_SHOLD_HOLD: sh_hold <= bus_wdata;
                R_RX_SHOLD_MAX:  sh_max <= bus_wdata;
                default: ;
                endcase
            end
            // reading a RAM's data steps its address on (the read itself takes the value now on rd_data)
            if (bus_re && bus_addr == R_RX_CM_DATA) cm_addr <= cm_addr + 1'b1;
            if (bus_re && bus_addr == R_RX_HIST_DATA) hist_addr <= hist_addr + 1'b1;

            if (clr) begin
                n_events <= 32'd0; n_decided <= 32'd0; n_confirm <= 32'd0; n_veto <= 32'd0; n_false <= 32'd0;
                n_missed <= 32'd0; n_refs <= 32'd0; n_undec <= 32'd0; lat_sum <= 32'd0; lat_n <= 32'd0; ber_bits <= 32'd0;
                ber_err <= 32'd0; lat_min <= 16'hFFFF; lat_max <= 16'd0; ref_pend <= 1'b0;
            end

            // ---- references: a new one; an old one runs out ----
            if (ref_pend) ref_age <= ref_age + 1'b1;
            if (ref_pend && ref_age >= window) begin
                ref_pend <= 1'b0;
                if (en) n_missed <= n_missed + 1'b1;
            end
            if (ref_now && en) begin
                if (ref_pend && ref_age < window) n_missed <= n_missed + 1'b1;   // the last one never got its event
                ref_pend <= 1'b1; ref_age <= 32'd0; t_ref <= t_ref_now; ref_msg <= tx_msg1;
                n_refs <= n_refs + 1'b1;
            end

            // ---- the decoder ----
            case (st)
            S_ARMED: if (en && !stopped && out_found1) begin
                t_ev      <= tf_out;
                ev_tprev  <= t_last;
                t_last    <= tf_out;
                evt_ts    <= free_cnt1;
                fired     <= fired1;
                n_events  <= n_events + 1'b1;
                ev_pulse  <= 1'b1;
                // paired with the reference only while it is inside its window: on the clock it runs out it is
                // counted missed (above), so the event is false (before ID 10 it was both: references counted twice)
                ev_has_ref <= ref_live;
                ev_tref   <= t_ref;
                if (ref_live) ref_pend <= 1'b0;
                else n_false <= n_false + 1'b1;
                remain <= {5'd0, out_s1} + {1'b0, dly};
                lo_m   <= ge_mask({5'd0, out_s1});
                hi_m   <= le_mask({5'd0, out_s1} + {1'b0, dly});
                st     <= S_DECIDE;
            end
            S_DECIDE: if (!dec_now) begin
                remain <= remain - SER9;
                lo_m   <= {SER{1'b1}};
                hi_m   <= le_mask(remain - SER9);
            end
            S_CONFIRM: begin
                if (dec1) ;                                 // the table's answer comes this clock
                else if (ccnt != 8'd0) ccnt <= ccnt - 1'b1;
                else begin
                    if (slow_exp[{dmsg, 2'b11}] && dvalid) begin
                        if (slow == slow_exp[{dmsg, 2'b00} +: 3]) begin n_confirm <= n_confirm + 1'b1; last_cv[0] <= 1'b1; end
                        else begin n_veto <= n_veto + 1'b1; last_cv[1] <= 1'b1; end
                    end
                    st <= S_QUIET; qcnt <= 8'd0;
                end
            end
            S_QUIET: begin
                if (!all_idle1) qcnt <= 8'd0;
                else if (qcnt >= quiet) begin
                    st <= S_ARMED;
                    if (single) stopped <= 1'b1;
                end else qcnt <= qcnt + 1'b1;
            end
            endcase

            // the decision: the sample's vector (or the fired set) chosen, then looked up a clock later
            dec1 <= dec_now;
            if (dec_now) begin
                li_q  <= lut_idx;
                dv_q  <= dec_vec;
                d_q   <= {1'b0, dly} + dec_s - remain;
                row_q <= cm_row_tx ? ref_msg : cm_row_reg;
                ccnt <= cdly; st <= S_CONFIRM;
                last_cv <= 2'b00;
            end
            if (dec1) begin
                dmsg <= lut_e[2:0]; dvalid <= lut_e[3];
                dec_pulse <= 1'b1;
                valid_pulse <= lut_e[3];
                if (lut_e[3]) n_decided <= n_decided + 1'b1;
                // the record goes down the pipeline: the arithmetic over the next four clocks
                p1_v     <= 1'b1;
                p1_hr    <= ev_has_ref;
                p1_tev   <= t_ev;
                p1_tref  <= ev_tref;
                p1_tprev <= ev_tprev;
                p1_e     <= lut_e;
                p1_vec   <= dv_q;
                p1_fired <= fired;
                p1_row   <= row_q;
                p1_d     <= d_q;
            end else p1_v <= 1'b0;

            // p1 -> p2: the latencies
            p2_v <= p1_v; p2_hr <= p1_hr; p2_e <= p1_e; p2_vec <= p1_vec; p2_fired <= p1_fired; p2_row <= p1_row;
            p2_d <= p1_d;
            p2_le <= sat16(p1_tev - p1_tref);
            p2_dt <= sat16(p1_tev - p1_tprev);
            // p2 -> pq: reference -> decision = reference -> event + the decision delay
            pq_v <= p2_v; pq_hr <= p2_hr; pq_e <= p2_e; pq_vec <= p2_vec; pq_fired <= p2_fired; pq_row <= p2_row;
            pq_le <= p2_le; pq_dt <= p2_dt;
            pq_ld <= sat16({16'd0, p2_le} + {23'd0, p2_d});
            // pq -> p3: the record, the statistics, the confusion matrix
            p3_v <= pq_v && (pq_hr || hist_what == 2'd2);
            if (pq_v) begin : rec
                reg [15:0] ld;
                ld = pq_ld;
                last     <= {pq_hr, pq_fired, pq_vec, pq_e};
                last_lat <= {ld, pq_le};
                if (pq_hr) begin
                    lat_sum <= lat_sum + {16'd0, ld}; lat_n <= lat_n + 1'b1;
                    if (ld < lat_min) lat_min <= ld;
                    if (ld > lat_max) lat_max <= ld;
                end
                p3_hv <= {16'd0, (hist_what == 2'd0) ? pq_le : (hist_what == 2'd2) ? pq_dt : ld};
                // the confusion matrix: with the row from this board's TX, only events that had a reference (a
                // false event's decision went against the last message sent: under interference 'right' and 'wrong'
                // ran to millions for 200 000 sent); with the row software's (a remote TX), every decision
                if (pq_e[3] && (pq_hr || !cm_row_tx)) begin
                    cm_inc <= 1'b1;
                    cm_iaddr <= {pq_row, pq_e[2:0]};
                end
                if (pq_hr && !pq_e[3]) n_undec <= n_undec + 1'b1;   // sent, the receiver fired, no message's vector
            end
            // p3: the histogram's bin
            if (p3_v) begin
                h_inc <= 1'b1; h_iaddr <= hbin(p3_hv, hist_shift);
            end

            // ---- the BER check: one bit a symbol at the set phase ----
            if (ber_en) begin
                scnt <= (scnt + 1'b1 >= sym_period) ? 32'd0 : scnt + 1'b1;
                if (ber_cdr ? cdr_v : (scnt == {16'd0, ph_clk})) begin
                    rbits <= {rbits[29:0], ber_cdr ? cdr_bit : ber_bit};
                    if (nfill != 5'd31) nfill <= nfill + 1'b1;
                    else begin
                        ber_bits <= ber_bits + 1'b1;
                        if ((ber_cdr ? cdr_bit : ber_bit) != ber_exp) ber_err <= ber_err + 1'b1;
                    end
                end
            end
            // a write of RX_BER_CFG restarts the check (the register fills again); one that enables it starts
            // a new count, one that disables it keeps the count for reading.  Last, so it wins its clock.
            if (bus_we && bus_addr == R_RX_BER_CFG) begin
                nfill <= 5'd0; scnt <= 32'd0;
                if (bus_wdata[0]) begin ber_bits <= 32'd0; ber_err <= 32'd0; end
            end
        end
    end

    // ---- the decoder's state for the reply lane (turnaround.v) -------------------------------------------------
    assign cfg_idle = idle; assign cfg_mask = mask; assign cfg_lut = lut; assign cfg_first = first_mode;
    assign cfg_dly  = dly;
    assign ref_now_o = ref_now;
    assign t_ref_o   = t_ref_now;
    assign arm_now  = en && !stopped && (st == S_ARMED);
    assign arm_next = en && !stopped && ((st == S_ARMED && !out_found1) ||
                                         (st == S_QUIET && all_idle1 && qcnt >= quiet && !single));

    // ---- reads ------------------------------------------------------------------------------------------------
    always @* begin
        case (bus_addr)
        R_RX_CTRL:     bus_rdata = {12'd0, cm_row_tx, cm_row_reg, 11'd0, single, ref_trig, first_mode,
                                    cm_clearing | h_clearing, en};
        R_RX_IDLE:     bus_rdata = {19'd0, mask, 3'd0, idle};
        R_RX_TIMING:   bus_rdata = {settle, cdly, quiet, dly};
        R_RX_WINDOW:   bus_rdata = window;
        R_RX_LUT0:     bus_rdata = lut[31:0];
        R_RX_LUT1:     bus_rdata = lut[63:32];
        R_RX_LUT2:     bus_rdata = lut[95:64];
        R_RX_LUT3:     bus_rdata = lut[127:96];
        R_RX_SLOW_EXP: bus_rdata = slow_exp;
        R_RX_EVENTS:   bus_rdata = n_events;
        R_RX_DECIDED:  bus_rdata = n_decided;
        R_RX_CONFIRM:  bus_rdata = n_confirm;
        R_RX_VETO:     bus_rdata = n_veto;
        R_RX_FALSE:    bus_rdata = n_false;
        R_RX_MISSED:   bus_rdata = n_missed;
        R_RX_REFS:     bus_rdata = n_refs;
        R_RX_UNDEC:    bus_rdata = n_undec;
        R_RX_LAST:     bus_rdata = {15'd0, last[14], last_cv, last[13:0]};
        R_RX_LAST_LAT: bus_rdata = last_lat;
        R_RX_LAT_MIN:  bus_rdata = {16'd0, lat_min};
        R_RX_LAT_MAX:  bus_rdata = {16'd0, lat_max};
        R_RX_LAT_SUM:  bus_rdata = lat_sum;
        R_RX_LAT_N:    bus_rdata = lat_n;
        R_RX_CM_ADDR:  bus_rdata = {26'd0, cm_addr};
        R_RX_CM_DATA:  bus_rdata = cm_rdata;
        R_RX_HIST_CFG: bus_rdata = {24'd0, hist_shift, 2'd0, hist_what};
        R_RX_HIST_ADDR: bus_rdata = {22'd0, hist_addr};
        R_RX_HIST_DATA: bus_rdata = h_rdata;
        R_RX_EVT_TS:   bus_rdata = evt_ts;
        R_RX_BER_CFG:  bus_rdata = {ber_src, ber_pol, ber_gain, ber_cdr, ber_phase, 1'b0, ber_poly, 2'd0, ber_inv, ber_en};
        R_RX_CDR_ERR:  bus_rdata = {{16{cdr_err[15]}}, cdr_err};
        R_RX_CDR_SUM:  bus_rdata = cdr_sum;
        R_RX_CDR_EDGES: bus_rdata = cdr_edges;
        R_RX_CDR_SKEW: bus_rdata = cdr_skew;
        R_RX_IHOLD_CFG: bus_rdata = {ih_last, 3'd0, ih_mask, ih_th, 3'd0, ih_act, ih_wlog, ih_en};
        R_RX_SHOLD_CFG: bus_rdata = {sh_last, 3'd0, sh_mask, sh_th, 3'd0, sh_act, sh_wlog, sh_en};
        R_RX_SHOLD_HOLD: bus_rdata = sh_hold;
        R_RX_SHOLD_MAX:  bus_rdata = sh_max;
        R_RX_SHOLD_N:    bus_rdata = sh_n;
        R_RX_SHOLD_CLK:  bus_rdata = sh_clk;
        R_RX_IHOLD_HOLD: bus_rdata = ih_hold;
        R_RX_IHOLD_MAX:  bus_rdata = ih_max;
        R_RX_IHOLD_N:    bus_rdata = ih_n;
        R_RX_IHOLD_CLK:  bus_rdata = ih_clk;
        R_RX_IHOLD_PERSIST: bus_rdata = {12'd0, ih_prop, ih_persist};
        R_RX_LOCK_STATE:  bus_rdata = {lk_i, 7'd0, lk_busy, lk_state};
        R_RX_LOCK_CFG:    bus_rdata = {16'd0, lk_at, lk_below};
        R_RX_LOCK_WIN:    bus_rdata = lk_win;
        R_RX_LOCK_LOSSES: bus_rdata = lk_losses;
        R_RX_LOCK_SECONDS: bus_rdata = lk_secs;
        R_RX_LOCK_Q:      bus_rdata = {lk_qn, lk_qp};
        R_RX_LOCK_IHIGH:  bus_rdata = lk_ihigh;
        R_LED_CTRL:       bus_rdata = {21'd0, led_sw, led_auto};
        R_RX_BER_BITS: bus_rdata = ber_bits;
        R_RX_BER_ERR:  bus_rdata = ber_err;
        R_RX_INFO:     bus_rdata = {CLK_HZ_MHZ[15:0], 8'd6, SER_W[7:0]};
        default:       bus_rdata = 32'hDEAD_0000 | {24'd0, bus_addr};
        endcase
    end
endmodule
