// ihold: the interference hold and the signal holdover (2026-10-30; BRINGUP_LOG 4.3-4.5).  A strong interferer drags the loop to a rail
// within milliseconds and the loop does not come back by itself; held (LOOP_HOLD) through the interferer it comes
// back in 50 ms, 24 times of 24.  This asks for the hold itself: while the chosen comparators keep changing, the
// loop is held, and it is released `hold` clocks after they were last busy.
//
// Each clock counts as active for a comparator of `mask` if it changed within the clock's SER samples (the previous
// clock's last sample counts); over a window of 2^(3 + wlog) clocks, a window in which at least two of the chosen
// comparators (one if only one is chosen) were each active in thresh / 2 clocks or more triggers (busy), and the sum
// of the actives is the window's count (a quiet window: a quarter of `thresh` or less).  With 256 clocks and 8 (the driver's defaults) a beat of 1 MHz and more on both Q windows
// triggers (a 5 MHz beat gives about 50), an event touches them twice, and the hold starts 3-5 us after the beat
// does: the drag takes milliseconds.  The default mask is the Q windows (QP, QN): the link's own BPSK data and A1 events move
// along I and leave them quiet, an A3 event touches each twice, and an interferer's beat crosses them once it reaches
// half the carrier.  A lost, beating loop also makes them chatter, and a hold must never keep a lost loop frozen:
// so a hold starts only if a quiet window (a quarter of the threshold or less) came after the last busy one: an
// interferer arriving at a locked loop finds it armed, a lost loop's beat never does.  After `max` clocks held
// without a break the hold lets go, the guard (`hold` clocks) passes, and it can start again only after a quiet
// window (measured on the bench, 2026-10-30 19:30: without the arming a hold released at `max` under the CW froze
// the dragged loop 37 kHz off, re-holding its beat 86 times).
// `persist` (ID version 7; BRINGUP_LOG 4.13, 4.14): a hold starts only after that many busy windows in a row (0 and 1:
// the first).  A held loop's oscillator walks off the carrier's phase (about 0.1 rad in 6 ms), so every hold costs
// the decisions; bursts of noise (WiFi's frames, 10 us - 1 ms) do not drag the loop at all, yet each re-triggered
// the hold within its release, and held through a burst train A3 got 1-17 thousand of 20 000 events right against 21-32
// thousand free.  A CW near the carrier beats too slowly for the windows and trips them only now and then, in its
// crossings' chatter; each short hold lost the loop's phase under a CW it would have ridden out (5.0 GHz: 10 of 12
// lost held, 0 of 12 free).  What drags the loop is a CW 1-40 MHz off, busy in every window and pulling about
// 13-19 kHz a millisecond: a streak of half a millisecond lets it move the loop by less than the capture window,
// and ignores the bursts and the chatter.  A busy window during the streak keeps the hold armed; a quiet one ends it.
// `prop` (ID version 8; BRINGUP_LOG 4.14): the release scaled to the busy span.  A streak long enough to skip 100 us
// bursts lets a strong CW drag the loop 21-169 kHz first (340 kHz a ms with the error at its rail), so the hold must
// start at once; what costs the decisions is how long it lasts (the held oscillator's phase walks 0.1 rad in 6 ms).
// With prop n the hold lets go when quiet for the lesser of `hold` and (its busy span so far) << n plus a window: a
// 100 us burst holds about half a millisecond (n 2), a near CW's lone busy windows a few microseconds, a CW of seconds
// to its end plus `hold`.  0: `hold` always, as before.
// The counts: holds started, clocks held; cleared by `clr`.  The signal holdover (LEVEL 1) needs no arming: holding
// with the carrier gone cannot lose anything, and holding again after `max` keeps the oscillator near the carrier's
// frequency for when it returns.
//
// LEVEL = 1 makes the same machine the signal holdover: a clock counts if any sample has a comparator of `mask`
// high, and a window with fewer than `thresh` such clocks triggers.  The default mask is all four windows (IP, IN,
// QP, QN): the carrier's idle sits beyond one of them, BPSK data and events swing across them, and with the carrier
// gone I and Q sit in the middle and all four are quiet.  Someone in front of the antenna: the loop is held while the
// carrier is gone, so it is still at the carrier's frequency when the carrier comes back.  A lost loop's vector
// rotates at full length, and a vector of length a always has |I| or |Q| beyond a / sqrt 2 > a / 2, so a lost loop
// that is trying to pull in is never held by this one (with the I windows alone it would be, for a third of each
// beat: the reason for all four).
module ihold #(
    parameter integer SER   = 8,
    parameter integer LEVEL = 0                 // 0: the interference hold (changes, at thresh or more);
                                                // 1: the signal holdover (clocks with a comparator of mask high, under thresh)
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
    input  wire [15:0]       persist,           // busy windows in a row before a hold starts (0, 1: the first)
    input  wire [3:0]        prop,              // the release: the lesser of hold and the busy span << prop (0: hold)
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
    // LEVEL 1: this clock shows the carrier if any of its samples has a comparator of mask high
    reg        lvl;
    integer    s2;                              // its own loop variable (one shared by two always @* is multi-driven)
    always @* begin
        lvl = 1'b0;
        for (s2 = 0; s2 < SER; s2 = s2 + 1)
            if (|(fs[6*s2 +: 5] & mask)) lvl = 1'b1;
    end
    wire [2:0] n_act = (LEVEL != 0) ? {2'd0, lvl} :
                       {2'd0, act[0]} + {2'd0, act[1]} + {2'd0, act[2]} + {2'd0, act[3]} + {2'd0, act[4]};

    reg  [2:0]  n_act_q;                        // registered: the window's adder starts from a register
    reg  [4:0]  act_q;                          // LEVEL 0: which comparators changed, registered
    reg  [7:0]  c0, c1, c2, c3, c4;             // LEVEL 0: each comparator's changes in the window (saturating)
    // LEVEL 0's busy window: at least two of the chosen comparators (one, if only one is chosen) each changed at least
    // thresh / 2 times.  An interferer's beat swings Q across both Q windows; noise on a Q leg that sits at one window's
    // threshold (no hysteresis) chatters only that one: measured on the bench, 2026-10-30 20:30, where such chatter
    // after a CW held the loop by itself until the maximum
    wire [7:0]  half = {1'b0, thresh[7:1]};
    function [7:0] sat8;
        input [7:0] cnt;
        input       inc;
        begin
            sat8 = (cnt == 8'd255) ? cnt : cnt + {7'd0, inc};
        end
    endfunction
    wire [7:0]  e0 = sat8(c0, act_q[0]), e1 = sat8(c1, act_q[1]), e2 = sat8(c2, act_q[2]), e3 = sat8(c3, act_q[3]),
                e4 = sat8(c4, act_q[4]);
    wire [2:0]  n_hit = {2'd0, mask[0] && e0 >= half} + {2'd0, mask[1] && e1 >= half} + {2'd0, mask[2] && e2 >= half}
                      + {2'd0, mask[3] && e3 >= half} + {2'd0, mask[4] && e4 >= half};
    wire [2:0]  n_mask = {2'd0, mask[0]} + {2'd0, mask[1]} + {2'd0, mask[2]} + {2'd0, mask[3]} + {2'd0, mask[4]};
    wire        busy0 = (n_hit >= ((n_mask >= 3'd2) ? 3'd2 : 3'd1)) && (n_mask != 3'd0);
    reg  [10:0] wcnt;                           // clocks into the window
    reg  [10:0] acc;                            // actives so far in it
    wire [10:0] wlen_m1 = (11'd8 << wlog) - 11'd1;
    reg         trig;                           // the window just closed over the threshold
    reg         wclose;                         // a window just closed
    reg  [15:0] streak;                         // busy windows in a row before this one
    wire [16:0] streak_now = {1'b0, streak} + 17'd1;            // with this one, when trig
    wire        long_enough = (persist <= 16'd1) || (streak_now >= {1'b0, persist});
    reg  [31:0] since;                          // clocks since the last trigger (hold timer)
    reg  [31:0] run;                            // clocks held without a break
    reg  [31:0] guard;                          // clocks of the guard still to go
    reg         armed;                          // LEVEL 0: a quiet window came after the last busy one
    // the release while held: the busy span so far (run - since) scaled, saturating at hold; registered in three
    // steps (in one clock the subtract, the shift, the add and the compare missed 100 MHz by 3 ns: ID 8's first
    // build).  Three clocks late is nothing against a window of 64 clocks or more, and the least release (a window
    // and a clock) is longer than the pipeline, so a hold just started never meets a stale one
    reg  [31:0] span_q, rel;
    reg  [47:0] scaled_q;

    always @(posedge clk) begin
        if (rst) begin
            prev <= 5'd0; n_act_q <= 3'd0; wcnt <= 11'd0; acc <= 11'd0; trig <= 1'b0; wclose <= 1'b0; streak <= 16'd0;
            act_q <= 5'd0; c0 <= 8'd0; c1 <= 8'd0; c2 <= 8'd0; c3 <= 8'd0; c4 <= 8'd0;
            since <= 32'd0; run <= 32'd0; guard <= 32'd0; active <= 1'b0; armed <= 1'b0;
            span_q <= 32'd0; scaled_q <= 48'd0; rel <= 32'd0;
            n_holds <= 32'd0; n_clocks <= 32'd0; last_count <= 8'd0;
        end else begin
            prev <= {fs[6*(SER-1) + 4], fs[6*(SER-1) + 3], fs[6*(SER-1) + 2], fs[6*(SER-1) + 1], fs[6*(SER-1)]};
            span_q   <= run - since;
            scaled_q <= ({16'd0, span_q} << prop) + {37'd0, wlen_m1} + 48'd1;
            rel      <= (prop == 4'd0 || scaled_q >= {16'd0, hold}) ? hold : scaled_q[31:0];
            n_act_q <= n_act;
            act_q <= act;
            trig <= 1'b0;
            wclose <= 1'b0;
            if (wclose) streak <= !trig ? 16'd0 : (streak == 16'hFFFF) ? streak : streak + 1'b1;
            if (wcnt >= wlen_m1) begin
                wcnt <= 11'd0;
                wclose <= 1'b1;
                acc <= 11'd0;
                c0 <= 8'd0; c1 <= 8'd0; c2 <= 8'd0; c3 <= 8'd0; c4 <= 8'd0;
                // LEVEL 0 arms on a quiet window (a quarter of the threshold or less) and disarms on a busy one that
                // starts no hold: an interferer arriving at a locked loop finds it armed, a lost loop never is
                if ((acc + {8'd0, n_act_q}) <= {5'd0, thresh[7:2]}) armed <= 1'b1;
                trig <= (LEVEL != 0) ? ((acc + {8'd0, n_act_q}) < {3'd0, thresh}) : busy0;
                last_count <= ((acc + {8'd0, n_act_q}) > 11'd255) ? 8'd255 : acc[7:0] + {5'd0, n_act_q};
            end else begin
                wcnt <= wcnt + 1'b1;
                acc <= acc + {8'd0, n_act_q};
                c0 <= e0; c1 <= e1; c2 <= e2; c3 <= e3; c4 <= e4;
            end
            if (guard != 32'd0) guard <= guard - 1'b1;

            if (!en) begin
                active <= 1'b0; run <= 32'd0; since <= 32'd0;
            end else if (active) begin
                n_clocks <= n_clocks + 1'b1;
                run <= run + 1'b1;
                since <= trig ? 32'd0 : since + 1'b1;
                if (run >= max) begin                        // too long: let go, the guard, and disarmed
                    active <= 1'b0; run <= 32'd0; guard <= hold; armed <= 1'b0;
                end else if (!trig && since >= rel) begin    // quiet long enough
                    active <= 1'b0; run <= 32'd0;
                end
            end else if (trig && guard == 32'd0 && (armed || LEVEL != 0)) begin
                if (long_enough) begin                      // busy for `persist` windows in a row: hold
                    active <= 1'b1; since <= 32'd0; run <= 32'd0; armed <= 1'b0;
                    n_holds <= n_holds + 1'b1;
                end                                         // else still armed, counting the streak
            end else if (trig) begin
                armed <= 1'b0;                              // busy and not allowed to hold: disarmed
            end
            if (clr) begin
                n_holds <= 32'd0; n_clocks <= 32'd0;
            end
        end
    end
endmodule
