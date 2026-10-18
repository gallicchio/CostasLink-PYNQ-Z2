"""The antenna-switch sheet (A3): one HMC536 T/R switch between an ANT jack and two jacks that the
user cables to the TX ANT and RX ANT jacks (or to the external PA and LNA), so one antenna serves
both directions in time (TDD).  Its two controls come from the FPGA (header pins 27/28, also on
J303 for an external switch module).  Leave the block unfitted and cable each direction to its
own antenna: the four panels do exactly that for one link.  References 401-499.

Why this switch (PLAN.md section 4): 15 ns rise, 30 ns on/off, 0/3.3 V control straight from the
FPGA, +29 dBm, MSOP-8 (hand-solderable), in JLCPCB's stock.  Its 27 dB isolation is enough for
TDD (the receiver is not listening while we transmit) but not for sharing an antenna in frequency.
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
    U.begin(S, ref_base=400)
    title(20, 18, "Antenna switch: one antenna shared by TX and RX in time (T/R), 30 ns")
    note(20, 24, "Fit this block to work with ONE antenna per board: connect the antenna to ANT and run two short SMA leads, TX ANT -> SW TX and "
         "SW RX -> RX ANT (1 ns each), and let the FPGA drive TR_A / TR_B (B = not A): A HIGH, B low = receive (ANT to RF2 = SW RX); A low, B high = transmit (ANT to RF1 = SW TX).  "
         "Without this block, two antennas per board and two frequencies 600 MHz apart: both carriers always on, no holds, no turnaround.  "
         "How a pair keeps its frequency with one antenna each: the VERIFIER transmits on its TCXO (JP201 on TCXO) and the PROVER's Costas loop "
         "locks its VCXO to that carrier; the prover's TX synthesizer runs from that VCXO (REF OUT -> REF IN, JP201 on REF IN: a transponder), "
         "so its reply is at the verifier's own frequency and phase.  While either board transmits its loop HOLDs (LOOP_HOLD, a sample-and-hold "
         "on the integrator: 0.1 rad after 6 ms typical), and when it listens again the carrier it hears is the one it was locked to, so the loop "
         "resumes instead of re-acquiring (3.8 ms from 30 kHz off).  ONE board carries the lead: both with it would be a ring of two VCXOs with "
         "no reference, wandering together to a rail.  sim/budget.py section 2b and PLAN.md section 14 have the numbers.", cols=120)

    y = 101.6
    sw = U.part_at_pin("HMC536", "U401", "3", 139.7, y)          # RFC at (139.7, y)
    rfc, rf1, rf2 = sw.pin("3"), sw.pin("5"), sw.pin("8")
    S.nc(*sw.pin("4"))
    B.bottom_gnd(sw, ["6", "7", "9"])
    # ANT at the left through a DC block
    j = part("SMA", "J401", rfc[0] - 45.72, y, rot=0, mirror="y", value="ANT", text="hide")     # pin facing the line (Prompt 35)
    jx, jy = j.pin("1")
    s2 = j.pin("2"); W(s2, (s2[0], s2[1] + G)); gnd(s2[0], s2[1] + G)
    B.dcblock(jx, y, rfc[0])
    B.esd_shunt(jx + 2.54, y, text="right")        # Prompt 28 (texts away from the jack)
    sig(jx - 12, y - 28, "ANT, the antenna: " + LV.txt("ANT"), cols=26)
    # RF1 (SW TX) up and right, RF2 (SW RX) down and right, each through a DC block to its jack
    for p, dy, ref, name, txt in ((rf1, -20.32, "J402", "SW TX", LV.txt("SW_TX")), (rf2, 20.32, "J403", "SW RX", LV.txt("SW_RX"))):
        xk = p[0] + 7.62
        yk = p[1] + dy
        W(p, (xk, p[1]), (xk, yk))
        x1 = xk + 30.48
        B.dcblock(xk, yk, x1)
        jk = part("SMA", ref, x1 + 12.7, yk, rot=0, value=name, text="hide")      # rot 0: the pin faces the line, the ground hangs below (Prompt 35)
        W((x1, yk), jk.pin("1"))
        sh = jk.pin("2"); W(sh, (sh[0], sh[1] + G)); gnd(sh[0], sh[1] + G)
        sig(x1 + 18, yk - 4 + (0 if dy > 0 else -8), txt, cols=30)
    # controls: A and B down from the chip, left through 100 ohm (the datasheet's evaluation board) to the FPGA lines
    a, b = sw.pin("1"), sw.pin("2")
    tr = {}
    for p, name, drop, pull_key, pull_rail in ((a, "TR_A", 7.62, "R 10k", "+3V3_DIG"), (b, "TR_B", 15.24, "R 10k", None)):
        yc = p[1] + drop
        W(p, (p[0], yc))
        xr = p[0] - 20.32
        ra, rb = series("R 100R", xr + 10.16, yc, above=False)
        W(rb, (p[0], yc))
        W((xr - 10.16, yc), ra)
        J(xr - 10.16, yc)
        if pull_rail:
            up(pull_key, xr - 10.16, yc, pull_rail, text="left")
        else:
            down(pull_key, xr - 10.16, yc, text="left")
        W((xr - 10.16, yc), (xr - 25.4, yc))
        tr[name] = (xr - 25.4, yc)
        if name == "TR_A":
            S.hlabel(xr - 25.4, yc, name, shape="input", rot=180)
        if pull_rail:                                                  # TR A's jack hangs off here (drawn last: late_taps)
            tr_tap = (xr - 2.54, yc)
    # TR_B = not TR_A, made here (Response 14): the header pin that carried TR_B now carries a comparator.
    # A 74LVC1G04 from TR_A's line drives TR_B's: at reset TR_A rests high (the pull-ups), so B rests low
    # and the switch rests in receive on both hosts.
    (xa, ya), (xb, yb) = tr["TR_A"], tr["TR_B"]
    inv = part("LVC1G04", "U402", xa - 20.32, yb, rot=0)
    ia, iy = inv.pin("2"), inv.pin("4")
    W((xa, ya), (xa - 30.48, ya)); J(xa, ya)
    W((xa - 30.48, ya), (xa - 30.48, ia[1]), ia)
    W(iy, (xb, iy[1])) if abs(iy[1] - yb) < 0.01 else W(iy, (iy[0] + 2.54, iy[1]), (iy[0] + 2.54, yb), (xb, yb))
    label(xb - 2.54, yb, "TR_B", size=1.0, justify="right bottom")
    vcc, gnd_ = inv.pin("5"), inv.pin("3")
    W(vcc, (vcc[0], vcc[1] - 5.08)); flag("+3V3_DIG", vcc[0], vcc[1] - 5.08)
    W((vcc[0], vcc[1] - 2.54), (vcc[0] + 7.62, vcc[1] - 2.54)); J(vcc[0], vcc[1] - 2.54)
    down("C 100nF", vcc[0] + 7.62, vcc[1] - 2.54, text="right")
    W(gnd_, (gnd_[0], gnd_[1] + G)); gnd(gnd_[0], gnd_[1] + G)
    U.S.nc(*inv.pin("1"))
    # J303: TR_A, TR_B and ground, for an external switch module
    jh = part("HDR1x3", "J303", xa - 30.48, yb + 30.48, rot=0, value="TR", text="hide")
    for i, net in enumerate(["TR_A", "TR_B", "GND"]):
        p = jh.pin(str(i + 1))
        if net == "GND":
            W(p, (p[0] - 5.08, p[1])); W((p[0] - 5.08, p[1]), (p[0] - 5.08, p[1] + G)); gnd(p[0] - 5.08, p[1] + G)
        else:
            W(p, (p[0] - 10.16, p[1])); label(p[0] - 10.16, p[1], net, size=1.0, justify="right bottom")
    note(xa - 60, yb + 46, "J303: TR_A, TR_B and ground for an external switch module (B made here by U402).", cols=30)
    sig(a[0] - 70, b[1] + 27, LV.txt("TR"), cols=38)
    note(a[0] - 70, b[1] + 56, "TR_A / TR_B: 0 / 3.3 V; A from the FPGA (header 27, also J303), B = not A from U402 (since Response 14).  Truth table (datasheet): A low, B high: ANT-RF1 = SW TX (transmit).  "
         "A high, B low: ANT-RF2 = SW RX (receive): A's pull-ups (10 k here, 2k2 on the PYNQ) hold A high until the gateware drives it, "
         "so B rests low and the switch rests in receive on both hosts.  30 ns from the edge to the RF settled; 15 ns rise; U402 adds about 3 ns to B.", cols=60)
    note(rfc[0] - 8, y + 36, "HMC536MS8G, T/R switch (SPDT, GaAs, DC-6 GHz): 0.7 dB loss, 27 dB isolation at 5-6 GHz, +29 dBm for 0.1 dB compression, "
         "12 dB return loss at 4-6 GHz.  Switching: 30 ns from the control's 50 %% to the RF at 10 / 90 %% (tON, tOFF), 15 ns RF rise and fall "
         "(10-90 %%); the far end hears our reply 30 ns + the air after TR_A falls.  Control 0 V (25 uA) / 3-5 V, absolute maximum -0.5 to +7.5 V; "
         "no supply pin (the controls power it).  DC blocks on all three RF pins (its datasheet).  Exposed pad to ground.", cols=36)
    # TR A's jack (Prompt 35: it was a test pad), drawn last with explicit references
    J(*tr_tap)
    W(tr_tap, (tr_tap[0], tr_tap[1] - 12.7))        # two rows up: the jack's ground (5.08 under its pin) stays off TR_A's line
    B.tap(tr_tap[0], tr_tap[1] - 12.7, "TR A", rkey=LV.VAL["tap_R"], ref="J490", rref="R490")
    return S
