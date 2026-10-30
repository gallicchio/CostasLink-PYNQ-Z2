#!/usr/bin/env python3
"""b210.py: the USRP B210 (UHD 4.9, serial 310BR0607) as the link's interference source and band monitor, for the
over-the-air lock tests (Jason, 2026-10-30: four FPV antennas, the Costas board's TX ANT and RX ANT and the B210's
TX/RX and RX2 of channel A; no splitter that reaches 6 GHz).

    python3 bringup/b210.py probe                      the device, its clocks and gains (no RF)
    python3 bringup/b210.py scan [--lo 4900 --hi 5900] the band's occupancy: 20 MHz channels, each received for a
                                                        while, power and the fraction of time over the floor + 10 dB
    python3 bringup/b210.py tone --mhz F --gain G --seconds S          a CW (an offset from the board's carrier)
    python3 bringup/b210.py bursts --mhz F --gain G --bw 20 --on 1 --off 4 --seconds S
                                                        band-limited noise bursts (WiFi-like: on / off in ms)

As a module: B210().tone(...), .bursts(...), .power(...), the lock tests in locklab.py call them.  The TX starts at
the gain asked (default 0, about -60 dBm at 5 GHz) and is never left on: every call ends with its stream.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "board_A", "b210")
SERIAL = "310BR0607"


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, time.strftime("%Y%m%d_%H%M%S")))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


class B210:
    def __init__(self, rate=20e6):
        import uhd
        self.uhd = uhd
        self.u = uhd.usrp.MultiUSRP("serial=%s" % SERIAL)
        self.rate = rate
        self.u.set_rx_antenna("RX2", 0)
        self.u.set_tx_antenna("TX/RX", 0)

    def probe(self):
        u = self.u
        return {"pp": u.get_pp_string(), "rx_gain_range": str(u.get_rx_gain_range(0)),
                "tx_gain_range": str(u.get_tx_gain_range(0)), "rx_freq_range": str(u.get_rx_freq_range(0))}

    # ---- receive ----
    def capture(self, mhz, n=200000, gain=40):
        x = self.u.recv_num_samps(int(n), float(mhz) * 1e6, self.rate, [0], float(gain))
        return np.asarray(x[0])

    def power(self, mhz, seconds=0.05, gain=40, blocks=10):
        """mean and peak power (dBFS) over `blocks` captures, and the fraction of 1 us windows over the median + 10 dB"""
        n = int(self.rate * seconds / blocks)
        p_mean, p_peak, busy = [], [], []
        for _ in range(blocks):
            x = self.capture(mhz, n, gain)
            w = np.abs(x) ** 2
            k = max(1, int(self.rate * 1e-6))
            m = w[: len(w) // k * k].reshape(-1, k).mean(axis=1)
            med = np.median(m) + 1e-20
            p_mean.append(10 * np.log10(w.mean() + 1e-20))
            p_peak.append(10 * np.log10(m.max() + 1e-20))
            busy.append(float((m > 10 * med).mean()))
        return {"mhz": mhz, "gain": gain, "mean_dbfs": float(np.mean(p_mean)), "peak_dbfs": float(np.max(p_peak)),
                "busy": float(np.mean(busy))}

    def scan(self, lo=4900, hi=5900, step=20, seconds=0.2, gain=40):
        rows = []
        for f in range(int(lo), int(hi) + 1, int(step)):
            r = self.power(f, seconds=seconds, gain=gain)
            rows.append(r)
            print("%5d MHz: mean %6.1f dBFS, peak %6.1f, busy %5.1f %%" % (f, r["mean_dbfs"], r["peak_dbfs"], 100 * r["busy"]),
                  flush=True)
        return rows

    # ---- transmit ----
    def _send(self, wave, mhz, seconds, gain):
        wave = np.asarray(wave, dtype=np.complex64)
        self.u.send_waveform(wave, float(seconds), float(mhz) * 1e6, self.rate, [0], float(gain))

    def tone(self, mhz, gain=0.0, seconds=1.0, offset_hz=0.0):
        """a CW at mhz (+ offset_hz), amplitude 0.7 of full scale"""
        n = int(self.rate / 1000)                              # 1 ms of samples, repeated
        t = np.arange(n) / self.rate
        f = offset_hz if offset_hz else 1000.0                 # a 1 kHz offset keeps it off the DC spur
        f = round(f * n / self.rate) * self.rate / n           # a whole number of cycles in the buffer
        self._send(0.7 * np.exp(2j * np.pi * f * t), mhz, seconds, gain)

    def bursts(self, mhz, gain=0.0, bw_mhz=20.0, on_ms=1.0, off_ms=4.0, seconds=1.0, seed=1):
        """band-limited complex noise, on for on_ms and off for off_ms, repeated (a WiFi-like duty cycle)"""
        rng = np.random.default_rng(seed)
        n_on, n_off = int(self.rate * on_ms * 1e-3), int(self.rate * off_ms * 1e-3)
        x = rng.normal(size=n_on) + 1j * rng.normal(size=n_on)
        X = np.fft.fft(x)
        fr = np.fft.fftfreq(n_on, 1 / self.rate)
        X[np.abs(fr) > bw_mhz * 1e6 / 2] = 0
        x = np.fft.ifft(X)
        x = 0.5 * x / (np.sqrt(np.mean(np.abs(x) ** 2)) + 1e-12)
        wave = np.concatenate([x, np.zeros(n_off)]) if n_off else x
        self._send(wave, mhz, seconds, gain)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["probe", "scan", "tone", "bursts"])
    ap.add_argument("--lo", type=float, default=4900)
    ap.add_argument("--hi", type=float, default=5900)
    ap.add_argument("--mhz", type=float, default=5200)
    ap.add_argument("--gain", type=float, default=0.0)
    ap.add_argument("--seconds", type=float, default=1.0)
    ap.add_argument("--bw", type=float, default=20.0)
    ap.add_argument("--on", type=float, default=1.0)
    ap.add_argument("--off", type=float, default=4.0)
    a = ap.parse_args(argv)
    b = B210()
    if a.what == "probe":
        print(json.dumps(b.probe(), indent=1))
    elif a.what == "scan":
        rows = b.scan(a.lo, a.hi)
        print(save("scan", rows))
    elif a.what == "tone":
        b.tone(a.mhz, a.gain, a.seconds)
    elif a.what == "bursts":
        b.bursts(a.mhz, a.gain, a.bw, a.on, a.off, a.seconds)


if __name__ == "__main__":
    main(sys.argv[1:])
