#!/usr/bin/env python3
"""Late assignment of the header's interchangeable pins, from the placed board (CLAUDE_PCB.md
section 5, the ECP5 and OWLternating Current lesson: bind swappable pins last, in the order the
lines arrive, so no two cross).

    python3 gen/pin_swap.py            propose: print the assignment that the placement wants
    python3 gen/pin_swap.py --apply    rewrite gen/pins.py's HEADER table with it, then rebuild
                                       (schematic, constraints, board all read that table)

The header runs along the bottom edge, pin 1 at the right-hand end and higher numbers to the left.
Every swappable signal's destination is the mean x of its chip pins; the signals sorted by that x,
right to left, take the swappable pins sorted by their x, right to left.  What is NOT swappable:
the I2C pair (the PYNQ's pull-ups are on 3 and 5), TR_A / TR_B (27 / 28, the PYNQ's pull-ups),
CMP_I (18) and TRIG_IN (26) (clock-capable on both boards), the fast comparator and ladder pins
(7, 8, 10, 11, 13, 15: on the banks and sites they were chosen for, already beside their parts),
and the rails.  The Icepi puts 35 and 37 on its bank 0 (no GDDRX2): slow signals only there, which
the swappable set already is.
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import pins as PINS
import placement as PL

SWAPPABLE = {12, 16, 19, 21, 22, 23, 24, 28, 29, 31, 32, 33, 35, 36, 37, 38, 40}   # 12 and 28 joined in Response 14 (the I window)
BANK0 = {35, 37}            # the Icepi's bank 0: no GDDRX2, so no fast input there


def propose():
    plan = json.load(open(os.path.join(ROOT, "build", "placement.json")))["place"]
    P = PL.Plan()
    P.pos = {r: tuple(v) for r, v in plan.items()}
    nets = {k: v for k, v in PINS.HEADER.items() if k in SWAPPABLE}
    dest = {}
    pin_net = {}
    for n, nodes in P.nets.items():
        for ref, num in nodes:
            pin_net[(ref, num)] = n

    def rail(n):
        b = n.split("/")[-1]
        return b.startswith("+") or "GND" in b or b.startswith("VBUS")

    def ends(n, seen):
        """The chip pins a header net reaches: through a series part (a two-pad R, C or L whose
        other side is not a rail) to the net beyond; a shunt to a rail is not a destination, and a
        rule-placed series part is not either (it sits wherever the pin pulls it, so using it made
        the assignment chase itself)."""
        out = []
        for ref, num in P.nets.get(n, []):
            if (ref.startswith("J") and not ref.startswith("JP")) or ref not in P.pos:
                continue                                  # the header, and the monitor jacks: not where a line is going
            pads = list(P.fp(ref)["pads"])
            if ref[0] in "RCL" and len(pads) == 2:
                other = pin_net.get((ref, [p for p in pads if p != num][0]))
                if other and not rail(other) and other not in seen:
                    out += ends(other, seen | {other})
                continue
            out.append(P.pad_xy(ref, num)[0])
        return out

    for pin, (net, zynq, site, what) in nets.items():
        full = [n for n in P.nets if n == net or n.endswith("/" + net)]
        xs = ends(full[0], {full[0]}) if full else []
        dest[net] = sum(xs) / len(xs) if xs else None
    pins_by_x = sorted(SWAPPABLE, key=lambda p: -PL.hdr_pin(p)[0])         # right to left
    sigs_by_x = sorted(nets.values(), key=lambda v: -(dest[v[0]] if dest[v[0]] is not None else 0.0))
    order = [v for v in sigs_by_x]
    # a fast input that lands on the Icepi's bank 0 trades places with its nearest slow neighbour
    for i, pin in enumerate(pins_by_x):
        if pin in BANK0 and order[i][0] in PINS.FAST_INPUTS:
            for d in (1, -1, 2, -2, 3, -3):
                j = i + d
                if 0 <= j < len(order) and pins_by_x[j] not in BANK0 and order[j][0] not in PINS.FAST_INPUTS:
                    order[i], order[j] = order[j], order[i]
                    break
    new = {}
    for pin, (net, zynq, site, what) in zip(pins_by_x, order):
        new[pin] = (net, PINS.HEADER[pin][1], PINS.HEADER[pin][2], what)
    moved = [(p, PINS.HEADER[p][0], new[p][0]) for p in sorted(new) if PINS.HEADER[p][0] != new[p][0]]
    return new, moved, dest


def apply(new):
    path = os.path.join(HERE, "pins.py")
    src = open(path, encoding="utf-8").read()
    for pin, (net, zynq, site, what) in new.items():
        # the Icepi's bank-0 note belongs to the pin, not the signal: drop it and add it where it applies
        what = re.sub(r"\s*\(Icepi:? bank 0[^)]*\)", "", what)
        if pin in (35, 37):
            what += " (Icepi bank 0: no GDDRX2)"
        pat = re.compile(r'^(    %d: \(")[^"]*(", "%s", "%s", )[^\n]*' % (pin, zynq, site), re.M)
        m = pat.search(src)
        if not m:
            raise SystemExit("pin_swap: pin %d not found in gen/pins.py as expected" % pin)
        src = src[:m.start()] + m.group(1) + net + m.group(2) + json.dumps(what) + ")," + src[m.end():]
    open(path, "w", encoding="utf-8").write(src)


def main(argv):
    new, moved, dest = propose()
    print("destination x of each swappable signal (mm): " + ", ".join("%s %.0f" % (n, x) for n, x in sorted(dest.items(), key=lambda kv: -(kv[1] or 0))))
    if not moved:
        print("pin_swap: the header already follows the placement; nothing to move")
        return 0
    for pin, old, nn in moved:
        print("   pin %2d (x %.1f): %-10s -> %s" % (pin, PL.hdr_pin(pin)[0], old, nn))
    if "--apply" in argv:
        apply(new)
        print("pin_swap: gen/pins.py rewritten for %d pins; rebuild from the schematic step" % len(moved))
    else:
        print("pin_swap: %d pins would move (--apply to rewrite gen/pins.py)" % len(moved))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
