#!/usr/bin/env python3
"""How low the latency could go, and what each step costs (Jason, Prompt 21: PLAN.md section 19).

    python3 sim/latency_roadmap.py      build/latency_roadmap.json, docs/images/latency_vs_cost.png

The figure of merit is the **prover's turnaround**: a challenge arrives at the RX SMA, is decided,
passes through the logic that computes the answer, and leaves the TX SMA (QPV bounds exactly this; the
verifier's own TX and RX delays are fixed and calibrated out).  Electronics only: add 3.34 ns per metre
of air.  Each step keeps everything before it and changes one more thing:

  rx_rf     RX SMA to the demodulator: LNA, DSA, gain blocks, lines (rev A 1.1 ns, sim/budget.py section 5)
  B_dem     the demodulator's baseband (one pole), B_arm the arm after it (one pole; None = none)
  cmp       comparator delay; link the comparator's edge to the logic (an RC to 50 %, or a pair)
  core      the logic: rev A's registered decoder at 100 MHz (an estimate: the ISERDES word, the
            4-sample decision delay and about five clocks of stages, gateware/README.md), or a
            combinational path, or a CML gate
  fpga_io   the FPGA's input and output buffers, 3 ns (with ~2 ns of routing and a LUT in `core`, a Zynq's
            or an ECP5's combinational pin-to-pin path is about 5 ns); 0 once the fast path leaves the FPGA
  tx_tau    the drive into the TX baseband node (the pin's RC, then the ladder's own node), B_mod the
            modulator's baseband, tx_rf the modulator to the TX SMA
The decision is the B2 scheme's (each message moves one window comparator, so the first edge is the
answer) from step 1 on; rev A's A3 waits its 4-sample decision delay.  The window sits at its CFAR
place (one false event an hour), and no decision can come sooner than the energy bound
t >= z^2 N0 / P (a sequential test at best: the received energy must clear the threshold).
"""
import json, math, os, sys
import numpy as np
from scipy.signal import lfilter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
B = json.load(open(os.path.join(ROOT, "build", "budget.json")))
OUT = os.path.join(ROOT, "docs", "images")
DT = 2e-12
T = np.arange(int(40e-9 / DT)) * DT
SNR = {"bench": B["link_rows"][1][4], "3 km": B["link_rows"][4][4]}     # dB in 100 MHz, the board alone (+9.8 dBm)
FA = 1.0 / 3600


def chain(x, taus):
    for tau in taus:
        k = 1.0 - math.exp(-DT / tau)
        x = lfilter([k], [1.0, -(1.0 - k)], x)
    return x


def t_at(g, level):
    i = int(np.argmax(g >= level))
    return T[i - 1] + (level - g[i - 1]) / (g[i] - g[i - 1]) * DT


def tau(MHz):
    return 1 / (2 * math.pi * MHz * 1e6)


#  step, latency label, what changes, delta $ (low, high) for a two-node link, parameters
STEPS = [
    ("0", "rev A as built", "PYNQ-Z2, header RCs, TLV3601, rev A gateware (A3, registered decoder at 100 MHz)",
     (0, 0), dict(rx_rf=1.1, B_dem=390, B_arm=94.4, cmp=2.5, link=1.62, core=59.4, fpga_io=3.0, tx_tau=[2.0, 0.72], B_mod=750, tx_rf=0.5)),
    ("1", "gateware fast path", "B2 scheme; comparator pins through one LUT level straight to the ladder pins, combinational (a TDC time-stamps alongside); no hardware change",
     (0, 0), dict(rx_rf=1.1, B_dem=390, B_arm=94.4, cmp=2.5, link=1.62, core=2.0, fpga_io=3.0, tx_tau=[2.0, 0.72], B_mod=750, tx_rf=0.5)),
    ("2", "bare-pin host", "Icepi Zero (or any host without series resistors): the 200 ohm RCs gone both ways",
     (-120, 0), dict(rx_rf=1.1, B_dem=390, B_arm=94.4, cmp=2.5, link=0.23, core=2.0, fpga_io=3.0, tx_tau=[0.3, 0.72], B_mod=750, tx_rf=0.5)),
    ("3", "LVDS comparators", "rev B on SYZYGY (Brain-1) or an on-board ECP5: TLV3604 (0.8 ns) over LVDS pairs",
     (1500, 2500), dict(rx_rf=1.1, B_dem=390, B_arm=94.4, cmp=0.8, link=0.15, core=2.0, fpga_io=3.0, tx_tau=[0.3, 0.72], B_mod=750, tx_rf=0.5)),
    ("4", "fast path out of the FPGA", "SiGe comparators (ADCMP572, 150 ps, CML) into a CML gate that drives the modulator's baseband; the FPGA only arms, configures and time-stamps; the DSA leaves the fast path",
     (1000, 2000), dict(rx_rf=0.8, B_dem=390, B_arm=94.4, cmp=0.15, link=0.05, core=0.25, fpga_io=0.0, tx_tau=[0.05, 0.1], B_mod=750, tx_rf=0.4)),
    ("5", "1 GHz baseband", "a wideband I/Q demodulator (a passive I/Q mixer and a GHz FDA) and arm, a wideband modulator: about 2 GHz on the air, which 5.8 GHz's ISM and amateur bands do not have (a shielded lab or an experimental licence); the PA at range",
     (2000, 5000), dict(rx_rf=0.6, B_dem=2000, B_arm=1000, cmp=0.15, link=0.05, core=0.25, fpga_io=0.0, tx_tau=[0.05, 0.1], B_mod=1500, tx_rf=0.3)),
    ("6", "60 GHz", "57-64 GHz unlicensed (2 GHz channels): ADI's HMC6300 / HMC6301 with 1.8 GHz of I/Q baseband, InP comparators (HMC674, 85 ps), a Rogers board, horns; oxygen (15 dB/km) limits it to hundreds of metres",
     (15000, 30000), dict(rx_rf=0.4, B_dem=900, B_arm=None, cmp=0.085, link=0.05, core=0.15, fpga_io=0.0, tx_tau=[0.05, 0.05], B_mod=900, tx_rf=0.3)),
]
BASE_TOTAL = (1200, 1400)    # rev A for a two-node link: JLCPCB's order for 2 assembled, the consigned chips, 2 PYNQ-Z2 (~$129)


def run(p, snr_dB):
    rx = [tau(p["B_dem"])] + ([tau(p["B_arm"])] if p["B_arm"] else [])
    step = (T >= 1e-9).astype(float)
    g = chain(step, rx)
    imp = np.zeros(int(20e-9 / DT)); imp[0] = 1.0
    h = chain(imp, rx)
    enbw = float(np.sum(h ** 2)) / (2 * DT)
    f = np.fft.rfftfreq(len(h), DT); hf = np.abs(np.fft.rfft(h))
    nu0 = math.sqrt(np.sum(f ** 2 * hf ** 2) / np.sum(hf ** 2))
    z = math.sqrt(2 * math.log(2 * nu0 / FA))
    p_over_n0 = 10 ** (snr_dB / 10) * 100e6              # the carrier over N0, Hz
    th = z * math.sqrt(enbw / p_over_n0)                  # the window, in units of a
    t_energy = z ** 2 / p_over_n0
    if th >= 0.9:
        return None
    t_rise = t_at(g, th) - 1e-9                           # the receive filter's own rise to the window
    # the transmitting end's rise at the far board (it shapes the edge the receiver sees): one-way, not in the turnaround
    tx = chain(step, [x * 1e-9 for x in p["tx_tau"]] + [tau(p["B_mod"])])
    t_tx50 = t_at(tx, 0.5) - 1e-9
    decide = max(t_rise, t_energy)
    turnaround = (p["rx_rf"] + p["cmp"] + p["link"] + p["core"] + p["fpga_io"] + p["tx_rf"]) * 1e-9 + decide + t_tx50
    return dict(window=th, z=z, rise_ns=t_rise * 1e9, energy_ns=t_energy * 1e9, decide_ns=decide * 1e9,
                tx50_ns=t_tx50 * 1e9, turnaround_ns=turnaround * 1e9)


def main():
    rows = []
    lo, hi = BASE_TOTAL
    for key, name, what, (dlo, dhi), p in STEPS:
        lo, hi = lo + dlo, hi + dhi
        r = dict(step=key, name=name, what=what, delta=(dlo, dhi), total=(lo, hi), params=p)
        for case, snr in SNR.items():
            r[case] = run(p, snr)
            r[case + "_PA"] = run(p, snr + 20.0)            # the 2 W module at +30 dBm: 20 dB more
        rows.append(r)
        b, k, kp = r["bench"], r["3 km"], r["3 km_PA"]
        print("%s %-26s bench %6.2f ns (decide %5.2f: rise %5.2f, energy %5.3f)  3 km %s  3 km + PA %6.2f   $%d-%d (total $%d-%d)"
              % (key, name, b["turnaround_ns"], b["decide_ns"], b["rise_ns"], b["energy_ns"],
                 ("%6.2f" % k["turnaround_ns"]) if k else "  n/a ", kp["turnaround_ns"], dlo, dhi, lo, hi))
    # the energy bound alone, for the text
    for case, snr in SNR.items():
        for pa in (0, 20):
            pn = 10 ** ((snr + pa) / 10) * 100e6
            print("energy bound, %s%s: z = 7.5 -> %.3f ns" % (case, " + PA" if pa else "", 7.5 ** 2 / pn * 1e9))
    json.dump(rows, open(os.path.join(ROOT, "build", "latency_roadmap.json"), "w"), indent=1, default=float)
    # the latency against the money
    fig, ax = plt.subplots(figsize=(8.0, 5.4))
    xs = [math.sqrt(r["total"][0] * r["total"][1]) for r in rows]
    yb = [r["bench"]["turnaround_ns"] for r in rows]
    yk = [r["3 km_PA"]["turnaround_ns"] for r in rows if r["step"] != "6"]      # 60 GHz: oxygen, 15 dB/km
    ax.plot(xs, yb, "o-", color="#1f5fbf", label="the bench (10 m, whips)")
    ax.plot(xs[:len(yk)], yk, "s--", color="#c8401a", label="3 km (panels, 10 m cables, the PA at +30 dBm)")
    ax.plot([math.sqrt(70e3 * 140e3)], [0.3], "o", mfc="none", mec="#1f5fbf", ms=8)
    ax.errorbar([math.sqrt(70e3 * 140e3)], [0.3], xerr=[[math.sqrt(70e3 * 140e3) - 70e3], [140e3 - math.sqrt(70e3 * 140e3)]],
                yerr=[[0.1], [0.2]], fmt="none", ecolor="#1f5fbf", alpha=0.4, lw=1)
    ax.annotate("7: optical (estimated, not modelled)", (math.sqrt(70e3 * 140e3), 0.3), xytext=(-150, 8),
                textcoords="offset points", fontsize=7.5)
    for r, x, y in zip(rows, xs, yb):
        ax.annotate("%s: %s" % (r["step"], r["name"]), (x, y), xytext=(6, 4), textcoords="offset points", fontsize=7.5)
    ax.errorbar(xs, yb, xerr=[[x - r["total"][0] for x, r in zip(xs, rows)], [r["total"][1] - x for x, r in zip(xs, rows)]],
                fmt="none", ecolor="#1f5fbf", alpha=0.4, lw=1)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("a two-node link's hardware, $ (log; rough, see PLAN.md section 19)")
    ax.set_ylabel("the prover's turnaround, RX SMA to TX SMA, ns (log)")
    ax.set_title("Latency against money: each step keeps the ones before it", fontsize=10)
    ax.grid(alpha=0.25, which="both")
    ax.legend(fontsize=8)
    fig.savefig(os.path.join(OUT, "latency_vs_cost.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("wrote build/latency_roadmap.json, docs/images/latency_vs_cost.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
