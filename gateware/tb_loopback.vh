// tb_loopback.vh: the loopback model tb_engines.v and tb_pipe.v share (Response 15).  The includer declares
// SER (localparam), `lat` and `lat_slow` (integers: samples, pins -> fast / slow comparators), clk, and the
// core's pins (tx_i1 ... tx_q1_hiz).  The ladder point on the pins comes back on the five fast comparators
// `lat` samples later (CMP_I = I > 0; CMP_IP / CMP_IN = I at +a / -a; CMP_QP / CMP_QN = Q at +a / -a), and
// on the three slow ones `lat_slow` samples later (CMP_I_S = I > 0, CMP_QP_S = Q > 0, CMP_QN_S = Q < 0).
// Knobs: mute (the comparators stay at the idle vector), flip_next (CMP_I inverted), glitch (CMP_QP high),
// trig_samp[] (TRIG_IN per sample), noise_mask / noise_ppm (random flips: false events).
//
// Sample by sample (Prompt 36), so the fast path's combinational loop runs in it: the pins are recorded
// once a sample (mid-sample), the comparators are driven once a sample on `cmp_async` (a quarter sample in),
// and the core gets them as words: `fs` this clock's (from the edge), `fs_early` the next clock's (from a
// quarter sample before the edge: the PYNQ-Z2's ISERDESE2 word a clock before its register, EARLY), and
// `fs_tx` the pins' samples of the clock before (the TXFB read-back, a clock late here; on the PYNQ-Z2 the
// read-back and the comparators go through ISERDESE2s alike).  With the pins moving only at clock edges this
// is the model it was (`lat` >= SER keeps it causal); the fast path adds no delay of its own here.
    // ---- the loopback model ---------------------------------------------------------------------------
    reg  [3:0] hist_pt [0:255];            // the pins once a sample, [0] the newest
    reg        trig_samp [0:SER-1];        // TRIG_IN this clock, per sample (the testbench drives it)
    reg        flip_next = 1'b0;           // invert CMP_I for one symbol (BER error injection)
    reg        mute = 1'b0;                // the link drops: comparators stay at idle
    reg        glitch = 1'b0;              // CMP_QP goes high for one clock with nothing sent
    reg  [4:0] noise_mask = 5'd0;          // comparators that flip at random, each sample with chance noise_ppm / 1e6
    integer    noise_ppm = 0;
    integer    noise_seed = 1;
    reg  [4:0] nz;
    integer    k;
    localparam real TS = 10.0 / SER;       // ns a sample (the 100 MHz clock)

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
    reg  [6*SER-1:0] fs_early;
    reg  [4*SER-1:0] fs_tx;
    reg  [4:0] cmp_async;
    reg  [4:0] cmpw [0:SER-1];             // this clock's comparators, one a sample, for cmp_async
    reg  [2:0] slow;
    reg  [3:0] ptmp;
    integer    s, ks, kh;

    // the edge: this clock's words, worked out a quarter sample before it
    always @(posedge clk) begin
        fs <= fs_early;
        for (s = 0; s < SER; s = s + 1) begin
            cmpw[s] = fs_early[6*s +: 5];
            fs_tx[4*s +: 4] <= hist_pt[SER - 1 - s];
        end
        slow <= mute ? 3'b001 : slows(hist_pt[lat_slow - 1]);
    end
    // the samples: the comparators out a quarter sample in, the pins recorded mid-sample, and the next
    // clock's word a quarter sample before its edge
    integer    samp = 0;                   // the sample now, counted from the start (tests time the pins with it)
    event      sample_ev;                  // each sample's pins, recorded mid-sample
    always @(posedge clk) begin
        for (ks = 0; ks < SER; ks = ks + 1) begin
            if (ks > 0) #(TS * 0.5);
            samp = samp + 1;
            #(TS * 0.25) cmp_async = cmpw[ks];
            #(TS * 0.25);
            for (kh = 255; kh > 0; kh = kh - 1) hist_pt[kh] = hist_pt[kh - 1];
            hist_pt[0] = pins;
            -> sample_ev;
        end
        #(TS * 0.25);
        for (s = 0; s < SER; s = s + 1) begin
            // hist_pt[j] holds the pins at sample (SER-1-j) of the clock now ending; sample s of the next
            // clock is SER + s samples later, so `lat` samples of delay is entry lat - 1 - s
            ptmp = hist_pt[lat - 1 - s];
            nz = 5'd0;
            if (noise_ppm > 0 && ($unsigned($random(noise_seed)) % 1000000) < noise_ppm) nz = noise_mask;
            fs_early[6*s +: 6] = {trig_samp[s], (mute ? 5'b01001 : (cmps(ptmp) ^ {4'd0, flip_next} | (glitch ? 5'b00010 : 5'd0))) ^ nz};
        end
    end
