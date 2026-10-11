// tx_symbol: the transmitter's constellation point and the BPSK test pattern.
//
// Board signals: TX_I1 / TX_I0 (header 7 / 11) and TX_Q1 / TX_Q0 (13 / 15), the two 2-bit resistor
// ladders into the ADL5375's IBBP / QBBP (PLAN.md section 13, the transmitter sheet).  Each ladder:
//   00 = -a, 01 or 10 = 0, 11 = +a   (a = 0.33 V single-ended about the 0.5 V bias)
// Idle is (I +a, Q 0) = i 11, q 01: the carrier at 0 degrees that the far end's loop tracks.  BPSK is
// I to -a (00); QPSK a corner (+-a, +-a); FSK the four phases in turn; OOK both ladders at 0.
//
// The symbol register holds the point; the pattern generator, when running, flips I (complements
// its code) every `period` clocks: for `width` clocks when width > 0 (a BPSK pulse), or toggling
// each period when width = 0 (a continuous square wave; in that mode `count` counts toggles, and I
// stays where the last toggle left it).  `count` events then stop (0 = run until stopped).  `width`
// must be less than `period`.  `sym_change` pulses on every change of the four pins: TRIG_A's source.

module tx_symbol (
    input  wire        clk,
    input  wire        rst,
    input  wire        sym_we,
    input  wire [3:0]  sym_wdata,     // {q[1:0], i[1:0]}
    input  wire [31:0] period,        // clocks between flips (>= 2)
    input  wire [31:0] width,         // clocks the flip lasts; 0 = toggle
    input  wire [15:0] count,         // pulses to send; 0 = forever
    input  wire        pat_start,     // pulse
    input  wire        pat_stop,      // pulse
    output reg  [1:0]  tx_i,
    output reg  [1:0]  tx_q,
    output reg         sym_change,
    output reg         running
);
    reg [3:0]  sym;                   // the register: {q, i}
    reg        flipped;
    reg [31:0] pcnt;
    reg [31:0] wcnt;
    reg [15:0] left;
    reg        forever_;
    reg [3:0]  prev;

    wire [1:0] i_eff = flipped ? ~sym[1:0] : sym[1:0];

    always @(posedge clk) begin
        if (rst) begin
            sym <= 4'b0111;           // idle: I +a, Q 0
            flipped <= 1'b0; running <= 1'b0; pcnt <= 32'd0; wcnt <= 32'd0;
            left <= 16'd0; forever_ <= 1'b0;
        end else begin
            if (sym_we) sym <= sym_wdata;
            // a pulse in progress ends after `width` clocks whatever `running` does (the last pulse of a
            // counted run must complete); a period event below overrides this with a new pulse
            if (width != 32'd0 && flipped) begin
                if (wcnt != 32'd0) wcnt <= wcnt - 1'b1;
                else flipped <= 1'b0;
            end
            if (pat_stop) begin
                running <= 1'b0; flipped <= 1'b0;
            end else if (pat_start) begin
                running  <= 1'b1;
                flipped  <= 1'b0;
                pcnt     <= period - 1'b1;
                left     <= count;
                forever_ <= (count == 16'd0);
            end else if (running) begin
                if (pcnt != 32'd0) begin
                    pcnt <= pcnt - 1'b1;
                end else begin
                    pcnt <= period - 1'b1;
                    if (width == 32'd0) flipped <= ~flipped;
                    else begin flipped <= 1'b1; wcnt <= width - 1'b1; end
                    if (!forever_) begin
                        left <= left - 1'b1;
                        if (left == 16'd1) running <= 1'b0;   // the last event; its pulse still completes
                    end
                end
            end
        end
    end

    always @(posedge clk) begin
        tx_i <= i_eff;
        tx_q <= sym[3:2];
        prev <= {tx_q, tx_i};
        sym_change <= !rst && ({tx_q, tx_i} != prev);
    end
endmodule
