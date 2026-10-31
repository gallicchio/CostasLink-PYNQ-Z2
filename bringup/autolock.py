#!/usr/bin/env python3
"""autolock.py: the link's automatic recovery, proven from the PC before it goes into the PYNQ and the gateware
(Jason, 2026-10-31: the boards run unattended, operated by physicists who do not know PLLs; "this part just needs to
work reliably without intervention").

The recovery: watch the lock with the comparators and the ADC (no scope); when it has read lost for t_lost without a
break, hold the loop, centre the integrator, set VC 20 kHz above the last VC it was locked at, and release it.  The map
of the unlocked loop (BRINGUP_LOG 4.12, docs/LOCK.md section 6) says why from above: VC falls everywhere above the lock,
down into it, while a loop let go 16-129 kHz below rests in the false lock and one further below runs to the rail.  If a
start does not lock, the next one starts higher (20, 40, 70, 120 kHz above).

    python3 bringup/autolock.py abuse [--mhz F ...] [--reps N] [--kinds K ...]
        every way the bench can break the lock, each followed by the supervisor until it is locked again:
        falselock   released 45 kHz below the lock: the loop rests in the false lock, beating
        rail        released 300 kHz below: VC runs to its bottom rail
        above       released 300 kHz above: it should come down by itself (the supervisor must not get in the way)
        blocked1, blocked10, blocked60   the carrier gone for 1, 10 or 60 s with the loop free (the TX muted)
        cwnear      the B210's CW 20 kHz below the carrier at full power for 3 s (5.5 GHz: 12 of 12 lost, 4.11)
        cwdrag      the B210's CW 10 MHz below at full power for 3 s (pull's drag below: lost without a hold)
        bursts      8 MHz noise bursts, 100 us every 10 ms at full power for 10 s: the supervisor must do nothing
        Each trial's record: what was done, the state after it, when the supervisor saw the loss, how many starts it
        took, and the time from the disturbance's end to locked again.  bringup/data/board_A/autolock/.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import weekend as W                                  # noqa: E402
import linktests as LT                               # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "autolock")
KINDS = ("falselock", "rail", "above", "blocked1", "blocked10", "blocked60", "cwnear", "cwdrag", "bursts")


def save(name, obj):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "%s_%s.json" % (name, time.strftime("%Y%m%d_%H%M%S")))
    with open(p, "w") as f:
        json.dump(obj, f, indent=1, default=float)
    return p


class AutoLock(W.Weekend):
    STARTS_KHZ = (20, 40, 70, 120)                   # above the last lock, in order

    # ---- the detector ----
    def locked(self, st):
        o = self.observe(st["cen"], st["a"])
        return o["state"] in ("locked", "slipped"), o

    # ---- the recovery ----
    def release_at(self, mhz, st, vc, settle_s=1.5):
        """hold, centre the integrator (at 5.8 GHz, the TX muted), VC to `vc`, the TX on, release; poll the lock"""
        cl = self.cl
        cl.ctrl(loop_hold=1)
        self.tx(False)
        self.center(mhz)
        cl.dsa(float(st["dsa"]))
        self.set_vc(vc)
        self.tx(True)
        time.sleep(0.05)
        cl.ctrl(loop_hold=0)
        t0 = time.time()
        o = None
        while time.time() - t0 < settle_s:
            ok, o = self.locked(st)
            if ok:
                return True, time.time() - t0, o
            time.sleep(0.05)
        return False, settle_s, o

    def recover(self, mhz, st):
        tries = []
        for k in self.STARTS_KHZ:
            vc = st["vc_lock"] + k * 1e3 / self.kv(mhz)
            ok, t, o = self.release_at(mhz, st, vc)
            tries.append({"start_khz": k, "ok": ok, "t_s": t, "state": o and o["state"], "vc": o and o["vc"]})
            if ok:
                st["vc_lock"] = o["vc"]
                st["side"] = o["side"]
                return True, tries
        return False, tries

    def supervise(self, mhz, st, seconds=30.0, t_lost=0.5, until_locked=True, poll_s=0.1):
        """watch for `seconds`; after t_lost of lost without a break, recover.  until_locked: stop at the first
        locked look after a recovery (or at once if locked).  Returns the events"""
        t0 = time.time()
        lost_since = None
        ev = {"looks": 0, "lost_looks": 0, "recoveries": [], "t_locked": None}
        while time.time() - t0 < seconds:
            ok, o = self.locked(st)
            ev["looks"] += 1
            now = time.time() - t0
            if ok:
                lost_since = None
                st["vc_lock"] = 0.9 * st["vc_lock"] + 0.1 * o["vc"]          # follow a slow drift of the far end
                if until_locked:
                    ev["t_locked"] = now
                    return ev
            else:
                ev["lost_looks"] += 1
                if lost_since is None:
                    lost_since = now
                elif now - lost_since >= t_lost:
                    good, tries = self.recover(mhz, st)
                    ev["recoveries"].append({"at_s": now, "lost_for_s": now - lost_since, "ok": good, "tries": tries})
                    lost_since = None
            time.sleep(poll_s)
        return ev

    # ---- the abuse ----
    def induce(self, kind, mhz, st):
        cl = self.cl
        kv = self.kv(mhz)
        if kind in ("falselock", "rail", "above"):
            k = {"falselock": -45, "rail": -300, "above": 300}[kind]
            self.release_at(mhz, st, st["vc_lock"] + k * 1e3 / kv, settle_s=0.0)
            time.sleep(2.0)
            return {"released_khz": k}
        if kind.startswith("blocked"):
            T = float(kind[len("blocked"):])
            cl.ctrl(tx_dis=1)
            time.sleep(T)
            self.tx(True)
            return {"blocked_s": T}
        if kind == "cwnear":
            th = self.bg(self.bb.tone, mhz + 2.0, gain=89.75, seconds=3.0, offset_hz=-20e3 - 2e6, rate=5e6)
            th.join(timeout=8)
            return {"cw_khz": -20, "gain": 89.75}
        if kind == "cwdrag":
            th = self.bg(self.bb.tone, mhz - 10.0, gain=89.75, seconds=3.0)
            th.join(timeout=8)
            return {"cw_mhz": -10, "gain": 89.75}
        raise ValueError(kind)

    def abuse_trial(self, kind, mhz, st):
        """one disturbance and the supervisor after it; bursts are supervised while they run"""
        if kind == "bursts":
            th = self.bg(self.bb.bursts, mhz, gain=89.75, bw_mhz=8.0, on_ms=0.1, off_ms=9.9, seconds=10.0)
            ev = self.supervise(mhz, st, seconds=10.0, until_locked=False)
            th.join(timeout=15)
            ok, o = self.locked(st)
            return {"kind": kind, "events": ev, "after": o["state"], "back_s": 0.0 if ok else None,
                    "acted": len(ev["recoveries"])}
        info = self.induce(kind, mhz, st)
        t_end = time.time()
        ok0, o0 = self.locked(st)
        ev = self.supervise(mhz, st, seconds=60.0)
        back = ev["t_locked"]
        return {"kind": kind, **info, "state_after_disturbance": o0["state"], "vc_after_disturbance": o0["vc"],
                "events": ev, "back_s": (time.time() - t_end) if back is not None else None,
                "starts": sum(len(r["tries"]) for r in ev["recoveries"])}

    def abuse(self, mhz, kinds=KINDS, reps=3):
        out = {"mhz": mhz, "trials": []}
        st = self.ready(mhz)
        if st is None:
            out["error"] = "no lock"
            return out
        st["vc_lock"] = self.cl.adc("VC")
        out.update(dsa=st["dsa"], a_leg=st["a"], vc_lock=st["vc_lock"])
        for kind in kinds:
            for r in range(reps):
                ok, _ = self.locked(st)
                if not ok:
                    good, _ = self.recover(mhz, st)
                    if not good:
                        out["trials"].append({"kind": kind, "error": "not locked before the trial"})
                        continue
                tr = self.abuse_trial(kind, mhz, st)
                tr["rep"] = r
                out["trials"].append(tr)
                ev = tr["events"]
                print("%d %-10s #%d: after the disturbance %-8s | %s" % (
                    mhz, kind, r, tr.get("state_after_disturbance", "-"),
                    ("back in %.1f s, %d start(s)" % (tr["back_s"], tr.get("starts", 0))) if tr["back_s"] is not None and kind != "bursts"
                    else ("supervisor acted %d times, after: %s" % (tr["acted"], tr["after"])) if kind == "bursts"
                    else "NOT BACK in 60 s (%d recoveries tried)" % len(ev["recoveries"])), flush=True)
                save("abuse_partial", out)
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["abuse"])
    ap.add_argument("--mhz", type=int, nargs="*", default=list(W.CARRIERS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--kinds", nargs="*", default=list(KINDS))
    a = ap.parse_args(argv)
    A = AutoLock()
    for mhz in a.mhz:
        A.piece("abuse", A.abuse, mhz, kinds=a.kinds, reps=a.reps)
    try:
        A.b.sa_live()
    except Exception:                                            # noqa: BLE001
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
