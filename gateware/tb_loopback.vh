// tb_loopback.vh: the loopback model tb_engines.v and tb_pipe.v share (Response 15).  The includer declares
// SER (localparam), `lat` and `lat_slow` (integers: samples, pins -> fast / slow comparators), clk, and the
// core's pins (tx_i1 ... tx_q1_hiz).  The ladder point on the pins comes back on the five fast comparators
// `lat` samples later (CMP_I = I > 0; CMP_IP / CMP_IN = I at +a / -a; CMP_QP / CMP_QN = Q at +a / -a), and
// on the three slow ones `lat_slow` samples later (CMP_I_S = I > 0, CMP_QP_S = Q > 0, CMP_QN_S = Q < 0).
// Knobs: mute (the comparators stay at the idle vector), flip_next (CMP_I inverted), glitch (CMP_QP high),
// trig_samp[] (TRIG_IN per sample), noise_mask / noise_ppm (random flips: false events).
    // ---- the loopback model ---------------------------------------------------------------------------
    reg  [3:0] hist_pt [0:255];            // the point at each of the last 256 samples, [0] the newest
    reg        trig_samp [0:SER-1];        // TRIG_IN this clock, per sample (the testbench drives it)
    reg        flip_next = 1'b0;           // invert CMP_I for one symbol (BER error injection)
    reg        mute = 1'b0;                // the link drops: comparators stay at idle
    reg        glitch = 1'b0;              // CMP_QP goes high for one clock with nothing sent
    reg  [4:0] noise_mask = 5'd0;          // comparators that flip at random, each sample with chance noise_ppm / 1e6
    integer    noise_ppm = 0;
    integer    noise_seed = 1;
    reg  [4:0] nz;
    integer    k;

    function signed [1:0] lvl;             // ladder code -> -1, 0, +1
        input [1:0] c;
        begin
            lvl = (c == 2'b11) ? 2'sd1 : (c == 2'b00) ? -2'sd1 : 2'sd0;
        end
    endfunction

    // the comparators' vector for a point: {TRIG_IN, CMP_IN, CMP_IP, CMP_QN, CMP_QP, CMP_I}
    function [4:0] cmps;
        input [3:0] p;
        reg signed [1:0] i, q;
        begin
            i = lvl(p[1:0]); q = lvl(p[3:2]);
            cmps = {i == -2'sd1, i == 2'sd1, q == -2'sd1, q == 2'sd1, i == 2'sd1};
        end
    endfunction
    function [2:0] slows;
        input [3:0] p;
        reg signed [1:0] i, q;
        begin
            i = lvl(p[1:0]); q = lvl(p[3:2]);
            slows = {q == -2'sd1, q == 2'sd1, i == 2'sd1};
        end
    endfunction

    wire [3:0] pins = {tx_q1_hiz ? 1'b0 : tx_q1, tx_q0, tx_i1, tx_i0};
    reg  [6*SER-1:0] fs;
    reg  [2:0] slow;
    reg  [3:0] ptmp;
    integer    s;
    always @(posedge clk) begin
        // this clock's SER samples all see the pins as they are now
        for (k = 255; k >= SER; k = k - 1) hist_pt[k] = hist_pt[k - SER];
        for (k = 0; k < SER; k = k + 1) hist_pt[k] = pins;
        for (s = 0; s < SER; s = s + 1) begin
            // hist_pt[j] holds the pins at sample (SER-1-j) of the clock just ended (read at this edge, before
            // the pins' own register moves); sample s of the clock these samples are seen in is SER + s
            // samples later, so `lat` samples of delay is entry lat - 1 - s
            ptmp = hist_pt[lat - 1 - s];
            nz = 5'd0;
            if (noise_ppm > 0 && ($unsigned($random(noise_seed)) % 1000000) < noise_ppm) nz = noise_mask;
            fs[6*s +: 6] <= {trig_samp[s], (mute ? 5'b01001 : (cmps(ptmp) ^ {4'd0, flip_next} | (glitch ? 5'b00010 : 5'd0))) ^ nz};
        end
        slow <= mute ? 3'b001 : slows(hist_pt[lat_slow - 1]);
    end
