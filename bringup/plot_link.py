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


def constellations(d, path, title=None, out_name=None):
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
    fig.suptitle(title or "Board A's constellations in loopback, %d MHz, DSA %.2f dB (the inverted Costas lock, idle on %sQ)" % (
        d["mhz"], r["dsa"], "+" if r["rot_deg"] > 0 else "-"), x=0.01, ha="left", fontsize=12, fontweight="bold")
    P.source(fig, "bringup/linktests.py schemes; %s; I MON / Q MON at 1 Mohm through the taps' 1 k: 5 us events, the messages in turn" % os.path.relpath(path, HERE))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return P.save(fig, os.path.join(OUTP, out_name or "link_constellations_%d.png" % d["mhz"]))


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


def turnaround(paths):
    """the reply overlay's turnaround in single-board loopback (linktests.py turn): from the stimulus's echo on the
    window comparators to the answer's, i.e. RX ANT to TX ANT plus ~1 ns of lead and pads, per path and frequency"""
    rows = [("base", "A2r", "no reply: TX event to RX decision (the receive path)"),
            ("sync_d16", "A2r", "synchronous reply, settled decision, 16 samples"),
            ("sync_d8", "A2r", "synchronous reply, settled, 8 samples"),
            ("sync_d4", "A2r", "synchronous reply, settled, 4 samples"),
            ("sync_d4_fe", "A2r", "synchronous reply, first-edge decision"),
            ("fast", "A2r", "fast path (pin to pin through LUTs), one shot"),
            ("ring", "A3r", "fast path, ring of the four A3r states (per hop)"),
            ("ring", "A1q2", "fast path, ring of the flip and the null (per hop)")]
    fig, ax = plt.subplots(figsize=(10.5, 5.6))
    for j, path in enumerate(paths):
        d = json.load(open(path))
        runs = {r["scheme"]: r for r in d["runs"]}
        col = P.SERIES[j]
        dy = 0.14 * (1 if j else -1)
        for i, (key, sch, _) in enumerate(rows):
            r = runs.get(sch, {})
            y = len(rows) - 1 - i + dy
            if key == "base" and "base" in r:
                b = r["base"]
                lo, mid, hi = b["lat_min"] * 1.25, (b["lat_mean"] or 0) * 1.25, b["lat_max"] * 1.25
            elif key == "ring" and r.get("ring", {}).get("turnaround_ns"):
                lo = mid = hi = r["ring"]["turnaround_ns"]
            elif key in r and r[key].get("mean_ns"):
                lo, mid, hi = r[key]["min_ns"], r[key]["mean_ns"], r[key]["max_ns"]
            else:
                continue
            ax.plot([lo, hi], [y, y], color=col, lw=2, solid_capstyle="round")
            ax.plot([mid], [y], "o", color=col, ms=8, mec=P.SURFACE, mew=1.5,
                    label=("%.1f GHz" % (d["mhz"] / 1000.0)) if i == 0 else None)
            ax.text(hi + 1.5, y, "%.1f" % mid, va="center", fontsize=8.5, color=P.INK2)
    ax.axvline(70, color=P.MUTED, lw=1, ls="--")
    ax.text(70.8, len(rows) - 0.45, "70 ns: TX event to decision, no reply", fontsize=8.5, color=P.INK2, va="top")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[2] for r in rows][::-1])
    ax.set_xlim(0, 100)
    ax.set_xlabel("ns (the mean marked, the line from min to max)")
    ax.grid(axis="y", visible=False)
    ax.set_title("Board A answers one of its own states in 23-25 ns by the fast path, 52-60 ns by the clocked reply")
    P.subtitle(ax, "Single-board loopback, 40 dB of pads; the window comparators' arrivals (CMP_I excluded: it chatters at the inverted lock), 1.25 ns samples")
    ax.legend(loc="lower right")
    P.source(fig, "bringup/linktests.py turn; " + ", ".join(os.path.relpath(p_, HERE) for p_ in paths))
    return P.save(fig, os.path.join(OUTP, "link_turnaround.png"))


def turn_sweep(path):
    """the fast path's ring hop against the windows' place on the edge (fraction of the leg) at each received level
    (linktests.py turnsweep).  A ring whose hops times its hop is not the ring's 20 us missed arrivals, and is left out;
    the line is the median of the rings kept, each ring a dot"""
    d = json.load(open(path))
    lv = sorted({r["dsa"] for r in d["runs"] if "a_leg" in r})
    fig, axs = plt.subplots(1, 2, figsize=(11.5, 5.2), sharey=True)
    for ax, sch, what in ((axs[0], "A3r", "A3r: a ring of the four corners\n(each hop enters a window)"),
                          (axs[1], "A1q2", "A1q2: flip, null, flip\n(half the hops leave a window)")):
        for k, dsa in enumerate(lv):
            runs = [r for r in d["runs"] if r.get("scheme") == sch and r["dsa"] == dsa and "a_leg" in r]
            if not runs:
                continue
            col = P.SEQ[min(len(P.SEQ) - 1, 2 + len(lv) - 1 - k)]          # darker = stronger
            xs, ys, weak = [], [], []
            for r in sorted(runs, key=lambda r: r["frac"]):
                ok = [h["turnaround_ns"] for h in r["rings"]
                      if h["turnaround_ns"] and h["hops"] and 0.97 < h["hops"] * h["turnaround_ns"] / (d["clocks"] * 10.0) < 1.03]
                ax.plot([r["frac"]] * len(ok), ok, "o", ms=3.5, color=col, alpha=0.45, mew=0)
                if ok:
                    xs.append(r["frac"])
                    ys.append(float(np.median(ok)))
                    weak.append(len(ok) < 2 or (max(ok) - min(ok)) > 3.0)
            ax.plot(xs, ys, "-", color=col, lw=2, label="DSA %.0f dB, leg %.0f mV" % (dsa, 1000 * runs[0]["a_leg"]))
            for x, y, w in zip(xs, ys, weak):
                ax.plot([x], [y], "o", ms=7, mfc=P.SURFACE if w else col, mec=col if w else P.SURFACE, mew=1.5)
        ax.set_title(what, fontsize=11, pad=8)
        ax.set_xlim(0.15, 0.75)
    axs[0].set_ylim(15, 36)
    fig.supxlabel("window threshold, as a fraction of the idle's leg from the no-carrier level", fontsize=10.5, color=P.INK2, y=0.03)
    axs[0].text(0.74, 15.4, "open: one clean ring, or rings 3 ns apart (the A3r ring\nstalls with high windows; its weakest level is off scale)",
                fontsize=8, color=P.INK2, ha="right", va="bottom")
    axs[0].set_ylabel("ns a hop, RX ANT to TX ANT plus ~0.7 ns of lead and pads")
    axs[1].legend(loc="upper right", title="received level", title_fontsize=9)
    fig.suptitle("Low windows save 3 ns: the fast path's hop is 20.4-20.8 ns at 0.2 of the leg, 23.3-25.3 at 0.4",
                 x=0.01, ha="left", fontsize=12.5, fontweight="bold", color=P.INK)
    fig.text(0.01, 0.915, "Board A, single-board loopback at %.1f GHz, 40 dB of pads; rings of 20 us on the fast path (CMP_I excluded). "
             "Regulated DSA %.0f dB; above %.0f dB the inverted lock did not hold." % (d["mhz"] / 1000.0, d["regulated_dsa"], lv[-1]),
             fontsize=9, color=P.INK2, ha="left")
    fig.subplots_adjust(top=0.80, bottom=0.14, wspace=0.12)
    P.source(fig, "bringup/linktests.py turnsweep; " + os.path.relpath(path, HERE))
    return P.save(fig, os.path.join(OUTP, "link_turn_sweep.png"))



# ---- after the sign jumpers moved (locktests.py) ----
def lock0(paths):
    """the designed lock at each frequency: pull-in, the step response, the DSA range, and the hold-in and hold tests"""
    ds = [json.load(open(p)) for p in paths]
    if not ds:
        return None
    extra = []
    for d in ds:                                       # the re-runs (locktests.py dsa / step) replace the first pass's
        f = newest("dsa0_%d_*.json" % d["mhz"])
        if f:
            d["dsa_range"] = json.load(open(f))["dsa_range"]
            extra.append(f)
        runs = [d["step_response"]] if d.get("step_response") else []
        for f in sorted(glob.glob(os.path.join(DATA, "link", "step0_%d_*.json" % d["mhz"]))):
            runs += [r for r in json.load(open(f))["runs"] if r.get("caps")]
            extra.append(f)
        fits = [(r, c) for r in runs for c in r.get("caps", []) if c.get("fit") and c["fit"].get("model") == "under"
                and 0.2 < c["fit"]["zeta"] < 1.5 and 500 < c["fit"]["fn_hz"] < 2e4 and c["tdiv"] < 5e-4]
        d["step_fits"] = [c["fit"] for _, c in fits]
        if fits:
            r, c = min(fits, key=lambda rc: rc[1]["fit"]["rms_rad"] / max(0.05, abs(rc[1]["fit"]["peak_rad"])))
            d["step_response"] = dict(r, caps=[c])
    paths = list(paths) + extra
    fig, axs = plt.subplots(2, 2, figsize=(15.0, 10.5), gridspec_kw={"wspace": 0.32, "hspace": 0.45})
    marks = {"locked": ("o", None), "railed": ("x", None), "false": ("D", None), "unlocked": ("s", None),
             "vc_clipped": ("+", None), "locked_off_axis": ("o", "hollow")}
    ax = axs[0, 0]
    for k, d in enumerate(ds):
        for r in d.get("pull_in", []):
            st = r.get("state0", r["state"])
            m, h = marks.get(st, ("s", None))
            col = P.SERIES[k]
            ax.plot(r["offset_khz"], k, ls="none", marker=m, markersize=9, color=col,
                    markerfacecolor=P.SURFACE if (h or m in "x+") else col, markeredgecolor=col, markeredgewidth=1.6)
    ax.set_yticks(range(len(ds)))
    ax.set_yticklabels(["%.1f GHz, DSA %.0f" % (d["mhz"] / 1e3, d["regulated_dsa"]) for d in ds])
    ax.set_ylim(-0.7, len(ds) - 0.3)
    ax.set_xlabel("the held beat's offset at release, kHz")
    ax.set_title("Pull-in: released from a held beat")
    P.subtitle(ax, "o locked (the idle on +-I, CMP_I quiet); x the integrator railed; diamond a false lock")
    ax = axs[0, 1]
    for k, d in enumerate(ds):
        sr = d.get("step_response") or {}
        caps = [c for c in sr.get("caps", []) if c.get("fit") and c["fit"].get("model") and c["tdiv"] < 5e-4]
        if not caps:
            continue
        c = min(caps, key=lambda c: c["fit"]["rms_rad"])
        t = np.asarray(c["t"]); q = np.asarray(c["q"]) - sr["q_mean"]
        phi = np.arcsin(np.clip(q / sr["a_mon"], -1, 1))
        f = c["fit"]; A, a, b, t0 = f["params"]
        x = np.clip(t - t0, 0, None)
        fit = A * np.exp(-a * x) * np.sin(b * x) if f["model"] == "under" else A * (np.exp(-a * x) - np.exp(-b * x))
        sg = np.sign(f["peak_rad"]) or 1
        ax.plot((t - t0) * 1e6, sg * phi, color=P.SERIES[k], lw=1.2, alpha=0.55)
        ax.plot((t - t0) * 1e6, sg * fit, color=P.SERIES[k], lw=2.2, ls=(0, (5, 2)),
                label="%.1f GHz: f_n %.2f kHz, damping %.2f (%s, %.1f kHz step)" % (d["mhz"] / 1e3, f["fn_hz"] / 1e3, f["zeta"],
                                                                                  "up" if c["up"] else "down", sr["khz"]))
        fs = d.get("step_fits") or []
        if len(fs) > 1:
            ax.text(0.98, 0.70 - 0.08 * k, "%.1f GHz, %d clean fits: f_n %.2f-%.2f kHz, damping %.2f-%.2f" % (
                d["mhz"] / 1e3, len(fs), min(x["fn_hz"] for x in fs) / 1e3, max(x["fn_hz"] for x in fs) / 1e3,
                min(x["zeta"] for x in fs), max(x["zeta"] for x in fs)), transform=ax.transAxes, ha="right", fontsize=8.5,
                color=P.INK2)
    ax.axhline(0, color=P.MUTED, lw=1)
    ax.set_xlim(-50, 600)
    ax.set_xlabel("time from the VC_OFF step, us")
    ax.set_ylabel("phase error, rad")
    ax.set_title("The step response after a frequency step")
    P.subtitle(ax, "asin(Q MON / the idle's I MON) on the scope at 1 Mohm; thin the capture, dashed the fit")
    ax.legend(loc="upper right")
    ax = axs[1, 0]
    for k, d in enumerate(ds):
        rows = d.get("dsa_range", [])
        lk = [r for r in rows if r["locked"]]
        if lk:
            ax.plot([r["dsa"] for r in lk], [20 * np.log10(abs(r["di"])) for r in lk], color=P.SERIES[k], marker="o",
                    markersize=5, label="%.1f GHz" % (d["mhz"] / 1e3))
        nl = [r for r in rows if not r["locked"]]
        if nl:
            ax.plot([r["dsa"] for r in nl], [-32] * len(nl), ls="none", marker="x", color=P.SERIES[k], markersize=8)
    if ds and ds[0].get("dsa_range"):
        r0 = [r for r in ds[0]["dsa_range"] if r["locked"]]
        if r0:
            x0 = r0[-1]["dsa"]; y0 = 20 * np.log10(abs(r0[-1]["di"]))
            xx = np.array([x0 - 20, x0])
            ax.plot(xx, y0 + (x0 - xx), color=P.MUTED, lw=1, ls=(0, (4, 3)))
            ax.text(x0 - 20, y0 + 20.5, "1 dB per dB", color=P.INK2, fontsize=8.5)
    ax.set_xlabel("DSA, dB")
    ax.set_ylabel("the I leg's DC at the lock, dB re 1 V")
    ax.set_title("The attenuator range")
    P.subtitle(ax, "A release from a few kHz at each DSA; x along the bottom: no lock")
    ax.legend(loc="upper right")
    ax = axs[1, 1]
    ax.axis("off")
    lines = []
    for d in ds:
        lines.append("%.1f GHz, DSA %.0f, the lock at VC %.3f V" % (d["mhz"] / 1e3, d["regulated_dsa"], d.get("vc_lock", float("nan"))))
        hi = d.get("hold_in", {})
        if hi:
            lines.append("  static hold-in (a slow ramp): %+.0f / %+.0f kHz," % (
                hi.get("+", {}).get("khz", float("nan")), hi.get("-", {}).get("khz", float("nan"))))
            lines.append("    the integrator's and the DAC's range, not the loop's")
        st = d.get("steps", [])
        if st:
            held = [abs(r["khz"]) for r in st if r["locked"]]
            lost = [r["khz"] for r in st if not r["locked"]]
            lines.append("  steps held to %.0f kHz%s" % (max(held) if held else 0,
                         (", lost at %+.0f kHz" % lost[0]) if lost else ""))
        for h in d.get("hold_test", []):
            lines.append("  hold %g s: %s%s%s" % (h["hold_s"], "locked after" if h["locked_after"] else "LOST",
                         ", to the other side" if h["slipped"] else "",
                         "" if h.get("dq_end") is None else ", Q moved %+.3f V" % h["dq_end"]))
        lines.append("")
    ax.text(0, 1, "\n".join(lines), transform=ax.transAxes, va="top", ha="left", fontsize=9.5, color=P.INK2, family="monospace")
    ax.set_title("Hold-in and the hold test")
    fig.suptitle("Board A: the Costas loop at its designed point (sign jumpers moved, 2026-10-30)", x=0.01, ha="left",
                 fontsize=13, fontweight="bold", color=P.INK)
    P.source(fig, "bringup/locktests.py lock; %s" % ", ".join(os.path.relpath(p, HERE) for p in paths))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.88, bottom=0.08)
    return P.save(fig, os.path.join(OUTP, "lock0.png"))


def schemes0(paths):
    """the plan's schemes at the designed lock: latency, the closed-loop BER, the idle's false events"""
    ds = [json.load(open(p)) for p in paths]
    if not ds:
        return None
    fig, axs = plt.subplots(1, 3, figsize=(15.5, 5.4))
    ax = axs[0]
    labels = []
    for k, d in enumerate(ds):
        for j, s in enumerate(d.get("runs", [])):
            if not s.get("lat_n"):
                continue
            y = j + 0.18 * (k - (len(ds) - 1) / 2)
            lo, mu, hi = (s[x] * 1.25 for x in ("lat_min", "lat_mean", "lat_max"))
            ax.plot([lo, hi], [y, y], color=P.SERIES[k], lw=2.4, solid_capstyle="round")
            ax.plot(mu, y, "o", color=P.SERIES[k], markersize=7, markeredgecolor=P.SURFACE,
                    label="%.1f GHz, DSA %.0f" % (d["mhz"] / 1e3, d["regulated_dsa"]) if j == 0 else None)
            ok = s["decided"] == s["events"] and not s["false"] and not s["missed"]
            if k == 0:
                labels.append("%s%s" % (s["scheme"], " (first edge)" if s["first_edge"] else ""))
            ax.text(hi + 0.6, y, "%d/%d%s" % (s["decided"], s["events"], "" if ok else " !"), fontsize=7.5, color=P.INK2,
                    va="center")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels)
    ax.set_ylim(len(labels) + 0.4, -0.6)
    ax.set_xlabel("TX event to RX decision, ns (min, mean, max)")
    ax.set_title("The plan's schemes, 20 000 events each")
    P.subtitle(ax, "Decided / sent beside each; none false or missed unless marked !")
    ax.legend(loc="lower right")
    ax = axs[1]
    for k, d in enumerate(ds):
        b = [r for r in d.get("ber", []) if r.get("bits")]
        if not b:
            continue
        x = np.array([r["baud"] / 1e6 for r in b])
        y = np.array([r["ber"] for r in b])
        z = y == 0
        ub = np.array([1.0 / r["bits"] for r in b])
        ax.plot(x[~z], y[~z], "o", color=P.SERIES[k], markersize=8, label="%.1f GHz: errors" % (d["mhz"] / 1e3))
        ax.plot(x[z], ub[z], "v", color=P.SERIES[k], markersize=8, markerfacecolor=P.SURFACE, markeredgewidth=1.6,
                label="%.1f GHz: none (1 / bits shown)" % (d["mhz"] / 1e3))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("symbol rate, Mbaud (BPSK, PRBS15)")
    ax.set_ylabel("bit-error rate")
    ax.set_title("The BER on CMP_I, the loop closed")
    P.subtitle(ax, "1 s a rate; the Costas loop tracks through the data")
    ax.legend(loc="upper left")
    ax = axs[2]
    wins = ("CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN", "CMP_I")
    for k, d in enumerate(ds):
        fe = d.get("false_events", [])
        if not fe:
            continue
        fr = [r["frac"] for r in fe]
        tot = [sum(r["edges"][w] for w in wins) for r in fe]
        y = [t if t else 0.5 for t in tot]
        ax.plot(fr, y, color=P.SERIES[k], marker="o", markersize=6, label="%.1f GHz" % (d["mhz"] / 1e3))
        for x_, t in zip(fr, tot):
            if not t:
                ax.plot(x_, 0.5, "v", color=P.SERIES[k], markersize=8, markerfacecolor=P.SURFACE, markeredgewidth=1.6)
    ax.set_yscale("log")
    ax.set_ylim(0.3, None)
    ax.set_xlabel("the windows' place, a fraction of the idle's leg a")
    ax.set_ylabel("comparator edges at the idle, per second (all five)")
    ax.set_title("The idle's false events")
    P.subtitle(ax, "Hollow at 0.5: none in 1 s")
    ax.legend(loc="upper right")
    fig.suptitle("Board A: the plan's schemes at the designed lock (sign jumpers moved, 2026-10-30)", x=0.01, ha="left",
                 fontsize=13, fontweight="bold", color=P.INK)
    P.source(fig, "bringup/locktests.py schemes; %s" % ", ".join(os.path.relpath(p, HERE) for p in paths))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    out = [P.save(fig, os.path.join(OUTP, "schemes0.png"))]
    for d, p in zip(ds, paths):
        if d.get("constellations"):
            d2 = {"mhz": d["mhz"], "runs": [{"constellations": d["constellations"], "dsa": d["regulated_dsa"]}]}
            out.append(constellations(d2, p, title="Board A's constellations at the designed lock, %d MHz, DSA %.2f dB (the idle on %sI)" % (
                d["mhz"], d["regulated_dsa"], "+" if d.get("side", 1) > 0 else "-"), out_name="schemes0_constellations_%d.png" % d["mhz"]))
    return out



# ---- the pop-in tests (podtests.py) ----
def pod(leak_path, lomon_path):
    """test B: the TX carrier at RX MON with both ports terminated, against the loopback's map; test C: LO RX MON"""
    fig, axs = plt.subplots(1, 2, figsize=(13.5, 5.0))
    ax = axs[0]
    d = json.load(open(leak_path))
    rows = d["rows"]
    f = np.array([r["mhz"] for r in rows]) / 1e3
    def col(on, dsa, key="tx_carrier"):
        return np.array([[x[key] for x in r["pts"] if x["tx_on"] == on and x["dsa"] == dsa][0] for r in rows])
    ax.plot(f, col(True, 31.75), color=P.SERIES[0], marker="o", markersize=4, label="terminated, TX on, DSA 31.75")
    ax.plot(f, col(True, 0.0), color=P.SERIES[1], marker="o", markersize=4, label="terminated, TX on, DSA 0")
    ax.plot(f, col(False, 31.75), color=P.MUTED, lw=1.4, label="terminated, TX muted, DSA 31.75")
    maps = sorted(glob.glob(os.path.join(DATA, "overnight", "map_20261030_*.json")))
    if maps:
        m = json.load(open(maps[-1]))
        mm = [(r["mhz"] / 1e3, [p["rx_mon"] for p in r["points"] if p["dsa"] == 31.75]) for r in m if r["mhz"] >= 4900]
        mm = [(x, y[0]) for x, y in mm if y]
        ax.plot([x for x, _ in mm], [y for _, y in mm], color=P.SERIES[2], marker="s", markersize=5, ls=(0, (4, 2)),
                label="loopback (lead + 40 dB), DSA 31.75, %s" % os.path.basename(maps[-1])[13:17])
    ax.set_xlabel("frequency, GHz")
    ax.set_ylabel("TX carrier at RX MON, dBm")
    ax.set_title("Test B: the leak with both ports terminated")
    P.subtitle(ax, "It stays within -6.5 / +14 dB of the loopback's level: on the board, not the lead")
    ax.legend(loc="lower left", fontsize=8.5)
    ax = axs[1]
    d = json.load(open(lomon_path))
    ax.plot([r["mhz"] / 1e3 for r in d["rows"]], [r["dbm"] for r in d["rows"]], color=P.SERIES[0], marker="o", markersize=4)
    for x, t in ((3.8, "model: a peak near 3.8"), (4.3, "model: a null near 4.3")):
        ax.axvline(x, color=P.MUTED, lw=1, ls=(0, (4, 3)))
        ax.text(x + 0.03, -22, t, color=P.INK2, fontsize=8.5, rotation=90, va="bottom")
    ax.axhline(-1, color=P.MUTED, lw=1)
    ax.text(5.2, -0.4, "RFOUTB programmed -1 dBm", color=P.INK2, fontsize=8.5)
    ax.set_xlabel("RX synthesizer, GHz")
    ax.set_ylabel("LO RX MON (J109), dBm")
    ax.set_title("Test C: LO RX MON against frequency")
    P.subtitle(ax, "RFOUTB on; the analyser on J109's U.FL pigtail (its loss not taken out)")
    fig.suptitle("Board A: tests B and C (2026-10-30)", x=0.01, ha="left", fontsize=13, fontweight="bold", color=P.INK)
    P.source(fig, "bringup/podtests.py; %s, %s" % (os.path.relpath(leak_path, HERE), os.path.relpath(lomon_path, HERE)))
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return P.save(fig, os.path.join(OUTP, "pod_tests_bc.png"))



# ---- the lock lab (locklab.py) ----
def locklab():
    """the lock and its loss, one figure: what the detector sees, dropouts free and held, where releases end, the
    acquisition search from real offsets"""
    L = os.path.join(DATA, "locklab")
    last = lambda pat: sorted(glob.glob(os.path.join(L, pat)))                               # noqa: E731
    fig, axs = plt.subplots(2, 2, figsize=(15.0, 10.5), gridspec_kw={"wspace": 0.28, "hspace": 0.5})
    # (a) the detector
    ax = axs[0, 0]
    d = json.load(open(last("detect_2*.json")[-1]))
    groups = (("locked", P.SERIES[0], "o"), ("beat", P.SERIES[1], "s"), ("no signal", P.MUTED, "x"), ("release", P.SERIES[3], "D"))
    for name, col, m in groups:
        rows = [r for r in d["rows"] if (r["kind"] == "locked" if name == "locked" else r["kind"].startswith(name))]
        rows = [r for r in rows if not (name == "release" and r["state"] == "locked")]
        if rows:
            ax.plot([max(1, r["edges"]["CMP_I"]) for r in rows], [r["log_q"] for r in rows], ls="none", marker=m, color=col,
                    markersize=7, label={"release": "false lock (far release)"}.get(name, name), alpha=0.85)
    ax.set_xscale("log")
    ax.set_xlabel("CMP_I edges in 10 ms (0 drawn at 1)")
    ax.set_ylabel("LOG_Q, V")
    ax.set_title("What tells the lock (3.9a)")
    P.subtitle(ax, "5.0 GHz at DSA 20 / 26 / 29 and 5.2 GHz at DSA 10 / 16 / 19; locked: CMP_I silent, the I leg up")
    ax.legend(loc="lower right")
    # (b) dropouts
    ax = axs[0, 1]
    d = json.load(open(last("drop_2*.json")[-1]))
    for hold, ls in ((0, "-"), (1, (0, (4, 2)))):
        for k, (mhz, dsa) in enumerate(sorted(set((r["mhz"], r["dsa"]) for r in d["rows"]))):
            rows = sorted([r for r in d["rows"] if r["hold"] == hold and (r["mhz"], r["dsa"]) == (mhz, dsa)], key=lambda r: r["dur_s"])
            n = [r["locked"] + r["slipped"] + r["lost"] for r in rows]
            ax.plot([r["dur_s"] for r in rows], [100.0 * r["lost"] / max(1, x) for r, x in zip(rows, n)], color=P.SERIES[k], ls=ls,
                    marker="o" if hold == 0 else "s", markersize=5,
                    label="%.1f GHz DSA %.0f, %s" % (mhz / 1e3, dsa, "free" if hold == 0 else "held: lost") if hold == 0 or k == 0 else None)
            if hold:
                ax.plot([r["dur_s"] for r in rows], [100.0 * r["slipped"] / max(1, x) for r, x in zip(rows, n)], color=P.SERIES[k],
                        ls=":", marker="^", markersize=5, label="held: slipped 180 degrees" if k == 0 else None)
    ax.set_xscale("log")
    ax.set_ylim(-5, 105)
    ax.set_xlabel("TX muted for, s (the sequencer)")
    ax.set_ylabel("% of five gaps")
    ax.set_title("Dropouts: free loop lost, held loop never lost (3.9b, 3.9e)")
    P.subtitle(ax, "Held: no losses up to 1 s; 180-degree slips from 10 ms, our own TX_DIS pushing the TCXO (3.9i)")
    ax.legend(loc="center left", fontsize=8)
    # (c) where releases end
    ax = axs[1, 0]
    d = json.load(open(last("falselock_2*.json")[-1]))
    conds = sorted(set((r["mhz"], r["dsa"]) for r in d["rows"]))
    for k, c in enumerate(conds):
        rows = [r for r in d["rows"] if (r["mhz"], r["dsa"]) == c]
        for r in rows:
            ok = r["state"] in ("locked", "slipped")
            ax.plot(r["start_khz"], k, ls="none", marker="o" if ok else "D", markersize=7, color=P.SERIES[0] if ok else P.SERIES[1],
                    markerfacecolor=P.SERIES[0] if ok else P.SURFACE, markeredgewidth=1.5)
    ax.set_yticks(range(len(conds)))
    ax.set_yticklabels(["%.1f GHz, DSA %.0f" % (m / 1e3, x) for m, x in conds])
    ax.set_ylim(-0.7, len(conds) - 0.3)
    ax.set_xlabel("released from, kHz off the lock")
    ax.set_title("Where releases end (3.9h)")
    P.subtitle(ax, "filled: locked; hollow diamond: false lock or runaway.  The window is about -10 to +20..+60 kHz")
    # (d) the search
    ax = axs[1, 1]
    for k, f in enumerate(last("search2_2*.json")):
        d = json.load(open(f))
        for j, dsa in enumerate(sorted(set(r["dsa"] for r in d["rows"]))):
            rows = sorted([r for r in d["rows"] if r["dsa"] == dsa], key=lambda r: r["offset_hz"])
            ax.plot([r["offset_hz"] / 1e3 for r in rows], [r["n_tries"] for r in rows], marker="o", markersize=5,
                    color=P.SERIES[2 * k + j], label="%.1f GHz DSA %.0f: %d of %d" % (d["mhz"] / 1e3, dsa, sum(r["locked"] for r in rows), len(rows)))
    ax.set_xlabel("the TX synthesizer's offset (fractional-N), kHz")
    ax.set_ylabel("releases until locked")
    ax.set_title("Acquisition from a real offset (3.9j)")
    P.subtitle(ax, "A downward stepped search from +120 kHz, 15 kHz a step, the detector stopping it")
    ax.legend(loc="upper right")
    fig.suptitle("Board A: the Costas loop's lock and its loss, in loopback (2026-10-30)", x=0.01, ha="left", fontsize=13,
                 fontweight="bold", color=P.INK)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.88, bottom=0.07)
    return P.save(fig, os.path.join(OUTP, "locklab.png"))


def main(argv):
    P.setup()
    if len(argv) > 1 and argv[1] == "locklab":
        print(locklab())
        return
    if len(argv) > 1 and argv[1] == "pod":
        pd = os.path.join(DATA, "pod")
        print(pod(sorted(glob.glob(os.path.join(pd, "leak_*.json")))[-1], sorted(glob.glob(os.path.join(pd, "lomon_*.json")))[-1]))
        return
    if len(argv) > 1 and argv[1] in ("lock0", "schemes0"):
        fs = argv[2:] or sorted(set(newest("%s_%d_*.json" % (argv[1], m)) for m in (5000, 5200)) - {None})
        print((lock0 if argv[1] == "lock0" else schemes0)(fs))
        return
    if len(argv) > 1 and argv[1] == "lodrive":
        print(lodrive(argv[2] if len(argv) > 2 else newest("lodrive_*.json")))
        return
    if len(argv) > 1 and argv[1] == "turnsweep":
        print(turn_sweep(argv[2] if len(argv) > 2 else newest("turnsweep_*.json")))
        return
    if len(argv) > 1 and argv[1] == "turn":
        print(turnaround(argv[2:]))
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
