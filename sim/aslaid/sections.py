#!/usr/bin/env python3
"""Each passive section between two IC pins (or a jack and a pin), as laid out, with 50 ohm at its ends:
insertion loss and return loss against frequency.  What the full-chain model adds is the ICs' own match."""
import math, os, sys, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import circuit as C
import extract as X
import paths as P

SECTIONS = {
    "RX1 J101 to LNA in": (["Net-(J101-In)", "Net-(U101-RF_IN)"], "SMA:J101.1", "U101.3"),
    "RX2 LNA out to DSA": (["Net-(U101-RF_OUT)", "Net-(U102-RF1)"], "U101.4", None),
    "RX3 DSA to GB1": (["Net-(U102-RF2)", "Net-(U103-RFIN)"], None, "U103.1"),
    "RX4 GB1 to GB2": (["Net-(U103-RFOUT)", "Net-(U117-RFIN)"], "U103.3", "U117.1"),
    "RX5 GB2 to balun (CP101)": (["Net-(U117-RFOUT)", "Net-(CP101-IN)", "Net-(CP101-OUT)", "Net-(CP101-CPL)", "Net-(CP101-ISO)"], "U117.3", "T101.1"),
    "TX1 modulator to GB": (["Net-(U201-RFOUT)", "Net-(U202-RFIN)"], None, None),
    "TX2 GB to TX ANT (CP201)": (["Net-(U202-RFOUT)", "Net-(C213-Pad2)", "Net-(CP201-IN)", "Net-(CP201-OUT)", "Net-(CP201-CPL)", "Net-(CP201-ISO)"], "U202.3", "SMA:J202.1"),
}


def ends_of(nets):
    """the IC pins of a section: pads of U* parts on its nets"""
    out = []
    for p in X.board()["pad"]:
        if p["net"] in nets and p["ref"][0] == "U":
            out.append("%s.%s" % (p["ref"], p["num"]))
    return out


def section(name, nets, a, b, extra_ports=()):
    c = C.Circuit(name)
    info = X.extract(c, nets, skip_parts=P.CHOKES, supply_node=lambda n, x, y, r: P.plane_node(c, n, x, y, r))
    pad = info["pad"]
    ics = ends_of(nets)
    names = []
    for e in (a, b):
        if e is None:
            continue
        if e.startswith("SMA:"):
            P.add_launch(c, e, pad[e[4:]])
        else:
            c.port(e, pad[e])
        names.append(e)
    for e in ics:
        if e not in names:
            c.port(e, pad[e])
            names.append(e)
    for cp in ("CP101", "CP201"):
        if "%s.1" % cp in pad:
            P.add_coupler(c, pad, cp)
    for j in ("J102.1", "J201.1"):
        if j in pad:
            c.port(j, pad[j]); names.append(j)
    return c, names


if __name__ == "__main__":
    fs = [3.5e9, 4.5e9, 5.0e9, 5.5e9, 5.8e9, 6.0e9, 6.5e9]
    out = {}
    for name, (nets, a, b) in SECTIONS.items():
        c, names = section(name, nets, a, b)
        src = names[0]
        print("%s  ports %s" % (name, names))
        rows = []
        for f in fs:
            V = c.drive_port(f, src)
            s11 = V[c.ports[src][0]] - 1.0 if not src.startswith("SMA:") else V[c.ports[src][0]] - 1.0
            row = ["S11 %5.1f" % (20 * math.log10(abs(s11)))]
            for n2 in names[1:]:
                row.append("%s %5.1f" % (n2, 20 * math.log10(abs(V[c.ports[n2][0]]))))
            rows.append(row)
            print("   %.1f GHz  " % (f / 1e9) + "  ".join(row))
        out[name] = rows
    json.dump(out, open(os.path.join(HERE, "out", "sections.json"), "w"), indent=0)
