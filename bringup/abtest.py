#!/usr/bin/env python3
"""abtest.py: the single symbols' A/B under one interference at a time (TODO, 2026-11-01: the settled decision and the
calibrated windows against the fixed delay and the plain rule; the night's random trials were no fair comparison).
The B210 is held at one setting while the self-test's plan 'ab' alternates A3 and A1, settled or fixed, each with the
calibrated windows or the plain rule's.

    python3 bringup/abtest.py [--minutes 4] [--conditions quiet,bursts,cw_near,cw_far]

Each condition: the B210 started by b210demo.py (announced on the page, so each result records what it did), the
self-test's results collected every 2 s by their start time, 30 s quiet between.  The plan is put back to 'cycle'
after.  Out: data/board_A/ab/ab_<stamp>.json and a table per condition: of every 10^6 symbols sent, how many right,
wrong, undecided and missed, the false decisions beside, and the mean latency.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import soak                                          # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "ab")
# what the B210 does (b210demo.py's arguments); none of these lost the lock in the soaks (BRINGUP_LOG 4.20, 4.24)
CONDITIONS = {
    "quiet": None,
    "bursts": ["bursts", "--on-ms", "1", "--per-ms", "20", "--gain", "85"],    # bit errors and false symbols (MONDAY)
    "cw_near": ["cw", "+0.43", "--gain", "80"],                                 # A2's false events in 4.24
    "cw_far": ["cw", "+2", "--gain", "85"],
}


def collect(seen, rows, cond):
    try:
        d = soak.get("/api/selftest")
    except Exception:                                    # noqa: BLE001 - the server busy a moment
        return
    for r in d.get("results", []):
        key = r.get("t0")
        if r.get("step") != "symbols" or key in seen:
            continue
        seen.add(key)
        rows.append(dict(r, condition=cond))


def run_condition(cond, minutes, seen, rows):
    args = CONDITIONS[cond]
    p = None
    if args:
        p = subprocess.Popen([sys.executable, os.path.join(HERE, "b210demo.py")] + args + ["--seconds", str(60 * minutes)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t_end = time.time() + 60 * minutes
    while time.time() < t_end and (p is None or p.poll() is None):
        collect(seen, rows, cond)
        time.sleep(2.0)
    if p is not None:
        p.wait(timeout=60)
    collect(seen, rows, cond)


def summary(rows):
    out = {}
    for r in rows:
        if r.get("interrupted") or not r.get("sent"):
            continue
        # a result belongs to its condition only if what the B210 did matches (a quiet run during a burst: dropped)
        quiet = (r.get("b210") or "quiet") == "quiet"
        if quiet != (r["condition"] == "quiet"):
            continue
        k = (r["condition"], r["scheme"], "settled" if r.get("settle") else "fixed", r.get("windows", "?"))
        c = out.setdefault(k, {"runs": 0, "sent": 0, "right": 0, "wrong": 0, "undecided": 0, "missed": 0, "false": 0,
                               "lat_sum": 0.0, "lat_n": 0})
        c["runs"] += 1
        for f in ("sent", "right", "wrong", "undecided", "missed", "false"):
            c[f] += int(r.get(f) or 0)
        if r.get("lat_ns") and r["lat_ns"][1] is not None:
            c["lat_sum"] += r["lat_ns"][1] * (r.get("right") or 0)
            c["lat_n"] += r.get("right") or 0
    return out


def table(s):
    lines = ["%-8s %-3s %-8s %-6s %4s %9s | %9s %8s %9s %8s %8s | %6s" % (
        "B210", "", "decided", "window", "runs", "sent", "right/1e6", "wrong", "undecided", "missed", "false", "ns")]
    for k in sorted(s):
        c = s[k]
        m = 1e6 / c["sent"]
        lines.append("%-8s %-3s %-8s %-6s %4d %9d | %9.0f %8.1f %9.1f %8.1f %8.1f | %6.1f" % (
            k[0], k[1], k[2], k[3], c["runs"], c["sent"], c["right"] * m, c["wrong"] * m, c["undecided"] * m,
            c["missed"] * m, c["false"] * m, c["lat_sum"] / c["lat_n"] if c["lat_n"] else float("nan")))
    return "\n".join(lines)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--minutes", type=float, default=4.0)
    ap.add_argument("--conditions", default="quiet,bursts,cw_near,cw_far")
    a = ap.parse_args(argv)
    conds = [c for c in a.conditions.split(",") if c]
    for c in conds:
        if c not in CONDITIONS:
            raise SystemExit("no condition %r (%s)" % (c, ", ".join(CONDITIONS)))
    seen, rows = set(), []
    soak.post("/api/selftest", {"on": True, "plan": "ab"})
    try:
        for c in conds:
            print("%s %s for %.1f min" % (time.strftime("%H:%M:%S"), c, a.minutes), flush=True)
            run_condition(c, a.minutes, seen, rows)
            time.sleep(30.0)
            collect(seen, rows, "after " + c)
    finally:
        soak.post("/api/selftest", {"on": True, "plan": "cycle"})
    s = summary(rows)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "ab_%s.json" % time.strftime("%Y%m%d_%H%M"))
    with open(path, "w") as f:
        json.dump({"conditions": {c: CONDITIONS[c] for c in conds}, "minutes": a.minutes, "rows": rows,
                   "summary": [dict(zip(("condition", "scheme", "decided", "windows"), k), **v) for k, v in s.items()]},
                  f, indent=1, default=str)
    print(table(s))
    print(path)


if __name__ == "__main__":
    main(sys.argv[1:])
