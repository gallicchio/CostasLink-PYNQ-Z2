// tb_ber_cdr: ber_cdr.v against a transmitter on another clock: PRBS15 symbols of period x SER x (1 + ppm) samples,
// each edge moved by up to +-JIT samples at random (the comparator's noise: glitches near the edges), from a random
// starting phase.  The self-synchronising check (b ^ b-14 ^ b-15) on what ber_cdr reads, after SETTLE symbols:
// no failure with the tracking on, at every period and offset; with it off and the clocks apart, failures (the
// control).
//
//     iverilog -g2005 -Wall -o tb_ber_cdr.vvp tb_ber_cdr.v ber_cdr.v && vvp -N tb_ber_cdr.vvp     (ends with PASS)
`timescale 1ns/1ps
module tb_ber_cdr;
    localparam integer SER = 8;
    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst = 1'b1, restart = 1'b0, track = 1'b1;
    reg [15:0] period = 16'd10, offset = 16'd40;
    reg [3:0]  gain = 4'd4;
    reg [SER-1:0] d = {SER{1'b0}};
    wire bit_v, bit_o;
    wire signed [15:0] err_o;
    wire signed [31:0] corr_sum;
    wire [31:0] edges;

    ber_cdr #(.SER(SER)) dut (.clk(clk), .rst(rst), .restart(restart), .track(track), .d(d), .period(period),
                              .offset(offset), .gain(gain), .bit_v(bit_v), .bit_o(bit_o), .err_o(err_o),
                              .corr_sum(corr_sum), .edges(edges));

    // ---- the transmitter: real-valued symbol times ----
    real    l_tx, t0, jit;
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

    // the bit of symbol k: the LFSR stepped forward as k grows (monotonic within a run)
    integer lfsr_k;
    function automatic bit_of;
        input integer k;
        begin
            while (lfsr_k < k) begin
                lfsr = {lfsr[13:0], lfsr[14] ^ lfsr[13]};
                lfsr_k = lfsr_k + 1;
            end
            bit_of = lfsr[0];
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
                if (k < lfsr_k) k = lfsr_k;          // the LFSR runs forwards only (a glitch back reads the same symbol)
                d[s] = bit_of(k);
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
    task run;
        input integer per;
        input real ppm;
        input integer trk;
        input integer n_sym;
        input integer settle;
        input integer want_clean;
        integer f0, b0;
        begin
            @(negedge clk);
            rst = 1'b1;
            period = per; offset = per * SER / 2; track = trk;
            l_tx = per * SER * (1.0 + ppm * 1e-6);
            t0 = ($random(seed) & 1023) / 1024.0 * l_tx;
            jit = 1.5;
            n_samp = 0; lfsr = 15'h7FFF; lfsr_k = 0;
            nb = 0; fails = 0; rb = 15'd0;
            repeat (3) @(negedge clk);
            rst = 1'b0;
            wait (nb >= settle);
            f0 = fails; b0 = nb;
            wait (nb >= settle + n_sym);
            $display("period %0d, %0.0f ppm, tracking %0d: %0d symbols read, %0d check failures after %0d (last error %0d/16 sample; the offset from the corrections %0.1f ppm)",
                     per, ppm, trk, nb - b0, fails - f0, settle, err_o, -corr_sum / 256.0 / (n_samp + 1e-9) * 1e6);
            if (want_clean && fails != f0) begin
                $display("FAIL: failures with the tracking on"); errors = errors + 1;
            end
            if (!want_clean && fails == f0) begin
                $display("FAIL: the control (tracking off, clocks apart) read clean"); errors = errors + 1;
            end
        end
    endtask

    initial begin
        run(10, 0.0, 1, 20000, 2000, 1);
        run(10, 100.0, 1, 20000, 2000, 1);
        run(10, -100.0, 1, 20000, 2000, 1);
        run(4, 300.0, 1, 20000, 2000, 1);
        run(2, -300.0, 1, 20000, 2000, 1);
        run(100, 50.0, 1, 4000, 1000, 1);
        run(100, -50.0, 1, 4000, 1000, 1);
        run(10, 100.0, 0, 20000, 2000, 0);
        if (errors == 0) $display("PASS");
        else $display("FAILED: %0d", errors);
        $finish;
    end
endmodule
