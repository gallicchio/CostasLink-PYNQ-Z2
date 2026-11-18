#!/usr/bin/env python3
"""The board's RF paths as laid out, against the vendor circuits placed at the pins, against the bench.

    python3 sim/aslaid/paths.py [rx|tx|lo|all]
"""
import json, math, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import circuit as C
import devices as D
import extract as X
import xsec

FREQS = np.arange(3.0e9, 7.0001e9, 0.02e9)
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)

LAUNCH_C, LAUNCH_L = 0.49e-12, 0.19e-9          # docs/LAUNCH.md, build 38's SMA launch (SWEEP mesh fit)
CHOKES = ("L103", "L104", "L201")                # the ADL5611 table already has its own 43 nH choke


def pad_of(ref, net):
    for p in X.board()["pad"]:
        if p["ref"] == ref and p["net"] == net:
            return "%s.%s" % (ref, p["num"])
    raise KeyError((ref, net))


_PAIR = None


def coupler_modes():
    global _PAIR
    if _PAIR is None:
        path = os.path.join(HERE, "coupler_modes.json")
        if os.path.exists(path):
            _PAIR = json.load(open(path))
        else:
            ze, zo, ee, eo = xsec.pair(0.29, 0.25, 0.25)
            _PAIR = dict(ze=ze, zo=zo, ee=ee, eo=eo)
            json.dump(_PAIR, open(path, "w"))
    return _PAIR


def add_coupler(c, pad, cp, length=7.3):
    m = coupler_modes()
    C.add_coupled(c, pad["%s.1" % cp], pad["%s.2" % cp], pad["%s.3" % cp], pad["%s.4" % cp],
                  m["ze"], m["zo"], m["ee"], m["eo"], length)


def add_launch(c, name, node):
    src = "SRC:" + name
    c.port(name, src)
    c.z2(src, node, C.z_l(LAUNCH_L))
    c.y2(node, "0", C.y_c(LAUNCH_C))


def plane_node(c, net, x, y, ref):
    """a supply pad: its via down to the plane (1.0 nH) and the plane as a good AC ground for the through
    path (the plane's own resonances are pdn.py's)"""
    n = "S:%s" % ref
    c.z2(n, "0", C.z_l(1.0e-9, 0.2))
    return n


# ---- the receive chain ----
RX_NETS = ["Net-(J101-In)", "Net-(U101-RF_IN)", "Net-(U101-RF_OUT)", "Net-(U102-RF1)", "Net-(U102-RF2)",
           "Net-(U103-RFIN)", "Net-(U103-RFOUT)", "Net-(U117-RFIN)", "Net-(U117-RFOUT)", "Net-(CP101-IN)",
           "Net-(CP101-OUT)", "Net-(CP101-CPL)", "Net-(CP101-ISO)", "Net-(T101-BAL1)", "Net-(T101-BAL2)",
           "Net-(U104-RFIP)", "Net-(U104-RFIN)"]


def rx_ics(c, pad, dsa_db=0.0, lna=True):
    pin = lambda ref, net: pad[pad_of(ref, net)]
    if lna:
        c.block((pin("U101", "Net-(U101-RF_IN)"), pin("U101", "Net-(U101-RF_OUT)")), D.sky65404_y)
    c.block((pin("U102", "Net-(U102-RF1)"), pin("U102", "Net-(U102-RF2)")), lambda f: D.pe43711_y(f, dsa_db))
    c.block((pin("U103", "Net-(U103-RFIN)"), pin("U103", "Net-(U103-RFOUT)")), D.adl5611_y)
    c.block((pin("U117", "Net-(U117-RFIN)"), pin("U117", "Net-(U117-RFOUT)")), D.adl5611_y)
    c.block((pin("T101", "Net-(CP101-OUT)"), pin("T101", "Net-(T101-BAL1)"), pin("T101", "Net-(T101-BAL2)")), D.balun_y)
    a, b = pin("U104", "Net-(U104-RFIP)"), pin("U104", "Net-(U104-RFIN)")
    c.z2(a, b, lambda f: D.ADL5380_RDIFF + 0j)
    c.y2(a, "0", C.y_c(D.ADL5380_CPIN))
    c.y2(b, "0", C.y_c(D.ADL5380_CPIN))
    return a, b


def rx_aslaid(dsa_db=0.0, skip=(), ideal=(), no_padcap=False):
    c = C.Circuit("RX as laid")
    info = X.extract(c, RX_NETS, skip_parts=CHOKES + tuple(skip), supply_node=lambda n, x, y, r: plane_node(c, n, x, y, r),
                     ideal=ideal, no_padcap=no_padcap)
    pad = info["pad"]
    add_launch(c, "RXANT", pad["J101.1"])
    c.port("RXMON", pad["J102.1"])
    add_coupler(c, pad, "CP101")
    dem = rx_ics(c, pad, dsa_db)
    return c, info, dem


def rx_reference(dsa_db=0.0):
    """the vendors' circuits at the pins: no lines, every ground a via in the pad"""
    c = C.Circuit("RX reference")
    n = {k: k for k in ("J", "IN", "OUT", "R1", "R2", "A1", "A2", "B1", "B2", "CI", "CO", "CPL", "ISO", "T1", "T2", "D1", "D2")}
    add_launch(c, "RXANT", "J")
    c.z2("J", "0", D.part_z("L101", "6.8nH", "0402")[0])
    c.z2("J", "IN", D.part_z("C101", "1.5pF", "0402")[0])
    c.z2("IN", "0", lambda f: D.part_z("C102", "0.5pF", "0402")[0](f) + 1j * 2 * math.pi * f * 0.1e-9)
    c.block(("IN", "OUT"), D.sky65404_y)
    c.z2("OUT", "R1", D.part_z("C104", "1.5pF", "0402")[0])
    c.block(("R1", "R2"), lambda f: D.pe43711_y(f, dsa_db))
    c.z2("R2", "A1", D.part_z("C106", "1.5pF", "0402")[0])
    c.block(("A1", "A2"), D.adl5611_y)
    c.z2("A2", "B1", D.part_z("C110", "1.5pF", "0402")[0])
    c.block(("B1", "B2"), D.adl5611_y)
    c.z2("B2", "CI", D.part_z("C114", "1.5pF", "0402")[0])
    m = coupler_modes()
    C.add_coupled(c, "CI", "CO", "CPL", "ISO", m["ze"], m["zo"], m["ee"], m["eo"], 7.3)
    c.port("RXMON", "CPL")
    c.z2("ISO", "0", D.part_z("R103", "49.9R", "0402")[0])
    c.block(("CO", "T1", "T2"), D.balun_y)
    c.z2("T1", "D1", D.part_z("C159", "1.5pF", "0402")[0])
    c.z2("T2", "D2", D.part_z("C160", "1.5pF", "0402")[0])
    c.z2("D1", "D2", lambda f: D.ADL5380_RDIFF + 0j)
    c.y2("D1", "0", C.y_c(D.ADL5380_CPIN))
    c.y2("D2", "0", C.y_c(D.ADL5380_CPIN))
    return c, ("D1", "D2")


def measured_rx(path=None):
    """the receive chain from the night's maps: RX MON + DSA - RX ANT's level (TX ANT less the 39.7 dB of pads),
    the lowest DSA setting at each frequency; above 5.85 GHz the leak is larger than the chain"""
    out = {}
    for fn in ("map_20261029_163008.json", "mapfine_20261029_173239.json"):
        rows = json.load(open(os.path.join(ROOT, "bringup", "data", "board_A", "overnight", fn)))
        for r in rows:
            p = min(r["points"], key=lambda q: q["dsa"])
            out[r["mhz"]] = p["rx_mon"] + p["dsa"] - (r["tx_ant_dbm"] - 39.7)
    return out


C102_FIT = 0.45e-9          # C102's ground beyond the extracted 0.14 nH (with its 0.3 nH ESL) that fits the bench


def rx_curves(c, dem):
    g_mon, g_dem, s11 = [], [], []
    for fr in FREQS:
        V = c.drive_port(fr, "RXANT")
        g_mon.append(20 * math.log10(abs(V[c.ports["RXMON"][0]])))
        a, b = dem
        g_dem.append(10 * math.log10(abs(V[a] - V[b]) ** 2 / (2 * D.ADL5380_RDIFF) / (4.0 / (8 * 50))))
        s11.append(20 * math.log10(abs(V[c.ports["RXANT"][0]] - 1.0) + 1e-12))
    return dict(rxmon=g_mon, demod=g_dem, s11=s11)


def run_rx():
    res = {"f": list(FREQS / 1e9)}
    X.EXTRA_GND = {}
    ca, info, dem = rx_aslaid()
    res["aslaid"] = rx_curves(ca, dem)
    X.EXTRA_GND = {"C102": C102_FIT}
    c, _, d = rx_aslaid(); res["aslaid_fit"] = rx_curves(c, d)
    c, _, d = rx_aslaid(skip=("C102",)); res["c102_lifted"] = rx_curves(c, d)
    c, _, d = rx_aslaid(skip=("C102",), no_padcap=True); res["lifted_nopadcap"] = rx_curves(c, d)
    c, _, d = rx_aslaid(no_padcap=True); res["fit_nopadcap"] = rx_curves(c, d)
    X.EXTRA_GND = {}
    cr, demr = rx_reference()
    res["reference"] = rx_curves(cr, demr)
    meas = measured_rx()
    res["measured"] = {"f": [k / 1000 for k in sorted(meas)], "rxmon": [meas[k] for k in sorted(meas)]}
    res["lines"], res["parts"], res["notes"] = info["lines"], info["parts"], ca.notes
    json.dump(res, open(os.path.join(OUT, "rx.json"), "w"))
    for fr in (3.5, 4.5, 5.0, 5.5, 5.8, 6.0):
        k = int(round((fr - 3.0) / 0.02))
        mk = min(meas, key=lambda m: abs(m / 1000 - fr))
        print("%.1f GHz RX ANT->RX MON: measured %6.1f | as laid %6.1f, fitted %6.1f, C102 lifted %6.1f, lifted + no pad C %6.1f, reference %6.1f | S11 as laid %5.1f, lifted %5.1f"
              % (fr, meas[mk], res["aslaid"]["rxmon"][k], res["aslaid_fit"]["rxmon"][k], res["c102_lifted"]["rxmon"][k],
                 res["lifted_nopadcap"]["rxmon"][k], res["reference"]["rxmon"][k], res["aslaid_fit"]["s11"][k], res["c102_lifted"]["s11"][k]))
    return res




# ---- the transmit chain ----
TX_NETS = ["Net-(U201-RFOUT)", "Net-(U202-RFIN)", "Net-(U202-RFOUT)", "Net-(C213-Pad2)", "Net-(CP201-IN)",
           "Net-(CP201-OUT)", "Net-(CP201-CPL)", "Net-(CP201-ISO)"]


def add_norton(c, name, node, zout):
    """a source of 1 V open-circuit behind zout(f), as a current into node and zout to ground"""
    c.source(name, node, lambda f: 1.0 / zout(f))
    c.z2(node, "0", zout)


def tx_aslaid(ideal=(), no_padcap=False):
    c = C.Circuit("TX as laid")
    info = X.extract(c, TX_NETS, skip_parts=CHOKES, supply_node=lambda n, x, y, r: plane_node(c, n, x, y, r),
                     ideal=ideal, no_padcap=no_padcap)
    pad = info["pad"]
    add_launch(c, "TXANT", pad["J202.1"])
    c.port("TXMON", pad["J201.1"])
    add_coupler(c, pad, "CP201")
    c.block((pad[pad_of("U202", "Net-(U202-RFIN)")], pad[pad_of("U202", "Net-(U202-RFOUT)")]), D.adl5611_y)
    src = pad[pad_of("U201", "Net-(U201-RFOUT)")]
    add_norton(c, "MOD", src, D.adl5375_zout)
    return c, info, src


def tx_reference():
    c = C.Circuit("TX reference")
    add_norton(c, "MOD", "M", D.adl5375_zout)
    c.z2("M", "A", D.part_z("C209", "1.5pF", "0402")[0])
    c.block(("A", "B"), D.adl5611_y)
    c.z2("B", "CI", D.part_z("C213", "1.5pF", "0402")[0])
    m = coupler_modes()
    C.add_coupled(c, "CI", "CO", "CPL", "ISO", m["ze"], m["zo"], m["ee"], m["eo"], 7.3)
    c.port("TXMON", "CPL")
    c.z2("ISO", "0", D.part_z("R213", "49.9R", "0402")[0])
    c.z2("CO", "0", D.part_z("L202", "6.8nH", "0402")[0])
    add_launch(c, "TXANT", "CO")
    return c, "M"


def tx_power(c, f):
    """P(TX ANT) and P(TX MON) in dB relative to the modulator's available power; and P_av of 1 V behind zout"""
    node, If = c.srcs["MOD"]
    V = c.solve(f, {node: If(f)})
    zs = D.adl5375_zout(f)
    p_av = 1.0 / (8 * zs.real)
    out = []
    for p in ("TXANT", "TXMON"):
        n, z0 = c.ports[p]
        out.append(10 * math.log10(abs(V[n]) ** 2 / (2 * z0) / p_av))
    return out


def measured_tx():
    out = {}
    for fn in ("map_20261029_163008.json", "mapfine_20261029_173239.json"):
        for r in json.load(open(os.path.join(ROOT, "bringup", "data", "board_A", "overnight", fn))):
            out[r["mhz"]] = r["tx_ant_dbm"]
    return out


def run_tx():
    ca, info, src = tx_aslaid()
    cr, _ = tx_reference()
    cn, _, _ = tx_aslaid(no_padcap=True)
    res = {"f": list(FREQS / 1e9)}
    for name, cc in (("aslaid", ca), ("reference", cr), ("no_padcap", cn)):
        ant, mon = zip(*[tx_power(cc, f) for f in FREQS])
        res[name] = dict(ant=list(ant), mon=list(mon))
    # the modulator's own output against frequency (1 V p-p baseband, into 50 ohm), and the available power
    pmod = [D.adl5375_pout_dbm(f) - 10 * math.log10(1 - abs((D.adl5375_zout(f) - 50) / (D.adl5375_zout(f) + 50)) ** 2) for f in FREQS]
    res["pmod_av"] = pmod
    meas = measured_tx()
    res["measured"] = {"f": [k / 1000 for k in sorted(meas)], "ant": [meas[k] for k in sorted(meas)]}
    res["parts"] = info["parts"]
    res["lines"] = info["lines"]
    # one offset (the board's baseband drive against the datasheet's 1 V p-p) fitted at 3.5 GHz
    k35 = int(round((3.5 - 3.0) / 0.02))
    off = meas[3500] - (pmod[k35] + res["aslaid"]["ant"][k35])
    res["offset_db"] = off
    json.dump(res, open(os.path.join(OUT, "tx.json"), "w"))
    print("offset (drive against 1 V p-p) %.1f dB" % off)
    for fr in (3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 5.8, 6.0):
        k = int(round((fr - 3.0) / 0.02))
        mk = min(meas, key=lambda m: abs(m / 1000 - fr))
        print("%.1f GHz: TX ANT model %5.1f dBm (ref %5.1f, no pad C %5.1f), measured %5.1f | TX ANT - TX MON model %5.1f dB"
              % (fr, pmod[k] + res["aslaid"]["ant"][k] + off, pmod[k] + res["reference"]["ant"][k] + off,
                 pmod[k] + res["no_padcap"]["ant"][k] + off, meas[mk], res["aslaid"]["ant"][k] - res["aslaid"]["mon"][k]))
    return res


# ---- the synthesizers' outputs: LO MON taps, and the LO into the demodulator and the modulator ----
def max2871_current(pwr_dbm, f_cal=3.0e9):
    """the output current that puts pwr_dbm into 50 ohm with the datasheet's network at the pin (27 nH to an
    AC ground, 50 ohm through an ideal block, Note 4), at 3 GHz; flat against frequency (an assumption)"""
    zl = D.part_z("L", "27nH", "0402")[0](f_cal)
    y = 1 / 50.0 + 1 / zl + 1j * 2 * math.pi * f_cal * D.MAX2871_COUT
    v = math.sqrt(2 * 50 * 1e-3 * 10 ** (pwr_dbm / 10))
    return v * abs(y)


def lo_circuit(nets, pins, loads, name):
    """nets of one synthesizer output pair; pins: (P pin, N pin) pads; loads: list of (pad, R to ground) and
    ports.  Pull-ups to their supply as plane_node (an AC ground through a via)."""
    c = C.Circuit(name)
    info = X.extract(c, nets, supply_node=lambda n, x, y, r: plane_node(c, n, x, y, r))
    pad = info["pad"]
    for pn in pins:
        c.y2(pad[pn], "0", C.y_c(D.MAX2871_COUT))
    return c, info, pad


def run_lo():
    res = {}
    f = FREQS
    # LO TX MON: U203 RFOUTB_P -> C231 -> 115.6 mm -> J204; RFOUTB_N -> C232 -> R220 49.9
    for tag, nets, pinp, pinn, mon in (
            ("lo_tx_mon", ["Net-(U203-RFOUTB_P)", "Net-(U203-RFOUTB_N)", "Net-(J204-In)", "Net-(C232-Pad2)"], "U203.14", "U203.15", "J204.1"),
            ("lo_rx_mon", ["Net-(U115-RFOUTB_P)", "Net-(U115-RFOUTB_N)", "Net-(J109-In)", "Net-(C152-Pad2)"], "U115.14", "U115.15", "J109.1")):
        c, info, pad = lo_circuit(nets, (pinp, pinn), (), tag)
        c.port("MON", pad[mon])
        i0 = max2871_current(-1.0)
        p = []
        for fr in f:
            V = c.solve(fr, {pad[pinp]: i0, pad[pinn]: -i0})
            p.append(10 * math.log10(abs(V[pad[mon]]) ** 2 / 100 / 1e-3))
        res[tag] = dict(p_dbm=p, parts=info["parts"], lines=info["lines"], notes=c.notes)
        # the datasheet's own network for comparison: 27 nH at the pin, 50 ohm load at the pin
        ref = []
        for fr in f:
            zl = D.part_z("L", "27nH", "0402")[0](fr)
            y = 1 / 50.0 + 1 / zl + 1j * 2 * math.pi * fr * D.MAX2871_COUT
            ref.append(10 * math.log10((i0 / abs(y)) ** 2 / 100 / 1e-3))
        res[tag]["ref_dbm"] = ref
    # the LO into the mixers: RFOUTA_P/N (APWR 1: -1 dBm a side) -> blocks -> lines -> blocks -> the LO pins
    for tag, nets, pp, pn, lp, ln, rload in (
            ("lo_rx_demod", ["Net-(U115-RFOUTA_P)", "Net-(U115-RFOUTA_N)", "/Receiver and Costas loop/LO_RX_P",
                             "/Receiver and Costas loop/LO_RX_N", "Net-(U104-LOIN)", "Net-(U104-LOIP)"],
             "U115.12", "U115.13", "U104.10", "U104.9", "diff50"),
            ("lo_tx_mod", ["Net-(U203-RFOUTA_P)", "Net-(U203-RFOUTA_N)", "/Transmitter and triggers/LO_TX_P",
                           "/Transmitter and triggers/LO_TX_N", "Net-(U201-LOIN)", "Net-(U201-LOIP)"],
             "U203.12", "U203.13", "U201.4", "U201.3", "se50")):
        c, info, pad = lo_circuit(nets, (pp, pn), (), tag)
        a, b = pad[lp], pad[ln]
        if rload == "diff50":
            c.z2(a, b, lambda fr: 50.0 + 0j)
            c.y2(a, "0", C.y_c(0.25e-12)); c.y2(b, "0", C.y_c(0.25e-12))
        else:
            c.z2(a, "0", lambda fr: 50.0 + 0j); c.z2(b, "0", lambda fr: 50.0 + 0j)
        i0 = max2871_current(-1.0)
        p = []
        for fr in f:
            V = c.solve(fr, {pad[pp]: i0, pad[pn]: -i0})
            if rload == "diff50":
                p.append(10 * math.log10(abs(V[a] - V[b]) ** 2 / 100 / 1e-3))
            else:
                p.append(10 * math.log10((abs(V[a]) ** 2 + abs(V[b]) ** 2) / 100 / 1e-3))
        res[tag] = dict(p_dbm=p, parts=info["parts"], lines=info["lines"])
    json.dump(res, open(os.path.join(OUT, "lo.json"), "w"))
    meas = {"lo_tx_mon": {3.0: -3.4, 3.5: -2.8, 4.0: -13.7, 5.0: -16.7, 5.7: -21.0, 5.8: -26.7, 6.0: -25.4},
            "lo_rx_mon": {5.8: -8.7}}
    for tag in ("lo_tx_mon", "lo_rx_mon", "lo_rx_demod", "lo_tx_mod"):
        row = []
        for fr in (3.0, 3.5, 4.0, 5.0, 5.7, 5.8, 6.0):
            k = int(round((fr - 3.0) / 0.02))
            m = meas.get(tag, {}).get(fr)
            row.append("%.1f: %5.1f%s" % (fr, res[tag]["p_dbm"][k], "" if m is None else " (meas %5.1f)" % m))
        print(tag, " | ".join(row))
    return res

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    if which in ("rx", "all"):
        run_rx()
    if which in ("tx", "all"):
        run_tx()
    if which in ("lo", "all"):
        run_lo()
