"""The 11-07 night's pages from night2.py's (and pipe.py's) records:
  1 latency   mark -> decision per point and scheme on each receiver's scope, the pipeline's three taps, the 60-shot spread
  2 level     against the leg: the decoder's right fractions per scheme and delay, the PRBS, the latency, the arms' plateaus
  3 night     the cycle against the hour: the boards' temperature, each link's leg and DSA, A8 / A3, the PRBS, the latency
  4 modes     the settled and first-edge decisions and the window fraction (pipe.py), as text
    python3 night2_fig.py [night2_<stamp>] [--pipe pipe_<stamp>] [--cycle night2_<stamp>]  ->  plots/night2_<stamp>_<page>.png/.pdf"""
import json
import os
import sys
import textwrap
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                 # noqa: E402
import numpy as np                                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ.get("CL_BRINGUP", HERE), "data", "twoboard")     # the project's bringup/, or another copy's
PLOTS = os.path.join(os.environ.get("CL_BRINGUP", HERE), "plots")
BLUE, ORANGE, AQUA, RED, GREEN, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#008300", "#6250d6"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
LCOL = {"AB": ORANGE, "BA": BLUE}
LNAME = {"AB": "A -> B (receiver B)", "BA": "B -> A (receiver A)"}
SCHEME_MARK = {"A8": "o", "A3": "s", "A2": "^", "A1": "D"}
DELAY_ALPHA = {2: 1.0, 6: 1.0, 7: 0.9, 8: 0.85, 10: 0.7, 16: 0.5}


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def load(base):
    if not base:
        return None
    if not os.path.dirname(base):
        base = os.path.join(DATA, base)
    return json.load(open(base + ".json"))


def frame(ax, xl="", yl="", t=""):
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(labelsize=7, colors=INK2)
    ax.grid(color=GRID, lw=0.4)
    ax.set_xlabel(xl, fontsize=7.5)
    ax.set_ylabel(yl, fontsize=7.5)
    ax.set_title(t, fontsize=8.5, loc="left", fontweight="bold")


def pt_label(p):
    return "(%+d,%+d)" % tuple(p)


def page_latency(J, P, out):
    fig, axs = plt.subplots(2, 2, figsize=(22, 13), dpi=100, gridspec_kw={"width_ratios": [1.7, 1]})
    fig.subplots_adjust(left=0.05, right=0.99, top=0.9, bottom=0.07, hspace=0.45, wspace=0.2)
    lat = (J.get("stages") or {}).get("lat") or {}
    for r, lk in enumerate(("AB", "BA")):
        ax = axs[r, 0]
        rec = lat.get(lk) or {}
        x, labels = 0, []
        for sp in rec.get("scope") or []:
            sc, dl = sp["scheme"], sp["delay"]
            for row in sp["rows"]:
                if row.get("mark_to_dec") is None:
                    x += 1
                    labels.append("%s d%d %s" % (sc, dl, pt_label(row["point"])))
                    continue
                ax.plot([x, x], [row["mark_to_dec_min"], row["mark_to_dec_max"]], color=LCOL[lk], lw=1.2, alpha=DELAY_ALPHA.get(dl, 0.7))
                ax.plot(x, row["mark_to_dec"], SCHEME_MARK.get(sc, "o"), color=LCOL[lk], ms=6, alpha=DELAY_ALPHA.get(dl, 0.7), mec="white", mew=0.8)
                labels.append("%s d%d %s" % (sc, dl, pt_label(row["point"])))
                x += 1
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=90, fontsize=6)
        lock = rec.get("lock") or {}
        frame(ax, yl="ns", t="%s: the sender's mark to the decision pulse (TRIG B), median of 6 shots with min / max; DSA %s, leg %.0f mV" % (
            LNAME[lk], lock.get("dsa"), 1e3 * (lock.get("leg") or 0)))
        # the pipeline's taps from pipe.py
        if P and lk in (P.get("runs") or {}):
            pr = P["runs"][lk]
            for src, ls, name in (("cmp_i", ":", "TRIG B = the sign comparator's edge"), ("rx_event", "--", "TRIG B = the event detected"),
                                  ("rx_decision", "-", "TRIG B = the decision (A8 d8)")):
                vals = [s["mark_to_dec"] for s in pr.get("sources", []) if s.get("trigb") == src and s.get("mark_to_dec") is not None and s["point"] == [-1, 0]]
                if vals:
                    ax.axhline(vals[0], color=MUTED, ls=ls, lw=1)
                    ax.text(len(labels) - 0.5, vals[0] + 0.6, "%s: %.0f ns" % (name, vals[0]), ha="right", fontsize=6.5, color=INK2)
    # the 60-shot spread
    ax = axs[0, 1]
    if P:
        for lk in ("AB", "BA"):
            h = ((P.get("runs") or {}).get(lk) or {}).get("hist") or {}
            a = np.array(h.get("mark_to_dec_all") or [])
            if len(a):
                ax.hist(a, bins=np.arange(np.floor(a.min()) - 0.5, np.ceil(a.max()) + 1.5, 1.0), color=LCOL[lk], alpha=0.55,
                        label="%s: %d shots, %.1f .. %.1f ns, std %.1f" % (LNAME[lk], len(a), a.min(), a.max(), a.std()))
        ax.legend(fontsize=6.5, frameon=False)
    frame(ax, xl="mark -> decision, ns", yl="shots", t="the spread at the flip (A8, delay 8): the 100 MHz word clock's phase")
    # the decoder's right fraction per scheme and delay at the lock's level
    ax = axs[1, 1]
    for lk in ("AB", "BA"):
        rec = lat.get(lk) or {}
        xs, ys, labels = [], [], []
        for k, g in enumerate(rec.get("gw") or []):
            if g.get("right_frac_min") is None:
                continue
            xs.append(k)
            ys.append(100 * min(1.0, g["right_frac_min"]))
            labels.append("%s d%d" % (g["scheme"], g["params"]["delay"]))
        ax.plot(xs, ys, "o-", color=LCOL[lk], ms=5, label=LNAME[lk])
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, rotation=45, fontsize=6.5)
    ax.set_ylim(0, 105)
    ax.legend(fontsize=6.5, frameon=False, loc="lower left")
    frame(ax, yl="%", t="the worst message's right fraction by the decoder, 20 000 events a message")
    fig.suptitle("The one-way latency to the decision over the cables, %s: the sender's mark to the receiver's TRIG B" % J["stamp"], fontsize=12, fontweight="bold")
    fig.savefig(out + "_latency.png", dpi=72)
    fig.savefig(out + "_latency.pdf")
    plt.close(fig)


def page_level(J, out):
    lev = (J.get("stages") or {}).get("level") or {}
    fig, axs = plt.subplots(2, 3, figsize=(24, 13), dpi=100)
    fig.subplots_adjust(left=0.05, right=0.99, top=0.9, bottom=0.07, hspace=0.4, wspace=0.25)
    for lk in ("AB", "BA"):
        rec = lev.get(lk) or {}
        rows = [l for l in rec.get("levels") or [] if l.get("leg_mv")]
        if not rows:
            continue
        legs = np.array([l["leg_mv"] for l in rows])
        # right fractions
        for (sc, dl), ls in ((("A8", 6), "-"), (("A8", 10), "--"), (("A8", 16), ":"), (("A3", 6), "-"), (("A2", 2), "-"), (("A1", 2), "-")):
            ys = []
            for l in rows:
                g = next((g for g in l["gw"] if g["scheme"] == sc and g["params"]["delay"] == dl), None)
                ys.append(100 * min(1.0, g["right_frac_min"]) if g and g.get("right_frac_min") is not None else np.nan)
            ax = axs[0, 0] if sc == "A8" else axs[0, 1]
            ax.plot(legs, ys, SCHEME_MARK[sc] + ls, color=LCOL[lk], ms=5, alpha=DELAY_ALPHA.get(dl, 0.7), label="%s %s d%d" % (lk, sc, dl))
        # the prbs
        ber = np.array([(l.get("prbs50") or {}).get("ber") if (l.get("prbs50") or {}).get("ber") is not None else np.nan for l in rows], float)
        axs[0, 2].plot(legs, np.where(ber > 0, ber, 1e-8), "o-", color=LCOL[lk], label="%s PRBS P50, 6 M bits a point (0 drawn at 1e-8)" % LNAME[lk])
        # the latency
        for pt, mk in (((-1, 0), "o"), ((0, 1), "^"), ((-1, 1), "s")):
            ys, lo, hi = [], [], []
            for l in rows:
                row = next((r for r in ((l.get("scope") or {}).get("rows") or []) if r["point"] == list(pt)), None)
                ys.append(row["mark_to_dec"] if row and row.get("mark_to_dec") is not None else np.nan)
                lo.append(row["mark_to_dec_min"] if row and row.get("mark_to_dec_min") is not None else np.nan)
                hi.append(row["mark_to_dec_max"] if row and row.get("mark_to_dec_max") is not None else np.nan)
            axs[1, 0].errorbar(legs, ys, yerr=[np.array(ys) - np.array(lo), np.array(hi) - np.array(ys)], fmt=mk + "-", color=LCOL[lk], ecolor=LCOL[lk],
                               ms=5, alpha=0.8 if pt == (-1, 0) else 0.55, capsize=2, lw=1, label="%s %s" % (lk, pt_label(pt)))
        # the plateaus
        for pt, nm, mk in (((-1, 0), "i_plateau", "o"), ((0, 1), "q_plateau", "^")):
            ys = []
            for l in rows:
                row = next((r for r in ((l.get("scope") or {}).get("rows") or []) if r["point"] == list(pt)), None)
                ys.append(abs(row[nm]) if row and row.get(nm) is not None else np.nan)
            axs[1, 1].plot(legs, ys, mk + "-", color=LCOL[lk], ms=5, alpha=0.8 if nm == "i_plateau" else 0.55, label="%s %s %s" % (lk, pt_label(pt), "I" if nm[0] == "i" else "Q"))
        # the DSA
        axs[1, 2].plot([l["dsa"] for l in rows], legs, "o-", color=LCOL[lk], label=LNAME[lk])
    for ax in axs.flat[:5]:
        ax.set_xscale("log")
        ax.set_xticks([10, 20, 50, 100, 200, 500])
        ax.set_xticklabels(["10", "20", "50", "100", "200", "500"])
    frame(axs[0, 0], xl="the leg, mV", yl="%", t="A8 (3 bits an event): the worst message right, at delays 6 / 10 / 16")
    frame(axs[0, 1], xl="the leg, mV", yl="%", t="A3 at delay 6, A2 and A1 at delay 2: the worst message right")
    frame(axs[0, 2], xl="the leg, mV", yl="BER", t="the PRBS bpsk at P50")
    axs[0, 2].set_yscale("log")
    frame(axs[1, 0], xl="the leg, mV", yl="ns", t="mark -> decision (A8, delay 6), median and min / max of 6 shots")
    frame(axs[1, 1], xl="the leg, mV", yl="mV at the arm", t="the arms' plateaus on the scope: the flip's I, the (0, +1) step's Q")
    frame(axs[1, 2], xl="DSA, dB", yl="the leg, mV", t="the leg against the attenuator")
    axs[1, 2].set_yscale("log")
    for ax in axs.flat:
        ax.legend(fontsize=6.2, frameon=False)
    axs[0, 0].set_ylim(-5, 105)
    axs[0, 1].set_ylim(-5, 105)
    fig.suptitle("Against the level, %s: the decoder, the PRBS and the latency as the leg goes from 320 to 13 mV (the 1 km budget's range)" % J["stamp"], fontsize=12, fontweight="bold")
    fig.savefig(out + "_level.png", dpi=72)
    fig.savefig(out + "_level.pdf")
    plt.close(fig)


def page_night(J, out):
    cyc = J.get("cycles") or []
    if not cyc:
        return False
    t0 = cyc[0]["t"]
    hours = np.array([c["t"] - t0 for c in cyc]) / 3600

    def q(path, default=np.nan):
        res = []
        for c in cyc:
            v = c
            try:
                for k in path:
                    v = v[k]
                res.append(default if v is None else v)
            except (KeyError, TypeError, IndexError):
                res.append(default)
        return np.array(res, float)

    fig, axs = plt.subplots(3, 3, figsize=(24, 16), dpi=100)
    fig.subplots_adjust(left=0.045, right=0.99, top=0.92, bottom=0.05, hspace=0.45, wspace=0.25)
    for b, col in (("A", BLUE), ("B", ORANGE)):
        axs[0, 0].plot(hours, q(("quiet", b, "temp_c")), ".-", color=col, label="board %s" % b)
        axs[0, 1].plot(hours, 1e3 * (q(("quiet", b, "centre_q_v")) - 1.65), ".-", color=col, label="board %s Q arm" % b)
        axs[0, 1].plot(hours, 1e3 * (q(("quiet", b, "centre_i_v")) - 1.65), ".--", color=col, alpha=0.6, label="board %s I arm" % b)
    for lk in ("AB", "BA"):
        axs[0, 2].plot(hours, 1e3 * q(("links", lk, "lock", "leg")), ".-", color=LCOL[lk], label=LNAME[lk])
        axs[1, 0].plot(hours, q(("links", lk, "lock", "dsa")), ".-", color=LCOL[lk], label=LNAME[lk])
        axs[1, 1].plot(hours, 100 * q(("links", lk, "A8", "right_frac_min")), ".-", color=LCOL[lk], label=LNAME[lk] + " A8 d8")
        axs[1, 1].plot(hours, 100 * q(("links", lk, "A3", "right_frac_min")), ".--", color=LCOL[lk], alpha=0.6, label=LNAME[lk] + " A3 d8")
        for k, ms in ((0, 2), (1, 4), (2, 6)):
            axs[1, 1].plot(hours, 100 * q(("links", lk, "settle", k, "right_frac_min")), ":", color=LCOL[lk], alpha=0.35 + 0.2 * k, lw=1,
                           label=LNAME[lk] + " A8 settled on %d (cap 16)" % ms)
        mis = np.nancumsum(q(("links", lk, "prbs20", "mismatches"), 0))
        bits = np.nancumsum(q(("links", lk, "prbs20", "bits"), 0))
        axs[1, 2].plot(hours, bits / 1e9, ".-", color=LCOL[lk], label="%s P20: %.2f G bits, %d mismatches" % (LNAME[lk], bits[-1] / 1e9 if len(bits) else 0, mis[-1] if len(mis) else 0))
        for k, (pt, ls) in enumerate((((-1, 0), "-"), ((0, 1), "--"))):
            ys = q(("links", lk, "scope", "rows", k, "mark_to_dec"))
            lo = q(("links", lk, "scope", "rows", k, "mark_to_dec_min"))
            hi = q(("links", lk, "scope", "rows", k, "mark_to_dec_max"))
            axs[2, 0].plot(hours, ys, "." + ls, color=LCOL[lk], alpha=1 if k == 0 else 0.6, label="%s %s" % (LNAME[lk], pt_label(pt)))
            if k == 0:
                axs[2, 0].fill_between(hours, lo, hi, color=LCOL[lk], alpha=0.12, lw=0)
        axs[2, 0].plot(hours, q(("links", lk, "scope_settle2", "rows", 0, "mark_to_dec")), ":", color=LCOL[lk], lw=1.2, label="%s the flip, settled on 2" % LNAME[lk])
        axs[2, 1].plot(hours, q(("links", lk, "scope", "rows", 0, "i_plateau")), ".-", color=LCOL[lk], label=LNAME[lk] + " the flip's I")
        axs[2, 1].plot(hours, q(("links", lk, "scope", "rows", 1, "q_plateau")), ".--", color=LCOL[lk], alpha=0.6, label=LNAME[lk] + " the (0,+1) step's Q")
        axs[2, 2].plot(hours, q(("links", lk, "lock", "vc_lock")), ".-", color=LCOL[lk], label=LNAME[lk])
    frame(axs[0, 0], xl="hours", yl="C", t="each board's temperature")
    frame(axs[0, 1], xl="hours", yl="mV from 1.65 V", t="the arms' no-carrier centres: Q solid, I dashed")
    frame(axs[0, 2], xl="hours", yl="mV", t="the leg at setup")
    frame(axs[1, 0], xl="hours", yl="dB", t="the DSA linkd chose")
    frame(axs[1, 1], xl="hours", yl="%", t="the worst message right: A8 solid, A3 dashed (delay 8), A8 settled dotted")
    axs[1, 1].set_ylim(-5, 105)
    frame(axs[1, 2], xl="hours", yl="G bits", t="the PRBS bpsk P20, 5 s a cycle (cumulative; the legend has the mismatches)")
    frame(axs[2, 0], xl="hours", yl="ns", t="mark -> decision (A8, delay 8): the flip solid with its min / max band, (0,+1) dashed")
    frame(axs[2, 1], xl="hours", yl="mV at the arm", t="the arms' plateaus on the scope")
    frame(axs[2, 2], xl="hours", yl="V", t="VC at lock")
    for ax in axs.flat:
        ax.legend(fontsize=6.2, frameon=False)
    fig.suptitle("The night of %s over the cables: %d cycles every %g min, A -> B at %g MHz and B -> A at %g MHz, %s to %s" % (
        J["stamp"], len(cyc), J.get("every_min", 10), J["mhz"]["AB"], J["mhz"]["BA"], cyc[0]["when"], cyc[-1]["when"]), fontsize=12, fontweight="bold")
    fig.savefig(out + "_night.png", dpi=72)
    fig.savefig(out + "_night.pdf")
    plt.close(fig)
    return True


def page_modes(P, out):
    if not P:
        return False
    lines = ["pipe.py %s: the decision modes on the scope and the window fraction by the decoder" % P["stamp"], ""]
    for lk in ("AB", "BA"):
        pr = (P.get("runs") or {}).get(lk) or {}
        if not pr or "error" in pr and not pr.get("modes"):
            lines.append("%s: %s" % (LNAME[lk], pr.get("error", "no run")))
            continue
        lock = pr.get("lock") or {}
        lines.append("%s, DSA %s, leg %.0f mV" % (LNAME[lk], lock.get("dsa"), pr.get("leg_mv") or 0))
        lines.append("  the pipeline's taps (the flip, A8 delay 8), mark -> TRIG B:")
        for s in pr.get("sources") or []:
            lines.append("    TRIG B = %-12s %s: %s ns (%s .. %s)" % (s["trigb"], pt_label(s["point"]), "%.1f" % s["mark_to_dec"] if s.get("mark_to_dec") is not None else "none",
                                                                   "%.1f" % s["mark_to_dec_min"] if s.get("mark_to_dec_min") is not None else "-",
                                                                   "%.1f" % s["mark_to_dec_max"] if s.get("mark_to_dec_max") is not None else "-"))
        lines.append("  the decision modes, mark -> decision:")
        for m in pr.get("modes") or []:
            lines.append("    %-3s delay %2d%s%s %s: %s ns (%s .. %s)" % (m["scheme"], m["delay"], " settle %d" % m["settle"] if m.get("settle") else "",
                                                                     " first-edge" if m.get("first_edge") else "", pt_label(m["point"]),
                                                                     "%.1f" % m["mark_to_dec"] if m.get("mark_to_dec") is not None else "none",
                                                                     "%.1f" % m["mark_to_dec_min"] if m.get("mark_to_dec_min") is not None else "-",
                                                                     "%.1f" % m["mark_to_dec_max"] if m.get("mark_to_dec_max") is not None else "-"))
        lines.append("  by the decoder:")
        for g in pr.get("frac") or []:
            pm = g.get("per_msg") or {}
            lines.append("    %-3s delay %d frac %.1f%s: right %s, min %s" % (g["scheme"], g["params"]["delay"], g["params"]["frac"],
                                                                        " x%d" % (g["params"]["count"] // 20000) if g["params"]["count"] != 20000 else "",
                                                                        " ".join("%.4f" % (r["right_frac"] or 0) for m, r in sorted(pm.items(), key=lambda kv: int(kv[0]))),
                                                                        "%.4f" % g["right_frac_min"] if g.get("right_frac_min") is not None else g.get("error")))
        lines.append("")
    fig = plt.figure(figsize=(16, 0.3 + 0.19 * len(lines)), dpi=100)
    fig.text(0.02, 0.98, "\n".join(lines), va="top", ha="left", fontsize=8, family="monospace", color=INK)
    fig.savefig(out + "_modes.png", dpi=72)
    fig.savefig(out + "_modes.pdf")
    plt.close(fig)
    return True


def main():
    base = next((a for a in sys.argv[1:] if not a.startswith("--") and sys.argv[sys.argv.index(a) - 1] not in ("--pipe", "--cycle")), None)
    base = base or sorted(f[:-5] for f in os.listdir(DATA) if f.startswith("night2_") and f.endswith(".json"))[-1]
    J = load(base)
    P = load(arg("--pipe", None))
    Jc = load(arg("--cycle", None)) or J
    out = os.path.join(PLOTS, os.path.basename(base))
    page_latency(J, P, out)
    print(out + "_latency")
    if (J.get("stages") or {}).get("level"):
        page_level(J, out)
        print(out + "_level")
    if page_night(Jc, out):
        print(out + "_night")
    if page_modes(P, out):
        print(out + "_modes")


if __name__ == "__main__":
    main()
