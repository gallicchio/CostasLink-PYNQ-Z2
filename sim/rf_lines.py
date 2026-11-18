#!/usr/bin/env python3
"""50 ohm line geometry on JLCPCB's JLC04161H-7628 4-layer stack-up (L1 copper over 0.2104 mm of
7628 prepreg to the L2 ground), for the board's RF class: a grounded coplanar waveguide (CPWG,
CLAUDE_PCB.md section 14) and, for comparison, plain microstrip.

Closed forms (Wadell, "Transmission Line Design Handbook", 1991; Hammerstad-Jensen for microstrip
with the IPC-2141 thickness correction).  The fab's own calculator is the authority
(CLAUDE_PCB.md section 13): JLCPCB's impedance tool for this stack gives 0.345 mm for a 50 ohm
microstrip (its published figure), which the formula below reproduces within 2 %.

    python3 sim/rf_lines.py      prints the widths; gen/project.py reads RF_W and RF_GAP
"""
import math

H = 0.2104          # prepreg thickness, mm (JLC04161H-7628)
ER = 4.4            # 7628 at 5.8 GHz (JLCPCB quotes 4.4 for 7628 at high frequency; 4.6 at 1 MHz)
T = 0.035           # 1 oz outer copper


def ellipk_ratio(k):
    """K(k)/K'(k) by Hilberg's approximation (0.1 % accurate)."""
    kp = math.sqrt(1 - k * k)
    if k <= 1 / math.sqrt(2):
        return math.pi / math.log(2 * (1 + math.sqrt(kp)) / (1 - math.sqrt(kp)))
    return math.log(2 * (1 + math.sqrt(k)) / (1 - math.sqrt(k))) / math.pi


def cpwg_z0(w, s, h=H, er=ER, t=T):
    """Grounded CPW with finite ground planes beside the line (Wadell 3.5.2)."""
    # effective width with copper thickness (a common correction)
    d = 1.25 * t / math.pi * (1 + math.log(4 * math.pi * w / t)) if t > 0 else 0
    w = w + d
    s = s - d
    k = w / (w + 2 * s)
    k1 = math.tanh(math.pi * w / (4 * h)) / math.tanh(math.pi * (w + 2 * s) / (4 * h))
    K = ellipk_ratio(k)
    K1 = ellipk_ratio(k1)
    eeff = (1 + er * K1 / K) / (1 + K1 / K)
    z0 = 60 * math.pi / math.sqrt(eeff) / (K + K1)
    return z0, eeff


def microstrip_z0(w, h=H, er=ER, t=T):
    we = w + t / math.pi * (1 + math.log(2 * h / t))          # IPC-2141 thickness correction
    u = we / h
    a = 1 + math.log((u ** 4 + (u / 52) ** 2) / (u ** 4 + 0.432)) / 49 + math.log(1 + (u / 18.1) ** 3) / 18.7
    b = 0.564 * ((er - 0.9) / (er + 3)) ** 0.053
    eeff = (er + 1) / 2 + (er - 1) / 2 * (1 + 10 / u) ** (-a * b)
    f = 6 + (2 * math.pi - 6) * math.exp(-(30.666 / u) ** 0.7528)
    z0 = 60 / math.sqrt(eeff) * math.log(f / u + math.sqrt(1 + (2 / u) ** 2))
    return z0, eeff


def solve(fn, target=50.0, lo=0.1, hi=1.5):
    for _ in range(60):
        mid = (lo + hi) / 2
        if fn(mid)[0] > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


RF_GAP = 0.25                                         # CPWG gap: wide enough for the fab's 0.127 mm rules twice over
RF_W = round(solve(lambda w: cpwg_z0(w, RF_GAP)), 2)
MS_W = round(solve(lambda w: microstrip_z0(w)), 3)
# a quarter wave of CPWG at 5.8 GHz, for the -20 dB coupled-line couplers (TX MON, RX MON)
_z, _eeff = cpwg_z0(RF_W, RF_GAP)
QUARTER_WAVE = 299.792458 / 5.8 / math.sqrt(_eeff) / 4           # mm

if __name__ == "__main__":
    print("JLC04161H-7628: h = %.4f mm, er = %.1f, t = %.3f mm" % (H, ER, T))
    print("microstrip 50 ohm: w = %.3f mm (JLCPCB publishes 0.345)" % MS_W)
    z, e = cpwg_z0(RF_W, RF_GAP)
    print("CPWG 50 ohm with gap %.2f mm: w = %.2f mm (Z0 %.1f ohm, eeff %.2f); quarter wave at 5.8 GHz %.2f mm" % (RF_GAP, RF_W, z, e, QUARTER_WAVE))
    for w in (0.25, 0.30, 0.35, 0.40):
        print("   w = %.2f: CPWG %.1f ohm, microstrip %.1f ohm" % (w, cpwg_z0(w, RF_GAP)[0], microstrip_z0(w)[0]))
