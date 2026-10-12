#!/usr/bin/env python3
"""From the idle to each of the four QPSK corners at the receiver: I and Q against time, the fast and
slow comparators, the path on the I/Q plane, and the same with the receiver's noise (Jason, Prompt 18).
docs/TRAJECTORIES.md explains the figures.

    python3 sim/trajectories.py        docs/images/traj_*.png and build/trajectories.json

Every number is the board's own: build/budget.json (sim/budget.py) for the levels, the poles and the
SNRs, and the driver's Scheme "A3" (gateware/driver/costaslink.py) for the comparators the gateware
reads and the table it decides with.  The model, from the FPGA's TX register to the comparators:

  transmitter  the PYNQ's 200 ohm into ~10 pF at the header, the resistor ladder's node (240 ohm, 3 pF),
               the ADL5375's 750 MHz baseband: three first-order poles
  fixed delay  the FPGA's output buffer, the gain blocks and lines (sim/budget.py section 5): 3.1 ns;
               the air is left out (a cable): add 3.34 ns a metre
  receiver     the ADL5380's 390 MHz baseband and the THS4541 at gain 4, noise gain 9: 850 MHz / 9
               = 94 MHz, two first-order poles.  The noise enters here (the LNA's), white, filtered
               by these two poles only
  comparators  TLV3601: 2.5 ns, 3 mV of hysteresis (typical; budget.json parts.cmp_hyst_typ_mV).  The fast path's five: CMP_I = sign(I), the
               windows CMP_QP / CMP_QN = Q above +t a / below -t a, CMP_IP / CMP_IN the same for I
  slow path    the fast arm's differential x20 in a second THS4541 (850 / 21 = 40 MHz), its legs
               clipped at 0.2 and 3.1 V (its output swing on 3.3 V), then 1 k / 33 pF on each leg
               (4.8 MHz); CMP_I_S = sign, CMP_QP_S / CMP_QN_S = one leg above V_T2 = 1.65 V + t2 (20 a) / 2
  the FPGA     each comparator's edge reaches it 1.6 ns later (33 + 200 ohm into 10 pF, to 50 %), and
               it samples every 1.25 ns (800 Ms/s): the event is the first sample with CMP_QP or
               CMP_QN off its idle value, the decision the five comparators 4 samples later through
               A3's table (the driver's defaults)

The SNR is the budget's: the carrier against kTF in 100 MHz, which makes a / sigma = sqrt(snr) per
quadrature (sim/constellations.py).  The model's two poles pass 119 MHz of noise, not 100, so its
sigma is 0.4 dB higher than that convention's; the figures use the model's.
"""
import json, math, os, sys
import numpy as np
from scipy.signal import lfilter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "gateware", "driver"))
import costaslink as CL                                         # noqa: E402  the driver's Scheme A3

B = json.load(open(os.path.join(ROOT, "build", "budget.json")))
P = B["parts"]
OUT = os.path.join(ROOT, "docs", "images")

# ---- the chain ------------------------------------------------------------------------------------
A = B["vcmp_rms"] * math.sqrt(2)                 # V: the axis amplitude a, differential at the comparators
TAU_TX = [P["hdr_R_ohm"] * P["hdr_C_pF"] * 1e-12,  # the PYNQ header's 200 ohm into 10 pF
          B["dac_Znode"] * 3e-12,                 # the ladder's node, 240 ohm and 3 pF
          1 / (2 * math.pi * 750e6)]              # the ADL5375's baseband
TAU_RX = [1 / (2 * math.pi * P["dem_bw_MHz"] * 1e6),   # the ADL5380's baseband
          1 / (2 * math.pi * B["fda_bw_MHz"] * 1e6)]   # the THS4541 at noise gain 9
T_FIXED = (1.5 + 0.5 + 1.1) * 1e-9               # FPGA output buffer; TX gain block and lines; RX front end
CMP_TPD = P["cmp_tpd_ns"] * 1e-9
CMP_HYS = P["cmp_hyst_typ_mV"] / 1e3            # TLV3601: 3 mV typ (1.5-5) at its input (sim/budget.py)
G_SLOW = B["G_slow"]
TAU_SLOW_FDA = 1 / (2 * math.pi * B["slow_bw_MHz"] * 1e6)
TAU_SLOW_RC = B["slow_Rrc"] * B["slow_Crc"]
V_MID, V_LO, V_HI = 1.65, 0.2, 3.1               # the THS4541's output swing on 3.3 V: 0.2 V from each rail
T_HDR = (33.0 + P["hdr_R_ohm"]) * P["hdr_C_pF"] * 1e-12 * math.log(2)   # comparator edge to the FPGA's 50 %
T_SAMPLE = 1.25e-9                               # 800 Ms/s on the PYNQ
DEC_DELAY = 4                                    # samples from the event to the decision (rx_config's default)

SCHEME = CL.SCHEMES["A3"]                         # idle (1, 0); the corners; event on QP / QN
T2 = SCHEME.t2                                   # the slow window: 0.1 a

DT = 10e-12
T0, T1 = -400e-9, 150e-9                          # the noise settles from -400 ns; the figures show -15 to 100
t = np.arange(int(round((T1 - T0) / DT))) * DT + T0
TNS = t * 1e9

ROWS = {r[0]: r for r in B["link_rows"]}
CASES = [("lab", "10 m, 2 dBi whips (the bench)", B["link_rows"][1][4]),
         ("3 km", "3 km, 24 dBi panels, 10 m cables", B["link_rows"][4][4])]
CORNERS = [((1, 1), "I+ Q+"), ((1, -1), "I+ Q-"), ((-1, 1), "I- Q+"), ((-1, -1), "I- Q-")]
NRUNS = 40
RNG = np.random.default_rng(18)
FA_RATE = 1.0 / 3600


def pole(x, tau):
    """one first-order low-pass, exact for a signal held over each DT"""
    k = 1.0 - math.exp(-DT / tau)
    return lfilter([k], [1.0, -(1.0 - k)], x, axis=-1, zi=None) if np.ndim(x) == 1 else \
        lfilter([k], [1.0, -(1.0 - k)], x, axis=-1)


def chain(x, taus):
    for tau in taus:
        x = pole(x, tau)
    return x


def settle_poles(x, taus):
    """the same, started in its steady state for the first sample (the idle has been there forever)"""
    for tau in taus:
        k = 1.0 - math.exp(-DT / tau)
        zi = (1.0 - k) * x[..., :1]
        x = lfilter([k], [1.0, -(1.0 - k)], x, axis=-1, zi=zi)[0]
    return x


# the step response g(t): 0 before the edge reaches the receiver, 1 at the end
step = (t >= T_FIXED).astype(float)
G = chain(step, TAU_TX + TAU_RX)


def t_cross(g_level, g=G):
    i = int(np.argmax(g >= g_level))
    return t[i - 1] + (g_level - g[i - 1]) / (g[i] - g[i - 1]) * DT


T10, T50, T90 = (t_cross(x) for x in (0.1, 0.5, 0.9))
G_RXONLY = chain(step, TAU_RX)
T10R, T90R = t_cross(0.1, G_RXONLY), t_cross(0.9, G_RXONLY)

# the arm's noise: white, through the receiver's two poles; scaled so that snr = a^2 / (N0 x 100 MHz)
imp = np.zeros(4000); imp[0] = 1.0
H = chain(imp, TAU_RX)
SUM_H2 = float(np.sum(H ** 2))
ENBW = SUM_H2 / (2 * DT)                          # one-sided noise bandwidth of the two poles, Hz
f = np.fft.rfftfreq(len(H), DT)
HF = np.abs(np.fft.rfft(H))
NU0 = math.sqrt(np.sum(f ** 2 * HF ** 2) / np.sum(HF ** 2))   # Rice: the noise's rms frequency


def sigma(snr_dB):
    """the arm's noise per quadrature (V), for the budget's snr in 100 MHz"""
    n0 = A ** 2 / (10 ** (snr_dB / 10) * 100e6)    # V^2/Hz, one-sided, per quadrature
    return math.sqrt(n0 * ENBW)


def noise(nruns, snr_dB):
    s = sigma(snr_dB)
    w = RNG.standard_normal((2, nruns, len(t)))
    n = settle_poles(w, TAU_RX)
    return n * s / math.sqrt(SUM_H2)


def z_fa(rate=FA_RATE, k=2):
    """sigma from the idle for k comparators to make `rate` false events a second (Rice)"""
    return math.sqrt(2 * math.log(k * NU0 / rate))


# ---- comparators ----------------------------------------------------------------------------------
def comparator(x, th, hys, start=None):
    """TLV3601: high above th + hys / 2, low below th - hys / 2, else as it was; then its 2.5 ns"""
    x = np.atleast_2d(x)
    out = np.zeros(x.shape, dtype=np.int8)
    st = (x[:, 0] > th).astype(np.int8) if start is None else np.full(x.shape[0], start, np.int8)
    hi, lo = x > th + hys / 2, x < th - hys / 2
    for k in range(x.shape[1]):
        st = np.where(hi[:, k], 1, np.where(lo[:, k], 0, st))
        out[:, k] = st
    d = int(round(CMP_TPD / DT))
    out = np.concatenate([np.repeat(out[:, :1], d, axis=1), out[:, :-d]], axis=1)
    return out


def receive(I, Q, tfrac):
    """the fast and slow paths from the fast arm's differential I and Q (V): the comparators' outputs
    (each [runs, samples]) and the slow arm's differential after its RC (V)"""
    th = tfrac * A
    fast = {"CMP_I": comparator(I, 0.0, 2 * CMP_HYS),            # differential in, its 3 mV on both legs' difference
            "CMP_QP": comparator(Q, th, 2 * CMP_HYS),            # one leg against V_TQP: 3 mV on a leg is 6 mV of Q
            "CMP_QN": comparator(-Q, th, 2 * CMP_HYS),
            "CMP_IP": comparator(I, th, 2 * CMP_HYS),
            "CMP_IN": comparator(-I, th, 2 * CMP_HYS)}
    slow = {}
    for name, x in (("I", I), ("Q", Q)):
        y = settle_poles(G_SLOW * np.atleast_2d(x), [TAU_SLOW_FDA])
        legs = [np.clip(V_MID + s * y / 2, V_LO, V_HI) for s in (1, -1)]
        legs = [settle_poles(l, [TAU_SLOW_RC]) for l in legs]
        slow[name] = legs
    vt2 = V_MID + T2 * G_SLOW * A / 2
    sl = {"CMP_I_S": comparator(slow["I"][0] - slow["I"][1], 0.0, CMP_HYS),
          "CMP_QP_S": comparator(slow["Q"][0], vt2, CMP_HYS),
          "CMP_QN_S": comparator(slow["Q"][1], vt2, CMP_HYS)}
    return fast, sl, slow, vt2


def decide(fast, tfrac, rng):
    """the gateware: comparator edges 1.6 ns later at the FPGA, sampled every 1.25 ns from a random
    phase (the transmitter's clock is another board's); the event, then the table 4 samples later.
    Returns [(event time s, decision time s, message or None)] per run."""
    scheme = CL.Scheme("A3t", "", SCHEME.idle, SCHEME.msgs, [CL.CMP_QP, CL.CMP_QN], t=tfrac, t2=T2)
    lut = scheme.lut()
    iv = scheme.idle_vector()
    names = CL.CMP_NAMES
    vec = sum(fast[n].astype(np.int32) << k for k, n in enumerate(names))
    out = []
    shift = int(round(T_HDR / DT))
    for r in range(vec.shape[0]):
        ph = rng.uniform(0, T_SAMPLE)
        ks = np.arange(int((-10e-9 - T0 + ph) / DT), len(t) - shift, int(round(T_SAMPLE / DT)))
        v = vec[r, ks - shift]
        ev = np.nonzero(((v ^ iv) & scheme.mask) != 0)[0]
        if not len(ev):
            out.append((None, None, None)); continue
        e = ev[0]
        d = min(e + DEC_DELAY, len(ks) - 1)
        entry = lut[v[d]]
        out.append((t[ks[e]], t[ks[d]], (entry & 7) if entry & 8 else None))
    return out


# ---- the runs -------------------------------------------------------------------------------------
def run(corner, snr_dB, tfrac, nruns):
    ci, cq = corner
    I0 = A * (1 + (ci - 1) * G)
    Q0 = A * cq * G
    if nruns:
        n = noise(nruns, snr_dB)
        I, Q = I0 + n[0], Q0 + n[1]
    else:
        I, Q = I0[None, :], Q0[None, :]
    fast, sl, slow, vt2 = receive(I, Q, tfrac)
    return dict(I=I, Q=Q, fast=fast, slow_cmp=sl, slow=slow, vt2=vt2)


def edge_time(x):
    """the first 0 -> 1 or 1 -> 0 after t = 0 in a noiseless comparator output, or None"""
    x = x[0]
    k0 = int(np.argmax(t >= 0))
    d = np.nonzero(np.diff(x[k0:]))[0]
    return t[k0 + d[0] + 1] if len(d) else None


def main():
    os.makedirs(OUT, exist_ok=True)
    res = {"a_V": A, "t10_ns": T10 * 1e9, "t50_ns": T50 * 1e9, "t90_ns": T90 * 1e9,
           "rise_10_90_ns": (T90 - T10) * 1e9, "rx_only_rise_ns": (T90R - T10R) * 1e9,
           "enbw_MHz": ENBW / 1e6, "nu0_MHz": NU0 / 1e6, "z_fa": z_fa(), "cases": {}}
    print("a = %.0f mV at the comparators; the step: 10 %% at %.2f ns, 50 %% at %.2f, 90 %% at %.2f (10-90 %.2f ns; the "
          "receiver alone %.2f ns); noise bandwidth %.0f MHz, Rice's nu0 %.0f MHz; 1 false event an hour on two "
          "comparators: %.2f sigma" % (A * 1e3, T10 * 1e9, T50 * 1e9, T90 * 1e9, (T90 - T10) * 1e9, (T90R - T10R) * 1e9,
                                         ENBW / 1e6, NU0 / 1e6, z_fa()))
    for key, label, snr in CASES:
        s = sigma(snr)
        tc = z_fa() * s / A
        res["cases"][key] = dict(label=label, snr_dB=snr, a_over_sigma=A / s, sigma_mV=s * 1e3, t_cfar=tc)
        print("%-5s %-34s snr %.1f dB: a / sigma = %.1f (sigma %.2f mV); the CFAR threshold %.2f sigma = %.3f a"
              % (key, label, snr, A / s, s * 1e3, z_fa(), tc))

    # one threshold for the figures: 3 km's CFAR place, about halfway (the A3 driver default is 0.5)
    tf = res["cases"]["3 km"]["t_cfar"]
    tl = res["cases"]["lab"]["t_cfar"]
    res["t_fig"] = tf
    runs = {}
    for c, name in CORNERS:
        runs[name] = {"clean": run(c, None, tf, 0),
                      "3 km": run(c, CASES[1][2], tf, NRUNS),
                      "lab": run(c, CASES[0][2], tl, NRUNS),
                      "clean_lab": run(c, None, tl, 0)}
    rng = np.random.default_rng(1)
    res["decisions"] = {}
    for name in runs:
        k_want = [m for m, (c, n) in enumerate(CORNERS) if n == name][0]
        row = {}
        for case, tfrac in (("3 km", tf), ("lab", tl)):
            d = decide(runs[name][case]["fast"], tfrac, rng)
            ok = sum(1 for e, dd, m in d if m == k_want)
            ev = [e for e, dd, m in d if e is not None]
            row[case] = dict(right=ok, wrong=sum(1 for e, dd, m in d if m is not None and m != k_want),
                             none=sum(1 for e, dd, m in d if m is None), runs=len(d),
                             event_ns_mean=float(np.mean(ev)) * 1e9 if ev else None,
                             event_ns_sd=float(np.std(ev)) * 1e9 if ev else None,
                             decision_ns_mean=float(np.mean([dd for e, dd, m in d if dd is not None])) * 1e9)
        for case, tfrac in (("clean", tf), ("clean_lab", tl)):
            fr = runs[name][case]
            row[case] = {n: (edge_time(fr["fast"][n]) or float("nan")) * 1e9 for n in fr["fast"]}
            row[case].update({n: (edge_time(fr["slow_cmp"][n]) or float("nan")) * 1e9 for n in fr["slow_cmp"]})
        res["decisions"][name] = row
        print("%s: noiseless edges (3 km thresholds) %s" % (name, ", ".join("%s %.1f" % (n, v) for n, v in row["clean"].items() if v == v)))
        for case in ("3 km", "lab"):
            r = row[case]
            print("   %-4s %d runs: %d right, %d wrong, %d undecided; event %.2f +- %.2f ns, decision %.1f ns"
                  % (case, r["runs"], r["right"], r["wrong"], r["none"], r["event_ns_mean"], r["event_ns_sd"], r["decision_ns_mean"]))
    for c, name in CORNERS:
        figure_time(runs[name], name, tf, tl, res)
    figure_iq(runs, tf, tl, res)
    figure_iq_slow(runs, res)
    figure_latency(res)
    json.dump(res, open(os.path.join(ROOT, "build", "trajectories.json"), "w"), indent=1, default=float)
    return 0


# ---- figures --------------------------------------------------------------------------------------
WIN = (TNS >= -15) & (TNS <= 100)
CI, CQ = "#1f5fbf", "#c8401a"
CS_FAST = {"CMP_I": "#1f5fbf", "CMP_IP": "#5f8fdf", "CMP_IN": "#9fbfef", "CMP_QP": "#c8401a", "CMP_QN": "#e8906a"}
CS_SLOW = {"CMP_I_S": "#1f5fbf", "CMP_QP_S": "#c8401a", "CMP_QN_S": "#e8906a"}


def cross_time(x, level, sign=1):
    """the first time (s) after t = 0 that sign * x rises through sign * level (noiseless curves)"""
    k0 = int(np.argmax(t >= 0))
    y = sign * (x - level)
    k = np.nonzero((y[k0:-1] <= 0) & (y[k0 + 1:] > 0))[0]
    if not len(k):
        return None
    k = k0 + k[0]
    return t[k] + (-y[k]) / (y[k + 1] - y[k]) * DT


def figure_time(r, name, tf, tl, res):
    fig, ax = plt.subplots(4, 1, figsize=(8.0, 14.0), gridspec_kw=dict(height_ratios=[3.2, 2.2, 2.6, 1.5], hspace=0.32))
    ci, cq = [c for c, n in CORNERS if n == name][0]
    Ic, Qc = r["clean"]["I"][0] / A, r["clean"]["Q"][0] / A
    zf = z_fa()
    # (a) the fast arm, zoomed to its own time scale
    a0 = ax[0]
    xf = (TNS >= -2) & (TNS <= 24)
    x = TNS[xf]
    for k in range(NRUNS):
        a0.plot(x, r["3 km"]["I"][k][xf] / A, color=CI, alpha=0.06, lw=0.6)
        a0.plot(x, r["3 km"]["Q"][k][xf] / A, color=CQ, alpha=0.06, lw=0.6)
    a0.plot(x, Ic[xf], color=CI, lw=2.4, label="I")
    a0.plot(x, Qc[xf], color=CQ, lw=2.4, label="Q")
    tx = np.where(x >= 0, 1.0, 0.0)
    a0.plot(x, 1 + (ci - 1) * tx, color=CI, lw=0.9, ls=":", label="what the FPGA sent")
    a0.plot(x, cq * tx, color=CQ, lw=0.9, ls=":")
    for y in (tf, -tf):
        a0.axhline(y, color="0.2", lw=1.0, ls="--")
    for y in (tl, -tl):
        a0.axhline(y, color="0.5", lw=0.9, ls=(0, (1, 2)))
    a0.axhline(0, color="0.3", lw=0.6)
    a0.text(23.7, tf + 0.03, "windows at %.2f a: the 3 km CFAR place (%.1f sigma there)" % (tf, zf), ha="right", va="bottom", fontsize=7.5)
    a0.text(23.7, tl + 0.02, "%.2f a: the bench's CFAR place (%.1f sigma there)" % (tl, zf), ha="right", va="bottom", fontsize=7.5, color="0.35")
    a0.text(23.7, -0.02, "sign(I)", ha="right", va="top", fontsize=7.5)
    a0.axvspan(T10 * 1e9, T90 * 1e9, color="0.85", alpha=0.6, lw=0)
    a0.text((T10 + T90) / 2 * 1e9, -1.3, "10-90 %%: %.1f ns" % ((T90 - T10) * 1e9), ha="center", va="bottom", fontsize=7.5)
    # where the event's comparator crosses at each place: the bench knows earlier
    for th, col, lab in ((tf, "k", "3 km"), (tl, "0.4", "bench")):
        tc = cross_time(Qc, cq * th, cq)
        if tc is not None:
            a0.plot(tc * 1e9, cq * th, "D", color=col, ms=6, zorder=6)
            a0.annotate("%s: Q past its window at %.1f ns" % (lab, tc * 1e9), (tc * 1e9, cq * th),
                        xytext=(-100, 26 * cq) if lab == "bench" else (10, -14 * cq), textcoords="offset points",
                        fontsize=7.5, color=col, arrowprops=dict(arrowstyle="-", color=col, lw=0.6),
                        bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=0.3))
    if ci < 0:
        tc = cross_time(Ic, 0.0, -1)
        a0.plot(tc * 1e9, 0, "D", color=CI, ms=6, zorder=6)
        a0.annotate("I through 0 at %.1f ns,\nwhatever the SNR" % (tc * 1e9), (tc * 1e9, 0), xytext=(12, 30 if cq < 0 else -38),
                    textcoords="offset points", fontsize=7.5, color=CI, arrowprops=dict(arrowstyle="-", color=CI, lw=0.6))
    a0.set_xlim(-2, 24); a0.set_ylim(-1.35, 1.35)
    a0.set_ylabel("fast arm / a   (a = %.0f mV)" % (A * 1e3))
    a0.set_xlabel("ns after the transmitting FPGA's register changes (a cable; add 3.34 ns a metre of air)", fontsize=8)
    a0.legend(loc="center left", fontsize=7.5, framealpha=0.9)
    a0.set_title("Idle (I +a, Q 0) to %s.   (a) the fast arm, 94 MHz: bold no noise, faint %d runs at the\n"
                 "3 km SNR (%.1f dB, a / sigma = %.1f).  (b) its comparators.  (c, d) the slow path, 4.8 MHz"
                 % (name, NRUNS, CASES[1][2], res["cases"]["3 km"]["a_over_sigma"]), fontsize=9.5)
    a0.grid(alpha=0.25)
    # (b) the fast comparators, same zoom
    a1 = ax[1]
    rows = ["CMP_I", "CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN"]
    for j, nm in enumerate(rows):
        y0 = len(rows) - 1 - j
        for k in range(NRUNS):
            a1.plot(x, y0 + 0.7 * r["3 km"]["fast"][nm][k][xf], color=CS_FAST[nm], alpha=0.07, lw=0.8)
        a1.plot(x, y0 + 0.7 * r["clean"]["fast"][nm][0][xf], color=CS_FAST[nm], lw=2.0)
        a1.text(-1.8, y0 + 0.35, nm, va="center", fontsize=7.5, bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=0.5))
    # what the decoder's table makes of the five comparators at each instant (no noise): the idle, a
    # vector in transit that no message settles to (no decision: wait), or the message
    scheme = CL.Scheme("A3t", "", SCHEME.idle, SCHEME.msgs, [CL.CMP_QP, CL.CMP_QN], t=tf, t2=T2)
    lut, iv = scheme.lut(), scheme.idle_vector()
    k_want = [m for m, (c, n) in enumerate(CORNERS) if n == name][0]
    vec = sum(r["clean"]["fast"][nm][0].astype(np.int32) << k for k, nm in enumerate(CL.CMP_NAMES))[xf]
    st = np.where(vec == iv, 0, np.where((np.array(lut)[vec] & 8) == 0, 1, np.where((np.array(lut)[vec] & 7) == k_want, 2, 3)))
    cols = {0: "0.75", 1: "#f0a020", 2: "#3aa04a", 3: "#d02020"}
    labs = {0: "idle", 1: "in transit: no message's vector, wait", 2: "%s" % name, 3: "a wrong message"}
    edges = np.nonzero(np.diff(st))[0]
    starts = np.concatenate([[0], edges + 1]); ends = np.concatenate([edges + 1, [len(st) - 1]])
    for i0, i1 in zip(starts, ends):
        a1.broken_barh([(x[i0], x[i1] - x[i0])], (5.15, 0.55), facecolors=cols[int(st[i0])], edgecolor="none")
        if x[i1] - x[i0] > 1.2:
            a1.text((x[i0] + x[i1]) / 2, 5.42, labs[int(st[i0])], ha="center", va="center", fontsize=6.8)
    a1.text(-1.8, 5.95, "the decoder's table on these five (A3, no noise):", fontsize=7, va="bottom")
    dec = res["decisions"][name]
    for key, ls, lab in (("3 km", "--", "3 km"), ("lab", ":", "bench")):
        ev, dd = dec[key]["event_ns_mean"], dec[key]["decision_ns_mean"]
        a1.axvline(ev, color="k", lw=0.9, ls=ls)
        a1.axvline(dd, color="0.5", lw=0.9, ls=ls)
        a1.text(ev - 0.2, -0.45 if key == "3 km" else 4.95, "%s event %.1f" % (lab, ev), fontsize=6.8, ha="right", va="bottom" if key == "3 km" else "top")
        a1.text(dd + 0.2, -0.45 if key == "3 km" else 4.95, "decided %.1f" % dd, fontsize=6.8, ha="left", va="bottom" if key == "3 km" else "top", color="0.35")
    a1.axvspan(dec["3 km"]["event_ns_mean"], dec["3 km"]["decision_ns_mean"], ymin=0.0, ymax=0.77, color="0.9", zorder=0)
    a1.set_xlim(-2, 24); a1.set_ylim(-0.5, 6.5); a1.set_yticks([])
    a1.set_xlabel("ns: the comparators at the 3 km windows (%.2f a); the dotted lines: the event and decision with the bench's\n"
                  "windows (%.2f a).  The FPGA sees each edge %.1f ns later, samples every 1.25 ns, decides 4 samples after the event"
                  % (tf, tl, T_HDR * 1e9), fontsize=7.5)
    a1.grid(alpha=0.25, axis="x")
    a1.text(23.8, 4.9, "3 km: %d / %d right\nbench: %d / %d right" % (dec["3 km"]["right"], NRUNS, dec["lab"]["right"], NRUNS),
            ha="right", va="top", fontsize=7.5, bbox=dict(facecolor="white", edgecolor="0.7", alpha=0.9))
    a1.text(23.8, 2.0, "QP / QN are a window round 0:\nboth low at the idle", ha="right", va="center", fontsize=7,
            color="0.3", bbox=dict(facecolor="white", edgecolor="none", alpha=0.85))
    # (c) the slow arm, differential (each leg 1.65 V +- half of it)
    a2 = ax[2]
    xs = (TNS >= -5) & (TNS <= 90)
    x2 = TNS[xs]
    for k in range(NRUNS):
        for nm, col in (("I", CI), ("Q", CQ)):
            l = r["3 km"]["slow"][nm]
            a2.plot(x2, (l[0][k] - l[1][k])[xs], color=col, alpha=0.06, lw=0.6)
    for nm, col in (("I", CI), ("Q", CQ)):
        l = r["clean"]["slow"][nm]
        a2.plot(x2, (l[0][0] - l[1][0])[xs], color=col, lw=2.2, label="%s slow: x%.0f, clipped, %.1f MHz" % (nm, G_SLOW, B["slow_fpole_MHz"]))
    th2 = 2 * (r["clean"]["vt2"] - V_MID)
    for y in (th2, -th2):
        a2.axhline(y, color="0.2", lw=1.0, ls="--")
    a2.axhline(0, color="0.3", lw=0.6)
    for y in (V_HI - V_LO, -(V_HI - V_LO)):
        a2.axhline(y, color="0.6", lw=0.6, ls="-.")
    a2.axvspan(-2, 24, color="0.92", lw=0, zorder=0)
    a2.text(11, -3.1, "(a) and (b)", ha="center", fontsize=7, color="0.45")
    a2.text(89, th2 + 0.06, "V_T2: %.2f V (%.1f a, x20)" % (th2, T2), ha="right", va="bottom", fontsize=7.5)
    a2.text(89, (V_HI - V_LO) + 0.06, "the stage's swing: legs 0.2 to 3.1 V", ha="right", va="bottom", fontsize=7, color="0.45")
    a2.set_xlim(-5, 90); a2.set_ylim(-3.3, 3.3)
    a2.set_ylabel("slow arm, differential (V)")
    a2.legend(loc="lower left", fontsize=7.5, framealpha=0.9)
    a2.grid(alpha=0.25)
    # (d) the slow comparators
    a3 = ax[3]
    rows = ["CMP_I_S", "CMP_QP_S", "CMP_QN_S"]
    for j, nm in enumerate(rows):
        y0 = len(rows) - 1 - j
        for k in range(NRUNS):
            a3.plot(x2, y0 + 0.7 * r["3 km"]["slow_cmp"][nm][k][xs], color=CS_SLOW[nm], alpha=0.07, lw=0.8)
        a3.plot(x2, y0 + 0.7 * r["clean"]["slow_cmp"][nm][0][xs], color=CS_SLOW[nm], lw=2.0)
        a3.text(-4.6, y0 + 0.35, nm, va="center", fontsize=7.5, bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=0.5))
    for nm in rows:
        te = dec["clean"].get(nm)
        if te == te and te is not None:
            a3.annotate("%.1f ns" % te, (te, 2.75 - rows.index(nm)), xytext=(4, 0), textcoords="offset points", fontsize=7)
    a3.set_xlim(-5, 90); a3.set_ylim(-0.3, 3.0); a3.set_yticks([])
    a3.set_xlabel("ns after the transmitting FPGA's register changes")
    a3.grid(alpha=0.25, axis="x")
    fn = os.path.join(OUT, "traj_time_%s.png" % name.replace(" ", "").replace("+", "p").replace("-", "m"))
    fig.savefig(fn, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.relpath(fn, ROOT))


def regions(ax, th, lim, label=True):
    """the fast comparators' regions: the Q windows (the event and the Q bit) shaded, the I windows
    hatched, sign(I) the line"""
    ax.axhspan(th, lim, color=CQ, alpha=0.13, lw=0)
    ax.axhspan(-lim, -th, color=CQ, alpha=0.13, lw=0)
    for x0, x1 in ((-lim, -th), (th, lim)):
        ax.fill_between([x0, x1], -lim, lim, facecolor="none", edgecolor=CI, alpha=0.18, hatch="////", lw=0)
    for y in (th, -th):
        ax.axhline(y, color=CQ, lw=1.1, ls="--")
        ax.axvline(y, color=CI, lw=0.8, ls="--")
    ax.axvline(0, color=CI, lw=1.4)
    ax.axhline(0, color="0.5", lw=0.5)
    if label:
        ax.text(-lim + 0.04, th + 0.03, "CMP_QP: Q > %.2f a" % th, color=CQ, ha="left", va="bottom", fontsize=8)
        ax.text(-lim + 0.04, -th - 0.03, "CMP_QN: Q < -%.2f a" % th, color=CQ, ha="left", va="top", fontsize=8)
        ax.text(th + 0.03, -lim + 0.05, "CMP_IP", color=CI, fontsize=8)
        ax.text(-th - 0.03, -lim + 0.05, "CMP_IN", color=CI, ha="right", fontsize=8)
        ax.text(0.03, lim - 0.05, "CMP_I = sign(I)", color=CI, fontsize=8, va="top")


def figure_iq(runs, tf, tl, res):
    fig, axs = plt.subplots(2, 1, figsize=(7.2, 14.2), gridspec_kw=dict(hspace=0.17))
    lim = 1.45
    sel = (TNS >= 0) & (TNS <= 30)
    for ax, case, th in ((axs[0], "3 km", tf), (axs[1], "lab", tl)):
        regions(ax, th, lim)
        for c, name in CORNERS:
            rr = runs[name]
            for k in range(NRUNS):
                ax.plot(rr[case]["I"][k][sel] / A, rr[case]["Q"][k][sel] / A, color="0.2", alpha=0.04, lw=0.6)
            I, Q = rr["clean"]["I"][0] / A, rr["clean"]["Q"][0] / A
            ax.plot(I[sel], Q[sel], color="k", lw=1.0)
            for tn in np.arange(0, 31, 1.0):
                kk = int(np.argmin(abs(TNS - tn)))
                big = tn % 5 == 0
                ax.plot(I[kk], Q[kk], "o", ms=5.0 if big else 2.6, color="#7a1fa0" if big else "#2a8a3a", zorder=5)
            # the dots' times along one path, the 1 ns ones that move
            if name == "I- Q+":
                for tn in range(6, 13):
                    kk = int(np.argmin(abs(TNS - tn)))
                    ax.annotate("%d" % tn, (I[kk], Q[kk]), xytext=(-2, 5), textcoords="offset points", fontsize=6.5,
                                color="#2a6a2a", ha="right")
            # where it crosses its event window, and when
            tc = cross_time(Q * A, c[1] * th * A, c[1])
            kk = int(np.argmin(abs(t - tc)))
            ax.plot(I[kk], c[1] * th, "D", ms=7, mfc="#ffd84a", mec="k", zorder=7)
            ax.annotate("%.1f ns" % (tc * 1e9), (I[kk], c[1] * th), xytext=(8 if c[0] > 0 else -8, 0), textcoords="offset points",
                        fontsize=8, fontweight="bold", ha="left" if c[0] > 0 else "right", va="center",
                        bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=0.3))
            ax.plot(*c, "s", ms=8, mfc="none", mec="k")
            ax.text(c[0], c[1] + (0.07 if c[1] > 0 else -0.07), name, ha="center", va="bottom" if c[1] > 0 else "top", fontsize=8)
        ax.plot(1, 0, "*", ms=15, color="#e0a000", mec="k", zorder=8)
        ax.text(1.05, 0.03, "idle", fontsize=9)
        cs = res["cases"][case]
        ax.set_title("%s: %s, SNR %.1f dB (a / sigma = %.0f)\nwindows at the CFAR place, %.1f sigma = %.2f a: one false event an hour"
                     % ("Range" if case == "3 km" else "Bench", cs["label"], cs["snr_dB"], cs["a_over_sigma"], z_fa(), th), fontsize=10)
        ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_aspect("equal")
        ax.set_xlabel("I / a"); ax.set_ylabel("Q / a")
        ax.grid(alpha=0.2)
    axs[0].text(-1.4, 0.45, "dots every 1 ns after the TX edge\n(purple every 5 ns); yellow: the\nevent window crossed (the FPGA\n"
                "sees it 2.5 + 1.6 ns later)\nfaint: %d noisy runs a corner" % NRUNS, fontsize=7.5, va="top",
                bbox=dict(facecolor="white", edgecolor="0.7", alpha=0.92))
    fn = os.path.join(OUT, "traj_iq_fast.png")
    fig.savefig(fn, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.relpath(fn, ROOT))


def figure_iq_slow(runs, res):
    fig, ax = plt.subplots(figsize=(7.2, 7.2))
    lim = 3.3
    sw = V_HI - V_LO
    th2 = 2 * (runs[CORNERS[0][1]]["clean"]["vt2"] - V_MID)
    ax.axhspan(th2, lim, color=CQ, alpha=0.10, lw=0); ax.axhspan(-lim, -th2, color=CQ, alpha=0.10, lw=0)
    for y in (th2, -th2):
        ax.axhline(y, color=CQ, lw=1.0, ls="--")
    ax.axvline(0, color=CI, lw=1.4)
    ax.plot([-sw, sw, sw, -sw, -sw], [-sw, -sw, sw, sw, -sw], color="0.5", lw=0.8, ls="-.")
    ax.text(sw, sw + 0.08, "the stage's swing", ha="right", fontsize=7.5, color="0.4")
    ax.text(lim - 0.05, th2 + 0.05, "CMP_QP_S (V_T2)", color=CQ, ha="right", fontsize=8)
    ax.text(lim - 0.05, -th2 - 0.05, "CMP_QN_S", color=CQ, ha="right", va="top", fontsize=8)
    ax.text(0.05, -lim + 0.1, "CMP_I_S = sign", color=CI, fontsize=8)
    sel = (TNS >= 0) & (TNS <= 150)
    for c, name in CORNERS:
        rr = runs[name]
        for k in range(NRUNS):
            li, lq = rr["3 km"]["slow"]["I"], rr["3 km"]["slow"]["Q"]
            ax.plot((li[0][k] - li[1][k])[sel], (lq[0][k] - lq[1][k])[sel], color="0.2", alpha=0.035, lw=0.6)
        li, lq = rr["clean"]["slow"]["I"], rr["clean"]["slow"]["Q"]
        I, Q = (li[0][0] - li[1][0]), (lq[0][0] - lq[1][0])
        ax.plot(I[sel], Q[sel], color="k", lw=1.0)
        for tn in np.arange(0, 151, 5.0):
            kk = int(np.argmin(abs(TNS - tn)))
            big = tn % 25 == 0
            ax.plot(I[kk], Q[kk], "o", ms=5.5 if big else 2.6, color="#7a1fa0" if big else "#2a8a3a", zorder=5)
            if big and 0 < tn <= 75:
                ax.annotate("%d ns" % tn, (I[kk], Q[kk]), xytext=(5, 0), textcoords="offset points", fontsize=7, color="#7a1fa0")
    ax.plot(sw, 0, "*", ms=14, color="#e0a000", mec="k", zorder=6)
    ax.text(sw - 0.1, 0.12, "idle (I saturated)", fontsize=8, ha="right")
    ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim); ax.set_aspect("equal")
    ax.set_xlabel("slow I, differential (V)"); ax.set_ylabel("slow Q, differential (V)")
    ax.set_title("The slow path on its own plane: x%.0f, clipped, then %.1f MHz\ndots every 5 ns, big every 25 ns; faint: the 3 km runs"
                 % (G_SLOW, B["slow_fpole_MHz"]), fontsize=10)
    ax.grid(alpha=0.2)
    fn = os.path.join(OUT, "traj_iq_slow.png")
    fig.savefig(fn, dpi=130, bbox_inches="tight")
    plt.close(fig)
    print("wrote", os.path.relpath(fn, ROOT))


def figure_latency(res):
    """when the event and the bits are known, against the SNR"""
    zf = z_fa()
    # from the SNR at which the window still sits at 0.9 a (7.5 sigma must fit inside a): below it the fast
    # path cannot hold one false event an hour, and the slow path (or a lower demand) has to
    lo = next(x for x in np.arange(10, 50, 0.05) if zf * sigma(x) / A <= 0.9)
    snrs = np.linspace(lo, 50, 161)
    tpd = (CMP_TPD + T_HDR) * 1e9
    dG = np.gradient(G, DT)
    cf, jit, half = [], [], []
    for s in snrs:
        th = min(zf * sigma(s) / A, 0.999)
        tc = t_cross(th)
        k = int(np.argmin(abs(t - tc)))
        cf.append(tc * 1e9 + tpd)
        jit.append(sigma(s) / (A * dG[k]) * 1e9)          # the noise's timing jitter at the crossing: sigma / slope
        half.append(t_cross(0.5) * 1e9 + tpd)
    cf, jit = np.array(cf), np.array(jit)
    slow = min(v for v in res["decisions"]["I+ Q+"]["clean"].values() if v == v and v > 15) + T_HDR * 1e9
    fig, ax = plt.subplots(figsize=(8.0, 5.4))
    ax.fill_between(snrs, cf - jit, cf + jit, color=CQ, alpha=0.18, lw=0, label="+- the noise's timing jitter (sigma / slope)")
    ax.plot(snrs, cf, color=CQ, lw=2.2, label="the event window at the CFAR place (%.1f sigma from the idle)" % zf)
    ax.plot(snrs, half, color=CI, lw=1.4, ls="--", label="a window halfway (0.5 a), and sign(I) for a corner across the origin")
    ax.axhline(slow, color="0.3", lw=1.2, ls="-.", label="the slow path's Q window (CMP_QP_S): its confirmation")
    ax.axhline(T_FIXED * 1e9 + tpd, color="0.7", lw=0.8)
    ax.text(lo + 0.5, T_FIXED * 1e9 + tpd - 0.15, "the fixed delays alone: no rise time at all", fontsize=7.5, color="0.4", va="top")
    ax.text(lo + 0.3, slow - 1.2, "below %.1f dB a window %.1f sigma\nfrom the idle no longer fits in 0.9 a" % (lo, zf),
            fontsize=7.5, color="0.35", va="top")
    for key in ("lab", "3 km"):
        cs = res["cases"][key]
        y = t_cross(min(zf * sigma(cs["snr_dB"]) / A, 0.999)) * 1e9 + tpd
        ax.plot(cs["snr_dB"], y, "o", color=CQ, ms=7)
        ax.annotate("%s\n%.1f dB: %.1f ns" % (cs["label"], cs["snr_dB"], y), (cs["snr_dB"], y), xytext=(8, 8),
                    textcoords="offset points", fontsize=7.5)
    ax.set_xlabel("SNR in 100 MHz (dB)")
    ax.set_ylabel("ns from the TX edge to the FPGA's input")
    ax.set_title("When the receiver knows: a window placed by the noise is crossed earlier as the SNR rises\n"
                 "(the arm's 10-90 %% rise is %.1f ns; the comparator's %.1f ns and the header's %.1f ns are included)"
                 % ((T90 - T10) * 1e9, CMP_TPD * 1e9, T_HDR * 1e9), fontsize=10)
    ax.legend(fontsize=7.5, loc="upper right")
    ax.grid(alpha=0.25)
    ax.set_ylim(T_FIXED * 1e9 + tpd - 1.0, slow + 2)
    fn = os.path.join(OUT, "traj_latency.png")
    fig.savefig(fn, dpi=130, bbox_inches="tight")
    plt.close(fig)
    res["latency"] = {"snr_min_dB": float(lo), "snr_dB": [float(v) for v in snrs[::20]], "cfar_ns": [float(v) for v in cf[::20]],
                      "jitter_ns": [float(v) for v in jit[::20]], "half_ns": float(half[0]), "slow_ns": slow}
    print("wrote", os.path.relpath(fn, ROOT))


if __name__ == "__main__":
    sys.exit(main())
