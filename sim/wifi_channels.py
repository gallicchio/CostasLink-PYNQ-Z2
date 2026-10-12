#!/usr/bin/env python3
"""Narrow the link into a WiFi channel?  What it costs in turnaround, what it buys in rejection
(Jason, Prompt 24: "does it make sense to narrow it a bit to 80 MHz or even 40 MHz to slot ourselves into
the existing WiFi channel scheme").

    python3 sim/wifi_channels.py        build/wifi_channels.json, docs/images/wifi_channels.png

An RF channel W wide is a baseband of +-W/2 on I and on Q.  To stay in it, the prover's transmitter
needs a baseband filter at about W/2, and to keep the neighbours out, its receiver needs one too.  Each
case puts the same filter at both ends (replacing the receive arm's pole and added after the TX ladder)
and runs the decision model of sim/latency_roadmap.py: the window at its CFAR place, the rise to it, the
transmitter's rise to 50 %.  The fixed terms are the RF table's rows 3 (TLV3604 into the FPGA's
combinational path) and 4 (the CML path).  "Today" is the board: the arm's one pole at 94.4 MHz and the
ladder and modulator on the TX side, which leave the transmitted spectrum unfiltered for hundreds of MHz.
"""
import json, math, os, sys
import numpy as np
from scipy import signal
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
B = json.load(open(os.path.join(ROOT, "build", "budget.json")))
DT = 0.01                                   # ns: the filters are written in ns and rad/ns, so the
T = np.arange(int(400 / DT)) * DT           # high-order polynomials stay well conditioned
FA = 1.0 / 3600
SNR = {"bench": B["link_rows"][1][4], "3 km": B["link_rows"][4][4], "3 km + PA": B["link_rows"][4][4] + 20.0}
FIXED = {"row 3": 1.1 + 0.8 + 0.15 + 2.0 + 3.0 + 0.5, "row 4": 0.8 + 0.165 + 0.05 + 0.25 + 0.0 + 0.4}


def pole(MHz):
    w = 2 * math.pi * MHz / 1000.0
    return ([], [-w], w)


def butter(MHz, n=4):
    return signal.butter(n, 2 * math.pi * MHz / 1000.0, analog=True, output="zpk")


def cascade(stages):
    z, p, k = [], [], 1.0
    for zz, pp, kk in stages:
        z, p, k = z + list(zz), p + list(pp), k * kk
    return signal.ZerosPolesGain(z, p, k)


def step(sys_):
    _, y, _ = signal.lsim(sys_.to_ss(), np.ones_like(T), T)
    return y


def t_at(y, level):
    i = int(np.argmax(y >= level))
    if i == 0:
        return float("nan")
    return T[i - 1] + (level - y[i - 1]) / (y[i] - y[i - 1]) * DT


def noise_terms(sys_):
    f = np.linspace(1e-6, 3.0, 300001)                       # GHz
    _, h = signal.freqs_zpk(sys_.zeros, sys_.poles, sys_.gain, worN=2 * math.pi * f)
    g2 = np.abs(h) ** 2
    df = f[1] - f[0]
    enbw = np.sum(g2) * df / g2[0] * 1e9                    # Hz
    nu0 = math.sqrt(np.sum(f ** 2 * g2) / np.sum(g2)) * 1e9
    return enbw, nu0


def att_dB(sys_, MHz):
    _, h = signal.freqs_zpk(sys_.zeros, sys_.poles, sys_.gain, worN=[2 * math.pi * MHz / 1000.0])
    return -20 * math.log10(abs(h[0]))


DEM = pole(390)
MOD = pole(750)
LADDER = {"row 3": [([], [-1 / 0.3], 1 / 0.3), ([], [-1 / 0.72], 1 / 0.72)],      # a bare pin's RC and the ladder node (ns)
          "row 4": [([], [-1 / 0.05], 1 / 0.05), ([], [-1 / 0.1], 1 / 0.1)]}       # the CML gate's drive
CASES = [("today: the arm's pole at 94.4 MHz, no TX filter", None, [pole(94.4)], [], 188.8),
         ("150 MHz (the ISM band), 2nd-order Butterworth at 75 MHz", 150, [butter(75, 2)], [butter(75, 2)], 150),
         ("80 MHz channel, one pole at 38 MHz", 80, [pole(38)], [pole(38)], 80),
         ("80 MHz channel, 4th-order Butterworth at 38 MHz", 80, [butter(38)], [butter(38)], 80),
         ("40 MHz channel, one pole at 19 MHz", 40, [pole(19)], [pole(19)], 40),
         ("40 MHz channel, 4th-order Butterworth at 19 MHz", 40, [butter(19)], [butter(19)], 40),
         ("20 MHz channel, 4th-order Butterworth at 9.5 MHz", 20, [butter(9.5)], [butter(9.5)], 20)]


def run_case(name, W, rx_f, tx_f, width):
    rx = cascade([DEM] + rx_f)
    g = step(rx)
    tx50 = {k: t_at(step(cascade(LADDER[k] + tx_f + [MOD])), 0.5) for k in FIXED}
    enbw, nu0 = noise_terms(rx)
    z = math.sqrt(2 * math.log(2 * nu0 / FA))
    out = dict(case=name, channel_MHz=W, rf_width_MHz=width, enbw_MHz=enbw / 1e6, z=z, tx50_ns=tx50, cases={})
    out["rx_delay_to_50_ns"] = t_at(g, 0.5)
    adj = (W if W else 40)                                             # the next channel's centre, MHz from ours
    out["rx_rejects_adjacent_dB"] = att_dB(rx, adj)
    out["tx_rejects_adjacent_dB"] = att_dB(cascade(LADDER["row 3"] + tx_f + [MOD]), adj)
    out["rx_rejects_2nd_adjacent_dB"] = att_dB(rx, 2 * adj)
    for case, snr in SNR.items():
        p_over_n0 = 10 ** (snr / 10) * 100e6
        th = z * math.sqrt(enbw / p_over_n0)
        row = dict(window=th, energy_ns=z * z / p_over_n0 * 1e9)
        if th < 0.9:
            rise = t_at(g, th)
            row["rise_ns"] = rise
            for k, fixed in FIXED.items():
                row[k + "_ns"] = fixed + max(rise, row["energy_ns"]) + tx50[k]
        out["cases"][case] = row
    return out


def main():
    res = [run_case(*c) for c in CASES]
    for r in res:
        cells = []
        for case in SNR:
            c = r["cases"][case]
            cells.append("%s %s/%s" % (case, ("%5.1f" % c["row 3_ns"]) if "row 3_ns" in c else "  -  ", ("%5.1f" % c["row 4_ns"]) if "row 4_ns" in c else "  -  "))
        print("%-50s tx50 %5.2f ns  ENBW %5.1f MHz  rejects adj RX %4.1f dB TX %4.1f dB, 2nd adj RX %4.1f dB | %s" % (
            r["case"][:50], r["tx50_ns"]["row 3"], r["enbw_MHz"], r["rx_rejects_adjacent_dB"], r["tx_rejects_adjacent_dB"], r["rx_rejects_2nd_adjacent_dB"], "  ".join(cells)))
    # interference in our band (Prompt 25): the window must sit above WiFi as well as the thermal noise.
    # During a burst WiFi's OFDM is noise-like, so it adds to N0: the SNR falls by 10 log(1 + INR).
    rx = cascade([DEM] + CASES[0][2])
    g = step(rx)
    enbw, nu0 = noise_terms(rx)
    z = math.sqrt(2 * math.log(2 * nu0 / FA))
    inr = []
    for INR in (0, 10, 20, 30, 40):
        row = dict(INR_dB=INR)
        for case in ("bench", "3 km + PA"):
            snr = SNR[case] - 10 * math.log10(1 + 10 ** (INR / 10))
            th = z * math.sqrt(enbw / (10 ** (snr / 10) * 100e6))
            row[case + "_window"] = th
            if th < 0.9:
                for k, fixed in FIXED.items():
                    row[case + " " + k + "_ns"] = fixed + t_at(g, th) + res[0]["tx50_ns"][k]
        inr.append(row)
        print("INR %2d dB in our band: bench window %.2f a, row 3 %s, row 4 %s | 3 km + PA window %.2f a, row 4 %s" % (
            INR, row["bench_window"], ("%.2f ns" % row["bench row 3_ns"]) if "bench row 3_ns" in row else "no fit",
            ("%.2f ns" % row["bench row 4_ns"]) if "bench row 4_ns" in row else "no fit",
            row["3 km + PA_window"], ("%.2f ns" % row["3 km + PA row 4_ns"]) if "3 km + PA row 4_ns" in row else "no fit"))
    n100 = B["link_rows"][1][3] - B["link_rows"][1][4]                 # the receiver's noise in 100 MHz, dBm
    print("the noise in 100 MHz is %.1f dBm: INR 10 dB is WiFi at %.0f dBm in our band, 20 dB at %.0f dBm" % (n100, n100 + 10, n100 + 20))
    res.append(dict(interference_today=inr, noise_dBm_in_100MHz=n100))
    json.dump(res, open(os.path.join(ROOT, "build", "wifi_channels.json"), "w"), indent=1)
    # the plot: the turnaround against the channel, and the filters against the WiFi grid
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.5, 4.8), gridspec_kw=dict(width_ratios=[1.1, 1]))
    labels = ["today\n(188 MHz, 1 pole)", "150 MHz\nButterworth 2", "80 MHz\n1 pole", "80 MHz\nButterworth 4", "40 MHz\n1 pole", "40 MHz\nButterworth 4", "20 MHz\nButterworth 4"]
    x = np.arange(len(res))
    for k, (row, case, col, mk) in enumerate([("row 3", "bench", "#1f5fbf", "o"), ("row 3", "3 km + PA", "#7aa5e0", "s"),
                                              ("row 4", "bench", "#c8401a", "o"), ("row 4", "3 km + PA", "#e8947a", "s")]):
        y = [r["cases"][case].get(row + "_ns", float("nan")) for r in res]
        a1.plot(x + (k - 1.5) * 0.08, y, mk, ls="none", ms=7, color=col, label="%s (%s), %s" % (row, "TLV3604 + FPGA" if row == "row 3" else "CML", case))
    a1.set_xticks(x); a1.set_xticklabels(labels, fontsize=7.5)
    a1.set_yscale("log"); a1.set_ylabel("the prover's turnaround, ns (log)")
    a1.set_title("What a channel filter at both ends costs", fontsize=10)
    a1.grid(alpha=0.25, which="both"); a1.legend(fontsize=7.5)
    f = np.linspace(0.1, 200, 2000)
    for r, c, ls in zip(res, ["k", "0.55", "#7aa5e0", "#1f5fbf", "#e8947a", "#c8401a", "#2a8a3a"], ["-", "--", ":", "-", ":", "-", "-"]):
        rx = cascade([DEM] + [cc for cc in CASES if cc[0] == r["case"]][0][2])
        _, h = signal.freqs_zpk(rx.zeros, rx.poles, rx.gain, worN=2 * math.pi * f / 1000.0)
        a2.plot(f, 20 * np.log10(np.abs(h)), ls, color=c, lw=1.3, label=r["case"].split(",")[0].split(" (")[0] + ("" if r["case"].startswith("today") else (", 1 pole" if "one pole" in r["case"] else (", Butterworth 2" if "2nd" in r["case"] else ", Butterworth 4"))))
    for e in (10, 30, 50, 70, 90, 110, 130, 150, 170, 190):
        a2.axvline(e, color="0.85", lw=0.7)
    a2.set_xlim(0, 200); a2.set_ylim(-60, 3)
    a2.set_xlabel("offset from our carrier, MHz (grey: 20 MHz WiFi channel edges)", fontsize=9); a2.set_ylabel("receive filter, dB")
    a2.set_title("What it rejects (the receiver; the transmitter's filter is the same)", fontsize=10)
    a2.grid(alpha=0.25); a2.legend(fontsize=7, loc="lower left")
    fig.tight_layout()
    fig.savefig(os.path.join(ROOT, "docs", "images", "wifi_channels.png"), dpi=130)
    plt.close(fig)
    print("wrote build/wifi_channels.json, docs/images/wifi_channels.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
