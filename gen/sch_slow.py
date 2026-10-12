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
from sch_util import (G, part, gnd, flag, W, J, label, note, title, nref, down, up, series, tp, sig)
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
    return S
