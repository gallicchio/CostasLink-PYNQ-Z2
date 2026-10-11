"""The transmitter sheet (A2): four FPGA pins into two 2-bit resistor ladders, the ADL5375
modulator, the ADL5611 gain block, the pi pad, the coupler and the TX SMA; the TX synthesizer on
its TCXO (or an external reference); the trigger buffers.  References 201-299.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import sch_util as U
from sch_util import (G, part, hpart, vpart, gnd, flag, W, J, label, note, title, box, nref, down, up, series, tp, sig)
import sch_blocks as B
from sch_blocks import stub, L
import levels as LV


def ladder(S, x, y, bits, ref_name, name):
    """A 2-bit resistor DAC centred on (x, y): two 2.2k from the FPGA pins (rows y -/+ 7.62) and
    300 ohm from the DAC reference (row y + 17.78) into the node at (x, y); returns the node."""
    for bit, dy in zip(bits, (-7.62, 7.62)):
        yb = y + dy
        S.hlabel(x - 33.02, yb, bit, shape="input", rot=180)
        ra, rb = series("R 2.2k", x - 20.32, yb)
        W((x - 33.02, yb), ra)
        W(rb, (x, yb))
    W((x, y - 7.62), (x, y + 7.62))
    J(x, y)
    yr = y + 17.78
    W((x, y + 7.62), (x, yr))
    J(x, y + 7.62)
    ra, rb = series("R 300R", x - 10.16, yr)
    W(rb, (x, yr))
    W((x - 33.02, yr), ra)
    S.hlabel(x - 33.02, yr, ref_name, shape="input", rot=180)
    J(x - 25.4, yr)
    down("C 1uF", x - 25.4, yr, text="right")
    label(x + 1.27, y, name, size=1.0)
    return (x, y)


def build(S):
    U.begin(S, ref_base=200)
    title(20, 18, "Transmitter: four FPGA pins set the constellation point; the ADL5375 puts it on the 5.8 GHz carrier")
    note(20, 24, "Idle = (I +a, Q 0): a carrier at 0 deg that the far end's loop tracks.  BPSK: I to -a.  QPSK: (+-a, +-a).  "
         "FSK: the four phases in turn at +-df.  OOK: both at 0.  Each ladder gives -a / 0 / +a as 00 / 01,10 / 11 "
         "(a = 0.33 V single-ended about the 0.5 V bias; sim/budget.py section 1).", cols=100)
    note(20, 33, LV.LEGEND, cols=100)

    y = 99.06
    mod = part("ADL5375", "U201", 228.6, y)
    ibbp, ibbn, qbbp, qbbn = mod.pin("21"), mod.pin("22"), mod.pin("10"), mod.pin("9")
    # the I ladder above the chip's I pins, the Q ladder below its Q pins; each node wired to its pin
    ni = ladder(S, ibbp[0] - 27.94, ibbp[1] - 30.48, ("TX_I1", "TX_I0"), "VR_I", "TX_I")
    sig(ni[0] - 35, ni[1] - 7.62 - 17, LV.txt("TX_BITS"), cols=34)
    sig(ni[0] + 4, ni[1] - 13, LV.txt("TX_NODE"), cols=20)
    sig(ni[0] - 70, ni[1] + 17.78 - 3, LV.txt("VR"), cols=22)
    W(ni, (ni[0] + 2.54, ni[1]), (ni[0] + 2.54, ibbp[1]), ibbp)
    nq = ladder(S, qbbp[0] - 27.94, qbbp[1] + 33.02, ("TX_Q1", "TX_Q0"), "VR_Q", "TX_Q")
    W(nq, (nq[0] + 2.54, nq[1]), (nq[0] + 2.54, qbbp[1]), qbbp)
    # the N inputs at the 0.5 V bias: 5.1k / 1k from +3V3_ANA, between the two
    xb = ibbn[0] - 10.16
    W(ibbn, (xb, ibbn[1])); W(qbbn, (xb, qbbn[1])); W((xb, ibbn[1]), (xb, qbbn[1]))
    yb = (ibbn[1] + qbbn[1]) / 2.0
    J(xb, yb)
    W((xb, yb), (xb - 7.62, yb))
    up("R 5.1k", xb - 7.62, yb, "+3V3_ANA", text="left")
    r, bpt = down("R 1k", xb - 7.62, yb, net=None, text="left")
    W(bpt, (bpt[0], bpt[1] + G)); gnd(bpt[0], bpt[1] + G)
    J(xb - 7.62, yb)
    W((xb - 7.62, yb), (xb - 17.78, yb))
    down("C 1uF", xb - 17.78, yb, text="left")
    label(xb - 16.51, yb, "VN_0V5", size=1.0)
    sig(xb - 60, yb - 3, LV.txt("TX_BIAS") + "  VR_I / VR_Q (the DAC) centre each ladder and null the carrier for OOK tests.", cols=30)
    # DSOP: from U206 (below), not from the header (Response 15, REVA_CHANGES.md 2).  R209 holds it high too.
    e = stub(mod, "1", dx=-12.7)
    label(e[0], e[1], "TX_DIS", size=1.0, justify="right bottom")
    J(e[0] + 5.08, e[1])
    _, rb209 = down("R 100k", e[0] + 5.08, e[1], net=None, text="right")     # R209, below as before; its rail hangs
    flag("+3V3_DIG", *rb209, rot=180)                                          # from its foot (a wire runs above it)
    note(e[0] - 2, e[1] + 14, "TX_DIS high mutes the output in 100 ns (200 ns to restore).", cols=24)
    # ---- TX_EN -> DSOP: the modulator transmits only while a running host holds TX_EN high ----------------
    # (Response 15, REVA_CHANGES.md 2).  With the 100 k pull-down DSOP had, a host that was off (its pin's
    # clamp diode at 0.6 V), unconfigured or loading another overlay left the modulator ON, the synthesizer
    # still running on this board's own supply.  R227's 1 k beats the Zynq's configuration pull-ups (10 k at
    # the strongest: 0.35 V, under the 74LVC1G04's 0.8 V); driven high it still reads 2.35 V or more through the
    # PYNQ's 200 ohm (VOH 2.9 V at the XDC's 4 mA, less 0.55 V), over the inverter's 2.0 V.
    xi, yi = 215.9, 167.64
    inv = part("LVC1G04", "U206", xi, yi, rot=0)
    ia, iy = inv.pin("2"), inv.pin("4")
    xin = ia[0] - 20.32
    W(ia, (xin, ia[1]))
    S.hlabel(xin, ia[1], "TX_EN", shape="input", rot=180)
    J(ia[0] - 10.16, ia[1]); down("R 1k", ia[0] - 10.16, ia[1], text="left", ref="R227")
    W(iy, (iy[0] + 10.16, iy[1])); label(iy[0] + 10.16, iy[1], "TX_DIS", size=1.0)
    vcc, gnd_ = inv.pin("5"), inv.pin("3")
    W(vcc, (vcc[0], vcc[1] - 5.08)); flag("+3V3_DIG", vcc[0], vcc[1] - 5.08)
    W((vcc[0], vcc[1] - 2.54), (vcc[0] + 7.62, vcc[1] - 2.54)); J(vcc[0], vcc[1] - 2.54)
    down("C 100nF", vcc[0] + 7.62, vcc[1] - 2.54, text="right", ref="C235")
    W(gnd_, (gnd_[0], gnd_[1] + G)); gnd(gnd_[0], gnd_[1] + G)
    U.S.nc(*inv.pin("1"))
    note(xin - 2, yi + 14, "TX_EN (header 24) high transmits.  U206 makes DSOP = not TX_EN; R227 holds TX_EN low, so the "
         "modulator is off whenever no running gateware drives it: the host off, unconfigured, or loading another overlay.  "
         "The gateware's CTRL[0] (TX_DIS) and the keyer drive the header pin inverted.", cols=44)
    # LO
    lop, lon = mod.pin("3"), mod.pin("4")
    e = stub(mod, "3", dx=-5.08)
    a, b = series("C 1.5pF", lop[0] - 12.7, lop[1]); W(b, e)
    e2 = stub(mod, "4", dx=-5.08)
    a2, b2 = series("C 1.5pF", lon[0] - 12.7, lon[1], above=False); W(b2, e2)
    lo_top = {"p": a, "n": a2}
    # supplies and grounds
    B.supply_bar(mod, ["18", "24"], "+5V_RF", dy=12.7, side_caps=2, bulk="C 1uF")
    B.bottom_gnd(mod, ["2", "5", "8", "11", "12", "14", "17", "19", "20", "23", "25"])
    for n in ("6", "7", "13", "15"):
        S.nc(*mod.pin(n))
    note(mod.pin("2")[0] - 4, y + 46, "ADL5375-05: 400 MHz-6 GHz quadrature modulator; -4.5 dBm out at 5.8 GHz with this drive, carrier feedthrough -19.5 dBm.  "
         "LO 0 dBm differential from the synthesizer below.  CONSIGNED.", cols=40)
    # RF out: DC block, gain block, bias tee, pi pad, coupler, SMA
    rfo = mod.pin("16")
    yr = rfo[1]
    gb = part("ADL5611", "U202", rfo[0] + 33.02, yr)
    sig(rfo[0] + 3, yr + 6, LV.txt("MOD_OUT"), cols=16)
    B.dcblock(rfo[0], yr, gb.pin("1")[0])
    B.bottom_gnd(gb, ["2"])
    gout = gb.pin("3")
    xbias = gout[0] + 10.16
    W(gout, (xbias, yr))
    B.bias_tee(xbias, yr)
    note(gb.pin("2")[0] - 2, yr + 18, "ADL5611: +14.3 dB at 5.8 GHz -> +9.8 dBm at the SMA.  P1dB about +16 dBm.", cols=28)
    xpad = xbias + 40.64                         # past the bias tee's three capacitors
    B.dcblock(xbias, yr, xpad)
    sig(xbias + 2, yr - 34, LV.txt("TX_OUT"), cols=24)
    # pi pad footprints: series 0 ohm fitted, shunts DNP
    for xs in (xpad, xpad + 15.24):
        r = part("R 49.9R", nref("R"), xs, yr + 3.81 + G, rot=0, dnp=True, value="DNP", text="right", fsize=1.0)
        top_, bot = sorted((r.pin("1"), r.pin("2")), key=lambda p: p[1])
        W((xs, yr), top_); J(xs, yr)
        W(bot, (bot[0], bot[1] + G)); gnd(bot[0], bot[1] + G)
    pa, pb = series("R 0R", xpad + 7.62, yr)
    W((xpad, yr), pa); W(pb, (xpad + 15.24, yr))
    note(xpad - 6, yr + 22, "Pi pad: 0 ohm fitted; fit three resistors for a fixed TX attenuation.", cols=24)
    xcp = xpad + 15.24 + 20.32
    W((xpad + 15.24, yr), (xcp, yr))
    cout = B.coupler_mon(xcp, yr, "TX MON", "CP201", level=LV.txt("TX_MON"))
    j = part("SMA", "J202", cout[0] + 12.7, yr, rot=180, value="TX ANT", text="hide")
    W(cout, j.pin("1"))
    s2 = j.pin("2"); W(s2, (s2[0], s2[1] + G)); gnd(s2[0], s2[1] + G)
    sig(xcp + 38, yr - 18, "TX ANT, 50 ohm SMA: " + LV.txt("TX_ANT"), cols=22)

    # ---- TX synthesizer and its reference --------------------------------------------------
    ys = 279.4
    tc = part("TCXO", "Y201", 30.48, ys)
    xv, yv = tc.pin("4"); W((xv, yv), (xv, yv - 5.08)); flag("+3V3_OSC", xv, yv - 5.08)
    W((xv, yv - 2.54), (xv + 7.62, yv - 2.54)); J(xv, yv - 2.54)
    down("C 100nF", xv + 7.62, yv - 2.54, text="right")
    gx, gy = tc.pin("2"); W((gx, gy), (gx, gy + G)); gnd(gx, gy + G)
    S.nc(*tc.pin("1"))
    note(tc.pin("1")[0] - 10, ys + 14, "25 MHz TCXO +-2.5 ppm (TC32H4, LVCMOS): the TX reference.  Two boards' carriers then differ by at most 29 kHz.", cols=30)
    tout = tc.pin("3")
    # reference selector: TCXO (pin 1) or REF IN (pin 3); pin 2 to the synthesizer
    jr = part("HDR1x3", "JP201", tout[0] + 17.78, ys - 10.16, rot=90, value="REF", text="hide")
    p1, p2, p3 = jr.pin("1"), jr.pin("2"), jr.pin("3")
    W(tout, (p1[0], tout[1]), p1)
    # REF IN above the TCXO, its line down to the jumper's pin 3; a DNP 49.9 ohm hangs at the jack
    jin = part(B.jack_of("REF IN"), nref("J"), p3[0] - 7.62, ys - 30.48, rot=0, value="REF IN", text="hide")
    rp = jin.pin("1")
    W(rp, (p3[0], rp[1]), p3)
    s2 = jin.pin("2"); W(s2, (s2[0], s2[1] + G)); gnd(s2[0], s2[1] + G)
    rt = part("R 49.9R", nref("R"), rp[0] - 7.62, rp[1] + 3.81 + G, rot=0, dnp=True, value="DNP", text="left", fsize=1.0)
    top_, bot = sorted((rt.pin("1"), rt.pin("2")), key=lambda p: p[1])
    W(rp, (rp[0] - 7.62, rp[1])); W((rp[0] - 7.62, rp[1]), top_)
    W(bot, (bot[0], bot[1] + G)); gnd(bot[0], bot[1] + G)
    ref_src = (p2[0], p2[1] - 7.62)
    sig(tout[0] + 2, ys + 3, LV.txt("REF_TX"), cols=20)
    W(p2, ref_src)
    note(tout[0] - 12, ys + 36, "JP201 REF: TCXO (default) or REF IN (SMA, 10-210 MHz, 0.7 V p-p min; fit 49.9 ohm for a 50 ohm source).  "
         "Lock two boards to one reference on the bench to take the frequency offset out of the experiment.", cols=34)
    pll, lo = B.synthesizer("U203", tout[0] + 83.82, ys + 5.08, "+3V3_PLL_TX", "LE_PLL_TX", "MUX_TX", "LO_TX", "LO TX MON", ref_src,
                            bar_dy=25.4)                      # the bar high enough for its capacitors to clear the REF IN jack
    lp, ln = lo["lo_p"], lo["lo_n"]
    xup_p, xup_n = lo_top["p"][0] - 5.08, lo_top["p"][0] - 2.54
    W(lp, (xup_p, lp[1]), (xup_p, lo_top["p"][1]), lo_top["p"])
    W(ln, (xup_n, ln[1]), (xup_n, lo_top["n"][1]), lo_top["n"])
    label(lp[0] + 1.27, lp[1], "LO_TX_P", size=1.0)
    sig(xup_p - 32, (lo_top["p"][1] + lp[1]) / 2.0, LV.txt("LO_TX"), cols=24)
    label(ln[0] + 1.27, ln[1], "LO_TX_N", size=1.0, justify="left top")
    note(tout[0] + 30, ys - 60, "TX synthesizer: MAX2871, 5.8 GHz integer-N from 25 MHz (N = 232; the far end's RX sits 50 MHz away), RFOUTA differential into the ADL5375's LO, "
         "RFOUTB to the LO TX MON jack.  Its own LDO, +3V3_PLL_TX.", cols=52)

    # ---- triggers -------------------------------------------------------------------------
    xt, yt = 457.2, 279.4
    title(xt - 40, yt - 30, "Latency triggers")
    for unit, n_in, n_out, name, dy in ((1, "1", "6", "TRIG_A", 0.0), (2, "3", "4", "TRIG_B", 22.86)):
        buf = part("LVC2G34", "U204", xt, yt + dy, unit=unit)
        e = stub(buf, n_in, dx=-12.7); S.hlabel(e[0], e[1], name, shape="input", rot=180)
        ox, oy = buf.pin(n_out)
        ra, rb = series("R 33R", ox + 7.62, oy); W((ox, oy), ra)
        jt = part(B.jack_of(name.replace("_", " ")), nref("J"), ox + 20.32, oy, rot=0, value=name.replace("_", " "), text="hide")
        W(rb, jt.pin("1"))
        s2 = jt.pin("2"); W(s2, (s2[0], s2[1] + G)); gnd(s2[0], s2[1] + G)
        if unit == 2:
            sig(ox + 12, oy + 14, LV.txt("TRIG_OUT"), cols=30)
    bufp = part("LVC2G34", "U204", xt + 43.18, yt + 10.16, unit=3)
    vp, vm = bufp.pin("5"), bufp.pin("2")
    W(vp, (vp[0], vp[1] - 5.08)); flag("+3V3_DIG", vp[0], vp[1] - 5.08)
    W((vp[0], vp[1] - 2.54), (vp[0] + 7.62, vp[1] - 2.54)); J(vp[0], vp[1] - 2.54)
    down("C 100nF", vp[0] + 7.62, vp[1] - 2.54, text="right")
    W(vm, (vm[0], vm[1] + G)); gnd(vm[0], vm[1] + G)
    sch = part("LVC1G17", "U205", xt, yt + 55.88)
    yin = sch.pin("2")[1]
    jin2 = part(B.jack_of("TRIG IN"), nref("J"), xt - 45.72, yin, rot=180, value="TRIG IN", text="hide")
    ip = jin2.pin("1")
    ra, rb = series("R 1k", ip[0] + 15.24, yin); W(ip, (ip[0] + 5.08, yin)); W((ip[0] + 5.08, yin), ra); W(rb, sch.pin("2"))
    s2 = jin2.pin("2"); W(s2, (s2[0], s2[1] + G)); gnd(s2[0], s2[1] + G)
    J(ip[0] + 5.08, yin)
    jt2 = part("HDR1x2", "JP202", ip[0] + 5.08, yin + 12.7, rot=270, value="50R", text="hide")
    W((ip[0] + 5.08, yin), jt2.pin("1"))
    rterm = part("R 49.9R", nref("R"), jt2.pin("2")[0], jt2.pin("2")[1] + 3.81 + G, rot=0, text="left", fsize=1.0)
    top_, bot = sorted((rterm.pin("1"), rterm.pin("2")), key=lambda p: p[1])
    W(jt2.pin("2"), top_)
    W(bot, (bot[0], bot[1] + G)); gnd(bot[0], bot[1] + G)
    e = stub(sch, "4", dx=12.7); S.hlabel(e[0], e[1], "TRIG_IN", shape="output", rot=0)
    # TRIG IN MON (Response 14, Jason: "To put a scope across TRIG IN, I'd like a U.FL or MMCX connector"):
    # the buffer's output, the edge the FPGA sees, through 453 ohm: /10 into a 50 ohm scope input
    o4 = sch.pin("4")
    xm = o4[0] + 5.08
    J(xm, o4[1])
    W((xm, o4[1]), (xm, o4[1] - 12.7))
    B.tap(xm, o4[1] - 12.7, "TRIG IN MON", rkey="R 453R")
    # the FPGA-free path (Response 12): a DNP 0 ohm from the buffer's output to the TX_Q1 ladder bit.  Fitted,
    # with the FPGA holding TX_Q1 as an input, a TRIG IN pulse steps the transmitter from idle to +Q and the far
    # board's QP comparator answers: TRIG IN MON here against QP MON there is the link's own latency.
    xb = o4[0] + 10.16
    J(xb, o4[1])
    t, b = U.vpart("R 0R", nref("R"), xb, o4[1] + G + 3.81, dnp=True, value="DNP 0R", text="right", fsize=1.0)
    W((xb, o4[1]), t)
    W(b, (b[0], b[1] + G))
    label(b[0], b[1] + G, "TX_Q1", size=1.0, justify="left top")
    note(xb + 6, o4[1] + 14, "DNP 0R to TX_Q1: fit it, and set the FPGA's TX_Q1 pin to an input, to step the transmitter straight "
         "from TRIG IN to +Q: the link's latency without either FPGA (TRIG IN MON here, QP MON on the far board).", cols=30)
    sig(xt + 20, yt + 70, LV.txt("TRIG_IN"), cols=30)
    vp2, vm2 = sch.pin("5"), sch.pin("3")
    W(vp2, (vp2[0], vp2[1] - 5.08)); flag("+3V3_DIG", vp2[0], vp2[1] - 5.08)
    W((vp2[0], vp2[1] - 2.54), (vp2[0] + 7.62, vp2[1] - 2.54)); J(vp2[0], vp2[1] - 2.54)
    down("C 100nF", vp2[0] + 7.62, vp2[1] - 2.54, text="right")
    W(vm2, (vm2[0], vm2[1] + G)); gnd(vm2[0], vm2[1] + G)
    S.nc(*sch.pin("1"))
    note(xt - 50, yt + 80, "TRIG IN: a detector pulse (3.3 V logic; 1k series protects the Schmitt input; JP202 terminates it in 50 ohm) "
         "starts the FPGA's latency counter.  TRIG A / B: the FPGA marks the symbol it sent or the one it decoded; "
         "board-to-board latency is TRIG A here against TRIG B there on the scope.", cols=40)
    box(xt - 56, yt - 36, 150, 140)
    return S
