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


#  step, latency label, what changes, parameters
STEPS = [
    ("0", "rev A as built", "PYNQ-Z2, header RCs, TLV3601, rev A gateware (A3, registered decoder at 100 MHz)",
     dict(rx_rf=1.1, B_dem=390, B_arm=94.4, cmp=2.5, link=1.62, core=59.4, fpga_io=3.0, tx_tau=[2.0, 0.72], B_mod=750, tx_rf=0.5)),
    ("1", "gateware fast path", "B2 scheme; comparator pins through one LUT level straight to the ladder pins, combinational (a TDC time-stamps alongside); no hardware change",
     dict(rx_rf=1.1, B_dem=390, B_arm=94.4, cmp=2.5, link=1.62, core=2.0, fpga_io=3.0, tx_tau=[2.0, 0.72], B_mod=750, tx_rf=0.5)),
    ("2", "bare-pin host", "Icepi Zero (or any host without series resistors): the 200 ohm RCs gone both ways",
     dict(rx_rf=1.1, B_dem=390, B_arm=94.4, cmp=2.5, link=0.23, core=2.0, fpga_io=3.0, tx_tau=[0.3, 0.72], B_mod=750, tx_rf=0.5)),
    ("3", "LVDS comparators", "rev B with an ECP5 on the board (or on SYZYGY, the Brain-1): TLV3604 (0.8 ns) over LVDS pairs",
     dict(rx_rf=1.1, B_dem=390, B_arm=94.4, cmp=0.8, link=0.15, core=2.0, fpga_io=3.0, tx_tau=[0.3, 0.72], B_mod=750, tx_rf=0.5)),
    ("4", "fast path out of the FPGA", "SiGe comparators (ADCMP572, 165 ps, CML) into a CML gate that drives the modulator's baseband; the FPGA only arms, configures and time-stamps; the DSA leaves the fast path",
     dict(rx_rf=0.8, B_dem=390, B_arm=94.4, cmp=0.165, link=0.05, core=0.25, fpga_io=0.0, tx_tau=[0.05, 0.1], B_mod=750, tx_rf=0.4)),
    ("5", "1 GHz baseband", "passive I/Q mixers (IF to GHz) and GHz FDAs for the ADL5380 and ADL5375: about 2 GHz on the air, which 5.8 GHz's ISM and amateur bands do not have (a shielded lab or an experimental licence); the PA at range",
     dict(rx_rf=0.6, B_dem=2000, B_arm=1000, cmp=0.165, link=0.05, core=0.25, fpga_io=0.0, tx_tau=[0.05, 0.1], B_mod=1500, tx_rf=0.3)),
    ("6", "60 GHz", "57-64 GHz unlicensed (2 GHz channels): ADI's HMC6300 / HMC6301 with 1.8 GHz of I/Q baseband, InP comparators (HMC674, 85 ps), a Rogers board, horns; oxygen (15 dB/km) limits it to hundreds of metres",
     dict(rx_rf=0.4, B_dem=900, B_arm=None, cmp=0.085, link=0.05, core=0.15, fpga_io=0.0, tx_tau=[0.05, 0.05], B_mod=900, tx_rf=0.3)),
]

# What each row's two-node link costs to build directly, line by line (antennas, amplifiers and bench kit
# excluded, except antennas a row needs that rev A's cannot be).  Prices Jason gave from Digi-Key on
# 2026-10-12 are exact (1-9 pieces); the rest are estimates, marked "est".  Each row's delta is its total
# less the row before; walking the steps one by one also pays a board order (~$1k) at every re-spin.
REV_A = ("two rev A boards, assembled: JLCPCB $777-792, the consigned chips $150, shipping them $35-60 (section 17)", 962, 1002)
REV_B = ("two rev B boards: rev A's, the TLV3601 swapped for 8 TLV3604 (est +$2-4 each, with duty)", 962 + 20, 1002 + 45)
ECP5 = ("an ECP5 on each board: LFE5U-25F, flash, oscillator, USB-JTAG, regulators, their assembly lines and duty (est)", 150, 300)
CML = [("8 ADCMP572 at $30.18 (Digi-Key) for the 8 TLV3604", 210, 225),
       ("CML logic: the answer gate and a fan-out to the FPGA's TDC, about 4 gates a board at $15-60 (est)", 120, 480),
       ("their assembly lines and duty (est)", 100, 250)]
WIDE = [("4 passive I/Q mixers (HMC525-class, IF to 3.5 GHz) for the ADL5380 and ADL5375-05, less the $64 of consigned chips (est)", 140, 260),
        ("GHz FDAs (LMH5401-class), 4 a board (est)", 120, 200),
        ("LO amplifiers for the passive mixers (est)", 40, 100),
        ("4 antennas for 4.8-6.8 GHz, Vivaldi or horn (est)", 120, 600),
        ("their assembly lines and duty (est)", 100, 200),
        ("an FCC Part 5 experimental licence (est)", 0, 100)]
V60 = [("2 HMC6300 + 2 HMC6301 at $25.91 (Digi-Key)", 104, 104),
       ("a 60 GHz board: a Rogers or hybrid stack, eWLB BGA assembly at a prototype house (est); ADI's evaluation PCBs instead are $1,587.52 each, $6,350 for four", 2000, 6350),
       ("4 WR-15 horns and transitions, if the boards need them (est)", 1200, 2400),
       ("8 InP comparators (HMC674-class) for the ADCMP572 (est)", 560, 1360),
       ("less the 5.8 GHz chain: mixers, LO, LNA, DSA, gain blocks, antennas (est)", -900, -300)]
COSTS = {
    "0": [REV_A, ("two PYNQ-Z2", 258, 258)],
    "1": [REV_A, ("two PYNQ-Z2", 258, 258)],
    "2": [REV_A, ("two Icepi Zero (est $69-129 each)", 138, 258)],
    "3": [REV_B, ECP5],
    "4": [REV_B, ECP5] + CML,
    "5": [REV_B, ECP5] + CML + WIDE,
    "6": [REV_B, ECP5] + CML + WIDE + V60,
}
ALT = {"3": ("two Brain-1 at $450 and a SYZYGY connector with its DNA chip a board, instead of the ECP5", 920 - 150, 950 - 300)}
OPTICAL = (26e3, 80e3)       # row 7, estimated: a node is a laser and its controller, a 20-40 GHz modulator and its
                             # driver, a photoreceiver, an EDFA, free-space optics, an InP / SiGe gate: $11-33k


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
    plo, phi = None, None
    for key, name, what, p in STEPS:
        lo, hi = sum(c[1] for c in COSTS[key]), sum(c[2] for c in COSTS[key])
        dlo, dhi = (lo - plo, hi - phi) if plo is not None else (0, 0)
        plo, phi = lo, hi
        r = dict(step=key, name=name, what=what, delta=(dlo, dhi), total=(lo, hi), costs=COSTS[key], params=p)
        if key in ALT:
            r["alternative"] = dict(item=ALT[key][0], total=(lo + ALT[key][1], hi + ALT[key][2]))
        for case, snr in SNR.items():
            r[case] = run(p, snr)
            r[case + "_PA"] = run(p, snr + 20.0)            # the 2 W module at +30 dBm: 20 dB more
        rows.append(r)
        b, k, kp = r["bench"], r["3 km"], r["3 km_PA"]
        print("%s %-26s bench %6.2f ns (decide %5.2f: rise %5.2f, energy %5.3f)  3 km %s  3 km + PA %6.2f   %+d to %+d (total $%d-%d)"
              % (key, name, b["turnaround_ns"], b["decide_ns"], b["rise_ns"], b["energy_ns"],
                 ("%6.2f" % k["turnaround_ns"]) if k else "  n/a ", kp["turnaround_ns"], dlo, dhi, lo, hi))
    # the energy bound alone, for the text
    for case, snr in SNR.items():
        for pa in (0, 20):
            pn = 10 ** ((snr + pa) / 10) * 100e6
            print("energy bound, %s%s: z = 7.5 -> %.3f ns" % (case, " + PA" if pa else "", 7.5 ** 2 / pn * 1e9))
    for r in rows:
        print("%s total $%d-%d, delta $%+d to %+d%s" % (r["step"], r["total"][0], r["total"][1], r["delta"][0], r["delta"][1],
              ("   (alternative: $%d-%d)" % r["alternative"]["total"]) if "alternative" in r else ""))
    json.dump(rows, open(os.path.join(ROOT, "build", "latency_roadmap.json"), "w"), indent=1, default=float)
    # the latency against the money
    fig, ax = plt.subplots(figsize=(8.0, 5.4))
    xs = [math.sqrt(r["total"][0] * r["total"][1]) for r in rows]
    yb = [r["bench"]["turnaround_ns"] for r in rows]
    yk = [r["3 km_PA"]["turnaround_ns"] for r in rows if r["step"] != "6"]      # 60 GHz: oxygen, 15 dB/km
    ax.plot(xs, yb, "o-", color="#1f5fbf", label="the bench (10 m, whips)")
    ax.plot(xs[:len(yk)], yk, "s--", color="#c8401a", label="3 km (panels, 10 m cables, the PA at +30 dBm)")
    xo = math.sqrt(OPTICAL[0] * OPTICAL[1])
    ax.plot([xo], [0.3], "o", mfc="none", mec="#1f5fbf", ms=8)
    ax.errorbar([xo], [0.3], xerr=[[xo - OPTICAL[0]], [OPTICAL[1] - xo]],
                yerr=[[0.1], [0.2]], fmt="none", ecolor="#1f5fbf", alpha=0.4, lw=1)
    ax.annotate("7: optical (estimated, not modelled)", (xo, 0.3), xytext=(-150, 8),
                textcoords="offset points", fontsize=7.5)
    for r, x, y in zip(rows, xs, yb):
        ax.annotate("%s: %s" % (r["step"], r["name"]), (x, y), xytext=(6, 4), textcoords="offset points", fontsize=7.5)
    ax.errorbar(xs, yb, xerr=[[x - r["total"][0] for x, r in zip(xs, rows)], [r["total"][1] - x for x, r in zip(xs, rows)]],
                fmt="none", ecolor="#1f5fbf", alpha=0.4, lw=1)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("a two-node link's hardware, $ (log; line items in PLAN.md section 19)")
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
