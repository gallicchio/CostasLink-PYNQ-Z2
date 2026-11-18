"""A pair of boards up from nothing: both servers answering, each receiver's fast Q arm centred on its loop's reference,
then every direction tried at every carrier frequency with the one-in-N schemes, the pilot schemes and the PRBS, the
comparator margins measured, and the best frequency chosen for each direction; then both links up at once (the duplex)
and tried again.  What it needs: the two PYNQs serving (costaslink-netbus), the boards powered after them, the null
table (data/twoboard/vr_null.json) for the frequencies tried (--nulls measures a missing one on the DSA875 if the
analyzer is on the bench with an antenna), the scopes not needed.

    python3 bringup/pairup.py [--mhz 4800 5200 5400] [--links AB BA] [--no-trim] [--no-duplex] [--nulls]

The steps, each one recorded (data/twoboard/pairup_<stamp>.jsonl) and summarised at the end (pairup_<stamp>.json):
  0. the servers: ID, the DAC shadows (a board's trims: costaslink.BOARD_DAC_V by hostname, twoboard.Q_OFF_F_V here);
     both boards put in the safe state.
  1. per receiver (the first frequency, the other board sending): the lock, then the loop's null (the locked idle's Q on
     the ADC) against the arm's no-carrier centre (the ladder at zero at the null): the difference is the loop's Q
     offset (BRINGUP_LOG 4.76); over 4 mV it is trimmed out with DAC1 Q_OFF_F (-19.8 mV at the arm per V) and
     verified; the sign comparator's duty with no carrier is read (0.5 is centred).  A trim found here is applied for
     the run and printed with the EEPROM command: writing it there is a calibration change for Jason.
  2. per direction and frequency: setup (linkd's search: the attenuator for a 150 mV leg, the lock), the lock's
     numbers, A1 / A2 / A3 (the one-in-N family), B1 / B2 (the pilot schemes), the PRBS bpsk at 50 and 20 clocks a bit,
     the comparator windows' margins (the gap between the idle and the nearest point, from A3's sweep).
  3. the score: 4 for the A family all right, 2 for both PRBS runs error-free, 1 for both pilot schemes right, minus 1
     for any false event at the idle; ties by the smallest window gap, then the leg.  The best frequency per direction.
  4. the duplex: both links up at once at their frequencies (qpvtests.Duplex), A3 on each.
When a scheme fails the summary says where to look: false events at the idle (the windows too close: the sweep's
frac), dead windows (the comparator DAC's range at that level), no pilot (the null or the pilot's sign), PRBS
mismatches with the schemes fine (the sampling phase or the symbol period), a weak leg (the link, not the decoder).
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "gateware", "driver"))
import twoboard as T                                      # noqa: E402

Q_LEVER_V_PER_V = -0.0198                                 # the arm's centre per volt of Q_OFF_F (4.76, R116 100 k)
TRIM_MIN_MV = 4.0


def args_list(name, default, cast=str):
    if name not in sys.argv:
        return default
    i = sys.argv.index(name) + 1
    out = []
    while i < len(sys.argv) and not sys.argv[i].startswith("--"):
        out.append(cast(sys.argv[i]))
        i += 1
    return out


def api(host):
    import urllib.request
    try:
        with urllib.request.urlopen("http://%s:8080/api/now" % host, timeout=8) as r:
            return json.load(r)
    except Exception as e:                                # noqa: BLE001
        return {"error": repr(e)[:120]}


# ---------------------------------------------------------------------------------------------------------------------
def step0_servers(nodes, log):
    out = {}
    for n, node in nodes.items():
        d = api(T.HOSTS[n])
        dv = node.cl.dac_volts()
        out[n] = {"host": T.HOSTS[n], "id": d.get("id"), "api_state": d.get("state"), "api_error": d.get("error"),
                  "dac": dv, "q_off_f": dv["Q_OFF_F"], "expected_q_off_f": T.Q_OFF_F_V.get(n, 1.65)}
        node.quiet()
        T.say("server %s (%s): ID %s, state %s, Q_OFF_F %.3f (expected %.3f), VC_OFF %.3f" % (
            n, T.HOSTS[n], d.get("id"), d.get("state"), dv["Q_OFF_F"], T.Q_OFF_F_V.get(n, 1.65), dv["VC_OFF"]))
    log(label="pairup servers", tag="servers", **out)
    return out


def centres(nodes, log):
    """each board's arms with no carrier (both boards quiet, the loop held): the Q and I centres, the sign comparator's
    duty.  Taken before any lock, so no lock has to be broken for them (the first run broke A -> B twice, 15:58)."""
    out = {}
    for n in nodes.values():
        n.quiet()
    time.sleep(0.5)
    for n, node in nodes.items():
        cl = node.cl
        q0 = sum(cl.adc("Q") for _ in range(8)) / 8.0
        i0 = sum(cl.adc("I") for _ in range(4)) / 4.0
        ones = sum(cl.cmp_state()["CMP_I"] for _ in range(200))
        out[n] = {"centre_q_v": q0, "centre_i_v": i0, "cmp_i_duty_no_carrier": ones / 200.0, "q_off_f": cl.dac_volts()["Q_OFF_F"]}
        T.say("   %s with no carrier: Q arm %.4f V, I arm %.4f V, CMP_I high %.0f %% of the time (50 %% is a centred sign comparator), Q_OFF_F %.3f V" % (
            n, q0, i0, 100 * out[n]["cmp_i_duty_no_carrier"], out[n]["q_off_f"]))
    log(label="pairup centres", tag="centres", **out)
    return out


def q_trim(L, cen, log):
    """the loop's null (the locked idle's Q on the ADC) against the arm's centre measured with no carrier, and the trim
    if they differ (step 1); the lock is kept throughout"""
    rx = L.rx.cl
    c = cen[L.rx.name]
    rec = {"rx": L.rx.name, "link": L.name, "mhz": L.mhz, "q_off_f_before": c["q_off_f"], "centre_q_v": c["centre_q_v"]}
    L.hold((1, 0))
    time.sleep(0.15)
    ref = sum(rx.adc("Q") for _ in range(6)) / 6.0
    rec.update(loop_null_v=ref, offset_mv=1e3 * (ref - c["centre_q_v"]))
    T.say("   %s's loop nulls Q at %.4f V, the arm's centre is %.4f V: the loop sits %+.1f mV from the centre (Q_OFF_F %.3f V)" % (
        L.rx.name, ref, c["centre_q_v"], rec["offset_mv"], c["q_off_f"]))
    if abs(rec["offset_mv"]) > TRIM_MIN_MV:
        new = float(min(3.0, max(0.3, c["q_off_f"] + (ref - c["centre_q_v"]) / Q_LEVER_V_PER_V)))
        rx.dac(Q_OFF_F=new)
        T.Q_OFF_F_V[L.rx.name] = new                      # kept through every later setup and recover (twoboard)
        time.sleep(0.3)
        L.ensure()
        rec.update(q_off_f_after=new, centre_predicted_v=c["centre_q_v"] + Q_LEVER_V_PER_V * (new - c["q_off_f"]))
        T.say("   trimmed Q_OFF_F %.3f -> %.3f V (the centre should now be %.4f V; checked with no carrier at the end).  To keep it: "
              "BOARD_DAC_V[%r] and dac_eeprom(DAC1, [VR_I_V, VR_Q_V, %.3f, V_MID]) on that board (a calibration change)" % (
                  c["q_off_f"], new, rec["centre_predicted_v"], "pynq-%s" % L.rx.name.lower(), new))
    else:
        rec["q_off_f_after"] = c["q_off_f"]
        T.say("   inside %.0f mV: no trim" % TRIM_MIN_MV)
    log(label="pairup trim", tag="trim", state=L.state(), **rec)
    return rec


def brief_events(r):
    if r.get("error"):
        return "error %s" % r["error"]
    pm = r.get("per_msg") or {}
    return "right %s, false %.0f/s%s" % ("/".join("%.4g" % (100 * x["right_frac"]) for x in pm.values()) + " %",
                                        r.get("idle_false_per_s") or 0,
                                        ", dead %s" % ",".join((r.get("rx_info") or {}).get("dead_windows")) if (r.get("rx_info") or {}).get("dead_windows") else "")


def link_trial(L, log, schemes=("A1", "A2", "A3", "B1", "B2")):
    """step 2 for one direction and frequency: the lock, the schemes, the PRBS, the margins; a row with the score"""
    row = {"link": L.name, "mhz": L.mhz, "events": {}, "prbs": {}}
    t0 = time.time()
    if not L.up():
        row["error"] = "no lock"
        T.say("   %s %g: no lock" % (L.name, L.mhz))
        log(label="pairup link", tag="link", state=L.state(), **row)
        return row
    row["lock"] = dict(L.info, side=L.s, setup_s=round(time.time() - t0, 1))
    look = L.look()
    row["received_dbm"] = look.get("received_dbm")
    T.say("   %s %g: locked in %.0f s, DSA %.2f, leg %.0f mV, %s dBm, side %+d" % (
        L.name, L.mhz, row["lock"]["setup_s"], row["lock"]["dsa"], 1e3 * row["lock"]["leg"],
        "%.1f" % look["received_dbm"] if look.get("received_dbm") is not None else "?", L.s))
    for sc in schemes:
        try:
            r = T.events_point(L, **dict(T.EVENTS_BASE, scheme=sc))
        except T.LinkDown:
            raise
        except Exception as e:                            # noqa: BLE001
            r = {"error": repr(e)[:200]}
            L.ensure()
        row["events"][sc] = {k: r.get(k) for k in ("per_msg", "right_frac_min", "right_frac_mean", "idle_false_per_s", "leg", "error",
                                                    "gaps_mv", "pilot")} | {"dead": (r.get("rx_info") or {}).get("dead_windows")}
        T.say("      %-3s %s" % (sc, brief_events(r)))
        log(label="pairup events", tag="events", scheme_=sc, state=L.state(), **{k: v for k, v in r.items() if k != "scheme"})
    for period in (50, 20):
        try:
            r = T.prbs_point(L, **dict(T.PRBS_BASE, period=period))
        except T.LinkDown:
            raise
        except Exception as e:                            # noqa: BLE001
            r = {"error": repr(e)[:200]}
            L.ensure()
        row["prbs"]["P%d" % period] = {k: r.get(k) for k in ("ber", "bits", "mismatches", "error")}
        T.say("      prbs P%-3d BER %s over %s bits%s" % (period, r.get("ber"), r.get("bits"), "; " + r["error"] if r.get("error") else ""))
        log(label="pairup prbs", tag="prbs", period_=period, state=L.state(), **r)
    score(row)
    log(label="pairup link", tag="link", state=L.state(), **row)
    return row


def score(row):
    ev, pr = row["events"], row["prbs"]
    fam = [ev.get(s, {}) for s in ("A1", "A2", "A3")]
    pil = [ev.get(s, {}) for s in ("B1", "B2")]
    ok_a = all(r.get("right_frac_min") is not None and r["right_frac_min"] >= 0.999 and not r.get("error") for r in fam)
    ok_prbs = all(pr.get(k, {}).get("ber") == 0 and (pr[k].get("bits") or 0) > 1e6 for k in ("P50", "P20"))
    ok_pilot = all(r.get("right_frac_min") is not None and r["right_frac_min"] >= 0.99 and not r.get("error") for r in pil)
    false_total = sum((r.get("idle_false_per_s") or 0) for r in fam + pil)
    gaps = [abs(g) for r in fam for g in (r.get("gaps_mv") or {}).values() if g is not None]
    row.update(ok_a=ok_a, ok_prbs=ok_prbs, ok_pilot=ok_pilot, false_total=false_total, gap_min_mv=min(gaps) if gaps else None,
               score=4 * ok_a + 2 * ok_prbs + 1 * ok_pilot - (1 if false_total > 0 else 0))
    why = []
    for s, r in ev.items():
        if r.get("error"):
            why.append("%s: %s (%s)" % (s, r["error"], "the pilot: the null at this frequency or the pilot's sign" if "pilot" in r["error"] else "the link"))
        elif r.get("right_frac_min") is not None and r["right_frac_min"] < 0.99:
            if (r.get("idle_false_per_s") or 0) > 100:
                why.append("%s: %.0f false events a second at the idle: the windows sit too close to the idle (frac) or the lock is unsteady" % (s, r["idle_false_per_s"]))
            elif r.get("dead"):
                why.append("%s: windows %s dead: the comparator DAC's range at this level" % (s, ",".join(r["dead"])))
            else:
                why.append("%s: right %.3f with the idle quiet: the decision's timing or the table (firmware)" % (s, r["right_frac_min"]))
    for k, r in pr.items():
        if r.get("ber") and ok_a:
            why.append("prbs %s: %s mismatches with the schemes fine: the sampling phase or the symbol period" % (k, r.get("mismatches")))
        elif r.get("ber"):
            why.append("prbs %s: BER %.2g" % (k, r["ber"]))
    if row.get("lock") and 1e3 * (row["lock"].get("leg") or 0) < 80:
        why.append("the leg %.0f mV: a weak link at this frequency, not the decoder" % (1e3 * row["lock"]["leg"]))
    row["why"] = why
    return row


# ---------------------------------------------------------------------------------------------------------------------
def main():
    mhzs = args_list("--mhz", [4800.0, 5200.0, 5400.0], float)
    links = args_list("--links", ["AB", "BA"])
    want_trim = "--no-trim" not in sys.argv
    want_duplex = "--no-duplex" not in sys.argv
    want_nulls = "--nulls" in sys.argv
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = T.Log("pairup")
    out = {"stamp": stamp, "mhz": mhzs, "links": links, "trims": {}, "rows": [], "best": {}, "duplex": None}
    nodes = {n: T.Node(n) for n in ("A", "B")}
    t_start = time.time()
    try:
        T.say("==== 0. the servers")
        out["servers"] = step0_servers(nodes, log)
        if want_nulls:
            missing = [(b, m) for b in ("A", "B") for m in mhzs if str(float(m)) not in (json.load(open(T.NULL_FILE)) if os.path.exists(T.NULL_FILE) else {}).get(b, {})]
            if missing:
                try:
                    sa = T.open_sa()
                    for b, m in missing:
                        r = T.null_fpv(nodes[b], nodes["B" if b == "A" else "A"], m, sa)
                        log(label="pairup nulls", exp="null_fpv", **r)
                        T.say("null %s %g: %.1f dBc at VR %s" % (b, m, r["depth_dbc"], r["vr"]))
                        T.VR_NULL[b][float(m)] = tuple(r["vr"])
                except Exception as e:                    # noqa: BLE001
                    T.say("nulls: %r (the analyzer not on the bench?): the nearest measured null is used" % e)
        for lk in links:
            for m in mhzs:
                off = nodes[lk[0]].vr(m)[1]
                if off > 1:
                    T.say("note: %s's null at %g MHz is the one measured %g MHz away" % (lk[0], m, off))
        if want_trim:
            T.say("==== 1. each receiver's Q arm against its loop's reference (the centres with no carrier, then a lock at %g MHz)" % mhzs[0])
            out["centres"] = cen = centres(nodes, log)
            for lk in links:
                L = T.Link(nodes[lk[0]], nodes[lk[1]], mhzs[0])
                try:
                    if L.up():
                        out["trims"][lk[1]] = q_trim(L, cen, log)
                    else:
                        T.say("   %s: no lock at %g: the trim step skipped for %s" % (lk, mhzs[0], lk[1]))
                except T.LinkDown as e:
                    T.say("   %s: %s" % (lk, e))
                finally:
                    for n in nodes.values():
                        n.quiet()
        T.say("==== 2. every direction at every frequency")
        for m in mhzs:
            for lk in links:
                L = T.Link(nodes[lk[0]], nodes[lk[1]], m)
                try:
                    out["rows"].append(link_trial(L, log))
                except T.LinkDown as e:
                    out["rows"].append({"link": lk, "mhz": m, "error": str(e), "score": -9})
                    T.say("   %s %g: %s" % (lk, m, e))
                except Exception as e:                    # noqa: BLE001
                    import traceback
                    out["rows"].append({"link": lk, "mhz": m, "error": repr(e)[:300], "score": -9})
                    T.say("   %s %g: %r\n%s" % (lk, m, e, traceback.format_exc()[-600:]))
                finally:
                    for n in nodes.values():
                        n.quiet()
        T.say("==== 3. the choice (one frequency per direction, different ones: each board transmits and receives at once)")

        def key(r):
            return (r["score"], r.get("gap_min_mv") or 0, (r.get("lock") or {}).get("leg") or 0)

        rows = {lk: [r for r in out["rows"] if r["link"] == lk and "score" in r] for lk in links}
        if all(rows.get(lk) for lk in ("AB", "BA")):
            pairs = [(a, b) for a in rows["AB"] for b in rows["BA"] if a["mhz"] != b["mhz"]]
            if pairs:                                     # the first run (15:57) put both on 4800 and B's own TX spoilt A -> B
                a, b = max(pairs, key=lambda ab: (key(ab[0])[0] + key(ab[1])[0], min(key(ab[0])[1], key(ab[1])[1])))
                chosen = {"AB": a, "BA": b}
            else:
                chosen = {lk: max(rows[lk], key=key) for lk in ("AB", "BA")}
        else:
            chosen = {lk: max(rs, key=key) for lk, rs in rows.items() if rs}
        for lk, best in chosen.items():
            out["best"][lk] = {"mhz": best["mhz"], "score": best["score"], "gap_min_mv": best.get("gap_min_mv"), "lock": best.get("lock"), "why": best.get("why")}
            T.say("   %s: %g MHz (score %d of 7%s)" % (lk, best["mhz"], best["score"], "" if best["score"] == 7 else "; " + "; ".join(best.get("why") or [])))
        if want_duplex and all(lk in out["best"] for lk in ("AB", "BA")):
            T.say("==== 4. both links up at once: A -> B at %g, B -> A at %g" % (out["best"]["AB"]["mhz"], out["best"]["BA"]["mhz"]))
            try:
                import qpvtests as Q
                D = Q.Duplex(nodes["A"], nodes["B"], out["best"]["AB"]["mhz"], out["best"]["BA"]["mhz"], tr_a_v=0, tr_a_p=0)
                ok = D.up()
                st = D.state()
                dup = {"up": bool(ok), "state": st, "events": {}}
                T.say("   duplex up: %s; %s" % (ok, st))
                if ok:
                    for name, L in (("AB", D.VP), ("BA", D.PV)):
                        r = T.events_point(L, **dict(T.EVENTS_BASE, scheme="A3"))
                        dup["events"][name] = {k: r.get(k) for k in ("per_msg", "right_frac_min", "idle_false_per_s", "leg", "error")}
                        T.say("      %s A3 with both transmitters on: %s" % (name, brief_events(r)))
                        log(label="pairup duplex", tag="duplex", link_=name, state=L.state(), **{k: v for k, v in r.items() if k != "scheme"})
                out["duplex"] = dup
            except Exception as e:                        # noqa: BLE001
                import traceback
                out["duplex"] = {"error": repr(e)[:300]}
                T.say("   duplex: %r\n%s" % (e, traceback.format_exc()[-600:]))
            finally:
                for n in nodes.values():
                    n.quiet()
        if any("centre_predicted_v" in t for t in out["trims"].values()):
            T.say("==== 5. the centres again with no carrier (the trims checked)")
            out["centres_after"] = centres(nodes, log)
            for rx, t in out["trims"].items():
                if "centre_predicted_v" in t:
                    t["centre_after_v"] = out["centres_after"][rx]["centre_q_v"]
                    t["offset_after_mv"] = 1e3 * (t["loop_null_v"] - t["centre_after_v"])
                    T.say("   %s: the loop's null %.4f V against the centre %.4f V now: %+.1f mV" % (rx, t["loop_null_v"], t["centre_after_v"], t["offset_after_mv"]))
    finally:
        path = os.path.join(T.DATA, "pairup_%s.json" % stamp)
        json.dump(out, open(path, "w"), indent=1, default=str)
        T.say("==== summary (%.0f min): %s" % ((time.time() - t_start) / 60, path))
        for r in out["rows"]:
            lk, m = r["link"], r["mhz"]
            if "lock" not in r:
                T.say("%s %6g: %s" % (lk, m, r.get("error")))
                continue
            T.say("%s %6g: score %d/7 | DSA %5.2f leg %3.0f mV %s dBm in %.0f s | A family %s, PRBS %s, pilots %s | false %.0f/s | gap %s mV%s" % (
                lk, m, r["score"], r["lock"]["dsa"], 1e3 * r["lock"]["leg"], "%.0f" % r["received_dbm"] if r.get("received_dbm") is not None else "?",
                r["lock"]["setup_s"], "ok" if r["ok_a"] else "FAIL", "ok" if r["ok_prbs"] else "FAIL", "ok" if r["ok_pilot"] else "FAIL",
                r["false_total"], "%.0f" % r["gap_min_mv"] if r.get("gap_min_mv") is not None else "?",
                ("\n      " + "\n      ".join(r["why"])) if r.get("why") else ""))
        for lk, b in out["best"].items():
            T.say("best %s: %g MHz" % (lk, b["mhz"]))
        if out.get("trims"):
            for rx, t in out["trims"].items():
                T.say("trim %s: Q_OFF_F %.3f -> %.3f V (the loop %+.1f mV from the centre before%s)" % (
                    rx, t["q_off_f_before"], t["q_off_f_after"], t["offset_mv"], ", %+.1f after" % t["offset_after_mv"] if "offset_after_mv" in t else ""))
        for n in nodes.values():
            try:
                n.quiet()
            except Exception as e:                        # noqa: BLE001
                T.say("quiet %s: %r" % (n.name, e))
        T.say("done; both quiet")


if __name__ == "__main__":
    main()
