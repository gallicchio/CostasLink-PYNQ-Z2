"""The round trip on an independent clock: an SDR's two coherent receive channels on the two boards' TX MONs (QPV_TIMING_REVIEW
section 6; Jason: the B210 or X310 are in the cupboard).  Channel 0 on V's TX MON (J201, U.FL: its challenges leave here),
channel 1 on P's TX MON (its replies): the time from each challenge's edge to its reply's edge, in the SDR's samples,
interpolated at the edge; nothing on either board times anything.  With the dishes in the challenge's path the difference
is the prover's turnaround plus 139.75 ns (4.43) plus the reply's path.

Cabling: TX MON is about 20 dB under TX ANT (-12 dBm at +8): a 10-20 dB pad into each SDR input (the B210's RX takes
-15 dBm at most, the X310's UBX about 0 dBm).  The challenge carrier at --mhz-c (5200), the reply at --mhz-r (5400): the
SDR's LO midway (5300) with a rate wide enough for both (B210: 30.72 MS/s on two channels is not; use --mhz-c 5200
--mhz-r 5210 for the B210, or the X310 at 200 MS/s with the UBX-160), or the two channels on separate LOs on the X310.
V's challenges periodic (qpvtests.py roundtrip --period 10000, or any run: this script only listens).

    python3 bringup/sdrtime.py --args "type=b200" --rate 30.72e6 --lo 5205e6 --seconds 2 --gain 30
    python3 bringup/sdrtime.py --args "addr=192.168.10.2" --rate 200e6 --lo 5300e6 --seconds 0.5

Untested on hardware (written 2026-11-04 night without an SDR at hand): the UHD calls follow bringup/b210.py's.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "twoboard")


def capture2(args, lo, rate, gain, seconds, chans=(0, 1), antenna="RX2"):
    import uhd
    u = uhd.usrp.MultiUSRP(args)
    for c in chans:
        u.set_rx_rate(rate, c)
        u.set_rx_freq(uhd.types.TuneRequest(lo), c)
        u.set_rx_gain(gain, c)
        try:
            u.set_rx_antenna(antenna, c)
        except RuntimeError:
            pass
    n = int(seconds * rate)
    st = uhd.usrp.StreamArgs("fc32", "sc16")
    st.channels = list(chans)
    rx = u.get_rx_stream(st)
    buf = np.zeros((len(chans), n), dtype=np.complex64)
    md = uhd.types.RXMetadata()
    cmd = uhd.types.StreamCMD(uhd.types.StreamMode.num_done)
    cmd.num_samps = n
    cmd.stream_now = False
    cmd.time_spec = u.get_time_now() + uhd.types.TimeSpec(0.1)
    rx.issue_stream_cmd(cmd)
    got = 0
    spp = rx.get_max_num_samps()
    tmp = np.zeros((len(chans), spp), dtype=np.complex64)
    while got < n:
        k = rx.recv(tmp, md, 1.0)
        if md.error_code != uhd.types.RXMetadataErrorCode.none:
            print("rx:", md.strerror(), file=sys.stderr)
            if k == 0:
                break
        k = min(k, n - got)
        buf[:, got:got + k] = tmp[:, :k]
        got += k
    return buf[:, :got], rate


def edges(x, rate, f_off, thresh=0.5, min_gap_s=1e-6):
    """the times (s) at which a carrier's baseband (mixed down from f_off to DC and low-passed) steps: an event is a
    change of the complex envelope; the edge time is where |d/dt| of the smoothed envelope peaks, interpolated"""
    t = np.arange(len(x)) / rate
    y = x * np.exp(-2j * np.pi * f_off * t)
    # low-pass by a short moving average (a few samples), then the envelope's difference
    w = max(2, int(rate / 20e6))
    y = np.convolve(y, np.ones(w) / w, mode="same")
    d = np.abs(np.diff(y))
    lim = thresh * d.max() if d.max() > 0 else 1.0
    out = []
    last = -1e9
    i = 1
    while i < len(d) - 1:
        if d[i] > lim and d[i] >= d[i - 1] and d[i] >= d[i + 1] and (i / rate - last) > min_gap_s:
            # parabolic interpolation of the peak
            a, b, c = d[i - 1], d[i], d[i + 1]
            den = (a - 2 * b + c)
            frac = 0.5 * (a - c) / den if den else 0.0
            out.append((i + frac) / rate)
            last = i / rate
        i += 1
    return np.array(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--args", default="type=b200")
    ap.add_argument("--rate", type=float, default=30.72e6)
    ap.add_argument("--lo", type=float, default=5205e6)
    ap.add_argument("--mhz-c", type=float, default=5200.0)
    ap.add_argument("--mhz-r", type=float, default=5210.0)
    ap.add_argument("--gain", type=float, default=30.0)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--max-pair-s", type=float, default=2e-6, help="a reply must follow its challenge within this")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    buf, rate = capture2(a.args, a.lo, a.rate, a.gain, a.seconds)
    os.makedirs(DATA, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    np.save(os.path.join(DATA, "sdrtime_%s.npy" % stamp), buf)
    ec = edges(buf[0], rate, a.mhz_c * 1e6 - a.lo)
    er = edges(buf[1], rate, a.mhz_r * 1e6 - a.lo)
    pairs = []
    j = 0
    for tc in ec:
        while j < len(er) and er[j] < tc:
            j += 1
        if j < len(er) and er[j] - tc <= a.max_pair_s:
            pairs.append((tc, er[j], (er[j] - tc) * 1e9))
    d = np.array([p[2] for p in pairs])
    out = {"t": stamp, "note": a.note, "rate": rate, "lo": a.lo, "challenges": int(len(ec)), "replies": int(len(er)),
           "pairs": int(len(pairs)), "sample_ns": 1e9 / rate}
    if len(d):
        out.update(mean_ns=float(d.mean()), p50_ns=float(np.median(d)), min_ns=float(d.min()), max_ns=float(d.max()),
                   std_ns=float(d.std()), p99_ns=float(np.percentile(d, 99)))
    json.dump(out, open(os.path.join(DATA, "sdrtime_%s.json" % stamp), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
