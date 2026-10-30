// top_icepi: the Icepi Zero's CostasLink top (Response 15): the 50 MHz oscillator through an EHXPLLL to
// 100 MHz, the IDDRX1F sampler (2 samples a clock: 200 Ms/s), the UART bridge at 1 Mbaud (the Icepi's FTDI;
// the capture buffer reads out in seconds, not minutes) and costaslink_core.v, the same core the PYNQ-Z2
// runs over AXI-Lite.  Ports as icepi_zero.lpf (gen_xdc.py) names them.
//
//     make pnr-icepi     (yosys, nextpnr-ecp5, ecppack -> ../build/gateware_scratch/top_icepi.bit)
//     openFPGALoader -b icepi-zero ../build/gateware_scratch/top_icepi.bit

module top_icepi #(
    parameter integer BAUD = 1_000_000
) (
    input  wire sysclk,                   // 50 MHz, ball M1
    inout  wire i2c_sda,
    inout  wire i2c_scl,
    output wire tx_i1,
    output wire tx_i0,
    inout  wire tx_q1,
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
    localparam integer CLK_HZ = 100_000_000;

    // ---- 50 -> 100 MHz (ecppll -i 50 -o 100) ---------------------------------------------------------------
    wire clk, locked;
    (* FREQUENCY_PIN_CLKI="50" *)
    (* FREQUENCY_PIN_CLKOP="100" *)
    (* ICP_CURRENT="12" *) (* LPF_RESISTOR="8" *) (* MFG_ENABLE_FILTEROPAMP="1" *) (* MFG_GMCREF_SEL="2" *)
    EHXPLLL #(
        .PLLRST_ENA("DISABLED"), .INTFB_WAKE("DISABLED"), .STDBY_ENABLE("DISABLED"), .DPHASE_SOURCE("DISABLED"),
        .OUTDIVIDER_MUXA("DIVA"), .OUTDIVIDER_MUXB("DIVB"), .OUTDIVIDER_MUXC("DIVC"), .OUTDIVIDER_MUXD("DIVD"),
        .CLKI_DIV(1), .CLKOP_ENABLE("ENABLED"), .CLKOP_DIV(6), .CLKOP_CPHASE(2), .CLKOP_FPHASE(0),
        .FEEDBK_PATH("CLKOP"), .CLKFB_DIV(2)
    ) u_pll (
        .RST(1'b0), .STDBY(1'b0), .CLKI(sysclk), .CLKOP(clk), .CLKFB(clk), .CLKINTFB(),
        .PHASESEL0(1'b0), .PHASESEL1(1'b0), .PHASEDIR(1'b1), .PHASESTEP(1'b1), .PHASELOADREG(1'b1),
        .PLLWAKESYNC(1'b0), .ENCLKOP(1'b0), .LOCK(locked));

    // ---- reset: 16 clocks after the PLL locks ---------------------------------------------------------------
    reg [4:0] rcnt = 5'd0;
    reg       rst = 1'b1;
    always @(posedge clk) begin
        if (!locked) begin rcnt <= 5'd0; rst <= 1'b1; end
        else if (!rcnt[4]) rcnt <= rcnt + 1'b1;
        else rst <= 1'b0;
    end

    // ---- the UART bridge --------------------------------------------------------------------------------------
    wire [7:0]  rx_data, tx_data, bus_addr;
    wire        rx_valid, tx_start, tx_busy, bus_we, bus_re;
    wire [31:0] bus_wdata, bus_rdata;
    uart_rx  #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_rx (.clk(clk), .rst(rst), .rx(uart_rx), .data(rx_data), .valid(rx_valid));
    uart_tx  #(.CLK_HZ(CLK_HZ), .BAUD(BAUD)) u_tx (.clk(clk), .rst(rst), .data(tx_data), .start(tx_start), .tx(uart_tx), .busy(tx_busy));
    uart_cmd u_cmd (.clk(clk), .rst(rst), .rx_data(rx_data), .rx_valid(rx_valid),
                    .tx_data(tx_data), .tx_start(tx_start), .tx_busy(tx_busy),
                    .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata));

    // ---- the fast sampler ---------------------------------------------------------------------------------------
    wire [11:0] fs;
    fast_sampler_ecp5 #(.N(6)) u_fs (.clk(clk), .rst(rst), .pin({trig_in, cmp_in, cmp_ip, cmp_qn, cmp_qp, cmp_i}), .q(fs));

    // ---- the core ---------------------------------------------------------------------------------------------------
    wire scl_o, sda_o, q1, q1_hiz;
    // TX_EN on the header is the core's TX_DIS inverted (Response 15, REVA_CHANGES.md 2): the board's 1 k
    // holds the pin low, and so the modulator off, whenever no gateware drives it
    wire tx_dis_core;
    assign tx_en = ~tx_dis_core;

    costaslink_core #(.CLK_HZ(CLK_HZ), .SER(2), .CAP_AW(11), .BOARD(2)) u_core (
        .clk(clk), .rst(rst),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata),
        .fs(fs), .fs_lane(fs), .cmp_async(5'd0), .fs_tx(8'd0),
        .cmp_i_s(cmp_i_s), .cmp_qp_s(cmp_qp_s), .cmp_qn_s(cmp_qn_s), .mux_tx(mux_tx), .mux_rx(mux_rx),
        .i2c_scl_i(i2c_scl), .i2c_sda_i(i2c_sda), .i2c_scl_o(scl_o), .i2c_sda_o(sda_o),
        .tx_i1(tx_i1), .tx_i0(tx_i0), .tx_q1(q1), .tx_q1_hiz(q1_hiz), .tx_q0(tx_q0),
        .spi_sclk(spi_sclk), .spi_sdata(spi_sdata), .le_pll_tx(le_pll_tx), .le_pll_rx(le_pll_rx), .le_dsa(le_dsa),
        .loop_hold(loop_hold), .loop_sel(loop_sel), .tx_dis(tx_dis_core), .trig_a(trig_a), .trig_b(trig_b), .tr_a(tr_a));

    // open drain (fit the board's DNP 4.7 k pull-ups R3xx for the Icepi: it has none), TX_Q1 released on CTRL[8]
    assign i2c_scl = scl_o ? 1'bz : 1'b0;
    assign i2c_sda = sda_o ? 1'bz : 1'b0;
    assign tx_q1   = q1_hiz ? 1'bz : q1;
endmodule
