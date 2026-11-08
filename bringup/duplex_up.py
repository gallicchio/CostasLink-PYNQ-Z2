"""linkd's duplex mode on the bench: one keeper a board (linkd.LinkD with "duplex": true, run from the laptop against its
own board only, as each station's laptop will in the courtyard), both brought up from nothing at the same time, then:
  1. the beam blocked: A's TX muted 3 s -> B's keeper must recover after it returns, A's lock must hold throughout
  2. the return blocked: B's TX muted 3 s -> A recovers, B holds
  3. the far board gone: B parked and muted 10 s (a power cycle), B's keeper set up again from nothing while A's keeper
     waits for the carrier and re-locks on it
    python3 duplex_up.py [--a_tx 4800 --a_rx 5000]      (B's TX / RX are the mirror)"""
import json
import os
import sys
import threading
import time

BR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BR)
sys.path.insert(0, os.path.join(os.path.dirname(BR), "gateware", "driver"))
import twoboard as T                                      # noqa: E402
import linkd                                              # noqa: E402

say = T.say


class Keeper:
    """a board's loop kept by linkd's own code, here on the laptop, in duplex mode"""
    def __init__(self, node, tx_mhz, rx_mhz):
        self.node, self.tx_mhz, self.rx_mhz = node, float(tx_mhz), float(rx_mhz)
        (vi, vq), _ = node.vr(self.tx_mhz)
        self.cfg = dict(T.LINK_CFG, duplex=True, tx_mhz=self.tx_mhz, rx_mhz=self.rx_mhz, vr={"VR_I": vi, "VR_Q": vq},
                        track_windows=False)
        if node.name in T.Q_OFF_F_V:
            self.cfg["q_off_f"] = T.Q_OFF_F_V[node.name]
        path = os.path.join(T.DATA, "cfg_%s_duplex_%d_%d.json" % (node.name, int(self.tx_mhz), int(self.rx_mhz)))
        json.dump(self.cfg, open(path, "w"))
        self.ld = linkd.LinkD(T._Srv(node.cl), config=path)
        self.lock = threading.Lock()                      # one caller on the board's socket at a time
        self.stop = False
        self.log = []                                     # (t, mode) changes
        self.thread = None

    def run(self):
        last = None
        while not self.stop:
            with self.lock:
                try:
                    self.ld.step()
                except Exception as e:                    # noqa: BLE001
                    self.ld.mode = "error: %r" % (e,)
            if self.ld.mode != last:
                last = self.ld.mode
                self.log.append((time.time(), last))
                say("   keeper %s: %s" % (self.node.name, last))
            time.sleep(0.2)

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name="keeper-" + self.node.name)
        self.thread.start()

    def locked(self):
        with self.lock:
            o = self.ld.observe()
        return bool(o["locked"]), o

    def info(self):
        ld = self.ld
        return {"mode": ld.mode, "dsa": self.node.cl._dsa_db, "leg_mv": 1e3 * ld.leg if ld.leg else None, "vc_lock": ld.vc_lock,
                "set_up": ld.set_up, **ld.counts}


def watch(k, seconds, label):
    """k's lock sampled 5 times a second for `seconds`: the fraction locked and the longest gap"""
    t0 = time.time()
    n = n_ok = 0
    gap = worst = 0.0
    t_last_ok = t0
    while time.time() - t0 < seconds:
        ok, _ = k.locked()
        n += 1
        if ok:
            n_ok += 1
            t_last_ok = time.time()
            gap = 0.0
        else:
            gap = time.time() - t_last_ok
            worst = max(worst, gap)
        time.sleep(0.2)
    say("   %s: %s locked %d of %d looks, longest gap %.1f s" % (label, k.node.name, n_ok, n, worst))
    return {"label": label, "looks": n, "locked": n_ok, "longest_gap_s": worst}


def until_locked(k, timeout, label):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if k.ld.set_up and k.ld.mode == "locked":
            ok, o = k.locked()
            if ok:
                say("   %s: %s locked again after %.1f s (mode %s, VC %.4f, di %.1f mV)" % (label, k.node.name, time.time() - t0, k.ld.mode, o["vc"], 1e3 * o["di"]))
                return time.time() - t0
        time.sleep(0.1)
    say("   %s: %s NOT locked after %.0f s (mode %s)" % (label, k.node.name, timeout, k.ld.mode))
    return None


def main():
    a_tx = float(sys.argv[sys.argv.index("--a_tx") + 1]) if "--a_tx" in sys.argv else 4800.0
    a_rx = float(sys.argv[sys.argv.index("--a_rx") + 1]) if "--a_rx" in sys.argv else 5000.0
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out = {"stamp": stamp, "a_tx": a_tx, "a_rx": a_rx, "tests": {}}
    A, B = T.Node("A"), T.Node("B")
    for n in (A, B):
        n.cl.safe()                                       # from nothing: both parked and muted
        # the bench's TRIG A -> (scope tee) -> the other board's TRIG IN with JP203 fitted puts every TX event of one
        # board into the other's Q ladder (contrun 09:22: A's engine 'saw' B's TRIG A pulses 85 ns after its own events,
        # B decoded nothing under A's): TRIG A off on both for the duplex work, TRIG B (rx_decision) kept
        n.cl.wr("TRIG_CFG", 10 | 1 << 9 | 2 << 13)
    kA, kB = Keeper(A, a_tx, a_rx), Keeper(B, a_rx, a_tx)
    try:
        # 0. both keepers at once, from nothing
        say("==== 0. both keepers set up at once from nothing (A: tx %g rx %g; B: tx %g rx %g)" % (a_tx, a_rx, a_rx, a_tx))
        t0 = time.time()
        kA.start()
        kB.start()
        tA = until_locked(kA, 240, "setup")
        tB = until_locked(kB, 240, "setup")
        out["tests"]["setup"] = {"A_s": tA, "B_s": tB, "A": kA.info(), "B": kB.info()}
        say("   setup: A %s s, B %s s; A %s; B %s" % (tA, tB, kA.info(), kB.info()))
        if tA is None or tB is None:
            return
        out["tests"]["steady"] = {"A": watch(kA, 10, "steady"), "B": watch(kB, 10, "steady")}
        # 1. the beam blocked: A's TX muted 3 s
        for label, blocker, victim, holder in (("beam blocked (A's TX muted 3 s)", kA, kB, kA), ("return blocked (B's TX muted 3 s)", kB, kA, kB)):
            say("==== %s" % label)
            with blocker.lock:
                blocker.node.cl.ctrl(tx_dis=1)
            t_mute = time.time()
            holder_watch = {"looks": 0, "locked": 0, "longest_gap_s": 0.0}
            w = threading.Thread(target=lambda: holder_watch.update(watch(holder, 12, "during " + label)), daemon=True)
            w.start()
            time.sleep(3.0)
            with blocker.lock:
                blocker.node.cl.ctrl(tx_dis=0)
            t_back = time.time()
            say("   carrier back after %.1f s; victim %s mode now: %s" % (t_back - t_mute, victim.node.name, victim.ld.mode))
            t_rel = until_locked(victim, 60, label)
            w.join()
            out["tests"][label] = {"relock_s": t_rel, "victim": victim.info(), "holder": holder_watch, "victim_log": [(round(t - t_mute, 1), m) for t, m in victim.log if t >= t_mute - 1]}
            time.sleep(3)
        # 3. the far board gone: B parked and muted 10 s, then its keeper sets up again
        say("==== far board gone: B parked and muted 10 s (its keeper stopped), then B's keeper from nothing again")
        kB.stop = True
        kB.thread.join()
        with kB.lock:
            B.cl.safe()
        t_gone = time.time()
        wA = watch(kA, 10, "A while B is gone")
        say("   A's keeper mode while B is gone: %s" % kA.ld.mode)
        kB2 = Keeper(B, a_rx, a_tx)
        kB2.start()
        tB2 = until_locked(kB2, 240, "B set up again")
        tA2 = until_locked(kA, 120, "A back on B's carrier")
        out["tests"]["far_board_gone"] = {"A_while_gone": wA, "B_setup_s": tB2, "A_relock_s": tA2, "A": kA.info(), "B": kB2.info(),
                                          "A_log": [(round(t - t_gone, 1), m) for t, m in kA.log if t >= t_gone - 1]}
        out["tests"]["steady2"] = {"A": watch(kA, 10, "steady after"), "B": watch(kB2, 10, "steady after")}
        kB2.stop = True
    finally:
        kA.stop = True
        for n in (A, B):
            try:
                n.cl.safe()
            except Exception as e:                        # noqa: BLE001
                say("safe %s: %r" % (n.name, e))
        json.dump(out, open(os.path.join(T.DATA, "duplex_up_%s.json" % stamp), "w"), indent=1, default=str)
        say("saved duplex_up_%s; both quiet" % stamp)


if __name__ == "__main__":
    main()
