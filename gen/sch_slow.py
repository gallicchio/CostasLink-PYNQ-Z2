"""The slow-path sheet (A3): the receiver's two arm outputs (I_P/I_N, Q_P/Q_N, from sheet 3)
through a second THS4541 stage at gain 20 and a 4.8 MHz pole into three more comparators, whose
outputs (CMP_I_S, CMP_QP_S, CMP_QN_S) reach the FPGA on header pins 40, 32 and 28; a second
MCP4728 (address 0x61) gives this path its own Q-window threshold and two offset trims.  The fast
path (sheet 3) flags a bit as its 100 MHz arm crosses; this path, 14 dB more sensitive and 37 ns later, confirms
or vetoes it, so a false alarm becomes a discarded trial instead of a wrong bit (Prompt 6).
References 501-599.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import sch_util as U
from sch_util import (G, part, gnd, flag, W, J, label, note, title, nref, down, up, series, tp, sig, diode, vpart)
import sch_blocks as B
from sch_blocks import stub, L
import levels as LV


def build(S):
    U.begin(S, ref_base=500)
    title(20, 18, "Slow path: the same decisions %.0f dB more sensitive and %.0f ns later, to confirm or veto the fast ones"
          % (LV.B["floor_fast_dBm"] - LV.B["noise_floor_slow_dBm"] - 11.4, LV.B["slow_t50_ns"]))
    note(20, 24, "The fast arms (sheet 3) decide in %.1f ns on %.0f MHz of bandwidth and read down to %.0f dBm; this path takes their outputs, "
         "multiplies by %.0f and filters to %.1f MHz, so it reads down to %.0f dBm (noise-limited: %.1f MHz of noise, SNR 11.4 dB for a quiet BPSK "
         "decision) and decides %.0f ns later.  The gateware acts on the fast flag at once and keeps the trial only if the slow comparators "
         "agree: a false alarm costs a trial, not a wrong bit.  The far end must hold a symbol at least %.0f ns for this path to see it "
         "(BPSK: the flipped phase simply persists).  Offsets: two THS4541s in cascade x%.0f can sit up to %.0f mV off; DAC2's I_OFF / Q_OFF "
         "null them (watch the slow comparators' duty cycle with no signal)."
         % (350.0 / LV.B["B_MHz"] * 0.5, LV.B["B_MHz"], LV.B["floor_fast_dBm"], LV.B["G_slow"], LV.B["slow_fpole_MHz"],
            LV.B["noise_floor_slow_dBm"] + 11.4, LV.B["B_slow_MHz"], LV.B["slow_t50_ns"], LV.B["slow_rise_ns"], LV.B["G_slow"], LV.B["slow_vos_mV"]), cols=120)
    note(20, 38, LV.LEGEND, cols=120)

    x0 = 30.48
    arms = {}
    for k, (name, yrow, ref) in enumerate((("I", 88.9, "U501"), ("Q", 165.1, "U502"))):
        hp, lp = (x0, yrow), (x0, yrow + 2.54)
        S.hlabel(hp[0], hp[1], name + "_P", shape="input", rot=180)
        S.hlabel(lp[0], lp[1], name + "_N", shape="input", rot=180)
        p, n = B.arm(S, name + "s", ref, hp, lp, yrow + 5.08, x0 + 71.12, LV.VAL["slow_Rf"], rg_key=LV.VAL["slow_Rg"], shunts=False,
                     out_rc=(LV.VAL["slow_Rrc"], LV.VAL["slow_Crc"]), trim=name + "_OFF", out_tap=name + " SLOW MON")
        arms[name] = (p, n)
        sig(hp[0] + 2, yrow + 32, LV.txt("I_SLOW") if name == "I" else LV.txt("Q_SLOW"), cols=40)
    note(x0 + 71.12 + 70, 88.9 + 5.08 + 30, LV.SLOW_ARM_NOTE, cols=38)
    # the I comparator: sign(I slow)
    ip, inn_ = arms["I"]
    ci = B.comparator("U503", ip[0] + 38.1, ip[1] + 7.62)
    W(ip, (ip[0] + 10.16, ip[1]), (ip[0] + 10.16, ci.pin("3")[1]), ci.pin("3"))
    W(inn_, (inn_[0] + 5.08, inn_[1]), (inn_[0] + 5.08, ci.pin("4")[1]), ci.pin("4"))
    co = ci.pin("1")
    W(co, (co[0] + 5.08, co[1]))
    ra, rb = series("R 33R", co[0] + 8.89, co[1]); W(rb, (co[0] + 20.32, co[1]))
    S.hlabel(co[0] + 20.32, co[1], "CMP_I_S", shape="output", rot=0)
    # the Q window: Q_sP > V_T2 and Q_sN > V_T2
    qp, qn = arms["Q"]
    cqp = B.comparator("U504", qp[0] + 38.1, qp[1] + 2.54)
    cqn = B.comparator("U505", qp[0] + 38.1, qp[1] + 33.02)
    xq = qp[0] + 10.16
    W(qp, (xq, qp[1])); J(xq, qp[1])
    W((xq, qp[1]), (xq, cqp.pin("3")[1]), cqp.pin("3"))
    xq2 = qn[0] + 5.08
    W(qn, (xq2, qn[1])); J(xq2, qn[1])
    W((xq2, qn[1]), (xq2, cqn.pin("3")[1]), cqn.pin("3"))
    vt_x = cqp.pin("4")[0] - 7.62
    W(cqp.pin("4"), (vt_x, cqp.pin("4")[1]))
    W(cqn.pin("4"), (vt_x, cqn.pin("4")[1]))
    W((vt_x, cqp.pin("4")[1]), (vt_x, cqn.pin("4")[1]))
    J(vt_x, cqp.pin("4")[1])
    label(vt_x, cqp.pin("4")[1] + 2.54, "V_T2", size=1.0)
    for c, name in ((cqp, "CMP_QP_S"), (cqn, "CMP_QN_S")):
        o = stub(c, "1", dx=5.08)
        ra, rb = series("R 33R", o[0] + 3.81, o[1]); W(rb, (o[0] + 12.7, o[1]))
        S.hlabel(o[0] + 12.7, o[1], name, shape="output", rot=0)
    sig(co[0] + 10, co[1] - 24, LV.txt("CMP_S"), cols=34)
    # DAC2: V_T2, I_OFF, Q_OFF, a spare on a test point
    xd, yd = 300.0, 215.9
    dac = part("MCP4728A1", "U506", xd, yd)
    for n, name in (("2", "I2C_SCL"), ("3", "I2C_SDA")):
        e = stub(dac, n, dx=-12.7); S.hlabel(e[0], e[1], name, shape="bidirectional", rot=180)
    e = stub(dac, "4", dx=-5.08); W(e, (e[0], e[1] + G)); gnd(e[0], e[1] + G)
    S.nc(*dac.pin("5"))
    for n, name in (("6", "V_T2"), ("7", "I_OFF"), ("8", "Q_OFF")):
        e = stub(dac, n, dx=12.7); label(e[0], e[1], name, size=1.0)
    e = stub(dac, "9", dx=12.7)                               # D: through 100 k into the fast I arm's summing node (sheet 3)
    label(e[0] - 5.08, e[1], "I_OFF_F", size=1.0)
    ra, rb = series("R 100k", e[0] + 8.89, e[1], above=False)
    W(e, ra); W(rb, (rb[0] + 5.08, rb[1]))
    S.hlabel(rb[0] + 5.08, rb[1], "I_SUM", shape="output", rot=0)
    B.supply_bar(dac, ["1"], "+3V3_DIG", dy=10.16)
    B.bottom_gnd(dac, ["10"])
    sig(xd + 36, yd - 34, LV.txt("DAC2"), cols=34)
    note(xd - 40, yd + 20, "MCP4728A1: the same DAC as sheet 3's at the factory-preset address 0x61 (no address programming).  V_T2 sets this path's "
         "Q window; I_OFF / Q_OFF reach the slow stages' summing nodes through 100 k; D = I_OFF_F does the same for the FAST I arm "
         "on sheet 3 through the 100 k here (its summing node I_SUM comes from that sheet).  Write all four EEPROM defaults to mid-scale (1.65 V) once, so power-up injects no offset.", cols=36)
    detectors(S)
    return S


def detectors(S):
    """The interference detectors (Prompt 28): a log amp on the fast Q arm (the link's whole band),
    its output averaged by an ADC and peak-held for WiFi's bursts; +5V_RF's level; the board's
    temperature; a second ADS1115 (0x49) reads all four on the I2C bus the board already has, so no
    FPGA pin is needed.  Drawn in the A2 sheet's lower band."""
    X0, Y0 = 50.8, 304.8
    title(X0, Y0 - 12.7, "Interference detectors: the link band's level and its bursts, +5V_RF, the temperature (Prompt 28)", size=1.6)
    # ---- the log amp: Q_P / Q_N through 1 k and 10 nF into the AD8310 (inputs biased inside) ----
    la = part("AD8310", "U507", X0 + 66.04, Y0 + 30.48)
    for pin, name, above in ((la.pin("8"), "Q_P", True), (la.pin("1"), "Q_N", False)):
        ca, cb = series("C 10nF", pin[0] - 10.16, pin[1], above=above)
        W(cb, pin)
        ra, rb = series("R 1k", pin[0] - 25.4, pin[1], above=above)
        W(rb, ca)
        W(ra, (ra[0] - 7.62, pin[1]))
        S.hlabel(ra[0] - 7.62, pin[1], name, shape="input", rot=180)
    B.supply_bar(la, ["5", "7"], "+5V_RF", dy=10.16)
    # COMM to ground; OFLT's 1 nF (the offset loop's corner, 2 MHz -> ~65 kHz); BFIN's 390 pF out to the
    # right (the video bandwidth, 25 MHz -> ~135 kHz: a burst's power, not the noise's every flicker)
    B.bottom_gnd(la, ["2"])
    down("C 1nF", la.pin("3")[0], la.pin("3")[1], drop=5.08, text="right")
    bf = stub(la, "6", dy=G)
    W(bf, (bf[0] + 12.7, bf[1])); down("C 390pF", bf[0] + 12.7, bf[1], text="right")
    vo = la.pin("4")
    # ---- the peak hold: OPA2388 A charges 10 nF through the diode inside its loop, B buffers it; 4.7 M bleeds it ----
    oa = part("OPA2388", "U508", X0 + 132.08, Y0 + 30.48 + 2.54, unit=1)
    inp, inn, out = oa.pin("3"), oa.pin("2"), oa.pin("1")
    W(vo, (inp[0] - 25.4, vo[1]), (inp[0] - 25.4, inp[1]), inp)
    label(vo[0] + 2.54, vo[1], "LOG_Q", size=1.0)
    xt = inp[0] - 15.24
    J(xt, inp[1]); W((xt, inp[1]), (xt, inp[1] - 10.16)); tp(xt, inp[1] - 10.16, "LOG Q")
    ra2, rb2 = series("R 10k", inn[0] - 12.7, inn[1], above=False)
    W(rb2, inn)
    W(ra2, (ra2[0] - 5.08, inn[1])); label(ra2[0] - 5.08, inn[1], "PEAK_Q", size=1.0)
    xn = inn[0] - 2.54
    J(xn, inn[1])
    yc = inn[1] + 10.16
    cl, cr = series("C 100pF", (xn + out[0] + 2.54) / 2.0, yc, above=False)
    W((xn, inn[1]), (xn, yc), cl)
    W(cr, (out[0] + 2.54, yc), (out[0] + 2.54, out[1]))
    J(out[0] + 2.54, out[1])
    an, ca_ = diode("1N4148W", "D501", out[0] + 10.16, out[1])
    W(out, an)
    ra, rb = series("R 100R", ca_[0] + 7.62, out[1])
    W(ca_, ra)
    xh = rb[0] + 5.08
    W(rb, (xh + 10.16, out[1]))
    J(xh, out[1]); down("C 10nF", xh, out[1], text="left")
    J(xh + 10.16, out[1]); down("R 4.7M", xh + 10.16, out[1], text="right")
    W((xh + 10.16, out[1]), (xh + 20.32, out[1]))
    label(xh + 20.32, out[1], "PEAK_HOLD", size=1.0)
    ob = part("OPA2388", "U508", X0 + 236.22, Y0 + 30.48 + 2.54, unit=2)
    e = stub(ob, "5", dx=-10.16); label(e[0], e[1], "PEAK_HOLD", size=1.0)
    bo, bn = ob.pin("7"), ob.pin("6")
    yf = bn[1] + 7.62
    W(bo, (bo[0] + 2.54, bo[1])); J(bo[0] + 2.54, bo[1])
    W((bo[0] + 2.54, bo[1]), (bo[0] + 2.54, yf), (bn[0] - 2.54, yf), (bn[0] - 2.54, bn[1]), bn)
    W((bo[0] + 2.54, bo[1]), (bo[0] + 12.7, bo[1])); label(bo[0] + 12.7, bo[1], "PEAK_Q", size=1.0)
    pw = part("OPA2388", "U508", X0 + 274.32, Y0 + 33.02, unit=3, text="right")
    B.supply_bar(pw, ["8"], "+3V3_ANA", dy=7.62, caps_side="left")
    B.bottom_gnd(pw, ["4"])
    note(X0 + 4, Y0 + 52, "AD8310 on the fast Q arm: the link's whole band (+-94 MHz round the carrier), 95 dB, 24 mV/dB; LOG_Q is "
         "a burst's envelope (BFIN ~135 kHz).  1 k + 1 k against its 1 k input: a third of the arm (its thermal noise ~0.8 mV, "
         "-62 dBV, 29 dB over the log amp's floor).  A scope on the LOG Q pad shows WiFi's frames.", cols=48)
    note(X0 + 112, Y0 + 52, "Peak hold of LOG_Q (Jason: a slowly decaying peak for WiFi's bursts beside a truer level).  A charges "
         "10 nF through the diode inside its loop (no diode drop), B reads it, 4.7 M lets it fall in 47 ms, so a 20 us frame "
         "still reads at the ADC a few conversions later.  The link's own events lift it too: read it in a pause.", cols=48)

    # ---- +5V_RF through 10 k / 10 k: the rail the ADL5380, ADL5375 and gain blocks need at 4.75-5.25 V (Prompt 28:
    # the LTC1968 true-RMS converter this channel was drawn for left rev A: over Jason's $25-35 a board, and the
    # router could not finish its lines in the arms' corner; the comparator survey measures the slow band) ----
    xv, yv = X0 + 337.82, Y0 + 30.48
    up("R 10k", xv, yv, "+5V_RF", text="right")
    down("R 10k", xv, yv, text="right")
    W((xv, yv), (xv - 10.16, yv)); label(xv - 10.16, yv, "V5_MON", size=1.0, justify="right bottom")
    note(X0 + 300, Y0 + 56, "AIN2: +5V_RF / 2.  The ADL53xx and the ADL5611s want 4.75-5.25 V; on a roof's long supply "
         "lead this says so before the link does.  (The LTC1968 true-RMS converter drawn here first is a rev B option: "
         "PLAN.md section 19.)", cols=40)

    # ---- the second ADC (0x49: ADDR to VDD): LOG_Q, PEAK_Q, V5_MON, TEMP ----
    adc = part("ADS1115", "U510", X0 + 472.44, Y0 + 30.48)
    for n, name in (("10", "I2C_SCL"), ("9", "I2C_SDA")):
        e = stub(adc, n, dx=12.7); S.hlabel(e[0], e[1], name, shape="bidirectional", rot=0)
    e = stub(adc, "1", dx=5.08); W(e, (e[0], e[1] + 5.08)); flag("+3V3_DIG", e[0], e[1] + 5.08, rot=180)
    S.nc(*adc.pin("2"))
    for k, (n, name) in enumerate((("4", "LOG_Q"), ("5", "PEAK_Q"), ("6", "V5_MON"), ("7", "TEMP"))):
        px, py = adc.pin(n)
        ra, rb = series("R 10k", px - 10.16 - 10.16 * (3 - k), py); W(rb, (px, py))
        x0 = px - 55.88 + 10.16 * k
        W((x0, py), ra)
        label(x0, py, name, size=1.0)
        J(x0 + 2.54, py); down("C 100nF", x0 + 2.54, py, text="right")
    B.supply_bar(adc, ["8"], "+3V3_DIG", dy=10.16)
    B.bottom_gnd(adc, ["3"])
    # the board's temperature: 10 k from 3.3 V over a 10 k NTC (B 3380): 1.65 V at 25 C, 0.76 V at 60 C
    xt, yt = X0 + 500.38, Y0 + 50.8
    up("R 10k", xt, yt, "+3V3_DIG", text="right")
    t, b = vpart("NTC10K", "TH501", xt, yt + G + 3.81, text="right", ref_at=(xt + 4.2, yt + G + 3.5), val_at=(xt + 4.2, yt + G + 4.1))
    W((xt, yt), t); gnd(*b)
    W((xt, yt), (xt - 10.16, yt)); label(xt - 10.16, yt, "TEMP", size=1.0, justify="right bottom")
    note(X0 + 412, Y0 + 56, "ADS1115 (I2C 0x49, ADDR to VDD): AIN0 LOG_Q (its conversion averages the log: 1.2 ms at 860 SPS, "
         "125 ms at 8 SPS), AIN1 PEAK_Q, AIN2 V5_MON (+5V_RF / 2), AIN3 TEMP (a 10 k NTC under 10 k from 3.3 V).  The driver's detectors() "
         "reads them; nothing new on the FPGA's header.", cols=40)
