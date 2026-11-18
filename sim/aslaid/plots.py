#!/usr/bin/env python3
"""The as-laid simulation's charts (bringup/plotstyle.py's look), from out/*.json.

    python3 sim/aslaid/plots.py
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "bringup"))
import plotstyle as P
import matplotlib.pyplot as plt

OUT = os.path.join(HERE, "out")
S = P.SERIES


def load(n):
    return json.load(open(os.path.join(OUT, n)))


def rx():
    r = load("rx.json")
    f = r["f"]
    m = r["measured"]
    P.setup()
    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.plot(f, r["reference"]["rxmon"], color=S[2], ls="--", label="the vendors' circuits at the pins (no layout)")
    ax.plot(f, r["c102_lifted"]["rxmon"], color=S[3], ls="--", label="as laid, C102 lifted (the prediction)")
    ax.plot(f, r["aslaid"]["rxmon"], color=S[4], lw=1.5, label="as laid, parasitics as extracted")
    ax.plot(f, r["aslaid_fit"]["rxmon"], color=S[1], label="as laid, C102's ground +0.45 nH (fitted)")
    fm = [x for x, y in zip(m["f"], m["rxmon"]) if x <= 5.85]
    ym = [y for x, y in zip(m["f"], m["rxmon"]) if x <= 5.85]
    ax.plot(fm, ym, color=S[0], marker="o", ms=4, lw=1.5, label="board A (the night's maps, the part that follows the DSA)")
    ax.axvspan(5.86, 7.0, color=P.GRID, alpha=0.5, lw=0)
    ax.text(5.9, 24, "above 5.86 GHz the bench\nreads the leak, not the chain", fontsize=8.5, color=P.INK2, va="top")
    ax.set_xlim(3.0, 7.0)
    ax.set_ylim(-30, 32)
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("RX ANT to RX MON (dB)")
    ax.set_title("The receive chain as laid out: C102's branch shorts the LNA's input near 5.9 GHz", pad=36)
    P.subtitle(ax, "Circuit model from the board file (lines, junctions, pads, vias, parts' parasitics) with the datasheets' ICs.  The DSA at 0 dB.\n"
                   "One parameter fitted: C102's ground return (0.14 nH extracted; 0.59 nH fits).  Lifting C102 is predicted to give back about 25 dB at 5.8 GHz.")
    ax.legend(loc="lower left", fontsize=8.5)
    P.source(fig, "sim/aslaid/paths.py rx; bringup/data/board_A/overnight/map_20261029_163008.json, mapfine_20261029_173239.json")
    P.save(fig, os.path.join(OUT, "rx_chain.png"))
    # S11 at RX ANT: the Monday VNA test
    fig, ax = plt.subplots(figsize=(10, 4.8))
    ax.plot(f, r["aslaid_fit"]["s11"], color=S[1], label="as laid (fitted): what the VNA should read on RX ANT, the board powered")
    ax.plot(f, r["c102_lifted"]["s11"], color=S[3], ls="--", label="C102 lifted")
    ax.plot(f, r["reference"]["s11"], color=S[2], ls="--", label="the vendors' circuits at the pins")
    ax.set_xlim(3.0, 7.0)
    ax.set_ylim(-25, 1)
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("S11 at RX ANT (dB)")
    ax.set_title("RX ANT's return loss tells the C102 short from the rest without touching a part", pad=26)
    P.subtitle(ax, "The model's prediction for the 8720ES on RX ANT: nearly all reflected from 5.5 to 6.1 GHz while C102 is fitted.")
    ax.legend(loc="lower left", fontsize=8.5)
    P.source(fig, "sim/aslaid/paths.py rx (the LNA's input as R + jwL matched by 0.5 pF at 5.4 GHz: an assumption)")
    P.save(fig, os.path.join(OUT, "rx_ant_s11.png"))


def tx():
    r = load("tx.json")
    f = r["f"]
    off = r["offset_db"]
    pm = r["pmod_av"]
    P.setup()
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(f, [a + b + off for a, b in zip(pm, r["reference"]["ant"])], color=S[2], ls="--", label="the vendors' circuits at the pins")
    ax.plot(f, [a + b + off for a, b in zip(pm, r["aslaid"]["ant"])], color=S[1], label="as laid")
    ax.plot(f, [a + b + off for a, b in zip(pm, r["no_padcap"]["ant"])], color=S[3], lw=1.5, ls=":", label="as laid, no pad capacitance")
    ax.plot(r["measured"]["f"], r["measured"]["ant"], color=S[0], marker="o", ms=4, lw=1.5, label="board A, TX ANT")
    ax.set_xlim(3.0, 6.1)
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("TX ANT (dBm)")
    ax.set_title("The transmit chain falls as its parts do: the layout costs about 1-2 dB at 5.8 GHz", pad=36)
    P.subtitle(ax, "ADL5375 POUT (Table 1, 1 V p-p) + the chain's gain; one offset fitted at 3.5 GHz (%.1f dB: the board's drive against 1 V p-p).\n"
                   "The model's ripple rests on the modulator's assumed output phase; the trend does not." % off)
    ax.legend(loc="lower left", fontsize=8.5)
    P.source(fig, "sim/aslaid/paths.py tx")
    P.save(fig, os.path.join(OUT, "tx_chain.png"))


def lo():
    r = load("lo.json")
    f = [3.0 + 0.02 * i for i in range(len(r["lo_tx_mon"]["p_dbm"]))]
    P.setup()
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.plot(f, r["lo_tx_mon"]["ref_dbm"], color=S[2], ls="--", label="the datasheet's network at the pin (-1 dBm at 3 GHz)")
    ax.plot(f, r["lo_tx_mon"]["p_dbm"], color=S[1], label="LO TX MON as laid (J204: 115.6 mm)")
    ax.plot(f, r["lo_rx_mon"]["p_dbm"], color=S[4], label="LO RX MON as laid (J109: 9.5 mm)")
    mt = {3.0: -3.4, 3.5: -2.8, 4.0: -13.7, 5.0: -16.7, 5.7: -21.0, 5.8: -26.7, 6.0: -25.4}
    ax.plot(list(mt), list(mt.values()), color=S[0], marker="o", ms=5, lw=1.5, label="board A, LO TX MON")
    ax.plot([5.8], [-8.7], color=S[5], marker="s", ms=7, ls="", label="board A, LO RX MON")
    ax.set_xlim(3.0, 7.0)
    ax.set_ylim(-35, 8)
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("at the U.FL (dBm)")
    ax.set_title("LO RX MON is explained; LO TX MON's long route loses 10-15 dB more than its model", pad=36)
    P.subtitle(ax, "MAX2871 RFOUTB as a current source (0.6 pF, assumed), calibrated to -1 dBm with Note 4's 27 nH and 50 ohm at 3 GHz.\n"
                   "Both pull-ups (27 nH, self-resonant near 3 GHz) hang on long branches with vias; the TX tap's line itself models at 4 dB.")
    ax.legend(loc="lower left", fontsize=8.5)
    P.source(fig, "sim/aslaid/paths.py lo; REVB rows 4 and 5")
    P.save(fig, os.path.join(OUT, "lo_mon.png"))


def leak():
    r = load("pdn.json")["leak"]
    f = [q["f"] for q in r]
    meas = {5.0: -53, 5.3: -53.4, 5.5: -53.1, 5.6: -57.2, 5.7: -73.4, 5.8: -69.2, 5.85: -61.2, 5.9: -51.2, 5.95: -47.3, 6.0: -45.7}
    P.setup()
    fig, ax = plt.subplots(figsize=(10, 5.0))
    ax.plot(f, [q["p_rxmon"] for q in r], color=S[1], label="model: TX gain block -> its choke -> +5V_RF -> the RX chokes -> the line")
    ax.plot(list(meas), list(meas.values()), color=S[0], marker="o", ms=5, lw=1.5, label="board A: RX MON at DSA 31.75 dB (the leak)")
    ax.set_xlim(4.0, 7.0)
    ax.set_ylim(-100, -35)
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("RX MON (dBm)")
    ax.set_title("The shared +5V_RF plane is not where the leak comes from: it models 20-40 dB too weak", pad=36)
    P.subtitle(ax, "+5V_RF meshed at 0.5 mm between In1 and the B.Cu ground pour 0.21 mm under it: |Z21| about 1 ohm between the chokes' vias.\n"
                   "The plane is a low-impedance cavity; the bench's leak must come another way (the cable and jacks, or the top pour).")
    ax.legend(loc="lower left", fontsize=8.5)
    P.source(fig, "sim/aslaid/pdn.py")
    P.save(fig, os.path.join(OUT, "leak.png"))


if __name__ == "__main__":
    rx()
    tx()
    lo()
    leak()
    print("plots in", OUT)
