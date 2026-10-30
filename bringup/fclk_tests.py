#!/usr/bin/env python3
"""fclk_tests.py: board A at fabric clocks other than 100 MHz (Jason, 2026-10-30: "Can you alter the FPGA PLLs to test
things at rates other than 50 MHz and 100 MHz?").  FCLK0 set on the PYNQ (pynq_fclk.py, root, over ssh with a password:
PYNQ_ASKPASS names an askpass script), the fabric reset so the clock wizard relocks; then at each clock f:

  * the bus, the I2C and both synthesizers checked;
  * BPSK PRBS15 on CMP_I at 1 and 2 clocks a symbol (f and f / 2 baud), the sampling phase scanned;
  * A1 and A3's decision latency (20 000 events), in ns at this clock: the decision's clocked part scales with 1 / f
    and the analog part does not, so the latencies against 1 / f split the two;
  * the fast path's ring (A3, windows at 0.4 a): combinational, so its hop should not move with f (a control).

The order is 90.9, 83.3, 76.9 MHz (inside the build's timing), then 111.1 MHz (outside it: flagged), then 100 MHz
restored and checked.  No other client may touch the bus while the clock changes (the watchdog stopped first).

    PYNQ_ASKPASS=... python3 bringup/fclk_tests.py [--only 11,1 ...]
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import campaign as C                                 # noqa: E402
import stages as S                                   # noqa: E402

HOST = "xilinx@192.168.8.142"
SETTINGS = [(11, 1), (6, 2), (13, 1), (9, 1)]          # 90.9, 83.3, 76.9, 111.1 MHz
RESTORE = (5, 2)


def ssh(cmd, timeout=40):
    env = dict(os.environ, SSH_ASKPASS=os.environ["PYNQ_ASKPASS"], SSH_ASKPASS_REQUIRE="force")
    r = subprocess.run(["setsid", "ssh", "-o", "PubkeyAuthentication=no", "-o", "ConnectTimeout=10", HOST, cmd],
                       env=env, capture_output=True, text=True, timeout=timeout)
    return (r.stdout + r.stderr).strip()


def scp(src, dst):
    env = dict(os.environ, SSH_ASKPASS=os.environ["PYNQ_ASKPASS"], SSH_ASKPASS_REQUIRE="force")
    subprocess.run(["setsid", "scp", "-o", "PubkeyAuthentication=no", "-o", "ConnectTimeout=10", src, HOST + ":" + dst],
                   env=env, capture_output=True, text=True, timeout=40, check=True)


def set_fclk(d0, d1):
    out = ssh("echo xilinx | sudo -S -p '' python3 /home/xilinx/pynq_fclk.py %d %d reset" % (d0, d1))
    time.sleep(1.0)
    return out


def at_clock(f_mhz, tag):
    c = C.Camp()
    cl = c.cl
    cl.clk_mhz = f_mhz
    cl.t_clk = 1e-6 / f_mhz
    cl.t_sample = cl.t_clk / cl.ser
    row = {"f_mhz": f_mhz, "tag": tag}
    try:
        row["id"] = "0x%08x" % cl.rd("ID")
        cl.safe()
        row["vc"] = cl.adc("VC")
        row["lock_5800"] = c.tune(5800)
        print("  %s: ID %s, VC %.3f V (I2C), synthesizers %s" % (tag, row["id"], row["vc"], row["lock_5800"]), flush=True)
        c.scope_iq(vdiv=0.1)
        reg = c.regulated_dsa(5000)
        lk = c.lock_at(5000, reg, fresh=True)
        if lk is None:
            row["error"] = "no lock at 5.0 GHz"
            print("  no lock", flush=True)
            return row
        cen, side, a_leg, _ = lk
        row["a_leg"] = a_leg
        row["ber"] = []
        for p in (1, 2):
            ph, scan, width = c.best_phase(side, p)
            r = c.ber_once(side, p, ph, 1.0)
            row["ber"].append({"period": p, "mbaud": f_mhz / p, "phase": ph, "open_phases": width, "scan": scan, **r})
            print("  %.1f Mbaud: open %d of %d phases, BER %s (%d bits)" % (f_mhz / p, width, 8 * p, r["ber"], r["bits"]), flush=True)
            side = c.ensure(5000, reg, cen, a_leg) or side
        c.thresholds(cen, a_leg, 0.5)
        row["latency"] = {}
        for name in ("A1", "A3"):
            side = c.ensure(5000, reg, cen, a_leg) or side
            st = c.scheme_run(name, side, count=20000, period=2000, width=20)
            row["latency"][name] = {k: st[k] for k in ("events", "decided", "right", "symbol_errors", "false", "missed",
                                                       "lat_min", "lat_max", "lat_mean", "sample_ns")}
            ns = [st[k] * st["sample_ns"] for k in ("lat_min", "lat_mean", "lat_max")] if st["lat_n"] else None
            print("  %s: decided %d of %d, right %d; latency %s ns" % (name, st["decided"], st["events"], st["right"],
                  ns and "%.2f / %.2f / %.2f" % tuple(ns)), flush=True)
        from netbus import NetBus
        from costaslink import CostasLink
        lc = CostasLink(NetBus(c.b.cfg["pynq_host"], c.b.cfg.get("pynq_port", 5800)))
        lc.clk_mhz, lc.t_clk, lc.t_sample = f_mhz, 1e-6 / f_mhz, 1e-6 / f_mhz / lc.ser
        c.thresholds(cen, a_leg, 0.4)
        hops = []
        for _ in range(3):
            side = c.ensure(5000, reg, cen, a_leg) or side
            rg = lc.ring_run(C.Frame0(C.RINGS["A3"], side), order=C.RING_ORDER["A3"], clocks=2000, mask=0x1F)
            hops.append({k: rg.get(k) for k in ("hops", "span", "turnaround_ns", "sample_ns")})
            c.cl.hold_point(1, 0)
        row["ring_A3"] = hops
        print("  ring A3 at 0.4 a: %s" % ["%s hops, %.2f ns" % (h["hops"], h["turnaround_ns"] or 0) for h in hops], flush=True)
        lc.fast_off()
        lc.wr("RT_CFG", 0)
    except Exception as e:                                   # noqa: BLE001
        row["error"] = str(e)[:300]
        print("  FAILED:", e, flush=True)
    finally:
        try:
            c.cleanup()
        except Exception as e:                               # noqa: BLE001
            row["cleanup_error"] = str(e)[:200]
    return row


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", default=None, help="d0,d1 pairs")
    a = ap.parse_args(argv)
    settings = [tuple(int(x) for x in s.split(",")) for s in a.only] if a.only else SETTINGS
    scp(os.path.join(HERE, "pynq_fclk.py"), "/home/xilinx/pynq_fclk.py")
    out = {"rows": [], "log": []}
    try:
        out["log"].append(ssh("echo xilinx | sudo -S -p '' python3 /home/xilinx/pynq_fclk.py"))
        out["rows"].append(at_clock(100.0, "100 MHz before"))
        for d0, d1 in settings:
            f = 1000.0 / (d0 * d1)
            print("==== FCLK0 %.3f MHz (%d x %d)" % (f, d0, d1), flush=True)
            out["log"].append(set_fclk(d0, d1))
            print(out["log"][-1], flush=True)
            out["rows"].append(at_clock(f, "%.1f MHz" % f))
            C.save("fclk_partial", out)
    finally:
        print("==== restoring 100 MHz", flush=True)
        out["log"].append(set_fclk(*RESTORE))
        print(out["log"][-1], flush=True)
        out["rows"].append(at_clock(100.0, "100 MHz restored"))
        path = C.save("fclk", out)
        c = C.Camp()
        c.b.record("verdict", test="campaign_fclk", ok=None, file=path,
                   text="the fabric's clock at 76.9-111.1 MHz (FCLK0 through the clock wizard): the BER at f and f / 2 baud, "
                        "A1 / A3's latency against 1 / f, the fast path's ring as a control; 100 MHz restored")
        print(path)


if __name__ == "__main__":
    main(sys.argv[1:])
