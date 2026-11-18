"""The overnight soak's page from soak_night.py's records: both boards' temperature and +5V_RF, their arms' no-carrier
centres and the sign comparator's duty, each link's lock (DSA, leg, VC), A3 / B1 right and false events, the PRBS
(cumulative bits and mismatches), the flip's quadrature and the latency on the scope, all against the hour.
    python3 soak_fig.py [soak_<stamp>]  ->  plots/soak_<stamp>.png / .pdf"""
import json
import os
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                 # noqa: E402
import numpy as np                                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.environ.get("CL_BRINGUP", HERE), "data", "twoboard")     # the project's bringup/, or another copy's
BLUE, ORANGE, AQUA, RED, GREEN, VIOLET = "#2a78d6", "#eb6834", "#1baf7a", "#e34948", "#008300", "#6250d6"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
BCOL = {"A": BLUE, "B": ORANGE}
LCOL = {"AB": ORANGE, "BA": BLUE}
LNAME = {"AB": "A -> B (receiver B)", "BA": "B -> A (receiver A)"}

base = sys.argv[1] if len(sys.argv) > 1 else sorted(f[:-5] for f in os.listdir(DATA) if f.startswith("soak_") and f.endswith(".json"))[-1]
if not os.path.dirname(base):
    base = os.path.join(DATA, base)
J = json.load(open(base + ".json"))
cyc = J["cycles"]
t0 = cyc[0]["t"] if cyc else time.time()
hours = np.array([c["t"] - t0 for c in cyc]) / 3600


def frame(ax, xl="hours since the start", yl="", t=""):
    for sp in ax.spines.values():
        sp.set_color(GRID)
    ax.tick_params(labelsize=7, colors=INK2)
    ax.grid(color=GRID, lw=0.4)
    ax.set_xlabel(xl, fontsize=7.5)
    ax.set_ylabel(yl, fontsize=7.5)
    ax.set_title(t, fontsize=8.5, loc="left", fontweight="bold")


def q(path, default=np.nan):
    out = []
    for c in cyc:
        v = c
        try:
            for k in path:
                v = v[k]
            out.append(default if v is None else v)
        except (KeyError, TypeError):
            out.append(default)
    return np.array(out, float)


fig, axs = plt.subplots(4, 3, figsize=(24, 20), dpi=100)
fig.subplots_adjust(left=0.045, right=0.99, top=0.93, bottom=0.04, hspace=0.5, wspace=0.25)
# row 0: the boards quiet
for b in ("A", "B"):
    axs[0, 0].plot(hours, q(("quiet", b, "temp_c")), ".-", color=BCOL[b], label="board %s" % b)
    axs[0, 1].plot(hours, q(("quiet", b, "v5_rf")), ".-", color=BCOL[b], label="board %s" % b)
    axs[0, 2].plot(hours, 1e3 * (q(("quiet", b, "centre_q_v")) - 1.65), ".-", color=BCOL[b], label="board %s Q arm" % b)
    axs[0, 2].plot(hours, 1e3 * (q(("quiet", b, "centre_i_v")) - 1.65), ".--", color=BCOL[b], alpha=0.6, label="board %s I arm" % b)
frame(axs[0, 0], yl="C", t="each board's temperature (the NTC)")
frame(axs[0, 1], yl="V", t="each board's +5V_RF")
frame(axs[0, 2], yl="mV from 1.65 V", t="the arms' no-carrier centres (both boards quiet): Q solid, I dashed")
# row 1: the locks
for lk in ("AB", "BA"):
    axs[1, 0].plot(hours, q(("links", lk, "lock", "dsa")), ".-", color=LCOL[lk], label=LNAME[lk])
    axs[1, 1].plot(hours, 1e3 * q(("links", lk, "lock", "leg")), ".-", color=LCOL[lk], label=LNAME[lk] + " at setup")
    axs[1, 1].plot(hours, q(("links", lk, "scope", "leg_mv")), ".:", color=LCOL[lk], alpha=0.6, label=LNAME[lk] + " at the scope step")
    axs[1, 2].plot(hours, q(("links", lk, "lock", "vc_lock")), ".-", color=LCOL[lk], label=LNAME[lk])
frame(axs[1, 0], yl="dB", t="the DSA linkd's search chose for a 150 mV leg")
frame(axs[1, 1], yl="mV", t="the leg")
frame(axs[1, 2], yl="V", t="VC at lock (the VCXO against the far board's reference)")
# row 2: the decoder and the PRBS
for lk in ("AB", "BA"):
    axs[2, 0].plot(hours, 100 * q(("links", lk, "A3", "right_frac_min")), ".-", color=LCOL[lk], label=LNAME[lk] + " A3")
    axs[2, 0].plot(hours, 100 * q(("links", lk, "B1", "right_frac_min")), ".--", color=LCOL[lk], alpha=0.6, label=LNAME[lk] + " B1")
    axs[2, 1].plot(hours, q(("links", lk, "A3", "idle_false_per_s"), 0), ".-", color=LCOL[lk], label=LNAME[lk] + " A3")
    axs[2, 1].plot(hours, q(("links", lk, "B1", "idle_false_per_s"), 0), ".--", color=LCOL[lk], alpha=0.6, label=LNAME[lk] + " B1")
    for per, ls in ((20, "-"), (50, "--")):
        bits = np.nancumsum(q(("links", lk, "prbs%d" % per, "bits"), 0))
        mis = np.nancumsum(q(("links", lk, "prbs%d" % per, "mismatches"), 0))
        axs[2, 2].plot(hours, bits / 1e9, "." + ls, color=LCOL[lk], alpha=1 if per == 20 else 0.6, label="%s P%d: %.2f G bits, %d mismatches" % (LNAME[lk], per, bits[-1] / 1e9 if len(bits) else 0, mis[-1] if len(mis) else 0))
frame(axs[2, 0], yl="%", t="the worst message's right fraction: A3 solid, B1 dashed")
axs[2, 0].set_ylim(-5, 105)
frame(axs[2, 1], yl="events a second", t="false events at the idle")
axs[2, 1].set_yscale("symlog")
frame(axs[2, 2], yl="G bits (cumulative)", t="the PRBS bpsk: bits checked (the legend has the mismatches)")
# row 3: the scope
for lk in ("AB", "BA"):
    fq = q(("links", lk, "scope", "-1,0", "q_plateau")) / q(("links", lk, "scope", "leg_mv"))
    axs[3, 0].plot(hours, fq, ".-", color=LCOL[lk], label=LNAME[lk] + " the flip")
    cq = q(("links", lk, "scope", "-1,1", "q_plateau")) / q(("links", lk, "scope", "leg_mv"))
    axs[3, 0].plot(hours, cq - 1, ".--", color=LCOL[lk], alpha=0.6, label=LNAME[lk] + " the (-1,1) corner's Q less 1")
    axs[3, 1].plot(hours, q(("links", lk, "scope", "-1,0", "latency_ns")), ".-", color=LCOL[lk], label=LNAME[lk])
    axs[3, 2].plot(hours, q(("links", lk, "scope", "-1,0", "i_rise")), ".-", color=LCOL[lk], label=LNAME[lk])
    pil = q(("links", lk, "B1", "pilot", "rho")) * q(("links", lk, "B1", "pilot", "a")) * 1e3
    axs[2, 0].plot(hours, pil, "x:", color=LCOL[lk], alpha=0.5, label=LNAME[lk] + " B1's pilot, mV")
frame(axs[3, 0], yl="fraction of the leg", t="the sender's quadrature term on the scope (the flip's Q / the leg; the corner's Q offset dashed)")
frame(axs[3, 1], yl="ns", t="the sender's mark to CMP I's edge")
frame(axs[3, 2], yl="ns", t="the I arm's 10-90 % rise on the flip")
for ax in axs.flat:
    ax.legend(fontsize=6.3, frameon=False)
n = len(cyc)
fig.suptitle("The overnight soak over the cables, %s: %d cycles every %g min, A -> B at %g MHz and B -> A at %g MHz, %s to %s" % (
    J["stamp"], n, J["every_min"], J["mhz"]["AB"], J["mhz"]["BA"], cyc[0]["when"] if cyc else "?", cyc[-1]["when"] if cyc else "?"), fontsize=12, fontweight="bold")
out = os.path.join(HERE, "plots", os.path.basename(base))
fig.savefig(out + ".png", dpi=72)
fig.savefig(out + ".pdf")
print(out)
