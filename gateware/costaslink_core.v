// costaslink_core: everything the CostasLink's gateware does that does not depend on the FPGA board
// (Response 15).  Plain Verilog-2005: Yosys (Icepi Zero, ECP5) and Vivado (PYNQ-Z2, Zynq) read the same
// files, and Vivado's block design takes the PYNQ's wrapper as a module reference, which a SystemVerilog
// top cannot be.
//
// The boards differ in three things only, all outside this module:
//   * the fast sampler: SER samples a clock of the six fast inputs (ISERDESE2 8:1 on the PYNQ-Z2,
//     IDDRX1F 2:1 on the Icepi Zero, a plain flip-flop in simulation), `fs` here; on the PYNQ-Z2 also its
//     word a clock earlier (`fs_lane`, EARLY), the comparators' combinational values (`cmp_async`, for the
//     fast path: FAST_PATH) and the ladder pins read back by their own ISERDESE2s (`fs_tx`, TXFB);
//   * the clocks (an MMCM from the PS's FCLK0; an EHXPLLL from the Icepi's 50 MHz);
//   * the way in to the register bus (AXI-Lite from the PS: axil_bridge.v; the UART: uart_cmd.v).
// The bus: 8-bit register numbers, 32-bit data, one-clock bus_we / bus_re pulses.  A write takes effect two
// clocks after bus_we (bus_stage.v, then the block's register); bus_rdata shows the register the address
// named three clocks before (READ_LAT below; both bridges hold the address that long before taking the
// data).  regmap.py has the map.
//
// Blocks: costaslink_regs (control pins, SPI, I2C, the first firmware's counters, 0x00-0x2F),
// tx_engine (0x30-0x3F), rx_engine (0x40-0x5F), seq_gate (0x60-0x6F), capture (0x78-0x7F), BUILD (0x80),
// turnaround (the synchronous reply, the fast path, the turnaround counter: 0x90-0xAF).

module costaslink_core #(
    parameter integer CLK_HZ        = 100_000_000,
    parameter integer SER           = 8,
    parameter integer CAP_AW        = 12,
    parameter integer BOARD         = 0,        // 0 simulation, 1 PYNQ-Z2, 2 Icepi Zero
    parameter integer EARLY         = 0,        // 1: fs_lane is fs a clock early (the reply lane reads it)
    parameter integer FAST_PATH     = 0,        // 1: the combinational path from cmp_async to the ladder pins
    parameter integer TXFB          = 0,        // 1: fs_tx (the ladder pins' samples) goes into the capture
    parameter integer RP_REG        = 1,        // 1: the synchronous reply a clock later (turnaround.v)
    parameter integer ID_WPM        = 20,
    parameter integer ID_INTERVAL_S = 600,
    parameter integer CALLSIGN_LEN  = 4,
    parameter [8*CALLSIGN_LEN-1:0] CALLSIGN = "W3JQ"
) (
    input  wire             clk,
    input  wire             rst,
    // the register bus
    input  wire [7:0]       bus_addr,
    input  wire [31:0]      bus_wdata,
    input  wire             bus_we,
    input  wire             bus_re,
    output reg  [31:0]      bus_rdata,
    // the fast inputs, sampled: sample s (0 the earliest) in [6s+5:6s] =
    // {TRIG_IN, CMP_IN, CMP_IP, CMP_QN, CMP_QP, CMP_I}, synchronous to clk
    input  wire [6*SER-1:0] fs,
    input  wire [6*SER-1:0] fs_lane,            // fs a clock early (EARLY), else fs itself
    input  wire [4:0]       cmp_async,          // {CMP_IN CMP_IP CMP_QN CMP_QP CMP_I} straight from the pins (FAST_PATH)
    input  wire [4*SER-1:0] fs_tx,              // the ladder pins' samples, sample s of {Q1 Q0 I1 I0} in [4s+3:4s] (TXFB)
    // the slow inputs, asynchronous (synchronised here)
    input  wire             cmp_i_s,
    input  wire             cmp_qp_s,
    input  wire             cmp_qn_s,
    input  wire             mux_tx,
    input  wire             mux_rx,
    // I2C, open drain: _o = 1 releases the line (the board top makes the tri-state)
    input  wire             i2c_scl_i,
    input  wire             i2c_sda_i,
    output wire             i2c_scl_o,
    output wire             i2c_sda_o,
    // the pins
    output wire             tx_i1,
    output wire             tx_i0,
    output wire             tx_q1,
    output wire             tx_q1_hiz,          // CTRL[8]: TX_Q1 an input (the board's TRIG IN bypass)
    output wire             tx_q0,
    output wire             spi_sclk,
    output wire             spi_sdata,
    output wire             le_pll_tx,
    output wire             le_pll_rx,
    output wire             le_dsa,
    output wire             loop_hold,
    output wire             loop_sel,
    output wire             tx_dis,
    output wire             trig_a,
    output wire             trig_b,
    output wire             tr_a
);
`include "regmap.vh"
    localparam integer CLK_MHZ = CLK_HZ / 1_000_000;
    localparam [15:0]  CLK_MHZ16 = CLK_MHZ[15:0];
    localparam [3:0]   BOARD4 = BOARD[3:0];
    localparam [7:0]   SER8 = SER[7:0];
    localparam         EARLY1 = (EARLY != 0), TXFB1 = (TXFB != 0), FAST1 = (FAST_PATH != 0), RPREG1 = (RP_REG != 0);

    // ---- the inputs ------------------------------------------------------------------------------------
    // ---- the bus and the reset, registered once beside each block (bus_stage.v): every block sees a write or
    // a read a clock after the bridge put it out
    wire        rst_regs, rst_seq, rst_tx, rst_rx, rst_cap, rst_core, rst_lat;
    wire [7:0]  a_regs, a_seq, a_tx, a_rx, a_cap, a_core, a_lat;
    wire [31:0] d_regs, d_seq, d_tx, d_rx, d_cap, d_core, d_lat;
    wire        we_regs, we_seq, we_tx, we_rx, we_cap, we_core, we_lat;
    wire        re_regs, re_rx, re_cap;
    /* verilator lint_off PINCONNECTEMPTY */
    bus_stage u_bs_regs (.clk(clk), .rst(rst), .addr(bus_addr), .wdata(bus_wdata), .we(bus_we), .re(bus_re),
        .rst_q(rst_regs), .addr_q(a_regs), .wdata_q(d_regs), .we_q(we_regs), .re_q(re_regs));
    bus_stage u_bs_seq (.clk(clk), .rst(rst), .addr(bus_addr), .wdata(bus_wdata), .we(bus_we), .re(1'b0),
        .rst_q(rst_seq), .addr_q(a_seq), .wdata_q(d_seq), .we_q(we_seq), .re_q());
    bus_stage u_bs_tx (.clk(clk), .rst(rst), .addr(bus_addr), .wdata(bus_wdata), .we(bus_we), .re(1'b0),
        .rst_q(rst_tx), .addr_q(a_tx), .wdata_q(d_tx), .we_q(we_tx), .re_q());
    bus_stage u_bs_rx (.clk(clk), .rst(rst), .addr(bus_addr), .wdata(bus_wdata), .we(bus_we), .re(bus_re),
        .rst_q(rst_rx), .addr_q(a_rx), .wdata_q(d_rx), .we_q(we_rx), .re_q(re_rx));
    bus_stage u_bs_cap (.clk(clk), .rst(rst), .addr(bus_addr), .wdata(bus_wdata), .we(bus_we), .re(bus_re),
        .rst_q(rst_cap), .addr_q(a_cap), .wdata_q(d_cap), .we_q(we_cap), .re_q(re_cap));
    bus_stage u_bs_core (.clk(clk), .rst(rst), .addr(bus_addr), .wdata(bus_wdata), .we(bus_we), .re(1'b0),
        .rst_q(rst_core), .addr_q(a_core), .wdata_q(d_core), .we_q(we_core), .re_q());
    bus_stage u_bs_lat (.clk(clk), .rst(rst), .addr(bus_addr), .wdata(bus_wdata), .we(bus_we), .re(1'b0),
        .rst_q(rst_lat), .addr_q(a_lat), .wdata_q(d_lat), .we_q(we_lat), .re_q());
    /* verilator lint_on PINCONNECTEMPTY */
    wire rst_mon = rst_regs;

    // the fast inputs as plain pins for the first firmware's counters: each clock's last sample
    wire [5:0] fs_last = fs[6*(SER-1) +: 6];
    reg  [4:0] slow_s1, slow_s2;                // {MUX_RX, MUX_TX, CMP_QN_S, CMP_QP_S, CMP_I_S}
    always @(posedge clk) begin
        slow_s1 <= {mux_rx, mux_tx, cmp_qn_s, cmp_qp_s, cmp_i_s};
        slow_s2 <= slow_s1;
    end

    // ---- the register file ---------------------------------------------------------------------------------
    wire        ctrl_tx_dis, ctrl_loop_hold, ctrl_loop_sel, ctrl_tr_a, ctrl_id_enable, ctrl_txq1_hiz, id_now;
    wire        sym_we, pat_start, pat_stop, pat_running;
    wire [3:0]  sym_wdata;
    wire [31:0] pat_period, pat_width;
    wire [15:0] pat_count;
    wire [7:0]  trig_width;
    wire        trig_a_en, trig_b_en, trig_b_rise_only, cnt_clear;
    wire [1:0]  trig_a_src, trig_b_src;
    wire [10:0] cmp_state;
    wire [31:0] free_cnt, cmp_i_ts;
    wire [255:0] edge_cnts;
    wire [17:0] latency;
    wire        id_active, id_key;
    wire [15:0] id_secs;
    wire [1:0]  pin_i, pin_q;
    wire [31:0] regs_rdata, tx_rdata, rx_rdata, seq_rdata, cap_rdata, lat_rdata;
    wire [3:0]  pins_reg = {pin_q, pin_i};       // the ladder pins' register (tx_engine), with a synchronous reply
    wire [3:0]  pins_out;                       // what drives the pads: with the fast path's entry while it drives

    costaslink_regs #(.CLK_HZ(CLK_HZ)) u_regs (
        .clk(clk), .rst(rst_regs),
        .bus_addr(a_regs), .bus_wdata(d_regs), .bus_we(we_regs), .bus_re(re_regs), .bus_rdata(regs_rdata),
        .ctrl_tx_dis(ctrl_tx_dis), .ctrl_loop_hold(ctrl_loop_hold), .ctrl_loop_sel(ctrl_loop_sel),
        .ctrl_tr_a(ctrl_tr_a), .ctrl_id_enable(ctrl_id_enable), .ctrl_txq1_hiz(ctrl_txq1_hiz), .id_now(id_now),
        .sym_we(sym_we), .sym_wdata(sym_wdata), .pat_period(pat_period), .pat_width(pat_width),
        .pat_count(pat_count), .pat_start(pat_start), .pat_stop(pat_stop), .sym_cur({pin_q, pin_i}), .pat_running(pat_running),
        .trig_width(trig_width), .trig_a_en(trig_a_en), .trig_b_en(trig_b_en), .trig_b_rise_only(trig_b_rise_only),
        .trig_a_src(trig_a_src), .trig_b_src(trig_b_src),
        .cnt_clear(cnt_clear), .cmp_state(cmp_state), .free_cnt(free_cnt), .edge_cnts(edge_cnts),
        .cmp_i_ts(cmp_i_ts), .latency(latency),
        .id_active(id_active), .id_key(id_key), .id_secs(id_secs),
        .spi_sclk(spi_sclk), .spi_sdata(spi_sdata), .le_pll_tx(le_pll_tx), .le_pll_rx(le_pll_rx), .le_dsa(le_dsa),
        .i2c_scl_i(i2c_scl_i), .i2c_sda_i(i2c_sda_i), .i2c_scl_o(i2c_scl_o), .i2c_sda_o(i2c_sda_o));

    // ---- the first firmware's counters, latency and triggers (the legacy sources of TRIG_A / TRIG_B) ---------
    wire sym_change, legacy_trig_a, legacy_trig_b;
    cmp_monitor u_mon (
        .clk(clk), .rst(rst_mon),
        .cmp_i(fs_last[0]), .cmp_qp(fs_last[1]), .cmp_qn(fs_last[2]),
        .cmp_i_s(slow_s2[0]), .cmp_qp_s(slow_s2[1]), .cmp_qn_s(slow_s2[2]),
        .trig_in(fs_last[5]), .mux_tx(slow_s2[3]), .mux_rx(slow_s2[4]), .cmp_ip(fs_last[3]), .cmp_in(fs_last[4]),
        .clear(cnt_clear), .sym_change(sym_change), .trig_width(trig_width),
        .trig_a_en(trig_a_en), .trig_b_en(trig_b_en), .trig_b_rise_only(trig_b_rise_only),
        .state(cmp_state), .free_cnt(free_cnt), .edge_cnts(edge_cnts), .cmp_i_ts(cmp_i_ts), .latency(latency),
        .trig_a(legacy_trig_a), .trig_b(legacy_trig_b));

    // ---- the sequencer and the gate ---------------------------------------------------------------------------
    wire       seq_active;
    wire [3:0] seq_out;
    wire       seq_step;
    wire       rx_ev_p, rx_dec_p, rx_valid_p, trig_in_rise;
    seq_gate #(.SER(SER)) u_seq (
        .clk(clk), .rst(rst_seq), .bus_addr(a_seq), .bus_wdata(d_seq), .bus_we(we_seq), .bus_rdata(seq_rdata),
        .fs(fs), .slow(slow_s2[2:0]), .rx_event(rx_ev_p), .seq_active(seq_active), .seq_out(seq_out),
        .seq_step(seq_step));
    wire tx_gate = seq_active ? seq_out[3] : 1'b1;

    // ---- the transmitter ----------------------------------------------------------------------------------------
    wire       tx_event, tx_busy;
    wire [2:0] tx_msg;
    wire       ovr_en;
    wire [3:0] ovr_pt;
    wire [31:0] tx_points;
    tx_engine u_tx (
        .clk(clk), .rst(rst_tx), .bus_addr(a_tx), .bus_wdata(d_tx), .bus_we(we_tx), .bus_rdata(tx_rdata),
        .sym_we(sym_we), .sym_wdata(sym_wdata), .pat_period(pat_period), .pat_width(pat_width), .pat_count(pat_count),
        .pat_start(pat_start), .pat_stop(pat_stop), .pat_running(pat_running),
        .free_cnt(free_cnt), .trig_in_rise(trig_in_rise), .seq_gate(tx_gate),
        .ovr_en(ovr_en), .ovr_pt(ovr_pt), .points_o(tx_points),
        .tx_i(pin_i), .tx_q(pin_q), .sym_change(sym_change), .tx_event(tx_event), .tx_msg(tx_msg), .tx_busy(tx_busy));

    // TX_PERIOD for the receiver's BER check (the transmitter's register, read back through the bus path)
    reg [31:0] tx_period_copy;
    always @(posedge clk)
        if (rst_core) tx_period_copy <= 32'd1000;
        else if (we_core && a_core == R_TX_PERIOD) tx_period_copy <= (d_core == 32'd0) ? 32'd1 : d_core;

    // ---- the receiver ------------------------------------------------------------------------------------------------
    wire [4:0]   rx_cfg_idle, rx_cfg_mask;
    wire [127:0] rx_cfg_lut;
    wire         rx_cfg_first, rx_arm_now, rx_arm_next, rx_ref_now;
    wire [31:0]  rx_t_ref;
    wire [7:0]   rx_cfg_dly;
    wire rx_ihold;                              // the interference hold: LOOP_HOLD while the comparators chatter
    rx_engine #(.SER(SER), .CLK_HZ(CLK_HZ)) u_rx (
        .clk(clk), .rst(rst_rx), .bus_addr(a_rx), .bus_wdata(d_rx), .bus_we(we_rx), .bus_re(re_rx),
        .bus_rdata(rx_rdata), .fs(fs), .slow(slow_s2[2:0]), .free_cnt(free_cnt),
        .tx_event(tx_event), .tx_msg(tx_msg), .sym_period(tx_period_copy),
        .ev_pulse(rx_ev_p), .dec_pulse(rx_dec_p), .valid_pulse(rx_valid_p), .trig_in_rise(trig_in_rise),
        .cfg_idle(rx_cfg_idle), .cfg_mask(rx_cfg_mask), .cfg_lut(rx_cfg_lut), .cfg_first(rx_cfg_first),
        .cfg_dly(rx_cfg_dly), .arm_now(rx_arm_now), .arm_next(rx_arm_next),
        .ref_now_o(rx_ref_now), .t_ref_o(rx_t_ref), .ihold_o(rx_ihold));

    // ---- the receive-to-transmit paths: the synchronous reply, the fast path, the turnaround counter ---------
    wire reply_ev, fp_hit_ev, fp_armed;
    turnaround #(.SER(SER), .EARLY(EARLY), .FAST_PATH(FAST_PATH), .RP_REG(RP_REG)) u_lat (
        .clk(clk), .rst(rst_lat), .bus_addr(a_lat), .bus_wdata(d_lat), .bus_we(we_lat), .bus_rdata(lat_rdata),
        .fs(fs), .fs_lane(fs_lane), .cmp_async(cmp_async), .free_cnt(free_cnt),
        .rx_idle(rx_cfg_idle), .rx_mask(rx_cfg_mask), .rx_lut(rx_cfg_lut), .rx_first(rx_cfg_first),
        .rx_dly(rx_cfg_dly), .rx_arm_now(rx_arm_now), .rx_arm_next(rx_arm_next),
        .rx_ref(rx_ref_now), .rx_t_ref(rx_t_ref),
        .tx_points(tx_points), .tx_event(tx_event), .ovr_en(ovr_en), .ovr_pt(ovr_pt),
        .pins_reg(pins_reg), .pins_out(pins_out), .reply_ev(reply_ev), .fp_hit_ev(fp_hit_ev), .fp_arm(fp_armed));
    wire reply_any = reply_ev || fp_hit_ev;

    // ---- the station identification ------------------------------------------------------------------------------
    morse_keyer #(.CLK_HZ(CLK_HZ), .WPM(ID_WPM), .INTERVAL_S(ID_INTERVAL_S),
                  .CALLSIGN_LEN(CALLSIGN_LEN), .CALLSIGN(CALLSIGN)) u_id (
        .clk(clk), .rst(rst_core), .enable(ctrl_id_enable), .send_now(id_now),
        .active(id_active), .key(id_key), .secs_to_id(id_secs));

    // ---- the control pins: the sequencer's while it runs, else CTRL's; the identification keys TX_DIS ------------
    assign tx_dis    = id_active ? ~id_key : (seq_active ? seq_out[2] : ctrl_tx_dis);
    assign loop_hold = seq_active ? seq_out[1] : (ctrl_loop_hold | rx_ihold);     // the interference hold (ihold.v)
    assign tr_a      = seq_active ? seq_out[0] : ctrl_tr_a;
    assign loop_sel  = ctrl_loop_sel;
    assign {tx_q1, tx_q0, tx_i1, tx_i0} = pins_out;
    assign tx_q1_hiz = ctrl_txq1_hiz;

    // ---- the triggers: TRIG_CFG[12:11] and [14:13] choose the source, [7:0] the pulse width ---------------------
    reg  [7:0] a_cnt, b_cnt;
    wire       a_new = ((trig_a_src == 2'd1) && tx_event) || ((trig_a_src == 2'd2) && reply_any);
    wire       b_new = (trig_b_src == 2'd1) ? rx_ev_p : (trig_b_src == 2'd2) ? rx_dec_p :
                       (trig_b_src == 2'd3) ? rx_valid_p : 1'b0;
    always @(posedge clk) begin
        if (rst_core) begin a_cnt <= 8'd0; b_cnt <= 8'd0; end
        else begin
            if (a_new) a_cnt <= (trig_width == 8'd0) ? 8'd1 : trig_width;
            else if (a_cnt != 8'd0) a_cnt <= a_cnt - 1'b1;
            if (b_new) b_cnt <= (trig_width == 8'd0) ? 8'd1 : trig_width;
            else if (b_cnt != 8'd0) b_cnt <= b_cnt - 1'b1;
        end
    end
    assign trig_a = (trig_a_src == 2'd0) ? legacy_trig_a : (a_cnt != 8'd0);
    assign trig_b = (trig_b_src == 2'd0) ? legacy_trig_b : (b_cnt != 8'd0);

    // ---- the capture buffer --------------------------------------------------------------------------------------
    wire [15:0] ctx = {reply_ev || fp_armed, rx_dec_p, rx_ev_p, tx_event, pin_q, pin_i, tx_dis, loop_hold, tr_a,
                       slow_s2[2], slow_s2[1], slow_s2[0], slow_s2[3], slow_s2[4]};
    capture #(.SER(SER), .AW(CAP_AW), .TXFB(TXFB)) u_cap (
        .clk(clk), .rst(rst_cap), .bus_addr(a_cap), .bus_wdata(d_cap), .bus_we(we_cap), .bus_re(re_cap),
        .bus_rdata(cap_rdata), .fs(fs), .ctx(ctx), .fs_tx(fs_tx),
        .t_tx(tx_event), .t_rxev(rx_ev_p), .t_trig(trig_in_rise), .t_rxdec(rx_dec_p), .t_seq(seq_step),
        .t_reply(reply_any));

    // ---- reads: the bus stage, then each block's read mux registered (regs_q ...), then the choice among the
    // blocks registered (bus_rdata), so each is a clock's path of its own (the Icepi's read path closed at
    // 75 MHz in one clock).  bus_rdata is the register the address named three clocks before (READ_LAT = 3).
    // A read's side effects (count_ram's and the capture's next address) take place at the edge that sees
    // the block's copy of bus_re, the same edge that registers the block's data, so every read returns the
    // state before its own step.  axil_bridge.v takes the data four clocks after its bus_re; uart_cmd.v in
    // bus_re's clock, from an address that has stood since the line's hex digits (thousands of clocks): also
    // the state before the step.
    reg [31:0] regs_q, tx_q, rx_q, seq_q, cap_q, lat_q;
    reg [2:0]  rsel;
    reg [7:0]  addr_q;
    always @(posedge clk) begin
        regs_q <= regs_rdata; tx_q <= tx_rdata; rx_q <= rx_rdata; seq_q <= seq_rdata; cap_q <= cap_rdata;
        lat_q <= lat_rdata;
        addr_q <= a_core;
        if (a_core <= 8'h2F)      rsel <= 3'd0;
        else if (a_core <= 8'h3F) rsel <= 3'd1;
        else if (a_core <= 8'h5F) rsel <= 3'd2;
        else if (a_core <= 8'h6F) rsel <= 3'd3;
        else if (a_core <= 8'h77) rsel <= 3'd2;          // the receiver's second window (ber_cdr, ihold)
        else if (a_core >= 8'h78 && a_core <= 8'h7F) rsel <= 3'd4;
        else if (a_core == R_BUILD) rsel <= 3'd5;
        else if (a_core <= 8'h8F) rsel <= 3'd2;          // the receiver's third window (the signal holdover)
        else if (a_core >= 8'h90 && a_core <= 8'hAF) rsel <= 3'd6;
        else rsel <= 3'd7;
    end
    always @(posedge clk) begin
        case (rsel)
        3'd0:    bus_rdata <= regs_q;
        3'd1:    bus_rdata <= tx_q;
        3'd2:    bus_rdata <= rx_q;
        3'd3:    bus_rdata <= seq_q;
        3'd4:    bus_rdata <= cap_q;
        3'd5:    bus_rdata <= {CLK_MHZ16, RPREG1, EARLY1, TXFB1, FAST1, BOARD4, SER8};
        3'd6:    bus_rdata <= lat_q;
        default: bus_rdata <= 32'hDEAD_0000 | {24'd0, addr_q};
        endcase
    end

    // unused: the TX busy flag (in TX_GO), the TRIG_IN bit of the slow copy
    wire _unused = &{1'b0, tx_busy};
endmodule
