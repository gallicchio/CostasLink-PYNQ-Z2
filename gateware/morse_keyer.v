// morse_keyer: the station identification, 47 CFR 97.119: the callsign in Morse at least every ten
// minutes while the station transmits in the amateur band (CW is always an acceptable form).
//
// Board signal: TX_DIS (header 24), the ADL5375's DSOP pin, through costaslink_top.v: while an
// identification runs, key down = carrier on (TX_DIS low), key up = carrier off (TX_DIS high); the
// rest of the time TX_DIS is the control register's bit.  (The link's idle carrier is thus switched
// on and off: on-off keying of the carrier itself, 100 / 200 ns edges.)
//
// `enable` arms the ten-minute timer (it restarts from zero when enabled and after each
// identification); `send_now` keys the callsign at once (the start and the end of a session).
// Timing: PARIS at WPM words per minute: dit = 1.2 s / WPM (60 ms at 20 WPM), dah 3 dits, 1 dit
// between elements, 3 between letters, 7 between words (a space in the string).
// The callsign is a parameter: a packed string, first character in the top byte.

module morse_keyer #(
    parameter integer CLK_HZ       = 50_000_000,
    parameter integer WPM          = 20,
    parameter integer INTERVAL_S   = 600,
    parameter integer CALLSIGN_LEN = 4,
    parameter [8*CALLSIGN_LEN-1:0] CALLSIGN = "W3JQ"
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,
    input  wire        send_now,       // pulse
    output reg         active,         // an identification is running: TX_DIS follows `key`
    output reg         key,            // 1 = key down = carrier on
    output wire [15:0] secs_to_id      // seconds until the timer keys the callsign (0 when disarmed)
);
    localparam integer DIT_CYCLES = (CLK_HZ / WPM) * 6 / 5;           // 1.2 s / WPM
    localparam integer DW = $clog2(DIT_CYCLES + 1);
    localparam [DW-1:0] DIT_M1 = DIT_CYCLES[DW-1:0] - 1'b1;
    localparam integer SW = $clog2(CLK_HZ + 1);
    localparam [SW-1:0] SEC_M1 = CLK_HZ[SW-1:0] - 1'b1;
    localparam integer IW = $clog2(CALLSIGN_LEN + 1);
    localparam integer CW = (CALLSIGN_LEN > 1) ? $clog2(CALLSIGN_LEN) : 1;   // the array's index width
    localparam [15:0] INTERVAL = INTERVAL_S[15:0];

    // {elements[7:0], n[3:0]}: element k (k = 0 first) at bit 4 + k, 0 = dit, 1 = dah; n = 0: a word space
    function [11:0] morse;
        input [7:0] c;
        begin
            case (c)
            "A": morse = {8'b00000010, 4'd2};  "B": morse = {8'b00000001, 4'd4};  "C": morse = {8'b00000101, 4'd4};
            "D": morse = {8'b00000001, 4'd3};  "E": morse = {8'b00000000, 4'd1};  "F": morse = {8'b00000100, 4'd4};
            "G": morse = {8'b00000011, 4'd3};  "H": morse = {8'b00000000, 4'd4};  "I": morse = {8'b00000000, 4'd2};
            "J": morse = {8'b00001110, 4'd4};  "K": morse = {8'b00000101, 4'd3};  "L": morse = {8'b00000010, 4'd4};
            "M": morse = {8'b00000011, 4'd2};  "N": morse = {8'b00000001, 4'd2};  "O": morse = {8'b00000111, 4'd3};
            "P": morse = {8'b00000110, 4'd4};  "Q": morse = {8'b00001011, 4'd4};  "R": morse = {8'b00000010, 4'd3};
            "S": morse = {8'b00000000, 4'd3};  "T": morse = {8'b00000001, 4'd1};  "U": morse = {8'b00000100, 4'd3};
            "V": morse = {8'b00001000, 4'd4};  "W": morse = {8'b00000110, 4'd3};  "X": morse = {8'b00001001, 4'd4};
            "Y": morse = {8'b00001101, 4'd4};  "Z": morse = {8'b00000011, 4'd4};
            "0": morse = {8'b00011111, 4'd5};  "1": morse = {8'b00011110, 4'd5};  "2": morse = {8'b00011100, 4'd5};
            "3": morse = {8'b00011000, 4'd5};  "4": morse = {8'b00010000, 4'd5};  "5": morse = {8'b00000000, 4'd5};
            "6": morse = {8'b00000001, 4'd5};  "7": morse = {8'b00000011, 4'd5};  "8": morse = {8'b00000111, 4'd5};
            "9": morse = {8'b00001111, 4'd5};  "/": morse = {8'b00001001, 4'd5};
            default: morse = {8'b00000000, 4'd0};                     // space or unknown: a word gap
            endcase
        end
    endfunction

    localparam [2:0] S_IDLE = 3'd0, S_LOAD = 3'd1, S_ON = 3'd2, S_OFF = 3'd3, S_GAP = 3'd4;

    reg [2:0]  st;
    reg [IW-1:0] ci;                 // character index
    reg [3:0]  ei;                   // element index
    reg [11:0] code;
    reg [2:0]  units;                // dit units left in the current on / off interval
    reg [DW-1:0] dcnt;
    reg [SW-1:0] scnt;
    reg [15:0] secs;

    // each character's code, worked out at elaboration (constant indices).  Selecting the character from
    // the string parameter by a register (CALLSIGN[8*(LEN-1-ci) +: 8]) and looking it up then crashed Vivado
    // 2024.1's synthesis (a segfault in its constant propagation, Response 15); Yosys took it.
    wire [11:0] codes [0:CALLSIGN_LEN-1];
    genvar gi;
    generate
        for (gi = 0; gi < CALLSIGN_LEN; gi = gi + 1) begin : g_code
            assign codes[gi] = morse(CALLSIGN[8*(CALLSIGN_LEN-1-gi) +: 8]);   // first character on top
        end
    endgenerate
    wire [11:0] ch_code = ({{(32-IW){1'b0}}, ci} < CALLSIGN_LEN) ? codes[ci[CW-1:0]] : 12'd0;
    wire unit_end = (dcnt == {DW{1'b0}});
    wire timer_fire = enable && (secs == INTERVAL);
    assign secs_to_id = enable ? (INTERVAL - secs) : 16'd0;

    // the ten-minute timer
    always @(posedge clk) begin
        if (rst || !enable || st != S_IDLE) begin
            scnt <= SEC_M1;
            secs <= 16'd0;
        end else if (scnt != {SW{1'b0}}) begin
            scnt <= scnt - 1'b1;
        end else begin
            scnt <= SEC_M1;
            if (secs != INTERVAL) secs <= secs + 1'b1;
        end
    end

    // the keyer
    always @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; active <= 1'b0; key <= 1'b0; ci <= {IW{1'b0}}; ei <= 4'd0;
            code <= 12'd0; units <= 3'd0; dcnt <= {DW{1'b0}};
        end else begin
            if (!unit_end) dcnt <= dcnt - 1'b1;
            case (st)
            S_IDLE: begin
                key <= 1'b0; active <= 1'b0;
                if (send_now || timer_fire) begin
                    active <= 1'b1;
                    ci <= {IW{1'b0}};
                    st <= S_LOAD;
                end
            end
            S_LOAD: begin                                 // fetch the next character
                if (ci == CALLSIGN_LEN[IW-1:0]) begin
                    st <= S_IDLE;
                end else begin
                    code <= ch_code;
                    ei   <= 4'd0;
                    ci   <= ci + 1'b1;
                    dcnt <= DIT_M1;
                    if (ch_code[3:0] == 4'd0) begin
                        units <= 3'd4;                    // a word gap: 4 more units on top of the letter gap
                        st    <= S_GAP;
                    end else begin
                        units <= ch_code[4] ? 3'd3 : 3'd1; // the first element
                        key   <= 1'b1;
                        st    <= S_ON;
                    end
                end
            end
            S_ON: if (unit_end) begin
                dcnt <= DIT_M1;
                if (units == 3'd1) begin
                    key   <= 1'b0;
                    units <= 3'd1;
                    ei    <= ei + 1'b1;
                    st    <= S_OFF;
                end else begin
                    units <= units - 1'b1;
                end
            end
            S_OFF: if (unit_end) begin                    // one unit between elements
                dcnt <= DIT_M1;
                if (ei == code[3:0]) begin
                    units <= 3'd2;                        // two more: the letter gap
                    st    <= S_GAP;
                end else begin
                    units <= code[4 + ei] ? 3'd3 : 3'd1;
                    key   <= 1'b1;
                    st    <= S_ON;
                end
            end
            S_GAP: if (unit_end) begin
                dcnt <= DIT_M1;
                if (units == 3'd1) st <= S_LOAD;
                else units <= units - 1'b1;
            end
            default: st <= S_IDLE;
            endcase
        end
    end

endmodule
