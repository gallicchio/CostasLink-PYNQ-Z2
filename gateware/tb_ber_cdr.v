// tb_ber_cdr: ber_cdr.v against a transmitter on another clock: PRBS15 symbols of period x SER x (1 + ppm) samples,
// each edge moved by up to +-JIT samples at random (the comparator's noise: glitches near the edges), from a random
// starting phase.  The self-synchronising check (b ^ b-14 ^ b-15) on what ber_cdr reads, after SETTLE symbols:
// no failure with the tracking on, at every period and offset; with it off and the clocks apart, failures (the
// control).  CMP_I's rising edges `dr` samples later than its falling ones (duty-cycle distortion, BRINGUP_LOG 4.9):
// with both kinds of edge tracked some restarts lock between them and read random bits (the control); with one_pol,
// none at any restart's phase, and RX_CDR_SKEW's skew reads the -dr it is.
//
//     iverilog -g2005 -Wall -o tb_ber_cdr.vvp tb_ber_cdr.v ber_cdr.v && vvp -N tb_ber_cdr.vvp     (ends with PASS)
`timescale 1ns/1ps
module tb_ber_cdr;
    localparam integer SER = 8;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst = 1'b1, restart = 1'b0, track = 1'b1, one_pol = 1'b0;
    reg [15:0] period = 16'd10, offset = 16'd40;
    reg [3:0]  gain = 4'd4;
    reg [SER-1:0] d = {SER{1'b0}};
    wire bit_v, bit_o;
    wire signed [15:0] err_o;
    wire signed [31:0] corr_sum;
    wire [31:0] edges;
    wire signed [31:0] skew;

    ber_cdr #(.SER(SER)) dut (.clk(clk), .rst(rst), .restart(restart), .track(track), .one_pol(one_pol), .d(d),
                              .period(period), .offset(offset), .gain(gain), .bit_v(bit_v), .bit_o(bit_o),
                              .err_o(err_o), .corr_sum(corr_sum), .edges(edges), .skew(skew));

    // ---- the transmitter: real-valued symbol times ----
    real    l_tx, t0, jit, dr;
    integer sym_now;
    reg [14:0] lfsr;
    reg        cur_bit;
    integer    seed = 7;

    function automatic integer sym_at;
        input real t;
        begin
            sym_at = $rtoi((t + t0) / l_tx);
        end
    endfunction

    // the bit of symbol k: the LFSR stepped forward as k grows, the last 1024 kept (a glitch back, or the previous
    // symbol's bit, reads them)
    integer lfsr_k;
    reg [0:1023] hist;
    function automatic bit_of;
        input integer k;
        begin
            while (lfsr_k < k) begin
                lfsr = {lfsr[13:0], lfsr[14] ^ lfsr[13]};
                lfsr_k = lfsr_k + 1;
                hist[lfsr_k % 1024] = lfsr[0];
            end
            bit_of = hist[k % 1024];
        end
    endfunction

    real    n_samp;
    integer s, k;
    real    tt, frac, dj;
    always @(negedge clk) begin
        if (!rst) begin
            for (s = 0; s < SER; s = s + 1) begin
                tt = n_samp + s;
                k = sym_at(tt);
                frac = (tt + t0) / l_tx - k;
                // near an edge, a random jitter decides which side the sample falls on
                dj = jit * ($random(seed) % 1000) / 1000.0 / l_tx;
                if (frac + dj < 0.0) k = k - 1;
                else if (frac + dj >= 1.0) k = k + 1;
                if (k < 1) k = 1;
                d[s] = bit_of(k);
                // a rise shows dr samples late: the first dr samples of a symbol that rose still read 0
                if (d[s] && !bit_of(k - 1) && frac * l_tx < dr) d[s] = 1'b0;
            end
            n_samp = n_samp + SER;
        end
    end

    // ---- the receiver's check ----
    reg [14:0] rb;
    integer nb, fails;
    always @(posedge clk) begin
        if (bit_v) begin
            rb <= {rb[13:0], bit_o};
            nb = nb + 1;
            if (nb > 15 && (bit_o ^ rb[13] ^ rb[14])) fails = fails + 1;
        end
    end

    integer errors = 0;
    integer last_fails;                         // the last run's failures after settling
    task run2;
        input integer per;
        input real ppm;
        input integer trk;
        input integer n_sym;
        input integer settle;
        input integer want_clean;
        input real    drs;
        input integer pol;
        integer f0, b0;
        begin
            @(negedge clk);
            rst = 1'b1;
            period = per; offset = per * SER / 2; track = trk; one_pol = pol;
            l_tx = per * SER * (1.0 + ppm * 1e-6);
            t0 = ($random(seed) & 1023) / 1024.0 * l_tx;
            jit = 1.5; dr = drs;
            n_samp = 0; lfsr = 15'h7FFF; lfsr_k = 0; hist[0] = 1'b1;
            nb = 0; fails = 0; rb = 15'd0;
            repeat (3) @(negedge clk);
            rst = 1'b0;
            wait (nb >= settle);
            f0 = fails; b0 = nb;
            wait (nb >= settle + n_sym);
            last_fails = fails - f0;
            $display("period %0d, %0.0f ppm, tracking %0d, rises %0.0f samples late, one_pol %0d: %0d symbols read, %0d check failures after %0d (last error %0d/16 sample; skew %0.2f samples; the offset from the corrections %0.1f ppm)",
                     per, ppm, trk, drs, pol, nb - b0, fails - f0, settle, err_o, skew / 256.0, -corr_sum / 256.0 / (n_samp + 1e-9) * 1e6);
            if (want_clean > 1) begin
                // the control: no verdict on one run
            end else if (want_clean && fails != f0) begin
                $display("FAIL: failures with the tracking on"); errors = errors + 1;
            end
            if (!want_clean && fails == f0) begin
                $display("FAIL: the control (tracking off, clocks apart) read clean"); errors = errors + 1;
            end
        end
    endtask

    task run;
        input integer per;
        input real ppm;
        input integer trk;
        input integer n_sym;
        input integer settle;
        input integer want_clean;
        begin
            run2(per, ppm, trk, n_sym, settle, want_clean, 0.0, 0);
        end
    endtask

    integer r, n_rand;
    initial begin
        run(10, 0.0, 1, 20000, 2000, 1);
        run(10, 100.0, 1, 20000, 2000, 1);
        run(10, -100.0, 1, 20000, 2000, 1);
        run(4, 300.0, 1, 20000, 2000, 1);
        run(2, -300.0, 1, 20000, 2000, 1);
        run(100, 50.0, 1, 4000, 1000, 1);
        run(100, -50.0, 1, 4000, 1000, 1);
        run(10, 100.0, 0, 20000, 2000, 0);
        // the rising edges 6 samples late at 2 clocks a symbol (the eye 10 of 16 samples open): both edges tracked,
        // some of 16 restarts lock between them (the control); one_pol, none of 16, and the skew reads -6 +- 2 (a
        // 64-edge average under this model's chatter at every edge: -4.4 to -6.7 seen)
        n_rand = 0;
        for (r = 0; r < 16; r = r + 1) begin
            run2(2, 5.0, 1, 3000, 1500, 2, 6.0, 0);
            if (last_fails > 1000) n_rand = n_rand + 1;
        end
        $display("both edges tracked, rises 6 samples late: %0d of 16 restarts read random bits", n_rand);
        if (n_rand == 0) begin
            $display("FAIL: the control (both edges, a skew of 6 samples) never locked falsely"); errors = errors + 1;
        end
        for (r = 0; r < 16; r = r + 1) begin
            run2(2, (r % 2) ? 300.0 : -300.0, 1, 3000, 1500, 1, 6.0, 1);
            if (skew > -4 * 256 || skew < -8 * 256) begin
                $display("FAIL: the skew reads %0.2f samples, not -6 +- 2", skew / 256.0); errors = errors + 1;
            end
        end
        // 25 Mbaud with a 10-sample skew (both edges: 8 of 24 restarts false in a scratch run), and no skew at all
        for (r = 0; r < 8; r = r + 1) run2(4, -100.0, 1, 3000, 1500, 1, 10.0, 1);
        for (r = 0; r < 4; r = r + 1) run2(10, 100.0, 1, 3000, 1500, 1, 0.0, 1);
        if (errors == 0) $display("PASS");
        else $display("FAILED: %0d", errors);
        $finish;
    end
endmodule
