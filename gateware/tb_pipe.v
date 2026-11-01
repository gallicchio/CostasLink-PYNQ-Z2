// tb_pipe: costaslink_core.v and the loopback model (tb_loopback.vh) driven through two named pipes, so the
// Python driver (driver/costaslink.py, through driver/sim_pipe.py's PipeBus) runs its experiments against
// the RTL (Response 15).  driver/test_sim.py starts it; by hand:
//
//     iverilog -g2005 -I. -o tb_pipe.vvp tb_pipe.v $(CORE)
//     vvp -N tb_pipe.vvp +cmd=path/cmd.fifo +rsp=path/rsp.fifo
//
// One command a line, one reply a line:
//   W aa dddddddd      write the register      -> OK
//   R aa               read it                 -> dddddddd
//   C n                run n clocks            -> OK
//   M knob value       set a model knob (mute, flip, glitch, noise_mask, noise_ppm, skew_q, lat, lat_slow) -> OK
//   T s n              TRIG_IN rises at sample s of the next clock, high n clocks, then low -> OK (after them)
//   Q                  end
// The bus is driven as axil_bridge.v drives it: the data taken four clocks after bus_re.
`timescale 1ns/1ps
module tb_pipe;
`include "regmap.vh"
    parameter integer SER = 8;
    localparam integer LAT = 13, LAT_SLOW = 40;

    reg clk = 1'b0;
    always #5 clk = ~clk;                  // 100 MHz
    reg rst = 1'b1;

    reg  [7:0]  bus_addr = 8'd0;
    reg  [31:0] bus_wdata = 32'd0;
    reg         bus_we = 1'b0, bus_re = 1'b0;
    wire [31:0] bus_rdata;

    wire tx_i1, tx_i0, tx_q1, tx_q1_hiz, tx_q0, spi_sclk, spi_sdata, le_pll_tx, le_pll_rx, le_dsa;
    wire loop_hold, loop_sel, tx_dis, trig_a, trig_b, tr_a, scl_o, sda_o;

    integer lat = LAT, lat_slow = LAT_SLOW;
`include "tb_loopback.vh"

    costaslink_core #(.CLK_HZ(100_000_000), .SER(SER), .CAP_AW(10), .BOARD(0), .ID_INTERVAL_S(600),
                      .EARLY(1), .FAST_PATH(1), .TXFB(1), .RP_REG(0)) dut (
        .clk(clk), .rst(rst),
        .bus_addr(bus_addr), .bus_wdata(bus_wdata), .bus_we(bus_we), .bus_re(bus_re), .bus_rdata(bus_rdata),
        .fs(fs), .fs_lane(fs_early), .cmp_async(cmp_async), .fs_tx(fs_tx), .cmp_i_s(slow[0]), .cmp_qp_s(slow[1]), .cmp_qn_s(slow[2]), .mux_tx(1'b1), .mux_rx(1'b1),
        .i2c_scl_i(scl_o), .i2c_sda_i(sda_o), .i2c_scl_o(scl_o), .i2c_sda_o(sda_o),
        .tx_i1(tx_i1), .tx_i0(tx_i0), .tx_q1(tx_q1), .tx_q1_hiz(tx_q1_hiz), .tx_q0(tx_q0),
        .spi_sclk(spi_sclk), .spi_sdata(spi_sdata), .le_pll_tx(le_pll_tx), .le_pll_rx(le_pll_rx), .le_dsa(le_dsa),
        .loop_hold(loop_hold), .loop_sel(loop_sel), .tx_dis(tx_dis), .trig_a(trig_a), .trig_b(trig_b), .tr_a(tr_a));

    task wr;
        input [7:0] a;
        input [31:0] d;
        begin
            @(negedge clk); bus_addr = a; bus_wdata = d; bus_we = 1'b1;
            @(negedge clk); bus_we = 1'b0;
        end
    endtask
    task rd;
        input  [7:0] a;
        output [31:0] d;
        begin
            @(negedge clk); bus_addr = a; bus_re = 1'b1;
            @(negedge clk); bus_re = 1'b0;
            @(negedge clk);
            @(negedge clk); d = bus_rdata;
        end
    endtask

    integer    cfd, rfd, r, n, ii, ti, s0, hold_n;   // (the model has k and s)
    reg [8*16-1:0] cmd, knob;
    reg [31:0] a, d, v;
    reg [8*256-1:0] cmd_path, rsp_path;

    initial begin
        for (ii = 0; ii < 256; ii = ii + 1) hist_pt[ii] = 4'b0111;
        for (ii = 0; ii < SER; ii = ii + 1) trig_samp[ii] = 1'b0;
        fs = {SER{6'b001001}}; fs_early = {SER{6'b001001}}; fs_tx = {SER{4'b0111}}; cmp_async = 5'b01001;
        slow = 3'b001;
        if (!$value$plusargs("cmd=%s", cmd_path) || !$value$plusargs("rsp=%s", rsp_path)) begin
            $display("tb_pipe: +cmd=<fifo> +rsp=<fifo>"); $finish;
        end
        repeat (5) @(posedge clk);
        rst = 1'b0;
        repeat (5) @(posedge clk);
        @(negedge clk);
        cfd = $fopen(cmd_path, "r");
        rfd = $fopen(rsp_path, "w");
        forever begin
            cmd = 0;
            r = $fscanf(cfd, "%s", cmd);
            if (r != 1) $finish;
            case (cmd[7:0])
            "W": begin
                r = $fscanf(cfd, "%h %h", a, d);
                wr(a[7:0], d);
                $fwrite(rfd, "OK\n");
            end
            "R": begin
                r = $fscanf(cfd, "%h", a);
                rd(a[7:0], v);
                $fwrite(rfd, "%08x\n", v);
            end
            "C": begin                              // to a falling edge: every rising edge's processes are done
                r = $fscanf(cfd, "%d", n);
                repeat (n) @(negedge clk);
                $fwrite(rfd, "OK\n");
            end
            "M": begin
                knob = 0;
                r = $fscanf(cfd, "%s %d", knob, n);
                case (knob)
                "mute":       mute = n[0];
                "flip":       flip_next = n[0];
                "glitch":     glitch = n[0];
                "noise_mask": noise_mask = n[4:0];
                "noise_ppm":  noise_ppm = n;
                "skew_q":     skew_q = n;
                "lat":        lat = n;
                "lat_slow":   lat_slow = n;
                default:      $display("tb_pipe: no knob %0s", knob);
                endcase
                $fwrite(rfd, "OK\n");
            end
            "T": begin                              // all from here: the model reads trig_samp at the rising edges
                r = $fscanf(cfd, "%d %d", s0, n);
                @(negedge clk);
                for (ii = 0; ii < SER; ii = ii + 1) trig_samp[ii] = (ii >= s0);
                for (hold_n = 1; hold_n < n; hold_n = hold_n + 1) begin
                    @(negedge clk);
                    for (ii = 0; ii < SER; ii = ii + 1) trig_samp[ii] = 1'b1;
                end
                @(negedge clk);
                for (ii = 0; ii < SER; ii = ii + 1) trig_samp[ii] = 1'b0;
                $fwrite(rfd, "OK\n");
            end
            "Q": $finish;
            default: $fwrite(rfd, "?\n");
            endcase
            $fflush(rfd);
        end
    end
endmodule
