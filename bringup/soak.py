#!/usr/bin/env python3
"""soak.py: the link left to linkd for hours while disturbances with random parameters hit it, each one checked
against everything that records it (Jason, 2026-10-31: "As you keep doing interference and lock tests and everything
else, randomize their parameters and check both the logs and the web dashboard to make sure that everything makes
sense").

    python3 bringup/soak.py run [--mhz 5200] [--hours 12] [--seed N] [--gap 20 90] [--shots 0.3] [--kinds K ...] [--holdover]
    python3 bringup/soak.py audit RUN.jsonl          the same checks on an earlier run (unattended.py's or soak.py's)

Each disturbance is drawn at random, its parameters from continuous ranges (the seed in the record):
    cw_far       the B210's CW 0.2-40 MHz above or below the carrier (log-uniform), gain 70-89.75, for 0.5-12 s
    cw_near      the B210's CW 0.5-80 kHz above or below, gain 70-89.75, for 0.5-8 s
    bursts       the B210's noise, 1-8 MHz wide, centred up to 3 MHz off the carrier, on 10 us - 3 ms every
                 1.5 x on - 300 ms (log-uniform), gain 70-89.75, for 3-40 s
    release      the loop held, re-centred and let go -400..+400 kHz from the lock: where it comes to rest is predicted
                 by the measured pull-in map (BRINGUP_LOG 4.12: the lock above -13 kHz, the false lock between the
                 watersheds at -16 and -94 kHz, the rail below -129 kHz; between those, either)
    carrier_off  the TX muted for 10 ms - 60 s (log-uniform; soak2 found 0.3 s enough to lose the lock, into the false lock)
    attn         the attenuator stepped -6..+6 dB (kept within 6-31.75 dB) for 5-30 s
    symbols      single symbols from the idle to one of 2 or 4 states and back (A1, A1w, A2, A3; the board's receiver
                 decides each, `campaign.scheme_run`): one every 32-4000 clocks (log-uniform), 2-40 clocks long, for
                 0.5-6 s; right, wrong, false and missed, and the latency
    data         a BPSK PRBS15 string at 1-50 Mbaud (2-100 clocks a bit, log-uniform) for 3-15 s in segments of about
                 1.5 s, checked by the board with its timing recovered (`campaign.segs`): bit errors, and each segment
                 clean, inverted (a slip), beating (lost) or partial
                 Each of the two with a B210 interferer drawn as above running across it (3 in 5), or none; the bench
                 scope's I MON and Q MON captured during it and posted to the page's fast constellation (the MON taps
                 smooth over about 0.1 us, so only symbols and bits slower than that show as clean clusters)
Each is announced on the status page (a note from soak.py, open until the link is locked again with linkd active), and
then checked:
    the page's own log on the PYNQ (dashboard.py writes every look, note and event) against its API: the same looks and
    the same events; the looks a second apart; the note shown; linkd's counts against the losses and recoveries in
    'What happened', every loss in the window called expected; a loss shown as a state that is not 'Locked'; a page
    that said 'Lost' with the oscillator away from the lock for 5 s while linkd was free to act has a loss counted; the
    carrier's level shown only while locked; no offset while a program holds the loop; after it, the offset back
    within 3 kHz and the levels within 1 dB of before; and what the kind predicts (the rest point for a release,
    'No carrier' for a muted TX, the demodulator's level following the attenuator while RX ANT stays put).
--holdover turns the signal holdover on for the run (`costaslink.shold`, its defaults; off at reset and in deployment
so far) and off again at the end: the loop held while the windows see no carrier (BRINGUP_LOG 4.8, 4.21).
Screenshots of the page (headless Chromium) during a random share of the disturbances and the first of each kind,
and after any that fails a check.  bringup/data/board_A/soak/.  Only the page (HTTP) and its log (ssh) are read
between disturbances: nothing touches the board but the disturbances that must.
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "data", "board_A", "soak")
DASH = "http://192.168.8.142:8080"
PYNQ = "xilinx@192.168.8.142"
KINDS = {"cw_far": 0.2, "cw_near": 0.18, "bursts": 0.2, "release": 0.2, "carrier_off": 0.12, "attn": 0.1, "symbols": 0.3, "data": 0.3}
DRIVES = ("release", "carrier_off", "attn", "symbols", "data")   # requests to the board: linkd waits a minute after
SCHEME_TEXT = {"A1": "A1, the BPSK flip", "A1w": "A1w, the BPSK flip seen beside the idle", "A2": "A2, 1 bit: the Q step",
               "A3": "A3, 2 bits: the QPSK corners"}
WATERSHEDS_KHZ = ((-16.0, -13.0), (-129.0, -94.0))   # 5.2 GHz, where a release can go either way (BRINGUP_LOG 4.12)
NOT_LOCKED = ("lost", "nocarrier", "interfered", "unsettled", "held", "holdover", "interference")

# runs on the PYNQ: the lines of the page's day logs between t0 and t1 (bisected: the log grows ~160 MB a day)
PYNQ_FILTER = r'''
import json, os, sys, time
t0, t1 = float(sys.argv[1]), float(sys.argv[2])
d = os.path.expanduser("~/costaslink_current/dashboard")
def t_of(line):
    try:
        return json.loads(line)["t"]
    except Exception:
        return None
for day in sorted({time.strftime("%Y-%m-%d", time.localtime(t)) for t in (t0, t1)}):
    p = os.path.join(d, day + ".jsonl")
    if not os.path.exists(p):
        continue
    with open(p, "rb") as f:
        lo, hi = 0, os.path.getsize(p)
        while hi - lo > 65536:
            mid = (lo + hi) // 2
            f.seek(mid)
            f.readline()
            t = None
            while t is None:
                line = f.readline()
                if not line:
                    break
                t = t_of(line)
            if t is None or t >= t0 - 5:
                hi = mid
            else:
                lo = mid
        f.seek(lo)
        if lo:
            f.readline()
        for line in f:
            t = t_of(line)
            if t is None:
                continue
            if t > t1 + 5:
                break
            if t0 <= t <= t1:
                sys.stdout.buffer.write(line)
'''


# ---- the page and its log ----
def get(path, timeout=10):
    return json.loads(urllib.request.urlopen(DASH + path, timeout=timeout).read())


def post(path, d):
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(DASH + path, data=json.dumps(d).encode(), method="POST"),
                                                 timeout=5).read())
    except Exception:                                            # noqa: BLE001 - the server restarting
        return {}


def wait(cond, timeout, poll=0.5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = get("/api/now", timeout=5)
            if cond(r):
                return r
        except Exception:                                        # noqa: BLE001
            pass
        time.sleep(poll)
    return None


def now_or_none():
    """the page's latest look, or None while its server restarts (a refused connection ended a run, 2026-10-31)"""
    try:
        return get("/api/now", timeout=5)
    except Exception:                                            # noqa: BLE001
        return None


def ready_(r):
    return r.get("state") == "locked" and (r.get("linkd") or {}).get("mode") == "locked"


def pynq_log(t0, t1):
    """the page's own record on the PYNQ: looks, notes (the last version of each) and events, t0 to t1"""
    p = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", PYNQ, "python3", "-", "%.3f" % t0, "%.3f" % t1],
                       input=PYNQ_FILTER, capture_output=True, text=True, timeout=120)
    looks, notes, events = [], {}, []
    for line in p.stdout.splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if "note" in d:
            notes[d["note"]["id"]] = d["note"]
        elif "event" in d:
            events.append(d["event"])
        elif "scope" in d:
            pass                                                 # a bench capture posted to the page, not a look
        else:
            looks.append(d)
    return looks, notes, events


def shot(name):
    """the page as a viewer sees it (headless Chromium, about 10 s, in the background)"""
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "%s_%s.png" % (name, time.strftime("%H%M%S")))
    def go():
        try:
            subprocess.run(["chromium-browser", "--headless", "--disable-gpu", "--hide-scrollbars", "--window-size=1400,3000",
                            "--virtual-time-budget=2500", "--screenshot=" + p, DASH + "/"], capture_output=True, timeout=90)
        except Exception:                                        # noqa: BLE001
            pass
    threading.Thread(target=go, daemon=True).start()
    return p


def med(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[len(xs) // 2] if xs else None


# ---- what the map predicts for a release ----
def predict_release(k):
    for lo, hi in WATERSHEDS_KHZ:
        if lo <= k <= hi:
            return "either"
    if k > WATERSHEDS_KHZ[0][1]:
        return "lock"
    if k > WATERSHEDS_KHZ[1][1]:
        return "falselock"
    return "rail"


def rest_class(off, vc):
    if vc is not None and vc < 0.4:
        return "rail"
    if off is None:
        return None
    if abs(off) < 8:
        return "lock"
    if -60 <= off <= -30:
        return "falselock"
    return "other (%.0f kHz)" % off


# ---- the checks ----
def audit(t0, t_end, t_back, note_id=None, kind=None, params=None, marks=None, t_fetch=None):
    """every record of one disturbance against the others and against what it should have shown"""
    t_fetch = t_fetch or time.time()
    lo = t0 - 20.0
    looks, notes, ev_log = pynq_log(lo, t_fetch)
    looks = [r for r in looks if r.get("t")]
    real = [r for r in looks if not r.get("busy") and not r.get("error")]
    out = {"n_looks": len(looks), "n_busy": sum(1 for r in looks if r.get("busy")), "checks": []}
    def check(name, ok, detail=""):
        out["checks"].append({"name": name, "ok": ok, "detail": detail})
    if not looks:
        check("log_read", False, "no looks in the PYNQ's log for the window")
        return out
    before = [r for r in real if r["t"] < t0 and r.get("state") == "locked"][-15:]
    base = {k: med([r.get(k) for r in before]) for k in ("rx_ant_dbm", "dem_dbm", "off_khz", "dsa_db")}
    base["vc"] = med([(r.get("adc") or {}).get("VC") for r in before])
    out["base"] = base
    t_last = t_back if t_back is not None else t_fetch
    during = [r for r in real if t0 <= r["t"] <= t_last]

    # the log against the API (the API holds 2 h; within ~25 min it is not thinned)
    try:
        if time.time() - lo < 1400:
            hist = get("/api/history?s=%d" % (time.time() - lo + 2))
            ht = {round(r["t"], 3) for r in hist if lo <= r["t"] <= t_fetch - 3}
            lt = {round(r["t"], 3) for r in looks if r["t"] <= t_fetch - 3}
            check("log_vs_api_looks", ht == lt, "" if ht == lt else "%d looks only in the log, %d only in the API" % (len(lt - ht), len(ht - lt)))
        # the API's list reaches back only so far (dashboard.py keeps a deque): compared where it reaches
        ev_all = get("/api/events?s=%d" % (time.time() - lo + 2))
        t_api0 = max(lo, min((e["t"] for e in ev_all), default=lo))
        ev_api = [e for e in ev_all if t_api0 <= e["t"] <= t_fetch - 3 and not e["kind"].startswith("note-")]
        ka = sorted((round(e["t"], 3), e["kind"]) for e in ev_api)
        kl = sorted((round(e["t"], 3), e["kind"]) for e in ev_log if t_api0 <= e["t"] <= t_fetch - 3)
        check("log_vs_api_events", ka == kl, "" if ka == kl else "API %s, log %s" % (ka, kl))
    except Exception as e:                                       # noqa: BLE001
        check("api_read", False, str(e)[:200])

    # the board's server restarted inside the window (linkd's counts went down: they start again at 0): its gap in the
    # looks and its counts are the restart's, not the disturbance's (soak15 #32 flagged both, a deploy at 14:54:45)
    Lc = [r["linkd"].get("losses", 0) for r in real if r.get("linkd") and r["linkd"].get("losses") is not None]
    restarted = any(b < a for a, b in zip(Lc, Lc[1:]))
    out["server_restarted"] = restarted
    # the looks a second apart
    ts = [r["t"] for r in looks]
    gap = max((b - a for a, b in zip(ts, ts[1:])), default=0.0)
    check("looks_continuous", gap <= 3.5 or restarted, "the longest gap between looks %.1f s%s" % (
        gap, " (the server restarted in the window)" if restarted else ""))

    # the note
    if note_id:
        n = notes.get(note_id)
        if n is None:
            try:
                n = next((x for x in get("/api/notes?s=%d" % (time.time() - lo + 2)) if x.get("id") == note_id), None)
            except Exception:                                    # noqa: BLE001
                n = None
        check("note_shown", n is not None and abs(n["t_start"] - t0) < 3 and (n.get("t_end") or 0) >= t_end,
              "" if n else "the note is in neither the log nor the API")

    # linkd's counts against 'What happened'
    # the page makes its events in its full looks (a busy look carries linkd's counts but makes none): counted from the
    # window's first full look on, the events after it against the counts' change
    Ls = [r for r in real if r.get("linkd")]
    d = {k: (Ls[-1]["linkd"].get(k, 0) - Ls[0]["linkd"].get(k, 0)) if Ls else 0 for k in ("losses", "recoveries", "failed")}
    out["linkd"] = d
    first_t = Ls[0]["t"] if Ls else lo
    n_ev_all = {k: sum(1 for e in ev_log if e["kind"] in ks and e["t"] > first_t)
                for k, ks in (("losses", ("loss", "loss-expected")), ("recoveries", ("recovered",)), ("failed", ("failed",)))}
    out["events"] = n_ev_all
    if not restarted:
        check("events_vs_linkd", n_ev_all == d, "linkd %s, the page's events %s" % (d, n_ev_all))
    # a jump to the other lock point with no unlocked look between: a slip, which the page must list
    lk = [r for r in real if r.get("state") == "locked" and r.get("adc") and r.get("i0") is not None
          and abs(r["adc"]["I"] - r["i0"]) > 0.05 and (r.get("rate") or {}).get("CMP_I", 1e9) < 2000]
    sides = [(r["t"], 1 if r["adc"]["I"] > r["i0"] else -1) for r in lk]
    bef = [s for t, s in sides if t < t0][-1:]
    aft = [s for t, s in sides if t > t_end][-1:]
    out["side"] = {"before": bef[0] if bef else None, "after": aft[0] if aft else None}
    flipped = bool(bef and aft and bef[0] != aft[0])
    pure = flipped and d["losses"] == 0 and not any(r.get("state") in ("lost", "nocarrier", "held")
                                                    for r in real if t0 - 1 <= r["t"] <= t_fetch)
    out["slip"] = pure
    if pure:
        check("slip_shown", any(e["kind"] == "slip" and t0 - 1 <= e["t"] <= t_fetch for e in ev_log),
              "the loop moved to its other lock point without a loss, and 'What happened' says nothing")
    unexp = [e for e in ev_log if e["kind"] == "loss" and t0 <= e["t"] <= t_fetch]
    check("losses_announced", not unexp, "; ".join(e["text"][:120] for e in unexp))

    # the states
    sts = {}
    for r in during:
        sts[r.get("state")] = sts.get(r.get("state"), 0) + 1
    out["states"] = sts
    modes = sorted({(r.get("linkd") or {}).get("mode", "")[:24] for r in looks if t0 <= r["t"] <= t_last})
    out["linkd_modes"] = modes
    if d["losses"] > 0:
        check("loss_shown", any(s in NOT_LOCKED for s in sts) or any("recovering" in m for m in modes),
              "linkd counted %d loss(es); the page's states %s" % (d["losses"], sts))
    run, worst = 0, 0
    for r in during:
        free = (r.get("linkd") or {}).get("mode") in ("locked", "watching", "recovering", "backing off")
        if r.get("state") == "lost" and r.get("off_khz") is not None and abs(r["off_khz"]) >= 8 and free:
            run += 1
            worst = max(worst, run)
        else:
            run = 0
    check("no_silent_loss", worst < 5 or d["losses"] > 0,
          "the page said 'Lost' away from the lock for %d looks with linkd free, and linkd counted none" % worst)
    bad = [r["t"] for r in looks if (r.get("rx_ant_dbm") is not None or r.get("dem_dbm") is not None) and r.get("state") != "locked"]
    check("levels_only_when_locked", not bad, "%d looks with a level while not locked" % len(bad))
    bad = [r["t"] for r in looks if r.get("state") == "held" and r.get("off_khz") is not None]
    check("no_offset_when_held", not bad, "%d held looks with an offset" % len(bad))
    offs = [r["off_khz"] for r in during if r.get("off_khz") is not None]
    vcs = [(r.get("adc") or {}).get("VC") for r in during if r.get("adc")]
    out["off_range"] = [min(offs), max(offs)] if offs else None
    out["vc_range"] = [min(vcs), max(vcs)] if vcs else None
    pk = [(r.get("det") or {}).get("peak_dbm") for r in during]
    out["peak_dbm_max"] = max((x for x in pk if x is not None), default=None)

    # back, and as before; when the page read locked for good (the wait for 'back' starts 3 s after the end, to let
    # the page see the disturbance first, so its time is no measure of a quick return)
    check("back", t_back is not None, "" if t_back is not None else "not locked again with linkd active")
    tail = [r for r in real if r["t"] > t_end - 1.5 and r["t"] <= t_last]
    t_rel = None
    for r in reversed(tail):
        if r.get("state") != "locked":
            break
        t_rel = r["t"]
    out["relocked_s"] = (t_rel - t_end) if t_rel is not None else None
    after = [r for r in real if t_back is not None and r["t"] > t_back][:10]
    if t_back is not None and len(after) >= 4:
        a = {k: med([r.get(k) for r in after]) for k in ("rx_ant_dbm", "dem_dbm", "off_khz")}
        out["after"] = a
        ok = a["off_khz"] is not None and abs(a["off_khz"]) < 3.0
        for k in ("rx_ant_dbm", "dem_dbm"):
            if a[k] is not None and base[k] is not None:
                ok = ok and abs(a[k] - base[k]) < 1.0
        check("as_before", ok, "after: offset %s kHz, RX ANT %s, demodulator %s dBm (before %s, %s)" % (
            *("%.1f" % a[k] if a[k] is not None else "-" for k in ("off_khz", "rx_ant_dbm", "dem_dbm")),
            *("%.1f" % base[k] if base[k] is not None else "-" for k in ("rx_ant_dbm", "dem_dbm"))))
    # the self-test's own single symbols and QPSK started once the link was back, quiet: each lost under 1 % (2026-11-01
    # 13:41: a calibration taken during an attenuator step left A2, A3 and QPSK 60 % missed, and every check passed)
    runs = {}
    for r in looks:
        for x in ((r.get("selftest") or {}).get("results") or []):
            if (x.get("t0") and t_back is not None and x["t0"] > t_back + 1.0 and x.get("step") in ("symbols", "qpsk")
                    and x.get("sent") and not x.get("interrupted") and (x.get("b210") or "quiet") == "quiet"):
                runs[x["t0"]] = x
    if runs:
        bad = [x for x in runs.values()
               if (x.get("missed") or 0) + (x.get("undecided") or 0) + (x.get("wrong") or 0) > 0.01 * x["sent"]]
        check("symbols_after", not bad, "%d of the self-test's runs after it, %d losing over 1 %%%s" % (
            len(runs), len(bad), "".join("; %s %s: %s of %s right" % (x.get("step"), x.get("scheme"), x.get("right"), x.get("sent"))
                                         for x in bad[:3])))

    # what the kind predicts
    params, marks = params or {}, marks or {}
    if kind == "release" or (kind == "carrier_off" and "unmuted" in marks):
        # where the loop came to rest: after a release, or once the carrier is back after an interruption
        t_rel = marks.get("released") or marks.get("unmuted") or t0
        # where it rested before linkd's first recovery after it: linkd now recovers within 2 s when the carrier is
        # there (it waits only while there is none), so look from 1 s on (the drifts take 0.05-0.5 s) and keep the looks
        # with linkd's count as before the disturbance (from 3 s on, soak13 #33 saw only the recovered lock)
        L0 = next(((r.get("linkd") or {}).get("recoveries", 0) for r in reversed(real) if r["t"] < t0), 0)
        rest = [r for r in real if t_rel + 1 <= r["t"] <= t_last and r.get("state") in ("lost", "locked", "interfered", "unsettled")
                and "recovering" not in (r.get("linkd") or {}).get("mode", "") and (r.get("linkd") or {}).get("recoveries", 0) == L0][:20]
        off_r = med([r.get("off_khz") for r in rest])
        vc_r = med([(r.get("adc") or {}).get("VC") for r in rest])
        got = rest_class(off_r, vc_r) if rest else None
        out["rest"] = {"class": got, "off_khz": off_r, "vc": vc_r, "looks": len(rest)}
        want = params.get("predicted")
        if kind == "release" and got is not None:
            check("rest_as_map", want == "either" or got == want, "predicted %s, rested %s" % (want, got))
        if got == "lock":
            check("lock_no_loss", d["losses"] == 0, "came to the lock by itself but linkd counted %d" % d["losses"])
        elif got in ("falselock", "rail"):
            lost = [r for r in rest if r.get("state") == "lost"]
            check("rest_shown_lost", len(lost) >= len(rest) // 2, "%d of %d looks at rest said 'Lost'" % (len(lost), len(rest)))
            check("recovered_by_linkd", d["recoveries"] >= 1, "linkd recovered %d" % d["recoveries"])
    if kind == "carrier_off" and params.get("seconds", 0) >= 3:
        off_ = [r for r in real if t0 + 2.0 <= r["t"] <= t_end - 0.5]
        nc = [r for r in off_ if r.get("state") in ("nocarrier", "holdover")]
        check("nocarrier_shown", off_ and len(nc) >= 0.8 * len(off_), "%d of %d looks said 'No carrier'" % (len(nc), len(off_)))
    if kind == "attn" and "up" in marks:
        stp = [r for r in real if marks["up"] + 2 <= r["t"] <= marks["back"] - 0.5 and r.get("dem_dbm") is not None]
        dd = params["db"]
        if len(stp) >= 3 and base["dem_dbm"] is not None:
            dem = med([r["dem_dbm"] for r in stp]) - base["dem_dbm"]
            ant = med([r.get("rx_ant_dbm") for r in stp])
            ant = ant - base["rx_ant_dbm"] if ant is not None and base["rx_ant_dbm"] is not None else None
            out["attn"] = {"dem_db": dem, "ant_db": ant}
            check("dem_follows_attn", abs(dem + dd) < 1.0 + 0.1 * abs(dd), "the attenuator %+.2f dB, the demodulator %+.2f dB" % (dd, dem))
            check("ant_stays", ant is not None and abs(ant) < 1.0 + 0.1 * abs(dd), "RX ANT %s dB" % ("%+.2f" % ant if ant is not None else "-"))
            # linkd's windows follow the level (2026-11-01): a step of 1.5 dB or more (the leg 16 % or more) moves them
            # within one round of the self-test (it learns the leg on the idle carrier: its idle step, 3 s in 16).  Down
            # only (71163c3: raised with a stronger carrier they lost A3's corners), so only a step that weakens it
            # (soak15 #59 flagged -2.50 dB, the carrier stronger, where no move is right)
            if dd >= 1.5 and marks["back"] - marks["up"] >= 20:
                check("windows_followed", any(e["kind"] == "windows" and marks["up"] <= e["t"] <= marks["back"] + 2 for e in ev_log),
                      "no 'windows' event while the attenuator was %+.2f dB" % dd)
        else:
            check("attn_levels", None, "not locked during the step (%d looks with a level)" % len(stp))
    if kind == "symbols" and marks.get("result"):
        res, ds, de = marks["result"], marks.get("data_start", t0), marks.get("data_end", t_end)
        rxl = [r["rx"] for r in real if r.get("rx") and ds <= r["t"] <= de + 1]
        check("symbols_on_page", bool(rxl), "the page read no decisions while the symbols ran")
        if rxl:
            # right and missed end with the transmitter; false decisions (and so 'events') go on while the receiver is
            # on and the interference lasts, after the run's own read (A1w under bursts: 22 000 more, soak10 #7)
            pr, keys = rxl[-1], ("events", "right", "false", "missed")
            ok = all(pr.get(k) == res.get(k) for k in ("right", "missed")) and all((pr.get(k) or 0) >= (res.get(k) or 0) for k in ("events", "false"))
            check("symbols_page_vs_run", ok, "the page's last look %s, the run's %s" % ({k: pr.get(k) for k in keys}, {k: res.get(k) for k in keys}))
        if not params.get("with") and res.get("events"):
            check("symbols_clean", res["right"] >= 0.999 * res["events"] and (res.get("false") or 0) <= max(2, 1e-4 * res["events"]),
                  "no interference: %s sent, %s right, %s wrong, %s false, %s missed" % tuple(res.get(k) for k in ("events", "right", "symbol_errors", "false", "missed")))
    if kind == "data" and marks.get("result"):
        res, ds, de = marks["result"], marks.get("data_start", t0), marks.get("data_end", t_end)
        bl = [r for r in real if r.get("ber") and ds <= r["t"] <= de + 1]
        check("data_on_page", bool(bl), "the page read no bit counts while the data ran")
        if bl and res["clean"] == params["segments"]:
            check("data_clean_on_page", all((r["ber"].get("mismatches") or 0) == 0 for r in bl), "the run saw no error and the page did")
        if not params.get("with") and params["period"] >= 5:
            check("data_clean", res["clean"] == params["segments"], "no interference at %.3g Mbaud: %d of %d segments clean" % (
                100.0 / params["period"], res["clean"], params["segments"]))
    if kind in ("cw_far", "cw_near", "bursts"):
        lost_near = [r for r in during if r.get("state") == "lost" and r.get("off_khz") is not None and abs(r["off_khz"]) < 8]
        check("interference_not_lost", not lost_near, "%d looks 'Lost' with the oscillator at the lock" % len(lost_near))
    return out


def outcome(a):
    """in words: what the page showed"""
    s = a.get("states") or {}
    if a["linkd"]["losses"]:
        return "lost, %d recovered by linkd" % a["linkd"]["recoveries"]
    if a.get("slip"):
        return "slipped to the other lock point"
    if s.get("lost"):
        return "lost, back by itself"
    if s.get("holdover") and not s.get("nocarrier"):
        return "held through it (the holdover)"
    if s.get("nocarrier") or s.get("holdover"):
        return "no carrier"
    if s.get("interfered") or s.get("unsettled"):
        return "interfered"
    return "rode it out"


# ---- the disturbances ----
def draw(kind, rng, d0):
    lu = lambda a, b: math.exp(rng.uniform(math.log(a), math.log(b)))       # noqa: E731 - log-uniform
    sign = rng.choice((-1, 1))
    if kind == "cw_far":
        return {"off_mhz": round(sign * lu(0.2, 40.0), 3), "gain": round(rng.uniform(70, 89.75), 2), "seconds": round(rng.uniform(0.5, 12), 2)}
    if kind == "cw_near":
        return {"off_khz": round(sign * lu(0.5, 80.0), 2), "gain": round(rng.uniform(70, 89.75), 2), "seconds": round(rng.uniform(0.5, 8), 2)}
    if kind == "bursts":
        on = lu(0.01, 3.0)
        return {"bw_mhz": round(rng.uniform(1, 8), 2), "off_mhz": round(rng.uniform(-3, 3), 3), "on_ms": round(on, 4),
                "per_ms": round(lu(max(1.5 * on, 0.05), 300.0), 4), "gain": round(rng.uniform(70, 89.75), 2),
                "seconds": round(rng.uniform(3, 40), 1), "seed": rng.randrange(1 << 16)}
    if kind == "release":
        k = round(rng.uniform(-400, 400), 1)
        return {"off_khz": k, "predicted": predict_release(k)}
    if kind == "carrier_off":
        return {"seconds": round(lu(0.01, 60.0), 3)}
    if kind in ("symbols", "data"):
        if kind == "symbols":
            period = int(round(lu(32, 4000)))
            p = {"scheme": rng.choice(("A1", "A1w", "A2", "A3")), "period": period,
                 "width": int(rng.uniform(2, max(3, min(40, period // 2)))), "seconds": round(rng.uniform(0.5, 6), 2)}
        else:
            p = {"period": int(round(lu(2, 100))), "seconds": round(rng.uniform(3, 15), 1)}
            p["segments"] = max(2, int(p["seconds"] // 1.5))
        w = rng.choice(("none", "none", "cw_far", "cw_near", "bursts"))
        if w != "none":
            q = draw(w, rng, d0)
            q["seconds"] = round(p["seconds"] + 1.5, 2)          # it starts first and covers the run
            p["with"] = dict(q, kind=w)
        return p
    if kind == "attn":
        dd = 0.0
        while abs(dd) < 0.5 or not 6.0 <= d0 + dd <= 31.75:
            dd = round(rng.uniform(-6, 6) * 4) / 4
        return {"db": dd, "seconds": round(rng.uniform(5, 30), 1)}
    raise ValueError(kind)


def describe(kind, p):
    if kind == "cw_far":
        return "B210: CW %+.2f MHz from the carrier at gain %.2f for %.1f s" % (p["off_mhz"], p["gain"], p["seconds"])
    if kind == "cw_near":
        return "B210: CW %+.1f kHz from the carrier at gain %.2f for %.1f s" % (p["off_khz"], p["gain"], p["seconds"])
    if kind == "bursts":
        return "B210: %.1f MHz noise bursts %+.2f MHz off the carrier, %.3g ms every %.3g ms at gain %.2f for %.0f s" % (
            p["bw_mhz"], p["off_mhz"], p["on_ms"], p["per_ms"], p["gain"], p["seconds"])
    if kind == "release":
        return "the loop released %+.0f kHz from the lock (the map predicts: %s)" % (p["off_khz"], p["predicted"])
    if kind == "carrier_off":
        return "the carrier switched off for " + (("%.0f ms" % (p["seconds"] * 1e3)) if p["seconds"] < 1 else ("%.1f s" % p["seconds"]))
    if kind == "attn":
        return "the attenuator %+.2f dB for %.0f s" % (p["db"], p["seconds"])
    if kind in ("symbols", "data"):
        w = p.get("with")
        tail = (", with the " + describe(w["kind"], w).replace("B210: ", "B210's ", 1)) if w else ", no interference"
        if kind == "symbols":
            return "single symbols of %s, one every %.3g us, %d clocks long, for %.1f s%s" % (
                SCHEME_TEXT[p["scheme"]], p["period"] * 1e-2, p["width"], p["seconds"], tail)
        return "BPSK PRBS15 data at %.3g Mbaud for %.0f s%s" % (100.0 / p["period"], p["seconds"], tail)
    return kind


class Soak:
    def __init__(self, mhz, world=False):
        self.mhz, self.world = mhz, world
        self._A = None
        from b210 import B210
        self.bb = B210()

    def board(self):
        """the bench's driver objects, made only when a disturbance needs the board (they make requests to it)"""
        if self._A is None:
            import autolock as A
            self._A = A.LinkdTest(b210=False)
            self._A.bb = self.bb
            if self.world:
                self._A.cl.bus.nodrive = True             # these requests stand in for the world: linkd stays on duty
        return self._A

    def b210(self, kind, p, announce=False):
        """one of the B210's interferers, as the kinds of the same name send it; announce: its own note, for the page's
        B210 lane (a data run's interferer, inside the run's note)"""
        mhz = self.mhz
        note = {}
        if announce:
            # ended when the radio stops: it starts streaming up to a second after the call, so a note ended at its start
            # plus its length closed early (a scope capture of the CW's beat was captioned 'the B210 was quiet', 22:36)
            t = time.time()
            note = post("/api/note", {"text": describe(kind, p), "kind": "intervention", "source": "soak.py", "t_start": t,
                                      "t_end": t + p["seconds"] + 5.0, "b210": dict(p, kind=kind)})
        try:
            self._b210(kind, p, mhz)
        finally:
            if note.get("id"):
                post("/api/note", {"id": note["id"], "end": True})

    def _b210(self, kind, p, mhz):
        if kind == "cw_far":
            self.bb.tone(mhz + p["off_mhz"], gain=p["gain"], seconds=p["seconds"])
        elif kind == "cw_near":
            self.bb.tone(mhz + 2.0, gain=p["gain"], seconds=p["seconds"], offset_hz=p["off_khz"] * 1e3 - 2e6, rate=5e6)
        elif kind == "bursts":
            self.bb.bursts(mhz + p["off_mhz"], gain=p["gain"], bw_mhz=p["bw_mhz"], on_ms=p["on_ms"], off_ms=p["per_ms"] - p["on_ms"],
                           seconds=p["seconds"], seed=p["seed"])

    def scope_capture(self, B, kind, p, out):
        """the bench scope's I MON (ch2) and Q MON (ch3) during a data run, its timebase put back after: about ten symbols
        across the screen, or 10 us of data"""
        sc = B.s
        try:
            time.sleep(min(1.0, 0.3 * p["seconds"]))
            old = sc.timebase()[0]
            tdiv = max(1e-7, 4 * p["period"] * 1e-8) if kind == "data" else max(1e-6, min(50e-6, 0.3 * p["period"] * 1e-8))
            sc.timebase(scale=tdiv)
            time.sleep(0.3)
            try:
                sc.single(timeout=3.0)
            except TimeoutError:
                sc.acquire_now()
            t2, v2, _ = sc.waveform(2)
            t3, v3, _ = sc.waveform(3)
            sc.run()
            sc.timebase(scale=float(old))
            k = max(1, len(v2) // 6000)
            out.update(t=time.time(), i=[float(v) for v in v2[::k]], q=[float(v) for v in v3[::k]],
                       dt_ns=float(t2[1] - t2[0]) * 1e9 * k if len(t2) > 1 else 0.0)
        except Exception as e:                                   # noqa: BLE001 - the run goes on without a picture
            out["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])

    def disturb(self, kind, p, r0, shots_at):
        """does it; returns the marks (times) of its steps"""
        mhz, marks = self.mhz, {}
        def later(dt, name):
            if dt is not None:
                threading.Timer(dt, lambda: marks.__setitem__("shot", shot(name))).start()
        if kind in ("cw_far", "cw_near", "bursts"):
            later(shots_at and shots_at * p["seconds"], kind)
            self.b210(kind, p, announce=True)
        elif kind == "release":
            B = self.board()
            vc_lock = r0["vc_lock"]
            st = {"dsa": r0["dsa_db"], "vc_lock": vc_lock}
            B.release_at(mhz, st, vc_lock + p["off_khz"] * 1e3 / B.kv(mhz), settle_s=0.0)
            marks["released"] = time.time()
            later(shots_at and 4 + 10 * shots_at, "release")
            time.sleep(15.0)
        elif kind == "carrier_off":
            # one write each way (CTRL bit 0, TX_DIS), so that a short interruption is as short as asked
            B = self.board()
            v = B.cl.rd("CTRL")
            later(shots_at and shots_at * p["seconds"] if p["seconds"] > 2 else None, "carrier_off")
            B.cl.wr("CTRL", (v | 1) & ~0x80)
            marks["muted"] = time.time()
            time.sleep(p["seconds"])
            B.cl.wr("CTRL", v & ~1 & ~0x80)
            marks["unmuted"] = time.time()
            p["actual_s"] = round(marks["unmuted"] - marks["muted"], 4)
        elif kind in ("symbols", "data"):
            B = self.board()
            side = 1 if (r0.get("adc") or {}).get("I", 0) > (r0.get("i0") or 1.65) else -1
            w = p.get("with")
            th = None
            if w:
                th = threading.Thread(target=self.b210, args=(w["kind"], w, True), daemon=True)
                th.start()
                time.sleep(0.8)                                  # the B210's stream running before the data starts
                marks["interference"] = time.time()
            cap = {}
            ct = threading.Thread(target=self.scope_capture, args=(B, kind, p, cap), daemon=True)
            later(shots_at and 0.5 + shots_at * p["seconds"], kind)
            marks["data_start"] = time.time()
            ct.start()
            try:
                if kind == "symbols":
                    count = max(10, int(p["seconds"] / (p["period"] * 1e-8)))
                    p["count"] = count
                    # the receiver's decision window inside the symbol period (100 clocks over a 64-clock period made
                    # the counts inconsistent, soak10 #10; campaign.rate's rule)
                    st = B.scheme_run(p["scheme"], side, count=count, period=p["period"], width=p["width"],
                                      window=max(4, min(100, p["period"] - 6)))
                    time.sleep(1.5)                              # a look of the page's with the counts final
                    marks["result"] = {k: st.get(k) for k in ("events", "decided", "right", "symbol_errors", "false", "missed",
                                                              "confirm", "veto", "lat_n", "lat_min", "lat_max", "lat_mean", "sample_ns")}
                else:
                    seg = B.segs(side, p["period"], 0, n=p["segments"], seconds=p["seconds"] / p["segments"])
                    marks["result"] = {k: seg[k] for k in ("clean", "inverted", "beating", "partial", "bits", "err_bits_partial", "rates")}
            finally:
                if kind == "symbols":
                    B.cl.rx_enable(False)
            marks["data_end"] = time.time()
            ct.join(timeout=30)
            if th:
                th.join(timeout=p["seconds"] + 30)
            if cap.get("i"):
                w_ = p.get("with")
                q = post("/api/scope", {"t": cap["t"], "text": describe(kind, p) + " (soak #%d)" % getattr(self, "_n", 0), "source": "soak.py",
                                        "dt_ns": cap["dt_ns"], "i0": r0.get("i0"), "q0": r0.get("q0"), "i": cap["i"], "q": cap["q"],
                                        "kind": kind, "period_ns": p["period"] * 10.0, "width_ns": p.get("width", 0) * 10.0 or None,
                                        "scheme": p.get("scheme", ""), "leg": (r0.get("leg_ref_mv") or 160) / 1000.0,
                                        "link": describe(kind, dict(p, **{"with": None})).replace(", no interference", "") + " (soak.py)",
                                        "b210": describe(w_["kind"], w_).replace("B210: ", "sent ", 1) if w_ else "quiet"})
                marks["scope"] = {"t": cap["t"], "n": len(cap["i"]), "posted": bool(q)}
            elif cap.get("error"):
                marks["scope"] = {"error": cap["error"]}
        elif kind == "attn":
            B = self.board()
            d0 = float(r0["dsa_db"])
            B.cl.dsa(d0 + p["db"])
            marks["up"] = time.time()
            later(shots_at and shots_at * p["seconds"], "attn")
            time.sleep(p["seconds"])
            B.cl.dsa(d0)
            marks["back"] = time.time()
        return marks

    def trial(self, n, kind, p, shots_at, path):
        self._n = n
        r0 = now_or_none()
        if r0 is None:
            return None
        # an end 10 min on, in case this program dies before it ends the note (an open one would read 'under way' for ever)
        note = post("/api/note", {"text": describe(kind, p) + " (soak #%d)" % n, "kind": "intervention", "source": "soak.py",
                                  "t_end": time.time() + 600})
        t0 = time.time()
        err = None
        try:
            marks = self.disturb(kind, p, r0, shots_at)
        except Exception as e:                                   # noqa: BLE001 - the B210 or the board: recorded, go on
            marks, err = {}, "%s: %s" % (type(e).__name__, e)
            if kind in DRIVES:
                self._A = None                                   # a fresh client next time (the server may have restarted)
        t_end = time.time()
        back = wait(lambda r: ready_(r) and time.time() - t_end > 3, 400)
        t_back = time.time() if back else None
        if note.get("id"):
            post("/api/note", {"id": note["id"], "end": True})
        time.sleep(15.0)                                         # looks after it, for the levels as before
        a = audit(t0, t_end, t_back, note.get("id"), kind, p, marks)
        bad = [c for c in a["checks"] if c["ok"] is False]
        if bad:
            marks["shot_after"] = shot("soak%03d_%s_after" % (n, kind))
        rec = {"n": n, "kind": kind, "params": p, "t0": t0, "t_end": t_end, "t_back": t_back, "back_s": (t_back - t_end) if t_back else None,
               "marks": marks, "error": err, "outcome": outcome(a), **a}
        with open(path, "a") as f:
            f.write(json.dumps(rec, default=float) + "\n")
        extra = ""
        if kind == "release":
            extra = " rest %s" % (a.get("rest") or {}).get("class")
        elif kind == "carrier_off":
            extra = " (off %.3f s) rest %s" % (p.get("actual_s", p["seconds"]), (a.get("rest") or {}).get("class"))
        elif kind == "symbols" and marks.get("result"):
            x = marks["result"]
            extra = " | %s sent: %s right, %s wrong, %s false, %s missed; latency %s ns" % (
                x.get("events"), x.get("right"), x.get("symbol_errors"), x.get("false"), x.get("missed"),
                ("%.0f-%.0f" % (x["lat_min"] * x["sample_ns"], x["lat_max"] * x["sample_ns"])) if x.get("lat_n") and x.get("sample_ns") else "-")
        elif kind == "data" and marks.get("result"):
            x = marks["result"]
            extra = " | %d segments: %d clean, %d inverted, %d beating, %d partial; %.3g bits, %.0f bit errors in the partial ones" % (
                p["segments"], x["clean"], x["inverted"], x["beating"], x["partial"], x["bits"], x["err_bits_partial"])
        elif kind == "attn" and a.get("attn") and a["attn"]["ant_db"] is not None:
            extra = " dem %+.1f, RX ANT %+.1f dB" % (a["attn"]["dem_db"], a["attn"]["ant_db"])
        print("%s #%-3d %-11s %s | %s%s, back %s | %s" % (
            time.strftime("%H:%M:%S"), n, kind, describe(kind, p).replace("B210: ", "", 1), rec["outcome"], extra,
            ("%.1f s" % max(0.0, a["relocked_s"])) if a.get("relocked_s") is not None else
            ("%.1f s (linkd)" % rec["back_s"]) if rec["back_s"] is not None else "NEVER",
            ("all %d checks ok" % sum(1 for c in a["checks"] if c["ok"])) if not bad else
            "FLAGS: " + "; ".join("%s (%s)" % (c["name"], c["detail"]) for c in bad)) + (" ERROR " + err if err else ""), flush=True)
        return rec

    def run(self, hours, gap, seed, p_shot, kinds, holdover=False):
        if holdover:
            note = post("/api/note", {"text": "the signal holdover switched on for a soak run (it holds the loop while no carrier is "
                                      "seen; off in deployment so far)", "kind": "info", "source": "soak.py"})
            self.board().cl.shold(True)
            try:
                return self._run(hours, gap, seed, p_shot, kinds, holdover)
            finally:
                try:
                    self.board().cl.shold(False)
                except Exception:                                # noqa: BLE001 - the server restarted: a fresh client
                    self._A = None
                    self.board().cl.shold(False)
                print("%s the signal holdover off again" % time.strftime("%H:%M:%S"), flush=True)
                if note.get("id"):
                    post("/api/note", {"id": note["id"], "end": True})
        return self._run(hours, gap, seed, p_shot, kinds, holdover)

    def _run(self, hours, gap, seed, p_shot, kinds, holdover):
        rng = random.Random(seed)
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, "soak_%s.jsonl" % time.strftime("%Y%m%d_%H%M%S"))
        with open(path, "a") as f:
            f.write(json.dumps({"start": time.time(), "mhz": self.mhz, "seed": seed, "gap": gap, "kinds": kinds,
                                "holdover": holdover}) + "\n")
        print("record %s, seed %d; waiting for the link locked with linkd active ..." % (path, seed), flush=True)
        t_stop = time.time() + hours * 3600
        n, seen, tally = 0, set(), {}
        while time.time() < t_stop:
            if wait(ready_, 900) is None:
                print("%s the link not locked with linkd active for 15 min: stopping" % time.strftime("%H:%M:%S"), flush=True)
                break
            time.sleep(rng.uniform(*gap))
            r = now_or_none()
            if r is None or not ready_(r):
                continue
            kind = rng.choices(list(kinds), [KINDS[k] for k in kinds])[0]
            p = draw(kind, rng, float(r.get("dsa_db") or 20.0))
            n += 1
            sa = rng.uniform(0.3, 0.8) if (kind not in seen or rng.random() < p_shot) else None
            seen.add(kind)
            try:
                rec = self.trial(n, kind, p, sa, path)
            except Exception as e:                               # noqa: BLE001 - recorded, and the run goes on
                print("%s #%d %s: the trial failed: %s: %s" % (time.strftime("%H:%M:%S"), n, kind, type(e).__name__, e), flush=True)
                continue
            if rec is None:
                continue
            for c in rec["checks"]:
                t = tally.setdefault(c["name"], [0, 0])
                t[0 if c["ok"] is not False else 1] += 1
            if n % 20 == 0:
                print("after %d: checks failed %s" % (n, {k: v[1] for k, v in tally.items() if v[1]}), flush=True)
        with open(path, "a") as f:
            f.write(json.dumps({"summary": tally, "n": n}) + "\n")
        print("summary: %d disturbances; checks (ok, failed): %s" % (n, json.dumps(tally)), flush=True)


def audit_file(path):
    """the checks on an earlier run's records (unattended.py's: t, seconds, back_s)"""
    for line in open(path):
        d = json.loads(line)
        if "kind" not in d:
            continue
        t0 = d.get("t0", d.get("t"))
        t_end = d.get("t_end") or (t0 + d.get("seconds", 0))
        t_back = d.get("t_back") or ((t_end + d["back_s"]) if d.get("back_s") is not None else None)
        a = audit(t0, t_end, t_back, None, d["kind"] if d["kind"] in KINDS else None, d.get("params"), d.get("marks"),
                  t_fetch=(t_back or t_end) + 15)
        bad = [c for c in a["checks"] if c["ok"] is False]
        print("%s %-10s %s | %s, linkd %s | %s" % (time.strftime("%H:%M:%S", time.localtime(t0)), d["kind"],
              ", ".join("%s %s" % (k, d[k]) for k in ("gain", "off_mhz", "off_khz", "on_ms", "per_ms", "seconds") if k in d),
              outcome(a), a["linkd"], "ok" if not bad else "FLAGS: " + "; ".join("%s (%s)" % (c["name"], c["detail"]) for c in bad)),
              flush=True)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=["run", "audit"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--mhz", type=float, default=5200.0)
    ap.add_argument("--hours", type=float, default=12.0)
    ap.add_argument("--gap", type=float, nargs=2, default=(20.0, 90.0))
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--shots", type=float, default=0.3)
    ap.add_argument("--kinds", nargs="*", default=list(KINDS))
    ap.add_argument("--holdover", action="store_true")
    ap.add_argument("--world", action="store_true", help="the board's self-test runs: only the B210 and the world's stand-ins "
                    "(the carrier cut, the attenuator stepped: a blocked path, a moved antenna) without pausing linkd")
    a = ap.parse_args(argv)
    if a.what == "audit":
        audit_file(a.file)
        return
    seed = a.seed if a.seed is not None else int(time.time()) % 100000
    kinds = a.kinds
    if a.world and kinds == list(KINDS):
        kinds = ["cw_far", "cw_near", "bursts", "carrier_off", "attn"]
    Soak(a.mhz, world=a.world).run(a.hours, tuple(a.gap), seed, a.shots, kinds, a.holdover)


if __name__ == "__main__":
    main(sys.argv[1:])
