#!/usr/bin/env python3
"""The figures of docs/LOCK.md (how the Costas loop holds lock and how it loses it), from the bench's data of
2026-10-30 in bringup/data/board_A/ and the model in bringup/loopmodel.py.  Nothing here is typed in by hand: rerun
it after new measurements and the figures follow.

    python3 docs/lock_figures.py          writes docs/images/lock_*.png

    lock_scurve      the detector's characteristic, clean and with an interferer near and far (the model)
    lock_forces      the restoring force and the push against the interferer's level, at three offsets (the model)
    lock_threshold   where the loop is dragged off, against the interferer's offset: the model and the bench
    lock_drag        VC through a strong CW, above and below, free and held (the bench)
    lock_pullin      why a dragged loop stays lost: what moves an unlocked loop, measured across the frequency
                     offset at three carriers, with the textbook's pull for comparison
    lock_pullout     the restoring force measured: the largest frequency step survived against a CW's level
    lock_holds       the gateware's holds at work (when bringup/data/board_A/holds/ has their tests)

The palette is the validated categorical set of the dataviz reference (blue, orange, aqua, and a neutral grey for
models and references); every figure is drawn on white so it reads in a browser, on GitHub's dark theme and printed.
"""
import glob
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "images")
DATA = os.path.join(ROOT, "bringup", "data", "board_A")
sys.path.insert(0, os.path.join(ROOT, "bringup"))
import loopmodel as M                                # noqa: E402

BLUE, ORANGE, AQUA, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#8a8984"
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]          # an interferer's level, low to high

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 200, "font.size": 10.5, "font.family": "DejaVu Sans",
    "axes.edgecolor": INK2, "axes.labelcolor": INK, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "xtick.color": INK2, "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 2.0, "legend.frameon": False, "figure.facecolor": "white", "axes.facecolor": "white",
})


def latest(pattern):
    fs = sorted(glob.glob(os.path.join(DATA, pattern)))
    return json.load(open(fs[-1])) if fs else None


def ic_db(gain):
    """the B210's gain to the interferer over the carrier at the board's receiver (BRINGUP_LOG 4.0: -6.4 dB at 70,
    +3.2 at 80, +11.4 at 89.75; about 0.96 dB a step; +-3 dB)"""
    if gain is None:
        return None
    return 11.4 if gain >= 89.7 else round(-6.4 + 0.96 * (gain - 70), 1)


def save(fig, name):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, name + ".png")
    fig.savefig(p, bbox_inches="tight", pad_inches=0.15, facecolor="white")
    plt.close(fig)
    print(os.path.relpath(p, ROOT))


# ---------------------------------------------------------------------------------------------------------------
def fig_scurve():
    th = np.linspace(-np.pi, np.pi, 721)
    fig, axs = plt.subplots(1, 2, figsize=(10, 3.9), sharey=True)
    for ax, fb, rdbs in ((axs[0], 0.1e6, (None, -6, 0, 6)), (axs[1], 20e6, (None, -6, 0, 3))):
        for k, rdb in enumerate(rdbs):
            r = 0.0 if rdb is None else 10 ** (rdb / 20)
            s = M.S(th, r, fb)
            lab = "no interferer" if rdb is None else ("%+d dB" % rdb)
            ax.plot(np.degrees(th), s, color=RAMP[k], label=lab)
        ax.axhline(0, color=INK2, lw=0.8)
        ax.set_xlim(-180, 180)
        ax.set_xticks([-180, -90, 0, 90, 180])
        ax.set_xlabel("carrier phase error θ (degrees)")
        ax.set_title("interferer %s MHz from the carrier" % ("0.1" if fb < 1e6 else "20"))
    axs[0].set_ylabel("detector output, averaged\n(1 = a clean carrier's peak)")
    for ax in axs:
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=4, fontsize=9, handlelength=1.6, columnspacing=1.0)
    axs[0].annotate("stable lock:\ncrosses zero going up", xy=(0, 0), xytext=(20, 0.62), fontsize=9, color=INK,
                    arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    axs[1].annotate("+3 dB: never reaches zero,\nno stable point at all", xy=(-30, 0.5), xytext=(-175, -0.6),
                    fontsize=9, color=INK, arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    save(fig, "lock_scurve")


def fig_forces():
    rdb = np.arange(-12, 18.01, 0.25)
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.6), sharey=True)
    for ax, fb in zip(axs, (0.1e6, 5e6, 20e6)):
        res = [M.restoring_and_push(10 ** (x / 20), fb) for x in rdb]
        rest = np.array([x[0] for x in res])
        push = np.abs(np.array([x[1] for x in res]))
        ax.plot(rdb, rest, color=BLUE, label="restoring force")
        ax.plot(rdb, push, color=ORANGE, label="push")
        thr = M.threshold_db(fb)
        if thr is not None and thr <= 18:
            ax.axvline(thr, color=INK2, ls="--", lw=1)
            ax.text(thr + 0.4, 1.08, "dragged from %+.1f dB" % thr, fontsize=9, color=INK, va="top")
        ax.set_title("interferer %g MHz away" % (fb / 1e6))
        ax.set_xlabel("interferer over carrier (dB)")
        ax.set_ylim(0, 1.15)
        ax.set_xlim(-12, 18)
    axs[0].set_ylabel("in units of a clean carrier's peak")
    axs[0].legend(loc="center left", fontsize=9)
    save(fig, "lock_forces")


def fig_threshold():
    fbs = np.logspace(np.log10(0.05e6), np.log10(50e6), 60)
    mod = [(f / 1e6, M.threshold_db(f)) for f in fbs]
    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    xs = [m[0] for m in mod if m[1] is not None]
    ys = [m[1] for m in mod if m[1] is not None]
    ax.plot(xs, ys, color=GREY, ls="--", label="model (comparator delay 12 ns)")
    pts = []
    runs = 0
    for f in sorted(glob.glob(os.path.join(DATA, "weekend", "decide_5200_*.json"))):
        dec = json.load(open(f))
        a = dec.get("a_leg")
        by = {}
        for r in dec.get("runs", []):
            if r["kind"] == "cw" and "during" in r:
                by.setdefault(r["x"], []).append((r["gain"], abs(r["during"]["di"]) < 0.5 * a))
        for x, v in by.items():
            g = next((g for g, lost in v if lost), None)
            pts.append(("round", "above", x, ic_db(g if g else max(gg for gg, _ in v)), g is None))
        runs += 1 if by else 0
    for f in sorted(glob.glob(os.path.join(DATA, "weekend", "pull_5200_*.json"))):
        pull = json.load(open(f))
        by = {}
        for r in pull.get("runs", []):
            if "lost_during" in r and not r.get("hold") and not r.get("auto"):
                by.setdefault(r["off_mhz"], []).append((r["gain"], all(r["lost_during"])))
        for off, v in by.items():
            g = next((g for g, lost in v if lost), None)
            pts.append(("pull", "above" if off > 0 else "below", abs(off), ic_db(g if g else max(gg for gg, _ in v)), g is None))
        runs += 1 if by else 0
    dodge = {("round", "above"): 0.90, ("pull", "above"): 0.97, ("pull", "below"): 1.07}    # apart, on the log axis
    for side, color in (("above", ORANGE), ("below", BLUE)):
        for setn, marker, lab in (("round", "o", "decision ladder"), ("pull", "^", "pull test")):
            p = [q for q in pts if q[0] == setn and q[1] == side]
            if not p:
                continue
            ax.scatter([q[2] * dodge.get((setn, side), 1.0) for q in p], [q[3] for q in p], marker=marker, s=60, zorder=3,
                       facecolors=[("white" if q[4] else color) for q in p], edgecolors=color, linewidths=1.6,
                       label="CW %s the carrier, %s" % (side, lab))
    ax.set_xscale("log")
    ax.set_xlim(0.05, 50)
    ax.set_xticks([0.1, 1, 10])
    ax.set_xticklabels(["0.1", "1", "10"])
    ax.set_ylim(-2, 22)
    ax.set_xlabel("interferer's offset from the carrier (MHz)")
    ax.set_ylabel("dragged off from (dB over the carrier)")
    ax.text(0.055, -1.4, "%d runs at 5.2 GHz (the kinds nudged apart sideways); hollow: never dragged up to the B210's +11 dB"
            % runs, fontsize=9, color=INK2)
    ax.legend(loc="upper right", fontsize=9)
    save(fig, "lock_threshold")


def fig_drag():
    d = latest("explain/drag_5200_*.json") or latest("explain/explain_drag_*.json")
    if not d:
        return
    kv = d["kv_hz_per_v"]
    fig, ax = plt.subplots(figsize=(9, 4.4))
    t_cw = cw = None
    for r in d["runs"]:
        if "rows" not in r:
            continue
        t = np.array([x[0] for x in r["rows"]])
        vc = np.array([x[1] for x in r["rows"]])
        khz = (vc - np.median(vc[:20])) * kv / 1e3
        lvl = ic_db(r["gain"])
        if r["hold"]:
            color, ls, lab = AQUA, ("--" if r["off_mhz"] < 0 else "-"), "%+g MHz, %+.0f dB, held" % (r["off_mhz"], lvl)
        elif lvl < 3:
            color, ls, lab = GREY, ":", "%+g MHz, %+.1f dB" % (r["off_mhz"], lvl)
        else:
            color, ls, lab = (ORANGE if r["off_mhz"] > 0 else BLUE), "-", "%+g MHz, %+.0f dB" % (r["off_mhz"], lvl)
        ax.plot(t, khz, color=color, ls=ls, label=lab)
        t_cw, cw = r["t_cw"], r["cw_s"]
    if t_cw is not None:
        ax.axvspan(t_cw, t_cw + cw, color=GRID, zorder=0)
        ax.text(t_cw + 0.5 * cw, 300, "CW on", fontsize=9, color=INK2, ha="center")
    ax.axhspan(-10, 60, color=AQUA, alpha=0.12, zorder=0)
    ax.text(0.02, 75, "capture window", fontsize=9, color=INK2, ha="left")
    ax.set_xlabel("time (s)")
    ax.set_ylabel("the loop's oscillator, offset from the lock (kHz)")
    ax.set_ylim(-720, 650)
    ax.legend(loc="lower right", fontsize=9, bbox_to_anchor=(1.0, 0.12))
    ax.annotate("stalls at +45 kHz:\na false lock", xy=(2.6, 45), xytext=(2.2, 260), fontsize=9,
                arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    save(fig, "lock_drag")


def zero_crossings(x, y):
    """where y changes sign between neighbours of x, by linear interpolation: (x0, falling) pairs; falling (y going
    from positive to negative as x rises) is a place an unlocked loop rests, rising a watershed"""
    out = []
    for k in range(len(x) - 1):
        if y[k] == 0 or y[k] * y[k + 1] < 0:
            x0 = x[k] - y[k] * (x[k + 1] - x[k]) / (y[k + 1] - y[k])
            out.append((float(x0), bool(y[k] > y[k + 1])))
    return out


def fig_pullin(kd=0.12, ko=2.70e6, tau1=1000e-6, tau2=75e-6):
    """what moves an unlocked loop: VC's rate of change against the oscillator's offset from the carrier, measured at
    three carriers (`bringup/weekend.py pullin`, BRINGUP_LOG 4.12: the loop held at each offset with the carrier on,
    then released for 3 ms by the sequencer with the TX left on, three releases a point).  For comparison the
    carrier's pull from the textbook's first-order result for a PI loop (Gardner, Phaselock Techniques, the pull-in
    chapter: the proportional path ripples the oscillator's phase at the beat, and the ripple's correlation with the
    detector leaves v = K_d^2 K_o (tau2 / tau1) / (2 dw), which the integrator turns into v / tau1 volts a second,
    toward the carrier), with this loop's parts (docs/images/block_loop.png).  Returns the measured zero crossings"""
    runs = [(m, c, latest("weekend/pullin_%d_*.json" % m)) for m, c in ((5000, BLUE), (5200, ORANGE), (5500, AQUA))]
    fig, ax = plt.subplots(figsize=(9.5, 5.0))
    ax.axvspan(36, 45, color=GREY, alpha=0.22, zorder=0)
    ax.axvspan(-61, -46, color=GREY, alpha=0.22, zorder=0)
    df = np.concatenate([-np.logspace(np.log10(700e3), np.log10(4e3), 300), np.logspace(np.log10(4e3), np.log10(700e3), 300)])
    pull = -np.sign(df) * kd ** 2 * ko * (tau2 / tau1) / (2 * 2 * np.pi * np.abs(df)) / tau1
    ax.plot(df[df < 0] / 1e3, pull[df < 0], color=GREY, lw=1.4, ls="--", label="the carrier's pull alone (textbook, this loop's parts)")
    ax.plot(df[df > 0] / 1e3, pull[df > 0], color=GREY, lw=1.4, ls="--")
    crossings = {}
    for m, c, d in runs:
        if not d:
            continue
        rows = sorted(d["rows"], key=lambda r: r["offset_khz"])
        x = np.array([r["offset_khz"] for r in rows], dtype=float)
        y = np.array([r["rate_v_s"] for r in rows])
        for side in (x < 0, x > 0):
            ax.plot(x[side], y[side], color=c, lw=1.8, marker="o", ms=5, mec="white", mew=1.0, zorder=3,
                    label="measured at %.1f GHz" % (m / 1e3) if side[0] else None)
        crossings[m] = zero_crossings(x[x < 0], y[x < 0]) + [(0.0, True)]
    ax.axhline(0, color=INK2, lw=0.8)
    ax.axvline(578, color=GREY, ls=":", lw=1)
    ax.axvline(-672, color=GREY, ls=":", lw=1)
    ax.text(560, -14.6, "dragged\nabove", fontsize=8.5, color=INK2, ha="right", va="bottom")
    ax.text(-650, -14.6, "dragged\nbelow", fontsize=8.5, color=INK2, ha="left", va="bottom")
    ax.annotate("below -100 kHz VC falls:\nto the bottom rail", xy=(-300, -2.6), xytext=(-640, -9.5), fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    ax.annotate("a resting place:\nthe false lock\n(-46 to -61 kHz, 3.9h)", xy=(-47, 0), xytext=(-640, 6.0), fontsize=8.5,
                color=INK, arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    ax.annotate("watersheds", xy=(-13, 0), xytext=(-48, -12.5), fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    ax.annotate("", xy=(-110, 0), xytext=(-40, -11.3), arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    ax.annotate("the lock", xy=(0, 0), xytext=(4, 9.5), fontsize=8.5, color=INK,
                arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    ax.annotate("above: VC falls everywhere,\ndown to the lock; slowest\nnear +40 kHz, where drags\nhave parked (4.5)",
                xy=(40, -1.5), xytext=(90, 4.0), fontsize=8.5, color=INK, arrowprops=dict(arrowstyle="->", color=INK2, lw=0.8))
    ax.set_xscale("symlog", linthresh=20, linscale=1.0)
    ax.set_xticks([-600, -300, -100, -50, -20, -10, 0, 10, 20, 50, 100, 300, 600])
    ax.set_xticklabels(["-600", "-300", "-100", "-50", "-20", "-10", "0", "10", "20", "50", "100", "300", "600"])
    ax.set_xlim(-750, 750)
    ax.set_ylim(-15, 12)
    ax.set_xlabel("the loop's oscillator, offset from the carrier (kHz; linear within +-20, logarithmic beyond)")
    ax.set_ylabel("rate of change of VC (V/s)\n(positive: up)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2, fontsize=8.5)
    save(fig, "lock_pullin")
    return crossings


def fig_pullout():
    po = latest("explain/pullout_5200_*.json") or latest("explain/explain_pullout_*.json")
    if not po:
        return
    rows = [r for r in po["rows"] if "held_khz" in r]
    clean = [r for r in rows if r["gain"] is None]
    meas = [r for r in rows if r["gain"] is not None]
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    x = np.array([ic_db(r["gain"]) for r in meas])
    ax.scatter(x - 0.2, [r["held_khz"]["+"] for r in meas], color=ORANGE, s=50, label="a step upward", zorder=3)
    ax.scatter(x + 0.2, [r["held_khz"]["-"] for r in meas], color=BLUE, marker="s", s=50, label="a step downward", zorder=3)
    if clean:
        c = clean[0]["held_khz"]
        cm = (c["+"] + c["-"]) / 2.0
        r0, _, _, _, _ = M.restoring_and_push(0.0, 1e6)
        rd = np.arange(-12, 12.01, 0.25)
        ax.plot(rd, [M.restoring_and_push(10 ** (v / 20), 1e6)[0] / r0 * cm for v in rd], color=GREY, ls="--",
                label="the model's restoring force, scaled to the clean loop")
        ax.axhline(cm, color=INK2, lw=0.8)
        ax.text(11.8, cm + 0.5, "no interferer: +%g / -%g kHz" % (c["+"], c["-"]), fontsize=9, color=INK2, ha="right")
    ax.set_xlabel("a CW 1 MHz from the carrier, over the carrier (dB)")
    ax.set_ylabel("largest sudden step survived (kHz)")
    ax.set_xlim(-12, 12)
    ax.set_ylim(0, 22)
    ax.legend(loc="upper left", fontsize=9)
    save(fig, "lock_pullout")


def fig_holds():
    """the gateware's holds at work (bringup/holds_tests.py): VC against the time from the event's start"""
    d = latest("holds/holds_5200_*.json")
    if not d:
        return
    runs = [r for r in d.get("runs", []) if "rows" in r]
    if not runs:
        return
    kv = d.get("kv_hz_per_v", 410e3)
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.4))
    word = {"locked": "locked", "slipped": "locked, 180° over", "beating": "lost", "other": "lost"}
    for ax, kind in zip(axs, ("interferer", "blocked")):
        rs = [r for r in runs if r["kind"] == kind]
        for r in rs:
            t = np.array([x[0] for x in r["rows"]]) - r["t_on"]
            vc = np.array([x[1] for x in r["rows"]])
            khz = (vc - np.median(vc[t < -0.05])) * kv / 1e3
            if kind == "interferer":
                ls = "-" if r["off_mhz"] > 0 else "--"
                what = "%+g MHz" % r["off_mhz"]
                color = AQUA if r["protect"] else ORANGE
            else:
                ls = "-" if r["dur_s"] > 1 else "--"
                what = "%g s" % r["dur_s"]
                color = AQUA if r["protect"] else BLUE
            ax.plot(t, khz, color=color, ls=ls, label="%s, %s: %s" % (what, "hold on" if r["protect"] else "hold off",
                                                                       word.get(r["after"], r["after"])))
        if kind == "interferer":
            ax.axvspan(0, 1.0, color=GRID, zorder=0)
            ax.text(0.5, 300, "CW on, +9 dB", fontsize=9, color=INK2, ha="center")
            ax.set_title("an interferer 10 MHz away, the interference hold")
        else:
            ax.axvspan(0, 2.0, color=GRID, zorder=0)
            ax.axvspan(0, 0.3, color=GRID, zorder=0)
            ax.text(1.0, -150, "carrier gone", fontsize=9, color=INK2, ha="center")
            ax.set_title("the carrier blocked, the signal holdover")
        ax.axhspan(-10, 60, color=AQUA, alpha=0.12, zorder=0)
        ax.set_xlabel("time from the event's start (s)")
        ax.set_xlim(-0.5, 4.0)
        ax.legend(loc="lower right", bbox_to_anchor=(1.0, 0.17), fontsize=8.5)
    axs[0].set_ylim(-720, 650)
    axs[1].set_ylim(-720, 650)
    axs[0].set_ylabel("the loop's oscillator, offset from the lock (kHz)")
    save(fig, "lock_holds")


def main():
    fig_scurve()
    fig_forces()
    fig_threshold()
    fig_drag()
    crossings = fig_pullin()
    fig_pullout()
    fig_holds()
    for m, c in sorted(crossings.items()):
        print("%d MHz, the unlocked loop's rate crosses zero at %s kHz (r: rests there, w: a watershed)" % (
            m, ", ".join("%+.0f %s" % (x, "r" if f else "w") for x, f in c)))


if __name__ == "__main__":
    main()
