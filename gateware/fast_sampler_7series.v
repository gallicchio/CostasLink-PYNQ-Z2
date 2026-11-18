// fast_sampler_7series: the PYNQ-Z2's fast sampler (Response 15): an ISERDESE2 per input, DDR 8:1.
//
// clk_fast (400 MHz) and clk (100 MHz) come from one MMCM (the block design's clock wizard), so they are
// phase-aligned; the ISERDES samples its pin on both edges of clk_fast, 800 Ms/s, and hands over eight
// samples per clk.  The inputs are asynchronous (comparators): nothing here aligns words (no bitslip),
// every sample is a sample.  Output: sample s (0 the earliest of the clock) of input k at q[N*s + k],
// the layout costaslink_core.v takes (N = 6 there).  Checked in Vivado's simulator against the UNISIM /
// secure-IP model (tb_sampler_7series.v, pynq/sim_sampler.tcl): Q8 is the earliest bit, Q1 the latest,
// and the 8-sample word starts 4 samples (5 ns) after the clk edge with clk_fast's rising edges on clk's,
// as the MMCM makes them (3 with the testbench's first, misaligned clocks): a constant for every input (no
// bitslip moves it), so it shifts every time stamp alike and the loopback calibration absorbs it.
//
// Three more outputs (Prompt 36):
//   * qr: the ISERDESE2's own word, the same layout as q a clock before q has it (its Q1-Q8 are the
//     output register, clocked by CLKDIV = clk): the reply lane's input (turnaround.v, EARLY).  In the
//     model the word holding samples [E(n-1) + 5 ns, E(n) + 3.75 ns] is on Q1-Q8 from E(n+1), in q from
//     E(n+2): a sample is on Q 6.25-15 ns after it was taken, 10.6 ns on average.
//   * o: the ISERDESE2's combinational O.  With IOBDELAY = "NONE" (and OFB_USED = "FALSE") O is D, the
//     input buffer's output, while D also feeds the deserialiser (UG471, ISERDESE2 attributes: IOBDELAY
//     "NONE" means O and Q both from D; the UNISIM model does exactly that).  The pin reaches the fabric
//     through O, the only way an IBUF that drives an ISERDESE2 gets there: the fast path's input.
//   * IBUF_IN = 0: the pins are already buffers' outputs (the ladder pins' IOBUFs, read back).

module fast_sampler_7series #(
    parameter integer N       = 6,
    parameter integer IBUF_IN = 1               // 1: an IBUF per pin here; 0: `pin` is a buffer's output
) (
    input  wire           clk,          // 100 MHz, the fabric
    input  wire           clk_fast,     // 400 MHz, from the same MMCM
    input  wire           rst,          // synchronous to clk: held a few clocks after the MMCM locks
    input  wire [N-1:0]   pin,          // straight from the pads (or from their buffers: IBUF_IN = 0)
    output reg  [8*N-1:0] q,
    output wire [8*N-1:0] qr,           // the ISERDESE2's word, a clock before q
    output wire [N-1:0]   o             // the pins, combinational (ISERDESE2.O)
);
    genvar k, s;
    generate
        for (k = 0; k < N; k = k + 1) begin : g_in
            wire d;
            wire [7:0] qq;              // qq[0] = Q1 ... qq[7] = Q8
            if (IBUF_IN != 0) begin : g_ibuf
                IBUF u_ibuf (.I(pin[k]), .O(d));
            end else begin : g_nobuf
                assign d = pin[k];
            end
            ISERDESE2 #(
                .DATA_RATE("DDR"), .DATA_WIDTH(8), .INTERFACE_TYPE("NETWORKING"), .IOBDELAY("NONE"),
                .NUM_CE(1), .OFB_USED("FALSE"), .SERDES_MODE("MASTER"),
                .DYN_CLKDIV_INV_EN("FALSE"), .DYN_CLK_INV_EN("FALSE"),
                .INIT_Q1(1'b0), .INIT_Q2(1'b0), .INIT_Q3(1'b0), .INIT_Q4(1'b0),
                .SRVAL_Q1(1'b0), .SRVAL_Q2(1'b0), .SRVAL_Q3(1'b0), .SRVAL_Q4(1'b0)
            ) u_iserdes (
                .Q1(qq[0]), .Q2(qq[1]), .Q3(qq[2]), .Q4(qq[3]), .Q5(qq[4]), .Q6(qq[5]), .Q7(qq[6]), .Q8(qq[7]),
                .O(o[k]), .SHIFTOUT1(), .SHIFTOUT2(),
                .BITSLIP(1'b0), .CE1(1'b1), .CE2(1'b1), .CLKDIVP(1'b0),
                .CLK(clk_fast), .CLKB(~clk_fast), .CLKDIV(clk), .OCLK(1'b0), .OCLKB(1'b0),
                .DYNCLKDIVSEL(1'b0), .DYNCLKSEL(1'b0),
                .D(d), .DDLY(1'b0), .OFB(1'b0), .RST(rst), .SHIFTIN1(1'b0), .SHIFTIN2(1'b0)
            );
            // Q8 is the earliest bit: sample s is Q(8-s)
            for (s = 0; s < 8; s = s + 1) begin : g_s
                assign qr[N*s + k] = qq[7 - s];
                always @(posedge clk) q[N*s + k] <= qq[7 - s];
            end
        end
    endgenerate
endmodule
