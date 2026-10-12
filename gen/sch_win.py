"""The window comparators (sheet 7, A3; Response 14).  Four TLV3603 tell an event and its message
from the idle, each against its own 16-bit threshold.  QP and QN read the Q arm (until Response 14
they sat on sheet 3 against one shared 12-bit threshold); IP and IN are new and read the I arm, so
the board can run every window scheme of PLAN.md section 18: the plan's corners, the Q step, a
BPSK flip decided beside the idle instead of at zero, and the pilot at 45 degrees with the four
corners (each message moves one comparator).  The AD5696R (I2C 0x0C, internal 2.5 V reference)
sets the four thresholds in 0.038 mV steps, which the FPGA's false-event count servoes.  Each
comparator's LE/HYS pin has two DNP footprints: 0 ohm to the rail (no hysteresis) and 150 k to
ground (30 mV); both empty is 3 mV.  Each output has a 453 ohm tap to a U.FL (/10 into 50 ohm) for
the scope, beside its 33 ohm line to the FPGA.  References 601-699.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
sys.path.insert(0, HERE)
import sch_util as U
from sch_util import (G, part, gnd, flag, W, J, label, note, title, nref, down, up, series, tp, sig)
import sch_blocks as B
from sch_blocks import stub
import levels as LV
import pins as PINS

# (name, the arm signal on IN+, the threshold on IN-, the FPGA line, reference)
ROWS = (("IP", "I_P", "V_TIP", "CMP_IP", "U603"), ("IN", "I_N", "V_TIN", "CMP_IN", "U604"),
        ("QP", "Q_P", "V_TQP", "CMP_QP", "U601"), ("QN", "Q_N", "V_TQN", "CMP_QN", "U602"))
X_IN = 38.1          # the input labels, at the sheet's left
X_CMP = 160.02       # the comparators' column
Y0, DY = 78.74, 45.72


def window(S, name, inp, vt, out, ref, x, y):
    c = B.comparator(ref, x, y, kind="TLV3603")
    ip = c.pin("3")
    S.hlabel(X_IN, ip[1], inp, shape="input", rot=180)
    W((X_IN, ip[1]), ip)
    e = stub(c, "4", dx=-10.16)
    label(e[0] - 1.27, e[1], vt, size=1.0, justify="right bottom")
    W(e, (e[0] - 1.27, e[1]))
    o = c.pin("1")
    xo = o[0] + 15.24
    W(o, (xo, o[1]))
    J(xo, o[1])
    ra, rb = series(LV.VAL["cmp_series"], xo + 7.62, o[1])
    W((xo, o[1]), ra)
    W(rb, (xo + 20.32, o[1]))
    S.hlabel(xo + 20.32, o[1], out, shape="output", rot=0)
    W((xo, o[1]), (xo, o[1] + 12.7))
    B.tap(xo, o[1] + 12.7, name + " MON", rkey=LV.VAL["tap_R"])
    return c


def build(S):
    U.begin(S, ref_base=600)
    title(20, 18, "Window comparators: I and Q, each side against its own 16-bit threshold")
    note(20, 24, "PLAN.md section 18 scores the ways an idle plus N messages can be decided by comparators.  These four do the window "
         "schemes: an event is the arm leaving a window round the idle, and which side it leaves by is the message.  Thresholds are set "
         "from the idle, 7.3 sigma out for one false event an hour, by the FPGA counting each comparator's false events and servoing its "
         "threshold (the AD5696R's 0.038 mV steps change that rate by 10 %% a step in the lab; the old 12-bit DAC's by x7.6).  With the "
         "transmitter's pilot at 45 degrees the four corners land on +I, -I, +Q and -Q, one comparator each: the event and both bits on "
         "one edge.  With the plan's full idle on +I, QP and QN give the event and the Q bit and CMP_I (sheet 3) the I bit.  "
         "Each output: 33 ohm to the FPGA (header %s) and 453 ohm to a U.FL (/10 into 50 ohm) for the scope, which sees 50-300 ps of "
         "jitter the FPGA's 1-2 ns sampling cannot."
         % ", ".join("%d" % PINS.SIGNALS[r[3]] for r in ROWS), cols=120)
    note(20, 46, LV.LEGEND, cols=120)
    for k, (name, inp, vt, out, ref) in enumerate(ROWS):
        window(S, name, inp, vt, out, ref, X_CMP, Y0 + DY * k)
    sig(X_IN + 4, Y0 - 12, LV.txt("I_ARM"), cols=40)
    sig(X_IN + 4, Y0 + 2 * DY - 12, LV.txt("Q_ARM"), cols=40)
    note(X_CMP - 30, Y0 + 4 * DY - 14, "LE/HYS (each comparator): both DNP = 3 mV of hysteresis (the TLV3601's); fit the 0 ohm = 0 mV, "
         "the sharpest edge; fit the 150 k = 30 mV (56 k = 60 mV), for slow or noisy edges.  Driving the pin low latches the output.", cols=60)

    # ---- the thresholds: AD5696R, address 0x0C (A1 = A0 = 0), outputs update on each write (LDAC low),
    # span 0-2.5 V (GAIN low), power-up at midscale 1.25 V (RSTSEL high) ----
    xd, yd = 337.82, 121.92
    dac = part("AD5696R", "U605", xd, yd)
    for n, name in (("8", "I2C_SDA"), ("13", "I2C_SCL")):
        e = stub(dac, n, dx=-12.7)
        S.hlabel(e[0], e[1], name, shape="bidirectional", rot=180)
    for n, vt in (("3", "V_TQP"), ("2", "V_TQN"), ("6", "V_TIP"), ("7", "V_TIN")):
        e = stub(dac, n, dx=10.16)
        label(e[0], e[1], vt, size=1.0)
    U.S.nc(*dac.pin("1"))
    B.supply_bar(dac, ["5", "11", "15", "16"], "+3V3_DIG", dy=10.16, side_caps=2, caps_side="right")
    B.bottom_gnd(dac, ["4", "9", "10", "12", "14"])
    note(xd - 30, yd + 30, "AD5696R (I2C 0x0C): A = V_TQP, B = V_TQN, C = V_TIP, D = V_TIN.  16 bits on its own 2.5 V reference "
         "(0.038 mV a step); GAIN low: 0-2.5 V, round the arms' 1.65 V centre.  It powers up at midscale (1.25 V), where all four "
         "comparators read high until the FPGA writes them.  VREF is the internal reference's output, unused.  The A grade: the "
         "threshold servo absorbs its INL and its reference's drift.", cols=44)
    return S
