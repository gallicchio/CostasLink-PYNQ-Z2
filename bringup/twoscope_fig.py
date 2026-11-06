"""One page per link from twoscope.py's twoscope_<stamp>.json / .npz (data/twoboard): the cabling verdicts, each scheme's
constellation on the receiver's scope (the idle, each point's plateau, its trajectory as a faint line, the expected point
hollow, the decoder's right fraction), the time traces per scheme, the flip's Q against the level with its fit (the
receiver's Q offset and the sender's leak), the flip's edges and the numbers.  Pages to plots/twoscope_<stamp>_<link>.png.

    python3 twoscope_fig.py [twoscope_<stamp> | path/to/twoscope_<stamp>]        (the latest in data/twoboard by default)
"""
import json
import os
import sys
import textwrap

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "twoboard")
PLOTS = os.path.join(HERE, "plots")
BLUE, ORANGE, AQUA, RED, GREEN, VIOLET, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#008300", "#6250d6", "#1d2430", "#6b7280"
PCOL = [BLUE, ORANGE, AQUA, VIOLET]
SCHEMES = ["A1", "A1w", "A2", "A3", "A4", "B1", "B2"]

if len(sys.argv) > 1:
    base = sys.argv[1][:-5] if sys.argv[1].endswith(".json") else sys.argv[1]
    if not os.path.dirname(base):
        base = os.path.join(DATA, base)
else:
    base = os.path.join(DATA, sorted(f[:-5] for f in os.listdir(DATA) if f.startswith("twoscope_") and f.endswith(".json"))[-1])
J = json.load(open(base + ".json"))
A = np.load(base + ".npz")
META = json.loads(str(A["meta"]))
G = J["gain"]
os.makedirs(PLOTS, exist_ok=True)


def traces(m):
    """a capture's I(t), Q(t) in mV at the arm relative to the idle (the pre-mark level), CMP I and the mark; t in ns"""
    k = m["k"]
    t = A["t1_%d" % k] * 1e9
    out = {"t": t, "mark": A["v1_%d" % k], "cmp": A["v4_%d" % k]}
    for ch, nm in ((2, "i"), (3, "q")):
        d = G * (A["v%d_%d" % (ch, k)] - m["base"][str(ch)]) * 1e3
        d = d - np.median(d[(t > -150) & (t < -20)])
        out[nm] = d
    return out


def median_traces(ms):
    tr = [traces(m) for m in ms]
    t = tr[0]["t"]
    n = min(len(x["t"]) for x in tr)
    return {"t": t[:n], **{k: np.median(np.array([x[k][:n] for x in tr]), axis=0) for k in ("i", "q", "mark", "cmp")}}


for lk, rec in J["links"].items():
    if "error" in rec and "constellations" not in rec:
        continue
    if "constellations" not in rec:
        continue
    rx = lk[1]
    fig = plt.figure(figsize=(26, 19))
    gs = fig.add_gridspec(4, 7, height_ratios=[0.9, 1.6, 1.25, 1.0], hspace=0.5, wspace=0.3, left=0.035, right=0.99, top=0.94, bottom=0.05)
    lock = rec["lock"]
    fig.suptitle("%s at %g MHz on scope %s (board %s's I MON, Q MON, CMP I MON, triggered by board %s's TRIG A), %s: "
                 "lock DSA %.2f, leg %.0f mV, side %+d" % (lk, rec["mhz"], rx, rx, lk[0], J["stamp"], lock["dsa"], 1e3 * lock["leg"], lock["side"]),
                 fontsize=12, fontweight="bold")
    # row 0: the cabling verdicts and the marks, as text
    ax = fig.add_subplot(gs[0, :])
    ax.axis("off")
    cab = rec["cabling"]
    mk = cab["marks"]
    lines = ["1. CABLING (the idle (1, 0), the flip (-1, 0) and the carrier null held; the receiver's ADC and comparator against the scope; then the flip as events, the scope triggered on the sender's mark):"]
    for v in cab["verdicts"]:
        lines += textwrap.wrap("   " + v, 230, subsequent_indent="      ")
    ax.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=7.4, family="DejaVu Sans Mono", transform=ax.transAxes, color=INK)
    # row 1: constellations per scheme
    leg = 1e3 * lock["leg"]
    for col, sc in enumerate(SCHEMES):
        ax = fig.add_subplot(gs[1, col])
        row = next((r for r in rec["constellations"] if r["scheme"] == sc), None)
        ax.set_title(sc, fontsize=10, fontweight="bold")
        ax.axhline(0, color=MUTED, lw=0.6)
        ax.axvline(0, color=MUTED, lw=0.6)
        ax.set_aspect("equal")
        lim = 1.9 * leg
        ax.set_xlim(-lim, lim)
        ax.set_ylim(-lim, lim)
        ax.grid(alpha=0.2)
        ax.tick_params(labelsize=7)
        if col == 0:
            ax.set_ylabel("Q at the arm (mV, from the receiver's centre)", fontsize=8)
        ax.set_xlabel("I at the arm (mV)", fontsize=8)
        if row is None or not row.get("points"):
            ax.text(0.5, 0.5, "no points\n%s" % (row or {}).get("pilot", {}).get("vr", "") if row else "not run", ha="center", va="center", transform=ax.transAxes, fontsize=8, color=MUTED)
            continue
        idle = row["idle"]
        i0, q0 = 1e3 * idle["di"], 1e3 * idle["dq"]
        ax.plot([i0], [q0], "o", color=INK, ms=7, mfc="white", mew=1.5, zorder=5)
        ax.annotate("idle", (i0, q0), textcoords="offset points", xytext=(5, 5), fontsize=7, color=INK)
        ms_all = [m for m in META if m["stage"] == "constellation" and m["link"] == lk and m["scheme"] == sc]
        for p in row["points"]:
            c = PCOL[p["m"] % 4]
            ms = [m for m in ms_all if m["m"] == p["m"]]
            if ms:
                tr = median_traces(ms)
                t0 = p["cmp_edge_t"] if p["cmp_edge_t"] is not None else (p["mark_t"] or 0) + (ms[0].get("lat_ns") or 0)
                sel = (tr["t"] > t0 - 30) & (tr["t"] < t0 + 330)
                ax.plot(i0 + tr["i"][sel], q0 + tr["q"][sel], "-", color=c, lw=1.2, alpha=0.35, zorder=3)
            if p["i_plateau"] is not None:
                ax.plot([p["abs_i_mv"]], [p["abs_q_mv"]], "o", color=c, ms=7, zorder=6)
                ax.annotate("m%d (%g,%g)%s" % (p["m"], p["point"][0], p["point"][1], "" if p["right_frac"] is None else "\n%.0f %% right" % (100 * p["right_frac"])),
                            (p["abs_i_mv"], p["abs_q_mv"]), textcoords="offset points", xytext=(6, -4), fontsize=6.5, color=c)
            lg = 1e3 * (row.get("leg") or lock["leg"])
            ex, ey = i0 + p["rx_point"][0] * lg, q0 + p["rx_point"][1] * lg      # the ladder's point adds to the idle (the pilot)
            ax.plot([ex], [ey], "o", color=c, ms=9, mfc="none", mew=1.0, alpha=0.7, zorder=4)
        if row.get("pilot"):
            ax.text(0.02, 0.02, "pilot rho %s, VR %s" % (row["pilot"].get("rho"), row["pilot"].get("vr")), transform=ax.transAxes, fontsize=6.5, color=MUTED)
        dec = row.get("decoder") or {}
        if dec and "error" not in dec:
            ax.text(0.02, 0.96, "decoder: right %s\nidle false %.0f/s" % (
                ", ".join("%.0f %%" % (100 * r["right_frac"]) for r in dec["per_msg"].values()), dec.get("idle_false_per_s") or 0),
                transform=ax.transAxes, fontsize=6.5, color=INK, va="top")
    # row 2: time traces per scheme
    for col, sc in enumerate(SCHEMES):
        ax = fig.add_subplot(gs[2, col])
        ax.set_title("%s: I (solid), Q (dashed), CMP I (grey), the mark (dotted)" % sc, fontsize=8)
        ax.tick_params(labelsize=7)
        ax.set_xlim(-100, 420)
        ax.set_xlabel("ns from the sender's mark", fontsize=8)
        if col == 0:
            ax.set_ylabel("mV at the arm, from the idle", fontsize=8)
        ax.grid(alpha=0.2)
        ms_all = [m for m in META if m["stage"] == "constellation" and m["link"] == lk and m["scheme"] == sc]
        if not ms_all:
            continue
        ymax = 1.0
        for mi in sorted(set(m["m"] for m in ms_all)):
            ms = [m for m in ms_all if m["m"] == mi]
            tr = median_traces(ms)
            c = PCOL[mi % 4]
            ax.plot(tr["t"], tr["i"], "-", color=c, lw=1.3, label="m%d (%g,%g)" % (mi, ms[0]["point"][0], ms[0]["point"][1]))
            ax.plot(tr["t"], tr["q"], "--", color=c, lw=1.3)
            ymax = max(ymax, np.abs(tr["i"][(tr["t"] > -50) & (tr["t"] < 400)]).max(), np.abs(tr["q"][(tr["t"] > -50) & (tr["t"] < 400)]).max())
        tr = median_traces(ms_all[:8])
        ax2 = ax.twinx()
        ax2.plot(tr["t"], tr["cmp"], "-", color=MUTED, lw=0.8)
        ax2.plot(tr["t"], tr["mark"], ":", color=INK, lw=0.8)
        ax2.set_ylim(-0.3, 4.5)
        ax2.tick_params(labelsize=6, colors=MUTED)
        ax.set_ylim(-1.25 * ymax, 1.25 * ymax)
        ax.legend(fontsize=6, loc="lower right")
    # row 3: the flip against the level, the edges, the numbers
    ax = fig.add_subplot(gs[3, 0:2])
    lv = [r for r in rec.get("levels", []) if r.get("locked") and r.get("q_plateau") is not None]
    fit = ""
    if lv:
        legs = np.array([r["leg_mv"] for r in lv])
        qs = np.array([r["q_plateau"] for r in lv])
        ax.plot(legs, qs, "o-", color=GREEN, label="the flip's Q plateau (mV)")
        ax.plot(legs, [r["q_spike_min"] or 0 for r in lv], "s", color=RED, ms=5, label="Q spike min (0-40 ns)")
        ax.plot(legs, [(r["i_plateau"] or 0) / 2 for r in lv], "^-", color=BLUE, label="the flip's I plateau / 2 (mV; -leg expected)")
        for r in lv:
            ax.annotate("DSA %.2f: %+.0f mV = %+.0f %%" % (r["dsa"], r["q_plateau"], 100 * (r["q_frac"] or 0)), (r["leg_mv"], r["q_plateau"]),
                        textcoords="offset points", xytext=(0, 8), fontsize=6.5, ha="center")
        if len(lv) >= 2:
            k, b = np.polyfit(legs, qs, 1)
            xx = np.linspace(0, legs.max() * 1.05, 10)
            ax.plot(xx, k * xx + b, "--", color=GREEN, lw=0.9)
            fit = ("the flip's Q = %+.0f mV %+.1f %% of the leg: a receiver Q offset of %+.0f mV (half the intercept: the loop nulls the idle's Q, "
                   "so the flipped point shows twice the offset) and a sender leak of %.1f %% (%.1f degrees)" % (b, 100 * k, b / 2, 100 * abs(k), np.degrees(np.arctan(abs(k)))))
            rec.setdefault("fit", {})["q_vs_leg"] = {"slope": float(k), "intercept_mv": float(b)}
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.set_xlim(0, None)
    ax.set_xlabel("the leg (mV at the arm)", fontsize=8)
    ax.set_ylabel("mV at the arm", fontsize=8)
    ax.set_title("3. the flip (-1, 0) against the level on receiver %s\n%s" % (rx, textwrap.fill(fit, 110)), fontsize=8)
    ax.legend(fontsize=7, loc="lower left")
    ax.grid(alpha=0.25)
    ax.tick_params(labelsize=7)
    ax = fig.add_subplot(gs[3, 2:4])
    ms = [m for m in META if m["stage"] == "cabling" and m["link"] == lk]
    if ms:
        tr = median_traces(ms)
        ax.plot(tr["t"], tr["i"], "-", color=BLUE, lw=1.4, label="I arm")
        ax.plot(tr["t"], tr["q"], "--", color=ORANGE, lw=1.4, label="Q arm")
        ax2 = ax.twinx()
        ax2.plot(tr["t"], tr["cmp"], "-", color=MUTED, lw=0.9, label="CMP I MON (V)")
        ax2.plot(tr["t"], tr["mark"], ":", color=INK, lw=0.9, label="TRIG A (V)")
        ax2.set_ylim(-0.3, 4.5)
        ax2.tick_params(labelsize=6, colors=MUTED)
        ax2.legend(fontsize=6, loc="upper right")
        e = mk.get("cmp_edge_t") or 0
        ax.set_xlim(min(-20, e - 60), e + 120)
        ax.axvline(e, color=RED, lw=0.8, ls=":")
    ax.set_title("the flip's edges: the mark, the I arm, CMP I (mark to CMP I %s ns; I's half-way to CMP I %s ns; I 10-90 %% %s ns)" % (
        "%.1f" % mk["latency_ns"] if mk.get("latency_ns") is not None else "-", "%.1f" % mk["cmp_delay_ns"] if mk.get("cmp_delay_ns") is not None else "-",
        "%.1f" % mk["i_rise"] if mk.get("i_rise") is not None else "-"), fontsize=8)
    ax.set_xlabel("ns from the mark", fontsize=8)
    ax.set_ylabel("mV at the arm", fontsize=8)
    ax.legend(fontsize=6, loc="lower left")
    ax.grid(alpha=0.25)
    ax.tick_params(labelsize=7)
    ax = fig.add_subplot(gs[3, 4:7])
    ax.axis("off")
    lines = ["2. CONSTELLATIONS: per scheme the decoder's view (events_point at frac 0.4, delay 16) then each message's events (width 20, period 1000) captured on the mark, 8 shots:",
             "   filled dot = the plateau 60-180 ns after the arrival, hollow = the expected point (the idle + rx_point x leg), the faint line = the median trajectory from 30 ns before the arrival to 330 after.", ""]
    for row in rec["constellations"]:
        if not row.get("points"):
            lines.append("   %s: no points (%s)" % (row["scheme"], (row.get("pilot") or {}).get("vr")))
            continue
        for p in row["points"]:
            ang = np.degrees(np.arctan2(p["abs_q_mv"], p["abs_i_mv"]))
            eang = np.degrees(np.arctan2(p["rx_point"][1], p["rx_point"][0])) if any(p["rx_point"]) else 0
            lines.append("   %-3s m%d (%2g,%2g): plateau (%+4.0f, %+4.0f) mV = %.2f x leg at %+4.0f deg (expected %+4.0f), spike Q %+4.0f/%+4.0f, I %+4.0f/%+4.0f, return Q %+4.0f, CMP moved %d/%d, I 10-90 %s ns, right %s" % (
                row["scheme"], p["m"], p["point"][0], p["point"][1], p["abs_i_mv"], p["abs_q_mv"], np.hypot(p["abs_i_mv"], p["abs_q_mv"]) / leg, ang, eang,
                p["q_spike_min"] or 0, p["q_spike_max"] or 0, p["i_spike_min"] or 0, p["i_spike_max"] or 0, p["q_ret_max"] or 0, p["cmp_moved"], p["n"],
                "%.0f" % p["i_rise"] if p.get("i_rise") else "-", "%.0f %%" % (100 * p["right_frac"]) if p["right_frac"] is not None else "-"))
    ts = cab["rows"][0]["tx_scope"]
    lines += ["", "   scope %s (the sender's own monitors, its receiver without a carrier): ch1 max %.2f V, I %.3f V, Q %.3f V, CMP %.2f V" % (
        lk[0], ts["1"]["max"], G * ts["2"]["dc"], G * ts["3"]["dc"], ts["4"]["dc"])]
    ax.text(0, 1, "\n".join(lines), va="top", ha="left", fontsize=6.3, family="DejaVu Sans Mono", transform=ax.transAxes, color=INK)
    out = os.path.join(PLOTS, "%s_%s.png" % (os.path.basename(base), lk))
    fig.savefig(out, dpi=100)
    print(out)
