#!/usr/bin/env python3
"""The numbers the hand-written documents quote, checked against what the build computed (CLAUDE_PCB.md
section 2, "one place for every parameter": a document may quote a number, but a step checks it).

    python3 tools/doc_check.py          exit 1 on a stale number, or on a claim that matches nowhere

A claim is a regular expression whose groups are numbers as a document writes them, the documents it is
looked for in, and the text each group must read now, formatted from build/*.json, the netlist and the
release.  Every match must read the current value, and every claim must match at least once: rewording a
sentence drops its check only with an edit here.  History is not checked: CLAUDE_CODE_CHAT.md,
DESIGN_REVIEW_*.md, the design_review_*/ rounds, REVA_CHANGES.md's past rows; a past number in a checked
document says it is past ("build 17 had ...") so that no claim's pattern takes it for the present.
Also checked: the register table in gateware/README.md is regmap.py --md's, and PLAN.md section 15's two range
tables are build/link_rates.md's, verbatim.  Run by build.py's last step, `docs`.
"""
import json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(ROOT, "gen")]


def J(name):
    return json.load(open(os.path.join(ROOT, "build", name)))


B = J("budget.json")
P = B["parts"]
COST = J("cost.json")
import net_check                                   # noqa: E402
import board_info as BI                            # noqa: E402
COMPS, NETS = net_check.read(BI.NETLIST)

I_A = B["I_total_mA"] / 1e3
RAILS = B["rails_mA"]
F = {
    "I_A": "%.2f" % I_A,
    "P_W": "%.1f" % (I_A * 5.0),
    "rest_mA": "%.0f" % (B["I_total_mA"] - P["dem_I_mA"] - P["mod_I_mA"] - 3 * P["gb_I_mA"] - 2 * P["pll_I_mA"]),
    "parts": "%d" % len(COMPS),
    "nets": "%d" % len(NETS),
    "bom_lines": "%d" % COST["lines"],
    "ext": "%d" % COST["ext"],
    "jlc": "%.0f-%.0f" % tuple(COST["jlc"]),
}

DOCS = ["PLAN.md", "BRINGUP.md", "README.md", "docs/SYSTEM.md", "docs/HOSTS.md", "docs/TRAJECTORIES.md", "gateware/README.md"]

import parts as PARTS_MOD                          # noqa: E402
DK = {}                                            # Digi-Key number -> (stock, price) as gen/parts.py saw them
for _k, _p in {**PARTS_MOD.consigned(), **PARTS_MOD.fallback()}.items():
    _m = re.match(r"Digi-Key ([\d,]+) at \$([\d.]+)", _p["consign"]["seen"])
    DK[_p["consign"]["digikey"]] = [_m.group(1), _m.group(2)] if _m else ["?", "?"]

CONS = J("constellations.json")
KNOBS = J("hosts_knobs.json")
ISO = {"%.0f" % r["df_MHz"]: "%.0f" % r["iso_dB"] for r in B["iso_table"]}
LR = open(os.path.join(ROOT, "build", "link_rates.md"), encoding="utf-8").read()


def quiet_bpsk(scenario, path):
    """The BPSK cell of build/link_rates.md's quiet table for a scenario (by its start), board alone, on a path."""
    t = LR[LR.index("**Range, quiet"):]
    for line in t.split("\n"):
        c = [x.strip() for x in line.split("|")]
        if len(c) > 5 and c[1].startswith(scenario) and c[2].startswith("board alone") and c[3] == path:
            return c[4]
    return "not in link_rates.md"


def m_or_km(m):
    return "%.0f m" % m if m < 999.5 else "%.1f km" % (m / 1e3)


def cons_row(m):
    r = CONS["range_m"][m.group(1)]
    return [m.group(1), "%.0f m" % r[0], m_or_km(r[1]), "%.1f km" % (r[2] / 1e3)]


def money_k(x):
    return "{:,}".format(int(round(x)))


EVERY = (COST["jlc"][0] + COST["digikey"] + COST["consign_ship"][0] + COST["other"][0],
         COST["jlc"][1] + COST["digikey"] + COST["consign_ship"][1] + COST["other"][1])
TWO = (COST["jlc"][0] + COST["digikey"] + COST["consign_ship"][0], COST["jlc"][1] + COST["digikey"] + COST["consign_ship"][1])
ROADMAP = {r["step"]: r["total"] for r in J("latency_roadmap.json") if isinstance(r, dict) and "step" in r}
L_LAT, L_TX, L_RX = B["latency_ns"], B["latency_tx_ns"], B["latency_rx_ns"]
ROWS = B["link_rows"]

# (what, regular expression, documents (None: all of DOCS), the values its groups must read: a list, or a
# function of the match giving one)
CLAIMS = [
    ("the electronics' latency (budget section 5)", r"\*\*(\d+\.\d) ns\*\* on the PYNQ-Z2 \(TX (\d+\.\d) \+ RX (\d+\.\d)\), \*\*(\d+\.\d) ns on the Icepi Zero\*\*",
     ["PLAN.md"], ["%.1f" % L_LAT, "%.1f" % L_TX, "%.1f" % L_RX, "%.1f" % B["latency_icepi_ns"]]),
    ("the latency in prose", r"(?:about |, )(\d+\.\d) ns of electronics", None, ["%.1f" % L_LAT]),
    ("the latency in prose", r"(\d+\.\d) ns is the quantity the whole project is about|the receive half of the (\d+\.\d) ns",
     ["BRINGUP.md"], lambda m: ["%.1f" % L_LAT if g else None for g in m.groups()]),
    ("the receive half", r"the edge comes \*\*(\d+) ns \+ the cable", ["BRINGUP.md"], ["%.0f" % L_RX]),
    ("jack to register", r"(\d+\.\d) ns from the jack to the FPGA register on the PYNQ, (\d+\.\d) ns on the Icepi", ["PLAN.md"],
     ["%.1f" % L_RX, "%.1f" % B["latency_icepi_rx_ns"]]),
    ("the link at 10 m (budget section 2)", r"RX −54 dBm, SNR (\d+) dB in 100 MHz \| Friis; NF (\d\.\d) dB; 30 m: SNR (\d+) dB", ["PLAN.md"],
     ["%.0f" % ROWS[1][4], "%.1f" % B["nf_chain_dB"], "%.0f" % ROWS[2][4]]),
    ("the noise floors and quiet levels", r"100 MHz: noise floor (-\d+\.\d) dBm, quiet from (-\d+\.\d) dBm \| 7\.5 MHz: noise floor (-\d+\.\d) dBm, quiet from (-\d+\.\d) dBm",
     ["PLAN.md"], ["%.1f" % B["noise_floor_dBm"], "%.1f" % (B["noise_floor_dBm"] + 11.4), "%.1f" % B["noise_floor_slow_dBm"], "%.1f" % (B["noise_floor_slow_dBm"] + 11.4)]),
    ("the isolation table (budget section 4)", r"\| (25|100|200) MHz \| [\d.]+ dB \| (\d+) dB \|", ["PLAN.md"], lambda m: [m.group(1), ISO[m.group(1)]]),
    ("the isolation 600 MHz apart", r"\| 600 MHz \(5\.2 GHz UNII vs 5\.8 GHz ISM\) \| \d+ dB \| (\d+) dB \|", ["PLAN.md"], [ISO["600"]]),
    ("gain 2 instead of 4 (budget section 4)", r"by (\d+) dB instead of (\d+), so the\ntwo-antenna full-duplex arrangement would have needed (\d+) dB of antenna isolation instead of (\d+)",
     ["PLAN.md"], ["%.0f" % B["gain2"]["reject600_dB"], "%.0f" % B["iso_table"][-1]["reject_dB"], "%.0f" % B["gain2"]["iso600_dB"], ISO["600"]]),
    ("the reach rows (build/link_rates.md's quiet table)", r"\| reach, lab, whips, no amplifier \(BPSK quiet\) \| ([\d.]+ k?m) \| ([\d.]+ k?m) \|", ["PLAN.md"],
     [quiet_bpsk("lab:", "fast"), quiet_bpsk("lab:", "slow")]),
    ("the reach rows", r"\| reach, campus, panels, amplifiers at the panel \| ([\d.]+ k?m) \| ([\d.]+ k?m) \|", ["PLAN.md"],
     [quiet_bpsk("campus: panels, PA and LNA at the panel", "fast"), quiet_bpsk("campus: panels, PA and LNA at the panel", "slow")]),
    ("the constellations' ranges (sim/constellations.py)", r"\| (A1|A4|A3|B2) [^|]*\| (\d+ m) \| ([\d.]+ k?m) \| ([\d.]+ km) \|", ["PLAN.md"], cons_row),
    ("the Costas loop as fitted (budget section 8c)", r"10 k fitted: fn (\d\.\d) kHz, ζ (\d\.\d\d)", ["PLAN.md"],
     ["%.1f" % (B["loop_fn_fit_Hz"] / 1e3), "%.2f" % B["loop_zeta_fit"]]),
    ("VC against the carrier (budget section 6)", r"watch VC move by (\d\.\d\d) V \((\d+) kHz/V", ["BRINGUP.md"],
     ["%.2f" % (100.0 / B["vc_kHz_per_V"]), "%.0f" % B["vc_kHz_per_V"]]),
    ("what received_dBm() reads (budget section 3)", r"cover about (−\d+) to\n(−\d+) dBm at RX ANT", ["BRINGUP.md"],
     ["−%.0f" % -B["rssi_range_dBm"][0], "−%.0f" % -B["rssi_range_dBm"][1]]),
    ("the FDA's summing nodes (budget section 7)", r"the summing nodes (\d+) mV under the guaranteed 2\.0 V; (\d+) mV at the worst corner", ["BRINGUP.md"],
     ["%.0f" % B["fda_vn_cases"][1]["margin_mV"], "%.0f" % B["fda_vn_cases"][2]["margin_mV"]]),
    ("the passives' knobs (sim/hosts.py)", r"The ladder's node at 100 Ω instead of 240 Ω: (\d\.\d\d) ns \((\d\.\d\d) ns at 3 km\)", ["PLAN.md"],
     ["%.2f" % KNOBS["the ladder's node at 100 ohm"]["bench"], "%.2f" % KNOBS["the ladder's node at 100 ohm"]["3 km"]]),
    ("the passives' knobs", r"The arm at gain 2 \((\d+) MHz\): (\d\.\d\d) ns at the bench, (\d\.\d\d) ns worse at 3 km", ["PLAN.md"],
     ["%.0f" % B["gain2"]["bw_MHz"], "%.2f" % KNOBS["the arm at gain 2"]["bench"], "%.2f" % -KNOBS["the arm at gain 2"]["3 km"]]),
    ("the passives' knobs", r"No arm at all: (\d\.\d\d) ns at the bench", ["PLAN.md"], ["%.2f" % KNOBS["no arm"]["bench"]]),
    # PLAN.md section 17: mfg/cost_estimate.py's last run (build/cost.json)
    ("the bare boards (section 17)", r"ENIG \(a model: \$(\d+)-(\d+)\) \| \$(\d+) \|", ["PLAN.md"],
     ["%.0f" % COST["pcb"][0], "%.0f" % COST["pcb"][2], "%.0f" % COST["pcb"][1]]),
    ("the assembly", r"(\d+) Extended codes' feeders, (\d+) SMT pads and (\d+) through-hole joints a board[^|]*\| \$(\d+) \|", ["PLAN.md"],
     [F["ext"], "%d" % COST["smt_pads"], "%d" % COST["tht_joints"], "%.0f" % COST["assembly"]]),
    ("JLCPCB's parts", r"their parts: (\d+) BOM lines, with attrition[^|]*\| \$(\d+) \|", ["PLAN.md"],
     [F["bom_lines"], "%.0f" % COST["parts"]]),
    ("the duty", r"US duty at 35 % under DDP \| \$(\d+) \|", ["PLAN.md"], ["%.0f" % COST["duty"]]),
    ("JLCPCB's total", r"\*\*JLCPCB total\*\* \| \*\*\$(\d+)-(\d+)\*\*", ["PLAN.md"], F["jlc"].split("-")),
    ("Digi-Key (section 17)", r"\| Digi-Key \| [^|]*\| \*\*\$(\d+)\*\* \|", ["PLAN.md"], ["%.0f" % COST["digikey"]]),
    ("the consignment's post", r"shipping a consignment to JLCPCB \| \$(\d+)-(\d+)", ["PLAN.md"], ["%.0f" % x for x in COST["consign_ship"]]),
    ("the bench and the field", r"when the far end needs them \| \*\*\$(\d+)-(\d+)\*\*", ["PLAN.md"], ["%.0f" % x for x in COST["other"]]),
    ("everything", r"\*\*everything\*\* \| \*\*\$([\d,]+)-([\d,]+)\*\*", ["PLAN.md"], [money_k(EVERY[0]), money_k(EVERY[1])]),
    ("a radio of the two-board order", r"The two-board order of section 17 is\n  ~\$(\d+)-(\d+) each", ["docs/SYSTEM.md"],
     ["%.0f" % round(TWO[0] / 2, -1), "%.0f" % round(TWO[1] / 2, -1)]),
    ("rev A's boards in the roadmap (sim/latency_roadmap.py, from build/cost.json)", r"Rev A's boards are section 17's \$([\d,]+)-([\d,]+): JLCPCB \$(\d+)-(\d+)",
     ["PLAN.md"], [money_k(TWO[0]), money_k(TWO[1])] + F["jlc"].split("-")),
    ("the roadmap's totals", r"\n\| (0|1|2|3|4|5) \| \*\*[^|]*\| [^|]*\| [^|]*\| [^|]*\| ≈? ?\$([\d,]+)-([\d,]+) \|", ["PLAN.md"],
     lambda m: [m.group(1)] + [money_k(round(x, -1)) for x in ROADMAP[m.group(1)]]),
    ("the board's current from 5 V (budget section 9)", r"(?<![\d.])(1\.\d\d) A\b", None, [F["I_A"]]),
    ("at power-up, before the synthesizers are programmed (budget I_powerup_mA)", r"Current: (\d\.\d\d) A plus up to (\d\.\d) A",
     ["BRINGUP.md"], ["%.2f" % (B["I_powerup_mA"] / 1e3), "%.1f" % (2 * P["pll_I_mA"] / 1e3)]),
    ("its power", r"(?:is|draws|heat:|\() ?(\d\.\d) W\b", None, [F["P_W"]]),
    ("the parts that are not the RF chips or the synthesizers", r"the rest (\d+) mA", ["PLAN.md"], [F["rest_mA"]]),
    ("rev A's band (budget band_GHz: the LNA and the balun)", r"(\d\.\d+)-(\d\.\d+) GHz in spec", None, ["%g" % x for x in P["band_GHz"]]),
    ("the arm's own noise over the log amp's floor (budget section 8b)", r"\((\d+) dB over the log amp's floor\)", ["PLAN.md"],
     ["%.0f" % (B["det_noise_log_dBV"] - P["log_floor_dBV"])]),
    ("the AD8310's offset-loop corner with C_OFLT (section 8b)", r"offset loop's corner[^.|]*? to (\d+) kHz", ["PLAN.md"], ["%.0f" % B["det_f_oflt_kHz"]]),
    ("its video bandwidth with C_BFIN (section 8b)", r"video bandwidth[^.|]*? to (\d+) kHz", ["PLAN.md"], ["%.0f" % B["det_f_video_kHz"]]),
    ("the peak hold's decay (section 8b)", r"lets it fall in (\d+) ms", ["PLAN.md"], ["%.0f" % B["det_tau_ms"]]),
    ("a consigned part at Digi-Key (gen/parts.py consign=)", r"\*\*Digi-Key ([\d,]+) at \$([\d.]+)\*\* \((?:1-9; )?([0-9A-Z-]+-ND)",
     ["PLAN.md"], lambda m: DK.get(m.group(3), ["not in gen/parts.py", "", ""])[:2] + [m.group(3)]),
]


def check():
    bad = 0
    text = {d: open(os.path.join(ROOT, d), encoding="utf-8").read() for d in DOCS}
    for what, rx, docs, want in CLAIMS:
        hits = 0
        for d in docs or DOCS:
            for m in re.finditer(rx, text[d]):
                hits += 1
                got = list(m.groups())
                exp = want(m) if callable(want) else want
                got = [g for g, e in zip(got, exp) if e is not None]
                exp = [e for e in exp if e is not None]
                if got != exp:
                    line = text[d].count("\n", 0, m.start()) + 1
                    print("%s:%d: %s: reads %s, the build says %s   [%s]" % (d, line, what, "/".join(got), "/".join(exp), m.group(0)[:80]))
                    bad += 1
        if not hits:
            print("no document matches the claim '%s' (%s): reworded?  update tools/doc_check.py" % (what, rx))
            bad += 1
    for title in ("**Range, 1 % wrong**", "**Range, quiet (1e-4)**"):          # PLAN.md section 15 carries these two whole
        block = LR[LR.index(title):].split("\n\n")[1]
        rows = [l for l in block.split("\n") if l.startswith("| ") and not l.startswith("| scenario")]
        lost = [l for l in rows if l not in text["PLAN.md"]]
        if lost:
            print("PLAN.md: %d rows of build/link_rates.md's %s table differ: paste the table again (first: %s)" % (len(lost), title, lost[0][:90]))
            bad += 1
    md = subprocess.run([sys.executable, os.path.join(ROOT, "gateware", "regmap.py"), "--md"], capture_output=True, text=True).stdout
    readme = open(os.path.join(ROOT, "gateware", "README.md"), encoding="utf-8").read()
    if md.strip() not in readme:
        print("gateware/README.md: the register table is not regmap.py --md's; paste its output again")
        bad += 1
    print("doc check: %d claims and 3 copied tables, %d stale" % (len(CLAIMS), bad))
    return bad


if __name__ == "__main__":
    sys.exit(1 if check() else 0)
