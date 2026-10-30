// costaslink_top: the generic top (Response 15): the UART bridge, a plain flip-flop as the fast sampler (one
// sample a clock) and costaslink_core.v.  It builds anywhere (`make synth`, `make pnr` for an Icepi Zero
// without the DDR sampler) and it is what the first firmware's testbench (tb_costaslink.v) drives.  The
// boards' own tops: top_icepi.v (Icepi Zero: PLL, IDDRX1F, UART) and costaslink_pynq.v (PYNQ-Z2: AXI-Lite,
// ISERDESE2, in Vivado's block design).
//
// Ports are the header signals of gen/pins.py in lower case, as gateware/pynq_z2.xdc and
// gateware/icepi_zero.lpf name them, plus `sysclk` and the UART pair.

module costaslink_top #(
    parameter integer CLK_HZ        = 50_000_000,
    parameter integer BAUD          = 115200,
    parameter integer ID_WPM        = 20,
    parameter integer ID_INTERVAL_S = 600,
    parameter integer CALLSIGN_LEN  = 4,
    parameter [8*CALLSIGN_LEN-1:0] CALLSIGN = "W3JQ"
) (
    input  wire sysclk,
    inout  wire i2c_sda,
    inout  wire i2c_scl,
    output wire tx_i1,
    output wire tx_i0,
    output wire tx_q1,
    output wire tx_q0,
    input  wire cmp_qn,
    input  wire cmp_qp,
    input  wire cmp_i,
    input  wire cmp_i_s,
    input  wire cmp_qn_s,
    input  wire cmp_qp_s,
    input  wire cmp_ip,
    input  wire cmp_in,
    output wire spi_sclk,
    output wire spi_sdata,
    output wire le_pll_tx,
    output wire le_pll_rx,
    output wire le_dsa,
    output wire loop_hold,
    output wire loop_sel,
    output wire tx_en,                    // header 24: high transmits (the core's TX_DIS inverted)
    input  wire trig_in,
    output wire trig_a,
    output wire trig_b,
    output wire tr_a,
    input  wire mux_tx,
    input  wire mux_rx,
    input  wire uart_rx,
    output wire uart_tx
);
    // ---- power-on reset: 16 clocks after configuration (the flip-flops start at 0 on both FPGAs) --------
    /* verilator lint_off PROCASSINIT */
    reg [4:0] por = 5'd0;
    /* verilator lint_on PROCASSINIT */
    wire rst = ~por[4];
    always @(posedge sysclk) if (!por[4]) por <= por + 1'b1;

    // ---- the UART bridge ----------------------------------------------------------------------------------
    wire [7:0]  rx_data, tx_data, bus_addr;
    wire        rx_valid, tx_start, tx_busy, bus_we, bus_re;
    wire [31:0] bus_wdata, bus_rdata;
    uart_rx  #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_rx (.clk(sysclk), .rst(rst), .rx(uart_rx), .data(rx_data), .valid(rx_valid));
    uart_tx  #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_tx (.clk(sysclk), .rst(rst), .data(tx_data), .start(tx_start), .tx(uart_tx), .busy(tx_busy));
    uart_cmd u_cmd (.clk(sysclk), .rst(rst), .rx_data(rx_data), .rx_valid(rx_valid),
                    .tx_data(tx_data), .tx_start(tx_start), .tx_busy(tx_busy),
                    .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata));

    // ---- the fast sampler: two flip-flops, one sample a clock ---------------------------------------------------
    wire [5:0] fs;
    fast_sampler_flop #(.N(6)) u_fs (.clk(sysclk), .d({trig_in, cmp_in, cmp_ip, cmp_qn, cmp_qp, cmp_i}), .q(fs));

    // ---- the core ------------------------------------------------------------------------------------------------
    wire scl_o, sda_o, q1, q1_hiz;
    // TX_EN on the header is the core's TX_DIS inverted (Response 15, REVA_CHANGES.md 2): the board's 1 k
    // holds the pin low, and so the modulator off, whenever no gateware drives it
    wire tx_dis_core;
    assign tx_en = ~tx_dis_core;

    costaslink_core #(.CLK_HZ(CLK_HZ), .SER(1), .CAP_AW(10), .BOARD(0), .ID_WPM(ID_WPM), .ID_INTERVAL_S(ID_INTERVAL_S),
                      .CALLSIGN_LEN(CALLSIGN_LEN), .CALLSIGN(CALLSIGN)) u_core (
        .clk(sysclk), .rst(rst),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata),
        .fs(fs), .fs_lane(fs), .cmp_async(5'd0), .fs_tx(4'd0),
        .cmp_i_s(cmp_i_s), .cmp_qp_s(cmp_qp_s), .cmp_qn_s(cmp_qn_s), .mux_tx(mux_tx), .mux_rx(mux_rx),
        .i2c_scl_i(i2c_scl), .i2c_sda_i(i2c_sda), .i2c_scl_o(scl_o), .i2c_sda_o(sda_o),
        .tx_i1(tx_i1), .tx_i0(tx_i0), .tx_q1(q1), .tx_q1_hiz(q1_hiz), .tx_q0(tx_q0),
        .spi_sclk(spi_sclk), .spi_sdata(spi_sdata), .le_pll_tx(le_pll_tx), .le_pll_rx(le_pll_rx), .le_dsa(le_dsa),
        .loop_hold(loop_hold), .loop_sel(loop_sel), .tx_dis(tx_dis_core), .trig_a(trig_a), .trig_b(trig_b), .tr_a(tr_a));

    // open drain: drive low or release to the pull-ups; TX_Q1 released for the board's TRIG IN bypass (CTRL[8])
    assign i2c_scl = scl_o ? 1'bz : 1'b0;
    assign i2c_sda = sda_o ? 1'bz : 1'b0;
    assign tx_q1   = q1_hiz ? 1'bz : q1;
endmodule
