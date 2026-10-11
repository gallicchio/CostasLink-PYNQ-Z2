// max2871_init: the power-up programming of both MAX2871 synthesizers, through spi_master.
//
// Board signals: the SPI pins through spi_master (LE_PLL_TX for the TX chip, then LE_PLL_RX for the
// RX chip).  The words come from max2871_words.vh, which gateware/max2871_regs.py --verilog writes
// (5800 MHz integer-N from the 25 MHz reference by default); the send order is the datasheet's
// "clean clock at start up" list: register 5, wait 20 ms, register 4 with both outputs off, 3, 2, 1,
// 0, 5 again, then register 4 with RFOUTA on (eight words per chip).  MUX = digital lock detect, so
// MUX_TX / MUX_RX (header 23 / 35) go high when each loop locks.
//
// `start` is a pulse; `busy` covers the whole sequence (about 41 ms); `done` is a pulse at its end.
// While busy it owns the SPI master (costaslink_regs.v arbitrates).

module max2871_init #(
    parameter integer CLK_HZ = 50_000_000
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,
    output reg         busy,
    output reg         done,
    // to spi_master
    output reg         spi_start,
    output wire [31:0] spi_word,
    output wire [1:0]  spi_sel,
    input  wire        spi_busy
);
    `include "max2871_words.vh"

    localparam integer WAIT_CYCLES = (CLK_HZ / 1000) * MAX2871_WAIT_MS;
    localparam integer WW = $clog2(WAIT_CYCLES + 1);
    localparam [WW-1:0] WAIT_M1 = WAIT_CYCLES[WW-1:0] - 1'b1;

    localparam [1:0] S_IDLE = 2'd0, S_ISSUE = 2'd1, S_WAIT_SPI = 2'd2, S_PAUSE = 2'd3;

    reg [1:0]  st;
    reg        pll;                 // 0 = TX, 1 = RX
    reg [2:0]  idx;                 // word 0..7 of the sequence
    reg [WW-1:0] wcnt;

    wire [32*MAX2871_SEQ_LEN-1:0] seq = pll ? MAX2871_RX_SEQ : MAX2871_TX_SEQ;
    assign spi_word = seq[{~idx, 5'd0} +: 32];      // word 0 sits in the top 32 bits: offset (7 - idx) * 32
    assign spi_sel  = {1'b0, pll};

    always @(posedge clk) begin
        spi_start <= 1'b0;
        done      <= 1'b0;
        if (rst) begin
            st <= S_IDLE; busy <= 1'b0; pll <= 1'b0; idx <= 3'd0; wcnt <= {WW{1'b0}};
        end else begin
            case (st)
            S_IDLE: if (start) begin
                busy <= 1'b1; pll <= 1'b0; idx <= 3'd0; st <= S_ISSUE;
            end
            S_ISSUE: if (!spi_busy && !spi_start) begin
                spi_start <= 1'b1;
                st <= S_WAIT_SPI;
            end
            S_WAIT_SPI: if (!spi_busy && !spi_start) begin  // spi_busy rises the cycle after spi_start
                if (idx == 3'd0) begin
                    wcnt <= WAIT_M1;
                    st   <= S_PAUSE;
                end else if (idx == 3'd7) begin
                    if (pll) begin busy <= 1'b0; done <= 1'b1; st <= S_IDLE; end
                    else begin pll <= 1'b1; idx <= 3'd0; st <= S_ISSUE; end
                end else begin
                    idx <= idx + 1'b1;
                    st  <= S_ISSUE;
                end
            end
            S_PAUSE: begin
                if (wcnt != {WW{1'b0}}) wcnt <= wcnt - 1'b1;
                else begin idx <= 3'd1; st <= S_ISSUE; end
            end
            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
