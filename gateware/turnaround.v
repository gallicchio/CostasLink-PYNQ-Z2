// turnaround: the receive-to-transmit paths and their measurement (Prompt 36; registers 0x90-0xA8, regmap.py).
//
// The prover's figure of merit is its turnaround: a state arrives at RX ANT, the answer that depends on it
// leaves TX ANT (PLAN.md section 19).  Three things here:
//
//  * The SYNCHRONOUS REPLY (RP_*).  On rx_engine's valid decision of message k (the same table, the same
//    first-edge or settled-vector rule, the same arming), the ladders take TX_POINTS[RP_MAP[k]] for
//    RP_CTRL[31:16] clocks, ahead of whatever tx_engine is sending.  The lane does not wait for rx_engine's
//    own pipeline: it runs its priority encoder on `fs_lane` (on the PYNQ-Z2 the ISERDESE2's word itself,
//    a clock before the sampler's register gives it to the rest of the core: EARLY = 1) and registers the
//    event with its decision vector (L1: the first-fired set, or the settled sample RX_TIMING[7:0] after
//    the event's when it is in the same word, chosen by selects set from RX_TIMING beforehand), then looks
//    it up in a composed table, comp[v] = {valid, TX_POINTS[RP_MAP[RX_LUT[v].msg]]}, straight into
//    tx_engine's pins register (L2).  So the reply's point is on the pins two clocks after the
//    ISERDESE2's word, one after the core's `fs` (rx_engine's own valid decision is four clocks after
//    `fs`, and a TX event from it two more).  RP_REG = 1 (the Icepi Zero's, the generic top's) registers
//    the point once more, a clock later: the ECP5's LUT4s do not close L2 into the pins at 100 MHz.  A settled decision whose sample is a word or more on waits a
//    clock for each, as rx_engine does.  The composed table is rebuilt one entry a clock (32 clocks after a
//    write of RX_LUT, TX_POINTS or RP_MAP).  `once` disarms the lane after a reply; RP_CTRL[2] re-arms it on
//    each of this board's TX events and RP_CTRL[5] when RX re-arms (the link quiet at its idle again,
//    whatever made the stimulus), so in single-board loopback the stimulus is answered once and the
//    answer's own echo is not.
//
//  * The FAST PATH (FP_*), FAST_PATH = 1 only.  The five comparators straight from their pins (the
//    ISERDESE2's combinational O on the PYNQ-Z2) choose an entry of a 32-entry table, FP_MAP[v] a ladder
//    point and FP_USE[v] whether it drives the pins (else the registered pins pass): pin to pin through
//    the fabric's LUTs, no clock.  Per ladder bit two 5-input tables, "force 1" and "force 0", each one
//    reloadable LUT (fp_lut5: a CFGLUT5 on the 7-series, loaded 32 clocks after a write of FP_USE or
//    FP_MAP, an arming waiting for it), and one LUT with the arm and the registered pin: two LUT levels,
//    each bit's three by its own pad (the pads are on two sides of the die: TX_I1 on bank 34, the others on
//    bank 13; CMP_IP on bank 35, the other comparators on bank 13).  The arm is synchronous: armed by
//    FP_CTRL, by a TX event or when RX re-arms; disarmed FP_TIME clocks after the first change it causes
//    (seen in the samples: a sample whose vector it drives), or, timed, FP_TIME clocks after the arming
//    (the ring: a permutation of the states with no fixed point cycles through the loop, one turnaround a
//    hop).
//
//  * The TURNAROUND COUNTER (RT_*).  An ARRIVAL is the first change of the watched comparators after at
//    least RT_CFG[23:16] samples of quiet.  After each reference (RX's: this board's TX event, the
//    stimulus, or with RX_CTRL[3] TRIG_IN's rising sample) the first arrival is the stimulus's echo and the
//    second the reply's: their difference, in samples, is the turnaround from RX ANT to TX ANT in
//    single-board loopback (plus the cable), whichever path replied.  A TX event is on the clock's grid, so
//    the synchronous reply's wait for the ISERDESE2's word is then one fixed phase; TRIG_IN from a free-
//    running generator (it sums into the Q ladder on the board) or a second board moves it.  Every arrival
//    is also counted with the first and the last one's time (RT_MARKS, RT_SPAN: the ring's hops), with
//    RT_CFG[2] only those inside the fast path's armed window.
//
// Times are in samples, FREE_CNT x SER + the sample, as rx_engine's: the same `fs` and the same time base.

module turnaround #(
    parameter integer SER       = 8,
    parameter integer EARLY     = 0,         // 1: fs_lane is fs a clock early (the PYNQ-Z2's ISERDESE2 word)
    parameter integer FAST_PATH = 0,         // 1: build the combinational path (needs the pins' raw values)
    parameter integer RP_REG    = 1          // 1: the reply's point registered once more before the pins'
                                             // register (a clock later; the Icepi's 100 MHz), 0 the PYNQ-Z2
) (
    input  wire             clk,
    input  wire             rst,
    input  wire [7:0]       bus_addr,
    input  wire [31:0]      bus_wdata,
    input  wire             bus_we,
    output reg  [31:0]      bus_rdata,
    input  wire [6*SER-1:0] fs,              // the core's samples (rx_engine's)
    input  wire [6*SER-1:0] fs_lane,         // the same, a clock early when EARLY (else fs itself)
    input  wire [4:0]       cmp_async,       // {CMP_IN CMP_IP CMP_QN CMP_QP CMP_I} straight from the pins
    input  wire [31:0]      free_cnt,
    // rx_engine's decoder as it is set, and whether it will take the event now in the lane
    input  wire [4:0]       rx_idle,
    input  wire [4:0]       rx_mask,
    input  wire [127:0]     rx_lut,
    input  wire             rx_first,
    input  wire [7:0]       rx_dly,
    input  wire             rx_arm_now,      // armed and enabled now (its stage 1 holds the lane's word)
    input  wire             rx_arm_next,     // will be armed, enabled, with no event, next clock
    input  wire             rx_ref,          // one clock: RX's reference (this board's TX event, or TRIG_IN's rise)
    input  wire [31:0]      rx_t_ref,        // its time in samples
    // tx_engine
    input  wire [31:0]      tx_points,
    input  wire             tx_event,        // one clock: this board's TX event is on the pins (the stimulus)
    output wire             ovr_en,          // into tx_engine's pins register: the reply's point instead
    output wire [3:0]       ovr_pt,
    // the ladders {Q1 Q0 I1 I0}
    input  wire [3:0]       pins_reg,        // tx_engine's pins register
    output wire [3:0]       pins_out,        // what drives the pins: the fast path's entry while it drives, else pins_reg
    output reg              reply_ev,        // one clock: a synchronous reply's point is on the pins from this clock
    output reg              fp_hit_ev,       // one clock: the samples first show the fast path driving the pins
    output reg              fp_arm           // the fast path is armed
);
`include "regmap.vh"
    localparam integer LS = (SER >= 8) ? 3 : (SER >= 4) ? 2 : (SER >= 2) ? 1 : 0;
    localparam integer LSX = (LS > 0) ? LS - 1 : 0;      // a sample index's top bit
    localparam [8:0]   SER9  = SER[8:0];
    localparam integer SER_M1I = SER - 1;
    localparam [8:0]   SER_M1 = SER_M1I[8:0];
    localparam [15:0]  SER16 = SER[15:0];
    localparam         FP    = (FAST_PATH != 0);

    function [5:0] vec;
        input [6*SER-1:0] f;
        input [8:0] s;
        begin
            vec = f[6*s +: 6];
        end
    endfunction
    function [15:0] sat16;
        input [31:0] v;
        begin
            sat16 = (v > 32'hFFFF) ? 16'hFFFF : v[15:0];
        end
    endfunction

    wire [31:0] t0 = free_cnt << LS;             // this clock's sample 0

    // ---- registers ----------------------------------------------------------------------------------------
    reg         rp_en, rp_once, rp_rearm, rp_rearm_rx, rp_armed;
    reg [15:0]  rp_width;
    reg [31:0]  rp_map;
    reg [23:0]  rp_n;
    reg [2:0]   rp_last_dec, rp_last_rep;
    reg         fp_timed, fp_arm_tx, fp_arm_rx, fp_took, fp_counting;
    reg [31:0]  fp_time, fp_cnt;
    reg [31:0]  fp_use;
    reg [127:0] fp_map;
    reg         rt_en, rt_ring;
    reg [4:0]   rt_mask;
    reg [7:0]   rt_guard, rt_win;
    reg [31:0]  rt_last, rt_sum, rt_n, rt_miss, rt_marks, rt_span;
    reg [15:0]  rt_min, rt_max;

    wire w_rp  = bus_we && bus_addr == R_RP_CTRL;
    wire w_fp  = bus_we && bus_addr == R_FP_CTRL;
    wire w_rt  = bus_we && bus_addr == R_RT_CFG;

    // RX re-arms: the link back at its idle, quiet (the rise of rx_arm_now)
    reg  rx_arm_d;
    always @(posedge clk) rx_arm_d <= rx_arm_now && !rst;
    wire rx_rearm = rx_arm_now && !rx_arm_d;

    // =========================================================================================================
    // the synchronous reply
    // =========================================================================================================
    // ---- the composed table, one entry a clock --------------------------------------------------------------
    // (two stages: the table's entry, then its reply's point; in one the 32:1, two 8:1 and the write's
    // decode closed at +0.16 ns)
    reg  [4:0]   cidx, cidx1;
    reg  [3:0]   c_le;
    reg  [31:0]  comp_v;
    reg  [127:0] comp_p;
    wire [2:0]   c_rk = rp_map[{c_le[2:0], 2'b00} +: 3];
    always @(posedge clk) begin
        if (rst) begin cidx <= 5'd0; cidx1 <= 5'd0; c_le <= 4'd0; comp_v <= 32'd0; comp_p <= 128'd0; end
        else begin
            cidx  <= cidx + 1'b1;
            cidx1 <= cidx;
            c_le  <= rx_lut[{cidx, 2'b00} +: 4];
            comp_v[cidx1] <= c_le[3];
            comp_p[{cidx1, 2'b00} +: 4] <= tx_points[{c_rk, 2'b00} +: 4];
        end
    end

    // ---- the settled sample's selects, from RX_TIMING[7:0] (static: a clock behind a write) ---------------
    // an event at sample s decides on sample s + dly: in the same word when s + dly < SER, at sel[s]
    reg [3*SER-1:0] d_sel;
    reg [SER-1:0]   d_fit;
    integer         q;
    always @(posedge clk)
        for (q = 0; q < SER; q = q + 1) begin
            d_sel[3*q +: 3] <= q[2:0] + rx_dly[2:0];
            d_fit[q]        <= ({1'b0, rx_dly} + q[8:0]) < SER9;
        end

    // ---- L1: the first sample off the idle in the lane's word, and its decision vector ------------------------
    reg        lf_c;
    reg [3:0]  ls_c;
    integer    j;
    always @* begin
        lf_c = 1'b0; ls_c = 4'd0;
        for (j = SER - 1; j >= 0; j = j - 1)
            if (|((vec(fs_lane, j[8:0]) ^ {1'b0, rx_idle}) & {1'b0, rx_mask})) begin lf_c = 1'b1; ls_c = j[3:0]; end
    end
    // each sample's settled candidate: the sample dly after it (a select set beforehand: off the event's path)
    reg  [5*SER-1:0] cand;
    integer          c;
    always @*
        for (c = 0; c < SER; c = c + 1)
            cand[5*c +: 5] = fs_lane[6*d_sel[3*c +: 3] +: 5];
    /* verilator lint_off UNUSEDSIGNAL */
    wire [5:0] lv_c = vec(fs_lane, {5'd0, ls_c});
    /* verilator lint_on UNUSEDSIGNAL */
    reg        l_found, l_fits;
    reg [3:0]  l_s;
    reg [4:0]  l_fired, l_dvec;
    always @(posedge clk) begin
        l_found <= lf_c && !rst;
        l_s     <= ls_c;
        l_fired <= (lv_c[4:0] ^ rx_idle) & rx_mask;
        l_dvec  <= cand[5*ls_c +: 5];
        l_fits  <= d_fit[ls_c[LSX:0]];
    end

    // ---- L2: the decision and its reply --------------------------------------------------------------------
    // rx_engine takes this event iff it is armed when its own stage 1 holds the word: now (EARLY = 0), or
    // next clock, with nothing in the word before (EARLY = 1)
    wire       lane_ok = (EARLY != 0) ? rx_arm_next : rx_arm_now;
    // a settled decision a word or more on: the same sample of each later word (dly mod SER after the
    // event's), taken from fs_lane into l_pv a clock before it is used, one word a clock
    reg        pend;
    reg [8:0]  pw;                                 // words still to wait
    reg [2:0]  p_lo;
    reg [4:0]  l_pv;
    wire [8:0] d_new = {5'd0, l_s} + {1'b0, rx_dly};
    wire [2:0] lo_now = pend ? p_lo : (d_new[2:0] & SER_M1[2:0]);
    always @(posedge clk) l_pv <= fs_lane[6*lo_now +: 5];
    wire       ev_new  = l_found && !pend && lane_ok;
    wire       dec_now = pend ? (pw == 9'd0) : (ev_new && (rx_first || l_fits));
    wire [4:0] dvec    = pend ? l_pv : rx_first ? l_fired : l_dvec;
    wire       c_valid = comp_v[dvec];
    wire [3:0] c_pt    = comp_p[{dvec, 2'b00} +: 4];
    wire       fire    = dec_now && c_valid && rp_en && rp_armed;

    // the launch: the decision's point into the pins' register (RP_REG = 0), or a register before it
    reg        fire_q;
    reg [3:0]  c_pt_q;
    always @(posedge clk) begin fire_q <= fire && !rst; c_pt_q <= c_pt; end
    wire       launch    = (RP_REG != 0) ? fire_q : fire;
    wire [3:0] launch_pt = (RP_REG != 0) ? c_pt_q : c_pt;

    reg        r_act;                             // the reply's point held after its first clock
    reg [15:0] r_cnt;
    reg [3:0]  r_pt;
    reg        rp_w_gt1;                          // rp_width > 1, and rp_width - 2: off the reply's path
    reg [15:0] rp_w_m2;
    assign ovr_en = launch || r_act;
    assign ovr_pt = launch ? launch_pt : r_pt;

    reg        f_v;
    reg [4:0]  f_vec;
    wire [2:0] f_le = rx_lut[{f_vec, 2'b00} +: 3];

    always @(posedge clk) begin
        if (rst) begin
            pend <= 1'b0; pw <= 9'd0; p_lo <= 3'd0; r_act <= 1'b0; r_cnt <= 16'd0; r_pt <= 4'd0; reply_ev <= 1'b0;
            rp_en <= 1'b0; rp_once <= 1'b0; rp_rearm <= 1'b0; rp_rearm_rx <= 1'b0; rp_armed <= 1'b0;
            rp_width <= 16'd20; rp_w_gt1 <= 1'b1; rp_w_m2 <= 16'd18;
            rp_map <= 32'h0000_0000; rp_n <= 24'd0; rp_last_dec <= 3'd0; rp_last_rep <= 3'd0;
            f_v <= 1'b0; f_vec <= 5'd0;
        end else begin
            reply_ev <= launch;
            // the decision's sample, a word or more on
            if (pend) begin
                if (pw == 9'd0) pend <= 1'b0;
                else pw <= pw - 1'b1;
            end else if (ev_new && !rx_first && !l_fits) begin
                pend <= 1'b1; pw <= (d_new >> LS) - 1'b1; p_lo <= d_new[2:0] & SER_M1[2:0];
            end
            // the reply on the pins for rp_width clocks: this edge, then r_act for the rest
            rp_w_gt1 <= (rp_width > 16'd1);
            rp_w_m2  <= (rp_width > 16'd1) ? rp_width - 16'd2 : 16'd0;
            if (launch) begin
                r_pt  <= launch_pt;
                r_act <= rp_w_gt1;
                r_cnt <= rp_w_m2;
            end else if (r_act) begin
                if (r_cnt == 16'd0) r_act <= 1'b0;
                else r_cnt <= r_cnt - 1'b1;
            end
            // arming
            if (w_rp) begin
                rp_en <= bus_wdata[0]; rp_once <= bus_wdata[1]; rp_rearm <= bus_wdata[2]; rp_rearm_rx <= bus_wdata[5];
                rp_width <= bus_wdata[31:16];
                rp_n <= 24'd0;
                if (bus_wdata[0] || bus_wdata[3]) rp_armed <= 1'b1;
                if (bus_wdata[4]) rp_armed <= 1'b0;
            end else if (fire && rp_once) rp_armed <= 1'b0;
            else if ((tx_event && rp_rearm) || (rx_rearm && rp_rearm_rx)) rp_armed <= 1'b1;
            if (bus_we && bus_addr == R_RP_MAP) rp_map <= bus_wdata;
            // what was answered, a clock later (off the reply's path)
            f_v <= fire; f_vec <= dvec;
            if (f_v) begin
                rp_n <= rp_n + 1'b1;
                rp_last_dec <= f_le[2:0];
                rp_last_rep <= rp_map[{f_le[2:0], 2'b00} +: 3];
            end
        end
    end

    // =========================================================================================================
    // the fast path
    // =========================================================================================================
    // the samples show it driving the pins: a sample whose vector it drives, while armed
    reg     hit_c;
    integer h;
    always @* begin
        hit_c = 1'b0;
        for (h = 0; h < SER; h = h + 1)
            if (fp_use[fs_lane[6*h +: 5]]) hit_c = 1'b1;
    end
    // the tables' load: written to the masters, then shifted into the LUTs, 32 clocks, entry 31 first
    reg         ld_go, ld_busy, arm_wait;
    reg [4:0]   ld_cnt;
    reg [127:0] ld_f1, ld_f0;                     // bit j's word at [32j+31:32j]: force 1, force 0
    integer     lj, lv;
    reg fp_hit;
    (* dont_touch = "true" *) reg [3:0] fp_arm_c;  // the arm, one copy per ladder bit (each by its pad)
    wire arm_req = FP && ((w_fp && bus_wdata[0]) || (fp_arm_tx && tx_event) || (fp_arm_rx && rx_rearm && !fp_arm));
    always @(posedge clk) begin
        if (rst) begin
            fp_arm <= 1'b0; fp_arm_c <= 4'd0; fp_timed <= 1'b0; fp_arm_tx <= 1'b0; fp_arm_rx <= 1'b0; fp_took <= 1'b0;
            fp_counting <= 1'b0; fp_time <= 32'd1; fp_cnt <= 32'd0; fp_use <= 32'd0; fp_map <= 128'd0; fp_hit <= 1'b0;
            fp_hit_ev <= 1'b0; ld_go <= 1'b0; ld_busy <= 1'b0; ld_cnt <= 5'd0; ld_f1 <= 128'd0; ld_f0 <= 128'd0;
            arm_wait <= 1'b0;
        end else begin
            fp_hit <= fp_arm && hit_c;
            fp_hit_ev <= 1'b0;
            ld_go <= 1'b0;
            if (FP && bus_we) begin
                case (bus_addr)
                R_FP_TIME:  fp_time <= (bus_wdata == 32'd0) ? 32'd1 : bus_wdata;
                R_FP_USE:   begin fp_use <= bus_wdata; ld_go <= 1'b1; end
                R_FP_MAP0:  begin fp_map[31:0]   <= bus_wdata; ld_go <= 1'b1; end
                R_FP_MAP1:  begin fp_map[63:32]  <= bus_wdata; ld_go <= 1'b1; end
                R_FP_MAP2:  begin fp_map[95:64]  <= bus_wdata; ld_go <= 1'b1; end
                R_FP_MAP3:  begin fp_map[127:96] <= bus_wdata; ld_go <= 1'b1; end
                default: ;
                endcase
            end
            // the load (restarted by every write): the LUTs shift while ld_busy, the arm waits for them
            if (ld_go) begin
                ld_busy <= 1'b1; ld_cnt <= 5'd31;
                for (lj = 0; lj < 4; lj = lj + 1)
                    for (lv = 0; lv < 32; lv = lv + 1) begin
                        ld_f1[32*lj + lv] <= fp_use[lv] &  fp_map[4*lv + lj];
                        ld_f0[32*lj + lv] <= fp_use[lv] & ~fp_map[4*lv + lj];
                    end
            end else if (ld_busy) begin
                for (lj = 0; lj < 4; lj = lj + 1) begin
                    ld_f1[32*lj +: 32] <= {ld_f1[32*lj +: 31], 1'b0};
                    ld_f0[32*lj +: 32] <= {ld_f0[32*lj +: 31], 1'b0};
                end
                if (ld_cnt == 5'd0) ld_busy <= 1'b0;
                ld_cnt <= ld_cnt - 1'b1;
            end
            if (FP && w_fp) begin fp_timed <= bus_wdata[2]; fp_arm_tx <= bus_wdata[3]; fp_arm_rx <= bus_wdata[4]; end
            if (ld_go || ld_busy) begin
                // the tables are moving: disarmed, an arming waits for the load's end
                if (fp_arm || arm_req) arm_wait <= 1'b1;
                fp_arm <= 1'b0; fp_arm_c <= 4'h0;
                if (w_fp && bus_wdata[1]) arm_wait <= 1'b0;
            end else if (arm_req || arm_wait) begin
                fp_arm <= 1'b1; fp_arm_c <= 4'hF; fp_took <= 1'b0; fp_hit <= 1'b0; arm_wait <= 1'b0;
                fp_counting <= (w_fp && bus_wdata[0]) ? bus_wdata[2] : fp_timed;
                fp_cnt <= fp_time - 1'b1;
            end else if (w_fp && bus_wdata[1]) begin
                fp_arm <= 1'b0; fp_arm_c <= 4'h0; fp_counting <= 1'b0;
            end else if (fp_arm) begin
                if (fp_hit && !fp_took) begin
                    fp_took <= 1'b1; fp_hit_ev <= 1'b1;
                    if (!fp_timed) begin fp_counting <= 1'b1; fp_cnt <= fp_time - 1'b1; end
                end
                if (fp_counting) begin
                    if (fp_cnt == 32'd0) begin fp_arm <= 1'b0; fp_arm_c <= 4'h0; fp_counting <= 1'b0; end
                    else fp_cnt <= fp_cnt - 1'b1;
                end
            end
        end
    end

    genvar fb;
    generate
        if (FAST_PATH != 0) begin : g_fast
            // the combinational path, one per ladder bit: "force 1" and "force 0" looked up by the
            // comparators' vector (one reloadable LUT each), then the arm and the registered pin
            for (fb = 0; fb < 4; fb = fb + 1) begin : g_bit
                wire f1, f0;
                fp_lut5 u_f1 (.clk(clk), .ce(ld_busy), .cdi(ld_f1[32*fb + 31]), .a(cmp_async), .o(f1));
                fp_lut5 u_f0 (.clk(clk), .ce(ld_busy), .cdi(ld_f0[32*fb + 31]), .a(cmp_async), .o(f0));
                assign pins_out[fb] = (fp_arm_c[fb] && f1) || (pins_reg[fb] && !(fp_arm_c[fb] && f0));
            end
        end else begin : g_nofast
            assign pins_out = pins_reg;
            wire _unused_fp = &{1'b0, cmp_async, fp_arm_c, ld_f1, ld_f0};
        end
    endgenerate

    // =========================================================================================================
    // the turnaround counter
    // =========================================================================================================
    // stage A: where the watched comparators changed this clock (the previous clock's last sample counts)
    reg  [4:0] a_prev;
    reg        chg_any;
    reg  [3:0] chg_first, chg_last;
    reg  [4:0] pv, cv;
    integer    m;
    always @* begin
        chg_any = 1'b0; chg_first = 4'd0; chg_last = 4'd0;
        for (m = 0; m < SER; m = m + 1) begin
            cv = fs[6*m +: 5] & rt_mask;
            pv = (m == 0) ? a_prev : (fs[6*m - 6 +: 5] & rt_mask);
            if (cv != pv) begin
                if (!chg_any) chg_first = m[3:0];
                chg_any = 1'b1; chg_last = m[3:0];
            end
        end
    end
    reg        a_any;
    reg [3:0]  a_first, a_last;
    reg [31:0] a_t0;
    // stage B: an arrival is a change after rt_guard samples of quiet (q: samples since the last change)
    reg [15:0] qs;
    reg        b_mark;
    reg [31:0] b_t;
    wire [16:0] q_first = {1'b0, qs} + {13'd0, a_first};
    // the reference: RX's (RX_CTRL[3]: this board's TX event, or TRIG_IN's rising sample), with its time
    reg        c_ref;
    reg [31:0] c_tref;
    // the pairing after a reference
    localparam [1:0] T_IDLE = 2'd0, T_W1 = 2'd1, T_W2 = 2'd2;
    reg [1:0]  t_st;
    reg [31:0] t_ref, t_1, t_3;
    reg [7:0]  t_wait;
    reg        p_done, d_v;
    reg [15:0] d_rt, d_l1;
    // the fast path's armed window in samples (the ring's hops)
    reg        fa_d;
    reg [31:0] t_on, t_off;
    reg        m_have;
    reg [31:0] m_first, m_lastt;
    wire [31:0] t_end   = fp_arm ? t0 : t_off;
    wire        in_win  = !(FP && rt_ring) || ((b_t - t_on) < (t_end - t_on));

    always @(posedge clk) begin
        a_prev <= fs[6*(SER-1) +: 5] & rt_mask;
        a_any <= chg_any; a_first <= chg_first; a_last <= chg_last; a_t0 <= t0;
        c_ref <= rx_ref; c_tref <= rx_t_ref;
        fa_d <= fp_arm;
        if (fp_arm && !fa_d) t_on <= t0;
        if (!fp_arm && fa_d) t_off <= t0;
        if (rst) begin
            qs <= 16'hFFFF; b_mark <= 1'b0; b_t <= 32'd0;
            rt_en <= 1'b0; rt_ring <= 1'b0; rt_mask <= 5'h1F; rt_guard <= 8'd8; rt_win <= 8'd0;
            rt_last <= 32'd0; rt_sum <= 32'd0; rt_n <= 32'd0; rt_miss <= 32'd0; rt_marks <= 32'd0; rt_span <= 32'd0;
            rt_min <= 16'hFFFF; rt_max <= 16'd0;
            t_st <= T_IDLE; t_ref <= 32'd0; t_1 <= 32'd0; t_3 <= 32'd0; t_wait <= 8'd0;
            p_done <= 1'b0; d_v <= 1'b0; d_rt <= 16'd0; d_l1 <= 16'd0;
            m_have <= 1'b0; m_first <= 32'd0; m_lastt <= 32'd0;
            t_on <= 32'd0; t_off <= 32'd0;
        end else begin
            // stage B
            b_mark <= a_any && (q_first >= {9'd0, rt_guard});
            b_t    <= a_t0 | {28'd0, a_first};
            if (a_any) qs <= SER16 - {12'd0, a_last};
            else       qs <= (qs > 16'hFFFF - SER16) ? 16'hFFFF : qs + SER16;

            // the pairing
            p_done <= 1'b0;
            if (c_ref && rt_en) begin
                if (t_st != T_IDLE) rt_miss <= rt_miss + 1'b1;
                t_st <= T_W1; t_ref <= c_tref;
            end else begin
                case (t_st)
                T_W1: if (b_mark) begin t_1 <= b_t; t_st <= T_W2; t_wait <= 8'd0; end
                T_W2: if (b_mark) begin t_3 <= b_t; t_st <= T_IDLE; p_done <= 1'b1; end
                      else if (rt_win != 8'd0 && t_wait >= rt_win) begin t_st <= T_IDLE; rt_miss <= rt_miss + 1'b1; end
                      else t_wait <= t_wait + 1'b1;
                default: ;
                endcase
            end
            // the latencies, then the statistics
            d_v  <= p_done;
            d_rt <= sat16(t_3 - t_1);
            d_l1 <= sat16(t_1 - t_ref);
            if (d_v) begin
                rt_last <= {d_l1, d_rt};
                rt_sum  <= rt_sum + {16'd0, d_rt};
                rt_n    <= rt_n + 1'b1;
                if (d_rt < rt_min) rt_min <= d_rt;
                if (d_rt > rt_max) rt_max <= d_rt;
            end
            // every arrival (inside the fast path's window with RT_CFG[2]): the ring's hops
            if (b_mark && rt_en && in_win) begin
                rt_marks <= rt_marks + 1'b1;
                if (!m_have) begin m_have <= 1'b1; m_first <= b_t; end
                m_lastt <= b_t;
            end
            rt_span <= m_lastt - m_first;

            if (w_rt) begin
                rt_en <= bus_wdata[0]; rt_ring <= bus_wdata[2]; rt_mask <= bus_wdata[12:8];
                rt_guard <= bus_wdata[23:16]; rt_win <= bus_wdata[31:24];
                if (bus_wdata[1]) begin
                    rt_last <= 32'd0; rt_sum <= 32'd0; rt_n <= 32'd0; rt_miss <= 32'd0; rt_marks <= 32'd0;
                    rt_min <= 16'hFFFF; rt_max <= 16'd0; m_have <= 1'b0; m_first <= 32'd0; m_lastt <= 32'd0;
                    t_st <= T_IDLE; d_v <= 1'b0;
                end
            end
        end
    end

    // ---- reads ---------------------------------------------------------------------------------------------
    always @* begin
        case (bus_addr)
        R_RP_CTRL:  bus_rdata = {rp_width, 7'd0, rp_armed, 2'd0, rp_rearm_rx, 2'd0, rp_rearm, rp_once, rp_en};
        R_RP_MAP:   bus_rdata = rp_map;
        R_RP_STAT:  bus_rdata = {rp_n, 1'b0, rp_last_rep, 1'b0, rp_last_dec};
        R_FP_CTRL:  bus_rdata = {23'd0, FP, 2'd0, ld_busy || ld_go, fp_arm_rx, fp_arm_tx, fp_timed, fp_took, fp_arm};
        R_FP_TIME:  bus_rdata = fp_time;
        R_FP_USE:   bus_rdata = fp_use;
        R_FP_MAP0:  bus_rdata = fp_map[31:0];
        R_FP_MAP1:  bus_rdata = fp_map[63:32];
        R_FP_MAP2:  bus_rdata = fp_map[95:64];
        R_FP_MAP3:  bus_rdata = fp_map[127:96];
        R_RT_CFG:   bus_rdata = {rt_win, rt_guard, 3'd0, rt_mask, 5'd0, rt_ring, 1'b0, rt_en};
        R_RT_LAST:  bus_rdata = rt_last;
        R_RT_MIN:   bus_rdata = {16'd0, rt_min};
        R_RT_MAX:   bus_rdata = {16'd0, rt_max};
        R_RT_SUM:   bus_rdata = rt_sum;
        R_RT_N:     bus_rdata = rt_n;
        R_RT_MISS:  bus_rdata = rt_miss;
        R_RT_MARKS: bus_rdata = rt_marks;
        R_RT_SPAN:  bus_rdata = rt_span;
        default:    bus_rdata = 32'hDEAD_0000 | {24'd0, bus_addr};
        endcase
    end

    wire _unused = &{1'b0, fs[6*SER-1 -: 1], fp_took};
endmodule
