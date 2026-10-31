// tb_ihold: ihold.v against the comparator patterns the bench met (BRINGUP_LOG 4.3-4.5):
//  * quiet, then the link's own A3 events (QP or QN up for 20 clocks every 2000): no hold;
//  * BPSK data on I (CMP_I toggling every 4 clocks, the Q windows quiet): no hold;
//  * an interferer's beat, QP and QN toggling every 10 clocks (a 5 MHz beat) for 50 000 clocks: held within two
//    windows (256 clocks each) of its start, released `hold` clocks after its end, one hold counted;
//  * a beat that never stops: released after `max` and not held again while it lasts (no quiet window to arm it);
//  * a lost, beating loop with no quiet window before it: never held; quiet, then an interferer: held;
//  * persist (ID version 7) at 195 windows (0.5 ms): bursts of the beat (10 and 100 us) and a near CW's chatter (one
//    busy window in 20) never hold, though the same chatter holds at persist 0; a streak broken by one quiet window
//    does not hold; a beat that lasts holds after 195 windows;
//  and the signal holdover (LEVEL 1, the I windows): no hold with the carrier, under BPSK data or for a lost loop's
//  beat; held within two windows of the carrier's loss, released `hold` after its return; let go at `max`.
//
//     iverilog -g2005 -Wall -o tb_ihold.vvp tb_ihold.v ihold.v && vvp -N tb_ihold.vvp      (ends with PASS)
`timescale 1ns/1ps
module tb_ihold;
    localparam integer SER = 8;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst = 1'b1, clr = 1'b0, en = 1'b1;
    reg [6*SER-1:0] fs = {6*SER{1'b0}};
    reg [4:0]  mask = 5'b00110;
    reg [2:0]  wlog = 3'd5;                     // 256 clocks
    reg [7:0]  thresh = 8'd8;
    reg [31:0] hold = 32'd1000, max = 32'd20000;
    reg [15:0] persist = 16'd0;
    wire active;
    wire [31:0] n_holds, n_clocks;
    wire [7:0] last_count;
    // the signal holdover: the four windows (IP, IN, QP, QN) show the carrier; 256 clocks, under 64 of them triggers
    reg        en_s = 1'b1;
    reg [31:0] hold_s = 32'd1000, max_s = 32'd100000;
    wire active_s;
    wire [31:0] n_holds_s, n_clocks_s;
    wire [7:0] last_count_s;
    ihold #(.SER(SER), .LEVEL(1)) dut_s (.clk(clk), .rst(rst), .clr(clr), .en(en_s), .fs(fs), .mask(5'b11110), .wlog(3'd5),
                            .thresh(8'd64), .hold(hold_s), .max(max_s), .persist(16'd0), .active(active_s), .n_holds(n_holds_s),
                            .n_clocks(n_clocks_s), .last_count(last_count_s));

    ihold #(.SER(SER)) dut (.clk(clk), .rst(rst), .clr(clr), .en(en), .fs(fs), .mask(mask), .wlog(wlog), .thresh(thresh),
                            .hold(hold), .max(max), .persist(persist), .active(active), .n_holds(n_holds), .n_clocks(n_clocks),
                            .last_count(last_count));

    // the comparators, as levels for the whole clock (each sample the same)
    reg [4:0] lv = 5'd0;
    integer s;
    always @(negedge clk) for (s = 0; s < SER; s = s + 1) fs[6*s +: 5] = lv;

    integer errors = 0, k, t_on, t_first, t_off, t_rel;
    task expect;
        input [8*40-1:0] what;
        input integer got, lo, hi;
        begin
            if (got < lo || got > hi) begin
                $display("FAIL %0s: %0d, want %0d..%0d", what, got, lo, hi); errors = errors + 1;
            end else $display("ok   %0s: %0d", what, got);
        end
    endtask

    integer held;
    real    ph;
    initial begin
        repeat (5) @(negedge clk);
        rst = 1'b0;
        // quiet, then A3 events
        held = 0;
        for (k = 0; k < 20000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0;
            if ((k % 2000) < 20) lv[(k / 2000) % 2 ? 2 : 1] = 1'b1;
            if (active) held = held + 1;
        end
        expect("clocks held under events", held, 0, 0);
        // BPSK on I
        for (k = 0; k < 20000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0; lv[0] = (k / 4) % 2;
            if (active) held = held + 1;
        end
        expect("clocks held under BPSK data on I", held, 0, 0);
        expect("holds so far", n_holds, 0, 0);
        // noise on one Q window: QP chattering every 2 clocks for 10 000 clocks (the Q leg at its threshold), QN quiet:
        // no hold (one comparator only)
        held = 0;
        for (k = 0; k < 10000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0; lv[1] = (k / 2) % 2;
            if (active) held = held + 1;
        end
        expect("clocks held with one Q window chattering on noise", held, 0, 0);
        for (k = 0; k < 2000; k = k + 1) @(negedge clk) lv = 5'd0;
        // a 5 MHz beat on the Q windows for 50 000 clocks (the longest hold well beyond it)
        max = 32'd1000000;
        t_first = -1; t_rel = -1;
        for (k = 0; k < 52000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0;
            if (k < 50000) begin lv[1] = (k / 10) % 2; lv[2] = ((k + 5) / 10) % 2; end
            if (active && t_first < 0) t_first = k;
            if (!active && t_first >= 0 && t_rel < 0 && k > 50000) t_rel = k;
        end
        expect("clocks from the beat's start to the hold", t_first, 0, 2 * 256 + 4);
        expect("clocks from the beat's end to the release", t_rel - 50000, 1000, 1000 + 2 * 256 + 4);
        expect("holds", n_holds, 1, 1);
        // a beat that never stops: released at max, the guard, then held again
        max = 32'd20000;
        t_first = -1; t_off = -1; t_rel = -1;
        for (k = 0; k < 30000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0; lv[1] = (k / 10) % 2; lv[2] = ((k + 5) / 10) % 2;
            if (active && t_first < 0) t_first = k;
            if (!active && t_first >= 0 && t_off < 0) t_off = k;
            if (active && t_off >= 0 && t_rel < 0) t_rel = k;
        end
        expect("a beat that never stops: held for (max)", t_off - t_first, 20000, 20002);
        expect("then not again while it lasts (no quiet window)", t_rel, -1, -1);
        expect("holds", n_holds, 2, 2);
        // a lost, beating loop from the start (no quiet window before it): never held
        rst = 1'b1; repeat (3) @(negedge clk); rst = 1'b0;
        held = 0;
        for (k = 0; k < 20000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0; lv[1] = (k / 10) % 2; lv[2] = ((k + 5) / 10) % 2;
            if (active) held = held + 1;
        end
        expect("a beating loop with no quiet window before it: clocks held", held, 0, 0);
        // quiet again, then an interferer: held
        t_first = -1;
        for (k = 0; k < 6000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0;
            if (k >= 3000) begin lv[1] = (k / 10) % 2; lv[2] = ((k + 5) / 10) % 2; end
            if (active && t_first < 0) t_first = k;
        end
        expect("quiet, then an interferer: clocks to the hold", t_first - 3000, 0, 2 * 256 + 4);
        // ---- persist: a hold only after 195 busy windows in a row ----
        max = 32'd1000000;
        for (k = 0; k < 2; k = k + 1) begin              // a near CW's chatter: one busy window in 20, at persist 0 and 195
            persist = k ? 16'd195 : 16'd0;
            rst = 1'b1; repeat (3) @(negedge clk); rst = 1'b0;
            for (t_on = 0; t_on < 2000; t_on = t_on + 1) @(negedge clk) lv = 5'd0;
            held = 0;
            for (t_on = 0; t_on < 20 * 256 * 12; t_on = t_on + 1) begin
                @(negedge clk);
                lv = 5'd0;
                if ((t_on / 256) % 20 == 7) begin lv[1] = (t_on / 10) % 2; lv[2] = ((t_on + 5) / 10) % 2; end
                if (active) held = held + 1;
            end
            if (k == 0) expect("persist 0: a near CW's chatter (a busy window in 20) holds: holds", n_holds, 1, 12);
            else expect("persist 195: the same chatter: clocks held", held, 0, 0);
        end
        persist = 16'd195;
        rst = 1'b1; repeat (3) @(negedge clk); rst = 1'b0;
        for (k = 0; k < 2000; k = k + 1) @(negedge clk) lv = 5'd0;
        held = 0;
        for (k = 0; k < 10 * 10000; k = k + 1) begin      // 10 us bursts of the beat every 100 us
            @(negedge clk);
            lv = 5'd0;
            if ((k % 10000) < 1000) begin lv[1] = (k / 10) % 2; lv[2] = ((k + 5) / 10) % 2; end
            if (active) held = held + 1;
        end
        for (k = 0; k < 5 * 20000; k = k + 1) begin       // 100 us bursts every 200 us
            @(negedge clk);
            lv = 5'd0;
            if ((k % 20000) < 10000) begin lv[1] = (k / 10) % 2; lv[2] = ((k + 5) / 10) % 2; end
            if (active) held = held + 1;
        end
        expect("persist 195: bursts of 10 and 100 us: clocks held", held, 0, 0);
        for (k = 0; k < 2000; k = k + 1) @(negedge clk) lv = 5'd0;
        for (k = 0; k < 201 * 256; k = k + 1) begin       // a beat of 100 windows, one quiet, 100 more: the streak broken
            @(negedge clk);
            lv = 5'd0;
            if ((k / 256) != 100) begin lv[1] = (k / 10) % 2; lv[2] = ((k + 5) / 10) % 2; end
            if (active) held = held + 1;
        end
        expect("persist 195: a streak broken by a quiet window: clocks held", held, 0, 0);
        for (k = 0; k < 2000; k = k + 1) @(negedge clk) lv = 5'd0;
        t_first = -1;
        for (k = 0; k < 260 * 256; k = k + 1) begin       // a beat that lasts: held after 195 windows
            @(negedge clk);
            lv = 5'd0; lv[1] = (k / 10) % 2; lv[2] = ((k + 5) / 10) % 2;
            if (active && t_first < 0) t_first = k;
        end
        expect("persist 195: a lasting beat: clocks to the hold", t_first, 194 * 256, 196 * 256 + 4);
        expect("persist 195: holds", n_holds, 1, 1);
        persist = 16'd0;
        // disabled: no hold at all
        en = 1'b0;
        held = 0;
        for (k = 0; k < 5000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0; lv[1] = (k / 10) % 2;
            if (active) held = held + 1;
        end
        expect("clocks held when disabled", held, 0, 0);
        // ---- the signal holdover ----
        en = 1'b0;
        rst = 1'b1; repeat (3) @(negedge clk); rst = 1'b0;
        // the carrier's idle beyond IP: present, no hold
        held = 0;
        for (k = 0; k < 10000; k = k + 1) begin
            @(negedge clk); lv = 5'b01000; if (active_s) held = held + 1;
        end
        expect("signal holdover: clocks held with the carrier", held, 0, 0);
        // BPSK data: IP and IN in turn, 4 clocks each: present
        for (k = 0; k < 10000; k = k + 1) begin
            @(negedge clk); lv = ((k / 4) % 2) ? 5'b10001 : 5'b01000; if (active_s) held = held + 1;
        end
        expect("signal holdover: clocks held under BPSK data", held, 0, 0);
        // a lost loop's beat at 50 kHz: the vector rotates at full length, each window high where its arm is beyond
        // half of it
        for (k = 0; k < 20000; k = k + 1) begin
            @(negedge clk);
            ph = 6.2831853 * (k % 2000) / 2000.0;
            lv = 5'd0;
            if ($cos(ph) > 0.5) lv[3] = 1'b1;
            if ($cos(ph) < -0.5) lv[4] = 1'b1;
            if ($sin(ph) > 0.5) lv[1] = 1'b1;
            if ($sin(ph) < -0.5) lv[2] = 1'b1;
            if (active_s) held = held + 1;
        end
        expect("signal holdover: clocks held for a beating, lost loop", held, 0, 0);
        // the carrier gone for 20 000 clocks (someone in front of the antenna), then back
        t_first = -1; t_rel = -1;
        for (k = 0; k < 24000; k = k + 1) begin
            @(negedge clk);
            lv = (k < 20000) ? 5'd0 : 5'b01000;
            if (active_s && t_first < 0) t_first = k;
            if (!active_s && t_first >= 0 && t_rel < 0) t_rel = k;
        end
        expect("signal holdover: clocks from the carrier's loss to the hold", t_first, 0, 2 * 256 + 4);
        expect("signal holdover: clocks from its return to the release", t_rel - 20000, 1000 - 256, 1000 + 2 * 256 + 4);
        expect("signal holdover: holds", n_holds_s, 1, 1);
        // gone for good: let go at max, the guard, held again
        t_first = -1; t_off = -1; t_rel = -1;
        for (k = 0; k < 120000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0;
            if (active_s && t_first < 0) t_first = k;
            if (!active_s && t_first >= 0 && t_off < 0) t_off = k;
            if (active_s && t_off >= 0 && t_rel < 0) t_rel = k;
        end
        expect("signal holdover: gone for good: held for (max)", t_off - t_first, 100000, 100002);
        expect("signal holdover: then off for at least the guard", t_rel - t_off, 1000, 1000 + 2 * 256 + 4);
        en_s = 1'b0;
        held = 0;
        for (k = 0; k < 3000; k = k + 1) begin
            @(negedge clk); lv = 5'd0; if (active_s) held = held + 1;
        end
        expect("signal holdover: clocks held when disabled", held, 0, 0);
        if (errors == 0) $display("PASS");
        else $display("FAILED: %0d", errors);
        $finish;
    end
endmodule
