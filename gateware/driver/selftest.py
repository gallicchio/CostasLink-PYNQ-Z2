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

from costaslink import SCHEMES, Scheme, point_code, CMP_I, CMP_QP, CMP_QN, CMP_IP, CMP_IN

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "selftest.json")

PLANS = {
    # a demonstration's round: the level, single symbols, data at a rate that changes each round (about 16 s); 2 Mbaud
    # among them for the bench scope, whose monitor taps smooth over about 0.1 us and close its eye above 5 Mbaud
    "cycle": [{"step": "idle", "seconds": 3.0},
              {"step": "symbols", "seconds": 4.0, "period": 2000, "width": 20},
              {"step": "qpsk", "seconds": 3.0},
              {"step": "data", "seconds": 8.0, "periods": [50, 10, 5, 4, 2], "gap_every": 1.0},
              {"step": "data", "mod": "ook", "seconds": 4.0, "periods": [50, 10, 4]}],
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
    "a3delay": [{"step": "symbols", "scheme": "A3", "seconds": 4.0, "period": 2000, "width": 20, "delay": d, "settle": 0}
                for d in (8, 12, 16, 20, 24, 32, 48)],
    # ID 11's settled decision: A3 within 30 ns and A1 within 20 ns, decided once the vector has held k samples (k = 0:
    # the fixed delay); a k shorter than the arms' skew decides a passing corner wrong, so the table's wrong ones count
    "settle": [{"step": "symbols", "scheme": "A3", "seconds": 4.0, "period": 2000, "width": 20, "delay": 24, "settle": k}
               for k in (0, 2, 4, 6, 8, 12, 16)] +
              [{"step": "symbols", "scheme": "A1", "seconds": 4.0, "period": 2000, "width": 20, "delay": 16, "settle": k}
               for k in (0, 2, 4, 8)],
    # the learning step before physics runs (Jason, 2026-11-01): the windows, then for each single-symbol scheme and the
    # QPSK rate the decision table and timing with the lowest latency that decides every symbol right, and the data's
    # timing recovery at each rate; kept in learned.json and used by every step after (once through, then the plan before)
    "learn": [{"step": "learn"}],
    # QPSK's latency tail (2026-11-01 23:05: on lock point - a decision or two in 7.5 M past 100 ns, to 256, with the
    # learned 'info' table within 24; on + almost never): each table at settle 6, within 24 and 32 samples
    "qpsktail": [{"step": "qpsk", "seconds": 3.0, "table": t, "settle": 6, "delay": d}
                 for t in ("all", "info", "learned") for d in (24, 32)],
    # the A/B under one interference (TODO, 2026-11-01): A3 and A1 settled (SETTLE's) or at the fixed delay, each with the
    # windows calibrated from the states' levels or by the plain rule (half the leg), in turn
    "ab": [{"step": "symbols", "scheme": name, "seconds": 4.0, "period": 2000, "width": 20, "settle": k, "delay": d,
            "windows": w}
           for name, fixed in (("A3", 24), ("A1", 16))
           for k, d in ((None, None), (0, fixed))
           for w in ("cal", "plain")],
}
SCHEME_ROTA = ("A3", "A1", "A2", "A1w")
# ID 11's settled decision by default (a step's "settle" not given): samples a vector must hold, and the longest wait.
# The plan 'settle' (2026-11-01, 01:10-01:20 PST, the B210 quiet): A1 62.4 ns at k = 2 against 76.2 fixed, all right; A3
# 66-67 ns at k = 4 against 80 fixed at 16 (90 at 24), no wrong decision and fewer undecided; A3 at k = 2 decided 0.8-1.3 %
# wrong (a corner passing through another's vector), so 4 for the corners; A1, A1w and A2 have no state between.
# With the windows calibrated from the states' levels (01:28 PST: a quarter of the leg out, not half) the passing vector
# lasts longer: A3 at k = 4 decided 2.1 % wrong, at 6 none wrong and none undecided at 63.1 ns (fixed at 24: 85.5 ns,
# none undecided where 2.9 % were before); A1 58.7 ns at 2.  So 6 for the corners
SETTLE = {"A1": (2, 16), "A1w": (2, 16), "A2": (2, 16), "A3": (6, 24)}
# the decision table's choices (a symbols step's "table"): "all" every comparator as the scheme's model says (the rule:
# a vector with a window the state should not light is undecided); "info" only the comparators that carry the scheme's
# bits, the others read as either (A1's flip with a CW's beat on Q still decided); "learned" the rule's table and every
# vector it leaves undecided that the board was seen to make for one state alone (the step 'learn')
INFO_USE = {"A1": (CMP_I,), "A1w": (CMP_IP,), "A2": (CMP_QP, CMP_QN), "A3": (CMP_I, CMP_QP, CMP_QN)}
LEARN_FILE = os.path.join(HERE, "learned.json")
LEVELS_FILE = os.path.join(HERE, "levels.json")   # the last sweep of the windows on each lock point (the page's panel)
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
        self.on, self.plan_name, self.calibrate_on = False, "cycle", True
        # where in each window's plateau its threshold goes, from the idle's side: 0.5 its middle (best against noise);
        # more, away from the idle (fewer false events from an interferer riding on it, less margin for the states).
        # 0.7 at the A/B of 2026-11-01 12:46 (BRINGUP_LOG 4.30): quiet, every slow A3 corner right as at 0.5; under a CW
        # 10 dB down 150 times fewer false events, A1 80-86 % right where 0.5 gave 69-74 %, A3's wrong 4-25 % not 37-48 %.
        # But the round's QPSK (the corners at 2.5 M a second) then lost 3e-5 undecided or missed, quiet (the corners on
        # the idle's side of I, whose Q the receiver reads short: 4.31): 0.6 since 13:24, 1.3e8 of them all right
        self.window_bias = 0.6
        try:
            with open(STATE_FILE) as f:
                d = json.load(f)
            self.on, self.plan_name = bool(d.get("on")), d.get("plan", "cycle")
            self.calibrate_on = bool(d.get("calibrate", True))
            self.window_bias = float(d.get("window_bias", 0.6))
        except (OSError, ValueError):
            pass
        self._cal_tried = 0.0
        self._bad_windows = False            # a quiet run lost over 1 %: calibrate again (the windows may be wrong)
        self.profile = None                  # the step 'learn''s choices (learned.json beside the server)
        self._after_learn = None
        try:
            with open(LEARN_FILE) as f:
                self.profile = json.load(f)
        except (OSError, ValueError):
            pass
        self.last_levels = None              # the last sweep of the windows' levels (the page's 'own constellation')
        self.levels_by_side = {}             # each lock point's, kept across a restart (one put back from windows.json
        try:                                 # takes none, and the panel stayed empty: 2026-11-01 22:04)
            with open(LEVELS_FILE) as f:
                self.levels_by_side = {int(k): v for k, v in (json.load(f).get("by_side") or {}).items()}
            self.last_levels = max(self.levels_by_side.values(), key=lambda v: v.get("t") or 0, default=None)
        except (OSError, ValueError, TypeError, AttributeError):
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
            side = getattr(getattr(self.server, "dashboard", None), "side", None)
            out["last_levels"] = self.levels_by_side.get(side) or self.last_levels
            out["last_hist"] = {k: last.get(k) for k in ("scheme", "sent", "events", "right", "wrong", "undecided", "false", "missed",
                                                         "exact", "cm", "lat_ns", "lat_hist", "b210", "t1", "period", "width")} if last else None
        return out

    def set(self, d):
        """POST /api/selftest: {"on": bool, "plan": name, "holdover": bool, "calibrate": bool, "window_bias": 0.5-0.9}"""
        if "holdover" in d:                              # from inside the server: linkd is not paused by it
            self._do(lambda cl: cl.shold(bool(d["holdover"])))
        if "plan" in d:
            if d["plan"] not in PLANS:
                raise ValueError("no plan %r (%s)" % (d["plan"], ", ".join(PLANS)))
            if d["plan"] == "learn" and self.plan_name != "learn":     # once through, then the plan before
                self._after_learn = self.plan_name
            self.plan_name = d["plan"]
        if "on" in d:
            self.on = bool(d["on"])
        if "calibrate" in d:                             # the windows from the states' levels (on by default)
            self.calibrate_on = bool(d["calibrate"])
        if "window_bias" in d:                           # calibrated again at the next step
            self.window_bias = min(0.9, max(0.1, float(d["window_bias"])))
            L = getattr(self.server, "linkd", None)
            if L is not None:
                L.cal = None
            self._cal_tried = 0.0
        try:
            with open(STATE_FILE, "w") as f:
                json.dump({"on": self.on, "plan": self.plan_name, "calibrate": self.calibrate_on,
                           "window_bias": self.window_bias}, f)
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

    def _restore_ook(self, cl):
        """the I window an OOK step moved, back where linkd keeps it"""
        w, self._ook_thr = getattr(self, "_ook_thr", None), None
        L = getattr(self.server, "linkd", None)
        if w and L is not None and L.cen:
            cl.threshold(w, min(2.499, max(0.0, L.thresholds()[w])))

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
            self._restore_ook(cl)
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

    def _during(self, t0, t1):
        """the other interventions announced during [t0, t1] (the carrier cut, the attenuator stepped, a deploy), in words,
        or None: a run they touched is not quiet though the B210 was (an OOK run's last 0.3 s inside a carrier cut, 3.9 %
        of its bits wrong, read 'the B210 quiet', 2026-11-02 02:27)"""
        d = getattr(self.server, "dashboard", None)
        if d is None:
            return None
        said = [n["text"] for n in list(d.notes) if n.get("kind") == "intervention" and not n.get("b210")
                and not n.get("text", "").startswith("B210") and n["t_start"] <= t1 and (d.note_end(n) or t1) >= t0]
        said = list(dict.fromkeys(said))
        return "; ".join(said)[:300] if said else None

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
        res = self._sweep_levels(name, float(st.get("span_v", 0.30)), float(st.get("step_v", 0.004)))
        res["step"] = "levels"
        if not res.get("error") and not res.get("interrupted"):
            self.last_levels = {"t": time.time(), "scheme": name, "side": res["side"], "leg_v": res["leg_v"],
                                "centres_v": res["centres_v"], "before_v": res["thresholds_v"], "after_v": None,
                                "sweeps": res["sweeps"], "b210": self._b210(time.time() - 10, time.time())}
            self._keep_levels()
        return res

    def qpsk(self, st):
        """QPSK data with the idle as its pilot: A3's corners at random half the time, 2.5 M a second (2 bits each: 5
        Mb/s), the receiver deciding every symbol against what was sent (the single symbols' engine at 40 clocks a
        symbol: it re-arms in about 24), so right / wrong / undecided / missed are the symbol errors.  The loop needs the
        idle between: over the four corners its I x Q averages to nothing (a QPSK loop is rev B's).  The scope's
        constellation is taken in it (the corners)"""
        res = self.symbols(dict(st, scheme="A3", period=int(st.get("period", 40)), width=int(st.get("width", 20)),
                                label="QPSK data (the idle as pilot), every symbol checked"))
        res["step"] = "qpsk"
        return res

    def pattern(self, st):
        """a scheme's states sent at random half the time, 2.5 M a second (40 clocks a symbol, 20 of them the state): the
        QPSK pattern for A3, so the bench scope's constellation shows the corners (single symbols are 1 % of the time,
        so a capture of them holds a few dozen samples off the idle; Jason, 2026-11-01).  Over A3's four corners the
        loop's I x Q averages to nothing and the idle between holds the lock"""
        name = st.get("scheme", "A3")
        tx = SCHEMES[name]
        seconds = float(st["seconds"])
        L = getattr(self.server, "linkd", None)
        losses0 = L.counts["losses"] if L else 0

        def start(cl):
            cl.rx_enable(False)
            cl.tx_points(tx.tx_idle(), [point_code(i, q) for i, q in tx.msgs])
            cl.events(period=40, width=20, count=0, n=tx.n, source="prbs" if tx.n > 1 else "count")
            cl.tx_go()
            self._busy = True

        def stop(cl):
            cl.tx_stop()
            cl.hold_point(1, 0)
            self._busy = False
        self._do(start)
        self._say("pattern", "the states of %s, %s, sent at random half the time, 2.5 M a second (for the scope's constellation)"
                  % (name, SCHEME_TEXT.get(name, "")), scheme=name, period=40, width=20, seconds=seconds)
        try:
            ok = self._watch(seconds, losses0)
        finally:
            self._do(stop)
        return {"step": "pattern", "scheme": name, "seconds": seconds, "interrupted": not ok}

    def _sweep_levels(self, name, span=0.30, step_v=0.004):
        tx = SCHEMES[name]
        L = getattr(self.server, "linkd", None)
        if L is None or not L.cen or not L.leg_windows:
            return {"scheme": name, "error": "linkd has not set the windows up"}
        thr = L.thresholds()
        names = {"QP": "CMP_QP", "QN": "CMP_QN", "IP": "CMP_IP", "IN": "CMP_IN"}
        losses0 = L.counts["losses"]

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
        res = {"scheme": name, "side": side, "leg_v": round(L.leg_windows, 4),
               "thresholds_v": {w: round(v, 4) for w, v in thr.items()}, "centres_v": {w: round(v, 4) for w, v in L.cen.items()},
               "sweeps": {}}
        ok = True
        try:
            for w in ("QP", "QN", "IP", "IN"):
                n = int(round(2 * span / step_v)) + 1
                vs = [L.cen[w] - span + k * step_v for k in range(n)]
                pts = []
                for k in range(0, n, 25):
                    if self._aborted or L.counts["losses"] != losses0:
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

    def calibrate(self, st=None):
        """the windows from the states' own levels (2026-11-01: on one lock point an A3 corner sat 2 mV past its window
        and the Q states 12 mV, the rule 'half the I leg from each comparator's centre' assuming a square constellation
        the TX does not make: its Q excursion about 0.6 of its I, one I-flipping corner 85 mV where the other is 150).
        A3's corners and A1's flip swept (`_sweep_levels`); for each window, the share of time its comparator should be
        high (the receiver's own model of each state, this lock point's frame) marks the plateau of the duty between the
        states that should read low and those that should read high, and the threshold goes in its middle, at least a
        quarter of the leg out from the centre (with no carrier the windows stay dark: the lock monitor's 'no carrier').
        linkd keeps them, scaled down with a weaker carrier; done again on the other lock point or a level 15 % away"""
        L = getattr(self.server, "linkd", None)
        if L is None or not L.cen or not L.leg_windows:
            return {"step": "calibrate", "error": "linkd has not set the windows up"}
        before = {w: round(v, 4) for w, v in L.thresholds().items()}
        # not while an intervention is announced, and only if the carrier's level is the one linkd keeps the windows
        # for, before and after the sweeps: one taken while the attenuator was 4.75 dB down set the Q windows for the
        # stronger carrier (QP 107, QN 119 mV out for a 159 mV one) and left A2, A3 and QPSK 60 % missed after (13:41)
        dash = getattr(self.server, "dashboard", None)

        def level(cl):
            time.sleep(0.02)
            return abs(sum(cl.adc("I") for _ in range(3)) / 3.0 - L.i0)

        def off_level():
            lv = self._do(level)
            return lv if abs(lv - L.leg_windows) > 0.12 * L.leg_windows else None

        if dash is not None and dash.active_note(time.time()):
            return {"step": "calibrate", "skipped": "an intervention is announced"}
        lv0 = off_level()
        if lv0 is not None:
            return {"step": "calibrate", "skipped": "the carrier's I leg %.0f mV, the windows' %.0f mV" % (lv0 * 1e3, L.leg_windows * 1e3)}
        sw = {name: self._sweep_levels(name) for name in ("A3", "A1")}
        if any(r.get("interrupted") or r.get("error") for r in sw.values()):
            return {"step": "calibrate", "interrupted": True, "before_v": before}
        lv1 = off_level()
        if lv1 is not None or (dash is not None and dash.active_note(time.time(), grace_s=0.0)):
            return {"step": "calibrate", "skipped": "the level moved or an intervention began during the sweep",
                    "before_v": before}
        side, leg = sw["A3"]["side"], L.leg_windows
        k_of = {"QP": 1, "QN": 2, "IP": 3, "IN": 4}
        new, plateaus = {}, {}
        b = self.window_bias
        for w in ("QP", "QN", "IP", "IN"):
            lo, hi = -1e9, 1e9
            tx3 = SCHEMES["A3"]
            idle_high = _Frame(tx3, side).fast(_Frame(tx3, side).rx_point(tx3.idle))[k_of[w]]
            for name, r in sw.items():
                tx = SCHEMES[name]
                fr = _Frame(tx, side)
                hs = [fr.fast(fr.rx_point(tx.idle))[k_of[w]]] + [fr.fast(fr.rx_point(m))[k_of[w]] for m in tx.msgs]
                if None in hs:
                    continue
                share = 0.5 * hs[0] + 0.5 * sum(hs[1:]) / float(len(hs) - 1)
                pts = r["sweeps"].get(w) or []
                best, run = None, []
                for v, d in pts + [[None, None]]:
                    if v is not None and abs(d - share) < 0.04:
                        run.append(v)
                        continue
                    if len(run) >= 3 and (best is None or run[-1] - run[0] > best[1] - best[0]):
                        best = (run[0], run[-1])
                    run = []
                if best is None:
                    lo, hi = None, None
                    break
                plateaus["%s %s" % (name, w)] = [round(best[0], 4), round(best[1], 4), round(share, 3)]
                lo, hi = max(lo, best[0]), min(hi, best[1])
            if lo is None or hi - lo < 0.010:
                continue
            # b of the way across the plateau from the idle's side: up from its bottom where the idle reads low, down
            # from its top where the idle reads high (b = 0.5: the middle either way)
            at = lo + b * (hi - lo) if not idle_high else hi - b * (hi - lo)
            new[w] = max(at, L.cen[w] + 0.25 * leg)
        res = {"step": "calibrate", "side": side, "leg_v": round(leg, 4), "before_v": before, "plateaus_v": plateaus,
               "after_v": {w: round(v, 4) for w, v in new.items()}, "window_bias": b}
        frac = float((L.cfg or {}).get("window_frac", 0.5))
        plain = {w: round(L.cen[w] + frac * leg, 4) for w in L.cen}      # the page's dashed lines: the plain rule's
        self.last_levels = {"t": time.time(), "scheme": "A3", "side": side, "leg_v": round(leg, 4),
                            "centres_v": sw["A3"]["centres_v"], "before_v": plain, "after_v": res["after_v"],
                            "sweeps": sw["A3"]["sweeps"], "b210": self._b210(time.time() - 10, time.time())}
        self._keep_levels()
        if len(new) == 4:
            self._do(lambda cl: L.set_windows(cl, new, side))
            self._bad_windows = False
        else:
            res["error"] = "no plateau for %s: the windows left as they were" % ", ".join(w for w in k_of if w not in new)
        return res

    def _keep_levels(self):
        """the last sweep kept for its lock point, beside the server"""
        lv = self.last_levels
        if not lv or lv.get("side") not in (1, -1):
            return
        self.levels_by_side[lv["side"]] = lv
        try:
            with open(LEVELS_FILE + ".tmp", "w") as f:
                json.dump({"by_side": {str(k): v for k, v in self.levels_by_side.items()}}, f)
            os.replace(LEVELS_FILE + ".tmp", LEVELS_FILE)
        except (OSError, TypeError, ValueError):
            pass

    def _need_calibration(self):
        """the windows calibrated on this lock point and near this level (and not tried within the last minute)"""
        L = getattr(self.server, "linkd", None)
        if L is None or not L.cen or not L.leg_windows or not self.calibrate_on:
            return False
        if time.time() - self._cal_tried < 60.0:
            return False
        side = self._do(self._side)
        return (L.cal is None or L.cal["side"] != side or self._bad_windows or
                abs((L.leg or L.leg_windows) - L.cal["leg"]) > 0.15 * L.cal["leg"])

    # ---- the decision tables and the learned profile ----
    def _rx_scheme(self, name, side, use=None):
        """scheme `name` as this lock point receives it (the frame's points), its comparators used `use` (all by default)"""
        tx = SCHEMES[name]
        rx = _Frame(tx, side)
        rx_s = Scheme(name, tx.text, rx.rx_point(tx.idle), [rx.rx_point(m) for m in tx.msgs], [], t=tx.t, t2=tx.t2)
        rx_s.mask, rx_s.use = tx.mask, tx.use if use is None else sum(1 << b for b in use)
        return rx_s

    def _table(self, name, side, table):
        """the 32-entry decision table: 'all' (the rule), 'info', 'learned', or a list given"""
        if isinstance(table, list):
            return table
        if table == "info":
            return self._rx_scheme(name, side, INFO_USE[name]).lut(False)
        rule = self._rx_scheme(name, side).lut(False)
        if table == "learned":
            lt = ((self.profile or {}).get("learned_tables") or {}).get("%s %d" % (name, side))
            return lt if lt else rule
        return rule

    def _profile_entry(self, kind, name, side):
        """the profile's choice for `kind` ('symbols' or 'qpsk') and scheme `name` on lock point `side`, if learned there
        near this level (each lock point keeps its own: learning on one leaves the other's)"""
        p = ((self.profile or {}).get("by_side") or {}).get(str(side))
        if p is None and (self.profile or {}).get("side") == side:
            p = self.profile
        L = getattr(self.server, "linkd", None)
        if not p or L is None or not (L.leg or L.leg_windows):
            return None
        e = (p.get(kind) or {}).get(name)
        if not e or not p.get("leg") or abs((L.leg or L.leg_windows) - p["leg"]) > 0.15 * p["leg"]:
            return None
        return dict(e, side=p.get("side"))

    class _Moved(Exception):
        """the loop changed lock point during the learning (a recovery): its tables and choices belong to the other"""

    def _quiet_run(self, st, tries=3, side=None):
        """one measuring run, again if the world disturbed it (an announced intervention, the B210 on, interrupted);
        on lock point `side` only (another: _Moved, the learning given up)"""
        dash = getattr(self.server, "dashboard", None)
        r = None
        for _ in range(tries):
            t_wait = time.time() + 180            # an intervention over and the link locked with linkd standing by
            while ((dash is not None and dash.active_note(time.time())) or not self._free()) and time.time() < t_wait and self.on:
                time.sleep(1.0)
            if not self.on:
                return None
            self._aborted = False                 # a run linkd aborted (a loss) is tried again, not the end of learning
            r = self.symbols(dict(st, profile=False)) if st["step"] == "symbols" else self.data(dict(st, profile=False))
            if side is not None and r.get("side") is not None and r["side"] != side:
                raise SelfTest._Moved()
            t1 = time.time()
            if (not r.get("interrupted") and r.get("b210", "quiet") == "quiet"
                    and self._b210(t1 - 10, t1) == "quiet" and not (dash and dash.active_note(t1))):
                return r
            time.sleep(2.0)
        return None

    @staticmethod
    def _verdict(r, lost_max=1e-5):
        """a run's standing: every sent symbol right but at most lost_max undecided or missed, no wrong; then the mean
        latency and the 99.9 % one (lower first)"""
        sent = r.get("sent") or 1
        bad, lost = r.get("wrong") or 0, (r.get("undecided") or 0) + (r.get("missed") or 0)
        ok = bad == 0 and lost <= max(1, lost_max * sent)
        lat = (r.get("lat_ns") or [None, 1e9, None])[1] or 1e9
        return (0 if ok else 1, 0 if ok else (10 * bad + lost) / sent, lat, r.get("lat_p999") or 1e9)

    def _learn_table(self, name, side, seconds=2.0, delay=32):
        """the vectors at the decision for each state sent: 7 vectors a pass, each its own label in the matrix, at a
        fixed delay (so the vector seen does not depend on the table); the rule's table and every vector it leaves
        undecided that one state made 90 % of the time, at least 10 times"""
        tx = SCHEMES[name]
        rx_s = self._rx_scheme(name, side)
        iv, rule = rx_s.idle_vector(), rx_s.lut(False)
        vecs = [v for v in range(32) if v != iv]
        counts = [[0] * 32 for _ in range(tx.n)]
        for k0 in range(0, len(vecs), 7):
            group = vecs[k0:k0 + 7]
            probe = [0] * 32
            for lab, v in enumerate(group):
                probe[v] = 0x8 | lab
            r = self._quiet_run({"step": "symbols", "scheme": name, "seconds": seconds, "period": 2000, "width": 20,
                                 "settle": 0, "delay": delay, "table": probe, "full_cm": True}, side=side)
            if r is None or not r.get("cm8"):
                return None, None
            for m in range(tx.n):
                for lab, v in enumerate(group):
                    counts[m][v] += r["cm8"][m][lab]
        learned = list(rule)
        added = {}
        for v in vecs:
            if rule[v] & 0x8:
                continue
            col = [counts[m][v] for m in range(tx.n)]
            tot = sum(col)
            if tot >= 10 and max(col) >= 0.9 * tot:
                learned[v] = 0x8 | col.index(max(col))
                added[v] = col
        return learned, {"counts": counts, "added": {str(v): c for v, c in added.items()}}

    def learn(self, st):
        """the learning step (plan 'learn'): the windows calibrated if they need it; for A1, A1w, A2 and A3 one at a time,
        every 20 us, the decision table learned, then each table ('all', 'info', 'learned') at each decision timing (a
        fixed delay of 8-32 samples, or settled on 2-8 held samples within 40 ns), the choice the lowest mean latency
        that decides every symbol right (no wrong, at most 1e-5 undecided or missed; the 99.9 % latency breaks ties),
        run again 10 s to confirm; A3 at the QPSK rate likewise; BPSK and OOK data at each rate and the timing
        recovery's gain, the lowest-error gain kept.  Kept in learned.json, used by every step after"""
        L = getattr(self.server, "linkd", None)
        if L is None or not L.cen or not L.leg_windows:
            return {"step": "learn", "error": "linkd has not set the link up"}
        t_start = time.time()
        if self._need_calibration():
            self.calibrate()
        side = self._do(self._side)
        prof = {"t": time.time(), "side": side, "leg": L.leg or L.leg_windows, "window_bias": self.window_bias,
                "thresholds_v": {w: round(v, 4) for w, v in L.thresholds().items()}, "symbols": {}, "qpsk": {},
                "data": {}, "learned_tables": {}, "learning": {}}
        timings = [(0, d) for d in (8, 12, 16, 20, 24, 32)] + [(k, 32) for k in (2, 3, 4, 6, 8)]

        def choose(name, kind, period, seconds, tables, timings_):
            tried = []
            for tbl in tables:
                for k, d in timings_:
                    self._say("learn", "learning %s%s: table '%s', %s" % (
                        name, " at the QPSK rate" if kind == "qpsk" else "", tbl,
                        "decided once held %d samples (within %d)" % (k, d) if k else "decided %d samples after it starts" % d),
                        scheme=name, step_kind=kind)
                    r = self._quiet_run({"step": "symbols", "scheme": name, "seconds": seconds, "period": period,
                                         "width": 20, "settle": k, "delay": d, "table": tbl,
                                         "label": "QPSK (learning)" if kind == "qpsk" else None}, side=side)
                    if r is None:
                        continue
                    tried.append({"table": tbl, "settle": k, "delay": d, "sent": r.get("sent"), "right": r.get("right"),
                                  "wrong": r.get("wrong"), "undecided": r.get("undecided"), "missed": r.get("missed"),
                                  "false": r.get("false"), "lat_ns": r.get("lat_ns"), "lat_p999": r.get("lat_p999"),
                                  "rx": r.get("rx")})
            if not tried:
                return None
            best = min(tried, key=self._verdict)
            # confirmed on a longer run
            r = self._quiet_run({"step": "symbols", "scheme": name, "seconds": 10.0 if kind == "symbols" else 3.0,
                                 "period": period, "width": 20, "settle": best["settle"], "delay": best["delay"],
                                 "table": best["table"], "label": "QPSK (learning)" if kind == "qpsk" else None}, side=side)
            conf = None if r is None else {k_: r.get(k_) for k_ in ("sent", "right", "wrong", "undecided", "missed", "false",
                                                                   "lat_ns", "lat_p999")}
            rx = best["rx"] or {}
            return {"table": best["table"], "settle": best["settle"], "delay": best["delay"], "lut": rx.get("lut"),
                    "lat_ns": best["lat_ns"], "lat_p999": best["lat_p999"], "confirmed": conf,
                    "ok": self._verdict(conf or best)[0] == 0,
                    "rx_config": {"idle": rx.get("idle"), "mask": rx.get("mask"), "lut": rx.get("lut"),
                                  "slow_exp": rx.get("slow_exp"), "delay": best["delay"], "settle": best["settle"],
                                  "quiet": 4, "confirm": 10, "window": rx.get("window")},
                    "tried": [{k_: v for k_, v in t.items() if k_ != "rx"} for t in tried]}

        moved = False
        try:
            self._learn_body(st, prof, side, choose, timings)
        except SelfTest._Moved:
            moved = True
        prof["seconds"] = round(time.time() - t_start, 1)
        prof["complete"] = bool(self.on and not moved and len(prof["symbols"]) == len(st.get("schemes") or ("A1", "A1w", "A2", "A3")))
        return self._learn_end(st, prof, side, moved)

    def _learn_body(self, st, prof, side, choose, timings):
        for name in st.get("schemes") or ("A1", "A1w", "A2", "A3"):
            self._say("learn", "learning %s's decision table: the vectors each state makes" % name, scheme=name)
            lt, info = self._learn_table(name, side)
            if lt is not None:
                prof["learned_tables"]["%s %d" % (name, side)] = lt
                prof["learning"][name] = info
            self.profile = dict(self.profile or {}, learned_tables=dict((self.profile or {}).get("learned_tables") or {},
                                                                       **prof["learned_tables"]))
            tables = ["all", "info"] + (["learned"] if lt is not None and lt != self._table(name, side, "all") else [])
            e = choose(name, "symbols", 2000, 2.0, tables, timings)
            if e is not None:
                prof["symbols"][name] = e
            if not self.on:
                break
        if self.on:
            lt3 = prof["learned_tables"].get("A3 %d" % side)
            tables = ["all", "info"] + (["learned"] if lt3 and lt3 != self._table("A3", side, "all") else [])
            e = choose("A3", "qpsk", 40, 1.5, tables, [(0, 16), (0, 24), (4, 24), (6, 24), (6, 32), (8, 32)])
            if e is not None:
                prof["qpsk"]["A3"] = e
        for mod, periods in (("bpsk", (50, 10, 5, 4, 2)), ("ook", (50, 10, 4))):
            if not self.on:
                break
            rows = {}
            for p in periods:
                for g in (4, 6):
                    self._say("learn", "learning the %s data's timing recovery at %.3g Mbaud, gain %d" % (
                        mod.upper(), 100.0 / p, g), mod=mod)
                    r = self._quiet_run({"step": "data", "mod": mod, "period": p, "seconds": 2.0, "gain": g}, side=side)
                    if r is not None:
                        rows.setdefault(str(p), {})[str(g)] = {"bits": r.get("bits"), "errors": r.get("errors"),
                                                               "skew_samples": r.get("skew_samples")}
            best = {}
            for p, gs in rows.items():
                g_best = min(gs, key=lambda g: ((gs[g]["errors"] or 0) / max(1, gs[g]["bits"] or 1), int(g)))
                best[p] = int(g_best)
            clean = [100.0 / int(p) for p, gs in rows.items() if gs.get(str(best[p]), {}).get("errors") == 0]
            prof["data"][mod] = {"runs": rows, "gain": best, "max_clean_mbaud": max(clean) if clean else None}

    def _learn_end(self, st, prof, side, moved):
        if prof["complete"]:
            # kept per lock point: the other point's choices (learned when the loop sat there) stay
            by_side = dict((self.profile or {}).get("by_side") or {})
            if self.profile and self.profile.get("side") is not None and str(self.profile["side"]) not in by_side:
                by_side[str(self.profile["side"])] = {k: v for k, v in self.profile.items() if k != "by_side"}
            by_side[str(side)] = dict(prof)
            prof["learned_tables"] = dict(((self.profile or {}).get("learned_tables") or {}), **prof["learned_tables"])
            prof["by_side"] = by_side
            self.profile = prof
            try:
                with open(LEARN_FILE, "w") as f:
                    json.dump(prof, f, indent=1)
            except OSError:
                pass
        if self._after_learn or self.plan_name == "learn":   # once through: back to the plan before (or the rounds, if
            # the plan before was lost with a restart: selftest.json keeps 'learn', and it learned again and again)
            self.plan_name, self._after_learn = self._after_learn or "cycle", None
            try:
                with open(STATE_FILE, "w") as f:
                    json.dump({"on": self.on, "plan": self.plan_name, "calibrate": self.calibrate_on,
                               "window_bias": self.window_bias}, f)
            except OSError:
                pass
        summ = {n: {k: e.get(k) for k in ("table", "settle", "delay", "lat_ns", "lat_p999", "ok")}
                for n, e in prof["symbols"].items()}
        return {"step": "learn", "complete": prof["complete"], "seconds": prof["seconds"], "side": side,
                "moved": moved,
                "symbols": summ, "qpsk": {n: {k: e.get(k) for k in ("table", "settle", "delay", "lat_ns", "ok")}
                                          for n, e in prof["qpsk"].items()},
                "data": {m: {"gain": d["gain"], "max_clean_mbaud": d["max_clean_mbaud"]} for m, d in prof["data"].items()}}

    def symbols(self, st):
        # the rota turns only for a step that names no scheme: the QPSK step (A3, named) turned it too, so the round's
        # symbols step took every other one, A3 and A2 only, A1 and A1w never (2026-11-01 12:04)
        name = st.get("scheme")
        if not name:
            name = SCHEME_ROTA[self._k["scheme"] % len(SCHEME_ROTA)]
            self._k["scheme"] += 1
        period, width, seconds = int(st["period"]), int(st["width"]), float(st["seconds"])
        # settle: ID 11's settled decision, k samples held (SETTLE's by default where the overlay has it); delay the
        # samples from the first comparator to fire to the decision, with settle the longest wait
        settle = st.get("settle")
        delay = st.get("delay")
        table = st.get("table")
        tx = SCHEMES[name]
        L = getattr(self.server, "linkd", None)
        losses0 = L.counts["losses"] if L else 0
        kind = "qpsk" if st.get("label") else "symbols"
        # the learned profile (the step 'learn') when the step asks for nothing of its own and it was learned on this
        # lock point near this level
        prof = None
        use_profile = st.get("profile", True) and settle is None and delay is None and table is None
        # "windows": "plain" (the A/B): the plain rule's windows for this run alone, the calibration kept and put back
        plain = st.get("windows") == "plain" and L is not None and L.cal is not None and bool(L.cen)
        cal_kept = L.cal if plain else None

        lut_used = {}

        def start(cl):
            nonlocal settle, delay, table, prof
            # the carrier alone, before the symbols: its level, for the page while they run (they move I with CMP_I
            # quiet, so it reads none from its own looks then: a 13 s attenuator step went unmeasured, soak15 #150)
            time.sleep(0.03)
            self.level = {"t": time.time(), "i": sum(cl.adc("I") for _ in range(3)) / 3.0}
            side = self._side(cl)
            if use_profile:
                prof = self._profile_entry(kind, name, side)
            if prof is not None:
                settle, delay, table = prof["settle"], prof["delay"], prof["lut"]
            if settle is None:
                settle = SETTLE[name][0] if getattr(cl, "rx_settle", False) else 0
            settle = int(settle)
            if plain:
                L.cal = None
                for w, v in L.thresholds().items():
                    cl.threshold(w, min(2.499, max(0.0, v)))
            if delay is None:
                delay = SETTLE[name][1] if settle else 16
            delay = int(delay)
            count = max(10, int(seconds / (period * cl.t_clk)))
            rx_s = self._rx_scheme(name, side)
            lut = self._table(name, side, table)
            lut_used.update(lut=lut, idle=rx_s.idle_vector(), mask=rx_s.mask, slow_exp=rx_s.slow_exp(),
                            window=max(4, min(100, period - 6)))
            cl.tx_points(tx.tx_idle(), [point_code(i, q) for i, q in tx.msgs])
            cl.rx_config(rx_s.idle_vector(), rx_s.mask, lut, rx_s.slow_exp(), delay=delay, settle=settle,
                         quiet=4, confirm=10,
                         window=max(4, min(100, period - 6)), first_edge=False)     # the window inside the period
            cl.hist_config("ref_to_decision", 0)
            cl.events(period=period, width=width, count=count, n=tx.n, source="prbs" if tx.n > 1 else "count")
            cl.rx_clear()
            cl.tx_go()
            self._busy = True
            return count, side, cl.t_clk, cl.t_sample
        count, side, t_clk, t_sample = self._do(start)
        lab = st.get("label")                                 # the QPSK step's run of the same engine
        self._say("qpsk" if lab else "symbols", (lab + " (%s, %s): one every %.3g us, %d clocks of it the state, %d of them, %s" if lab else
                  "single symbols of %s, %s: one every %.3g us, %d clocks long, %d of them, %s") % (
            name, SCHEME_TEXT[name], period * t_clk * 1e6, width, count,
            ("each decided once its pattern has held %.3g ns (at most %.3g ns after it starts)" % (
                settle * t_sample * 1e9, delay * t_sample * 1e9)) if settle else
            "each decided %.3g ns after it starts" % (delay * t_sample * 1e9)),
            scheme=name, period=period, width=width, count=count, seconds=seconds, settle=settle, delay=delay)
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
            if plain:
                L.cal = cal_kept
                for w, v in L.thresholds().items():
                    cl.threshold(w, min(2.499, max(0.0, v)))
            self._busy = False
            n = tx.n
            # each symbol sent (a reference) is right, wrong, undecided (the receiver fired, its vector no message's)
            # or missed; every event is one of the first three or false.  The whole matrix: a decision outside the
            # scheme's own messages is wrong too.  From ID 10 these add up exactly ('exact'); before, a false event's
            # decision went into right or wrong (against the last message sent) and 'undecided' was not counted
            p999 = None
            if hist:                                      # the latency 99.9 % of the right decisions stay under
                tot, acc = sum(c for _, c in hist), 0
                for ns, c in hist:
                    acc += c
                    if acc >= 0.999 * tot:
                        p999 = ns
                        break
            return {"sent": s.get("refs"), "events": s.get("events"), "decided": s.get("decided"), "lat_p999": p999,
                    "cm8": cm if st.get("full_cm") else None,
                    "right": sum(cm[a][a] for a in range(8)),
                    "wrong": sum(cm[a][b] for a in range(8) for b in range(8) if a != b), "undecided": s.get("undec"),
                    "false": s.get("false"), "missed": s.get("missed"), "exact": bool(getattr(cl, "rx_exact", False)),
                    "cm": [row[:n] for row in cm[:n]],                # [sent][decided], the scheme's own states
                    "lat_ns": [s[k] * t_sample * 1e9 if s.get(k) is not None else None
                               for k in ("lat_min", "lat_mean", "lat_max")] if s.get("lat_n") else None,
                    "lat_hist": hist}
        # aborted (linkd recovering): the windows left plain with cal cleared, as linkd's own setup leaves them; the
        # self-test calibrates again when it next finds no calibration
        res = self._do(finish) if not self._aborted else {}
        return dict({"step": "symbols", "scheme": name, "period": period, "width": width, "count": count, "side": side,
                     "delay": delay, "settle": settle, "windows": "plain" if plain else ("cal" if L and L.cal else "plain"),
                     "table": prof["table"] if prof is not None else (table if isinstance(table, str) or table is None else "explicit"),
                     "profile": prof is not None, "rx": lut_used, "interrupted": not ok}, **res)

    def data(self, st):
        ps = st.get("periods") or [st.get("period", 4)]
        key = "period_" + st.get("mod", "bpsk")
        period = int(ps[self._k.get(key, 0) % len(ps)])
        self._k[key] = self._k.get(key, 0) + 1
        # the modulation: BPSK (the default: bit 0 the carrier, bit 1 it inverted, checked on the sign of I), or on-off
        # keying (ID 12: bit 1 the carrier nulled, checked on the I window on the carrier's side, IP or IN)
        ook = st.get("mod") == "ook"
        seconds = float(st["seconds"])
        # every gap_every seconds a moment of the carrier alone, its level read: the slow I arm reads the level only
        # off an idle carrier, so without the gaps the page has no signal strength while data runs
        gap_every = float(st.get("gap_every") or 0.0)
        L = getattr(self.server, "linkd", None)
        losses0 = L.counts["losses"] if L else 0
        side = None

        def check(sd):
            return dict(invert=True, src="IP" if sd > 0 else "IN") if ook else dict(invert=sd > 0)

        gain = st.get("gain")
        if gain is None and st.get("profile", True):
            gp = (((self.profile or {}).get("data") or {}).get("ook" if ook else "bpsk") or {}).get("gain") or {}
            gain = gp.get(str(period))
        gain = int(gain or 4)

        def start(cl):
            sd = side if side is not None else self._side(cl)
            # OOK is read on the I window on the carrier's side, whose threshold the calibration puts a quarter of the
            # leg out (right for single symbols' corners); OOK's two levels are the carrier and its null, so for the
            # step it goes half way between them (2026-11-01: 25 Mbaud OOK 4e-7 with the quarter, the B210 quiet)
            if ook and L is not None and L.cen and (L.leg or L.leg_windows):
                w = "IP" if sd > 0 else "IN"
                self._ook_thr = w
                cl.threshold(w, min(2.499, max(0.0, L.cen[w] + 0.5 * (L.leg or L.leg_windows))))
            cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(0, 0) if ook else point_code(-1, 0)])
            cl.tx_timing(period=period)
            cl.tx_prbs(15)
            cl.tx_mode("prbs", n=2)
            cl.tx_go()
            self._busy = True
            time.sleep(0.005)
            cl.ber_config(15, None, enable=True, cdr=True, period=period, gain=gain, **check(sd))
            return sd, cl.t_clk

        def stop(cl):
            cl.ber_config(15, None, enable=False, cdr=True, period=period, gain=gain, **check(side))
            r = cl.ber()
            c = cl.cdr_state()
            cl.tx_stop()
            cl.hold_point(1, 0)
            self._restore_ook(cl)
            self._busy = False
            return r, c

        def level(cl):
            time.sleep(0.03)                                   # the arm settled on the idle carrier
            return sum(cl.adc("I") for _ in range(3)) / 3.0
        side, t_clk = self._do(start)
        mbaud = 1e-6 / (period * t_clk)
        self._say("data", "%s PRBS15 data at %.3g Mbaud, the bits checked with the timing recovered, %g s%s" % (
            "OOK (on-off keying: the carrier on or nulled)" if ook else "BPSK", mbaud, seconds,
            ", the carrier's level read each second" if gap_every else ""), period=period, mbaud=mbaud,
            seconds=seconds, mod="ook" if ook else "bpsk")
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
        return {"step": "data", "mod": "ook" if ook else "bpsk", "period": period, "mbaud": mbaud, "seconds": seconds,
                "side": side, "gain": gain, "interrupted": not ok,
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
            if self._need_calibration():                             # the windows from the states' levels first
                st = {"step": "calibrate"}
                self._cal_tried = time.time()
            else:
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
            dur = self._during(t0, res["t1"])
            if dur:
                res["during"] = dur
            # a quiet run of symbols that lost over 1 % (missed or undecided) says the windows are wrong for the link
            # now: calibrate again (13:41 a calibration taken during an attenuator step left A2, A3 and QPSK 60 % missed)
            dash = getattr(self.server, "dashboard", None)
            if (res.get("step") in ("symbols", "qpsk") and res.get("sent") and not res.get("interrupted")
                    and res["b210"] == "quiet" and not res.get("during") and not (dash and dash.active_note(t0))
                    and ((res.get("missed") or 0) + (res.get("undecided") or 0)) > 0.01 * res["sent"]):
                self._bad_windows = True
            self.results.append(res)

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="selftest").start()
        return self
