#!/usr/bin/env python3
"""Read the netlist back (CLAUDE_PCB.md section 4, "the checks every schematic gets"): every power
net with its pin count, every one-pin net, and the signal paths walked end to end.

    python3 tools/net_check.py        exit 1 on a one-pin net that is not a test pad or a path that breaks
"""
import os, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "gen")]
from sexp import parse, kids, kid, val
import board_info as BI


def read(path):
    doc = parse(open(path, encoding="utf-8").read())[0]
    comps = {val(kid(c, "ref")): val(kid(c, "value")) for c in kids(kid(doc, "components"), "comp")}
    nets = {}
    for n in kids(kid(doc, "nets"), "net"):
        nets[val(kid(n, "name"))] = [(val(kid(x, "ref")), val(kid(x, "pin"))) for x in kids(n, "node")]
    return comps, nets


# the paths, as (ref, pin) hops; each consecutive pair must share a net, through two-pin parts
PATHS = {
    "RX RF chain": [("J101", "1"), ("U101", "3"), ("U101", "4"), ("U102", "5"), ("U102", "14"), ("U103", "1"), ("U103", "3"),
                    ("CP101", "1"), ("CP101", "2"), ("T101", "1"), ("T101", "3"), ("U104", "22")],
    "RX I arm": [("U104", "3"), ("U105", "2"), ("U105", "10"), ("U107", "3"), ("U107", "1")],
    "RX Q arm": [("U104", "16"), ("U106", "2"), ("U106", "10"), ("U601", "3"), ("U601", "1")],     # QP on sheet 7 since Response 14
    "slow I path": [("U105", "10"), ("U501", "2"), ("U501", "10"), ("U503", "3"), ("U503", "1")],
    "slow Q path": [("U106", "10"), ("U502", "2"), ("U502", "10"), ("U504", "3"), ("U504", "1")],
    "RX RF chain 2": [("U103", "3"), ("U117", "1"), ("U117", "3"), ("CP101", "1")],
    "Costas loop": [("U106", "10"), ("JP101", "1"), ("JP101", "2"), ("U110", "3"), ("U110", "4"), ("U111", "3"), ("U111", "4"), ("U112", "2"),
                    ("U112", "1"), ("U112", "6"), ("U112", "7"), ("Y101", "1")],
    "RX LO": [("Y101", "3"), ("U115", "29"), ("U115", "12"), ("U104", "9")],
    "TX baseband I": [("J302", "7"), ("U201", "21")],
    "TX RF chain": [("U201", "16"), ("U202", "1"), ("U202", "3"), ("CP201", "1"), ("CP201", "2"), ("J202", "1")],
    "TX LO": [("Y201", "3"), ("JP201", "1"), ("JP201", "2"), ("U203", "29"), ("U203", "12"), ("U201", "3")],
    "5 V": [("J301", "A4"), ("F301", "1"), ("F301", "2"), ("Q301", "3"), ("Q301", "2"), ("FB301", "1"), ("FB301", "2"), ("U104", "6")],
}
TWO_PIN = ("R", "C", "L", "F", "FB", "D")


def main():
    comps, nets = read(BI.NETLIST)
    pin_net = {}
    for name, nodes in nets.items():
        for rp in nodes:
            pin_net[rp] = name
    bad = 0
    print("power nets:")
    for name in sorted(nets):
        if name.startswith("+") or name == "GND" or name.startswith("VBUS"):
            print("   %-14s %3d pins" % (name, len(nets[name])))
    # a one-pin net that KiCad named "unconnected-..." carries a no-connect flag: deliberate
    ones = [(n, nodes) for n, nodes in nets.items() if len(nodes) == 1 and not nodes[0][0].startswith("TP") and not n.startswith("unconnected-")]
    for n, nodes in sorted(ones):
        print("   ONE-PIN NET %s: %s" % (n, nodes))
        bad += 1
    for pname, hops in PATHS.items():
        ok = True
        trail = []
        for a, b in zip(hops, hops[1:]):
            same_part = a[0] == b[0]
            if same_part:
                trail.append("%s(%s->%s)" % (a[0], a[1], b[1]))
                continue
            na, nb = pin_net.get(a), pin_net.get(b)
            if na is None or nb is None:
                ok = False; trail.append("MISSING %s or %s" % (a, b)); break
            if na == nb:
                trail.append(na)
                continue
            # through two-pin parts: breadth-first over nets joined by R/C/L/F/FB/D/JP
            seen = {na}; frontier = [na]; found = False; depth = 0
            while frontier and depth < 4 and not found:
                depth += 1
                nxt = []
                for net in frontier:
                    for ref, pin in nets[net]:
                        if ref.startswith(TWO_PIN) and not ref.startswith("FB3") or ref.startswith("FB"):
                            for ref2, pin2 in [rp for rp in pin_net if rp[0] == ref and rp[1] != pin]:
                                n2 = pin_net[(ref2, pin2)]
                                if n2 == nb:
                                    found = True
                                if n2 not in seen:
                                    seen.add(n2); nxt.append(n2)
                frontier = nxt
            if found:
                trail.append("%s..%s" % (na, nb))
            else:
                ok = False; trail.append("BREAK %s -> %s" % (na, nb)); break
        print("   %-16s %s: %s" % (pname, "ok" if ok else "BROKEN", " > ".join(trail)[:200]))
        bad += 0 if ok else 1
    # every pad of every footprint carries a net, or a no-connect flag: a symbol that omits a pin
    # (Response 8's audit: nine grounds on the PE43711, the HMC536's paddle, the SMA's centre) passes
    # ERC and the path walk, and only this catches it
    sys.path.insert(0, os.path.join(ROOT, "gen"))
    import placement as PL
    fps = PL.load_footprints()
    doc = parse(open(BI.NETLIST, encoding="utf-8").read())[0]
    fp_of = {val(kid(c, "ref")): val(kid(c, "footprint")).split(":")[-1] for c in kids(kid(doc, "components"), "comp")}
    netless = []
    for ref, fpname in sorted(fp_of.items()):
        if fpname not in fps:
            continue
        for num in fps[fpname]["pads"]:
            if num and (ref, num) not in pin_net:
                netless.append("%s.%s (%s)" % (ref, num, fpname))
    for n in netless:
        print("   PAD WITHOUT A NET: " + n)
    bad += len(netless)
    print("net check: %d parts, %d nets, %d problems" % (len(comps), len(nets), bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
