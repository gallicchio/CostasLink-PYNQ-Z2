// fast_sampler_flop: the generic fast sampler (Response 15): two flip-flops per input, one sample a clock
// (SER = 1).  Any FPGA, and the testbench of the generic top.  The boards' samplers take SER samples a
// clock with their I/O primitives: fast_sampler_7series.v (ISERDESE2), fast_sampler_ecp5.v (IDDRX1F).

module fast_sampler_flop #(
    parameter integer N = 6
) (
    input  wire         clk,
    input  wire [N-1:0] d,
    output reg  [N-1:0] q
);
    reg [N-1:0] s1;
    always @(posedge clk) begin
        s1 <= d;
        q  <= s1;
    end
endmodule
