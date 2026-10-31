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
leaves it alone.  It records losses, recoveries, failures, how long the last took, in `state()`, for the dashboard.  Settings it
needs from whoever configured the link: the synthesizers' frequencies and the attenuation (the driver's own record
of its last pll_tune and dsa calls), and a lock to learn from.
"""
import threading
import time

V_MID = 1.65
KV_HZ_PER_V_5800 = 457e3
RELOCK_S = 0.2
DAC1, DAC2 = 0x60, 0x61                 # the two AD5696R (costaslink.DAC1, DAC2)


class LinkD:
    STARTS_KHZ = (20, 40, 70, 120)

    def __init__(self, server, idle_s=60.0, poll_s=0.2, off_khz_min=8.0, t_lost=0.5, backoff_s=(5.0, 60.0)):
        self.server = server
        self.idle_s, self.poll_s, self.off_khz_min, self.t_lost = idle_s, poll_s, off_khz_min, t_lost
        self.backoff_s = backoff_s
        self.vc_lock = self.leg = None
        self.i0, self.q0 = 1.6535, 1.628
        self.mode = "starting"
        self.lost_since = None
        self.next_try = 0.0
        self.wait = backoff_s[0]
        self.counts = {"losses": 0, "recoveries": 0, "failed": 0, "last_recovery_s": None, "t_last_loss": None,
                       "t_last_recovery": None, "last_starts": None}
        self.enabled = True

    # ---- for the dashboard ----
    def state(self):
        return {"mode": self.mode, "enabled": self.enabled, "vc_lock": self.vc_lock, "leg": self.leg,
                "lost_for_s": (time.time() - self.lost_since) if self.lost_since else None,
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
        if cl.rd("CTRL") >> 1 & 1:                                   # LOOP_HOLD by software: someone has taken the loop
            self.mode = "parked: the loop is held by a program"
            self.lost_since = None
            return
        o = self.observe()
        now = time.time()
        if o["locked"]:
            self.lost_since = None
            self.wait = self.backoff_s[0]
            self.vc_lock = o["vc"] if self.vc_lock is None else 0.9 * self.vc_lock + 0.1 * o["vc"]
            if o["e_i"] < 50:                                         # idle carrier: the leg is visible
                self.leg = abs(o["di"]) if self.leg is None else 0.9 * self.leg + 0.1 * abs(o["di"])
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
        if self.mode != "backing off" or now >= self.next_try:
            if self.mode not in ("backing off",):
                self.counts["losses"] += 1
                self.counts["t_last_loss"] = now
            self.mode = "recovering"
            t0 = time.time()
            ok, starts = self.recover()
            self.counts["last_starts"] = starts
            if ok:
                self.counts["recoveries"] += 1
                self.counts["last_recovery_s"] = time.time() - self.lost_since
                self.counts["t_last_recovery"] = time.time()
                self.lost_since = None
                self.mode = "locked"
                self.wait = self.backoff_s[0]
            else:
                self.counts["failed"] += 1
                self.mode = "backing off"
                self.next_try = time.time() + self.wait
                self.wait = min(self.backoff_s[1], 2 * self.wait)

    # ---- the recovery (bringup/autolock.py's, on the driver alone) ----
    def recover(self):
        cl = self.server.cl
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
