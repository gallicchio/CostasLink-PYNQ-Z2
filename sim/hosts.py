#!/usr/bin/env python3
"""What the host changes: the trajectory model of sim/trajectories.py with each host's own terms
(Jason, Prompt 20: the Icepi Zero, a SYZYGY port on the Brain-1, an ECP5 on the board).

    python3 sim/hosts.py        docs/images/hosts_latency.png, hosts_breakdown.png, build/hosts.json and
                                build/hosts_knobs.json (what each passive on rev A's chips saves)

A variant is the same radio (the ADL5375, the RF chain, the ADL5380) with these swapped:
  tx_tau     the transmitting FPGA pin into the ladder: the PYNQ's 200 ohm into ~10 pF, or a bare pin
             (~30 ohm of driver into the same 10 pF)
  fda_MHz    the fast arm's closed-loop bandwidth (850 MHz / noise gain); None = no FDA, the
             comparator straight on the ADL5380's outputs
  cmp_ns     the comparator: TLV3601 (2.5 ns, LVCMOS out) or TLV3604 (0.8 ns, LVDS out)
  rx50_ns    the comparator's edge to the FPGA's 50 %: 33 + 200 ohm into 10 pF on the PYNQ (1.6 ns),
             33 ohm into 10 pF on a bare pin (0.23 ns), an LVDS pair (0.15 ns)
  ts_ns      the FPGA's time step: ISERDES 1.25 ns, the Icepi's IDDRX1F 5 ns or GDDRX2 1.52 ns, or a
             carry-chain time-to-digital converter (~0.03 ns)
The FPGA's own output and input buffers (1.5 and 1.0 ns) are the same class on a Zynq and an ECP5 and
are kept equal.  Timing is from the transmitting FPGA's register to the receiving FPGA's register.
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
P = B["parts"]
OUT = os.path.join(ROOT, "docs", "images")

DT = 5e-12
t = np.arange(int(80e-9 / DT)) * DT
A_REG = B["vcmp_rms"] * math.sqrt(2)             # a at gain 4 (249 mV): only the comparator's overdrive cares
FA_RATE = 1.0 / 3600
SNRS = {"bench": B["link_rows"][1][4], "3 km": B["link_rows"][4][4]}
T_RF = (0.5 + 1.1) * 1e-9                         # TX gain block and lines; RX front end (sim/budget.py section 5)
T_OBUF, T_IBUF = 1.5e-9, 1.0e-9
TAU_LADDER = B["dac_Znode"] * 3e-12
TAU_MOD = 1 / (2 * math.pi * 750e6)
TAU_DEM = 1 / (2 * math.pi * P["dem_bw_MHz"] * 1e6)


def pole(x, tau):
    k = 1.0 - math.exp(-DT / tau)
    return lfilter([k], [1.0, -(1.0 - k)], x)


def chain(x, taus):
    for tau in taus:
        x = pole(x, tau)
    return x


def t_cross(g, level):
    i = int(np.argmax(g >= level))
    return t[i - 1] + (level - g[i - 1]) / (g[i] - g[i - 1]) * DT


VARIANTS = [
    # key, label, tx_tau, fda_MHz, cmp_ns, rx50_ns, ts_ns, comparator, colour
    ("pynq", "PYNQ-Z2 header (rev A as built)", 200 * 10e-12, B["fda_bw_MHz"], 2.5, 1.62, 1.25, "TLV3601", "#555555"),
    ("icepi1", "Icepi Zero, today's gateware (IDDRX1F, 200 Ms/s)", 30 * 10e-12, B["fda_bw_MHz"], 2.5, 0.23, 5.0, "TLV3601", "#c8a000"),
    ("icepi2", "Icepi Zero, GDDRX2 at 656 Ms/s (same board)", 30 * 10e-12, B["fda_bw_MHz"], 2.5, 0.23, 1.52, "TLV3601", "#e07000"),
    ("syzygy", "SYZYGY / Brain-1: TLV3604 LVDS, ISERDES 800 Ms/s", 30 * 10e-12, B["fda_bw_MHz"], 0.8, 0.15, 1.25, "TLV3604", "#1f5fbf"),
    ("tdc", "the same with a carry-chain TDC (or an ECP5 on the board)", 30 * 10e-12, B["fda_bw_MHz"], 0.8, 0.15, 0.03, "TLV3604", "#2a8a3a"),
    ("wide", "... and the arm at gain 2 (%.0f MHz)" % B["gain2"]["bw_MHz"], 30 * 10e-12, B["gain2"]["bw_MHz"], 0.8, 0.15, 0.03, "TLV3604", "#7a1fa0"),
    ("bare", "... and no FDA: TLV3604 on the ADL5380 (390 MHz)", 30 * 10e-12, None, 0.8, 0.15, 0.03, "TLV3604", "#c8401a"),
]


def model(v, tau_ladder=TAU_LADDER):
    key, label, tx_tau, fda, cmp_ns, rx50, ts, cmpn, col = v
    rx_taus = [TAU_DEM] + ([1 / (2 * math.pi * fda * 1e6)] if fda else [])
    step = (t >= T_RF + T_OBUF).astype(float)
    g = chain(step, [tx_tau, tau_ladder, TAU_MOD] + rx_taus)
    imp = np.zeros(20000); imp[0] = 1.0
    h = chain(imp, rx_taus)
    enbw = float(np.sum(h ** 2)) / (2 * DT)
    f = np.fft.rfftfreq(len(h), DT); hf = np.abs(np.fft.rfft(h))
    nu0 = math.sqrt(np.sum(f ** 2 * hf ** 2) / np.sum(hf ** 2))
    z = math.sqrt(2 * math.log(2 * nu0 / FA_RATE))
    dg = np.gradient(g, DT)
    tail = (cmp_ns + rx50 + ts / 2) * 1e-9 + T_IBUF
    out = dict(key=key, label=label, comparator=cmpn, enbw_MHz=enbw / 1e6, nu0_MHz=nu0 / 1e6, z=z,
               rise_ns=(t_cross(g, 0.9) - t_cross(g, 0.1)) * 1e9, cases={})
    for case, snr in SNRS.items():
        sig_over_a = math.sqrt(enbw / 100e6) / 10 ** (snr / 20)     # sigma / a, the budget's snr in 100 MHz
        th = z * sig_over_a
        row = dict(snr_dB=snr, t=th)
        if th < 0.9:
            tc = t_cross(g, th)
            k = int(np.argmin(abs(t - tc)))
            jit = math.sqrt((sig_over_a / (dg[k] * 1e-9)) ** 2 * 1e-18 + (ts * 1e-9) ** 2 / 12) if dg[k] > 0 else float("nan")
            row.update(event_ns=(tc + tail) * 1e9, jitter_ns=jit * 1e9)
        row["sign_ns"] = (t_cross(g, 0.5) + tail) * 1e9          # A3's I bit: sign(I) at half the rise
        out["cases"][case] = row
    out["parts"] = dict(fpga_out=T_OBUF * 1e9, rf=T_RF * 1e9, rise_to_bench_window=(t_cross(g, out["cases"]["bench"]["t"]) - T_RF - T_OBUF) * 1e9,
                        comparator=cmp_ns, to_fpga=rx50, fpga_in=T_IBUF * 1e9, sampling=ts / 2)
    curve = []
    for snr in np.linspace(14, 50, 145):
        th = z * math.sqrt(enbw / 100e6) / 10 ** (snr / 20)
        curve.append((snr, (t_cross(g, th) + tail) * 1e9 if th < 0.9 else float("nan")))
    out["curve"] = curve
    return out


def knobs():
    """The passives on rev A's own chips (PLAN.md section 19, "the knobs"): what each saves on the PYNQ-Z2's
    event, at the bench and at 3 km.  The arm's noise gain with the 1 k summing-node shunts is 1 + Rf / 500."""
    base = VARIANTS[0]
    def arm(mhz):
        return base[:3] + (mhz,) + base[4:]
    b0 = model(base)["cases"]
    out = {}
    for name, v, lad in (("the ladder's node at 100 ohm", base, 100 * 3e-12), ("the ladder's node at 50 ohm", base, 50 * 3e-12),
                         ("the arm at gain 2", arm(B["gain2"]["bw_MHz"]), TAU_LADDER), ("the arm at gain 1", arm(P["fda_gbw_MHz"] / 3), TAU_LADDER),
                         ("no arm", arm(None), TAU_LADDER)):
        c = model(v, lad)["cases"]
        out[name] = {case: (b0[case]["event_ns"] - c[case]["event_ns"]) if "event_ns" in c[case] else None for case in SNRS}
    return out


def main():
    res = [model(v) for v in VARIANTS]
    kn = knobs()
    for name, d in kn.items():
        print("knob: %-30s saves %s" % (name, ", ".join("%s %s" % (c, "%.2f ns" % x if x is not None else "no fit") for c, x in d.items())))
    print("%-58s %7s %7s %6s %18s %18s %8s" % ("variant", "rise", "ENBW", "z", "bench: t, event", "3 km: t, event", "sign(I)"))
    for r in res:
        b, k = r["cases"]["bench"], r["cases"]["3 km"]
        print("%-58s %5.1f ns %4.0f MHz %5.2f   %.2f a %5.1f+-%.2f   %s   %5.1f ns" % (
            r["label"][:58], r["rise_ns"], r["enbw_MHz"], r["z"], b["t"], b.get("event_ns", float("nan")), b.get("jitter_ns", float("nan")),
            ("%.2f a %5.1f+-%.2f" % (k["t"], k["event_ns"], k["jitter_ns"])) if "event_ns" in k else ("%.2f a   (no fit) " % k["t"]),
            b["sign_ns"]))
    os.makedirs(OUT, exist_ok=True)
    # the event against the SNR, per host
    fig, ax = plt.subplots(figsize=(8.4, 5.6))
    for v, r in zip(VARIANTS, res):
        s = np.array([c[0] for c in r["curve"]]); y = np.array([c[1] for c in r["curve"]])
        ax.plot(s, y, color=v[8], lw=2.0 if v[0] in ("pynq", "icepi2", "tdc") else 1.4, label=r["label"])
    for case, snr in SNRS.items():
        ax.axvline(snr, color="0.75", lw=0.8, ls="--")
        ax.text(snr + 0.3, 4.2, "%s\n%.1f dB" % (case, snr), fontsize=7.5, color="0.4", va="bottom")
    ax.set_xlabel("SNR in 100 MHz (dB)")
    ax.set_ylabel("ns, TX FPGA register to RX FPGA register")
    ax.set_title("The event (a Q window at its CFAR place, 1 false event an hour), host by host\n"
                 "(the same radio; each line swaps the host's pins, comparator, sampling or arm)", fontsize=10)
    ax.set_ylim(4, 18); ax.set_xlim(18, 50)
    ax.legend(fontsize=7.2, loc="upper right")
    ax.grid(alpha=0.25)
    fig.savefig(os.path.join(OUT, "hosts_latency.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    # where the bench's event time goes
    keys = ["fpga_out", "rf", "rise_to_bench_window", "comparator", "to_fpga", "fpga_in", "sampling"]
    names = ["FPGA out", "RF chips and lines", "the rise to the window", "comparator", "to the FPGA (RC)", "FPGA in", "sampling (mean)"]
    cols = ["0.7", "0.85", "#c8401a", "#1f5fbf", "#e0a000", "0.55", "#2a8a3a"]
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    y = np.arange(len(res))[::-1]
    left = np.zeros(len(res))
    for k_, n_, c_ in zip(keys, names, cols):
        w = np.array([r["parts"][k_] for r in res])
        ax.barh(y, w, left=left, color=c_, edgecolor="white", label=n_)
        for yi, l0, wi in zip(y, left, w):
            if wi > 0.9:
                ax.text(l0 + wi / 2, yi, "%.1f" % wi, ha="center", va="center", fontsize=7, color="white" if c_ in ("#c8401a", "#1f5fbf", "#2a8a3a", "0.55") else "k")
        left += w
    for yi, tot in zip(y, left):
        ax.text(tot + 0.2, yi, "%.1f ns" % tot, va="center", fontsize=8)
    ax.set_yticks(y); ax.set_yticklabels([r["label"] for r in res], fontsize=7.5)
    ax.set_xlabel("ns at the bench SNR (%.1f dB), window at its CFAR place" % SNRS["bench"])
    ax.set_title("Where the bench's event time goes, host by host", fontsize=10)
    ax.legend(fontsize=7, ncol=4, loc="upper center", bbox_to_anchor=(0.4, -0.13))
    ax.set_xlim(0, 12.5)
    fig.savefig(os.path.join(OUT, "hosts_breakdown.png"), dpi=130, bbox_inches="tight")
    plt.close(fig)
    for r in res:
        r.pop("curve")
    json.dump(res, open(os.path.join(ROOT, "build", "hosts.json"), "w"), indent=1)
    json.dump(kn, open(os.path.join(ROOT, "build", "hosts_knobs.json"), "w"), indent=1)
    print("wrote docs/images/hosts_latency.png, docs/images/hosts_breakdown.png, build/hosts.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
