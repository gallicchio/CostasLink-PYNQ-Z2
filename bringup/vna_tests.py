"""The 8720ES tests of MONDAY.md section 2 (TODO rows 6-7): RX ANT's S11 (test A) and the chains' S21 (test F), each
saved as Touchstone into bringup/data/board_A/vna/ (gitignored) with its plot, and the numbers the plan predicts.

    python3 bringup/vna_tests.py measure rxant_unpowered             # port 1 RX ANT, port 2 RX MON, the board off
    python3 bringup/vna_tests.py measure rxant_dsa20 --dsa 20        # the board on: the DSA held at 20 dB throughout
    python3 bringup/vna_tests.py measure txant_txmon --tx-null       # port 1 TX ANT, port 2 TX MON: the TX nulled
    python3 bringup/vna_tests.py summary FILE.s2p [FILE2.s2p ...]    # the numbers again, no instrument

It needs the calibration in force (register 29, BRINGUP_LOG 4.36: full 2-port, 3-6.5 GHz, 1601 points, -40 dBm) and
refuses a source above -30 dBm (RX ANT's absolute maximum is +1 dBm).  With --dsa it sets the board's DSA before each
of the four sweeps, and with --tx-null holds the TX at its carrier null (hold_point(0, 0)) the same way, so the
TX's own carrier does not land in port 1: every such call is a client driving the board, which keeps linkd paused (its idle_s, 60 s) so it
cannot retune or re-level the board while the analyzer sweeps.  The analyzer is left in HOLD: with the 2-port
correction on, every sweep throws option 085's mechanical transfer switch (lab-instrument-control hp/hp.md).
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.expanduser("~/lab-instrument-control/hp")
sys.path.insert(0, LIC)
from hp_87xxES import HP87xxES, PARAMETERS                     # noqa: E402
import vna_measure                                              # noqa: E402  (plot, read_s2p, reciprocity)

MAX_SOURCE_DBM = -30.0
# the points the bench's map read the receive chain at (BRINGUP_LOG 3.3, REVB 8) and the link's carriers
SPOT_GHZ = (3.0, 3.5, 4.0, 4.4, 5.0, 5.2, 5.5, 5.725, 5.8, 5.875, 6.1)
S11_BAND = (5.5e9, 6.1e9)             # sim/aslaid/REPORT.md: S11 above -2 dB here, -0.8 dB at 5.8 GHz


def db(x):
    return 20 * np.log10(np.maximum(np.abs(x), 1e-10))


def summary(f, data, name=""):
    lines = ["%s: %d points, %.3f-%.3f GHz" % (name, len(f), f[0] / 1e9, f[-1] / 1e9)]
    for p in PARAMETERS:
        lines.append("  %s  " % p + "  ".join("%g:%+.2f" % (g, db(np.interp(g * 1e9, f, data[p]))) for g in SPOT_GHZ))
    m = (f >= S11_BAND[0]) & (f <= S11_BAND[1])
    s11 = db(data["S11"])
    k_hi, k_lo = np.argmax(s11[m]), np.argmin(s11[m])
    lines.append("  S11 over 5.5-6.1 GHz: worst (highest) %+.2f dB at %.3f GHz, best %+.2f dB at %.3f GHz, mean %+.2f dB"
                 % (s11[m][k_hi], f[m][k_hi] / 1e9, s11[m][k_lo], f[m][k_lo] / 1e9, s11[m].mean()))
    s21 = db(data["S21"])
    k = np.argmax(s21)
    lines.append("  S21 peak %+.2f dB at %.3f GHz;  S12 peak %+.2f dB" % (s21[k], f[k] / 1e9, db(data["S12"]).max()))
    return "\n".join(lines)


def measure(name, dsa=None, board="A", tx_null=False):
    out = os.path.join(HERE, "data", "board_%s" % board, "vna")
    os.makedirs(out, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    path = os.path.join(out, "%s_%s.s2p" % (stamp, name))
    bench = None
    if dsa is not None or tx_null:
        from bench import Bench
        bench = Bench(board, "vna")
    with HP87xxES() as vna:
        pw = vna.power()
        if pw > MAX_SOURCE_DBM:
            raise SystemExit("the source is at %+.1f dBm, above %+.0f: not into this board" % (pw, MAX_SOURCE_DBM))
        if not vna.corrected():
            raise SystemExit("correction is off: recall the calibration first (RECAREG29;)")
        f, data = None, {}
        try:
            for p in PARAMETERS:
                if dsa is not None:
                    bench.board_call("dsa", dsa)
                if tx_null:
                    bench.board_call("hold_point", 0, 0)
                f, data[p] = vna.trace(p)
        finally:
            vna.w("HOLD;")
        settings = "%d points, %.0f-%.0f Hz, IF bandwidth %.0f Hz, source %+.2f dBm, kit %s" % (
            len(f), f[0], f[-1], vna.if_bandwidth(), pw, vna.cal_kit())
        with open(path, "w") as fh:
            fh.write("! %s, via bringup/vna_tests.py\n! %s\n! measured %s, %s\n" % (
                vna.idn, name, time.strftime("%Y-%m-%d %H:%M:%S"), settings))
            if dsa is not None:
                fh.write("! board %s, DSA %.2f dB (set before each sweep)\n" % (board, dsa))
            if tx_null:
                fh.write("! board %s, the TX held at its carrier null, hold_point(0, 0), before each sweep\n" % board)
            fh.write("# HZ S RI R 50\n")
            for n, fr in enumerate(f):
                fh.write("%.0f " % fr + " ".join("%.6e %.6e" % (data[p][n].real, data[p][n].imag) for p in PARAMETERS)
                         + "\n")
    png = path[:-4] + ".png"
    vna_measure.plot(f, data, title="board %s: %s (%s)" % (board, name, stamp), path=png)
    print(summary(f, data, name))
    print("wrote %s\n      %s" % (path, png))
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("measure", "summary"))
    ap.add_argument("names", nargs="+", help="measure: the test's name; summary: .s2p files")
    ap.add_argument("--dsa", type=float, help="hold the board's DSA at this attenuation (dB) during the sweeps")
    ap.add_argument("--tx-null", action="store_true", help="hold the TX at its carrier null during the sweeps")
    ap.add_argument("--board", default="A")
    a = ap.parse_args()
    if a.action == "measure":
        measure(a.names[0], a.dsa, a.board, a.tx_null)
    else:
        for p in a.names:
            f, data, _ = vna_measure.read_s2p(p)
            print(summary(f, data, os.path.basename(p)))


if __name__ == "__main__":
    main()
