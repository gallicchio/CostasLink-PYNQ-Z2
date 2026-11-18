// i2c_master: a 100 kHz I2C master for one transaction at a time: START, address+W, up to 9 bytes
// written, then (if nread > 0) a repeated START, address+R and 1-2 bytes read, then STOP.
// nwrite = 0 and nread = 0 is an address probe (START, address, ACK?, STOP): the bus scan of
// BRINGUP.md stage 1.5.
//
// Board signals: I2C_SDA (header 3) and I2C_SCL (5), open drain: scl_o / sda_o = 1 release the line
// (the 2k2 pull-ups on the PYNQ-Z2, the DNP 4.7 k on this board for the Icepi), 0 drives it low.  The
// slaves are the two MCP4728 DACs (0x60 and 0x61) and the ADS1115 ADC (0x48); the wire never carries
// anything faster than 100 kHz.  Clock stretching is honoured (the bit's high phase waits for SCL), for
// at most STRETCH_US: none of these slaves stretches at all, so SCL still low after that is a fault (a
// bridge, a dead part: rev A board A, 2026-10-29, hung here for good).  The transaction is then
// abandoned: both lines released, `timeout` and `nack` set, `done` pulsed.
//
// Byte 0 of wbuf is its top byte [71:64] and goes first; rbuf is {first byte read, second byte read}
// (a single read lands in [7:0]).  `nack` is set when any byte written is not acknowledged (the
// transaction then stops) and cleared by the next start.

module i2c_master #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer SCL_HZ = 100_000,
    parameter integer STRETCH_US = 10_000
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,          // sampled while !busy
    input  wire [6:0]  addr,
    input  wire [3:0]  nwrite,         // 0..9
    input  wire [1:0]  nread,          // 0..2
    input  wire [71:0] wbuf,
    output reg         busy,
    output reg         done,           // one-cycle pulse at the STOP
    output reg         nack,
    output reg         timeout,        // the last transaction was abandoned: SCL held low STRETCH_US
    output reg  [15:0] rbuf,
    input  wire        scl_i,
    input  wire        sda_i,
    output reg         scl_o,
    output reg         sda_o
);
    localparam integer QT = CLK_HZ / (4 * SCL_HZ);      // a quarter of a bit
    localparam integer CW = $clog2(QT + 1);
    localparam [CW-1:0] QT_M1 = QT[CW-1:0] - 1'b1;

    localparam [3:0] S_IDLE = 4'd0, S_START = 4'd1, S_WBIT = 4'd2, S_WACK = 4'd3, S_RSTART = 4'd4,
                     S_RBIT = 4'd5, S_RACK = 4'd6, S_STOP = 4'd7;

    reg [3:0]  st;
    reg [1:0]  ph;                  // four phases per bit, QT cycles each
    reg [CW-1:0] cnt;
    reg [2:0]  bitn;
    reg [7:0]  sh;
    reg [3:0]  wleft;               // bytes still to write after the current one
    reg [3:0]  widx;                // next byte of wbuf
    reg [1:0]  rleft;
    reg        rd;                  // in the read half of the transaction
    reg        ack_bit;
    reg [6:0]  addr_r;
    reg [1:0]  nread_r;

    wire [7:0] next_wbyte = wbuf[{4'd8 - widx, 3'd0} +: 8];       // byte widx: offset (8 - widx) * 8

    // the phase timer: phases advance every QT cycles; a high phase (ph 1 -> 2) also waits for SCL
    // to really be high (clock stretching)
    wire hold_for_scl = (ph == 2'd1) && scl_o && !scl_i;
    wire tick = (cnt == {CW{1'b0}}) && !hold_for_scl;

    // how long SCL has been held low against us
    localparam integer STRETCH_CYC = CLK_HZ / 1_000_000 * STRETCH_US;
    localparam integer SW = $clog2(STRETCH_CYC + 1);
    localparam [SW-1:0] STRETCH_M1 = STRETCH_CYC[SW-1:0] - 1'b1;
    reg [SW-1:0] scnt;
    always @(posedge clk) scnt <= (rst || !hold_for_scl) ? {SW{1'b0}} : scnt + 1'b1;

    always @(posedge clk) begin
        done <= 1'b0;
        if (rst) begin
            st <= S_IDLE; ph <= 2'd0; cnt <= {CW{1'b0}}; busy <= 1'b0; nack <= 1'b0; timeout <= 1'b0;
            scl_o <= 1'b1; sda_o <= 1'b1; bitn <= 3'd0; sh <= 8'd0; wleft <= 4'd0; widx <= 4'd0;
            rleft <= 2'd0; rd <= 1'b0; ack_bit <= 1'b1; rbuf <= 16'd0; addr_r <= 7'd0; nread_r <= 2'd0;
        end else if (st == S_IDLE) begin
            scl_o <= 1'b1; sda_o <= 1'b1; ph <= 2'd0; cnt <= QT_M1;
            if (start) begin
                busy <= 1'b1; nack <= 1'b0; timeout <= 1'b0; rd <= 1'b0;
                addr_r <= addr; nread_r <= nread;
                wleft <= nwrite; widx <= 4'd0; rleft <= nread;
                st <= S_START;
            end
        end else if (hold_for_scl && scnt == STRETCH_M1) begin   // SCL stuck low: give the bus up
            st <= S_IDLE; busy <= 1'b0; done <= 1'b1; nack <= 1'b1; timeout <= 1'b1;
        end else if (!tick) begin
            if (cnt != {CW{1'b0}}) cnt <= cnt - 1'b1;
        end else begin
            cnt <= QT_M1;
            ph  <= ph + 1'b1;
            case (st)
            S_START: case (ph)                             // SDA falls while SCL is high
                2'd0: sda_o <= 1'b0;
                2'd1: scl_o <= 1'b0;
                2'd3: begin sh <= {addr_r, 1'b0}; bitn <= 3'd0; st <= S_WBIT; end
                default: ;
            endcase
            S_WBIT: case (ph)                              // one bit out, MSB first
                2'd0: sda_o <= sh[7];
                2'd1: scl_o <= 1'b1;
                2'd3: begin
                    scl_o <= 1'b0;
                    sh    <= {sh[6:0], 1'b0};
                    bitn  <= bitn + 1'b1;
                    if (bitn == 3'd7) st <= S_WACK;
                end
                default: ;
            endcase
            S_WACK: case (ph)                              // the slave's acknowledge
                2'd0: sda_o <= 1'b1;
                2'd1: scl_o <= 1'b1;
                2'd2: ack_bit <= sda_i;
                2'd3: begin
                    scl_o <= 1'b0;
                    if (ack_bit) begin
                        nack <= 1'b1;
                        st   <= S_STOP;
                    end else if (rd) begin                 // address+R acknowledged: read
                        bitn <= 3'd0; sh <= 8'd0; st <= S_RBIT;
                    end else if (wleft != 4'd0) begin
                        sh <= next_wbyte; widx <= widx + 1'b1; wleft <= wleft - 1'b1;
                        bitn <= 3'd0; st <= S_WBIT;
                    end else if (nread_r != 2'd0) begin
                        st <= S_RSTART;
                    end else begin
                        st <= S_STOP;
                    end
                end
                default: ;
            endcase
            S_RSTART: case (ph)                            // repeated START
                2'd0: sda_o <= 1'b1;
                2'd1: scl_o <= 1'b1;
                2'd2: sda_o <= 1'b0;
                2'd3: begin scl_o <= 1'b0; rd <= 1'b1; sh <= {addr_r, 1'b1}; bitn <= 3'd0; st <= S_WBIT; end
                default: ;
            endcase
            S_RBIT: case (ph)                              // one bit in
                2'd0: sda_o <= 1'b1;
                2'd1: scl_o <= 1'b1;
                2'd2: sh <= {sh[6:0], sda_i};
                2'd3: begin
                    scl_o <= 1'b0;
                    bitn  <= bitn + 1'b1;
                    if (bitn == 3'd7) st <= S_RACK;
                end
                default: ;
            endcase
            S_RACK: case (ph)                              // our ACK, or NACK after the last byte
                2'd0: sda_o <= (rleft == 2'd1);
                2'd1: scl_o <= 1'b1;
                2'd3: begin
                    scl_o <= 1'b0;
                    rbuf  <= {rbuf[7:0], sh};
                    rleft <= rleft - 1'b1;
                    bitn  <= 3'd0;
                    st    <= (rleft == 2'd1) ? S_STOP : S_RBIT;
                end
                default: ;
            endcase
            S_STOP: case (ph)                              // SDA rises while SCL is high
                2'd0: sda_o <= 1'b0;
                2'd1: scl_o <= 1'b1;
                2'd2: sda_o <= 1'b1;
                2'd3: begin busy <= 1'b0; done <= 1'b1; st <= S_IDLE; end
                default: ;
            endcase
            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
