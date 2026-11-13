"""survey_board.py HOST OUT.json START_EPOCH HOLD_UNTIL_EPOCH [STEP_MHZ]: the board's own receiver surveys 4300-6000 MHz
through its dish, both boards at once (each disables its own TX and holds its loop, so both TXs are off together).
At each frequency: the RX synthesizer tuned there, the slow arm's window threshold (V_T2 against CMP_QP_S, ~7.5 MHz
noise bandwidth) found by a coarse pass over 0.60-2.60 V in 20 mV steps, then stepped in 2 mV steps over +-40 mV
around it (the driver's own survey() ladder assumes the arm sits at V_MID; the arm's centre moves with the LO frequency
by tens of mV, 1.0-2.05 V on board A tonight, and its noise sigma is ~5 mV), the noise's Gaussian fitted
here (probit, the duties between 0.05 and 0.95), its sigma turned into dBm at RX ANT by the driver's sigma_to_dbm, and
the duty past v0 + 4 sigma kept as the bursts' share ('tail': ~3e-5 for noise alone).  Passes at DSA 0 and DSA 20.
After the passes this board's TX stays disabled until HOLD_UNTIL, then TX and loop are released (the stations set up again)."""
import json, os, statistics, sys, time
sys.path.insert(0, os.path.expanduser(os.environ.get("CL_DRIVER", "~/OpticsPCBs/CostasLink-PYNQ-Z2/gateware/driver")))
from netbus import RemoteCostasLink  # noqa: E402

host, out, start, hold = sys.argv[1], sys.argv[2], float(sys.argv[3]), float(sys.argv[4])
step = int(sys.argv[5]) if len(sys.argv) > 5 else 10
freqs = list(range(4300, 6001, step))
COARSE = [round(0.60 + 0.02 * k, 3) for k in range(101)]
nd = statistics.NormalDist()


def fit(points):
    pts = [(v, nd.inv_cdf(1.0 - d)) for v, d in points if 0.05 < d < 0.95]
    if len(pts) < 2:
        return None, None
    n = len(pts); mv = sum(v for v, _ in pts) / n; mz = sum(z for _, z in pts) / n
    szz = sum((z - mz) ** 2 for _, z in pts); svz = sum((v - mv) * (z - mz) for v, z in pts)
    if szz <= 0 or svz <= 0:
        return None, None
    sigma = svz / szz
    return mv - sigma * mz, sigma


rec = {"host": host, "freqs": freqs, "coarse": [COARSE[0], COARSE[-1], 0.02], "fine": "+-40 mV at 2 mV", "passes": []}
cl = RemoteCostasLink(host)
try:
    rec["before"] = {"ctrl": cl.rd("CTRL")}
    th = cl.thermal_dbm("slow")
    rec["thermal_dbm_slow"] = th
    while time.time() < start:
        time.sleep(0.05)
    cl.ctrl(tx_dis=1, loop_hold=1)
    for dsa in (0.0, 20.0):
        cl.dsa(dsa)
        t0 = time.time()
        rows = []
        for f in freqs:
            cl.pll_tune(1, f, f_pfd=5.0, cp=15)
            time.sleep(0.005)
            coarse = cl.noise_scan("slow", volts=COARSE, seconds=0.002)
            cross = [v for (v, d), (v2, d2) in zip(coarse, coarse[1:]) if d >= 0.5 > d2]
            if cross:
                c = cross[0]
                pts = cl.noise_scan("slow", volts=[round(c - 0.04 + 0.002 * k, 4) for k in range(46)], seconds=0.003)
            else:
                pts = coarse
            v0, sigma = fit(pts)
            row = {"f_mhz": f, "v0": v0, "sigma": sigma, "dbm": None, "inr_db": None, "tail": None,
                   "duty_lo": pts[0][1], "duty_hi": pts[-1][1]}
            if sigma:
                row["dbm"] = cl.sigma_to_dbm(sigma, "slow") + dsa
                row["inr_db"] = row["dbm"] - dsa - th
                past = [d for v, d in pts if v > v0 + 4.0 * sigma]
                row["tail"] = past[0] if past else None
            rows.append(row)
        rec["passes"].append({"dsa": dsa, "t0": time.strftime("%H:%M:%S", time.localtime(t0)), "s": round(time.time() - t0, 1), "rows": rows})
        print(time.strftime("%T"), host, "DSA", dsa, "%d freqs in %.0f s" % (len(freqs), time.time() - t0), flush=True)
        json.dump(rec, open(out, "w"), indent=1, default=str)
    while time.time() < hold:
        time.sleep(0.2)
finally:
    try:
        cl.ctrl(tx_dis=0, loop_hold=0)
        rec["after"] = {"ctrl": cl.rd("CTRL")}
    finally:
        json.dump(rec, open(out, "w"), indent=1, default=str)
        print(time.strftime("%T"), "->", out, flush=True)
