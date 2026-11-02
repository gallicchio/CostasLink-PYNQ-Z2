"""linkd.py: the link's automatic recovery on the board itself, in the board server on the PYNQ (`netbus.py serve
--linkd`).  Jason, 2026-10-31: the boards run unattended, operated by physicists who do not know PLLs; "this part
just needs to work reliably without intervention."  The algorithm is bringup/autolock.py's, proven on the bench
from the PC (BRINGUP_LOG 4.15: 108 of 108 forced losses back in 1.7-3.0 s, one start each): this is the same with
only the driver beneath it, so it runs with no PC, no network and nobody watching.

What it does.  About five times a second, when no program has driven the board for `idle_s` (60 s: whoever drives
it owns it, so it never fights a test or a person), it looks at the lock with the comparators and the slow ADC:
locked when CMP_I is quiet with the I leg up, or when both Q windows are quiet with Q near its middle (the link's own
BPSK data moves along I only).  While locked it learns VC at lock, the I leg and the arms' middles.  It calls the
link lost when VC has been more than `off_khz_min` (8 kHz) from the learned lock for `t_lost` (0.5 s): every real
loss moves VC tens of kHz (the false lock 45 kHz below, the rail hundreds, a drag, the carrier gone), and a lost loop
cannot stay within 8 kHz of the lock, where it pulls in (the map of BRINGUP_LOG 4.12); noise bursts make the
comparators chatter but leave VC where it is.  Then it recovers: hold the loop; re-centre its integrator (both
synthesizers to 5.8 GHz, the TX muted, stages.loop_center's trims); back on the link's frequencies and attenuation;
VC 20 kHz above the learned lock; release; from above, the unlocked loop always comes down into the lock (the map).
If that start does not lock, 40, 70 and 120 kHz above.  A failed recovery (the far board off, the path blocked)
backs off: 5 s, doubling to 60 s, so it does not thrash.  The TX's mode is left as it was: only TX_DIS is restored.

A loop held by software (CTRL's LOOP_HOLD) is parked on purpose (a test setting up, the bench's quiet state): linkd
leaves it alone.  It records losses, recoveries, failures, how long the last took, in `state()`, for the dashboard.

Setting the link up from nothing (the board just powered, the server just started): when link.json sits beside the
server, linkd does it first, before anyone asks.  link.json: {"mhz": 5200 (or "tx_mhz" and "rx_mhz" apart: two boards
as two one-way links, MONDAY.md 5), "vr": {"VR_I": .., "VR_Q": ..} (the TX
carrier's null at that frequency, from the board's calibration), "leg_target": 0.15, "window_frac": 0.5, "v_t2": 2.9,
"dsa_min": 6.0}.  Both synthesizers to the carrier, the TX at its idle point; with no carrier (TX muted, DSA 31.75)
the arms' middles on the ADC and each window comparator's centre (Rice's parabola, stage 3.7); then the attenuation
stepped down from 31.75 dB in 2 dB steps, the loop released 60 kHz above the nominal lock at each (the map: from
above it comes down into the lock), until it locks with the I leg at leg_target or more; the windows at window_frac
of the leg, V_T2.  If it finds no carrier (the far board off, the path blocked) it backs off and tries again.
Without link.json it waits for someone to set the link up, and learns from the first lock it sees.
"""
import json
import os
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
V_MID = 1.65
VC_NOMINAL = 1.861                       # VC with the VCXO on the TCXO's frequency (bringup/linktests.py VC_LOCK)
KV_HZ_PER_V_5800 = 457e3
RELOCK_S = 0.2
DAC1, DAC2 = 0x60, 0x61                 # the two AD5696R (costaslink.DAC1, DAC2)
CAL_FILE = os.path.join(HERE, "windows.json")    # each lock point's calibration, kept across a restart


class LinkD:
    STARTS_KHZ = (20, 40, 70, 120)

    def __init__(self, server, idle_s=60.0, poll_s=0.2, off_khz_min=8.0, t_lost=0.5, backoff_s=(5.0, 60.0), config=None):
        self.server = server
        path = config or os.path.join(HERE, "link.json")
        try:
            with open(path) as f:
                self.cfg = json.load(f)
        except (OSError, ValueError):
            self.cfg = None
        self.set_up = self.cfg is None                   # nothing to set up: learn from the first lock seen
        self.setup_next = 0.0
        self.setup_wait = backoff_s[0]
        self.idle_s, self.poll_s, self.off_khz_min, self.t_lost = idle_s, poll_s, off_khz_min, t_lost
        self.backoff_s = backoff_s
        self.vc_lock = self.leg = None
        self.i0, self.q0 = 1.6535, 1.628
        self.mid_t = None                                # when the arms' middles were measured (setup)
        self.cen = None                                  # each window comparator's centre (setup)
        self.leg_windows = None                          # the leg the windows were last set for
        self.leg_setup = None                            # the leg setup set them for: the most they follow
        self.cal = None                                  # the windows from the states' levels: {side, leg, off, t}
        self.cal_by_side = {}                            # each lock point's own, kept across the loop's changes of point
        self.mode = "starting"
        self.lost_since = None
        self.next_try = 0.0
        self.wait = backoff_s[0]
        self._loss_open = False                          # a loss counted and not yet recovered
        self.counts = {"losses": 0, "recoveries": 0, "failed": 0, "last_recovery_s": None, "t_last_loss": None,
                       "t_last_recovery": None, "last_starts": None, "window_moves": 0, "calibrations": 0}
        self.enabled = True

    # ---- for the dashboard ----
    def state(self):
        return {"mode": self.mode, "enabled": self.enabled, "vc_lock": self.vc_lock, "leg": self.leg, "leg_windows": self.leg_windows, "leg_setup": self.leg_setup,
                "cal": ({"side": self.cal["side"], "leg": self.cal["leg"], "t": self.cal["t"],
                         "restored": bool(self.cal.get("restored")),
                         "thresholds_mv": {w: round(1e3 * (v - self.cen[w]), 1) for w, v in self.thresholds().items()}}
                        if self.cal else None), "config": self.cfg, "idle_s": self.idle_s,
                "lost_for_s": (time.time() - self.lost_since) if self.lost_since else None,
                "i0": self.i0, "q0": self.q0, "mid_t": self.mid_t,
                "next_try_in_s": max(0.0, self.next_try - time.time()) if self.mode == "backing off" else None,
                **self.counts}

    # ---- the looks ----
    def driving(self):
        t = self.server.last.get("t")
        return t is not None and time.time() - t < self.idle_s

    def kv(self):
        f = self.server.cl._pll.get(1, (5800.0,))[0]
        return KV_HZ_PER_V_5800 * f / 5800.0

    def observe(self):
        cl = self.server.cl
        g = cl.gate(seconds=0.01, inputs=("CMP_I", "CMP_QP", "CMP_QN"))
        i, q, vc = cl.adc("I"), cl.adc("Q"), cl.adc("VC")
        di, dq = i - self.i0, q - self.q0
        a = self.leg or 0.1
        e_i, e_q = g["CMP_I"]["edges"], g["CMP_QP"]["edges"] + g["CMP_QN"]["edges"]
        locked = (e_i < 50 and abs(di) > 0.5 * a and abs(dq) < 0.35 * a) or (e_q < 20 and abs(dq) < 0.35 * a and abs(di) > 0.03)
        return {"locked": locked, "di": di, "dq": dq, "vc": vc, "e_i": e_i, "e_q": e_q}

    def step(self):
        cl = self.server.cl
        if not self.set_up:
            if time.time() < self.setup_next:
                return
            self.led(recovering=True)
            try:
                ok = self.setup(self.cfg)
            finally:
                self.led(recovering=False)
            if ok:
                self.set_up = True
                self.mode = "locked"
                self.setup_wait = self.backoff_s[0]
            else:
                self.mode = "setup found no carrier: trying again"
                self.setup_next = time.time() + self.setup_wait
                self.setup_wait = min(self.backoff_s[1], 2 * self.setup_wait)
            return
        if cl.rd("CTRL") >> 1 & 1:                                   # LOOP_HOLD by software: someone has taken the loop
            self.mode = "parked: the loop is held by a program"
            self.lost_since = None
            return
        o = self.observe()
        now = time.time()
        # locked by the comparators but far from the learned lock: locked to something else (a strong CW captured the
        # loop: soak14 #50, a CW 9.7 MHz away at gain 87 held it 600 kHz off with I up and Q quiet), so not learned
        # from (one such look pulled the learned VC 70 kHz down, the recovery then started there and took 7.9 s, and
        # the page's offset crept back for 20 s) and judged by VC below like any other drag
        if o["locked"] and self.vc_lock is not None and abs(o["vc"] - self.vc_lock) * self.kv() / 1e3 > self.off_khz_min:
            o["locked"] = False
        if o["locked"]:
            if self._loss_open:                                     # back by itself (the carrier returned near the lock)
                self._loss_open = False
                self.counts["recoveries"] += 1
                self.counts["last_recovery_s"] = (now - self.lost_since) if self.lost_since else None
                self.counts["t_last_recovery"] = now
                self.counts["last_starts"] = 0
            self.lost_since = None
            self.wait = self.backoff_s[0]
            self.vc_lock = o["vc"] if self.vc_lock is None else 0.9 * self.vc_lock + 0.1 * o["vc"]
            # idle carrier: the leg is visible.  Not while the self-test sends: OOK's nulls leave the sign of I quiet,
            # so its data passed for the idle and the leg read 107-165 mV for a 173 mV carrier, the windows moved six
            # times in 15 s and the calibration was dropped (2026-11-01 11:23)
            st = getattr(self.server, "selftest", None)
            if o["e_i"] < 50 and not (st is not None and getattr(st, "_busy", False)):
                self.leg = abs(o["di"]) if self.leg is None else 0.9 * self.leg + 0.1 * abs(o["di"])
                self.track_windows(cl, 1 if o["di"] > 0 else -1)
            self.mode = "locked"
            return
        if self.vc_lock is None:
            self.mode = "waiting for a first lock"
            return
        off_khz = abs(o["vc"] - self.vc_lock) * self.kv() / 1e3
        if self.lost_since is None:
            self.lost_since = now
        if off_khz <= self.off_khz_min or now - self.lost_since < self.t_lost:
            self.mode = "watching"
            return
        if not self._loss_open:                               # one loss, however many tries it takes
            self.counts["losses"] += 1
            self.counts["t_last_loss"] = now
            self._loss_open = True
        # no carrier at all (the board's lock monitor: nothing arrives): a recovery cannot find one, so do not try,
        # and do not back off: start the moment one is seen again.  Trying held the board 11 s for four starts with the
        # carrier gone, then waited out 5 s of back-off after it came back (soak13 #12: locked 7 s after the carrier
        # returned, 18 s after the loss)
        if self.no_carrier():
            self.mode = "waiting for the carrier"
            self.next_try = 0.0
            return
        if self.mode != "backing off" or now >= self.next_try:
            self.mode = "recovering"
            t0 = time.time()
            self.led(recovering=True)
            try:
                ok, starts = self.recover()
            finally:
                self.led(recovering=False)
            self.counts["last_starts"] = starts
            if ok:
                # the lock the recovery came down into from above is the carrier's: learn its VC afresh (a learned VC
                # gone wrong would otherwise make every true lock look 'far' and be recovered again)
                time.sleep(0.2)
                self.vc_lock = self.server.cl.adc("VC")
                self.counts["recoveries"] += 1
                self.counts["last_recovery_s"] = time.time() - self.lost_since
                self.counts["t_last_recovery"] = time.time()
                self.lost_since = None
                self._loss_open = False
                self.mode = "locked"
                self.wait = self.backoff_s[0]
            else:
                self.counts["failed"] += 1
                self.mode = "backing off"
                self.next_try = time.time() + self.wait
                self.wait = min(self.backoff_s[1], 2 * self.wait)

    def no_carrier(self):
        """the lock monitor's 'no carrier' (ID 8 on: the I windows dark and Q still), else unknown: False"""
        cl = self.server.cl
        if not getattr(cl, "lockmon", False):
            return False
        try:
            return cl.lock_state().get("state") == "no carrier"
        except Exception:                                        # noqa: BLE001
            return False

    def led(self, recovering):
        """LD5 blue while recovering (ID version 8's LEDs; nothing on older overlays)"""
        cl = self.server.cl
        if getattr(cl, "lockmon", False):
            cl.leds(auto=True, ld5=(0, 0, 1) if recovering else (0, 0, 0))

    # ---- the link from nothing ----
    def setup(self, cfg):
        cl = self.server.cl
        self.cal = None                                  # new centres: the self-test calibrates again
        self.cal_by_side = {}
        # one carrier both ways (one board to itself), or two apart (two boards, each receiving the other's TX: the TX
        # synthesizer on tx_mhz, the RX one on rx_mhz; VR, the TX's carrier null, belongs to tx_mhz)
        tx_mhz = float(cfg.get("tx_mhz", cfg.get("mhz")))
        rx_mhz = float(cfg.get("rx_mhz", cfg.get("mhz")))
        self.mode = ("setting up the link at %g MHz" % rx_mhz if tx_mhz == rx_mhz else
                     "setting up the link: receiving at %g MHz, sending at %g MHz" % (rx_mhz, tx_mhz))
        cl.ctrl(loop_hold=1, tx_dis=1)
        cl.pll_tune(0, tx_mhz)
        cl.pll_tune(1, rx_mhz)
        time.sleep(RELOCK_S)
        vr = cfg.get("vr")
        if vr:
            cl.dac(DAC1, VR_I=float(vr["VR_I"]), VR_Q=float(vr["VR_Q"]))
        cl.hold_point(1, 0)
        cl.dsa(31.75)
        time.sleep(0.1)
        self.i0 = sum(cl.adc("I") for _ in range(8)) / 8.0
        self.q0 = sum(cl.adc("Q") for _ in range(8)) / 8.0
        self.mid_t = time.time()
        cen = {}
        for w in ("QP", "QN", "IP", "IN"):
            vs = [V_MID - 0.06 + 0.002 * k for k in range(61)]
            try:
                cen[w] = cl.rice_fit([p for p in cl.threshold_scan(w, vs, seconds=0.02) if p[1] > 0])[0]
            except ValueError:
                cen[w] = V_MID
        self.cen = cen
        target = float(cfg.get("leg_target", 0.15))
        pll = dict(cl._pll)
        self.vc_lock = VC_NOMINAL
        dsa, floor, got = 31.75, float(cfg.get("dsa_min", 6.0)), None
        while dsa >= floor - 1e-9:
            if self.release_at(VC_NOMINAL + 60e3 / self.kv(), pll, dsa, 0):
                leg = abs(self.observe()["di"])
                got = (dsa, leg)
                if leg >= target:
                    break
            dsa -= 2.0
        if got is None:
            cl.ctrl(loop_hold=1, tx_dis=1)
            return False
        if abs(dsa - got[0]) > 1e-9:                      # the last step did not lock: back to the best one
            self.release_at(VC_NOMINAL + 60e3 / self.kv(), pll, got[0], 0)
        di = self.observe()["di"]
        a = abs(di)
        frac = float(cfg.get("window_frac", 0.5))
        for w, v0 in cen.items():
            cl.threshold(w, min(2.499, max(0.0, v0 + frac * a)))
        cl.dac(DAC2, V_T2=float(cfg.get("v_t2", 2.9)))
        self.vc_lock = cl.adc("VC")
        self.leg = self.leg_windows = self.leg_setup = a
        # the calibrations kept across a restart: this lock point's put back now, near its level (waiting for an idle
        # look, with the self-test sending at once, left a QPSK run 6.4 % lost on the plain windows, 19:35:57)
        self.cal_by_side = self._load_cal(cfg)
        self.track_windows(cl, 1 if di > 0 else -1)
        return True

    def _cal_link(self, cfg):
        return {k: (cfg or {}).get(k) for k in ("mhz", "tx_mhz", "rx_mhz", "vr")}

    def _save_cal(self):
        """each lock point's calibration beside the server, as offsets from the window comparators' centres (setup
        measures those again), for the link it was taken on"""
        try:
            with open(CAL_FILE + ".tmp", "w") as f:
                json.dump({"link": self._cal_link(self.cfg), "by_side": {str(s): {k: c[k] for k in ("side", "leg", "off", "t")}
                                                                          for s, c in self.cal_by_side.items()}}, f)
            os.replace(CAL_FILE + ".tmp", CAL_FILE)
        except OSError:
            pass

    def _load_cal(self, cfg):
        """the calibrations kept by _save_cal, if taken on this link (frequencies, VR).  A restart used to start on the
        plain rule's windows until the self-test calibrated again, which the soak's announced trials put off for
        minutes: QPSK lost 6.6-6.9 % a run after a deploy (2026-11-01 19:24), 2.2 % for a minute before (17:47)"""
        try:
            with open(CAL_FILE) as f:
                d = json.load(f)
            if d.get("link") != self._cal_link(cfg):
                return {}
            out = {}
            for s, c in (d.get("by_side") or {}).items():
                if set(c.get("off") or {}) == set(self.cen) and c.get("leg"):
                    out[int(s)] = dict(c, side=int(s), restored=True)
            return out
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def thresholds(self):
        """the window thresholds as linkd sets them: calibrated (the self-test's 'calibrate': each between its states'
        levels) scaled with the leg, or else window_frac of the leg from each comparator's centre"""
        if self.cal:
            f = (self.leg_windows or self.cal["leg"]) / self.cal["leg"]
            return {w: self.cen[w] + self.cal["off"][w] * f for w in self.cen}
        frac = float((self.cfg or {}).get("window_frac", 0.5))
        return {w: self.cen[w] + frac * (self.leg_windows or 0.1) for w in self.cen}

    def set_windows(self, cl, thr, side):
        """the self-test's calibration (selftest.calibrate) on lock point `side`: kept as offsets from the centres"""
        self.leg_windows = self.leg_windows or self.leg
        self.cal = {"side": side, "leg": self.leg_windows, "off": {w: thr[w] - self.cen[w] for w in self.cen},
                    "t": time.time()}
        self.cal_by_side[side] = self.cal
        for w, v in self.thresholds().items():
            cl.threshold(w, min(2.499, max(0.0, v)))
        self.counts["calibrations"] += 1
        self._save_cal()

    def track_windows(self, cl, side=None):
        """the windows follow the carrier's level.  Setup puts them at window_frac of the leg it found; a level that
        changes after (an antenna moved or blocked, the attenuator) left the Q steps of A2 and A3 short of them or far
        past them (2026-11-01 01:12: 148 055 of 199 999 A2 symbols missed while the attenuator was 4.25 dB up, A3 at
        23:51 likewise; A1, the sign of I alone, untouched).  Set again when the leg learned on the idle carrier is
        10 % from the one they were set for; link.json's "track_windows": false keeps them where setup put them.
        Down only, never above where setup put them: with the attenuator 4.25 dB down (the leg 229 mV, not 165) the
        windows raised to half of it lost A3 its corners (2 311 of 199 999 right, 01:36:39): the corners' excursions do
        not grow with the idle's I leg (the chain compressing, the ladders' asymmetry), so a window from the I leg is
        right only for a weaker carrier.  The windows from the states' own levels (the self-test's 'corners') next"""
        if not self.cfg or not self.cfg.get("track_windows", True) or not self.cen or not self.leg_windows or not self.leg:
            return
        own = self.cal_by_side.get(side) if side is not None else None
        near = own is not None and abs(self.leg - own["leg"]) <= 0.15 * own["leg"]
        if side is not None and ((self.cal and side != self.cal["side"]) or (not self.cal and near)):
            # the calibration belongs to the other lock point (the loop slipped or was recovered there), or there is
            # none yet (a restart: the ones kept in windows.json): this point's own, if it has one near this level,
            # else the plain windows until the self-test calibrates it (the plain rule's Q sits past the corners'
            # plateau: QPSK lost 4-11 % after each soak recovery that changed point, 2026-11-01 14:36-14:50, the
            # calibration put off by the soak's announced trials)
            if near:
                self.cal = own
                self.leg_windows = min(self.leg, own["leg"])
            else:
                self.cal = None
                self.leg_windows = min(self.leg, self.leg_setup or self.leg)
            for w, v in self.thresholds().items():
                cl.threshold(w, min(2.499, max(0.0, v)))
            self.counts["window_moves"] += 1
            return
        leg = min(self.leg, self.cal["leg"] if self.cal else (self.leg_setup or self.leg))
        if abs(leg - self.leg_windows) < 0.1 * self.leg_windows:
            return
        self.leg_windows = leg
        for w, v in self.thresholds().items():
            cl.threshold(w, min(2.499, max(0.0, v)))
        self.counts["window_moves"] += 1

    # ---- the recovery (bringup/autolock.py's, on the driver alone) ----
    def recover(self):
        cl = self.server.cl
        # the idle carrier first: data (the self-test's, selftest.py) keeps this detector from ever reading locked
        st = getattr(self.server, "selftest", None)
        if st is not None:
            st.abort(cl)
        pll = dict(cl._pll)
        dsa = cl._dsa_db
        tx_dis = cl.rd("CTRL") & 1
        starts = 0
        try:
            for k in self.STARTS_KHZ:
                starts += 1
                if self.release_at(self.vc_lock + k * 1e3 / self.kv(), pll, dsa, tx_dis):
                    return True, starts
            return False, starts
        finally:
            cl.ctrl(tx_dis=tx_dis)

    def release_at(self, vc, pll, dsa, tx_dis, settle_s=1.5):
        cl = self.server.cl
        cl.ctrl(loop_hold=1, tx_dis=1)
        cl.dsa(31.75)
        cl.pll_tune(0, 5800.0)
        cl.pll_tune(1, 5800.0)
        time.sleep(RELOCK_S)
        self.loop_center()
        for which in (0, 1):
            f, f_pfd, cp = pll.get(which, (5800.0, 25.0, None))
            cl.pll_tune(which, f, f_pfd=f_pfd, cp=cp)
        time.sleep(RELOCK_S)
        cl.dsa(dsa)
        u = 3 * V_MID - cl.adc("VC") - cl.dac_volts()["VC_OFF"]             # the integrator, held
        cl.dac(DAC1, VC_OFF=float(min(3.2, max(0.1, 3 * V_MID - u - vc))))
        time.sleep(0.05)
        cl.ctrl(tx_dis=tx_dis)
        time.sleep(0.05)
        cl.ctrl(loop_hold=0)
        t0 = time.time()
        while time.time() - t0 < settle_s:
            if self.observe()["locked"]:
                return True
            time.sleep(0.05)
        return False

    def loop_center(self, target_v=V_MID, tol_v=0.04, max_steps=10):
        """bringup/stages.py's loop_center on the driver alone: the integrator back to mid-scale with no carrier, by
        the trims that put ERR on the side that moves VC the right way and timed releases of the hold"""
        cl = self.server.cl
        cl.ctrl(loop_hold=1, tx_dis=1)
        cl.dac(DAC1, VC_OFF=V_MID)
        rate = {}
        try:
            for _ in range(max_steps):
                time.sleep(0.05)
                vc = cl.adc("VC")
                if abs(vc - target_v) <= tol_v:
                    return True
                up = vc < target_v
                want = 1 if up else -1
                best = None
                for trims in ({"I_OFF_F": 3.0 if up else 0.3}, {"I_OFF_F": 0.3 if up else 3.0},
                              {"I_OFF_F": 3.0 if up else 0.3, "Q_OFF_F": 0.3 if up else 3.0},
                              {"I_OFF_F": 0.3 if up else 3.0, "Q_OFF_F": 0.3 if up else 3.0}):
                    cl.dac(DAC2, I_OFF_F=trims["I_OFF_F"])
                    cl.dac(DAC1, Q_OFF_F=trims.get("Q_OFF_F", V_MID))
                    time.sleep(0.03)
                    v_a = cl.adc("VC")
                    cl.seq_program([(0.003 / cl.t_clk, {"loop_hold": 0})])       # muted on purpose: no carrier
                    cl.seq_run()
                    time.sleep(0.02)
                    dv = (cl.adc("VC") - v_a) * want
                    if dv > 0.002 and (best is None or dv > best[1]):
                        best = (trims, dv)
                if best is None:
                    return False
                cl.dac(DAC2, I_OFF_F=best[0]["I_OFF_F"])
                cl.dac(DAC1, Q_OFF_F=best[0].get("Q_OFF_F", V_MID))
                time.sleep(0.05)
                err, vc = cl.adc("ERR"), cl.adc("VC")
                rate.setdefault(up, best[1] / 0.003)
                r = rate.get(up, abs(err - V_MID) / 1e-3)
                dt = min(0.5, max(1e-4, abs(target_v - vc) / max(r, 1.0)))
                cl.seq_program([(dt / cl.t_clk, {"loop_hold": 0})])
                cl.seq_run()
                time.sleep(dt + 0.02)
                cl.dac(DAC2, I_OFF_F=V_MID)
                cl.dac(DAC1, Q_OFF_F=V_MID)
                time.sleep(0.05)
                vc2 = cl.adc("VC")
                if abs(vc2 - vc) > 0.02 and 0.02 < abs(vc2 - target_v) and (vc2 - vc) * (target_v - vc) > 0:
                    rate[up] = abs(vc2 - vc) / dt
            return abs(cl.adc("VC") - target_v) <= tol_v
        finally:
            cl.dac(DAC2, I_OFF_F=V_MID)
            cl.dac(DAC1, Q_OFF_F=V_MID)
            cl.ctrl(loop_hold=1)

    # ---- the loop ----
    def run(self):
        while True:
            time.sleep(self.poll_s)
            if not self.enabled:
                self.mode = "off"
                continue
            if self.driving():
                self.mode = "paused: a program is driving the board"
                self.lost_since = None
                continue
            if not self.server.lock.acquire(timeout=0.05):
                continue
            try:
                self.step()
            except Exception as e:                                   # noqa: BLE001 - never stops the server
                self.mode = "error: %s: %s" % (type(e).__name__, str(e)[:120])
            finally:
                self.server.lock.release()

    def start(self):
        threading.Thread(target=self.run, daemon=True, name="linkd").start()
        print("CostasLink linkd: automatic recovery on (idle after %.0f s without a client)" % self.idle_s, flush=True)
        return self
