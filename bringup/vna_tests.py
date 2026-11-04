"""The 8720ES tests of MONDAY.md section 2 (TODO rows 6-7): RX ANT's S11 (test A) and the chains' S21 (test F), each
saved as Touchstone into bringup/data/board_A/vna/ (gitignored) with its plot, and the numbers the plan predicts.

    python3 bringup/vna_tests.py measure rxant_unpowered             # port 1 RX ANT, port 2 RX MON, the board off
    python3 bringup/vna_tests.py measure rxant_dsa20 --dsa 20        # the board on: the DSA held at 20 dB throughout
    python3 bringup/vna_tests.py measure txant_txmon --tx-null       # port 1 TX ANT, port 2 TX MON: the TX nulled
    python3 bringup/vna_tests.py measure sw_ant_swrx_tx --ctrl tr_a=0   # the switch block held in transmit
    python3 bringup/vna_tests.py compress rx_dsa0 --dsa 0 --cw 4.0 5.2 --window -58 -40   # gain against drive (P1dB)
    python3 bringup/vna_tests.py levels rx_dsa0 --dsa 0 --powers -46 -40 -34   # S21 sweeps at several drives
    python3 bringup/vna_tests.py tdr CABLE.s2p [...] --length 10    # delay, velocity factor, reflections by distance
    python3 bringup/vna_tests.py summary FILE.s2p [FILE2.s2p ...]    # the numbers again, no instrument

It needs the calibration in force (register 29, BRINGUP_LOG 4.36: full 2-port, 3-6.5 GHz, 1601 points, -40 dBm) and
refuses a source above -30 dBm (RX ANT's absolute maximum is +1 dBm).  With --dsa it sets the board's DSA before each
of the four sweeps, and with --tx-null holds the TX at its carrier null (hold_point(0, 0)) the same way, so the
TX's own carrier does not land in port 1, and with --ctrl holds CTRL bits (tr_a=0: the antenna switch in transmit,
ANT to SW TX; tr_a=1, its rest: ANT to SW RX; tx_dis=1: the modulator off): every such call is a client driving the board, which keeps linkd paused (its idle_s, 60 s) so it
cannot retune or re-level the board while the analyzer sweeps.  The analyzer is left in HOLD: with the 2-port
correction on, every sweep throws option 085's mechanical transfer switch (lab-instrument-control hp/hp.md).
"""
import argparse
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.expanduser("~/lab-instrument-control/hp")
sys.path.insert(0, LIC)
from hp_87xxES import HP87xxES, PARAMETERS                     # noqa: E402
import vna_measure                                              # noqa: E402  (plot, read_s2p, reciprocity)

MAX_SOURCE_DBM = -30.0
# the points the bench's map read the receive chain at (BRINGUP_LOG 3.3, REVB 8) and the link's carriers
SPOT_GHZ = (3.0, 3.5, 4.0, 4.4, 5.0, 5.2, 5.5, 5.725, 5.8, 5.875, 6.1)
S11_BAND = (5.5e9, 6.1e9)             # sim/aslaid/REPORT.md: S11 above -2 dB here, -0.8 dB at 5.8 GHz


def db(x):
    return 20 * np.log10(np.maximum(np.abs(x), 1e-10))


def summary(f, data, name=""):
    lines = ["%s: %d points, %.3f-%.3f GHz" % (name, len(f), f[0] / 1e9, f[-1] / 1e9)]
    for p in PARAMETERS:
        lines.append("  %s  " % p + "  ".join("%g:%+.2f" % (g, db(np.interp(g * 1e9, f, data[p]))) for g in SPOT_GHZ))
    m = (f >= S11_BAND[0]) & (f <= S11_BAND[1])
    s11 = db(data["S11"])
    k_hi, k_lo = np.argmax(s11[m]), np.argmin(s11[m])
    lines.append("  S11 over 5.5-6.1 GHz: worst (highest) %+.2f dB at %.3f GHz, best %+.2f dB at %.3f GHz, mean %+.2f dB"
                 % (s11[m][k_hi], f[m][k_hi] / 1e9, s11[m][k_lo], f[m][k_lo] / 1e9, s11[m].mean()))
    s21 = db(data["S21"])
    k = np.argmax(s21)
    lines.append("  S21 peak %+.2f dB at %.3f GHz;  S12 peak %+.2f dB" % (s21[k], f[k] / 1e9, db(data["S12"]).max()))
    return "\n".join(lines)


def measure(name, dsa=None, board="A", tx_null=False, ctrl=None):
    out = os.path.join(HERE, "data", "board_%s" % board, "vna")
    os.makedirs(out, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    path = os.path.join(out, "%s_%s.s2p" % (stamp, name))
    bench = None
    if dsa is not None or tx_null or ctrl:
        from bench import Bench
        bench = Bench(board, "vna")
    with HP87xxES() as vna:
        pw = vna.power()
        if pw > MAX_SOURCE_DBM:
            raise SystemExit("the source is at %+.1f dBm, above %+.0f: not into this board" % (pw, MAX_SOURCE_DBM))
        if not vna.corrected():
            raise SystemExit("correction is off: recall the calibration first (RECAREG29;)")
        f, data = None, {}
        try:
            for p in PARAMETERS:
                if dsa is not None:
                    bench.board_call("dsa", dsa)
                if tx_null:
                    bench.board_call("hold_point", 0, 0)
                if ctrl:
                    bench.board_call("ctrl", **ctrl)
                f, data[p] = vna.trace(p)
        finally:
            vna.w("HOLD;")
        settings = "%d points, %.0f-%.0f Hz, IF bandwidth %.0f Hz, source %+.2f dBm, kit %s" % (
            len(f), f[0], f[-1], vna.if_bandwidth(), pw, vna.cal_kit())
        with open(path, "w") as fh:
            fh.write("! %s, via bringup/vna_tests.py\n! %s\n! measured %s, %s\n" % (
                vna.idn, name, time.strftime("%Y-%m-%d %H:%M:%S"), settings))
            if dsa is not None:
                fh.write("! board %s, DSA %.2f dB (set before each sweep)\n" % (board, dsa))
            if tx_null:
                fh.write("! board %s, the TX held at its carrier null, hold_point(0, 0), before each sweep\n" % board)
            if ctrl:
                fh.write("! board %s, CTRL bits %s set before each sweep\n" % (board, ctrl))
            fh.write("# HZ S RI R 50\n")
            for n, fr in enumerate(f):
                fh.write("%.0f " % fr + " ".join("%.6e %.6e" % (data[p][n].real, data[p][n].imag) for p in PARAMETERS)
                         + "\n")
    png = path[:-4] + ".png"
    vna_measure.plot(f, data, title="board %s: %s (%s)" % (board, name, stamp), path=png)
    print(summary(f, data, name))
    print("wrote %s\n      %s" % (path, png))
    return path


def compress(name, cws_ghz, start, stop, dsa=None, board="A", ctrl=None, register=29):
    """S21 against source power at each CW frequency (the analyzer's power sweep, the 2-port correction applied at
    the CW frequency), then the calibrated frequency sweep back (RECAREG<register>) and HOLD.  The powers are the
    analyzer's at port 1, so the board's input; never above MAX_SOURCE_DBM."""
    if stop > MAX_SOURCE_DBM:
        raise SystemExit("a power sweep to %+.1f dBm: above %+.0f, not into this board" % (stop, MAX_SOURCE_DBM))
    out = os.path.join(HERE, "data", "board_%s" % board, "vna")
    os.makedirs(out, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    bench = None
    if dsa is not None or ctrl:
        from bench import Bench
        bench = Bench(board, "vna")
    rows = []
    with HP87xxES() as vna:
        if not vna.corrected():
            raise SystemExit("correction is off: recall the calibration first (RECAREG29;)")
        try:
            for g in cws_ghz:
                vna.power_sweep(cw_hz=g * 1e9, start_dbm=start, stop_dbm=stop)
                if not vna.corrected():
                    # 2026-11-03: a power sweep needing another source power range than the calibration's turned the
                    # correction off (error 66, 'CAUTION: CORRECTION TURNED OFF'); uncorrected gains are not usable
                    raise SystemExit("the power sweep %+.0f to %+.0f dBm turned the correction off (%s): this window is "
                                     "outside the calibration's power range" % (start, stop, vna.errors()))
                if dsa is not None:
                    bench.board_call("dsa", dsa)
                if ctrl:
                    bench.board_call("ctrl", **ctrl)
                r = vna.compression("S21")
                path = os.path.join(out, "%s_%s_%gGHz_%+.0f_%+.0fdBm.csv" % (stamp, name, g, start, stop))
                with open(path, "w") as fh:
                    fh.write("# %s, S21 against port 1's power at %.4f GHz%s\npower_dBm,gain_dB,phase_deg\n"
                             % (name, g, "" if dsa is None else ", DSA %.2f dB" % dsa))
                    for pw, ga, ph in zip(r["power"], r["gain"], r["phase"]):
                        fh.write("%.3f,%.4f,%.3f\n" % (pw, ga, ph))
                sm = r["smooth"]
                line = ("%s %.3f GHz, %+.0f to %+.0f dBm: small-signal %+.2f dB, at the top %+.2f dB (%.2f dB down), "
                        "noise %.3f dB, P1dB in %s" % (name, g, start, stop, r["small_signal"], sm[-1],
                                                      r["small_signal"] - sm[-1], r["noise"],
                                                      "none" if r["p_in"] is None else "%+.1f dBm" % r["p_in"]))
                print(line)
                rows.append(line)
        finally:
            vna._opc("RECAREG%d;" % register, sweeps=2, floor=30)
            vna.w("HOLD;")
            print("recalled register %d, held; corrected %s, power %+.1f dBm" % (register, vna.corrected(), vna.power()))
    return rows


def levels(name, powers, dsa=None, board="A", ctrl=None, register=29, home=-40.0):
    """S21 frequency sweeps at several source powers (POWE in the calibrated frequency sweep, which kept the
    correction on where a power sweep in another power range turned it off: 2026-11-03): gain against drive at
    every frequency at once.  Stops (and recalls the register) if the correction drops.  Back at `home`, HOLD."""
    if max(powers) > MAX_SOURCE_DBM:
        raise SystemExit("%+.1f dBm: above %+.0f, not into this board" % (max(powers), MAX_SOURCE_DBM))
    out = os.path.join(HERE, "data", "board_%s" % board, "vna")
    os.makedirs(out, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    bench = None
    if dsa is not None or ctrl:
        from bench import Bench
        bench = Bench(board, "vna")
    res = {}
    with HP87xxES() as vna:
        if not vna.corrected():
            raise SystemExit("correction is off: recall the calibration first (RECAREG29;)")
        ok = False
        try:
            for pw in powers:
                vna.power(pw)
                if not vna.corrected():
                    raise SystemExit("at %+.1f dBm the correction went off (%s)" % (pw, vna.errors()))
                if dsa is not None:
                    bench.board_call("dsa", dsa)
                if ctrl:
                    bench.board_call("ctrl", **ctrl)
                f, s21 = vna.trace("S21")
                res[pw] = s21
                print("%+6.1f dBm: " % pw + "  ".join("%g:%+.2f" % (g, db(np.interp(g * 1e9, f, s21))) for g in SPOT_GHZ),
                      flush=True)
            ok = True
        finally:
            vna.power(home)
            if not ok or not vna.corrected():
                vna._opc("RECAREG%d;" % register, sweeps=2, floor=30)
            vna.w("HOLD;")
            print("back at %+.1f dBm, held; corrected %s" % (vna.power(), vna.corrected()))
    path = os.path.join(out, "%s_%s_levels.csv" % (stamp, name))
    with open(path, "w") as fh:
        fh.write("# %s: |S21| dB against port 1's power%s\nfreq_Hz,%s\n" % (
            name, "" if dsa is None else ", DSA %.2f dB" % dsa, ",".join("%+.1fdBm" % p for p in sorted(res))))
        for n_, fr in enumerate(f):
            fh.write("%.0f," % fr + ",".join("%.3f" % db(res[p][n_]) for p in sorted(res)) + "\n")
    print("wrote", path)
    return f, res


C = 299792458.0


def delay_s(f, s21):
    """the group delay from S21's unwrapped phase, a straight-line fit over the band"""
    ph = np.unwrap(np.angle(s21))
    return -np.polyfit(2 * np.pi * f, ph, 1)[0]


def time_response(f, s, n_fft=1 << 15, beta=6.0):
    """the band-pass time response (as the analyzer's time-domain band-pass mode): a Kaiser window over the
    band, zero-padded; scaled so that one broadband reflection of |G| peaks at |G|.  Returns (t in s, h)"""
    w = np.kaiser(len(f), beta)
    h = np.fft.ifft(s * w, n_fft) * n_fft / w.sum()
    df = (f[-1] - f[0]) / (len(f) - 1)
    return np.arange(n_fft) / (n_fft * df), h


def peaks(t, h, floor_db=-45.0, t_max=None, min_sep=0.4e-9):
    a = db(h)
    idx = [k for k in range(1, len(a) - 1) if a[k] >= a[k - 1] and a[k] > a[k + 1] and a[k] > floor_db
           and (t_max is None or t[k] <= t_max)]
    idx.sort(key=lambda k: -a[k])
    keep = []
    for k in idx:
        if all(abs(t[k] - t[j]) > min_sep for j in keep):
            keep.append(k)
    return sorted(keep)


def tdr(paths, length_m=10.0, board="A"):
    """each 2-port file's electrical delay (S21's phase), the velocity factor for `length_m`, and the band-pass
    time responses of S11 and S22 with their reflections listed by one-way distance; a plot beside the first"""
    import matplotlib.pyplot as plt
    fig, axs = plt.subplots(2, 1, figsize=(10.5, 7.5), sharex=True)
    for n_, p in enumerate(paths):
        f, data, _ = vna_measure.read_s2p(p)
        tau = delay_s(f, data["S21"])
        vf = length_m / (C * tau)
        name = os.path.basename(p)[:-4]
        print("%s: delay %.3f ns, velocity factor %.3f for %.2f m (adapters included)" % (name, tau * 1e9, vf, length_m))
        for ax, sp in zip(axs, ("S11", "S22")):
            t, h = time_response(f, data[sp])
            m = t <= 2.4 * tau
            d = t * C * vf / 2
            ax.plot(d[m], db(h[m]), color=vna_measure.SERIES[n_ % 3], label=name[16:] or name)
            pk = peaks(t, h, t_max=2.4 * tau)
            print("  %s reflections (one-way m, ns round trip, dB): " % sp + ";  ".join(
                "%.3f m %.2f ns %+.1f" % (d[k], t[k] * 1e9, db(h[k])) for k in pk))
    for ax, sp, end in zip(axs, ("S11", "S22"), ("port 1 (the SMA end)", "port 2 (the N end)")):
        ax.set_title("%s time response, from %s" % (sp, end), loc="left")
        ax.set_ylabel("reflection (dB)")
        ax.set_ylim(-80, 0)
        ax.legend(loc="upper right")
    axs[-1].set_xlabel("one-way distance along the cable (m, at each cable's own velocity factor)")
    png = paths[0][:-4] + "_tdr.png"
    fig.savefig(png)
    print("wrote", png)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("measure", "compress", "levels", "summary", "tdr"))
    ap.add_argument("names", nargs="+", help="measure: the test's name; summary: .s2p files")
    ap.add_argument("--dsa", type=float, help="hold the board's DSA at this attenuation (dB) during the sweeps")
    ap.add_argument("--tx-null", action="store_true", help="hold the TX at its carrier null during the sweeps")
    ap.add_argument("--ctrl", help="CTRL bits to hold during the sweeps, e.g. tr_a=0 or tr_a=1,tx_dis=1")
    ap.add_argument("--cw", type=float, nargs="+", default=[5.2], help="compress: the CW frequencies, GHz")
    ap.add_argument("--window", type=float, nargs=2, default=[-58.0, -40.0], help="compress: start and stop, dBm")
    ap.add_argument("--powers", type=float, nargs="+", default=[-46, -43, -40, -37, -34, -31],
                    help="levels: source powers, dBm (none above -30)")
    ap.add_argument("--length", type=float, default=10.0, help="tdr: the cable's physical length, m")
    ap.add_argument("--board", default="A")
    a = ap.parse_args()
    if a.action == "measure":
        ctrl = {k: int(v) for k, v in (kv.split("=") for kv in a.ctrl.split(","))} if a.ctrl else None
        measure(a.names[0], a.dsa, a.board, a.tx_null, ctrl)
    elif a.action == "tdr":
        tdr(a.names, a.length)
    elif a.action == "levels":
        ctrl = {k: int(v) for k, v in (kv.split("=") for kv in a.ctrl.split(","))} if a.ctrl else None
        levels(a.names[0], a.powers, a.dsa, a.board, ctrl)
    elif a.action == "compress":
        ctrl = {k: int(v) for k, v in (kv.split("=") for kv in a.ctrl.split(","))} if a.ctrl else None
        compress(a.names[0], a.cw, a.window[0], a.window[1], a.dsa, a.board, ctrl)
    else:
        for p in a.names:
            f, data, _ = vna_measure.read_s2p(p)
            print(summary(f, data, os.path.basename(p)))


if __name__ == "__main__":
    main()
