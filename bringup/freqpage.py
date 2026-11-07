"""One page per centre frequency: the analog I and Q paths of every scheme on both receivers, from twoscope.py's runs
(one run per frequency, both links).  Per scheme a row: the ideal received constellation; receiver A's I/Q plane with
the scope's trajectories from the idle to each point and back (I MON, Q MON through the 1 k taps, x21) with the
decoder's thresholds and its right fraction; A's time traces; the same two for receiver B.  The header: each link's lock,
latency and the flip-against-level fit; the PRBS from the optsweep run at that frequency.  Pages into one PDF and PNGs.

    python3 freqpage.py --runs twoscope_<stamp> ... [--opt optsweep_<stamp>.jsonl] [--out schemes_byfreq_<date>] [--title "..."]
"""
import json
import math
import os
import sys
import textwrap
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                 # noqa: E402
from matplotlib.backends.backend_pdf import PdfPages            # noqa: E402
import numpy as np                                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/jason/OpticsPCBs/CostasLink-PYNQ-Z2/gateware/driver")
import costaslink as C                                          # noqa: E402

DATA = "/home/jason/OpticsPCBs/CostasLink-PYNQ-Z2/bringup/data/twoboard"
BLUE, ORANGE, AQUA, RED, GREEN, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#008300", "#6250d6"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
PCOL = [BLUE, ORANGE, AQUA, VIOLET, "#b5651d", "#2f8f9d", "#c23b8a", "#6b6b6b"]
WIN = ["QP", "QN", "IP", "IN"]
WIN_INDEX = {"QP": 1, "QN": 2, "IP": 3, "IN": 4}
AXIS = {"QP": (1, +1), "QN": (1, -1), "IP": (0, +1), "IN": (0, -1)}
ORDER = ["A1", "A2", "A3", "A4", "B1", "B2"]


def args_list(name, default):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name) + 1
    out = []
    while i < len(sys.argv) and not sys.argv[i].startswith("--"):
        out.append(sys.argv[i])
        i += 1
    return out


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


class Run:
    """one twoscope run: the json, the captures, the per-(link, scheme, m) shots in mV at the arm"""
    def __init__(self, base):
        if not os.path.dirname(base):
            base = os.path.join(DATA, base)
        self.base = base
        self.J = json.load(open(base + ".json"))
        self.Z = np.load(base + ".npz")
        self.meta = json.loads(str(self.Z["meta"]))
        self.g = self.J.get("gain", 21.0)
        self.mhz = self.J["mhz"]
        self.pts = {}
        for lk, rec in self.J["links"].items():
            for row in rec.get("constellations", []):
                for pp in row.get("points", []):
                    self.pts[(lk, row["scheme"], pp["m"])] = pp
        self.shots = {}
        for m in self.meta:
            if m["stage"] != "constellation":
                continue
            k = m["k"]
            pp = self.pts.get((m["link"], m["scheme"], m["m"]))
            t = self.Z["t1_%d" % k] * 1e9
            sh = {"t": t, "cmp": self.Z["v4_%d" % k], "mark": self.Z["v1_%d" % k], "point": tuple(int(x) for x in m["point"]), "link": m["link"],
                  "leg": m["leg"], "side": m["side"], "m": m["m"]}
            t0 = pp["cmp_edge_t"] if pp and pp.get("cmp_edge_t") is not None else (m.get("lat_ns") or 0.0)
            sh["t0"] = t0
            for ch, nm in ((2, "i"), (3, "q")):
                d = (self.Z["v%d_%d" % (ch, k)] - m["base"][str(ch)]) * 1e3 * self.g
                pre = (t > -150) & (t < -20)
                d = d - float(np.median(d[pre]))
                sh[nm] = d
                mid = (t > t0 + 60) & (t < t0 + 180)
                sh[nm + "_set"] = float(np.median(d[mid])) if mid.any() else None
            self.shots.setdefault((m["link"], m["scheme"]), {}).setdefault(m["m"], []).append(sh)

    def row(self, lk, scheme):
        rec = self.J["links"].get(lk) or {}
        for r in rec.get("constellations", []):
            if r["scheme"] == scheme:
                return r
        return None


def opt_numbers(path):
    """the optsweep run's base points and PRBS per (link, mhz)"""
    out = {"events": {}, "prbs": {}}
    if not path:
        return out
    if not os.path.dirname(path):
        path = os.path.join(DATA, path)
    if not os.path.exists(path):
        return out
    for line in open(path):
        try:
            d = json.loads(line)
        except Exception:
            continue
        st = d.get("state") or {}
        p = d.get("params") or {}
        if d.get("tag") == "events" and "per_msg" in d and p.get("frac") == 0.4 and p.get("delay") == 16:
            out["events"][(st.get("link"), st.get("mhz"), d.get("scheme"))] = {
                "right": [x.get("right_frac") for m, x in sorted(d["per_msg"].items(), key=lambda kv: int(kv[0]))], "false_s": d.get("idle_false_per_s"),
                "leg": d.get("leg"), "dead": (d.get("rx_info") or {}).get("dead_windows"), "gaps": d.get("gaps_mv")}
        elif d.get("tag") == "prbs":
            out["prbs"][(st.get("link"), st.get("mhz"), p.get("period"))] = {"ber": d.get("ber"), "bits": d.get("bits"), "error": d.get("error")}
    return out


# ---- geometry ----------------------------------------------------------------------------------------------------------
def rot(p, deg):
    r = math.radians(deg)
    return (p[0] * math.cos(r) - p[1] * math.sin(r), p[0] * math.sin(r) + p[1] * math.cos(r))


def tx_pt(s, iq):
    i, q = iq
    if s.pilot is not None and tuple(iq) != tuple(s.idle):
        i, q = i + s.pilot[0], q + s.pilot[1]
    return (i, q)


def rx_pt(s, iq):
    return rot(tx_pt(s, iq), s.rot_deg)


def rx_idle(s):
    return rot(tuple(s.pilot) if s.pilot is not None else tuple(s.idle), s.rot_deg)


def _frame(ax, lim=1.75):
    ax.set_aspect("equal")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color(GRID)
    t = np.linspace(0, 2 * np.pi, 200)
    ax.plot(np.cos(t), np.sin(t), color=GRID, lw=0.8)
    ax.axhline(0, color=GRID, lw=0.6)
    ax.axvline(0, color=GRID, lw=0.6)


def draw_ideal(ax, s):
    _frame(ax)
    ip = rx_idle(s)
    for m, pt in enumerate(s.msgs):
        p = rx_pt(s, pt)
        ax.annotate("", xy=p, xytext=ip, arrowprops=dict(arrowstyle="->", color=PCOL[m % 8], lw=1.0))
        ax.plot(p[0], p[1], "o", color=PCOL[m % 8], ms=6)
        ax.text(p[0] + 0.08, p[1] + 0.08, "(%d,%d)" % tuple(pt), fontsize=7, color=INK)
    ax.plot(ip[0], ip[1], "s", color=GREEN, ms=8)
    ax.text(ip[0] + 0.08, ip[1] - 0.3, "idle" if s.pilot is None else "pilot", fontsize=7, color=GREEN)
    turn = "" if abs(s.rot_deg) < 1e-6 else ", turned %.0f deg" % s.rot_deg
    ax.set_title("%s: as received, ideal%s" % (s.name, turn), fontsize=8.5, loc="left", fontweight="bold")
    ax.text(0.02, 0.02, textwrap.fill(s.text, 34), transform=ax.transAxes, fontsize=6.2, color=INK2, va="bottom")


def _thr_lines(ax, thm, s, lim, dead=()):
    k = 0
    for w in WIN:
        x = thm.get(w)
        if x is None or abs(x) > 1.5 * lim:
            continue
        c, sg = AXIS[w]
        pos = sg * x
        ev = bool(s.mask >> WIN_INDEX[w] & 1)
        lw, al = (1.4, 0.9) if ev else (0.8, 0.5)
        ls = ":" if w in dead else "-"
        if c == 1:
            ax.axhline(pos, color=RED, lw=lw, alpha=al, ls=ls)
            ax.text(-lim * 0.97 + (k % 2) * lim * 0.95, pos + lim * 0.02, w, fontsize=6, color=RED, alpha=al)
        else:
            ax.axvline(pos, color=RED, lw=lw, alpha=al, ls=ls)
            ax.text(pos + lim * 0.02, -lim * 0.95 + (k % 2) * lim * 0.9, w, fontsize=6, color=RED, alpha=al, rotation=90, va="bottom")
        k += 1


def draw_plane(ax, run, lk, s):
    rx = lk[1]
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(labelsize=6.5, colors=INK2)
    ax.set_aspect("equal")
    row = run.row(lk, s.name) if run else None
    shots = (run.shots.get((lk, s.name)) if run else None) or {}
    if not row or not shots:
        ax.text(0.5, 0.5, "no capture" if not row else ("no pilot: skipped" if row.get("pilot", {}).get("vr") is None else "no shots"),
                ha="center", va="center", fontsize=8, color=MUTED, transform=ax.transAxes)
        ax.set_title("receiver %s: %s -> %s" % (rx, lk[0], lk[1]), fontsize=7, loc="left", fontweight="bold")
        return
    leg = 1e3 * (row.get("leg") or run.J["links"][lk]["lock"]["leg"])
    dec = row.get("decoder") or {}
    pmr = {int(m): r.get("right_frac") for m, r in (dec.get("per_msg") or {}).items()} if "error" not in dec else {}
    # the settled points and the mirror vote
    sets = {}
    for m, sh in shots.items():
        is_ = [x["i_set"] for x in sh if x.get("i_set") is not None]
        qs = [x["q_set"] for x in sh if x.get("q_set") is not None]
        if is_ and qs:
            sets[m] = (float(np.median(is_)), float(np.median(qs)))
    i0 = rx_idle(s)
    votes = []
    for m, (i, q) in sets.items():
        p = rx_pt(s, s.msgs[m])
        if abs(p[1] - i0[1]) > 0.3 and abs(q) > 20:
            votes.append(1 if (q > 0) == (p[1] - i0[1] > 0) else -1)
    qmir = -1 if votes and sum(votes) < 0 else 1
    vals = [abs(v) for p in sets.values() for v in p] + [leg * 1.6]
    lim = max(60.0, max(vals) * 1.2)
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim, lim)
    ax.axhline(0, color=GRID, lw=0.6)
    ax.axvline(0, color=GRID, lw=0.6)
    # the decoder's thresholds, mV from the idle at each window's arm
    if "error" not in dec and dec.get("thresholds") and dec.get("levels"):
        idle_key = "%d,%d" % tuple(s.idle)
        base = dec["levels"].get(idle_key) or {}
        thm = {w: (1e3 * (dec["thresholds"][w] - base[w]) if dec["thresholds"].get(w) is not None and base.get(w) is not None else None) for w in WIN}
        _thr_lines(ax, thm, s, lim, dead=set((dec.get("rx_info") or {}).get("dead_windows") or []))
    for m, pt in enumerate(s.msgs):
        p = rx_pt(s, pt)
        ax.plot(leg * (p[0] - i0[0]), qmir * leg * (p[1] - i0[1]), "+", color=MUTED, ms=9, mew=1.0, zorder=3)
    notes = []
    for m, sh in sorted(shots.items()):
        col = PCOL[m % 8]
        for x in sh:
            w = (x["t"] > x["t0"] - 40) & (x["t"] < x["t0"] + 330)
            ax.plot(x["i"][w], x["q"][w], color=col, lw=0.6, alpha=0.35, zorder=2)
        if m in sets:
            i, q = sets[m]
            rf = pmr.get(m)
            ring = MUTED if rf is None else GREEN if rf >= 0.99 else ORANGE if rf >= 0.9 else RED
            ax.plot(i, q, "o", color=col, ms=6.5, zorder=5, markeredgecolor=ring, markeredgewidth=1.8)
            lab = "(%d,%d)" % tuple(s.msgs[m]) + ("" if rf is None else " %.4g %%" % (100 * min(1.0, rf)))
            ax.text(i + lim * 0.03, q + lim * 0.03, lab, fontsize=6.3, color=INK)
            ang = math.degrees(math.atan2(q, i))
            notes.append("(%d,%d) %+.0f, %+.0f mV (%.2f leg, %.0f deg)" % (s.msgs[m][0], s.msgs[m][1], i, q, math.hypot(i, q) / leg, ang))
    ax.plot(0, 0, "s", color=GREEN, ms=8, zorder=6)
    pil = row.get("pilot") or {}
    pt = ""
    if pil.get("rho") and pil.get("a"):
        pt = ", pilot %.0f mV (rho %.2f)" % (1e3 * pil["rho"] * pil["a"], pil["rho"])
    side = (row.get("idle") or {}).get("side")
    fs = dec.get("idle_false_per_s") if "error" not in dec else None
    ax.set_title("receiver %s: %s -> %s, leg %.0f mV%s, side %s%s%s" % (
        rx, lk[0], lk[1], leg, pt, "%+d" % side if side is not None else "?", ", idle false %.0f/s" % fs if fs else "",
        " (Q mirrored at this side)" if qmir < 0 else ""), fontsize=6.8, loc="left", fontweight="bold")
    ax.set_xlabel("I, mV from the idle at the arm", fontsize=6.3, color=INK2)
    ax.set_ylabel("Q, mV", fontsize=6.3, color=INK2)
    if notes:
        ax.text(0.02, 0.02, "\n".join(notes), transform=ax.transAxes, fontsize=5.6, color=INK2, va="bottom")


def draw_traces(ax, run, lk, s):
    rx = lk[1]
    for sp in ax.spines.values():
        sp.set_color(GRID)
    shots = (run.shots.get((lk, s.name)) if run else None) or {}
    if not shots:
        ax.axis("off")
        return
    row = run.row(lk, s.name) or {}
    leg = 1e3 * (row.get("leg") or run.J["links"][lk]["lock"]["leg"])
    cmp_any = False
    for m, sh in sorted(shots.items()):
        col = PCOL[m % 8]
        for n, x in enumerate(sh):
            w = (x["t"] > x["t0"] - 80) & (x["t"] < x["t0"] + 360)
            tt = x["t"][w] - x["t0"]
            ax.plot(tt, x["i"][w], color=col, lw=0.55, alpha=0.45, label=("(%d,%d) I" % x["point"]) if n == 0 else None)
            ax.plot(tt, x["q"][w], color=col, lw=0.55, alpha=0.45, ls="--", label=("(%d,%d) Q" % x["point"]) if n == 0 else None)
            if n == 0 and not cmp_any:
                c = x["cmp"][w]
                ax.plot(tt, (c - 0.15) / 0.3 * leg * 0.5, color=MUTED, lw=0.6, alpha=0.6, label="CMP I MON (scaled)")
                cmp_any = True
    ax.set_xlim(-80, 360)
    ax.axvline(0, color=GRID, lw=0.8)
    ax.axhline(0, color=GRID, lw=0.6)
    ax.tick_params(labelsize=6.5)
    ax.grid(color=GRID, lw=0.4)
    ax.set_xlabel("ns after the event's arrival at receiver %s (CMP I's edge, or the mark + the latency)" % rx, fontsize=6.5)
    ax.set_ylabel("mV at the arm from the idle (I solid, Q dashed)", fontsize=6.5)
    ax.legend(fontsize=5.6, loc="upper right", frameon=False, ncol=3)
    n = len(next(iter(shots.values())))
    ax.set_title("%s on receiver %s's scope: 200 ns events of each point, %d shots each" % (s.name, rx, n), fontsize=6.8, loc="left", fontweight="bold")


def draw_levels(ax, run, lk):
    """the flip's Q against the leg on this receiver with the fit Q = 2 off + k leg"""
    for sp in ax.spines.values():
        sp.set_color(GRID)
    rec = (run.J["links"].get(lk) if run else None) or {}
    rows = [r for r in rec.get("levels", []) if r.get("locked") and r.get("q_plateau") is not None]
    if not rows:
        ax.axis("off")
        return
    legs = np.array([r["leg_mv"] for r in rows])
    qs = np.array([r["q_plateau"] for r in rows])
    ax.plot(legs, qs, "o", color=BLUE, ms=6)
    for r in rows:
        ax.text(r["leg_mv"], r["q_plateau"], "  DSA %.2f" % r["dsa"], fontsize=6, color=INK2, va="center")
    fit = None
    if len(rows) >= 2:
        k, b = np.polyfit(legs, qs, 1)
        xx = np.linspace(0, legs.max() * 1.05, 10)
        ax.plot(xx, k * xx + b, color=ORANGE, lw=1.2)
        fit = (k, b)
    ax.axhline(0, color=GRID, lw=0.6)
    ax.set_xlim(0, legs.max() * 1.15)
    ax.tick_params(labelsize=6.5)
    ax.set_xlabel("the leg, mV (the receiver's level, set by its DSA)", fontsize=6.5)
    ax.set_ylabel("the flip's Q plateau, mV", fontsize=6.5)
    t = "the flip (-1, 0) against the level on receiver %s (%s -> %s)" % (lk[1], lk[0], lk[1])
    if fit:
        t += "\nfit Q = %+.0f mV + %+.3f x leg: the receiver's Q offset %+.1f mV, the sender's quadrature term %+.1f %% (%.1f deg)" % (
            fit[1], fit[0], fit[1] / 2, 100 * fit[0], math.degrees(math.atan(fit[0])))
    ax.set_title(t, fontsize=6.8, loc="left", fontweight="bold")
    return fit


def header_text(run, opt, mhz):
    lines = []
    for lk in ("AB", "BA"):
        rec = run.J["links"].get(lk) if run else None
        if not rec:
            lines.append("%s -> %s: not run" % (lk[0], lk[1]))
            continue
        if "lock" not in rec:
            lines.append("%s -> %s: %s" % (lk[0], lk[1], rec.get("error", "no lock")))
            continue
        lock = rec["lock"]
        s = "%s -> %s: locked in %.0f s at DSA %.2f, leg %.0f mV, VC %.4f V, side %+d" % (
            lk[0], lk[1], lock.get("setup_s", 0), lock["dsa"], 1e3 * lock["leg"], lock.get("vc_lock") or 0, lock["side"])
        mk = (rec.get("cabling") or {}).get("marks") or {}
        if mk.get("latency_ns") is not None:
            s += "; the sender's mark to CMP I's edge %.1f ns, the I arm's half-way to CMP I %.1f ns, I's 10-90 %% %.1f ns" % (
                mk["latency_ns"], mk.get("cmp_delay_ns") or 0, mk.get("i_rise") or 0)
        dec = []
        for row in rec.get("constellations", []):
            d = row.get("decoder") or {}
            if "error" in d or "per_msg" not in d:
                dec.append("%s %s" % (row["scheme"], "no pilot" if (row.get("pilot") or {}).get("vr") is None and C.SCHEMES[row["scheme"]].pilot is not None else (d.get("error") or "?")[:40]))
            else:
                dec.append("%s %s" % (row["scheme"], "/".join("%.4g" % (100 * min(1.0, r["right_frac"])) for m, r in sorted(d["per_msg"].items(), key=lambda kv: int(kv[0]))) + " %"
                                      + (" (%.0f false/s)" % d["idle_false_per_s"] if d.get("idle_false_per_s") else "")))
        if dec:
            s += ".  Decoded right: " + ", ".join(dec)
        pr = [(p, opt["prbs"].get((lk, mhz, p))) for p in (50, 20)]
        pr = [(p, r) for p, r in pr if r]
        if pr:
            s += ".  PRBS bpsk (optsweep, 1 s each): " + ", ".join("%d clocks a bit BER %s over %.1f M bits" % (p, "0" if not r.get("ber") else "%.2g" % r["ber"], (r.get("bits") or 0) / 1e6) for p, r in pr if r.get("bits"))
        lines.append(s)
    return lines


def main():
    runs = [Run(b) for b in args_list("--runs", [])]
    opt = opt_numbers(arg("--opt", ""))
    out = os.path.join(HERE, "plots", arg("--out", "schemes_byfreq_%s" % time.strftime("%Y%m%d")))
    title = arg("--title", "The boards over SMA cables through 40 dB pads (no antennas), 2026-11-06")
    runs.sort(key=lambda r: r.mhz)
    with PdfPages(out + ".pdf") as pdf:
        for run in runs:
            mhz = run.mhz
            fig = plt.figure(figsize=(26, 32), dpi=100)
            nr = len(ORDER)
            gs = fig.add_gridspec(nr + 2, 5, width_ratios=[0.75, 1.15, 1.45, 1.15, 1.45], height_ratios=[0.42] + [1] * nr + [0.9],
                                  left=0.03, right=0.99, top=0.965, bottom=0.03, hspace=0.55, wspace=0.25)
            ax = fig.add_subplot(gs[0, :])
            ax.axis("off")
            head = ["%g MHz (%s).  %s" % (mhz, run.J["stamp"], title)]
            head += header_text(run, opt, mhz)
            head.append("Each row: the scheme's ideal received constellation; receiver A's I/Q plane (B -> A) with the scope's trajectories from the idle "
                        "to each point and back (I MON and Q MON through 1 k taps into 50 ohm, x21, 8 shots a point, the dot the settled level 60-180 ns "
                        "after the arrival, the ring its decoded-right fraction: green 99 %+, orange 90-99, red under 90; + the ideal point at this leg; red "
                        "lines the decoder's thresholds); A's time traces; then receiver B (A -> B).  The bottom row: the flip's Q against the level on each receiver.")
            ax.text(0, 1, "\n".join(textwrap.fill(h, 300) for h in head), va="top", ha="left", fontsize=8.2, color=INK, linespacing=1.3)
            for r, name in enumerate(ORDER):
                s = C.SCHEMES[name]
                draw_ideal(fig.add_subplot(gs[r + 1, 0]), s)
                draw_plane(fig.add_subplot(gs[r + 1, 1]), run, "BA", s)
                draw_traces(fig.add_subplot(gs[r + 1, 2]), run, "BA", s)
                draw_plane(fig.add_subplot(gs[r + 1, 3]), run, "AB", s)
                draw_traces(fig.add_subplot(gs[r + 1, 4]), run, "AB", s)
            draw_levels(fig.add_subplot(gs[nr + 1, 1:3]), run, "BA")
            draw_levels(fig.add_subplot(gs[nr + 1, 3:5]), run, "AB")
            axc = fig.add_subplot(gs[nr + 1, 0])
            axc.axis("off")
            cab = []
            for lk in ("BA", "AB"):
                v = ((run.J["links"].get(lk) or {}).get("cabling") or {}).get("verdicts") or []
                cab += ["%s -> %s cabling: " % (lk[0], lk[1]) + "; ".join(x for x in v if "WRONG" in x or "UNTERMINATED" in x) if any("WRONG" in x or "UNTERMINATED" in x for x in v)
                        else "%s -> %s cabling: every check passed (%d)" % (lk[0], lk[1], len(v))]
            axc.text(0, 1, "\n".join(textwrap.fill(c, 40) for c in cab), va="top", fontsize=7, color=INK)
            fig.text(0.03, 0.982, "The constellation schemes at %g MHz on rev A: the analog I and Q paths on both receivers (page %d of %d)" % (
                mhz, runs.index(run) + 1, len(runs)), fontsize=12, fontweight="bold", va="bottom")
            pdf.savefig(fig)
            fig.savefig("%s_%d.png" % (out, int(mhz)), dpi=72)
            plt.close(fig)
            print("page", mhz)
    print(out + ".pdf")


if __name__ == "__main__":
    main()
