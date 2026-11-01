#!/usr/bin/env python3
"""scopewatch.py: the bench scope's I MON (ch2) and Q MON (ch3) captured once in each of the board's self-test steps
that sends single symbols or data, and posted to the status page's scope views (raw, aligned, eye, the fast
constellation) with what the link and the B210 were doing then (Jason, 2026-10-31: plots of I and Q from the 'idle to
one of N' tests and from a PRBS burst, raw and with the timing recovered, each saying what the board and the B210 did).

    python3 bringup/scopewatch.py [--hours 60]

It reads the page (HTTP) and the scope only: no request to the board, so linkd and the self-test go on.  The scope's
timebase is set for each capture and put back after; its channels, offsets and trigger are left as they are (ch2 and
ch3 at 0.1 V/div about 1.65 V: BRINGUP_LOG's bench).  Since 2026-11-01 07:30 PST ch2 and ch3 are at 50 ohm with the
probe factor 21 (each tap is 1 k into 50 ohm: /21; REVB 34), so the scope reads volts at the arm, fast (the 1 M input
and the cable had smoothed it over 115 ns); the scope's DC at 50 ohm is a millivolt or so off at its input (20 mV at
the arm), so it is measured in the self-test's carrier-alone step (the scope's mean against the board's own slow I
and Q, both on the same steady idle) and taken off every capture.  (Putting each capture's mean on the board's slow
reading, as first done, lifted BPSK data a whole leg: during data the board reads its level in a 0.1 s gap each
second, on the idle carrier, so the data looked like on-off keying; Jason, 07:40.)
"""
import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DASH = "http://192.168.8.142:8080"
SCOPE = "192.168.8.203"


def get(path):
    return json.loads(urllib.request.urlopen(DASH + path, timeout=5).read())


def post(path, d):
    return json.loads(urllib.request.urlopen(urllib.request.Request(DASH + path, data=json.dumps(d).encode(), method="POST"),
                                             timeout=10).read())


def b210_now():
    """the B210's announced activity now, in words, or 'quiet'"""
    t = time.time()
    try:
        now = [n for n in get("/api/notes?s=600") if n["t_start"] <= t <= (n.get("t_end") or t + 1)]
        for n in [m for m in now if m.get("b210")] or [m for m in now if m.get("text", "").startswith("B210")]:
            return n["text"].replace("B210: ", "sent ", 1)
    except Exception:                                            # noqa: BLE001
        pass
    return "quiet"


def capture(sc, tdiv, trig=None):
    """trig: (channel, level, slope) for this capture, else the bench's (ch2, I, through its middle); put back after.
    A2 moves only Q, so it triggers on Q's step up: on I the single shot waited out its 3 s and the capture came after
    the symbols had ended (2026-11-01 07:32)"""
    old = sc.q(":TIMebase:SCALe?")
    old_trig = (sc.q(":TRIGger:EDGE:SOURce?"), sc.q(":TRIGger:EDGE:LEVel?"), sc.q(":TRIGger:EDGE:SLOPe?"))
    if trig:
        sc.w(":TRIGger:EDGE:SOURce C%d" % trig[0])
        sc.w(":TRIGger:EDGE:LEVel %.4f" % trig[1])
        sc.w(":TRIGger:EDGE:SLOPe %s" % trig[2])
    sc.timebase(scale=tdiv)
    time.sleep(0.3)
    try:
        sc.single(timeout=1.5)
    except TimeoutError:
        sc.acquire_now()
    finally:
        if trig:
            sc.w(":TRIGger:EDGE:SOURce %s" % old_trig[0])
            sc.w(":TRIGger:EDGE:LEVel %s" % old_trig[1])
            sc.w(":TRIGger:EDGE:SLOPe %s" % old_trig[2])
    t2, v2, _ = sc.waveform(2)
    t3, v3, _ = sc.waveform(3)
    sc.run()
    sc.timebase(scale=float(old))
    k = max(1, len(v2) // 6000)
    return [float(v) for v in v2[::k]], [float(v) for v in v3[::k]], (float(t2[1] - t2[0]) * 1e9 * k if len(t2) > 1 else 0.0)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=60.0)
    a = ap.parse_args(argv)
    sys.path.insert(0, os.path.expanduser("~/lab-instrument-control/siglent"))
    from siglent_SDS2104X import SDS2104X
    sc = SDS2104X(SCOPE)
    done, t_stop = set(), time.time() + 3600 * a.hours
    off = {"i": 0.0, "q": 0.0, "t": None}            # the scope's DC error at 50 ohm, in volts at the arm
    print("%s watching the self-test for symbols and data" % time.strftime("%H:%M:%S"), flush=True)
    while time.time() < t_stop:
        time.sleep(0.5)
        try:
            r = get("/api/now")
        except Exception:                                        # noqa: BLE001 - the server restarting
            continue
        st = r.get("selftest") or {}
        now = st.get("now") or {}
        if st.get("on") and now.get("step") == "idle" and now.get("since") not in done and time.time() - now["since"] > 1.0:
            done.add(now["since"])
            adc = r.get("adc") or {}
            if r.get("state") == "locked" and adc.get("I") is not None and adc.get("Q") is not None and not r.get("busy"):
                try:
                    i, q, _ = capture(sc, 1e-6)
                    di, dq = adc["I"] - sum(i) / len(i), adc["Q"] - sum(q) / len(q)
                    if abs(di) < 0.08 and abs(dq) < 0.08:
                        k = 0.5 if off["t"] else 1.0
                        off.update(i=off["i"] + k * (di - off["i"]), q=off["q"] + k * (dq - off["q"]), t=time.time())
                        print("%s the scope's offset on the idle: I %+.1f mV, Q %+.1f mV at the arm" % (
                            time.strftime("%H:%M:%S"), 1e3 * off["i"], 1e3 * off["q"]), flush=True)
                except Exception as e:                           # noqa: BLE001
                    print("%s offset capture failed: %s" % (time.strftime("%H:%M:%S"), e), flush=True)
            continue
        if not st.get("on") or now.get("step") not in ("symbols", "data", "pattern") or now.get("since") in done:
            continue
        if time.time() - now["since"] < 1.0 or time.time() - now["since"] > now.get("seconds", 10) - 1.0:
            continue
        # data: in the middle of a second, clear of the 0.1 s gap each second in which the board reads the idle carrier's
        # level (a capture at 1.0 s caught the gap: the carrier idling, the data stopped; 07:40)
        if now["step"] == "data" and not 0.35 < (time.time() - now["since"]) % 1.0 < 0.65:
            continue
        done.add(now["since"])
        period_ns = now["period"] * 10.0
        # single symbols: about three across the screen (the aligned view wants the samples close); data: about forty bits
        # the pattern (states half the time, 400 ns apart): about fifty across the screen
        tdiv = (max(1e-6, min(50e-6, 0.3 * period_ns * 1e-9)) if now["step"] == "symbols" else
                5 * period_ns * 1e-9 if now["step"] == "pattern" else max(1e-7, 4 * period_ns * 1e-9))
        b2 = b210_now()
        try:
            leg = (r.get("leg_ref_mv") or 160) / 1000.0
            trig = (3, (r.get("q0") or 1.63) + 0.3 * leg, "RISing") if now.get("scheme") == "A2" and now["step"] == "symbols" else None
            i, q, dt = capture(sc, tdiv, trig)
            i, q = [v + off["i"] for v in i], [v + off["q"] for v in q]
        except Exception as e:                                   # noqa: BLE001 - the next step tries again
            print("%s capture failed: %s" % (time.strftime("%H:%M:%S"), e), flush=True)
            continue
        try:
            out = post("/api/scope", {"t": time.time(), "kind": now["step"], "period_ns": period_ns,
                                  "width_ns": now.get("width", 0) * 10.0 or None, "scheme": now.get("scheme", ""),
                                  "leg": (r.get("leg_ref_mv") or 160) / 1000.0, "i0": r.get("i0"), "q0": r.get("q0"),
                                  "link": now.get("text", ""), "b210": b2, "text": now.get("text", ""),
                                  "source": "scopewatch.py", "dt_ns": dt, "i": i, "q": q,
                                  "input": "50 ohm, the 1 k taps /21 (the arm's own edge)"})
        except Exception as e:                                   # noqa: BLE001 - the server restarting: the next step
            out = "not posted: %s" % e
        print("%s %s: %d samples %.2f ns apart; the B210 %s -> %s" % (time.strftime("%H:%M:%S"), now.get("text", ""), len(i), dt, b2, out),
              flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
