"""The ICs and parts, from their datasheets (no Touchstone files: none were fetched).

Each is an n-port admittance function of frequency referenced to ground, or a two-terminal impedance.  What is
assumed rather than read is said beside it.
"""
import json, math, os
import numpy as np
from circuit import s2y, z_cap, z_ind, z_res, z_l, unilateral_amp

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- ADL5611: the datasheet's Table 2 (its evaluation board, 43 nH 0603 choke and 100 nF blocks included) ----
_A = json.load(open(os.path.join(HERE, "adl5611_sparams.json")))
_AF = np.array(sorted(int(k) for k in _A["rows"]))
_AV = np.array([_A["rows"][str(k)] for k in _AF])


def adl5611_s(f):
    mhz = f / 1e6
    out = []
    for k in range(4):
        db = np.interp(mhz, _AF, _AV[:, 2 * k])
        if mhz > _AF[-1]:                       # above 6 GHz: hold the magnitude, extend the phase's slope
            ph = _AV[-1, 2 * k + 1] + (_AV[-1, 2 * k + 1] - _AV[-2, 2 * k + 1]) / (_AF[-1] - _AF[-2]) * (mhz - _AF[-1])
        else:
            ph = np.interp(mhz, _AF, _AV[:, 2 * k + 1])
        out.append(10 ** (db / 20) * np.exp(1j * math.radians(ph)))
    s11, s21, s12, s22 = out
    return np.array([[s11, s12], [s21, s22]])


def adl5611_y(f):
    return s2y(adl5611_s(f))


# ---- PE43711 at 0 dB: insertion loss 1.9 dB typ (2.2-4 GHz), 2.4 (4-6 GHz); return loss 14 / 16 dB ----
def pe43711_y(f, atten_db=0.0):
    ghz = f / 1e9
    il = np.interp(ghz, [1.0, 2.2, 4.0, 6.0, 7.0], [1.6, 1.9, 2.15, 2.6, 2.9])
    rl = 14.0 if ghz < 4 else 16.0
    tau = 120e-12                               # about 120 ps through the switch-and-pad stack (assumed)
    t = 10 ** (-(il + atten_db) / 20) * np.exp(-1j * 2 * math.pi * f * tau)
    r = 10 ** (-rl / 20)
    return s2y(np.array([[r, t], [t, r]]))


# ---- SKY65404-31: matched at RF_OUT; its input needs 0.5 pF shunt at the pin (Figure 10) ----
C_MATCH = 0.5e-12


def sky65404_gain_db(f):
    """13 dB typ across 4.9-5.9 GHz (Table 4, Figure 3: flat 4.8-6.0 GHz).  Outside it: unknown; taken
    falling 3 dB per GHz below 4.8 and above 6.0 (an assumption, flagged in the report)."""
    g = f / 1e9
    if g < 4.8:
        return 13.0 - 3.0 * (4.8 - g)
    if g > 6.0:
        return 13.0 - 3.0 * (g - 6.0)
    return 13.0


LNA_INPUT = "series"          # "series": R + jwL that the 0.5 pF matches at 5.4 GHz; "ideal": matched at every f


def sky65404_yin(f):
    w = 2 * math.pi * f
    if LNA_INPUT == "ideal":
        return 1 / 50.0 - 1j * w * C_MATCH      # what the 0.5 pF at the pin turns into 50 ohm, at every frequency
    # a physical input: the bare input that 0.5 pF at the pin matches to 50 ohm at 5.4 GHz (the band's centre):
    # Y(f0) = 1/50 - j w0 C  ->  Z = 29.0 + j24.6 ohm, as R in series with 0.725 nH
    w0 = 2 * math.pi * 5.4e9
    z0 = 1 / (1 / 50.0 - 1j * w0 * C_MATCH)
    return 1 / (z0.real + 1j * w * z0.imag / w0)


def sky65404_y(f):
    return unilateral_amp(sky65404_yin, sky65404_gain_db)(f)


# ---- TDK HHM1907B1: 1:1 balun, 0.8 dB max 4.9-5.95 GHz; ideal centre-tapped transformer with that loss ----
def balun_y(f):
    ghz = f / 1e9
    il = 0.8 if 4.9 <= ghz <= 5.95 else 0.8 + 1.2 * min(abs(ghz - 4.9), abs(ghz - 5.95))   # out of band: assumed
    t = 10 ** (-il / 20) / math.sqrt(2)
    S = np.array([[0.05, t, -t], [t, 0.5, 0.5], [-t, 0.5, 0.5]], complex)
    return s2y(S)


# ---- ADL5380 RF input: 50 ohm differential (RL -10 to -19 dB): 50 ohm across the pins, 0.25 pF a pin ----
ADL5380_RDIFF = 50.0
ADL5380_CPIN = 0.25e-12

# ---- ADL5375-05 output: POUT at 1 V p-p baseband (Table 1), output return loss ----
ADL5375_POUT = [(0.45, 0.85), (0.9, 0.75), (1.9, 0.53), (2.15, 0.73), (2.6, 0.61), (3.5, 0.21), (5.8, -1.36), (6.0, -1.6)]
ADL5375_RL = [(0.45, 16.4), (0.9, 15.7), (1.9, 16.2), (2.15, 17.1), (2.6, 19.3), (3.5, 20.7), (5.8, 7.4), (6.0, 7.0)]


def adl5375_pout_dbm(f):
    g = f / 1e9
    return float(np.interp(g, [a for a, b in ADL5375_POUT], [b for a, b in ADL5375_POUT]))


def adl5375_zout(f):
    """the output impedance from the return loss, given a capacitive phase (assumed)"""
    g = f / 1e9
    rl = float(np.interp(g, [a for a, b in ADL5375_RL], [b for a, b in ADL5375_RL]))
    m = 10 ** (-rl / 20)
    gam = m * np.exp(-1j * math.radians(90 + 60 * g / 6.0))
    return 50 * (1 + gam) / (1 - gam)


# ---- MAX2871 RFOUT: an open-collector current with the datasheet's 27 nH pull-up into 50 ohm (Note 4) ----
MAX2871_COUT = 0.6e-12          # the pin's capacitance: assumed (not in the datasheet)


# ---- passives by part number ----
def part_z(ref, value, footprint):
    """the two-terminal model of a passive: impedance function, and a short description"""
    v = value.strip()
    pkg = "0603" if "0603" in footprint else "0805" if "0805" in footprint else "1206" if "1206" in footprint else "0402"
    esl = {"0402": 0.3e-9, "0603": 0.45e-9, "0805": 0.6e-9, "1206": 0.9e-9}[pkg]
    if ref.startswith("C"):
        C = parse_value(v, "F")
        esr = 0.15 if C < 1e-9 else 0.05
        return z_cap(C, esl, esr), "%s C %s ESL %.2f nH" % (ref, v, esl * 1e9)
    if ref.startswith("L"):
        L = parse_value(v, "H")
        if abs(L - 43e-9) < 1e-12:
            return z_ind(L, 2.9e9, q=40, q_f=0.25e9), "%s 43 nH LQW18AN43NG00D, SRF 2.7 GHz min (2.9 taken)" % ref
        if abs(L - 27e-9) < 1e-12:
            return z_ind(L, 3.2e9, q=25, q_f=0.25e9), "%s 27 nH LQW15AN27NG80D, SRF taken 3.2 GHz (assumed)" % ref
        if abs(L - 6.8e-9) < 1e-12:
            return z_ind(L, 6.4e9, q=30, q_f=1e9), "%s 6.8 nH LQW15AN6N8G00D, SRF 6.0 GHz min (6.4 taken)" % ref
        if abs(L - 0.6e-9) < 1e-12:
            return z_l(0.6e-9, 0.1), "%s 0.6 nH MLG1005S0N6CT000" % ref
        return z_ind(L, 1e10, q=30), "%s L %s" % (ref, v)
    if ref.startswith("R"):
        if v.upper().startswith("0R") or v in ("0", "0R"):
            return z_l(0.3e-9, 0.02), "%s 0 ohm" % ref
        R = parse_value(v.replace("R", ""), "")
        return z_res(R, 0.3e-9), "%s R %s" % (ref, v)
    if ref.startswith("FB"):
        # 220 ohm at 100 MHz, 2 A, 0805 (C85840): R 220 || L 0.35 uH, with 1 pF across (a generic bead)
        def z(f):
            w = 2 * math.pi * f
            zl = 1 / (1 / 220.0 + 1 / (1j * w * 0.35e-6))
            return 1 / (1 / (zl + 0.05) + 1j * w * 1e-12)
        return z, "%s ferrite 220 ohm @ 100 MHz (generic model)" % ref
    return None, "%s ?" % ref


def parse_value(v, unit):
    v = v.replace(unit, "").replace("u", "e-6").replace("n", "e-9").replace("p", "e-12").replace("k", "e3").replace("M", "e6")
    v = v.replace("µ", "e-6")
    try:
        return float(v)
    except ValueError:
        # 4k7, 1k5, 0R5 style
        for s, m in (("e3", 1e3), ("e-12", 1e-12), ("e-9", 1e-9), ("e-6", 1e-6)):
            if s in v:
                a, b = v.split(s)
                return float(a + "." + b) * m if b else float(a) * m
        raise
