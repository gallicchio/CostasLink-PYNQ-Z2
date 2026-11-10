"""The lab laptop's SDS1104X-E on board A's monitors (2026-11-03): the cabling check and the captures the night's runs take.

    python3 bringup/scope_e.py check          # each channel against what the board's own ADC reads of the same node
    python3 bringup/scope_e.py capture NAME   # one capture of all four channels into bringup/data/board_A/scope/

The channels (Jason cabled them on 2026-11-03, BRINGUP_LOG 4.45):
    ch1  TRIG A (J205, SMA): tx_event's mark, a 33 ohm source-terminated LVCMOS output; 50 ohm at the scope (about 1.7 V)
    ch2  I MON  (J104, U.FL): the I arm through 1 k; 50 ohm at the scope, so the arm's voltage / 21 (PROBE_FACTOR)
    ch3  Q MON  (J105, U.FL): the Q arm, the same
    ch4  ERR MON (J106, MMCX): the Costas loop's error through 1 k; 1 Mohm, so full size (1.65 V +- 0.125)
The SDS1000X-E's inputs are 1 Mohm only: the 50 ohm are external feed-through terminators.  No *RST is ever sent (the
lab's rule for the Siglents); the scope is left running in AUTO.

Two SDS1104X-E since 2026-11-06 (both on USB; `usbtmc_node` without a serial returns whichever enumerated first, so each
is opened by its serial number, SCOPES below): scope A on board A's monitors (serial ...R1353), scope B on board B's (serial
...R6919, plugged in 11-06 10:44).  The cabling planned for the two (BRINGUP_LOG 4.74), every input through a 50 ohm
feed-through:
    scope A  ch1 board B's TRIG A (J205, SMA)   ch2 board A's I MON (J104)   ch3 Q MON (J105)   ch4 CMP I MON (J103)
    scope B  ch1 board A's TRIG A (J205, SMA)   ch2 board B's I MON (J104)   ch3 Q MON (J105)   ch4 CMP I MON (J103)
(the trigger is the other board's mark: each scope watches a receiver, triggered by the sender).  `check` and
`capture` take `--scope A|B`; `check` compares against that board's own ADC.
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LIC = os.path.expanduser(os.environ.get("LAB_INSTRUMENT_CONTROL", "~/lab-instrument-control"))   # as bench.py: a station kit
sys.path.insert(0, LIC)                                                                     # carries its own copy
sys.path.insert(0, os.path.join(LIC, "siglent"))
from siglent_SDS1104XE import SDS1104XE                               # noqa: E402

PROBE_FACTOR = 21.0          # a 1 k tap into 50 ohm: (1000 + 50) / 50
CHANNELS = {1: "TRIG A", 2: "I MON", 3: "Q MON", 4: "ERR MON"}
# (V/div, offset) for each channel: offsets centre the expected level
SETUP = {1: (0.5, -0.85), 2: (0.005, -0.078), 3: (0.005, -0.078), 4: (0.05, -1.63)}   # 5 mV/div = 0.1 V/div at the arm, the bench's


SCOPES = {"A": "SDSMMEBC3R1353", "B": "SDSMMFCQ5R6919"}     # each SDS1104X-E's serial number (its *IDN?)
BOARD_API = {"A": "http://192.168.2.99:8080", "B": "http://192.168.2.98:8080"}


def open_scope(which="A"):
    """Scope A or B by its serial number (the lab driver's SDS1104XE(serial=...)); scope A falls back to the first
    SDS1104X-E on USB (one scope, as before 11-06).  Until 11-09 this file found the serial in sysfs itself and replaced the
    driver's waveform(), whose sample-count query scope B's firmware (8.1.6.1.35R2) never answers for C2 and C4; the
    driver does both now (lab-instrument-control 57a4fcf)."""
    try:
        return SDS1104XE(serial=SCOPES[which])
    except IOError:
        if which != "A":
            raise
        return SDS1104XE(usb=True)


def setup(s, tdiv=1e-3):
    for ch, (vdiv, off) in SETUP.items():
        s.channel(ch, on=True, scale=vdiv, offset=off, coupling="DC", probe=1)
    s.timebase(scale=tdiv, delay=0)
    s.trigger(source=1, level=0.85, slope="rising", mode="auto")


def grab(s, tdiv):
    """One acquisition of every channel that is on (a channel that is off never answers SANU?, and the read times out)."""
    s.timebase(scale=tdiv, delay=0)
    on = [ch for ch in CHANNELS if s.channel(ch)["on"]]
    s.acquire_now()
    out = {}
    try:
        for ch in on:
            t, v, info = s.waveform(ch)
            out[ch] = (t, v, info)
    finally:
        s.run()                   # never leave the scope stopped
    return out


def board_now(board="A"):
    import urllib.request
    with urllib.request.urlopen(BOARD_API[board] + "/api/now", timeout=10) as r:
        return json.load(r)


def stats(v, info):
    clipped = info["codes_min"] <= -127 or info["codes_max"] >= 127
    return {"mean": float(v.mean()), "min": float(v.min()), "max": float(v.max()), "pp": float(v.max() - v.min()),
            "clipped": bool(clipped)}


def check(board="A"):
    d = board_now(board)
    adc = d.get("adc") or {}
    s = open_scope(board)
    try:
        setup(s)
        slow = grab(s, 1e-3)          # 14 ms: the DC levels
        fast = grab(s, 1e-6)          # 14 us: TRIG A's marks
    finally:
        s.close()
    rep = {}
    for ch, name in CHANNELS.items():
        st = stats(slow[ch][1], slow[ch][2])
        stf = stats(fast[ch][1], fast[ch][2])
        rep[name] = {"slow": st, "fast": stf}
    i_arm, q_arm = rep["I MON"]["slow"]["mean"] * PROBE_FACTOR, rep["Q MON"]["slow"]["mean"] * PROBE_FACTOR
    print("board: linkd %s, state %s, DSA %s, ADC %s" % ((d.get("linkd") or {}).get("mode"), d.get("state"),
                                                         d.get("dsa_db"), adc))
    for name, r in rep.items():
        print("%-8s slow: mean %+.4f V, %+.4f to %+.4f%s;  fast: %+.4f to %+.4f%s" % (
            name, r["slow"]["mean"], r["slow"]["min"], r["slow"]["max"], " CLIPPED" if r["slow"]["clipped"] else "",
            r["fast"]["min"], r["fast"]["max"], " CLIPPED" if r["fast"]["clipped"] else ""))
    print("I MON x %g = %.3f V against the ADC's I %.3f;  Q MON x %g = %.3f V against Q %.3f;  ERR MON %.3f against ERR %.3f"
          % (PROBE_FACTOR, i_arm, adc.get("I", float("nan")), PROBE_FACTOR, q_arm, adc.get("Q", float("nan")),
             rep["ERR MON"]["slow"]["mean"], adc.get("ERR", float("nan"))))
    verdicts = []
    for nm, arm, ref in (("I MON", i_arm, adc.get("I")), ("Q MON", q_arm, adc.get("Q"))):
        if ref is None:
            continue
        if abs(rep[nm]["slow"]["mean"] - ref) < 0.15:
            verdicts.append("%s reads the arm at full size: no 50 ohm terminator on it" % nm)
        elif abs(arm - ref) > 0.15:
            verdicts.append("%s x 21 is %.2f V off the ADC's: the cable, the jack or the terminator" % (nm, arm - ref))
        else:
            verdicts.append("%s ok (terminated, on the right arm)" % nm)
    e = rep["ERR MON"]["slow"]["mean"]
    if adc.get("ERR") is not None:
        verdicts.append("ERR MON ok (1 Mohm)" if abs(e - adc["ERR"]) < 0.1 else
                        "ERR MON %.3f V against the ADC's %.3f: %s" % (e, adc["ERR"],
                                                                      "terminated in 50 ohm?" if e * PROBE_FACTOR - adc["ERR"] < 0.15
                                                                      else "the cable or the jack"))
    hi = rep["TRIG A"]["fast"]["max"]
    verdicts.append("TRIG A high %.2f V: %s" % (hi, "terminated (about 1.7 V expected)" if 1.2 < hi < 2.2 else
                                                 "unterminated (about 3.3 V)" if hi > 2.6 else
                                                 "no marks in 14 us (no tx_event now?) or no connection"))
    for v_ in verdicts:
        print("  " + v_)
    return rep


def capture(name, tdiv=1e-6, board="A"):
    out = os.path.join(HERE, "data", "board_%s" % board, "scope")
    os.makedirs(out, exist_ok=True)
    s = open_scope(board)
    try:
        g = grab(s, tdiv)
    finally:
        s.close()
    path = os.path.join(out, "%s_%s.npz" % (time.strftime("%Y-%m-%d_%H%M%S"), name))
    np.savez_compressed(path, **{"t%d" % ch: g[ch][0] for ch in g}, **{"v%d" % ch: g[ch][1] for ch in g},
                        info=json.dumps({ch: g[ch][2] for ch in g}))
    return path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=("check", "capture"))
    ap.add_argument("name", nargs="?", default="capture")
    ap.add_argument("--tdiv", type=float, default=1e-6)
    ap.add_argument("--scope", choices=tuple(SCOPES), default="A", help="scope A (board A's monitors) or B (board B's)")
    a = ap.parse_args()
    if a.action == "check":
        check(a.scope)
    else:
        print(capture(a.name, a.tdiv, a.scope))


if __name__ == "__main__":
    main()
