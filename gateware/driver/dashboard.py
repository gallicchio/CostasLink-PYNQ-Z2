"""dashboard.py: the CostasLink board's live status page, served from the PYNQ by the board server
(`netbus.py serve --dashboard 8080`).  Jason, 2026-10-31: the boards run unattended and are looked after by
physicists who do not know PLLs; they need pictures, each good or bad state with what led to it and how to improve
it, a help button on every plot, an arrow on each axis pointing the good way and green / yellow / red bands; live and
historical; and it must survive new firmware, tests and experiments being loaded.

Read-only, and never in a test's way.  A thread looks at the board about once a second between the server's
requests, under the server's own lock, and skips a look rather than wait when a request is running.  Every look uses
only reads that change nothing: the free-running comparator edge counters (rates from their differences), the hold
engines' state, the control bits, the timing recovery's registers; every few looks the slow ADC channels and the
detectors as well, each one I2C transaction that the lock keeps whole.  The page re-attaches by itself after the
server restarts or the overlay is reloaded, and says so when the loaded firmware is not CostasLink's.

It keeps two hours in memory and appends every look to dashboard/YYYY-MM-DD.jsonl beside the server (about 160 MB a
day; the days older than keep_days, and the oldest while the card has under min_free_mb left, are deleted at each new
day's first look).  HTTP: / the
page (dashboard.html beside this file, read again at every request, so a new page needs no restart), /api/now the
latest look, /api/history?s=600 the last s seconds, /api/events, /api/notes?s=, /api/pullin (pullin_map.json: the
measured map of the unlocked loop); POST /api/note {"text", "kind": "intervention" | "explained" | "info", "source",
"id", "end": true, "t_start", "t_end"}: a note from whoever is running an experiment (unattended.py says when the B210
interferes), shown in 'What happened' and as a band on the plots; a loss inside an intervention is called expected.
The page needs nothing from the internet.

The state is a judgement from those readings, provisional until the gateware's lock supervisor keeps its own (TODO,
'Unattended operation'): locked when both Q window comparators are quiet and the carrier is there; lost when both
toggle at a beat; no carrier when every window is quiet and I and Q sit at their middles; held when software or a
hold engine froze the loop.
"""
import collections
import json
import math
import uuid
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
KV_HZ_PER_V_5800 = 457e3                 # the RX LO's pull at 5.8 GHz (bringup/linktests.py)
I0_V, Q0_V = 1.6535, 1.628              # the arms' outputs with no carrier, on the ADC (board A, 2026-10-31): learned again
                                         # whenever the board is in the bench's quiet state (TX muted, DSA 31.75)
EDGES = ("CMP_I", "CMP_QP", "CMP_QN", "CMP_I_S", "CMP_QP_S", "CMP_QN_S", "CMP_IP", "CMP_IN")
EDGE_REGS = ("EDGE_CNT0", "EDGE_CNT1", "EDGE_CNT2", "EDGE_CNT3", "EDGE_CNT4", "EDGE_CNT5", "EDGE_CNT6", "EDGE_CNT7")


class Dashboard:
    def __init__(self, server, port=8080, period_s=1.0, slow_every=1, keep_s=7200, log_dir=None, keep_days=14, min_free_mb=1000):
        self.server = server
        server.dashboard = self                          # the self-test reads the notes (what the B210 did meanwhile)
        self.port = port
        self.period_s = period_s
        self.slow_every = slow_every
        self.hist = collections.deque(maxlen=int(keep_s / period_s) + 10)
        self.log_dir = log_dir or os.path.join(HERE, "dashboard")
        self.keep_days, self.min_free_mb = keep_days, min_free_mb
        self._day = None                 # the day of the last write (a new one prunes the old logs)
        self.n = 0
        self._prev = None                # (t, edges, ihold clocks, shold clocks)
        self._slow = {}                  # the last slow readings, carried into the looks between them
        self.vc_lock = None              # VC at lock, learned
        self.leg_ref = None              # the I leg at lock, learned (the constellation's targets)
        self.t_state = (None, time.time())
        self.i0, self.q0 = I0_V, Q0_V
        self.rx_carrier = None           # the carrier's frequency (from the locked looks): the middles are learned there
        self.side_i = {1: None, -1: None}   # the locked idle I on each lock point: (I, attenuator, t)
        self.i_delta = None              # the two lock points' mean less the muted middle
        self._mid_t = None               # linkd's measurement of the middles last taken
        self.side = None                 # the lock point (the sign of I) of the last locked idle look
        self._gap = False                # a look not locked since then
        self.events = collections.deque(maxlen=5000)   # what happened, in words, for the page's list (2 h of a busy test)
        self.notes = collections.deque(maxlen=500)     # notes posted by experiments: interventions, explanations
        self.scopes = collections.deque(maxlen=40)     # I MON / Q MON captures a bench test posted (POST /api/scope)
        self._lk = None                                 # linkd's counts at the last look

    # ---- the looks ----
    def look(self):
        srv = self.server
        if not srv.lock.acquire(timeout=0.05):
            out = {"t": time.time(), "busy": True, "driving": dict(srv.last)}
            if getattr(srv, "linkd", None) is not None:
                out["linkd"] = srv.linkd.state()
            return out
        try:
            return self._look()
        except Exception as e:                                       # noqa: BLE001 - shown on the page, never fatal
            return {"t": time.time(), "error": "%s: %s" % (type(e).__name__, e), "trace": traceback.format_exc()[-800:]}
        finally:
            srv.lock.release()

    def _look(self):
        import costaslink
        cl = self.server.cl
        t = time.time()
        r = {"t": t, "busy": False, "driving": dict(self.server.last)}
        if getattr(self.server, "linkd", None) is not None:
            r["linkd"] = self.server.linkd.state()
        ident = cl.rd("ID")
        r["id"] = "0x%08X" % ident
        if ident not in costaslink.ID_ACCEPTED:
            r["state"] = "firmware"
            self._prev = None
            return r
        edges = [cl.rd(n) for n in EDGE_REGS]
        ih, sh = cl.ihold_state(), cl.shold_state()
        ctrl = cl.rd("CTRL")
        r["ctrl"] = {"tx_dis": ctrl & 1, "loop_hold": ctrl >> 1 & 1}
        # what the link is asked to do, from its own registers whoever drives it: the transmitter's mode, the receiver
        # deciding single symbols, the bit check (the page's 'What is being done' lanes)
        tm, go = cl.rd("TX_MODE"), cl.rd("TX_GO")
        r["tx"] = {"mode": {v: k for k, v in cl.MODES.items()}.get(tm & 7, str(tm & 7)), "running": go & 1,
                   "n": (tm >> 8 & 7) + 1, "period": cl.rd("TX_PERIOD")}
        r["rx_on"] = cl.rd("RX_CTRL") & 1
        r["ber_on"] = cl.rd("RX_BER_CFG") & 1
        stt = getattr(self.server, "selftest", None)
        if stt is not None:
            r["selftest"] = stt.state()
        r["ihold"] = {k: ih[k] for k in ("on", "holding", "holds", "seconds", "hold_s", "persist_s") if k in ih}
        r["shold"] = {k: sh[k] for k in ("on", "holding", "holds", "seconds")}
        r["cmp"] = cl.rd("CMP_STATE")
        if getattr(cl, "lockmon", False):
            r["gw_lock"] = cl.lock_state()            # the gateware's own judgement (ID version 8, lockmon.v)
        pll = getattr(cl, "_pll", {})
        r["rx_mhz"] = pll.get(1, (None,))[0] if isinstance(pll, dict) else None
        r["dsa_db"] = getattr(cl, "_dsa_db", None)
        cfg = cl.rd("RX_BER_CFG")
        if cfg & 1:
            r["ber"] = cl.ber()
            if cfg >> 24 & 1:
                c = cl.cdr_state()
                r["cdr"] = c
                if c.get("skew_samples") is not None:
                    r["skew_ns"] = abs(c["skew_samples"]) * 1e3 / (cl.clk_mhz * cl.ser)
        if cl.rd("RX_CTRL") & 1:                       # the receive engine on: single symbols decided (rx_engine.v)
            st = cl.rx_stats()
            cm = cl.confusion()
            r["rx"] = {k: st.get(k) for k in ("events", "decided", "false", "missed", "confirm", "veto", "lat_n", "lat_min",
                                              "lat_max", "lat_mean")}
            r["rx"]["right"] = sum(cm[a][a] for a in range(8))
            r["rx"]["wrong"] = sum(cm[a][b] for a in range(8) for b in range(8) if a != b)
            r["rx"]["sample_ns"] = cl.t_sample * 1e9
        if self._prev is not None:
            t0, e0, ih0, sh0 = self._prev
            dt = t - t0
            if dt > 0:
                r["rate"] = {n: ((e - p) % (1 << 32)) / dt for n, e, p in zip(EDGES, edges, e0)}
                # the holds' clock counters are 32 bits at the fabric clock: they wrap every 42.9 s of holding (a 35 s
                # holdover crossed it, soak7); a reset (new firmware) reads as more than the look's own length
                wrap = (1 << 32) / (cl.clk_mhz * 1e6)
                d = (ih["seconds"] - ih0) % wrap
                r["hold_pct"] = 100.0 * d / dt if d <= dt * 1.05 else None
                d = (sh["seconds"] - sh0) % wrap
                r["holdover_pct"] = 100.0 * d / dt if d <= dt * 1.05 else None
        self._prev = (t, edges, ih["seconds"], sh["seconds"])
        if self.n % self.slow_every == 0:
            s = {"adc": {k: cl.adc(k) for k in ("I", "Q", "VC", "ERR")}}
            try:
                d = cl.detectors()
                s["det"] = {k: d.get(k) for k in ("log_dbm", "peak_dbm", "log_inr_db", "peak_inr_db", "v5_rf", "temp_c")}
            except Exception as e:                                   # noqa: BLE001
                s["det_error"] = str(e)[:200]
            s["t_slow"] = t
            self._slow = s
            r["slow_now"] = True
        r.update(self._slow)
        self.judge(r)
        self.note_events(r)
        return r

    OPEN_NOTE_S = 3600.0                 # a note never ended (its program died) counts as ended an hour after it began

    def note_end(self, n):
        if n.get("t_end") is not None:
            return n["t_end"]
        return n["t_start"] + self.OPEN_NOTE_S if time.time() - n["t_start"] > self.OPEN_NOTE_S else None

    def active_note(self, t, grace_s=10.0):
        """the intervention under way at t (or ended within grace_s), if any"""
        for n in reversed(self.notes):
            end = self.note_end(n)
            if n.get("kind") == "intervention" and n["t_start"] <= t <= (end if end is not None else 1e18) + grace_s:
                return n
        return None

    def note(self, d):
        """a note posted by an experiment (POST /api/note): begins one, ends one (id and end), or both at once"""
        t = time.time()
        if d.get("end") and d.get("id"):
            for n in reversed(self.notes):
                if n.get("id") == d["id"]:
                    n["t_end"] = float(d.get("t_end", t))
                    self.write({"t": t, "note": n})
                    return n
        n = {"id": d.get("id") or uuid.uuid4().hex[:12], "text": str(d.get("text", ""))[:400],
             "kind": d.get("kind", "info") if d.get("kind") in ("intervention", "explained", "info") else "info",
             "source": str(d.get("source", ""))[:80], "t_start": float(d.get("t_start", t)),
             "t_end": float(d["t_end"]) if d.get("t_end") is not None else None}
        if isinstance(d.get("b210"), dict):              # what the B210 sends, for the page's lane: {kind, off_mhz, gain...}
            n["b210"] = {k: v for k, v in d["b210"].items() if isinstance(v, (int, float, str)) and len(str(k)) < 20}
        self.notes.append(n)
        self.events.append({"t": n["t_start"], "kind": "note-" + n["kind"],
                            "text": n["text"] + ((" (" + n["source"] + ")") if n["source"] else "")})
        self.write({"t": t, "note": n})
        return n

    def scope(self, d):
        """a capture of I MON and Q MON from a bench oscilloscope (POST /api/scope {i, q, dt_ns, text, source, i0, q0}):
        the constellation at the scope's rate, which the slow readings cannot show (they average 1.2 ms)"""
        n = min(len(d["i"]), len(d["q"]), 6000)
        c = {"t": float(d.get("t", time.time())), "text": str(d.get("text", ""))[:300], "source": str(d.get("source", ""))[:80],
             "dt_ns": float(d.get("dt_ns", 0)), "i0": d.get("i0"), "q0": d.get("q0"),
             # what it shows: single symbols or data, their timing (for the aligned and folded views), and what the link
             # and the B210 were doing, in words
             "kind": str(d.get("kind", ""))[:20], "period_ns": d.get("period_ns"), "width_ns": d.get("width_ns"),
             "scheme": str(d.get("scheme", ""))[:10], "leg": d.get("leg"), "link": str(d.get("link", ""))[:300],
             "b210": str(d.get("b210", ""))[:300],
             "i": [round(float(v), 4) for v in d["i"][:n]], "q": [round(float(v), 4) for v in d["q"][:n]]}
        self.scopes.append(c)
        self.write({"t": c["t"], "scope": c})
        return {"t": c["t"], "n": n}

    def event(self, e):
        """one line of 'What happened', kept in the day's log too (restore() reads it back after a restart)"""
        self.events.append(e)
        self.write({"t": e["t"], "event": e})

    def restore(self, tail_bytes=16 << 20):
        """the last keep_s of looks, the notes and the events from the day's log (and yesterday's), so that a restart of
        the server (new firmware, a new driver) does not blank the page"""
        t_min = time.time() - self.hist.maxlen * self.period_s
        notes, n_looks = {}, 0
        for day in sorted({time.strftime("%Y-%m-%d", time.localtime(t)) for t in (t_min, time.time())}):
            path = os.path.join(self.log_dir, day + ".jsonl")
            try:
                with open(path, "rb") as f:
                    f.seek(max(0, os.path.getsize(path) - tail_bytes))
                    if f.tell():
                        f.readline()                                     # the partial line the seek landed in
                    for line in f:
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        if d.get("t", 0) < t_min:
                            continue
                        if "note" in d:
                            notes[d["note"]["id"]] = d["note"]
                        elif "event" in d:
                            self.events.append(d["event"])
                        elif "scope" in d:
                            self.scopes.append(d["scope"])
                        else:
                            self.hist.append(d)
                            n_looks += 1
            except OSError:
                pass
        for n in sorted(notes.values(), key=lambda n: n["t_start"]):
            self.notes.append(n)
            self.events.append({"t": n["t_start"], "kind": "note-" + n["kind"],
                                "text": n["text"] + ((" (" + n["source"] + ")") if n["source"] else "")})
        self.events = collections.deque(sorted(self.events, key=lambda e: e["t"]), maxlen=self.events.maxlen)
        if self.hist and time.time() - self.hist[-1]["t"] < 600:
            self.vc_lock = self.hist[-1].get("vc_lock")                  # the lock learned before (it adapts again)
            self.i_delta = self.hist[-1].get("i_delta")                 # (the middles themselves: linkd's setup)
            for r in reversed(self.hist):
                if r.get("state") == "locked" and r.get("rx_mhz"):
                    self.rx_carrier = r["rx_mhz"]
                    break
        return n_looks, len(notes)

    def note_events(self, r):
        """losses and recoveries as linkd counted them, and the state's changes, for 'What happened'"""
        if r.get("slip"):
            act = self.active_note(r["t"])
            self.event({"t": r["t"], "kind": "slip", "text": "The loop slipped to its other lock point (half a cycle) without "
                        "losing the lock: the link's data would arrive inverted until the receiver resolves it." +
                        (" During '%s'." % act["text"] if act else "")})
        L = r.get("linkd")
        if L:
            if self._lk is not None:
                if L["losses"] > self._lk["losses"]:
                    # linkd counts a loss when it acts, often after VC has come back: the furthest the last 30 s went
                    offs = [x["off_khz"] for x in list(self.hist)[-30:] + [r] if x.get("off_khz") is not None]
                    off = max(offs, key=abs) if offs else None
                    where = (" (the oscillator went %.0f kHz %s the carrier)" % (abs(off), "below" if off < 0 else "above")) \
                        if off is not None and abs(off) >= 3 else ""
                    act = self.active_note(r["t"])
                    self.event({"t": r["t"], "kind": "loss-expected" if act else "loss",
                                        "text": "The lock was lost" + where + "; the board started to recover it." +
                                                (" Expected: during '%s'." % act["text"] if act else "")})
                if L["recoveries"] > self._lk["recoveries"]:
                    d = L.get("last_recovery_s")
                    self.event({"t": r["t"], "kind": "recovered",
                                        "text": "Locked again by itself" + (" %.1f s after the loss" % d if d is not None else "") +
                                                ((", %d start(s)" % L["last_starts"]) if L.get("last_starts") else "") + "."})
                if L["failed"] > self._lk["failed"]:
                    self.event({"t": r["t"], "kind": "failed",
                                        "text": "A recovery found no carrier; it will try again (is the other board on?)."})
            self._lk = {k: L.get(k, 0) for k in ("losses", "recoveries", "failed")}

    def judge(self, r):
        """the state, its cause and what to do, in words for someone who does not know PLLs"""
        cl = self.server.cl
        rate = r.get("rate") or {}
        adc = r.get("adc") or {}
        # no carrier reaches the arms: their middles.  Only at the carrier's own frequency: while a program re-centres
        # the integrator at 5.8 GHz its trims push I by +-25 mV, which the page learned as the middle (1.637-1.658 V
        # in one afternoon, the carrier's level 1.3 dB off after it; soak.py, 2026-10-31)
        L = r.get("linkd") or {}
        if L.get("mid_t") and L["mid_t"] != self._mid_t:          # linkd measured them at its setup, at the carrier
            self.i0, self.q0, self._mid_t = L["i0"], L["q0"], L["mid_t"]
        elif adc and r.get("slow_now") and r["ctrl"]["tx_dis"] and r.get("dsa_db") == 31.75 and r.get("rx_mhz") is not None \
                and r.get("rx_mhz") == self.rx_carrier:
            self.i0 = 0.8 * self.i0 + 0.2 * adc["I"]
            self.q0 = 0.8 * self.q0 + 0.2 * adc["Q"]
        # the two lock points sit asymmetrically about the muted middle (on board A by 4.5 mV, which read the carrier
        # 0.5 dB apart on the two sides): their middle is the muted one plus the learned offset
        i_mid = self.i0 + (self.i_delta or 0.0)
        r["i0"], r["q0"], r["i_delta"] = i_mid, self.q0, self.i_delta
        di = adc.get("I", i_mid) - i_mid
        dq = adc.get("Q", self.q0) - self.q0
        r["leg_mv"] = abs(di) * 1e3 if adc else None
        qp, qn = rate.get("CMP_QP", 0), rate.get("CMP_QN", 0)
        ip, inn = rate.get("CMP_IP", 0), rate.get("CMP_IN", 0)
        held_sw = r["ctrl"]["loop_hold"]
        vc = adc.get("VC")
        off = None
        if vc is not None and self.vc_lock is not None and r.get("rx_mhz"):
            off = (vc - self.vc_lock) * KV_HZ_PER_V_5800 * r["rx_mhz"] / 5800.0 / 1e3
        gw = r.get("gw_lock")
        if not rate:
            st = "starting"
        elif held_sw:
            st = "held"
        elif r["ihold"].get("holding"):
            st = "interference"
        elif r["shold"].get("holding"):
            st = "holdover"
        else:
            if gw:                                    # the gateware's judgement (lockmon.v): bursts are not a beat
                st = {"locked": "locked", "lost": "lost", "no carrier": "nocarrier", "unsure": "unsettled"}.get(gw["state"], "unsettled")
            elif max(qp, qn, ip, inn) < 200 and abs(di) < 0.04 and abs(dq) < 0.04:
                st = "nocarrier"
            elif qp > 20000 and qn > 20000:
                st = "lost"
            elif qp < 5000 and qn < 5000:
                st = "locked"
            else:
                st = "unsettled"
            # busy windows with the oscillator still at the lock: interference, not a loss (a lost loop cannot stay
            # within 8 kHz of the lock: BRINGUP_LOG 4.12, 4.15; the first live page called beacon bursts 'lost')
            if st in ("lost", "unsettled") and off is not None and abs(off) < 8.0:
                st = "interfered"
            # the board's own symbols move the Q windows (A2, A3), which the lock monitor before ID 9 reads as busy:
            # with the oscillator at the lock that is the link working, not interference.  From ID 9 it masks them
            # itself, so its 'lost' during the board's own symbols is real interference (a CW 0.43 MHz away, 22:34)
            tx = r.get("tx") or {}
            if st == "interfered" and not getattr(cl, "lockmon_own", False) and tx.get("running") and \
                    tx.get("mode") in ("events", "prbs", "rotate", "trig_in"):
                st = "locked"
                r["own_activity"] = True
        r["state"] = st
        # the carrier's level, from the locked idle I arm (I_P = V_MID + I / 2: a = 2 |di|, the differential peak at the
        # comparators) and the attenuator: at the demodulator's input, and at RX ANT (costaslink.received_dBm's sums).
        # Only locked (a near interferer or a beat adds to it: a CW 20 kHz off read 8 dB high) and while CMP_I is quiet
        # (data averages I towards zero on this slow reading)
        idle = bool(adc) and rate.get("CMP_I", 1e9) < 2000
        # not interference or the holdover: a slip across those counts (a held loop loses its phase across a gap of the
        # carrier 30-60 % of the time, REVB 24, and nothing else would show it)
        if st in ("lost", "nocarrier", "held", "firmware", "starting"):
            self._gap = True
        if st == "locked":
            self.rx_carrier = r.get("rx_mhz")
            if idle and abs(adc["I"] - self.i0) > 0.05:
                sd = 1 if adc["I"] > self.i0 else -1
                # the other lock point with no look unlocked between: a half-cycle slip (a carrier interruption of
                # 16 ms did it, soak.py 2026-10-31), which inverts BPSK data; after a loss either point is as likely
                if self.side is not None and sd != self.side and not self._gap:
                    r["slip"] = True
                self.side, self._gap = sd, False
                self.side_i[sd] = (adc["I"], r.get("dsa_db"), r["t"])
                o = self.side_i[-sd]                  # the other side's latest, at the same attenuator, comparable
                if o and o[1] == r.get("dsa_db") and r["t"] - o[2] < 1800:
                    a1, a2 = abs(adc["I"] - self.i0), abs(o[0] - self.i0)
                    if abs(a1 - a2) < 0.15 * max(a1, a2):
                        dlt = (adc["I"] + o[0]) / 2.0 - self.i0
                        self.i_delta = dlt if self.i_delta is None else 0.8 * self.i_delta + 0.2 * dlt
            try:
                from board_constants import RX_GAIN_DB, DEM_REG_DBM, A_REG_V
                a_diff = 2.0 * abs(di)
                if idle and a_diff > 0.004:
                    r["dem_dbm"] = DEM_REG_DBM + 20.0 * math.log10(a_diff / A_REG_V)
                    if r.get("dsa_db") is not None:
                        r["rx_ant_dbm"] = r["dem_dbm"] - RX_GAIN_DB + r["dsa_db"]
            except ImportError:
                pass
        if st == "locked" and vc is not None:
            self.vc_lock = vc if self.vc_lock is None else 0.95 * self.vc_lock + 0.05 * vc
            if abs(di) > 0.05 and r.get("ber") is None:
                self.leg_ref = abs(di) if self.leg_ref is None else 0.9 * self.leg_ref + 0.1 * abs(di)
        if off is not None and st != "held":        # held, a program sets VC (and re-centres it at 5.8 GHz): no offset
            r["off_khz"] = off
        r["vc_lock"] = self.vc_lock
        r["leg_ref_mv"] = self.leg_ref * 1e3 if self.leg_ref else None
        prev, since = self.t_state
        if st != prev:
            self.t_state = (st, r["t"])
            since = r["t"]
        r["state_since"] = since

    # ---- the loop and the record ----
    def run(self):
        while True:
            t0 = time.time()
            r = self.look()
            self.n += 1
            self.hist.append(r)
            self.write(r)
            time.sleep(max(0.05, self.period_s - (time.time() - t0)))

    def write(self, r):
        try:
            os.makedirs(self.log_dir, exist_ok=True)
            day = time.strftime("%Y-%m-%d", time.localtime(r["t"]))
            if day != self._day:
                self._day = day
                self.prune(day)
            with open(os.path.join(self.log_dir, day + ".jsonl"), "a") as f:
                f.write(json.dumps(r, default=str) + "\n")
        except OSError:
            pass

    def prune(self, today):
        """the SD card kept from filling: the day logs older than keep_days go, then the oldest (never today's or
        yesterday's, which restore() reads) while less than min_free_mb is left"""
        try:
            t_today = time.mktime(time.strptime(today, "%Y-%m-%d"))
            days = sorted(f for f in os.listdir(self.log_dir) if f.endswith(".jsonl") and len(f) == 16)
            keep = []
            for f in days:
                try:
                    age = (t_today - time.mktime(time.strptime(f[:10], "%Y-%m-%d"))) / 86400.0
                except ValueError:
                    continue
                if age > self.keep_days:
                    os.remove(os.path.join(self.log_dir, f))
                elif age >= 2:
                    keep.append(f)
            for f in keep:
                st = os.statvfs(self.log_dir)
                if st.f_bavail * st.f_frsize / 1e6 >= self.min_free_mb:
                    break
                os.remove(os.path.join(self.log_dir, f))
        except OSError:
            pass

    def history(self, s):
        t_min = time.time() - s
        out = [r for r in list(self.hist) if r["t"] >= t_min]
        step = max(1, len(out) // 1500)              # at most 1500 points to the page
        return out[::step] + ([out[-1]] if out and (len(out) - 1) % step else [])

    # ---- the web page ----
    def http(self):
        dash = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def send(self, code, body, ctype):
                b = body.encode() if isinstance(body, str) else body
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(b)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(b)

            def do_GET(self):
                u = urlparse(self.path)
                if u.path == "/":
                    try:
                        with open(os.path.join(HERE, "dashboard.html"), "rb") as f:
                            self.send(200, f.read(), "text/html; charset=utf-8")
                    except OSError:
                        self.send(200, PAGE, "text/html; charset=utf-8")
                elif u.path == "/api/pullin":
                    try:
                        with open(os.path.join(HERE, "pullin_map.json"), "rb") as f:
                            self.send(200, f.read(), "application/json")
                    except OSError:
                        self.send(200, "{}", "application/json")
                elif u.path == "/api/selftest":
                    st = getattr(dash.server, "selftest", None)
                    self.send(200, json.dumps(st.state() if st else {"on": False, "absent": True}, default=str), "application/json")
                elif u.path == "/api/scope":
                    s = float(parse_qs(u.query).get("s", ["7200"])[0])
                    t0 = time.time() - s
                    self.send(200, json.dumps([c for c in dash.scopes if c.get("t", 0) >= t0], default=str), "application/json")
                elif u.path == "/api/notes":
                    s = float(parse_qs(u.query).get("s", ["7200"])[0])
                    t0 = time.time() - s
                    ns = [dict(n, t_end=dash.note_end(n)) for n in dash.notes]
                    self.send(200, json.dumps([n for n in ns if (n["t_end"] or 1e18) >= t0], default=str), "application/json")
                elif u.path == "/api/now":
                    self.send(200, json.dumps(dash.hist[-1] if dash.hist else {}, default=str), "application/json")
                elif u.path == "/api/events":
                    s = float(parse_qs(u.query).get("s", ["7200"])[0])     # the page's span (it listed only the last 30)
                    t0 = time.time() - s
                    self.send(200, json.dumps([e for e in dash.events if e["t"] >= t0][-3000:], default=str), "application/json")
                elif u.path == "/api/history":
                    s = float(parse_qs(u.query).get("s", ["600"])[0])
                    self.send(200, json.dumps(dash.history(s), default=str), "application/json")
                else:
                    self.send(404, "not here", "text/plain")

            def do_POST(self):
                u = urlparse(self.path)
                if u.path not in ("/api/note", "/api/scope", "/api/selftest"):
                    self.send(404, "not here", "text/plain")
                    return
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                    d = json.loads(self.rfile.read(min(n, 1 << 20 if u.path == "/api/scope" else 65536)) or b"{}")
                    if u.path == "/api/selftest":
                        st = getattr(dash.server, "selftest", None)
                        if st is None:
                            raise ValueError("this server runs without --selftest")
                        out = st.set(d)
                        dash.note({"text": ("the signal holdover switched %s" % ("on" if d["holdover"] else "off")) if "holdover" in d and len(d) == 1
                                   else "the link's self-test %s (plan '%s')" % ("on" if out["on"] else "off", out["plan"]),
                                   "kind": "info", "source": "the page's API"})
                    else:
                        out = dash.scope(d) if u.path == "/api/scope" else dash.note(d)
                    self.send(200, json.dumps(out, default=str), "application/json")
                except (ValueError, TypeError, KeyError) as e:
                    self.send(400, "bad %s: %s" % (u.path, e), "text/plain")

        return ThreadingHTTPServer(("0.0.0.0", self.port), H)

    def start(self):
        try:
            print("dashboard: %d looks and %d notes restored from the log" % self.restore(), flush=True)
        except Exception as e:                                           # noqa: BLE001 - never keep the page from starting
            print("dashboard: nothing restored (%s)" % e, flush=True)
        threading.Thread(target=self.run, daemon=True, name="dashboard looks").start()
        srv = self.http()
        threading.Thread(target=srv.serve_forever, daemon=True, name="dashboard http").start()
        print("CostasLink dashboard on port %d" % self.port, flush=True)
        return self


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>CostasLink link status</title>
<style>
:root { --ink:#16181d; --ink2:#555b66; --line:#d9dce1; --bg:#f5f6f8; --card:#fff;
        --good:#1f9d6a; --warn:#d9a400; --bad:#d64545; --goodb:rgba(31,157,106,.16); --warnb:rgba(217,164,0,.18);
        --badb:rgba(214,69,69,.15); --trace:#1e3a8a; }
* { box-sizing:border-box; }
body { margin:0; font:15px/1.4 system-ui,-apple-system,"Segoe UI",sans-serif; color:var(--ink); background:var(--bg); }
header { padding:14px 16px 8px; display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
h1 { font-size:18px; margin:0 12px 0 0; }
.meta { color:var(--ink2); font-size:13px; }
#status { margin:0 16px 12px; padding:14px 16px; border-radius:10px; background:var(--card); border-left:10px solid var(--line);
          display:grid; grid-template-columns:auto 1fr; gap:4px 16px; }
#status .word { font-size:26px; font-weight:700; grid-row:span 3; align-self:center; }
#status .why, #status .todo { font-size:15px; }
#status .todo { font-weight:600; }
#status .small { font-size:13px; color:var(--ink2); }
.ranges { margin:0 16px 8px; display:flex; gap:6px; }
.ranges button { border:1px solid var(--line); background:var(--card); border-radius:6px; padding:4px 10px; cursor:pointer; }
.ranges button.on { background:var(--ink); color:#fff; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(420px,1fr)); gap:12px; padding:0 16px 16px; }
@media (max-width:480px) { .grid { grid-template-columns:1fr; } }
.panel { background:var(--card); border-radius:10px; padding:10px 12px 8px; border:1px solid var(--line); }
.panel h2 { font-size:15px; margin:0; display:flex; align-items:center; gap:8px; }
.panel h2 .val { margin-left:auto; font-size:20px; font-weight:700; }
.help { border:1px solid var(--ink2); color:var(--ink2); background:none; border-radius:50%; width:22px; height:22px;
        font-weight:700; cursor:pointer; padding:0; }
canvas { width:100%; height:180px; display:block; margin-top:6px; }
.verdict { font-size:13px; color:var(--ink2); margin-top:4px; min-height:1.4em; }
dialog { max-width:560px; border:none; border-radius:12px; padding:18px 20px; box-shadow:0 10px 40px rgba(0,0,0,.25); }
dialog h3 { margin:0 0 8px; }
dialog p { margin:6px 0; }
dialog .k { font-weight:700; }
dialog button { margin-top:10px; }
</style></head><body>
<header><h1>CostasLink link status</h1><span class="meta" id="meta">connecting...</span></header>
<div id="status"><div class="word" id="word">...</div><div class="why" id="why"></div><div class="todo" id="todo"></div>
<div class="small" id="small"></div></div>
<div class="ranges"><span class="meta" style="align-self:center">show the last</span>
<button data-s="600" class="on">10 min</button><button data-s="3600">1 hour</button><button data-s="7200">2 hours</button></div>
<div class="grid" id="grid"></div>
<div class="panel" style="margin:0 16px 16px"><h2><button class='help' id='evhelp'>?</button>What happened</h2>
<div id="events" class="verdict" style="font-size:14px;color:#16181d"></div></div>
<dialog id="dlg"><h3 id="dlgt"></h3><div id="dlgb"></div><button onclick="dlg.close()">Close</button></dialog>
<script>
const C = {good:"#1f9d6a", warn:"#d9a400", bad:"#d64545"};
const B = {good:"rgba(31,157,106,.16)", warn:"rgba(217,164,0,.20)", bad:"rgba(214,69,69,.15)"};
const STATES = {
  locked:      ["Locked", "good", "The receiver is locked to the other board's carrier: the link is working.", "Nothing to do."],
  lost:        ["Lost", "bad", "The receiver's oscillator is not on the carrier (the plot 'Distance from the carrier' shows how far). Usually a strong interferer dragged it off, or the carrier was blocked for a while.",
                "Wait: the recovery brings it back within seconds. If it stays lost for more than a minute, check that the other board is on and that the antennas face each other."],
  nocarrier:   ["No carrier", "bad", "The receiver sees no carrier at all.", "Is the other board powered and transmitting? Are both antennas connected and pointed at each other, with nothing in between?"],
  interference:["Riding out interference", "warn", "A strong interferer is on the air; the loop is held still until it goes, so that it is not dragged off.",
                "Nothing to do if it is brief. If it lasts, look for a nearby transmitter (a WiFi access point, a phone, a microwave oven) and move it or the antennas."],
  holdover:    ["Carrier interrupted: holding", "warn", "The carrier went away (someone or something in the path?); the loop is held at the carrier's frequency so it picks up again at once when the carrier returns.",
                "Clear the path between the antennas."],
  held:        ["Held by a test", "warn", "A test program, or a person, has frozen the loop on purpose.", "Nothing to do: it is part of a test."],
  unsettled:   ["Settling", "warn", "The readings disagree for the moment: the receiver may be acquiring the carrier, or interference is passing.", "Wait a few seconds."],
  starting:    ["Starting", "warn", "The status page has just started.", "Wait a moment."],
  firmware:    ["Not the CostasLink firmware", "bad", "The firmware loaded on the board is not one this page knows, so it cannot read the link.", "Load a CostasLink overlay (or this is a new one the page does not know yet)."],
  busy:        ["Busy (a test is running)", "warn", "The board is busy answering a test program, so this look was skipped.", "Nothing to do."],
  error:       ["Cannot read the board", "bad", "Reading the board failed (see the detail below).", "If it persists, the board server may need a restart."]
};
const HELP_COMMON = "<p>The coloured bands behind each plot say how good a value is: <span style='color:"+C.good+"'>green</span> good, <span style='color:"+C.warn+"'>yellow</span> marginal, <span style='color:"+C.bad+"'>red</span> bad. The arrow beside the axis points the good way.</p>";
const PANELS = [
 {id:"state", title:"Lock, over time", kind:"timeline",
  help:"<p>Each moment coloured by the receiver's state: green locked, yellow holding or settling, red lost or no carrier.</p><p class='k'>Good: solid green.</p><p>Red stretches are losses; the recovery should end each within seconds. Many red stretches mean strong interference or a weak signal: see the other plots for which.</p>"},
 {id:"level", title:"Received signal", unit:"mV", get:r=>r.leg_mv, lo:0, hi:450, arrow:"upcap",
  bands:[[0,50,"bad"],[50,100,"warn"],[100,250,"good"],[250,350,"warn"],[350,450,"bad"]],
  help:"<p>How strong the other board's carrier is at this receiver (the I arm's level when the link is idle; data averages it towards zero on this slow reading).</p><p class='k'>Good: 100-250 mV (green). More is better, up to overload above about 350 mV.</p><p><b>Too low:</b> point the antennas at each other, shorten the path, check the cables and connectors, keep the line of sight clear. <b>Too high:</b> the boards are too close or the attenuation is too low.</p><p>Bands from the bench, 2026-10-30: the loop held 25 dB fades down to a 44 mV leg; the arms clip near 500 mV.</p>"},
 {id:"offset", title:"Distance from the carrier", unit:"kHz", get:r=>r.off_khz, lo:-150, hi:150, arrow:"middle", symlog:5, ticks:[-150,-13,0,5,60,150],
  bands:[[-150,-13,"bad"],[-13,-5,"warn"],[-5,5,"good"],[5,60,"warn"],[60,150,"bad"]],
  help:"<p>How far the receiver's oscillator is from where it sits when locked. Locked, it stays near zero.</p><p class='k'>Good: within 5 kHz (green).</p><p><b>Below -13 kHz</b> the loop cannot pull itself back: it drifts to a 'false lock' about 45 kHz below, or to its limit. <b>Above</b>, it drifts back down by itself. A red trace means a recovery is needed; it normally follows within seconds.</p><p>From the bench map of the unlocked loop (BRINGUP_LOG 4.12).</p>"},
 {id:"constellation", title:"Constellation (slow)", kind:"scatter",
  help:"<p>The received signal's I and Q, one dot per reading (slow: each reading averages about a millisecond). The rings mark where the idle carrier should sit when locked: on the horizontal axis, left or right.</p><p class='k'>Good: a tight cluster on a ring.</p><p><b>A smear around a circle</b>: not locked (the oscillator beats against the carrier). <b>A cluster near the middle</b>: no carrier, or data running (data averages out on this slow reading). The real constellation at the symbol rate needs the next board's fast I/Q converter.</p>"},
 {id:"interference", title:"Unwanted power in Q", unit:"dB", get:r=>r.det&&r.det.log_inr_db, lo:0, hi:60, arrow:"down",
  bands:[[0,26,"good"],[26,35,"warn"],[35,60,"bad"]],
  help:"<p>The average power on the receiver's Q arm, in dB over the receiver's own noise. Locked, the carrier sits on the I arm and Q holds only noise and whatever else is on the air: about 21 dB on the bench. Two things raise it: an interferer in the band, or the loop not being locked (then the carrier beats through Q: about 54 dB).</p><p class='k'>Good: low (green).</p><p><b>High while the status says Locked:</b> something else transmits nearby in the band (WiFi, phones, radars): move it, move the antennas, or choose another carrier frequency. <b>High while Lost:</b> that is the lost lock itself.</p><p>Bands provisional, from the bench's locked (20.8-23.9 dB) and lost (about 54 dB) readings, 2026-10-31.</p>"},
 {id:"hold", title:"Time spent riding out interference", unit:"%", get:r=>r.hold_pct, lo:0, hi:100, arrow:"down", symlog:1, ticks:[0,1,10,100],
  bands:[[0,1,"good"],[1,10,"warn"],[10,100,"bad"]],
  help:"<p>The share of the last second the interference hold kept the loop frozen.</p><p class='k'>Good: under 1 % (green).</p><p>The hold keeps a strong interferer from dragging the loop off, but while held the link's decisions slowly lose their phase, so long holds cost data. <b>Often high:</b> a persistent interferer nearby.</p>"},
 {id:"skew", title:"Timing: comparator skew", unit:"ns", get:r=>r.skew_ns, lo:0, hi:6, arrow:"down",
  bands:[[0,1.5,"good"],[1.5,3.5,"warn"],[3.5,6,"bad"]],
  help:"<p>When a timing-recovered data check runs: how much later the receiver's sign comparator switches one way than the other (its duty-cycle distortion). It eats into the eye.</p><p class='k'>Good: under 1.5 ns.</p><p>Shown only while data is being checked. Large values come from the comparator's threshold sitting off the signal's middle (REVB 30); a trim can reduce it.</p>"},
 {id:"temp", title:"Board temperature", unit:"°C", get:r=>r.det&&r.det.temp_c, lo:0, hi:90, arrow:"middle",
  bands:[[0,5,"bad"],[5,15,"warn"],[15,60,"good"],[60,75,"warn"],[75,90,"bad"]],
  help:"<p>The board's thermistor, near the RF chain.</p><p class='k'>Good: 15-60 °C.</p><p><b>Hot:</b> shade the board, give it airflow. Its frequencies drift with temperature; the loop follows slow drift.</p>"},
 {id:"supply", title:"RF supply", unit:"V", get:r=>r.det&&r.det.v5_rf, lo:4.5, hi:5.5, arrow:"middle",
  bands:[[4.5,4.75,"bad"],[4.75,4.85,"warn"],[4.85,5.25,"good"],[5.25,5.35,"warn"],[5.35,5.5,"bad"]],
  help:"<p>The +5 V rail of the RF chain (the demodulator and amplifiers want 4.75-5.25 V).</p><p class='k'>Good: 4.85-5.25 V.</p><p><b>Low:</b> a weak or long USB / power cable, or a supply set too low.</p>"}
];
let span = 600, hist = [], last = null;
const grid = document.getElementById("grid");
for (const p of PANELS) {
  const d = document.createElement("div"); d.className = "panel";
  d.innerHTML = "<h2><button class='help' title='What is this?'>?</button>"+p.title+"<span class='val' id='v_"+p.id+"'></span></h2>"+
                "<canvas id='c_"+p.id+"'></canvas><div class='verdict' id='x_"+p.id+"'></div>";
  d.querySelector(".help").onclick = () => { document.getElementById("dlgt").textContent = p.title;
      document.getElementById("dlgb").innerHTML = p.help + (p.bands ? HELP_COMMON : ""); dlg.showModal(); };
  grid.appendChild(d);
}
document.querySelectorAll(".ranges button").forEach(b => b.onclick = () => {
  document.querySelectorAll(".ranges button").forEach(x => x.classList.remove("on")); b.classList.add("on");
  span = +b.dataset.s; load(); });
function band(p, v) { if (v == null || !p.bands) return null; for (const [a, b, k] of p.bands) if (v >= a && v <= b) return k;
  return v < p.bands[0][0] ? p.bands[0][2] : p.bands[p.bands.length - 1][2]; }
function stateColour(s) { return (STATES[s] || STATES.unsettled)[1]; }
function sizeCanvas(cv) { const r = window.devicePixelRatio || 1, w = cv.clientWidth, h = cv.clientHeight;
  if (cv.width != w * r || cv.height != h * r) { cv.width = w * r; cv.height = h * r; }
  const g = cv.getContext("2d"); g.setTransform(r, 0, 0, r, 0, 0); return [g, w, h]; }
function arrow(g, x, y0, y1, kind, mid) {
  g.save(); g.strokeStyle = g.fillStyle = "#16181d"; g.lineWidth = 2;
  const tri = (y, up) => { g.beginPath(); g.moveTo(x - 6, y + (up ? 8 : -8)); g.lineTo(x + 6, y + (up ? 8 : -8)); g.lineTo(x, y); g.fill(); };
  if (kind == "up" || kind == "upcap") { g.beginPath(); g.moveTo(x, y1 - 8); g.lineTo(x, y0 + 8); g.stroke(); tri(y0 + 2, true);
    if (kind == "upcap") { g.beginPath(); g.moveTo(x - 7, y0); g.lineTo(x + 7, y0); g.stroke(); } }
  else if (kind == "down") { g.beginPath(); g.moveTo(x, y0 + 8); g.lineTo(x, y1 - 8); g.stroke(); tri(y1 - 2, false); }
  else if (kind == "middle") { const m = mid != null ? mid : (y0 + y1) / 2; g.beginPath(); g.moveTo(x, y0 + 4); g.lineTo(x, m - 10); g.moveTo(x, y1 - 4); g.lineTo(x, m + 10); g.stroke();
    tri(m - 4, false); tri(m + 4, true); }
  g.restore(); }
function drawSeries(p) {
  const cv = document.getElementById("c_" + p.id), [g, w, h] = sizeCanvas(cv);
  const L = 54, R = 8, T = 6, Bt = 20, pw = w - L - R, ph = h - T - Bt, now = Date.now() / 1000, t0 = now - span;
  const f = v => p.symlog ? Math.sign(v) * Math.log1p(Math.abs(v) / p.symlog) : v;
  const y = v => T + ph * (1 - (f(Math.min(p.hi, Math.max(p.lo, v))) - f(p.lo)) / (f(p.hi) - f(p.lo)));
  const x = t => L + pw * (t - t0) / span;
  g.clearRect(0, 0, w, h);
  for (const [a, b, k] of p.bands) { g.fillStyle = B[k]; g.fillRect(L, y(b), pw, y(a) - y(b)); }
  g.strokeStyle = "#c9ccd2"; g.lineWidth = 1; g.strokeRect(L, T, pw, ph);
  g.fillStyle = "#555b66"; g.font = "12px system-ui"; g.textAlign = "right";
  for (const v of (p.ticks || [p.lo, (p.lo + p.hi) / 2, p.hi])) g.fillText((+v.toFixed(2)) + "", L - 22, y(v) + 4);
  g.textAlign = "center"; g.fillText("-" + (span >= 3600 ? (span / 3600) + " h" : (span / 60) + " min"), L + 20, h - 5); g.fillText("now", w - R - 14, h - 5);
  const gb = p.bands.find(b => b[2] == "good");
  arrow(g, L - 10, T + 2, T + ph - 2, p.arrow, gb ? (y(gb[0]) + y(gb[1])) / 2 : null);
  g.strokeStyle = "#1e3a8a"; g.lineWidth = 2; g.beginPath(); let pen = false, prevT = null;
  for (const r of hist) { const v = r.busy ? null : p.get(r); if (r.t < t0) continue;
    if (v == null || (prevT != null && r.t - prevT > Math.max(10, span / 150))) { pen = false; }
    if (v != null) { if (!pen) { g.moveTo(x(r.t), y(v)); pen = true; } else g.lineTo(x(r.t), y(v)); prevT = r.t; } }
  g.stroke();
  const lv = lastValue(p), el = document.getElementById("v_" + p.id), k = band(p, lv);
  el.textContent = lv == null ? "-" : (Math.abs(lv) >= 100 ? lv.toFixed(0) : lv.toFixed(lv < 10 ? 2 : 1)) + " " + p.unit;
  el.style.color = k ? C[k] : "#555b66";
  document.getElementById("x_" + p.id).textContent = lv == null ? "no reading yet" : ({good:"good", warn:"marginal", bad:"bad"}[k] || "");
}
function lastValue(p) { for (let i = hist.length - 1; i >= 0; i--) { const r = hist[i]; if (!r.busy) { const v = p.get(r); if (v != null) return v; } } return null; }
function drawTimeline(p) {
  const cv = document.getElementById("c_" + p.id), [g, w, h] = sizeCanvas(cv);
  const L = 54, R = 8, now = Date.now() / 1000, t0 = now - span, pw = w - L - R, x = t => L + pw * (t - t0) / span;
  g.clearRect(0, 0, w, h); g.fillStyle = "#eef0f3"; g.fillRect(L, 30, pw, h - 70);
  let prev = null;
  for (const r of hist) { if (r.t < t0) { prev = r; continue; } const s = r.busy ? (prev && prev.state) : r.state;
    const a = prev ? Math.max(x(prev.t), L) : x(r.t); g.fillStyle = C[stateColour(s || "unsettled")]; g.fillRect(a, 30, Math.max(1, x(r.t) - a + 0.5), h - 70); prev = r.busy ? (prev ? Object.assign({}, prev, {t:r.t}) : r) : r; }
  g.fillStyle = "#555b66"; g.font = "12px system-ui"; g.textAlign = "center";
  g.fillText("-" + (span >= 3600 ? (span / 3600) + " h" : (span / 60) + " min"), L + 20, h - 22); g.fillText("now", w - R - 14, h - 22);
  let lost = 0, n = 0, run = null; for (const r of hist) { if (r.t < t0 || r.busy) continue; n++; const bad = r.state == "lost" || r.state == "nocarrier";
    if (bad && !run) lost++; run = bad; }
  const s = last && !last.busy ? last.state : null, e = document.getElementById("v_" + p.id);
  e.textContent = s ? (STATES[s] || STATES.unsettled)[0] : "-"; e.style.color = s ? C[stateColour(s)] : "#555b66";
  document.getElementById("x_" + p.id).textContent = n ? lost + " loss" + (lost == 1 ? "" : "es") + " in this window" : "";
}
function drawScatter(p) {
  const cv = document.getElementById("c_" + p.id), [g, w, h] = sizeCanvas(cv), cx = w / 2, cy = h / 2, sc = Math.min(w, h) / 2 / 0.35;
  g.clearRect(0, 0, w, h); g.strokeStyle = "#c9ccd2"; g.beginPath(); g.moveTo(10, cy); g.lineTo(w - 10, cy); g.moveTo(cx, 5); g.lineTo(cx, h - 5); g.stroke();
  g.fillStyle = "#555b66"; g.font = "12px system-ui"; g.fillText("I", w - 18, cy - 6); g.fillText("Q", cx + 6, 14);
  const ref = last && last.leg_ref_mv ? last.leg_ref_mv / 1000 : 0.16;
  for (const sgn of [-1, 1]) { g.strokeStyle = C.good; g.lineWidth = 2; g.beginPath(); g.arc(cx + sgn * ref * sc, cy, 0.035 * sc, 0, 7); g.stroke(); }
  const t0 = Date.now() / 1000 - Math.min(span, 120);
  for (const r of hist) { if (r.t < t0 || !r.adc || !r.slow_now) continue; const i = r.adc.I - (r.i0 || 1.6535), q = r.adc.Q - (r.q0 || 1.628);
    g.fillStyle = C[stateColour(r.state)]; g.globalAlpha = 0.75; g.beginPath(); g.arc(cx + i * sc, cy - q * sc, 3.5, 0, 7); g.fill(); g.globalAlpha = 1; }
  document.getElementById("v_" + p.id).textContent = "";
  document.getElementById("x_" + p.id).textContent = "the last " + Math.min(span, 120) / 60 + " min of slow readings; rings: where the locked, idle carrier sits";
}
function drawAll() { for (const p of PANELS) { try { if (p.kind == "timeline") drawTimeline(p); else if (p.kind == "scatter") drawScatter(p); else drawSeries(p); } catch (e) { console.log(e); } } }
function status() {
  const st = document.getElementById("status"), r = last;
  if (!r) return;
  let key = r.error ? "error" : r.busy ? "busy" : (r.state || "unsettled");
  if (r.busy) { for (let i = hist.length - 1; i >= 0; i--) if (!hist[i].busy && hist[i].state) { key = hist[i].state; break; } }
  const s = STATES[key] || STATES.unsettled; st.style.borderLeftColor = C[s[1]];
  document.getElementById("word").textContent = s[0]; document.getElementById("word").style.color = C[s[1]];
  document.getElementById("why").textContent = s[2]; document.getElementById("todo").textContent = s[3];
  const since = r.state_since ? Math.round(Date.now() / 1000 - r.state_since) : null;
  const dr = r.driving || {}, ago = dr.t ? Math.round(Date.now() / 1000 - dr.t) : null;
  const L = r.linkd, rec = !L ? "Automatic recovery: not running on this board." :
     "Automatic recovery: " + L.mode + ". " + L.losses + " loss" + (L.losses == 1 ? "" : "es") + ", " + L.recoveries + " recovered" +
     (L.failed ? ", " + L.failed + " failed tries" : "") + (L.last_recovery_s != null ? " (the last in " + L.last_recovery_s.toFixed(1) + " s)" : "") +
     (L.next_try_in_s != null ? "; trying again in " + Math.round(L.next_try_in_s) + " s" : "") + ".";
  document.getElementById("small").textContent = (since != null ? "In this state for " + dur(since) + ". " : "") +
     (ago != null && ago < 30 ? "Being driven now by " + dr.peer + " (" + (dr.name || dr.op) + "). " : "No program is driving the board. ") +
     rec + (r.gw_lock ? " The board's own lock monitor: " + r.gw_lock.state + " (" + r.gw_lock.losses + " losses, " +
     dur(r.gw_lock.seconds_locked) + " locked since power-up)." : "") + (r.error ? " Detail: " + r.error : "");
  if (L && L.mode == "recovering") { document.getElementById("word").textContent = "Recovering";
     document.getElementById("why").textContent = "The link was lost; the board is bringing it back by itself (it re-centres its loop and starts it just above the carrier).";
     document.getElementById("todo").textContent = "Wait a few seconds."; }
  if (L && L.mode == "backing off") { document.getElementById("todo").textContent =
     "The automatic recovery could not find the carrier and will try again. Check that the other board is on and transmitting, and that the antennas face each other."; }
  document.getElementById("meta").textContent = "firmware " + (r.id || "?") + (r.rx_mhz ? ", carrier " + r.rx_mhz + " MHz" : "") +
     (r.dsa_db != null ? ", attenuator " + r.dsa_db + " dB" : "") + ", updated " + new Date(r.t * 1000).toLocaleTimeString();
}
function dur(s) { return s < 90 ? s + " s" : s < 5400 ? Math.round(s / 60) + " min" : (s / 3600).toFixed(1) + " h"; }
async function events() { try { const ev = await (await fetch("/api/events")).json();
  const el = document.getElementById("events");
  el.innerHTML = ev.length ? ev.slice().reverse().slice(0, 20).map(e => "<div><span style='color:" +
     (e.kind == "recovered" ? C.good : e.kind == "loss" ? C.bad : C.warn) + "'>\u25cf</span> " +
     new Date(e.t * 1000).toLocaleString() + ": " + e.text + "</div>").join("") : "Nothing since the page's server started."; } catch (e) {} }
document.getElementById("evhelp").onclick = () => { document.getElementById("dlgt").textContent = "What happened";
  document.getElementById("dlgb").innerHTML = "<p>The board's own record of losses and recoveries, newest first: when the lock was lost, " +
  "how far the oscillator had gone, and how long the board took to bring it back by itself.</p><p class='k'>Good: few entries, each loss " +
  "followed by 'Locked again' within seconds.</p><p><b>Many losses:</b> strong interference or a weak signal (see the plots). <b>A loss " +
  "without a recovery, or repeated 'found no carrier':</b> check that the other board is on and that the antennas face each other.</p>"; dlg.showModal(); };
async function load() { try { hist = await (await fetch("/api/history?s=" + span)).json(); last = hist[hist.length - 1]; status(); drawAll(); } catch (e) {} }
async function tick() { try { const r = await (await fetch("/api/now")).json(); if (r && r.t && (!last || r.t > last.t)) { hist.push(r); last = r;
    const t0 = Date.now() / 1000 - span; while (hist.length && hist[0].t < t0) hist.shift(); } status(); drawAll(); }
  catch (e) { document.getElementById("meta").textContent = "cannot reach the board's server (restarting, or the network?)"; } }
window.onresize = drawAll; load(); events(); setInterval(tick, 1000); setInterval(events, 5000);
</script></body></html>
"""
