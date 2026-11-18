#!/usr/bin/env python3
"""sdr_rx.py: a software receiver (BPSK, OOK, QPSK) for captures of the board's TX (the USRP B210 receiving), with the carrier and
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

    rx = demod_ook(x, fs, baud)    on-off keying (the board's OOK, ID 12: bit 1 the carrier's null): the carrier's own
                                   line (not squared) in step 1, the decision on the symbol's magnitude at the threshold
                                   between the two levels; its Q factor (the levels' distance over their spreads)
    rx = demod_qpsk(x, fs, baud)   QPSK, two PRBS bits a symbol (the board's TX mode 3 on A3's corners): the carrier from
                                   the fourth power, its phase per block likewise; the 90-degree ambiguity and a mirror
                                   resolved by the PRBS check (the combination with the fewest failures)
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


def coarse_freq(x, fs, max_hz=None, f_exp=None, f_win=200e3, power=2):
    """f_exp: the carrier expected there (the receiver's LO set off it), searched within +-f_win: keeps the
    squared spectrum's DC (the receiver's own LO leak, squared) out of the search.  power: the modulation taken off
    (2 BPSK, 4 QPSK, 1 OOK, whose carrier is a line of its own); the result is modulo fs / power"""
    y = x ** power
    n = 1 << int(np.ceil(np.log2(len(y))))
    Y = np.abs(np.fft.fft(y * np.hanning(len(y)), n))
    f = np.fft.fftfreq(n, 1 / fs)
    if max_hz:
        Y[np.abs(f) > power * max_hz] = 0
    if f_exp is not None:
        f2 = ((power * f_exp + fs / 2) % fs) - fs / 2       # power times it, aliased into the band
        dd = ((f - f2 + fs / 2) % fs) - fs / 2
        Y[np.abs(dd) > power * f_win] = 0
    k = int(np.argmax(Y))
    a, b, c = Y[(k - 1) % n], Y[k], Y[(k + 1) % n]
    d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
    return (f[k] + d * fs / n) / power


def _symbols(x, fs, baud, power=2, block=512, max_hz=None, f_exp=None, f_win=200e3):
    """steps 1-3 and the reading of step 4: the symbols at the recovered instants, the carrier's offset taken off but
    not its phase"""
    x = np.asarray(x, dtype=np.complex128)
    x = x - np.mean(x)                                      # the receiver's own DC (its LO leak), off the carrier
    sps = fs / baud
    f0 = coarse_freq(x, fs, max_hz, f_exp, f_win, power)
    if f_exp is not None and power > 1:                     # the line's aliases (fs / power apart): the one nearer f_exp
        cands = [f0 + k * fs / power for k in range(-power, power + 1)]
        f0 = min((c for c in cands if -fs / 2 <= c < fs / 2), key=lambda c: abs(c - f_exp))
    t = np.arange(len(x)) / fs
    x = x * np.exp(-2j * np.pi * f0 * t)
    L = max(1, int(round(sps)))
    y = np.convolve(x, np.ones(L) / L, mode="same")
    return dict(_om(y, fs, baud, block), f0=f0)


def _om(y, fs, baud, block=512):
    """steps 3-4 on a matched filter's output y (complex, or real: FSK's discriminator): the timing by Oerder and Meyr
    per block, the clocks' offset, the symbols read at the recovered instants"""
    sps = fs / baud
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
    return {"s": y[i] * (1 - fr) + y[i + 1] * fr, "ppm": ppm, "sps": sps, "ph": ph, "nb": nb}


def demod(x, fs, baud, poly=15, block=512, max_hz=None, f_exp=None, f_win=200e3):
    r = _symbols(x, fs, baud, 2, block, max_hz, f_exp, f_win)
    f0, ppm, sps, ph, nb = r["f0"], r["ppm"], r["sps"], r["ph"], r["nb"]
    # the carrier's phase per block from the symbols squared, unwrapped (twice the phase, so the blocks join without
    # 180-degree jumps); the feedthrough taken out first as the symbols' mean
    s = r["s"] - np.mean(r["s"])
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


def demod_ook(x, fs, baud, poly=15, block=512, max_hz=None, f_exp=None, f_win=200e3):
    r = _symbols(x, fs, baud, 1, block, max_hz, f_exp, f_win)
    a = np.abs(r["s"])
    thr = float(np.mean(a))
    for _ in range(30):                                     # two-means: the threshold between the levels
        hi, lo = a[a > thr], a[a <= thr]
        if not len(hi) or not len(lo):
            break
        nxt = 0.5 * (hi.mean() + lo.mean())
        if abs(nxt - thr) <= 1e-9 * thr:
            break
        thr = nxt
    bits = (a < thr).astype(np.uint8)                       # bit 1 the null
    f1, f2 = check(bits, poly), check(1 - bits, poly)
    fails = int(min(f1.sum(), f2.sum()))
    hi, lo = a[a > thr], a[a <= thr]
    q = float((hi.mean() - lo.mean()) / (hi.std() + lo.std())) if len(hi) and len(lo) else None
    nbits = len(f1)
    return {"f0_hz": r["f0"], "ppm": r["ppm"], "sps": r["sps"], "bits": nbits, "fails": fails,
            "ber": fails / 3.0 / nbits if nbits else None, "q": q,
            "off_on": float(lo.mean() / hi.mean()) if len(hi) and len(lo) else None, "blocks": r["nb"],
            "timing_cycles": (r["ph"] / (2 * np.pi)).tolist()[:400], "symbols": r["s"]}


def demod_qpsk(x, fs, baud, poly=15, block=512, max_hz=None, f_exp=None, f_win=200e3):
    r = _symbols(x, fs, baud, 4, block, max_hz, f_exp, f_win)
    s = r["s"] - np.mean(r["s"])
    nb2 = max(1, len(s) // block)
    th4 = np.unwrap([np.angle(np.sum(s[m * block:(m + 1) * block] ** 4)) for m in range(nb2)])
    th = np.interp(np.arange(len(s)), (np.arange(nb2) + 0.5) * block, (th4 - np.pi) / 4.0)
    s = s * np.exp(-1j * th)                                # the corners at 45 + 90 k degrees
    best = None
    for rot in range(4):
        z = s * np.exp(0.5j * np.pi * rot)
        for mirror in (False, True):
            zz = np.conj(z) if mirror else z
            bits = np.empty(2 * len(zz), dtype=np.uint8)
            bits[0::2], bits[1::2] = np.real(zz) < 0, np.imag(zz) < 0
            f = int(check(bits, poly).sum())
            if best is None or f < best[0]:
                best = (f, rot, mirror, zz, len(bits) - TAPS[poly][0])
    fails, rot, mirror, zz, nbits = best
    u = zz / np.mean(np.abs(zz))
    ideal = (np.sign(np.real(u)) + 1j * np.sign(np.imag(u))) / np.sqrt(2)
    evm = float(np.sqrt(np.mean(np.abs(u - ideal) ** 2)))
    return {"f0_hz": r["f0"], "ppm": r["ppm"], "sps": r["sps"], "bits": nbits, "fails": fails,
            "ber": fails / 3.0 / nbits if nbits else None, "evm": evm, "rot90": rot, "mirror": mirror,
            "corners_deg": [float(np.degrees(np.angle(np.mean(u[(np.real(u) > 0) == (a > 0) & ((np.imag(u) > 0) == (b > 0))]))))
                            for a, b in ((1, 1), (1, -1), (-1, 1), (-1, -1))],
            "blocks": r["nb"], "timing_cycles": (r["ph"] / (2 * np.pi)).tolist()[:400], "symbols": zz}


def demod_fsk(x, fs, baud, poly=15, block=512, max_hz=None, f_exp=None, f_win=200e3):
    """binary FSK (the board's, ID 13: TX mode 4 turning the four axis points, a turn a bit, its tones +-baud from
    the carrier): the instantaneous frequency (the phase step between samples), the carrier's offset taken off as its
    mean, then a real NRZ signal: the matched filter, the timing as BPSK's, the bit the tone's sign"""
    x = np.asarray(x, dtype=np.complex128)
    x = x - np.mean(x)
    if f_exp is not None:
        x = x * np.exp(-2j * np.pi * f_exp * np.arange(len(x)) / fs)
        # the receiver's own DC, now at -f_exp, off the discriminator: a low-pass over a quarter symbol
        Lq = max(1, int(round(fs / baud / 4)))
        x = np.convolve(x, np.ones(Lq) / Lq, mode="same")
    d = np.angle(x[1:] * np.conj(x[:-1])) * fs / (2 * np.pi)       # Hz
    f0 = float(np.mean(d))
    d = d - f0
    L = max(1, int(round(fs / baud)))
    y = np.convolve(d, np.ones(L) / L, mode="same")
    r = _om(y, fs, baud, block)
    sv = np.real(r["s"])
    bits = (sv < 0).astype(np.uint8)                                # the lower tone (backwards) 1
    f1, f2 = check(bits, poly), check(1 - bits, poly)
    fails = int(min(f1.sum(), f2.sum()))
    a = np.abs(sv)
    nbits = len(f1)
    return {"f0_hz": f0 + (f_exp or 0.0), "ppm": r["ppm"], "sps": r["sps"], "bits": nbits, "fails": fails,
            "ber": fails / 3.0 / nbits if nbits else None, "dev_hz": float(np.mean(a)),
            "q": float(np.mean(a) / np.std(a)) if np.std(a) > 0 else None, "blocks": r["nb"],
            "timing_cycles": (r["ph"] / (2 * np.pi)).tolist()[:400], "symbols": r["s"]}


DEMOD = {"bpsk": demod, "ook": demod_ook, "qpsk": demod_qpsk, "fsk": demod_fsk}


def synth(baud=1e6, fs=20e6, n_sym=40000, f_off=12e3, ppm=30.0, snr_db=20.0, feed=0.2, poly=15, seed=3, mod="bpsk"):
    rng = np.random.default_rng(seed)
    if mod == "fsk":                                        # continuous phase, the tones +-baud (the board's turns)
        bits = np.resize(prbs_bits(poly), n_sym)
        rate = baud * (1 + ppm * 1e-6)
        t = np.arange(int(n_sym / rate * fs) - 10) / fs
        k = np.minimum((t * rate + 0.37).astype(int), n_sym - 1)
        fi = np.where(bits[k] == 1, -baud, baud)
        x = np.exp(1j * (2 * np.pi * np.cumsum(fi) / fs + 2 * np.pi * f_off * t + 0.7)) + feed
        return x + (rng.normal(size=len(x)) + 1j * rng.normal(size=len(x))) * 10 ** (-snr_db / 20) / np.sqrt(2) * np.sqrt(sps_of(fs, baud))
    if mod == "qpsk":
        b2 = np.resize(prbs_bits(poly), 2 * n_sym)
        a = ((1.0 - 2.0 * b2[0::2]) + 1j * (1.0 - 2.0 * b2[1::2])) / np.sqrt(2)
    else:
        bits = np.resize(prbs_bits(poly), n_sym)
        a = (1.0 - bits) if mod == "ook" else (1.0 - 2.0 * bits)
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
    for mod in ("bpsk", "ook", "qpsk", "fsk"):
        for ppm in (0.0, 30.0, -55.0):
            for snr in (20.0, 8.0):
                x = synth(ppm=ppm, snr_db=snr, mod=mod, f_off=4e6 + 12e3, feed=0.0 if mod == "ook" else 0.2)
                r = DEMOD[mod](x, 20e6, 1e6, f_exp=4e6)
                print("synthetic %s: ppm %+5.1f snr %4.1f dB -> f0 %.1f Hz, ppm %+.2f, %d bits, BER %.2e, %s" % (
                    mod, ppm, snr, r["f0_hz"], r["ppm"], r["bits"], r["ber"],
                    "Q %.1f" % r["q"] if mod in ("ook", "fsk") else "EVM %.2f" % r["evm"]))
