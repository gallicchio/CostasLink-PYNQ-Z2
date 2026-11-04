"""What mutes board A's transmitter for its own receiver, and how fast: the T/R switch, the modulator's DSOP
(TX_DIS) and a baseband null (the ladders at (0, 0)) taken apart (2026-11-04, BRINGUP_LOG 4.54).

switch_recovery.py timed the windows' quiet after a burst through the switch; that is DSOP's turn-off, not the
switch's, because the HMC536 passes SW TX to SW RX 25 dB down in either state (REVB 50).  This separates them.

Cabling (Jason, by hand; RX ANT sees about -15..-21 dBm, 16 dB or more under its +1 dBm absolute maximum):
    TX ANT -> short cable -> SW TX (J402);  SW RX (J403) -> short cable -> RX ANT;  ANT (J401) -> 50 ohm
    never TX ANT straight to RX ANT

    python3 bringup/switch_probe.py --cabled                                   # every part at DSA 31.75 and 20
    python3 bringup/switch_probe.py --cabled --parts null quiet --dsa 10 15

Parts (the loop held unless said; the windows as linkd set them; times from the capture, 1.25 ns a sample):
    dsop    TX_DIS low for 1 and 4 us with the switch held in each state: the windows' first high after TX_DIS's
            fall and last high after its rise, from the CONTEXT bit (the pad is about 24 samples later: the
            ladder pins' own readback lags their register by that)
    switch  the TX on, TR_A 0 -> 1 -> 0 every 4 us: each state's windows, and when they change after each edge
    null    DSOP on, the idle point the null, one event of the carrier point 1 and 4 us long (TX_MODE 1): the
            windows against the ladder pins' READBACK (pad time)
    depth   locked to the leak on the carrier point, held, then each state for ~0.1 s: the I/Q vector on the
            ADC against the carrier's, and against the arms' zero measured with both mutes (needs the lock:
            VC within 4 mV of linkd's vc_lock, else the state is skipped)
    quiet   nothing switching, per mute state: the windows' edges and high samples in 8 forced captures
    det     the log detector's band power (detectors()) in each state: carrier, null, DSOP off, both
Records go to bringup/data/board_A/switch/<time>_probe.jsonl (gitignored).  CTRL, the TX registers and the DSA are
put back afterwards; with the dishes cabled again, restart the server (night.py).
"""
import argparse
import json
import math
import os
import statistics
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("COSTAS_BENCH_CONFIG", os.path.join(HERE, "bench_config_laptop.json"))
sys.path.insert(0, HERE)
import bench as B                                                    # noqa: E402

WIN = ("CMP_IP", "CMP_IN", "CMP_QP", "CMP_QN")
NULL, CARR = 0b0101, 0b0111                  # ladder codes {Q1 Q0 I1 I0}: (0, 0) and (+a, 0)
SERVER = "http://192.168.2.99:8080"
OUT_DIR = os.path.join(HERE, "data", "board_A", "switch")
VC_LOCK = None
cl = t_clk = depth = log = None


def rec(kind, **kw):
    kw.update(kind=kind, t=time.time())
    log.write(json.dumps(kw) + "\n"); log.flush()
    return kw


def edges(bits, v, start=0):
    return [k for k in range(max(1, start), len(bits)) if bits[k] == v and bits[k - 1] != v]


def win_any(c):
    return [any(c[w][s] for w in WIN) for s in range(len(c["CMP_IP"]))]


def first_high(a, s0, s1=None):
    for s in range(s0, s1 if s1 is not None else len(a)):
        if a[s]:
            return s
    return None


def last_high(a, s0, s1=None):
    r = None
    for s in range(s0, s1 if s1 is not None else len(a)):
        if a[s]:
            r = s
    return r


def seq_capture(steps, post=None):
    cl("seq_program", steps, loop=False)
    cl("cap_arm", "seq_step", post if post is not None else depth * 7 // 8)
    cl("seq_run")
    return cl("cap_read", 1.0)


def dsop_try(tr_a, burst):
    """TX_DIS low for `burst` clocks with the switch held at tr_a; on/off times of the windows"""
    c = seq_capture([[burst, {"tr_a": tr_a, "loop_hold": 1, "tx_dis": 0, "tx_gate": 1}],
                     [depth, {"tr_a": tr_a, "loop_hold": 1, "tx_dis": 1, "tx_gate": 0}]])
    ser, ns = len(c["CMP_IP"]) // len(c["words"]), c["sample_ns"]
    tw = c["trigger_word"]
    fall = [k for k in edges(c["TX_DIS"], 0, tw - 2)]
    rise = [k for k in edges(c["TX_DIS"], 1, tw)]
    if not fall or not rise:
        return {"error": "no TX_DIS edges", "tw": tw}
    a = win_any(c)
    s_fall, s_rise = fall[0] * ser, rise[0] * ser
    on = first_high(a, s_fall)
    off = last_high(a, s_rise)
    pre = c["valid_from"] * ser
    return {"tr_a": tr_a, "burst_ns": (s_rise - s_fall) * ns,
            "on_ns": None if on is None else (on - s_fall) * ns,
            "quiet_after_off_ns": None if off is None else (off + 1 - s_rise) * ns,
            "high_in_burst": sum(a[s_fall:s_rise]) / max(1, s_rise - s_fall),
            "high_before": sum(a[pre:s_fall]) / max(1, s_fall - pre),
            "high_after_1us": sum(a[s_rise + int(1000 / ns):]) / max(1, len(a) - s_rise - int(1000 / ns)),
            "per_win_on_ns": {w: ((first_high(c[w], s_fall) or s_fall) - s_fall) * ns for w in WIN}}


def switch_try(half):
    """TX on, the switch 0 -> 1 -> 0 every `half` clocks; each state's windows and the transition"""
    c = seq_capture([[half, {"tr_a": 0, "loop_hold": 1, "tx_dis": 0, "tx_gate": 1}],
                     [half, {"tr_a": 1, "loop_hold": 1, "tx_dis": 0, "tx_gate": 1}],
                     [half, {"tr_a": 0, "loop_hold": 1, "tx_dis": 0, "tx_gate": 1}],
                     [depth, {"tr_a": 1, "loop_hold": 1, "tx_dis": 1, "tx_gate": 0}]])
    ser, ns = len(c["CMP_IP"]) // len(c["words"]), c["sample_ns"]
    tw = c["trigger_word"]
    up = edges(c["TR_A"], 1, tw)
    dn = edges(c["TR_A"], 0, up[0] + 1) if up else []
    out = {"half_ns": half * t_clk * 1e9, "tr_a_up_w": up[:2], "tr_a_dn_w": dn[:2]}
    if not up or not dn:
        out["error"] = "no TR_A edges"
        return out
    u, d = up[0] * ser, dn[0] * ser
    t0 = tw * ser
    pattern = lambda s0, s1: {w: round(sum(c[w][s0:s1]) / max(1, s1 - s0), 3) for w in WIN}
    m = int(200 / ns)
    out["tx_state"] = pattern(t0 + m, u)            # TR_A 0: SW TX to ANT
    out["rx_state"] = pattern(u + m, d)             # TR_A 1: SW RX to ANT
    # the transition: first sample after the edge where the window set matches the new state's majority
    def settle(s_edge, s_end, newpat):
        key = tuple(w for w in WIN if newpat[w] > 0.5)
        for s in range(s_edge, s_end):
            if all(tuple(w for w in WIN if c[w][x]) == key for x in range(s, min(s_end, s + 16))):
                return (s - s_edge) * ns
        return None
    out["settle_up_ns"] = settle(u, d, out["rx_state"])
    out["settle_dn_ns"] = settle(d, d + (u - t0), out["tx_state"])
    def change(s_edge, s_end, oldpat):
        key = tuple(w for w in WIN if oldpat[w] > 0.5)
        for s in range(s_edge, s_end):
            if tuple(w for w in WIN if c[w][s]) != key:
                return (s - s_edge) * ns
        return None
    out["change_up_ns"] = change(u, d, out["tx_state"])
    out["change_dn_ns"] = change(d, d + (u - t0), out["rx_state"])
    out["raw_around_up"] = ["".join(str(c[w][s]) for w in WIN) for s in range(u - 8, u + 64, 2)]
    return out


def baseband_try(width, tr_a):
    """TX_DIS low (DSOP on), the ladder idle at the null, one event of the carrier point `width` clocks"""
    cl("ctrl", tx_dis=0, loop_hold=1, tr_a=tr_a)
    cl("tx_points", NULL, [CARR])
    cl("tx_timing", period=width + 50, width=width, count=1)
    cl("tx_msg", 0)
    cl("tx_mode", "events", n=1, source="fixed")
    time.sleep(0.05)
    cl("cap_arm", "tx_event", depth * 3 // 4)
    cl("tx_one")
    c = cl("cap_read", 1.0)
    ser, ns = len(c["CMP_IP"]) // len(c["words"]), c["sample_ns"]
    pins = c.get("TX_PINS")
    tw = c["trigger_word"]
    a = win_any(c)
    out = {"width_ns": width * t_clk * 1e9, "tr_a": tr_a}
    reg = [(c["Q1"][k] << 3) | (c["Q0"][k] << 2) | (c["I1"][k] << 1) | c["I0"][k] for k in range(len(c["words"]))]
    r_on = [k for k in range(max(1, tw - 4), len(reg)) if reg[k] == CARR and reg[k - 1] != CARR]
    r_off = [k for k in range(max(1, tw - 4), len(reg)) if reg[k] != CARR and reg[k - 1] == CARR]
    if pins:
        p_on = [s for s in range(max(1, (tw - 4) * ser), len(pins)) if pins[s] == CARR and pins[s - 1] != CARR]
        p_off = [s for s in range(max(1, (tw - 4) * ser), len(pins)) if pins[s] != CARR and pins[s - 1] == CARR]
    else:
        p_on = p_off = []
    out.update(reg_on_w=r_on[:1], reg_off_w=r_off[:1], pin_on_s=p_on[:1], pin_off_s=p_off[:1])
    if r_on and p_on:
        out["pin_lag_samples"] = p_on[0] - r_on[0] * ser
    if p_on and p_off:
        s_on, s_off = p_on[0], p_off[0]
        on = first_high(a, s_on)
        off = last_high(a, s_off)
        pre = max(c["valid_from"] * ser, s_on - int(5000 / ns))
        out.update(on_ns=None if on is None else (on - s_on) * ns,
                   quiet_after_off_ns=None if off is None else (off + 1 - s_off) * ns,
                   high_in_event=sum(a[s_on:s_off]) / max(1, s_off - s_on),
                   high_in_null_before=sum(a[pre:s_on]) / max(1, s_on - pre),
                   per_win_on_ns={w: ((first_high(c[w], s_on) or s_on) - s_on) * ns for w in WIN})
    return out


def vec(i0, q0, n=3):
    """n (I, Q) pairs read back to back, after the ADC input's filter settles; the median of each pair's length"""
    time.sleep(0.02)
    ps = []
    for _ in range(n):
        di = cl("adc", "I") - i0
        dq = cl("adc", "Q") - q0
        ps.append((round(di, 5), round(dq, 5), round(math.hypot(di, dq), 5)))
    return {"pairs": ps, "amp": statistics.median(p[2] for p in ps)}


STATES = {"null": (0, 0, 0), "dsop_off": (1, 0, 1), "dsop_off_null": (0, 0, 1), "carrier_minus": (-1, 0, 0)}


def depth_try(i0, q0, tr_a):
    """per state: lock to the leak on the carrier point, hold, read; the state; read; the carrier; read"""
    r = {"tr_a": tr_a}
    for name, (i, q, dis) in STATES.items():
        cl("ctrl", tx_dis=0, loop_hold=0, tr_a=tr_a)
        cl("hold_point", 1, 0)
        time.sleep(0.4)
        cl("ctrl", loop_hold=1)
        vc = cl("adc", "VC")
        if VC_LOCK is not None and abs(vc - VC_LOCK) > 0.004:
            r[name] = {"error": "not locked: VC %.4f against %.4f" % (vc, VC_LOCK), "db": float("nan"),
                       "ref1": {"amp": 0}, "ref2": {"amp": 0}, "state": {"pairs": []}, "seconds": 0, "vc": vc}
            continue
        t0 = time.time()
        ref1 = vec(i0, q0, 1)
        cl("hold_point", i, q)
        if dis:
            cl("ctrl", tx_dis=1)
        st = vec(i0, q0, 3)
        cl("ctrl", tx_dis=0)
        cl("hold_point", 1, 0)
        ref2 = vec(i0, q0, 1)
        ref = 0.5 * (ref1["amp"] + ref2["amp"])
        r[name] = {"ref1": ref1, "state": st, "ref2": ref2, "seconds": round(time.time() - t0, 3),
                   "db": round(20 * math.log10(max(1e-6, st["amp"]) / max(1e-6, ref)), 1)}
    # against the arms' zero measured now (both mutes), not the learned i0/q0
    z = r["dsop_off_null"]["state"]["pairs"]
    if not z:
        return r
    zi = statistics.median(p[0] for p in z); zq = statistics.median(p[1] for p in z)
    for name in STATES:
        x = r[name]
        if "error" in x:
            x["db_vs_zero"] = float("nan"); x["resid_vs_zero_mv"] = float("nan")
            continue
        a = statistics.median(math.hypot(p[0] - zi, p[1] - zq) for p in x["state"]["pairs"])
        ref = 0.5 * (math.hypot(x["ref1"]["pairs"][0][0] - zi, x["ref1"]["pairs"][0][1] - zq) +
                     math.hypot(x["ref2"]["pairs"][0][0] - zi, x["ref2"]["pairs"][0][1] - zq))
        x["db_vs_zero"] = round(20 * math.log10(max(1e-6, a) / max(1e-6, ref)), 1)
        x["resid_vs_zero_mv"] = round(a * 1e3, 3)
    cl("ctrl", loop_hold=0)
    return r




def quiet_part(dsa, tr_a, n=8):
    """nothing switching: each mute state's window edges and high samples over n forced captures"""
    for name, (i, dis) in {"null": (0, 0), "dsop_off": (1, 1), "both": (0, 1)}.items():
        cl("ctrl", tx_dis=dis, loop_hold=1, tr_a=tr_a)
        cl("hold_point", i, 0)
        time.sleep(0.05)
        hits = {w: 0 for w in WIN}
        n_edges = {w: 0 for w in WIN}
        samples = 0
        for _ in range(n):
            cl("cap_arm", "none", 0)
            cl("cap_force")
            c = cl("cap_read", 1.0)
            s0 = c["valid_from"] * (len(c["CMP_IP"]) // len(c["words"]))
            for w in WIN:
                x = c[w][s0:]
                hits[w] += sum(x)
                n_edges[w] += sum(1 for k in range(1, len(x)) if x[k] and not x[k - 1])
            samples += len(c["CMP_IP"]) - s0
        r = rec("quiet", dsa=dsa, tr_a=tr_a, state=name, us=samples * 1.25e-3, edges=n_edges, hits=hits)
        print("QUIET dsa %5.2f tr_a %d %-8s %.0f us: edges %s, high samples %s" % (dsa, tr_a, name, r["us"], n_edges,
                                                                                    hits), flush=True)


def det_part(dsa, tr_a):
    """the log detector's band power in each state"""
    for name, (i, dis) in {"carrier": (1, 0), "null": (0, 0), "dsop_off": (1, 1), "both": (0, 1)}.items():
        cl("ctrl", tx_dis=dis, loop_hold=1, tr_a=tr_a)
        cl("hold_point", i, 0)
        time.sleep(0.1)
        lg = [d["log_dbm"] for d in (cl("detectors") for _ in range(4)) if d.get("log_dbm") is not None]
        rec("det", dsa=dsa, tr_a=tr_a, state=name, log_dbm=lg)
        print("DET dsa %5.2f tr_a %d %-8s log_dbm %s (median %s)" % (
            dsa, tr_a, name, [round(x, 1) for x in lg], round(statistics.median(lg), 1) if lg else None), flush=True)


def main():
    global cl, t_clk, depth, log, VC_LOCK
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cabled", action="store_true", help="the cabling above is in place (required)")
    ap.add_argument("--parts", nargs="+", default=["dsop", "switch", "null", "depth", "quiet", "det"])
    ap.add_argument("--dsa", type=float, nargs="+", default=[31.75, 20.0])
    a = ap.parse_args()
    if not a.cabled:
        print(__doc__)
        sys.exit("not run: check the cabling above, then add --cabled")
    b = B.Bench("A", "switch")
    cl = b.board_call
    info = cl("info")
    t_clk = 1e-6 / float(info["clock_MHz"])
    depth = info["capture"]["depth"]
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, time.strftime("%Y-%m-%d_%H%M%S") + "_probe.jsonl")
    log = open(path, "a")
    regs = {n: cl("rd", n) for n in ("CTRL", "TX_MODE", "TX_IDLE", "TX_POINTS", "TX_PERIOD", "TX_WIDTH", "TX_COUNT",
                                     "TX_MSG", "TX_GO")}
    now = json.loads(urllib.request.urlopen(SERVER + "/api/now", timeout=5).read())
    dsa0, i0, q0 = now.get("dsa_db"), now["linkd"]["i0"], now["linkd"]["q0"]
    VC_LOCK = now.get("vc_lock")
    print("saved", {k: hex(v) for k, v in regs.items()}, "DSA", dsa0, "i0 q0", i0, q0, "vc_lock", VC_LOCK, flush=True)
    rec("start", regs=regs, dsa0=dsa0, i0=i0, q0=q0, vc_lock=VC_LOCK, depth=depth, parts=a.parts)
    parts = a.parts
    try:
        for dsa in a.dsa:
            cl("dsa", dsa)
            if parts != ["depth"]:
                cl("ctrl", tx_dis=1, loop_hold=1, tr_a=1)
            for tr_a in ((1, 0) if "dsop" in parts else ()):
                for burst_us in (1.0, 4.0):
                    rs = [dsop_try(tr_a, int(burst_us * 1e-6 / t_clk)) for _ in range(3)]
                    for r in rs:
                        rec("dsop", dsa=dsa, burst_us=burst_us, **r)
                    print("DSOP dsa %.2f tr_a %d burst %.0f us: on %s ns, quiet %s ns after off, high %s in burst, "
                          "%s before, %s after 1us" % (dsa, tr_a, burst_us, [r.get("on_ns") for r in rs],
                                                       [r.get("quiet_after_off_ns") for r in rs],
                                                       [round(r.get("high_in_burst", -1), 2) for r in rs],
                                                       [round(r.get("high_before", -1), 3) for r in rs],
                                                       [round(r.get("high_after_1us", -1), 3) for r in rs]), flush=True)
            for k in range(3 if "switch" in parts else 0):
                r = switch_try(int(4e-6 / t_clk))
                rec("switch", dsa=dsa, **r)
                print("SWITCH dsa %.2f: TX state %s RX state %s; change up %s dn %s ns, settle up %s dn %s ns" % (
                    dsa, r.get("tx_state"), r.get("rx_state"), r.get("change_up_ns"), r.get("change_dn_ns"),
                    r.get("settle_up_ns"), r.get("settle_dn_ns")), flush=True)
                if k == 0:
                    print("   around TR_A up (IP IN QP QN every 2.5 ns from -10 ns):", " ".join(r.get("raw_around_up", [])), flush=True)
            cl("seq_stop")
            for tr_a in ((1, 0) if "null" in parts else ()):
                for width_us in (1.0, 4.0):
                    rs = [baseband_try(int(width_us * 1e-6 / t_clk), tr_a) for _ in range(3)]
                    for r in rs:
                        rec("baseband", dsa=dsa, **r)
                    print("NULL dsa %.2f tr_a %d width %.0f us: on %s ns, quiet %s ns after the pins, high %s in event, "
                          "%s in the null before; pin lag %s samples" % (
                              dsa, tr_a, width_us, [r.get("on_ns") for r in rs], [r.get("quiet_after_off_ns") for r in rs],
                              [round(r.get("high_in_event", -1), 2) for r in rs],
                              [round(r.get("high_in_null_before", -1), 3) for r in rs],
                              [r.get("pin_lag_samples") for r in rs]), flush=True)
            for tr_a in ((1, 0) if "depth" in parts else ()):
                r = depth_try(i0, q0, tr_a)
                rec("depth", dsa=dsa, **r)
                for name in STATES:
                    x = r[name]
                    print("DEPTH dsa %.2f tr_a %d %-14s %6.1f dB (vs the zero now %6.1f dB, %.3f mV): ref %.4f / %.4f V, "
                          "state %s (%.2f s)" % (dsa, tr_a, name, x["db"], x["db_vs_zero"], x["resid_vs_zero_mv"],
                                                 x["ref1"]["amp"], x["ref2"]["amp"], x["state"]["pairs"], x["seconds"]),
                          flush=True)
            for tr_a in ((1, 0) if "quiet" in parts else ()):
                quiet_part(dsa, tr_a)
            for tr_a in ((1, 0) if "det" in parts else ()):
                det_part(dsa, tr_a)
    finally:
        try:
            cl("seq_stop")
        except Exception as x:  # noqa: BLE001
            print("seq_stop:", x)
        cl("tx_stop")
        for n in ("TX_IDLE", "TX_POINTS", "TX_PERIOD", "TX_WIDTH", "TX_COUNT", "TX_MSG", "TX_MODE"):
            cl("wr", n, regs[n])
        if regs["TX_GO"] & 1:
            cl("tx_go")
        cl("wr", "CTRL", regs["CTRL"] & ~0x80)
        if dsa0 is not None:
            cl("dsa", dsa0)
        print("restored CTRL 0x%x TX_MODE 0x%x DSA %s" % (cl("rd", "CTRL"), cl("rd", "TX_MODE"), dsa0), flush=True)
        print("records in %s" % path, flush=True)


if __name__ == "__main__":
    main()
