// tb_sampler_7series: which ISERDESE2 output holds the earliest sample, and where the 8-sample word starts
// (Response 15).  Vivado's simulator with the UNISIM / secure-IP model: pynq/sim_sampler.tcl.
//
// Two one-sample pulses, at samples 4 and 6 after a clk edge (samples every 1.25 ns from the edge), must
// come out two indices apart with the earlier at the lower index, in one word: that is the order.  The
// lower index says where the ISERDES's word starts: 3 samples after the clk edge in the model (the
// word boundary has no bitslip to move it; a constant for every input, which the latency calibration with
// a known cable absorbs).
`timescale 1ps/1ps
module tb_sampler_7series;
    reg clk = 1'b0, clk_fast = 1'b0;
    always #5000 clk = ~clk;            // 100 MHz
    always #1250 clk_fast = ~clk_fast;  // 400 MHz, rising edges aligned with clk's
    reg rst = 1'b1;
    reg pin = 1'b0;
    wire [7:0] q;
    fast_sampler_7series #(.N(1)) dut (.clk(clk), .clk_fast(clk_fast), .rst(rst), .pin(pin), .q(q));
    integer c, i, lo, hi, nbits, ok;
    reg [7:0] word;
    initial begin
        repeat (20) @(posedge clk);
        rst = 1'b0;
        repeat (20) @(posedge clk);
        // pulses over sample 4 (5000 ps) and sample 6 (7500 ps)
        #4500 pin = 1'b1; #1000 pin = 1'b0;
        #1500 pin = 1'b1; #1000 pin = 1'b0;
        word = 8'd0;
        for (c = 0; c < 6; c = c + 1) begin
            @(posedge clk); #1;
            if (q != 8'd0) word = q;
        end
        lo = -1; hi = -1; nbits = 0;
        for (i = 0; i < 8; i = i + 1) if (word[i]) begin nbits = nbits + 1; if (lo < 0) lo = i; hi = i; end
        ok = (nbits == 2) && (hi - lo == 2);
        $display("SAMPLER: pulses at samples 4 and 6 -> indices %0d and %0d (word %b): order %s; the word starts %0d samples after the clk edge",
                 lo, hi, word, ok ? "PASS" : "FAIL", 4 - lo);
        $finish;
    end
endmodule
