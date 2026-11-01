"""selftest.py: the link checking itself, in the board server beside linkd (Jason, 2026-10-31: a demonstration with
single-shot 'idle to one of N' latency tests and continuous data with timing recovery and bit-error estimation, the
status page changing with what the board does and what the B210 does; and the deployed link's own check on its data
path, TODO 'the eye, latency and bit errors need data on the link').

    netbus.py serve --dashboard 8080 --linkd --selftest
    POST /api/selftest {"on": true, "plan": "cycle" | "data" | "symbols" | "carrier"}      (the page's server)
    POST /api/selftest {"holdover": true | false}     the signal holdover on or off (off at reset and after a restart:
                                                      whether deployment keeps it on is Jason's call, BRINGUP_LOG 4.22)

A plan is a list of steps run in turn, round and round, each only while linkd stands by with the link locked:
    idle     the carrier alone for `seconds`: the page reads the carrier's level then (RX ANT, the demodulator)
    symbols  single symbols of a scheme (A3, A1, A2, A1w in turn, or the one named), from the idle to one of its 1, 2
             or 4 states and back: one every `period` clocks, `width` clocks long, for `seconds`; the receiver's
             decisions (right, wrong, false, missed) and the latency (campaign.py's scheme_run, here on the board)
    data     BPSK PRBS15, one bit every `period` clocks (in turn through `periods`), for `seconds`, the check's timing
             recovered from CMP_I's own edges; the page reads the bit errors every second (campaign.py's ber_once)
It takes the server's lock only for each burst of requests, so the page goes on looking and linkd on watching while a
step runs.  When linkd recovers the link, linkd.recover() calls abort() first (data on the link keeps linkd's detector
from ever reading locked), and the step in progress is recorded as interrupted.  A client driving the board (a bench
test) pauses it as it pauses linkd.  Whether it is on, and its plan, are kept in selftest.json beside the server.
"""
import collections
import json
import os
import threading
import time

from costaslink import SCHEMES, Scheme, point_code

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "selftest.json")

PLANS = {
    # a demonstration's round: the level, single symbols, data at a rate that changes each round (about 16 s); 2 Mbaud
    # among them for the bench scope, whose monitor taps smooth over about 0.1 us and close its eye above 5 Mbaud
    "cycle": [{"step": "idle", "seconds": 3.0},
              {"step": "symbols", "seconds": 4.0, "period": 2000, "width": 20},
              {"step": "data", "seconds": 8.0, "periods": [50, 10, 5, 4, 2]}],
    # data nearly all the time (the bit errors every second), the level once a round, 25 Mbaud and 2 Mbaud in turn
    "data": [{"step": "idle", "seconds": 2.0}, {"step": "data", "seconds": 28.0, "periods": [4, 50]}],
    # single symbols nearly all the time, the schemes in turn
    "symbols": [{"step": "idle", "seconds": 2.0}, {"step": "symbols", "seconds": 13.0, "period": 2000, "width": 20}],
    # the carrier alone: the level every second
    "carrier": [{"step": "idle", "seconds": 10.0}],
}
SCHEME_ROTA = ("A3", "A1", "A2", "A1w")
SCHEME_TEXT = {"A1": "the BPSK flip (1 of 1)", "A1w": "the BPSK flip seen beside the idle (1 of 1)",
               "A2": "1 bit: the Q step (1 of 2)", "A3": "2 bits: the QPSK corners (1 of 4)"}


class _Frame(Scheme):
    """a scheme seen in this lock's frame: the idle on side x I, the I arm mirrored (REVB 9; campaign.Frame0)"""

    def __init__(self, tx, side):
        super().__init__(tx.name, tx.text, tx.idle, tx.msgs, [], rot_deg=0.0, pilot=tx.pilot, t=tx.t, t2=tx.t2)
        self.mask, self.use, self.side = tx.mask, tx.use, side

    def rx_point(self, iq):
        return (self.side * iq[0], -self.side * iq[1])


class SelfTest:
    def __init__(self, server, poll_s=0.2):
        self.server, self.poll_s = server, poll_s
        self.on, self.plan_name = False, "cycle"
        try:
            with open(STATE_FILE) as f:
                d = json.load(f)
            self.on, self.plan_name = bool(d.get("on")), d.get("plan", "cycle")
        except (OSError, ValueError):
            pass
        self.now = {"step": "off", "since": time.time(), "text": "off"}
        self.results = collections.deque(maxlen=30)
        self._k = {"scheme": 0, "period": 0}
        self._aborted = False
        self._busy = False                   # a step's TX, RX or bit check is set up on the board

    # ---- for the page ----
    def state(self):
        return {"on": self.on, "plan": self.plan_name, "now": dict(self.now), "results": list(self.results)[-3:]}

    def set(self, d):
        """POST /api/selftest: {"on": bool, "plan": name, "holdover": bool}"""
        if "holdover" in d:                              # from inside the server: linkd is not paused by it
            self._do(lambda cl: cl.shold(bool(d["holdover"])))
        if "plan" in d:
            if d["plan"] not in PLANS:
                raise ValueError("no plan %r (%s)" % (d["plan"], ", ".join(PLANS)))
            self.plan_name = d["plan"]
        if "on" in d:
            self.on = bool(d["on"])
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({"on": self.on, "plan": self.plan_name}, f)
        except OSError:
            pass
        return self.state()

    # ---- the board ----
    def _do(self, fn):
        with self.server.lock:
            return fn(self.server.cl)

    def _free(self):
        """the link locked and linkd standing by, and no client driving"""
        L = getattr(self.server, "linkd", None)
        if L is not None:
            if L.driving() or L.mode not in ("locked", "watching"):
                return False
        return True

    def _side(self, cl):
        L = getattr(self.server, "linkd", None)
        i0 = L.i0 if L is not None else 1.65
        return 1 if cl.adc("I") > i0 else -1

    def abort(self, cl):
        """the idle carrier back at once, under the caller's lock (linkd.recover())"""
        if not self._busy:
            return
        self._aborted = True
        try:
            cl.ber_config(15, None, enable=False, cdr=True)
            cl.rx_enable(False)
            cl.tx_stop()
            cl.hold_point(1, 0)
        finally:
            self._busy = False

    def _watch(self, seconds, losses0):
        """wait out a step; False if it was interrupted (linkd recovering, a client driving, switched off)"""
        t_end = time.time() + seconds
        L = getattr(self.server, "linkd", None)
        while time.time() < t_end:
            time.sleep(self.poll_s)
            if self._aborted or not self.on or (L is not None and (L.counts["losses"] != losses0 or L.driving()
                                                                    or L.mode not in ("locked", "watching"))):
                return False
        return True

    def _b210(self, t0, t1):
        """what the B210 was announced to send during [t0, t1] (the page's notes), in words, or 'quiet'"""
        d = getattr(self.server, "dashboard", None)
        if d is None:
            return None
        said = [n["text"] for n in list(d.notes) if (n.get("b210") or n.get("text", "").startswith("B210"))
                and n["t_start"] <= t1 and (n.get("t_end") or t1) >= t0]
        return "; ".join(said)[:300] if said else "quiet"

    def _say(self, step, text, **kw):
        self.now = dict({"step": step, "since": time.time(), "text": text}, **kw)

    # ---- the steps ----
    def idle(self, st):
        self._say("idle", "the carrier alone, %g s: the page reads its level" % st["seconds"], seconds=st["seconds"])
        L = getattr(self.server, "linkd", None)
        ok = self._watch(st["seconds"], L.counts["losses"] if L else 0)
        return {"step": "idle", "seconds": st["seconds"], "interrupted": not ok}

    def symbols(self, st):
        name = st.get("scheme") or SCHEME_ROTA[self._k["scheme"] % len(SCHEME_ROTA)]
        self._k["scheme"] += 1
        period, width, seconds = int(st["period"]), int(st["width"]), float(st["seconds"])
        tx = SCHEMES[name]
        L = getattr(self.server, "linkd", None)
        losses0 = L.counts["losses"] if L else 0

        def start(cl):
            count = max(10, int(seconds / (period * cl.t_clk)))
            side = self._side(cl)
            rx = _Frame(tx, side)
            rx_s = Scheme(name, tx.text, rx.rx_point(tx.idle), [rx.rx_point(m) for m in tx.msgs], [], t=tx.t, t2=tx.t2)
            rx_s.mask, rx_s.use = tx.mask, tx.use
            cl.tx_points(tx.tx_idle(), [point_code(i, q) for i, q in tx.msgs])
            cl.rx_config(rx_s.idle_vector(), rx_s.mask, rx_s.lut(False), rx_s.slow_exp(), delay=16, quiet=4, confirm=10,
                         window=max(4, min(100, period - 6)), first_edge=False)     # the window inside the period
            cl.hist_config("ref_to_decision", 0)
            cl.events(period=period, width=width, count=count, n=tx.n, source="prbs" if tx.n > 1 else "count")
            cl.rx_clear()
            cl.tx_go()
            self._busy = True
            return count, side, cl.t_clk, cl.t_sample
        count, side, t_clk, t_sample = self._do(start)
        self._say("symbols", "single symbols of %s, %s: one every %.3g us, %d clocks long, %d of them" % (
            name, SCHEME_TEXT[name], period * t_clk * 1e6, width, count), scheme=name, period=period, width=width,
            count=count, seconds=seconds)
        ok = self._watch(count * period * t_clk + 0.2, losses0)
        if ok:
            ok = self._watch(1.3, losses0)                      # a look of the page's with the counts final

        def finish(cl):
            s = cl.rx_stats()
            cm = cl.confusion()
            cl.rx_enable(False)
            cl.tx_stop()
            cl.hold_point(1, 0)
            self._busy = False
            n = tx.n
            return {"events": s.get("events"), "right": sum(cm[a][a] for a in range(n)),
                    "wrong": sum(cm[a][b] for a in range(n) for b in range(n) if a != b), "false": s.get("false"),
                    "missed": s.get("missed"), "lat_ns": [s[k] * t_sample * 1e9 if s.get(k) is not None else None
                                                         for k in ("lat_min", "lat_mean", "lat_max")] if s.get("lat_n") else None}
        res = self._do(finish) if not self._aborted else {}
        return dict({"step": "symbols", "scheme": name, "period": period, "width": width, "count": count, "side": side,
                     "interrupted": not ok}, **res)

    def data(self, st):
        ps = st.get("periods") or [st.get("period", 4)]
        period = int(ps[self._k["period"] % len(ps)])
        self._k["period"] += 1
        seconds = float(st["seconds"])
        L = getattr(self.server, "linkd", None)
        losses0 = L.counts["losses"] if L else 0

        def start(cl):
            side = self._side(cl)
            cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
            cl.tx_timing(period=period)
            cl.tx_prbs(15)
            cl.tx_mode("prbs", n=2)
            cl.tx_go()
            self._busy = True
            time.sleep(0.005)
            cl.ber_config(15, None, invert=side > 0, enable=True, cdr=True, period=period)
            return side, cl.t_clk
        side, t_clk = self._do(start)
        self._say("data", "BPSK PRBS15 data at %.3g Mbaud, the bits checked with the timing recovered, %g s" % (
            1e-6 / (period * t_clk), seconds), period=period, mbaud=1e-6 / (period * t_clk), seconds=seconds)
        ok = self._watch(seconds, losses0)

        def finish(cl):
            cl.ber_config(15, None, invert=side > 0, enable=False, cdr=True, period=period)
            r = cl.ber()
            c = cl.cdr_state()
            cl.tx_stop()
            cl.hold_point(1, 0)
            self._busy = False
            return {"bits": r.get("bits"), "errors": (r.get("mismatches") or 0) / 3.0, "ber": r.get("ber"),
                    "skew_samples": c.get("skew_samples")}
        res = self._do(finish) if not self._aborted else {}
        return dict({"step": "data", "period": period, "mbaud": 1e-6 / (period * t_clk), "seconds": seconds, "side": side,
                     "interrupted": not ok}, **res)

    # ---- the loop ----
    def run(self):
        k = 0
        while True:
            if not self.on:
                if self.now["step"] != "off":
                    self._say("off", "off")
                time.sleep(0.5)
                continue
            if not self._free():
                if self.now["step"] != "waiting":
                    self._say("waiting", "waiting for the link locked and no program driving the board")
                time.sleep(0.5)
                continue
            plan = PLANS.get(self.plan_name, PLANS["cycle"])
            st = plan[k % len(plan)]
            k += 1
            self._aborted = False
            t0 = time.time()
            try:
                res = getattr(self, st["step"])(st)
            except Exception as e:                                   # noqa: BLE001 - never stops the server
                res = {"step": st["step"], "error": "%s: %s" % (type(e).__name__, str(e)[:160])}
                try:
                    self._do(self.abort)
                except Exception:                                    # noqa: BLE001
                    pass
                time.sleep(2.0)
            if self._aborted:
                res["interrupted"] = True
            res.update(t0=t0, t1=time.time())
            res["b210"] = self._b210(t0, res["t1"])
            self.results.append(res)

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="selftest").start()
        return self
