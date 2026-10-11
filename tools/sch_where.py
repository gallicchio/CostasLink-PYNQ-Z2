#!/usr/bin/env python3
"""What is drawn near a point of a sheet: parts (with the pin positions) within a radius.

    python3 tools/sch_where.py rx 455 209 [radius]      sheets: rx, tx, pwr
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "gen")]
import kisch, sch_util as U, board_info as BI
from parts import LIB


def main(sheet, x, y, r=10.0):
    kisch.SYMS.load_library(os.path.join(BI.HW, "lib", LIB + ".kicad_sym"), LIB)
    orig = U.part
    seen = []

    def part(key, ref, px, py, *a, **k):
        pl = orig(key, ref, px, py, *a, **k)
        node, pins = kisch.SYMS.get(pl.lib_id)
        pts = [(p["num"], pl.pin(p["num"])) for p in pins if p["unit"] in (0, pl.unit)]
        if abs(px - x) < r and abs(py - y) < r or any(abs(q[0] - x) < r and abs(q[1] - y) < r for _, q in pts):
            seen.append("%-6s %-14s at (%.2f, %.2f) unit %s: %s" % (ref, key, px, py, pl.unit,
                        " ".join("%s=(%.2f,%.2f)" % (n, q[0], q[1]) for n, q in pts)[:200]))
        return pl
    U.part = part
    import sch_blocks, sch_rx, sch_tx, sch_pwr
    for m in (sch_blocks, sch_rx, sch_tx, sch_pwr):
        m.part = part
    mod = {"rx": sch_rx, "tx": sch_tx, "pwr": sch_pwr}[sheet]
    s = kisch.Sch(BI.NAME, sheet + ".kicad_sch", paper="A2")
    mod.build(s)
    for ln in seen:
        print(ln)
    for (x0, y0, x1, y1), where in U.WIRE_ORIGIN.items():
        if (abs(x0 - x) < r and abs(y0 - y) < r) or (abs(x1 - x) < r and abs(y1 - y) < r):
            print("wire (%.1f,%.1f)-(%.1f,%.1f)  %s" % (x0, y0, x1, y1, where))


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]) if len(sys.argv) > 4 else 10.0)
