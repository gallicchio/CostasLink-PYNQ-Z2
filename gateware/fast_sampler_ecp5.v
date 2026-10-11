// fast_sampler_ecp5: the Icepi Zero's fast sampler (Response 15): an IDDRX1F per input, 2 samples a clock.
//
// IDDRX1F samples its pad on both edges of SCLK and presents both on the rising edge: Q0 the rising-edge
// sample, Q1 the falling edge's (Lattice TN1265, the X1 gearing), so Q0 is the earlier.  At 100 MHz that is
// 200 Ms/s (5 ns).  Yosys has IDDRX1F only as a black box, so the order is TN1265's, not simulated: stage 0
// of BRINGUP.md checks it on the board (a capture of TRIG_IN's edge from a pulse generator must show one
// transition, never a 1-0-1 pattern within a clock).  Every fast input is on the Icepi's left banks 6 and 7
// (REVA_CHANGES.md 1), where IDDRX2F (4 samples a clock, 2.5 ns at ECLK 200 MHz) also works: the next step.
// Output: sample s of input k at q[N*s + k], costaslink_core.v's layout.

module fast_sampler_ecp5 #(
    parameter integer N = 6
) (
    input  wire           clk,
    input  wire           rst,
    input  wire [N-1:0]   pin,
    output reg  [2*N-1:0] q
);
    genvar k;
    generate
        for (k = 0; k < N; k = k + 1) begin : g_in
            wire q0, q1;
            IDDRX1F u_iddr (.D(pin[k]), .SCLK(clk), .RST(rst), .Q0(q0), .Q1(q1));
            always @(posedge clk) begin
                q[k]     <= q0;            // sample 0: the rising edge's
                q[N + k] <= q1;            // sample 1: the falling edge's, half a clock later
            end
        end
    endgenerate
endmodule
