// tb_lockmon: lockmon.v against the comparator patterns of the bench (BRINGUP_LOG 4.15), with 1 ms looks (100 000
// clocks: 64 sub-windows of 1 562) and the reset thresholds (locked below 24 busy sub-windows, lost from 48):
//  * locked, the idle carrier beyond the IP window, Q still: locked; LD0 and LD4 green on, the rest off
//  * locked, BPSK data across both I windows, Q still: locked
//  * lost, a 50 kHz beat rotating the vector at full length (every window in turn): lost, one loss counted, LD1 blinks
//  * no carrier, every window low: no carrier, LD2 on, a second loss counted (locked, then no carrier)
//  * locked with 10 us bursts on Q every 100 us: never lost
//  * the seconds locked count; the software LEDs when auto is off
//
//     iverilog -g2005 -Wall -o tb_lockmon.vvp tb_lockmon.v lockmon.v && vvp -N tb_lockmon.vvp      (ends with PASS)
`timescale 1ns/1ps
module tb_lockmon;
    localparam integer SER = 8;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst = 1'b1;
    reg [6*SER-1:0] fs = {6*SER{1'b0}};
    reg [31:0] window = 32'd100000;
    reg        hold = 1'b0, auto = 1'b1;
    reg [9:0]  led_sw = 10'd0;
    wire [1:0] state;
    wire [31:0] n_losses, n_locked_s, last_ihigh;
    wire [15:0] last_qp, last_qn, last_i;
    wire [6:0]  last_busy;
    wire [3:0] led;
    wire [5:0] rgb;
    // CLK_HZ 1 MHz for the seconds and the blink, so they come round in simulated milliseconds
    lockmon #(.SER(SER), .CLK_HZ(1_000_000)) dut (.clk(clk), .rst(rst), .fs(fs), .window(window), .locked_below(8'd24),
        .lost_at(8'd48), .hold(hold), .auto(auto), .led_sw(led_sw), .state(state), .n_losses(n_losses),
        .n_locked_s(n_locked_s), .last_qp(last_qp), .last_qn(last_qn), .last_i(last_i), .last_ihigh(last_ihigh),
        .last_busy(last_busy), .led(led), .rgb(rgb));

    // {TRIG, IN, IP, QN, QP, I} as levels for the whole clock
    reg [5:0] lv = 6'd0;
    integer s;
    always @(negedge clk) for (s = 0; s < SER; s = s + 1) fs[6*s +: 6] = lv;

    integer errors = 0, k, rgb_on;
    real ph;
    task expect;
        input [8*48-1:0] what;
        input integer got, lo, hi;
        begin
            if (got < lo || got > hi) begin
                $display("FAIL %0s: %0d, want %0d..%0d", what, got, lo, hi); errors = errors + 1;
            end else $display("ok   %0s: %0d", what, got);
        end
    endtask
    task run;                               // n clocks of a pattern: 0 idle, 1 data, 2 beat, 3 none, 4 idle + bursts
        input integer pat, n;
        integer j;
        begin
            for (j = 0; j < n; j = j + 1) begin
                @(negedge clk);
                lv = 6'd0;
                case (pat)
                    0: begin lv[0] = 1'b1; lv[3] = 1'b1; end
                    1: begin lv[0] = (j / 4) % 2; lv[3] = (j / 4) % 2; lv[4] = !((j / 4) % 2); end
                    2: begin
                        ph = 6.2831853 * (j % 2000) / 2000.0;
                        lv[0] = $cos(ph) > 0; lv[3] = $cos(ph) > 0.5; lv[4] = $cos(ph) < -0.5;
                        lv[1] = $sin(ph) > 0.5; lv[2] = $sin(ph) < -0.5;
                    end
                    3: lv = 6'd0;
                    4: begin lv[0] = 1'b1; lv[3] = 1'b1;
                             if ((j % 10000) < 1000) begin lv[1] = (j / 7) % 2; lv[2] = ((j + 3) / 7) % 2; end end
                    default: lv = 6'd0;
                endcase
            end
        end
    endtask

    integer n_lost_seen;
    reg     count_ld1 = 1'b0;
    always @(posedge clk) if (count_ld1 && led[1]) n_lost_seen = n_lost_seen + 1;
    initial begin
        repeat (5) @(negedge clk);
        rst = 1'b0;
        run(0, 250000);
        expect("idle carrier: state (1 locked)", state, 1, 1);
        expect("idle carrier: LD0", led[0], 1, 1);
        expect("idle carrier: LD1..LD3 off", led[3:1], 0, 0);
        rgb_on = 0;
        for (k = 0; k < 64; k = k + 1) begin @(negedge clk); lv = 6'b001001; if (rgb[1]) rgb_on = rgb_on + 1; end
        expect("idle carrier: LD4 green lit 1/8 of the clocks", rgb_on, 7, 9);
        run(1, 250000);
        expect("BPSK data: state (1 locked)", state, 1, 1);
        run(2, 250000);
        expect("a 50 kHz beat: state (2 lost)", state, 2, 2);
        expect("a 50 kHz beat: QP changing clocks a look", last_qp, 80, 120);
        expect("losses", n_losses, 1, 1);
        expect("a 50 kHz beat: busy sub-windows", last_busy, 48, 64);
        count_ld1 = 1; n_lost_seen = 0;
        run(2, 600000);
        count_ld1 = 0;
        expect("lost: LD1 blinks (on about half)", n_lost_seen, 200000, 400000);
        run(0, 250000);
        expect("locked again", state, 1, 1);
        run(3, 250000);
        expect("no carrier: state (0)", state, 0, 0);
        expect("no carrier: LD2", led[2], 1, 1);
        expect("losses (locked, then no carrier)", n_losses, 2, 2);
        run(0, 250000);
        n_lost_seen = 0;
        for (k = 0; k < 20; k = k + 1) begin run(4, 100000); if (state == 2) n_lost_seen = n_lost_seen + 1; end
        expect("10 us bursts every 100 us on a lock: looks judged lost", n_lost_seen, 0, 0);
        expect("the bursts: busy sub-windows", last_busy, 0, 23);
        expect("the bursts: still locked", state, 1, 1);
        expect("losses unchanged by the bursts", n_losses, 2, 2);
        expect("seconds locked (CLK_HZ 1 MHz)", n_locked_s, 1, 10);
        hold = 1'b1; run(0, 1000); hold = 1'b0;
        expect("a hold: LD3 (stretched)", led[3], 1, 1);
        auto = 1'b0; led_sw = 10'b1010000101;
        @(negedge clk);
        expect("software LEDs: LD0..LD3", led, 4'b0101, 4'b0101);
        if (errors == 0) $display("PASS");
        else $display("FAILED: %0d", errors);
        $finish;
    end
endmodule
