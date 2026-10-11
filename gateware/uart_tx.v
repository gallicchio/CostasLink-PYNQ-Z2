// uart_tx: 8N1 serial transmitter, one byte per `start` while not busy.
//
// Board signal: none.  It carries the UART bridge's replies (uart_cmd.v) to the Icepi Zero's FTDI
// (ball K15) or to a USB-UART dongle on the PYNQ-Z2's Arduino header.

module uart_tx #(
    parameter integer CLK_HZ = 50_000_000,
    parameter integer BAUD   = 115200
) (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] data,
    input  wire       start,      // sampled only while !busy
    output reg        tx,
    output reg        busy
);
    localparam integer DIV = CLK_HZ / BAUD;
    localparam integer CW  = $clog2(DIV + 1);
    localparam [CW-1:0] DIV_M1 = DIV[CW-1:0] - 1'b1;

    reg [CW-1:0] cnt;
    reg [3:0]    bitn;              // bits already put on the line after the start bit
    reg [8:0]    shift;             // {stop, data[7:0]}, LSB first

    always @(posedge clk) begin
        if (rst) begin
            tx    <= 1'b1;
            busy  <= 1'b0;
            cnt   <= {CW{1'b0}};
            bitn  <= 4'd0;
            shift <= 9'd0;
        end else if (!busy) begin
            tx <= 1'b1;
            if (start) begin
                busy  <= 1'b1;
                tx    <= 1'b0;                  // the start bit
                shift <= {1'b1, data};
                cnt   <= DIV_M1;
                bitn  <= 4'd0;
            end
        end else if (cnt != {CW{1'b0}}) begin
            cnt <= cnt - 1'b1;
        end else begin
            cnt <= DIV_M1;
            if (bitn == 4'd9) begin             // the stop bit has had its bit time
                busy <= 1'b0;
            end else begin
                tx    <= shift[0];
                shift <= {1'b1, shift[8:1]};
                bitn  <= bitn + 1'b1;
            end
        end
    end
endmodule
