// ihold: the interference hold (2026-10-30; BRINGUP_LOG 4.3-4.5).  A strong interferer drags the loop to a rail
// within milliseconds and the loop does not come back by itself; held (LOOP_HOLD) through the interferer it comes
// back in 50 ms, 24 times of 24.  This asks for the hold itself: while the chosen comparators keep changing, the
// loop is held, and it is released `hold` clocks after they were last busy.
//
// Each clock counts as active for a comparator of `mask` if it changed within the clock's SER samples (the previous
// clock's last sample counts); the actives are summed over a window of 2^(3 + wlog) clocks, and a window with
// `thresh` or more triggers.  With 256 clocks and 8 (the driver's defaults) a beat of 1 MHz and more on both Q windows
// triggers (a 5 MHz beat gives about 50), an event touches them twice, and the hold starts 3-5 us after the beat
// does: the drag takes milliseconds.  The default mask is the Q windows (QP, QN): the link's own BPSK data and A1 events move
// along I and leave them quiet, an A3 event touches each twice, and an interferer's beat crosses them once it reaches
// half the carrier.  A lost, beating loop also makes them chatter, and a hold must never keep it from locking again:
// after `max` clocks held without a break the hold lets go and cannot trigger again for `hold` clocks (the guard).
// The counts: holds started, clocks held; cleared by `clr`.
module ihold #(
    parameter integer SER = 8
) (
    input  wire              clk,
    input  wire              rst,
    input  wire              clr,
    input  wire              en,
    input  wire [6*SER-1:0]  fs,                // the fast samples, sample s in [6s+5:6s] (rx_engine's order)
    input  wire [4:0]        mask,              // {CMP_IN CMP_IP CMP_QN CMP_QP CMP_I}
    input  wire [2:0]        wlog,              // the window: 2^(3 + wlog) clocks (8 .. 1024)
    input  wire [7:0]        thresh,            // active comparator-clocks in a window that trigger
    input  wire [31:0]       hold,              // clocks held after the last triggering window (and the guard)
    input  wire [31:0]       max,               // the longest hold without a break
    output reg               active,            // the hold, to LOOP_HOLD
    output reg  [31:0]       n_holds,
    output reg  [31:0]       n_clocks,
    output reg  [7:0]        last_count         // the last window's count
);
    // a comparator changed this clock
    reg  [4:0] prev;
    reg  [4:0] chg;
    integer s, b;
    always @* begin
        chg = 5'd0;
        for (b = 0; b < 5; b = b + 1) begin
            if (fs[b] != prev[b]) chg[b] = 1'b1;
            for (s = 1; s < SER; s = s + 1)
                if (fs[6*s + b] != fs[6*(s - 1) + b]) chg[b] = 1'b1;
        end
    end
    wire [4:0] act = chg & mask;
    wire [2:0] n_act = {2'd0, act[0]} + {2'd0, act[1]} + {2'd0, act[2]} + {2'd0, act[3]} + {2'd0, act[4]};

    reg  [2:0]  n_act_q;                        // registered: the window's adder starts from a register
    reg  [10:0] wcnt;                           // clocks into the window
    reg  [10:0] acc;                            // actives so far in it
    wire [10:0] wlen_m1 = (11'd8 << wlog) - 11'd1;
    reg         trig;                           // the window just closed over the threshold
    reg  [31:0] since;                          // clocks since the last trigger (hold timer)
    reg  [31:0] run;                            // clocks held without a break
    reg  [31:0] guard;                          // clocks of the guard still to go

    always @(posedge clk) begin
        if (rst) begin
            prev <= 5'd0; n_act_q <= 3'd0; wcnt <= 11'd0; acc <= 11'd0; trig <= 1'b0;
            since <= 32'd0; run <= 32'd0; guard <= 32'd0; active <= 1'b0;
            n_holds <= 32'd0; n_clocks <= 32'd0; last_count <= 8'd0;
        end else begin
            prev <= {fs[6*(SER-1) + 4], fs[6*(SER-1) + 3], fs[6*(SER-1) + 2], fs[6*(SER-1) + 1], fs[6*(SER-1)]};
            n_act_q <= n_act;
            trig <= 1'b0;
            if (wcnt >= wlen_m1) begin
                wcnt <= 11'd0;
                acc <= 11'd0;
                trig <= ((acc + {8'd0, n_act_q}) >= {3'd0, thresh});
                last_count <= ((acc + {8'd0, n_act_q}) > 11'd255) ? 8'd255 : acc[7:0] + {5'd0, n_act_q};
            end else begin
                wcnt <= wcnt + 1'b1;
                acc <= acc + {8'd0, n_act_q};
            end
            if (guard != 32'd0) guard <= guard - 1'b1;

            if (!en) begin
                active <= 1'b0; run <= 32'd0; since <= 32'd0;
            end else if (active) begin
                n_clocks <= n_clocks + 1'b1;
                run <= run + 1'b1;
                since <= trig ? 32'd0 : since + 1'b1;
                if (run >= max) begin                        // too long: let go, and the guard
                    active <= 1'b0; run <= 32'd0; guard <= hold;
                end else if (!trig && since >= hold) begin   // quiet long enough
                    active <= 1'b0; run <= 32'd0;
                end
            end else if (trig && guard == 32'd0) begin
                active <= 1'b1; since <= 32'd0; run <= 32'd0;
                n_holds <= n_holds + 1'b1;
            end
            if (clr) begin
                n_holds <= 32'd0; n_clocks <= 32'd0;
            end
        end
    end
endmodule
