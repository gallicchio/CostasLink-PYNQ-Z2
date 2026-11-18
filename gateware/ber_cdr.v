// ber_cdr: timing recovery for the BER check (2026-10-30, the B210 and then a second board as the transmitter: its
// symbol clock is not this board's).  The symbol's frame is tracked in samples from CMP_I's own transitions,
// SER samples a clock (sample 0 the earliest), and CMP_I is read once a symbol `offset` samples after the frame's
// start (its middle: 4 x the period for SER = 8).
//
// pos is this clock's sample 0's place in the symbol, in 1/256 sample, 0 <= pos < L = period x SER x 256.  Each
// clock: the first transition among the samples (the previous clock's last counts) is at pos + k - 1/2; its error
// is that place wrapped into [-L/2, L/2) (an edge belongs at 0); pos moves on by SER samples less the error >> gain,
// the correction clamped to +-4 samples (a first-order loop: at 100 ppm and 100 clocks a symbol it settles 2-3
// samples late with gain 4).  The error goes through four registered stages and is applied four clocks after its
// edge (the loop is far slower than that), so no path holds more than about one adder and a compare.  The sample is taken in the clock whose samples first reach the sampling point, once
// a symbol (a correction backwards over the frame's start does not read a symbol twice, one forwards over the
// point does not skip it: the first sample past it is read).  For periods of 2 clocks and more.
//
// one_pol (2026-10-31, BRINGUP_LOG 4.9): with CMP_I's rising and falling edges apart (a threshold off the I leg's
// middle: duty-cycle distortion), the mean of both has two stable points half a symbol apart, and the second samples
// between the two kinds of edge: random bits.  Which one a restart lands in is its phase's draw (at 5.0 GHz some 25
// and 50 Mbaud segments read exactly half wrong; in simulation, rising edges 6 samples late at 2 clocks a symbol, 6
// restarts of 24).  With one_pol the frame tracks the rising edges alone (one stable point at any skew), the falling
// edges' mean place against it is `skew`, and the sampling point moves by half of it: the middle of the open eye.
// A clock's edge counts as rising or falling by its net change (its last sample against the previous clock's last),
// so a comparator's chatter at an edge, which starts some clocks with a transition the other way, is not taken for
// the other kind of edge; and the skew is a circular average, each falling edge's error wrapped against the skew so
// far (a linear one is pulled to 0 by edges near half a symbol and can settle on the wrong side).
module ber_cdr #(
    parameter integer SER = 8
) (
    input  wire              clk,
    input  wire              rst,
    input  wire              restart,           // a write of RX_BER_CFG: the frame starts again at 0
    input  wire              track,             // 0: free-running at the nominal period (no correction)
    input  wire              one_pol,           // 1: track the rising edges, measure the falling ones (skew)
    input  wire [SER-1:0]    d,                 // CMP_I's samples this clock
    input  wire [15:0]       period,            // clocks a symbol (2 or more)
    input  wire [15:0]       offset,            // samples from the frame's start to the sampling point
    input  wire [3:0]        gain,
    output reg               bit_v,             // one clock: a symbol read
    output reg               bit_o,
    output reg signed [15:0] err_o,             // the last edge's error, in 1/16 sample
    output reg signed [31:0] corr_sum,          // the corrections since the restart, in 1/256 sample (the other
                                                // clock's offset: -corr_sum / 256 / samples elapsed)
    output reg        [31:0] edges,             // the transitions seen since the restart
    output reg signed [31:0] skew               // one_pol: the falling edges' mean place against the rising ones,
                                                // in 1/256 sample, wrapped into half a symbol either way
);
    localparam integer LS = (SER >= 8) ? 3 : (SER >= 4) ? 2 : (SER >= 2) ? 1 : 0;
    localparam integer IW = (LS > 0) ? LS : 1;
    localparam signed [31:0] STEP = SER * 256;
    localparam signed [31:0] CLAMP = 4 * 256;
    localparam integer       SK_SH = 6;          // skew's average: 2^6 falling edges

    // the settings in registers (they stand still while the check runs): L, L/2, and the sampling point S
    // (x 256; with one_pol moved by half the skew) as the constants the one-adder paths below need: S + 255 and
    // S - STEP
    reg signed [31:0] L, LH, S0, S255, S_STEP;
    always @(posedge clk) begin
        L      <= $signed({8'd0, period, 8'd0}) <<< LS;              // period x SER x 256
        LH     <= $signed({8'd0, period, 8'd0}) <<< (LS - 1 + (LS == 0));
        S0     <= $signed({8'd0, offset, 8'd0}) + (one_pol ? (skew >>> 1) : 32'sd0);
        S255   <= S0 + 32'sd255;
        S_STEP <= S0 - STEP;
    end

    reg  signed [31:0] pos;
    reg                taken;
    reg                prev;

    // ---- stage 0: the first transition this clock, with this clock's pos, and the clock's net change ----
    reg        e_found;
    reg [3:0]  e_k;
    integer    i;
    always @* begin
        e_found = 1'b0; e_k = 4'd0;
        for (i = SER - 1; i >= 0; i = i - 1) begin
            if (d[i] != ((i == 0) ? prev : d[(i == 0) ? 0 : i - 1])) begin
                e_found = 1'b1; e_k = i[3:0];
            end
        end
    end
    wire       e_up   = e_found && !prev && d[SER - 1];               // the clock rose, net
    wire       e_down = e_found && prev && !d[SER - 1];               // it fell, net
    wire signed [31:0] kk = ($signed({28'd0, e_k}) <<< 8) - 32'sd128;  // the edge's place in this clock
    reg               v1, u1, f1;                                     // an edge; it rose, it fell (net)
    reg signed [31:0] a1, b1;                                         // pos + kk, and the same less L
    // ---- stage 1: wrapped once into [0, L) ----
    reg               v2, u2, f2;
    reg signed [31:0] w2;
    // ---- stage 2: into [-L/2, L/2) ----
    reg               v3, u3, f3;
    reg signed [31:0] e3;
    // ---- one_pol: a falling edge's error against the skew so far, wrapped into [-L/2, L/2), then the step ----
    reg               vs, vw;
    reg signed [31:0] ds, dw;
    // ---- stage 3: the correction, and the three next-pos addends it makes ----
    reg               v4;
    reg signed [31:0] c4, cs4, csl4, csp4;                           // corr, STEP - corr, then less / plus L
    wire signed [31:0] e_sh = e3 >>> gain;
    wire signed [31:0] corr = !track ? 32'sd0 : (e_sh > CLAMP) ? CLAMP : (e_sh < -CLAMP) ? -CLAMP : e_sh;

    // ---- every clock: the next pos, one adder each way, the stage-3 correction in it if one is ready ----
    wire signed [31:0] add0 = v4 ? cs4  : STEP;
    wire signed [31:0] addm = v4 ? csl4 : STEP - L;
    wire signed [31:0] addp = v4 ? csp4 : STEP + L;
    wire signed [31:0] n0 = pos + add0;
    wire signed [31:0] nm = pos + addm;                               // n0 - L
    wire signed [31:0] np = pos + addp;                               // n0 + L

    // the sample: the first one at or past S, if this clock reaches S and the symbol is not read yet
    wire               reach  = (pos > S_STEP);                       // S - pos < STEP
    wire signed [31:0] up     = S255 - pos;                           // ceil((S - pos) / 256) x 256 + ...
    wire signed [31:0] idx_w  = (up < 32'sd256) ? 32'sd0 : (up >>> 8);
    wire [IW-1:0]      idx    = idx_w[IW-1:0];
    wire               take   = !taken && reach && (idx_w < SER);

    always @(posedge clk) begin
        bit_v <= 1'b0;
        if (rst || restart) begin
            pos <= 32'sd0; taken <= 1'b0; prev <= 1'b0; err_o <= 16'sd0; corr_sum <= 32'sd0; edges <= 32'd0;
            v1 <= 1'b0; v2 <= 1'b0; v3 <= 1'b0; v4 <= 1'b0; u1 <= 1'b0; u2 <= 1'b0; u3 <= 1'b0;
            f1 <= 1'b0; f2 <= 1'b0; f3 <= 1'b0;
            vs <= 1'b0; vw <= 1'b0; ds <= 32'sd0; dw <= 32'sd0; skew <= 32'sd0;
            a1 <= 32'sd0; b1 <= 32'sd0; w2 <= 32'sd0; e3 <= 32'sd0; c4 <= 32'sd0; cs4 <= 32'sd0; csl4 <= 32'sd0; csp4 <= 32'sd0;
        end else begin
            prev <= d[SER - 1];
            if (take) begin
                bit_v <= 1'b1;
                bit_o <= d[idx];
            end
            // the edge's error, a stage a clock
            v1 <= e_found; u1 <= e_up; f1 <= e_down; a1 <= pos + kk; b1 <= pos + kk - L;
            v2 <= v1;      u2 <= u1;   f2 <= f1;     w2 <= (b1 >= 0) ? b1 : a1;
            v3 <= v2;      u3 <= u2;   f3 <= f2;     e3 <= (w2 >= LH) ? w2 - L : w2;
            // one_pol: only a rising edge corrects the frame; a falling one steps the skew's circular average
            v4 <= one_pol ? u3 : v3;
            c4 <= corr; cs4 <= STEP - corr; csl4 <= STEP - corr - L; csp4 <= STEP - corr + L;
            vs <= one_pol && f3;  ds <= e3 - skew;
            vw <= vs;             dw <= (ds >= LH) ? ds - L : (ds < -LH) ? ds + L : ds;
            if (vw) skew <= skew + (dw >>> SK_SH);
            else if (skew >= LH) skew <= skew - L;
            else if (skew < -LH) skew <= skew + L;
            if (v3) begin
                err_o <= e3[19:4];
                edges <= edges + 1'b1;
            end
            if (v4) corr_sum <= corr_sum + c4;
            if (nm >= 0) begin
                pos <= nm; taken <= 1'b0;
            end else if (n0 < 0) begin
                pos <= np; taken <= 1'b1;
            end else begin
                pos <= n0; taken <= taken | take;
            end
        end
    end
endmodule
