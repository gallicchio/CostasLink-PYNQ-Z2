#!/usr/bin/env python3
"""The figures the top-level README shows (docs/images/readme_*.svg).

    python3 docs/readme_figures.py            write the four SVGs
    python3 docs/readme_figures.py --png DIR  also write PNGs into DIR, to look at

They explain; they are not measurements.  The numbers printed on them are the measured ones the README
quotes (bringup/LATENCY.md, bringup/BRINGUP_LOG.md), and the curve in the early-decision figure is a smooth
step drawn with the measured 12.5 ns rise.  The look is bringup/plotstyle.py's.
"""
import math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "bringup"))
import plotstyle as P                                            # noqa: E402
import matplotlib.pyplot as plt                                  # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle, Polygon   # noqa: E402
import numpy as np                                               # noqa: E402

OUT = os.path.join(HERE, "images")
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = P.SERIES[:5]
PNG_DIR = sys.argv[sys.argv.index("--png") + 1] if "--png" in sys.argv else None


def save(fig, name):
    fig.savefig(os.path.join(OUT, name + ".svg"), format="svg", bbox_inches="tight", pad_inches=0.12, facecolor=P.SURFACE)
    if PNG_DIR:
        fig.savefig(os.path.join(PNG_DIR, name + ".png"), dpi=130, bbox_inches="tight", pad_inches=0.12, facecolor=P.SURFACE)
    plt.close(fig)
    print("wrote docs/images/%s.svg" % name)


# ---------------------------------------------------------------------------------------------------------------
# 1. the architecture: what is on the board, and which path the latency runs along
def architecture():
    W, Hh, U = 141, 69, 0.0845                             # the drawing's units, and inches a unit
    fig = plt.figure(figsize=(W * U, Hh * U))
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, Hh); ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, Hh, facecolor=P.SURFACE, edgecolor="none"))
    FT, FS = 11.0, 9.6                                     # a box's name, and the part under it

    def box(x, y, w, h, title, sub=None):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.9", facecolor="#ffffff", edgecolor=P.AXIS, linewidth=0.9))
        if sub:
            ax.text(x + w / 2, y + h * 0.65, title, ha="center", va="center", fontsize=FT, color=P.INK, fontweight="bold")
            ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center", fontsize=FS, color=P.INK2)

    def arrow(p0, p1, color, lw=2.0):
        ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=11, color=color, linewidth=lw, shrinkA=0, shrinkB=0, zorder=3))

    def note(x, y, text, ha="center", bold=False):
        ax.text(x, y, text, ha=ha, va="center", fontsize=FS, color=P.INK if bold else P.INK2, fontweight="bold" if bold else "normal")

    def antenna(x, y, label, sub):
        ax.plot([x, x], [y - 3.2, y + 1.2], color=P.INK2, lw=1.4)
        ax.add_patch(Polygon([[x - 2.2, y + 4.2], [x + 2.2, y + 4.2], [x, y + 1.2]], closed=True, facecolor="none", edgecolor=P.INK2, linewidth=1.4))
        ax.text(x + 3.4, y + 1.7 if sub else y + 0.4, label, ha="left", va="center", fontsize=FT, color=P.INK, fontweight="bold")
        if sub:
            note(x + 3.4, y - 1.7, sub, ha="left")

    H = 8.6
    yT, yL, yC, yR = 52.0, 39.0, 25.0, 9.5                 # rows: transmit, TX synthesizer, carrier recovery, receive
    cT, cC, cR = yT + H / 2, yC + (H - 1) / 2, yR + H / 2   # their centre lines
    x1, w1, x2, w2, x3, w3 = 30.5, 20, 53.5, 18.5, 75, 20     # three columns of boxes
    # the FPGA
    ax.add_patch(FancyBboxPatch((2, 7), 25, 60, boxstyle="round,pad=0,rounding_size=1.1", facecolor="#f3f2ee", edgecolor=P.AXIS, linewidth=0.9))
    ax.text(14.5, 64.9, "FPGA", ha="center", va="center", fontsize=12.5, color=P.INK, fontweight="bold")
    note(14.5, 62.3, "Zynq-7020, PYNQ-Z2")
    box(4.2, yT, 20.6, H, "symbol out", "4 pins, 3.3 V")
    box(4.2, 28.3, 20.6, 16.0, "", " ")
    ax.text(14.5, 41.5, "fast path", ha="center", va="center", fontsize=FT, color=P.INK, fontweight="bold")
    for k, s in enumerate(("comparator pins", "to a lookup table", "to the ladder pins")):
        note(14.5, 38.3 - 2.6 * k, s)
    note(14.5, 30.3, "no clock: 5 to 6 ns", bold=True)
    box(4.2, yR, 20.6, H, "decode", "800 MS/s sampler")
    arrow((14.5, yR + H), (14.5, 28.3), ORANGE)
    arrow((14.5, 44.3), (14.5, yT), BLUE)
    # transmit, left to right
    box(x1, yT, w1, H, "resistor ladders", "2 bits each: I and Q")
    box(x2, yT, w2, H, "I/Q modulator", "ADL5375")
    box(x3 + 3, yT, 14, H, "gain block", "ADL5611")
    box(x2, yL, w2, H - 1.0, "TX synthesizer", "MAX2871, TCXO")
    antenna(117, cT - 0.4, "TX ANT", "+8 dBm at 5.2 GHz")
    for a, b in ((24.8, x1), (x1 + w1, x2), (x2 + w2, x3 + 3), (x3 + 17, 117)):
        arrow((a, cT), (b, cT), BLUE)
    arrow((x2 + w2 / 2, yL + H - 1.0), (x2 + w2 / 2, yT), BLUE, lw=1.6)
    # receive, right to left
    antenna(117, cR - 0.4, "RX ANT", "")
    box(98.5, yR, 13, H, "LNA", "SKY65404-31")
    box(x3, yR, w3, H, "attenuator, gain", "PE43711, 2 x ADL5611")
    box(x2, yR, w2, H, "I/Q demodulator", "ADL5380, zero-IF")
    box(x1, yR, w1, H, "5 comparators", "TLV3601, 4 x TLV3603")
    for a, b in ((117, 111.5), (98.5, x3 + w3), (x3, x2 + w2), (x2, x1 + w1), (x1, 24.8)):
        arrow((a, cR), (b, cR), ORANGE)
    note(x1, yR - 2.4, "between these two: the I and Q amplifiers (2 x THS4541, DC-coupled); thresholds from a 16-bit DAC", ha="left")
    # carrier recovery
    box(x1, yC, w1, H - 1.0, "sign(I) x Q", "analog switch")
    box(x2, yC, w2, H - 1.0, "loop filter", "3 kHz loop")
    box(x3, yC, w3, H - 1.0, "RX synthesizer", "MAX2871, VCXO")
    arrow((x1 + w1 / 2, yR + H), (x1 + w1 / 2, yC), AQUA, lw=1.6)
    arrow((x1 + w1, cC), (x2, cC), AQUA, lw=1.6)
    arrow((x2 + w2, cC), (x3, cC), AQUA, lw=1.6)
    ax.plot([x3 + w3 / 2, x3 + w3 / 2, x2 + w2 / 2], [yC, 21.6, 21.6], color=AQUA, lw=1.6, solid_capstyle="round", zorder=3)
    arrow((x2 + w2 / 2, 21.6), (x2 + w2 / 2, yR + H), AQUA, lw=1.6)
    note(74.5, 23.2, "local oscillator")
    note(x1 + w1 / 2 + 1.3, 21.6, "sign(I), Q", ha="left")
    # what it adds up to
    arrow((117, cR + 6.2), (117, cT - 5.2), P.INK2, lw=1.2)
    ax.text(119.4, 34.0, "antenna jack\nto antenna jack:\n20 to 25 ns", ha="left", va="center", fontsize=FT, color=P.INK, fontweight="bold", linespacing=1.4)
    # legend
    x = 2.5
    for c, s, w in ((BLUE, "transmit", 21), (ORANGE, "receive: no clock, no loop", 38), (AQUA, "carrier recovery: a hardware Costas loop that only steers the oscillator", 0)):
        ax.plot([x, x + 4], [2.6, 2.6], color=c, lw=2.4, solid_capstyle="round")
        ax.text(x + 5.2, 2.6, s, ha="left", va="center", fontsize=FS, color=P.INK2)
        x += w
    save(fig, "readme_architecture")


# ---------------------------------------------------------------------------------------------------------------
# 2. the constellations: the idle and N messages, and the comparators' thresholds
def constellation():
    P.setup()
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 5.4), facecolor=P.SURFACE)
    fig.subplots_adjust(wspace=0.12, left=0.03, right=0.97, top=0.82, bottom=0.11)
    idle = (1, 0)

    def frame(ax, title, sub):
        ax.set_facecolor(P.SURFACE); ax.grid(False)
        ax.set_xlim(-1.75, 1.75); ax.set_ylim(-1.62, 1.62); ax.set_aspect("equal")
        for s in ax.spines.values(): s.set_visible(False)
        ax.set_xticks([]); ax.set_yticks([])
        ax.axhline(0, color=P.AXIS, lw=0.9, zorder=1); ax.axvline(0, color=P.AXIS, lw=0.9, zorder=1)
        ax.text(1.72, -0.07, "I", ha="right", va="top", fontsize=10.5, color=P.INK2, style="italic")
        ax.text(0.05, 1.6, "Q", ha="left", va="top", fontsize=10.5, color=P.INK2, style="italic")
        ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", color=P.INK, pad=40)
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=9.2, color=P.INK2, va="bottom", ha="left", linespacing=1.4)

    def points(ax, msgs):
        for (x, y) in msgs:
            ax.add_patch(FancyArrowPatch(idle, (x, y), arrowstyle="-", color="#cfcec6", linewidth=1.0, zorder=2, shrinkA=7, shrinkB=7))
        ax.scatter([m[0] for m in msgs], [m[1] for m in msgs], s=95, color=ORANGE, edgecolor=P.SURFACE, linewidth=2, zorder=4, label="a message: one brief step, then back")
        ax.scatter([idle[0]], [idle[1]], s=130, color=BLUE, edgecolor=P.SURFACE, linewidth=2, zorder=5, label="idle: the carrier the loop stays locked to")

    def thr(ax, kind, v, label, where):
        if kind == "h":
            ax.plot([-1.6, 1.6], [v, v], color=P.MUTED, lw=1.1, ls=(0, (5, 3)), zorder=2)
            ax.text(where, v + (0.06 if v > 0 else -0.06), label, ha="left", va="bottom" if v > 0 else "top", fontsize=8.6, color=P.INK2)
        else:
            ax.plot([v, v], [-1.5, 1.5], color=P.MUTED, lw=1.1, ls=(0, (5, 3)), zorder=2)
            ax.text(v + 0.05, where, label, ha="left", va="center", fontsize=8.6, color=P.INK2, rotation=90)

    ax = axes[0]
    frame(ax, "Idle to 1 of 4: two bits a symbol", "The scheme the two-board tests ran.  Q leaving its window\nis the event and one bit; sign(I) is the other bit.")
    thr(ax, "h", 0.4, "Q above: comparator QP", -1.6); thr(ax, "h", -0.4, "Q below: comparator QN", -1.6)
    thr(ax, "v", 0.0, "sign(I)", -1.02)
    points(ax, [(1, 1), (-1, 1), (-1, -1), (1, -1)])
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles[::-1], labels[::-1], loc="lower center", bbox_to_anchor=(0.5, 0.01), ncol=2, fontsize=9.2, handletextpad=0.4, columnspacing=3.0)

    ax = axes[1]
    frame(ax, "Idle to 1 of 8: three bits a symbol", "The most this board's hardware can do: nine ladder points,\nread by four window comparators.")
    thr(ax, "h", 0.5, "QP", -1.6); thr(ax, "h", -0.5, "QN", -1.6)
    thr(ax, "v", 0.5, "IP", -1.33); thr(ax, "v", -0.5, "IN", -1.33)
    points(ax, [(x, y) for x in (-1, 0, 1) for y in (-1, 0, 1) if (x, y) != idle])
    save(fig, "readme_constellation")


# ---------------------------------------------------------------------------------------------------------------
# 3. deciding on the rise: a threshold near the idle is crossed long before the symbol settles
def early_decision():
    P.setup()
    RISE = 12.5                                   # ns, 10-90 %, measured end to end (BRINGUP_LOG 4.82, 4.86)
    sigma = RISE / 2.563                          # a Gaussian step: 10-90 % = 2.563 sigma
    T0 = 2.326 * sigma                            # the time axis starts where the step has moved 1 %
    cdf = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
    step = lambda tt: np.array([cdf((x - T0) / sigma) for x in np.atleast_1d(tt)])

    def cross(level):
        lo, hi = -20.0, 100.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if cdf((mid - T0) / sigma) < level else (lo, mid)
        return lo
    B_MHz = 350.0 / RISE                          # the usual 0.35 / rise time
    inv_B = 1e3 / B_MHz

    fig, ax = plt.subplots(figsize=(10.4, 5.2), facecolor=P.SURFACE)
    fig.subplots_adjust(left=0.07, right=0.97, top=0.80, bottom=0.13)
    ax.set_facecolor(P.SURFACE)
    t = np.linspace(-6, 48, 1200)
    ax.axhspan(-0.07, 0.07, color=P.MUTED, alpha=0.16, lw=0, zorder=1)
    ax.text(-5.6, 0.095, "noise on the idle", fontsize=8.8, color=P.INK2, va="bottom", ha="left")
    ax.plot(t, step(t), color=BLUE, lw=2.2, zorder=4, solid_capstyle="round")
    ax.text(42.5, 1.03, "received symbol", fontsize=9.2, color=P.INK2, va="bottom", ha="center")
    # the thresholds and where each is crossed
    for level, name in ((0.2, "a threshold for a quiet link"), (0.4, "the threshold of the two-station tests")):
        tc = cross(level)
        ax.plot([-6, tc], [level, level], color=P.MUTED, lw=1.1, ls=(0, (5, 3)), zorder=2)
        ax.plot([tc, tc], [-0.16, level], color=ORANGE, lw=1.1, zorder=3)
        ax.scatter([tc], [level], s=70, color=ORANGE, edgecolor=P.SURFACE, linewidth=2, zorder=5)
        ax.text(-5.6, level + 0.022, name, fontsize=8.8, color=P.INK2, va="bottom", ha="left")
        ax.text(tc + 0.8, level - 0.03, "crossed at about %.0f ns" % tc, fontsize=9.2, color=P.INK, va="top", ha="left", fontweight="bold")
    # the fast path's reply, and where a receiver that waits would decide
    ax.axvspan(20.4, 25.3, color=AQUA, alpha=0.20, lw=0, zorder=1)
    ax.text(22.85, 0.52, "measured: the reply\nis already leaving\nthe antenna jack,\n20 to 25 ns", fontsize=9.2, color=P.INK, va="center", ha="center", fontweight="bold", linespacing=1.4)
    ax.plot([inv_B, inv_B], [-0.16, 1.0], color=P.INK2, lw=1.1, zorder=3)
    ax.scatter([inv_B], [float(step(inv_B)[0])], s=70, color=P.INK2, edgecolor=P.SURFACE, linewidth=2, zorder=5)
    ax.text(inv_B + 0.8, 0.52, "1 / bandwidth = %.0f ns:\nwhere a receiver that\nwaits for the symbol\nwould decide" % inv_B, fontsize=9.2, color=P.INK, va="center", ha="left", linespacing=1.4)
    ax.set_xlim(-6, 48); ax.set_ylim(-0.16, 1.14)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0]); ax.set_yticklabels(["idle", "0.2", "0.4", "0.6", "0.8", "settled"])
    ax.set_xticks(range(0, 50, 5))
    ax.set_xlabel("time after the symbol's edge reaches the receiver (ns)")
    ax.grid(axis="x", visible=False)
    ax.set_title("The receiver decides on the rise, not on the settled symbol", loc="left", fontsize=12.5, fontweight="bold", color=P.INK, pad=40)
    ax.text(0, 1.02, "An illustration: a smooth step with the measured %.1f ns rise (10 to 90 %%), so a bandwidth near %.0f MHz.\n"
            "The lower the noise, the nearer the idle a threshold can sit, and the sooner the step crosses it." % (RISE, B_MHz),
            transform=ax.transAxes, fontsize=9.2, color=P.INK2, va="bottom", ha="left", linespacing=1.4)
    save(fig, "readme_early_decision")


# ---------------------------------------------------------------------------------------------------------------
# 4. where one round trip's time went (BRINGUP_LOG 4.70: the first exchange over the air, 2026-11-05)
def round_trip():
    P.setup()
    parts = [("dishes, cables and air: the path itself", 139.75, BLUE, "139.75 ns"),
             ("both boards' radio electronics", 3.3, ORANGE, "3.3 ns"),
             ("the prover's decision and reply, with no clock", 25.0, AQUA, "24 to 26 ns"),
             ("the reply's short path", 4.0, YELLOW, "about 4 ns"),
             ("the two FPGAs' clocked detection of an edge", 45.0, MAGENTA, "about 45 ns")]
    total = 217.5
    fig = plt.figure(figsize=(10.4, 2.9), facecolor=P.SURFACE)
    ax = fig.add_axes([0.03, 0.02, 0.94, 0.96]); ax.set_xlim(0, total); ax.set_ylim(0, 10); ax.axis("off")
    ax.text(0, 9.25, "Where one 217.5 ns round trip went", fontsize=12.5, fontweight="bold", color=P.INK, va="center", ha="left")
    ax.text(0, 7.75, "The first challenge and reply over the air, 2026-11-05: station A's transmit edge to its decision on B's echo.", fontsize=9.6, color=P.INK2, va="center", ha="left")
    gap = total * 0.0022
    x = 0.0
    for name, v, c, lab in parts:
        w = v * (total - gap * (len(parts) - 1)) / sum(p[1] for p in parts)
        ax.add_patch(FancyBboxPatch((x, 4.7), w, 1.95, boxstyle="round,pad=0,rounding_size=%g" % min(0.9, w / 2.2), facecolor=c, edgecolor="none", mutation_aspect=0.045))
        if w > 20:
            ax.text(x + 2.2, 5.67, lab, fontsize=9.6, color="#0b0b0b" if c == YELLOW else "#ffffff", va="center", ha="left", fontweight="bold")
        x += w + gap
    # legend, in block order; a number only where the block is too narrow to print it
    lx, ly = 0.0, 3.25
    for i, (name, v, c, lab) in enumerate(parts):
        col, row = divmod(i, 3)
        px, py = lx + col * 112, ly - row * 1.3
        ax.add_patch(FancyBboxPatch((px, py - 0.36), 3.0, 0.72, boxstyle="round,pad=0,rounding_size=0.3", facecolor=c, edgecolor="none", mutation_aspect=0.045))
        ax.text(px + 4.4, py, name + ("" if v > 20 else ": " + lab), fontsize=9.6, color=P.INK2, va="center", ha="left")
    save(fig, "readme_round_trip")


if __name__ == "__main__":
    P.setup()
    architecture(); constellation(); early_decision(); round_trip()
