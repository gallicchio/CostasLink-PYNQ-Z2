// the fast path alone on the Icepi Zero's pins: five comparator pins through four reloadable 5-input tables to the
// four ladder pins, no clock in the path (the timing of turnaround.v's FAST_PATH, which top_icepi.v does not build)
module fp_test (input wire sysclk, input wire ce, input wire cdi, input wire [4:0] cmp, output wire [3:0] tx);
    genvar k;
    generate for (k = 0; k < 4; k = k + 1) begin : g
        fp_lut5 u (.clk(sysclk), .ce(ce), .cdi(cdi ^ k[0]), .a(cmp), .o(tx[k]));
    end endgenerate
endmodule
