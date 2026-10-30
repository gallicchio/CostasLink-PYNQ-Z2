#!/usr/bin/env python3
"""pynq_fclk.py: runs ON the PYNQ, as root (sudo python3 pynq_fclk.py ...).  The Zynq's FCLK0, which the overlay's
clock wizard multiplies by 8 (VCO 600-1200 MHz, so FCLK0 75-150 MHz) and divides back to the fabric's clock (x1) and
the ISERDES's (x4): the board's whole clock, the sampler's 8 samples a clock included.

    pynq_fclk.py                 read: the IO PLL, FPGA0_CLK_CTRL's divisors, the frequency
    pynq_fclk.py D0 D1 [reset]   set FCLK0 = IO PLL / (D0 x D1) (1000 MHz: 13 -> 76.9, 12 -> 83.3, 11 -> 90.9, 10 -> 100,
                                 9 -> 111.1); with 'reset', pulse FCLK_RESET0 (FPGA_RST_CTRL bit 0) after it, which
                                 resets the clock wizard and the whole fabric (the MMCM relocks at the new input)

The SLCR is unlocked (0xF8000008 = 0xDF0D) for the writes and locked again (0xF8000004 = 0x767B).  Nothing on the AXI
bus may be in flight while the fabric's clock changes: stop every client first.
"""
import mmap
import os
import struct
import sys
import time

SLCR = 0xF8000000
fd = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
m = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=SLCR)


def rd(o):
    return struct.unpack("<I", m[o:o + 4])[0]


def wr(o, v):
    m[o:o + 4] = struct.pack("<I", v)


def show(tag):
    fdiv = (rd(0x108) >> 12) & 0x7F                         # IO_PLL_CTRL [18:12], from the 50 MHz PS clock
    v = rd(0x170)                                          # FPGA0_CLK_CTRL: [25:20] DIVISOR1, [13:8] DIVISOR0
    d0, d1 = (v >> 8) & 0x3F, (v >> 20) & 0x3F
    f = 50.0 * fdiv / (d0 * d1)
    print("%s: IO PLL %d MHz, FPGA0_CLK_CTRL 0x%08x (d0 %d, d1 %d): FCLK0 %.3f MHz; FPGA_RST_CTRL 0x%x"
          % (tag, 50 * fdiv, v, d0, d1, f, rd(0x240)), flush=True)
    return f


show("before")
if len(sys.argv) >= 3:
    n0, n1 = int(sys.argv[1]), int(sys.argv[2])
    assert 1 <= n0 <= 63 and 1 <= n1 <= 63
    v = rd(0x170)
    nv = (v & ~((0x3F << 20) | (0x3F << 8))) | (n1 << 20) | (n0 << 8)
    wr(0x008, 0xDF0D)
    wr(0x170, nv)
    if len(sys.argv) > 3 and sys.argv[3] == "reset":
        time.sleep(0.01)
        wr(0x240, rd(0x240) | 1)
        time.sleep(0.01)
        wr(0x240, rd(0x240) & ~1)
    wr(0x004, 0x767B)
    time.sleep(0.05)
    show("after")
