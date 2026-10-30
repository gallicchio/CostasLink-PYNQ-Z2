// the fast path as one 16x4 distributed RAM read with no clock: the four window comparators (B2, A3r: CMP_I left out)
// address it, its four bits drive the ladder pins; the table is written synchronously (one level of logic)
module fp_ram (input wire sysclk, input wire we, input wire [3:0] wa, input wire [3:0] wd, input wire [3:0] cmp,
               output wire [3:0] tx);
    reg [3:0] mem [0:15];
    always @(posedge sysclk) if (we) mem[wa] <= wd;
    assign tx = mem[cmp];
endmodule
