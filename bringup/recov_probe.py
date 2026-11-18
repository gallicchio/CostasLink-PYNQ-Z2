"""Why did B's duplex keeper fail to recover after a 3 s beam block (duplex_up 09:38) while A's recovered in 1 s?
A's TX on at 4800 (idle), B's keeper (duplex, tx 5400 / rx 4800) set up; then A's TX muted `--mute` s and back, B
watched for `--wait` s (does the loop come back alone?), then B's recover() run by hand with every start reported.
    python3 recov_probe.py [--mute 3] [--wait 5] [--board B] [--other A] [--rx 4800 --tx 5400]"""
import os
import sys
import time

BR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BR)
sys.path.insert(0, os.path.join(os.path.dirname(BR), "gateware", "driver"))
import twoboard as T                                      # noqa: E402
import linkd                                              # noqa: E402
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duplex_up import Keeper                              # noqa: E402

say = T.say


def arg(name, default):
    return type(default)(sys.argv[sys.argv.index(name) + 1]) if name in sys.argv else default


def look(k, label):
    o = k.ld.observe()
    ls = k.node.cl.lock_state() if getattr(k.node.cl, "lockmon", False) else {}
    say("   %-28s locked %s di %+6.1f dq %+6.1f mV vc %.4f e_i %d e_q %d  lockmon %s" % (
        label, o["locked"], 1e3 * o["di"], 1e3 * o["dq"], o["vc"], o["e_i"], o["e_q"], ls.get("state")))
    return o


def main():
    mute, wait = arg("--mute", 3.0), arg("--wait", 5.0)
    bn, on = arg("--board", "B"), arg("--other", "A")
    rx, tx = arg("--rx", 4800.0), arg("--tx", 5400.0)
    B, A = T.Node(bn), T.Node(on)
    for n in (A, B):
        n.cl.safe()
        n.cl.wr("TRIG_CFG", 10 | 1 << 9 | 2 << 13)
    A.send(rx, muted=False)                               # the far carrier, idle
    k = Keeper(B, tx, rx)
    try:
        t0 = time.time()
        ok = k.ld.setup(k.cfg)
        say("%s set up: %s in %.0f s, DSA %.2f, leg %.1f mV, VC %.4f" % (bn, ok, time.time() - t0, B.cl._dsa_db, 1e3 * (k.ld.leg or 0), k.ld.vc_lock))
        if not ok:
            return
        k.ld.set_up = True
        k.ld.mode = "locked"
        for _ in range(3):
            k.ld.step()
            time.sleep(0.3)
        look(k, "steady")
        say("==== %s's TX muted %.0f s" % (on, mute))
        A.cl.ctrl(tx_dis=1)
        t_m = time.time()
        while time.time() - t_m < mute:
            look(k, "muted %.1f s" % (time.time() - t_m))
            time.sleep(0.5)
        A.cl.ctrl(tx_dis=0)
        t_b = time.time()
        say("==== carrier back; %s alone for %.0f s (no keeper step)" % (bn, wait))
        while time.time() - t_b < wait:
            look(k, "back %.1f s" % (time.time() - t_b))
            time.sleep(0.5)
        o = k.ld.observe()
        if o["locked"]:
            say("   back by itself")
        say("==== recover() by hand: starts at vc_lock %.4f + 20 / 40 / 70 / 120 kHz, DSA %.2f" % (k.ld.vc_lock, B.cl._dsa_db))
        cl = B.cl
        pll = dict(cl._pll)
        dsa = cl._dsa_db
        starts = [float(x) for x in arg("--starts", "20,40,70,120").split(",")]
        for khz in starts:
            vc = k.ld.vc_lock + khz * 1e3 / k.ld.kv()
            t1 = time.time()
            ok = k.ld.release_at(vc, pll, dsa, 0)
            say("   release at %+.0f kHz (vc %.4f): %s in %.1f s" % (khz, vc, ok, time.time() - t1))
            look(k, "after the release")
            time.sleep(0.5)
            look(k, "0.5 s later")
            if ok and "--all" not in sys.argv:
                break
        if "--quick" in sys.argv:
            return
        say("==== and the keeper's own recover()")
        t1 = time.time()
        r = k.ld.recover()
        say("   recover -> %s in %.1f s" % (r, time.time() - t1))
        look(k, "after recover")
        say("==== a fresh setup at the end, for comparison")
        t1 = time.time()
        ok = k.ld.setup(k.cfg)
        say("   setup -> %s in %.0f s, DSA %.2f, leg %.1f mV" % (ok, time.time() - t1, cl._dsa_db, 1e3 * (k.ld.leg or 0)))
        look(k, "after setup")
    finally:
        for n in (A, B):
            try:
                n.cl.safe()
            except Exception as e:                        # noqa: BLE001
                say("safe %s: %r" % (n.name, e))
        say("both quiet")


if __name__ == "__main__":
    main()
