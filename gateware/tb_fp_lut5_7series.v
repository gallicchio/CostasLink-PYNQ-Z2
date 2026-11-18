// tb_fp_lut5_7series: fp_lut5_7series.v's CFGLUT5 against fp_lut5.v's rule (Prompt 36), in Vivado's
// simulator with the UNISIM model (pynq/sim_sampler.tcl): 32 clocks of ce shift a table in, entry 31
// first, and then o = table[a] for every a.  The simulations of the core use fp_lut5.v; this is what makes
// them stand for the PYNQ-Z2's fast path.
`timescale 1ps/1ps
module tb_fp_lut5_7series;
    reg clk = 1'b0;
    always #5000 clk = ~clk;
    reg ce = 1'b0, cdi = 1'b0;
    reg [4:0] a = 5'd0;
    wire o;
    fp_lut5 dut (.clk(clk), .ce(ce), .cdi(cdi), .a(a), .o(o));
    reg [31:0] t;
    integer k, n, errors;
    initial begin
        errors = 0;
        repeat (20) @(posedge clk);
        for (n = 0; n < 3; n = n + 1) begin
            t = (n == 0) ? 32'hDEADBEEF : (n == 1) ? 32'h0F0F_3C5A : 32'h8000_0001;
            for (k = 31; k >= 0; k = k - 1) begin
                @(negedge clk); ce = 1'b1; cdi = t[k];
            end
            @(negedge clk); ce = 1'b0;
            for (k = 0; k < 32; k = k + 1) begin
                a = k[4:0]; #100;
                if (o !== t[k]) begin errors = errors + 1; $display("table %0d entry %0d: %b, want %b", n, k, o, t[k]); end
            end
        end
        $display("FP_LUT5: three tables loaded and read back: %s (%0d errors)", errors == 0 ? "PASS" : "FAIL", errors);
        $finish;
    end
endmodule
