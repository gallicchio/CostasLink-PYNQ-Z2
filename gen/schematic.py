#!/usr/bin/env python3
"""Draw the schematic: a root sheet that is the block diagram, and three A2 sheets.

    python3 gen/schematic.py        writes hardware/CostasLink-PYNQ-Z2.kicad_sch and rx/tx/pwr.kicad_sch

The sheets meet on the root through hierarchical sheet pins: every FPGA signal leaves the power
sheet (the header) for the RX or TX sheet, and the DAC's two TX references cross from RX to TX.
Power nets are global flags.  Each sheet module draws one sheet; gen/sch_blocks.py holds what
they share.
"""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import kisch
from parts import LIB
import board_info as BI
import sch_util as U
import pins as PINS
import sch_rx, sch_tx, sch_pwr, sch_ant, sch_slow, sch_win

HW = BI.HW

# sheet pins: (name, shape as seen from the sheet, side) for each sheet, in drawing order
RX_PINS = [("CMP_I", "output"), ("LOOP_HOLD", "input"), ("LOOP_SEL", "input"),
           ("SPI_SCLK", "input"), ("SPI_SDATA", "input"), ("LE_PLL_RX", "input"), ("LE_DSA", "input"), ("MUX_RX", "output"),
           ("I2C_SDA", "bidirectional"), ("I2C_SCL", "bidirectional"), ("VR_I", "output"), ("VR_Q", "output"),
           ("I_P", "output"), ("I_N", "output"), ("Q_P", "output"), ("Q_N", "output"), ("I_SUM", "input")]
SLOW_PINS = [("I_P", "input"), ("I_N", "input"), ("Q_P", "input"), ("Q_N", "input"), ("I_SUM", "output"),
             ("CMP_I_S", "output"), ("CMP_QP_S", "output"), ("CMP_QN_S", "output"),
             ("I2C_SDA", "bidirectional"), ("I2C_SCL", "bidirectional")]
TX_PINS = [("TX_I1", "input"), ("TX_I0", "input"), ("TX_Q1", "input"), ("TX_Q0", "input"), ("TX_EN", "input"),
           ("SPI_SCLK", "input"), ("SPI_SDATA", "input"), ("LE_PLL_TX", "input"), ("MUX_TX", "output"),
           ("TRIG_A", "input"), ("TRIG_B", "input"), ("TRIG_IN", "output"), ("VR_I", "input"), ("VR_Q", "input")]
ANT_PINS = [("TR_A", "input")]                    # TR_B is made from TR_A on the sheet since Response 14
# the window comparators (Response 14): the four arm outputs in, four comparator lines out, the DAC on I2C;
# connected at the root by net labels, so the other sheets' corridors stay as they were
WIN_PINS = [("I_P", "input"), ("I_N", "input"), ("Q_P", "input"), ("Q_N", "input"),
            ("CMP_IP", "output"), ("CMP_IN", "output"), ("CMP_QP", "output"), ("CMP_QN", "output"),
            ("I2C_SDA", "bidirectional"), ("I2C_SCL", "bidirectional")]
PWR_PINS = [(s, "output" if s in PINS.OUTPUTS else "input" if s in PINS.INPUTS else "bidirectional")
            for s in sorted(PINS.SIGNALS) if not s.startswith("SPARE")]

SHEETS = [
    ("Power and FPGA header", "pwr.kicad_sch", "A2", sch_pwr.build, PWR_PINS, (25.4, 63.5), "r"),      # its 27 rows must not share a y with the transmitter's
    ("Receiver and Costas loop", "rx.kicad_sch", "A2", sch_rx.build, RX_PINS, (182.88, 50.8), "l"),    # under the description (Prompt 35)
    ("Transmitter and triggers", "tx.kicad_sch", "A2", sch_tx.build, TX_PINS, (182.88, 139.7), "l"),
    ("Antenna switch: one antenna by T/R", "ant.kicad_sch", "A3", sch_ant.build, ANT_PINS, (182.88, 203.2), "l"),
    ("Slow path: confirm or veto; interference detectors", "slow.kicad_sch", "A2", sch_slow.build, SLOW_PINS, (322.58, 38.1), "l"),
    ("Window comparators: I and Q", "win.kicad_sch", "A3", sch_win.build, WIN_PINS, (322.58, 101.6), "l"),
]
SLOW_X, CORRIDOR_Y = 322.58, 236.22          # the slow sheet's left edge; the corridor below the switch sheet


def company():
    return BI.AUTHORS


def draw():
    kisch.SYMS.load_library(os.path.join(HW, "lib", LIB + ".kicad_sym"), LIB)
    root = kisch.Sch(BI.NAME, BI.NAME + ".kicad_sch", paper="A3", title=BI.TITLE,          # the tagline is the big text on the sheet; the title block is 98 mm
                     rev=BI.REV, date=BI.DATE, company=company(),
                     comments=["Made by gen/schematic.py from gen/pins.py and gen/parts.py", BI.LICENCE, "https://" + BI.URL])
    root.text(17.78, 21.59, "%s: %s" % (BI.TITLE, BI.TAGLINE), size=3.0, bold=True)
    root.note(17.78, 25.4, "A 5.8 GHz link that carries one or two bits FPGA to FPGA in the speed-of-light time plus about 25 ns "
              "of electronics, for quantum position verification; it plugs onto a PYNQ-Z2's or an Icepi Zero's Raspberry Pi header, "
              "and two of them talk to each other.  The receiver (sheet 3) is a zero-IF quadrature demodulator whose LO is a synthesizer "
              "on a VCXO; a hardware Costas loop steers the VCXO, so the LO stays on the far end's carrier and the demodulated I and Q "
              "are the constellation point the far end sent, read by comparators straight into the FPGA.  For example, for BPSK, "
              "I is the data and Q the phase error; for QPSK and the pilot-plus-corners schemes the four window comparators (sheet 7) "
              "decide which way the point left the idle; a slow confirming path (sheet 6) vetoes false alarms.  The transmitter (sheet 4) "
              "is a quadrature modulator driven by two 2-bit resistor ladders from FPGA pins (and TRIG IN, summed into the Q ladder), "
              "on its own synthesizer and TCXO.  Sheet 5 is an optional T/R switch for one antenna.  PLAN.md has the arithmetic; "
              "sim/budget.py computes it and every blue box quotes it.", cols=130)
    sheets = []
    pinpos = {}
    for i, (name, fn, paper, build, pins, (x, y), side) in enumerate(SHEETS):
        h = max(25.4, 2.54 * (len(pins) + 2))
        plist = [(p, shape, side, 2.54 * (k + 1)) for k, (p, shape) in enumerate(pins)]
        u, pos = root.sheet(x, y, 63.5, h, name, fn, i + 2, pins=plist)
        pinpos[fn] = pos
        s = kisch.Sch(BI.NAME, fn, paper=paper, title="%s: %s" % (BI.TITLE, name.lower()), rev=BI.REV, date=BI.DATE,
                      company=company(), comments=["Made by gen/%s.py" % build.__module__, BI.LICENCE, "https://" + BI.URL],
                      root=root.uuid, sheet_box_uuid=u)
        build(s)
        for line in U.flush_notes(s):
            print(line)
        sheets.append(s)
    # wires between the sheets on the root: the header's pins to the RX/TX sheets' pins, VR_I/VR_Q
    # from RX to TX; each signal on its own horizontal, stepping through a column of verticals
    pw, rx, tx, ant, slow = (pinpos["pwr.kicad_sch"], pinpos["rx.kicad_sch"], pinpos["tx.kicad_sch"], pinpos["ant.kicad_sch"],
                             pinpos["slow.kicad_sch"])
    xcol = 91.44                                   # 27 columns at 2.54 stay left of the sheets at 182.88
    k = 0
    j = 0                                          # corridor lanes under the switch sheet, for the slow sheet's signals
    for name, _ in PWR_PINS:
        src = pw[name]
        dsts = [d[name] for d in (rx, tx, ant) if name in d]
        xc = xcol + 2.54 * k
        k += 1
        if not dsts and name not in slow:
            continue                               # reaches only the window sheet: its label on the pin connects it
        root.wires(src, (xc, src[1]))
        for d in dsts:
            root.wires((xc, src[1]), (xc, d[1]), d)
        if name in slow:
            d = slow[name]
            yl = CORRIDOR_Y + 2.54 * j
            xr = SLOW_X - 3.81 - 2.54 * j
            j += 1
            root.wires((xc, src[1]), (xc, yl), (xr, yl), (xr, d[1]), d)
            dsts.append(d)
        root.junction(xc, src[1]) if len(dsts) > 1 else None
    for name in ("VR_I", "VR_Q"):
        a, b = rx[name], tx[name]
        root.wires(a, (a[0] - 6.35 - 2.54 * (1 if name == "VR_Q" else 0), a[1]), (a[0] - 6.35 - 2.54 * (1 if name == "VR_Q" else 0), b[1]), b)
    # the four arm outputs from the receiver sheet to the slow-path sheet: out of the receiver's left
    # pins, down the corridor under the switch sheet, up into the slow sheet's left pins
    for k, name in enumerate(("I_P", "I_N", "Q_P", "Q_N", "I_SUM")):
        a, b = rx[name], slow[name]
        xl = a[0] - 11.43 - 2.54 * k
        yl = CORRIDOR_Y + 2.54 * (j + k)
        xr = SLOW_X - 3.81 - 2.54 * (j + k)
        root.wires(a, (xl, a[1]), (xl, yl), (xr, yl), (xr, b[1]), b)
    # the window comparators' sheet: a net label at each of its pins, and the same label on each net's
    # line where it already runs on this sheet (the header's pin, or the receiver's arm outputs)
    win = pinpos["win.kicad_sch"]
    for name, _ in WIN_PINS:
        x, y = win[name]
        root.wires((x, y), (x - 7.62, y))
        root.label(x - 7.62, y, name, size=1.0, justify="right bottom")
        arm = name in ("I_P", "I_N", "Q_P", "Q_N")
        src = rx[name] if arm else pw[name]                  # the label sits on the pin, where that net's wire starts
        root.label(src[0], src[1], name, size=1.0, justify="right bottom" if arm else "left bottom")
    root.note(25.4, 190.5, "Power sheet (left): the header's %d FPGA signals leave as named lines to the receiver, transmitter, antenna-switch and slow-path sheets; "
              "the window-comparator sheet's nets are joined by the net labels at its pins and at the header's.  "
              "VR_I and VR_Q are the monitoring DAC's two TX references, from the receiver sheet (where the DAC lives) to the transmitter.  "
              "The switch sheet is its own block with three SMAs: fit it to share one antenna (T/R), leave it off for two antennas (full duplex on two frequencies)." % len(PWR_PINS), cols=52)   # narrower than the 66 mm to the first root wire column
    return root, sheets


def main():
    root, sheets = draw()
    import json
    os.makedirs(os.path.join(HW, "checks"), exist_ok=True)
    json.dump(dict(sorted(U.ROLES.items())), open(os.path.join(HW, "checks", "roles.json"), "w"), indent=1)
    bad = 0
    for s in [root] + sheets:
        touches, nets, over = s.touches(), s.nets(), s.overlaps()
        out = s.save(HW, is_root=(s is root))
        print("%-28s %3d accidental touches, %3d net problems, %3d overlaps"
              % (os.path.relpath(out, ROOT), len(touches), len(nets), len(over)))
        for m in (touches + nets + over)[:60]:
            g = re.search(r"wire \(([-\d.]+),([-\d.]+)\)-\(([-\d.]+),([-\d.]+)\)", m)
            origin = ""
            if g:
                key = tuple(round(float(v), 1) for v in g.groups())
                for k, v in U.WIRE_ORIGIN.items():
                    if all(abs(a - b) < 0.11 for a, b in zip(k, key)):
                        origin = "   <- " + v
                        break
            print("    ", m + origin)
        bad += len(touches) + len(nets) + len(over)
    return 1 if bad else 0


if __name__ == "__main__":
    try:
        rc = main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        rc = 2                       # a crash, not a report of overlaps (build.py accepts only 0 and 1)
    sys.exit(rc)
