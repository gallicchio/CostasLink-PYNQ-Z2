#!/usr/bin/env python3
"""plot_link.py: the night's loopback link tests (linktests.py) as plots in bringup/data/board_A/plots/.

    python3 bringup/plot_link.py [schemes json]        default the newest schemes_*.json
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import plotstyle as P                                # noqa: E402
import matplotlib.pyplot as plt                      # noqa: E402
import numpy as np                                   # noqa: E402

DATA = os.path.join(HERE, "data", "board_A")
OUTP = os.path.join(DATA, "plots")


def newest(pat):
    fs = sorted(f for f in glob.glob(os.path.join(DATA, "link", pat)) if "partial" not in f)
    return fs[-1] if fs else None


def constellations(d, path):
    runs = [r for r in d["runs"] if r.get("constellations")]
    if not runs:
        return None
    r = runs[0]
    names = list(r["constellations"])
    fig, axs = plt.subplots(1, len(names), figsize=(3.9 * len(names), 4.6), sharex=True, sharey=True)
    allv = np.concatenate([np.r_[r["constellations"][n]["i"], r["constellations"][n]["q"]] for n in names])
    lo, hi = np.percentile(allv, 0.2) - 0.02, np.percentile(allv, 99.8) + 0.02
    for ax, n in zip(np.atleast_1d(axs), names):
        c = r["constellations"][n]
        i, q = np.asarray(c["i"]), np.asarray(c["q"])
        ax.plot(i, q, ".", ms=1.2, color=P.SERIES[0], alpha=0.35)
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_aspect("equal")
        ax.set_xlabel("I MON (V)")
        ax.set_ylabel("Q MON (V)")
        ax.set_title(n, pad=6)
        ax.grid(True)
    fig.suptitle("Board A's constellations in loopback, %d MHz, DSA %.2f dB (the inverted Costas lock, idle on %sQ)" % (
        d["mhz"], r["dsa"], "+" if r["rot_deg"] > 0 else "-"), x=0.01, ha="left", fontsize=12, fontweight="bold")
    P.source(fig, "bringup/linktests.py schemes; %s; I MON / Q MON at 1 Mohm through the taps' 1 k: 5 us events, the messages in turn" % os.path.relpath(path, HERE))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return P.save(fig, os.path.join(OUTP, "link_constellations_%d.png" % d["mhz"]))


def latency(d, path):
    rows = []
    for r in d["runs"]:
        for s in r.get("schemes", []):
            if s.get("lat_n") and s.get("hist"):
                rows.append((r["dsa"], s))
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    k = 0
    seen = set()
    rows.sort(key=lambda x: abs(x[0] - d.get("regulated_dsa", x[0])))
    for dsa, s in rows:
        key = (s["scheme"], s["first_edge"])
        if key in seen:
            continue
        seen.add(key)
        h = np.asarray(s["hist"], float)
        x = np.arange(len(h)) * 1.25
        if h.sum() == 0:
            continue
        ax.step(x, h / h.sum(), where="mid", color=P.SERIES[k % len(P.SERIES)], lw=1.8,
                label="%s%s (DSA %.2f): mean %.1f ns" % (s["scheme"], ", first edge" if s["first_edge"] else "", dsa,
                                                         s["lat_mean"] * 1.25))
        k += 1
    shown = [s for _, s in rows if (s["scheme"], s["first_edge"]) in seen]
    lo = min(s["lat_min"] for s in shown) * 1.25 - 4
    ax.set_xlim(lo, lo + 40)
    ax.set_xlabel("TX event to RX decision (ns, 1.25 ns samples)")
    ax.set_ylabel("fraction of events")
    ax.set_title("Loopback latency per scheme, %d MHz" % d["mhz"], pad=26)
    P.subtitle(ax, "From the FPGA's TX event (the ladder pins' register) to the decoder's decision: the receive half plus the decoder's clocks")
    ax.legend(loc="upper right")
    P.source(fig, "bringup/linktests.py schemes; %s; rx_engine.v's histogram (RX_HIST, 1 sample bins)" % os.path.relpath(path, HERE))
    return P.save(fig, os.path.join(OUTP, "link_latency_%d.png" % d["mhz"]))


def main(argv):
    P.setup()
    path = argv[1] if len(argv) > 1 else newest("schemes_*.json")
    d = json.load(open(path))
    for f in (constellations, latency):
        out = f(d, path)
        if out:
            print(out)


if __name__ == "__main__":
    main(sys.argv)
