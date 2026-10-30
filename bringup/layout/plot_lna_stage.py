#!/usr/bin/env python3
"""Board A's LNA stage, measured against the input network's model (bring-up, 2026-10-29).

    python3 bringup/layout/plot_lna_stage.py [map json]       default the night's coarse map

The measured line is what the receive chain leaves for the LNA stage (U101 and its parts, RX ANT's launch to C104)
once the parts after it are taken at their datasheet values: the chain's gain (RX MON at the lowest DSA setting, plus
that setting and the coupler's 20.95 dB scaled by sin(theta) for its quarter wave at 5.8 GHz, less RX ANT's level)
minus two ADL5611s (Table 2 S21), 1.5 dB of DSA and 1.4 dB of DC blocks and launch.  Above 5.85 GHz the chain is under
the leak that does not follow the DSA (REVB 10), so the line stops there.  The model lines are 13 dB (the datasheet's
typical gain) plus lna_input_model.py's input network: as laid out, and with C102 lifted.
"""
import glob, json, math, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import plotstyle as P
import lna_input_model as M
import matplotlib.pyplot as plt

DATA = os.path.join(os.path.dirname(HERE), "data", "board_A")
# ADL5611 S21 (dB), its datasheet's Table 2, every 100 MHz over the range used here
ADL5611 = {3000: 20.38, 3100: 20.411, 3200: 20.422, 3300: 20.411, 3400: 20.419, 3500: 20.412, 3600: 20.385, 3700: 20.334,
           3800: 20.321, 3900: 20.283, 4000: 20.107, 4100: 19.93, 4200: 19.528, 4300: 18.987, 4400: 18.248, 4500: 17.627,
           4600: 17.415, 4700: 17.3, 4800: 17.18, 4900: 16.938, 5000: 16.723, 5100: 16.407, 5200: 16.142, 5300: 15.797,
           5400: 15.601, 5500: 15.423, 5600: 15.212, 5700: 15.016, 5800: 14.811, 5900: 14.64, 6000: 14.474}


def s21(f):
    ks = sorted(ADL5611)
    lo = max(k for k in ks if k <= f)
    hi = min(k for k in ks if k >= f)
    return ADL5611[lo] if lo == hi else ADL5611[lo] + (ADL5611[hi] - ADL5611[lo]) * (f - lo) / (hi - lo)


def main(argv):
    path = argv[1] if len(argv) > 1 else sorted(glob.glob(os.path.join(DATA, "overnight", "map_2*.json")))[0]
    rows = json.load(open(path))
    fm, gm = [], []
    for r in rows:
        f = r["mhz"]
        if f > 5850:
            continue
        p = min(r["points"], key=lambda q: q["dsa"])
        th = math.radians(90.0 * f / 5800)
        chain = p["rx_mon"] + p["dsa"] + 20.95 - 20 * math.log10(math.sin(th)) - (r["tx_ant_dbm"] - 40)
        fm.append(f / 1000)
        gm.append(chain - (2 * s21(f) - 2.9))
    fs = [3.0 + 0.02 * i for i in range(151)]
    P.setup()
    fig, ax = plt.subplots(figsize=(9.5, 5.4))
    ax.axhspan(11, 16, color=P.GRID, alpha=0.6, lw=0)
    ax.text(3.02, 15.4, "datasheet gain, 4.9-5.9 GHz: 11-16 dB", fontsize=8.5, color=P.INK2, va="top")
    ax.plot(fs, [13 + M.gain(f * 1e9, "C102 removed") for f in fs], color=P.SERIES[2], lw=2, ls="--", label="model: C102 lifted")
    ax.plot(fs, [13 + M.gain(f * 1e9, "as laid") for f in fs], color=P.SERIES[1], lw=2, label="model: the input network as laid out (13 dB LNA behind it)")
    ax.plot(fm, gm, color=P.SERIES[0], lw=2, marker="o", ms=4.5, label="measured: what the chain leaves for the LNA stage")
    ax.set_xlim(3.0, 6.0)
    ax.set_ylim(-30, 20)
    ax.set_xlabel("frequency (GHz)")
    ax.set_ylabel("LNA stage gain (dB)")
    ax.set_title("The LNA stage falls 28 dB from 4.4 to 5.8 GHz; C102's resonance gives the trend, not all of it", pad=38)
    P.subtitle(ax, "RX ANT to C104.  Measured: the chain's gain less two ADL5611s (datasheet), the DSA, DC blocks.  Model: lossless lines, an ideal LNA input;\n"
                    "C102's ground 0.5 nH puts its null at 5.9 GHz (0.2 nH: 6.5 GHz; 1.0 nH: 5.0 GHz).")
    ax.legend(loc="lower left")
    P.source(fig, "bringup/layout/plot_lna_stage.py; %s; bringup/layout/lna_input_model.py (C102's ground 0.5 nH, ESL 0.3 nH)" % os.path.relpath(path, os.path.dirname(HERE)))
    out = os.path.join(DATA, "plots", "rx_lna_stage_model.png")
    print(P.save(fig, out))


if __name__ == "__main__":
    main(sys.argv)
