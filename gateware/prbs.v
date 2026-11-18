/* verilator lint_off DECLFILENAME */
// prbs: the PRBS polynomials both the transmitter and the receiver's BER check use (Response 15).
//
// Fibonacci LFSRs of the ITU-T O.150 sequences, one bit a step: the new bit is s[a-1] ^ s[b-1] and the
// register shifts left with it in bit 0.  `poly`: 0 PRBS7 (x^7 + x^6 + 1), 1 PRBS9 (x^9 + x^5 + 1),
// 2 PRBS15 (x^15 + x^14 + 1), 3 PRBS23 (x^23 + x^18 + 1), 4 PRBS31 (x^31 + x^28 + 1).  The state is 31
// bits wide whatever the polynomial; the bits above its length are never fed back.  A state of all
// zeros in the polynomial's length is stuck: the engines seed with all ones.

module prbs_step (
    input  wire [30:0] state,
    input  wire [2:0]  poly,
    output wire [30:0] next,
    output wire        bit_out
);
    reg b;
    always @* begin
        case (poly)
        3'd0:    b = state[6]  ^ state[5];
        3'd1:    b = state[8]  ^ state[4];
        3'd2:    b = state[14] ^ state[13];
        3'd3:    b = state[22] ^ state[17];
        default: b = state[30] ^ state[27];
        endcase
    end
    assign next = {state[29:0], b};
    assign bit_out = b;
endmodule

// the bit a self-synchronising checker expects next, from the last 31 bits received (r[0] the newest)
module prbs_expect (
    /* verilator lint_off UNUSEDSIGNAL */
    input  wire [30:0] r,                  // only the taps of the chosen polynomial are read
    /* verilator lint_on UNUSEDSIGNAL */
    input  wire [2:0]  poly,
    output reg         e
);
    always @* begin
        case (poly)
        3'd0:    e = r[6]  ^ r[5];
        3'd1:    e = r[8]  ^ r[4];
        3'd2:    e = r[14] ^ r[13];
        3'd3:    e = r[22] ^ r[17];
        default: e = r[30] ^ r[27];
        endcase
    end
endmodule

// prbs_multi: the five sequences side by side, each its own register with fixed taps, so taking up to three
// bits a clock is a few XORs and one 5-way choice, not three chained steps each through the polynomial's
// mux (tx_engine's PRBS path held the Icepi Zero at 73 MHz that way, Response 15).  `bits` = the next three
// bits of the chosen sequence, b1 first in bits[0]; `adv` (0-3) of them are taken at the clock.  Every
// register starts, and is reseeded, at all ones.
//
// The registers step a clock late: `adv` goes into `pend` (two flip-flops), and in the next clock each
// register steps by `pend` while `bits` are read `pend` bits further on (six bits of look-ahead), so a
// draw in every clock still sees the bits after the last one.  The event logic behind `adv` (TRIG_IN,
// the gate, the period) then drives two flip-flops, not the 85 of the registers (the Icepi's last path
// at 90 MHz).

module prbs_multi (
    input  wire       clk,
    input  wire       rst,
    input  wire       reseed,
    input  wire [1:0] adv,
    input  wire [2:0] poly,
    output reg  [2:0] bits
);
    reg  [1:0] pend;
    wire       init = rst || reseed;
    wire [2:0] b7, b9, b15, b23, b31;
    prbs_ahead #(.N(7),  .A(7),  .B(6))  u7  (.clk(clk), .init(init), .pend(pend), .bits(b7));
    prbs_ahead #(.N(9),  .A(9),  .B(5))  u9  (.clk(clk), .init(init), .pend(pend), .bits(b9));
    prbs_ahead #(.N(15), .A(15), .B(14)) u15 (.clk(clk), .init(init), .pend(pend), .bits(b15));
    prbs_ahead #(.N(23), .A(23), .B(18)) u23 (.clk(clk), .init(init), .pend(pend), .bits(b23));
    prbs_ahead #(.N(31), .A(31), .B(28)) u31 (.clk(clk), .init(init), .pend(pend), .bits(b31));
    always @* begin
        case (poly)
        3'd0:    bits = b7;
        3'd1:    bits = b9;
        3'd2:    bits = b15;
        3'd3:    bits = b23;
        default: bits = b31;
        endcase
    end
    always @(posedge clk) pend <= init ? 2'd0 : adv;
endmodule

// one fixed-tap register of prbs_multi: steps by `pend` at the clock; `bits` are the three after those
module prbs_ahead #(
    parameter integer N = 7,
    parameter integer A = 7,
    parameter integer B = 6
) (
    input  wire       clk,
    input  wire       init,
    input  wire [1:0] pend,
    output reg  [2:0] bits
);
    reg [N-1:0] s, t, s1, s2, s3;
    reg [5:0]   fut;                        // the next six bits, fut[0] first
    integer     i;
    always @* begin
        t = s; s1 = s; s2 = s; s3 = s;
        for (i = 0; i < 6; i = i + 1) begin
            fut[i] = t[A-1] ^ t[B-1];
            t = {t[N-2:0], fut[i]};
            if (i == 0) s1 = t;
            if (i == 1) s2 = t;
            if (i == 2) s3 = t;
        end
        case (pend)
        2'd0:    bits = fut[2:0];
        2'd1:    bits = fut[3:1];
        2'd2:    bits = fut[4:2];
        default: bits = fut[5:3];
        endcase
    end
    always @(posedge clk) begin
        if (init) s <= {N{1'b1}};
        else case (pend)
            2'd1:    s <= s1;
            2'd2:    s <= s2;
            2'd3:    s <= s3;
            default: ;
        endcase
    end
endmodule
