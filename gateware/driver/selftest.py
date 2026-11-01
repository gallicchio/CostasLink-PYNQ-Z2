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
              {"step": "data", "seconds": 8.0, "periods": [50, 10, 5, 4, 2], "gap_every": 1.0}],
    # data nearly all the time (the bit errors every second), the level once a round, 25 Mbaud and 2 Mbaud in turn
    "data": [{"step": "idle", "seconds": 2.0}, {"step": "data", "seconds": 28.0, "periods": [4, 50], "gap_every": 1.0}],
    # single symbols nearly all the time, the schemes in turn
    "symbols": [{"step": "idle", "seconds": 2.0}, {"step": "symbols", "seconds": 13.0, "period": 2000, "width": 20}],
    # the carrier alone: the level every second
    "carrier": [{"step": "idle", "seconds": 10.0}],
    # two boards: this one sends BPSK data continuously (25 Mbaud), or checks the other's (MONDAY.md 5)
    "send": [{"step": "data_tx", "seconds": 30.0, "period": 4}],
    "check": [{"step": "data_rx", "seconds": 30.0, "period": 4}],
    # where each window comparator's input sits for every state of A3, then A2 (the margins on this lock point)
    "levels": [{"step": "levels", "scheme": "A3"}, {"step": "idle", "seconds": 3.0}, {"step": "levels", "scheme": "A2"},
               {"step": "idle", "seconds": 3.0}],
    # A3 decided 8-48 samples (10-60 ns) after its first comparator fired: how many of each corner stay undecided while
    # the arms are still crossing (2026-11-01: one corner of four lost 10 % to 'undecided' at the usual 16)
    "a3delay": [{"step": "symbols", "scheme": "A3", "seconds": 4.0, "period": 2000, "width": 20, "delay": d}
                for d in (8, 12, 16, 20, 24, 32, 48)],
    # ID 11's settled decision: A3 within 30 ns and A1 within 20 ns, decided once the vector has held k samples (k = 0:
    # the fixed delay); a k shorter than the arms' skew decides a passing corner wrong, so the table's wrong ones count
    "settle": [{"step": "symbols", "scheme": "A3", "seconds": 4.0, "period": 2000, "width": 20, "delay": 24, "settle": k}
               for k in (0, 2, 4, 6, 8, 12, 16)] +
              [{"step": "symbols", "scheme": "A1", "seconds": 4.0, "period": 2000, "width": 20, "delay": 16, "settle": k}
               for k in (0, 2, 4, 8)],
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
        self.level = None                    # the carrier's I in the data step's last gap: {t, i} (dashboard.py)

    # ---- for the page ----
    def state(self, full=False):
        """for each look (small: the histograms stay out of the log) or, full, for /api/selftest (the last symbol run's
        latency histogram with its scheme and what the B210 did)"""
        res = [{k: v for k, v in r.items() if k != "lat_hist"} for r in list(self.results)[-3:]]
        out = {"on": self.on, "plan": self.plan_name, "now": dict(self.now), "results": res}
        if full:
            last = next((r for r in reversed(self.results) if r.get("lat_hist")), None)
            out["last_hist"] = {k: last.get(k) for k in ("scheme", "sent", "events", "right", "wrong", "undecided", "false", "missed",
                                                         "exact", "cm", "lat_ns", "lat_hist", "b210", "t1", "period", "width")} if last else None
        return out

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
        return self.state(full=True)

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
        # the B210's own announcements (they carry 'b210'); a test's note that only names the B210 counts only when no
        # announcement does (the same burst was listed twice, 23:24)
        ns = [n for n in list(d.notes) if n["t_start"] <= t1 and (n.get("t_end") or t1) >= t0]
        said = [n["text"] for n in ns if n.get("b210")] or [n["text"] for n in ns if n.get("text", "").startswith("B210")]
        said = list(dict.fromkeys(said))
        return "; ".join(said)[:300] if said else "quiet"

    def _say(self, step, text, **kw):
        self.now = dict({"step": step, "since": time.time(), "text": text}, **kw)

    # ---- the steps ----
    def idle(self, st):
        self._say("idle", "the carrier alone, %g s: the page reads its level" % st["seconds"], seconds=st["seconds"])
        L = getattr(self.server, "linkd", None)
        ok = self._watch(st["seconds"], L.counts["losses"] if L else 0)
        return {"step": "idle", "seconds": st["seconds"], "interrupted": not ok}

    def levels(self, st):
        """where each window comparator's input sits for each state of a scheme, the loop closed: the scheme's states
        sent at random, half the time (2.5 M a second, the idle between: over its four corners the loop's I x Q
        averages to nothing, so the lock stays), and each window's threshold swept across its arm with its
        comparator's duty read at each step.  The duty against the threshold is the arm's distribution summed from
        above: a step down at the idle's level (half the time) and at each state's (2.5-25 %), so the margins of every
        state against every threshold (2026-11-01: one A3 corner 5 % undecided on one lock point even 60 ns after the
        event).  (A first try held each state still with the loop held: the VCXO is not the TCXO, so the phase turned
        while it was held, and its readings were rotated.)  The sweep a few dozen steps at a time under the lock, so
        the page's looks go on; linkd's windows put back after"""
        name = st.get("scheme", "A3")
        tx = SCHEMES[name]
        L = getattr(self.server, "linkd", None)
        if L is None or not L.cen or not L.leg_windows:
            return {"step": "levels", "scheme": name, "error": "linkd has not set the windows up"}
        frac = float((L.cfg or {}).get("window_frac", 0.5))
        thr = {w: L.cen[w] + frac * L.leg_windows for w in L.cen}
        names = {"QP": "CMP_QP", "QN": "CMP_QN", "IP": "CMP_IP", "IN": "CMP_IN"}
        span, step_v = float(st.get("span_v", 0.30)), float(st.get("step_v", 0.004))
        L_ = getattr(self.server, "linkd", None)
        losses0 = L_.counts["losses"] if L_ else 0

        def start(cl):
            side = self._side(cl)
            cl.rx_enable(False)
            cl.tx_points(tx.tx_idle(), [point_code(i, q) for i, q in tx.msgs])
            cl.events(period=40, width=20, count=0, n=tx.n, source="prbs" if tx.n > 1 else "count")
            cl.tx_go()
            self._busy = True
            return side

        def sweep(cl, w, vs):
            out = []
            for v in vs:
                cl.threshold(w, v)
                out.append([round(v, 4), round(cl.gate(seconds=0.002, inputs=(names[w],))[names[w]]["duty"], 4)])
            cl.threshold(w, thr[w])
            return out

        def finish(cl):
            for w, v in thr.items():
                cl.threshold(w, v)
            cl.tx_stop()
            cl.hold_point(1, 0)
            self._busy = False

        side = self._do(start)
        self._say("levels", "the states of %s sent at random half the time, each window's threshold swept: where every state "
                  "sits against every threshold" % name, scheme=name)
        res = {"step": "levels", "scheme": name, "side": side, "leg_v": round(L.leg_windows, 4),
               "thresholds_v": {w: round(v, 4) for w, v in thr.items()}, "centres_v": {w: round(v, 4) for w, v in L.cen.items()},
               "sweeps": {}}
        ok = True
        try:
            for w in ("QP", "QN", "IP", "IN"):
                n = int(round(2 * span / step_v)) + 1
                vs = [L.cen[w] - span + k * step_v for k in range(n)]
                pts = []
                for k in range(0, n, 25):
                    if self._aborted or (L_ is not None and L_.counts["losses"] != losses0):
                        ok = False
                        break
                    pts += self._do(lambda cl: sweep(cl, w, vs[k:k + 25]))
                res["sweeps"][w] = pts
                if not ok:
                    break
        finally:
            self._do(finish)
        res["interrupted"] = not ok
        return res

    def symbols(self, st):
        name = st.get("scheme") or SCHEME_ROTA[self._k["scheme"] % len(SCHEME_ROTA)]
        self._k["scheme"] += 1
        period, width, seconds = int(st["period"]), int(st["width"]), float(st["seconds"])
        delay = int(st.get("delay", 16))                     # samples from the first comparator to fire to the decision
        settle = int(st.get("settle", 0))                    # ID 11: decided once settled this many samples, delay at most
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
            cl.rx_config(rx_s.idle_vector(), rx_s.mask, rx_s.lut(False), rx_s.slow_exp(), delay=delay, settle=settle,
                         quiet=4, confirm=10,
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
            # the engine stopped first: running, it goes on counting (a CW's false events, 2 M/s) between the counters'
            # reads, and 'events' and 'false' no longer belonged together (602 references unaccounted in a run)
            cl.rx_enable(False)
            s = cl.rx_stats()
            cm = cl.confusion()
            # the latency's spread, not only its mean: the histogram's bins (one sample each) up to the slowest
            # decision, kept as [ns, count] where counted (the page's 'latency, the last run's spread')
            hist = None
            if s.get("lat_n"):
                n_b = min(1024, int(s["lat_max"]) + 2)
                h = cl.histogram(n_b)
                hist = [[round(k * t_sample * 1e9, 2), c] for k, c in enumerate(h) if c]
            cl.tx_stop()
            cl.hold_point(1, 0)
            self._busy = False
            n = tx.n
            # each symbol sent (a reference) is right, wrong, undecided (the receiver fired, its vector no message's)
            # or missed; every event is one of the first three or false.  The whole matrix: a decision outside the
            # scheme's own messages is wrong too.  From ID 10 these add up exactly ('exact'); before, a false event's
            # decision went into right or wrong (against the last message sent) and 'undecided' was not counted
            return {"sent": s.get("refs"), "events": s.get("events"), "decided": s.get("decided"),
                    "right": sum(cm[a][a] for a in range(8)),
                    "wrong": sum(cm[a][b] for a in range(8) for b in range(8) if a != b), "undecided": s.get("undec"),
                    "false": s.get("false"), "missed": s.get("missed"), "exact": bool(getattr(cl, "rx_exact", False)),
                    "cm": [row[:n] for row in cm[:n]],                # [sent][decided], the scheme's own states
                    "lat_ns": [s[k] * t_sample * 1e9 if s.get(k) is not None else None
                               for k in ("lat_min", "lat_mean", "lat_max")] if s.get("lat_n") else None,
                    "lat_hist": hist}
        res = self._do(finish) if not self._aborted else {}
        return dict({"step": "symbols", "scheme": name, "period": period, "width": width, "count": count, "side": side,
                     "delay": delay, "settle": settle, "interrupted": not ok}, **res)

    def data(self, st):
        ps = st.get("periods") or [st.get("period", 4)]
        period = int(ps[self._k["period"] % len(ps)])
        self._k["period"] += 1
        seconds = float(st["seconds"])
        # every gap_every seconds a moment of the carrier alone, its level read: the slow I arm reads the level only
        # off an idle carrier, so without the gaps the page has no signal strength while data runs
        gap_every = float(st.get("gap_every") or 0.0)
        L = getattr(self.server, "linkd", None)
        losses0 = L.counts["losses"] if L else 0
        side = None

        def start(cl):
            sd = side if side is not None else self._side(cl)
            cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
            cl.tx_timing(period=period)
            cl.tx_prbs(15)
            cl.tx_mode("prbs", n=2)
            cl.tx_go()
            self._busy = True
            time.sleep(0.005)
            cl.ber_config(15, None, invert=sd > 0, enable=True, cdr=True, period=period)
            return sd, cl.t_clk

        def stop(cl):
            cl.ber_config(15, None, invert=side > 0, enable=False, cdr=True, period=period)
            r = cl.ber()
            c = cl.cdr_state()
            cl.tx_stop()
            cl.hold_point(1, 0)
            self._busy = False
            return r, c

        def level(cl):
            time.sleep(0.03)                                   # the arm settled on the idle carrier
            return sum(cl.adc("I") for _ in range(3)) / 3.0
        side, t_clk = self._do(start)
        mbaud = 1e-6 / (period * t_clk)
        self._say("data", "BPSK PRBS15 data at %.3g Mbaud, the bits checked with the timing recovered, %g s%s" % (
            mbaud, seconds, ", the carrier's level read each second" if gap_every else ""), period=period, mbaud=mbaud,
            seconds=seconds)
        bits, errors, skew, ok = 0, 0.0, None, True
        t_end = time.time() + seconds
        while True:
            ok = self._watch(min(gap_every, t_end - time.time()) if gap_every else seconds, losses0)
            if self._aborted:
                break
            r, c = self._do(stop)
            bits += r.get("bits") or 0
            errors += (r.get("mismatches") or 0) / 3.0
            skew = c.get("skew_samples", skew)
            if not ok or time.time() > t_end - 0.2:
                break
            v = self._do(level)
            self.level = {"t": time.time(), "i": v}
            self._do(start)
        return {"step": "data", "period": period, "mbaud": mbaud, "seconds": seconds, "side": side, "interrupted": not ok,
                "bits": bits, "errors": errors, "ber": (errors / bits) if bits else None, "skew_samples": skew}

    # ---- two boards (MONDAY.md 5): one sends, the other checks ----
    def data_tx(self, st):
        """BPSK PRBS15 sent continuously for another board to check (plan 'send'): no check here, no gaps"""
        period, seconds = int(st.get("period", 4)), float(st["seconds"])
        L = getattr(self.server, "linkd", None)
        losses0 = L.counts["losses"] if L else 0

        def start(cl):
            cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])
            cl.tx_timing(period=period)
            cl.tx_prbs(15)
            cl.tx_mode("prbs", n=2)
            cl.tx_go()
            self._busy = True
            return cl.t_clk

        def stop(cl):
            cl.tx_stop()
            cl.hold_point(1, 0)
            self._busy = False
        t_clk = self._do(start)
        mbaud = 1e-6 / (period * t_clk)
        self._say("data", "BPSK PRBS15 data at %.3g Mbaud sent for the other board to check, %g s" % (mbaud, seconds),
                  period=period, mbaud=mbaud, seconds=seconds)
        try:
            ok = self._watch(seconds, losses0)
        finally:
            self._do(stop)
        return {"step": "data_tx", "period": period, "mbaud": mbaud, "seconds": seconds, "interrupted": not ok}

    def data_rx(self, st):
        """the other board's BPSK PRBS15 checked (plan 'check'), the timing recovered from its own edges (ber_cdr.v):
        this board's TX the carrier alone.  The 180-degree ambiguity is the two boards' (which lock point each sits
        on), so the first 0.2 s picks the polarity: a check reading nearly every bit wrong is the other one"""
        period, seconds = int(st.get("period", 4)), float(st["seconds"])
        L = getattr(self.server, "linkd", None)
        losses0 = L.counts["losses"] if L else 0
        inv = {"v": False}

        def start(cl):
            cl.hold_point(1, 0)
            cl.ber_config(15, None, invert=inv["v"], enable=True, cdr=True, period=period)
            self._busy = True
            return cl.t_clk

        def read(cl):
            cl.ber_config(15, None, invert=inv["v"], enable=False, cdr=True, period=period)
            return cl.ber(), cl.cdr_state()

        def stop(cl):
            cl.ber_config(15, None, invert=inv["v"], enable=False, cdr=True, period=period)
            self._busy = False
        t_clk = self._do(start)
        time.sleep(0.2)
        r, _ = self._do(read)
        if r.get("bits") and (r.get("mismatches") or 0) / 3.0 > 0.4 * r["bits"]:
            inv["v"] = True
        mbaud = 1e-6 / (period * t_clk)
        self._say("data", "the other board's BPSK PRBS15 data at %.3g Mbaud checked, the timing recovered, %g s" % (
            mbaud, seconds), period=period, mbaud=mbaud, seconds=seconds)
        bits, errors, skew, ok = 0, 0.0, None, True
        t_end = time.time() + seconds
        try:
            while True:
                self._do(start)
                ok = self._watch(min(1.0, max(0.05, t_end - time.time())), losses0)
                r, c = self._do(read)
                bits += r.get("bits") or 0
                errors += (r.get("mismatches") or 0) / 3.0
                skew = c.get("skew_samples", skew)
                if not ok or self._aborted or time.time() > t_end - 0.05:
                    break
        finally:
            self._do(stop)
        return {"step": "data_rx", "period": period, "mbaud": mbaud, "seconds": seconds, "inverted": inv["v"],
                "interrupted": not ok, "bits": bits, "errors": errors, "ber": (errors / bits) if bits else None,
                "skew_samples": skew}

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
