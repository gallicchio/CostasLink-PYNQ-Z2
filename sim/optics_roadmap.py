#!/usr/bin/env python3
"""The optical version of the latency roadmap (Jason, Prompt 23: PLAN.md section 19).

    python3 sim/optics_roadmap.py       build/optics_roadmap.json (sim/latency_roadmap.py plots it)

It starts from the group's free-space terminals as built ("used gear + Thorlabs"): used 80-100 mm William
Optics refractors on used Rainbow Astro / iOptron HAE mounts, a slow pointing loop (a 90/10 splitter to a
ZWO ASI camera), a dichroic that injects a beacon or the classical TX, Thorlabs 30 mm cage optics,
multimode fibres, and 50 MBd LED plastic-fibre links for the classical channel.  Each row keeps the one
before it and changes one more thing.

The turnaround is the same figure of merit as the RF table's, but **aperture to aperture**: an optical
terminal's own path (objective to focus, fibre) is part of the prover, as an antenna's few millimetres are
not.  The physics that sets each row:

  pointing   the residual angle per axis: the camera loop and the mount (~25 urad rms, est), or a fast
             steering mirror (~3 urad, est); the atmosphere adds its angle of arrival (Cn2 = 1e-14,
             moderate turbulence near the ground; 1e-13 on a sunny afternoon)
  field      the receiver must accept +-4 sigma of that plus half the spot: theta
  detector   etendue: a detector (or fibre core) of diameter d behind a cone of NA accepts
             theta = d NA / D from an aperture D, so d = theta D / NA, and a photodiode's bandwidth falls
             with its area: f = 10 GHz (40 um / d)^1.6, at most 50 GHz (a fit to commercial InGaAs parts, est)
  divergence the transmitted beam must cover the pointing and the beam wander: 2 (4 sigma + 3 wander),
             at least the aperture's diffraction
  power      geometric capture (D_rx / spot)^2, the optics, the air (0.5 dB/km clear at 1550 nm), a
             6 dB scintillation margin; the receiver's noise 3 pA/rtHz (B / 1 GHz)^0.7 (est), 0.9 A/W.
             The decision then follows sim/latency_roadmap.py's model: a window at its CFAR place and
             the energy bound t >= z^2 S / (R P)^2.
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import latency_roadmap as LR                                    # noqa: E402  (run(): the decision model)

C = 299792458.0
NS_M_FIBRE = 1.468 / C * 1e9          # 4.9 ns a metre of silica fibre
NS_M_POF = 1.49 / C * 1e9             # 5.0 ns a metre of plastic fibre
NS_M_AIR = 1e9 / C                    # 3.34 ns a metre inside a telescope
LAM = 1550e-9
CN2 = 1e-14
SIG_SLOW, SIG_FAST = 25e-6, 3e-6      # rad rms a axis (est)
AA_LEFT = {SIG_SLOW: 1.0, SIG_FAST: 0.3}   # the steering mirror (~1 kHz) also takes out most of the angle of arrival
LOSS_TX, LOSS_RX, AIR_KM, FADE = 3.0, 4.0, 0.5, 6.0
RANGES = {"100 m": 100.0, "3 km": 3000.0}


def sigma_aa(L, D):
    return math.sqrt(1.455 * CN2 * L * D ** (-1 / 3))


def sigma_wander(L, D_tx):
    return math.sqrt(2.42 * CN2 * L ** 3 * (D_tx / 2) ** (-1 / 3)) / L / math.sqrt(2)


def r0(L):
    k = 2 * math.pi / LAM
    return (0.423 * k * k * CN2 * L) ** (-3 / 5)


def f_det(d):
    return min(10e9 * (40e-6 / d) ** 1.6, 50e9)


def need_half_fov(L, D, sig):
    s = math.sqrt(sig ** 2 + (AA_LEFT[sig] * sigma_aa(L, D)) ** 2)
    return 4 * s + 0.5 * max(2.44 * LAM / D, LAM / r0(L))


def tx_div(L, D_tx, sig):
    return max(2 * (4 * sig + 3 * sigma_wander(L, D_tx)), 2.44 * LAM / D_tx)


def p_rx_dBm(L, o):
    div = o["tx_div"] if o.get("tx_div") else tx_div(L, o["D_tx"], o["sig"])
    g = min(1.0, (o["D_rx"] / (o["D_tx"] + div * L)) ** 2)
    return o["P_tx"] + 10 * math.log10(g) - LOSS_TX - LOSS_RX - AIR_KM * L / 1000 - FADE, div


# Each row: what changes, the cost lines (two nodes; "est" where not a quoted price), and the terminal.
#   path_rx/path_tx  metres inside the terminal: objective to focus (a WO 80-100 mm refractor is f/5.5-7, ~0.55 m)
#   fib_rx/fib_tx    metres of fibre in the fast path;  pof = the 50 MBd modules' fixed delays instead of a model
#   d, NA            the detector or fibre core and the cone that feeds it
OWNED = [("2 used WO 80-100 mm refractors at $2-3k (Jason)", 4000, 6000),
         ("2 used Rainbow Astro / iOptron HAE mounts at $2-4k (Jason)", 4000, 8000),
         ("2 ZWO ASI cameras for the slow loop (est)", 600, 2000),
         ("Thorlabs 30 mm cage cubes, splitters, dichroics, stages, mounts, two terminals (est; 'a very big expense')", 6000, 12000),
         ("2 beacon lasers, multimode fibres, the 50 MBd POF links, two FPGA boards (est)", 800, 2500)]
O2 = [("2 1550 nm DFBs, pigtailed, +10 dBm, with DC-coupled 2.5 Gb/s drivers (est)", 600, 1600),
      ("2 fibre-coupled ~1 GHz DC-coupled InGaAs photoreceivers (est)", 800, 2000),
      ("4 fibre ports (FiberPort-class) and 2 f/6 to f/2.3 relays for the 105 um fibre (est)", 1600, 3600),
      ("2 dichroics for 1550 nm (est)", 400, 1000),
      ("a comparator and LVDS board, rev B's (est)", 300, 600)]
O3 = [("2 10G PIN-TIA receivers at the focal plane, ~50 um, behind f/1.7 relays (est)", 600, 5000),
      ("2 10G DFB TOSAs with drivers and 2 booster SOAs, +18 dBm (est)", 1400, 4000),
      ("the CML fast path: ADCMP572 ($30.18) or the TIA's limiting output into CML gates, 2 boards (est)", 400, 1000)]
O4 = [("2 fast steering mirrors with drivers (est; Newport FSM-300 ~$11-12k, a voice-coil DIY ~$3k)", 6000, 24000),
      ("2 quadrant detectors and loop controllers (est)", 1000, 3000),
      ("2 x 75 mm off-axis parabolas f = 150 mm and 30 mm TX collimators, boresighted mounts (est)", 1200, 3000)]
O5 = [("2 30-40 GHz photoreceivers, 20 um (est)", 6000, 16000),
      ("2 CW DFBs into EDFAs (CW, so the doped fibre's 25-150 ns is out of the path) and 40 GHz EAM/EML modulators (est)", 6000, 16000),
      ("InP comparator and gate boards (HMC674-class, 85 ps; ~20 ps gates) (est)", 2000, 6000)]
O6 = [("a monolithic InP photonic chip: photodiode, gate, modulator at one focal plane (an MPW run, design, packaging) (est)", 25000, 100000),
      ("2 f = 50 mm apertures used both ways (est)", 400, 1000)]

TERM0 = dict(D_rx=0.09, D_tx=0.09, path_rx=0.55, path_tx=0.55, sig=SIG_SLOW)
ROWS = [
    ("O0", "as built: used gear + Thorlabs, 50 MBd POF", "50 MBd LED plastic-fibre links (650 nm, 1 mm core) at the focal planes; a registered FPGA path; the slow camera loop; multimode fibres",
     OWNED, dict(TERM0, pof=True, fib_rx=1.0, fib_tx=1.0, P_tx=-5.0, d=1e-3, NA=0.083, rx_mod=25.0, tx_mod=12.0, core=40.0, sens=-23.0)),
    ("O1", "gateware fast path", "the FPGA path combinational, pin to pin (as the RF table's row 1)",
     OWNED, dict(TERM0, pof=True, fib_rx=1.0, fib_tx=1.0, P_tx=-5.0, d=1e-3, NA=0.083, rx_mod=25.0, tx_mod=12.0, core=5.0, sens=-23.0)),
    ("O2", "1550 nm, 1 GHz, DC-coupled", "a pigtailed DFB (+10 dBm, defocused to the pointing) and a ~1 GHz InGaAs receiver on 20 cm of 105 um fibre behind an f/2.3 relay; TLV3604 into the FPGA's combinational path",
     OWNED + O2, dict(TERM0, fib_rx=0.2, fib_tx=0.2, P_tx=10.0, d=105e-6, NA=0.22, B_rx=1000, tia=0.3,
                      cmp=0.8, link=0.15, core=2.0, fpga_io=3.0, tx_tau=[0.15, 0.1], B_mod=2500, tx_fix=0.2)),
    ("O3", "CML fast path, 10 GHz at the focus", "the receiver and the laser at the focal planes (no fibre); a 10G PIN-TIA (~50 um, f/1.7); ADCMP572 or the TIA's limiting output into CML gates into a 10G laser driver; a booster SOA (+18 dBm) for range, never an EDFA after the modulation",
     OWNED + O2 + O3, dict(TERM0, fib_rx=0.0, fib_tx=0.05, P_tx=18.0, d=50e-6, NA=0.3, B_rx=7000, tia=0.15,
                           cmp=0.165, link=0.05, core=0.25, fpga_io=0.0, tx_tau=[0.03, 0.03], B_mod=10000, tx_fix=0.1)),
    ("O4", "short optics + fast tip/tilt", "the classical path gets its own short apertures on the same mount: a 75 mm off-axis parabola (f = 150 mm) to receive, a 30 mm collimator (f = 50 mm) to send; a fast steering mirror loop",
     OWNED + O2 + O3 + O4, dict(D_rx=0.075, D_tx=0.03, path_rx=0.15, path_tx=0.05, sig=SIG_FAST, fib_rx=0.0, fib_tx=0.05, P_tx=18.0,
                                d=50e-6, NA=0.3, B_rx=7000, tia=0.15, cmp=0.165, link=0.05, core=0.25, fpga_io=0.0,
                                tx_tau=[0.03, 0.03], B_mod=10000, tx_fix=0.1)),
    ("O5", "30 GHz", "20 um 30 GHz receivers (the steering mirror makes room for them); InP comparators and gates; a CW DFB through an EDFA (+23 dBm) into a 40 GHz electro-absorption modulator",
     OWNED + O2 + O3 + O4 + O5, dict(D_rx=0.075, D_tx=0.03, path_rx=0.15, path_tx=0.05, sig=SIG_FAST, fib_rx=0.0, fib_tx=0.02, P_tx=23.0,
                                     d=20e-6, NA=0.3, B_rx=30000, tia=0.08, cmp=0.085, link=0.02, core=0.12, fpga_io=0.0,
                                     tx_tau=[0.015, 0.01], B_mod=35000, tx_fix=0.05)),
    ("O6", "one photonic chip at the focus", "the photodiode, the gate and the modulator on one InP chip at a single short focus (f = 50 mm) used both ways; the CW light from the EDFA (+23 dBm) into its modulator",
     OWNED + O2 + O3 + O4 + O5 + O6, dict(D_rx=0.05, D_tx=0.05, path_rx=0.05, path_tx=0.05, sig=SIG_FAST, fib_rx=0.0, fib_tx=0.0, P_tx=23.0,
                                          d=15e-6, NA=0.35, B_rx=40000, tia=0.03, cmp=0.03, link=0.01, core=0.03, fpga_io=0.0,
                                          tx_tau=[0.01, 0.005], B_mod=40000, tx_fix=0.02)),
]


def noise_density(B_MHz):
    return 3e-12 * (B_MHz / 1000.0) ** 0.7


def turnaround(o, L):
    """aperture to aperture, ns; None when the link does not close"""
    P, div = p_rx_dBm(L, o)
    fov_need = need_half_fov(L, o["D_rx"], o["sig"])
    fov_have = o["d"] * o["NA"] / o["D_rx"]
    optics = (o["path_rx"] + o["path_tx"]) * NS_M_AIR
    out = dict(P_rx_dBm=P, tx_div_urad=div * 1e6, fov_need_urad=fov_need * 1e6, fov_have_urad=fov_have * 1e6,
               d_um=o["d"] * 1e6, f_det_GHz=f_det(o["d"]) / 1e9, optics_ns=optics)
    if fov_have < fov_need:
        out["fails"] = "the detector's field (%.0f urad) is narrower than the pointing needs (%.0f urad)" % (fov_have * 1e6, fov_need * 1e6)
        return out
    if o.get("pof"):
        fib = (o["fib_rx"] + o["fib_tx"]) * NS_M_POF
        out.update(fibre_ns=fib, electronics_ns=o["rx_mod"] + o["core"] + o["tx_mod"])
        if P < o["sens"]:
            out["fails"] = "%.0f dBm at the receiver, below its ~%.0f dBm" % (P, o["sens"])
            return out
        out["turnaround_ns"] = optics + fib + out["electronics_ns"]
        return out
    fib = o["fib_rx"] * NS_M_FIBRE + o["fib_tx"] * NS_M_FIBRE
    R = 0.9
    i = R * 1e-3 * 10 ** (P / 10)
    p_over_n0 = i * i / noise_density(o["B_rx"]) ** 2
    snr_100 = 10 * math.log10(p_over_n0 / 100e6)
    p = dict(rx_rf=o["path_rx"] * NS_M_AIR + o["fib_rx"] * NS_M_FIBRE + o["tia"], B_dem=o["B_rx"], B_arm=None,
             cmp=o["cmp"], link=o["link"], core=o["core"], fpga_io=o["fpga_io"], tx_tau=o["tx_tau"], B_mod=o["B_mod"],
             tx_rf=o["path_tx"] * NS_M_AIR + o["fib_tx"] * NS_M_FIBRE + o["tx_fix"])
    r = LR.run(p, snr_100)
    out.update(fibre_ns=fib, snr_100MHz_dB=snr_100)
    if r is None:
        out["fails"] = "%.1f dB in 100 MHz: the window does not fit" % snr_100
        return out
    out.update(r)
    return out


def rows():
    res = []
    prev = None
    for key, name, what, costs, o in ROWS:
        lo, hi = sum(c[1] for c in costs), sum(c[2] for c in costs)
        olo, ohi = sum(c[1] for c in OWNED), sum(c[2] for c in OWNED)
        r = dict(step=key, name=name, what=what, total=(lo, hi), beyond_owned=(lo - olo, hi - ohi),
                 delta=(lo - prev[0], hi - prev[1]) if prev else (0, 0), costs=costs, terminal=o)
        prev = (lo, hi)
        for case, L in RANGES.items():
            r[case] = turnaround(o, L)
        res.append(r)
    return res


def main():
    res = rows()
    for r in res:
        cells = []
        for case in RANGES:
            t = r[case]
            cells.append("%s %s" % (case, ("%6.2f ns" % t["turnaround_ns"]) if "turnaround_ns" in t else "  fails  "))
        t3 = r["3 km"]
        print("%-3s %-38s %s | 3 km: %5.1f dBm, div %4.0f urad, field %4.0f/%4.0f urad, optics %.2f fibre %.2f%s   $%d-%d (beyond owned $%d-%d)"
              % (r["step"], r["name"][:38], "  ".join(cells), t3["P_rx_dBm"], t3["tx_div_urad"], t3["fov_have_urad"], t3["fov_need_urad"],
                 t3["optics_ns"], t3.get("fibre_ns", 0), ("  [" + t3["fails"] + "]") if "fails" in t3 else "",
                 r["total"][0], r["total"][1], r["beyond_owned"][0], r["beyond_owned"][1]))
    for L in RANGES.values():
        print("L = %5.0f m: angle of arrival %.1f urad, wander %.1f urad, r0 %.1f cm" % (L, sigma_aa(L, 0.09) * 1e6, sigma_wander(L, 0.09) * 1e6, r0(L) * 100))
    json.dump(res, open(os.path.join(ROOT, "build", "optics_roadmap.json"), "w"), indent=1, default=float)
    print("wrote build/optics_roadmap.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
