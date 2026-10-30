// fp_lut5 (7-series): the fast path's reloadable 5-input table on a CFGLUT5 (Prompt 36), the PYNQ-Z2's build
// of fp_lut5.v's port (pynq/build.tcl lists this file in its place).  O6 = INIT[{I4,I3,I2,I1,I0}] through
// one LUT, the comparators straight in; 32 clocks of CE shift CDI in at the bottom (INIT <= {INIT[30:0],
// CDI}).  It sits in a SLICEM: a LUT that is also a shift register.

module fp_lut5 (
    input  wire       clk,
    input  wire       ce,
    input  wire       cdi,
    input  wire [4:0] a,
    output wire       o
);
    CFGLUT5 #(.INIT(32'h0000_0000)) u_lut (
        .CDO(), .O5(), .O6(o), .CDI(cdi), .CE(ce), .CLK(clk),
        .I0(a[0]), .I1(a[1]), .I2(a[2]), .I3(a[3]), .I4(a[4]));
endmodule
