// uart_rx: 8N1 serial receiver, one byte at a time, each bit sampled at its middle.
//
// Board signal: none.  It is the command input of the UART bridge (uart_cmd.v): the Icepi Zero's FTDI
// (ball K16) or a USB-UART dongle on the PYNQ-Z2's Arduino header.  The AXI-Lite path on the PYNQ
// replaces it later (README.md).
//
// CLK_HZ / BAUD must be at least 16 (it is about 434 at 50 MHz, 1085 at 125 MHz).

module uart_rx #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer BAUD   = 115200
) (
    input  wire       clk,
    input  wire       rst,
    input  wire       rx,
    output reg  [7:0] data,
    output reg        valid       // one-cycle pulse: `data` holds a new byte
);
    localparam integer DIV = CLK_HZ / BAUD;
    localparam integer CW  = $clog2(DIV + 1);
    localparam integer HALF = DIV / 2;
    localparam [CW-1:0] DIV_M1  = DIV[CW-1:0] - 1'b1;
    localparam [CW-1:0] HALF_M1 = HALF[CW-1:0] - 1'b1;

    reg          rx_s1, rx_s2;      // two flip-flops: the line is asynchronous
    reg          busy;
    reg [CW-1:0] cnt;
    reg [3:0]    bitn;              // 0 = start bit, 1..8 = data, 9 = stop
    reg [7:0]    shift;

    always @(posedge clk) begin
        rx_s1 <= rx;
        rx_s2 <= rx_s1;
    end

    always @(posedge clk) begin
        valid <= 1'b0;
        if (rst) begin
            busy  <= 1'b0;
            cnt   <= {CW{1'b0}};
            bitn  <= 4'd0;
            shift <= 8'd0;
            data  <= 8'd0;
        end else if (!busy) begin
            if (!rx_s2) begin               // a start bit's falling edge: aim for its middle
                busy <= 1'b1;
                cnt  <= HALF_M1;
                bitn <= 4'd0;
            end
        end else if (cnt != {CW{1'b0}}) begin
            cnt <= cnt - 1'b1;
        end else begin
            cnt <= DIV_M1;
            if (bitn == 4'd0) begin
                if (rx_s2) busy <= 1'b0;    // the line went back high: a glitch, not a start bit
                else       bitn <= 4'd1;
            end else if (bitn <= 4'd8) begin
                shift <= {rx_s2, shift[7:1]};   // LSB first
                bitn  <= bitn + 1'b1;
            end else begin                  // the stop bit
                busy <= 1'b0;
                if (rx_s2) begin
                    data  <= shift;
                    valid <= 1'b1;
                end                         // a framing error drops the byte
            end
        end
    end
endmodule
