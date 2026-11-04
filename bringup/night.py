#!/usr/bin/env python3
"""night.py: board A over the two 24 dBi grids across the room, the night of 2026-11-03 (Jason: "run tests at many
different frequencies and settings all night.  Anything that you can control about the RF link should be tested.  You
should sweep for WiFi interference").  The path: TX ANT -> cable A -> grid -> about 15.6 m of room -> grid -> cable B ->
RX ANT, -50.3 dB at 5.2 GHz, 139.75 ns (BRINGUP_LOG 4.43); C102 off (4.44).  The board's own machinery does the work:
linkd's setup from link.json at each carrier, the self-test's rounds (BPSK and OOK data with their bit errors, single
symbols, QPSK), the page's record; this program sets the conditions and reads the results.

    python3 bringup/night.py survey [--step 5]            the 5 GHz band's interference: the board's receiver (survey(),
                                                          its TX off, the loop held) and the laptop's WiFi scan
    python3 bringup/night.py carriers [--mhz ...] [--minutes 8]   per carrier: link.json, the server restarted (linkd's
                                                          setup), the self-test for --minutes; link.json back after
    python3 bringup/night.py levels [--dsa ...] [--minutes 3]     the DSA stepped as a change of path loss ('nodrive':
                                                          linkd and the self-test stay on duty), the self-test at each
    python3 bringup/night.py gaps [--n 20] [--holdover]   the carrier muted 10 ms - 60 s at random (nodrive), what linkd
                                                          and the page make of each; with --holdover the self-test's
                                                          holdover on for the run and off after
    python3 bringup/night.py wifi [--minutes 10] [--hours 8]      the laptop's WiFi scan every --minutes (read only)

Each writes JSON lines to bringup/data/board_A/night/<section>_<time>.jsonl (not committed) and prints a summary.
The watchdog (stages.watch) runs beside: a server restart is announced to it first (bench.py's WATCH_PAUSE).
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("COSTAS_BENCH_CONFIG", os.path.join(HERE, "bench_config_laptop.json"))
import bench as B                                                     # noqa: E402

PAGE = "http://192.168.2.99:8080"
CONSOLE = "/dev/serial/by-id/usb-Xilinx_TUL_1234-tul-if01-port0"
SERVER_DIR = "/home/xilinx/costaslink_current"
LINK = {"mhz": 5200, "vr": {"VR_I": 0.2552, "VR_Q": 0.2782}, "leg_target": 0.15, "window_frac": 0.5, "v_t2": 2.9,
        "dsa_min": 6.0}
OUT = os.path.join(HERE, "data", "board_A", "night")


# ---- the page (HTTP: not a client of the board, so it never pauses linkd) ----
def page(path, timeout=10):
    return json.loads(urllib.request.urlopen(PAGE + path, timeout=timeout).read())


def page_post(path, d):
    return json.loads(urllib.request.urlopen(urllib.request.Request(PAGE + path, data=json.dumps(d).encode(),
                                                                    method="POST"), timeout=10).read())


def now_state():
    try:
        d = page("/api/now")
    except Exception as e:                                       # noqa: BLE001 - the server restarting
        return {"error": str(e)[:80]}
    L = d.get("linkd") or {}
    det = d.get("det") or {}
    return {"t": d.get("t"), "state": d.get("state"), "mode": L.get("mode"), "dsa": d.get("dsa_db"), "leg": L.get("leg"),
            "leg_setup": L.get("leg_setup"), "losses": L.get("losses"), "recoveries": L.get("recoveries"),
            "failed": L.get("failed"), "log_dbm": det.get("log_dbm"), "peak_dbm": det.get("peak_dbm"),
            "temp_c": det.get("temp_c"), "v5_rf": det.get("v5_rf"), "tx_mhz": d.get("tx_mhz"), "rx_mhz": d.get("rx_mhz"),
            "adc": d.get("adc"), "step": ((d.get("selftest") or {}).get("now") or {}).get("step"),
            "shold": d.get("shold")}


def note(text, kind="info"):
    try:
        page_post("/api/note", {"text": text, "kind": kind, "source": "night.py"})
    except Exception:                                            # noqa: BLE001
        pass


# ---- the PYNQ's console (its sudo is allowed; no SSH key on it, Jason's rule) ----
def console(cmd, timeout=30.0):
    import serial
    s = serial.Serial(CONSOLE, 115200, timeout=0.3)
    try:
        s.write(b"\r")
        time.sleep(0.3)
        s.read(65536)
        s.write((cmd + "; echo @@E''ND_$?\r").encode())          # the echo of the line itself holds E''ND, not END
        buf, t0 = b"", time.time()
        while time.time() - t0 < timeout and b"@@END_" not in buf:
            buf += s.read(4096)
        return buf.decode("utf-8", "replace")
    finally:
        s.close()


def pause_watchdog(minutes):
    os.makedirs(os.path.dirname(B.WATCH_PAUSE), exist_ok=True)
    with open(B.WATCH_PAUSE, "w") as f:
        f.write("%.0f\n" % (time.time() + 60 * minutes))


def write_link(cfg):
    txt = json.dumps(cfg)
    assert "'" not in txt
    r = console("printf '%%s\\n' '%s' > %s/link.json && cat %s/link.json" % (txt, SERVER_DIR, SERVER_DIR))
    if '"mhz": %s' % json.dumps(cfg["mhz"]) not in r.split("printf", 1)[-1]:
        raise IOError("link.json not written: %r" % r[-300:])


def restart_server(wait_s=300.0):
    """the server restarted (linkd's setup from link.json); returns when the page reads locked, or the setup's
    failure, or after wait_s"""
    pause_watchdog(8)
    t0 = time.time()
    r = console("echo xilinx | sudo -S systemctl restart costaslink-netbus", timeout=60)
    if "@@END_0" not in r:
        raise IOError("restart: %r" % r[-300:])
    seen = []
    while time.time() - t0 < wait_s:
        time.sleep(5)
        s = now_state()
        seen.append((round(time.time() - t0), s.get("mode"), s.get("state"), s.get("dsa")))
        if s.get("state") == "locked" and s.get("mode") in ("locked", "watching"):
            s["setup_s"] = time.time() - t0
            return s, seen
        # 'setup found no carrier: trying again' is not the end: linkd tries again after its back-off (4500 MHz's first
        # setup failed and the sweep moved on, 2026-11-04 00:33)
    s = now_state()
    s["setup_s"] = time.time() - t0
    return s, seen


# ---- the self-test's results, summarised ----
def summarise(res):
    data, sym = {}, {}
    for r in res:
        if r.get("interrupted"):
            continue
        if r.get("step") == "data" and r.get("bits"):
            k = "%s %g Mbaud" % (r.get("mod", "bpsk"), r.get("mbaud"))
            d = data.setdefault(k, {"bits": 0, "errors": 0.0, "n": 0})
            d["bits"] += r["bits"]
            d["errors"] += r.get("errors") or 0
            d["n"] += 1
        elif r.get("step") in ("symbols", "qpsk") and r.get("sent"):
            k = "%s %s" % (r["step"], r.get("scheme"))
            d = sym.setdefault(k, {"sent": 0, "right": 0, "wrong": 0, "undecided": 0, "false": 0, "missed": 0, "n": 0,
                                   "lat_mean_ns": []})
            for f in ("sent", "right", "wrong", "undecided", "false", "missed"):
                d[f] += r.get(f) or 0
            d["n"] += 1
            if r.get("lat_ns"):
                d["lat_mean_ns"].append(r["lat_ns"][1])
    for d in data.values():
        d["ber"] = d["errors"] / d["bits"] if d["bits"] else None
    for d in sym.values():
        d["right_frac"] = d["right"] / d["sent"] if d["sent"] else None
        d["lat_mean_ns"] = sum(d["lat_mean_ns"]) / len(d["lat_mean_ns"]) if d["lat_mean_ns"] else None
    return {"data": data, "symbols": sym}


def fmt_summary(s):
    parts = ["%s BER %s (%d bits)" % (k, "%.1e" % v["ber"] if v["ber"] is not None else "-", v["bits"])
             for k, v in sorted(s["data"].items())]
    parts += ["%s right %.4f wrong %d false %d missed %d lat %s ns" % (
        k, v["right_frac"] or 0, v["wrong"], v["false"], v["missed"],
        "%.0f" % v["lat_mean_ns"] if v["lat_mean_ns"] else "-") for k, v in sorted(s["symbols"].items())]
    return "; ".join(parts)


COLLECTED = {}      # the self-test's results as they appear (the page keeps only the latest round), by (t0, step)


def collect_results():
    try:
        for r in page("/api/selftest").get("results") or []:
            if r.get("t0"):
                COLLECTED[(round(r["t0"], 3), r.get("step"), r.get("scheme"), r.get("mod"))] = r
    except Exception:                                            # noqa: BLE001
        pass


def results_between(t0, t1):
    collect_results()
    return [r for r in COLLECTED.values() if t0 <= r["t0"] and (r.get("t1") or 0) <= t1 + 1]


def watch_for(seconds, every=5.0):
    """the page every `every` s for `seconds`: the states seen, the lowest leg, the losses; the self-test's results
    collected on the way"""
    t0, rows = time.time(), []
    while time.time() - t0 < seconds:
        rows.append(now_state())
        collect_results()
        time.sleep(every)
    locked = [r for r in rows if r.get("state") == "locked"]
    return {"looks": len(rows), "locked_frac": len(locked) / max(1, len(rows)),
            "losses": [r.get("losses") for r in rows if r.get("losses") is not None][-1:] or [None],
            "dsa": sorted({r.get("dsa") for r in rows if r.get("dsa") is not None}),
            "leg_min": min([r["leg"] for r in rows if r.get("leg")], default=None),
            "leg_max": max([r["leg"] for r in rows if r.get("leg")], default=None),
            "log_dbm_med": (lambda v: v[len(v) // 2] if v else None)(sorted(r["log_dbm"] for r in rows if r.get("log_dbm"))),
            "temp_c": rows[-1].get("temp_c") if rows else None}


class Log:
    def __init__(self, section):
        os.makedirs(OUT, exist_ok=True)
        self.path = os.path.join(OUT, "%s_%s.jsonl" % (section, time.strftime("%Y-%m-%d_%H%M")))

    def __call__(self, **kw):
        kw.setdefault("t", time.time())
        with open(self.path, "a") as f:
            f.write(json.dumps(kw, default=str) + "\n")


# ---- sections ----
def laptop_wifi():
    """the laptop's own scan (read only: the connection stays as it is)"""
    try:
        out = subprocess.run(["nmcli", "-t", "-f", "SSID,BSSID,CHAN,FREQ,SIGNAL,RATE", "dev", "wifi", "list", "--rescan",
                              "yes"], capture_output=True, text=True, timeout=60).stdout
    except Exception as e:                                       # noqa: BLE001
        return {"error": str(e)}
    aps = []
    for line in out.splitlines():
        parts = line.replace("\\:", "\x00").split(":")
        if len(parts) >= 6:
            parts = [p.replace("\x00", ":") for p in parts]
            try:
                aps.append({"ssid": parts[0], "bssid": parts[1], "chan": int(parts[2]),
                            "mhz": int(parts[3].split()[0]), "signal": int(parts[4]), "rate": parts[5]})
            except ValueError:
                pass
    return {"aps": aps}


LADDER = [0.0005 * 1.35 ** k for k in range(20)]       # 0.5 mV to about 150 mV, each side of the arm's middle


def survey(step=5, lo=4900, hi=6000, seconds=0.005, park_tx=None):
    """the RX synthesizer stepped (5 MHz PFD), the TX disabled and the loop held, V_T2 scanned against the slow Q arm
    on both sides of its measured middle (the driver's survey() scans from V_MID up only: tonight's middle is 23 mV
    below it and nothing resolved), the Gaussian fitted where the duty is 0.1-0.9; the tail at 4 sigma for bursts"""
    import statistics
    log = Log("survey_txparked" if park_tx else "survey")
    b = B.Bench("A", "night")
    st0 = now_state()
    mhz0 = int(st0.get("rx_mhz") or 5200)
    fs = list(range(lo, hi + 1, step))
    ctrl0 = b.board_call("rd", "CTRL")
    rows, t0 = [], time.time()
    note("night.py: the band surveyed by the board's receiver (its TX off, the loop held) %d-%d MHz" % (lo, hi))
    nd = statistics.NormalDist()
    try:
        b.board_call("ctrl", tx_dis=1, loop_hold=1)
        if park_tx:                                      # the TX synthesizer moved out of the band: its own LO and
            b.board_call("pll_tune", 0, park_tx)         # sidebands are then not in the survey
        time.sleep(0.3)
        q0 = b.board_call("adc", "Q")
        volts = sorted([q0 - d for d in LADDER] + [q0] + [q0 + d for d in LADDER])
        for f in fs:
            b.board_call("pll_tune", 1, f, f_pfd=5.0, cp=15)
            time.sleep(0.005)
            pts = b.board_call("noise_scan", "slow", volts=volts, seconds=seconds)
            row = {"f_mhz": f, "q0": q0, "sigma": None, "v0": None, "dbm": None, "inr_db": None, "tail": None}
            z = [(v, nd.inv_cdf(1.0 - d)) for v, d in pts if 0.1 < d < 0.9]
            # three points at least, and the fit's middle inside the scan and its sigma under the scan's half-span: two
            # points made 5885 MHz '-44.1 dBm' with v0 5.05 V and sigma 3.2 V (2026-11-04 07:26), a line through anything
            if len(z) >= 3:
                n = len(z)
                mz, mv = sum(a for _, a in z) / n, sum(v for v, _ in z) / n
                szz = sum((a - mz) ** 2 for _, a in z)
                if szz > 0:
                    slope = sum((v - mv) * (a - mz) for v, a in z) / szz      # volts per unit z
                    sigma, v0 = abs(slope), mv - slope * mz
                if szz > 0 and not (volts[0] <= v0 <= volts[-1] and sigma < (volts[-1] - volts[0]) / 2):
                    row["fit"] = "implausible: v0 %.3f V, sigma %.3f V" % (v0, sigma)
                elif szz > 0:
                    dbm = b.board_call("sigma_to_dbm", sigma, "slow")
                    past = [d for v, d in pts if v > v0 + 4.0 * sigma]
                    row.update(sigma=sigma, v0=v0, dbm=dbm, inr_db=dbm - b.board_call("thermal_dbm", "slow"),
                               tail=past[0] if past else None)
            row["duty_max_far"] = max([d for v, d in pts if v - q0 > 0.02] or [0.0])   # bursts, 20 mV and more above
            rows.append(row)
            log(kind="survey", **row)
    finally:
        b.board_call("pll_tune", 1, mhz0)
        if park_tx:
            b.board_call("pll_tune", 0, int(st0.get("tx_mhz") or mhz0))
        b.board_call("dac", 0x61, V_T2=LINK["v_t2"])
        b.board_call("ctrl", tx_dis=ctrl0 & 1, loop_hold=ctrl0 >> 1 & 1)
    wifi = laptop_wifi()
    log(kind="laptop_wifi", **wifi)
    good = [r for r in rows if r.get("dbm") is not None]
    print("survey %d-%d MHz in %.0f s at DSA %s (Q's middle %.4f V): %d of %d resolved" % (
        lo, hi, time.time() - t0, st0.get("dsa"), q0, len(good), len(rows)))
    for r in sorted(good, key=lambda x: -x["inr_db"])[:15]:
        print("  %d MHz: %.1f dBm in 7.5 MHz, %+.1f dB over the receiver's noise, tail %s, far duty %.4f" % (
            r["f_mhz"], r["dbm"], r["inr_db"], r.get("tail"), r["duty_max_far"]))
    for r in sorted(rows, key=lambda x: -x["duty_max_far"])[:10]:
        if r["duty_max_far"] > 1e-3:
            print("  bursts at %d MHz: duty %.4f more than 20 mV from the middle" % (r["f_mhz"], r["duty_max_far"]))
    med = sorted(r["inr_db"] for r in good)[len(good) // 2] if good else None
    print("  the median INR %s dB" % ("%.1f" % med if med is not None else "-"))
    aps5 = [a for a in wifi.get("aps", []) if a["mhz"] > 4900]
    print("laptop: %d networks, %d in 5 GHz: %s" % (len(wifi.get("aps", [])), len(aps5), ", ".join(
        "ch%d %d%%" % (a["chan"], a["signal"]) for a in sorted(aps5, key=lambda a: -a["signal"])[:15])))
    return rows, wifi


def survey_driver(step=5, lo=5150, hi=5850, chunk=8):
    log = Log("survey")
    b = B.Bench("A", "night")
    st0 = now_state()
    mhz0 = st0.get("rx_mhz") or 5200
    rows = []
    fs = list(range(lo, hi + 1, step))
    t0 = time.time()
    note("night.py: the band surveyed by the board's receiver (its TX off, the loop held) %d-%d MHz" % (lo, hi))
    try:
        for i in range(0, len(fs), chunk):
            part = fs[i:i + chunk]
            r = b.board_call("survey", part, restore_mhz=mhz0)
            for row in r:
                row.pop("points", None)
                rows.append(row)
                log(kind="survey", **row)
    finally:
        pass
    wifi = laptop_wifi()
    log(kind="laptop_wifi", **wifi)
    good = [r for r in rows if r.get("dbm") is not None]
    print("survey %d-%d MHz in %.0f s at DSA %s: %d of %d resolved" % (lo, hi, time.time() - t0, st0.get("dsa"), len(good),
                                                                     len(rows)))
    for r in sorted(good, key=lambda x: -x["inr_db"])[:12]:
        print("  %d MHz: %.1f dBm in 7.5 MHz, %+.1f dB over the receiver's noise, tail %s" % (
            r["f_mhz"], r["dbm"], r["inr_db"], r.get("tail")))
    med = sorted(r["inr_db"] for r in good)[len(good) // 2] if good else None
    print("  the median INR %s dB" % ("%.1f" % med if med is not None else "-"))
    aps5 = [a for a in wifi.get("aps", []) if a["mhz"] > 4900]
    print("laptop: %d networks, %d in 5 GHz: %s" % (len(wifi.get("aps", [])), len(aps5), ", ".join(
        "ch%d %d%%" % (a["chan"], a["signal"]) for a in sorted(aps5, key=lambda a: -a["signal"])[:15])))
    return rows, wifi


def carriers(mhzs, minutes=8.0, dsa_min=None):
    log = Log("carriers")
    out = []
    try:
        for mhz in mhzs:
            cfg = dict(LINK, mhz=mhz, **({} if dsa_min is None else {"dsa_min": dsa_min}), note="night.py %s: the carrier sweep; the original is link.json.bak_20261103" %
                       time.strftime("%Y-%m-%d %H:%M"))
            write_link(cfg)
            st, seen = restart_server()
            row = {"mhz": mhz, "setup": st, "seen": seen}
            print("%s %d MHz: %s after %.0f s, DSA %s, leg %s (setup %s)" % (
                time.strftime("%H:%M:%S"), mhz, st.get("mode"), st.get("setup_s", 0), st.get("dsa"),
                "%.3f" % st["leg"] if st.get("leg") else None, "%.3f" % st["leg_setup"] if st.get("leg_setup") else None),
                flush=True)
            if st.get("state") == "locked":
                t0 = time.time()
                w = watch_for(60 * minutes)
                s = summarise(results_between(t0, time.time()))
                row.update(watch=w, summary=s)
                print("    locked %.0f %% of %d looks, losses %s, DSA %s, leg %s-%s, LOG %s dBm, %.1f C" % (
                    100 * w["locked_frac"], w["looks"], w["losses"], w["dsa"], w["leg_min"], w["leg_max"],
                    w["log_dbm_med"], w["temp_c"] or 0), flush=True)
                print("    " + fmt_summary(s), flush=True)
            log(kind="carrier", **row)
            out.append(row)
    finally:
        write_link(dict(LINK, note="board A over the air (BRINGUP_LOG 4.0, 4.15); restored by night.py %s" %
                        time.strftime("%Y-%m-%d %H:%M")))
        st, _ = restart_server()
        print("%s back at 5200 MHz: %s, DSA %s" % (time.strftime("%H:%M:%S"), st.get("mode"), st.get("dsa")), flush=True)
        log(kind="restored", **st)
    return out


def levels(dsas, minutes=3.0):
    """the DSA stepped as the world would change the path (nodrive: linkd and the self-test stay on duty)"""
    log = Log("levels")
    b = B.Bench("A", "night")
    b.cl.bus.nodrive = True
    st0 = now_state()
    dsa0 = st0.get("dsa")
    print("%s levels at %s MHz from DSA %s" % (time.strftime("%H:%M:%S"), st0.get("rx_mhz"), dsa0), flush=True)
    out = []
    try:
        for dsa in dsas:
            b.board_call("dsa", dsa)
            t0 = time.time()
            w = watch_for(60 * minutes)
            s = summarise(results_between(t0 + 20, time.time()))   # 20 s for the self-test's windows to follow
            row = {"mhz": st0.get("rx_mhz"), "dsa": dsa, "watch": w, "summary": s}
            log(kind="level", **row)
            out.append(row)
            print("%s DSA %5.2f: locked %.0f %%, losses %s, leg %s-%s, LOG %s dBm\n    %s" % (
                time.strftime("%H:%M:%S"), dsa, 100 * w["locked_frac"], w["losses"], w["leg_min"], w["leg_max"],
                w["log_dbm_med"], fmt_summary(s)), flush=True)
    finally:
        if dsa0 is not None:
            b.board_call("dsa", dsa0)
            print("%s DSA back at %s" % (time.strftime("%H:%M:%S"), dsa0), flush=True)
    return out


def gaps(n=20, holdover=False, gap_s=(30, 60), seed=None):
    """the carrier muted for 10 ms - 60 s (log-uniform), as the world would (a blocked path, the far TX off)"""
    log = Log("gaps_holdover" if holdover else "gaps")
    rnd = random.Random(seed if seed is not None else int(time.time()))
    b = B.Bench("A", "night")
    b.cl.bus.nodrive = True
    if holdover:
        page_post("/api/selftest", {"holdover": True})
    out = []
    try:
        for k in range(n):
            dur = math.exp(rnd.uniform(math.log(0.01), math.log(60.0)))
            before = now_state()
            t0 = time.time()
            b.board_call("ctrl", tx_dis=1)
            time.sleep(dur)
            b.board_call("ctrl", tx_dis=0)
            t1 = time.time()
            back, looks = None, []
            while time.time() - t1 < 180:
                s = now_state()
                looks.append((round(time.time() - t1, 1), s.get("state"), s.get("mode")))
                if s.get("state") == "locked" and s.get("mode") in ("locked", "watching") and time.time() - t1 > 2:
                    back = time.time() - t1
                    break
                time.sleep(1.0)
            after = now_state()
            try:
                ev = [e for e in page("/api/events") if e.get("t", 0) >= t0 - 1]
            except Exception:                                    # noqa: BLE001
                ev = []
            row = {"k": k, "muted_s": dur, "holdover": holdover, "locked_again_s": back,
                   "losses": (after.get("losses") or 0) - (before.get("losses") or 0),
                   "recoveries": (after.get("recoveries") or 0) - (before.get("recoveries") or 0),
                   "failed": (after.get("failed") or 0) - (before.get("failed") or 0),
                   # the holdover's own counts across the gap (gap 13 of 2026-11-04 04:51, held on, lost 1.7 s into a
                   # 15.8 s mute: whether the hold let go or never took could not be told from the page's states)
                   "holds": ((after.get("shold") or {}).get("holds") or 0) - ((before.get("shold") or {}).get("holds") or 0),
                   "held_s": ((after.get("shold") or {}).get("seconds") or 0) - ((before.get("shold") or {}).get("seconds") or 0),
                   "events": [(round(e["t"] - t0, 2), e.get("kind"), e.get("text", "")[:90]) for e in ev], "looks": looks[:8]}
            log(kind="gap", **row)
            out.append(row)
            print("%s gap %2d: muted %7.3f s -> locked again %s s after; losses %d, recoveries %d, failed %d; %s" % (
                time.strftime("%H:%M:%S"), k, dur, "%.1f" % back if back is not None else "NOT", row["losses"],
                row["recoveries"], row["failed"], "; ".join("%s %s" % (e[1], e[2][:50]) for e in row["events"][:3])),
                flush=True)
            time.sleep(rnd.uniform(*gap_s))
    finally:
        b.board_call("ctrl", tx_dis=0)
        if holdover:
            page_post("/api/selftest", {"holdover": False})
    return out


def agc(hours=1.0, target=None, tol_db=1.5, every=15.0, hold=3, world=None, seed=None, dsa_min=6.0):
    """a slow AGC outside linkd (Jason, 2026-11-03 23:40: 'having some sense of (even slow and occasional) AGC and
    comparator level setting would be good'): every `every` s the I leg linkd learns on the idle carrier, against
    `target` (linkd's setup leg unless given); off by more than tol_db for `hold` looks in a row, the DSA stepped by the
    difference (0.25 dB steps, dsa_min to 31.75), as nodrive so linkd and the self-test stay on duty and the windows
    follow by their own rules (linkd's tracking, the self-test's calibration).  world=(lo_db, hi_db, gap_lo_s, gap_hi_s):
    the path changed at random meanwhile, as the DSA moved by an offset the AGC has to take back (the only level knob)"""
    log = Log("agc")
    rnd = random.Random(seed if seed is not None else int(time.time()))
    b = B.Bench("A", "night")
    b.cl.bus.nodrive = True
    st = now_state()
    target = target or st.get("leg_setup") or LINK["leg_target"]
    dsa = st.get("dsa")
    print("%s AGC: target leg %.3f V, tolerance %.1f dB, from DSA %s" % (time.strftime("%H:%M:%S"), target, tol_db, dsa),
          flush=True)
    t_end, off, next_world = time.time() + 3600 * hours, 0, time.time() + (rnd.uniform(*world[2:]) if world else 1e18)
    steps = []
    while time.time() < t_end:
        time.sleep(every)
        collect_results()
        s = now_state()
        if s.get("dsa") is not None:
            dsa = s["dsa"]
        if world and time.time() >= next_world:
            d = rnd.choice((-1, 1)) * rnd.uniform(world[0], world[1])
            new = max(dsa_min, min(31.75, round((dsa + d) * 4) / 4))
            b.board_call("dsa", new)
            log(kind="world", dsa_from=dsa, dsa_to=new, db=new - dsa)
            print("%s world: the path %+.2f dB (DSA %.2f -> %.2f)" % (time.strftime("%H:%M:%S"), new - dsa, dsa, new),
                  flush=True)
            dsa, off = new, 0
            next_world = time.time() + rnd.uniform(*world[2:])
            continue
        if s.get("state") != "locked" or not s.get("leg"):
            off = 0
            continue
        err_db = 20 * math.log10(s["leg"] / target)
        off = off + 1 if abs(err_db) > tol_db else 0
        if off >= hold:
            new = max(dsa_min, min(31.75, round((dsa + err_db) * 4) / 4))
            if new != dsa:
                b.board_call("dsa", new)
                steps.append((time.time(), dsa, new, err_db))
                log(kind="agc", leg=s["leg"], err_db=err_db, dsa_from=dsa, dsa_to=new)
                print("%s AGC: leg %.3f V (%+.1f dB) -> DSA %.2f -> %.2f" % (time.strftime("%H:%M:%S"), s["leg"], err_db,
                                                                           dsa, new), flush=True)
                dsa = new
            off = 0
    return steps


def wifi(minutes=10.0, hours=8.0):
    log = Log("wifi")
    t_end = time.time() + 3600 * hours
    while time.time() < t_end:
        w = laptop_wifi()
        log(kind="laptop_wifi", **w)
        aps5 = [a for a in w.get("aps", []) if a["mhz"] > 4900]
        print("%s %d networks, %d at 5 GHz; strongest: %s" % (time.strftime("%H:%M:%S"), len(w.get("aps", [])), len(aps5),
              ", ".join("ch%d %d%%" % (a["chan"], a["signal"]) for a in sorted(aps5, key=lambda a: -a["signal"])[:6])),
              flush=True)
        time.sleep(60 * minutes)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("section", choices=("survey", "carriers", "levels", "gaps", "wifi", "agc"))
    ap.add_argument("--mhz", type=float, nargs="+", default=[5150 + 50 * k for k in range(15)])
    ap.add_argument("--dsa", type=float, nargs="+", default=[6, 9, 12, 15, 18, 21, 24, 27, 30, 31.75])
    ap.add_argument("--minutes", type=float, default=None)
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--step", type=int, default=5)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--holdover", action="store_true")
    ap.add_argument("--dsa-min", type=float, default=None, help="carriers: link.json's dsa_min (setup's floor) for the run")
    ap.add_argument("--target", type=float, default=None, help="agc: the leg to hold, V (default linkd's setup leg)")
    ap.add_argument("--world", type=float, nargs=4, default=None, help="agc: path changes lo_db hi_db gap_lo_s gap_hi_s")
    ap.add_argument("--park-tx", type=int, default=None, help="survey: the TX synthesizer parked here meanwhile (MHz)")
    a = ap.parse_args()
    if a.section == "survey":
        survey(a.step, park_tx=a.park_tx)
    elif a.section == "carriers":
        carriers([int(m) for m in a.mhz], a.minutes or 8.0, a.dsa_min)
    elif a.section == "levels":
        levels(a.dsa, a.minutes or 3.0)
    elif a.section == "gaps":
        gaps(a.n, a.holdover)
    elif a.section == "agc":
        agc(a.hours, a.target, world=tuple(a.world) if a.world else None)
    else:
        wifi(a.minutes or 10.0, a.hours)


if __name__ == "__main__":
    main()
