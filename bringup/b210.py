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
import threading
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

    def rx(self, mhz, n, rate, gain, chan=0, antenna="RX2", bw=None, mcr=None, settle=0.05):
        """n samples through our own RX streamer, every packet's metadata checked: returns (x, overflows, other
        errors).  mcr: the master clock set first (an even decimation keeps the halfband filters: 32 MHz for 4 Ms/s,
        40 MHz for 10 / 20 Ms/s); bw: the analog filter (default: the rate)"""
        uhd, u = self.uhd, self.u
        if mcr:
            u.set_master_clock_rate(float(mcr))
        u.set_rx_antenna(antenna, chan)
        u.set_rx_rate(float(rate), chan)
        u.set_rx_freq(uhd.types.TuneRequest(float(mhz) * 1e6), chan)
        u.set_rx_gain(float(gain), chan)
        u.set_rx_bandwidth(float(bw or rate), chan)
        time.sleep(settle)
        st = uhd.usrp.StreamArgs("fc32", "sc16")
        st.channels = [chan]
        rs = u.get_rx_stream(st)
        md = uhd.types.RXMetadata()
        spp = rs.get_max_num_samps()
        buf = np.zeros((1, spp), dtype=np.complex64)
        out = np.zeros(int(n), dtype=np.complex64)
        cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
        cmd.num_samps = int(n)
        cmd.stream_now = True
        rs.issue_stream_cmd(cmd)
        got, ovf, errs = 0, 0, []
        t_end = time.time() + n / rate + 3.0
        while got < n and time.time() < t_end:
            k = rs.recv(buf, md, 1.0)
            if md.error_code == uhd.types.RXMetadataErrorCode.overflow:
                ovf += 1
            elif md.error_code not in (uhd.types.RXMetadataErrorCode.none,):
                errs.append(str(md.error_code))
                if md.error_code == uhd.types.RXMetadataErrorCode.timeout:
                    break
            k = min(k, n - got)
            out[got:got + k] = buf[0, :k]
            got += k
        rs = None
        return out[:got], ovf, errs

    def info(self):
        u = self.u
        return {"mboard": u.get_mboard_name(), "rx_subdev": str(u.get_rx_subdev_spec()),
                "rx0": u.get_rx_subdev_name(0), "rx_antennas0": list(u.get_rx_antennas(0)),
                "n_rx": u.get_rx_num_channels(), "mcr": u.get_master_clock_rate(), "pp": u.get_pp_string()}

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

    def tone(self, mhz, gain=0.0, seconds=1.0, offset_hz=0.0, rate=2e6):
        """a CW at mhz (+ offset_hz), amplitude 0.7 of full scale: at 2 Ms/s with a 50 ms buffer, which Python keeps
        fed (at 20 Ms/s and 1 ms the stream underflowed and the tone had gaps)"""
        r0 = self.rate
        self.rate = rate
        try:
            n = int(rate * 0.05)
            t = np.arange(n) / rate
            f = offset_hz if offset_hz else 1000.0             # a 1 kHz offset keeps it off the DC spur
            f = round(f * n / rate) * rate / n                 # a whole number of cycles in the buffer
            self._send(0.7 * np.exp(2j * np.pi * f * t), mhz, seconds, gain)
        finally:
            self.rate = r0

    def bursts(self, mhz, gain=0.0, bw_mhz=8.0, on_ms=1.0, off_ms=4.0, seconds=1.0, seed=1, rate=10e6):
        """band-limited complex noise, on for on_ms and off for off_ms, repeated (a WiFi-like duty cycle); at 10 Ms/s,
        8 MHz wide by default, which Python keeps fed"""
        r0 = self.rate
        self.rate = rate
        try:
            return self._bursts(mhz, gain, bw_mhz, on_ms, off_ms, seconds, seed)
        finally:
            self.rate = r0

    def _bursts(self, mhz, gain, bw_mhz, on_ms, off_ms, seconds, seed):
        rng = np.random.default_rng(seed)
        n_on, n_off = int(self.rate * on_ms * 1e-3), int(self.rate * off_ms * 1e-3)
        x = rng.normal(size=n_on) + 1j * rng.normal(size=n_on)
        X = np.fft.fft(x)
        fr = np.fft.fftfreq(n_on, 1 / self.rate)
        X[np.abs(fr) > bw_mhz * 1e6 / 2] = 0
        x = np.fft.ifft(X)
        x = 0.5 * x / (np.sqrt(np.mean(np.abs(x) ** 2)) + 1e-12)
        wave = np.concatenate([x, np.zeros(n_off)]) if n_off else x
        reps = max(1, int(np.ceil(0.05 * self.rate / len(wave))))   # a buffer of 50 ms or more: fewer underflows
        self._send(np.tile(wave, reps), mhz, seconds, gain)


class Stream:
    """a continuous TX stream whose buffer can be swapped while it runs (a carrier, then events or data) with no retune
    and no gap: the B210 as a transmitter of the link (2026-10-30, Jason: "start now going from the B210 to the Costas
    board and also vice versa").  The baseband is shifted by park_hz in software and the LO tuned the other way, so
    the B210's own LO leak sits park_hz from the signal; every buffer must hold a whole number of park cycles (the
    phase then runs on across a swap)."""

    def __init__(self, b, mhz, gain, rate=4e6, park_hz=-1e6, amp=0.5):
        self.b, self.rate, self.park, self.amp = b, float(rate), float(park_hz), amp
        self.mhz, self.gain = mhz, gain
        self.cyc = int(round(abs(rate / park_hz))) if park_hz else 1
        self._buf = None
        self._stop = threading.Event()
        self._th = None
        self.sent = 0
        self.error = None
        self.underflows = 0                              # UHD's async reports: gaps in what went out
        self.t_first = None                              # time.time() of the first buffer handed to UHD

    def shape(self, base, min_s=0.02):
        """complex baseband (unit scale) to the buffer streamed: amp times it, shifted by park_hz; the length is cut to a
        whole number of park cycles.  A buffer shorter than min_s is repeated to at least that: a 400-sample buffer at
        20 Ms/s took 50 000 sends a second from Python, which underflowed (each a jump in the carrier's phase that slipped
        the board's loop to its other lock point, 2026-11-01)"""
        base = np.asarray(base, dtype=np.complex128)
        if len(base) and len(base) // self.cyc * self.cyc == len(base) and len(base) < min_s * self.rate:
            base = np.tile(base, int(np.ceil(min_s * self.rate / len(base))))
        n = len(base) // self.cyc * self.cyc
        t = np.arange(n) / self.rate
        return (self.amp * base[:n] * np.exp(2j * np.pi * self.park * t)).astype(np.complex64).reshape(1, -1)

    def set(self, base):
        self._buf = self.shape(base)

    def start(self, base):
        self.set(base)
        uhd = self.b.uhd
        u = self.b.u
        u.set_tx_rate(self.rate, 0)
        u.set_tx_freq(uhd.types.TuneRequest(float(self.mhz) * 1e6 - self.park), 0)
        u.set_tx_gain(float(self.gain), 0)
        st = uhd.usrp.StreamArgs("fc32", "sc16")
        st.channels = [0]
        self._tx = u.get_tx_stream(st)
        self._stop.clear()
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()
        self._ta = threading.Thread(target=self._watch, daemon=True)
        self._ta.start()
        time.sleep(0.2)
        return self

    def _watch(self):
        uhd = self.b.uhd
        md = uhd.types.TXAsyncMetadata()
        while not self._stop.is_set():
            tx = self._tx
            if tx is None:
                break
            try:
                if tx.recv_async_msg(md, 0.1) and md.event_code in (uhd.types.TXMetadataEventCode.underflow,
                                                                    uhd.types.TXMetadataEventCode.underflow_in_packet):
                    self.underflows += 1
            except Exception:                            # noqa: BLE001
                break

    def _run(self):
        md = self.b.uhd.types.TXMetadata()
        try:
            while not self._stop.is_set():
                if self.t_first is None:
                    self.t_first = time.time()
                self.sent += self._tx.send(self._buf, md)
        except Exception as e:                               # noqa: BLE001
            self.error = str(e)
        finally:
            md.end_of_burst = True
            try:
                self._tx.send(np.zeros((1, 1), dtype=np.complex64), md)
            except Exception:                                # noqa: BLE001
                pass

    def stop(self):
        self._stop.set()
        if self._th:
            self._th.join(timeout=3)
        if getattr(self, "_ta", None):
            self._ta.join(timeout=1)
        self._tx = None


def prbs_bits(poly=15):
    a, b = {7: (7, 6), 9: (9, 5), 15: (15, 14), 23: (23, 18), 31: (31, 28)}[poly]
    n = (1 << a) - 1
    s = [1] * a
    out = np.empty(n, dtype=np.uint8)
    for k in range(n):
        bit = s[a - 1] ^ s[b - 1]
        out[k] = bit
        s = [bit] + s[:-1]
    return out


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
