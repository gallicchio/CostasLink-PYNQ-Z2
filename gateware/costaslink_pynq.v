// costaslink_pynq: the PYNQ-Z2's CostasLink overlay core (Response 15), a module reference in Vivado's
// block design (pynq/build.tcl): AXI-Lite from the PS (axil_bridge.v), the ISERDESE2 sampler at 800 Ms/s
// (fast_sampler_7series.v) and costaslink_core.v.  Plain Verilog: a module reference's top cannot be
// SystemVerilog.  Vivado infers the S_AXI interface and the clocks from the X_INTERFACE attributes.
//
// Clocks (the block design's clock wizard, from the PS's FCLK_CLK0 at 100 MHz): s_axi_aclk = 100 MHz,
// the whole fabric and the AXI; clk_fast = 400 MHz from the same MMCM, the ISERDES's sampling clock.
// The pins: the header signals of gen/pins.py in lower case, as pynq/costaslink_pynq.xdc names them.

module costaslink_pynq #(
    parameter integer CLK_HZ = 100_000_000,
    parameter integer CAP_AW = 12
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn, FREQ_HZ 100000000" *)
    input  wire        s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        s_axi_aresetn,
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 clk_fast CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_RESET none, FREQ_HZ 400000000" *)
    input  wire        clk_fast,
    input  wire [9:0]  s_axi_awaddr,
    input  wire [2:0]  s_axi_awprot,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    output wire [1:0]  s_axi_bresp,
    output wire        s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [9:0]  s_axi_araddr,
    input  wire [2:0]  s_axi_arprot,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output wire [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output wire        s_axi_rvalid,
    input  wire        s_axi_rready,
    // the header (gen/pins.py)
    inout  wire        i2c_sda,
    inout  wire        i2c_scl,
    output wire        tx_i1,
    output wire        tx_i0,
    inout  wire        tx_q1,
    output wire        tx_q0,
    input  wire        cmp_qn,
    input  wire        cmp_qp,
    input  wire        cmp_i,
    input  wire        cmp_i_s,
    input  wire        cmp_qn_s,
    input  wire        cmp_qp_s,
    input  wire        cmp_ip,
    input  wire        cmp_in,
    output wire        spi_sclk,
    output wire        spi_sdata,
    output wire        le_pll_tx,
    output wire        le_pll_rx,
    output wire        le_dsa,
    output wire        loop_hold,
    output wire        loop_sel,
    output wire        tx_en,          // header 24: high transmits (the core's TX_DIS inverted; the board's U206 makes DSOP)
    input  wire        trig_in,
    output wire        trig_a,
    output wire        trig_b,
    output wire        tr_a,
    input  wire        mux_tx,
    input  wire        mux_rx
);
    wire clk = s_axi_aclk;

    // the reset, held 16 clocks after the PS's (and the clock wizard's lock, through proc_sys_reset)
    reg [4:0] rcnt;
    reg       rst;
    always @(posedge clk) begin
        if (!s_axi_aresetn) begin rcnt <= 5'd0; rst <= 1'b1; end
        else if (!rcnt[4]) rcnt <= rcnt + 1'b1;
        else rst <= 1'b0;
    end

    // ---- AXI-Lite -> the register bus ----------------------------------------------------------------------
    wire [7:0]  bus_addr;
    wire [31:0] bus_wdata, bus_rdata;
    wire        bus_we, bus_re;
    axil_bridge u_axi (
        .clk(clk), .resetn(s_axi_aresetn),
        .awaddr(s_axi_awaddr), .awvalid(s_axi_awvalid), .awready(s_axi_awready),
        .wdata(s_axi_wdata), .wvalid(s_axi_wvalid), .wready(s_axi_wready),
        .bresp(s_axi_bresp), .bvalid(s_axi_bvalid), .bready(s_axi_bready),
        .araddr(s_axi_araddr), .arvalid(s_axi_arvalid), .arready(s_axi_arready),
        .rdata(s_axi_rdata), .rresp(s_axi_rresp), .rvalid(s_axi_rvalid), .rready(s_axi_rready),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata));

    // ---- the fast sampler: 8 samples a clock -----------------------------------------------------------------
    wire [47:0] fs;
    fast_sampler_7series #(.N(6)) u_fs (
        .clk(clk), .clk_fast(clk_fast), .rst(rst),
        .pin({trig_in, cmp_in, cmp_ip, cmp_qn, cmp_qp, cmp_i}), .q(fs));

    // ---- the core --------------------------------------------------------------------------------------------
    wire scl_o, sda_o, q1, q1_hiz;
    // TX_EN on the header is the core's TX_DIS inverted (Response 15, REVA_CHANGES.md 2): the board's 1 k
    // holds the pin low, and so the modulator off, whenever no gateware drives it
    wire tx_dis_core;
    assign tx_en = ~tx_dis_core;

    costaslink_core #(.CLK_HZ(CLK_HZ), .SER(8), .CAP_AW(CAP_AW), .BOARD(1)) u_core (
        .clk(clk), .rst(rst),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata),
        .fs(fs), .cmp_i_s(cmp_i_s), .cmp_qp_s(cmp_qp_s), .cmp_qn_s(cmp_qn_s), .mux_tx(mux_tx), .mux_rx(mux_rx),
        .i2c_scl_i(i2c_scl), .i2c_sda_i(i2c_sda), .i2c_scl_o(scl_o), .i2c_sda_o(sda_o),
        .tx_i1(tx_i1), .tx_i0(tx_i0), .tx_q1(q1), .tx_q1_hiz(q1_hiz), .tx_q0(tx_q0),
        .spi_sclk(spi_sclk), .spi_sdata(spi_sdata), .le_pll_tx(le_pll_tx), .le_pll_rx(le_pll_rx), .le_dsa(le_dsa),
        .loop_hold(loop_hold), .loop_sel(loop_sel), .tx_dis(tx_dis_core), .trig_a(trig_a), .trig_b(trig_b), .tr_a(tr_a));

    // open drain I2C (the PYNQ fits 2k2 pull-ups on these two pins), TX_Q1 released for the TRIG IN bypass
    assign i2c_scl = scl_o ? 1'bz : 1'b0;
    assign i2c_sda = sda_o ? 1'bz : 1'b0;
    assign tx_q1   = q1_hiz ? 1'bz : q1;

    // AXI fields this slave does not use
    wire _unused = &{1'b0, s_axi_awprot, s_axi_arprot, s_axi_wstrb};
endmodule
