#!/usr/bin/env python3
"""The constraint files for this board, from gen/pins.py (one source of truth).

    python3 gateware/gen_xdc.py      writes gateware/pynq_z2.xdc, gateware/icepi_zero.lpf and
                                     gateware/pynq/costaslink_pynq.xdc (the block design's: the pins only)

PYNQ-Z2 (Vivado): every header signal is LVCMOS33 (the PYNQ's banks 13, 34 and 35 are at 3.3 V);
outputs get the slowest slew and the lowest drive that the 200 ohm header resistors allow
(CLAUDE_PCB.md section 13), except the TX ladder and trigger pins, which set an edge and get FAST.

Icepi Zero (nextpnr-ecp5): the same signals on the ECP5 balls of gen/pins.py ICEPI, LVCMOS33, and
there are no series resistors, so even the FAST pins use the 8 mA drive.  The Icepi's own 50 MHz
oscillator is on ball M1.  The port names are the net names in lower case on both boards, so one
Verilog top serves both; only the clocking primitives differ (PLAN.md section 8).  Both files end
with the clock (sysclk) and the first firmware's command UART (uart_rx / uart_tx: the Icepi's FTDI;
a dongle on the PYNQ's Arduino header until the register file is on AXI-Lite).
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gen"))
import pins as PINS

FAST = {"TX_I1", "TX_I0", "TX_Q1", "TX_Q0", "TRIG_A", "TRIG_B", "TR_A", "TR_B"}


def xdc(pins_only=False):
    L = ["# CostasLink-PYNQ-Z2 on the PYNQ-Z2's Raspberry Pi header.  Made by gateware/gen_xdc.py from gen/pins.py.",
         "# Header pin -> Zynq package pin from the GPSDO-PYNQ-Z2 board's verified table (TUL schematic sheet 4).",
         "# Clock-capable header pins on this board: %s (18 and 26 are also clock-capable on the Icepi Zero)." % sorted(PINS.PYNQ_CLK),
         ""]
    for hp in sorted(PINS.HEADER):
        net, zynq, site, what = PINS.HEADER[hp]
        if not zynq:
            continue
        port = net.lower()
        L.append("# header %2d  %-26s %s" % (hp, site, what))
        L.append("set_property PACKAGE_PIN %s [get_ports {%s}]" % (zynq, port))
        L.append("set_property IOSTANDARD LVCMOS33 [get_ports {%s}]" % port)
        if net in PINS.OUTPUTS or net in PINS.SPARES:
            L.append("set_property DRIVE %d [get_ports {%s}]" % (8 if net in FAST else 4, port))
            L.append("set_property SLEW %s [get_ports {%s}]" % ("FAST" if net in FAST else "SLOW", port))
        if net in PINS.BIDIR:
            L.append("set_property PULLUP true [get_ports {%s}]" % port)
        L.append("")
    if pins_only:
        # the block design's overlay (pynq/build.tcl): the fabric runs on the PS's FCLK0 through the clock wizard,
        # and the register file is on AXI-Lite, so no sysclk and no UART
        L += ["# the overlay's outputs need no timing to the board: the comparators are asynchronous to every clock here,",
              "# and the slow outputs (SPI, I2C, the control pins) change at kHz rates",
              "set_false_path -to [get_ports -filter {DIRECTION == OUT || DIRECTION == INOUT}]",
              "set_false_path -from [get_ports -filter {DIRECTION == IN || DIRECTION == INOUT}]", ""]
        return "\n".join(L) + "\n"
    L += ["# the PYNQ-Z2's 125 MHz clock (Ethernet PHY), as the stock constraints have it",
          "set_property PACKAGE_PIN H16 [get_ports {sysclk}]",
          "set_property IOSTANDARD LVCMOS33 [get_ports {sysclk}]",
          "create_clock -period 8.000 -name sysclk [get_ports {sysclk}]", "",
          "# the command UART of the first firmware (gateware/uart_cmd.v).  The PYNQ-Z2's own USB UART belongs to the PS",
          "# (MIO), not the PL, so a USB-UART dongle goes on the Arduino header's D0 (RX) / D1 (TX): T14 / U12 = ar[0] / ar[1]",
          "# in TUL's PYNQ-Z2 master XDC (from memory, not a measured table: verify against the schematic before building).",
          "# The register file moves to AXI-Lite on the PYNQ later (README.md), and these two lines go.",
          "set_property PACKAGE_PIN T14 [get_ports {uart_rx}]",
          "set_property IOSTANDARD LVCMOS33 [get_ports {uart_rx}]",
          "set_property PULLUP true [get_ports {uart_rx}]",
          "set_property PACKAGE_PIN U12 [get_ports {uart_tx}]",
          "set_property IOSTANDARD LVCMOS33 [get_ports {uart_tx}]",
          "set_property DRIVE 4 [get_ports {uart_tx}]",
          "set_property SLEW SLOW [get_ports {uart_tx}]", ""]
    return "\n".join(L) + "\n"


def lpf():
    L = ["# CostasLink-PYNQ-Z2 on the Icepi Zero's Raspberry Pi header (ECP5 LFE5U-25F-6BG256C).",
         "# Made by gateware/gen_xdc.py from gen/pins.py: header pin -> ball from cheyao/icepi-zero",
         "# gateware/icepi-zero.lpf, functions from Lattice FPGA-SC-02033 (ECP5U-25 pinout).",
         "# Clock-capable header pins here: %s (18 and 26 are also clock-capable on the PYNQ-Z2)." % sorted(PINS.ICEPI_CLK),
         "# No series resistors on the Icepi: the balls meet the header directly.",
         "",
         "# the configuration options of cheyao/icepi-zero gateware/icepi-zero.lpf (3.3 V I/O, compressed bitstream, master SPI boot)",
         "SYSCONFIG CONFIG_IOVOLTAGE=3.3 COMPRESS_CONFIG=ON MCCLK_FREQ=62 MASTER_SPI_PORT=ENABLE SLAVE_SPI_PORT=DISABLE SLAVE_PARALLEL_PORT=DISABLE;",
         "",
         "BLOCK RESETPATHS;", "BLOCK ASYNCPATHS;", "",
         "# the Icepi's 50 MHz oscillator",
         'LOCATE COMP "sysclk" SITE "%s";' % PINS.ICEPI_CLK_BALL,
         'IOBUF PORT "sysclk" IO_TYPE=LVCMOS33;',
         'FREQUENCY PORT "sysclk" 50 MHZ;', ""]
    for hp in sorted(PINS.ICEPI):
        ball, pad, dual = PINS.ICEPI[hp]
        net = PINS.HEADER[hp][0]
        port = net.lower()
        L.append("# header %2d  %-4s %-6s %-11s %s" % (hp, ball, pad, dual, PINS.HEADER[hp][3]))
        L.append('LOCATE COMP "%s" SITE "%s";' % (port, ball))
        attrs = ["IO_TYPE=LVCMOS33"]
        if net in PINS.OUTPUTS or net in PINS.SPARES:
            attrs += ["DRIVE=%d" % (8 if net in FAST else 4), "SLEWRATE=%s" % ("FAST" if net in FAST else "SLOW")]
        if net in PINS.BIDIR:
            attrs += ["PULLMODE=UP"]
        if net in PINS.INPUTS:
            attrs += ["PULLMODE=NONE"]
        L.append('IOBUF PORT "%s" %s;' % (port, " ".join(attrs)))
        L.append("")
    L += ["# the command UART of the first firmware (gateware/uart_cmd.v) on the Icepi's FTDI: cheyao/icepi-zero",
          "# gateware/icepi-zero.lpf has usb_rx on K16 (the FTDI transmits, the FPGA receives) and usb_tx on K15.",
          'LOCATE COMP "uart_rx" SITE "K16";',
          'IOBUF PORT "uart_rx" IO_TYPE=LVCMOS33 PULLMODE=UP;',
          'LOCATE COMP "uart_tx" SITE "K15";',
          'IOBUF PORT "uart_tx" IO_TYPE=LVCMOS33 PULLMODE=UP DRIVE=4;', ""]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    PINS.check()
    os.makedirs(os.path.join(HERE, "pynq"), exist_ok=True)
    for name, text in (("pynq_z2.xdc", xdc()), ("icepi_zero.lpf", lpf()), (os.path.join("pynq", "costaslink_pynq.xdc"), xdc(True))):
        out = os.path.join(HERE, name)
        open(out, "w").write(text)
        print("wrote", os.path.relpath(out, os.path.dirname(HERE)))
