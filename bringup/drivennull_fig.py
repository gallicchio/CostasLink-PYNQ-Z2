"""The driven null's page from drivennull.py's run: per sender the flip's Q (as a fraction of the leg) against the VR_Q
offset at each frequency and level, the zeros; the table; and the 3 x 3 ladder constellation on the receiver's scope at
the zero-ladder null and at the driven null, per sender and frequency.
    python3 drivennull_fig.py [drivennull_<stamp>]  ->  plots/drivennull_<stamp>.png / .pdf"""
import json
import math
import os
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                 # noqa: E402
import numpy as np                                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ.get("CL_BRINGUP", HERE), "data", "twoboard")     # the project's bringup/, or another copy's
BLUE, ORANGE, AQUA, RED, GREEN, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#008300", "#6250d6"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
FCOL = {4800.0: BLUE, 5000.0: ORANGE, 5200.0: AQUA, 5400.0: VIOLET}
PCOL = {(-1, 0): BLUE, (0, 1): ORANGE, (0, -1): AQUA, (1, 1): VIOLET, (1, -1): "#b5651d", (-1, 1): "#2f8f9d", (-1, -1): "#c23b8a", (0, 0): "#6b6b6b"}

base = sys.argv[1] if len(sys.argv) > 1 else sorted(f[:-5] for f in os.listdir(DATA) if f.startswith("drivennull_") and f.endswith(".json"))[-1]
if not os.path.dirname(base):
    base = os.path.join(DATA, base)
J = json.load(open(base + ".json"))
Z = np.load(base + ".npz")
META = json.loads(str(Z["meta"]))
G = J.get("gain", 21.0)


def trace(m):
    k = m["k"]
    t = Z["t1_%d" % k] * 1e9
    out = {"t": t}
    for ch, nm in ((2, "i"), (3, "q")):
        d = (Z["v%d_%d" % (ch, k)] - m["base"][str(ch)]) * 1e3 * G
        d = d - float(np.median(d[(t > -150) & (t < -20)]))
        out[nm] = d
    c = Z["v4_%d" % k]
    pre = float(np.median(c[(t > -150) & (t < -20)]))
    idle = pre > 0.15
    hit = np.where((c > 0.15) != idle)[0]
    hit = hit[t[hit] > -20] if len(hit) else hit
    out["t0"] = float(t[hit[0]]) if len(hit) else float(m.get("lat_ns") or 8.0)
    return out


runs = [r for r in J["runs"] if "error" not in r or r.get("scans")]
senders = sorted({r["sender"] for r in runs})
mhzs = sorted({r["mhz"] for r in runs})
fig = plt.figure(figsize=(24, 8 + 5.6 * len(mhzs)), dpi=100)
gs = fig.add_gridspec(1 + len(mhzs), 4, height_ratios=[1.25] + [1] * len(mhzs), left=0.035, right=0.99, top=0.955, bottom=0.025, hspace=0.5, wspace=0.22)

# ---- row 0: the scans per sender, and the table ----
table = []
for col, snd in enumerate(senders):
    ax = fig.add_subplot(gs[0, col])
    for sp in ax.spines.values():
        sp.set_color(GRID)
    for r in [r for r in runs if r["sender"] == snd]:
        c = FCOL.get(r["mhz"], INK)
        for n, sc in enumerate(r.get("scans", [])):
            rows = [x for x in sc.get("rows", []) if x.get("q_plateau") is not None]
            if not rows:
                continue
            xs = [x["d_mv"] for x in rows]
            ys = [x["q_plateau"] / sc["leg_mv"] for x in rows]
            ax.plot(xs, ys, "o-" if n == 0 else "s--", color=c, ms=4, lw=1.0, alpha=0.9 if n == 0 else 0.6,
                    label="%g MHz, leg %.0f mV" % (r["mhz"], sc["leg_mv"]))
        d = r.get("driven") or {}
        if d.get("d_mv") is not None:
            ax.axvline(d["d_mv"], color=c, lw=0.8, ls=":")
        table.append((snd, r["mhz"], r["null"]["vr"][1], d.get("d_mv"), d.get("vr_q"), d.get("k_at_null"), d.get("rx_offset_mv"), d.get("zero_per_level_mv"),
                      (r.get("check_at_driven") or {}).get("q_plateau"), (r.get("constellations") or {}).get("driven", {}).get("leg_mv"),
                      r.get("lock", {}).get("side"), r.get("lock", {}).get("dsa"), r.get("lock", {}).get("leg")))
    ax.axhline(0, color=GRID, lw=0.8)
    ax.axvline(0, color=GRID, lw=0.8)
    ax.set_xlabel("the sender's VR_Q offset from its zero-ladder null, mV", fontsize=8)
    ax.set_ylabel("the flip's Q plateau as a fraction of the leg", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.legend(fontsize=6.5, frameon=False, ncol=2)
    ax.set_title("board %s sending: the flipped carrier's quadrature against VR_Q\n(circles at the lock's level, squares 9 dB stronger; dotted: the zero)" % snd,
                 fontsize=8.5, loc="left", fontweight="bold")
ax = fig.add_subplot(gs[0, 2:4])
ax.axis("off")
lines = ["The driven null per sender and frequency (two levels each, fitted as Q = 2 x the receiver's offset + k(d) x leg, k linear in d):", ""]
lines.append("%-6s %-6s %-9s %-9s %-9s %-9s %-10s %-14s %-12s %-8s" % ("sender", "MHz", "null VR_Q", "d* mV", "VR_Q*", "k at null", "rx off mV", "zeros/level mV", "check Q/leg", "lock"))
for snd, mhz, vq0, dstar, vqs, k, off, zl, chk, legd, side, dsa, leg in table:
    lines.append("%-6s %-6g %-9.4f %-9s %-9s %-9s %-10s %-14s %-12s DSA %.2f %.0f mV %+d" % (
        snd, mhz, vq0, "%+.1f" % dstar if dstar is not None else "?", "%.4f" % vqs if vqs else "?", "%+.3f" % k if k is not None else "?",
        "%+.1f" % off if off is not None else "?", "/".join("%+.0f" % z for z in (zl or []) if z is not None), "%+.3f" % (chk / legd) if chk is not None and legd else "?",
        dsa or 0, 1e3 * (leg or 0), side or 0))
lines.append("")
lines.append(textwrap.fill("Reading it: the sender's I ladder, driven to +a or -a, puts a quadrature component k x a onto its carrier (REVB 66), the same "
                           "sign in both states; the receiver's loop nulls the idle's Q with it in, so the flipped point shows 2 k x leg (the plateau "
                           "fraction is k itself as plotted, the leg being the idle's I).  VR_Q adds a fixed Q to every state, so there is one VR_Q, "
                           "the driven null, at which the driven carrier is pure I; the zero-ladder null (the FPV-antenna table) is the other "
                           "calibration, for the pilot schemes' idle, and the two differ by d*.  The receiver's own Q offset is the level-free part "
                           "(the fit's intercept over two), small on both boards since B's Q_OFF_F trim (4.76).  d* is 30-50 mV on both boards at "
                           "every frequency, the leak 14-21 % (8-12 degrees); the per-level zeros differ by up to 10 mV, so the two-level fit is "
                           "the number to use.  The constellations below: the eight ladder points from the idle (1, 0) on the receiver's scope, "
                           "trajectories from the idle to the point and back (x21 through the 1 k taps, 5 shots), at the zero-ladder null and at "
                           "the driven null; the -I points' Q offset is what the driven null removes.  (0, 0) is the carrier off for 200 ns: it put "
                           "the loop on its other side every time (noted on the panel).", 150))
ax.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=7.6, family="DejaVu Sans Mono", color=INK)

# ---- the constellations ----
by = {}
for m in META:
    if m.get("stage") == "constellation":
        by.setdefault((m["link"], m["mhz"], m["which"]), []).append(m)
for row, mhz in enumerate(mhzs):
    col = 0
    for snd in senders:
        r = next((r for r in runs if r["sender"] == snd and r["mhz"] == mhz), None)
        for which in ("null", "driven"):
            ax = fig.add_subplot(gs[row + 1, col])
            col += 1
            for sp in ax.spines.values():
                sp.set_color(GRID)
            ax.set_aspect("equal")
            ax.tick_params(labelsize=6.5, colors=INK2)
            c = (r or {}).get("constellations", {}).get(which) if r else None
            ms = by.get((r["link"], mhz, which), []) if r else []
            if not c or not ms:
                ax.text(0.5, 0.5, "not measured", ha="center", va="center", color=MUTED, transform=ax.transAxes)
                ax.set_title("%s sending at %g MHz, %s" % (snd, mhz, which), fontsize=7.5, loc="left", fontweight="bold")
                continue
            leg = c["leg_mv"]
            lim = leg * 2.3
            ax.set_xlim(-lim, lim)
            ax.set_ylim(-lim * 0.75, lim * 0.75)
            ax.axhline(0, color=GRID, lw=0.6)
            ax.axvline(0, color=GRID, lw=0.6)
            side0 = c["side"]
            for pt, col_ in PCOL.items():
                ideal = (leg * (pt[0] - 1), leg * pt[1])
                ax.plot(ideal[0], ideal[1], "+", color=MUTED, ms=9, mew=1.0, zorder=3)
            flips = {tuple(x[0]) for x in c.get("side_changes", [])}
            for m in ms:
                pt = tuple(int(x) for x in m["point"])
                if m.get("side", side0) != side0:
                    continue                                  # a point taken after the lock changed side: left off the plane
                tr = trace(m)
                w = (tr["t"] > tr["t0"] - 40) & (tr["t"] < tr["t0"] + 330)
                ax.plot(tr["i"][w], tr["q"][w], color=PCOL[pt], lw=0.6, alpha=0.35, zorder=2)
            notes = []
            for p in c["points"]:
                pt = tuple(p["point"])
                if p.get("side", side0) != side0 or p.get("i_plateau") is None:
                    continue
                ax.plot(p["i_plateau"], p["q_plateau"], "o", color=PCOL[pt], ms=6, zorder=5, mec=INK, mew=0.6)
                ax.text(p["i_plateau"] + lim * 0.02, p["q_plateau"] + lim * 0.02, "(%d,%d)" % pt, fontsize=6, color=INK)
                notes.append("(%d,%d) %+.0f,%+.0f" % (pt[0], pt[1], p["i_plateau"], p["q_plateau"]))
            ax.plot(0, 0, "s", color=GREEN, ms=8, zorder=6)
            a3 = c.get("A3") or {}
            gaps = a3.get("gaps_mv") or {}
            flip = next((p for p in c["points"] if p["point"] == [-1, 0]), {})
            ax.set_title("%s sends at %g MHz on %s's scope, %s (VR_Q %.4f)\nleg %.0f mV, side %+d; the flip's Q %+.0f mV (%+.2f of the leg); A3 right %s, "
                         "gaps QP %s QN %s%s" % (
                             snd, mhz, r["link"][1], "the zero-ladder null" if which == "null" else "the driven null",
                             r["null"]["vr"][1] if which == "null" else (r.get("driven") or {}).get("vr_q") or 0, leg, side0, flip.get("q_plateau") or 0,
                             (flip.get("q_plateau") or 0) / leg, "%.4f" % a3["right_frac_min"] if a3.get("right_frac_min") is not None else a3.get("error"),
                             gaps.get("QP"), gaps.get("QN"), "; (0,0) flipped the loop's side" if (0, 0) in flips else ""), fontsize=6.3, loc="left", fontweight="bold")
            ax.set_xlabel("I, mV from the idle at the arm", fontsize=6.3, color=INK2)
            ax.set_ylabel("Q, mV", fontsize=6.3, color=INK2)
            ax.text(0.01, 0.01, "  ".join(notes), transform=ax.transAxes, fontsize=5.4, color=INK2, va="bottom")
fig.text(0.035, 0.975, "The driven null over the cables, %s: each sender's VR_Q offset that takes the quadrature out of its driven carrier, per frequency, "
         "and the 3 x 3 constellation before and after" % J["stamp"], fontsize=12, fontweight="bold", va="bottom")
out = os.path.join(HERE, "plots", os.path.basename(base))
fig.savefig(out + ".png", dpi=80)
fig.savefig(out + ".pdf")
print(out)
