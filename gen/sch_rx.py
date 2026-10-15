"""The receiver sheet (A2): the RF chain from the RX SMA through the LNA, the step attenuator,
the gain block and the balun into the ADL5380; its I and Q outputs through the two THS4541s to
the three comparators and the FPGA; the Costas loop (the sign(I)*Q switch, the HOLD switch, the
PI filter and the VC summing stage) steering the VCXO that references the RX synthesizer; the
monitoring DAC and ADC.  Signals run left to right; the synthesizer sits under the demodulator
it feeds, the loop under the arms.  References 101-199.
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

Y_RF = 66.04                 # the RF chain's line


def rf_blocks(b1, b2, dem):
    """The balun's balanced pair into RFIP/RFIN through a DC block each (ADL5380 datasheet: "both the LO and RF
    ports should be ac-coupled"; its evaluation board's C2x/C3x; review A of Prompt 31: a lattice balun's balanced
    terminals have a DC path to its ground terminal, which would have pulled the demodulator's biased RF inputs
    to 0 V).  The same 1.5 pF as the LO legs' blocks.  Drawn after everything else so that the two capacitors
    take the sheet's last references and no hand-placed part's reference moves (gen/placement.py anchors)."""
    e = B.dcblock(b1[0], b1[1], b1[0] + 10.16)
    W(e, dem.pin("22"))
    xm = b2[0] + 10.16
    B.dcblock(b2[0], b2[1], xm, above=False)
    L((xm, b2[1]), dem.pin("21"), first="h")


def build(S):
    U.begin(S, ref_base=100)
    title(20, 18, "Receiver: 5.8 GHz in, I/Q out, and the Costas loop that keeps the LO on the carrier")
    note(20, 24, "Signal flows left to right.  " + LV.LEGEND + "  The DSA holds the demodulator at about -20 dBm from 3 m to 3 km.", cols=100)

    # ---- RF chain -------------------------------------------------------------------------
    y = Y_RF
    j = part("SMA", "J101", 22.86, y, rot=0, value="RX ANT", text="hide")
    jx, jy = j.pin("1")
    s2 = j.pin("2"); W(s2, (s2[0], s2[1] + G)); gnd(s2[0], s2[1] + G)
    sig(10, y + 14, "RX ANT, 50 ohm SMA: " + LV.txt("RX_ANT"), cols=30)
    e = B.dcblock(jx, y, jx + 12.7)
    B.esd_shunt(jx + 1.27, y)                     # Prompt 28: the antenna side of the DC block
    lna = U.part_at_pin("SKY65404", "U101", "3", e[0] + 7.62, y)
    rin = lna.pin("3")
    xm = e[0]
    W((xm, y), rin)
    J(xm, y); down("C 0.5pF", xm, y, text="left")
    B.pullup_top(lna, "1", "R 100R", "+3V3_ANA", text="right")
    # supply through 0.6 nH, with 100 nF beside it
    vx, vy = lna.pin("6")
    W((vx, vy), (vx, vy - 2.54))
    lt, lb = vpart("L0N6", nref("L"), vx, vy - 2.54 - 3.81, fsize=1.0, text="left")
    yj = lt[1] - G
    W(lt, (vx, yj)); W((vx, yj), (vx, yj - G)); flag("+3V3_ANA", vx, yj - G)
    W((vx, yj), (vx - 12.7, yj)); J(vx, yj)
    down("C 100nF", vx - 12.7, yj, text="left")
    W((vx, vy - 2.54), (vx - 2.54, vy - 2.54)); U.pwr_flag(vx - 2.54, vy - 2.54, rot=90); J(vx, vy - 2.54)   # ERC: the LNA's VCC node is fed through the inductor
    B.bottom_gnd(lna, ["2", "5", "7"])
    note(lna.pin("2")[0] - 24, y + 27, "SKY65404-31: 13 dB, NF 1.0 dB, 10 mA.  Skyworks' circuit: 0.5 pF shunt at RF_IN, 0.6 nH + 100 nF on VCC, 100 ohm on the enable.", cols=36)
    rout = lna.pin("4")
    sig(jx + 30, y + 14, LV.txt("LNA_OUT"), cols=20)
    # DSA
    dsa = U.part_at_pin("PE43711", "U102", "5", rout[0] + 17.78, y)
    r1 = dsa.pin("5")
    B.dcblock(rout[0], y, r1[0])
    B.supply_bar(dsa, ["2"], "+3V3_ANA", dy=10.16, caps_side="left")
    B.pullup_top(dsa, "3", "R 10k", "+3V3_DIG", text="right")
    B.bottom_gnd(dsa, ["1", "24", "23", "22", "21", "20", "19", "4", "25"])
    B.side_gnd(dsa, ["6", "7", "8", "9", "10", "11", "12", "13", "15"])
    for n, name in (("17", "SPI_SCLK"), ("18", "SPI_SDATA"), ("16", "LE_DSA")):
        e = stub(dsa, n, dx=-12.7)
        S.hlabel(e[0], e[1], name, shape="input", rot=180)
    note(dsa.pin("4")[0] - 30, y + 36, "PE43711: 0-31.75 dB in 0.25 dB steps, serial mode (P/S high; the parallel pins grounded as the datasheet asks).  "
         "Powers up at 31.75 dB.", cols=36)
    r2 = dsa.pin("14")
    sig(r2[0] + 1, y + 5, LV.txt("DSA_OUT"), cols=20)
    # gain block and its bias tee
    gb = U.part_at_pin("ADL5611", "U103", "1", r2[0] + 15.24, y)
    B.dcblock(r2[0], y, gb.pin("1")[0])
    B.bottom_gnd(gb, ["2"])
    gout = gb.pin("3")
    xb = gout[0] + 10.16
    W(gout, (xb, y))
    B.bias_tee(xb, y)
    note(gb.pin("2")[0] - 4, y + 26, "2 x ADL5611: +14.3 dB each at 5.8 GHz (22 dB at 1 GHz), 5 V through 43 nH chokes (Table 6).  The second one "
         "(Response 6) puts the comparators' 20 mV floor near the noise: the fast path reads to %.0f dBm, the slow one to %.0f." % (LV.B["floor_fast_dBm"], LV.B["noise_floor_slow_dBm"] + 8.4), cols=30)
    # the second gain block, its own bias tee
    xg2 = xb + 38.1                             # past the bias tee's three capacitors and their texts
    B.dcblock(xb, y, xg2)
    gb2 = U.part_at_pin("ADL5611", "U117", "1", xg2, y)
    B.bottom_gnd(gb2, ["2"])
    gout2 = gb2.pin("3")
    xb2 = gout2[0] + 10.16
    W(gout2, (xb2, y))
    B.bias_tee(xb2, y)
    sig(xb - 8, y - 40, LV.txt("GB1_OUT"), cols=18)
    # coupler and RX MON, then the balun
    xc = xb2 + 38.1                              # past the second bias tee's capacitors
    B.dcblock(xb2, y, xc)
    cout = B.coupler_mon(xc, y, "RX MON", "CP101", level=LV.txt("RX_MON"))
    sig(xc + 6, y - 34, LV.txt("DEM_IN"), cols=20)
    t = U.part_at_pin("BALUN", "T101", "1", cout[0] + 7.62, y)
    W(cout, t.pin("1"))
    px, py = t.pin("4"); W((px, py), (px, py + G)); gnd(px, py + G)
    note(xc + 2, y + 18, "TDK HHM1907B1 1:1 balun, 4.9-5.95 GHz, 0.8 dB: the ADL5380 sheet's Johanson 5400 from JLCPCB's shelf "
         "(same ratio and band).  The 1.5 pF blocks: the RF port is AC-coupled (the sheet's C2x/C3x); the balun's balanced "
         "terminals have a DC path to ground.", cols=26)
    # demodulator: RFIP on the balun's BAL1 row, 7.62 to the right of its pins
    b1, b2 = t.pin("2"), t.pin("3")
    dem = U.part_at_pin("ADL5380", "U104", "22", b1[0] + 20.32, b1[1])
    balun_pair = (b1, b2, dem)                   # wired at the end of the sheet (rf_blocks): its two DC blocks are the sheet's last parts
    B.supply_bar(dem, ["6", "13", "24"], "+5V_RF", dy=12.7, bulk="C 1uF")
    B.bottom_gnd(dem, ["7", "1", "2", "5", "8", "11", "14", "17", "18", "20", "23", "25"])
    adj = stub(dem, "19", dx=-7.62)               # past the LO pair's two verticals
    # the resistor stands straight on the stub's end (no gap), so its flag stays under the RF blocks' lines (Prompt 31)
    r_adj = part("R 1.5k", nref("R"), adj[0], adj[1] - 3.81, rot=0, dnp=True, value="DNP 1.5k", text="right", fsize=1.0)
    rt, rbt = sorted((r_adj.pin("1"), r_adj.pin("2")), key=lambda p: p[1])
    W(rt, (rt[0], rt[1] - G)); flag("+5V_RF", rt[0], rt[1] - G)
    S.nc(*dem.pin("12"))
    note(dem.pin("1")[0] - 20, y + 48, "ADL5380: ADJ open at 5.8 GHz (its spec condition): baseband common mode 3.2 V, gain x1.95, 390 MHz.  "
         "Fit 1.5k here to drop the common mode to 2.5 V (and the 5.8 GHz gain).  LO 0 dBm, differential from the synthesizer below.  "
         "JLCPCB C579152; consigned from Digi-Key only if their shelf is short on the day.", cols=44)
    # P to LOIN, N to LOIP (the design review, KimiK3): on the board the synthesizer's RFOUTA_P faces
    # the demodulator's LOIN, so the pair runs straight and equal; P to LOIP crossed it and sent one
    # leg 40 mm round.  Inverting the LO inverts I and Q together, which the Costas loop's
    # sign(I) x Q and the gateware's learned idle do not see.
    lop, lon = dem.pin("10"), dem.pin("9")
    # the LO pair arrives from the synthesizer below on two verticals just left of the chip, each
    # with its DC block standing in the vertical (the upper pin's outside, turning in above the other's top)
    x_out, x_in = min(lop[0], lon[0]) - 5.08, min(lop[0], lon[0]) - 2.54
    xlo_p, xlo_n = (x_out, x_in) if lop[1] < lon[1] else (x_in, x_out)
    W(lop, (xlo_p, lop[1])); W(lon, (xlo_n, lon[1]))
    yblk = max(lop[1], lon[1]) + 27.94
    tops = {}
    for xv, yrow in ((xlo_p, lop[1]), (xlo_n, lon[1])):      # the inner block lower: their texts clear each other
        dyb = 0.0 if xv == x_out else 10.16
        ct, cb = vpart("C 1.5pF", nref("C"), xv, yblk + dyb, fsize=1.0, text="left" if xv == x_out else "right")
        W((xv, yrow), ct)
        tops[xv] = (xv, yblk + dyb + 3.81)
    lo_top = {"p": tops[xlo_p], "n": tops[xlo_n]}
    sig(x_out - 36, yblk - 4, LV.txt("LO_RX"), cols=26)

    # ---- I and Q arms: the FDAs and the comparators -----------------------------------------
    ihi, ilo, qhi, qlo = dem.pin("3"), dem.pin("4"), dem.pin("16"), dem.pin("15")
    xf = dem.pin("3")[0] + 66.04
    # IHI drives the I arm's - input and ILO its + input (Response 10): on the board the demodulator's
    # IHI pin faces the amplifier's - input, so the pair arrives uncrossed and the gain and feedback
    # resistors sit at the pins.  I is inverted; the Costas loop locks 180 degrees round and the idle
    # reads the same sign as before, and the gateware takes the sign from the idle in any case.
    ip, inn_ = B.arm(S, "I", "U105", ilo, ihi, ihi[1] + 5.08, xf, LV.VAL["fda_Rf"], rg_key=LV.VAL["fda_Rg"], rs_key=LV.VAL["fda_Rs"], hlabels=True,
                     node_label="I_SUM",
                     note_text=LV.FAST_ARM_NOTE + "  I is the data, inverted: ILO drives + (the board's pin order; the idle sets the sign).  "
                     "I_SUM goes to sheet 6, where DAC2's channel D trims this arm's offset through 100 k: a few mV of demodulator "
                     "offset x4 is a fair part of the comparator's 20 mV.")
    sig(ihi[0] + 10, ihi[1] - 21, LV.txt("IQ_DEM"), cols=26)
    qp, qn = B.arm(S, "Q", "U106", qhi, qlo, qhi[1] + 50.8, xf, LV.VAL["fda_Rf"], rg_key=LV.VAL["fda_Rg"], rs_key=LV.VAL["fda_Rs"], hlabels=True,
                   trim="Q_OFF_F",
                   note_text=LV.FAST_ARM_NOTE + "  Q is the phase error; both pairs also leave to the slow path (sheet 6) and the window "
                   "comparators (sheet 7).  Q_OFF_F (DAC1 C, 100 k) trims this arm's offset: with a weak pilot the loop's lock point moves "
                   "by the arm's offset over the pilot's slope (PLAN.md section 18).")
    # comparator I
    ci = B.comparator("U107", ip[0] + 35.56, ip[1] + 7.62)
    L(ip, ci.pin("3"), first="h") if abs(ip[1] - ci.pin("3")[1]) < 0.01 else W(ip, (ip[0] + 10.16, ip[1]), (ip[0] + 10.16, ci.pin("3")[1]), ci.pin("3"))
    W(inn_, (inn_[0] + 5.08, inn_[1]), (inn_[0] + 5.08, ci.pin("4")[1]), ci.pin("4"))
    co = ci.pin("1")
    W(co, (co[0] + 7.62, co[1]))
    ra, rb = series(LV.VAL["cmp_series"], co[0] + 11.43, co[1])                # source termination for the line to the FPGA (no series R on the Icepi)
    W((co[0] + 7.62, co[1]), ra); W(rb, (co[0] + 20.32, co[1]))
    S.hlabel(co[0] + 20.32, co[1], "CMP_I", shape="output", rot=0)
    J(co[0] + 7.62, co[1])
    W((co[0] + 7.62, co[1]), (co[0] + 7.62, co[1] + 15.24))
    B.tap(co[0] + 7.62, co[1] + 15.24, "CMP I MON", rkey=LV.VAL["tap_R"], text="CMP I MON: the comparator's output, /10 into 50 ohm")
    sig(co[0] + 10, co[1] - 24, LV.txt("CMP_I"), cols=34)
    sig(ip[0] + 2, ip[1] + 13, LV.txt("I_ARM"), cols=22)
    # I MON tap and the ADC branch from the I_P line
    xi = ip[0] + 10.16
    J(xi, ip[1])
    W((xi, ip[1]), (xi, ip[1] - 10.16))
    B.tap(xi, ip[1] - 10.16, "I MON")
    # the Q window comparators (QP, QN) moved to sheet 7 with the new I pair (Response 14); Q MON stays here
    xq = qp[0] + 10.16
    W(qp, (xq, qp[1])); J(xq, qp[1])
    W((xq, qp[1]), (xq, qp[1] - 10.16))
    B.tap(xq, qp[1] - 10.16, "Q MON")                         # 10.16, not 15.24: its resistor was in the I arm's note
    xq2 = qn[0] + 5.08
    W(qn, (xq2, qn[1]))
    yqp_tap, yqn_tap = qp[1], qn[1]                          # where the Costas loop's Q branches leave the arm's lines
    sig(qp[0] + 7, qp[1] + 8, LV.txt("Q_ARM"), cols=18)

    # ---- the Costas loop ----------------------------------------------------------------
    y0 = qn[1] + 76.2
    title(xf - 60, y0 - 30, "Costas loop: error = sign(I) x Q, PI filter, VCXO -> synthesizer x232")
    # Q_P and Q_N come down from the Q arm's outputs (branches off the lines to the comparators)
    xqp, xqn = xq, xq2
    # two sign jumpers: B1 takes Q+ or Q-, B2 the other
    mux = part("LVC1G3157", "U110", xf - 38.1, y0)
    b1, b2, ao, sel = mux.pin("3"), mux.pin("1"), mux.pin("4"), mux.pin("6")
    jp1 = part("HDR1x3", "JP101", b1[0] - 12.7, b1[1] - 10.16, rot=90, value="SIGN", text="hide")
    jp2 = part("HDR1x3", "JP102", b2[0] - 12.7, b2[1] + 2.54, rot=90, value="SIGN", text="hide")
    # jumper 1 (pins below the body at b1 - 5.08): 1 <- Q+, 2 -> B1, 3 <- Q-
    p1, p2, p3 = jp1.pin("1"), jp1.pin("2"), jp1.pin("3")
    W(p2, (p2[0], b1[1]), b1)
    # jumper 2 (pins above the body): 1 <- Q+, 2 -> B2, 3 <- Q-
    q1, q2, q3 = jp2.pin("1"), jp2.pin("2"), jp2.pin("3")
    W(q2, (q2[0], b2[1]), b2)
    # the Q+ line: down from the Q arm, along y0 - 20, to both jumpers' pin 1 (left pins)
    yq = y0 - 33.02
    xl1 = min(p1[0], q1[0]) - 7.62
    W((xqp, qp[1]), (xqp, yq)) if False else None
    # Q+ branch: from the junction on the Q_P line at xq, down to yq, left to xl1, down to the jumpers
    xqp_v = xqp
    W((xqp_v, yqp_tap), (xqp_v, yq))
    W((xqp_v, yq), (xl1, yq), (xl1, q1[1]))
    W((xl1, p1[1]), p1); J(xl1, p1[1])
    W((xl1, q1[1]), q1)
    # Q- branch: from the Q_N line at xq2, down to yq + 5.08, to the jumpers' pin 3 (right pins)
    yq2 = yq + 5.08
    xl3 = max(p3[0], q3[0]) + 5.08
    W((xqn, yqn_tap), (xqn, yq2))
    W((xqn, yq2), (xl3, yq2), (xl3, q3[1]))
    W((xl3, p3[1]), p3); J(xl3, p3[1])
    W((xl3, q3[1]), q3)
    note(jp1.pin("2")[0] - 40, y0 - 4, "JP101 / JP102 SIGN: set them OPPOSITE ways.  Default: JP101 right (Q- to B1), JP102 left (Q+ to B2): the switch "
         "connects A to B1 when S is low and to B2 when S is high (its datasheet), so ERR = sign(I) x Q.  Both the other way = -sign(I) x Q: "
         "move both if the loop runs away (positive feedback).", cols=26)
    B.supply_bar(mux, ["5"], "+3V3_DIG", dy=10.16)
    B.bottom_gnd(mux, ["2"])
    # select: the comparator's output or the FPGA, by the SEL jumper below the switch
    jps = part("HDR1x3", "JP103", sel[0], sel[1] + 12.7, rot=90, value="SEL", text="hide")
    W(sel, jps.pin("2"))
    W(jps.pin("1"), (jps.pin("1")[0] - 10.16, jps.pin("1")[1]))
    label(jps.pin("1")[0] - 10.16, jps.pin("1")[1], "CMP_I", size=1.0)
    W(jps.pin("3"), (jps.pin("3")[0] + 10.16, jps.pin("3")[1]))
    S.hlabel(jps.pin("3")[0] + 10.16, jps.pin("3")[1], "LOOP_SEL", shape="input", rot=0)
    note(sel[0] - 14, sel[1] + 24, "JP103 SEL: COSTAS = sign(I) from U107 (the net CMP_I); FPGA = LOOP_SEL (hold it high for a plain PLL on Q).", cols=30)
    # error output, HOLD switch
    ex = ao[0] + 10.16
    W(ao, (ex, ao[1])); J(ex, ao[1])
    label(ao[0] + 1.27, ao[1], "ERR", size=1.0)
    sig(ex + 2, ao[1] + 4, LV.txt("ERR"), cols=18)
    W((ex, ao[1]), (ex, ao[1] - 15.24))
    B.tap(ex, ao[1] - 15.24, "ERR MON")
    # Response 14: NC takes the error (LOOP_HOLD low), NO takes V_MID (LOOP_HOLD high), COM drives the
    # integrator's input resistor.  A hold then ties that resistor to the integrator's own reference, so
    # the switch's leakage flows into V_MID instead of being integrated: holds 2-4x longer (PLAN.md s18).
    hold = part("TS5A3159", "U111", ex + 27.94, ao[1] - 2.54)
    W((ex, ao[1]), hold.pin("3"))
    nox, noy = hold.pin("1")
    W((nox, noy), (nox - 5.08, noy))
    label(nox - 5.08, noy, "V_MID", size=1.0, justify="right bottom")
    hx, hy = hold.pin("6")
    W((hx, hy), (hx, hy + 7.62)); W((hx, hy + 7.62), (hx + 15.24, hy + 7.62))
    S.hlabel(hx + 15.24, hy + 7.62, "LOOP_HOLD", shape="input", rot=0)
    J(hx + 7.62, hy + 7.62); down("R 100k", hx + 7.62, hy + 7.62, text="right")
    B.supply_bar(hold, ["5"], "+3V3_DIG", dy=10.16)
    B.bottom_gnd(hold, ["2"])
    note(hold.pin("4")[0] - 10, hy + 26, "LOOP_HOLD high ties the integrator's input to V_MID: no error in, VC holds, and the "
         "switch's leakage goes into V_MID, not the integrator.", cols=26)
    cx_, cy_ = hold.pin("4")
    W((cx_, cy_), (cx_ + 2.54, cy_), (cx_ + 2.54, ao[1] + 2.54))
    ncx, ncy = cx_ + 2.54, ao[1] + 2.54
    # op amp A: the PI filter
    oa = part("OPA2388", "U112", ncx + 38.1, ncy + 2.54, unit=1, mirror="x")
    inn, inp, out = oa.pin("2"), oa.pin("3"), oa.pin("1")
    ra, rb = series(LV.VAL["loop_R1"], ncx + 10.16, ncy)
    W((ncx, ncy), ra)
    xn = inn[0] - 5.08
    W(rb, (xn, ncy), (xn, inn[1]), inn)
    J(xn, inn[1])
    yfb = inn[1] - 15.24
    W((xn, inn[1]), (xn, yfb))
    r2a, r2b = series(LV.VAL["loop_R2"], xn + 10.16, yfb)
    W((xn, yfb), r2a)
    ca, cb = series(LV.VAL["loop_C"], r2b[0] + 10.16, yfb)
    W(r2b, ca)
    xo = out[0] + 5.08
    W(cb, (xo, yfb), (xo, out[1]))
    W(out, (xo, out[1])); J(xo, out[1])
    # 1.65 V reference: a divider with a capacitor below the op amp (its + input is the lower one)
    vref = (inp[0] - 7.62, inp[1])
    W(inp, vref)
    yv = vref[1] + 25.4
    W(vref, (vref[0], yv))
    W((vref[0], yv), (vref[0] - 7.62, yv))
    up("R 10k", vref[0] - 7.62, yv, "+3V3_ANA", text="left")
    r, bpt = down("R 10k", vref[0] - 7.62, yv, net=None, text="left")
    W(bpt, (bpt[0], bpt[1] + G)); gnd(bpt[0], bpt[1] + G)
    J(vref[0] - 7.62, yv)
    W((vref[0] - 7.62, yv), (vref[0] - 15.24, yv))
    down("C 1uF", vref[0] - 15.24, yv, text="left")
    label(vref[0] - 5.08, yv, "V_MID", size=1.0)
    note(ncx - 20, y0 - 24, "PI loop filter (sim/budget.py section 6): R1 %s, R2 %s, C 100 nF C0G -> fn 3 kHz, zeta 0.7 at the DSA's regulated level "
         "(Kd %.2f V/rad; it scales with the signal, which the DSA keeps).  U112A inverts; U112B inverts again: net non-inverting."
         % (LV.VAL["loop_R1"][2:], LV.VAL["loop_R2"][2:], LV.B["loop_Kd"]), cols=40)
    # op amp B: sums the filter output and the DAC's offset about 1.65 V (unity, inverting)
    ob = part("OPA2388", "U112", xo + 35.56, ncy + 2.54, unit=2, mirror="x")
    binn, binp, bout = ob.pin("6"), ob.pin("5"), ob.pin("7")
    xbn = binn[0] - 5.08
    r3a, r3b = series("R 10k", xo + 12.7, binn[1])
    J(xo, binn[1])                                            # the feedback column already runs through this row
    W((xo, binn[1]), r3a); W(r3b, (xbn, binn[1]), binn); J(xbn, binn[1])
    # the DAC's offset comes in through R4, standing under the summing node
    r4 = part("R 10k", nref("R"), xbn, binn[1] + 2.54 + 3.81, rot=0, text="left", fsize=1.0)
    r4top, r4bot = sorted((r4.pin("1"), r4.pin("2")), key=lambda p: p[1])
    W((xbn, binn[1]), r4top)
    yfb2 = binn[1] - 15.24
    r5a, r5b = series("R 10k", (xbn + bout[0]) / 2.0 + 2.54, yfb2)
    W((xbn, binn[1]), (xbn, yfb2), r5a)
    xob = bout[0] + 5.08
    W(r5b, (xob, yfb2), (xob, bout[1]))
    W(bout, (xob, bout[1])); J(xob, bout[1])
    W(binp, (binp[0], binp[1] + 7.62))
    label(binp[0], binp[1] + 7.62, "V_MID", size=1.0, justify="left top")
    # V_MID is wired: from the divider to op amp B's + input
    W((vref[0], yv), (vref[0], yv) ) if False else None
    label(xob, bout[1] + 2.54, "VC", size=1.0)
    J(xob, bout[1] + 10.16)
    B.tap(xob, bout[1] + 10.16, "VC MON", text=False)         # off the VC line below the output, clear of the feedback column above it
    sig(xob - 10, bout[1] - 38, "VC MON. " + LV.txt("VC") + " | " + LV.txt("V_MID"), cols=26)
    # the op amp's supply (unit 3)
    opw = part("OPA2388", "U112", ncx + 63.5, ncy + 33.02, unit=3, text="left",
               ref_at=(ncx + 63.5 - 3.0, ncy + 33.02 - 3.0), val_at=(ncx + 63.5 - 3.0, ncy + 33.02 - 1.0))
    vp, vm = opw.pin("8"), opw.pin("4")
    W(vp, (vp[0], vp[1] - 5.08)); flag("+3V3_ANA", vp[0], vp[1] - 5.08)
    W((vp[0], vp[1] - 2.54), (vp[0] + 7.62, vp[1] - 2.54)); J(vp[0], vp[1] - 2.54)
    down("C 100nF", vp[0] + 7.62, vp[1] - 2.54, text="right")
    W(vm, (vm[0], vm[1] + G)); gnd(vm[0], vm[1] + G)
    note(ncx + 72, ncy + 24, "OPA2388: zero drift, 5 uV offset, rail-to-rail in and out on 3.3 V, so the loop's static phase error is the comparator's, not the op amp's.  (The OPA2187 first drawn here needs 4.5 V and its inputs stop 2 V below the rail: it could never have sat at 1.65 V on 3.3 V.)", cols=28)
    # VC runs left along a corridor under the loop to the VCXO (drawn below the synthesizer row)
    y_vc = ncy + 45.72
    W((xob, bout[1]), (xob, y_vc))

    # ---- VCXO and the RX synthesizer ------------------------------------------------------
    ys = y_vc + 38.1
    vc = part("VCXO", "Y101", 76.2, ys)
    vcin = vc.pin("1")
    W((vcin[0] - 10.16, vcin[1]), vcin)
    W((vcin[0] - 10.16, vcin[1]), (vcin[0] - 10.16, y_vc), (xob, y_vc))
    label(vcin[0] - 8.89, vcin[1], "VC", size=1.0)
    xv, yv2 = vc.pin("4"); W((xv, yv2), (xv, yv2 - 5.08)); flag("+3V3_OSC", xv, yv2 - 5.08)
    W((xv, yv2 - 2.54), (xv + 7.62, yv2 - 2.54)); J(xv, yv2 - 2.54)
    down("C 100nF", xv + 7.62, yv2 - 2.54, text="right")
    gx, gy = vc.pin("2"); W((gx, gy), (gx, gy + G)); gnd(gx, gy + G)
    note(vcin[0] - 20, ys + 14, "25 MHz VCXO (SX3V): +-100 ppm over 0.3-3.0 V = +-580 kHz at 5.8 GHz, 15 kHz modulation bandwidth.  "
         "The loop's VCO.  Same pads as the TX TCXO.", cols=30)
    vout = vc.pin("3")
    sig(vout[0] + 10, ys + 4, LV.txt("REF_RX"), cols=16)
    # REF OUT: the VCXO's 25 MHz buffered to an MMCX, for the TX synthesizer's REF IN (a coherent transponder)
    rb = part("LVC1G17", "U116", vcin[0] - 10.16, ys + 38.1)       # under the VCXO, clear of the synthesizer's loop filter
    p2 = rb.pin("2")
    yin = p2[1]
    J(*vout)
    W(vout, (vout[0], yin - 17.78), (p2[0] - 5.08, yin - 17.78), (p2[0] - 5.08, yin), p2)
    vp, vm = rb.pin("5"), rb.pin("3")
    W(vp, (vp[0], vp[1] - 5.08)); flag("+3V3_DIG", vp[0], vp[1] - 5.08)
    W((vp[0], vp[1] - 2.54), (vp[0] + 7.62, vp[1] - 2.54)); J(vp[0], vp[1] - 2.54)
    down("C 100nF", vp[0] + 7.62, vp[1] - 2.54, text="right")
    W(vm, (vm[0], vm[1] + G)); gnd(vm[0], vm[1] + G)
    o = stub(rb, "4", dx=5.08)
    B.tap(o[0], o[1], "REF OUT", rkey="R 33R", text=LV.txt("REF_OUT") + ".  An MMCX-to-SMA lead to the TX sheet's REF IN "
          "(JP201 to REF IN) locks our carrier to the one we receive: the one-antenna T/R mode needs it (sheet 5).")
    pll, lo = B.synthesizer("U115", vout[0] + 109.22, ys + 5.08, "+3V3_PLL_RX", "LE_PLL_RX", "MUX_RX", "LO_RX", "LO RX MON", vout)
    # LO pair up to the demodulator: two verticals in the corridor left of the chip
    lp, ln = lo["lo_p"], lo["lo_n"]
    W(lp, (lo_top["p"][0], lp[1]), lo_top["p"])
    W(ln, (lo_top["n"][0], ln[1]), lo_top["n"])
    label(lp[0] + 1.27, lp[1], "LO_RX_P", size=1.0)
    label(ln[0] + 1.27, ln[1], "LO_RX_N", size=1.0, justify="left top")
    note(vout[0] + 20, ys - 34, "RX synthesizer: MAX2871, 5.8 GHz integer-N from the 25 MHz VCXO (N = 232), RFOUTA differential into the ADL5380's LO (0 dBm), "
         "RFOUTB to the LO RX MON jack.  Its own LDO, +3V3_PLL_RX.  The Costas loop steers the VCXO, so this whole synthesizer is the loop's VCO.", cols=52)

    # ---- the DAC and the ADC (right of the loop) ------------------------------------------
    xd = 449.58                                 # left of the loop's summing-node column (xbn) and its corridors
    dac = part("MCP4728", "U113", xd, y0 + 68.58)
    for n, name in (("2", "I2C_SCL"), ("3", "I2C_SDA")):
        e = stub(dac, n, dx=-12.7); S.hlabel(e[0], e[1], name, shape="bidirectional", rot=180)
    e = stub(dac, "4", dx=-5.08); W(e, (e[0], e[1] + G)); gnd(e[0], e[1] + G)
    S.nc(*dac.pin("5"))
    for n, name in (("6", "VR_I"), ("7", "VR_Q")):
        e = stub(dac, n, dx=12.7); S.hlabel(e[0], e[1], name, shape="output", rot=0)
    B.supply_bar(dac, ["1"], "+3V3_DIG", dy=10.16)
    B.bottom_gnd(dac, ["10"])
    ybot = dac.pin("10")[1] + 2.54
    # V_T (C): down the DAC's right side, under it, right and up a corridor east of the loop, then
    # left under the comparators and up into their inverting inputs
    e = stub(dac, "8", dx=10.16)                # C: the fast Q arm's offset trim (Response 14; it was V_T, now on sheet 7's 16-bit DAC)
    label(e[0], e[1], "Q_OFF_F", size=1.0)
    # VC_OFF (D): under the DAC and left to R4, which stands under op amp B's summing node
    vo = stub(dac, "9", dx=2.54)
    W(vo, (vo[0], ybot + 17.78), (xbn, ybot + 17.78), (xbn, r4bot[1]))
    label(vo[0] + 2.54, ybot + 17.78, "VC_OFF", size=1.0)
    sig(vo[0] + 2.54, ybot + 19.8, LV.txt("VC_OFF"), cols=30)
    sig(xd + 22, y0 + 50, LV.txt("DAC"), cols=30)
    sig(xd + 22, y0 + 136, LV.txt("ADC"), cols=30)
    note(xd - 30, y0 + 90, "MCP4728 (I2C 0x60): A = VR_I, B = VR_Q (the TX ladders' references, 0.21 V: amplitude and carrier null), C = Q_OFF_F (the fast Q arm's offset trim, through 100 k), "
         "D = VC_OFF (a frequency offset / acquisition sweep).", cols=36)
    adc = part("ADS1115", "U114", xd, y0 + 127.0)
    for n, name in (("10", "I2C_SCL"), ("9", "I2C_SDA")):
        e = stub(adc, n, dx=12.7); S.hlabel(e[0], e[1], name, shape="bidirectional", rot=0)
    e = stub(adc, "1", dx=-5.08); W(e, (e[0], e[1] + G)); gnd(e[0], e[1] + G)
    S.nc(*adc.pin("2"))
    # four RC inputs: the resistor between the source and the capacitor, the capacitor at the pin (sch_blocks.adc_inputs)
    B.adc_inputs(adc, (("4", "I_P"), ("5", "Q_P"), ("6", "VC"), ("7", "ERR")))
    B.supply_bar(adc, ["8"], "+3V3_DIG", dy=10.16)
    B.bottom_gnd(adc, ["3"])
    note(xd + 20, y0 + 110, "ADS1115 (I2C 0x48, 860 SPS): the averaged I and Q (lock = I large, Q small), VC (how far the VCXO is pulled) and the loop error.  "
         "Its four inputs are the nets named at the taps above (I_P, Q_P, VC, ERR).", cols=36)
    rf_blocks(*balun_pair)
    sel_pulldown(sel)
    return S


def sel_pulldown(sel):
    """A 100 k from the sign switch's S input to ground (Prompt 32): with JP103 unfitted the CMOS select
    floated (review A's note A8).  Low = B1 = the Q- jumper's side, the same as the comparator at rest.
    Drawn last so the sheet's resistor references do not move."""
    xs, ys = sel[0], sel[1] + 5.08
    J(xs, ys); W((xs, ys), (xs + 7.62, ys))
    down("R 100k", xs + 7.62, ys, text="right")
