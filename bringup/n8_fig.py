"""The N = 8 page from n8test.py's run: per scheme (A8, B3, and the others run) the ideal received constellation, each
receiver's I/Q plane with the scope's trajectories and the decoder's thresholds and right fractions, the time traces;
the gap trials as text.  Uses freqpage.py's panels.
    python3 n8_fig.py [n8_<stamp>] [--out name]  ->  <out>.png / .pdf beside this file"""
import json
import os
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                                 # noqa: E402
import numpy as np                                              # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import freqpage as F                                            # noqa: E402
C = F.C

base = next((a for a in sys.argv[1:] if not a.startswith("--") and (sys.argv.index(a) == 1 or sys.argv[sys.argv.index(a) - 1] != "--out")), None)
base = base or sorted(f[:-5] for f in os.listdir(F.DATA) if f.startswith("n8_") and f.endswith(".json"))[-1]
if not os.path.dirname(base):
    base = os.path.join(F.DATA, base)
out = os.path.join(HERE, "plots", F.arg("--out", os.path.basename(base)))


class N8Run(F.Run):
    """n8test's json has 'runs' (one a link) in place of 'links'"""
    def __init__(self, base):
        self.base = base
        self.J = json.load(open(base + ".json"))
        self.Z = np.load(base + ".npz")
        self.meta = json.loads(str(self.Z["meta"]))
        self.g = self.J.get("gain", 21.0)
        self.J["links"] = {r["link"]: r for r in self.J["runs"]}
        self.J["stamp"] = self.J["stamp"]
        self.mhz = self.J["runs"][0]["mhz"]
        self.pts, self.shots = {}, {}
        for lk, rec in self.J["links"].items():
            for row in rec.get("constellations", []):
                for pp in row.get("points", []):
                    self.pts[(lk, row["scheme"], pp["m"])] = pp
        for m in self.meta:
            if m.get("stage") != "constellation":
                continue
            k = m["k"]
            pp = self.pts.get((m["link"], m["scheme"], m["m"]))
            t = self.Z["t1_%d" % k] * 1e9
            sh = {"t": t, "cmp": self.Z["v4_%d" % k], "mark": self.Z["v1_%d" % k], "point": tuple(int(x) for x in m["point"]), "link": m["link"],
                  "leg": m["leg"], "side": m["side"], "m": m["m"]}
            t0 = pp["cmp_edge_t"] if pp and pp.get("cmp_edge_t") is not None else (m.get("lat_ns") or 0.0)
            sh["t0"] = t0
            for ch, nm in ((2, "i"), (3, "q")):
                d = (self.Z["v%d_%d" % (ch, k)] - m["base"][str(ch)]) * 1e3 * self.g
                d = d - float(np.median(d[(t > -150) & (t < -20)]))
                sh[nm] = d
                mid = (t > t0 + 60) & (t < t0 + 180)
                sh[nm + "_set"] = float(np.median(d[mid])) if mid.any() else None
            self.shots.setdefault((m["link"], m["scheme"]), {}).setdefault(m["m"], []).append(sh)


run = N8Run(base)
schemes = [s for s in ("A8", "B3", "A3", "B1", "B2", "A4") if any((lk, s) in run.shots for lk in ("AB", "BA"))]
fig = plt.figure(figsize=(26, 6 + 5.2 * len(schemes)), dpi=100)
gs = fig.add_gridspec(len(schemes) + 1, 5, width_ratios=[0.75, 1.15, 1.45, 1.15, 1.45], height_ratios=[0.9] + [1] * len(schemes),
                      left=0.03, right=0.99, top=0.95, bottom=0.03, hspace=0.55, wspace=0.25)
ax = fig.add_subplot(gs[0, :])
ax.axis("off")
head = ["%s at %g MHz over the cables: the N = 8 schemes by the decoder with the receiver's scope on every point, and the carrier-gap trials" % (run.J["stamp"], run.mhz)]
for lk in ("AB", "BA"):
    rec = run.J["links"].get(lk)
    if not rec or "lock" not in rec:
        continue
    lock = rec["lock"]
    s = "%s -> %s: DSA %.2f, leg %.0f mV, side %+d.  " % (lk[0], lk[1], lock["dsa"], 1e3 * lock["leg"], lock["side"])
    dec = []
    for row in rec.get("constellations", []):
        d = row.get("decoder") or {}
        if "per_msg" in d:
            dec.append("%s %s%s" % (row["scheme"], "/".join("%.4g" % (100 * min(1.0, r["right_frac"])) for m, r in sorted(d["per_msg"].items(), key=lambda kv: int(kv[0]))) + " %",
                                    " (%.0f false/s)" % d["idle_false_per_s"] if d.get("idle_false_per_s") else ""))
        else:
            dec.append("%s %s" % (row["scheme"], (d.get("error") or "no pilot")[:40]))
    s += "Decoded right: " + ", ".join(dec) + ".  "
    kn = rec.get("A8_knobs") or {}
    if kn:
        s += "A8 at " + ", ".join("%s: %s" % (k, "%.4g %%" % (100 * v["right_frac_min"]) if v.get("right_frac_min") is not None else v.get("error")) for k, v in kn.items()) + ".  "
    gaps = rec.get("gaps") or []
    cnt = [g for g in gaps if g.get("count")]
    runs_ = [g for g in gaps if g.get("seconds") and not g.get("count") and g.get("kind") != "flipcap"]
    if cnt:
        s += "Counted (0,0) gaps: " + ", ".join("%d %s" % (g["count"], "flipped" if g["flipped"] else "kept") for g in cnt) + ".  "
    if runs_:
        s += "Half a second of events: " + ", ".join("(%d,%d) x%d every %d %s" % (g["point"][0], g["point"][1], g["width"], g["period"], "FLIPPED" if g["flipped"] else "kept") for g in runs_) + "."
    head.append(s)
head.append("The loop's side changed only with (0, 0) sequences, one gap as often as a thousand: the harness's own carrier-off before each events start (the register order, fixed 21:50), not the 200 ns gap (BRINGUP_LOG 4.84).")
ax.text(0, 1, "\n".join(textwrap.fill(h, 300) for h in head), va="top", ha="left", fontsize=8, color=F.INK, linespacing=1.3)
for r, name in enumerate(schemes):
    s = C.SCHEMES[name]
    F.draw_ideal(fig.add_subplot(gs[r + 1, 0]), s)
    F.draw_plane(fig.add_subplot(gs[r + 1, 1]), run, "BA", s)
    F.draw_traces(fig.add_subplot(gs[r + 1, 2]), run, "BA", s)
    F.draw_plane(fig.add_subplot(gs[r + 1, 3]), run, "AB", s)
    F.draw_traces(fig.add_subplot(gs[r + 1, 4]), run, "AB", s)
fig.text(0.03, 0.975, "Three bits an event on rev A: the A8 and B3 schemes on both receivers' scopes over the cables (%s)" % run.J["stamp"], fontsize=12, fontweight="bold", va="bottom")
fig.savefig(out + ".png", dpi=72)
fig.savefig(out + ".pdf")
print(out)
