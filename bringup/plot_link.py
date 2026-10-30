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


def lockmap(rows, out_name, title):
    """rows: (mhz, kind, dsa, offset_khz, state); one panel per frequency: DSA against start offset, coloured by state"""
    STATE = {"locked": (P.SERIES[2], "locked"), "false": (P.SERIES[3], "false lock"), "unlocked": (P.SERIES[1], "unlocked"),
             "railed": (P.SERIES[7], "railed"), "vc_clipped": (P.MUTED, "VC clipped"), "not_centred": (P.MUTED, "not centred")}
    mhzs = sorted({r[0] for r in rows})
    fig, axs = plt.subplots(1, len(mhzs), figsize=(5.2 * len(mhzs), 4.4), squeeze=False)
    for ax, m in zip(axs[0], mhzs):
        for st, (c, lab) in STATE.items():
            pts = [(r[3], r[2]) for r in rows if r[0] == m and r[4] == st]
            if pts:
                x, y = zip(*pts)
                ax.scatter(x, y, s=70, color=c, label=lab, edgecolor=P.SURFACE, linewidth=1.5, zorder=3)
        ax.set_xlabel("start offset from zero beat (kHz)")
        ax.set_ylabel("DSA (dB)")
        ax.set_title("%d MHz" % m, pad=8)
        ax.set_xscale("symlog", linthresh=2)
        ax.set_xticks([-40, -20, -10, -5, -2, 2, 5, 10, 20, 40])
        ax.set_xticklabels(["-40", "-20", "-10", "-5", "-2", "2", "5", "10", "20", "40"])
    h, l = axs[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper left", ncol=6, bbox_to_anchor=(0.005, 0.93))
    fig.suptitle(title, x=0.01, ha="left", fontsize=12, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    return P.save(fig, os.path.join(OUTP, out_name))


def lock_rows_from_log(path):
    rows = []
    for line in open(path):
        w = line.split()
        if len(w) > 12 and w[0].isdigit() and w[1] == "costas" and "->" in w:
            k = w.index("->")
            rows.append((int(w[0]), w[1], float(w[5]), int(w[7].replace("+", "")), w[k + 1]))
    return rows


def lock_rows_from_json(path):
    rows = []
    for rec in json.load(open(path)):
        for x in rec["rows"]:
            if x.get("kind") == "costas":
                rows.append((rec["mhz"], "costas", x["dsa"], x["offset_khz"], x["state"]))
    return rows


def tune_a3(paths):
    """A3r: the decided fraction and the mean latency against the decision delay, per window fraction and frequency"""
    fig, ax = plt.subplots(figsize=(9.5, 5.2))
    k = 0
    for path in paths:
        d = json.load(open(path))
        for fr in sorted({r["frac"] for r in d.get("runs", [])}):
            rs = sorted([r for r in d["runs"] if r["frac"] == fr], key=lambda r: r["delay"])
            x = [r["lat_mean"] * 1.25 for r in rs]
            y = [100.0 * sum(r["cm"][j][j] for j in range(4)) / r["refs"] for r in rs]
            ax.plot(x, y, "-o", color=P.SERIES[k % len(P.SERIES)], ms=7,
                    label="%d MHz, windows at %.2f a" % (d["mhz"], fr))
            for r, xi, yi in zip(rs, x, y):
                ax.annotate("%d" % r["delay"], (xi, yi), textcoords="offset points", xytext=(0, 7), ha="center",
                            fontsize=8, color=P.INK2)
            k += 1
    ax.set_xlabel("mean latency, TX event to decision (ns)")
    ax.set_ylabel("events decided right (%)")
    ax.set_title("A3r (two bits, four non-idle states): decided against latency", pad=26)
    P.subtitle(ax, "The fast I arm nulled first (I_OFF_F); the labels are the decision delay in samples after the first window fires")
    ax.legend(loc="lower right")
    P.source(fig, "bringup/linktests.py tune_a3; " + ", ".join(os.path.relpath(p_, HERE) for p_ in paths))
    return P.save(fig, os.path.join(OUTP, "link_a3r_tuning.png"))


def lodrive(path):
    """tests D and E: the change in the TX carrier at RX MON and in the I/Q beat against each synthesizer's APWR,
    in dB from the default (APWR 1, -1 dBm a side)"""
    d = json.load(open(path))
    fig, ax = plt.subplots(figsize=(9.0, 5.2))
    k = 0
    for what, key, label in (("tx_drive", "carrier", "TX level (RX MON), TX APWR"), ("rx_drive", "amp_i", "I beat, RX APWR")):
        for run in d[what]:
            rows = [r for r in run["rows"] if r.get(key)]
            ref = [r[key] for r in rows if r["apwr"] == 1]
            if not ref:
                continue
            ref = float(np.mean(ref))
            pts = {}
            for r in rows:
                v = r[key] - ref if what == "tx_drive" else 20 * np.log10(r[key] / ref)
                pts.setdefault(r["apwr_dbm"], []).append(v)
            xs = sorted(pts)
            ys = [float(np.mean(pts[x])) for x in xs]
            ax.plot(xs, ys, marker="o", ms=7, color=P.SERIES[k], ls="-" if what == "tx_drive" else "--",
                    label="%s, %.1f GHz" % (label, run["mhz"] / 1000))
            k += 1
    ax.axhline(0, color=P.AXIS, lw=0.8)
    ax.set_xticks([-4, -1, 2, 5])
    ax.set_xlabel("RFOUTA power per side, as programmed (dBm)")
    ax.set_ylabel("change from the default APWR (dB)")
    ax.set_title("Board A's LO drive changes nothing: both mixers' LO ports are saturated from -4 dBm", pad=30)
    P.subtitle(ax, "Loopback, 40 dB of pads, DSA fixed.  TX: the (1, 0) carrier at RX MON, the RX synthesizer parked 200 MHz off.  RX: the I arm's beat by sine fit, the loop held.")
    ax.legend(loc="best", ncol=2)
    P.source(fig, "bringup/linktests.py lodrive; %s" % os.path.relpath(path, HERE))
    return P.save(fig, os.path.join(OUTP, "link_lo_drive.png"))


def main(argv):
    P.setup()
    if len(argv) > 1 and argv[1] == "lodrive":
        print(lodrive(argv[2] if len(argv) > 2 else newest("lodrive_*.json")))
        return
    if len(argv) > 1 and argv[1] == "tune_a3":
        print(tune_a3(argv[2:]))
        return
    if len(argv) > 1 and argv[1] == "lock":
        rows = []
        for f in argv[2:]:
            rows += lock_rows_from_log(f) if f.endswith(".log") else lock_rows_from_json(f)
        print(lockmap(rows, "link_lock_map.png", "Where the inverted Costas lock catches: releases from a held beat, per DSA and start offset"))
        return
    path = argv[1] if len(argv) > 1 else newest("schemes_*.json")
    d = json.load(open(path))
    for f in (constellations, latency):
        out = f(d, path)
        if out:
            print(out)


if __name__ == "__main__":
    main(sys.argv)
