// spi_master: the 3-wire write-only SPI shared by the three slaves, with one latch-enable line each.
//
// Board signals: SPI_SCLK (header 31), SPI_SDATA (29), LE_PLL_TX (21), LE_PLL_RX (33), LE_DSA (36).
//   sel 0: MAX2871 TX  -- 32 bits MSB first, data latched into the chip on SCLK's rising edge, the
//   sel 1: MAX2871 RX     word loaded into its register when LE goes high (datasheet: 4-wire serial
//                         interface; tLES 20 ns, tLEW 20 ns; SCLK up to 20 MHz)
//   sel 2: PE43711 DSA -- 8 bits LSB first (D0 first), shifted on CLK's rising edge, latched on LE's
//                         rising edge; D7 must be 0; SCLK <= 10 MHz, high/low >= 30 ns, LE >= 30 ns
// SCLK and SDATA idle low, LE idles low; the LE pulse is 2 half-periods wide.
// Half period = ceil(CLK_HZ / (2 x SCLK_HZ_MAX)) cycles: 8 at 125 MHz (7.8 MHz), 4 at 50 MHz (6.25 MHz).

module spi_master #(
    parameter integer CLK_HZ      = 50_000_000,
    parameter integer SCLK_HZ_MAX = 8_000_000
) (
    input  wire        clk,
    input  wire        rst,
    input  wire        start,      // sampled while !busy
    input  wire [31:0] word,       // the word; for nbits < 32 and MSB first its low nbits are sent
    input  wire [5:0]  nbits,      // 1..32 (0 is treated as 32)
    input  wire        lsb_first,
    input  wire [1:0]  sel,        // which LE to pulse: 0 TX PLL, 1 RX PLL, 2 DSA
    output reg         busy,
    output reg         sclk,
    output reg         sdata,
    output reg         le_tx,
    output reg         le_rx,
    output reg         le_dsa
);
    localparam integer HALF = (CLK_HZ + 2 * SCLK_HZ_MAX - 1) / (2 * SCLK_HZ_MAX);
    localparam integer CW   = (HALF < 2) ? 2 : $clog2(2 * HALF + 1);
    localparam integer LEW  = 2 * HALF;
    localparam [CW-1:0] HALF_M1 = HALF[CW-1:0] - 1'b1;
    localparam [CW-1:0] LEW_M1  = LEW[CW-1:0] - 1'b1;

    localparam [2:0] S_IDLE = 3'd0, S_LO = 3'd1, S_HI = 3'd2, S_LESU = 3'd3, S_LEHI = 3'd4, S_LELO = 3'd5;

    reg [2:0]  st;
    reg [CW-1:0] cnt;
    reg [31:0] sh;
    reg [5:0]  left;
    reg        lsb;
    reg [1:0]  sel_r;

    wire [5:0]  n_eff = (nbits == 6'd0) ? 6'd32 : nbits;
    wire [31:0] word_aligned = lsb_first ? word : (word << (6'd32 - n_eff));   // MSB-first words start at bit 31

    always @(posedge clk) begin
        if (rst) begin
            st <= S_IDLE; busy <= 1'b0; sclk <= 1'b0; sdata <= 1'b0;
            le_tx <= 1'b0; le_rx <= 1'b0; le_dsa <= 1'b0;
            cnt <= {CW{1'b0}}; sh <= 32'd0; left <= 6'd0; lsb <= 1'b0; sel_r <= 2'd0;
        end else begin
            case (st)
            S_IDLE: begin
                sclk <= 1'b0; sdata <= 1'b0;
                le_tx <= 1'b0; le_rx <= 1'b0; le_dsa <= 1'b0;
                if (start) begin
                    busy  <= 1'b1;
                    sh    <= word_aligned;
                    left  <= n_eff;
                    lsb   <= lsb_first;
                    sel_r <= sel;
                    cnt   <= HALF_M1;
                    st    <= S_LO;
                end
            end
            S_LO: begin                                    // SCLK low: present the bit
                sdata <= lsb ? sh[0] : sh[31];
                if (cnt != {CW{1'b0}}) cnt <= cnt - 1'b1;
                else begin sclk <= 1'b1; cnt <= HALF_M1; st <= S_HI; end
            end
            S_HI: begin                                    // SCLK high: the slave has taken it
                if (cnt != {CW{1'b0}}) cnt <= cnt - 1'b1;
                else begin
                    sclk <= 1'b0;
                    sh   <= lsb ? {1'b0, sh[31:1]} : {sh[30:0], 1'b0};
                    left <= left - 1'b1;
                    cnt  <= HALF_M1;
                    st   <= (left == 6'd1) ? S_LESU : S_LO;
                end
            end
            S_LESU: begin                                  // last clock low, data released, then LE
                sdata <= 1'b0;
                if (cnt != {CW{1'b0}}) cnt <= cnt - 1'b1;
                else begin
                    le_tx  <= (sel_r == 2'd0);
                    le_rx  <= (sel_r == 2'd1);
                    le_dsa <= (sel_r == 2'd2);
                    cnt <= LEW_M1;
                    st  <= S_LEHI;
                end
            end
            S_LEHI: begin
                if (cnt != {CW{1'b0}}) cnt <= cnt - 1'b1;
                else begin
                    le_tx <= 1'b0; le_rx <= 1'b0; le_dsa <= 1'b0;
                    cnt <= HALF_M1;
                    st  <= S_LELO;
                end
            end
            S_LELO: begin                                  // LE hold, then free
                if (cnt != {CW{1'b0}}) cnt <= cnt - 1'b1;
                else begin busy <= 1'b0; st <= S_IDLE; end
            end
            default: st <= S_IDLE;
            endcase
        end
    end
endmodule
