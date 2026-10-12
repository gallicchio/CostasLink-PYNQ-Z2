#!/usr/bin/env python3
"""Range against error rate for every modulation and both receiver paths, at several amplifier
price levels (Jason, Prompts 2, 3 and 6), from the numbers sim/budget.py established.

    python3 sim/link_rates.py                 prints the tables
    python3 sim/link_rates.py --json F        also writes them for the block diagrams
                                              (and always build/link_rates.md, the markdown tables)

The model (PLAN.md section 13 explains it in words):

* Two receiver paths share the RF chain and the demodulator.  The FAST path is the arm
  amplifier at gain 4 (B_fast, about 100 MHz) into the first comparators: it flags a bit in a few
  nanoseconds.  The SLOW path takes the same arm outputs through a gain-20 stage and a 4.8 MHz
  pole (noise bandwidth B_slow = 7.5 MHz) into three more comparators: 11 dB more sensitive, 37 ns
  later; the gateware uses it to confirm or veto the fast flag.
* Each path has two limits.  NOISE: the comparator sees the carrier's I (or Q) plus Gaussian noise
  of power kT B F in its bandwidth; call that ratio "snr".  FLOOR: a TLV3601 needs about 20 mV
  peak (twice its offset plus hysteresis) to decide at all; with the DSA at 0 dB that is a fixed
  level at the antenna for each path (sim/budget.py section 3: the fast path -81 dBm, the slow
  path -107 dBm).  The range is the shorter of the two.
* Each scheme's error probability PER DECISION, as a function of snr.  The comparators decide on
  the instantaneous value behind the arm's low-pass of noise bandwidth B, so the decision's
  amplitude-to-sigma ratio is sqrt(snr) with snr = P / (kTF B): the I noise of a zero-IF receiver
  is the RF noise of BOTH sidebands, 2B wide (Response 10 measured it: an RF-level simulation of a
  carrier in white noise, an ideal mixer and a brick-wall B gives (I / sigma)^2 = P / (N0 B) to
  0.5 %).  Until Response 10 these were the textbook Eb/N0 forms with Eb/N0 = snr, which is the
  matched filter of a symbol 1/B long, not 1/(2B): every coherent range was 3 dB optimistic.
    BPSK   (sign of I)                              Pe = Q(sqrt(snr))
    QPSK   (I and Q at +-45 deg, one bit each)      Pe = Q(sqrt(snr / 2))   per bit (and the floor is 3 dB higher)
    FSK    (the direction of (I,Q) rotation,
            decided from edge order: a differential,
            noncoherent decision)                    Pe = exp(-snr/4) / 2
    OOK    (envelope detector, noncoherent, and no
            frequency selectivity: its noise is the
            detector's whole 500 MHz; the old board,
            no comparator floor modelled)            Pe = exp(-snr_ook/8) / 2,  snr_ook = snr - 10 log(500 / B_fast)
    whitened BPSK stream (an LFSR scrambler, matched filter over one 10 ns symbol: Eb/N0 = snr
            in the fast path's 100 MHz, so this one keeps the textbook form):
                                                     Pe = 3 Q(sqrt(2 snr))   (a self-synchronising
            descrambler turns each channel error into three; an additive scrambler with frame
            sync makes it 1 x but loses a whole frame when sync slips)
* Three thresholds: 1 % and 5 % of the MESSAGES wrong (Jason's tolerance), and "quiet": at
  most 1e-4 per decision, which at 1e8 decisions a second is 1e4 false events a second, one
  per hundred trials when trials run at 1 MHz.  An idle link that is not quiet keeps
  delivering bits nobody sent; with two paths a fast false flag is vetoed by the slow path
  and costs a trial, not a bit, so "quiet" is what the SLOW path must be.
* Range: Friis in free space with the antennas and cables of sim/budget.py and a margin
  (6 dB outdoors for pointing and ground reflection; 10 dB indoors for multipath), solved for
  the distance at which snr falls to each threshold.  The amplifier tiers are transmit power
  at the antenna port: the board alone, a cheap USB-C amplifier (unmeasured: 20 and 27 dBm
  bracket what those sell as), a 2 W FPV booster, a 10 W amplifier.  An LNA at the antenna
  removes the receive cable from the noise figure (NF 2 dB instead of 1.5 dB + cable).
"""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
c0 = 299792458.0


def Q(x):
    return 0.5 * math.erfc(x / math.sqrt(2.0))


def Qinv(p):
    lo, hi = 0.0, 40.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if Q(mid) > p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def db(x):
    return 10.0 * math.log10(x)


SCHEMES = ["BPSK", "QPSK", "FSK", "OOK", "whitened"]
FLOOR_EXTRA_dB = {"BPSK": 0.0, "QPSK": 3.0, "FSK": 0.0, "OOK": None, "whitened": 0.0}   # OOK: the old board, no floor modelled
THRESHOLDS = [("5 % wrong", 0.05), ("1 % wrong", 0.01), ("quiet (1e-4)", 1e-4)]

# transmit power at the antenna port above the board's own: the board alone; the SBB5089+SE5004 2 W
# module Jason has (sim/budget.py section 2c), run 3 dB below its P1dB through a 20 dB pad; the same
# module at its P1dB; a 10 W amplifier (not owned).  The budget's JSON carries the module's numbers.
PA = None


def pa_tiers(B):
    pm = B["pa_module"]
    return [("board alone", 0.0, "$0"),
            ("2 W module at +%.0f dBm (%.0f dB pad)" % (pm["out_dBm"], pm["pad_dB"]), pm["out_dBm"] - B["tx_out_dBm"], "$%.0f, owned" % pm["price_usd"]),
            ("2 W module at its P1dB (+%.0f)" % pm["p1db_dBm"], pm["p1db_dBm"] - B["tx_out_dBm"], "compressed"),
            ("10 W amplifier (+40)", 40.0 - B["tx_out_dBm"], "$300+")]

# (name, antenna at each end, cable metres at each end, LNA at the antenna?, margin dB, indoor?)
SCENARIOS = [
    ("lab: 2 dBi whips on the SMAs, no cables", "whip", 0.0, False, 10.0, True),
    ("campus: panels, 10 m cables, amplifiers at the board", "panel", 10.0, False, 6.0, False),
    ("campus: panels, PA and LNA at the panel", "panel", 0.0, True, 6.0, False),
    ("mountain: 30 dBi dishes, PA and LNA at the dish", "dish", 0.0, True, 6.0, False),
]


def fmt(d):
    return "-" if d < 1 else ("%.0f m" % d if d < 1000 else ("%.1f km" % (d / 1e3) if d < 1e5 else ">100 km"))


def main(argv):
    B = json.load(open(os.path.join(ROOT, "build", "budget.json")))
    f = B["f_Hz"]
    lam = c0 / f
    ptx = B["tx_out_dBm"]
    ant = B["antennas"]
    cab = B["cable_dB_per_m"]
    nf0 = B["nf_chain_dB"]
    B_fast, B_slow = B["B_MHz"], B["B_slow_MHz"]
    global PA
    PA = pa_tiers(B)
    PATHS = {"fast": dict(B_MHz=B_fast, floor_dBm=B["floor_fast_dBm"]), "slow": dict(B_MHz=B_slow, floor_dBm=B["floor_slow_dBm"])}
    snr_fn = {
        "BPSK": lambda pe: Qinv(pe) ** 2,
        "QPSK": lambda pe: 2.0 * Qinv(pe) ** 2,
        "FSK": lambda pe: -4.0 * math.log(2.0 * pe),
        "OOK": lambda pe: -8.0 * math.log(2.0 * pe) * (500.0 / B_fast),      # the detector's 500 MHz against the fast arm
        "whitened": lambda pe: Qinv(pe / 3.0) ** 2 / 2.0,
    }
    out = {"schemes": {}, "paths": PATHS, "scenarios": [], "latency": {}}

    print("required SNR in the path's bandwidth, dB:")
    print("  %-10s" % "scheme" + "".join("%16s" % t for t, _ in THRESHOLDS))
    for name in SCHEMES:
        req = {t: db(snr_fn[name](pe)) for t, pe in THRESHOLDS}
        out["schemes"][name] = req
        print("  %-10s" % name + "".join("%16.1f" % req[t] for t, _ in THRESHOLDS))
    assert abs(out["schemes"]["BPSK"]["1 % wrong"] - 7.3) < 0.2       # Q^-1(0.01)^2 = 5.41 (4.3 dB until Response 10's correction)
    print("paths: fast %.0f MHz, comparator floor %.1f dBm; slow %.1f MHz, floor %.1f dBm" % (B_fast, PATHS["fast"]["floor_dBm"], B_slow, PATHS["slow"]["floor_dBm"]))

    print("\nrange in metres at which each path's error rate reaches each threshold (free space, Friis; the shorter of the noise limit and the comparator floor):")
    for sname, a, cable_m, lna, margin, indoor in SCENARIOS:
        nf = B["lna_module"]["nf_dB"] if lna else nf0 + cable_m * cab     # the LNA module at the antenna hides the receive cable
        gain = 2 * ant[a] if lna else 2 * ant[a] - 2 * cable_m * cab   # a PA at the antenna hides the transmit cable too
        rows = []
        print("\n%s  (NF %.1f dB, antennas %.0f dBi, margin %.0f dB)" % (sname, nf, ant[a], margin))
        print("  %-24s %-5s %-10s" % ("amplifier", "path", "scheme") + "".join("%14s" % t for t, _ in THRESHOLDS))
        for pname, pa, price in PA:
            for path, pp in PATHS.items():
                noise = -174.0 + db(pp["B_MHz"] * 1e6) + nf
                for scheme, req in out["schemes"].items():
                    ds = []
                    for t, _ in THRESHOLDS:
                        budget_noise = ptx + pa + gain - margin - noise - req[t]
                        d_noise = lam / (4 * math.pi) * 10 ** (budget_noise / 20.0)
                        if FLOOR_EXTRA_dB[scheme] is None:
                            d = d_noise
                        else:
                            budget_floor = ptx + pa + gain - margin - pp["floor_dBm"] - FLOOR_EXTRA_dB[scheme]
                            d = min(d_noise, lam / (4 * math.pi) * 10 ** (budget_floor / 20.0))
                        ds.append(min(d, 1e5))
                    rows.append(dict(amplifier=pname, pa_dB=pa, price=price, path=path, scheme=scheme, d_m=ds))
                    print("  %-24s %-5s %-10s" % (pname if (scheme == "BPSK" and path == "fast") else "", path if scheme == "BPSK" else "", scheme)
                          + "".join("%14s" % fmt(d) for d in ds))
        out["scenarios"].append(dict(name=sname, nf_dB=nf, antenna_dBi=ant[a], margin_dB=margin, indoor=indoor, rows=rows))
    # the lab, board alone: the slow path must be quiet to 30 m in every scheme, the fast flag in BPSK
    lab = out["scenarios"][0]["rows"]
    for r in lab:
        if r["pa_dB"] == 0.0 and r["scheme"] != "OOK" and (r["path"] == "slow" or r["scheme"] == "BPSK"):
            assert r["d_m"][2] > 30, (r["path"], r["scheme"], r["d_m"])
    # extra loss the lab link can absorb (walls) at 30 m with the board alone, BPSK quiet, slow path
    noise_slow = -174.0 + db(B_slow * 1e6) + nf0
    budget30 = ptx + 2 * ant["whip"] - 10.0 - noise_slow - out["schemes"]["BPSK"]["quiet (1e-4)"] - (20 * math.log10(4 * math.pi * 30.0 / lam))
    budget30 = min(budget30, ptx + 2 * ant["whip"] - 10.0 - PATHS["slow"]["floor_dBm"] - (20 * math.log10(4 * math.pi * 30.0 / lam)))
    out["walls_dB_at_30m"] = budget30
    print("\nat 30 m indoors with whips and no amplifier the slow path stays quiet through %.0f dB of walls (drywall 3-6 dB, brick 10-15, a floor 15-25)" % budget30)

    # latency: the idle-carrier event against the whitened stream, electronics only (sim/budget.py section 5)
    t_rise = 0.35 / B_fast * 1e3                            # 10-90 % rise of the fast arm, ns
    Ts = 10.0                                               # the stream's symbol, ns (100 Mbaud)
    out["latency"] = dict(idle_carrier_extra_ns=0.0, whitened_extra_ns=Ts / 2.0 + (Ts - t_rise * 0.5), slow_confirm_ns=B["slow_t50_ns"],
                          note="the whitened stream waits for the next symbol slot (Ts/2 on average) and integrates a whole symbol before deciding")
    print("\nlatency: the fast path delivers the flip when its %.0f MHz arm crosses (%.1f ns rise), %.1f ns pin to register on the PYNQ; "
          "the slow path confirms %.0f ns later; a whitened stream at 100 Mbaud would add %.1f ns on average"
          % (B_fast, t_rise, B["latency_ns"], B["slow_t50_ns"], out["latency"]["whitened_extra_ns"]))

    # the side-by-side tables (markdown): schemes as columns, one line per scenario x amplifier x path
    md = ["<!-- made by sim/link_rates.py; the plan and the chat copy these -->", ""]
    for ti, (tname, _) in enumerate(THRESHOLDS):
        md.append("**Range, %s** (metres unless km; free space plus margin; the shorter of the noise limit and the comparator floor; '-' below 1 m)" % tname)
        md.append("")
        md.append("| scenario | amplifier | path | " + " | ".join(SCHEMES) + " |")
        md.append("|---|---|---|" + "---|" * len(SCHEMES))
        for sc in out["scenarios"]:
            for pname, pa, price in PA:
                for path in PATHS:
                    cells = [fmt([r for r in sc["rows"] if r["scheme"] == s and r["amplifier"] == pname and r["path"] == path][0]["d_m"][ti]) for s in SCHEMES]
                    md.append("| %s | %s (%s) | %s | %s |" % (sc["name"], pname, price, path, " | ".join(cells)))
        md.append("")
    open(os.path.join(ROOT, "build", "link_rates.md"), "w").write("\n".join(md) + "\n")
    print("wrote build/link_rates.md")
    if "--json" in argv:
        fn = argv[argv.index("--json") + 1]
        json.dump(out, open(os.path.join(ROOT, fn) if not os.path.isabs(fn) else fn, "w"), indent=1)
        print("wrote", fn)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
