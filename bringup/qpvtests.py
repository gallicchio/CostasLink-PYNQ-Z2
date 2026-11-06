"""The QPV tests that need hands first (QPV_TIMING_REVIEW.md section 6; Jason, 2026-11-04: 'All of those things are in the
cupboard.  Write the tests and rank them by bang-for-the-buck').  Built on twoboard.py (the nodes, links, windows from
the received constellation, the mirror).  Each command says what it needs cabled.

  roundtrip   the real exchange: V (Verifier 0) sends one-of-4 challenges over the dishes, P (the Prover) answers by its
              fast path (or the clocked reply) over a second path, V times and decodes the replies.  V's TX and RX on
              different frequencies (the challenge at --mhz-c, the reply at --mhz-r, 200 MHz apart or more), so neither
              board hears its own TX.  Cabling (10 min): V's RX ANT off its switch onto an FPV antenna on the bench, P's TX
              ANT off its switch onto a second FPV antenna 10-20 cm from it (a 10-20 dB pad on one if the level reads over
              -20 dBm); V's switch left on TX (TX ANT -> SW TX -> ANT -> cable -> dish), P's on RX (dish -> cable -> ANT ->
              SW RX -> RX ANT).  The spool test is this with a measured delay in one leg (--note 'spool 50 m in cable B');
              the all-coax calibration is this with TX ANT -> 40 dB -> RX ANT both ways (--note coax).
  soak        the BER soak with a note (cross-pol, a person in the beam, the WiFi AP on channel 40 ...)
  supplywalk  the boards' supply stepped 4.75-5.30 V under a soak (the watchdog paused)
  coldstart   the boards' 5 V cycled N times (the PYNQs up, link.json on both): time to a working link each time
  autochannel the receiver surveys the band, the quietest channel is chosen, the link set up there and measured
  sdrtime     see sdrtime.py: the B210 / X310's two coherent channels on the two TX MONs, an independent clock

    COSTAS_BENCH_CONFIG=bringup/bench_config_laptop.json python3 bringup/qpvtests.py roundtrip --v A --p B --mhz-c 5200 --mhz-r 5400
"""
import argparse
import json
import math
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("COSTAS_BENCH_CONFIG", os.path.join(HERE, "bench_config_laptop.json"))
sys.path.insert(0, HERE)
import twoboard as T                                   # noqa: E402
import costaslink as C                                 # noqa: E402
import linkd                                           # noqa: E402

say, Log = T.say, T.Log


# ---------------------------------------------------------------------------------------------------------------------
# the duplex pair: V -> P on one frequency, P -> V on another, each board's loop locked to the other's carrier
# ---------------------------------------------------------------------------------------------------------------------
class Duplex:
    def __init__(self, v, p, mhz_c, mhz_r, tr_a_v=0, tr_a_p=1, cfg=None):
        self.v, self.p, self.mhz_c, self.mhz_r = v, p, float(mhz_c), float(mhz_r)
        self.tr_a_v, self.tr_a_p = tr_a_v, tr_a_p
        base = dict(T.LINK_CFG, **(cfg or {}))
        # P receives V's challenge at mhz_c and keeps its own TX synthesizer at mhz_r (its null there)
        (pvi, pvq), _ = p.vr(mhz_r)
        self.VP = T.Link(v, p, mhz_c, cfg=dict(base, tx_mhz=self.mhz_r, vr={"VR_I": pvi, "VR_Q": pvq}))
        # V receives P's reply at mhz_r and keeps its TX synthesizer at mhz_c
        (vvi, vvq), _ = v.vr(mhz_c)
        self.PV = T.Link(p, v, mhz_r, cfg=dict(base, tx_mhz=self.mhz_c, vr={"VR_I": vvi, "VR_Q": vvq}))
        for L in (self.VP, self.PV):
            L._orig_release = L.ld.release_at = self._rx_only_release(L)

    def _rx_only_release(self, L):
        """linkd's release_at without the TX synthesizer's retune (which would glitch this board's outgoing carrier and
        drop the other board's lock): the RX synthesizer alone is moved away for the loop's centring and back"""
        ld = L.ld

        def release_at(vc, pll, dsa, tx_dis, settle_s=1.5):
            cl = ld.server.cl
            if not L._carrier:
                L.tx.idle((1, 0))
                L.tx.cl.ctrl(tx_dis=0)
                L._carrier = True
            cl.ctrl(loop_hold=1, tx_dis=1)
            cl.dsa(31.75)
            cl.pll_tune(1, T.park(L.mhz))
            time.sleep(linkd.RELOCK_S)
            ld.loop_center()
            f, f_pfd, cp = pll.get(1, (L.mhz, 25.0, None))
            cl.pll_tune(1, f, f_pfd=f_pfd, cp=cp)
            time.sleep(linkd.RELOCK_S)
            cl.dsa(dsa)
            u = 3 * linkd.V_MID - cl.adc("VC") - cl.dac_volts()["VC_OFF"]
            cl.dac(C.DAC1, VC_OFF=float(min(3.2, max(0.1, 3 * linkd.V_MID - u - vc))))
            time.sleep(0.05)
            cl.ctrl(tx_dis=1)                              # this board's TX: muted here; the exchange turns it on
            time.sleep(0.05)
            cl.ctrl(loop_hold=0)
            t0 = time.time()
            while time.time() - t0 < settle_s:
                if ld.observe()["locked"]:
                    return True
                time.sleep(0.05)
            return False
        return release_at

    def _place(self):
        v, p = self.v.cl, self.p.cl
        for cl, tx_mhz, rx_mhz, vrf, tr in ((v, self.mhz_c, self.mhz_r, self.v.vr(self.mhz_c)[0], self.tr_a_v),
                                            (p, self.mhz_r, self.mhz_c, self.p.vr(self.mhz_r)[0], self.tr_a_p)):
            cl.safe()
            cl.pll_tune(0, tx_mhz)
            cl.pll_tune(1, rx_mhz)
            cl.dac(VR_I=vrf[0], VR_Q=vrf[1])
            cl.hold_point(1, 0)
            cl.ctrl(tr_a=tr, tx_dis=1)

    def up(self):
        """V's loop on P's idle carrier first (P's setup retunes P's own synthesizers, so it goes second), then P's loop on
        V's carrier, then V's lock recovered (P's TX synthesizer's retune glitched its carrier)"""
        self._place()
        t0 = time.time()
        ok_v = self.PV.ld.setup(self.PV.cfg)
        self.PV._carrier = True
        self.PV.info = {"ok": ok_v, "setup_s": round(time.time() - t0, 1), "dsa": self.v.cl._dsa_db, "leg": self.PV.ld.leg}
        if ok_v:
            self.PV.frame()
        say("V (%s) on P's carrier at %g MHz: %s in %.0f s, DSA %s, leg %s mV, side %s" % (
            self.v.name, self.mhz_r, "locked" if ok_v else "NO LOCK", time.time() - t0, self.v.cl._dsa_db,
            round(1e3 * (self.PV.ld.leg or 0), 1), self.PV.s))
        self.p.cl.ctrl(tx_dis=1)
        t0 = time.time()
        ok_p = self.VP.ld.setup(self.VP.cfg)
        self.VP._carrier = True
        self.VP.info = {"ok": ok_p, "setup_s": round(time.time() - t0, 1), "dsa": self.p.cl._dsa_db, "leg": self.VP.ld.leg}
        if ok_p:
            self.VP.frame()
        say("P (%s) on V's carrier at %g MHz: %s in %.0f s, DSA %s, leg %s mV, side %s" % (
            self.p.name, self.mhz_c, "locked" if ok_p else "NO LOCK", time.time() - t0, self.p.cl._dsa_db,
            round(1e3 * (self.VP.ld.leg or 0), 1), self.VP.s))
        # both carriers on at their idles; V's lock back after P's retune
        self.p.cl.ctrl(tr_a=self.tr_a_p, tx_dis=0)
        self.v.cl.ctrl(tr_a=self.tr_a_v, tx_dis=0)
        self.PV.tx.idle((1, 0))
        self.VP.tx.idle((1, 0))
        time.sleep(0.2)
        st = self.PV.ensure()
        say("V's lock after P's setup: %s" % st)
        self.PV.s = 1 if st["di"] > 0 else -1
        self.PV.wcal = self.PV.slev = None
        return ok_v and ok_p and st["locked"]

    def ensure(self):
        a = self.VP.ensure()
        b = self.PV.ensure()
        self.v.cl.ctrl(tr_a=self.tr_a_v, tx_dis=0)
        self.p.cl.ctrl(tr_a=self.tr_a_p, tx_dis=0)
        return a, b

    def state(self):
        return {"v": self.v.name, "p": self.p.name, "mhz_c": self.mhz_c, "mhz_r": self.mhz_r, "v_dsa": self.v.cl._dsa_db,
                "p_dsa": self.p.cl._dsa_db, "side_p": self.VP.s, "side_v": self.PV.s, "wifi_c": T.wifi_tag(self.mhz_c),
                "wifi_r": T.wifi_tag(self.mhz_r)}


def roundtrip_point(dx, scheme="A3", path="fast", reply="xor1", count=20000, period=1000, width=20, frac=0.5,
                    first_edge=False, delay=16, quiet=4, confirm=6, window=120, settle=0, fp_clocks=4, reply_width=40,
                    source="prbs", msg=None, idle_s=0.5):
    """one exchange run: V sends `count` challenges (PRBS-chosen, or `msg`) every `period` clocks, `width` long; P answers
    every one by the fast path (the reply held fp_clocks) or the clocked reply (reply_width); V's RX engine, referenced
    to its own TX event, counts and histograms the reply's arrival and decision (1.25 ns bins), and its confusion matrix
    [challenge][decoded] is the reply as received against the map"""
    V, P = dx.v.cl, dx.p.cl
    s = C.SCHEMES[scheme]
    rmap = T.reply_maps(s.n).get(reply, list(T.reply_maps(s.n).values())[0])
    out = {"exp": "roundtrip", "scheme": scheme, "path": path, "reply": reply, "reply_map": rmap, "count": count,
           "period": period, "width": width, "frac": frac, "first_edge": first_edge, "delay": delay, "window": window,
           "settle": settle, "fp_clocks": fp_clocks, "reply_width": reply_width, "source": source, "msg": msg}
    a, b = dx.ensure()
    out["locks"] = {"p_on_v": a, "v_on_p": b}
    if not (a["locked"] and b["locked"]):
        out["error"] = "no lock"
        return out
    # P decodes V's challenges in its frame; V decodes P's replies in its own
    out["p_windows"], out["p_levels"], out["p_gaps_mv"] = T.scheme_windows(dx.VP, s, frac)
    out["v_windows"], out["v_levels"], out["v_gaps_mv"] = T.scheme_windows(dx.PV, s, frac)
    ts = 1e3 / (dx.v.clk_mhz * dx.v.ser)
    try:
        # P: its RX engine on the scheme (so it re-arms after each challenge), its reply path armed on RX re-arm
        P.tx_stop()
        P.tx_points(dx.PV.pt(*s.idle), [dx.PV.pt(*m) for m in s.msgs])
        p_iv, p_lut, p_sexp, out["p_rx_info"] = T.rx_tables(dx.VP, s, first_edge)      # P's view of V's challenges
        P.rx_config(p_iv, s.mask, p_lut, p_sexp, delay=delay, quiet=quiet, confirm=confirm, window=0, first_edge=first_edge,
                    settle=settle, row=0)
        if path == "fast":
            P.reply_off()
            cm = T._code_map(dx.PV)
            owners = out["p_rx_info"].get("owners") or {}
            ent = {v_: cm[C.point_code(*s.msgs[rmap[k]])] for v_, k in owners.items() if k < len(rmap)}
            fp_word = T._fast_load(P, ent, "oneshot", fp_clocks, "rx")
            T._fast_arm(P, fp_word)                 # not P.fast_arm(): it clears the arm-on-RX bit (T._fast_arm's note)
        elif path == "hardware":                    # row 14: a lead from P's comparator monitor to its own TRIG IN keys +Q
            P.fast_off()                            # on the air (JP203): no gateware in the reply; P's idle must have Q = 0
            P.reply_off()
            P.hold_point(*dx.PV.pt(1, 0))
        else:
            P.fast_off()
            P.reply_config(list(rmap), width=reply_width, once=False, rearm="rx")
        P.rx_clear()
        # V: its challenges, its decoder on the replies, referenced to its own TX events
        V.tx_stop()
        v_iv, v_lut, v_sexp, out["v_rx_info"] = T.rx_tables(dx.PV, s, first_edge)      # V's view of P's idle
        V.tx_points(dx.VP.pt(*s.idle), [dx.VP.pt(*m) for m in s.msgs])
        V.rx_config(v_iv, s.mask, v_lut, v_sexp, delay=delay, quiet=quiet, confirm=confirm, window=window,
                    first_edge=first_edge, settle=settle, row="tx")
        V.turnaround_config(mask=0x1E, guard=12, window=255)
        V.rx_clear()
        time.sleep(idle_s)
        V.rx_enable(False)
        out["v_idle_false_per_s"] = V.rx_stats()["events"] / idle_s
        res = {}
        for what in ("ref_to_event", "ref_to_decision"):
            # the idle after a run (tx.idle: hold_point) rewrites the TX points: both boards' points again before each run
            # (17:25: the second run of every point sent the wrong challenges, P decoded none or one constant message)
            V.tx_points(dx.VP.pt(*s.idle), [dx.VP.pt(*m) for m in s.msgs])
            P.tx_points(dx.PV.pt(*s.idle), [dx.PV.pt(*m) for m in s.msgs])
            V.rx_config(v_iv, s.mask, v_lut, v_sexp, delay=delay, quiet=quiet, confirm=confirm, window=window,
                        first_edge=first_edge, settle=settle, row="tx")
            V.hist_config(what, 0)
            V.rx_clear()
            P.rx_clear()
            if source == "fixed":
                V.tx_msg(msg or 0)
            V.events(period=period, width=width, count=count, source=source, n=s.n)
            V.tx_go()
            time.sleep(count * period / (dx.v.clk_mhz * 1e6) + 0.05)
            V.rx_enable(False)
            q = V.rx_stats()
            h = V.histogram()
            cmx = V.confusion()
            pq = P.rx_stats()
            rt = V.turnaround_stats()
            V.tx_stop()
            dx.VP.tx.idle((1, 0))
            r = T._hist_summary(h, 0, ts)
            r["stats"] = {k: q.get(k) for k in ("events", "decided", "false", "missed", "refs", "lat_n", "lat_min", "lat_max", "lat_mean")}
            r["lat_min_ns"] = q["lat_min"] * ts if q["lat_n"] else None
            r["lat_max_ns"] = q["lat_max"] * ts if q["lat_n"] else None
            r["lat_mean_ns"] = q["lat_mean"] * ts if q["lat_n"] else None
            m4 = [row[:s.n] for row in cmx[:s.n]]
            r["confusion"] = m4
            tot = sum(sum(x) for x in m4)
            r["reply_right_frac"] = (sum(m4[k][rmap[k]] for k in range(s.n)) / tot) if tot else None
            r["per_challenge_right"] = [(m4[k][rmap[k]] / sum(m4[k])) if sum(m4[k]) else None for k in range(s.n)]
            r["p_stats"] = {k: pq.get(k) for k in ("events", "decided", "false", "missed")}
            r["p_reply"] = P.fast_state() if path == "fast" else P.reply_stat()
            r["rt_last_ref_to_arrival_ns"] = rt.get("last_ref_to_arrival_ns")
            res[what] = r
        out["results"] = res
        ev, de = res["ref_to_event"], res["ref_to_decision"]
        out.update(replies=ev["stats"]["events"], missed=ev["stats"]["missed"], false=ev["stats"]["false"],
                   arrival_p50_ns=ev.get("p50_ns"), arrival_p99_ns=ev.get("p99_ns"), arrival_p999_ns=ev.get("p999_ns"),
                   arrival_min_ns=ev.get("min_ns"), arrival_max_ns=ev.get("max_ns"),
                   decision_p50_ns=de.get("p50_ns"), decision_max_ns=de.get("max_ns"),
                   reply_right_frac=de.get("reply_right_frac"), per_challenge_right=de.get("per_challenge_right"))
    finally:
        try:
            P.fast_off()
            P.reply_off()
            P.rx_enable(True)
            V.wr("RT_CFG", 0)
            V.tx_stop()
            V.rx_enable(True)
            dx.VP.tx.idle((1, 0))
            dx.PV.tx.idle((1, 0))
        except Exception as e:                                  # noqa: BLE001
            out["cleanup_error"] = repr(e)[:200]
    return out


RT_BASE = {"scheme": "A3", "path": "fast", "reply": "xor1", "count": 20000, "period": 1000, "width": 20, "frac": 0.5,
           "first_edge": False, "delay": 16, "settle": 0, "fp_clocks": 4, "reply_width": 40, "window": 120}
RT_OFAT = {"frac": [0.3, 0.4, 0.6, 0.7], "delay": [4, 8, 12, 24, 32], "settle": [2, 4], "first_edge": [True],
           "width": [5, 10, 40], "fp_clocks": [1, 2, 8], "period": [200, 500, 5000], "window": [60, 255]}


def roundtrip_plan(schemes=("A3", "B2", "A2", "B1"), quick=False):
    pts = []
    for sc in schemes:
        s = C.SCHEMES[sc]
        maps = list(T.reply_maps(s.n))
        for path in ("fast", "sync"):
            base = dict(RT_BASE, scheme=sc, path=path)
            for r in (maps if path == "fast" else maps[:1]):
                pts.append(dict(base, reply=r, tag="map"))
            for k, vals in RT_OFAT.items():
                for v_ in (vals[::2] if quick else vals):
                    pts.append(dict(base, tag="ofat_" + k, **{k: v_}))
            for m in range(s.n):                                  # each challenge alone, for its own histogram
                pts.append(dict(base, tag="fixed_msg", source="fixed", msg=m, count=5000))
    return pts


def cmd_roundtrip(a, log):
    nodes = {n: T.Node(n) for n in ("A", "B")}
    dx = Duplex(nodes[a.v], nodes[a.p], a.mhz_c, a.mhz_r, tr_a_v=a.tr_a_v, tr_a_p=a.tr_a_p)
    try:
        ok = dx.up()
        log(label="roundtrip", exp="setup", note=a.note, state=dx.state(), ok=ok, vp=dx.VP.info, pv=dx.PV.info)
        if not ok:
            say("no duplex lock: stop")
            return
        t_end = time.time() + a.minutes * 60 if a.minutes else None
        first = True
        while first or (t_end and time.time() < t_end):
            first = False
            if a.prover_mode == "hardware":
                pts = [dict(RT_BASE, scheme="A2", path="hardware", tag="hardware")] + \
                      [dict(RT_BASE, scheme="A2", path="hardware", tag="fixed_msg", source="fixed", msg=m, count=5000) for m in range(2)]
            elif a.repeat_only:
                pts = [dict(RT_BASE, scheme=sc, tag="repeat") for sc in (a.scheme or ["A3", "B2"])]
            else:
                pts = roundtrip_plan(tuple(a.scheme) if a.scheme else ("A3", "B2", "A2", "B1"), a.quick)
            for p in pts:
                tag = p.pop("tag", None)
                try:
                    r = roundtrip_point(dx, **p)
                except Exception as e:                          # noqa: BLE001
                    r = {"error": repr(e)[:300], "tb": traceback.format_exc()[-800:]}
                    say("roundtrip %s: %r" % (p, e))
                d = {}
                try:
                    d = {"v_temp_c": dx.v.cl.detectors().get("temp_c"), "p_temp_c": dx.p.cl.detectors().get("temp_c")}
                except Exception:                               # noqa: BLE001
                    pass
                log(label="roundtrip", tag=tag, note=a.note, params=p, state=dx.state(), **d, **r)
                if not r.get("error"):
                    say("%s %s %s %s: replies %s/%s (missed %s false %s) arrival p50 %s p99 %s max %s ns; decision p50 %s; right %s %s" % (
                        r["scheme"], r["path"], r["reply"], tag, r.get("replies"), p.get("count"), r.get("missed"), r.get("false"),
                        r.get("arrival_p50_ns"), r.get("arrival_p99_ns"),
                        r.get("arrival_max_ns"), r.get("decision_p50_ns"), r.get("reply_right_frac"),
                        [round(x, 4) if x is not None else None for x in (r.get("per_challenge_right") or [])]))
                if t_end and time.time() >= t_end:
                    break
    finally:
        for n in nodes.values():
            try:
                n.quiet()
            except Exception:                                   # noqa: BLE001
                pass


# ---------------------------------------------------------------------------------------------------------------------
# soak with a note; the supply walk; the cold start; the autonomous channel
# ---------------------------------------------------------------------------------------------------------------------
def cmd_soak(a, log):
    nodes = {n: T.Node(n) for n in ("A", "B")}
    d = a.dir[0]
    L = T.Link(nodes[d[0]], nodes[d[1]], a.mhz[0])
    try:
        if not L.up():
            log(label="soak", exp="setup", note=a.note, state=L.state(), **L.info)
            return
        log(label="soak", exp="setup", note=a.note, state=L.state(), **L.info)
        T.soak(log, L, minutes=a.minutes, cond=a.note)
    finally:
        for n in nodes.values():
            n.quiet()


def cmd_supplywalk(a, log):
    """the boards' supply from 5.30 down to 4.75 V and back in 0.05 V steps, `dwell` seconds each, the B -> A soak's
    windows throughout (the watchdog paused: +5V_RF would trip its limit)"""
    import bench as B
    b = B.Bench("A", "supply")
    open(B.WATCH_PAUSE, "w").write(str(int(time.time() + a.minutes * 60 + 120)))
    nodes = {n: T.Node(n) for n in ("A", "B")}
    L = T.Link(nodes["B"], nodes["A"], a.mhz[0])
    try:
        if not L.up():
            return
        volts = [round(5.30 - 0.05 * k, 2) for k in range(12)] + [round(4.75 + 0.05 * k, 2) for k in range(12)]
        for v in volts:
            b.psu_setup(volts=v)                     # the limit and OVP as the bench has them, the voltage stepped
            time.sleep(0.5)
            r = b.psu_read("supplywalk %.2f" % v)
            d = {n: nodes[n].cl.detectors() for n in ("A", "B")}
            log(label="supplywalk", exp="step", volts_set=v, psu=r, v5_rf={n: d[n].get("v5_rf") for n in d},
                temp={n: d[n].get("temp_c") for n in d})
            bits, errs = T.soak(log, L, minutes=a.dwell / 60.0, cond="supply %.2f V" % v)
            say("supply %.2f V: %s A, +5V_RF A %.3f B %.3f: %.3g bits, %.0f errors" % (
                v, r.get("amps"), d["A"].get("v5_rf") or 0, d["B"].get("v5_rf") or 0, bits, errs))
    finally:
        try:
            b.psu_setup(volts=5.30)
        except Exception:                                       # noqa: BLE001
            pass
        for n in nodes.values():
            n.quiet()


def _linkd_mode(host):
    import urllib.request
    try:
        now = json.loads(urllib.request.urlopen("http://%s:8080/api/now" % host, timeout=3).read())
        return (now.get("linkd") or {}).get("mode"), now
    except Exception:                                           # noqa: BLE001
        return None, None


def cmd_coldstart(a, log):
    """the boards' 5 V off and on `n` times (the PYNQs stay up, their linkd with link.json on each: A receiving at mhz,
    B sending), the time from power to both pages saying 'locked'.  Needs link.json deployed on both PYNQs (the
    candidates: gateware/driver/link_A_rx5200.json, link_B_tx5200.json) and the campaign stopped."""
    import bench as B
    b = B.Bench("A", "coldstart")
    for k in range(a.n):
        b.psu_output(False)
        time.sleep(a.off_s)
        t0 = time.time()
        b.psu_output(True)
        got = {}
        while time.time() - t0 < a.timeout_s:
            for host, name in ((T.HOSTS["A"], "A"), (T.HOSTS["B"], "B")):
                if name not in got:
                    m, now = _linkd_mode(host)
                    if m and m.startswith("locked"):
                        got[name] = round(time.time() - t0, 1)
            if len(got) == 2:
                break
            time.sleep(1.0)
        rec = {"cycle": k, "t_lock_s": got, "both_s": max(got.values()) if len(got) == 2 else None,
               "modes": {n: _linkd_mode(T.HOSTS[n])[0] for n in ("A", "B")}}
        log(label="coldstart", exp="cycle", **rec)
        say("cold start %d: %s" % (k, rec))
        time.sleep(a.hold_s)


def cmd_autochannel(a, log):
    """both TXs muted, the receiver surveys the band at 5 MHz steps (the slow window's noise fit), the quietest 25 MHz
    grid frequency with the least inr_db over its +-20 MHz is chosen, the link set up there and measured (a quick prbs
    and events set)"""
    nodes = {n: T.Node(n) for n in ("A", "B")}
    d = a.dir[0]
    tx, rx = nodes[d[0]], nodes[d[1]]
    tx.quiet()
    rx.quiet()
    rx.cl.ctrl(tr_a=1)
    lo, hi = int(a.lo), int(a.hi)
    freqs = list(range(lo, hi + 1, 5))
    rows = rx.cl.survey(freqs, path="slow", net_timeout=600) if False else rx.cl.survey(freqs, path="slow")
    by = {r["mhz"] if isinstance(r, dict) and "mhz" in r else f: r for f, r in zip(freqs, rows)}
    log(label="autochannel", exp="survey", rx=rx.name, rows=rows)
    best = None
    for f in range(lo + 25 - lo % 25, hi + 1, 25):
        near = [by[g] for g in range(f - 20, f + 21, 5) if g in by and isinstance(by[g], dict)]
        if not near:
            continue
        inr = max((r.get("inr_db") or 0) for r in near)
        tail = max((r.get("tail") or 0) for r in near)
        score = inr + 10 * tail
        if best is None or score < best[1]:
            best = (f, score, inr, tail)
    say("survey %d-%d: quietest %s MHz (worst INR %.1f dB, tail %.2g over +-20 MHz)" % (lo, hi, best[0], best[2], best[3]))
    log(label="autochannel", exp="choice", mhz=best[0], score=best[1], inr_db=best[2], tail=best[3])
    L = T.Link(tx, rx, float(best[0]))
    try:
        if not L.up():
            log(label="autochannel", exp="setup", state=L.state(), **L.info)
            return
        log(label="autochannel", exp="setup", state=L.state(), **L.info)
        pts = [dict(T.PRBS_BASE, const=c, frac=T.CONST_FRAC.get(c, 0.5), tag="auto") for c in T.CONSTS]
        T.run_points(log, L, T.prbs_point, pts, "autochannel prbs")
        pts = [dict(T.EVENTS_BASE, scheme=sc, tag="auto") for sc in ("A3", "A2")]
        T.run_points(log, L, T.events_point, pts, "autochannel events")
    finally:
        for n in nodes.values():
            n.quiet()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("cmd", choices=["roundtrip", "soak", "supplywalk", "coldstart", "autochannel"])
    ap.add_argument("--v", default="A", help="roundtrip: Verifier 0")
    ap.add_argument("--p", default="B", help="roundtrip: the Prover")
    ap.add_argument("--mhz-c", type=float, default=5200.0, help="roundtrip: the challenge's carrier (V's TX)")
    ap.add_argument("--mhz-r", type=float, default=5400.0, help="roundtrip: the reply's carrier (P's TX)")
    ap.add_argument("--tr-a-v", type=int, default=0, help="roundtrip: V's switch (0: its TX on ANT)")
    ap.add_argument("--tr-a-p", type=int, default=1, help="roundtrip: P's switch (1: its RX on ANT)")
    ap.add_argument("--scheme", nargs="+", default=None)
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--minutes", type=float, default=0.0, help="roundtrip: repeat the plan until; soak: its length")
    ap.add_argument("--repeat-only", action="store_true", help="roundtrip: the baseline point only, repeated (temperature)")
    ap.add_argument("--note", default="", help="what is different (spool 50 m, coax, cross-pol, WiFi AP ch 40 ...)")
    ap.add_argument("--prover-mode", choices=["gateware", "hardware"], default="gateware",
                    help="roundtrip: 'hardware': P's paths off, its reply keyed by a lead from its comparator monitor to its TRIG IN (A2's Q step)")
    ap.add_argument("--dir", nargs="+", default=["BA"])
    ap.add_argument("--mhz", type=float, nargs="+", default=[5200.0])
    ap.add_argument("--dwell", type=float, default=60.0, help="supplywalk: seconds a step")
    ap.add_argument("--n", type=int, default=10, help="coldstart: cycles")
    ap.add_argument("--off-s", type=float, default=10.0)
    ap.add_argument("--hold-s", type=float, default=30.0)
    ap.add_argument("--timeout-s", type=float, default=300.0)
    ap.add_argument("--lo", type=float, default=5150.0)
    ap.add_argument("--hi", type=float, default=5850.0)
    a = ap.parse_args(argv)
    log = Log("qpv_" + a.cmd)
    open(os.path.join(T.DATA, "qpvtests.pid"), "w").write(str(os.getpid()))
    {"roundtrip": cmd_roundtrip, "soak": cmd_soak, "supplywalk": cmd_supplywalk, "coldstart": cmd_coldstart,
     "autochannel": cmd_autochannel}[a.cmd](a, log)
    say("done")


if __name__ == "__main__":
    main()
