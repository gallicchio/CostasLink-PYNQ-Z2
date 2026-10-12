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
    ("6E", "E-band, instead of 60 GHz", "71-76 GHz (light-licensed in the US): ADI's ADMV7310 upconverter and ADMV7410 downconverter, I/Q to 2 GHz, 25 dBm out, 5 dB noise figure; InP comparators; 43 dBi dishes (the FCC's minimum); oxygen 0.3-0.4 dB/km, so kilometres; heavy rain is the limit",
     dict(rx_rf=0.4, B_dem=2000, B_arm=None, cmp=0.085, link=0.05, core=0.15, fpga_io=0.0, tx_tau=[0.05, 0.05], B_mod=2000, tx_rf=0.4,
          snr=None)),
]


def eband_snr(L, G_dBi, rain_dB_km=0.0):
    """SNR in 100 MHz: +20 dBm (5 dB under the ADMV7310's P1dB), two antennas, free space, oxygen and water
    vapour 0.7 dB/km (est), the ADMV7410's 5 dB noise figure and 2 dB of waveguide"""
    lam = 299792458.0 / 73.5e9
    fspl = 20 * math.log10(4 * math.pi * L / lam)
    p_rx = 20 + 2 * G_dBi - fspl - (0.7 + rain_dB_km) * L / 1000
    return p_rx - (-174 + 80 + 5 + 2)


STEPS[-1][3]["snr"] = {"bench": eband_snr(10, 24), "3 km": eband_snr(3000, 43)}

# What each row's two-node link costs to build directly, line by line (antennas, amplifiers and bench kit
# excluded, except antennas a row needs that rev A's cannot be).  Prices Jason gave from Digi-Key on
# 2026-10-12 are exact (1-9 pieces); the rest are estimates, marked "est".  Each row's delta is its total
# less the row before; walking the steps one by one also pays a board order (~$1k) at every re-spin.
# rev A's order from mfg/cost_estimate.py's last run (build/cost.json, PLAN.md section 17)
_C = json.load(open(os.path.join(ROOT, "build", "cost.json")))
_lo = _C["jlc"][0] + _C["digikey"] + _C["consign_ship"][0]
_hi = _C["jlc"][1] + _C["digikey"] + _C["consign_ship"][1]
REV_A = ("two rev A boards, assembled: JLCPCB $%.0f-%.0f, the consigned chips $%.0f, shipping them $%.0f-%.0f (section 17)"
         % (_C["jlc"][0], _C["jlc"][1], _C["digikey"], _C["consign_ship"][0], _C["consign_ship"][1]), round(_lo), round(_hi))
REV_B = ("two rev B boards: rev A's, the TLV3601 swapped for 8 TLV3604 (est +$2-4 each, with duty)", REV_A[1] + 20, REV_A[2] + 45)
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
EBAND = [("2 ADMV7310 + 2 ADMV7410: no public price ('quote required'); the 81-86 GHz ADMV7420 shows ~$830 at an aggregator (est $300-900 each)", 1200, 3600),
         ("2 LO synthesizers at ~12 GHz (the chips multiply by 6) (est)", 100, 300),
         ("a board and machined waveguide back plates, WR-12 parts (est); ADI's evaluation boards instead are $2,606.81 (ADMV7310-EVALZ) and $2,053.22 (ADMV7410-EVALZ) at Richardson, $9,320 for two nodes", 1500, 4000),
         ("4 dishes of 43 dBi or more, ~30 cm (est; used backhaul dishes cost less)", 1200, 6000),
         ("the FCC's non-exclusive nationwide licence and a link registration with a database manager (their fees not found) (est)", 0, 1000),
         ("8 InP comparators (HMC674-class) for the ADCMP572 (est)", 560, 1360),
         ("less the 5.8 GHz chain: mixers, LO, LNA, DSA, gain blocks, antennas (est)", -900, -300)]
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
    "6E": [REV_B, ECP5] + CML + WIDE + EBAND,
}
PREV = {"6E": "5"}           # E-band is the alternative to row 6: its delta is from row 5
ALT = {"3": ("two Brain-1 at $450 and a SYZYGY connector with its DNA chip a board, instead of the ECP5", 920 - 150, 950 - 300)}


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
        if key in PREV:
            plo, phi = next(r["total"] for r in rows if r["step"] == PREV[key])
        dlo, dhi = (lo - plo, hi - phi) if plo is not None else (0, 0)
        plo, phi = lo, hi
        r = dict(step=key, name=name, what=what, delta=(dlo, dhi), total=(lo, hi), costs=COSTS[key], params=p)
        if key in ALT:
            r["alternative"] = dict(item=ALT[key][0], total=(lo + ALT[key][1], hi + ALT[key][2]))
        for case, snr in SNR.items():
            if p.get("snr"):                                 # E-band: its own link budget, 25 dBm out already
                r[case] = r[case + "_PA"] = run(p, p["snr"][case])
                r[case + "_snr_dB"] = p["snr"][case]
                continue
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
    # the latency against the money: the RF rows, E-band, and the optical rows (sim/optics_roadmap.py)
    import optics_roadmap as OR
    orows = OR.rows()
    json.dump(orows, open(os.path.join(ROOT, "build", "optics_roadmap.json"), "w"), indent=1, default=float)
    gm = lambda t: math.sqrt(t[0] * t[1])
    fig, ax = plt.subplots(figsize=(9.6, 6.4))
    rf = [r for r in rows if r["step"] != "6E"]
    eb = next(r for r in rows if r["step"] == "6E")
    xs = [gm(r["total"]) for r in rf]
    yb = [r["bench"]["turnaround_ns"] for r in rf]
    k3 = [r for r in rf if r["step"] != "6"] + [eb]                              # 60 GHz: oxygen, 15 dB/km
    ax.plot(xs, yb, "o-", color="#1f5fbf", label="RF, the bench (10 m, whips): SMA to SMA")
    ax.plot([gm(r["total"]) for r in k3], [r["3 km_PA"]["turnaround_ns"] for r in k3], "s--", color="#c8401a",
            label="RF, 3 km (the PA at +30 dBm; E-band its own budget)")
    ax.plot([gm(eb["total"])], [eb["bench"]["turnaround_ns"]], "D", color="#1f5fbf", ms=7)
    ax.annotate("6E: E-band", (gm(eb["total"]), eb["bench"]["turnaround_ns"]), xytext=(6, -11), textcoords="offset points", fontsize=7.5)
    ox = [gm(r["total"]) for r in orows]
    oy = [r["100 m"].get("turnaround_ns") for r in orows]
    ax.plot(ox, oy, "o-", color="#2a8a3a", label="optics, 100 m: aperture to aperture (the terminals included)")
    o3 = [(x, r["3 km"]["turnaround_ns"]) for x, r in zip(ox, orows) if "turnaround_ns" in r["3 km"]]
    ax.plot([a_[0] for a_ in o3], [a_[1] for a_ in o3], "s--", color="#2a8a3a", alpha=0.7, label="optics, 3 km (where it closes)")
    ob = [(gm(r["beyond_owned"]), r["100 m"]["turnaround_ns"]) for r in orows if r["beyond_owned"][0] > 0]
    ax.plot([a_[0] for a_ in ob], [a_[1] for a_ in ob], "o:", color="#2a8a3a", mfc="none", alpha=0.8,
            label="optics, the money beyond the gear already owned")
    for r, x, y in zip(orows, ox, oy):
        ax.annotate("%s: %s" % (r["step"], r["name"].split(":")[0] if r["step"] == "O0" else r["name"]), (x, y),
                    xytext=(6, 4), textcoords="offset points", fontsize=7.2, color="#1d5e28")
    ax.errorbar(ox, oy, xerr=[[x - r["total"][0] for x, r in zip(ox, orows)], [r["total"][1] - x for x, r in zip(ox, orows)]],
                fmt="none", ecolor="#2a8a3a", alpha=0.35, lw=1)
    for r, x, y in zip(rf, xs, yb):
        ax.annotate("%s: %s" % (r["step"], r["name"]), (x, y), xytext=(6, 4), textcoords="offset points", fontsize=7.5)
    ax.errorbar(xs, yb, xerr=[[x - r["total"][0] for x, r in zip(xs, rf)], [r["total"][1] - x for x, r in zip(xs, rf)]],
                fmt="none", ecolor="#1f5fbf", alpha=0.4, lw=1)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("a two-node link's hardware, $ (log; line items in PLAN.md section 19)")
    ax.set_ylabel("the prover's turnaround, ns (log)")
    ax.set_title("Latency against money, RF and optical: each step keeps the ones before it", fontsize=10)
    ax.grid(alpha=0.25, which="both")
    ax.legend(fontsize=7.5, loc="lower left")
    fig.savefig(os.path.join(OUT, "latency_vs_cost.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("wrote build/latency_roadmap.json, docs/images/latency_vs_cost.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
