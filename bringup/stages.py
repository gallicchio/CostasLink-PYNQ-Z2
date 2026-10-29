#!/usr/bin/env python3
"""stages.py: BRINGUP.md's measurements as procedures, each one recording its readings and a verdict against the
stage's pass condition in the board's log (bench.py's Log).  Run them through bench.py:

    python3 bringup/bench.py run stage1.i2c [--eeprom true]
    python3 bringup/bench.py run stage2.lo --which tx
    python3 bringup/stages.py                   # the list, with each one's first line

What each needs cabled is in its docstring: read it (or ask) before running one.  Every procedure that turns the
transmitter on turns it off again (TX_DIS high) before it returns, also on an error.
"""
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bench as B                                       # noqa: E402
from board_constants import VR_I_V, VR_Q_V, V_MID      # noqa: E402

DAC1, DAC2 = 0x60, 0x61
F_LO = 5800e6            # both synthesizers' PLL_INIT frequency (max2871_words.vh)
F_REF = 25e6             # the TCXO / VCXO, and the PFD (R = 1): the reference spurs sit at +-25 MHz
BPWR_DBM = -1.0          # RFOUTB as max2871_regs.py programs it (BPWR = 1): the LO MON level, less the tap's loss
TX_MON_DBM = -10.0       # BRINGUP 2.3: +9.8 dBm at TX ANT through the -20 dB coupler
KVCXO_HZ_V = 430e3       # sim/budget.py: the VCXO's pull at 5.8 GHz, 430 kHz/V
CURRENT_BEFORE_PLL_A = (0.89, 0.89 + 0.40)   # BRINGUP 1.3: before the MAX2871s are programmed
CURRENT_RUNNING_A = 1.37                     # both synthesizers at full output, the transmitter on
RELOCK_S = 0.2           # a retune's wait: every write of the six words reruns the VCO autoselect, and with
                         # VAS_TEMP = 1 that took 62 ms on board A (BRINGUP_LOG 2.1), not the 200 us without it


def _fit_line(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return my - b * mx, b


# ---------------------------------------------------------------------------------------------------------
# stage 1: first power, no RF
# ---------------------------------------------------------------------------------------------------------
def smoke(b, volts=B.SUPPLY_V, amps=B.SMOKE_A, seconds=3.0):
    """1.1: 5 V at a 0.10 A limit for a few seconds, then off.  The ADL5380 and the three ADL5611 have no enable,
    so a sound board pulls the supply into its limit and settles at a volt or two; a short holds it near 0 V.
    Cabled: the supply's output (bench_config psu.out) into the board's USB-C (the short USB-A-to-C lead), nothing
    on the header.  The output must start off: a board already powered has had its first power."""
    b.stage = b.stage or "1.1"
    if b.psu.q("OUTPut?") == "1":
        raise IOError("the %s's output is already on: psu off first (and say what was connected)" % b.psu.model)
    b.psu_setup(volts, amps)
    rows = []
    b.psu_output(True)
    try:
        t0 = time.time()
        while time.time() - t0 < seconds:
            rows.append(b.psu_read("smoke"))
    finally:
        b.psu_output(False)
    last = rows[-1]
    v, i, mode = last["volts"], last["amps"], last["mode"]
    if v < 0.3:
        text, ok = "SHORT: %.2f V at %.3f A. Stop: look for D303 or C320 backwards, a solder bridge on +5V_IN" % (v, i), False
    elif mode == "CC" and v < volts - 0.2:
        text, ok = ("sound: in the %.2f A limit at %.2f V (the chips that have no enable start to draw). "
                    "Raise the limit (psu on)" % (amps, v)), True
    else:
        text, ok = ("%.2f V at %.3f A, not in the limit: the board draws less than %.2f A at full voltage, and the "
                    "ADL5380 alone should take more. Check the USB-C lead and the supply's leads before raising "
                    "the limit" % (v, i, amps)), None
    return b.record("verdict", test="smoke", ok=ok, text=text, readings=[(r["volts"], r["amps"], r["mode"]) for r in rows])


def ramp(b, volts=B.SUPPLY_V, limits=(0.10, 0.25, 0.50, 0.80, 1.10, B.SUPPLY_A), dwell_s=2.0):
    """1.1-1.3 in one go: the supply at `volts` with its current limit raised step by step from the smoke test's
    0.10 A to 1.5 A, the supply read at every step.  Off at once on a short (under 0.3 V at the first step), an OVP
    trip, or a draw over the budget (still in its limit at the last step, or above 1.42 A).  Left ON at the last
    limit when every step was sound, for the rails (1.2) and the heat log (1.3-1.4).
    Cabled: the supply's output into the board's USB-C, nothing on the header.  The output must start off."""
    b.stage = b.stage or "1.1"
    p = b.psu
    out = b.cfg["psu"].get("out", 1)
    if p.q("OUTPut?") == "1":
        raise IOError("the %s's output is already on: psu off first (and say what was connected)" % p.model)
    hi = CURRENT_BEFORE_PLL_A[1] * 1.10                       # 1.42 A: the budget's top plus 10 %
    b.psu_setup(volts, limits[0])
    steps, why, ok = [], None, False
    b.psu_output(True)
    try:
        for k, amps in enumerate(limits):
            if k:
                p.set(volts, amps, out=out)
            t0, rows = time.time(), []
            while time.time() - t0 < dwell_s:
                rows.append(b.psu_read("ramp %.2f A" % amps))
            last = rows[-1]
            v, i, mode = last["volts"], last["amps"], last["mode"]
            steps.append({"limit_a": amps, "volts": v, "amps": i, "mode": mode})
            print("  limit %.2f A: %.3f V %.3f A %s" % (amps, v, i, mode), flush=True)
            if p.setting(out)["ovp_tripped"]:
                why = "OVP tripped at the %.2f A step (%.3f V): its accuracy is +-(0.5 %% + 0.5 V)" % (amps, v)
            elif k == 0 and v < 0.3:
                why = "SHORT: %.2f V at %.3f A. Look for D303 or C320 backwards, a bridge on +5V_IN" % (v, i)
            elif mode == "CV" and i > hi:
                why = "%.3f A in CV: over the budget's %.2f A" % (i, hi)
            elif mode == "CC" and amps >= limits[-1]:
                why = "still in the %.2f A limit at %.2f V: the board wants more than the budget" % (amps, v)
            elif mode not in ("CC", "CV"):
                why = "the output regulates %s at the %.2f A step" % (mode, amps)
            if why:
                break
        else:
            ok = True
    finally:
        if not ok:
            b.psu_output(False)
    smoke = steps[0]
    lo, top = CURRENT_BEFORE_PLL_A[0] * 0.90, hi
    if ok:
        i = steps[-1]["amps"]
        within = lo <= i <= top
        text = ("sound: %.2f V at the %.2f A limit (%s) at first; %.3f V %.3f A (%s) at %.2f A, %s the budget %.2f-%.2f A. "
                "Output left ON: the rails next" % (smoke["volts"], limits[0], smoke["mode"], steps[-1]["volts"], i,
                                                     steps[-1]["mode"], limits[-1], "within" if within else "OUTSIDE",
                                                     lo, top))
        ok = within
    else:
        text = "STOPPED, output off: " + why
    return b.record("verdict", test="ramp", ok=ok, text=text, steps=steps)


def rails_walk(b, order=("+5V_IN", "+5V_RF", "+3V3_PLL_TX", "+3V3_PLL_RX", "+3V3_ANA", "+3V3_DIG", "+3V3_OSC"),
               steady_n=8, steady_v=0.003, lifted_v=0.3, moved_v=0.02, timeout_s=900.0):
    """1.2 hands-free: the Fluke's black lead on TP308 (GND), the red lead on each test pad in `order` (TP301 to TP307,
    the bottom-right strip), lifted between pads.  A reading steady for `steady_n` readings (within `steady_v`, above
    `lifted_v`) is the next rail's; the next is taken once the lead has been lifted (under `lifted_v`) or has moved to
    another node (more than `moved_v` away).  The supply's
    volts and amps are logged with each rail.  A pad touched out of turn shows as that rail out of its limits."""
    b.stage = b.stage or "1.2"
    m = b.dmm
    m.rate("M")
    got, t0 = [], time.time()
    if isinstance(order, str):
        order = [x.strip() for x in order.split(",")]
    print("red lead to %s (%s) ..." % (B.RAIL_PADS.get(order[0], ("",))[0], order[0]), flush=True)
    for label in order:
        window = []
        while True:
            if time.time() - t0 > timeout_s:
                return b.record("verdict", test="rails", ok=None, text="timed out after %s" % [g["label"] for g in got],
                                rails=got)
            v = m.read()
            window = (window + [v])[-steady_n:]
            if (len(window) == steady_n and min(abs(w) for w in window) > lifted_v
                    and max(window) - min(window) <= steady_v):
                break
        supply = b.psu_read("with " + label)
        r = b.dmm_read(label, settle=0, n=3, supply_v=supply["volts"])
        got.append(r)
        print("  %-12s %s %.4f V  %s   (supply %.3f V %.3f A)" % (label, B.RAIL_PADS.get(label, ("",))[0], r["volts"],
              {True: "ok", False: "OUT OF LIMITS %s" % r["limits"], None: ""}[r["ok"]], supply["volts"], supply["amps"]),
              flush=True)
        while True:                                              # the lead lifted, or moved to another node
            v = m.read()
            if abs(v) < lifted_v or abs(v - r["volts"]) > moved_v or time.time() - t0 > timeout_s:
                break
    bad = [g["label"] for g in got if g["ok"] is False]
    text = ("every rail within its limits" if not bad else "OUT OF LIMITS: " + ", ".join(bad)) + ": " + ", ".join(
        "%s %.3f V" % (g["label"], g["volts"]) for g in got)
    return b.record("verdict", test="rails", ok=not bad, text=text, rails=[(g["label"], g["volts"]) for g in got])


def watch(b, hours=3.0, dt_s=10.0, amps_lo=0.6, amps_hi=1.2, pynq_misses=3, det_every=3, v5_lo=4.75, v5_hi=5.30,
          temp_hi=85.0):
    """Unattended: the supply read every dt_s and the PYNQ's server pinged; the output switched OFF on a current
    outside amps_lo-amps_hi, a mode other than CV, an OVP trip, or the PYNQ silent for pynq_misses pings in a row
    (this board powered into an unpowered Zynq drives its clamp diodes: REVB R3).  Every det_every readings the
    board's own detectors too (I2C): OFF on +5V_RF outside v5_lo-v5_hi or the NTC above temp_hi.  All logged."""
    b.stage = b.stage or "watch"
    p = b.psu
    out = b.cfg["psu"].get("out", 1)
    t_end, misses, n, why = time.time() + hours * 3600, 0, 0, None
    while time.time() < t_end:
        r = b.psu_read("watch")
        n += 1
        alive = False
        for attempt in (0, 1):                                   # a restarted server breaks the old connection:
            try:                                                 # reconnect once before calling it silent
                alive = bool(B.reachable(b.cfg["pynq_host"], b.cfg["pynq_port"], timeout=3) and b.cl.bus.ping())
                break
            except Exception:                                    # noqa: BLE001 - a silent PYNQ is the event
                old = b._open.pop("cl", None)
                if old is not None:
                    try:
                        old.close()
                    except Exception:                            # noqa: BLE001
                        pass
        misses = 0 if alive else misses + 1
        if r["mode"] != "CV" or not amps_lo <= r["amps"] <= amps_hi:
            why = "%.3f V %.3f A %s: outside %.2f-%.2f A in CV" % (r["volts"], r["amps"], r["mode"], amps_lo, amps_hi)
        elif p.setting(out)["ovp_tripped"]:
            why = "OVP tripped"
        elif misses >= pynq_misses:
            why = "the PYNQ has not answered for %d pings" % misses
        elif alive and det_every and n % det_every == 1:
            try:
                d = b.cl.detectors()
                b.record("detectors", label="watch", v5_rf=d["v5_rf"], temp_c=d["temp_c"], volts=d["volts"])
                if not v5_lo <= d["v5_rf"] <= v5_hi:
                    why = "+5V_RF %.3f V outside %.2f-%.2f V" % (d["v5_rf"], v5_lo, v5_hi)
                elif d["temp_c"] is not None and d["temp_c"] > temp_hi:
                    why = "the board's NTC at %.1f C, over %.0f C" % (d["temp_c"], temp_hi)
            except Exception as e:                               # noqa: BLE001 - logged, not a reason to cut power
                b.record("detectors", label="watch", error=str(e)[:200])
        if why:
            b.psu_output(False)
            break
        if n % 30 == 1:
            print("%s %.3f V %.4f A, PYNQ %s" % (time.strftime("%H:%M:%S"), r["volts"], r["amps"], "up" if alive else "silent"),
                  flush=True)
        time.sleep(dt_s)
    text = ("OUTPUT SWITCHED OFF: " + why) if why else "%.1f h watched, nothing out of bounds; the output left on" % hours
    print(text, flush=True)
    return b.record("verdict", test="watch", ok=why is None, text=text, readings=n)


def heat_log(b, seconds=600.0, dt_s=5.0, with_board=False):
    """1.3-1.4: the supply's volts and amps every dt_s for `seconds` (and, with_board, the board's NTC and +5V_RF
    from the detectors' ADC); prints a line each.  Meanwhile the IR camera on the ADL5380, the ADL5375, the three
    ADL5611 and the two MAX2871: note each one's reading (bench.py note) at ten minutes."""
    b.stage = b.stage or "1.4"
    t0 = time.time()
    rows = []
    while time.time() - t0 < seconds:
        r = b.psu_read("heat")
        row = {"s": round(time.time() - t0, 1), "volts": r["volts"], "amps": r["amps"]}
        if with_board:
            try:
                d = b.cl.detectors()
                row.update(temp_c=d["temp_c"], v5_rf=d["v5_rf"])
                b.record("board", call="detectors", result=d)
            except Exception as e:                                       # noqa: BLE001 - keep logging the supply
                row["board"] = str(e)
        rows.append(row)
        print(row, flush=True)
        time.sleep(max(0.0, dt_s - 0.3))
    amps = [r["amps"] for r in rows]
    lo, hi = CURRENT_BEFORE_PLL_A
    summary = {"test": "current", "first_a": amps[0], "last_a": amps[-1], "min_a": min(amps), "max_a": max(amps),
               "budget_a": [lo, hi], "ok": lo * 0.9 <= amps[-1] <= hi * 1.1,
               "text": "BRINGUP 1.3: 0.89 A plus up to 0.4 A for the unprogrammed MAX2871s, within 10 %%: %.3f A" % amps[-1]}
    if with_board and "temp_c" in rows[-1]:
        summary["temp_c_first_last"] = [rows[0].get("temp_c"), rows[-1].get("temp_c")]
    return b.record("verdict", **summary)


def stage1_i2c(b, eeprom=False):
    """1.5: on the PYNQ (PYNQ first, this board last): the I2C scan (0x0C, 0x48, 0x49, 0x60, 0x61), the DACs at
    their safe defaults (the ladders' references at VR_I_V / VR_Q_V, the rest mid-scale; eeprom=True writes them as
    the power-up values too, once a board), the window thresholds above the idle, the ADC's I, Q, VC, ERR and the
    detectors.  Pass: five acknowledges; VC near 1.65 V (LOOP_HOLD high: VC follows VC_OFF); V5_MON = +5V_RF / 2;
    TEMP near room."""
    b.stage = b.stage or "1.5"
    b.board_call("safe")
    r = b.board_call("bringup_stage1", eeprom=eeprom)
    adc = r.get("adc", {})
    det = r.get("detectors", {})
    checks = {"five_acks": not r["missing"],
              "vc_near_v_mid": adc.get("VC") is not None and abs(adc["VC"] - V_MID) < 0.1,
              "v5_rf_in_range": det.get("v5_rf") is not None and 4.75 <= det["v5_rf"] <= 5.25,
              "temp_room": det.get("temp_c") is not None and 15 <= det["temp_c"] <= 45}
    return b.record("verdict", test="stage1.5", ok=all(checks.values()), checks=checks, found=r["found"],
                    missing=r["missing"], adc=adc, v5_rf=det.get("v5_rf"), temp_c=det.get("temp_c"))


# ---------------------------------------------------------------------------------------------------------
# stage 2: the synthesizers and the transmitter
# ---------------------------------------------------------------------------------------------------------
def stage2_pll(b):
    """2.1: both MAX2871s' power-up sequence (5.800 GHz each, integer-N, R = 1) and their lock detects (the MUX pins).
    Watch the supply's current go up by the synthesizers' share (BRINGUP 1.3)."""
    b.stage = b.stage or "2.1"
    before = b.psu_read("before pll_init") if "psu" in b.cfg and b.cfg["psu"].get("serial") else None
    done = b.board_call("pll_init")
    time.sleep(RELOCK_S)
    lock = b.board_call("pll_locked")
    after = b.psu_read("after pll_init") if before else None
    return b.record("verdict", test="pll_init", ok=bool(done and lock["tx"] and lock["rx"]), done=done, lock=lock,
                    amps_before=before and before["amps"], amps_after=after and after["amps"])


def stage2_lo(b, which="tx", f_hz=F_LO):
    """2.2: one LO MON jack on the analyser (LO TX MON J204 / LO RX MON J109, U.FL -> SMA pigtail -> N adapter -> the
    DSA875): RFOUTB on, the carrier's frequency and level, and the 25 MHz reference spurs.  Pass: within 3 dB of the
    programmed -1 dBm (less the pigtail's few tenths); spurs 60 dB down or better."""
    b.stage = b.stage or "2.2"
    k = {"tx": 0, "rx": 1}[which]
    b.board_call("lo_mon", k, True)
    time.sleep(RELOCK_S)
    lock = b.board_call("pll_locked")
    coarse = b.sa_peak(f_hz, 20e6, ref=10.0, label="LO %s MON coarse" % which.upper())
    fine = b.sa_peak(coarse["hz"], 200e3, rbw=1e3, ref=10.0, label="LO %s MON carrier" % which.upper())
    spurs = []
    ref = min(10.0, math.ceil(fine["dbm"] + 5))          # the floor follows the reference level (its attenuator)
    for off in (-F_REF, F_REF, 2 * F_REF):
        s = b.sa_peak(fine["hz"] + off, 200e3, rbw=1e3, ref=ref, label="LO %s MON at %+g MHz" % (which.upper(), off / 1e6))
        spurs.append({"offset_mhz": off / 1e6, "dbm": s["dbm"], "dbc": s["dbm"] - fine["dbm"],
                      "atten_db": s["settings"]["amplitude"]["attenuation_dB"]})
    worst = max(s["dbc"] for s in spurs)
    ppm = (fine["hz"] - f_hz) / f_hz * 1e6
    ok = abs(fine["dbm"] - BPWR_DBM) <= 3.5 and worst <= -60 and bool(lock[which])
    return b.record("verdict", test="lo_%s" % which, ok=ok, lock=lock, hz=fine["hz"], ppm_vs_sa=ppm, dbm=fine["dbm"],
                    programmed_dbm=BPWR_DBM, spurs=spurs, worst_spur_dbc=worst,
                    text="frequency error is against the analyser's own timebase (lock it to a house 10 MHz to trust ppm)")


def stage2_vcxo(b, volts=(0.3, 0.6, 0.9, 1.2, 1.5, 1.65, 1.8, 2.1, 2.4, 2.7, 3.0)):
    """2.2's pull: the loop held (LOOP_HOLD high: VC follows VC_OFF, DAC1 D), VC_OFF stepped across its range, the RX
    LO's frequency at LO RX MON on the analyser and VC on the ADC.  Pass: +-500 kHz or more at 5.8 GHz (the plan:
    +-580 kHz over 0.3-3.0 V, 430 kHz/V).  Cabled: LO RX MON to the analyser."""
    b.stage = b.stage or "2.2"
    b.board_call("ctrl", loop_hold=1)
    b.board_call("lo_mon", 1, True)
    time.sleep(RELOCK_S)
    pts = []
    try:
        for v in volts:
            b.cl.dac(DAC1, VC_OFF=v)
            time.sleep(0.3)
            vc = b.cl.adc("VC")
            f0, _ = b.sa_peak(F_LO, 4e6, rbw=10e3, record=False)
            f1, p1 = b.sa_peak(f0, 40e3, rbw=300, record=False)
            pts.append({"vc_off": v, "vc_adc": vc, "hz": f1, "dbm": p1})
            print(pts[-1], flush=True)
    finally:
        b.cl.dac(DAC1, VC_OFF=V_MID)
    a, slope = _fit_line([p["vc_adc"] for p in pts], [p["hz"] for p in pts])
    span = max(p["hz"] for p in pts) - min(p["hz"] for p in pts)
    return b.record("verdict", test="vcxo_pull", ok=span >= 1.0e6, points=pts, slope_hz_per_v=slope,
                    plan_hz_per_v=KVCXO_HZ_V, span_hz=span, f_at_v_mid=a + slope * V_MID)


def _ref_hz(b, ch=1):
    """REF OUT's frequency from one scope record: 100 us at 2 GSa/s (2500 periods), the rising edges' times
    interpolated at mid-swing and fitted to a line.  Repeats to about 1 Hz at 25 MHz (0.04 ppm) on the
    SDS2104X Plus, against the scope's own timebase; its counter reads only 3 digits over SCPI.  Returns
    (hz, edges, rms edge residual in s)."""
    import numpy as np
    s = b.scope
    s.single()
    t, v, _ = s.waveform(ch)
    t, v = np.asarray(t), np.asarray(v)
    th = 0.5 * (np.percentile(v, 95) + np.percentile(v, 5))
    i = np.nonzero((v[:-1] < th) & (v[1:] >= th))[0]
    tc = t[i] + (th - v[i]) / (v[i + 1] - v[i]) * (t[i + 1] - t[i])
    k = np.round((tc - tc[0]) / np.median(np.diff(tc)))         # cycle numbers, robust to a missed edge
    p = np.polyfit(k, tc, 1)
    return float(1 / p[0]), len(tc), float(np.std(tc - np.polyval(p, k)))


def loop_center(b, target_v=V_MID, tol_v=0.04, max_steps=10):
    """Bring the loop integrator (U112A) back to mid-scale, so VC = target_v with VC_OFF at V_MID, with no carrier.
    Held (LOOP_HOLD high) its input is V_MID against V_MID and it keeps its state, but it walks on its own ~30 pA
    of offset and leakage: from mid to its 3.28 V rail in about 1.5 h on board A (VC = 3 V_MID - U112A - VC_OFF,
    stuck near 0 V).  Here I_OFF_F pushes I to one side of the comparator, so ERR = sign(I) x Q sits ~20 mV to the
    side of V_MID that moves VC the right way (I_OFF_F 3.0 V: ERR +19 mV, VC rises at ~19 V/s; 0.3 V: -25 mV), and
    the sequencer releases the hold for a counted time; repeated with the rate it measured until VC is within tol_v.
    I_OFF_F goes back to V_MID and the hold stays high.  Nothing cabled."""
    cl = b.cl
    b.board_call("ctrl", loop_hold=1, tx_dis=1)
    cl.dac(DAC1, VC_OFF=V_MID)
    steps = []
    rate = {}                                                  # V/s of VC per direction, as measured
    try:
        for _ in range(max_steps):
            time.sleep(0.05)
            vc = cl.adc("VC")
            if abs(vc - target_v) <= tol_v:
                break
            up = vc < target_v
            cl.dac(DAC2, I_OFF_F=3.0 if up else 0.3)
            time.sleep(0.05)
            err = cl.adc("ERR")
            r = rate.get(up, abs(err - V_MID) / 1e-3)          # R126 10 k x C130 100 nF = 1 ms
            # a rail-stuck integrator needs the far side of mid first: aim at the target, at most 0.5 s
            dt = min(0.5, max(1e-4, abs(target_v - vc) / max(r, 1.0)))
            cl.seq_program([(dt / cl.t_clk, {"loop_hold": 0})])
            cl.seq_run()
            time.sleep(dt + 0.02)
            cl.dac(DAC2, I_OFF_F=V_MID)
            time.sleep(0.05)
            vc2 = cl.adc("VC")
            if abs(vc2 - vc) > 0.02 and 0.02 < abs(vc2 - target_v) and (vc2 - vc) * (target_v - vc) > 0:
                rate[up] = abs(vc2 - vc) / dt
            steps.append({"vc": vc, "err": err, "up": up, "open_s": dt, "vc_after": vc2, "rate_v_s": rate.get(up)})
            print(steps[-1], flush=True)
    finally:
        cl.dac(DAC2, I_OFF_F=V_MID)
        b.board_call("ctrl", loop_hold=1)
    vc = cl.adc("VC")
    return b.record("verdict", test="loop_center", ok=abs(vc - target_v) <= tol_v, vc=vc, target_v=target_v, steps=steps)


def stage2_vcxo_ref(b, volts=(0.3, 0.6, 0.9, 1.2, 1.5, 1.65, 1.8, 2.1, 2.4, 2.7, 3.0), ch=1):
    """2.2's pull, measured at the VCXO itself: the loop held (LOOP_HOLD high: VC follows VC_OFF, inverted), VC_OFF
    stepped, REF OUT's frequency on the scope (`_ref_hz`) and VC on the ADC; the RX LO is 232 x REF OUT.  Pass
    (BRINGUP 2): the RX LO reaches 500 kHz or more each side of 5.8 GHz (86 ppm; the datasheet's +-100 ppm over
    0.3-3.0 V on VC, centred at 1.65 V, includes its tolerance).  Run loop_center first: a held integrator walks to a
    rail and takes VC's range with it.  Cabled: REF OUT (J108) to scope channel `ch`.  Needs no analyser."""
    b.stage = b.stage or "2.2"
    s = b.scope
    s.timebase(scale=10e-6)
    s.trigger(source=ch, level=1.65, slope="rising", mode="auto")
    b.board_call("ctrl", loop_hold=1)
    pts = []
    try:
        for v in volts:
            b.cl.dac(DAC1, VC_OFF=v)
            time.sleep(0.3)
            vc = b.cl.adc("VC")
            hz, n, res = _ref_hz(b, ch)
            pts.append({"vc_off": v, "vc_adc": vc, "hz": hz, "ppm": (hz - F_REF) / F_REF * 1e6, "edges": n, "edge_rms_s": res})
            print({k: round(x, 4) if isinstance(x, float) else x for k, x in pts[-1].items()}, flush=True)
    finally:
        b.cl.dac(DAC1, VC_OFF=V_MID)
        s.run()
    a, slope = _fit_line([p["vc_adc"] for p in pts], [p["hz"] for p in pts])
    f_mid = a + slope * V_MID
    span = max(p["hz"] for p in pts) - min(p["hz"] for p in pts)
    ppm = lambda hz: (hz - F_REF) / F_REF * 1e6                                    # noqa: E731
    lo_ppm, hi_ppm = min(ppm(p["hz"]) for p in pts), max(ppm(p["hz"]) for p in pts)
    reach_khz = [lo_ppm * F_LO * 1e-9, hi_ppm * F_LO * 1e-9]                   # the RX LO's reach from 5.8 GHz
    ok = reach_khz[0] <= -500 and reach_khz[1] >= 500                          # BRINGUP 2's pass: +-500 kHz or more
    return b.record("verdict", test="vcxo_pull_ref_out", ok=ok, points=pts, slope_hz_per_v=slope,
                    slope_ppm_per_v=slope / F_REF * 1e6, plan_ppm_per_v=KVCXO_HZ_V / F_LO * 1e6, span_ppm=span / F_REF * 1e6,
                    ppm_range=[lo_ppm, hi_ppm], rx_lo_reach_khz=reach_khz, ppm_at_vc_1v65=ppm(f_mid),
                    rx_lo_hz_at_vc_1v65=232 * f_mid,
                    text="against the scope's timebase; the RX LO's leak on LO TX MON (the analyser) agreed within 1 ppm at VC_OFF 1.65")


def _tx_off(b):
    b.board_call("ctrl", tx_dis=1)
    b.board_call("safe")


def stage2_tx(b):
    """2.3: TX MON (J201, U.FL, -20 dB coupler) on the analyser; TX ANT into a 50 ohm termination (or 20 dB or more of pad):
    the transmitter on with the ladders held at each point: (1, 0) the idle, the three other axis points, (0, 0) the
    OOK null, then TX_DIS high.  Pass: -10 dBm +-3 at TX MON; the axis points within 1 dB of each other; (0, 0) 15-20 dB
    down before the null is trimmed (stage2.null); TX_DIS mutes it."""
    b.stage = b.stage or "2.3"
    b.board_call("safe")
    rows = {}
    try:
        b.board_call("hold_point", 1, 0)
        b.board_call("ctrl", tx_dis=0)
        time.sleep(0.1)
        f0 = b.sa_peak(F_LO, 20e6, ref=0.0, label="TX MON coarse")["hz"]
        b.sa_setup(f0, 100e3, rbw=1e3, ref=0.0)
        for pt in ((1, 0), (-1, 0), (0, 1), (0, -1), (0, 0)):
            b.board_call("hold_point", *pt)
            time.sleep(0.05)
            b.sa.single()
            rows[str(pt)] = b.sa.peak()[1]
        b.board_call("hold_point", 1, 0)
        b.board_call("ctrl", tx_dis=1)
        time.sleep(0.05)
        b.sa.single()
        rows["tx_dis"] = b.sa.peak()[1]
    finally:
        _tx_off(b)
    axis = [rows[k] for k in ("(1, 0)", "(-1, 0)", "(0, 1)", "(0, -1)")]
    checks = {"level": abs(rows["(1, 0)"] - TX_MON_DBM) <= 3, "axis_flat_1db": max(axis) - min(axis) <= 1.0,
              "ook_null_15db": rows["(1, 0)"] - rows["(0, 0)"] >= 15, "tx_dis_mutes_30db": rows["(1, 0)"] - rows["tx_dis"] >= 30}
    return b.record("verdict", test="tx_levels", ok=all(checks.values()), checks=checks, hz=f0, dbm=rows,
                    at_tx_ant_dbm=rows["(1, 0)"] + 20, text="TX ANT = TX MON + 20 dB (the coupler's nominal: calibrate it once)")


def stage2_null(b, step_v=0.008, min_step_v=0.0008, max_iter=40):
    """2.3's null: the ladders at (0, 0), VR_I and VR_Q (DAC1 A, B) moved by coordinate descent for the least carrier at
    TX MON.  Pass: the null lands within a few mV of the printed Vr (VR_I_V, VR_Q_V: the divider carries the ADL5375's
    own 2 x 41 uA since build 18).  Same cabling as stage2.tx; writes the found values as the runtime DAC values."""
    b.stage = b.stage or "2.3"
    b.board_call("safe")
    path = []
    try:
        b.board_call("hold_point", 1, 0)
        b.board_call("ctrl", tx_dis=0)
        time.sleep(0.1)
        f0 = b.sa_peak(F_LO, 20e6, ref=0.0, label="TX MON coarse")["hz"]
        b.sa_setup(f0, 50e3, rbw=1e3, ref=0.0)
        b.sa.single()
        full = b.sa.peak()[1]
        b.board_call("hold_point", 0, 0)

        def level(vi, vq):
            b.cl.dac(DAC1, VR_I=vi, VR_Q=vq)
            time.sleep(0.03)
            b.sa.single()
            d = b.sa.peak()[1]
            path.append((round(vi, 5), round(vq, 5), d))
            return 10 ** (d / 10)

        v = [VR_I_V, VR_Q_V]
        best = level(*v)
        step = step_v
        it = 0
        while step >= min_step_v and it < max_iter:
            moved = False
            for ax in (0, 1):
                for sgn in (+1, -1):
                    trial = list(v)
                    trial[ax] += sgn * step
                    p = level(*trial)
                    if p < best:
                        best, v, moved = p, trial, True
                        break
                it += 1
            if not moved:
                step /= 2
        null_dbm = 10 * math.log10(best)
    finally:
        _tx_off(b)
    return b.record("verdict", test="carrier_null", ok=abs(v[0] - VR_I_V) < 0.010 and abs(v[1] - VR_Q_V) < 0.010,
                    vr_i=v[0], vr_q=v[1], printed=[VR_I_V, VR_Q_V], full_dbm=full, null_dbm=null_dbm,
                    suppression_db=full - null_dbm, path=path,
                    text="the DACs keep these until the next write; the EEPROM still holds the printed values")


def stage2_ref_in(b, vpp=1.0, ch=1):
    """2.4: the generator's 25 MHz sine, vpp open-circuit (REF IN is high impedance: R214's 49.9 ohm is DNP), into REF
    IN (J203) with JP201 moved to REF IN by hand first; the TX synthesizer must lock to it, and its LO moves by the
    generator's offset from the TCXO (x 232).  The generator's output goes off after."""
    b.stage = b.stage or "2.4"
    g = b.gen
    g.output(ch, False, load="HZ")
    g.sine(ch, freq=F_REF, vpp=vpp)
    g.output(ch, True)
    try:
        time.sleep(0.2)
        b.board_call("lo_mon", 0, True)
        b.board_call("pll_tune", 0, F_LO / 1e6)              # the VCO autoselect again, on the new reference
        time.sleep(RELOCK_S)
        lock = b.board_call("pll_locked")
        f0, _ = b.sa_peak(F_LO, 4e6, rbw=10e3, record=False)
        pk = b.sa_peak(f0, 40e3, rbw=300, label="LO TX MON on REF IN")
    finally:
        g.output(ch, False)
    return b.record("verdict", test="ref_in", ok=bool(lock["tx"]), lock=lock, hz=pk["hz"], dbm=pk["dbm"],
                    gen={"ch": ch, "hz": F_REF, "vpp_open": vpp}, text="move JP201 back to TCXO after")


def stage2_ref_out(b, ch=1):
    """2.2's REF OUT (J108, MMCX -> the scope, 50 ohm input): 25 MHz, about 1.7 V p-p into 50 ohm (33 ohm + the
    LVC's own); 3.3 V into 1 M."""
    b.stage = b.stage or "2.2"
    s = b.scope
    s.channel(ch, on=True, scale=0.5, offset=-0.85, coupling="DC", impedance="50")
    s.timebase(scale=20e-9)
    s.trigger(source=ch, level=0.85, slope="rising", mode="auto")
    time.sleep(0.5)
    m = {k: s.measure(k, ch) for k in ("FREQ", "PKPK", "RISE", "FALL", "DUTY")}
    ok = m["FREQ"] is not None and abs(m["FREQ"] - F_REF) < 2e3 and m["PKPK"] is not None and m["PKPK"] > 1.2
    return b.record("verdict", test="ref_out", ok=ok, scope=m)


PROCS = {
    "smoke": smoke, "stage1.ramp": ramp, "stage1.rails": rails_walk, "watch": watch, "stage1.heat": heat_log, "stage1.i2c": stage1_i2c,
    "stage2.pll": stage2_pll, "stage2.lo": stage2_lo, "stage2.vcxo": stage2_vcxo, "stage2.tx": stage2_tx,
    "stage2.null": stage2_null, "stage2.ref_in": stage2_ref_in, "stage2.ref_out": stage2_ref_out,
    "stage2.vcxo_ref": stage2_vcxo_ref, "loop_center": loop_center,
}


def run(b, name, **kw):
    if name not in PROCS:
        raise SystemExit("no procedure %r: %s" % (name, ", ".join(PROCS)))
    return PROCS[name](b, **kw)


if __name__ == "__main__":
    for k, fn in PROCS.items():
        print("%-14s %s" % (k, (fn.__doc__ or "").strip().split("\n")[0]))
