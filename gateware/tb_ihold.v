// tb_ihold: ihold.v against the comparator patterns the bench met (BRINGUP_LOG 4.3-4.5):
//  * quiet, then the link's own A3 events (QP or QN up for 20 clocks every 2000): no hold;
//  * BPSK data on I (CMP_I toggling every 4 clocks, the Q windows quiet): no hold;
//  * an interferer's beat, QP and QN toggling every 10 clocks (a 5 MHz beat) for 50 000 clocks: held within two
//    windows (256 clocks each) of its start, released `hold` clocks after its end, one hold counted;
//  * a beat that never stops (a lost, beating loop): released after `max`, the guard keeps it off for `hold`, then
//    it holds again.
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
    wire active;
    wire [31:0] n_holds, n_clocks;
    wire [7:0] last_count;
    ihold #(.SER(SER)) dut (.clk(clk), .rst(rst), .clr(clr), .en(en), .fs(fs), .mask(mask), .wlog(wlog), .thresh(thresh),
                            .hold(hold), .max(max), .active(active), .n_holds(n_holds), .n_clocks(n_clocks),
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
        expect("then off for at least the guard", t_rel - t_off, 1000, 1000 + 2 * 256 + 4);
        expect("holds", n_holds, 3, 3);
        // disabled: no hold at all
        en = 1'b0;
        held = 0;
        for (k = 0; k < 5000; k = k + 1) begin
            @(negedge clk);
            lv = 5'd0; lv[1] = (k / 10) % 2;
            if (active) held = held + 1;
        end
        expect("clocks held when disabled", held, 0, 0);
        if (errors == 0) $display("PASS");
        else $display("FAILED: %0d", errors);
        $finish;
    end
endmodule
