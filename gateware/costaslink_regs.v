// costaslink_regs: the register file behind the tiny bus (addr / wdata / we / re / rdata), and the
// two serial masters it owns: the SPI to the synthesizers and the DSA (with the MAX2871 power-up
// sequencer) and the I2C to the DACs and the ADC (with the fast-write / config / read helpers).
//
// Board signals: SPI_SCLK, SPI_SDATA, LE_PLL_TX, LE_PLL_RX, LE_DSA; I2C_SDA, I2C_SCL (open drain, via
// the top); and, as register bits handed to the top, TX_DIS, LOOP_HOLD, LOOP_SEL, TR_A / TR_B,
// SPARE3.  The TX symbol, the comparator monitor and the Morse keyer live in their own modules; this
// one holds their settings and exposes their results.  The full map is in README.md.
//
// Bus: `we` / `re` are one-cycle pulses; `rdata` is combinational from `addr` (no read side effects).
// uart_cmd.v drives it now; an AXI-Lite bridge drives it on the PYNQ-Z2 later.

module costaslink_regs #(
    parameter integer CLK_HZ = 50_000_000
) (
    input  wire         clk,
    input  wire         rst,
    // the bus
    input  wire [7:0]   bus_addr,
    input  wire [31:0]  bus_wdata,
    input  wire         bus_we,
    input  wire         bus_re,
    output reg  [31:0]  bus_rdata,
    // control bits (CTRL, 0x01)
    output reg          ctrl_tx_dis,
    output reg          ctrl_loop_hold,
    output reg          ctrl_loop_sel,
    output reg          ctrl_tr_a,
    output reg          ctrl_id_enable,
    output reg          ctrl_txq1_hiz,     // [8]: TX_Q1 an input, for the board's FPGA-free trigger path (Response 14)
    output reg          id_now,            // pulse
    // tx_symbol
    output reg          sym_we,
    output wire [3:0]   sym_wdata,
    output reg  [31:0]  pat_period,
    output reg  [31:0]  pat_width,
    output reg  [15:0]  pat_count,
    output reg          pat_start,
    output reg          pat_stop,
    input  wire [3:0]   sym_cur,
    input  wire         pat_running,
    // cmp_monitor
    output reg  [7:0]   trig_width,
    output reg          trig_a_en,
    output reg          trig_b_en,
    output reg          trig_b_rise_only,
    output reg  [1:0]   trig_a_src,        // TRIG_CFG[12:11] (Response 15): 0 symbol change, 1 TX event
    output reg  [1:0]   trig_b_src,        // TRIG_CFG[14:13]: 0 CMP_I edge, 1 RX event, 2 RX decision, 3 valid decision
    output reg          cnt_clear,         // pulse
    input  wire [10:0]  cmp_state,
    input  wire [31:0]  free_cnt,
    input  wire [255:0] edge_cnts,
    input  wire [31:0]  cmp_i_ts,
    input  wire [17:0]  latency,
    // morse_keyer
    input  wire         id_active,
    input  wire         id_key,
    input  wire [15:0]  id_secs,
    // SPI pins
    output wire         spi_sclk,
    output wire         spi_sdata,
    output wire         le_pll_tx,
    output wire         le_pll_rx,
    output wire         le_dsa,
    // I2C (open drain: _o = 1 releases)
    input  wire         i2c_scl_i,
    input  wire         i2c_sda_i,
    output wire         i2c_scl_o,
    output wire         i2c_sda_o
);
    // ---- addresses ------------------------------------------------------------------------------
    localparam [7:0] A_ID = 8'h00, A_CTRL = 8'h01, A_TXSYM = 8'h02, A_PAT_PERIOD = 8'h03, A_PAT_WIDTH = 8'h04,
                     A_PAT_CTRL = 8'h05, A_TRIG_CFG = 8'h06,
                     A_SPI_DATA = 8'h08, A_SPI_CTRL = 8'h09, A_PLL_INIT = 8'h0A, A_STATUS = 8'h0B, A_BUS_COUNT = 8'h0C,
                     A_I2C_CTRL = 8'h10, A_I2C_WDATA0 = 8'h11, A_I2C_WDATA1 = 8'h12, A_I2C_WDATA2 = 8'h13, A_I2C_RDATA = 8'h14,
                     A_DAC_AB = 8'h18, A_DAC_CD = 8'h19, A_DAC_GO = 8'h1A, A_ADC_CFG = 8'h1B, A_ADC_READ = 8'h1C,
                     A_CMP_STATE = 8'h20, A_FREE_CNT = 8'h21, A_EDGE0 = 8'h22, A_EDGE5 = 8'h27, A_CMP_I_TS = 8'h28,
                     A_LAT = 8'h29, A_CNT_CTRL = 8'h2A, A_MORSE = 8'h2B, A_EDGE6 = 8'h2C, A_EDGE7 = 8'h2D;
    localparam [31:0] ID_WORD = 32'h434C_0002;          // "CL", version 2: the experiment engines (Response 15)

    // ---- SPI: the register path and the init sequencer share one master ------------------------
    reg  [31:0] spi_data;
    reg  [1:0]  spi_sel_r;
    reg         spi_go;
    reg         init_go;
    wire        spi_busy;
    wire        init_busy, init_done;
    wire        init_spi_start;
    wire [31:0] init_word;
    wire [1:0]  init_sel;
    reg         init_done_flag;

    wire        m_start = init_busy ? init_spi_start : spi_go;
    wire [31:0] m_word  = init_busy ? init_word : spi_data;
    wire [1:0]  m_sel   = init_busy ? init_sel : spi_sel_r;
    wire        m_dsa   = (m_sel == 2'd2);

    spi_master #(.CLK_HZ(CLK_HZ)) u_spi (
        .clk(clk), .rst(rst), .start(m_start), .word(m_word),
        .nbits(m_dsa ? 6'd8 : 6'd32), .lsb_first(m_dsa), .sel(m_sel),
        .busy(spi_busy), .sclk(spi_sclk), .sdata(spi_sdata),
        .le_tx(le_pll_tx), .le_rx(le_pll_rx), .le_dsa(le_dsa));

    max2871_init #(.CLK_HZ(CLK_HZ)) u_init (
        .clk(clk), .rst(rst), .start(init_go), .busy(init_busy), .done(init_done),
        .spi_start(init_spi_start), .spi_word(init_word), .spi_sel(init_sel), .spi_busy(spi_busy));

    // ---- I2C ------------------------------------------------------------------------------------
    reg  [6:0]  i2c_addr;
    reg  [3:0]  i2c_nwrite;
    reg  [1:0]  i2c_nread;
    reg  [71:0] i2c_wbuf;
    reg         i2c_go;
    wire        i2c_busy, i2c_done, i2c_nack, i2c_timeout;
    wire [15:0] i2c_rbuf;
    reg  [1:0]  scl_sync, sda_sync;     // the lines as they are, for I2C_CTRL [21:20] (a stuck bus, seen from here)
    always @(posedge clk) begin scl_sync <= {scl_sync[0], i2c_scl_i}; sda_sync <= {sda_sync[0], i2c_sda_i}; end
    reg         i2c_done_flag;
    reg         adc_pending;
    reg  [15:0] adc_result;
    reg         adc_valid;
    reg  [15:0] adc_cfg;
    reg  [11:0] dac_a, dac_b, dac_c, dac_d;

    i2c_master #(.CLK_HZ(CLK_HZ)) u_i2c (
        .clk(clk), .rst(rst), .start(i2c_go), .addr(i2c_addr), .nwrite(i2c_nwrite), .nread(i2c_nread),
        .wbuf(i2c_wbuf), .busy(i2c_busy), .done(i2c_done), .nack(i2c_nack), .timeout(i2c_timeout), .rbuf(i2c_rbuf),
        .scl_i(i2c_scl_i), .sda_i(i2c_sda_i), .scl_o(i2c_scl_o), .sda_o(i2c_sda_o));

    // ADS1115 config: OS = 1 (start), MUX = 1cc (AINc vs GND), PGA = 001 (+-4.096 V: the 3.3 V nodes),
    // MODE = 1 (single shot), DR = 111 (860 SPS), comparator off (COMP_QUE = 11)
    function [15:0] ads_cfg;
        input [1:0] ch;
        begin
            ads_cfg = {1'b1, 1'b1, ch, 3'b001, 1'b1, 3'b111, 1'b0, 1'b0, 1'b0, 2'b11};
        end
    endfunction

    // ---- the registers ------------------------------------------------------------------------------
    reg [3:0]  sym_reg;
    reg [15:0] n_writes, n_reads;
    assign sym_wdata = sym_reg;

    always @(posedge clk) begin
        sym_we <= 1'b0; pat_start <= 1'b0; pat_stop <= 1'b0; cnt_clear <= 1'b0; id_now <= 1'b0;
        spi_go <= 1'b0; init_go <= 1'b0; i2c_go <= 1'b0;
        if (rst) begin
            ctrl_tx_dis <= 1'b1;            // muted until the host says otherwise (BRINGUP.md stage 2.3)
            ctrl_loop_hold <= 1'b1;         // the loop open: VC at V_MID (stage 1.5)
            ctrl_loop_sel <= 1'b0;
            ctrl_tr_a <= 1'b1;              // the switch in receive (A high, B low)
            ctrl_id_enable <= 1'b0; ctrl_txq1_hiz <= 1'b0;
            sym_reg <= 4'b0111;             // idle: I +a, Q 0
            pat_period <= 32'd1000; pat_width <= 32'd10; pat_count <= 16'd0;
            trig_width <= 8'd8; trig_a_en <= 1'b1; trig_b_en <= 1'b1; trig_b_rise_only <= 1'b0;
            trig_a_src <= 2'd0; trig_b_src <= 2'd0;
            spi_data <= 32'd0; spi_sel_r <= 2'd0; init_done_flag <= 1'b0;
            i2c_addr <= 7'd0; i2c_nwrite <= 4'd0; i2c_nread <= 2'd0; i2c_wbuf <= 72'd0; i2c_done_flag <= 1'b0;
            adc_pending <= 1'b0; adc_result <= 16'd0; adc_valid <= 1'b0; adc_cfg <= 16'd0;
            dac_a <= 12'd0; dac_b <= 12'd0; dac_c <= 12'd0; dac_d <= 12'd0;
            n_writes <= 16'd0; n_reads <= 16'd0;
        end else begin
            if (init_done) init_done_flag <= 1'b1;
            if (i2c_done) begin
                i2c_done_flag <= 1'b1;
                if (adc_pending) begin
                    adc_pending <= 1'b0;
                    if (!i2c_nack) begin adc_result <= i2c_rbuf; adc_valid <= 1'b1; end
                end
            end
            if (bus_re) n_reads <= n_reads + 1'b1;
            if (bus_we) begin
                n_writes <= n_writes + 1'b1;
                case (bus_addr)
                A_CTRL: begin
                    ctrl_tx_dis     <= bus_wdata[0];
                    ctrl_loop_hold  <= bus_wdata[1];
                    ctrl_loop_sel   <= bus_wdata[2];
                    ctrl_tr_a       <= bus_wdata[3];      // [5:4] retired: TR_B is made on the board from TR_A
                    ctrl_id_enable  <= bus_wdata[6];
                    id_now          <= bus_wdata[7];
                    ctrl_txq1_hiz   <= bus_wdata[8];
                end
                A_TXSYM: begin sym_reg <= bus_wdata[3:0]; sym_we <= 1'b1; end
                A_PAT_PERIOD: pat_period <= bus_wdata;
                A_PAT_WIDTH:  pat_width  <= bus_wdata;
                A_PAT_CTRL: begin
                    pat_count <= bus_wdata[31:16];
                    pat_start <= bus_wdata[0];
                    pat_stop  <= ~bus_wdata[0];
                end
                A_TRIG_CFG: begin
                    trig_width       <= bus_wdata[7:0];
                    trig_a_en        <= bus_wdata[8];
                    trig_b_en        <= bus_wdata[9];
                    trig_b_rise_only <= bus_wdata[10];
                    trig_a_src <= bus_wdata[12:11];
                    trig_b_src <= bus_wdata[14:13];
                end
                A_SPI_DATA: spi_data <= bus_wdata;
                A_SPI_CTRL: if (!spi_busy && !init_busy) begin spi_sel_r <= bus_wdata[1:0]; spi_go <= 1'b1; end
                A_PLL_INIT: if (!spi_busy && !init_busy) begin init_go <= 1'b1; init_done_flag <= 1'b0; end
                A_I2C_CTRL: if (!i2c_busy) begin
                    i2c_addr   <= bus_wdata[6:0];
                    i2c_nwrite <= bus_wdata[11:8];
                    i2c_nread  <= bus_wdata[13:12];
                    i2c_go     <= 1'b1;
                    i2c_done_flag <= 1'b0;
                end
                A_I2C_WDATA0: i2c_wbuf[71:40] <= bus_wdata;
                A_I2C_WDATA1: i2c_wbuf[39:8]  <= bus_wdata;
                A_I2C_WDATA2: i2c_wbuf[7:0]   <= bus_wdata[31:24];
                A_DAC_AB: begin dac_a <= bus_wdata[27:16]; dac_b <= bus_wdata[11:0]; end
                A_DAC_CD: begin dac_c <= bus_wdata[27:16]; dac_d <= bus_wdata[11:0]; end
                A_DAC_GO: if (!i2c_busy) begin             // MCP4728 fast write: C2 C1 = 00, PD = 00, 12 bits, x 4
                    i2c_addr   <= {6'b110000, bus_wdata[0]};   // 0x60 or 0x61
                    i2c_nwrite <= 4'd8;
                    i2c_nread  <= 2'd0;
                    i2c_wbuf   <= {4'b0000, dac_a, 4'b0000, dac_b, 4'b0000, dac_c, 4'b0000, dac_d, 8'd0};
                    i2c_go     <= 1'b1;
                    i2c_done_flag <= 1'b0;
                end
                A_ADC_CFG: if (!i2c_busy) begin            // ADS1115: pointer 01 = Config, then the two bytes
                    i2c_addr   <= 7'h48;
                    i2c_nwrite <= 4'd3;
                    i2c_nread  <= 2'd0;
                    i2c_wbuf   <= {8'h01, ads_cfg(bus_wdata[1:0]), 48'd0};
                    adc_cfg    <= ads_cfg(bus_wdata[1:0]);
                    i2c_go     <= 1'b1;
                    i2c_done_flag <= 1'b0;
                end
                A_ADC_READ: if (!i2c_busy) begin           // pointer 00 = Conversion, repeated start, two bytes
                    i2c_addr   <= 7'h48;
                    i2c_nwrite <= 4'd1;
                    i2c_nread  <= 2'd2;
                    i2c_wbuf   <= {8'h00, 64'd0};
                    i2c_go     <= 1'b1;
                    i2c_done_flag <= 1'b0;
                    adc_pending <= 1'b1;
                    adc_valid   <= 1'b0;
                end
                A_CNT_CTRL: cnt_clear <= bus_wdata[0];
                default: ;
                endcase
            end
        end
    end

    // ---- reads ----------------------------------------------------------------------------------------
    wire [2:0] edge_idx = bus_addr[2:0] - 3'd2;          // 0x22..0x27 -> 0..5
    always @* begin
        case (bus_addr)
        A_ID:         bus_rdata = ID_WORD;
        A_CTRL:       bus_rdata = {23'd0, ctrl_txq1_hiz, 1'b0, ctrl_id_enable, 2'b00,
                                   ctrl_tr_a, ctrl_loop_sel, ctrl_loop_hold, ctrl_tx_dis};
        A_TXSYM:      bus_rdata = {24'd0, sym_cur, sym_reg};          // [7:4] the pins now, [3:0] the register
        A_PAT_PERIOD: bus_rdata = pat_period;
        A_PAT_WIDTH:  bus_rdata = pat_width;
        A_PAT_CTRL:   bus_rdata = {pat_count, 15'd0, pat_running};
        A_TRIG_CFG:   bus_rdata = {17'd0, trig_b_src, trig_a_src, trig_b_rise_only, trig_b_en, trig_a_en, trig_width};
        A_SPI_DATA:   bus_rdata = spi_data;
        A_SPI_CTRL:   bus_rdata = {28'd0, spi_sel_r, init_busy, spi_busy};
        A_PLL_INIT:   bus_rdata = {30'd0, init_done_flag, init_busy};
        A_STATUS:     bus_rdata = {26'd0, id_key, id_active, i2c_busy, spi_busy | init_busy, cmp_state[8], cmp_state[7]};
        A_BUS_COUNT:  bus_rdata = {n_writes, n_reads};
        A_I2C_CTRL:   bus_rdata = {10'd0, sda_sync[1], scl_sync[1], i2c_timeout, i2c_done_flag, i2c_nack, i2c_busy, 2'd0,
                                   i2c_nread, i2c_nwrite, 1'b0, i2c_addr};
        A_I2C_WDATA0: bus_rdata = i2c_wbuf[71:40];
        A_I2C_WDATA1: bus_rdata = i2c_wbuf[39:8];
        A_I2C_WDATA2: bus_rdata = {i2c_wbuf[7:0], 24'd0};
        A_I2C_RDATA:  bus_rdata = {16'd0, i2c_rbuf};
        A_DAC_AB:     bus_rdata = {4'd0, dac_a, 4'd0, dac_b};
        A_DAC_CD:     bus_rdata = {4'd0, dac_c, 4'd0, dac_d};
        A_DAC_GO:     bus_rdata = {31'd0, i2c_busy};
        A_ADC_CFG:    bus_rdata = {16'd0, adc_cfg};
        A_ADC_READ:   bus_rdata = {15'd0, adc_valid, adc_result};
        A_CMP_STATE:  bus_rdata = {21'd0, cmp_state};
        A_FREE_CNT:   bus_rdata = free_cnt;
        A_CMP_I_TS:   bus_rdata = cmp_i_ts;
        A_LAT:        bus_rdata = {14'd0, latency};
        A_CNT_CTRL:   bus_rdata = 32'd0;
        A_MORSE:      bus_rdata = {id_secs, 14'd0, id_key, id_active};
        A_EDGE6:      bus_rdata = edge_cnts[223:192];                 // CMP_IP
        A_EDGE7:      bus_rdata = edge_cnts[255:224];                 // CMP_IN
        default: begin
            if (bus_addr >= A_EDGE0 && bus_addr <= A_EDGE5) bus_rdata = edge_cnts[{edge_idx, 5'd0} +: 32];
            else bus_rdata = 32'hDEAD_0000 | {24'd0, bus_addr};
        end
        endcase
    end
endmodule
