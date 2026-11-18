"""The TX's spectrum on the DSA875 in each mute state: where the baseband null's noise is (2026-11-04, REVB 55's
"First on rev A", BRINGUP_LOG 4.54/4.55).

switch_probe.py found that the null (the ladders at (0, 0)) leaves broadband power 33-41 dB under the carrier, part
of it gone with the TX synthesizer's RFOUTA off and the rest only with DSOP.  This takes its spectrum: which offsets,
how it compares with the carrier's own skirts, and whether it has lines (the FPGA's clocks, the 25 MHz PFD).
The answer (4.55): not noise, but REVB 5's 25 MHz sidebands and the carrier of a null trimmed on RX MON; the TX's
noise at the null is about -144 dBm/Hz on TX ANT, which needs --att 0 to see (the analyzer's floor is -144 there).

Cabling (Jason, by hand), --at:
    ant     TX ANT -> short cable -> SW TX (J402);  SW RX (J403) -> short cable -> RX ANT;  ANT (J401) -> DSA875.
            TR_A 0 puts SW TX (the TX) on the analyzer; the state "rx_side" (TR_A 1) shows what comes out of RX ANT
            backwards, plus the TX through the switch's isolation
    txant   TX ANT -> DSA875 directly (about +10 dBm in the carrier state: the analyzer takes +20 with 10 dB or more
            of attenuation; this keeps 30 dB for the carrier and while the board changes state, --att otherwise)
    never TX ANT straight to RX ANT

    python3 bringup/tx_spectrum.py --cabled --at ant
    python3 bringup/tx_spectrum.py --cabled --at txant --states carrier null dsop --avg 16

The states (the loop held, the TX point held, TX_MODE 5):
    carrier        (+a, 0), both synthesizers on
    null           (0, 0) as 0101;  null_1010 as 1010;  null_trim as 0101 with --null-vr's VR_I and VR_Q
    null_txlo_off  the null with the TX synthesizer's RFOUTA off (register 4 with RFA_EN clear)
    null_rxlo_off  the null with the RX synthesizer's RFOUTA off (the RX LO is at the same frequency here)
    dsop           TX_DIS high (the modulator's output off), both synthesizers on
    dsop_txlo_off  DSOP with the TX RFOUTA off;  all_off  DSOP with both RFOUTAs off: near enough the floor
    rx_side        (--at ant only) TR_A 1, DSOP: what RX ANT sends back out, through SW RX to ANT
The spans: wide 10 MHz-7.5 GHz (1 MHz RBW, peak detector), band fc +-250 MHz (1 MHz, RMS), near +-20 MHz (100 kHz,
RMS), close +-1 MHz (10 kHz, RMS); each the power average of --avg sweeps.  Traces go to
bringup/data/board_A/switch/<time>_spectrum_<at>.npz (gitignored), the summary to a .json beside it.
Afterwards CTRL, the TX registers, both synthesizers' register 4, VR_I / VR_Q and the DSA are put back; a server restart
(night.restart_server()) reprograms both synthesizers whatever this leaves.
"""
import argparse
import json
import math
import os
import sys
import time
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("COSTAS_BENCH_CONFIG", os.path.join(HERE, "bench_config_laptop.json"))
sys.path.insert(0, HERE)
import bench as B                                                    # noqa: E402  (also puts the drivers on the path)
from rigol_DSA875 import DSA875, usbtmc_node, USB_VENDOR, USB_PRODUCT  # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "gateware"))
import max2871_regs                                                  # noqa: E402

SERVER = "http://%s:8080" % os.environ.get("COSTAS_PYNQ_HOST", "192.168.2.99")   # board B: COSTAS_PYNQ_HOST=192.168.2.98
OUT_DIR = os.path.join(HERE, "data", "board_A", "switch")
CARR, NULL, NULL2 = 0b0111, 0b0101, 0b1010   # ladder codes {Q1 Q0 I1 I0}: (+a, 0), (0, 0), (0, 0)
# name: (tr_a, tx_dis, code, tx RFOUTA, rx RFOUTA)
STATES = {
    "carrier":       (0, 0, CARR, 1, 1),
    "null":          (0, 0, NULL, 1, 1),
    "null_1010":     (0, 0, NULL2, 1, 1),
    "null_trim":     (0, 0, NULL, 1, 1),     # with --null-vr's VR_I / VR_Q (link.json's otherwise)
    "null_txlo_off": (0, 0, NULL, 0, 1),
    "null_rxlo_off": (0, 0, NULL, 1, 0),
    "dsop":          (0, 1, NULL, 1, 1),
    "dsop_txlo_off": (0, 1, NULL, 0, 1),
    "all_off":       (0, 1, NULL, 0, 0),
    "rx_side":       (1, 1, NULL, 1, 1),
}
# name: (start or None, stop or None, half span about fc, rbw, detector)
SPANS = {
    "wide":  (10e6, 7.5e9, None, 1e6, "POSitive"),
    "band":  (None, None, 250e6, 1e6, "RMS"),
    "near":  (None, None, 20e6, 100e3, "RMS"),
    "close": (None, None, 1e6, 10e3, "RMS"),
}
OFFSETS_MHZ = (0.05, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 94, 150, 240)


def db_mean(traces):
    """the power average of traces in dBm"""
    return 10 * np.log10(np.mean(10 ** (np.asarray(traces) / 10), axis=0))


def density_at(f, dbm, rbw, f0, df, width):
    """the median level near f0 + df and f0 - df, over +-width/2, as dBm/Hz (RBW, not its noise bandwidth)"""
    out = {}
    for sgn in (1, -1):
        m = np.abs(f - (f0 + sgn * df)) <= width / 2
        if m.any():
            out["+" if sgn > 0 else "-"] = round(float(np.median(dbm[m])) - 10 * math.log10(rbw), 1)
    return out


def band_power(f, dbm, rbw, f0, half, exclude):
    """the power within f0 +- half, without f0 +- exclude, from an RMS trace (each point's bucket over its RBW)"""
    step = f[1] - f[0]
    m = (np.abs(f - f0) <= half) & (np.abs(f - f0) > exclude)
    p = np.sum(10 ** (dbm[m] / 10)) * step / rbw
    return round(10 * math.log10(p), 1) if p > 0 else None


def lines(f, dbm, over_db=10.0, k=15, top=12):
    """points that stand over_db above the running median of 2k+1 points around them, the largest first"""
    med = np.array([np.median(dbm[max(0, i - k):i + k + 1]) for i in range(len(dbm))])
    ex = dbm - med
    idx = [i for i in range(1, len(dbm) - 1) if ex[i] >= over_db and dbm[i] >= dbm[i - 1] and dbm[i] >= dbm[i + 1]]
    idx.sort(key=lambda i: -dbm[i])
    return [(round(f[i] / 1e6, 3), round(float(dbm[i]), 1), round(float(ex[i]), 1)) for i in idx[:top]]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cabled", action="store_true", help="the cabling above is in place (required)")
    ap.add_argument("--at", choices=("ant", "txant"), required=True, help="where the analyzer is (above)")
    ap.add_argument("--board", default="A", help="A or B (with COSTAS_PYNQ_HOST its PYNQ; the records say which)")
    ap.add_argument("--states", nargs="+", default=None)
    ap.add_argument("--spans", nargs="+", default=list(SPANS))
    ap.add_argument("--avg", type=int, default=8, help="sweeps power-averaged per trace")
    ap.add_argument("--null-vr", type=float, nargs=2, metavar=("VR_I", "VR_Q"), default=None,
                    help="volts for the state null_trim (the null found on the analyzer); VR is put back after")
    ap.add_argument("--att", type=float, default=10, help="input attenuation (dB) for every state but the carrier")
    a = ap.parse_args()
    if not a.cabled:
        print(__doc__)
        sys.exit("not run: check the cabling above, then add --cabled")
    states = a.states or [s for s in STATES if (a.at == "ant" or s != "rx_side") and (a.null_vr or s != "null_trim")]
    if "null_trim" in states and not a.null_vr:
        sys.exit("null_trim needs --null-vr VR_I VR_Q")
    b = B.Bench(a.board, "switch")
    cl = b.board_call
    sa = DSA875(usb=usbtmc_node(USB_VENDOR, USB_PRODUCT))
    now = json.loads(urllib.request.urlopen(SERVER + "/api/now", timeout=5).read())
    tx_mhz, rx_mhz, dsa0 = now.get("tx_mhz") or 5200, now.get("rx_mhz") or 5200, now.get("dsa_db")
    fc = tx_mhz * 1e6
    r4 = {}
    for which, f in ((0, tx_mhz), (1, rx_mhz)):
        on = [w for w in max2871_regs.regs(f) if w & 7 == 4][0]
        r4[which] = (on & ~(1 << 5), on)                             # RFA_EN clear, as max2871_regs makes it
    regs = {n: cl("rd", n) for n in ("CTRL", "TX_MODE", "TX_IDLE", "TX_POINTS", "TX_PERIOD", "TX_WIDTH", "TX_COUNT",
                                     "TX_MSG", "TX_GO")}
    dac0 = cl("dac_volts")
    vr0 = (dac0["VR_I"], dac0["VR_Q"])
    sa_prev = sa.status()
    stamp = time.strftime("%Y-%m-%d_%H%M%S")
    out_dir = OUT_DIR.replace("board_A", "board_" + a.board)
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.join(out_dir, "%s_spectrum_%s" % (stamp, a.at))
    print("TX %s MHz RX %s MHz, DSA %s; saved %s; the analyzer was %s" % (
        tx_mhz, rx_mhz, dsa0, {k: hex(v) for k, v in regs.items()}, sa_prev["frequency"]), flush=True)
    traces, summary = {}, {"at": a.at, "tx_mhz": tx_mhz, "rx_mhz": rx_mhz, "dsa0": dsa0, "avg": a.avg,
                            "regs": regs, "vr0": vr0, "null_vr": a.null_vr, "att": a.att,
                            "states": {}, "t0": time.time()}

    def set_state(name):
        tr_a, dis, code, tx_on, rx_on = STATES[name]
        vr = a.null_vr if name == "null_trim" else vr0
        cl("dac", VR_I=vr[0], VR_Q=vr[1])
        cl("ctrl", tx_dis=dis, loop_hold=1, tr_a=tr_a)
        cl("spi", 0, r4[0][tx_on])
        cl("spi", 1, r4[1][rx_on])

    try:
        cl("ctrl", tx_dis=1, loop_hold=1, tr_a=1)
        for name in states:
            tr_a, dis, code, tx_on, rx_on = STATES[name]
            sa.amplitude(attenuation=30, ref_level=20)              # the most, before the board changes state
            cl("tx_points", CARR, [code])
            cl("tx_msg", 0)
            cl("tx_mode", "hold")
            set_state(name)
            time.sleep(0.05)
            locked = cl("pll_locked")
            att, ref = (30, 20) if name == "carrier" else (a.att, -10 - (10 - a.att))
            sa.amplitude(attenuation=att, ref_level=ref)
            res = {"pll_locked": locked, "attenuation_dB": att}
            for span in a.spans:
                start, stop, half, rbw, det = SPANS[span]
                set_state(name)                                    # a driving request: keeps linkd paused
                if start is not None:
                    sa.frequency(start=start, stop=stop)
                else:
                    sa.frequency(center=fc, span=2 * half)
                sa.bandwidth(rbw=rbw, vbw=rbw if det == "RMS" else 3 * rbw)
                sa.detector(det)
                tr = []
                for _ in range(a.avg):
                    f, y = sa.trace(binary=True)
                    tr.append(y)
                y = db_mean(tr) if det == "RMS" else np.max(tr, axis=0)
                traces["%s|%s" % (name, span)] = y
                traces["f|%s|%s" % (name, span)] = f
                s = {"peak": (round(float(f[np.argmax(y)]) / 1e6, 3), round(float(np.max(y)), 1)),
                     "lines": lines(f, y)}
                if det == "RMS":
                    s["dbm_hz"] = {str(o): density_at(f, y, rbw, fc, o * 1e6, max(3 * (f[1] - f[0]), 0.1 * o * 1e6))
                                   for o in OFFSETS_MHZ if o * 1e6 < half * 0.97}
                if span == "band":
                    s["band_dbm_94"] = band_power(f, y, rbw, fc, 94e6, 1.5e6)
                    s["carrier_dbm"] = round(float(np.max(y[np.abs(f - fc) <= 1.5e6])), 1)
                res[span] = s
                print("%-14s %-5s peak %s; lines %s" % (name, span, s["peak"], s["lines"][:6]), flush=True)
                if det == "RMS":
                    print("%20s dBm/Hz at offsets (MHz) %s" % ("", {k: v for k, v in s["dbm_hz"].items()}), flush=True)
                if span == "band":
                    print("%20s band +-94 MHz (carrier +-1.5 MHz out) %s dBm; carrier bucket %s dBm" % (
                        "", s["band_dbm_94"], s["carrier_dbm"]), flush=True)
            summary["states"][name] = res
            np.savez_compressed(base + ".npz", **traces)
            json.dump(summary, open(base + ".json", "w"), indent=1)
    finally:
        sa.amplitude(attenuation=30, ref_level=20)                  # before the TX comes back at full power
        cl("dac", VR_I=vr0[0], VR_Q=vr0[1])
        cl("spi", 0, r4[0][1])
        cl("spi", 1, r4[1][1])
        cl("tx_stop")
        for n in ("TX_IDLE", "TX_POINTS", "TX_PERIOD", "TX_WIDTH", "TX_COUNT", "TX_MSG", "TX_MODE"):
            cl("wr", n, regs[n])
        if regs["TX_GO"] & 1:
            cl("tx_go")
        cl("wr", "CTRL", regs["CTRL"] & ~0x80)
        if dsa0 is not None:
            cl("dsa", dsa0)
        print("restored CTRL 0x%x TX_MODE 0x%x DSA %s, PLLs %s, VR %s" % (
            cl("rd", "CTRL"), cl("rd", "TX_MODE"), dsa0, cl("pll_locked"),
            {k: v for k, v in cl("dac_volts").items() if k.startswith("VR")}), flush=True)
        sa.frequency(center=fc, span=500e6)
        sa.bandwidth(rbw="auto", vbw="auto")
        sa.detector("POSitive")
        sa.run()
        print("records in %s.npz / .json; the analyzer left at fc +-250 MHz, 30 dB attenuation, sweeping" % base,
              flush=True)


if __name__ == "__main__":
    main()
