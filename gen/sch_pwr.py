"""The power and FPGA sheet (A2): the two 5 V inputs (USB-C and the PYNQ's header) each through a
fuse and a P-FET ideal diode, the ferrite into +5V_RF, the five 3.3 V regulators, the rail LEDs;
the 2x20 socket onto the PYNQ-Z2's Raspberry Pi header with every FPGA signal leaving to the RX
or TX sheet; the spare header; mounting holes.  References 301-399.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import sch_util as U
from sch_util import (G, part, hpart, vpart, gnd, flag, W, J, label, note, title, box, nref, down, up, series, tp, sig)
import sch_blocks as B
from sch_blocks import stub, L
import pins as PINS
import levels as LV


def pfet(ref, x, y, pull=True):
    """AO3401A as an ideal diode lying on the rail at height y: drain on the left (the input),
    source on the right (the board), gate below through 100 k to ground (pull=True).  Returns
    (drain, source, gate-node) points; the gate node is 7.62 below the channel."""
    q = part("AO3401A", ref, x, y + 2.54, rot=90)       # rotated, the channel sits 2.54 above the anchor
    g, s, d = q.pin("1"), q.pin("2"), q.pin("3")
    gn = (g[0], g[1] + 5.08)
    W(g, gn)
    if pull:
        down("R 100k", gn[0], gn[1], text="right")
    return d, s, gn


def usb_gate(gn):
    """The USB ideal diode's gate: 100 k up to +5V_HDR (so the FET is OFF while the header
    supplies the board: +5V_IN never reaches the USB-C's VBUS), and a 2N7002 that pulls the gate
    to ground whenever VBUS is present (so USB wins over the header, whose own FET VBUS turns
    off).  Response 9's review: with the gate simply grounded, header power ran back onto VBUS,
    lifted the header FET's gate, and the board sat on a body diode at about 4.1 V."""
    J(gn[0], gn[1])
    ra, rb = series("R 100k", gn[0] - 10.16, gn[1])
    W(rb, gn)
    xf = ra[0] - 2.54
    W(ra, (xf, gn[1])); W((xf, gn[1]), (xf, gn[1] - 5.08)); flag("+5V_HDR", xf, gn[1] - 5.08)
    qn = part("2N7002", "Q303", gn[0], gn[1] + 15.24, rot=0)
    dn, sn, gg = qn.pin("3"), qn.pin("2"), qn.pin("1")
    W(gn, dn)
    W(sn, (sn[0], sn[1] + G)); gnd(sn[0], sn[1] + G)
    xg = gg[0] - 7.62
    W(gg, (xg, gg[1])); J(xg, gg[1])
    down("R 100k", xg, gg[1], text="left")
    ra2, rb2 = series("R 10k", xg - 10.16, gg[1])
    W(rb2, (xg, gg[1]))
    W((ra2[0] - 5.08, gg[1]), ra2)
    label(ra2[0] - 5.08, gg[1], "VBUS", size=1.0)


def ldo(ref, key, x, y, rail, series_r=None, note_text=""):
    """A SOT-23-5 LDO at (x, y): input (optionally through a resistor) with its capacitor, EN tied
    to the input, the output with 2.2 uF and 10 uF to the rail's flag."""
    u = part(key, ref, x, y)
    vin, vout, en, g = u.pin("1"), u.pin("5"), u.pin("3"), u.pin("2")
    U.S.nc(*u.pin("4"))
    yv = vin[1]
    # EN to the input node
    xe = vin[0] - 5.08
    W(en, (xe, en[1]), (xe, yv))
    J(xe, yv)
    W((xe, yv), vin)
    xin = xe - 12.7
    if series_r:
        ra, rb = series(series_r, xe - 7.62, yv)
        W(rb, (xe, yv))
        U.pwr_flag(xe - 2.54, yv); J(xe - 2.54, yv)               # ERC: a power pin fed through a resistor
        W((xin - 5.08, yv), ra)
        xin = xin - 5.08
    else:
        W((xin, yv), (xe, yv))
    W((xin, yv), (xin, yv - 5.08)); flag("+5V_IN", xin, yv - 5.08)
    J(xin, yv)
    down("C 10uF" if series_r else "C 2.2uF", xin, yv, text="left", drop=5.08)
    W(g, (g[0], g[1] + G)); gnd(g[0], g[1] + G)
    xo = vout[0] + 7.62
    W(vout, (xo + 10.16, vout[1]))
    J(xo, vout[1]); down("C 2.2uF", xo, vout[1], text="right")
    J(xo + 10.16, vout[1]); down("C 10uF", xo + 10.16, vout[1], text="right")
    W((xo + 10.16, vout[1]), (xo + 10.16, vout[1] - 5.08)); flag(rail, xo + 10.16, vout[1] - 5.08)
    sig(vout[0] + 30, vout[1] - 6, LV.txt(rail), cols=22)
    if note_text:
        note(x - 24, y + 14, note_text, cols=36)
    return u


def build(S):
    U.begin(S, ref_base=300)
    title(20, 18, "Power and the FPGA: 5 V in, five quiet 3.3 V rails, the PYNQ-Z2's Raspberry Pi header")

    # ---- inputs ---------------------------------------------------------------------------
    y = 55.88
    usb = part("USBC", "J301", 45.72, y + 15.24)
    vb = usb.pin("A4")                       # the four VBUS pins are one point on the symbol
    W(vb, (vb[0] + 5.08, vb[1]))
    W((vb[0] + 5.08, vb[1]), (vb[0] + 5.08, y), (vb[0] + 10.16, y))
    label(vb[0] + 10.16, y, "VBUS", size=1.0)
    U.pwr_flag(vb[0] + 7.62, y); J(vb[0] + 7.62, y)
    for n, dx in (("A5", 12.7), ("B5", 5.08)):      # CC: 5.1 k to ground asks a USB-C source for 5 V at up to 3 A
        p = usb.pin(n)                                 # (the upper pin's resistor farther out, clear of the lower line)
        W(p, (p[0] + dx, p[1]))
        down("R 5.1k", p[0] + dx, p[1], text="right")
    gp = usb.pin("A1")
    W(gp, (gp[0], gp[1] + G)); gnd(gp[0], gp[1] + G)
    sh = usb.pin("SH")
    W(sh, (sh[0], sh[1] + G)); gnd(sh[0], sh[1] + G)
    for n in ("A6", "A7", "B6", "B7", "A8", "B8"):
        U.S.nc(*usb.pin(n))
    note(14, y + 42, "USB-C: 5 V only (CC 5.1 k each: a C-C cable gets 5 V; an A-C cable from any 5 V supply works).  1.3 A at most.  "
         "HRO TYPE-C-31-M-12: this part's CPL datum is known from three boards.", cols=40)
    # fuse, FET, TVS, bulk
    x0 = vb[0] + 10.16
    fa, fb = series("PTC2A", x0 + 7.62, y, ref="F301")
    W((x0, y), fa)
    d, s, gn = pfet("Q301", fb[0] + 12.7, y, pull=False)
    W(fb, d)
    usb_gate(gn)
    xin = s[0] + 10.16
    W(s, (xin, y))
    note(fb[0] - 10, y - 22, "2 A PTC, then a P-FET as an ideal diode (60 mOhm: 80 mV at 1.3 A; a Schottky's 350 mV would put the ADL53xx under their 4.75 V).", cols=40)
    # header 5 V path, below
    yh = y + 66.04
    xh0 = 20.32
    flag("+5V_HDR", xh0, yh - 5.08); W((xh0, yh - 5.08), (xh0, yh)); W((xh0, yh), (xh0 + 7.62, yh))
    U.pwr_flag(xh0 + 2.54, yh); J(xh0 + 2.54, yh)
    jp = part("HDR1x2", "JP301", xh0 + 7.62, yh - 5.08, rot=90, value="HDR 5V", text="hide")
    j1, j2 = jp.pin("1"), jp.pin("2")          # both on the line, 2.54 apart: the jumper bridges them
    fa2, fb2 = series("PTC2A", j2[0] + 12.7, yh, ref="F302")
    W(j2, fa2)
    d2, s2, gn2 = pfet("Q302", fb2[0] + 12.7, yh)
    W(fb2, d2)
    W(s2, (xin, yh), (xin, y))
    J(xin, y)
    # Q302's gate is lifted by VBUS through 1 k (against its 100 k to ground: 0.99 x VBUS, so its Vgs is
    # -0.05 V, well above the AO3401A's -0.5 V minimum threshold; 10 k left -0.45 V, the review's item 6)
    ra, rb = series("R 1k", gn2[0] + 15.24, gn2[1])
    W(gn2, ra); J(gn2[0], gn2[1])
    W(rb, (rb[0] + 5.08, gn2[1]), (rb[0] + 5.08, y + 30.48), (vb[0] + 5.08, y + 30.48)) if False else None
    W(rb, (rb[0] + 7.62, gn2[1]))
    label(rb[0] + 7.62, gn2[1], "VBUS", size=1.0)
    note(14, yh + 24, "JP301 HDR 5V: fit it to power the board from the PYNQ-Z2's 5 V (pins 2/4) when the PYNQ runs on its barrel supply.  "
         "Q302 turns off whenever USB-C 5 V is present (VBUS lifts its gate), and Q301 is off unless VBUS is present (Q303 pulls its gate down; +5V_HDR holds it up), so USB wins when both are plugged and neither supply ever feeds the other.", cols=34)
    # TVS, bulk, LED, the +5V_IN flag
    W((xin, y), (xin + 38.1, y))
    J(xin + 7.62, y); down("C 22uF", xin + 7.62, y, text="right")
    J(xin + 17.78, y); down("C 22uF", xin + 17.78, y, text="right")
    J(xin + 27.94, y); down("TVS5V", xin + 27.94, y, text="right", ref="D303")
    W((xin + 38.1, y), (xin + 43.18, y))
    W((xin + 43.18, y), (xin + 43.18, y - 5.08)); flag("+5V_IN", xin + 43.18, y - 5.08)
    # ERC: these rails are made by passive parts (a FET, a bead), so each carries a PWR_FLAG
    U.pwr_flag(xin + 2.54, y); J(xin + 2.54, y)
    J(xin + 43.18, y)
    r, b = down("R 1k", xin + 43.18, y, net=None, text="right")
    dled = part("LED_G", "D301", b[0], b[1] + 3.81 + G, rot=90, value="5V", text="right", fsize=1.0)
    W(b, dled.pin("2"))
    k = dled.pin("1"); W(k, (k[0], k[1] + G)); gnd(k[0], k[1] + G)
    # ferrite to +5V_RF
    yrf = yh + 45.72
    flag("+5V_IN", xh0, yrf - 5.08); W((xh0, yrf - 5.08), (xh0, yrf))
    fa3, fb3 = series("FB_2A", xh0 + 12.7, yrf, ref="FB301")
    W((xh0, yrf), fa3)
    W(fb3, (fb3[0] + 22.86, yrf))
    J(fb3[0] + 7.62, yrf); down("C 22uF", fb3[0] + 7.62, yrf, text="right")
    J(fb3[0] + 17.78, yrf); down("C 10uF", fb3[0] + 17.78, yrf, text="right")
    W((fb3[0] + 22.86, yrf), (fb3[0] + 27.94, yrf))
    W((fb3[0] + 27.94, yrf), (fb3[0] + 27.94, yrf - 5.08)); flag("+5V_RF", fb3[0] + 27.94, yrf - 5.08)
    sig(fb3[0] + 36, yrf - 10, LV.txt("5V_RF"), cols=30)
    U.pwr_flag(fb3[0] + 2.54, yrf); J(fb3[0] + 2.54, yrf)
    note(14, yrf + 18, "+5V_RF: the ADL5380 (245 mA), the ADL5375 (203 mA) and both ADL5611 (124 mA each) through a 2 A bead.  "
         "They need 4.75 V: 80 mV in the FET and 100 mV in the PTC leave 4.8 V from a 5.0 V source.", cols=34)

    # ---- the five regulators -----------------------------------------------------------
    xl = 205.74
    ldo("U301", "TPS7A2033", xl, y, "+3V3_PLL_TX", series_r="R 2.2R 1206",
        note_text="TPS7A2033: 300 mA, 10 uVrms.  2.2 ohm ahead of it shares the heat: 0.25 W in the LDO at 200 mA (+47 C).")
    ldo("U302", "TPS7A2033", xl, y + 40.64, "+3V3_PLL_RX", series_r="R 2.2R 1206")
    ldo("U303", "TPS7A2033", xl, y + 81.28, "+3V3_ANA", note_text="+3V3_ANA: the two FDAs, the loop op amp, the LNA, the DSA, the TX bias reference: 40 mA.")
    ldo("U304", "TPS7A2033", xl, y + 121.92, "+3V3_DIG", note_text="+3V3_DIG: comparators, switches, DAC, ADC, buffers: 30 mA.")
    ldo("U305", "LP5907", xl, y + 162.56, "+3V3_OSC", note_text="LP5907: 6.5 uVrms for the VCXO and the TCXO (supply noise on an oscillator is FM).")
    # 3V3 LED
    xled = xl + 71.12
    yl = y + 121.92 - 2.54
    flag("+3V3_DIG", xled, yl - 5.08); W((xled, yl - 5.08), (xled, yl))
    r, b = down("R 1k", xled, yl, net=None, text="right")
    dled2 = part("LED_G", "D302", b[0], b[1] + 3.81 + G, rot=90, value="3V3", text="right", fsize=1.0)
    W(b, dled2.pin("2"))
    k = dled2.pin("1"); W(k, (k[0], k[1] + G)); gnd(k[0], k[1] + G)
    # test points per rail
    ytp = y + 162.56 + 38.1
    for i, rail in enumerate(("+5V_IN", "+5V_RF", "+3V3_PLL_TX", "+3V3_PLL_RX", "+3V3_ANA", "+3V3_DIG", "+3V3_OSC")):
        x = xl - 20.32 + 15.24 * i
        flag(rail, x, ytp - 5.08); W((x, ytp - 5.08), (x, ytp))
        tp(x, ytp, rail)
    xg = xl - 20.32 + 15.24 * 7
    tp(xg, ytp, "GND"); W((xg, ytp), (xg, ytp + G)); gnd(xg, ytp + G)
    W((xg, ytp), (xg + 7.62, ytp)); U.pwr_flag(xg + 7.62, ytp)       # ERC: the ground net's flag
    note(xl - 20, ytp + 10, "Test pads: one per rail, and a ground for the probe's clip.", cols=30)
    sig(xl + 20, ytp + 10, LV.txt("5V_IN"), cols=60)

    # ---- the PYNQ header -----------------------------------------------------------------
    xh, yh0 = 436.88, 101.6
    hdr = part("RPI_SOCKET", "J302", xh, yh0)
    title(xh - 70, yh0 - 70, "PYNQ-Z2 Raspberry Pi header (2x20 socket on the underside)")
    note(xh - 70, yh0 - 64, "28 Zynq pins, LVCMOS33 through the PYNQ's own 200 ohm series resistors (gen/pins.py is the one table: "
         "this symbol, the silkscreen and gateware/pynq_z2.xdc come from it).  Odd pins are the PYNQ's outer row; pin 1 is at the right-hand end.", cols=56)
    for n, (net, zynq, site, what) in PINS.HEADER.items():
        if net == "GND":
            p = hdr.pin(str(n)); W(p, (p[0], p[1] + G)); gnd(p[0], p[1] + G)
        elif net == "+5V_HDR":
            p = hdr.pin(str(n))                            # pins 2 and 4 are top pins side by side: one flag
            W(p, (p[0], p[1] - 5.08))
            if n == 2:
                flag("+5V_HDR", p[0], p[1] - 5.08)
            else:
                p2 = hdr.pin("2")
                W((p[0], p[1] - 5.08), (p2[0], p2[1] - 5.08)); J(p2[0], p2[1] - 5.08)
        elif net == "3V3_HOST":
            U.S.nc(*hdr.pin(str(n)))
        else:
            left = (n % 2 == 1)
            e = stub(hdr, str(n), dx=-12.7 if left else 12.7)
            if net.startswith("SPARE"):
                label(e[0], e[1], net, size=1.0, justify="right bottom" if left else "left bottom")
                continue
            shape = "output" if net in PINS.OUTPUTS else ("input" if net in PINS.INPUTS else "bidirectional")
            U.S.hlabel(e[0], e[1], net, shape=shape, rot=0 if not left else 180)
    # J303 (the switch controls for an external module) moved to the antenna sheet in Response 14, with TR_B
    # I2C pull-ups for a host without them (the Icepi Zero): DNP; the PYNQ-Z2 has 2k2 on its header
    xi = xh + 116.84
    yi = yh0 + 55.88
    flag("+3V3_DIG", xi + 3.81, yi - 15.24)
    W((xi + 3.81, yi - 15.24), (xi + 3.81, yi - 12.7)); W((xi, yi - 12.7), (xi + 7.62, yi - 12.7)); J(xi + 3.81, yi - 12.7)
    for k, net in enumerate(("I2C_SDA", "I2C_SCL")):
        xk = xi + 7.62 * k
        r = part("R 4.7k", nref("R"), xk, yi - 12.7 + 3.81 + G, rot=0, dnp=True, value="DNP 4.7k", text="right" if k else "left", fsize=1.0)
        top_, bot = sorted((r.pin("1"), r.pin("2")), key=lambda p: p[1])
        W((xk, yi - 12.7), top_)
        W(bot, (bot[0], bot[1] + G)); label(bot[0], bot[1] + G, net, size=1.0, justify="left top")
    note(xi - 6, yi + 6, "I2C pull-ups, DNP: fit 4.7 k for the Icepi Zero (no pull-ups there); the PYNQ-Z2 has 2k2.", cols=24)
    # the lines that must rest low while no gateware drives the header (Response 15, REVA_CHANGES.md 3): the
    # synthesizers' and the DSA's latch enables, so a floating line cannot load a word into them, and TRIG A /
    # TRIG B's buffer inputs, so their jacks stay quiet.  Explicit references: nothing after them renumbers.
    xd, yd = xh + 3.81, yh0 + 50.8
    for k, (net, ref) in enumerate((("LE_PLL_TX", "R314"), ("LE_PLL_RX", "R315"), ("LE_DSA", "R316"),
                                    ("TRIG_A", "R317"), ("TRIG_B", "R318"))):
        xk = xd + 15.24 * k
        r = part("R 100k", ref, xk, yd + 3.81 + G, rot=0, text="right", fsize=1.0)
        top_, bot = sorted((r.pin("1"), r.pin("2")), key=lambda p: p[1])
        W(top_, (top_[0], top_[1] - G)); label(top_[0], top_[1] - G, net, size=1.0, justify="left bottom")
        W(bot, (bot[0], bot[1] + G)); gnd(bot[0], bot[1] + G)
    note(xd - 4, yd + 22, "100 k to ground: the latch enables and the trigger buffers' inputs rest low while no gateware "
         "drives the header (the host off, unconfigured, or loading another overlay).  TX_EN's own 1 k is on sheet 4.", cols=60)
    # holes
    for i in range(3):
        part("HOLE", "H30%d" % (i + 1), xh + 80.01 + 12.7 * i, yh0 + 109.22, value="M3", text="right", fsize=1.0)
    part("HOLE_SLOT", "H304", xh + 80.01 + 12.7 * 3, yh0 + 109.22, value="M3 slot", text="right", fsize=1.0)
    note(xh + 70, yh0 + 118, "Three M3 standoffs to the desk (H301-H303) and one slot (H304) onto the PYNQ-Z2's top-right mounting hole, "
         "where the two boards register through the 2x20 header.", cols=28)
    return S
