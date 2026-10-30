// tb_axil: axil_bridge.v and costaslink_core.v together, the PYNQ-Z2's register path without the PS
// (Response 15).  An AXI-Lite master writes with the address and the data in the same clock, the address
// first and the data first, reads back, reads back to back, and checks the ID, BUILD and an unlisted
// register; the slave's handshakes are checked against the AXI rules a SmartConnect relies on (VALID held
// until READY, one response per request).  Run: make sim-axil.

`timescale 1ns / 1ps
module tb_axil;
`include "regmap.vh"
    localparam integer SER = 8;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg resetn = 1'b0;
    reg rst = 1'b1;

    reg  [9:0]  awaddr = 10'd0, araddr = 10'd0;
    reg         awvalid = 1'b0, wvalid = 1'b0, bready = 1'b0, arvalid = 1'b0, rready = 1'b0;
    reg  [31:0] wdata = 32'd0;
    wire        awready, wready, bvalid, arready, rvalid;
    wire [1:0]  bresp, rresp;
    wire [31:0] rdata;
    wire [7:0]  bus_addr;
    wire [31:0] bus_wdata, bus_rdata;
    wire        bus_we, bus_re;

    axil_bridge u_axi (
        .clk(clk), .resetn(resetn),
        .awaddr(awaddr), .awvalid(awvalid), .awready(awready), .wdata(wdata), .wvalid(wvalid), .wready(wready),
        .bresp(bresp), .bvalid(bvalid), .bready(bready),
        .araddr(araddr), .arvalid(arvalid), .arready(arready), .rdata(rdata), .rresp(rresp), .rvalid(rvalid),
        .rready(rready),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata));

    /* verilator lint_off PINCONNECTEMPTY */
    costaslink_core #(.CLK_HZ(100_000_000), .SER(SER), .CAP_AW(10), .BOARD(1)) dut (
        .clk(clk), .rst(rst),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata),
        .fs({6*SER{1'b0}}), .fs_lane({6*SER{1'b0}}), .cmp_async(5'd0), .fs_tx({4*SER{1'b0}}), .cmp_i_s(1'b0), .cmp_qp_s(1'b0), .cmp_qn_s(1'b0), .mux_tx(1'b0), .mux_rx(1'b0),
        .i2c_scl_i(1'b1), .i2c_sda_i(1'b1), .i2c_scl_o(), .i2c_sda_o(),
        .tx_i1(), .tx_i0(), .tx_q1(), .tx_q1_hiz(), .tx_q0(),
        .spi_sclk(), .spi_sdata(), .le_pll_tx(), .le_pll_rx(), .le_dsa(),
        .loop_hold(), .loop_sel(), .tx_dis(), .trig_a(), .trig_b(), .tr_a());
    /* verilator lint_on PINCONNECTEMPTY */

    integer errors = 0;
    task expect;
        input [8*32-1:0] what;
        input [31:0] got, want;
        begin
            if (got !== want) begin
                $display("FAIL %0s: got %08x, want %08x", what, got, want); errors = errors + 1;
            end
        end
    endtask

    // the AXI rules: a slave's VALID stays up until its READY; no response without a request
    reg bvalid_q = 1'b0, rvalid_q = 1'b0, bready_q = 1'b0, rready_q = 1'b0;
    integer n_aw = 0, n_w = 0, n_b = 0, n_ar = 0, n_r = 0;
    always @(posedge clk) begin
        if (resetn) begin
            if (bvalid_q && !bready_q && !bvalid) begin $display("FAIL BVALID dropped before BREADY"); errors = errors + 1; end
            if (rvalid_q && !rready_q && !rvalid) begin $display("FAIL RVALID dropped before RREADY"); errors = errors + 1; end
            if (awvalid && awready) n_aw = n_aw + 1;
            if (wvalid && wready)   n_w  = n_w + 1;
            if (bvalid && bready)   n_b  = n_b + 1;
            if (arvalid && arready) n_ar = n_ar + 1;
            if (rvalid && rready)   n_r  = n_r + 1;
            if (n_b > n_aw || n_b > n_w || n_r > n_ar) begin
                $display("FAIL a response without its request"); errors = errors + 1;
            end
        end
        bvalid_q <= bvalid; rvalid_q <= rvalid; bready_q <= bready; rready_q <= rready;
    end

    // The master samples the slave's READY and VALID at the falling edge, so a handshake is the rising edge
    // after a falling edge that saw VALID and READY both high (as the slave sees it).
    // A write: mode 0 the address and the data together, 1 the address first, 2 the data first (the second
    // half three clocks after the first's handshake).
    task axi_write;
        input [7:0]  r;
        input [31:0] d;
        input integer mode;
        integer guard;
        reg aw_done, w_done, hs_aw, hs_w, hs_b;
        begin
            @(negedge clk);
            aw_done = 1'b0; w_done = 1'b0;
            if (mode != 2) begin awaddr = {r, 2'b00}; awvalid = 1'b1; end
            if (mode != 1) begin wdata = d; wvalid = 1'b1; end
            guard = 0;
            while (!(aw_done && w_done) && guard < 100) begin
                hs_aw = awvalid && awready; hs_w = wvalid && wready;
                @(posedge clk); #1;
                if (hs_aw) begin awvalid = 1'b0; aw_done = 1'b1; end
                if (hs_w)  begin wvalid = 1'b0;  w_done  = 1'b1; end
                if (mode == 1 && aw_done && !w_done && !wvalid) begin
                    repeat (3) @(posedge clk); #1; wdata = d; wvalid = 1'b1;
                end
                if (mode == 2 && w_done && !aw_done && !awvalid) begin
                    repeat (3) @(posedge clk); #1; awaddr = {r, 2'b00}; awvalid = 1'b1;
                end
                @(negedge clk);
                guard = guard + 1;
            end
            if (!(aw_done && w_done)) begin $display("FAIL write not accepted"); errors = errors + 1; end
            bready = 1'b1;
            hs_b = bvalid; guard = 0;
            while (!hs_b && guard < 100) begin
                @(negedge clk); hs_b = bvalid; guard = guard + 1;
            end
            if (!hs_b) begin $display("FAIL no write response"); errors = errors + 1; end
            expect("BRESP", {30'd0, bresp}, 32'd0);
            @(posedge clk); #1; bready = 1'b0;
        end
    endtask

    task axi_read;
        input  [7:0]  r;
        output [31:0] d;
        input integer rready_delay;
        integer guard;
        reg hs_ar, hs_r;
        begin
            @(negedge clk); araddr = {r, 2'b00}; arvalid = 1'b1;
            hs_ar = 1'b0; guard = 0;
            while (!hs_ar && guard < 100) begin
                @(negedge clk); hs_ar = arvalid && arready; guard = guard + 1;
            end
            @(posedge clk); #1; arvalid = 1'b0;
            if (!hs_ar) begin $display("FAIL read not accepted"); errors = errors + 1; end
            guard = 0;
            while (!rvalid && guard < 100) begin @(negedge clk); guard = guard + 1; end
            if (!rvalid) begin $display("FAIL no read response"); errors = errors + 1; end
            repeat (rready_delay) @(negedge clk);
            rready = 1'b1; d = rdata;
            expect("RRESP", {30'd0, rresp}, 32'd0);
            @(posedge clk); #1; rready = 1'b0;
        end
    endtask

    reg [31:0] v;
    integer k;
    initial begin
        repeat (5) @(posedge clk);
        resetn = 1'b1;
        repeat (3) @(posedge clk);
        rst = 1'b0;
        repeat (3) @(posedge clk);

        axi_read(R_ID, v, 0);    expect("ID", v, 32'h434C_0004);
        axi_read(R_BUILD, v, 0); expect("BUILD", v, {16'd100, 4'b1000, 4'd1, 8'd8});   // [15]: RP_REG, the core's default
        axi_read(8'h74, v, 0);   expect("unlisted register", v, 32'hDEAD_0074);

        axi_write(R_TX_PERIOD, 32'h0001_2345, 0); axi_read(R_TX_PERIOD, v, 0);
        expect("write, address and data together", v, 32'h0001_2345);
        axi_write(R_TX_PERIOD, 32'h0000_0777, 1); axi_read(R_TX_PERIOD, v, 0);
        expect("write, the address first", v, 32'h0000_0777);
        axi_write(R_TX_PERIOD, 32'h0000_0999, 2); axi_read(R_TX_PERIOD, v, 3);
        expect("write, the data first; RREADY late", v, 32'h0000_0999);

        // back to back, alternating registers: each read returns its own register, never the last one's
        for (k = 0; k < 4; k = k + 1) begin
            axi_read(R_ID, v, 0);        expect("back to back: ID", v, 32'h434C_0004);
            axi_read(R_TX_PERIOD, v, 0); expect("back to back: TX_PERIOD", v, 32'h0000_0999);
        end
        // a write straight after a read, then a read of the written register
        axi_write(R_TX_PERIOD, 32'h0000_0042, 0); axi_read(R_TX_PERIOD, v, 0);
        expect("read after write", v, 32'h0000_0042);
        repeat (10) @(posedge clk);
        expect("one B per write", n_b, n_aw);
        expect("one R per read", n_r, n_ar);

        if (errors == 0) $display("PASS: tb_axil, %0d reads, %0d writes", n_r, n_b);
        else             $display("FAIL: tb_axil, %0d errors", errors);
        $finish;
    end
    initial begin #200000; $display("FAIL: tb_axil timed out"); $finish; end
endmodule
