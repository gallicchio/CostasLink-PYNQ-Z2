#!/usr/bin/env python3
"""The prover's whole chain, on the board and off it (Jason, Prompt 27: docs/SYSTEM.md).

    python3 sim/system_budget.py        build/system_budget.json, docs/images/system_budget.png

The prover's turnaround in QPV-BB84^f: the verifiers' challenges arrive at the prover's receive antennas;
the prover combines them (f, an XOR or a small hash) into a basis, sets the Pockels cell, measures the
photon (which waits in a fibre coil until the cell has settled), and its answer (click A, click B, no
click; or "invalid") leaves its transmit antennas.  Each term is (low, high) in ns with its source:
"model" (sim/ and PLAN.md), a datasheet or manual, or "est" (an estimate to measure on the bench).
The air between the nodes is geometry, not the prover's time: it is listed apart, for scale.
"""
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
NS_M_COAX = 1e9 / (299792458.0 * 0.85)        # LMR-240/400-class coax, velocity factor 0.84-0.85: 3.9 ns/m
NS_M_FIBRE = 4.90
NS_M_AIR = 3.336

ON, OFF = "on the board", "off the board"
# name, where, {config: (low, high)}, source
TERMS = [
    ("RF receive: RX SMA to the challenge's bit in the FPGA", ON,
     {"A": (60, 70), "B": (20, 35), "C": (5, 8)},
     "model: A, rev A's registered A3 decoder (PLAN.md 19, row 0 less its TX); B, B2's first edge into one or two "
     "fabric clocks at 100 MHz, the slow path a veto, not a wait; C, rev B's LVDS comparators into a LUT (row 3)"),
    ("combine the verifiers' bits: f = XOR or a small hash", ON,
     {"A": (10, 10), "B": (10, 10), "C": (1, 2)}, "model: one clock at 100 MHz, or a LUT level"),
    ("the basis out to the BME driver: a 5 V buffer and 1 m of cable", OFF,
     {"A": (8, 13), "B": (8, 13), "C": (8, 13)},
     "SyzygyRadioBoard review 1: the Pockels path 1.4-9.5 ns on its board (SN74ACT04 x6, 15 ohm); 1 m of coax 3.9 ns"),
    ("BME PCD-dpp: trigger to the cell settled in its basis", OFF,
     {"A": (25, 55), "B": (25, 55), "C": (25, 55)},
     "manual: 4-7 ns edges, >= 3 V (4 V) into 50 ohm, 50 ns minimum On-to-Off; the trigger-to-output delay is not "
     "in it (est 15-40 ns); a Leysop RTP cell is a few pF (6 pF for the RTP-4-20) with little piezo ringing (est 3-10 ns to settle)"),
    ("the photon after the cell: PBS and fibre to the detector", OFF,
     {"A": (2.5, 10), "B": (2.5, 10), "C": (2.5, 10)}, "est: 0.5-2 m at 4.9 ns/m"),
    ("detector: photon to its output pulse", OFF,
     {"A": (20, 60), "B": (20, 60), "C": (10, 20)},
     "est: InGaAs SPAD modules (ID Qube, ID120) do not publish it (A, B); an SNSPD's own latency is ps, its amplifiers "
     "and ~2 m of coax out of the cryostat about 10-20 ns (C)"),
    ("the detector's cable to the prover's box", OFF,
     {"A": (4, 8), "B": (4, 8), "C": (4, 8)}, "1-2 m of coax"),
    ("detector pulse in to the answer on the TX ladder pins", ON,
     {"A": (15, 27), "B": (12, 20), "C": (5, 8)},
     "model: rev A's TRIG IN (1 k into a Schmitt buffer) on clock-capable pin 26, then one or two clocks; rev B a "
     "buffer and a LUT"),
    ("constant-time release: the detection window's width", ON,
     {"A": (1, 3), "B": (1, 3), "C": (1, 3)},
     "a click and a no-click leave at the same time after the window (the detector's jitter and the photon's timing)"),
    ("RF transmit: ladder, modulator, to the TX SMA (50 %)", ON,
     {"A": (3, 3.5), "B": (3, 3.5), "C": (1.2, 1.8)}, "model: sim/latency_roadmap.py (PYNQ's 200 ohm; a bare or LVDS pin)"),
    ("antenna cables at the prover, receive and transmit, 1 m each", OFF,
     {"A": (7.8, 7.8), "B": (7.8, 7.8), "C": (7.8, 7.8)},
     "3.9 ns/m each way; a box behind the antenna.  10 m each way would be 78 ns"),
]
CONFIGS = {"A": "rev A, the gateware as planned (the registered A3 decoder), InGaAs SPADs",
           "B": "rev A, a robust fast gateware path (first edge, slow-path veto), InGaAs SPADs",
           "C": "rev B on a Brain-1 (LVDS, combinational paths), SNSPDs"}


def main():
    res = {}
    for k, label in CONFIGS.items():
        lo = sum(t[2][k][0] for t in TERMS)
        hi = sum(t[2][k][1] for t in TERMS)
        on_lo = sum(t[2][k][0] for t in TERMS if t[1] == ON)
        on_hi = sum(t[2][k][1] for t in TERMS if t[1] == ON)
        rf_lo = TERMS[0][2][k][0] + TERMS[-2][2][k][0]
        rf_hi = TERMS[0][2][k][1] + TERMS[-2][2][k][1]
        res[k] = dict(label=label, total=(lo, hi), on_board=(on_lo, on_hi), rf_link=(rf_lo, rf_hi),
                      rf_share=tuple(sorted((rf_lo / lo, rf_hi / hi))), radius_m=(lo * 0.1499, hi * 0.1499))
        print("%s %-75s total %5.1f-%5.1f ns, on the board %5.1f-%5.1f, the RF link's own %4.1f-%4.1f (%2.0f-%2.0f %%), "
              "c t / 2 = %4.1f-%4.1f m" % (k, label, lo, hi, on_lo, on_hi, rf_lo, rf_hi, 100 * rf_lo / lo, 100 * rf_hi / hi,
                                          lo * 0.1499, hi * 0.1499))
    air = {d: d * NS_M_AIR for d in (30, 100, 300, 1000)}
    print("the air, for scale: " + ", ".join("%d m %.0f ns" % (d, t) for d, t in air.items()))
    json.dump(dict(terms=[dict(name=t[0], where=t[1], ns=t[2], source=t[3]) for t in TERMS], configs=res,
                   air_ns=air, coax_ns_per_m=NS_M_COAX), open(os.path.join(ROOT, "build", "system_budget.json"), "w"), indent=1)
    # the plot: one bar a configuration, each term's middle value, on-board terms blue, off-board grey/green
    fig, ax = plt.subplots(figsize=(10.5, 4.6))
    cols_on = ["#1f5fbf", "#4f86d8", "#7aa5e0", "#9fc0ea", "#c4d8f2"]
    cols_off = ["#8a8a8a", "#2a8a3a", "#a0a0a0", "#5aa86a", "#c0c0c0", "#b8dcb8"]
    keys = list(CONFIGS)[::-1]
    for yi, k in enumerate(keys):
        x = 0.0
        ion = ioff = 0
        for t in TERMS:
            w = sum(t[2][k]) / 2.0
            if t[1] == ON:
                c = cols_on[ion % len(cols_on)]; ion += 1
            else:
                c = cols_off[ioff % len(cols_off)]; ioff += 1
            ax.barh(yi, w, left=x, color=c, edgecolor="white", height=0.62)
            if w >= 9:
                short = {"RF receive": "RF RX", "combine": "f", "the basis": "to BME", "BME": "BME + cell",
                         "the photon": "optics", "detector:": "detector", "the detector's": "cable",
                         "detector pulse": "answer", "constant": "", "RF transmit": "", "antenna": "ant. cables"}
                lab = next((v for kk, v in short.items() if t[0].startswith(kk)), "")
                ax.text(x + w / 2, yi, lab, ha="center", va="center", fontsize=7, color="white" if t[1] == ON else "k")
            x += w
        r = res[k]
        sh = sorted(r["rf_share"])
        ax.text(x + 6, yi, "%.0f-%.0f ns\nthe RF link %.0f-%.0f %%" % (r["total"][0], r["total"][1], 100 * sh[0], 100 * sh[1]),
                va="center", fontsize=8)
    ax.set_yticks(range(len(keys)))
    ax.set_yticklabels([k + ": " + CONFIGS[k].replace(", ", ",\n", 1) for k in keys], fontsize=7.5)
    ax.set_xlim(0, 300)
    ax.set_xlabel("ns, the middle of each term's range (blue: on the board; grey and green: off it)")
    ax.set_title("The prover's turnaround: challenges in at its antennas, the answer out (air excluded: 3.34 ns/m)", fontsize=10)
    ax.grid(alpha=0.25, axis="x")
    fig.tight_layout()
    fig.savefig(os.path.join(ROOT, "docs", "images", "system_budget.png"), dpi=130)
    plt.close(fig)
    print("wrote build/system_budget.json, docs/images/system_budget.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
