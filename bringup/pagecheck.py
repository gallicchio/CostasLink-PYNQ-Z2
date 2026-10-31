#!/usr/bin/env python3
"""pagecheck.py: deliberate, slow disturbances that the status page (gateware/driver/dashboard.py) must show the right
way (Jason, 2026-10-31: run pull tests and other tests slow enough to check that each plot does the right thing).

    python3 bringup/pagecheck.py [--mhz 5200] [--kinds K ...] [--no-shots]

The link is set up from the PC (weekend.py's ready), then each trial is announced on the page (a note from
pagecheck.py that lasts until the page reads locked again), done, and watched only through the page's HTTP.  The page's
readings, twice a second, go to bringup/data/board_A/pagecheck/ with a verdict on what it should have shown, and a
screenshot of the page (headless Chromium) at the moment that tells:
    above      released 150 kHz above the lock: back to 0 by itself (the map: everything above drifts down), no loss
    between    released 30 kHz below, between the watersheds: rests in the false lock (-43..-49 kHz); linkd recovers it
    falselock  released 45 kHz below: rests in the false lock; linkd recovers it
    rail       released 300 kHz below: VC runs to its bottom rail (the offset off scale below); linkd recovers it
    blocked    the carrier off for 20 s (the TX muted): 'No carrier', the levels not measurable (hatched); back after
    attn       the attenuator 3 dB up for 20 s, then 3 dB down for 20 s: the demodulator's level follows it, RX ANT does not
    bursts     noise bursts at a beacon's rhythm (1 ms every 102.4 ms) at full power for 30 s: 'Interference' or
               'Locked', never 'Lost'; the RX ANT plot's orange line up, the carrier hatched
    cwnear     a CW 20 kHz below at full power for 5 s: the loop captured by it ('Lost', the offset -10..-35 kHz)
The drifts themselves (from +150 kHz to the lock, from -300 kHz to the rail) take 0.05-0.5 s, faster than the page's
look (one a second): the page shows where the loop comes to rest, the bench's map how it got there.  At the end the
link is left locked and released for linkd (not parked).
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import autolock as A                                 # noqa: E402

OUT = os.path.join(HERE, "data", "board_A", "pagecheck")
DASH = "http://192.168.8.142:8080"
KINDS = ("above", "between", "falselock", "rail", "blocked", "attn", "bursts", "cwnear")


def post(path, d):
    try:
        return json.loads(urllib.request.urlopen(urllib.request.Request(DASH + path, data=json.dumps(d).encode(), method="POST"),
                                                 timeout=5).read())
    except Exception:                                            # noqa: BLE001
        return {}


class Watch:
    """the page's /api/now twice a second, kept with the PC's time"""
    def __init__(self):
        self.rows, self._stop = [], False
        threading.Thread(target=self.run, daemon=True).start()

    def run(self):
        while not self._stop:
            try:
                r = json.loads(urllib.request.urlopen(DASH + "/api/now", timeout=3).read())
                r["t_pc"] = time.time()
                self.rows.append(r)
            except Exception:                                    # noqa: BLE001
                pass
            time.sleep(0.5)

    def since(self, t0, t1=None):
        return [r for r in self.rows if r["t_pc"] >= t0 and (t1 is None or r["t_pc"] <= t1)]


def shot(name):
    """the page as a viewer sees it, in the background (Chromium takes about 10 s)"""
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, "%s_%s.png" % (name, time.strftime("%H%M%S")))
    def go():
        subprocess.run(["chromium-browser", "--headless", "--disable-gpu", "--hide-scrollbars", "--window-size=1400,3000",
                        "--virtual-time-budget=8000", "--screenshot=" + p, DASH + "/"], capture_output=True, timeout=90)
    threading.Thread(target=go, daemon=True).start()
    return p


class PageCheck(A.LinkdTest):
    def trial(self, kind, mhz, st, W, shots):
        cl, kv = self.cl, self.kv(mhz)
        r0 = W.rows[-1] if W.rows else {}
        L0 = r0.get("linkd") or {}
        base = {k: r0.get(k) for k in ("rx_ant_dbm", "dem_dbm", "dsa_db", "off_khz")}
        what = {"above": "the loop released 150 kHz above the lock", "between": "the loop released 30 kHz below the lock",
                "falselock": "the loop released 45 kHz below the lock (into the false lock)",
                "rail": "the loop released 300 kHz below the lock (to the rail)", "blocked": "the carrier switched off for 20 s",
                "attn": "the attenuator 3 dB up for 20 s, then 3 dB down for 20 s",
                "bursts": "B210: noise bursts at a WiFi beacon's rhythm at full power for 30 s",
                "cwnear": "B210: a CW 20 kHz below the carrier at full power for 5 s"}[kind]
        n = post("/api/note", {"text": what + " (a check of this page)", "kind": "intervention", "source": "pagecheck.py"})
        t0 = time.time()
        marks = {}
        if kind in ("above", "between", "falselock", "rail"):
            k = {"above": 150, "between": -30, "falselock": -45, "rail": -300}[kind]
            self.release_at(mhz, st, st["vc_lock"] + k * 1e3 / kv, settle_s=0.0)
            marks["released"] = time.time()
            time.sleep(8.0)
            if shots and kind != "above":
                marks["shot"] = shot(kind)
        elif kind == "blocked":
            cl.ctrl(tx_dis=1)
            time.sleep(10.0)
            if shots:
                marks["shot"] = shot(kind)
            time.sleep(10.0)
            self.tx(True)
        elif kind == "attn":
            d0 = float(st["dsa"])
            cl.dsa(d0 + 3.0)
            marks["up"] = time.time()
            time.sleep(20.0)
            cl.dsa(d0 - 3.0)
            marks["down"] = time.time()
            time.sleep(10.0)
            if shots:
                marks["shot"] = shot(kind)
            time.sleep(10.0)
            cl.dsa(d0)
            marks["back"] = time.time()
        elif kind == "bursts":
            th = self.bg(self.bb.bursts, mhz, gain=89.75, bw_mhz=8.0, on_ms=1.0, off_ms=101.4, seconds=30.0)
            time.sleep(20.0)
            if shots:
                marks["shot"] = shot(kind)
            th.join(timeout=40)
        elif kind == "cwnear":
            th = self.bg(self.bb.tone, mhz + 2.0, gain=89.75, seconds=5.0, offset_hz=-20e3 - 2e6, rate=5e6)
            time.sleep(3.5)
            if shots:
                marks["shot"] = shot(kind)
            th.join(timeout=10)
        t_end = time.time()

        # back: the page locked with linkd locked, and a few seconds of it
        def done_(x):
            return x.get("state") == "locked" and (x.get("linkd") or {}).get("mode") == "locked" and time.time() - t_end > 5
        back, _ = self.wait_linkd(done_, 240)
        t_back = time.time()
        if n.get("id"):
            post("/api/note", {"id": n["id"], "end": True})
        time.sleep(3.0)
        if shots and kind in ("between", "falselock", "rail", "blocked", "cwnear"):
            marks["shot_after"] = shot(kind + "_after")
        rows = W.since(t0, t_back)
        L1 = (W.rows[-1].get("linkd") or {}) if W.rows else {}
        st_seen = sorted({r.get("state") for r in rows if r.get("state")})
        offs = [r["off_khz"] for r in rows if r.get("off_khz") is not None]
        vcs = [r["adc"]["VC"] for r in rows if r.get("adc")]
        v = {"states_seen": st_seen, "off_min": min(offs) if offs else None, "off_max": max(offs) if offs else None,
             "vc_min": min(vcs) if vcs else None, "linkd_losses": L1.get("losses", 0) - L0.get("losses", 0),
             "linkd_recoveries": L1.get("recoveries", 0) - L0.get("recoveries", 0), "back_s": (t_back - t_end) if back else None}
        ok, why = True, []
        def need(cond, text):
            nonlocal ok
            if not cond:
                ok = False
                why.append(text)
        need(back is not None, "not locked again in 240 s")
        if kind == "above":
            need(v["linkd_losses"] == 0, "linkd counted a loss (from above the loop should come down by itself)")
        if kind in ("between", "falselock"):
            rest = [r["off_khz"] for r in rows if r.get("off_khz") is not None and r.get("state") == "lost"]
            need(any(-55 <= o <= -35 for o in rest), "the page never showed 'Lost' at the false lock (-35..-55 kHz)")
            need(v["linkd_recoveries"] >= 1, "linkd did not recover it")
        if kind == "rail":
            need(v["vc_min"] is not None and v["vc_min"] < 0.3, "VC never read at its bottom rail")
            need(v["off_min"] is not None and v["off_min"] < -150, "the offset never read off scale below")
            need("lost" in st_seen, "the page never said 'Lost'")
            need(v["linkd_recoveries"] >= 1, "linkd did not recover it")
        if kind == "blocked":
            need("nocarrier" in st_seen or "holdover" in st_seen, "the page never said 'No carrier' (or holding)")
            dur = W.since(t0 + 3, t0 + 18)
            need(dur and all(r.get("rx_ant_dbm") is None for r in dur), "a carrier level shown while it was off")
        if kind == "attn":
            up = [r for r in W.since(marks["up"] + 3, marks["down"]) if r.get("dem_dbm") is not None]
            dn = [r for r in W.since(marks["down"] + 3, marks["back"]) if r.get("dem_dbm") is not None]
            def med(rs, key):
                xs = sorted(r[key] for r in rs)
                return xs[len(xs) // 2] if xs else None
            v.update(dem_up=med(up, "dem_dbm"), dem_down=med(dn, "dem_dbm"), ant_up=med(up, "rx_ant_dbm"), ant_down=med(dn, "rx_ant_dbm"),
                     dsa_up=med(up, "dsa_db"), dsa_down=med(dn, "dsa_db"))
            need(None not in (v["dem_up"], v["dem_down"], base["dem_dbm"]), "no level read during a step")
            if None not in (v["dem_up"], v["dem_down"], base["dem_dbm"]):
                need(abs(v["dem_up"] - base["dem_dbm"] + 3) < 1.0 and abs(v["dem_down"] - base["dem_dbm"] - 3) < 1.0,
                     "the demodulator's level did not follow the attenuator (3 dB each way)")
                need(abs(v["ant_up"] - base["rx_ant_dbm"]) < 1.0 and abs(v["ant_down"] - base["rx_ant_dbm"]) < 1.0,
                     "RX ANT moved with the attenuator")
        if kind == "bursts":
            need("lost" not in st_seen, "the page said 'Lost' during bursts")
            need(v["linkd_losses"] == 0, "linkd counted a loss during bursts")
            pk = [r["det"]["peak_dbm"] for r in W.since(t0 + 2, t_end) if r.get("det") and r["det"].get("peak_dbm") is not None]
            v["peak_dbm_max"] = max(pk) if pk else None
        if kind == "cwnear":
            cw = [r for r in W.since(t0 + 1, t_end) if r.get("off_khz") is not None]
            v["off_during"] = [round(r["off_khz"], 1) for r in cw]
            need(any(r.get("state") == "lost" and -35 <= r["off_khz"] <= -10 for r in cw),
                 "the page never showed the capture ('Lost' at -10..-35 kHz)")
        rec = {"kind": kind, "t0": t0, "t_end": t_end, "t_back": t_back, "marks": marks, "base": base, "verdict": v,
               "ok": ok, "why": why, "rows": rows}
        print("%s %-9s %s | states %s, offset %s..%s kHz, VC min %s, linkd %d loss %d recovered, back %s%s" % (
            time.strftime("%H:%M:%S"), kind, "PASS" if ok else "FAIL: " + "; ".join(why), "/".join(st_seen),
            ("%.1f" % v["off_min"]) if v["off_min"] is not None else "-", ("%.1f" % v["off_max"]) if v["off_max"] is not None else "-",
            ("%.2f" % v["vc_min"]) if v["vc_min"] is not None else "-", v["linkd_losses"], v["linkd_recoveries"],
            ("%.1f s" % v["back_s"]) if v["back_s"] is not None else "never",
            (" | dem %+.1f/%+.1f dB, RX ANT %+.1f/%+.1f dB" % (v["dem_up"] - base["dem_dbm"], v["dem_down"] - base["dem_dbm"],
             v["ant_up"] - base["rx_ant_dbm"], v["ant_down"] - base["rx_ant_dbm"])) if kind == "attn" and ok else
            (" | peak in the band %.1f dBm" % v["peak_dbm_max"]) if kind == "bursts" and v.get("peak_dbm_max") is not None else ""),
            flush=True)
        return rec

    def run_all(self, mhz, kinds, shots):
        W = Watch()
        st = self.ready(mhz)
        if st is None:
            print("no lock at %d MHz" % mhz, flush=True)
            return None
        st["vc_lock"] = self.cl.adc("VC")
        print("%s set up: DSA %.2f, leg %.3f V, VC %.4f V" % (time.strftime("%H:%M:%S"), st["dsa"], st["a"], st["vc_lock"]), flush=True)
        # the page's level and lock learned first (it learns VC at lock from its own locked looks)
        self.wait_linkd(lambda x: x.get("state") == "locked" and x.get("rx_ant_dbm") is not None, 60)
        time.sleep(10.0)
        out = {"mhz": mhz, "setup": {k: st[k] for k in ("dsa", "a", "vc_lock")}, "trials": []}
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, "pagecheck_%s.json" % time.strftime("%Y%m%d_%H%M%S"))
        for kind in kinds:
            ok, _ = self.locked(st)
            if not ok:
                self.recover(mhz, st)
                time.sleep(5.0)
            out["trials"].append(self.trial(kind, mhz, st, W, shots))
            with open(path, "w") as f:
                json.dump(out, f, indent=0, default=float)
        W._stop = True
        n_ok = sum(1 for t in out["trials"] if t["ok"])
        print("summary: %d of %d as the page should show them; record %s" % (n_ok, len(out["trials"]), path), flush=True)
        return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mhz", type=int, default=5200)
    ap.add_argument("--kinds", nargs="*", default=list(KINDS))
    ap.add_argument("--no-shots", action="store_true")
    a = ap.parse_args(argv)
    P = PageCheck()
    P.run_all(a.mhz, a.kinds, not a.no_shots)
    try:
        P.b.sa_live()
    except Exception:                                            # noqa: BLE001
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
