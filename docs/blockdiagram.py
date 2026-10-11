#!/usr/bin/env python3
"""The annotated block diagrams (Jason, Prompt 2): big blocks you can read at a glance, and on
every arrow a box with the signal's level, centre frequency, bandwidth and DC offset, with a
thumbnail of what the signal looks like in time or frequency.  Every number comes from
build/budget.json and build/link_rates.json (sim/budget.py and sim/link_rates.py), so the
diagrams cannot drift from the design.

    python3 docs/blockdiagram.py          writes docs/images/block_*.svg and .png

    block_system      the two stations, the air between them, the protocol's timing, the
                      three antenna arrangements and the channel plan
    block_rx          the receiver chain and the Costas loop, arrow by arrow
    block_tx          the transmitter chain, arrow by arrow
    block_loop        the Costas loop as a control system: detector, filter, VCO, numbers, plots
    block_modulations the five ways to send a bit, what each looks like on every arrow, the
                      SNR each needs and how far it reaches

Open the SVG in a browser and zoom: the text stays text.  The PNGs are for READMEs.
"""
import json, math, os, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Rectangle

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, "images")
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["font.family"] = "DejaVu Sans"

B = json.load(open(os.path.join(ROOT, "build", "budget.json")))
LR = json.load(open(os.path.join(ROOT, "build", "link_rates.json")))
QUIET = LR["schemes"]["BPSK"]["quiet (1e-4)"]          # BPSK's "quiet" SNR (11.4 dB since Response 10's sideband correction)
ONE_PCT = LR["schemes"]["BPSK"]["1 % wrong"]
P = B["parts"]

# colours by what flows: RF, LO, baseband analogue, logic, control (slow DC), power
C_RF, C_LO, C_BB, C_LOGIC, C_CTL, C_PWR = "#b8232f", "#7a3e9d", "#1f6fb4", "#2b8a3e", "#b86e00", "#666666"
C_BLOCK = "#eef2f7"
C_NOTE = "#fffbe6"


def dbm_to_vpp(dbm, R=50.0):
    return 2 * math.sqrt(2) * math.sqrt(10 ** (dbm / 10.0) * 1e-3 * R)


def fmt_level(dbm):
    v = dbm_to_vpp(dbm)
    return "%+.1f dBm (%.0f mV p-p in 50 Ω)" % (dbm, v * 1e3) if v >= 1e-3 else "%+.1f dBm (%.0f µV p-p)" % (dbm, v * 1e6)


class Canvas:
    """A page W x H mm; everything is placed in mm from the bottom-left corner."""

    def __init__(self, W, H, title, subtitle):
        self.W, self.H = W, H
        self.fig = plt.figure(figsize=(W / 25.4, H / 25.4))
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, W); self.ax.set_ylim(0, H); self.ax.axis("off")
        self.ax.add_patch(Rectangle((0, 0), W, H, fc="white", ec="none"))
        self.ax.text(12, H - 14, title, fontsize=30, fontweight="bold", va="top")
        self.ax.text(12, H - 26, subtitle, fontsize=11, va="top", color="#333")

    def block(self, x, y, w, h, title, sub="", fs=20, fc=C_BLOCK, ec="#334", sfs=8.5):
        self.ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=3", fc=fc, ec=ec, lw=1.6))
        if sub:
            self.ax.text(x + w / 2, y + h - 4, title, fontsize=fs, fontweight="bold", ha="center", va="top")
            self.ax.text(x + w / 2, y + 3, sub, fontsize=sfs, ha="center", va="bottom", color="#222", linespacing=1.25)
        else:
            self.ax.text(x + w / 2, y + h / 2, title, fontsize=fs, fontweight="bold", ha="center", va="center")
        return dict(x=x, y=y, w=w, h=h, l=(x, y + h / 2), r=(x + w, y + h / 2), t=(x + w / 2, y + h), b=(x + w / 2, y))

    def arrow(self, p0, p1, color=C_RF, lw=2.2, style="-|>"):
        self.ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle=style, mutation_scale=16, color=color, lw=lw, shrinkA=0, shrinkB=0))

    def wire(self, pts, color=C_RF, lw=2.2, arrow=True):
        for a, b in zip(pts, pts[1:-1]):
            self.ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=lw, solid_capstyle="round")
        if arrow:
            self.arrow(pts[-2], pts[-1], color=color, lw=lw)
        else:
            self.ax.plot([pts[-2][0], pts[-1][0]], [pts[-2][1], pts[-1][1]], color=color, lw=lw)

    def note(self, x, y, text, fs=7.5, w=None, ha="left", va="bottom", fc=C_NOTE, ec="#998", title=None):
        if title:
            text = title + "\n" + text
        t = self.ax.text(x, y, text, fontsize=fs, ha=ha, va=va, linespacing=1.3,
                         bbox=dict(boxstyle="round,pad=0.5", fc=fc, ec=ec, lw=0.6))
        return t

    def label(self, x, y, text, fs=9, color="#222", ha="center", va="center", weight="normal", rot=0):
        self.ax.text(x, y, text, fontsize=fs, color=color, ha=ha, va=va, fontweight=weight, rotation=rot)

    def thumb(self, x, y, w, h, draw, caption="", frame=True):
        """An inset w x h mm at (x, y) drawn by draw(ax); caption below."""
        a = self.fig.add_axes([x / self.W, y / self.H, w / self.W, h / self.H])
        a.set_xticks([]); a.set_yticks([])
        for s in a.spines.values():
            s.set_visible(frame); s.set_color("#aaa"); s.set_linewidth(0.6)
        a.set_facecolor("#fafafa")
        draw(a)
        if caption:
            self.ax.text(x + w / 2, y - 1.2, caption, fontsize=6.5, ha="center", va="top", color="#444", style="italic")
        return a

    def save(self, name):
        os.makedirs(OUT, exist_ok=True)
        for ext, kw in (("svg", {}), ("png", dict(dpi=55))):
            self.fig.savefig(os.path.join(OUT, name + "." + ext), **kw)
        plt.close(self.fig)
        print("wrote docs/images/%s.svg and .png" % name)


# ---------------------------------------------------------------------------------------------
# thumbnails: little pictures of what the signal looks like
def t_carrier_flip(a, flip_at=0.5, cycles=14, kind="bpsk"):
    t = np.linspace(0, 1, 1200)
    ph = np.where(t > flip_at, math.pi, 0.0) if kind == "bpsk" else np.where(t > flip_at, math.pi / 4, 0.0)
    if kind == "fsk":
        ph = np.where(t > flip_at, 2 * math.pi * 3 * (t - flip_at), 0.0)
    y = np.cos(2 * math.pi * cycles * t + ph)
    a.plot(t, y, color=C_RF, lw=0.8)
    a.axvline(flip_at, color="#999", lw=0.5, ls=":")
    a.set_ylim(-1.3, 1.3)


def t_noisy_carrier(a, snr_db=20, cycles=14):
    t = np.linspace(0, 1, 1200)
    y = np.cos(2 * math.pi * cycles * t) + np.random.default_rng(1).normal(0, 10 ** (-snr_db / 20), t.size)
    a.plot(t, y, color=C_RF, lw=0.7)
    a.set_ylim(-1.5, 1.5)


def t_iq_step(a, which="I", flip_at=0.5, kind="bpsk", noise=0.03):
    t = np.linspace(0, 1, 600)
    rng = np.random.default_rng(2)
    if kind == "bpsk":
        I = np.where(t > flip_at, -1.0, 1.0); Qv = np.zeros_like(t)
    elif kind == "qpsk":
        I = np.where((t > flip_at) & (t < flip_at + 0.15), 0.707, 1.0); Qv = np.where((t > flip_at) & (t < flip_at + 0.15), 0.707, 0.0)
    elif kind == "fsk":
        ang = np.where((t > flip_at) & (t < flip_at + 0.3), 2 * math.pi * 3 * (t - flip_at), 0.0)
        I = np.cos(ang); Qv = np.sin(ang)
    else:
        I = np.where((t > flip_at) & (t < flip_at + 0.15), 0.0, 1.0); Qv = np.zeros_like(t)
    y = I if which == "I" else Qv
    # the arm filter: a 2-pole low-pass, drawn as a simple smoothing
    k = np.exp(-np.arange(0, 40) / 8.0); k /= k.sum()
    y = np.convolve(y, k, mode="same") + rng.normal(0, noise, t.size)
    a.plot(t, y, color=C_BB, lw=0.9)
    a.axhline(0, color="#999", lw=0.5)
    a.set_ylim(-1.4, 1.4)


def t_logic(a, edges=((0.5, 1),), lo=0.0):
    t = np.linspace(0, 1, 600)
    y = np.full_like(t, lo)
    for s, v in edges:
        y = np.where(t > s, v, y)
    a.step(t, y, color=C_LOGIC, lw=1.2, where="post")
    a.set_ylim(-0.3, 1.5)


def t_constellation(a, points, labels=None, idle=0, show_axes=True):
    if show_axes:
        a.axhline(0, color="#bbb", lw=0.5); a.axvline(0, color="#bbb", lw=0.5)
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    a.scatter(xs, ys, s=14, color=C_BB, zorder=3)
    if idle is not None:
        a.scatter([xs[idle]], [ys[idle]], s=40, facecolors="none", edgecolors=C_RF, zorder=4, lw=1.0)
    if labels:
        for (x, y), l in zip(points, labels):
            a.annotate(l, (x, y), fontsize=5, xytext=(2, 2), textcoords="offset points")
    a.set_xlim(-1.5, 1.5); a.set_ylim(-1.5, 1.5); a.set_aspect("equal")


def t_spectrum(a, kind="line", fc=0.5, bw=0.08):
    f = np.linspace(0, 1, 800)
    if kind == "line":
        y = np.exp(-((f - fc) / 0.004) ** 2)
        a.plot(f, y, color=C_RF, lw=0.9)
        a.fill_between(f, 0, 0.12 * np.sinc((f - fc) / bw) ** 2, color=C_RF, alpha=0.25, lw=0)
    elif kind == "sinc":
        y = np.sinc((f - fc) / bw) ** 2
        a.plot(f, y, color=C_RF, lw=0.9)
    elif kind == "baseband":
        y = 1 / (1 + (f / bw) ** 4)
        a.plot(f, y, color=C_BB, lw=0.9)
        a.axvline(bw, color="#999", lw=0.5, ls=":")
    elif kind == "lo":
        y = np.exp(-((f - fc) / 0.003) ** 2) + 0.02 / (1 + ((f - fc) / 0.02) ** 2)
        a.semilogy(f, y + 1e-4, color=C_LO, lw=0.9)
    a.set_ylim(bottom=0) if kind != "lo" else None


def t_ladder(a):
    t = np.linspace(0, 1, 600)
    lv = B["dac_levels"]
    y = np.where(t < 0.3, lv[1], np.where(t < 0.55, lv[2], np.where(t < 0.8, lv[0], lv[1])))
    a.step(t, y, color=C_CTL, lw=1.2, where="post")
    for v in lv:
        a.axhline(v, color="#ccc", lw=0.4, ls=":")
    a.set_ylim(0, 1.0)


def t_lo(a, cycles=10):
    t = np.linspace(0, 1, 600)
    a.plot(t, np.cos(2 * math.pi * cycles * t), color=C_LO, lw=0.8)
    a.set_ylim(-1.3, 1.3)


def t_square(a, cycles=4):
    t = np.linspace(0, 1, 600)
    a.step(t, (np.floor(t * cycles * 2) % 2), color=C_LOGIC, lw=1.0, where="post")
    a.set_ylim(-0.3, 1.5)


def t_error(a):
    t = np.linspace(0, 1, 600)
    y = 0.6 * np.exp(-t * 6) * np.cos(2 * math.pi * 1.2 * t)
    a.plot(t, y, color=C_CTL, lw=1.0)
    a.axhline(0, color="#999", lw=0.5)
    a.set_ylim(-0.8, 0.8)


def t_vc(a):
    t = np.linspace(0, 1, 600)
    y = 1.65 + 0.3 * (1 - np.exp(-t * 5)) * (1 + 0.1 * np.sin(2 * math.pi * 0.7 * t))
    a.plot(t, y, color=C_CTL, lw=1.0)
    a.set_ylim(0, 3.3)
    a.axhline(0.3, color="#ccc", lw=0.4, ls=":"); a.axhline(3.0, color="#ccc", lw=0.4, ls=":")


def t_scurve(a):
    ph = np.linspace(-math.pi, math.pi, 600)
    y = np.sign(np.cos(ph)) * np.sin(ph)
    a.plot(ph, y, color=C_CTL, lw=1.0)
    a.axhline(0, color="#999", lw=0.5); a.axvline(0, color="#999", lw=0.5)
    a.set_ylim(-1.3, 1.3)


# ---------------------------------------------------------------------------------------------
def rx_levels():
    """Levels along the receiver at 10 m, as sim/budget.py section 3 computed them."""
    pr = B["link_rows"][1][3]
    lna = pr + P["lna_gain_dB"]
    dsa = lna - P["dsa_il_dB"] - B["dsa_set_dB"]
    gb = dsa + P["gb_gain_dB"]
    return pr, lna, dsa, gb, B["dem_in_dBm"]


def block_rx():
    W, H = 1300, 760
    c = Canvas(W, H, "Receiver, Costas loop, and the two decision paths",
               "One zero-IF quadrature demodulator does everything: its LO is a synthesizer on a VCXO, and the loop below steers the VCXO until the LO sits exactly on the far carrier.  "
               "Then I is the data and Q the phase error.  The FAST path (gain %.0f, %.0f MHz) flags a bit in nanoseconds; the SLOW path (x%.0f more, %.1f MHz) confirms or vetoes it %.0f ns later from %.0f dB further away.  "
               "Levels are for the 10 m bench link (%.1f dBm at the jack, DSA at %.2f dB); sim/budget.py sections 2, 3, 6, 7, 7b."
               % (B["G_fda"], B["B_MHz"], B["G_slow"], B["slow_fpole_MHz"], B["slow_t50_ns"], (B["floor_fast_dBm"] - B["noise_floor_slow_dBm"] - QUIET), B["link_rows"][1][3], B["dsa_set_dB"]))
    pr, lna_o, dsa_o, gb_o, dem_i = rx_levels()
    y = 590
    bw = 86; gap = 48; x = 20
    xs = []
    def nb(title, sub, w=bw):
        nonlocal x
        b = c.block(x, y - 30, w, 60, title, sub)
        xs.append(b); x += w + gap
        return b
    ant = nb("RX ANT", "SMA, 50 Ω\nabs. max +1 dBm", w=62)
    lna = nb("LNA", "SKY65404\n+%.0f dB, NF %.0f dB\nP1dB out +%.0f dBm" % (P["lna_gain_dB"], P["lna_nf_dB"], P["lna_p1db_out_dBm"]))
    dsa = nb("DSA", "PE43711\n0 to %.2f dB in 0.25\nSPI, %.0f ns" % (P["dsa_max_dB"], P["dsa_switch_ns"]))
    gb = nb("2 gain blocks", "2 x ADL5611\n+%.1f dB each at 5.8 GHz\nP1dB +%.0f dBm; the second one\nputs the comparator floor near the noise" % (P["gb_gain_dB"], P["gb_p1db_dBm"]), w=100)
    dem = nb("I/Q demodulator", "ADL5380\n0.4-6 GHz, %.0f MHz baseband\ngain %.1f dB into 450 Ω, IP1dB +%.1f dBm" % (P["dem_bw_MHz"], P["dem_gain_dB"], P["dem_ip1db_dBm"]), w=120)
    fda = nb("Fast arms", "2 x THS4541\ngain %.0f, %.0f MHz\ncommon mode 3.2 V -> 1.65 V" % (B["G_fda"], B["fda_bw_MHz"]), w=100)
    cmp_ = nb("Fast comparators", "3 x TLV3601, %.1f ns\nsign(I) = data\nQ > +Vth,  Q < -Vth\nfloor %.0f dBm at the antenna" % (P["cmp_tpd_ns"], B["floor_fast_dBm"]), w=110)
    fpga = nb("FPGA", "PYNQ-Z2 (Zynq) or\nIcepi Zero (ECP5)\nfast flag on 18, 10, 8\nslow confirm on 33, 40, 37", w=96)
    # arrows and their boxes
    arrows = [
        (ant, lna, C_RF, "5.8 GHz carrier, %s\nband 5.15-5.875 GHz (parts 4.9-6 GHz)\nbandwidth: a CW line, flips add ±%.0f MHz skirts\nDC: none (1.5 pF block)" % (fmt_level(pr), B["B_MHz"]), lambda a: t_noisy_carrier(a, 25), "what the antenna delivers"),
        (lna, dsa, C_RF, "%s\nnoise floor in %.0f MHz: %.1f dBm at the jack\nSNR %.0f dB" % (fmt_level(lna_o), B["B_MHz"], B["noise_floor_dBm"], pr - B["noise_floor_dBm"]), lambda a: t_noisy_carrier(a, 35), "amplified, noise set here"),
        (dsa, gb, C_RF, "%s\nthe DSA puts the demodulator at ~-20 dBm\n(strong signals: more attenuation)" % fmt_level(dsa_o), lambda a: t_noisy_carrier(a, 35), "levelled"),
        (gb, dem, C_RF, "%s\n(IP1dB +%.1f dBm: %.0f dB headroom; the DSA holds this\nat -20 dBm from 3 m to about 300 m)" % (fmt_level(dem_i), P["dem_ip1db_dBm"], P["dem_ip1db_dBm"] - dem_i), lambda a: t_carrier_flip(a), "a BPSK flip on the carrier"),
        (dem, fda, C_BB, "I and Q, each differential: %.0f mV rms (%.0f mV p-p)\nDC-%.0f MHz; common mode 3.2 V, 25 Ω per pin\nidle: I = +A, Q = 0 (the loop holds it there)" % (B["vbb_diff_rms"] * 1e3, B["vbb_diff_rms"] * 2.83e3, P["dem_bw_MHz"]), lambda a: t_iq_step(a, "I"), "I: a step at the flip"),
        (fda, cmp_, C_BB, "I, Q: %.0f mV rms (±%.0f mV peak) differential\nDC-%.0f MHz, %.1f ns rise, centred 1.65 V\nQ window ±Vth = 2 (V_T - 1.65 V), V_T from the DAC" % (B["vcmp_rms"] * 1e3, B["vcmp_rms"] * 1.414e3, B["fda_bw_MHz"], 350.0 / B["fda_bw_MHz"]), lambda a: t_iq_step(a, "Q", kind="qpsk"), "Q: a blip only for QPSK/FSK"),
        (cmp_, fpga, C_LOGIC, "the FAST FLAG: 3.3 V CMOS through 33 Ω (+200 Ω on the PYNQ)\nCMP_I: level = the bit (a flip = the event)\nCMP_QP / CMP_QN: a pulse during a QPSK or FSK symbol\n%.1f ns from the jack to the FPGA register (%.1f ns on the Icepi)" % (B["latency_ns"] - 8.5, B["latency_icepi_ns"] - 4.1), lambda a: t_logic(a, ((0.5, 1),)), "CMP_I flips"),
    ]
    for k, (a, b, col, text, th, cap) in enumerate(arrows):
        c.arrow(a["r"], b["l"], color=col)
        xm = (a["r"][0] + b["l"][0]) / 2
        above = (k % 2 == 0)
        c.note(xm, y + 36 if above else y - 36, text, ha="center", va="bottom" if above else "top", fs=7)
        c.thumb(xm - 14, (y - 70) if above else (y + 42), 28, 18, th, caption=cap)
    # the slow path: a second stage and its comparators under the fast ones
    sy = y - 150
    slow = c.block(fda["x"], sy - 30, 100, 60, "Slow stage", "2 x THS4541, gain %.0f\n%.0f Ω / %.0f pF = %.1f MHz\noffset trims from DAC2" % (B["G_slow"], B["slow_Rrc"], B["slow_Crc"] * 1e12, B["slow_fpole_MHz"]))
    scmp = c.block(cmp_["x"], sy - 30, 110, 60, "Slow comparators", "3 x TLV3601\nsign(I), Q window at V_T2\nfloor %.0f dBm at the antenna" % B["floor_slow_dBm"])
    c.wire([(fda["r"][0] + 10, fda["r"][1]), (fda["r"][0] + 10, slow["t"][1] + 30), (slow["t"][0] - 20, slow["t"][1] + 30), (slow["t"][0] - 20, slow["t"][1])], color=C_BB)
    c.arrow(slow["r"], scmp["l"], color=C_BB)
    c.wire([scmp["r"], (scmp["r"][0] + 20, scmp["r"][1]), (scmp["r"][0] + 20, fpga["b"][1] - 10), (fpga["b"][0], fpga["b"][1] - 10), fpga["b"]], color=C_LOGIC)
    c.note((slow["r"][0] + scmp["l"][0]) / 2, sy + 36, "I_s, Q_s: x%.0f, so ±%.1f V (the rails) at the bench level; the sign survives\n%.1f MHz: %.0f ns rise, decides %.0f ns after the fast comparator\nnoise in %.1f MHz: %.1f dBm; quiet from %.1f dBm at the antenna (%.0f dB further than the fast path)"
           % (B["G_slow"], 1.65, B["slow_fpole_MHz"], B["slow_rise_ns"], B["slow_t50_ns"], B["B_slow_MHz"], B["noise_floor_slow_dBm"], B["noise_floor_slow_dBm"] + QUIET, B["noise_floor_dBm"] - B["noise_floor_slow_dBm"]), ha="center", fs=7)
    c.thumb((slow["r"][0] + scmp["l"][0]) / 2 - 14, sy - 70, 28, 18, lambda a: t_iq_step(a, "I", noise=0.01), caption="I slow: the same step, cleaner and later")
    c.note(scmp["r"][0] + 24, sy + 20, "the SLOW CONFIRM: CMP_I_S, CMP_QP_S, CMP_QN_S on header pins 33, 40, 37\nthe gateware acts on the fast flag at once and keeps the trial only\nif these agree %.0f ns later: a false alarm costs a trial, not a bit" % B["slow_t50_ns"], fs=7)
    c.note(fda["x"] - 60, sy + 36, "the same I_P/I_N and Q_P/Q_N pairs\nleave the fast arms to sheet 6", ha="center", fs=7)
    # LO into the demodulator, from the synthesizer below
    synth = c.block(dem["x"] + 10, 300, 100, 56, "Synthesizer", "MAX2871, integer-N x232\n25 MHz ref, PFD 25 MHz\nloop %.0f kHz, 50°" % (B["pll_fc"] / 1e3))
    c.arrow((synth["t"][0], synth["t"][1]), (synth["t"][0], dem["b"][1]), color=C_LO)
    c.note(synth["t"][0] + 6, 385, "LO: 5.8 GHz, 0 dBm differential (two 1.5 pF)\nphase noise ~%.0f dBc/Hz in the %.0f kHz loop\nthis is the loop's VCO: it moves with the VCXO" % (-109, B["pll_fc"] / 1e3), fs=7)
    c.thumb(synth["t"][0] - 44, 372, 28, 18, lambda a: t_spectrum(a, "lo"), caption="LO spectrum (log)")
    vcxo = c.block(40, 300, 100, 56, "VCXO", "25 MHz, 3225\n±%.0f ppm over %.1f-%.1f V\n15 kHz modulation BW" % (P["vcxo_pull_ppm"], P["vcxo_vc_V"][0], P["vcxo_vc_V"][1]))
    c.arrow(vcxo["r"], synth["l"], color=C_LO)
    c.note((vcxo["r"][0] + synth["l"][0]) / 2, 362, "25 MHz, 3.3 V CMOS square, through 100 nF\n±%.0f ppm pull = ±%.0f kHz at 5.8 GHz\nalso buffered out as REF OUT (U.FL)" % (P["vcxo_pull_ppm"], P["vcxo_pull_ppm"] * 5.8), ha="center", fs=7)
    c.thumb((vcxo["r"][0] + synth["l"][0]) / 2 - 14, 275, 28, 18, lambda a: t_square(a, 4), caption="25 MHz reference")
    # Costas loop under the comparators
    ly = 180
    mul = c.block(cmp_["x"] - 20, ly, 110, 56, "sign(I) × Q", "74LVC1G3157 analogue switch:\nCMP_I selects +Q or -Q\n(a BPSK flip inverts both: product unchanged)")
    hold = c.block(mul["x"] - 150, ly, 96, 56, "HOLD", "TS5A3159 switch\nLOOP_HOLD opens the\nintegrator's input")
    pi = c.block(hold["x"] - 160, ly, 116, 56, "PI loop filter", "OPA2388: R1 %.0f k, R2 %.0f Ω, C %.0f nF\nf_n %.0f Hz, ζ 0.7\n+ VC_OFF summing (DAC)" % (B["loop_R1"] / 1e3, B["loop_R2"], B["loop_C"] * 1e9, 3000))
    c.wire([(cmp_["b"][0], cmp_["b"][1]), (cmp_["b"][0], mul["t"][1])], color=C_LOGIC)
    c.wire([(fda["b"][0] + 30, fda["b"][1]), (fda["b"][0] + 30, mul["t"][1] + 50), (mul["x"] + 100, mul["t"][1] + 50), (mul["x"] + 100, mul["t"][1])], color=C_BB)
    c.label(fda["b"][0] + 46, mul["t"][1] + 54, "Q (the phase error, ±%.0f mV peak)" % (B["vcmp_rms"] * 1.414e3), fs=7, ha="left")
    c.label(cmp_["b"][0] + 2, mul["t"][1] + 20, "sign(I)", fs=7, ha="left")
    c.arrow(mul["l"], hold["r"], color=C_CTL)
    c.note((mul["l"][0] + hold["r"][0]) / 2, ly + 62, "error = sign(I)·Q: 0 at lock, ±Q off lock\nS-curve: sin(φ)·sign(cos φ), period π\n(lock at 0 or 180°: the data may be inverted;\nthe gateware defines 'idle' after lock)", ha="center", fs=7)
    c.thumb((mul["l"][0] + hold["r"][0]) / 2 - 14, ly - 24, 28, 18, t_scurve, caption="error vs phase (S-curve)")
    c.arrow(hold["l"], pi["r"], color=C_CTL)
    c.note((hold["l"][0] + pi["r"][0]) / 2, ly + 62, "same signal, gated: HOLD high\nfreezes VC (own TX, or a lost carrier)", ha="center", fs=7)
    c.thumb((hold["l"][0] + pi["r"][0]) / 2 - 14, ly - 24, 28, 18, t_error, caption="error settling after a step")
    c.wire([pi["l"], (vcxo["t"][0], pi["l"][1]), vcxo["t"]], color=C_CTL)
    c.note(vcxo["t"][0] + 8, ly + 10, "VC: 0.3-3.0 V, 1.65 V centred, slow (3 kHz loop)\nVC MON U.FL and the ADC watch it\nVC_OFF (DAC) centres it; LOOP_SEL = FPGA makes a plain PLL on Q", fs=7)
    c.thumb(vcxo["t"][0] + 12, ly - 24, 28, 18, t_vc, caption="VC pulling in")
    # how-to-read box and the numbers table
    c.note(20, 70, "Follow the red arrows left to right: 5.8 GHz comes in, gets amplified and levelled, and the demodulator multiplies it by the LO twice (once with the LO shifted 90°), giving I and Q at DC.\n"
           "If the LO is exactly on the carrier, I is the carrier's amplitude (sign = the BPSK bit) and Q is zero; a phase error shows up in Q.  The loop (orange) feeds sign(I)·Q, which is the phase error\n"
           "with the BPSK ambiguity removed, through a PI filter to the VCXO; the synthesizer multiplies the VCXO by 232, so the LO follows.  The loop is slow (3 kHz) on purpose: a 10 ns flip is far too\n"
           "brief for it to notice, so the carrier phase reference survives the data.  Every U.FL tap (12 of them) lets you look at a node on a scope: I MON, Q MON, ERR MON, VC MON, LO RX MON, REF OUT ...",
           fs=8.5, title="How to read this", fc="#eef7ee", ec="#7a7")
    c.note(W - 20, 70, "fast path: %.0f MHz, noise floor %.1f dBm (NF %.1f dB), comparator floor %.0f dBm\nslow path: %.1f MHz, noise floor %.1f dBm, comparator floor %.0f dBm: quiet from %.0f dBm\n10 m bench link: %.1f dBm, SNR %.0f dB in the fast arm\nfast latency jack-to-register: %.1f ns PYNQ, %.1f ns Icepi; slow confirm +%.0f ns\nloop: f_n 3 kHz, ζ 0.7, pull ±%.0f kHz\npower: %.2f A from 5 V (both chains)"
           % (B["B_MHz"], B["noise_floor_dBm"], B["nf_chain_dB"], B["floor_fast_dBm"], B["B_slow_MHz"], B["noise_floor_slow_dBm"], B["floor_slow_dBm"], B["noise_floor_slow_dBm"] + QUIET,
              B["link_rows"][1][3], B["link_rows"][1][4], B["latency_ns"] - 8.5, B["latency_icepi_ns"] - 4.1, B["slow_t50_ns"], P["vcxo_pull_ppm"] * 5.8, B["I_total_mA"] / 1e3),
           ha="right", fs=8, title="The numbers (sim/budget.py)")
    c.save("block_rx")


def block_tx():
    W, H = 1000, 560
    c = Canvas(W, H, "Transmitter",
               "Four FPGA pins set which point of the constellation the carrier sits at; the modulator puts it on 5.8 GHz.  Idle is a plain carrier at 0°.  A bit is a brief move to another point.  sim/budget.py sections 1, 2, 5.")
    y = 400
    lv = B["dac_levels"]
    fpga = c.block(20, y - 30, 90, 60, "FPGA", "TX_I1, TX_I0,\nTX_Q1, TX_Q0\n3.3 V CMOS, FAST slew")
    lad = c.block(170, y - 30, 120, 60, "Resistor ladders", "2 x (2.2 k, 2.2 k, 300 Ω to Vr)\nVr = %.2f V from the DAC\nthree levels per axis" % B["dac_Vr"])
    mod = c.block(360, y - 30, 130, 60, "I/Q modulator", "ADL5375-05\n0.4-6 GHz, 750 MHz baseband\nbias 0.5 V, LO 0 dBm")
    gb = c.block(560, y - 30, 100, 60, "Gain block", "ADL5611\n+%.1f dB, P1dB +%.0f dBm\n43 nH bias tee" % (P["gb_gain_dB"], P["gb_p1db_dBm"]))
    pad = c.block(720, y - 30, 80, 60, "Pad + coupler", "pi pad (0 Ω fitted)\n-20 dB coupled line\n→ TX MON U.FL")
    ant = c.block(870, y - 30, 90, 60, "TX ANT", "SMA, 50 Ω\n%+.1f dBm" % B["tx_out_dBm"])
    arrows = [
        (fpga, lad, C_LOGIC, "two bits per axis, 0 / 3.3 V\nedge 1.5 ns (+4.4 ns through the PYNQ's 200 Ω,\nnone on the Icepi)\n00 → -a, 01/10 → 0, 11 → +a", lambda a: t_logic(a, ((0.3, 1), (0.55, 0))), "TX_I1 (bit 1)"),
        (lad, mod, C_CTL, "IBBP / QBBP: %.2f / %.2f / %.2f V (DC levels!)\nIBBN / QBBN held at 0.54 V\n→ differential ±%.2f V about 0, 0-1 V allowed\nnode %.0f Ω, 3 pF: 1.6 ns" % (lv[0], lv[1], lv[2], lv[2] - lv[1], B["dac_Znode"]), t_ladder, "ladder node: three DC levels"),
        (mod, gb, C_RF, "%s\ncarrier feedthrough %.1f dBm (nulled by Vr)\n5.8 GHz, 1.5 pF DC block" % (fmt_level(B["tx_mod_out_dBm"]), P["mod_carrier_feedthrough_dBm"]), lambda a: t_carrier_flip(a), "the carrier with a flip"),
        (gb, pad, C_RF, "%s\n%.0f dB below P1dB" % (fmt_level(B["tx_out_dBm"]), P["gb_p1db_dBm"] - B["tx_out_dBm"]), lambda a: t_spectrum(a, "line"), "spectrum: a line, flips add skirts"),
        (pad, ant, C_RF, "%s to the antenna\n(or to the PA, or to SW TX)\nTX MON: %.1f dBm" % (fmt_level(B["tx_out_dBm"]), B["tx_out_dBm"] - 20), lambda a: t_carrier_flip(a, kind="qpsk"), "a QPSK symbol: 45° step"),
    ]
    for k, (a, b, col, text, th, cap) in enumerate(arrows):
        c.arrow(a["r"], b["l"], color=col)
        xm = (a["r"][0] + b["l"][0]) / 2
        above = (k % 2 == 0)
        c.note(xm, y + 36 if above else y - 36, text, ha="center", va="bottom" if above else "top", fs=7)
        c.thumb(xm - 14, (y - 70) if above else (y + 42), 28, 18, th, caption=cap)
    # LO chain
    tcxo = c.block(200, 220, 100, 56, "TCXO", "25 MHz ±%.1f ppm\n(or REF IN / REF OUT\nby jumper JP201)" % P["tcxo_ppm"])
    synth = c.block(mod["x"] + 15, 220, 100, 56, "Synthesizer", "MAX2871 x232\nloop %.0f kHz\nMUX: lock detect" % (B["pll_fc"] / 1e3))
    c.arrow(tcxo["r"], synth["l"], color=C_LO)
    c.note((tcxo["r"][0] + synth["l"][0]) / 2, 282, "25 MHz CMOS square\n±2.5 ppm = ±14.5 kHz at 5.8 GHz:\ntwo boards differ by < 29 kHz, inside the\nfar loop's ±580 kHz pull", ha="center", fs=7)
    c.thumb((tcxo["r"][0] + synth["l"][0]) / 2 - 14, 196, 28, 18, lambda a: t_square(a, 4), caption="reference")
    c.arrow(synth["t"], (synth["t"][0], mod["b"][1]), color=C_LO)
    c.note(synth["t"][0] + 6, 300, "LO 5.8 GHz, 0 dBm differential\nthe modulator's carrier", fs=7)
    c.thumb(synth["t"][0] - 44, 290, 28, 18, lambda a: t_lo(a), caption="LO")
    # constellation legend
    pts = [(1, 0), (-1, 0), (0.707, 0.707), (-0.707, 0.707), (-0.707, -0.707), (0.707, -0.707), (0, 0)]
    c.thumb(640, 215, 60, 60, lambda a: t_constellation(a, pts, ["idle", "BPSK", "QPSK 11", "QPSK 01", "QPSK 00", "QPSK 10", "OOK off"], idle=0), caption="the nine ladder points, the ones used")
    c.note(720, 215, "Idle: I = +a, Q = 0 (circled).  The far loop locks to this.\nBPSK: I → -a (a 180° flip; the receiver's sign(I) inverts).\nQPSK: (±a, ±a), i.e. ±45°/±135°: sign(I) is one bit, sign(Q) the other; the Q window says 'a symbol is here'.\nFSK: the four points in turn, +90° per step: the receiver sees (I,Q) rotate and reads the direction from the order of the edges.\nOOK: (0, 0), the carrier off (for comparison with the old envelope-detector link).\nThe ladder's third level per axis (0) is what makes FSK and OOK possible on the same pins.",
           fs=7.5, title="The constellation")
    c.note(20, 60, "Follow the arrows: two FPGA pins per axis drive a 3-resistor ladder whose node is one of three DC voltages; the modulator's input is DC-coupled and biased at 0.5 V, so the\n"
           "DC level IS the baseband signal (there is no 'symbol clock': the carrier moves the moment a pin moves).  The modulator multiplies I by the LO and Q by the LO shifted 90° and adds\n"
           "them: the carrier's phase is atan2(Q, I) and its amplitude sqrt(I²+Q²).  The gain block brings it to +9.8 dBm; the coupler siphons 1 % to a monitor jack.  The TX synthesizer\n"
           "runs on the TCXO: the two boards' carriers differ by at most 29 kHz, which the receiving Costas loop removes.  Triggers (TRIG A/B out, TRIG IN) are on the same sheet for time-stamping.",
           fs=8.5, title="How to read this", fc="#eef7ee", ec="#7a7")
    c.save("block_tx")


def block_loop():
    W, H = 900, 620
    c = Canvas(W, H, "The Costas loop as a control system",
               "A phase-locked loop whose phase detector ignores 180° flips.  Numbers from sim/budget.py section 6; the plots are the textbook second-order loop with these numbers.")
    N = B["loop_N"]; Ko = B["loop_Ko"]; Kd = B["loop_Kd"]; R1 = B["loop_R1"]; R2 = B["loop_R2"]; Cc = B["loop_C"]
    y = 440
    pd = c.block(60, y - 30, 150, 60, "Phase detector", "ADL5380 + sign(I)·Q\nK_d = %.2f V/rad\n(at the comparator level)" % Kd)
    lf = c.block(300, y - 30, 160, 60, "Loop filter F(s)", "PI: (1 + s R2 C) / (s R1 C)\nR1 %.1f k, R2 %.0f Ω, C %.0f nF\nOPA2187 integrator + HOLD" % (R1 / 1e3, R2, Cc * 1e9))
    vco = c.block(550, y - 30, 160, 60, "VCO", "VCXO x %d (MAX2871)\nK_o = 2π·%d·%.0f Hz/V\n= %.2e rad/s/V" % (N, N, P["vcxo_pull_ppm"] * 25, Ko))
    c.arrow(pd["r"], lf["l"], color=C_CTL); c.arrow(lf["r"], vco["l"], color=C_CTL)
    c.wire([vco["r"], (vco["r"][0] + 40, vco["r"][1]), (vco["r"][0] + 40, y - 90), (pd["b"][0], y - 90), pd["b"]], color=C_LO)
    c.label(pd["b"][0] + 6, y - 86, "LO phase θ_o back to the demodulator (the 'minus' input: error = θ_i - θ_o)", fs=8, ha="left")
    c.arrow((pd["l"][0] - 50, pd["l"][1]), pd["l"], color=C_RF)
    c.label(pd["l"][0] - 52, pd["l"][1] + 6, "carrier phase θ_i", fs=8, ha="left")
    c.note(255, y + 36, "error voltage: K_d·sin(θ_i - θ_o)·sign(cos(θ_i - θ_o))\nzero at 0 AND at 180°: a BPSK flip is invisible", ha="center", fs=7)
    c.note(505, y + 36, "VC: 0.3-3.0 V, 1.65 V at centre\nslews at most ±580 kHz of LO", ha="center", fs=7)
    wn = 2 * math.pi * 3000.0; zeta = 0.7
    c.note(60, 330, "Open loop:  G(s) = K_d · F(s) · K_o / s\nwith F(s) = (1 + s τ2) / (s τ1),  τ1 = R1 C = %.0f µs,  τ2 = R2 C = %.0f µs\n\nClosed loop (second order):  ω_n = sqrt(K_d K_o / τ1) = 2π · %.0f Hz,   ζ = ω_n τ2 / 2 = %.2f\n\nWhat the numbers mean:\n• 3 kHz: the loop corrects phase in ~100 µs, follows oscillator drift and the TCXO offset (29 kHz, inside the ±580 kHz pull),\n  and is 30,000 times slower than a 10 ns symbol, so the symbols do not move it.\n• ζ = 0.7: settles without ringing; 2 %% overshoot.\n• Hold range ±580 kHz (the VCXO's pull); pull-in from anywhere inside it, in ~ (Δf)² / ω_n³ … a few ms at worst.\n• Phase noise of the LO inside 3 kHz is cleaned up by the loop (it follows the far carrier); outside, it is the MAX2871's own (-109 dBc/Hz in-band, 80 kHz PLL).\n• Lock is 0° or 180°: both are stable; the data appears inverted in one of them.  The gateware defines 'idle' = the level it sees after lock, and an event is a change."
           % (R1 * Cc * 1e6, R2 * Cc * 1e6, wn / 2 / math.pi, zeta), fs=8.5, va="top", title="The transfer function")
    # plots: S-curve, step response, closed-loop Bode
    def step(a):
        t = np.linspace(0, 2e-3, 800)
        wd = wn * math.sqrt(1 - zeta ** 2)
        y = 1 - np.exp(-zeta * wn * t) * (np.cos(wd * t) + zeta / math.sqrt(1 - zeta ** 2) * np.sin(wd * t))
        a.plot(t * 1e3, y, color=C_CTL, lw=1.2)
        a.axhline(1, color="#999", lw=0.5, ls=":")
        a.set_xlabel("ms", fontsize=6); a.set_ylabel("phase (of a step)", fontsize=6)
        a.tick_params(labelsize=6)
    def bode(a):
        f = np.logspace(1, 6, 400)
        s = 1j * 2 * np.pi * f
        Hc = (2 * zeta * wn * s + wn ** 2) / (s ** 2 + 2 * zeta * wn * s + wn ** 2)
        a.semilogx(f, 20 * np.log10(np.abs(Hc)), color=C_CTL, lw=1.2)
        a.axvline(3000, color="#999", lw=0.5, ls=":")
        a.axvline(1e8, color=C_RF, lw=0.8, ls="--")
        a.set_xlabel("Hz", fontsize=6); a.set_ylabel("dB", fontsize=6)
        a.set_ylim(-60, 10); a.tick_params(labelsize=6)
        a.text(3500, -50, "3 kHz loop", fontsize=6); a.text(1.2e8 / 20, -35, "a 10 ns symbol\nlives at 100 MHz", fontsize=6, color=C_RF, ha="right")
    def scurve(a):
        t_scurve(a)
        a.set_xlabel("phase error, rad", fontsize=6); a.set_ylabel("error / K_d", fontsize=6); a.tick_params(labelsize=6)
    for k, (fn, cap) in enumerate(((scurve, "the detector's S-curve: stable at 0 and ±π"), (step, "closed-loop step response (f_n 3 kHz, ζ 0.7)"), (bode, "closed-loop |H(f)|: what the loop follows"))):
        a = c.fig.add_axes([(480 + k * 135) / W, 235 / H, 115 / W, 80 / H])
        a.set_facecolor("#fafafa")
        fn(a)
        c.label(480 + k * 135 + 57, 230, cap, fs=7, color="#444")
    c.note(60, 60, "Why a Costas loop and not a plain PLL: a PLL on a BPSK signal sees the carrier flip 180° at every bit and loses lock.  The Costas detector multiplies the Q arm by the SIGN of the I arm:\n"
           "flipping the carrier flips both, so the product does not change.  Here the multiplication is an analogue switch (74LVC1G3157) selecting +Q or -Q under the comparator's sign(I): a 'hard-limited'\n"
           "Costas loop, the cheapest and the one whose S-curve is drawn above.  The loop filter is a PI (proportional + integral): the integral term drives the steady-state phase error to zero even with\n"
           "a frequency offset (the TCXO's 29 kHz).  The HOLD switch opens the integrator's input when the FPGA knows the carrier is absent (our own TX in T/R mode): VC stays where it was and the LO\n"
           "coasts on the VCXO's stability (1e-9 over a microsecond = 6 Hz: nothing).  LOOP_SEL = FPGA turns the detector into a plain Q-only PLL, for comparison in the lab.",
           fs=8.5, title="For the students", fc="#eef7ee", ec="#7a7")
    c.save("block_loop")


def block_modulations():
    W, H = 1150, 800
    c = Canvas(W, H, "Five ways to send a bit, and what each costs",
               "Rows: the schemes.  Columns: what the FPGA does, where the carrier goes, what the receiver's I/Q and comparators see, the spectrum, the SNR each needs, how far it reaches.  sim/link_rates.py.")
    rows = [("BPSK", "idle +a → flip I to -a\n(TX_I1,I0: 11 → 00)", "bpsk", "sign(I) flips:\nCMP_I = the bit", (1, 0), (-1, 0)),
            ("QPSK", "two bits at once: (±a, ±a)\n45° / 135° / 225° / 315°", "qpsk", "Q window fires (symbol here);\nsign(I), sign(Q) = the bits", (1, 0), (0.707, 0.707)),
            ("FSK", "step through the four\npoints, +90° each", "fsk", "(I,Q) rotates; the order of\nthe CMP_I / CMP_Q edges = direction", (1, 0), (0, 1)),
            ("OOK", "(0, 0): carrier off\n(the old envelope link)", "ook", "I drops to 0; a window on |I|\n(needs an amplitude threshold)", (1, 0), (0, 0)),
            ("whitened\nstream", "an LFSR scrambles a\ncontinuous 100 Mbaud BPSK stream;\nthe bit is XORed in when it comes", "bpsk", "a symbol clock recovered from\nthe transitions; descrambler", (1, 0), (-1, 0))]
    schemes = ["BPSK", "QPSK", "FSK", "OOK", "whitened"]
    y0 = H - 70; rh = 108
    cols = [20, 120, 260, 400, 540, 680, 800, 950]
    heads = ["scheme", "the transmitter", "constellation path", "RF (time)", "receiver I and Q", "comparators", "spectrum", "needs / reaches"]
    for x, h in zip(cols, heads):
        c.label(x, y0 + 6, h, fs=11, weight="bold", ha="left")
    for r, (name, txd, kind, rxd, p0, p1) in enumerate(rows):
        y = y0 - (r + 1) * rh
        c.ax.add_patch(Rectangle((15, y), W - 30, rh - 6, fc="#f7f8fa" if r % 2 else "white", ec="#ddd", lw=0.5))
        c.label(cols[0], y + rh / 2, name, fs=20, weight="bold", ha="left")
        c.label(cols[1], y + rh / 2, txd, fs=7.5, ha="left")
        c.thumb(cols[2], y + 20, 55, 55, lambda a, p0=p0, p1=p1: (t_constellation(a, [p0, p1] if p1 != p0 else [p0], ["idle", ""] if p1 != p0 else ["idle"], idle=0),
                                                            a.annotate("", xy=p1, xytext=p0, arrowprops=dict(arrowstyle="->", color=C_RF, lw=1)) if p1 != p0 else None))
        c.thumb(cols[3], y + 30, 110, 40, lambda a, kind=kind: t_carrier_flip(a, kind=("bpsk" if kind in ("bpsk",) else "qpsk" if kind == "qpsk" else "fsk" if kind == "fsk" else "bpsk")) if kind != "ook" else
                (a.plot(np.linspace(0, 1, 1200), np.cos(2 * math.pi * 14 * np.linspace(0, 1, 1200)) * (np.linspace(0, 1, 1200) < 0.5), color=C_RF, lw=0.8), a.set_ylim(-1.3, 1.3)))
        c.thumb(cols[4], y + 52, 110, 22, lambda a, kind=kind: t_iq_step(a, "I", kind=kind), caption="I")
        c.thumb(cols[4], y + 18, 110, 22, lambda a, kind=kind: t_iq_step(a, "Q", kind=kind), caption="Q")
        edges = {"bpsk": ((0.5, 1),), "qpsk": ((0.5, 1), (0.65, 0)), "fsk": ((0.5, 1), (0.8, 0)), "ook": ((0.5, 1), (0.65, 0))}[kind]
        c.thumb(cols[5], y + 48, 100, 22, lambda a, e=edges: t_logic(a, e), caption="CMP_I" if kind in ("bpsk",) else "CMP_QP (window)" if kind in ("qpsk", "fsk") else "|I| window")
        c.label(cols[5], y + 30, rxd, fs=7, ha="left", va="top")
        sp = "line" if name != "whitened\nstream" else "sinc"
        c.thumb(cols[6], y + 30, 100, 40, lambda a, sp=sp: t_spectrum(a, sp, bw=0.25 if sp == "sinc" else 0.08), caption="a CW line + brief skirts" if sp == "line" else "200 MHz wide, always on")
        s = LR["schemes"][schemes[r]]
        def pick(sc, path):
            return [rw for rw in LR["scenarios"][sc]["rows"] if rw["scheme"] == schemes[r] and rw["pa_dB"] == 0.0 and rw["path"] == path][0]["d_m"][2]
        def fm(v):
            return ">100 km" if v >= 1e5 else ("%.0f m" % v if v < 1000 else "%.0f km" % (v / 1e3))
        c.label(cols[7], y + rh - 12, "SNR for 1 %%: %.1f dB   quiet: %.1f dB\nlab, whips, no amp: fast %s, slow %s\ncampus, panels, amps at panel: fast %s, slow %s\n%s"
                % (s["1 % wrong"], s["quiet (1e-4)"], fm(pick(0, "fast")), fm(pick(0, "slow")), fm(pick(2, "fast")), fm(pick(2, "slow")),
                   {"BPSK": "lowest SNR; one bit per event", "QPSK": "two bits per event, 3 dB more", "FSK": "noncoherent: 4.6 dB more; longest symbol",
                    "OOK": "no frequency selectivity: 14 dB worse", "whitened": "same energy as BPSK, x3 errors, +14 ns"}[schemes[r]]),
                fs=7.5, ha="left", va="top")
    # the protocol comparison and the range table
    yb = y0 - len(rows) * rh - 20
    c.note(20, yb, "IDLE CARRIER + EVENTS (this board's native mode): the carrier is always on; a bit is a phase (or frequency) change at the instant the FPGA pin moves; the receiver's comparator reports it as soon\n"
           "as the 100 MHz arm filter settles (3.5 ns).  There is no symbol clock, no slot to wait for, no frame.  The price: while idle, every noise excursion past the comparator is a false bit, so the link\n"
           "must be QUIET: ≤ 1e-4 errors per decision (1e4 false events/s at 100 MHz; 1 in 100 trials at 1 MHz) → BPSK needs %.1f dB, not the %.1f dB that 1 %%%% message errors would.  The gateware's dwell\n"
           "requirement (a flip must persist N samples) trades latency for quiet.\n\n"
           "WHITENED STREAM (an LFSR-scrambled continuous BPSK at 100 Mbaud): the receiver recovers a symbol clock from the transitions, integrates each symbol (a matched filter) and descrambles.  Same energy\n"
           "per decision as the idle carrier (the arm filter IS a one-symbol matched filter), so no sensitivity gain; a self-synchronising descrambler triples the errors; the bit waits for the next slot\n"
           "(5 ns average) and a full symbol (10 ns): +%.0f ns of latency; the transmitter is always 200 MHz wide (it interferes with every WiFi channel it touches, and it is what §15.247 wants a digital\n"
           "transmitter to look like).  It does NOT help against interference: spreading gain is zero when chips = bits.  Where it helps: when the receiver is a conventional slotted detector that needs a\n"
           "clock; a continuous quality estimate.  Both run on this hardware unchanged (the FPGA drives the ladders), so the comparison is an experiment, not a design decision.  Interference robustness\n"
           "comes from elsewhere: the arm bandwidth (narrower = quieter = slower), the antennas' directivity (24 dBi panels reject 20-30 dB off-axis), transmit power, and the channel (UNII-2C 5.47-5.725 GHz\n"
           "is nearly empty indoors; scan with the B210 first)." % (QUIET, ONE_PCT, LR["latency"]["whitened_extra_ns"]), fs=8, va="top", title="Idle carrier against a whitened stream: which is lower latency, which is more robust")
    # a compact range table: scenarios x amplifiers for BPSK quiet
    tx0 = 20; ty = yb - 66
    c.label(tx0, ty + 4, "Range at which BPSK stays quiet (1e-4 per decision), metres: the fast path (flags) / the slow path (confirms), with the old OOK link in brackets.  Free space + margin; the shorter of noise and the comparator floor.", fs=9, weight="bold", ha="left")
    pas = [rw["amplifier"] for rw in LR["scenarios"][0]["rows"] if rw["scheme"] == "BPSK" and rw["path"] == "fast"]
    c.label(tx0, ty - 8, "%-52s" % "scenario" + "".join("%30s" % p for p in pas), fs=7.5, ha="left", va="top")
    f = lambda v: ">100 km" if v >= 1e5 else ("%.0f" % v if v < 1e4 else "%.0f km" % (v / 1e3))
    for k, sc in enumerate(LR["scenarios"]):
        vals = []
        for p in pas:
            bf = [rw for rw in sc["rows"] if rw["scheme"] == "BPSK" and rw["amplifier"] == p and rw["path"] == "fast"][0]["d_m"][2]
            bs = [rw for rw in sc["rows"] if rw["scheme"] == "BPSK" and rw["amplifier"] == p and rw["path"] == "slow"][0]["d_m"][2]
            o = [rw for rw in sc["rows"] if rw["scheme"] == "OOK" and rw["amplifier"] == p and rw["path"] == "slow"][0]["d_m"][2]
            vals.append("%s / %s (%s)" % (f(bf), f(bs), f(o)))
        c.label(tx0, ty - 18 - k * 9, "%-52s" % sc["name"] + "".join("%30s" % v for v in vals), fs=7.5, ha="left", va="top")
    c.label(tx0, ty - 18 - 4 * 9 - 2, "Through walls at 30 m with whips and no amplifier the slow path has %.0f dB to spare (drywall 3-6 dB, brick 10-15, a floor 15-25).  The USB-C amplifier's output is a guess until measured: the TX MON jack and the ADC read it." % LR["walls_dB_at_30m"], fs=7.5, ha="left", va="top")
    c.save("block_modulations")


def block_system():
    W, H = 1100, 700
    c = Canvas(W, H, "The link: two stations, the air between, and the time it takes",
               "Quantum position verification: a verifier sends a 2-bit basis, the prover measures and answers 1-2 bits; what matters is that the answer leaves the instant the measurement is done.  The radio adds a fixed ~%.0f ns to each hop." % B["latency_ns"])
    y = 520
    v_fpga = c.block(30, y - 35, 110, 70, "Verifier FPGA", "PYNQ-Z2 or Icepi Zero\nsends the basis;\ntime-stamps the answer")
    v_brd = c.block(190, y - 35, 150, 70, "CostasLink board", "TX: ladders → ADL5375 → +9.8 dBm\nRX: LNA → ADL5380 → Costas loop")
    v_ant = c.block(390, y - 35, 90, 70, "Antennas", "TX and RX panels\n24 dBi, or whips\n(or one, via the switch)")
    p_ant = c.block(620, y - 35, 90, 70, "Antennas", "RX and TX panels\n24 dBi")
    p_brd = c.block(760, y - 35, 150, 70, "CostasLink board", "the same board\n(the prover's reply is coherent\nwith the verifier's carrier in T/R mode)")
    p_fpga = c.block(960, y - 35, 110, 70, "Prover FPGA", "reads the basis, fires\nthe measurement,\nsends the result")
    for a, b, col in ((v_fpga, v_brd, C_LOGIC), (v_brd, v_ant, C_RF), (p_ant, p_brd, C_RF), (p_brd, p_fpga, C_LOGIC)):
        c.arrow(a["r"], b["l"], color=col)
        c.arrow((b["l"][0], b["l"][1] - 14), (a["r"][0], a["r"][1] - 14), color=col)
    c.arrow((v_ant["r"][0], y + 8), (p_ant["l"][0], y + 8), color=C_RF)
    c.arrow((p_ant["l"][0], y - 8), (v_ant["r"][0], y - 8), color=C_RF)
    c.note(550, y + 44, "over the air: 5.8 GHz (5.15-5.875 GHz usable), each direction its own frequency (two antennas) or the same one in turns (one antenna + switch)\n"
           "path loss: %.0f dB at 10 m, %.0f dB at 300 m, %.0f dB at 20 km (free space)\nflight time 3.34 ns per metre: 33 ns across the lab, 1 µs across campus, 67 µs to a mountain 20 km away\n"
           "with 24 dBi panels both ends and no amplifier: %.0f dBm at 20 km (SNR %.0f dB in %.0f MHz; the slow path confirms from 20 dB further)" % (B["link_rows"][1][2], B["link_rows"][3][2], B["link_rows"][6][2], B["link_rows"][6][3], B["link_rows"][6][4], B["B_MHz"]), ha="center", fs=7.5)
    c.thumb(535, y - 70, 30, 18, lambda a: t_spectrum(a, "line"), caption="each carrier: a line")
    c.note(265, y + 44, "FPGA ↔ board: 3.3 V CMOS on the 40-pin header\nTX: 4 ladder bits; RX: 3 comparator lines\n+ SPI, I2C, HOLD, SEL, TRIG, T/R", ha="center", fs=7.5)
    c.note(835, y + 44, "the same signals mirrored\nCMP_I on pin 18 and TRIG_IN on 26 are\nclock-capable on both FPGA boards", ha="center", fs=7.5)
    # the timeline
    ty = 380
    c.label(30, ty + 22, "The round trip, in nanoseconds (10 m across the lab)", fs=13, weight="bold", ha="left")
    segs = [("verifier FPGA pin moves", 0, 0, C_LOGIC), ("TX electronics", 0, 9.8, C_CTL), ("flight 10 m", 9.8, 33.4, C_RF), ("RX electronics to the prover's register", 33.4, 14.3, C_BB),
            ("prover decides, measures, answers (the quantity under test)", 57.5, 10, "#999"), ("TX electronics", 67.5, 9.8, C_CTL), ("flight 10 m", 77.3, 33.4, C_RF), ("RX electronics to the verifier's register", 110.7, 14.3, C_BB)]
    scale = 7.0
    for name, t0, dt, col in segs:
        c.ax.add_patch(Rectangle((40 + t0 * scale, ty - 10), max(dt * scale, 1.5), 16, fc=col, ec="none", alpha=0.75))
        c.label(40 + (t0 + dt / 2) * scale, ty - 20, "%.0f" % dt if dt else "", fs=7)
        c.label(40 + (t0 + dt / 2) * scale, ty + 12, name, fs=6.5, rot=20, ha="left", va="bottom")
    c.ax.plot([40, 40 + 125 * scale], [ty - 10, ty - 10], color="#333", lw=0.8)
    for tt in range(0, 126, 25):
        c.ax.plot([40 + tt * scale] * 2, [ty - 12, ty - 10], color="#333", lw=0.8); c.label(40 + tt * scale, ty - 16, "%d ns" % tt, fs=6.5, va="top")
    c.note(40, ty - 80, "Electronics per hop: %.1f ns on the PYNQ-Z2 (8.8 ns of it is the PYNQ's 200 Ω header resistors, twice), %.1f ns on the Icepi Zero; sim/budget.py section 5 itemises it.  "
           "The old OOK link budgeted 10-100 ns for its envelope detector.\nIn one-antenna T/R mode each station's switch adds 30 ns (HMC536) before it can answer; a 1 µs switch (SKY13453) would be 15 round trips of the lab."
           % (B["latency_ns"], B["latency_icepi_ns"]), fs=7.5)
    # antenna arrangements
    ay = 180
    c.label(30, ay + 90, "Three ways to point antennas", fs=13, weight="bold", ha="left")
    c.note(30, ay, "TWO ANTENNAS PER LINK, TWO FREQUENCIES (full duplex)\n• this is what the board does with nothing added: TX ANT and RX ANT\n• both carriers on all the time: both loops locked, no holds, no turnaround\n• TX→RX isolation needed in the same band: 60-70 dB (sim/budget.py §4), which two panels side by side (~40 dB) plus 600 MHz of separation (the arm filter's 31 dB) give\n• the four panels = one link, exactly\n• 3 directions: 6 panels, 6 channels; with the arm filter at 50 MHz they fit 5.15-5.85 GHz",
           fs=7.5, va="top", title="1.  Two antennas")
    c.note(390, ay, "ONE ANTENNA PER DIRECTION, SAME FREQUENCY, IN TURNS (T/R, half duplex)\n• the on-board HMC536 block: ANT, SW TX, SW RX jacks, TR_A/TR_B from the FPGA\n• 30 ns to switch, 27 dB isolation, +29 dBm; the far loop HOLDs while we transmit\n• the reply carrier must already be on frequency: REF OUT → REF IN makes the prover a coherent transponder (its TX synthesizer runs on the VCXO the loop steers)\n• with a PA: a limiter ahead of the LNA (0 dBm leaks through the switch at +27 dBm)\n• 3 directions: 3 panels, 3 channels (or 1 channel if the schedule never overlaps)",
           fs=7.5, va="top", title="2.  One antenna and the switch")
    c.note(750, ay, "WHAT FREQUENCY MULTIPLEXING BUYS\n• each link needs ~200 MHz (the ±100 MHz arm filter) to be deaf to its neighbour by 14 dB, 600 MHz to be deaf by 31 dB\n• the usable span 5.15-5.875 GHz is 725 MHz: three or four 200 MHz channels, six at 100 MHz spacing with a 50 MHz arm filter (+3.5 ns)\n• ISM 5.725-5.875 alone holds one link; the UNII bands (5.15-5.725) the others — DFS radar-detection rules apply to 5.25-5.725 for licensed-exempt gear; an amateur licence (5.65-5.925 GHz, 5 cm band) is the clean way to run the PAs\n• beyond that, it is the switch again: time division at 30 ns",
           fs=7.5, va="top", title="3.  The band")
    c.save("block_system")


def main():
    np.random.seed(0)
    block_rx(); block_tx(); block_loop(); block_modulations(); block_system()
    return 0


if __name__ == "__main__":
    sys.exit(main())
