"""Summaries of twoboard.py's records (bringup/data/twoboard/*.jsonl): the prover's turnaround by scheme, path, reply
function and each factor; the events' right fractions; the prbs error rates; the band; and the prbs points against the
WiFi monitor's records (wifimon.py's JSONL, joined by time).  Markdown to stdout (and --out FILE).

    python3 bringup/twoboard_report.py [records.jsonl ...] [--wifi wifimon.jsonl ...] [--out report.md]
"""
import argparse
import glob
import json
import os
import statistics
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "twoboard")


def load(paths):
    rows = []
    for p in paths:
        for line in open(p):
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def factor(r):
    """the factor a one-factor-at-a-time point varies, and its value"""
    tag = r.get("tag") or ""
    p = r.get("params") or {}
    if tag.startswith("ofat_"):
        k = tag[5:]
        return k, p.get(k)
    if tag == "reply":
        return "reply", p.get("reply")
    if tag.startswith("grid_"):
        a, b = tag[5:].split("_", 1)
        return tag, "%s=%s %s=%s" % (a, p.get(a), b, p.get(b))
    return tag or "-", ""


def fmt(x, nd=2):
    if x is None:
        return "-"
    if isinstance(x, float):
        return ("%." + str(nd) + "f") % x
    return str(x)


def prover_table(rows, out):
    pr = [r for r in rows if r.get("exp") == "prover"]
    if not pr:
        return
    out.append("## The prover (loopback through its switch block: RX ANT to TX ANT)\n")
    out.append("Counter: over `count` stimuli (every challenge), min / mean / max of the turnaround; captures: one stimulus "
               "each, its turnaround and the FPGA's pin-to-pin share; right: replies decided right as received.\n")
    out.append("| board | MHz | scheme | path | factor | value | n | miss | min | mean | max | captures (ns) | FPGA (ns) | "
               "right | decided / false |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in pr:
        st = r.get("stats") or {}
        rx = r.get("rx") or {}
        f, v = factor(r)
        caps = r.get("cap_turn_ns") or []
        fp = r.get("cap_fpga_ns") or []
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            (r.get("state") or {}).get("link", "-"), fmt((r.get("state") or {}).get("mhz"), 0), r.get("scheme"),
            r.get("path"), f, v, st.get("n"), st.get("miss"), fmt(st.get("min_ns")), fmt(st.get("mean_ns")),
            fmt(st.get("max_ns")), ", ".join(fmt(c) for c in caps), ", ".join(fmt(c) for c in fp),
            "%s/%d" % (r.get("cap_right_rx"), len(r.get("captures") or [])),
            "%s / %s" % (rx.get("decided"), rx.get("false")) if rx else (r.get("error") or "-")))
    # the best of each path
    out.append("")
    good = [r for r in pr if (r.get("stats") or {}).get("mean_ns") and r.get("cap_right_rx") == len(r.get("captures") or [1])
            and (r.get("stats") or {}).get("miss") == 0]
    for path in ("fast", "sync"):
        g = [r for r in good if r.get("path") == path]
        if g:
            b = min(g, key=lambda r: r["stats"]["mean_ns"])
            out.append("* **%s, the lowest mean with every reply right and none missed:** %.2f ns (min %.2f, max %.2f), %s %s, %s=%s" % (
                path, b["stats"]["mean_ns"], b["stats"]["min_ns"], b["stats"]["max_ns"], b["state"].get("link"), b["scheme"],
                *factor(b)))
    out.append("")


def events_table(rows, out):
    ev = [r for r in rows if r.get("exp") == "events"]
    if not ev:
        return
    out.append("## Events, idle to 1-in-N, across the boards\n")
    out.append("Right: decisions of the sent message over events sent, per message; extra: events seen over those sent; "
               "idle: false events a second with the transmitter idle.\n")
    out.append("| link | MHz | scheme | factor | value | right by message | min | extra | idle false/s | error |")
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in ev:
        f, v = factor(r)
        pm = r.get("per_msg") or {}
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            (r.get("state") or {}).get("link", "-"), fmt((r.get("state") or {}).get("mhz"), 0), r.get("scheme"), f, v,
            " ".join("%.4f" % x["right_frac"] for x in pm.values()), fmt(r.get("right_frac_min"), 4),
            " ".join(str(x["extra"]) for x in pm.values()), fmt(r.get("idle_false_per_s"), 1), r.get("error", "")))
    out.append("")


def prbs_table(rows, out):
    pb = [r for r in rows if r.get("exp") == "prbs"]
    if not pb:
        return
    out.append("## PRBS across the boards\n")
    out.append("| link | MHz | const | factor | value | MBd | bits | errors | BER | threshold | error |")
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in pb:
        f, v = factor(r)
        out.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            (r.get("state") or {}).get("link", "-"), fmt((r.get("state") or {}).get("mhz"), 0), r.get("const"), f, v,
            fmt(r.get("mbaud"), 3), r.get("bits"), fmt(r.get("errors"), 1), "%.2g" % r["ber"] if r.get("ber") is not None else "-",
            r.get("thresholds") or "", r.get("error", "")))
    out.append("")


def band_table(rows, out):
    bd = [r for r in rows if r.get("label", "").startswith("band")]
    if not bd:
        return
    out.append("## The band\n")
    per = defaultdict(dict)
    for r in bd:
        st = r.get("state") or {}
        key = (st.get("link"), st.get("mhz"))
        d = per[key]
        if r.get("exp") == "setup":
            d["setup"] = "%s DSA %s leg %s" % ("ok" if r.get("ok") else "FAILED", fmt(r.get("dsa")), fmt((r.get("leg") or 0) * 1e3, 1))
        elif r.get("exp") == "level":
            d["rx_dbm"] = r.get("received_dbm")
        elif r.get("exp") == "prbs" and r.get("tag") == "band":
            d.setdefault("prbs", {})[r["const"]] = r.get("ber")
        elif r.get("exp") == "events" and r.get("tag") == "band":
            d.setdefault("events", {})[r["scheme"]] = r.get("right_frac_min")
        elif r.get("exp") == "prover" and r.get("tag") == "band":
            d.setdefault("prover", {})[r["path"]] = (r.get("stats") or {}).get("mean_ns")
        d["wifi"] = st.get("wifi")
    out.append("| link | MHz | WiFi on / seen in band | setup | received dBm | prbs BER by const | events right (min) | prover mean ns |")
    out.append("|---|---|---|---|---|---|---|---|")
    for (link, mhz), d in sorted(per.items(), key=lambda kv: (str(kv[0][0]), kv[0][1] or 0)):
        w = d.get("wifi") or {}
        out.append("| %s | %s | %s / %s | %s | %s | %s | %s | %s |" % (
            link, fmt(mhz, 0), w.get("on"), w.get("seen_in_band"), d.get("setup", "-"), fmt(d.get("rx_dbm"), 1),
            " ".join("%s %s" % (k, "%.1g" % v if v is not None else "-") for k, v in (d.get("prbs") or {}).items()),
            " ".join("%s %s" % (k, fmt(v, 3)) for k, v in (d.get("events") or {}).items()),
            " ".join("%s %s" % (k, fmt(v)) for k, v in (d.get("prover") or {}).items())))
    out.append("")


def wifi_join(rows, wifi_rows, out, margin_mhz=12.0):
    """each prbs point against the WiFi monitor's records over its window: the band's strongest excursion outside the
    link's own +-margin, and the BER with and without activity"""
    if not wifi_rows:
        return
    ws = [w for w in wifi_rows if w.get("kind") == "s"]
    pb = [r for r in rows if r.get("exp") == "prbs" and r.get("bits")]
    if not ws or not pb:
        return
    out.append("## PRBS against the WiFi monitor (the FPV antenna on the DSA875)\n")
    hits = {"active": [0, 0, 0], "quiet": [0, 0, 0]}
    for r in pb:
        t1 = r["t"]
        t0 = t1 - (r.get("seconds") or 1.0) - 0.5
        lvl = []
        for w in ws:
            if t0 - 10 <= w["t"] <= t1:
                for e in w.get("events") or []:
                    if t0 <= e[0] <= t1 and abs(e[1] - (r.get("state") or {}).get("mhz", 0)) > margin_mhz:
                        lvl.append(e[2])
        k = "active" if lvl else "quiet"
        hits[k][0] += 1
        hits[k][1] += r["bits"]
        hits[k][2] += r.get("errors") or 0
    for k, (n, b, e) in hits.items():
        out.append("* %s (a WiFi excursion outside the link's own +-%g MHz during the window): %d points, %.3g bits, %.0f errors, BER %s" % (
            k, margin_mhz, n, b, e, "%.2g" % (e / b) if b else "-"))
    out.append("")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("records", nargs="*")
    ap.add_argument("--wifi", nargs="*", default=None)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    paths = a.records or sorted(glob.glob(os.path.join(DATA, "night_*.jsonl")))[-1:]
    rows = load(paths)
    wifi = load(a.wifi) if a.wifi else []
    out = ["# Two boards: %s (%d records)\n" % (", ".join(os.path.basename(p) for p in paths), len(rows))]
    prover_table(rows, out)
    events_table(rows, out)
    prbs_table(rows, out)
    band_table(rows, out)
    wifi_join(rows, wifi, out)
    text = "\n".join(out)
    if a.out:
        open(a.out, "w").write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
