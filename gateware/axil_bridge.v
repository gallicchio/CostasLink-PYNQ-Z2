// axil_bridge: AXI4-Lite slave -> the core's register bus (Response 15).
//
// Register n at byte offset 4 n (address bits [9:2]; 1 KB).  The write address and the write data are
// latched independently, in either order or the same clock (SmartConnect offers both at once; the GPSDO's
// first slave decoded the previous write's address there), and the bus write goes out once both are in.
// A read puts the address on the bus with a one-clock bus_re and returns bus_rdata four clock edges later
// (costaslink_core.v's bus stage and two read registers), the state before the read's own side effect, as
// uart_cmd.v returns it, so every register reads the same through either bridge.  Writes win over reads; one
// transaction at a time; every response OKAY (an unlisted register reads 0xDEAD00nn).

module axil_bridge (
    input  wire        clk,
    input  wire        resetn,
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire [9:0]  awaddr,                // [1:0]: the byte in the word, ignored (32-bit registers)
    /* verilator lint_on UNUSEDSIGNAL */
    input  wire        awvalid,
    output reg         awready,
    input  wire [31:0] wdata,
    input  wire        wvalid,
    output reg         wready,
    output wire [1:0]  bresp,
    output reg         bvalid,
    input  wire        bready,
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire [9:0]  araddr,
    /* verilator lint_on UNUSEDSIGNAL */
    input  wire        arvalid,
    output reg         arready,
    output reg  [31:0] rdata,
    output wire [1:0]  rresp,
    output reg         rvalid,
    input  wire        rready,
    // the register bus
    output reg  [7:0]  bus_addr,
    output reg  [31:0] bus_wdata,
    output reg         bus_we,
    output reg         bus_re,
    input  wire [31:0] bus_rdata
);
    assign bresp = 2'b00;
    assign rresp = 2'b00;

    reg       have_aw, have_w, rd_wait;
    reg [3:0] rd_sh;                          // bus_re's clock, then the core's bus stage and two read registers
    reg [7:0] aw_q;

    always @(posedge clk) begin
        if (!resetn) begin
            awready <= 1'b0; wready <= 1'b0; bvalid <= 1'b0; arready <= 1'b0; rvalid <= 1'b0; rdata <= 32'd0;
            bus_addr <= 8'd0; bus_wdata <= 32'd0; bus_we <= 1'b0; bus_re <= 1'b0;
            have_aw <= 1'b0; have_w <= 1'b0; rd_wait <= 1'b0; aw_q <= 8'd0; rd_sh <= 4'd0;
        end else begin
            awready <= 1'b0; wready <= 1'b0; arready <= 1'b0; bus_we <= 1'b0; bus_re <= 1'b0;
            rd_sh <= {rd_sh[2:0], 1'b0};
            // ---- writes ----
            if (awvalid && !have_aw && !awready && !bvalid) begin
                awready <= 1'b1; have_aw <= 1'b1; aw_q <= awaddr[9:2];
            end
            if (wvalid && !have_w && !wready && !bvalid) begin
                wready <= 1'b1; have_w <= 1'b1; bus_wdata <= wdata;
            end
            if (have_aw && have_w && !bvalid && !rd_wait) begin
                bus_addr <= aw_q; bus_we <= 1'b1; bvalid <= 1'b1;
                have_aw <= 1'b0; have_w <= 1'b0;
            end
            if (bvalid && bready) bvalid <= 1'b0;
            // ---- reads (when no write is waiting) ----
            if (arvalid && !arready && !rvalid && !rd_wait && !have_aw && !have_w && !bus_we) begin
                arready <= 1'b1; bus_addr <= araddr[9:2]; bus_re <= 1'b1; rd_wait <= 1'b1; rd_sh <= 4'b0001;
            end else if (rd_wait && rd_sh[3]) begin
                rdata <= bus_rdata; rvalid <= 1'b1; rd_wait <= 1'b0;   // the core's last read register
            end
            if (rvalid && rready) rvalid <= 1'b0;
        end
    end
endmodule
