"""The overnight soak over the cables (Jason, 2026-11-06: 'you'll have this wired-only confirmation for at least 12 hours'):
a cycle every --every minutes until --until (HH:MM), each cycle:
  0. both boards quiet: each board's temperature and +5V_RF (the detector ADC), its arms' no-carrier centres (I, Q) and
     the sign comparator's duty (the Q_OFF_F trim's hold over the night: REVB 59);
  1. per link (A -> B at --mhz_ab, B -> A at --mhz_ba): the lock (setup), its DSA / leg / VC / i0 / q0; A3 and B1 by the
     decoder (20 000 events a message; B1 with its pilot set up); the PRBS bpsk at 20 clocks a bit for 10 s and at 50 for
     5 s; the flip (-1, 0) and the (-1, 1) corner on the receiver's scope (5 shots: the sender's quadrature term and the
     arms' settling over the night); then quiet.
Records data/twoboard/soak_<stamp>.jsonl and a summary soak_<stamp>.json (rewritten each cycle); the morning's page:
soak_fig.py.

    python3 soak_night.py [--every 10] [--until 09:00] [--mhz_ab 4800] [--mhz_ba 5000]
"""
import json
import os
import sys
import time

import numpy as np

BR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BR)
sys.path.insert(0, os.path.join(os.path.dirname(BR), "gateware", "driver"))
import twoboard as T                                      # noqa: E402
import scope_e                                            # noqa: E402
import twoscope as TS                                     # noqa: E402

LAT_NS = {"AB": 5.8, "BA": 10.0}


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def until_s(hhmm):
    h, m = (int(x) for x in hhmm.split(":"))
    now = time.localtime()
    t = time.mktime((now.tm_year, now.tm_mon, now.tm_mday, h, m, 0, 0, 0, -1))
    if t <= time.time():
        t += 86400
    return t


def quiet_readings(nodes, log):
    for n in nodes.values():
        n.quiet()
    time.sleep(0.5)
    out = {}
    for n, node in nodes.items():
        cl = node.cl
        q0 = sum(cl.adc("Q") for _ in range(8)) / 8.0
        i0 = sum(cl.adc("I") for _ in range(4)) / 4.0
        ones = sum(cl.cmp_state()["CMP_I"] for _ in range(100))
        try:
            det = cl.detectors()
        except Exception as e:                            # noqa: BLE001
            det = {"error": repr(e)[:100]}
        dv = cl.dac_volts()
        out[n] = {"centre_q_v": q0, "centre_i_v": i0, "cmp_i_duty": ones / 100.0, "temp_c": det.get("temp_c"), "v5_rf": det.get("v5_rf"),
                  "log_dbm": det.get("log_dbm"), "q_off_f": dv.get("Q_OFF_F"), "vr": (dv.get("VR_I"), dv.get("VR_Q")), "adc_vc": cl.adc("VC")}
        T.say("   %s quiet: Q centre %.4f I centre %.4f V, CMP_I duty %.2f, %.1f C, +5V_RF %.3f V, Q_OFF_F %.3f" % (
            n, q0, i0, out[n]["cmp_i_duty"], out[n]["temp_c"] or float("nan"), out[n]["v5_rf"] or float("nan"), out[n]["q_off_f"] or 0))
    log(label="soak quiet", tag="quiet", **out)
    return out


def scope_flip(L, rs, keeper, lat, cycle):
    leg = L.leg()
    TS.set_arms(rs, leg)
    L.hold((1, 0))
    time.sleep(0.1)
    TS.centre(rs)
    bb = TS.scope_dc(rs, (2, 3))
    base = {2: bb[2]["dc"], 3: bb[3]["dc"]}
    out = {"leg_mv": 1e3 * leg, "side": L.s}
    for pt in ((-1, 0), (-1, 1)):
        L.events_on(pt, 20, 1000, idle=(1, 0))
        time.sleep(0.05)
        got = TS.shots(rs, 1, TS.MARK_V, "rising", 5, (1, 2, 3, 4))
        L.events_off()
        L.hold((1, 0))
        rs.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
        nums = [TS.shot_numbers(g, base, lat) for g in got]
        if cycle % 6 == 0:                                # the traces kept every sixth cycle (an hour)
            keeper.keep(got, stage="soak", link=L.name, mhz=L.mhz, point=list(pt), base=base, leg=leg, side=L.s, cycle=cycle)
        r = {"n": len(got)}
        for k in ("i_plateau", "q_plateau", "q_spike_min", "i_rise", "cmp_edge_t", "mark_t", "i_pre", "q_pre"):
            r[k] = TS.med(nums, k)
        r["latency_ns"] = (r["cmp_edge_t"] - r["mark_t"]) if r["cmp_edge_t"] is not None and r["mark_t"] is not None else None
        out["%d,%d" % pt] = r
    return out


def main():
    every = arg("--every", 10.0)
    t_end = until_s(arg("--until", "09:00"))
    mhz = {"AB": arg("--mhz_ab", 4800.0), "BA": arg("--mhz_ba", 5000.0)}
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("soak")
    nodes = {n: T.Node(n) for n in ("A", "B")}
    scopes = {}
    keeper = TS.Keeper()
    out = {"stamp": stamp, "mhz": mhz, "every_min": every, "cycles": []}
    path = os.path.join(T.DATA, "soak_%s.json" % stamp)
    t0 = time.time()
    try:
        for n in ("A", "B"):
            scopes[n] = scope_e.open_scope(n)
            TS.scope_setup(scopes[n])
        cycle = 0
        while time.time() < t_end:
            t_cycle = time.time()
            cyc = {"cycle": cycle, "t": t_cycle, "when": time.strftime("%H:%M:%S"), "links": {}}
            T.say("==== cycle %d at %s, %.1f h in" % (cycle, cyc["when"], (t_cycle - t0) / 3600))
            try:
                cyc["quiet"] = quiet_readings(nodes, log)
            except Exception as e:                        # noqa: BLE001
                T.say("quiet readings: %r" % (e,))
                cyc["quiet"] = {"error": repr(e)[:200]}
            for lk in ("AB", "BA"):
                L = T.Link(nodes[lk[0]], nodes[lk[1]], mhz[lk])
                rs = scopes[L.rx.name]
                rec = {"mhz": mhz[lk]}
                cyc["links"][lk] = rec
                try:
                    t1 = time.time()
                    if not L.up(tries=2):
                        rec["error"] = "no link"
                        T.say("   %s: no link" % lk)
                        log(label="soak setup", tag="setup", cycle=cycle, state=L.state(), error="no link", **L.info)
                        continue
                    rec["lock"] = dict(L.info, side=L.s)
                    log(label="soak setup", tag="setup", cycle=cycle, state=L.state(), **L.info)
                    L.tx.cl.triggers(width=10, a="tx_event")
                    L.rx.cl.triggers(width=10, a="tx_event")
                    for sc in ("A3", "B1"):
                        try:
                            d = T.events_point(L, **dict(T.EVENTS_BASE, scheme=sc))
                        except T.LinkDown:
                            raise
                        except Exception as e:            # noqa: BLE001
                            d = {"error": repr(e)[:200]}
                            L.ensure()
                        rec[sc] = {k: d.get(k) for k in ("per_msg", "right_frac_min", "right_frac_mean", "idle_false_per_s", "leg", "gaps_mv", "thresholds", "error")}
                        rec[sc]["dead"] = (d.get("rx_info") or {}).get("dead_windows")
                        rec[sc]["pilot"] = {k: (d.get("pilot") or {}).get(k) for k in ("rho", "a", "vr")} if d.get("pilot") else None
                        T.say("   %s %s: %s" % (lk, sc, d.get("error") or "right min %.4f, idle false %.0f/s, gaps %s%s" % (
                            d["right_frac_min"], d.get("idle_false_per_s") or 0, d.get("gaps_mv"),
                            ", pilot %.0f mV" % (1e3 * d["pilot"]["rho"] * d["pilot"]["a"]) if d.get("pilot") and d["pilot"].get("rho") else "")))
                        log(label="soak events %s" % sc, tag="events", cycle=cycle, params=dict(T.EVENTS_BASE, scheme=sc), state=L.state(),
                            **{k: v for k, v in d.items() if k not in ("levels",)})
                    for period, secs in ((20, 10.0), (50, 5.0)):
                        try:
                            p = T.prbs_point(L, **dict(T.PRBS_BASE, period=period, seconds=secs))
                        except T.LinkDown:
                            raise
                        except Exception as e:            # noqa: BLE001
                            p = {"error": repr(e)[:200]}
                            L.ensure()
                        rec["prbs%d" % period] = {k: p.get(k) for k in ("ber", "bits", "mismatches", "error", "invert")}
                        T.say("   %s prbs P%d %.0f s: BER %s over %s bits (%s mismatches)%s" % (lk, period, secs, p.get("ber"), p.get("bits"), p.get("mismatches"),
                                                                                           " error %s" % p["error"] if p.get("error") else ""))
                        log(label="soak prbs %d" % period, tag="prbs", cycle=cycle, params=dict(T.PRBS_BASE, period=period, seconds=secs), state=L.state(), **p)
                    try:
                        rec["scope"] = scope_flip(L, rs, keeper, LAT_NS.get(lk, 8.0), cycle)
                        f = rec["scope"]["-1,0"]
                        T.say("   %s scope: leg %.0f mV side %+d, the flip's Q %+.0f mV (%+.3f of the leg), I rise %s ns, latency %s ns" % (
                            lk, rec["scope"]["leg_mv"], rec["scope"]["side"], f["q_plateau"] or 0, (f["q_plateau"] or 0) / rec["scope"]["leg_mv"],
                            "%.1f" % f["i_rise"] if f.get("i_rise") else "-", "%.1f" % f["latency_ns"] if f.get("latency_ns") is not None else "-"))
                        log(label="soak scope", tag="scope", cycle=cycle, state=L.state(), **rec["scope"])
                    except Exception as e:                # noqa: BLE001
                        T.say("   %s scope: %r" % (lk, e))
                        rec["scope"] = {"error": repr(e)[:200]}
                    rec["seconds"] = time.time() - t1
                except T.LinkDown as e:
                    T.say("   %s: %s" % (lk, e))
                    rec["error"] = str(e)
                except Exception as e:                    # noqa: BLE001
                    import traceback
                    T.say("   %s: %r\n%s" % (lk, e, traceback.format_exc()))
                    rec["error"] = repr(e)[:300]
                finally:
                    for n in ("A", "B"):
                        try:
                            nodes[n].quiet()
                        except Exception as e:            # noqa: BLE001
                            T.say("quiet %s: %r" % (n, e))
            out["cycles"].append(cyc)
            json.dump(out, open(path, "w"), indent=1, default=str)
            cycle += 1
            wait = every * 60 - (time.time() - t_cycle)
            if time.time() + max(0, wait) >= t_end:
                break
            if wait > 0:
                T.say("   cycle took %.0f s; sleeping %.0f s" % (time.time() - t_cycle, wait))
                time.sleep(wait)
    finally:
        for n, s in scopes.items():
            try:
                s.trigger(source=1, level=TS.MARK_V, slope="rising", mode="auto")
                s.run()
                s.close()
            except Exception as e:                        # noqa: BLE001
                T.say("scope %s: %r" % (n, e))
        json.dump(out, open(path, "w"), indent=1, default=str)
        if keeper.arr:
            np.savez_compressed(os.path.join(T.DATA, "soak_%s.npz" % stamp), meta=json.dumps(keeper.meta), **keeper.arr)
        for n in ("A", "B"):
            try:
                nodes[n].quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n, e))
        T.say("done after %d cycles, %.1f h; both quiet" % (len(out["cycles"]), (time.time() - t0) / 3600))


if __name__ == "__main__":
    main()
