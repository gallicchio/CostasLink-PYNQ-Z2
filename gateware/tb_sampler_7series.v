// tb_sampler_7series: which ISERDESE2 output holds the earliest sample, where the 8-sample word starts and
// when it is out (Response 15; the latency and the clocks' phase, Prompt 36).  Vivado's simulator with the
// UNISIM / secure-IP model: pynq/sim_sampler.tcl.
//
// Two one-sample pulses, at samples 4 and 6 after a clk edge (samples every 1.25 ns from the edge), must
// come out two indices apart with the earlier at the lower index, in one word: that is the order.  The
// lower index says where the ISERDES's word starts (the word boundary has no bitslip to move it; a constant
// for every input, which the latency calibration with a known cable absorbs).  Then a step at each sample
// of a clock: the clk edge at which the ISERDESE2's Q (the reply lane's word, EARLY) and the sampler's
// register first show it, which is the sampler's latency.
//
// clk_fast's rising edges are on clk's, as the MMCM makes them (the first version of this testbench had
// clk_fast's falling edges there and read a 3-sample offset; with the MMCM's phase it is 4).
`timescale 1ps/1ps
module tb_sampler_7series;
    reg clk = 1'b0, clk_fast = 1'b1;
    always #5000 clk = ~clk;            // 100 MHz, rising at 5 ns + 10 k
    always #1250 clk_fast = ~clk_fast;  // 400 MHz, rising at 2.5 ns + 2.5 k: on clk's rising edges
    reg rst = 1'b1;
    reg pin = 1'b0;
    wire [7:0] q, qr;
    /* the combinational O is the fast path's, not this test's */
    fast_sampler_7series #(.N(1)) dut (.clk(clk), .clk_fast(clk_fast), .rst(rst), .pin(pin), .q(q), .qr(qr), .o());
    integer c, i, lo, hi, nbits, ok, p, e_q, e_r, wmin, wmax;
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
        // the latency: a step 0.6 ns after sample p of a clock (p = 0..7); the edges until Q and q show it
        wmin = 99; wmax = -99;
        for (p = 0; p < 8; p = p + 1) begin
            repeat (4) @(posedge clk);
            #(p * 1250 + 600) pin = 1'b1;
            e_q = 0; e_r = 0;
            for (c = 1; c <= 4; c = c + 1) begin
                @(posedge clk); #300;
                if (e_r == 0 && qr != 8'd0) e_r = c;
                if (e_q == 0 && q != 8'd0) e_q = c;
            end
            $display("SAMPLER: a step 0.6 ns after sample %0d: on the ISERDESE2's Q from edge %0d, in the register from edge %0d", p, e_r, e_q);
            if (e_r < wmin) wmin = e_r;
            if (e_r > wmax) wmax = e_r;
            pin = 1'b0;
        end
        $display("SAMPLER: a sample is on Q one or two clk edges after the edge it follows (%0d to %0d), the register a clock later", wmin, wmax);
        $finish;
    end
endmodule
