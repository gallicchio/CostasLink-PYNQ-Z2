"""How fast board A's receiver comes back after its own transmission through the antenna switch (2026-11-04).

The verifier's problem in one-antenna time division (PLAN.md section 14, BRINGUP.md stage 4.4): while it sends the
challenge its own TX leaks into its receiver through the HMC536's isolation (25 dB measured, VNA S3, BRINGUP_LOG
4.39), some 24 dB above the reply it must hear about 280 ns later over the dishes.  How long the receive chain takes to
recover is the one number the two-board test needs that nothing has measured.

Cabling (Jason, by hand; RX ANT sees about -15 dBm through the switch, 16 dB under its +1 dBm absolute maximum):
    TX ANT -> short cable -> SW TX (J402)
    SW RX (J403) -> short cable -> RX ANT
    ANT (J401) -> 50 ohm
    never TX ANT straight to RX ANT (+10 dBm: over RX ANT's absolute maximum)

    python3 bringup/switch_recovery.py --cabled            # the sweep below, about a minute; drives the board
    python3 bringup/switch_recovery.py --cabled --burst-us 2 --dsa 20 --n 10

Each try: the sequencer runs once: the TX burst (TR_A low, TX_DIS low, the loop held), 3 clocks with TX_DIS high, then
receive (TR_A high) for the rest; the capture is triggered by the burst's first step.  From the capture's context bits
(TX_DIS, TR_A per word) and the window comparators' samples: when the windows (IP, IN, QP, QN) and the slow ones go
quiet after the switch is back in receive.  The loop is held throughout (no carrier in receive: ANT is on a load).
Afterwards CTRL, the DSA and the sequencer are put back; with the dishes cabled again, restart the server (night.py).
"""
import argparse
import json
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("COSTAS_BENCH_CONFIG", os.path.join(HERE, "bench_config_laptop.json"))
sys.path.insert(0, HERE)
import bench as B                                                    # noqa: E402

WINDOWS = ("CMP_IP", "CMP_IN", "CMP_QP", "CMP_QN")
SLOW = ("CMP_QP_S", "CMP_QN_S")
OUT_DIR = os.path.join(HERE, "data", "board_A", "switch")


def edges(bits, value):
    """indices where a 0/1 list turns to `value`"""
    return [k for k in range(1, len(bits)) if bits[k] == value and bits[k - 1] != value]


def analyse(c):
    ser = len(c["CMP_IP"]) // len(c["words"])
    ns = c["sample_ns"]
    trig_w = c["trigger_word"]
    off_w = [k for k in edges(c["TX_DIS"], 1) if k >= trig_w]
    rx_w = [k for k in edges(c["TR_A"], 1) if k >= trig_w]
    if not off_w or not rx_w:
        return {"error": "no TX_DIS / TR_A edge after the trigger in the capture"}
    t_off, t_rx = off_w[0] * ser, rx_w[0] * ser                     # in samples
    burst = range(trig_w * ser, t_off)
    win_any = [any(c[w][s] for w in WINDOWS) for s in range(len(c["CMP_IP"]))]
    pre = range(c["valid_from"] * ser, trig_w * ser)
    after = [s for s in range(t_rx, len(win_any)) if win_any[s]]
    slow_any = [any(c[w][k] for w in SLOW) for k in range(len(c["words"]))]
    slow_after = [k for k in range(rx_w[0], len(slow_any)) if slow_any[k]]
    return {
        "sample_ns": ns,
        "burst_ns": (t_off - trig_w * ser) * ns,
        "rx_after_off_ns": (t_rx - t_off) * ns,
        "windows_high_in_burst": sum(win_any[s] for s in burst) / max(1, len(burst)),
        "windows_high_before": sum(win_any[s] for s in pre) / max(1, len(pre)),
        "windows_quiet_after_ns": ((after[-1] + 1 - t_rx) * ns) if after else 0.0,
        "windows_high_after_frac": len(after) / max(1, len(win_any) - t_rx),
        "slow_quiet_after_ns": ((slow_after[-1] + 1 - rx_w[0]) * ser * ns) if slow_after else 0.0,
        "seen_after_ns": (len(win_any) - t_rx) * ns,
        "per_window_last_ns": {w: ((max([s for s in range(t_rx, len(win_any)) if c[w][s]] or [t_rx - 1]) + 1 - t_rx) * ns)
                               for w in WINDOWS},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cabled", action="store_true", help="the cabling above is in place (required)")
    ap.add_argument("--burst-us", type=float, nargs="+", default=[0.2, 1.0, 4.0])
    ap.add_argument("--dsa", type=float, nargs="+", default=[31.75, 20.0, 10.0])
    ap.add_argument("--n", type=int, default=3, help="tries per setting")
    a = ap.parse_args()
    if not a.cabled:
        print(__doc__)
        sys.exit("not run: check the cabling above, then add --cabled")
    b = B.Bench("A", "switch")
    cl = b.board_call
    info = cl("info")
    clk_mhz = float(info["clock_MHz"])
    t_clk = 1e-6 / clk_mhz
    cap = info["capture"]
    ctrl0 = cl("rd", "CTRL")
    dsa0 = None
    try:
        import urllib.request
        dsa0 = json.load(urllib.request.urlopen("http://192.168.2.99:8080/api/now", timeout=5)).get("dsa_db")
    except Exception:                                                # noqa: BLE001
        pass
    depth_ns = cap["depth"] * t_clk * 1e9
    print("capture %d words x %d samples (%.0f ns), clock %g MHz; CTRL 0x%x, DSA %s" % (
        cap["depth"], cap["ser"], depth_ns, clk_mhz, ctrl0, dsa0), flush=True)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, time.strftime("%Y-%m-%d_%H%M%S") + "_recovery.jsonl")
    log = open(path, "a")
    rows = []
    try:
        cl("ctrl", tx_dis=1, loop_hold=1, tr_a=1)                     # receive, held, muted: the state between tries
        for dsa in a.dsa:
            cl("dsa", dsa)
            for burst_us in a.burst_us:
                burst = max(1, int(round(burst_us * 1e-6 / t_clk)))
                post_ns = depth_ns * 7 / 8
                rx = max(16, int(round((post_ns * 1e-9 - burst * t_clk) / t_clk)) + 64)
                res = []
                for k in range(a.n):
                    cl("seq_program", [[burst, {"tr_a": 0, "loop_hold": 1, "tx_dis": 0, "tx_gate": 1}],
                                       [3, {"tr_a": 0, "loop_hold": 1, "tx_dis": 1, "tx_gate": 0}],
                                       [rx, {"tr_a": 1, "loop_hold": 1, "tx_dis": 1, "tx_gate": 0}]], loop=False)
                    cl("cap_arm", "seq_step", cap["depth"] * 7 // 8)
                    cl("seq_run")
                    c = cl("cap_read", 1.0)
                    r = analyse(c)
                    r.update(dsa=dsa, burst_us=burst_us, k=k, t=time.time())
                    log.write(json.dumps(r) + "\n")
                    log.flush()
                    res.append(r)
                    time.sleep(0.05)
                ok = [r for r in res if "error" not in r]
                if not ok:
                    print("DSA %5.2f burst %4.1f us: %s" % (dsa, burst_us, res[0].get("error")), flush=True)
                    continue
                q = [r["windows_quiet_after_ns"] for r in ok]
                s = [r["slow_quiet_after_ns"] for r in ok]
                print("DSA %5.2f burst %4.1f us: windows high %.0f %% in the burst, %.0f %% before; quiet %s ns after "
                      "TR_A (median %.0f), slow quiet %s ns; TR_A %.0f ns after TX_DIS; %.0f ns watched" % (
                          dsa, burst_us, 100 * statistics.mean(r["windows_high_in_burst"] for r in ok),
                          100 * statistics.mean(r["windows_high_before"] for r in ok),
                          "/".join("%.0f" % x for x in q), statistics.median(q), "/".join("%.0f" % x for x in s),
                          ok[0]["rx_after_off_ns"], ok[0]["seen_after_ns"]), flush=True)
                rows += ok
    finally:
        cl("seq_stop")
        cl("wr", "CTRL", ctrl0 & ~0x80)
        if dsa0 is not None:
            cl("dsa", dsa0)
        print("restored CTRL 0x%x, DSA %s; records in %s" % (cl("rd", "CTRL"), dsa0, path), flush=True)
    return rows


if __name__ == "__main__":
    main()
