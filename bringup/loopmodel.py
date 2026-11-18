#!/usr/bin/env python3
"""loopmodel.py: an averaged model of the board's Costas loop under an interferer, for explaining what the bench saw
(BRINGUP_LOG 4.3-4.5: a strong CW drags the loop to a rail on its own side; held through the CW it comes back).

The detector is the board's: sign(I) from a comparator (CMP_I, delay tau) switching Q (U110).  With the carrier at
phase theta and amplitude 1 and an interferer of relative amplitude r beating at f_b (phase psi = 2 pi f_b t),

    I(t) = cos theta + r cos psi,      Q(t) = sin theta + r sin psi,     e(t) = sign(I(t - tau)) Q(t)

The loop (3-4 kHz) cannot follow a beat of 100 kHz and more, so it sees e averaged over psi: S(theta), the
detector's characteristic.  Clean (r = 0), S = |sin theta| sign... = sign(cos theta) sin theta: zero at 0 and 180
degrees (the two stable locks), its peak the most push the loop can resist.  With r < 1 sign(I) still follows the
carrier and S keeps its shape; with r > 1 sign(I) follows the interferer, the carrier's part averages towards
zero (the hard limiter's capture), and the delay leaves a constant term r <sign(cos(psi - d)) sin psi> =
(2 / pi) r sin d, d = 2 pi f_b tau: a push with the sign of f_b.  When the push exceeds what is left of the
restoring force there is no zero of S at all, and the integrator runs VC to a rail.

    python3 bringup/loopmodel.py [--out DIR]     the figures (PNG) and a JSON of the curves
"""
import argparse
import json
import os

import numpy as np

TAU = 12e-9          # the I comparator's delay against the Q path (the 10-13 ns edge, REVB 20)


def S(theta, r, fb, tau=TAU, n=4096, offset=0.0):
    """the averaged detector at carrier phase theta (array), interferer r at fb; offset: a DC offset on I before the
    comparator, in units of the carrier (the board's trims and mid-point errors)"""
    th = np.atleast_1d(theta)[:, None]
    psi = np.linspace(0, 2 * np.pi, n, endpoint=False)[None, :]
    d = 2 * np.pi * fb * tau
    i_del = np.cos(th) + r * np.cos(psi - d) + offset
    q = np.sin(th) + r * np.sin(psi)
    return np.mean(np.sign(i_del) * q, axis=1)


def restoring_and_push(r, fb, tau=TAU):
    th = np.linspace(-np.pi, np.pi, 721)
    s = S(th, r, fb, tau)
    push = 0.5 * (s.max() + s.min())                 # the curve's offset
    restore = 0.5 * (s.max() - s.min())              # its half-swing
    has_zero = bool(np.any(np.sign(s[:-1]) != np.sign(s[1:])))
    return restore, push, has_zero, th, s


def threshold_db(fb, tau=TAU, rs=None):
    """the smallest r (in dB) at which S has no zero: the loop is dragged"""
    rs = rs if rs is not None else 10 ** (np.arange(-6, 30.01, 0.25) / 20)
    for r in rs:
        _, _, z, _, _ = restoring_and_push(r, fb, tau)
        if not z:
            return 20 * np.log10(r)
    return None


def simulate(r_of_t, fb, t_end=0.05, dt=2e-6, fn=3.5e3, zeta=0.7, rails_hz=(-670e3, 580e3), hold_of_t=None,
             f0_hz=0.0, unlocked_push_hz_s=0.0):
    """the loop in time with the averaged detector: a second-order type-II loop (natural frequency fn, damping zeta),
    the VCO's offset from the carrier f (Hz) clamped at the rails.  r_of_t, hold_of_t: functions of t.  Returns t,
    f (Hz), theta (rad)"""
    wn = 2 * np.pi * fn
    kp, ki = 2 * zeta * wn, wn ** 2                 # on the detector's slope at lock (S'(0) = 1 in these units)
    ths = np.linspace(-np.pi, np.pi, 361)
    cache = {}
    n = int(t_end / dt)
    t = np.arange(n) * dt
    f = np.zeros(n)
    th = np.zeros(n)
    integ = 2 * np.pi * f0_hz
    theta = 0.0
    for k in range(n):
        r = r_of_t(t[k])
        key = round(r, 3)
        if key not in cache:
            cache[key] = S(ths, key, fb)
        e = np.interp((theta + np.pi) % (2 * np.pi) - np.pi, ths, cache[key])
        held = hold_of_t(t[k]) if hold_of_t else False
        if not held:
            integ += ki * e * dt + 2 * np.pi * unlocked_push_hz_s * dt * (abs(e) < 0.05)
        w = integ + (0 if held else kp * e)
        w = np.clip(w, 2 * np.pi * rails_hz[0], 2 * np.pi * rails_hz[1])
        integ = np.clip(integ, 2 * np.pi * rails_hz[0], 2 * np.pi * rails_hz[1])
        theta = theta - w * dt                      # the LO's offset rotates the carrier's phase the other way
        f[k] = w / (2 * np.pi)
        th[k] = theta
    return t, f, th


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "board_A", "model"))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    out = {"tau_s": TAU, "curves": [], "thresholds": []}
    for fb in (0.1e6, 1e6, 5e6, 20e6):
        for rdb in (-20, -6, 0, 3, 6, 12):
            r = 10 ** (rdb / 20)
            restore, push, z, th, s = restoring_and_push(r, fb)
            out["curves"].append({"fb": fb, "r_db": rdb, "restore": restore, "push": push, "has_zero": z,
                                  "theta_deg": np.degrees(th[::8]).tolist(), "S": s[::8].tolist()})
    for fb in (0.1e6, 0.3e6, 1e6, 2e6, 5e6, 10e6, 20e6, 40e6):
        out["thresholds"].append({"fb": fb, "model_db": threshold_db(fb)})
        print("f_b %5.1f MHz: the model drags from %s dB" % (fb / 1e6, out["thresholds"][-1]["model_db"]))
    with open(os.path.join(a.out, "loopmodel.json"), "w") as f:
        json.dump(out, f)
    print(os.path.join(a.out, "loopmodel.json"))


if __name__ == "__main__":
    main()
