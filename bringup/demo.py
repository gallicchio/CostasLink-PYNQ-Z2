"""The courtyard demo's driver (DEMO_COURTYARD.md): one process a station, started once, running for ever.

Station A (the beam's sender) sends A3's four corners at random every `period` clocks (2 bits a symbol, the idle (1, 0)
between them: the random QPSK stream the scopes show) and treats every symbol as a challenge: its receiver, on the
return path, decodes B's echo of each and pairs it with its own TX event, so the round trip's histogram, the replies
right, missed and false come out of the gateware at 2 million a second.  Station B (the beam's receiver) decodes every
symbol and answers it at once by the fast path (the reply map xor1: a corner comes back as its neighbour).  Each station
keeps its own loop with linkd's code in duplex mode (its TX never muted: the other station's loop hangs on it) and
serves its tiles at http://<laptop>:8090/ (demo.html beside this file, /api/demo the numbers).  Nothing alternates:
block the beam and B's symbols stop, A's replies stop and its missed count climbs; clear it and both loops come back by
themselves.

    python3 demo.py A [--tx 4800 --rx 5400] [--port 8090] [--period 50] [--window 45] [--t0_ns T]
    python3 demo.py B [--tx 5400 --rx 4800] [--port 8090]
    --trig_a off      on the bench, where TRIG A is wired into the other board's TRIG IN (JP203 puts it on the Q ladder)
"""
import argparse
import http.server
import json
import math
import os
import signal
import sys
import threading
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gateware", "driver"))
import twoboard as T                                      # noqa: E402
import costaslink as C                                    # noqa: E402
import linkd                                              # noqa: E402

say = T.say
SCHEME = "A3"
REPLY = "xor1"
C_M_PER_NS = 0.299792458
BUDGET = [("cable", "5.0 ns a metre (4.43)"), ("air", "3.34 ns a metre"), ("the boards' RF", "1-3 ns a side"),
          ("B's answer", "about 25 ns from its comparators (the fast path)"), ("A's decision", "85-95 ns from the echo's edge (REVB 68)")]


class DemoKeeper(linkd.LinkD):
    """linkd's keeper with a look that survives data on the carrier.  linkd's own rule wants an idle carrier (few edges,
    I's mean the leg); under the corners at random I's mean is the leg times the idle's share of the time and Q's is
    nothing.  CMP_I's duty gives that share (1 at the idle on this side, 0 on the other, 1 - dc/2 under the stream), so
    the leg is I's mean over |2 duty - 1|, and a lock under data is a clear I mean with Q's mean small beside it.  Without
    this B's setup under A's stream found 'no carrier' at every level (10:37) and its leg read 0.6 of itself (10:05)"""
    def observe(self):
        cl = self.server.cl
        g = cl.gate(seconds=0.01, inputs=("CMP_I", "CMP_QP", "CMP_QN"))
        i, q, vc = cl.adc("I"), cl.adc("Q"), cl.adc("VC")
        di, dq = i - self.i0, q - self.q0
        e_i, e_q = g["CMP_I"]["edges"], g["CMP_QP"]["edges"] + g["CMP_QN"]["edges"]
        duty = g["CMP_I"]["duty"]
        f = abs(2 * duty - 1)
        di_raw = di
        if e_i >= 50 and f >= 0.2:
            di = di / f
        a = max(self.leg or 0.1, abs(di))
        locked = (e_i < 50 and abs(di) > 0.5 * a and abs(dq) < 0.35 * a) or (e_q < 20 and abs(dq) < 0.35 * a and abs(di) > 0.03)
        if not locked and e_i >= 50 and abs(di) > 0.02 and abs(dq) < 0.5 * abs(di):
            locked = True
        return {"locked": locked, "di": di, "dq": dq, "vc": vc, "e_i": e_i, "e_q": e_q, "di_raw": di_raw, "duty_i": duty}


def nominal_tables(cl, s, first_edge=False):
    """the decoder's idle vector, table and owners for scheme s on this receiver from the scheme's geometry alone, the
    180-degree twin when CMP_I reads the other way now (twoboard.rx_tables's nominal branch without the sender's help:
    across the courtyard nobody can ask the far board to hold a point)"""
    g = cl.gate(seconds=0.01, inputs=tuple(C.CMP_NAMES))
    vec = sum((1 if g[n]["duty"] > 0.5 else 0) << k for k, n in enumerate(C.CMP_NAMES))
    use = s
    if (vec ^ s.idle_vector()) & 1:
        use = s.twin()
    lut = use.lut(first_edge)
    owners = {v: (e & 7) for v, e in enumerate(lut) if e & 8}
    info = {"vec": vec, "twin": use is not s, "duty": {n: round(g[n]["duty"], 3) for n in C.CMP_NAMES}}
    return use.idle_vector(), lut, use.slow_exp(), owners, info


def wrap32(now, before):
    d = now - before
    return d + (1 << 32) if d < 0 else d


class Station:
    def __init__(self, a):
        self.a = a
        self.name = a.station
        self.role = "sender" if self.name == "A" else "echo"
        self.node = T.Node(self.name)
        self.cl = self.node.cl
        self.lock = threading.RLock()
        self.s = C.SCHEMES[SCHEME]
        self.rmap = T.reply_maps(self.s.n)[REPLY]
        (vi, vq), _ = self.node.vr(a.tx)
        self.cfg = dict(T.LINK_CFG, duplex=True, tx_mhz=float(a.tx), rx_mhz=float(a.rx), vr={"VR_I": vi, "VR_Q": vq},
                        track_windows=False)
        if self.name in T.Q_OFF_F_V:
            self.cfg["q_off_f"] = T.Q_OFF_F_V[self.name]
        path = os.path.join(T.DATA, "cfg_%s_demo.json" % self.name)
        json.dump(self.cfg, open(path, "w"))
        self.ld = DemoKeeper(T._Srv(self.cl), config=path)
        self.ts_ns = 1e3 / (self.cl.clk_mhz * self.cl.ser)
        self.armed_key = None
        self.bad_looks = 0
        self.info = {}
        self.cal = {}
        self.totals = {}
        self.prev = None
        self.det = {}
        self.t_det = 0.0
        self.state = {"t": time.time(), "station": self.name, "role": self.role, "tx_mhz": a.tx, "rx_mhz": a.rx,
                      "scheme": SCHEME, "period_ns": 10.0 * a.period, "starting": True}
        self.t0_ns = a.t0_ns
        stamp = time.strftime("%Y%m%d_%H%M%S")
        self.logf = open(os.path.join(T.DATA, "demo_%s_%s.jsonl" % (self.name, stamp)), "a")
        self.t_start = time.time()

    # ---- the loop's keeper, in its own thread ----
    def keep(self):
        last = None
        while True:
            with self.lock:
                try:
                    self.ld.step()
                except Exception as e:                    # noqa: BLE001
                    self.ld.mode = "error: %r" % (e,)
            if self.ld.mode != last:
                last = self.ld.mode
                say("keeper %s: %s" % (self.name, last))
            time.sleep(0.2)

    def locked(self):
        return self.ld.set_up and self.ld.mode == "locked"

    # ---- the decoders ----
    def calibrate(self):
        """the four windows from the stream itself: each comparator's duty against its threshold is a staircase whose
        steps are the points' levels, and the points' presence is known (a corner `width` of every `period` clocks at B,
        an echo of `fp_clocks` at A), so a bisection to half a step's duty finds each level (twoboard._level).  IP's +1
        level and -1 level give its centre and swing; IN's the same on the inverted arm; QP / QN's centre is the idle's
        Q (half the stream's duty) and their on level the corner's.  Thresholds at frac_i / frac_q of the swing.  The
        window set from the keeper's leg while the stream ran put B's IP so low that Q crossed QP before I left the
        idle window at the (-1, +1) corner, which was then decided (+1, +1) and vetoed 27 % of the time (11-08 09:55)"""
        cl, a = self.cl, self.a
        g = cl.gate(seconds=0.01, inputs=("CMP_QP", "CMP_QN"))
        e_q = g["CMP_QP"]["edges"] + g["CMP_QN"]["edges"]
        if e_q < 500:                                     # no data on the carrier yet (the far station not up): the plain
            leg = self.ld.leg or 0.1                      # rule from the keeper's leg, and again when the data comes
            thr = {w: min(2.499, max(0.0, self.ld.cen[w] + 0.5 * leg)) for w in ("IP", "IN", "QP", "QN")}
            for w, v in thr.items():
                cl.threshold(w, v)
            self.cal = {"ok": False, "why": "no data on the carrier (e_q %d)" % e_q, "levels": {}, "thresholds": {w: round(v, 4) for w, v in thr.items()}, "t": time.time()}
            say("%s windows: PLAIN from the keeper's leg (no data on the carrier yet, e_q %d)" % (self.name, e_q))
            return False
        dc = (a.width if self.role == "echo" else a.fp_clocks) / float(a.period)     # the corners' share of the time
        p_minus, p_qs = dc / 2, dc / 2                                                # the (-1, q) corners; one sign of Q
        plan = {"IP": (1 - p_minus) / 2, "IN": p_minus / 2, "QP": p_qs / 2, "QN": p_qs / 2}       # on-level targets
        far = {"IP": 1 - p_minus / 2, "IN": 1 - (1 - p_minus) / 2, "QP": 0.5, "QN": 0.5}          # the other level's
        side = 1 if cl.gate(seconds=0.01, inputs=("CMP_I",))["CMP_I"]["duty"] > 0.5 else -1
        if side < 0:                                                                  # the loop's other lock point: the
            plan["IP"], plan["IN"] = plan["IN"], plan["IP"]                           # idle reads -1, the (-1, q) corners
            far["IP"], far["IN"] = far["IN"], far["IP"]                               # +1 (B on side -1 found nothing, 10:41)
        lv, thr, ok = {}, {}, True
        for w in ("IP", "IN", "QP", "QN"):
            on = T._level(cl, w, duty_target=plan[w], seconds=0.01)
            other = T._level(cl, w, duty_target=far[w], seconds=0.01)
            lv[w] = (on, other)
            if on is None or other is None or abs(on - other) < 0.02:      # a level not found, or no real swing (the
                ok = False                                                 # far station's fast path echoing a beat, 10:05)
                continue
            c = other if w in ("QP", "QN") else 0.5 * (on + other)
            f = a.frac_i if w in ("IP", "IN") else a.frac_q
            thr[w] = min(2.499, max(0.0, c + f * (on - c)))
        if not ok:                                                                    # the plain rule from the keeper
            leg = self.ld.leg or 0.1
            for w in ("IP", "IN", "QP", "QN"):
                thr.setdefault(w, min(2.499, max(0.0, self.ld.cen[w] + 0.5 * leg)))
        for w, v in thr.items():
            cl.threshold(w, v)
        self.cal = {"ok": ok, "why": "" if ok else "a level not found", "side": side, "levels": {w: tuple(None if x is None else round(x, 4) for x in v) for w, v in lv.items()},
                    "thresholds": {w: round(v, 4) for w, v in thr.items()}, "t": time.time()}
        say("%s windows from the data (side %+d): %s; levels %s" % (self.name, side, "ok" if ok else "PLAIN (a level not found)", self.cal["levels"]))
        return ok

    def arm(self):
        cl, s, a = self.cl, self.s, self.a
        cl.tx_stop()
        if self.role == "sender":
            cl.triggers(width=10, a="tx_event", b="rx_decision")
            if a.trig_a == "off":
                cl.wr("TRIG_CFG", 10 | 1 << 9 | 2 << 13)
            cl.events(period=a.period, width=a.width, count=0, source="prbs", n=s.n)       # the mode first (4.84)
            cl.tx_points(C.point_code(*s.idle), [C.point_code(*m) for m in s.msgs])
            cl.tx_go()
            self.calibrate()
            iv, lut, sexp, owners, info = nominal_tables(cl, s)
            cl.rx_config(iv, s.mask, lut, sexp, delay=a.delay, quiet=4, confirm=6, window=a.window, settle=a.settle, row="tx")
            cl.hist_config("ref_to_decision", 0)
            cl.rx_clear()
        else:
            cl.wr("TRIG_CFG", 10 | 1 << 9 | 2 << 13)                                       # TRIG B the decision; TRIG A off
            cl.events(period=1000, width=20, count=0, source="fixed", n=1)                 # stopped: the pins at TX_IDLE
            cl.tx_points(C.point_code(*s.idle), [C.point_code(*s.msgs[self.rmap[k]]) for k in range(s.n)])
            self.calibrate()
            iv, lut, sexp, owners, info = nominal_tables(cl, s)
            cl.rx_config(iv, s.mask, lut, sexp, delay=a.delay, quiet=4, confirm=6, window=0, settle=a.settle, row=0)
            cl.reply_off()
            ent = {v: C.point_code(*s.msgs[self.rmap[k]]) for v, k in owners.items() if k < len(self.rmap)}
            word = T._fast_load(cl, ent, "oneshot", self.a.fp_clocks, "rx")
            cl.rx_clear()
            T._fast_arm(cl, word)
        self.info = dict(info, owners=owners, side=-1 if info["twin"] else 1, cal=self.cal)
        self.prev = None
        say("%s armed as the %s: side %+d, idle vector %d, owners %s, thresholds %s" % (
            self.name, self.role, self.info["side"], iv, owners, self.cal["thresholds"]))

    # ---- one look a second ----
    def look(self):
        cl = self.cl
        now = time.time()
        o = self.ld.observe()
        st = {"t": now, "station": self.name, "role": self.role, "tx_mhz": self.a.tx, "rx_mhz": self.a.rx, "scheme": SCHEME,
              "period_ns": 10.0 * self.a.period, "up_s": now - self.t_start, "starting": False}
        sig = abs(o["di"])                                   # the leg now (the keeper's look corrects for the data)
        dsa = cl._dsa_db
        dbm = None
        if sig > 2 * C.ADC_LSB_V:
            dbm = C.DEM_REG_DBM + 20 * math.log10(2 * sig / C.A_REG_V) - C.RX_GAIN_DB + dsa
        if now - self.t_det > 5.0:
            try:
                d = cl.detectors()
                self.det = {"log_dbm": d.get("log_dbm"), "temp_c": d.get("temp_c"), "v5_rf": d.get("v5_rf")}
            except Exception:                                 # noqa: BLE001
                pass
            self.t_det = now
        st["lock"] = {"mode": self.ld.mode, "locked": bool(o["locked"]), "leg_mv": 1e3 * self.ld.leg if self.ld.leg else None,
                      "signal_mv": 1e3 * sig, "rx_ant_dbm": dbm, "vc": o["vc"], "vc_lock": self.ld.vc_lock, "dsa_db": dsa,
                      "side": self.info.get("side"), "losses": self.ld.counts["losses"], "recoveries": self.ld.counts["recoveries"],
                      "lost_for_s": (now - self.ld.lost_since) if self.ld.lost_since else None,
                      "last_recovery_s": self.ld.counts["last_recovery_s"], "t_last_loss": self.ld.counts["t_last_loss"]}
        st["det"] = self.det
        st["cal"] = self.cal
        if self.role == "sender":
            if not (cl.rd("TX_GO") & 1):                     # the stream stopped by something else: arm again
                say("%s: the stream is not running: arming again" % self.name)
                self.armed_key = None
            q = cl.rx_stats()
            h = cl.histogram()
            cm = cl.confusion()
            cl.rx_clear()
            n = self.s.n
            m = [row[:n] for row in cm[:n]]
            tot = sum(sum(r) for r in m)
            right = sum(m[k][self.rmap[k]] for k in range(n))
            dt = (now - self.prev) if self.prev else 1.0
            self.prev = now
            hs = T._hist_summary(h, 0, self.ts_ns)
            rt = {k: hs.get(k) for k in ("n", "p50_ns", "p99_ns", "p999_ns", "min_ns", "max_ns", "bin_ns")}
            rt["bins"] = hs.get("bins", [])
            rates = {"challenges_s": q["refs"] / dt, "replies_s": q["events"] / dt, "missed_s": q["missed"] / dt,
                     "false_s": q["false"] / dt, "wrong_s": (tot - right) / dt, "decided_s": q["decided"] / dt}
            for k, v in (("challenges", q["refs"]), ("replies", q["events"]), ("missed", q["missed"]), ("false", q["false"]),
                         ("wrong", tot - right), ("right", right)):
                self.totals[k] = self.totals.get(k, 0) + v
            st["A"] = {"roundtrip": rt, "rates": rates, "right_frac": (right / tot) if tot else None, "confusion": m,
                       "per_challenge_right": [(m[k][self.rmap[k]] / sum(m[k])) if sum(m[k]) else None for k in range(n)],
                       "totals": dict(self.totals), "t0_ns": self.t0_ns,
                       "path_m": ((rt["p50_ns"] - self.t0_ns) * C_M_PER_NS / 2) if (self.t0_ns is not None and rt.get("p50_ns") is not None) else None,
                       "budget": BUDGET, "reply_map": self.rmap}
            say("%s %5.0f s: %s leg %s mV sig %.0f mV | %.0f k challenges/s, replies %.0f k/s, missed %.0f/s, false %.0f/s, wrong %.0f/s, "
                "right %s | round trip p50 %s p99.9 %s max %s ns" % (
                    self.name, st["up_s"], self.ld.mode[:12], "%.0f" % st["lock"]["leg_mv"] if st["lock"]["leg_mv"] else "-", 1e3 * sig,
                    rates["challenges_s"] / 1e3, rates["replies_s"] / 1e3, rates["missed_s"], rates["false_s"], rates["wrong_s"],
                    "%.5f" % st["A"]["right_frac"] if st["A"]["right_frac"] is not None else "-", rt["p50_ns"], rt["p999_ns"], rt["max_ns"]))
            # the windows again when the replies are all there and still wrong or undecided for three looks running (the
            # side slipped, or the windows were measured on the far station's garbage as it came back: 10:07:12, 95 %
            # for 30 s), never on a transient
            full = rates["replies_s"] > 0.9 * rates["challenges_s"] and rates["challenges_s"] > 1e5
            good = full and rates["decided_s"] > 0.98 * rates["replies_s"] and (st["A"]["right_frac"] or 0) > 0.99
            self.bad_looks = 0 if (good or not full) else self.bad_looks + 1
            if self.bad_looks >= 3 and now - self.cal.get("t", 0) > 5.0:
                say("%s: the replies are all here but %.1f %% decided and %.3f right for three looks: the windows again" % (
                    self.name, 100 * rates["decided_s"] / max(1, rates["replies_s"]), st["A"]["right_frac"] or 0))
                self.armed_key = None
                self.bad_looks = 0
        else:
            q = cl.rx_stats()
            cm = cl.confusion()
            fs = cl.fast_state()
            cur = {k: q.get(k) or 0 for k in ("events", "decided", "false", "undec")}
            dt = (now - self.prev[0]) if self.prev else None
            rates = {}
            if self.prev:
                for k in cur:
                    rates[k + "_s"] = wrap32(cur[k], self.prev[1][k]) / dt
            self.prev = (now, cur)
            row = cm[0][:self.s.n]
            st["B"] = {"rates": rates, "counts": cur, "messages": row, "echo": fs, "undec_known": q.get("undec") is not None}
            say("%s %5.0f s: %s leg %s mV sig %.0f mV | symbols %.0f k/s, decided %.0f k/s, undecided %.0f/s, false %.0f/s; echo armed %d drove %d; messages %s" % (
                self.name, st["up_s"], self.ld.mode[:12], "%.0f" % st["lock"]["leg_mv"] if st["lock"]["leg_mv"] else "-", 1e3 * sig,
                rates.get("events_s", 0) / 1e3, rates.get("decided_s", 0) / 1e3, rates.get("undec_s", 0), rates.get("false_s", 0),
                fs["armed"], fs["drove"], row))
            full = rates.get("events_s", 0) > 1e5
            good = full and rates.get("decided_s", 0) > 0.98 * rates["events_s"]
            self.bad_looks = 0 if (good or not full) else self.bad_looks + 1
            if self.bad_looks >= 3 and now - self.cal.get("t", 0) > 5.0:
                say("%s: symbols arriving but %.1f %% decided for three looks: the windows again" % (self.name, 100 * rates["decided_s"] / rates["events_s"]))
                self.armed_key = None                          # the side slipped, or the windows are off
                self.bad_looks = 0
        if not self.cal.get("ok") and o["e_q"] > 500 and now - self.cal.get("t", 0) > (3.0 if self.cal.get("why", "").startswith("no data") else 20.0):
            self.armed_key = None                              # data on the carrier now: the windows from it (a failed
                                                               # measurement is tried again after 20 s, not every look)
        self.state = st
        self.logf.write(json.dumps({k: v for k, v in st.items() if k != "A"} | ({"A": {k: v for k, v in st["A"].items() if k not in ("budget",)}} if "A" in st else {}), default=str) + "\n")
        self.logf.flush()

    def adopt(self):
        """the PYNQ's own linkd (link.json, duplex) may hold the loop already: take its lock over instead of the 60 s
        setup (its middles, centres, VC and leg from the dashboard's /api/now; the synthesizers' and the DSA's settings
        into this proxy's shadows, which recover() reads)"""
        import urllib.request
        try:
            r = json.loads(urllib.request.urlopen("http://%s:8080/api/now" % T.HOSTS[self.name], timeout=4).read())
        except Exception as e:                                # noqa: BLE001
            say("%s: no dashboard to adopt from (%r)" % (self.name, e))
            return False
        ld = r.get("linkd") or {}
        # its mode may read 'paused: a program is driving' for a minute after the last demo process: what counts is that
        # it set the link up (its centres and VC are there) at these carriers, and that the loop reads locked now
        if not ld.get("cen") or ld.get("vc_lock") is None or not ld.get("leg") or not ld.get("duplex") or r.get("tx_mhz") != self.a.tx or r.get("rx_mhz") != self.a.rx:
            say("%s: nothing to adopt (linkd %s, tx %s rx %s, duplex %s)" % (self.name, ld.get("mode"), r.get("tx_mhz"), r.get("rx_mhz"), ld.get("duplex")))
            return False
        cl = self.cl
        cl._pll = {0: (float(r["tx_mhz"]), 25.0, None), 1: (float(r["rx_mhz"]), 25.0, None)}
        cl._dsa_db = float(r["dsa_db"])
        k = self.ld
        k.i0, k.q0, k.cen = ld["i0"], ld["q0"], ld["cen"]
        k.vc_lock, k.leg = ld["vc_lock"], ld["leg"]
        k.leg_setup = ld.get("leg_setup") or ld["leg"]
        k.leg_windows = ld.get("leg_windows") or ld["leg"]
        k.mid_t = ld.get("mid_t")
        k.duplex = True
        o = k.observe()
        if not o["locked"]:
            say("%s: the PYNQ's lock (leg %.0f mV, DSA %.2f, VC %.4f) does not read locked now: setting up instead" % (self.name, 1e3 * (k.leg or 0), cl._dsa_db, k.vc_lock))
            return False
        k.set_up, k.mode = True, "locked"
        say("%s: adopted the PYNQ's lock (leg %.0f mV, DSA %.2f, VC %.4f)" % (self.name, 1e3 * (k.leg or 0), cl._dsa_db, k.vc_lock))
        return True

    def selftest_off(self):
        """the PYNQ's self-test plan drives the TX in steps when nothing else does: off for the demo (pynq-a's was on and
        put A's TX in hold a moment after the stream started, 10:34)"""
        import urllib.request
        try:
            req = urllib.request.Request("http://%s:8080/api/selftest" % T.HOSTS[self.name], data=b'{"on": false}',
                                         headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=4).read()
            say("%s: the PYNQ's self-test plan switched off" % self.name)
        except Exception as e:                                # noqa: BLE001
            say("%s: could not reach the dashboard to switch the self-test off (%r)" % (self.name, e))

    def run(self):
        self.selftest_off()
        with self.lock:
            if self.role == "echo":
                self.cl.fast_off()                            # a previous process's echo path, answering a beat while the
                self.cl.reply_off()                           # loop is not yet locked, is garbage for the far station
            self.adopt()
        threading.Thread(target=self.keep, daemon=True, name="keeper").start()
        self.stop = False
        while not self.stop:
            if not self.lock.acquire(timeout=0.5):            # the keeper in a setup or a recovery: stay answerable
                continue
            try:
                if self.locked():
                    key = (self.ld.counts["recoveries"], self.ld.counts["losses"])
                    if self.armed_key != key:
                        self.arm()
                        self.armed_key = key
                    self.look()
                else:
                    if self.armed_key is not None and self.role == "echo":
                        self.cl.fast_off()                    # no echoes of a beat while the loop is lost (A saw 'replies'
                        self.armed_key = None                 # a quarter right for a second as B came back, 10:07:09)
                    self.state = dict(self.state, t=time.time(), lock=dict(self.state.get("lock") or {}, mode=self.ld.mode, locked=False,
                                                                            lost_for_s=(time.time() - self.ld.lost_since) if self.ld.lost_since else None),
                                      starting=not self.ld.set_up)
            except Exception as e:                            # noqa: BLE001
                say("%s: %r\n%s" % (self.name, e, traceback.format_exc()[-600:]))
                self.armed_key = None
            finally:
                self.lock.release()
            time.sleep(1.0)
        say("%s: stopped (the board left as it is)" % self.name)


def serve(station, port):
    page = os.path.join(HERE, "demo.html")

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith("/api/demo"):
                body = json.dumps(station.state, default=str).encode()
                ct = "application/json"
            else:
                try:
                    body = open(page, "rb").read()
                except OSError:
                    body = b"demo.html missing"
                ct = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ct)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("0.0.0.0", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True, name="http").start()
    say("tiles at http://0.0.0.0:%d/" % port)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("station", choices=("A", "B"))
    p.add_argument("--tx", type=float, default=None)
    p.add_argument("--rx", type=float, default=None)
    p.add_argument("--port", type=int, default=8090)
    p.add_argument("--period", type=int, default=50, help="clocks a symbol (50: 2 M a second)")
    p.add_argument("--window", type=int, default=45, help="A's pairing window in clocks (under the period)")
    p.add_argument("--fp_clocks", type=int, default=8, help="B's echo held this many clocks (4 left A's I arm short of the (-1, q) corners)")
    p.add_argument("--width", type=int, default=20, help="clocks a corner is held")
    p.add_argument("--delay", type=int, default=16, help="the decision this many samples after the event's first edge (16: at 8 the (-1, +1) echo "
                   "went undecided on A's 75 mV return, its I arm still falling when Q had crossed, REVB 66; the night's A8 d16 was 100 %%)")
    p.add_argument("--settle", type=int, default=0, help="or the settled decision on this many samples (2) with --delay as the cap (16)")
    p.add_argument("--frac_i", type=float, default=0.5, help="IP / IN thresholds at this fraction of their measured swing")
    p.add_argument("--frac_q", type=float, default=0.5, help="QP / QN thresholds at this fraction of their measured swing")
    p.add_argument("--t0_ns", type=float, default=None, help="the round trip at zero path (B4's calibration)")
    p.add_argument("--trig_a", choices=("tx_event", "off"), default="tx_event")
    a = p.parse_args()
    if a.tx is None:
        a.tx = 4800.0 if a.station == "A" else 5400.0
    if a.rx is None:
        a.rx = 5400.0 if a.station == "A" else 4800.0
    st = Station(a)
    st.stop = False

    def on_signal(signum, frame):
        st.stop = True
    signal.signal(signal.SIGTERM, on_signal)
    signal.signal(signal.SIGINT, on_signal)
    serve(st, a.port)
    say("station %s: the %s, TX %g MHz, RX %g MHz, %s every %d clocks" % (a.station, st.role, a.tx, a.rx, SCHEME, a.period))
    st.run()


if __name__ == "__main__":
    main()
