"""Aim the dishes by ear (Jason, 2026-11-04): a page whose two tones follow the two receivers' levels, one dish each,
while the boards take turns transmitting.  1 dB is a semitone (12 dB an octave); a click marks a new maximum; the numbers
in large type.  Runs on the laptop; the page on the laptop's speakers or on a phone that can reach the laptop
(http://<laptop>:8082/).  Needs the boards to itself (stop the campaign first).

    COSTAS_BENCH_CONFIG=bringup/bench_config_laptop.json python3 bringup/aimtone.py [--mhz 5200] [--dwell 0.4] [--port 8082]
    ... --one-way BA        B transmits all the time, A's receiver alone (one tone)
    ... --demo              no boards: two wandering tones, to try the page

Each board: TX ANT -> SW TX, SW RX -> RX ANT, ANT -> cable -> dish (as 4.59).  The transmitting board's switch on TX (TR_A
0), the listening board's on RX (TR_A 1); the sender's carrier at mhz with its output null, its RX synthesizer parked;
the listener's RX synthesizer at mhz, its TX muted and parked.  The level is the listener's log detector, the +-94 MHz
band at RX ANT (no lock needed, 860 readings a second over I2C), the median of 5."""
import argparse
import json
import math
import os
import random
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ.setdefault("COSTAS_BENCH_CONFIG", os.path.join(HERE, "bench_config_laptop.json"))
sys.path.insert(0, HERE)

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aim by ear</title>
<style>
 body { font-family: system-ui, sans-serif; background: #111; color: #eee; margin: 0; padding: 16px; }
 .row { display: flex; gap: 16px; flex-wrap: wrap; }
 .card { flex: 1 1 280px; background: #222; border-radius: 12px; padding: 16px; }
 .big { font-size: 64px; font-weight: 700; line-height: 1; margin: 8px 0; font-variant-numeric: tabular-nums; }
 .max { font-size: 22px; color: #9f9; }
 .name { font-size: 20px; color: #aaa; }
 button { font-size: 20px; padding: 12px 20px; border-radius: 10px; border: 0; margin: 6px 8px 6px 0; }
 #go { background: #4c4; } #stop { background: #c44; } #reset { background: #777; }
 .bar { height: 18px; background: #333; border-radius: 9px; margin-top: 8px; overflow: hidden; }
 .fill { height: 100%; background: #4c4; width: 0; }
 .stale { color: #f66; }
 small { color: #888; }
</style></head><body>
<h2 style="margin:0 0 8px">Aim by ear <small id="mode"></small></h2>
<div><button id="go">Sound on</button><button id="stop">Off</button><button id="reset">Reset max</button>
<label><input type="checkbox" id="click" checked> click at a new max</label></div>
<div class="row" id="cards"></div>
<p><small>1 dB = 1 semitone (12 dB an octave).  Left ear: the first card's receiver, right ear: the second's.  The level is each
listener's log detector (the +-94 MHz band at RX ANT) while the other board transmits.  Read-only page; the laptop drives the boards.</small></p>
<script>
let ctx = null, osc = {}, gain = {}, pan = {}, maxes = {}, last = null, clickOn = true;
const REF_DBM = -60, REF_HZ = 440;
function hz(d) { return REF_HZ * Math.pow(2, (d - REF_DBM) / 12); }
function ensureAudio() {
  if (ctx) return;
  ctx = new (window.AudioContext || window.webkitAudioContext)();
}
function voice(name, p) {
  if (osc[name]) return;
  const o = ctx.createOscillator(); o.type = "triangle";
  const g = ctx.createGain(); g.gain.value = 0;
  const s = ctx.createStereoPanner ? ctx.createStereoPanner() : null;
  if (s) { s.pan.value = p; o.connect(g); g.connect(s); s.connect(ctx.destination); }
  else { o.connect(g); g.connect(ctx.destination); }
  o.start();
  osc[name] = o; gain[name] = g;
}
function click() {
  if (!ctx || !clickOn) return;
  const o = ctx.createOscillator(); o.type = "square"; o.frequency.value = 2000;
  const g = ctx.createGain(); g.gain.value = 0.5;
  o.connect(g); g.connect(ctx.destination); o.start(); o.stop(ctx.currentTime + 0.04);
}
function render(d) {
  const cards = document.getElementById("cards");
  const names = Object.keys(d.levels);
  document.getElementById("mode").textContent = d.mode + " at " + d.mhz + " MHz";
  names.forEach((n, i) => {
    let c = document.getElementById("card-" + n);
    if (!c) {
      c = document.createElement("div"); c.className = "card"; c.id = "card-" + n;
      c.innerHTML = '<div class="name"></div><div class="big">-</div><div class="max"></div><div class="bar"><div class="fill"></div></div><div><small class="info"></small></div>';
      cards.appendChild(c);
    }
    const L = d.levels[n];
    const v = L.dbm;
    c.querySelector(".name").textContent = L.label;
    const big = c.querySelector(".big");
    big.textContent = (v == null) ? "-" : v.toFixed(1) + " dBm";
    big.className = "big" + (L.stale ? " stale" : "");
    if (v != null && !L.stale) {
      if (maxes[n] == null || v > maxes[n] + 0.05) { if (maxes[n] != null) click(); maxes[n] = v; }
      c.querySelector(".fill").style.width = Math.max(0, Math.min(100, (v + 100) * 1.4)) + "%";
    }
    c.querySelector(".max").textContent = (maxes[n] == null) ? "" : "max " + maxes[n].toFixed(1) + " dBm  (" + (v == null ? "" : (v - maxes[n]).toFixed(1)) + " dB)";
    c.querySelector(".info").textContent = L.info || "";
    if (ctx) {
      voice(n, names.length > 1 ? (i === 0 ? -1 : 1) : 0);
      const target = (v == null || L.stale) ? 0 : 0.25;
      gain[n].gain.setTargetAtTime(target, ctx.currentTime, 0.05);
      if (v != null) osc[n].frequency.setTargetAtTime(hz(v), ctx.currentTime, 0.03);
    }
  });
}
async function tick() {
  try {
    const r = await (await fetch("/api/levels", {cache: "no-store"})).json();
    last = r; render(r);
  } catch (e) {
    if (last) { Object.values(last.levels).forEach(L => L.stale = true); render(last); }
  }
}
document.getElementById("go").onclick = () => { ensureAudio(); ctx.resume(); };
document.getElementById("stop").onclick = () => { if (ctx) Object.values(gain).forEach(g => g.gain.setTargetAtTime(0, ctx.currentTime, 0.05)); };
document.getElementById("reset").onclick = () => { maxes = {}; };
document.getElementById("click").onchange = (e) => { clickOn = e.target.checked; };
setInterval(tick, 150);
</script></body></html>
"""


class State:
    def __init__(self, mode, mhz):
        self.mode, self.mhz = mode, mhz
        self.levels = {}
        self.lock = threading.Lock()

    def set(self, name, label, dbm, info=""):
        with self.lock:
            self.levels[name] = {"label": label, "dbm": dbm, "t": time.time(), "info": info}

    def snapshot(self):
        with self.lock:
            now = time.time()
            out = {}
            for n, L in self.levels.items():
                out[n] = dict(L, stale=(now - L["t"]) > 2.0)
            return {"mode": self.mode, "mhz": self.mhz, "levels": out, "t": now}


def demo_loop(st):
    a, b = -70.0, -65.0
    while True:
        a += random.uniform(-1.5, 1.5)
        b += random.uniform(-1.5, 1.5)
        st.set("A", "A's receiver (dish A)", round(a, 1), "demo")
        st.set("B", "B's receiver (dish B)", round(b, 1), "demo")
        time.sleep(0.2)


def board_loop(st, mhz, dwell, one_way):
    import twoboard as T
    nodes = {n: T.Node(n) for n in ("A", "B")}

    def sender(n):
        nodes[n].send(mhz, muted=False)

    def listener(n):
        cl = nodes[n].cl
        cl.safe()
        cl.pll_tune(0, T.park(mhz))
        cl.pll_tune(1, mhz)
        cl.ctrl(tr_a=1, tx_dis=1)
        cl.dsa(20.0)

    def level(n):
        v = []
        for _ in range(5):
            d = nodes[n].cl.detectors()
            if d.get("log_dbm") is not None:
                v.append(d["log_dbm"])
        v.sort()
        return (v[len(v) // 2] if v else None), (d.get("peak_dbm") if v else None)

    pairs = [("B", "A")] if one_way == "BA" else [("A", "B")] if one_way == "AB" else [("B", "A"), ("A", "B")]
    label = {"A": "A's receiver: aim dish A", "B": "B's receiver: aim dish B"}
    for tx, rx in pairs:
        listener(rx)
    try:
        while True:
            for tx, rx in pairs:
                nodes[rx].cl.ctrl(tr_a=1, tx_dis=1)                 # the listener muted and on its dish first
                if len(pairs) > 1:
                    nodes[rx].cl.pll_tune(0, T.park(mhz))           # (it was the sender a moment ago)
                    nodes[rx].cl.pll_tune(1, mhz)
                    nodes[rx].cl.dsa(20.0)
                sender(tx)
                time.sleep(0.03)
                t0 = time.time()
                while time.time() - t0 < dwell:
                    dbm, pk = level(rx)
                    st.set(rx, label[rx], None if dbm is None else round(dbm, 1), "%s transmitting; peak %s" % (tx, None if pk is None else round(pk, 1)))
                nodes[tx].cl.ctrl(tx_dis=1)
    finally:
        for n in nodes.values():
            try:
                n.quiet()
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--mhz", type=float, default=5200.0)
    ap.add_argument("--dwell", type=float, default=0.4, help="seconds each board transmits in turn")
    ap.add_argument("--port", type=int, default=8082)
    ap.add_argument("--one-way", choices=["BA", "AB"], default=None, help="one direction only (one tone)")
    ap.add_argument("--demo", action="store_true", help="no boards: wandering tones")
    a = ap.parse_args()
    st = State("demo" if a.demo else ("one way %s" % a.one_way if a.one_way else "both dishes, the boards in turn"), a.mhz)
    th = threading.Thread(target=demo_loop if a.demo else board_loop, args=(st,) if a.demo else (st, a.mhz, a.dwell, a.one_way),
                          daemon=True)
    th.start()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path.startswith("/api/levels"):
                body = json.dumps(st.snapshot()).encode()
                ctype = "application/json"
            else:
                body = PAGE.encode()
                ctype = "text/html; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer(("0.0.0.0", a.port), H)
    print("aim by ear: http://%s:%d/  (and on the LAN at this laptop's address)" % ("localhost", a.port), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
