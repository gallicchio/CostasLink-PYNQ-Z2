// lockmon: the lock's state judged in gateware, for the status registers and the LEDs (ID version 8, 2026-10-31;
// BRINGUP_LOG 4.15, REVB U1: the boards run unattended, and setting them up should not need a laptop on a roof).
//
// Every `window` clocks (reset: 10 ms) it looks at 64 sub-windows: in how many both Q window comparators (CMP_QP,
// CMP_QN) changed, and in how many clocks either I window (CMP_IP, CMP_IN) was high, and judges:
//   no carrier  the I windows hardly ever high (under 1/64 of the look) and Q busy in fewer than locked_below
//               sub-windows: nothing arrives
//   locked      Q busy in fewer than locked_below of the 64 (reset 24), the I windows high in more than a quarter: the
//               carrier on I (idle beyond one window, or BPSK data across both); the link's own data moves along I only
//   lost        Q busy in lost_at or more (reset 48): a beat swings Q across both windows all the time
//   unsure      anything else (a dense train of bursts, an interferer passing)
// Counting changes alone cannot tell noise bursts from a beat (bursts of 10 us every 100 us read lost in every look
// on the simulation); a beat is busy in every sub-window, bursts in a few (one of 10 us straddles 1-2 sub-windows,
// so bursts of 10 % duty touch about 16 of 64): as linkd learned on the
// bench, where the comparators' chatter under bursts drew needless recoveries (BRINGUP_LOG 4.15).  A 45 kHz false
// lock beats every 22 us, a 5 kHz one every 200 us: both fill the 156 us sub-windows of a 10 ms look.  It counts the
// losses (a look locked, the next lost or no carrier) and the seconds locked, and keeps each look's changes.  It judges from the windows' thresholds as software set them
// (0.5 a in the bench's runs): with the thresholds at their reset, the judgement means little.
//
// The PYNQ-Z2's own LEDs, while the auto bit is set (reset): LD0 locked, LD1 lost (blinking), LD2 no carrier, LD3
// a hold (interference or holdover) active (stretched to 100 ms so it is seen); LD4 green locked, red lost
// (blinking), red no carrier, yellow unsure, blue held; LD5 set by software (linkd: recovering).  The RGB LEDs are
// run at 1/8 duty: at full drive they glare.
module lockmon #(
    parameter integer SER    = 8,
    parameter integer CLK_HZ = 100_000_000
) (
    input  wire              clk,
    input  wire              rst,
    input  wire [6*SER-1:0]  fs,                // the fast samples, sample s in [6s+5:6s] {TRIG, IN, IP, QN, QP, I}
    input  wire [31:0]       window,            // clocks a look
    input  wire [7:0]        locked_below,      // Q busy in fewer of the 64 sub-windows: still (reset 16)
    input  wire [7:0]        lost_at,           // Q busy in this many or more: a beat (reset 48)
    input  wire              hold,              // the loop held (any hold): LD3, blue on LD4
    input  wire              own,               // this board's own event on the pins (tx_engine's tx_busy): its Q moves
    input  wire              auto,              // LEDs from the state (else from led_sw)
    input  wire [9:0]        led_sw,            // {LD5 RGB, LD4 RGB, LD3..LD0} when not auto; LD5 always from here
    output reg  [1:0]        state,             // 0 no carrier, 1 locked, 2 lost, 3 unsure
    output reg  [31:0]       n_losses,
    output reg  [31:0]       n_locked_s,
    output reg  [15:0]       last_qp,
    output reg  [15:0]       last_qn,
    output reg  [15:0]       last_i,
    output reg  [31:0]       last_ihigh,
    output reg  [6:0]        last_busy,         // the last look's sub-windows with both Q windows changing (of 64)
    output wire [3:0]        led,               // LD0..LD3
    output wire [5:0]        rgb                // {LD5 R G B, LD4 R G B}: the board file's order is B, G, R from bit 0
);
    localparam [1:0] S_NONE = 2'd0, S_LOCKED = 2'd1, S_LOST = 2'd2, S_UNSURE = 2'd3;
    // which comparators changed this clock, and whether an I window was high
    reg  [2:0] prev;
    reg  [2:0] chg;
    reg        ihi;
    integer    s;
    always @* begin
        chg = 3'd0;
        ihi = 1'b0;
        for (s = 0; s < SER; s = s + 1) begin
            if (s == 0) begin
                if (fs[0] != prev[0]) chg[0] = 1'b1;
                if (fs[1] != prev[1]) chg[1] = 1'b1;
                if (fs[2] != prev[2]) chg[2] = 1'b1;
            end else begin
                if (fs[6*s]     != fs[6*(s-1)])     chg[0] = 1'b1;
                if (fs[6*s + 1] != fs[6*(s-1) + 1]) chg[1] = 1'b1;
                if (fs[6*s + 2] != fs[6*(s-1) + 2]) chg[2] = 1'b1;
            end
            if (fs[6*s + 3] || fs[6*s + 4]) ihi = 1'b1;
        end
    end

    // the board's own single symbols (A2, A3 step Q, A3 and A1 flip I) and their settling are not a beat: the Q windows'
    // changes during an event and GUARD clocks after are not counted (ID version 9; the self-test's A2 / A3 read lost in
    // every look on ID 8, 2026-10-31).  A beat changes Q between the events as well, so it still reads lost
    localparam [7:0] GUARD = 8'd64;
    reg  [7:0]  own_g;
    wire        mute = own || own_g != 8'd0;
    wire        cq1 = chg[1] & ~mute, cq2 = chg[2] & ~mute;
    reg  [31:0] wcnt, ihigh, sec, scnt;
    reg  [15:0] ci, cqp, cqn;
    reg         sqp, sqn;                       // QP / QN changed in this sub-window
    reg  [6:0]  busy;                           // sub-windows busy so far in this look
    wire [31:0] sub = (window >> 6) == 32'd0 ? 32'd1 : (window >> 6);
    function [15:0] inc16;
        input [15:0] c;
        input        b;
        begin
            inc16 = (c == 16'hFFFF) ? c : c + {15'd0, b};
        end
    endfunction
    // the judgement of the look that just closed
    wire        dark  = ihigh < (window >> 6);
    wire        still = {1'b0, busy} < locked_below;
    wire        on_i  = ihigh > (window >> 2);
    wire        beat  = {1'b0, busy} >= lost_at;
    wire [1:0]  judge = (dark && still) ? S_NONE : (still && on_i) ? S_LOCKED : beat ? S_LOST : S_UNSURE;

    // the LEDs' clocks: a 2 Hz blink, a 1/8 duty for the RGB, a 100 ms stretch for the hold
    reg  [31:0] blink_cnt, stretch;
    reg         blink;
    reg  [2:0]  pwm;
    always @(posedge clk) begin
        if (rst) begin
            prev <= 3'd0; wcnt <= 32'd0; ihigh <= 32'd0; ci <= 16'd0; cqp <= 16'd0; cqn <= 16'd0; own_g <= 8'd0;
            scnt <= 32'd0; sqp <= 1'b0; sqn <= 1'b0; busy <= 7'd0; last_busy <= 7'd0;
            state <= S_NONE; n_losses <= 32'd0; n_locked_s <= 32'd0; sec <= 32'd0;
            last_qp <= 16'd0; last_qn <= 16'd0; last_i <= 16'd0; last_ihigh <= 32'd0;
            blink_cnt <= 32'd0; blink <= 1'b0; pwm <= 3'd0; stretch <= 32'd0;
        end else begin
            prev <= {fs[6*(SER-1) + 2], fs[6*(SER-1) + 1], fs[6*(SER-1)]};
            own_g <= own ? GUARD : (own_g != 8'd0 ? own_g - 8'd1 : 8'd0);
            // the sub-windows: busy when both Q windows changed in it
            if (scnt + 32'd1 >= sub) begin
                scnt <= 32'd0; sqp <= 1'b0; sqn <= 1'b0;
                if ((sqp || cq1) && (sqn || cq2) && busy != 7'd127) busy <= busy + 1'b1;
            end else begin
                scnt <= scnt + 1'b1; sqp <= sqp | cq1; sqn <= sqn | cq2;
            end
            if (wcnt + 32'd1 >= window) begin
                wcnt <= 32'd0;
                if (state == S_LOCKED && (judge == S_LOST || judge == S_NONE)) n_losses <= n_losses + 1'b1;
                state <= judge;
                last_qp <= cqp; last_qn <= cqn; last_i <= ci; last_ihigh <= ihigh; last_busy <= busy;
                busy <= 7'd0; scnt <= 32'd0; sqp <= 1'b0; sqn <= 1'b0;
                ci <= {15'd0, chg[0]}; cqp <= {15'd0, cq1}; cqn <= {15'd0, cq2}; ihigh <= {31'd0, ihi};
            end else begin
                wcnt <= wcnt + 1'b1;
                ci <= inc16(ci, chg[0]); cqp <= inc16(cqp, cq1); cqn <= inc16(cqn, cq2);
                ihigh <= ihigh + {31'd0, ihi};
            end
            if (state == S_LOCKED) begin
                if (sec + 32'd1 >= CLK_HZ) begin sec <= 32'd0; n_locked_s <= n_locked_s + 1'b1; end
                else sec <= sec + 1'b1;
            end
            if (blink_cnt + 32'd1 >= CLK_HZ / 4) begin blink_cnt <= 32'd0; blink <= ~blink; end
            else blink_cnt <= blink_cnt + 1'b1;
            pwm <= pwm + 1'b1;
            if (hold) stretch <= CLK_HZ / 10;
            else if (stretch != 32'd0) stretch <= stretch - 1'b1;
        end
    end

    wire       held = hold || stretch != 32'd0;
    wire [3:0] led_auto = {held, state == S_NONE, state == S_LOST && blink, state == S_LOCKED};
    // LD4 as {R, G, B}
    wire [2:0] ld4_auto = held ? 3'b001 :
                          (state == S_LOCKED) ? 3'b010 :
                          (state == S_LOST) ? {blink, 2'b00} :
                          (state == S_NONE) ? 3'b100 : 3'b110;
    wire [2:0] ld4 = auto ? ld4_auto : led_sw[6:4];
    wire [2:0] ld5 = led_sw[9:7];
    wire       lit = (pwm == 3'd0);
    assign led = auto ? led_auto : led_sw[3:0];
    // the board file's order: rgb_led_tri_o_0..2 = LD4 B, G, R; 3..5 = LD5 B, G, R
    assign rgb = {ld5[2] & lit, ld5[1] & lit, ld5[0] & lit, ld4[2] & lit, ld4[1] & lit, ld4[0] & lit};
endmodule
