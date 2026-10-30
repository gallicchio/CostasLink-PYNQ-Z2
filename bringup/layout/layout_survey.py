#!/usr/bin/env python3
"""The receive chain's layout read from the board file (bring-up, 2026-10-29, Jason: "How well impedance controlled are
all of the signal traces around the LNA? ... enough ground vias? ... power plane issues? ... decoupling?").

    python3 bringup/layout/layout_survey.py [rx|tx|all]

Prints, for every F.Cu segment width of each RF net: its length, the gap to the top ground pour (median, min/max), the
share of it with In1 ground under it, the fence (ground vias 0.5-1.6 mm off its centre line, per mm), and which In2
plane lies under it.  Then each ADL5611 bias choke's nearest supply capacitor, and how far the pours on F.Cu and B.Cu
are from their nearest ground via (the stitching).
"""
import math, os, sys, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rfgeo as G

RX = ["Net-(J101-In)", "Net-(U101-RF_IN)", "Net-(U101-RF_OUT)", "Net-(U102-RF1)", "Net-(U102-RF2)", "Net-(U103-RFIN)",
      "Net-(U103-RFOUT)", "Net-(U117-RFIN)", "Net-(U117-RFOUT)", "Net-(CP101-IN)", "Net-(CP101-OUT)", "Net-(CP101-CPL)",
      "Net-(T101-BAL1)", "Net-(T101-BAL2)", "Net-(U104-RFIN)", "Net-(U104-RFIP)"]
TX = ["Net-(U201-RFOUT)", "Net-(C213-Pad2)", "Net-(U202-RFIN)", "Net-(U202-RFOUT)", "Net-(CP201-IN)", "Net-(CP201-OUT)",
      "Net-(CP201-CPL)", "Net-(U401-RF1)", "Net-(U401-RF2)", "Net-(U401-RFC)", "Net-(J401-In)", "Net-(J402-In)", "Net-(J403-In)"]
CHOKES = ("L103", "L104", "L201")


def lines(B, nets):
    gvia = np.array([(v[0], v[1]) for v in B["via"] if v[4] == "GND"])
    top, in1 = B["fill"][("F.Cu", "GND")], B["fill"][("In1.Cu", "GND")]
    in2 = {n: P for (l, n), P in B["fill"].items() if l == "In2.Cu"}
    print("%-14s %5s %6s %6s %11s %7s %8s  %s" % ("net", "w mm", "mm", "gap", "gap min/max", "In1 GND", "fence/mm", "In2 under"))
    for net in nets:
        segs = [s for s in B["seg"] if s[6] == net and s[5] == "F.Cu"]
        if not segs:
            continue
        xs = [s[0] for s in segs] + [s[2] for s in segs]
        ys = [s[1] for s in segs] + [s[3] for s in segs]
        box = (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2)
        E = G.edges([P for P in top if not (P[:, 0].max() < box[0] or P[:, 0].min() > box[2] or
                                            P[:, 1].max() < box[1] or P[:, 1].min() > box[3])], box)
        own = [G.pad_poly(p) for p in B["pad"] if p["net"] == net]
        acc = {}
        for (xa, ya, xb, yb, w, l, n) in segs:
            L = math.dist((xa, ya), (xb, yb))
            k = max(int(L / 0.1), 1)
            t = (np.arange(k) + 0.5) / k
            pts = np.c_[xa + (xb - xa) * t, ya + (yb - ya) * t]
            keep = np.ones(len(pts), bool)
            for P in own:                     # the samples on the net's own pads measure the pad, not the line
                keep &= ~G.inside(pts, [P])
            pts = pts[keep]
            if not len(pts):
                continue
            e = acc.setdefault(w, dict(L=0.0, gap=[], ref=[], fence=0, under={}))
            e["L"] += L
            e["gap"] += list(G.dist_to_edges(pts, E) - w / 2)
            e["ref"] += list(G.inside(pts, in1))
            ux, uy = (xb - xa) / max(L, 1e-9), (yb - ya) / max(L, 1e-9)
            rel = gvia - (xa, ya)
            along, perp = rel @ (ux, uy), rel @ (-uy, ux)
            e["fence"] += int(((along >= 0) & (along <= L) & (abs(perp) >= 0.5) & (abs(perp) <= 1.6)).sum())
            for n2, P in in2.items():
                m = G.inside(pts, P).mean()
                if m > 0.05:
                    e["under"][n2] = e["under"].get(n2, 0) + m * L
        for w, e in sorted(acc.items()):
            g = np.array(e["gap"])
            print("%-14s %5.2f %6.1f %6.2f %5.2f/%-5.2f %6.0f%% %8.2f  %s" % (
                net[5:-1], w, e["L"], np.median(g), g.min(), g.max(), 100 * np.mean(e["ref"]), e["fence"] / e["L"],
                ", ".join("%s %.0f%%" % (k, 100 * v / e["L"]) for k, v in e["under"].items())))


def chokes(B):
    caps = [p for p in B["pad"] if p["net"] == "+5V_RF" and p["ref"].startswith("C")]
    for L in CHOKES:
        cold = next(p for p in B["pad"] if p["ref"] == L and p["net"] == "+5V_RF")
        dv = min(math.dist((v[0], v[1]), (cold["x"], cold["y"])) for v in B["via"] if v[4] == "+5V_RF")
        near = sorted((math.dist((c["x"], c["y"]), (cold["x"], cold["y"])), c["ref"], B["fp"][c["ref"]][3]) for c in caps)[:3]
        print("%s (%s): its +5V_RF via %.1f mm from the cold pad; nearest capacitors %s" % (
            L, B["fp"][L][3], dv, ", ".join("%s %s %.1f mm" % (r, v, d) for d, r, v in near)))


def stitching(B, box=(40, 30, 60, 90), step=0.25):
    gv = np.array([(v[0], v[1]) for v in B["via"] if v[4] == "GND"] +
                  [(p["x"], p["y"]) for p in B["pad"] if p["net"] == "GND" and p["drill"] > 0])
    xs, ys = np.arange(box[0], box[2], step), np.arange(box[1], box[3], step)
    pts = np.array([(x, y) for x in xs for y in ys])
    for lay in ("F.Cu", "B.Cu"):
        ins = np.zeros(len(pts), bool)
        for P in B["fill"][(lay, "GND")]:
            m = (pts[:, 0] >= P[:, 0].min()) & (pts[:, 0] <= P[:, 0].max()) & (pts[:, 1] >= P[:, 1].min()) & (pts[:, 1] <= P[:, 1].max())
            if m.any():
                ins[np.where(m)[0][G.inside(pts[m], [P])]] = True
        q = pts[ins]
        d = np.array([np.sqrt(((gv - p) ** 2).sum(1)).min() for p in q])
        print("%s pour in x %g-%g, y %g-%g (%.0f mm2): nearest ground via median %.1f mm, 95th percentile %.1f, max %.1f; "
              "%.0f%% of it more than 2.5 mm (lambda/10 at 5.8 GHz in FR4) from one" % (
                  lay, box[0], box[2], box[1], box[3], len(q) * step * step, np.median(d), np.percentile(d, 95), d.max(), 100 * (d > 2.5).mean()))


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "rx"
    B = G.load()
    lines(B, RX if which == "rx" else TX if which == "tx" else RX + TX)
    print()
    chokes(B)
    print()
    stitching(B)
    stitching(B, box=(25, 25, 145, 125), step=0.5)
