#!/usr/bin/env python3
"""sdr_rx.py: a software BPSK receiver for captures of the board's TX (the USRP B210 receiving), with the carrier and
the symbol timing recovered from the signal itself: the two ends' clocks are not coherent (Jason, 2026-10-30: "We'll
need timing recovery when we go to two Costas boards, so you might as well start now").  The same steps are the model
for the board's own timing recovery in gateware.

    rx = demod(x, fs, baud)        x: complex baseband samples at fs, a BPSK PRBS at baud (nominal)

  1. the carrier's offset, coarse: BPSK squared is a tone at twice it (the FFT's peak, refined by a parabola);
  2. a matched filter (the symbol's rectangle: a moving average one symbol long);
  3. the timing, per block of symbols, by Oerder and Meyr: the square-law signal |y|^2 has a line at the symbol rate
     whose phase is the timing; the blocks' phases unwrapped give the timing's drift, i.e. the clocks' offset in ppm;
  4. the symbols read at those instants (linear interpolation), the carrier's phase per block from the symbols
     squared (the 180-degree ambiguity left: the check below does not care), the carrier feedthrough taken out as the
     symbols' mean;
  5. the decisions and the self-synchronising PRBS check (x^15 + x^14 + 1 by default: b_n ^ b_n-14 ^ b_n-15 is 0),
     the data's polarity taken as the one with fewer failures (inverted data fails every check).

The check counts failures; one wrong bit fails three checks, so the BER is failures / 3 / bits (as the board's).
"""
import numpy as np

TAPS = {7: (7, 6), 9: (9, 5), 15: (15, 14), 23: (23, 18), 31: (31, 28)}


def prbs_bits(poly=15, n=None, seed=None):
    a, b = TAPS[poly]
    n = n or (1 << a) - 1
    s = list(seed or [1] * a)                     # s[0] the newest
    out = np.empty(n, dtype=np.uint8)
    for k in range(n):
        bit = s[a - 1] ^ s[b - 1]
        out[k] = bit
        s = [bit] + s[:-1]
    return out


def check(bits, poly=15):
    a, b = TAPS[poly]
    bits = np.asarray(bits, dtype=np.uint8)
    f = bits[a:] ^ bits[a - b: len(bits) - b] ^ bits[: len(bits) - a]
    return f


def coarse_freq(x, fs, max_hz=None, f_exp=None, f_win=200e3):
    """f_exp: the carrier expected there (the receiver's LO set off it), searched within +-f_win: keeps the
    squared spectrum's DC (the receiver's own LO leak, squared) out of the search"""
    y = x * x
    n = 1 << int(np.ceil(np.log2(len(y))))
    Y = np.abs(np.fft.fft(y * np.hanning(len(y)), n))
    f = np.fft.fftfreq(n, 1 / fs)
    if max_hz:
        Y[np.abs(f) > 2 * max_hz] = 0
    if f_exp is not None:
        f2 = ((2 * f_exp + fs / 2) % fs) - fs / 2           # twice it, aliased into the band
        dd = ((f - f2 + fs / 2) % fs) - fs / 2
        Y[np.abs(dd) > 2 * f_win] = 0
    k = int(np.argmax(Y))
    a, b, c = Y[(k - 1) % n], Y[k], Y[(k + 1) % n]
    d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    return (f[k] + d * fs / n) / 2.0


def demod(x, fs, baud, poly=15, block=512, max_hz=None, f_exp=None, f_win=200e3):
    x = np.asarray(x, dtype=np.complex128)
    x = x - np.mean(x)                                      # the receiver's own DC (its LO leak), off the carrier
    sps = fs / baud
    f0 = coarse_freq(x, fs, max_hz, f_exp, f_win)
    if f_exp is not None:                                   # the half-frequency's alias: the one nearer f_exp
        alt = f0 + fs / 2 if f0 < 0 else f0 - fs / 2
        if abs(alt - f_exp) < abs(f0 - f_exp):
            f0 = alt
    t = np.arange(len(x)) / fs
    x = x * np.exp(-2j * np.pi * f0 * t)
    L = max(1, int(round(sps)))
    y = np.convolve(x, np.ones(L) / L, mode="same")
    # Oerder and Meyr per block of symbols: the line at the symbol rate in |y|^2
    p = np.abs(y) ** 2
    nb = int(len(y) // (block * sps))
    if nb < 2:
        raise ValueError("capture too short")
    phases = []
    for k in range(nb):
        i0, i1 = int(k * block * sps), int((k + 1) * block * sps)
        tt = np.arange(i0, i1)
        phases.append(np.angle(np.sum(p[i0:i1] * np.exp(-2j * np.pi * tt / sps))))
    ph = np.unwrap(np.array(phases))
    # the timing's drift: phase in cycles of the symbol against time; the slope is the clocks' offset
    tb = (np.arange(nb) + 0.5) * block * sps / fs
    slope, icpt = np.polyfit(tb, ph / (2 * np.pi), 1)
    ppm = slope / baud * 1e6
    # the instants, continuous: the unwrapped timing phase interpolated between the blocks' centres (no symbol skipped
    # or read twice where the timing crosses a symbol's edge); the |y|^2 line peaks mid-symbol for a matched filter
    # ("same" mode centres it)
    n_sym = int((len(y) - 2 * sps) / sps)
    k = np.arange(n_sym)
    nominal = k * sps
    tau = -np.interp(nominal / fs, tb, ph) / (2 * np.pi) * sps
    pos = nominal + (tau - tau[0] + (tau[0] % sps))
    pos = pos[(pos >= 0) & (pos < len(y) - 1)]
    i = np.floor(pos).astype(int)
    fr = pos - i
    s = y[i] * (1 - fr) + y[i + 1] * fr
    # the carrier's phase per block from the symbols squared, unwrapped (twice the phase, so the blocks join without
    # 180-degree jumps); the feedthrough taken out first as the symbols' mean
    s = s - np.mean(s)
    nb2 = max(1, len(s) // block)
    th2 = np.unwrap([np.angle(np.sum(s[m * block:(m + 1) * block] ** 2)) for m in range(nb2)])
    th = np.interp(np.arange(len(s)), (np.arange(nb2) + 0.5) * block, th2 / 2.0)
    s = s * np.exp(-1j * th)
    bits = (np.real(s) < 0).astype(np.uint8)
    f1 = check(bits, poly)
    f2 = check(1 - bits, poly)
    fails = int(min(f1.sum(), f2.sum()))
    nbits = len(f1)
    evm = np.sqrt(np.mean((np.abs(np.real(s)) - np.mean(np.abs(np.real(s)))) ** 2 + np.imag(s) ** 2)) / np.mean(np.abs(np.real(s)))
    return {"f0_hz": f0, "ppm": ppm, "sps": sps, "bits": nbits, "fails": fails, "ber": fails / 3.0 / nbits if nbits else None,
            "evm": float(evm), "blocks": nb, "timing_cycles": (ph / (2 * np.pi)).tolist()[:400], "symbols": s}


def synth(baud=1e6, fs=20e6, n_sym=40000, f_off=12e3, ppm=30.0, snr_db=20.0, feed=0.2, poly=15, seed=3):
    rng = np.random.default_rng(seed)
    bits = np.resize(prbs_bits(poly), n_sym)
    a = 1.0 - 2.0 * bits
    rate = baud * (1 + ppm * 1e-6)
    t = np.arange(int(n_sym / rate * fs) - 10) / fs
    k = np.minimum((t * rate + 0.37).astype(int), n_sym - 1)
    x = a[k] + feed
    x = x * np.exp(2j * np.pi * f_off * t + 1j * 0.7)
    x = x + (rng.normal(size=len(x)) + 1j * rng.normal(size=len(x))) * 10 ** (-snr_db / 20) / np.sqrt(2) * np.sqrt(sps_of(fs, baud))
    return x


def sps_of(fs, baud):
    return fs / baud


if __name__ == "__main__":
    for ppm in (0.0, 30.0, -55.0):
        for snr in (20.0, 8.0):
            x = synth(ppm=ppm, snr_db=snr)
            r = demod(x, 20e6, 1e6)
            print("synthetic: ppm %+5.1f snr %4.1f dB -> f0 %.1f Hz, ppm %+.2f, %d bits, BER %.2e, EVM %.2f" % (
                ppm, snr, r["f0_hz"], r["ppm"], r["bits"], r["ber"], r["evm"]))
