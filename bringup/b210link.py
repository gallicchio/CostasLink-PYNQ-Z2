#!/usr/bin/env python3
"""b210link.py: the USRP B210 as the other end of the link, both ways, with clocks that are not coherent (Jason,
2026-10-30: "We'll need timing recovery when we go to two Costas boards, so you might as well start now going from
the B210 to the Costas board and also vice versa").  The bench of weekend.py (four antennas within 30-40 cm).

    python3 bringup/b210link.py offset   [--mhz 5200]    the board's TX carrier as the B210 hears it (its offset in
                                                          the B210's frame: where the B210 must send to land on the
                                                          board's RX LO at VC_LOCK)
    python3 bringup/b210link.py from     [--mhz 5200]    board -> B210: the board sends BPSK PRBS15 at 1-10 Mbaud, the
                                                          B210 captures, sdr_rx.py recovers the carrier and the timing
                                                          and checks the PRBS: the BER, the clocks' offset in ppm
    python3 bringup/b210link.py pattern  [--mhz 5200]    board -> B210: the board's TX constellation itself (Jason,
                                                          2026-11-01: where does Q's 0.6 of I come from?): A1, A2,
                                                          A3's states sent half the time (the self-test's QPSK pattern),
                                                          the B210 captures, its idle carrier the phase reference, the
                                                          states clustered: each state's I and Q against the idle's
    python3 bringup/b210link.py to       [--mhz 5200]    B210 -> board, the board's TX muted: the board locks to the
                                                          B210's carrier; A1 and A3 events from the B210 decided by the
                                                          board; BPSK PRBS15 from the B210 checked by the board's
                                                          fixed-phase BER check (no timing recovery in the gateware):
                                                          the phase scan and short segments show the drift; then the
                                                          B210's rate trimmed by the measured ppm (pre-compensated)

    python3 bringup/b210link.py self     [--mhz 5400]    B210 -> B210 (Jason, 2026-11-01: every link for every test):
                                                          its TX/RX antenna to its RX2, BPSK, OOK and QPSK PRBS15 with its
                                                          rate trimmed 25 ppm (one chip's TX and RX share a clock), 200
                                                          MHz from the board's link (at 5240 the self-test's own data,
                                                          BPSK up to 50 Mbaud: +-50 MHz, swamped it)
    --mods bpsk,ook,qpsk                                  'from' and 'self': the modulations (ID 12's OOK; QPSK the TX's
                                                          mode 3 on A3's corners, two PRBS bits a symbol)
    --rate 20e6                                           'to': the B210's stream rate; at 10 Ms/s or more 'to' also sends
                                                          A3's corners at the self-test's QPSK rate (2.5 M a second, the
                                                          idle between), the four in turn (one alone pulls the loop)

Data go to bringup/data/board_A/b210link/.  The board is left muted and held, the B210 silent.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import weekend as W                                  # noqa: E402
import campaign as C                                 # noqa: E402
import linktests as LT                               # noqa: E402
import stages as S                                   # noqa: E402
import sdr_rx                                        # noqa: E402
from b210 import Stream, prbs_bits                   # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "b210link")


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "%s_%s.json" % (name, LT.O.stamp()))
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return os.path.relpath(path, HERE)


def data_buffer(mod, baud, rate, cyc, trim_ppm=0.0, reps=4):
    """PRBS15 at baud as BPSK (+-1), OOK (bit 1 nothing) or QPSK (two bits a symbol, I first; two periods so the
    pairs run on across the buffer's repeat), sampled at rate (trimmed by trim_ppm), a whole number of park cycles"""
    bits = prbs_bits(15)
    if mod == "fsk":                                 # continuous phase, the tones +-baud (as the board's turns)
        sps = rate / baud * (1 + (trim_ppm or 0.0) * 1e-6)
        n = int(round(len(bits) * reps * sps / cyc)) * cyc
        idx = np.minimum((np.arange(n) / sps).astype(int), len(bits) * reps - 1) % len(bits)
        f = np.where(bits[idx] == 1, -baud, baud)
        return np.exp(2j * np.pi * np.cumsum(f) / rate)
    if mod == "qpsk":
        b2 = np.concatenate([bits, bits])
        sym = ((1.0 - 2.0 * b2[0::2]) + 1j * (1.0 - 2.0 * b2[1::2])) / np.sqrt(2)
    else:
        sym = (1.0 - bits) if mod == "ook" else (1.0 - 2.0 * bits)
    sps = rate / baud * (1 + (trim_ppm or 0.0) * 1e-6)
    n = int(round(len(sym) * reps * sps / cyc)) * cyc
    idx = np.minimum((np.arange(n) / sps).astype(int), len(sym) * reps - 1) % len(sym)
    return sym[idx].astype(np.complex128)


def _quality(mod, r):
    if mod == "fsk":
        return "tones +-%.0f kHz, Q %.1f" % (r["dev_hz"] / 1e3, r["q"])
    return ("Q %.1f" % r["q"]) if mod == "ook" else ("EVM %.2f" % r["evm"])


def b210_self(mhz=5400, mods=("bpsk", "ook", "qpsk", "fsk"), bauds=(0.25e6, 1e6, 2e6), rate=16e6, park_hz=-4e6, tx_gain=60,
              rx_gain=45, trim_ppm=25.0, n=2000000, caps=3, bb=None):
    """B210 -> B210 over the air: its TX/RX antenna to its RX2 (30-40 cm); the stream at rate with its LO park_hz off,
    the capture at the same rate with the RX LO rate / 5 below the carrier; each modulation's PRBS15 trimmed by
    trim_ppm, recovered by sdr_rx (the recovered clocks' offset should read the trim).  A note on the board's page
    for the while (the self-test records the B210's activity from it)."""
    import b210 as BB
    import soak
    bb = bb or BB.B210()
    out = {"mhz": mhz, "rate": rate, "trim_ppm": trim_ppm, "tx_gain": tx_gain, "rx_gain": rx_gain, "runs": []}
    t = time.time()
    note = soak.post("/api/note", {"text": "B210 -> B210 at %d MHz (%.0f MHz from the carrier), TX gain %.0f: the B210 tested "
                                           "on its own (b210link.py self)" % (mhz, mhz - 5200, tx_gain),
                                   "kind": "intervention", "source": "b210link.py", "t_start": t, "t_end": t + 600,
                                   "b210": {"kind": "selfloop", "mhz": mhz, "gain": tx_gain}})
    st = BB.Stream(bb, mhz, tx_gain, rate=rate, park_hz=park_hz, amp=0.5)
    st.start(np.ones(int(rate * 1e-3) // st.cyc * st.cyc))
    prev = st._buf.shape[1]
    try:
        for mod in mods:
            for baud in bauds:
                st.set(data_buffer(mod, baud, rate, st.cyc, trim_ppm=trim_ppm))
                time.sleep(0.3 + prev / rate)        # the buffer before goes out to its end first (0.25 Mbaud's: 0.52 s)
                prev = st._buf.shape[1]
                u0 = st.underflows
                res = []
                for _ in range(caps):
                    x, ovf, errs = bb.rx(mhz - rate / 5 / 1e6, n, rate, rx_gain, bw=rate)
                    x = x[2000:]
                    if ovf:
                        res.append({"error": "overflow", "ovf": ovf})
                        continue
                    try:
                        r = sdr_rx.DEMOD[mod](x, rate, baud, block=512 if baud < 5e6 else 1024, f_exp=rate / 5)
                        r.pop("symbols")
                        r.pop("timing_cycles")
                        r["rms"] = float(np.sqrt(np.mean(np.abs(x) ** 2)))
                    except Exception as e:                       # noqa: BLE001
                        r = {"error": str(e)[:200]}
                    res.append(r)
                ok = [r for r in res if "ber" in r]
                row = {"mod": mod, "baud": baud, "caps": res, "underflows": st.underflows - u0,
                       "bits": sum(r["bits"] for r in ok), "fails": sum(r["fails"] for r in ok)}
                row["ber"] = row["fails"] / 3.0 / row["bits"] if row["bits"] else None
                out["runs"].append(row)
                print("%d B210 -> B210 %s %.2f Mbaud: %d bits, BER %s; clocks %s ppm (the trim %+.0f); %s; rms %s; underflows %d" % (
                    mhz, mod.upper(), baud / 1e6, row["bits"], row["ber"] if row["ber"] is None else "%.2e" % row["ber"],
                    ["%+.2f" % r["ppm"] for r in ok], trim_ppm, [_quality(mod, r) for r in ok],
                    ["%.3f" % r["rms"] for r in ok], row["underflows"]), flush=True)
    finally:
        st.stop()
        if note.get("id"):
            soak.post("/api/note", {"id": note["id"], "end": True})
    return out


class Link(W.Weekend):
    ext = False                                      # True: the B210 is the transmitter, the board's TX stays muted

    def tx(self, on):
        if self.ext:
            self.cl.ctrl(tx_dis=1)
            time.sleep(0.05)
            return
        super().tx(on)

    # ---- the board's carrier in the B210's frame ----
    def offset(self, mhz, lo_off=0.25e6, rate=1e6, n=1000000, gain=45):
        self.ext = False
        self.tune(mhz)                                   # both synthesizers there (the rounds may have left them anywhere)
        self.set_null(mhz)
        self.tx(True)
        time.sleep(0.3)
        try:
            x, ovf, errs = self.bb.rx(mhz + lo_off / 1e6, int(n), rate, gain, bw=rate, mcr=32e6)
        finally:
            self.tx(False)
        x = x[1000:]
        N = 1 << int(np.ceil(np.log2(len(x))))
        X = np.abs(np.fft.fft(x * np.hanning(len(x)), N))
        f = np.fft.fftfreq(N, 1 / rate)
        sel = np.abs(f + lo_off) < 60e3
        k = int(np.argmax(np.where(sel, X, 0)))
        a, b, c = X[k - 1], X[k], X[(k + 1) % N]
        d = 0.5 * (a - c) / (a - 2 * b + c)
        f_pk = f[k] + d * rate / N
        delta = f_pk + lo_off
        snr = 20 * np.log10(b / np.median(X[sel]))
        r = {"mhz": mhz, "delta_hz": float(delta), "ppm": float(delta / (mhz * 1e6) * 1e6), "peak_over_median_db": float(snr)}
        print("%d MHz: the board's carrier at %+.1f Hz in the B210's frame (%+.3f ppm; %.0f dB over the floor)" % (
            mhz, delta, r["ppm"], snr), flush=True)
        return r

    # ---- board -> B210 ----
    MCR = {4e6: 32e6, 10e6: 40e6, 20e6: 40e6, 40e6: 40e6}      # even decimations: the halfband filters kept

    def from_board(self, mhz, runs=((1000, 1e6), (100, 4e6), (40, 10e6), (20, 20e6), (10, 40e6)), caps=4, gain=45,
                   mod="bpsk"):
        """the board's PRBS15 at 100 / p Mbaud (the carrier nulled, the windows irrelevant) as BPSK, OOK (ID 12: bit 1
        the null) or QPSK (mode 3 on A3's corners, two bits a symbol); the B210 at fs, its LO a fifth of fs below the
        carrier (off its own DC), `caps` captures of 0.1 s or 2 M samples, every packet's overflow counted (a capture
        with one is dropped)"""
        self.ext = False
        # FSK (ID 13): the four axis points turned, a turn a bit (its direction the PRBS's), the tones +-baud
        points = {"bpsk": [(1, 0), (-1, 0)], "ook": [(1, 0), (0, 0)], "qpsk": list(C.SCHEMES["A3"].msgs),
                  "fsk": [(1, 0), (0, 1), (-1, 0), (0, -1)]}[mod]
        out = {"mhz": mhz, "mod": mod, "runs": []}
        if mod == "fsk" and not getattr(self.cl, "fsk", False):
            print("%d board -> B210 FSK: the overlay has no FSK data (ID 13)" % mhz, flush=True)
            return dict(out, error="no FSK data before ID 13")
        self.tune(mhz)
        self.set_null(mhz)
        cl = self.cl
        try:
            for p, fs in runs:
                baud = 100e6 / p / (len(points) if mod == "fsk" else 1)
                cl.tx_points(C.point_code(1, 0), [C.point_code(*q) for q in points])
                cl.tx_timing(period=p)
                cl.tx_prbs(15)
                if mod == "fsk":
                    cl.tx_mode("rotate", n=len(points), source="prbs")
                else:
                    cl.tx_mode("prbs", n=len(points))
                cl.ctrl(tx_dis=0)
                cl.tx_go()
                time.sleep(0.2)
                lo = float(mhz) * 1e6 - fs / 5
                res = []
                for _ in range(caps):
                    n = int(min(2e6, max(0.1 * fs, 400000)))
                    x, ovf, errs = self.bb.rx(lo / 1e6, n, fs, gain, bw=fs, mcr=self.MCR.get(fs, 32e6))
                    x = x[2000:]
                    if ovf:
                        res.append({"error": "overflow", "ovf": ovf})
                        continue
                    try:
                        r = sdr_rx.DEMOD[mod](x, fs, baud, block=512 if baud < 5e6 else 1024, f_exp=fs / 5)
                        r.pop("symbols")
                        r.pop("timing_cycles")
                        r["rms"] = float(np.sqrt(np.mean(np.abs(x) ** 2)))
                    except Exception as e:                       # noqa: BLE001
                        r = {"error": str(e)[:200]}
                    res.append(r)
                cl.tx_stop()
                cl.hold_point(1, 0)
                ok = [r for r in res if "ber" in r]
                row = {"period": p, "baud": baud, "fs": fs, "caps": res,
                       "bits": sum(r["bits"] for r in ok), "fails": sum(r["fails"] for r in ok)}
                row["ber"] = row["fails"] / 3.0 / row["bits"] if row["bits"] else None
                out["runs"].append(row)
                print("%d board -> B210 %s %5.1f Mbaud (fs %.0f Ms/s): %d bits, BER %s; carrier %s kHz; clocks %s ppm; %s" % (
                    mhz, mod.upper(), baud / 1e6, fs / 1e6, row["bits"], row["ber"] if row["ber"] is None else "%.2e" % row["ber"],
                    ["%.2f" % ((r["f0_hz"] + fs / 5) / 1e3) for r in ok], ["%+.3f" % r["ppm"] for r in ok],
                    [_quality(mod, r) for r in ok]), flush=True)
        finally:
            cl.tx_stop()
            cl.ctrl(tx_dis=1)
        return out

    # ---- board -> B210: the TX's own constellation ----
    def pattern(self, mhz, schemes=("A1", "A2", "A3"), fs=20e6, gain=45, caps=3):
        """each scheme's states at random half the time (40 clocks a symbol, 20 of them the state: 2.5 M a second), as
        the self-test's pattern; the B210 at fs (its LO fs / 5 below), the carrier found from the idle's line (half the
        time: the mean of the states is the idle's half), each 1 ms block turned so its mean (the idle) lies on +I, the
        samples between two states dropped, and k-means from the nominal states: each state's position against the
        idle's (the B210's own I / Q matched to a percent, so what is left is the board's TX: its ladders, VR's null,
        the modulator)"""
        self.ext = False
        cl = self.cl
        self.tune(mhz)
        self.set_null(mhz)
        out = {"mhz": mhz, "fs": fs, "schemes": {}}
        try:
            for name in schemes:
                tx = C.SCHEMES[name]
                cl.tx_points(tx.tx_idle(), [C.point_code(i, q) for i, q in tx.msgs])
                cl.ctrl(tx_dis=0)
                cl.events(period=40, width=20, count=0, n=tx.n, source="prbs" if tx.n > 1 else "count")
                cl.tx_go()
                time.sleep(0.2)
                lo = float(mhz) * 1e6 - fs / 5
                pts = []
                for _ in range(caps):
                    x, ovf, errs = self.bb.rx(lo / 1e6, int(0.05 * fs), fs, gain, bw=fs, mcr=self.MCR.get(fs, 32e6))
                    x = np.asarray(x[2000:])
                    if ovf:
                        continue
                    pts.append(self._stable_points(x, fs))
                cl.tx_stop()
                cl.hold_point(1, 0)
                if not pts:
                    out["schemes"][name] = {"error": "every capture overflowed"}
                    continue
                z = np.concatenate(pts)
                res = self._clusters(z, [complex(*tx.idle)] + [complex(i, q) for i, q in tx.msgs])
                res["n"] = int(len(z))
                out["schemes"][name] = res
                print("%s: the idle at 1; %s" % (name, "; ".join("state %d (TX %+d, %+d) at I %+.3f, Q %+.3f (|%.3f|)" % (
                    k, m[0], m[1], c[0], c[1], abs(complex(*c))) for k, (m, c) in enumerate(zip(tx.msgs, res["states"])))), flush=True)
                self._plot_pattern(name, z, res)
        finally:
            cl.tx_stop()
            cl.hold_point(1, 0)
        return out

    @staticmethod
    def _stable_points(x, fs, block_s=1e-3):
        N = 1 << int(np.ceil(np.log2(len(x))))
        X = np.abs(np.fft.fft(x * np.hanning(len(x)), N))
        f = np.fft.fftfreq(N, 1 / fs)
        sel = np.abs(f - fs / 5) < 80e3
        k = int(np.argmax(np.where(sel, X, 0)))
        a, b, c = X[k - 1], X[k], X[(k + 1) % N]
        f_pk = f[k] + 0.5 * (a - c) / (a - 2 * b + c) * fs / N
        y = x * np.exp(-2j * np.pi * f_pk * np.arange(len(x)) / fs)
        nb = int(block_s * fs)
        out = []
        for k0 in range(0, len(y) - nb, nb):
            blk = y[k0:k0 + nb]
            m = np.mean(blk)                                 # the idle's half (the states average to nothing)
            blk = blk * np.exp(-1j * np.angle(m)) / (2 * abs(m))
            d1 = np.abs(np.diff(blk))
            keep = np.zeros(len(blk), bool)
            keep[1:-1] = (d1[:-1] < 0.15) & (d1[1:] < 0.15)   # not on the way between two states
            out.append(blk[keep])
        return np.concatenate(out)

    @staticmethod
    def _clusters(z, nominal, iters=30):
        c = np.array(nominal, complex) * np.array([1.0] + [0.8] * (len(nominal) - 1))
        for _ in range(iters):
            lab = np.argmin(np.abs(z[:, None] - c[None, :]), axis=1)
            c = np.array([z[lab == k].mean() if np.any(lab == k) else c[k] for k in range(len(c))])
        idle = c[0]
        rel = c * np.exp(-1j * np.angle(idle)) / abs(idle)
        spread = [float(np.std(np.abs(z[lab == k] - c[k]))) / abs(idle) if np.any(lab == k) else None for k in range(len(c))]
        share = [float(np.mean(lab == k)) for k in range(len(c))]
        return {"idle": [float(idle.real), float(idle.imag)], "states": [[float(v.real), float(v.imag)] for v in rel[1:]],
                "spread": spread, "share": share}

    @staticmethod
    def _plot_pattern(name, z, res):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(5, 5))
        zz = z[:: max(1, len(z) // 20000)]
        ax.plot(zz.real, zz.imag, ".", ms=1, alpha=0.3, color="#1e3a8a")
        for k, (i, q) in enumerate([[1.0, 0.0]] + res["states"]):
            ax.plot(i, q, "s", mfc="none", mec="#d64545", ms=10)
            ax.annotate("idle" if k == 0 else str(k - 1), (i, q), textcoords="offset points", xytext=(8, 6), color="#d64545")
        ax.axhline(0, color="#999", lw=0.5); ax.axvline(0, color="#999", lw=0.5)
        ax.set_aspect("equal"); ax.set_xlim(-1.6, 1.6); ax.set_ylim(-1.6, 1.6)
        ax.set_title("%s from the board's TX, as the B210 hears it (the idle at 1)" % name, fontsize=10)
        fig.tight_layout()
        os.makedirs(OUT, exist_ok=True)
        fig.savefig(os.path.join(OUT, "pattern_%s_%s.png" % (name, LT.O.stamp())), dpi=90)
        plt.close(fig)

    def corners_turn(self, mhz, st, period_s=0.4e-6, width_s=0.2e-6, seconds=0.2, delay=96, settle=6):
        """A3's four corners in turn at the self-test's QPSK rate (2.5 M a second, the idle between): one corner sent
        alone at that rate pulls the Costas loop (its mean, (1, 0.5) at half duty, turns the loop 27 degrees and the idle's
        Q with it), so the corners go in turn, the mean on the idle's axis.  The decisions in one row of the matrix: every
        symbol decided, a quarter on each corner, none undecided, is the pass (which symbol went where is not known)"""
        out = []
        rate = self.stream.rate
        P, Wd = int(round(period_s * rate)), max(1, int(round(width_s * rate)))
        tx = C.SCHEMES["A3"]
        for mirror in (True, False):
            rx = C.Frame0(tx, st["side"], mirror=mirror)
            rx_s = C.Scheme("A3", tx.text, rx.rx_point(tx.idle), [rx.rx_point(m) for m in tx.msgs], [], t=tx.t, t2=tx.t2)
            rx_s.mask, rx_s.use = tx.mask, tx.use
            base = np.full(P * 4 * 25, complex(*tx.idle))
            for k in range(4 * 25):
                base[k * P: k * P + Wd] = complex(*tx.msgs[k % 4])
            self.stream.set(base)
            self.cl.rx_config(rx_s.idle_vector(), rx_s.mask, rx_s.lut(False), rx_s.slow_exp(), delay=delay, quiet=4,
                              confirm=10, window=100, row=0, settle=settle)
            time.sleep(0.05)
            self.cl.rx_clear()
            time.sleep(seconds)
            self.cl.rx_enable(False)
            s_ = self.cl.rx_stats()
            dec = self.cl.confusion()[0][:4]
            self.stream.set(np.full(P * 50, complex(*tx.idle)))
            sent = seconds / period_s
            r = {"mirror": mirror, "sent_about": sent, "events": s_["events"], "decided": s_["decided"], "decoded": dec,
                 "delay": delay, "settle": settle}
            out.append(r)
            print("%d B210 -> board A3's corners in turn at %.2f M a second (Q %s, delay %d settle %d): %d events for about "
                  "%d sent, %d decided, each corner %s" % (mhz, 1e-6 / period_s, "mirrored" if mirror else "as is", delay,
                                                           settle, s_["events"], sent, s_["decided"], dec), flush=True)
            time.sleep(0.1)
        return out

    # ---- B210 -> board: the board's receiver against the B210's exact states ----
    # no pure-Q states: the board's loop is a hard-limited Costas loop (sign of I times Q), and a state with I near zero
    # gives it a sign from noise or the slightest turn: half the time on (0, +-1) pulled it to -48 degrees (12:50)
    RX_PATTERNS = {"corners": [(1, 1), (1, -1), (-1, 1), (-1, -1)], "flip": [(-1, 0)]}

    @staticmethod
    def duty_steps(pts, floor=0.002):
        """a comparator's duty against its threshold (it falls as the threshold rises past each level the signal spends
        time at): the steps, each [its middle (V), its height (the share of time at that level)]"""
        v = np.array([p[0] for p in pts])
        d = np.array([p[1] for p in pts])
        fall = -np.diff(d)
        mids = 0.5 * (v[1:] + v[:-1])
        steps, run = [], []
        for k in range(len(fall) + 1):
            if k < len(fall) and fall[k] > floor:
                run.append(k)
                continue
            if run:
                w = fall[run]
                steps.append([float(np.sum(mids[run] * w) / np.sum(w)), float(np.sum(w))])
                run = []
        return [s_ for s_ in steps if s_[1] > 0.03]

    def rx_accuracy(self, mhz, st, period_s=4e-6, width_s=2e-6, span=0.26, step=0.001, seconds=0.004):
        """the B210's states (its DAC's numbers, its I and Q matched to about a percent) as the board's receiver sees
        them: each pattern the idle half the time and its states in turn (balanced, so the loop, about 3 kHz wide, sees
        the idle's axis), each window's threshold swept in 1 mV steps and its comparator's duty read; each state's level
        is where the duty steps by its share.  Q's scale against I's (the axes), a pure-Q state's I (the quadrature
        error), an exact flip's Q (the receiver's own part of A1's Q, REVB 35)"""
        rate = self.stream.rate
        P, Wd = int(round(period_s * rate)), int(round(width_s * rate))
        cen = {w: st["cen"][w]["v0"] for w in ("QP", "QN", "IP", "IN")}
        out = {"mhz": mhz, "cen": cen, "a": st["a"], "side": st["side"], "period_s": period_s, "width_s": width_s,
               "patterns": {}}
        try:
            for pname, states in self.RX_PATTERNS.items():
                self.stream.set(np.ones(P * 50))       # the lock checked on the idle alone first, found again if gone
                time.sleep(0.3)
                o = self.observe(st["cen"], st["a"])
                if o["state"] != "locked":
                    st2 = self.lock_ext(mhz, self._delta, gain=self._gain, rate=rate)
                    if st2 is None:
                        out["patterns"][pname] = {"error": "no lock before it (%s)" % o["state"]}
                        continue
                    st = st2
                    cen = {w: st["cen"][w]["v0"] for w in ("QP", "QN", "IP", "IN")}
                base = np.full(P * len(states) * 20, complex(1, 0))
                for k in range(len(states) * 20):
                    base[k * P: k * P + Wd] = complex(*states[k % len(states)])
                self.stream.set(base)
                time.sleep(0.5)
                sweeps, steps = {}, {}
                for w in ("QP", "QN", "IP", "IN"):
                    vs = [float(x) for x in np.arange(cen[w] - span, cen[w] + span + 1e-9, step)]
                    pts = [(v, d) for v, r, d in self.cl.threshold_scan(w, vs, seconds=seconds)]
                    sweeps[w] = [[round(v, 4), round(d, 5)] for v, d in pts]
                    steps[w] = [[round(1e3 * (m - cen[w]), 2), round(h, 3)] for m, h in self.duty_steps(pts)]
                self.stream.set(np.ones(P * 50))       # judged on the idle: the pattern itself reads as 'beating'
                time.sleep(0.3)
                o = self.observe(st["cen"], st["a"])
                self.stream.set(base)
                out["patterns"][pname] = {"states": states, "sweeps": sweeps, "steps_mv": steps,
                                          "lock_after": {k: o[k] for k in ("state", "di", "vc")}}
                print("%d rxcal %-7s %s: %s; then %s" % (mhz, pname, states, "; ".join(
                    "%s %s" % (w, " ".join("%+.1f mV x%.2f" % (m, h) for m, h in steps[w])) for w in steps), o["state"]),
                    flush=True)
        finally:
            self.stream.set(np.ones(P * 50))
            self.thresholds(st["cen"], st["a"], 0.5)
        return out

    def rx_scope(self, mhz, st, period_s=4e-6, width_s=2e-6, caps=5, tdiv=5e-6, only=None):
        """the same states on the bench scope (I MON, Q MON at 50 ohm, probe factor 21: volts at the arm): each state's
        cluster from thousands of samples, the samples between states dropped; relative to the idle on the same channel,
        so a channel's gain error cancels in the flip's Q (the receiver's own share of A1's 30 mV, REVB 35).  Q's scale
        against I's from the corners carries the scope's two channels' gains (about 1 %)"""
        import scopewatch as SW
        sc = self.b.scope
        rate = self.stream.rate
        P, Wd = int(round(period_s * rate)), int(round(width_s * rate))
        # each pattern: its states, and a turn of the whole buffer (the loop locks to the turned idle, so each of the
        # board's quadrants is fed by another of the B210's codes: an error that stays put is the board's); 'small'
        # the corners at 0.71 of the idle's amplitude, not 1.41 (compression shows as an error that goes away)
        C4 = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        pats = {"idle": ([], 1), "flip": ([(-1, 0)], 1), "corners": (C4, 1),
                "small": ([(0.5 * a_, 0.5 * b_) for a_, b_ in C4], 1), "idle_j": ([], 1j), "corners_j": (C4, 1j),
                # the window comparators silenced (thresholds at the top: never high), I's alone and all four: if the
                # corners' asymmetry (Q 7-15 % smaller on the idle's side of I) goes, it is their switching on the node
                "corners_noiwin": (C4, 1), "corners_nowin": (C4, 1)}
        if only:
            pats = {k: v for k, v in pats.items() if k in only}
        out = {"mhz": mhz, "side": st["side"], "a": st["a"], "patterns": {}}
        try:
            for pname, (states, rot) in pats.items():
                if states:
                    base = np.full(P * len(states) * 20, complex(1, 0))
                    for k in range(len(states) * 20):
                        base[k * P: k * P + Wd] = complex(*states[k % len(states)])
                else:
                    base = np.ones(P * 50, dtype=complex)
                self.stream.set(base * rot)
                if pname in ("corners_noiwin", "corners_nowin"):
                    for w in (("IP", "IN") if pname == "corners_noiwin" else ("QP", "QN", "IP", "IN")):
                        self.cl.threshold(w, 2.499)
                time.sleep(0.5)
                I, Q = [], []
                for _ in range(caps):
                    i, q, dt = SW.capture(sc, tdiv)
                    I += i
                    Q += q
                I, Q = np.array(I), np.array(Q)
                # the clusters: k-means from the idle (the densest place) and each state at the middle plus the idle's
                # vector turned by the state's angle (the patterns are balanced: the middle is twice the mean less the
                # idle; a mirrored Q gives the same set of corners, so the mirror does not matter)
                z = I + 1j * Q
                if not states:                            # the idle alone: its place for the patterns after (per turn)
                    z_idle = complex(np.median(I), np.median(Q))
                    idle_alone = z_idle
                else:
                    z_idle = idle_alone
                # the patterns' mean is the middle plus half the idle's vector times (1 + the states' mean direction):
                # the corners average to the middle (2 mean - idle), a flip half the time is the middle itself
                ub = 1.0 + (np.mean([complex(a_, b_) for a_, b_ in states]) if states else 0)
                origin = (complex(np.mean(I), np.mean(Q)) - 0.5 * ub * z_idle) / (1 - 0.5 * ub) if states else 0j
                v = z_idle - origin
                cents = np.array([z_idle] + [origin + v * complex(a_, b_) for a_, b_ in states], dtype=complex)
                r_keep = 0.25 * abs(v) if states else 0.05
                for _ in range(20):
                    dd = np.abs(z[:, None] - cents[None, :])
                    lab = np.argmin(dd, axis=1)
                    keep = dd[np.arange(len(z)), lab] < r_keep
                    for k in range(len(cents)):
                        m = keep & (lab == k)
                        if m.sum() > 10:
                            cents[k] = np.mean(z[m])
                spread = [float(np.std(np.abs(z[keep & (lab == k)] - cents[k]))) * 1e3 if (keep & (lab == k)).sum() > 10 else None
                          for k in range(len(cents))]
                row = {"states": states, "n": int(len(z)), "kept": int(keep.sum()),
                       "centres_mv": [[round(c.real * 1e3, 2), round(c.imag * 1e3, 2)] for c in cents],
                       "spread_mv": [round(x, 2) if x is not None else None for x in spread],
                       "shares": [round(float(np.mean(lab[keep] == k)), 3) for k in range(len(cents))]}
                if pname == "flip":
                    # the tilt of the line from the idle to the flip: their Q apart on the same channel over their I
                    # apart (the board's own TX: about 30 mV on a 0.35 V swing, 5 degrees of tilt for its 10 off 180)
                    row["flip_dq_mv"] = round((cents[1].imag - cents[0].imag) * 1e3, 2)
                    row["flip_tilt_deg"] = round(float(np.degrees(np.arctan2(cents[1].imag - cents[0].imag,
                                                                             abs(cents[1].real - cents[0].real)))), 2)
                if pname in ("corners", "small", "corners_j", "corners_noiwin", "corners_nowin"):
                    m_ = np.mean(cents[1:])                  # about the corners' own centre (no middle needed)
                    cs = cents[1:] - m_
                    ref = (cents[0] - m_) / abs(cents[0] - m_)   # the idle's direction: 0 degrees
                    cr = cs / ref
                    row["corner_i_mv"] = [round(abs(c.real) * 1e3, 1) for c in cr]
                    row["corner_q_mv"] = [round(abs(c.imag) * 1e3, 1) for c in cr]
                    row["q_over_i"] = round(float(np.mean(np.abs(cr.imag)) / np.mean(np.abs(cr.real))), 4)
                    row["corner_deg"] = [round(float(np.degrees(np.angle(c))), 1) for c in cr]
                    row["idle_over_corner_i"] = round(float(abs(cents[0] - m_) / np.mean(np.abs(cr.real))), 4)
                if pname in ("corners_noiwin", "corners_nowin"):
                    self.thresholds(st["cen"], st["a"], 0.5)
                out["patterns"][pname] = row
                print("%d rxscope %-7s centres %s mV (spread %s, shares %s)%s" % (
                    mhz, pname, row["centres_mv"], row["spread_mv"], row["shares"],
                    (": the flip's Q %+.1f mV from the idle's, the line between them tilted %+.2f degrees" % (row["flip_dq_mv"], row["flip_tilt_deg"])) if pname == "flip" else
                    (": |I| %s, |Q| %s mV, Q/I %.4f, angles %s" % (row["corner_i_mv"], row["corner_q_mv"], row["q_over_i"], row["corner_deg"])) if "q_over_i" in row else ""),
                    flush=True)
        finally:
            self.stream.set(np.ones(P * 50))
        return out

    # ---- B210 -> board ----
    def lock_ext(self, mhz, delta_hz, gain=80, rate=4e6, park_hz=-1e6, target=0.15):
        """the board's TX muted, its centres taken with the B210 silent, then the B210's carrier at the board's RX LO
        (mhz + delta: where the board's own carrier sits in the B210's frame) and the DSA stepped down to a lock"""
        self.ext = True
        self.tx(False)
        self.center(mhz)
        self._cen[mhz] = self.centres()
        st = Stream(self.bb, mhz + delta_hz / 1e6, gain, rate=rate, park_hz=park_hz)
        st.start(np.ones(int(rate * 1e-3)))
        self.stream = st
        cen, best = self.lock_ota(mhz, target=target, fresh=False)
        if best is None:
            return None
        dsa, a, lk = best
        self.thresholds(cen, a, 0.5)
        self.cl.dac(S.DAC2, V_T2=2.9)
        o = self.observe(cen, a)
        print("%d locked to the B210 at DSA %.2f, leg %.3f V, VC %.3f V (%+.1f kHz from VC_LOCK)" % (
            mhz, dsa, a, o["vc"], (o["vc"] - LT.VC_LOCK) * self.kv(mhz) / 1e3), flush=True)
        return {"cen": cen, "dsa": dsa, "a": a, "side": o["side"], "vc": o["vc"]}

    def events_ext(self, mhz, st, names=("A1", "A3"), period_s=20e-6, width_s=0.5e-6, seconds=0.5, delay=200, settle=0,
                   label=""):
        """the B210 sends one message's events (every period_s, width_s long, from the idle) for a while; the board's
        decoder in this lock's frame, its confusion row fixed at that message: the decisions by message"""
        out = []
        rate = self.stream.rate
        P, Wd = int(round(period_s * rate)), max(1, int(round(width_s * rate)))
        for name in names:
            tx = C.SCHEMES[name]
            for mirror in (True, False):
                rx = C.Frame0(tx, st["side"], mirror=mirror)
                rx_s = C.Scheme(name, tx.text, rx.rx_point(tx.idle), [rx.rx_point(m) for m in tx.msgs], [], t=tx.t, t2=tx.t2)
                rx_s.mask, rx_s.use = tx.mask, tx.use
                rows = []
                for m, (i, q) in enumerate(tx.msgs):
                    base = np.full(P * 50, complex(*tx.idle))
                    for k in range(50):
                        base[k * P: k * P + Wd] = complex(i, q)
                    self.stream.set(base)
                    self.cl.rx_config(rx_s.idle_vector(), rx_s.mask, rx_s.lut(False), rx_s.slow_exp(), delay=delay, quiet=4,
                                      confirm=10, window=100, row=m, settle=settle)
                    time.sleep(0.05)
                    self.cl.rx_clear()
                    time.sleep(seconds)
                    self.cl.rx_enable(False)        # the counts and the matrix read alike (the engine stopped: ID 10)
                    s_ = self.cl.rx_stats()
                    cm = self.cl.confusion()
                    self.stream.set(np.full(P * 50, complex(*tx.idle)))
                    dec = cm[m][:tx.n]
                    sent = seconds / period_s
                    rows.append({"msg": m, "sent_about": sent, "events": s_["events"], "decided": s_["decided"],
                                 "decoded": dec, "confirm": s_["confirm"], "veto": s_["veto"]})
                    time.sleep(0.1)
                right = sum(r["decoded"][r["msg"]] for r in rows)
                total = sum(r["decided"] for r in rows)
                out.append({"scheme": name, "label": label, "period_s": period_s, "width_s": width_s, "mirror": mirror,
                            "rows": rows, "right": right, "decided": total})
                print("%d B210 -> board %s%s (Q %s): %s; right %d of %d decided" % (
                    mhz, name, label, "mirrored" if mirror else "as is", "; ".join(
                        "m%d: %d events, decoded %s" % (r["msg"], r["events"], r["decoded"]) for r in rows), right, total), flush=True)
                if right >= 0.95 * total and total:
                    break
        return out

    def ber_ext(self, mhz, st, baud=1e6, seconds=0.02, nseg=60, trim_ppm=None):
        """the B210 sends BPSK PRBS15 (bit 0 at the idle's +I); the board's BER check, which samples CMP_I once a
        symbol at a fixed phase on its own clock: a phase scan (16 phases), then nseg segments of `seconds` at the
        best phase.  trim_ppm: the B210's symbol rate scaled to the board's clock (the waveform resampled)"""
        p = int(round(100e6 / baud))
        base = self.bpsk_buffer(baud, trim_ppm)
        self.stream.set(base)
        time.sleep(0.3)
        cl = self.cl
        cl.tx_timing(period=p)
        o = self.observe(st["cen"], st["a"])
        res = {"baud": baud, "period": p, "trim_ppm": trim_ppm, "lock": {k: o[k] for k in ("state", "di", "dq", "vc")}}

        def seg(ph, inv, sec):
            cl.ber_config(15, ph, invert=inv, enable=True)
            time.sleep(sec)
            cl.ber_config(15, ph, invert=inv, enable=False)
            r = cl.ber()
            return r["ber"] if r["ber"] is not None else 1.0, r["bits"]

        nph = 16
        phs = [int(k * 8 * p / nph) for k in range(nph)]
        scan = {inv: [seg(ph, inv, seconds)[0] for ph in phs] for inv in (False, True)}
        inv = min(scan, key=lambda v: min(scan[v]))
        best = phs[int(np.argmin(scan[inv]))]
        res.update(scan={str(k): v for k, v in scan.items()}, invert=inv, phase=best)
        segs = []
        t0 = time.time()
        for _ in range(nseg):
            b, nb = seg(best, inv, seconds)
            segs.append((round(time.time() - t0, 4), b, nb))
        res["segs"] = segs
        clean = sum(1 for s in segs if s[1] == 0)
        res["clean"] = clean
        self.stream.set(np.ones(len(base) // self.stream.cyc * self.stream.cyc))
        print("%d B210 -> board BPSK %.2f Mbaud%s: phase scan %s; at phase %d %d of %d segments of %.0f ms clean, rates %s" % (
            mhz, baud / 1e6, " (trimmed %+.3f ppm)" % trim_ppm if trim_ppm is not None else "",
            " ".join("%.2f" % x for x in scan[inv]), best, clean, nseg, seconds * 1e3,
            " ".join("0" if s[1] == 0 else "%.3f" % s[1] for s in segs[:30])), flush=True)
        return res

    def bpsk_buffer(self, baud, trim_ppm=None, reps=4, ook=False):
        bits = prbs_bits(15)
        sym = (1.0 - bits) if ook else (1.0 - 2.0 * bits)       # OOK: bit 0 the carrier, bit 1 nothing
        sps = self.stream.rate / baud * (1 + (trim_ppm or 0.0) * 1e-6)
        n = int(round(len(sym) * reps * sps / self.stream.cyc)) * self.stream.cyc
        idx = np.minimum((np.arange(n) / sps).astype(int), len(sym) * reps - 1) % len(sym)
        return sym[idx].astype(np.complex128)

    def ber_cdr_ext(self, mhz, st, baud=1e6, seconds=1.0, nseg=10, gain=4, ook=False):
        """the B210's BPSK PRBS15 checked by the board with the timing recovered (ID version 4): the polarity from a
        short run each way, then nseg runs of `seconds`; each run's clock offset from the recovery's corrections
        (-sum / samples elapsed), read while it runs (a write of RX_BER_CFG restarts the recovery)"""
        cl = self.cl
        p = int(round(100e6 / baud))
        self.stream.set(self.bpsk_buffer(baud, ook=ook))
        time.sleep(0.3)
        cl.tx_timing(period=p)
        # OOK (ID 12): read on the I window on the carrier's side of this lock
        src = ("IP" if st["side"] > 0 else "IN") if ook else "I"

        def run(inv, sec):
            u0 = self.stream.underflows
            cl.ber_config(15, None, invert=inv, enable=True, cdr=True, gain=gain, period=p, src=src)
            time.sleep(sec)
            c = cl.cdr_state()
            b_run = cl.rd("RX_BER_BITS")
            cl.ber_config(15, None, invert=inv, enable=False, cdr=True, gain=gain, period=p, src=src)
            r = cl.ber()
            ppm = -c["sum_samples"] / (b_run * p * cl.ser) * 1e6 if b_run else None
            return {"bits": r["bits"], "mismatches": r["mismatches"], "ber": r["ber"], "ppm": ppm,
                    "underflows": self.stream.underflows - u0, **c}

        trial = {inv: run(inv, 0.1) for inv in (False, True)}
        inv = min(trial, key=lambda v: trial[v]["ber"] if trial[v]["ber"] is not None else 1.0)
        runs = [run(inv, seconds) for _ in range(nseg)]
        bits = sum(r["bits"] for r in runs)
        mism = sum(r["mismatches"] for r in runs)
        o = self.observe(st["cen"], st["a"])
        res = {"mod": "ook" if ook else "bpsk", "baud": baud, "period": p, "gain": gain, "invert": inv, "trial": {str(k): v for k, v in trial.items()},
               "runs": runs, "bits": bits, "mismatches": mism, "ber": mism / 3.0 / bits if bits else None,
               "lock_after": {k: o[k] for k in ("state", "di", "vc")}}
        self.stream.set(np.ones(int(self.stream.rate * 1e-3)))
        print("%d B210 -> board %s %.2f Mbaud, timing recovered (gain %d): %d bits, %d mismatches (BER %s); clocks %s ppm; "
              "runs clean %d of %d; the B210's underflows per run %s" % (
                  mhz, "OOK" if ook else "BPSK", baud / 1e6, gain, bits, mism, res["ber"] if not res["ber"] else "%.2e" % res["ber"],
                  " ".join("%+.2f" % r["ppm"] for r in runs if r["ppm"] is not None),
                  sum(1 for r in runs if r["mismatches"] == 0), nseg, [r["underflows"] for r in runs]), flush=True)
        return res

    def to_board(self, mhz, delta_hz, ppm_clk=None, gain=80, fixed=True, events=True, rate=4e6):
        out = {"mhz": mhz, "delta_hz": delta_hz, "rate": rate}
        st = self.lock_ext(mhz, delta_hz, gain=gain, rate=rate)
        try:
            if st is None:
                out["error"] = "no lock to the B210"
                print(out["error"], flush=True)
                return out
            out["lock"] = st
            if events:
                out["events"] = self.events_ext(mhz, st, names=("A1", "A1w", "A2", "A3"))
                if self.stream.rate >= 10e6:          # the self-test's QPSK rate: 40 clocks a symbol, 20 of them the corner
                    out["corners_turn"] = self.corners_turn(mhz, st)
            out["ber"] = [self.ber_ext(mhz, st, baud=1e6)] if fixed else []
            if fixed and ppm_clk is not None:
                out["ber"].append(self.ber_ext(mhz, st, baud=1e6, trim_ppm=-ppm_clk))
                out["ber"].append(self.ber_ext(mhz, st, baud=1e6, trim_ppm=ppm_clk))
            if getattr(self.cl, "cdr", False):
                out["ber_cdr"] = []
                for ook in ((False, True) if getattr(self.cl, "ber_src", False) else (False,)):
                    for baud in (1e6, 2e6):
                        out["ber_cdr"].append(self.ber_cdr_ext(mhz, st, baud=baud, gain=4, ook=ook))
        finally:
            self.stream.stop()
            self.ext = False
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", nargs="+", choices=["offset", "from", "to", "pattern", "self", "rxcal", "rxscope"])
    ap.add_argument("--mhz", type=float, default=None, help="5200 (5400 for 'self' alone: 200 MHz from the board's link)")
    ap.add_argument("--gain", type=float, default=80)
    ap.add_argument("--no-fixed", action="store_true", help="skip the fixed-phase BER runs")
    ap.add_argument("--no-events", action="store_true")
    ap.add_argument("--mods", default="bpsk,ook,qpsk,fsk", help="'from' and 'self': the modulations (fsk: ID 13)")
    ap.add_argument("--only", default=None, help="'rxscope': its patterns, e.g. idle,corners,corners_noiwin")
    ap.add_argument("--rate", type=float, default=4e6, help="'to': the B210's stream rate (10e6 or more: A3 at 2.5 M/s too)")
    a = ap.parse_args(argv)
    mods = [m for m in a.mods.split(",") if m]
    if a.what == ["self"]:
        mhz = int(a.mhz or 5400)
        out = {"self": b210_self(mhz, mods=mods)}
        print(save("b210self_%d" % mhz, out))
        return
    L = Link()
    out = {}
    mhz = int(a.mhz or 5200)
    import soak
    t = time.time()
    # announced on the board's page: the loop held, the TX muted and the board locked to the B210 are this test's, not
    # losses of the link's own (35 'unannounced losses' in ten minutes on the page, 2026-11-01 11:14-11:22)
    note = soak.post("/api/note", {"text": "B210 link test (b210link.py %s): the board's loop held, its TX muted and the "
                                           "board locked to the B210 in turn; linkd and the self-test stand by" % " ".join(a.what),
                                   "kind": "intervention", "source": "b210link.py", "t_start": t, "t_end": t + 3600,
                                   "b210": {"kind": "link", "what": a.what}})
    try:
        if "offset" in a.what or "to" in a.what:
            out["offset"] = L.offset(mhz)
        if "from" in a.what:
            out["from"] = {m: L.from_board(mhz, mod=m) for m in mods}
        if "pattern" in a.what:
            out["pattern"] = L.pattern(mhz)
        if "to" in a.what:
            ppm = None
            if out.get("from"):
                pp = [c["ppm"] for f in out["from"].values() for r in f["runs"] for c in r["caps"] if "ppm" in c]
                ppm = float(np.median(pp)) if pp else None
            out["to"] = L.to_board(mhz, out["offset"]["delta_hz"], ppm_clk=ppm, gain=a.gain, fixed=not a.no_fixed,
                                   events=not a.no_events, rate=a.rate)
        if "self" in a.what:
            out["self"] = b210_self(mhz + 200, mods=mods, bb=L.bb)
        if "rxcal" in a.what:                          # the board's receiver against the B210's exact states
            if "offset" not in out:
                out["offset"] = L.offset(mhz)
            L._delta, L._gain = out["offset"]["delta_hz"], a.gain
            st = L.lock_ext(mhz, L._delta, gain=a.gain, rate=a.rate)
            out["rxcal"] = L.rx_accuracy(mhz, st) if st else {"error": "no lock to the B210"}
        if "rxscope" in a.what:                        # the same on the bench scope (scopewatch.py stopped first)
            if "offset" not in out:
                out["offset"] = L.offset(mhz)
            st = L.lock_ext(mhz, out["offset"]["delta_hz"], gain=a.gain, rate=a.rate)
            out["rxscope"] = L.rx_scope(mhz, st, only=a.only.split(",") if a.only else None) if st else {"error": "no lock to the B210"}
    finally:
        try:
            L.cl.dac(S.DAC2, V_T2=S.V_MID)
            L.restore()
            L.cleanup()
        except Exception:                                    # noqa: BLE001
            pass
        if note.get("id"):
            soak.post("/api/note", {"id": note["id"], "end": True})
        path = save("b210link_%d" % mhz, out)
        L.b.record("verdict", test="b210link", ok=None, file=path,
                   text="the B210 as the other end: board -> B210 with software carrier and timing recovery; B210 -> "
                        "board events and the fixed-phase BER check against the clocks' drift")
        print(path)


if __name__ == "__main__":
    main(sys.argv[1:])
