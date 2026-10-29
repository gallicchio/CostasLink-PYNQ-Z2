#!/usr/bin/env python3
"""Every net's routed track length against the shortest tree through its pads (bring-up, 2026-10-29: board A's
LO TX MON read 25.7 dB low at 5.8 GHz because Net-(J204-In), 12.3 mm from C231 to J204, was routed 115.6 mm
round the board; DRC, the net check and three design reviews passed it).

    python3 tools/detour_check.py [board.kicad_pcb]        default the project's board

Prints every net routed more than RATIO times its pads' minimum spanning distance and longer than MIN_MM, the
plane nets aside.  An RF net (one touching a U.FL, SMA or MMCX footprint, or with RF or LO in its name) fails at
RF_RATIO and RF_EXTRA_MM over its tree: exit 1.  A slow header line's detour is printed and passes.
"""
import math, os, re, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "gen"))
sys.path.insert(0, HERE)
import board_info as BI
from sexp import parse, kids, kid, val, num

RATIO, MIN_MM = 2.0, 15.0           # print
RF_RATIO, RF_EXTRA_MM = 1.5, 10.0   # fail: both, so a 14 mm comparator tap (J103, 5.6 mm extra) passes; 10 mm is a
                                    # third of a wavelength on the outer layers at 5.8 GHz
RF_FOOTPRINTS = re.compile(r"U\.FL|SMA|MMCX", re.I)
RF_NAMES = re.compile(r"(^|[/_(-])(RF|LO)(_|$|[)-])")


def mst(pts):
    """Prim's minimum spanning tree length through the points, mm."""
    if len(pts) < 2:
        return 0.0
    d = {j: math.dist(pts[0], pts[j]) for j in range(1, len(pts))}
    tot = 0.0
    while d:
        j = min(d, key=d.get)
        tot += d.pop(j)
        for k in d:
            d[k] = min(d[k], math.dist(pts[j], pts[k]))
    return tot


def nets(pcb):
    """net -> {'track': mm, 'pads': [(x, y)], 'rf': bool}"""
    doc = parse(open(pcb, encoding="utf-8").read())[0]
    out = collections.defaultdict(lambda: {"track": 0.0, "pads": [], "rf": False})
    for seg in kids(doc, "segment") + kids(doc, "arc"):
        a, b = kid(seg, "start"), kid(seg, "end")
        out[str(val(kid(seg, "net")))]["track"] += math.dist((num(a, 1), num(a, 2)), (num(b, 1), num(b, 2)))
    for fp in kids(doc, "footprint"):
        at = kid(fp, "at")
        fx, fy = num(at, 1), num(at, 2)
        rot = num(at, 3) if len(at) > 3 else 0.0
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        rf = bool(RF_FOOTPRINTS.search(str(val(fp))))
        for pad in kids(fp, "pad"):
            n = kid(pad, "net")
            if n is None:
                continue
            pat = kid(pad, "at")
            dx, dy = num(pat, 1), num(pat, 2)
            e = out[str(val(n))]
            e["pads"].append((fx + dx * c + dy * s, fy - dx * s + dy * c))
            e["rf"] |= rf
    for name, e in out.items():
        e["rf"] |= bool(RF_NAMES.search(name))
    return out


def main(argv):
    pcb = argv[1] if len(argv) > 1 else BI.PCB
    fails = []
    print("%6s %8s %8s %5s  %s" % ("ratio", "track", "tree", "pads", "net"))
    for name, e in sorted(nets(pcb).items(), key=lambda kv: -kv[1]["track"]):
        if name.startswith(("+", "GND")) or not e["track"]:
            continue
        tree = mst(e["pads"])
        if tree <= 0:
            continue
        r = e["track"] / tree
        bad = e["rf"] and r > RF_RATIO and e["track"] - tree > RF_EXTRA_MM
        if bad or (r > RATIO and e["track"] > MIN_MM):
            print("%6.1f %8.1f %8.1f %5d  %s%s" % (r, e["track"], tree, len(e["pads"]), name, "   <- RF: FAIL" if bad else ""))
        if bad:
            fails.append(name)
    print("%d RF net(s) detoured" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
