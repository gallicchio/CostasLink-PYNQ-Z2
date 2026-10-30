#!/usr/bin/env python3
"""plot_board.py: board A's bring-up plots from its log (bringup/data/board_A/*.jsonl) and the night's files
(data/board_A/overnight/), written to data/board_A/plots/.  python3 bringup/plot_board.py [names...]"""
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np                      # noqa: E402
import plotstyle as P                  # noqa: E402

plt = P.plt
DATA = os.path.join(HERE, "data", "board_A")
OUT = os.path.join(DATA, "plots")


def log():
    rows = []
    for p in sorted(glob.glob(os.path.join(DATA, "*.jsonl"))):
        rows += [json.loads(l) for l in open(p)]
    return rows


def last(rows, **kv):
    m = [r for r in rows if all(r.get(k) == v for k, v in kv.items())]
    return m[-1] if m else None


def night(name):
    files = sorted(glob.glob(os.path.join(DATA, "overnight", name if "*" in name else name + "_*.json")))
    return json.load(open(files[-1])) if files else None, (files[-1] if files else None)


def label_end(ax, x, y, text, color, dy=0):
    ax.annotate(text, (x, y), xytext=(6, dy), textcoords="offset points", color=P.INK2, fontsize=9, va="center")


# ---- 1: the RF levels against frequency ----
def rf_levels(L):
    fig, ax = plt.subplots(figsize=(8.6, 4.6))
    tx = last(L, test="tx_spurs")
    sweeps = [r for r in L if r.get("kind") == "sweep"]
    lo_tx = [r for r in sweeps if r["label"].startswith("LO TX MON")][-1]
    lo_rx = [r for r in sweeps if r["label"].startswith("LO RX MON")][-1]
    series = [("TX ANT, the carrier at (1, 0)", [(r["mhz"], r["carrier"]) for r in tx["sweep"]]),
              ("LO RX MON (J109), RFOUTB at -1 dBm", [(r[0], r[2]) for r in lo_rx["rows"]]),
              ("LO TX MON (J204), RFOUTB at -1 dBm", [(r[0], r[2]) for r in lo_tx["rows"]])]
    for (name, pts), c in zip(series, P.SERIES):
        x, y = zip(*pts)
        ax.plot(np.array(x) / 1e3, y, color=c, marker="o", markersize=4, label=name)
    ax.axhline(9.8, color=P.MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(3.0, 10.4, "TX ANT planned at 5.8 GHz: +9.8 dBm", color=P.INK2, fontsize=8.5)
    ax.axhline(-1, color=P.MUTED, lw=1, ls=(0, (1, 2)))
    ax.text(3.0, -0.4, "RFOUTB as programmed: -1 dBm", color=P.INK2, fontsize=8.5)
    ax.axvspan(5.725, 5.875, color=P.GRID, alpha=0.5, lw=0)
    ax.set_xlabel("frequency, GHz")
    ax.set_ylabel("dBm at the jack")
    ax.set_xlim(2.95, 6.05)
    ax.set_title("Transmitter and LO monitors against frequency")
    P.subtitle(ax, "Board A, 2026-10-29.  The shaded band is the link's 5.8 GHz.  LO TX MON's tap runs 115.6 mm round the board.")
    ax.legend(loc="lower left")
    P.source(fig, "DSA875 spectrum analyser; TX ANT through 10 cm of RG-316 (+0.5 dB), the LO MON jacks through a U.FL pigtail.")
    return P.save(fig, os.path.join(OUT, "rf_levels.png"))


# ---- 2: the VCXO's pull ----
def vcxo_pull(L):
    r = last(L, test="vcxo_pull_ref_out", ok=True)
    vc = np.array([p["vc_adc"] for p in r["points"]])
    ppm = np.array([p["ppm"] for p in r["points"]])
    o = np.argsort(vc)
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.axhspan(-86, 86, color=P.GRID, alpha=0.45, lw=0)
    ax.text(0.32, 89, "needed: +-86 ppm (+-500 kHz at 5.8 GHz)", color=P.INK2, fontsize=8.5)
    ax.plot(vc[o], ppm[o], color=P.SERIES[0], marker="o", markersize=6)
    ax.axhline(0, color=P.AXIS, lw=0.8)
    k = np.polyfit(vc, ppm, 1)
    ax.annotate("%.1f ppm/V (%.0f kHz/V at 5.8 GHz)" % (k[0], k[0] * 5.8), (2.3, np.polyval(k, 2.3)),
                xytext=(10, -22), textcoords="offset points", color=P.INK2, fontsize=9)
    ax.set_xlabel("VC, V (the board's ADC)")
    ax.set_ylabel("REF OUT, ppm from 25 MHz")
    ax.set_title("The VCXO's pull")
    P.subtitle(ax, "Loop held, VC_OFF stepped 0.3-3.0 V; REF OUT's frequency from a line fit to 2500 edges per point.")
    P.source(fig, "SDS2104X Plus on REF OUT (J108); its timebase agreed with the DSA875's within 1 ppm.")
    return P.save(fig, os.path.join(OUT, "vcxo_pull.png"))


# ---- 3: the sidebands against REF IN's drive ----
def sideband_drive(L):
    r = last(L, test="ref_in_amplitude")
    v = np.array([x["vpp"] for x in r["rows"]])
    lo = np.array([x["-f"] for x in r["rows"]])
    hi = np.array([x["+f"] for x in r["rows"]])
    t3 = np.array([max(x["-3f"], x["+3f"]) for x in r["rows"]])
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    vv = np.linspace(0.7, 3.0, 50)
    ax.plot(vv, lo[0] + 20 * np.log10(vv / v[0]), color=P.MUTED, lw=1, ls=(0, (4, 3)), label="20 log V from 0.75 V: linear coupling")
    ax.plot(v, lo, color=P.SERIES[0], marker="o", markersize=6, label="carrier - 25.010 MHz")
    ax.plot(v, hi, color=P.SERIES[1], marker="o", markersize=6, label="carrier + 25.010 MHz")
    ax.plot(v, t3, color=P.SERIES[2], marker="s", markersize=5, label="+-75 MHz (the larger)")
    ax.set_xscale("log")
    ax.set_xticks([0.75, 1.0, 1.4, 2.0, 2.8])
    ax.set_xticklabels(["0.75", "1.0", "1.4", "2.0", "2.8"])
    ax.minorticks_off()
    ax.set_xlabel("REF IN's sine, V p-p open-circuit (log)")
    ax.set_ylabel("dBc at TX ANT")
    ax.set_title("The 25 MHz sidebands follow the reference trace's voltage")
    P.subtitle(ax, "JP201 on REF IN, the SDG1032X at 25.010 MHz.  A buffer inside U203 would square the sine: flat, with a 3rd harmonic.")
    ax.legend(loc="center right")
    P.source(fig, "DSA875 on TX ANT, 1 kHz RBW; the carrier at (1, 0).")
    return P.save(fig, os.path.join(OUT, "sideband_drive.png"))


# ---- 4: the sidebands at the ladder points ----
def sideband_points(L):
    r = last(L, test="tx_spurs")
    names = ["(1, 0)", "(-1, 0)", "(0, 1)", "(0, 0)", "tx_dis"]
    shown = ["(1, 0)", "(-1, 0)", "(0, 1)", "(0, 0)\nnulled", "TX_DIS"]
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    for j, (key, c, lab) in enumerate((("carrier", P.SERIES[0], "carrier"), ("-25", P.SERIES[1], "carrier - 25 MHz"),
                                         ("+25", P.SERIES[2], "carrier + 25 MHz"))):
        y = [r["points"][n][key] for n in names]
        ax.plot(np.arange(len(names)) + (j - 1) * 0.12, y, ls="none", marker="o", markersize=8, color=c, label=lab,
                markeredgecolor=P.SURFACE, markeredgewidth=1.5)
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels(shown)
    ax.set_ylabel("dBm at TX ANT")
    ax.set_title("The sidebands do not ride on the carrier")
    P.subtitle(ax, "5.8 GHz.  Nulling the carrier to -50 dBm leaves both sidebands where they were; TX_DIS removes them.")
    ax.legend(loc="lower left")
    P.source(fig, "DSA875 on TX ANT, 1 kHz RBW, 30 dB input attenuation.")
    return P.save(fig, os.path.join(OUT, "sideband_points.png"))


# ---- 5: RX MON against the DSA at 5.8 GHz (16:01) ----
def rx_dsa_5800(L):
    r = last(L, test="rx_mon_dsa")
    x = [w["dsa_db"] for w in r["walk"]]
    y = [w["rx_mon_dbm"] for w in r["walk"]]
    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    ax.plot(x, y, color=P.SERIES[0], lw=1.6)
    ax.plot([0, 31.75], [y[-1], y[-1] - 31.75], color=P.MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(14, y[-1] - 16, "1 dB per dB of DSA", color=P.INK2, fontsize=8.5)
    ax.invert_xaxis()
    ax.set_xlabel("DSA setting, dB")
    ax.set_ylabel("RX MON, dBm")
    ax.set_title("At 5.8 GHz, RX MON hardly follows the step attenuator")
    P.subtitle(ax, "TX ANT -> 40.2 dB -> RX ANT, all 128 steps.  Under ~9 dB it follows (the chain, ~28 dB under plan); over it, a -55 dBm floor.")
    P.source(fig, "DSA875 on RX MON (J102), 1 kHz RBW.")
    return P.save(fig, os.path.join(OUT, "rx_dsa_5800.png"))


# ---- the night ----
def night_map(L):
    rows, path = night("map")
    if not rows:
        return None
    f = np.array([r["mhz"] for r in rows]) / 1e3
    fig, axs = plt.subplots(1, 2, figsize=(12.4, 4.8))
    # slope of RX MON against the DSA (the linear part: DSA 20 down to the floor) and the chain's gain at DSA 0
    slopes, gains, floors_on, floors_off = [], [], [], []
    for r in rows:
        pts = [p for p in r["points"]]
        d = np.array([p["dsa"] for p in pts]); y = np.array([p["rx_mon"] for p in pts])
        k = np.polyfit(d, y, 1) if len(d) >= 3 else (np.nan, np.nan)
        slopes.append(-k[0])
        rx_ant = r["tx_ant_dbm"] - 40.2
        top = pts[-1]
        gains.append(top["rx_mon"] + 20.0 + top["dsa"] - rx_ant)
        floors_on.append(pts[0]["rx_mon"]); floors_off.append(r["tx_dis"]["rx_mon"])
    ax = axs[0]
    ax.axhline(1.0, color=P.MUTED, lw=1, ls=(0, (4, 3)))
    ax.plot(f, slopes, color=P.SERIES[0], marker="o", markersize=4)
    ax.set_ylim(-0.1, 1.3)
    ax.set_xlabel("frequency, GHz"); ax.set_ylabel("RX MON's slope, dB per dB of DSA")
    ax.set_title("Does RX MON follow the attenuator?")
    P.subtitle(ax, "1 = the signal passes the DSA; 0 = what RX MON sees arrives some other way.")
    ax = axs[1]
    ax.plot(f, gains, color=P.SERIES[0], marker="o", markersize=4, label="RX ANT -> coupler, at the lowest DSA")
    ax.axhline(38.9, color=P.MUTED, lw=1, ls=(0, (4, 3)))
    ax.text(f[0], 39.6, "planned at 5.8 GHz: 38.9 dB", color=P.INK2, fontsize=8.5)
    ax.set_xlabel("frequency, GHz"); ax.set_ylabel("gain, dB (RX MON + 20 + DSA - RX ANT)")
    ax.set_title("The receive chain's gain")
    P.subtitle(ax, "Where the slope above is under 1, this is an upper bound: leakage props RX MON up.")
    P.source(fig, "overnight %s: TX ANT -> 40.2 dB -> RX ANT; RX ANT from the TX ANT sweep less the pads; 20 dB coupling assumed." % os.path.basename(path))
    fig.tight_layout()
    return P.save(fig, os.path.join(OUT, "night_rx_chain.png"))


def night_map_heat(L):
    rows, path = night("map")
    if not rows:
        return None
    dsas = sorted({p["dsa"] for r in rows for p in r["points"]})
    f = [r["mhz"] for r in rows]
    Z = np.full((len(dsas), len(f)), np.nan)
    for j, r in enumerate(rows):
        for p in r["points"]:
            Z[dsas.index(p["dsa"]), j] = p["iq"]["2"]["PKPK"] or np.nan
    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("seq", P.SEQ)
    fig, ax = plt.subplots(figsize=(11.5, 4.6))
    m = ax.pcolormesh(np.array(f) / 1e3, dsas, Z, cmap=cmap, shading="nearest")
    cb = fig.colorbar(m, ax=ax, pad=0.01)
    cb.set_label("I MON beat, V p-p", color=P.INK2)
    cb.outline.set_edgecolor(P.AXIS)
    ax.grid(False)
    ax.set_xlabel("frequency, GHz"); ax.set_ylabel("DSA, dB")
    ax.set_title("The I arm's beat against frequency and attenuation")
    P.subtitle(ax, "Blank cells: the DSA kept above the floor that holds the demodulator at 0 dBm.  A column that barely changes is leakage.")
    P.source(fig, "SDS2104X ch2 on I MON (J104), 1 Mohm; overnight %s." % os.path.basename(path))
    return P.save(fig, os.path.join(OUT, "night_iq_heat.png"))


def night_iq(L):
    rows, path = night("iq")
    if not rows:
        return None
    ok = [r for r in rows if r.get("fit")]
    f = np.array([r["mhz"] for r in ok]) / 1e3
    ratio = [r["fit"]["ratio_db"] for r in ok]
    ph = [r["fit"]["phase_q_minus_i_deg"] for r in ok]
    fig, axs = plt.subplots(1, 2, figsize=(12.4, 4.6))
    axs[0].axhline(0, color=P.MUTED, lw=1, ls=(0, (4, 3)))
    axs[0].plot(f, ratio, color=P.SERIES[0], marker="o", markersize=5)
    axs[0].set_xlabel("frequency, GHz"); axs[0].set_ylabel("Q / I amplitude, dB")
    axs[0].set_title("I/Q amplitude balance")
    P.subtitle(axs[0], "Sine fits to the beat on I MON and Q MON, the DSA set for about 0.4 V p-p.")
    axs[1].axhline(0, color=P.MUTED, lw=1, ls=(0, (4, 3)))
    axs[1].plot(f, [abs(x) - 90 for x in ph], color=P.SERIES[1], marker="o", markersize=5)
    axs[1].set_ylim(-4, 4)
    axs[1].set_xlabel("frequency, GHz"); axs[1].set_ylabel("quadrature error, degrees (|phase| - 90)")
    axs[1].set_title("I/Q quadrature")
    P.subtitle(axs[1], "The phase of Q against I from the same fits, less the ideal 90 degrees.")
    P.source(fig, "overnight %s." % os.path.basename(path))
    fig.tight_layout()
    return P.save(fig, os.path.join(OUT, "night_iq_balance.png"))


def night_loop(L):
    rows, path = night("loop")
    if not rows:
        return None
    fig, axs = plt.subplots(1, len(rows), figsize=(4.2 * len(rows), 4.2), squeeze=False)
    for ax, r in zip(axs[0], rows):
        sc = [p for p in r["scan"] if p["beat_hz"]]
        ax.plot([p["vc"] for p in sc], [p["beat_hz"] / 1e3 for p in sc], color=P.SERIES[0], marker="o", markersize=5)
        for t in r["tries"]:
            if t["locked"]:
                ax.axvline(t["vc_end"], color=P.SERIES[5], lw=1.5)
                ax.text(t["vc_end"], ax.get_ylim()[1] * 0.9, " locked", color=P.INK2, fontsize=9)
        ax.set_xlabel("VC, V (loop held)"); ax.set_ylabel("I/Q beat, kHz")
        ax.set_title("%.1f GHz" % (r["mhz"] / 1e3))
    P.source(fig, "overnight %s; the beat from the scope's counter on I MON." % os.path.basename(path))
    fig.tight_layout()
    return P.save(fig, os.path.join(OUT, "night_loop_beat.png"))


def night_acquire(L):
    rows, path = night("acquire_20*.json")            # the combined file, not one frequency's
    if not rows:
        return None
    rows = [r for r in rows if r.get("rows")]
    states = [("locked", P.SERIES[0], "o"), ("false", P.SERIES[1], "D"), ("unlocked", P.SERIES[3], "s"), ("railed", P.MUTED, "x"),
              ("vc_clipped", P.MUTED, "+")]
    for r in rows:                                   # batch 2 ran before lock_state knew a clipped VC: reclassify
        for x in r["rows"]:
            if x.get("state") in ("locked", "false") and not 0.1 < x.get("vc", 1.65) < 3.2:
                x["state"] = "vc_clipped"
    n = len(rows)
    cols = min(3, n)
    fig, axs = plt.subplots((n + cols - 1) // cols, cols, figsize=(4.4 * cols, 3.9 * ((n + cols - 1) // cols)), squeeze=False)
    for ax, r in zip(axs.flat, rows):
        for st, c, m in states:
            pts = [x for x in r["rows"] if x.get("state") == st]
            if pts:
                ax.plot([x["vc_start"] for x in pts], [x["vc"] for x in pts], ls="none", marker=m, color=c,
                        markersize=7 if m != "x" else 6, label=st, markeredgecolor=P.SURFACE if m != "x" else c)
        locked = [x for x in r["rows"] if x.get("state") == "locked"]
        note = "DSA %.2f dB" % r["dsa"]
        if locked:
            v = [x["vc_start"] for x in locked]
            note += "; locks from VC %.2f-%.2f V" % (min(v), max(v))
        walk = [w for w in r.get("dsa_walk", []) if w["state"] == "locked" and 0.1 < w.get("vc", 1.65) < 3.2]
        if walk:
            note += "\nheld over DSA %.0f-%.0f dB" % (min(w["dsa"] for w in walk), max(w["dsa"] for w in walk))
        hold = [h for h in r.get("hold_in", []) if h["state"] == "locked" and 0.1 < h.get("vc", 1.65) < 3.2]
        if hold:
            note += "; VC_OFF %+.2f/%+.2f V" % (min(h["dvc_off"] for h in hold), max(h["dvc_off"] for h in hold))
        ax.set_title("%.1f GHz" % (r["mhz"] / 1e3))
        P.subtitle(ax, note)
        ax.set_xlabel("VC when released, V"); ax.set_ylabel("VC 2 s later, V")
        ax.set_xlim(0, 3.3); ax.set_ylim(0, 3.3)
    for ax in list(axs.flat)[n:]:
        ax.axis("off")
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], ls="none", marker=m, color=c, markersize=7, label={"locked": "locked (VC holds, no beat)",
               "false": "false lock (VC holds, a beat)", "unlocked": "unlocked (VC follows the step)", "railed": "integrator railed",
               "vc_clipped": "VC clipped at 0 V"}[st]) for st, c, m in states]
    fig.legend(handles=handles, loc="upper left", ncol=5, bbox_to_anchor=(0.005, 0.955))
    fig.suptitle("Where the Costas loop ends up, released from each VC", x=0.01, ha="left", fontsize=13, fontweight="bold", color=P.INK)
    P.source(fig, "overnight %s: the integrator centred each time; locked = VC holds through a 0.02 V VC_OFF step and no beat on I MON." % os.path.basename(path))
    fig.tight_layout(rect=(0, 0, 1, 0.91))
    return P.save(fig, os.path.join(OUT, "night_acquire.png"))


def night_drift(L):
    rows = [r for r in L if r.get("kind") == "night_drift" and "tcxo_hz" in r]
    if len(rows) < 3:
        return None
    import datetime as dt
    t = [dt.datetime.fromisoformat(r["t"]) if isinstance(r["t"], str) else dt.datetime.fromtimestamp(r["t"]) for r in rows]
    tc = np.array([r["tcxo_hz"] for r in rows]); vx = np.array([r["vcxo_hz"] for r in rows])
    fig, axs = plt.subplots(3, 1, figsize=(10.5, 8.2), sharex=True)
    axs[0].plot(t, (tc - tc[0]) / 25e6 * 1e6, color=P.SERIES[0])
    axs[0].set_ylabel("TCXO, ppm from the first")
    axs[0].set_title("Overnight: the two references and the board's temperature")
    P.subtitle(axs[0], "TCXO from the carrier / 232 on the analyser; VCXO from REF OUT on the scope (VC re-centred each time).")
    axs[1].plot(t, (vx - vx[0]) / 25e6 * 1e6, color=P.SERIES[1])
    axs[1].set_ylabel("VCXO, ppm from the first")
    axs[2].plot(t, [r["temp_c"] for r in rows], color=P.SERIES[2])
    axs[2].set_ylabel("NTC near U104, C")
    fig.autofmt_xdate()
    fig.tight_layout()
    return P.save(fig, os.path.join(OUT, "night_drift.png"))


ALL = [rf_levels, vcxo_pull, sideband_drive, sideband_points, rx_dsa_5800, night_map, night_map_heat, night_iq, night_acquire,
       night_drift]


def main(names):
    P.setup()
    os.makedirs(OUT, exist_ok=True)
    L = log()
    for fn in ALL:
        if names and fn.__name__ not in names:
            continue
        try:
            print(fn.__name__, "->", fn(L))
        except Exception as e:                                       # noqa: BLE001
            print(fn.__name__, "FAILED:", type(e).__name__, e)


if __name__ == "__main__":
    main(sys.argv[1:])
