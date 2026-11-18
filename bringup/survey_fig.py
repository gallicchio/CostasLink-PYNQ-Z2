"""survey_fig.py A.json B.json OUT.png: the two boards' own-receiver surveys of the lecture hall (2026-11-13), dBm at
RX ANT in the slow path's noise bandwidth against the LO frequency, DSA 0 (and DSA 20 where DSA 0 clipped), the hall's
WiFi channels from both laptops shaded, the TX synthesizers' leak frequencies marked (each TX disabled but its
synthesizer running: board A's at 4800, board B's at 5400)."""
import json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

WIFI = [(5170, 5210, 36), (5210, 5250, 48), (5250, 5290, 52), (5290, 5330, 64), (5490, 5530, 100), (5530, 5570, 112),
        (5570, 5610, 116), (5610, 5650, 124), (5650, 5690, 136), (5735, 5775, 149)]
fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
for ax, path, name, own, far in ((axes[0], sys.argv[1], "board A's receiver (the return's dish, vertical)", 4800, 5400),
                                 (axes[1], sys.argv[2], "board B's receiver (the beam's dish, horizontal)", 5400, 4800)):
    r = json.load(open(path))
    for lo, hi, ch in WIFI:
        ax.axvspan(lo, hi, color="#d9d9d9", lw=0)
        ax.text((lo + hi) / 2, 1.0, str(ch), transform=ax.get_xaxis_transform(), ha="center", va="bottom", fontsize=7, color="#555")
    th = r.get("thermal_dbm_slow")
    for p, style in zip(r["passes"], ("-o", "--s")):
        f = [x["f_mhz"] for x in p["rows"] if x["dbm"] is not None]
        d = [x["dbm"] for x in p["rows"] if x["dbm"] is not None]
        ax.plot(f, d, style, ms=2.5, lw=1, label="DSA %.0f" % p["dsa"])
        burst = [(x["f_mhz"], x["dbm"]) for x in p["rows"] if x["dbm"] is not None and (x.get("tail") or 0) > 1e-3]
        if burst:
            ax.plot(*zip(*burst), "x", color="red", ms=6, label="bursts past 4 sigma > 0.1 %% (DSA %.0f)" % p["dsa"])
    if th is not None:
        ax.axhline(th, color="k", lw=0.6, ls=":", label="the receiver's own noise (slow path)")
    for x, lab in ((own, "own TX synth (leak)"), (far, "far TX synth (leak)")):
        ax.axvline(x, color="#888", lw=0.8, ls="--")
        ax.text(x, 0.02, " " + lab, transform=ax.get_xaxis_transform(), fontsize=7, color="#555", rotation=90, va="bottom")
    ax.set_ylabel("dBm at RX ANT (7.5 MHz)")
    ax.set_title(name, fontsize=10, loc="left")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=7, loc="upper right")
axes[1].set_xlabel("MHz (the receiver's LO; both TXs disabled; grey: the WiFi channels the laptops see)")
fig.suptitle("Lecture hall, 2026-11-13 ~00:20: what each board's receiver hears through its dish", fontsize=11)
fig.tight_layout()
fig.savefig(sys.argv[3], dpi=110)
print("->", sys.argv[3])
