"""The pages of series.py's run: the DSA series as one page per level (both receivers' I/Q planes with the flip and
A3's corners, the time traces, the decoder's numbers) and a summary page (the leg, the flip's quadrature, A3 / B1 /
PRBS against the level); the width series (the traces per width, the decoder against the width); the event-rate series
(the loop's pull against the duty).  One PDF, PNGs per page.
    python3 series_fig.py [series_<stamp>]  ->  plots/series_<stamp>.pdf and series_<stamp>_<page>.png"""
import json
import math
import os
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                 # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages            # noqa: E402
import numpy as np                                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = "/home/jason/OpticsPCBs/CostasLink-PYNQ-Z2/bringup/data/twoboard"
BLUE, ORANGE, AQUA, RED, GREEN, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#008300", "#6250d6"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
PCOL = {(-1, 0): BLUE, (1, 1): ORANGE, (1, -1): AQUA, (-1, 1): VIOLET, (-1, -1): "#c23b8a"}
LCOL = {"BA": BLUE, "AB": ORANGE}
LNAME = {"BA": "receiver A (B -> A)", "AB": "receiver B (A -> B)"}

base = sys.argv[1] if len(sys.argv) > 1 else sorted(f[:-5] for f in os.listdir(DATA) if f.startswith("series_") and f.endswith(".json"))[-1]
if not os.path.dirname(base):
    base = os.path.join(DATA, base)
J = json.load(open(base + ".json"))
Z = np.load(base + ".npz")
META = json.loads(str(Z["meta"]))
G = J.get("gain", 21.0)
out = os.path.join(HERE, "plots", os.path.basename(base))


def trace(m):
    k = m["k"]
    t = Z["t1_%d" % k] * 1e9
    o = {"t": t, "cmp": Z["v4_%d" % k]}
    for ch, nm in ((2, "i"), (3, "q")):
        d = (Z["v%d_%d" % (ch, k)] - m["base"][str(ch)]) * 1e3 * G
        d = d - float(np.median(d[(t > -150) & (t < -20)]))
        o[nm] = d
    c = o["cmp"]
    pre = float(np.median(c[(t > -150) & (t < -20)]))
    hit = np.where(((c > 0.15) != (pre > 0.15)) & (t > -20))[0]
    o["t0"] = float(t[hit[0]]) if len(hit) else 6.0
    return o


def meta_for(stage, lk, **kv):
    return [m for m in META if m.get("stage") == stage and m.get("link") == lk and all(m.get(k) == v for k, v in kv.items())]


def pct(d):
    if not d or d.get("error") or not d.get("per_msg"):
        return None
    return min(r["right_frac"] for r in d["per_msg"].values())


def frame(ax):
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(labelsize=6.5, colors=INK2)


pages = []
with PdfPages(out + ".pdf") as pdf:
    # ---- the DSA series: a page per step ----
    steps = sorted({r["step"] for lk in J["links"] for r in J["links"][lk].get("dsa", [])})
    for step in steps:
        fig = plt.figure(figsize=(24, 13), dpi=100)
        gs = fig.add_gridspec(2, 4, height_ratios=[1.3, 1], left=0.035, right=0.99, top=0.9, bottom=0.06, hspace=0.4, wspace=0.25)
        head = []
        for col, lk in enumerate(("BA", "AB")):
            rec = J["links"].get(lk) or {}
            row = next((r for r in rec.get("dsa", []) if r["step"] == step), None)
            axp = fig.add_subplot(gs[0, 2 * col])
            axt = fig.add_subplot(gs[0, 2 * col + 1])
            axn = fig.add_subplot(gs[1, 2 * col:2 * col + 2])
            frame(axp)
            frame(axt)
            axn.axis("off")
            lock = rec.get("lock") or {}
            if not row or not row.get("locked"):
                axp.text(0.5, 0.5, "nothing locked at this level" if row else "not run", ha="center", va="center", color=MUTED, transform=axp.transAxes)
                axp.set_title("%s: DSA %s" % (LNAME[lk], "%.2f" % row["dsa"] if row else "?"), fontsize=8, loc="left", fontweight="bold")
                axt.axis("off")
                continue
            leg = row["leg_mv"]
            axp.set_aspect("equal")
            lim = leg * 2.4
            axp.set_xlim(-lim, lim * 0.5)
            axp.set_ylim(-lim * 0.7, lim * 0.7)
            axp.axhline(0, color=GRID, lw=0.6)
            axp.axvline(0, color=GRID, lw=0.6)
            # the decoder's thresholds for A3
            a3 = row.get("A3") or {}
            th, lv = a3.get("thresholds") or {}, a3.get("levels") or {}
            b = lv.get("1,0") or {}
            for w, (c_, sg) in {"QP": (1, 1), "QN": (1, -1), "IP": (0, 1), "IN": (0, -1)}.items():
                if th.get(w) is not None and b.get(w) is not None:
                    v = sg * 1e3 * (th[w] - b[w])
                    if abs(v) < 1.5 * lim:
                        (axp.axhline if c_ == 1 else axp.axvline)(v, color=RED, lw=0.9, alpha=0.7)
            for m in meta_for("dsa", lk, step=step):
                pt = tuple(int(x) for x in m["point"])
                tr = trace(m)
                w = (tr["t"] > tr["t0"] - 40) & (tr["t"] < tr["t0"] + 330)
                axp.plot(tr["i"][w], tr["q"][w], color=PCOL.get(pt, INK), lw=0.6, alpha=0.4)
                ww = (tr["t"] > tr["t0"] - 80) & (tr["t"] < tr["t0"] + 360)
                axt.plot(tr["t"][ww] - tr["t0"], tr["i"][ww], color=PCOL.get(pt, INK), lw=0.5, alpha=0.5)
                axt.plot(tr["t"][ww] - tr["t0"], tr["q"][ww], color=PCOL.get(pt, INK), lw=0.5, alpha=0.5, ls="--")
            for p in row["points"]:
                pt = tuple(p["point"])
                axp.plot(leg * (pt[0] - 1), leg * pt[1], "+", color=MUTED, ms=9, mew=1.0)
                if p.get("i_plateau") is not None:
                    axp.plot(p["i_plateau"], p["q_plateau"], "o", color=PCOL.get(pt, INK), ms=6, mec=INK, mew=0.6, zorder=5)
                    axp.text(p["i_plateau"] + lim * 0.02, p["q_plateau"] + lim * 0.02, "(%d,%d)" % pt, fontsize=6.5)
            axp.plot(0, 0, "s", color=GREEN, ms=8, zorder=6)
            flip = row["points"][0]
            axp.set_title("%s: DSA %.2f (%+d dB from the lock's %.2f), leg %.0f mV, side %+d; the flip's Q %+.0f mV (%+.2f of the leg)" % (
                LNAME[lk], row["dsa"], step, lock.get("dsa", 0), leg, row["side"], flip.get("q_plateau") or 0, (flip.get("q_plateau") or 0) / leg),
                fontsize=7.5, loc="left", fontweight="bold")
            axp.set_xlabel("I, mV from the idle at the arm", fontsize=6.5)
            axp.set_ylabel("Q, mV", fontsize=6.5)
            axt.set_xlim(-80, 360)
            axt.axvline(0, color=GRID, lw=0.8)
            axt.grid(color=GRID, lw=0.4)
            axt.set_xlabel("ns after the arrival (CMP I's edge)", fontsize=6.5)
            axt.set_ylabel("mV at the arm (I solid, Q dashed)", fontsize=6.5)
            axt.set_title("the flip and A3's corners in time, %d shots each" % row["points"][0]["n"], fontsize=7.5, loc="left", fontweight="bold")
            b1 = row.get("B1") or {}
            pr = row.get("prbs50") or {}
            lines = ["A3 by the decoder: " + ("error %s" % a3["error"] if a3.get("error") else "right %s, idle false %.0f/s, gaps %s, dead %s" % (
                "/".join("%.4g" % (100 * min(1.0, r["right_frac"])) for m, r in sorted((a3.get("per_msg") or {}).items(), key=lambda kv: int(kv[0]))) + " %",
                a3.get("idle_false_per_s") or 0, a3.get("gaps_mv"), a3.get("dead")))]
            pil = b1.get("pilot") or {}
            lines.append("B1 by the decoder: " + ("error %s" % b1["error"] if b1.get("error") else "right %s, idle false %.0f/s, gaps %s, dead %s" % (
                "/".join("%.4g" % (100 * min(1.0, r["right_frac"])) for m, r in sorted((b1.get("per_msg") or {}).items(), key=lambda kv: int(kv[0]))) + " %",
                b1.get("idle_false_per_s") or 0, b1.get("gaps_mv"), b1.get("dead"))) + (
                "; the pilot %.0f mV (rho %.2f of a %.0f mV axis point, VR %s)" % (1e3 * pil["rho"] * pil["a"], pil["rho"], 1e3 * pil["a"], pil.get("vr")) if pil.get("rho") else "; no pilot held"))
            lines.append("PRBS bpsk at 50 clocks a bit: " + ("error %s" % pr["error"] if pr.get("error") else "BER %s over %s bits (%s mismatches)" % (
                "0" if not pr.get("ber") else "%.2g" % pr["ber"], pr.get("bits"), pr.get("mismatches"))))
            lines.append("the scope's plateaus (mV from the idle): " + "; ".join("(%d,%d) I %+.0f Q %+.0f, spike Q %+.0f/%+.0f, I rise %s ns" % (
                p["point"][0], p["point"][1], p["i_plateau"] or 0, p["q_plateau"] or 0, p["q_spike_min"] or 0, p["q_spike_max"] or 0,
                "%.1f" % p["i_rise"] if p.get("i_rise") else "-") for p in row["points"]))
            axn.text(0, 1, "\n".join(textwrap.fill(x, 150) for x in lines), va="top", fontsize=7.3, color=INK)
        fig.suptitle("The step attenuator series at %g MHz over the cables (%s): the lock's DSA %+d dB, page %d of %d" % (
            J["mhz"], J["stamp"], step, steps.index(step) + 1, len(steps)), fontsize=12, fontweight="bold")
        pdf.savefig(fig)
        fig.savefig("%s_dsa%+03d.png" % (out, step), dpi=72)
        plt.close(fig)
    # ---- the DSA summary ----
    fig, axs = plt.subplots(2, 3, figsize=(24, 12), dpi=100)
    fig.subplots_adjust(left=0.05, right=0.99, top=0.9, bottom=0.07, hspace=0.4, wspace=0.28)
    for lk in ("BA", "AB"):
        rows = [r for r in (J["links"].get(lk) or {}).get("dsa", []) if r.get("locked")]
        if not rows:
            continue
        c = LCOL[lk]
        dsa = np.array([r["dsa"] for r in rows])
        leg = np.array([r["leg_mv"] for r in rows])
        axs[0, 0].plot(dsa, leg, "o-", color=c, label=LNAME[lk])
        axs[0, 0].set_yscale("log")
        axs[0, 1].plot(leg, [(r["points"][0]["q_plateau"] or 0) / r["leg_mv"] for r in rows], "o-", color=c, label=LNAME[lk])
        axs[0, 2].plot(leg, [100 * (pct(r.get("A3")) or 0) for r in rows], "o-", color=c, label=LNAME[lk] + " A3")
        axs[0, 2].plot(leg, [100 * (pct(r.get("B1")) or 0) for r in rows], "s--", color=c, alpha=0.6, label=LNAME[lk] + " B1")
        for w, ls in (("QP", "-"), ("IP", "--")):
            axs[1, 0].plot(leg, [((r.get("A3") or {}).get("gaps_mv") or {}).get(w) or 0 for r in rows], "o" + ls, color=c, alpha=0.9 if w == "QP" else 0.5, label="%s %s" % (LNAME[lk], w))
        axs[1, 1].plot(leg, [max(1e-8, (r.get("prbs50") or {}).get("ber") or 0) for r in rows], "o-", color=c, label=LNAME[lk])
        axs[1, 1].set_yscale("log")
        axs[1, 2].plot(leg, [1e3 * ((r.get("B1") or {}).get("pilot") or {}).get("rho", 0) * ((r.get("B1") or {}).get("pilot") or {}).get("a", 0) for r in rows], "o-", color=c, label=LNAME[lk])
    for ax, (xl, yl, t) in zip(axs.flat, [("the DSA, dB", "the leg, mV", "the leg against the attenuator"),
                                         ("the leg, mV", "the flip's Q plateau / the leg", "the sender's quadrature term against the level (level-free: the transmitter's)"),
                                         ("the leg, mV", "right, % (the worst message)", "A3 (solid) and B1 (dashed) by the decoder against the level"),
                                         ("the leg, mV", "the window's gap, mV", "A3's window gaps (QP solid, IP dashed) against the level"),
                                         ("the leg, mV", "BER (1e-8 = none)", "the PRBS bpsk at 50 clocks a bit against the level"),
                                         ("the leg, mV", "the pilot held, mV", "B1's pilot as held against the level (0 = not held)")]):
        frame(ax)
        ax.set_xlabel(xl, fontsize=8)
        ax.set_ylabel(yl, fontsize=8)
        ax.set_title(t, fontsize=9, loc="left", fontweight="bold")
        ax.legend(fontsize=7, frameon=False)
        ax.grid(color=GRID, lw=0.4)
    fig.suptitle("The step attenuator series at %g MHz over the cables (%s): the summary" % (J["mhz"], J["stamp"]), fontsize=12, fontweight="bold")
    pdf.savefig(fig)
    fig.savefig("%s_dsa_summary.png" % out, dpi=72)
    plt.close(fig)
    # ---- the width series ----
    widths = sorted({r["width"] for lk in J["links"] for r in J["links"][lk].get("width", [])})
    if widths:
        fig = plt.figure(figsize=(24, 14), dpi=100)
        gs = fig.add_gridspec(3, len(widths), height_ratios=[1, 1, 0.8], left=0.035, right=0.99, top=0.9, bottom=0.06, hspace=0.45, wspace=0.25)
        for row_, lk in enumerate(("BA", "AB")):
            rows = (J["links"].get(lk) or {}).get("width", [])
            for col, w in enumerate(widths):
                ax = fig.add_subplot(gs[row_, col])
                frame(ax)
                r = next((x for x in rows if x["width"] == w), None)
                if not r:
                    ax.axis("off")
                    continue
                span = min(10 * w + 150, 2400)
                for m in meta_for("width", lk, width=w):
                    pt = tuple(int(x) for x in m["point"])
                    tr = trace(m)
                    ww = (tr["t"] > tr["t0"] - 60) & (tr["t"] < tr["t0"] + span)
                    ax.plot(tr["t"][ww] - tr["t0"], tr["i"][ww], color=PCOL.get(pt, INK), lw=0.6, alpha=0.5)
                    ax.plot(tr["t"][ww] - tr["t0"], tr["q"][ww], color=PCOL.get(pt, INK), lw=0.6, alpha=0.5, ls="--")
                ax.axvline(0, color=GRID, lw=0.8)
                ax.axvline(10 * w, color=GRID, lw=0.8, ls=":")
                ax.set_xlim(-60, span)
                ax.grid(color=GRID, lw=0.4)
                a3 = r.get("A3") or {}
                ax.set_title("%s, %d clocks = %.0f ns\nflip I %+.0f Q %+.0f (extreme %+.0f/%+.0f); (1,1) I %+.0f Q %+.0f\nA3 right %s" % (
                    LNAME[lk], w, 10 * w, r["points"][0]["i_plateau"] or 0, r["points"][0]["q_plateau"] or 0, r["points"][0]["i_extreme"] or 0, r["points"][0]["q_extreme"] or 0,
                    r["points"][1]["i_plateau"] or 0, r["points"][1]["q_plateau"] or 0, "%.4g %%" % (100 * pct(a3)) if pct(a3) is not None else a3.get("error")), fontsize=6.5, loc="left")
                ax.set_xlabel("ns after the arrival", fontsize=6.5)
                if col == 0:
                    ax.set_ylabel("mV at the arm (I solid, Q dashed; blue the flip, orange (1,1))", fontsize=6.5)
        ax = fig.add_subplot(gs[2, :])
        frame(ax)
        for lk in ("BA", "AB"):
            rows = (J["links"].get(lk) or {}).get("width", [])
            if rows:
                ax.plot([r["width"] for r in rows], [100 * (pct(r.get("A3")) or 0) for r in rows], "o-", color=LCOL[lk], label=LNAME[lk] + " A3 right (worst message)")
                ax.plot([r["width"] for r in rows], [100 * abs(r["points"][0]["i_extreme"] or 0) / (2 * r["leg_mv"]) for r in rows], "s--", color=LCOL[lk], alpha=0.6,
                        label=LNAME[lk] + " the flip's I excursion, % of the full 2 legs")
        ax.set_xscale("log")
        ax.set_xlabel("the event's width, clocks of 10 ns", fontsize=8)
        ax.set_ylabel("%", fontsize=8)
        ax.grid(color=GRID, lw=0.4)
        ax.legend(fontsize=7, frameon=False)
        ax.set_title("the decoder and the arms' excursion against the event's width (the dotted line in each panel is the event's end)", fontsize=9, loc="left", fontweight="bold")
        fig.suptitle("The event-width series at %g MHz over the cables (%s): the flip and the (1,1) corner on each receiver's scope" % (J["mhz"], J["stamp"]),
                     fontsize=12, fontweight="bold")
        pdf.savefig(fig)
        fig.savefig("%s_width.png" % out, dpi=72)
        plt.close(fig)
    # ---- the rate series ----
    pers = sorted({r["period"] for lk in J["links"] for r in J["links"][lk].get("period", [])})
    if pers:
        fig, axs = plt.subplots(1, 3, figsize=(24, 7), dpi=100)
        fig.subplots_adjust(left=0.05, right=0.99, top=0.85, bottom=0.12, wspace=0.28)
        for lk in ("BA", "AB"):
            rows = (J["links"].get(lk) or {}).get("period", [])
            if not rows:
                continue
            duty = [100 * r["duty"] for r in rows]
            c = LCOL[lk]
            for pt, ls in (("1_1", "-"), ("-1_-1", "--")):
                axs[0].plot(duty, [1e3 * (r["during_" + pt]["di"] - r["idle_di"]) for r in rows], "o" + ls, color=c, label="%s, (%s) events: I" % (LNAME[lk], pt.replace("_", ",")))
                axs[1].plot(duty, [1e3 * (r["during_" + pt]["dq"] - r["idle_dq"]) for r in rows], "o" + ls, color=c, label="%s, (%s) events: Q" % (LNAME[lk], pt.replace("_", ",")))
            axs[2].plot(duty, [100 * (pct(r.get("A3")) or 0) for r in rows], "o-", color=c, label=LNAME[lk] + " A3 right")
            axs[2].plot(duty, [min(100, (r.get("A3") or {}).get("idle_false_per_s") or 0) for r in rows], "s:", color=c, alpha=0.6, label=LNAME[lk] + " idle false/s (capped 100)")
        for ax, (yl, t) in zip(axs, [("the idle's I on the ADC while the events run, mV from its quiet value", "the loop's average pull along I against the duty"),
                                    ("the idle's Q, mV", "the loop's average pull along Q against the duty"),
                                    ("%", "A3 by the decoder against the event rate")]):
            frame(ax)
            ax.set_xscale("log")
            ax.set_xlabel("the events' duty, % (200 ns events, one in 50 ... 20 000 clocks)", fontsize=8)
            ax.set_ylabel(yl, fontsize=8)
            ax.set_title(t, fontsize=9, loc="left", fontweight="bold")
            ax.grid(color=GRID, lw=0.4)
            ax.legend(fontsize=6.5, frameon=False)
        fig.suptitle("The event-rate series at %g MHz over the cables (%s)" % (J["mhz"], J["stamp"]), fontsize=12, fontweight="bold")
        pdf.savefig(fig)
        fig.savefig("%s_period.png" % out, dpi=72)
        plt.close(fig)
print(out + ".pdf")
