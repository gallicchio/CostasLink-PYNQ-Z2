#!/usr/bin/env python3
"""Walk the netlist from a pin through the two-terminal parts in its way and print every hop: the raw
material for the by-hand trace of every signal path (docs/PATHS.md, Prompt 32).

    python3 tools/path_walk.py J101 1            from one pin
    python3 tools/path_walk.py --rf              every RF port of the table below

A hop is (ref, pin) -> net -> the other pads on that net.  A two-terminal part (R, C, L, FB, D, JP's
two pins, a coupler's through pair) is passed through to its other pin; the walk stops at an active
part's pin, a jack, or a net with more than one way on (a branch), which it lists.  DNP parts are
named but not followed.
"""
import os, sys, re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from sexp import parse, kids, kid, val

NET = os.path.join(ROOT, "hardware", "checks", "netlist.net")


def load():
    net = parse(open(NET, encoding="utf-8").read())[0]
    comps = {}
    for c in kids(net, "components")[0][1:]:
        if not isinstance(c, list):
            continue
        ref = val(kid(c, "ref"))
        props = {}
        for p in kids(c, "property"):
            nm = kid(p, "name")
            if nm is not None:
                props[val(nm)] = val(kid(p, "value")) if kid(p, "value") is not None else ""
        comps[ref] = dict(value=val(kid(c, "value")) or "", fp=(val(kid(c, "footprint")) or "").split(":")[-1],
                          dnp=("dnp" in props) or (val(kid(c, "value")) or "").startswith("DNP"))
    by_pin, by_net = {}, {}
    for n in kids(net, "nets")[0][1:]:
        if not isinstance(n, list):
            continue
        name = val(kid(n, "name"))
        for node in kids(n, "node"):
            k = (val(kid(node, "ref")), val(kid(node, "pin")))
            by_pin[k] = name
            by_net.setdefault(name, []).append(k)
    return comps, by_pin, by_net


TWO = re.compile(r"^(R|C|L|FB|D|TH)\d+$")


def other_pin(ref, pin, comps, by_pin):
    """The other pin of a two-terminal part, or None."""
    if not TWO.match(ref):
        return None
    pins = [p for (r, p) in by_pin if r == ref]
    if len(pins) != 2:
        return None
    return [p for p in pins if p != pin][0]


def walk(ref, pin, comps, by_pin, by_net, depth=12):
    """Hops from (ref, pin): [(net, [(ref, pin, value), ...]), ...] until an active pin or a branch."""
    out, seen = [], set()
    cur = (ref, pin)
    for _ in range(depth):
        net = by_pin.get(cur)
        if net is None:
            out.append(("(no net)", []))
            break
        others = [(r, p) for (r, p) in by_net[net] if (r, p) != cur]
        out.append((net, [(r, p, comps[r]["value"] + (" DNP" if comps[r]["dnp"] else "")) for r, p in others]))
        live = [(r, p) for r, p in others if not comps[r]["dnp"]]
        passable = [(r, p) for r, p in live if other_pin(r, p, comps, by_pin)]
        if len(live) != 1 or not passable or net == "GND" or net.startswith("+"):
            break                                    # an active pin, a jack, a rail, or a branch
        r, p = passable[0]
        cur = (r, other_pin(r, p, comps, by_pin))
        if cur in seen:
            break
        seen.add(cur)
    return out


def show(ref, pin, comps, by_pin, by_net):
    print("%s.%s (%s)" % (ref, pin, comps[ref]["value"]))
    for net, others in walk(ref, pin, comps, by_pin, by_net):
        print("   %-34s %s" % (net, "  ".join("%s.%s[%s]" % o for o in others)))


# every port that carries 5.8 GHz (or the LO / reference), with what the datasheet says about DC on it
RF_PORTS = [
    ("J101", "1"), ("U101", "3"), ("U101", "4"), ("U102", "5"), ("U102", "14"), ("U103", "1"), ("U103", "3"),
    ("U117", "1"), ("U117", "3"), ("CP101", "1"), ("CP101", "2"), ("CP101", "3"), ("CP101", "4"), ("T101", "1"),
    ("T101", "2"), ("T101", "3"), ("U104", "22"), ("U104", "21"), ("U104", "9"), ("U104", "10"),
    ("U115", "12"), ("U115", "13"), ("U115", "14"), ("U115", "15"), ("J109", "1"),
    ("U201", "16"), ("U201", "3"), ("U201", "4"), ("U202", "1"), ("U202", "3"), ("CP201", "1"), ("CP201", "2"),
    ("CP201", "3"), ("CP201", "4"), ("J202", "1"), ("J201", "1"), ("U203", "12"), ("U203", "13"), ("U203", "14"),
    ("U203", "15"), ("J204", "1"), ("U401", "3"), ("U401", "5"), ("U401", "8"), ("J401", "1"), ("J402", "1"),
    ("J403", "1"), ("J203", "1"), ("U115", "29"), ("U203", "29"),
]

if __name__ == "__main__":
    comps, by_pin, by_net = load()
    if "--rf" in sys.argv:
        for ref, pin in RF_PORTS:
            if (ref, pin) in by_pin:
                show(ref, pin, comps, by_pin, by_net)
            else:
                print("%s.%s: no such pin" % (ref, pin))
    else:
        show(sys.argv[1], sys.argv[2], comps, by_pin, by_net)
