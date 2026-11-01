// tb_costaslink: the simulation of costaslink_top at the Icepi's 50 MHz, driven through its UART.
//
// What it checks (make sim; Icarus Verilog):
//   * the register ID reads back over the UART protocol;
//   * "W 0A 1" sends both synthesizers' power-up sequences: 16 words on SPI_SDATA / SPI_SCLK, each
//     latched by the right LE (LE_PLL_TX for the first eight, LE_PLL_RX for the next), 32 bits MSB
//     first, equal to max2871_regs.py --hex (read from ../build/gateware_scratch/max2871_expected.hex),
//     with the 20 ms pause after the first word of each chip;
//   * a DSA write is 8 bits LSB first with LE_DSA;
//   * a DAC fast write is START, 0xC0, eight data bytes, STOP, each byte acknowledged by the slave model;
//   * the ADS1115 config write and the pointer-write / repeated-start / two-byte read, whose result
//     reads back through the register;
//   * an address probe of an absent slave reports NACK;
//   * the TX symbol register moves the ladder pins and pulses TRIG_A; the BPSK pattern runs its count;
//   * the comparator edge counters, TRIG_B and the TRIG_IN -> CMP_I latency counter;
//   * the Morse identification keys TX_DIS with the dits and dahs of "W3JQ" (at 4800 WPM here).
// The whole file is skipped under SYNTHESIS so `read_verilog gateware/*.v` in yosys is harmless.

`ifndef SYNTHESIS
`timescale 1ns / 1ps
`ifndef EXPECTED_HEX
`define EXPECTED_HEX "../build/gateware_scratch/max2871_expected.hex"
`endif

module tb_costaslink;
    localparam integer CLK_HZ = 50_000_000;
    localparam integer BAUD   = 115200;
    localparam integer ID_WPM = 4800;                   // dit = 0.25 ms here; 20 WPM on the board
    localparam real    BIT_NS = 1.0e9 / BAUD;
    localparam real    DIT_NS = 1.2e9 / ID_WPM;

    reg sysclk = 1'b0;
    always #10 sysclk = ~sysclk;

    tri1 i2c_sda, i2c_scl;                              // the pull-ups
    reg  scl_hold = 1'b0;                               // 1: something on the board holds SCL low
    assign i2c_scl = scl_hold ? 1'b0 : 1'bz;
    real t0;
    wire tx_i1, tx_i0, tx_q1, tx_q0;
    reg  cmp_qn = 1'b0, cmp_qp = 1'b0, cmp_i = 1'b0, cmp_i_s = 1'b0, cmp_qn_s = 1'b0, cmp_qp_s = 1'b0;
    reg  cmp_ip = 1'b0, cmp_in = 1'b0;
    wire spi_sclk, spi_sdata, le_pll_tx, le_pll_rx, le_dsa;
    wire loop_hold, loop_sel, tx_en;
    wire tx_dis = ~tx_en;                  // the core's TX_DIS (the header carries TX_EN, Response 15)
    reg  trig_in = 1'b0;
    wire trig_a, trig_b, tr_a;
    reg  mux_tx = 1'b0, mux_rx = 1'b0;
    reg  uart_rx_line = 1'b1;
    wire uart_tx_line;

    costaslink_top #(.CLK_HZ(CLK_HZ), .BAUD(BAUD), .ID_WPM(ID_WPM)) dut (
        .sysclk(sysclk), .i2c_sda(i2c_sda), .i2c_scl(i2c_scl),
        .tx_i1(tx_i1), .tx_i0(tx_i0), .tx_q1(tx_q1), .tx_q0(tx_q0),
        .cmp_qn(cmp_qn), .cmp_qp(cmp_qp), .cmp_i(cmp_i), .cmp_i_s(cmp_i_s), .cmp_qn_s(cmp_qn_s), .cmp_qp_s(cmp_qp_s),
        .cmp_ip(cmp_ip), .cmp_in(cmp_in),
        .spi_sclk(spi_sclk), .spi_sdata(spi_sdata), .le_pll_tx(le_pll_tx), .le_pll_rx(le_pll_rx), .le_dsa(le_dsa),
        .loop_hold(loop_hold), .loop_sel(loop_sel), .tx_en(tx_en),
        .trig_in(trig_in), .trig_a(trig_a), .trig_b(trig_b), .tr_a(tr_a),
        .mux_tx(mux_tx), .mux_rx(mux_rx),
        .uart_rx(uart_rx_line), .uart_tx(uart_tx_line));

    i2c_slave_model slave (.sda(i2c_sda), .scl(i2c_scl));

    integer errors = 0;
    task fail; input [8*64-1:0] msg; begin
        errors = errors + 1;
        $display("FAIL at %0t: %0s", $time, msg);
    end endtask

    // ---- the expected MAX2871 words -------------------------------------------------------------------
    reg [31:0] expected [0:15];
    initial $readmemh(`EXPECTED_HEX, expected);

    // ---- SPI slave model: shift on SCLK's rising edge, record on any LE's rising edge ---------------------
    reg [31:0] spi_sh = 32'd0;
    integer    spi_nbits = 0;
    always @(posedge spi_sclk) begin
        spi_sh    = {spi_sh[30:0], spi_sdata};
        spi_nbits = spi_nbits + 1;
    end
    integer    nw = 0;
    reg [31:0] w_word [0:63];
    integer    w_sel  [0:63];
    integer    w_bits [0:63];
    time       w_time [0:63];
    always @(posedge le_pll_tx or posedge le_pll_rx or posedge le_dsa) begin
        if (spi_sclk !== 1'b0) fail("SCLK not low at LE");
        if ({2'b0, le_pll_tx} + {2'b0, le_pll_rx} + {2'b0, le_dsa} != 3'd1) fail("more than one LE high");
        w_word[nw] = spi_sh;
        w_sel[nw]  = le_pll_tx ? 0 : (le_pll_rx ? 1 : 2);
        w_bits[nw] = spi_nbits;
        w_time[nw] = $time;
        nw = nw + 1;
        spi_sh = 32'd0;
        spi_nbits = 0;
    end
    function [7:0] bitrev8; input [7:0] v; integer k; begin
        for (k = 0; k < 8; k = k + 1) bitrev8[k] = v[7-k];
    end endfunction

    // ---- UART: send, and collect the reply up to its newline --------------------------------------------
    task uart_send_byte; input [7:0] b; integer k; begin
        uart_rx_line = 1'b0; #(BIT_NS);
        for (k = 0; k < 8; k = k + 1) begin uart_rx_line = b[k]; #(BIT_NS); end
        uart_rx_line = 1'b1; #(BIT_NS);
    end endtask

    reg [8*16-1:0] reply = 0;
    integer        reply_len = 0;
    reg            reply_ready = 1'b0;
    reg [7:0]      rxb;
    integer        rk;
    always begin
        @(negedge uart_tx_line);
        #(BIT_NS * 1.5);
        for (rk = 0; rk < 8; rk = rk + 1) begin rxb[rk] = uart_tx_line; #(BIT_NS); end
        if (uart_tx_line !== 1'b1) fail("UART reply framing");
        if (rxb == 8'h0A) reply_ready = 1'b1;
        else begin reply = {reply[8*15-1:0], rxb}; reply_len = reply_len + 1; end
    end

    // send a command (up to 24 characters, newline included) and compare the reply text
    task cmd; input [8*24-1:0] s; input [8*16-1:0] exp; integer i, t; begin
        reply = 0; reply_len = 0; reply_ready = 1'b0;
        for (i = 23; i >= 0; i = i - 1) if (s[8*i +: 8] != 8'd0) uart_send_byte(s[8*i +: 8]);
        t = 0;
        while (!reply_ready && t < 100000) begin #1000; t = t + 1; end       // up to 100 ms
        if (!reply_ready) fail({"no reply to: ", s[8*24-1:8*8]});
        else if (reply !== exp) begin
            fail({"wrong reply to: ", s[8*24-1:8*8]});
            $display("      got '%0s' expected '%0s'", reply, exp);
        end
    end endtask

    function [31:0] hexval; input [8*16-1:0] s; integer i; reg [7:0] c; begin
        hexval = 32'd0;
        for (i = 7; i >= 0; i = i - 1) begin
            c = s[8*i +: 8];
            hexval = {hexval[27:0], (c <= 8'h39) ? c[3:0] : (c[3:0] + 4'd9)};
        end
    end endfunction

    // read a register and return its value
    task rd; input [7:0] a; output [31:0] v; reg [8*24-1:0] s; integer t; begin
        s = {"R ", hexchar(a[7:4]), hexchar(a[3:0]), 8'h0A};
        reply = 0; reply_len = 0; reply_ready = 1'b0;
        uart_send_byte("R"); uart_send_byte(" "); uart_send_byte(hexchar(a[7:4])); uart_send_byte(hexchar(a[3:0])); uart_send_byte(8'h0A);
        t = 0;
        while (!reply_ready && t < 100000) begin #1000; t = t + 1; end
        if (!reply_ready || reply_len != 8) begin fail("bad read reply"); v = 32'hFFFFFFFF; end
        else v = hexval(reply);
    end endtask
    function [7:0] hexchar; input [3:0] v; begin
        hexchar = (v < 4'd10) ? (8'h30 + {4'd0, v}) : (8'h37 + {4'd0, v});
    end endfunction

    // ---- counters for the pins ----------------------------------------------------------------------------
    integer n_trig_a = 0, n_trig_b = 0;
    time    trig_a_rise = 0, trig_a_width = 0;
    always @(posedge trig_a) begin n_trig_a = n_trig_a + 1; trig_a_rise = $time; end
    always @(negedge trig_a) trig_a_width = $time - trig_a_rise;
    always @(posedge trig_b) n_trig_b = n_trig_b + 1;

    // the keyed carrier: TX_DIS low = key down
    integer n_on = 0, n_off = 0;
    time    key_down_t = 0, key_up_t = 0;
    time    on_dur [0:31];
    time    off_dur [0:31];
    reg     id_running = 1'b0;
    always @(negedge tx_dis) if (id_running) begin
        if (n_on > 0) begin off_dur[n_off] = $time - key_up_t; n_off = n_off + 1; end
        key_down_t = $time;
    end
    always @(posedge tx_dis) if (id_running) begin
        on_dur[n_on] = $time - key_down_t; n_on = n_on + 1; key_up_t = $time;
    end
    function integer units; input time d; begin
        units = (d + DIT_NS / 2) / DIT_NS;
    end endfunction
    reg [3:0] exp_on  [0:15];
    reg [3:0] exp_off [0:14];

    // ---- the test ---------------------------------------------------------------------------------------------
    integer i, t;
    reg [31:0] v;
    time t_gap;
    initial begin
        // W3JQ: W .--  3 ...--  J .---  Q --.-
        exp_on[0]=1; exp_on[1]=3; exp_on[2]=3;
        exp_on[3]=1; exp_on[4]=1; exp_on[5]=1; exp_on[6]=3; exp_on[7]=3;
        exp_on[8]=1; exp_on[9]=3; exp_on[10]=3; exp_on[11]=3;
        exp_on[12]=3; exp_on[13]=3; exp_on[14]=1; exp_on[15]=3;
        exp_off[0]=1; exp_off[1]=1; exp_off[2]=3;
        exp_off[3]=1; exp_off[4]=1; exp_off[5]=1; exp_off[6]=1; exp_off[7]=3;
        exp_off[8]=1; exp_off[9]=1; exp_off[10]=1; exp_off[11]=3;
        exp_off[12]=1; exp_off[13]=1; exp_off[14]=1;

        #2000;                                           // the power-on reset (16 clocks) and some
        // defaults on the pins
        if (tx_dis !== 1'b1)    fail("TX_DIS should come up high (muted)");
        if (loop_hold !== 1'b1) fail("LOOP_HOLD should come up high");
        if (tr_a !== 1'b1) fail("TR_A should come up 1 (receive; the board makes B = not A)");
        if ({tx_i1, tx_i0, tx_q1, tx_q0} !== 4'b1101) fail("ladders should idle at I +a (11), Q 0 (01)");

        // 1. the ID register and a bad line
        cmd("R 00\n", "434C000A");
        cmd("X 00\n", "?");
        cmd("W 01\n", "?");

        // 2. the synthesizers' power-up sequence
        cmd("W 0A 1\n", "OK");
        t = 0;
        while (nw < 16 && t < 100000) begin #1000; t = t + 1; end
        if (nw != 16) fail("expected 16 SPI words from the init");
        else begin
            for (i = 0; i < 16; i = i + 1) begin
                if (w_word[i] !== expected[i]) begin
                    fail("init word mismatch");
                    $display("      word %0d: got %08X expected %08X", i, w_word[i], expected[i]);
                end
                if (w_bits[i] != 32) fail("init word not 32 bits");
                if (w_sel[i] != (i < 8 ? 0 : 1)) fail("init word latched by the wrong LE");
            end
            t_gap = w_time[1] - w_time[0];
            if (t_gap < 20_000_000 || t_gap > 21_000_000) begin fail("TX: no 20 ms pause after register 5"); $display("      gap %0t", t_gap); end
            t_gap = w_time[9] - w_time[8];
            if (t_gap < 20_000_000 || t_gap > 21_000_000) begin fail("RX: no 20 ms pause after register 5"); $display("      gap %0t", t_gap); end
            if (w_time[2] - w_time[1] > 100_000) fail("words after the pause should follow at once");
            $display("init: 16 words OK, TX pause %0t ns, words %08X %08X ... %08X", w_time[1] - w_time[0], w_word[0], w_word[1], w_word[15]);
        end
        rd(8'h0A, v); if (v !== 32'h2) fail("PLL_INIT should read done, not busy");

        // 3. the DSA: 12.5 dB = 50 = 0x32, LSB first
        cmd("W 08 00000032\n", "OK");
        cmd("W 09 2\n", "OK");
        t = 0; while (nw < 17 && t < 1000) begin #1000; t = t + 1; end
        if (nw != 17) fail("no DSA word");
        else begin
            if (w_sel[16] != 2) fail("DSA word not latched by LE_DSA");
            if (w_bits[16] != 8) fail("DSA word not 8 bits");
            if (bitrev8(w_word[16][7:0]) !== 8'h32) begin fail("DSA word bits wrong (LSB first expected)"); $display("      raw %02X", w_word[16][7:0]); end
            else $display("DSA: 8 bits LSB first OK (raw %02X -> %02X)", w_word[16][7:0], bitrev8(w_word[16][7:0]));
        end

        // 4. a DAC fast write: all four channels to 0x800 on DAC 0x60
        slave.reset_log;
        cmd("W 18 08000800\n", "OK");
        cmd("W 19 08000800\n", "OK");
        cmd("W 1A 0\n", "OK");
        t = 0; while (slave.nstop < 1 && t < 5000) begin #1000; t = t + 1; end
        if (slave.nstop != 1 || slave.nstart != 1) fail("DAC write: expected one START and one STOP");
        if (slave.addr_byte !== 8'hC0) begin fail("DAC write: address byte"); $display("      got %02X", slave.addr_byte); end
        if (slave.nbytes != 8) begin fail("DAC write: expected 8 data bytes"); $display("      got %0d", slave.nbytes); end
        for (i = 0; i < 8; i = i + 1)
            if (slave.bytes[i] !== ((i % 2 == 0) ? 8'h08 : 8'h00)) begin fail("DAC write: data byte"); $display("      byte %0d = %02X", i, slave.bytes[i]); end
        if (slave.n_nacked != 0) fail("DAC write: the master saw a NACK?");
        rd(8'h10, v); if (v[18:16] !== 3'b100) begin fail("I2C_CTRL after the DAC write: done, no nack, not busy"); $display("      got %08X", v); end
        $display("DAC: START %02X + %0d bytes + STOP OK", slave.addr_byte, slave.nbytes);

        // 5. ADS1115: config of channel 0, then the conversion read
        slave.reset_log;
        cmd("W 1B 0\n", "OK");
        t = 0; while (slave.nstop < 1 && t < 5000) begin #1000; t = t + 1; end
        if (slave.addr_byte !== 8'h90 || slave.nbytes != 3) fail("ADC config: framing");
        if (slave.bytes[0] !== 8'h01 || slave.bytes[1] !== 8'hC3 || slave.bytes[2] !== 8'hE3) begin
            fail("ADC config bytes"); $display("      got %02X %02X %02X", slave.bytes[0], slave.bytes[1], slave.bytes[2]);
        end
        rd(8'h1B, v); if (v !== 32'h0000C3E3) fail("ADC_CFG readback");
        slave.reset_log;
        cmd("W 1C 0\n", "OK");
        t = 0; while (slave.nstop < 1 && t < 5000) begin #1000; t = t + 1; end
        if (slave.nstart != 2) begin fail("ADC read: expected a START and a repeated START"); $display("      starts %0d", slave.nstart); end
        if (slave.addr_byte !== 8'h91) fail("ADC read: second address byte should be 0x91");
        if (slave.nbytes != 1 || slave.bytes[0] !== 8'h00) fail("ADC read: pointer byte");
        if (slave.nread_bytes != 2) fail("ADC read: slave should have sent two bytes");
        cmd("R 1C\n", "00011234");
        $display("ADC: config %02X %02X %02X, read -> 0x1234 OK", 8'h01, 8'hC3, 8'hE3);

        // 6. an address probe of nobody
        cmd("W 10 00000055\n", "OK");
        #1_000_000;
        rd(8'h10, v); if (v !== 32'h00360055) begin fail("probe of 0x55 should report NACK, both lines high"); $display("      got %08X", v); end

        // 6b. a stuck bus: SCL held low (rev A board A, 2026-10-29) must not hang the master for good: it gives up
        //     after 10 ms with timeout and NACK, and the next transaction works once the line is free
        scl_hold = 1'b1;
        t0 = $realtime;
        cmd("W 10 00000060\n", "OK");                   // a probe of DAC 0x60
        v = 32'h10000; t = 0;
        while (v[16] && t < 40) begin #500_000; rd(8'h10, v); t = t + 1; end
        if (v[16] !== 1'b0 || v[17] !== 1'b1 || v[18] !== 1'b1 || v[19] !== 1'b1) begin
            fail("stuck SCL: expected not busy, NACK, done, timeout"); $display("      got %08X", v); end
        if (v[20] !== 1'b0 || v[21] !== 1'b1) begin fail("stuck SCL: [20] SCL low, [21] SDA high"); $display("      got %08X", v); end
        if ($realtime - t0 < 10.0e6 || $realtime - t0 > 16.0e6) begin fail("stuck SCL: abandoned after 10 ms?"); $display("      %0.1f ms", ($realtime - t0) / 1.0e6); end
        $display("stuck SCL: abandoned (I2C_CTRL %08X) within %0.1f ms", v, ($realtime - t0) / 1.0e6);
        scl_hold = 1'b0;
        #2000;
        slave.reset_log;
        cmd("W 10 00000060\n", "OK");
        #1_000_000;
        rd(8'h10, v); if (v[21:16] !== 6'b110100) begin fail("after the stuck bus: the next probe of 0x60 should ACK"); $display("      got %08X", v); end
        if (slave.nstop != 1) fail("after the stuck bus: one STOP expected");

        // 7. the TX symbol and TRIG_A
        n_trig_a = 0;
        cmd("W 02 3\n", "OK");                           // I = 11 (+a), Q = 00 (-a)
        #1000;
        if ({tx_q1, tx_q0, tx_i1, tx_i0} !== 4'b0011) fail("TXSYM pins");
        if (n_trig_a != 1) fail("TRIG_A should pulse once on the symbol change");
        if (trig_a_width < 150 || trig_a_width > 170) begin fail("TRIG_A width should be 8 clocks"); $display("      %0t", trig_a_width); end
        cmd("W 02 7\n", "OK");                           // back to idle
        rd(8'h02, v); if (v !== 32'h77) fail("TXSYM readback (pins and register)");

        // 8. the BPSK pattern: 5 pulses of 10 clocks every 100 clocks
        n_trig_a = 0;
        cmd("W 03 00000064\n", "OK");
        cmd("W 04 0000000A\n", "OK");
        cmd("W 05 00050001\n", "OK");
        #20_000;
        if (n_trig_a != 10) begin fail("pattern: expected 10 edges (5 pulses)"); $display("      got %0d", n_trig_a); end
        if ({tx_i1, tx_i0} !== 2'b11) fail("pattern: I should be back at +a");
        rd(8'h05, v); if (v[0] !== 1'b0) fail("pattern should have stopped");

        // 9. the comparator counters, TRIG_B and the latency
        cmd("W 2A 1\n", "OK");
        n_trig_b = 0;
        for (i = 0; i < 10; i = i + 1) begin #1000; cmp_i = ~cmp_i; end
        #1000;
        rd(8'h22, v); if (v !== 32'd10) begin fail("CMP_I edge count"); $display("      got %0d", v); end
        if (n_trig_b != 10) begin fail("TRIG_B should pulse on every CMP_I edge"); $display("      got %0d", n_trig_b); end
        rd(8'h20, v); if (v[0] !== cmp_i) fail("CMP_STATE bit 0 should be cmp_i");
        trig_in = 1'b1; #1000; cmp_i = ~cmp_i; #500; trig_in = 1'b0; #1000;
        rd(8'h29, v);
        if (v[16] !== 1'b1 || v[17] !== 1'b0) fail("latency should be valid");
        else if (v[15:0] < 47 || v[15:0] > 53) begin fail("latency should be about 50 clocks"); $display("      got %0d", v[15:0]); end
        else $display("latency: %0d clocks for a 1 us gap OK", v[15:0]);
        trig_in = 1'b1; #100; trig_in = 1'b0;            // no CMP_I edge follows: times out at 65535 clocks
        #1_400_000;
        rd(8'h29, v); if (v[17] !== 1'b1) fail("latency should time out");

        // 10. the Morse identification: enable + send now, TX_DIS muted otherwise
        id_running = 1'b1; n_on = 0; n_off = 0;
        cmd("W 01 000000C9\n", "OK");
        rd(8'h2B, v); if (v[0] !== 1'b1) fail("MORSE should be active");
        t = 0; while (n_on < 16 && t < 200000) begin #1000; t = t + 1; end
        #(DIT_NS * 4);
        id_running = 1'b0;
        if (n_on != 16) begin fail("Morse: expected 16 elements"); $display("      got %0d", n_on); end
        else begin
            for (i = 0; i < 16; i = i + 1)
                if (units(on_dur[i]) != exp_on[i]) begin fail("Morse: element length"); $display("      element %0d: %0d units, expected %0d", i, units(on_dur[i]), exp_on[i]); end
            for (i = 0; i < 15; i = i + 1)
                if (units(off_dur[i]) != exp_off[i]) begin fail("Morse: gap length"); $display("      gap %0d: %0d units, expected %0d", i, units(off_dur[i]), exp_off[i]); end
            $display("Morse: W3JQ keyed on TX_DIS, 16 elements OK");
        end
        if (tx_dis !== 1'b1) fail("TX_DIS should return to the control bit (muted) after the ID");
        rd(8'h2B, v); if (v[0] !== 1'b0) fail("MORSE should be idle again");
        if (v[31:16] == 16'd0 || v[31:16] > 16'd600) fail("the ten-minute timer should be armed");

        // 11. the control bits
        cmd("W 01 00000000\n", "OK");                    // tx_dis 0, loop_hold 0, tr_a 0
        #100;
        if (tx_dis !== 1'b0 || loop_hold !== 1'b0 || tr_a !== 1'b0) fail("control bits");
        cmd("W 01 00000108\n", "OK");                    // tr_a 1; CTRL[8]: TX_Q1 an input (the board's TRIG IN path)
        #100;
        if (tr_a !== 1'b1) fail("TR_A should follow CTRL[3]");
        if (tx_q1 !== 1'bz) fail("TX_Q1 should be high-impedance with CTRL[8] set");
        cmd("W 01 00000008\n", "OK");
        #100;
        if (tx_q1 === 1'bz) fail("TX_Q1 should drive again with CTRL[8] clear");
        // 12. the I window's edge counters (0x2C, 0x2D)
        cmd("W 2A 00000001\n", "OK");                    // clear the counters
        #100;
        cmp_ip = 1'b1; #200; cmp_ip = 1'b0; #200; cmp_in = 1'b1; #200;
        rd(8'h2C, v); if (v !== 32'd2) fail("EDGE6 should count CMP_IP's two edges");
        rd(8'h2D, v); if (v !== 32'd1) fail("EDGE7 should count CMP_IN's edge");
        rd(8'h20, v); if (v[10] !== 1'b1 || v[9] !== 1'b0) fail("CMP_STATE [10:9] should be {cmp_in, cmp_ip}");

        if (errors == 0) $display("PASS: tb_costaslink, %0d SPI words, %0d I2C transactions", nw, slave.total_stops);
        else $display("FAIL: %0d errors", errors);
        $finish;
    end

    initial begin
        #400_000_000;
        $display("TIMEOUT");
        $finish;
    end
endmodule


// A behavioural I2C slave that answers to 0x60, 0x61 (the DACs) and 0x48 (the ADC), logs what it is
// sent and, when read, returns 0x12 then 0x34.
module i2c_slave_model (inout wire sda, input wire scl);
    reg sda_drv = 1'b0;                                  // 1 = pull SDA low
    assign sda = sda_drv ? 1'b0 : 1'bz;

    localparam integer P_RECV = 0, P_ACK = 1, P_SEND = 2, P_MACK = 3, P_IDLE = 4;
    integer   phase = P_IDLE;
    integer   bitc = 0;
    reg [7:0] sh = 8'd0;
    reg       addr_phase = 1'b0, addressed = 1'b0, rw = 1'b0, master_acked = 1'b0;
    reg [7:0] addr_byte = 8'd0;
    reg [7:0] bytes [0:15];
    integer   nbytes = 0, nstart = 0, nstop = 0, nread_bytes = 0, n_nacked = 0, total_stops = 0;
    reg [7:0] rd_data [0:1];
    integer   rd_idx = 0;
    initial begin rd_data[0] = 8'h12; rd_data[1] = 8'h34; end

    task reset_log; begin
        nbytes = 0; nstart = 0; nstop = 0; nread_bytes = 0; n_nacked = 0; addr_byte = 8'd0; rd_idx = 0;
    end endtask

    always @(negedge sda) if (scl === 1'b1) begin        // START or repeated START
        nstart = nstart + 1;
        phase = P_RECV; bitc = 0; addr_phase = 1'b1; sda_drv = 1'b0;
    end
    always @(posedge sda) if (scl === 1'b1) begin        // STOP
        nstop = nstop + 1; total_stops = total_stops + 1;
        phase = P_IDLE; sda_drv = 1'b0;
    end

    always @(posedge scl) begin
        if (phase == P_RECV && bitc < 8) begin
            sh[7-bitc] = sda;
            bitc = bitc + 1;
        end else if (phase == P_MACK) begin
            master_acked = (sda === 1'b0);
        end
    end

    always @(negedge scl) begin
        case (phase)
        P_RECV: if (bitc == 8) begin
            if (addr_phase) begin
                addressed = (sh[7:1] == 7'h60) || (sh[7:1] == 7'h61) || (sh[7:1] == 7'h48);
                rw = sh[0];
                addr_byte = sh;
                addr_phase = 1'b0;
                rd_idx = 0;
            end else begin
                bytes[nbytes] = sh;
                nbytes = nbytes + 1;
            end
            sda_drv = addressed;                         // ACK
            if (!addressed) n_nacked = n_nacked + 1;
            phase = P_ACK;
        end
        P_ACK: begin
            sda_drv = 1'b0; bitc = 0;
            if (addressed && rw) begin
                phase = P_SEND;
                sda_drv = ~rd_data[rd_idx][7];
                bitc = 1;
            end else if (addressed) phase = P_RECV;
            else phase = P_IDLE;
        end
        P_SEND: begin
            if (bitc < 8) begin
                sda_drv = ~rd_data[rd_idx][7-bitc];
                bitc = bitc + 1;
            end else begin
                sda_drv = 1'b0;                          // release for the master's ACK / NACK
                nread_bytes = nread_bytes + 1;
                phase = P_MACK;
            end
        end
        P_MACK: begin
            rd_idx = rd_idx + 1;
            bitc = 0;
            if (master_acked && rd_idx < 2) begin
                phase = P_SEND;
                sda_drv = ~rd_data[rd_idx][7];
                bitc = 1;
            end else begin
                phase = P_IDLE;
            end
        end
        default: ;
        endcase
    end
endmodule
`endif
