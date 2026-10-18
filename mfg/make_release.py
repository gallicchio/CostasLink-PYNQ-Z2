#!/usr/bin/env python3
"""The JLCPCB release for CostasLink-PYNQ-Z2: everything to upload, in one folder.

    python3 mfg/make_release.py [--boards N] [--assembled N] [--refresh]

--boards is the number of bare boards ordered (JLCPCB's minimum, 5) and --assembled how many of
them JLCPCB assembles (2).  --refresh asks JLCPCB's parts API again instead of using answers
cached within the last 24 hours (tools/jlc_api.py).

One board, 120 x 100 mm, 4 layers (JLC04161H-7628), 1.6 mm, ENIG, green; assembled on ONE side, the
top: the 2x20 socket J302, alone on the back, is soldered at home (HAND_SOLDER below: fitting it made the
order two-sided, about $38 before duty); Standard PCBA for the top's through-hole parts; no panel.  Nothing is consigned
unless JLCPCB's shelf is short on the day (Prompt 31): the two ADI chips have a Digi-Key fallback (gen/parts.py
consign=), and parts_report() consigns one only when JLCPCB's live stock cannot cover the order; such a line
stays in the BOM under its LCSC code, flagged CONSIGNED in the Note column, and CONSIGNMENT.md says what to buy
at Digi-Key and send to JLCPCB's consignment warehouse (with none, it says so).  Through-hole parts on the top
(the SMAs, the 2.54 mm headers) are fitted by JLCPCB; their joints are counted for the fee.

Writes mfg/release/:
    CostasLink-PYNQ-Z2_gerbers.zip   Gerbers (4 copper layers, both masks, both silks, both
                                     pastes, edge cuts) and Excellon drill, all measured from
                                     the drill/place origin (the board's bottom-left corner);
                                     gerbers/ holds the same files unzipped
    BOM_JLCPCB.csv                   Comment, Designator, Footprint, LCSC, Note: one line per
                                     LCSC code, every part JLCPCB places (consigned ones flagged)
    CostasLink-PYNQ-Z2_cpl_jlcpcb_upload.csv   the one to upload: Designator, Mid X, Mid Y, Layer,
                                     Rotation, with JLCPCB's conventions: the bottom-side mirror
                                     and each part's correction (mfg/jlc_rotation.py, read in a
                                     preview or predicted from JLCPCB's own drawing), and each
                                     part moved to where JLCPCB's drawing has its origin
                                     (mfg/footprint_check.py's datum)
    CostasLink-PYNQ-Z2_cpl_kicad_native.csv    KiCad's own positions and angles, for reference
    PLACEMENT_CHECKS.txt             what to look at in JLCPCB's placement preview, both sides
    FOOTPRINT_CHECK.txt              does each ordered part fit its copper?
    COST_ESTIMATE.md                 the order's price, fee by fee (mfg/cost_estimate.py's
                                     calibrated fees), the parts' stock, the consignment's cost
    ORDER_SETTINGS.md                JLCPCB's order form, field by field in its own order, every
                                     value that is not JLCPCB's default marked
    CONSIGNMENT.md                   the consigned parts: Digi-Key numbers, quantities, where to send
    excluded_from_assembly.csv       what is on the board but not placed, and why
    hand_solder_bom.csv              what is soldered or fitted at home: J302, and the jumper shunts
    CostasLink-PYNQ-Z2_assembly_top.pdf, _bottom.pdf   designators, from the fab layers

Gates: the release stops, and leaves mfg/release/ as it was, if any of these fails
(CLAUDE_PCB.md sections 8 and 10):
  * every component of the netlist is a part JLCPCB places (an LCSC code), a consigned part, or
    one gen/parts.py says is not a part (couplers are copper; test pads, holes, power flags);
  * every code is in gen/parts.py, the schematic's MPN is the table's, and JLCPCB's own
    description of the code carries every one of the part's `match` words, the schematic's
    value and package, and the MPN as JLCPCB's model (the consigned codes too);
  * every code JLCPCB supplies is in stock for the order, attrition included;
  * the board: 4 copper layers, 1.6 mm, 120 x 100 mm, filled zones, DRC clean (tools/pcb_check.py),
    every netlist component on it with the same footprint, nothing coded on it that the netlist
    lacks, bottom footprints stored as KiCad's own flip stores them;
  * no ordered part wants a hole the board lacks (FOOTPRINT_CHECK.txt);
  * every part of three or more pads has a rotation correction somebody read or one predicted
    from JLCPCB's drawing (never KiCad's bare angle without a reading: rev A's SMAs at a predicted +90 lay along the edge);
  * the CPL agrees with KiCad's own position export, and JLCPCB's drawing of each chip, placed
    as the CPL tells JLCPCB to place it, lands on our pads pin for pin, on both sides;
  * no output names a place on this machine (relative paths only).

Testing on a copy of the board (never a release): --pcb FILE --out DIR [--skip-drc]
[--accept-hole LCSC].
"""
import argparse
import collections
import csv
import datetime
import json
import math
import os
import re
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (HERE, os.path.join(ROOT, "tools"), os.path.join(ROOT, "gen"), os.path.join(ROOT, "sim")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import kienv                                  # noqa: E402
import jlc_api                                # noqa: E402
import jlc_rotation                           # noqa: E402
import footprint_check as FC                  # noqa: E402
import board_info as BI                       # noqa: E402
import placement as PL                        # noqa: E402
import cost_estimate as CE                    # noqa: E402  (the calibrated fees, the PCB model, the consigned prices)
import rf_lines as RF                         # noqa: E402  (the 50 ohm line geometry the order form quotes)
from parts import PARTS, consigned, fallback  # noqa: E402
from sexp import parse, kids, kid, val        # noqa: E402

NAME = BI.NAME
COPPER = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
THICKNESS = 1.6
STACKUP = "JLC04161H-7628"
GERBER_LAYERS = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts"
GERBER_FILES = ["F_Cu", "In1_Cu", "In2_Cu", "B_Cu", "F_Paste", "B_Paste", "F_Silkscreen", "B_Silkscreen",
                "F_Mask", "B_Mask", "Edge_Cuts"]
LIBDIR = os.path.join(BI.HW, "lib", BI.LIB + ".pretty")
# a place on one machine (CLAUDE_PCB.md section 2), spelt with character classes so that the
# repository's own path audit (git grep before every commit) does not flag this line
FORBIDDEN = re.compile(rb"/hom[e]/|/User[s]/|/tm[p]/|/mn[t]/|[A-Za-z]:\\{1,2}User[s]")
DEPANEL = CE.FEES["depanel"]        # the ECP5-2ADC-2DAC cart of 2026-10-09 (CLAUDE_PCB.md section 8)
SPARES_EACH = CE.CONSIGN_SPARES     # consigned parts: spares per line for JLCPCB's attrition and the bench (Jason)

# A HOLE finding (FOOTPRINT_CHECK.txt: JLCPCB's drawing of a part wants a hole where the board
# has no drill) stops the release.  Accept one here only after a person has put the maker's
# drawing beside JLCPCB's and decided the part seats as the board is drawn, and say who and why:
# "C431540": "Jason, 2026-10-08: ..."
HOLE_ACCEPTED = {}

# Parts JLCPCB does not fit, soldered at home (CLAUDE_PCB.md section 8, "Nothing hand-soldered, except a
# host socket that costs more than a few dollars to have fitted").  Jason, Prompt 15 (2026-10-10): "if it
# costs more than a few dollars to have JLCPCB solder the raspberry pi connectors, I'll do that myself.  I'd
# like them to do SMAs and small-pin headers."  J302 is the only part on the back: fitting it costs the second
# side's setup and stencil, its Extended feeder and its 40 joints (cost_table's ONE_SIDE_SAVES line).
HAND_SOLDER = {
    "J302": "the PYNQ-Z2 socket on the back, alone there: JLCPCB fitting it made the order two-sided (a second "
            "setup and stencil, its feeder and 40 joints a board: about $38 before duty, $51 with it).  Solder it "
            "from the back, square to the board, after JLCPCB's top side (as the GPSDO's J4001)",
}
assert set(HAND_SOLDER) == set(CE.HAND_SOLDER_REFS), "make_release.HAND_SOLDER and cost_estimate.HAND_SOLDER_REFS disagree"
# What ships loose: the jumper shunts (BRINGUP.md stage 3 names the positions)
LOOSE = [
    ("(not on the board)", "2.54 mm jumper shunt", "", "C5305", "", "7 a board",
     "JP101 SIGN B1 on Q-, JP102 SIGN B2 on Q+, JP103 SEL on CMP, JP201 REF on TCXO, JP203 TRIG>Q before the first power-up "
     "(BRINGUP.md stage 3); JP202 (50R on TRIG IN), JP301 (HDR 5V: the board powered from the PYNQ's header) and "
     "JP302 / JP303 (the I2C pull-ups, for the Icepi Zero) only when wanted.  Order a few spare"),
]
# the same parts at Digi-Key, so that they go into the consigned parts' cart (Digi-Key's pages, 2026-10-12): by
# designator or LCSC code -> (MPN, Digi-Key number, unit price, why it is the same part)
DIGIKEY_LOOSE = {
    "J302": ("PPTC202LFBN-RC", "S6104-ND", 2.14, "Sullins 2x20 female, 2.54 mm, 8.51 mm insulator, through-hole: C2977589's height"),
    "C5305": ("SPC02SYAN", "S9001-ND", 0.029, "Sullins 2.54 mm shunt"),
}

# the placement files (CLAUDE_PCB.md section 8): the name says which one goes to JLCPCB
CPL_UPLOAD = NAME + "_cpl_jlcpcb_upload.csv"
CPL_NATIVE = NAME + "_cpl_kicad_native.csv"


def draft():
    """Why this release is a DRAFT (CLAUDE_PCB.md section 10, gate 10), or None."""
    try:
        datetime.date.fromisoformat(BI.DATE)
    except ValueError:
        return "gen/board_info.py DATE (%r) is not a real date" % BI.DATE
    return None


class Gate(Exception):
    """A release gate failed: say why, change nothing."""


# ---------------------------------------------------------------------------------------
# the netlist and the parts table
# ---------------------------------------------------------------------------------------
def read_netlist(path):
    doc = parse(open(path, encoding="utf-8").read())[0]
    comps = []
    for c in kids(kid(doc, "components"), "comp"):
        fields = {}
        fl = kid(c, "fields")
        for f in kids(fl, "field") if fl else []:
            fields[val(kid(f, "name"))] = val(f, 2) if len(f) > 2 and isinstance(f[2], tuple) else ""
        props = {val(kid(p, "name")): (val(kid(p, "value")) if kid(p, "value") else "") for p in kids(c, "property")}
        lib = kid(c, "libsource")
        fp = kid(c, "footprint")
        comps.append(dict(ref=val(kid(c, "ref")), value=val(kid(c, "value")),
                          fp=(val(fp) if fp and len(fp) > 1 else "").split(":")[-1], lcsc=fields.get("LCSC", "").strip(),
                          mpn=fields.get("MPN", "").strip(), sym=val(kid(lib, "part")) if lib else "",
                          sheet=props.get("Sheetname", ""), dnp="dnp" in props,
                          no_bom="exclude_from_bom" in props, no_board="exclude_from_board" in props))
    return comps


def refkey(ref):
    m = re.match(r"([A-Za-z_#]+)(\d*)", ref)
    return (m.group(1), int(m.group(2) or 0)) if m else (ref, 0)


CONSIGNED = consigned()                                    # key -> gen/parts.py entry (consignment-only parts: none since Prompt 31)
CONSIGNED_BY_MPN = {p["mpn"]: k for k, p in CONSIGNED.items()}
FALLBACK_BY_CODE = {p["lcsc"]: k for k, p in fallback().items()}   # shelf parts consigned only when JLCPCB's stock is short


def not_a_part(c):
    """The gen/parts.py entry saying that this code-less component is not a part JLCPCB
    places (a coupler is copper; a test pad or a hole is bare board; a power flag has no
    footprint), or None."""
    if not c["fp"]:
        return next((k for k, p in PARTS.items() if not p.get("fp") and p["sym"].split(":")[-1] == c["sym"]), None)
    keys = [k for k, p in PARTS.items() if not p.get("lcsc") and not p.get("consign") and p["fp"].split(":")[-1] == c["fp"]
            and p["sym"].split(":")[-1] == c["sym"]]
    named = [k for k in keys if PARTS[k].get("value") and c["value"].split()[0] == PARTS[k]["value"]]
    return (named or keys or [None])[0]


def classify(comps):
    """placed: JLCPCB fits it from stock (an LCSC code); consigned: JLCPCB fits it from the
    parts we send (gen/parts.py's `consign`, filed under its LCSC code); hand: soldered at
    home (HAND_SOLDER); none: not a part; dnp: marked do-not-populate or excluded from the
    BOM; nocode: a gate failure."""
    for c in comps:
        c["consign"] = None
        k = not_a_part(c) if not c["lcsc"] and c["mpn"] not in CONSIGNED_BY_MPN else None
        if k:
            c["cls"], c["why"] = "none", "%s: %s" % (k, PARTS[k].get("note") or "not a part")
        elif c["dnp"] or c["no_bom"]:
            c["cls"], c["why"] = "dnp", "marked do-not-populate or excluded from the BOM in the schematic"
        elif c["ref"] in HAND_SOLDER:
            c["cls"], c["why"] = "hand", "hand-soldered at home: " + HAND_SOLDER[c["ref"]]
        elif c["lcsc"]:
            c["cls"], c["why"] = "placed", ""
        elif c["mpn"] in CONSIGNED_BY_MPN:
            k = CONSIGNED_BY_MPN[c["mpn"]]
            c["cls"], c["why"], c["consign"] = "consigned", "", k
            c["lcsc"] = CONSIGNED[k]["consign"]["lcsc"]          # the code JLCPCB's consignment files it under
        else:
            c["cls"], c["why"] = "nocode", ""
    return comps


def parts_for(code):
    """gen/parts.py's entries for one LCSC code: the parts JLCPCB supplies, and the consigned
    parts whose consignment is filed under it."""
    return [(k, p) for k, p in PARTS.items() if p.get("lcsc") == code or (p.get("consign") or {}).get("lcsc") == code]


# ---------------------------------------------------------------------------------------
# JLCPCB's description of each code against the parts table and the schematic
# ---------------------------------------------------------------------------------------
PKG = re.compile(r"_(0201|0402|0603|0805|1206|1210|1812|2010|2512)_")
SI = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6}


def _qty(text, unit):
    """Every quantity in `text` with that unit (Ω, F, H, V), in SI."""
    out = set()
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*([pnuµmkKM]?)" + unit + r"(?![a-zA-Z])", text):
        out.add(round(float(m.group(1)) * SI[m.group(2)], 15))
    return out


def schematic_value(c):
    """What the schematic's value says, as (kind, number in SI, extra words): '4.7uF' on a
    capacitor is ('F', 4.7e-6, []); '100nF C0G' adds 'C0G'; '0R' on a resistor is 0 ohm; '27nH'
    on an inductor 27 nH.  None when the value is not a number (a part name)."""
    kind = {"R": "Ω", "C": "F", "L": "H"}.get(c["sym"][:1]) if c["sym"] in ("R", "C", "C_Polarized", "L") else None
    if not kind:
        return None
    words = c["value"].replace("µ", "u").split()
    m = re.match(r"^(\d+(?:\.\d+)?)([pnumkKM]?)(?:F|H|R|Ω)?$", words[0]) if words else None
    if not m:
        return None
    return kind, round(float(m.group(1)) * SI[m.group(2)], 15), words[1:]


def check_code(code, comps, p):
    """Problems with one code: JLCPCB's record `p` against gen/parts.py and the schematic."""
    bad = []
    desc = " ".join(str(p.get(k) or "") for k in ("describe", "componentModelEn", "componentSpecificationEn",
                                                  "componentTypeEn", "componentBrandEn"))
    low = desc.lower().replace("µ", "u")
    entries = parts_for(code)
    if not entries:
        return ["%s (%s) is in the schematic but not in gen/parts.py" % (code, ", ".join(c["ref"] for c in comps))]
    for key, e in entries:
        missing = [w for w in e["match"] if w.lower().replace("µ", "u") not in low]
        if missing:
            bad.append("%s %s: JLCPCB's description lacks %s: %s" % (code, key, missing, desc[:110]))
    mpns = {e["mpn"] for _, e in entries}
    # a consigned part may be filed at JLCPCB under the maker's earlier number (the balun)
    models = {re.sub(r"\s+", "", m).upper() for m in mpns} | \
             {re.sub(r"\s+", "", (e.get("consign") or {}).get("legacy", "")).upper() for _, e in entries} - {""}
    model = re.sub(r"\s+", "", (p.get("componentModelEn") or "")).upper()
    for c in comps:
        if c["mpn"] not in mpns:
            bad.append("%s on %s: the schematic says MPN %r, gen/parts.py %s" % (code, c["ref"], c["mpn"], sorted(mpns)))
        if model not in models:
            bad.append("%s on %s: MPN %r but JLCPCB's model is %r" % (code, c["ref"], c["mpn"], p.get("componentModelEn")))
        fps = {e["fp"].split(":")[-1] for _, e in entries}
        if c["fp"] not in fps:
            bad.append("%s on %s: footprint %s, but gen/parts.py gives %s" % (code, c["ref"], c["fp"], sorted(fps)))
    seen = set()
    for c in comps:
        sv = schematic_value(c)
        if sv and (c["value"], c["fp"]) not in seen:
            seen.add((c["value"], c["fp"]))
            kind, number, extra = sv
            have = _qty(desc.replace("µ", "u"), kind)
            if kind in ("Ω", "F") and number not in have:
                bad.append("%s on %s: value %s, but JLCPCB's description says %s" % (code, c["ref"], c["value"], desc[:110]))
            elif kind == "H" and have and number not in have:
                bad.append("%s on %s: value %s, but JLCPCB's description says %s" % (code, c["ref"], c["value"], desc[:110]))
            for w in extra:
                if w.upper().endswith("V"):
                    if float(w[:-1]) not in _qty(desc, "V"):
                        bad.append("%s on %s: rated %s, JLCPCB says %s" % (code, c["ref"], w, desc[:110]))
                elif w.lower() not in low:
                    bad.append("%s on %s: %s not in JLCPCB's description %s" % (code, c["ref"], w, desc[:110]))
        m = PKG.search("_" + c["fp"] + "_") or PKG.search(c["fp"] + "_")
        if m and m.group(1) not in desc:
            bad.append("%s on %s: footprint %s, JLCPCB's package is %s" % (code, c["ref"], c["fp"],
                                                                         p.get("componentSpecificationEn")))
    return sorted(set(bad))


def parts_report(fitted, assembled, refresh):
    """Ask JLCPCB about every code JLCPCB places, supplied or consigned; return (rows by code,
    failures, thin stock).  A consigned code is checked for its description (it names the part
    in the BOM) but not for stock: we send the parts.  A shelf part with a Digi-Key fallback
    (gen/parts.py consign=) whose live stock cannot cover the order is turned into a consigned
    one here, and the row says so (`short`)."""
    by = collections.OrderedDict()
    for c in sorted(fitted, key=lambda c: refkey(c["ref"])):
        by.setdefault(c["lcsc"], []).append(c)
    rows, bad, thin = [], [], []
    for code, comps in by.items():
        cons = comps[0]["consign"]
        try:
            p, ts = jlc_api.by_code(code, refresh=refresh)
        except Exception as e:                                    # noqa: BLE001
            bad.append("%s: JLCPCB's parts API did not answer (%s); run again when online" % (code, e))
            continue
        if not p:
            bad.append("%s (%s): JLCPCB does not know this code" % (code, ", ".join(c["ref"] for c in comps)))
            continue
        bad += check_code(code, comps, p)
        n = len(comps)
        need = n * assembled
        order = jlc_api.order_qty(p, need)
        stock = int(p.get("stockCount") or 0)
        short = ""
        if not cons and code in FALLBACK_BY_CODE and stock < order:
            cons = FALLBACK_BY_CODE[code]
            for c in comps:
                c["consign"], c["cls"] = cons, "consigned"
            short = ("%s %s: %d in stock, the order needs %d: consigned from Digi-Key instead (gen/parts.py's fallback)"
                     % (code, p.get("componentModelEn"), stock, order))
        if not cons:
            if stock < order:
                bad.append("%s %s: %d in stock, the order needs %d (%d a board x %d boards, plus %d attrition)"
                           % (code, p.get("componentModelEn"), stock, order, n, assembled, order - need))
            elif stock < max(3 * order, 20):
                thin.append(code)
        rows.append(dict(code=code, comps=comps, n=n, need=need, order=order if not cons else need + SPARES_EACH,
                         stock=stock, part=p, asked=ts, consigned=cons, short=short,
                         lib=jlc_api.library_type(p) if not cons else "consigned",
                         unit=jlc_api.unit_price(p, order) if not cons else 0.0,
                         model=p.get("componentModelEn") or "", pkg=p.get("componentSpecificationEn") or ""))
    return rows, bad, thin


def write_bom(rows, out):
    """JLCPCB's BOM: one line per LCSC code (two lines for one code make JLCPCB's 'multiple
    lines matched to the same part', GPSDO P32).  The Note column flags the consigned lines;
    JLCPCB's upload maps the four it knows and ignores the rest."""
    path = os.path.join(out, "BOM_JLCPCB.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Comment", "Designator", "Footprint", "LCSC", "Note"])
        for r in sorted(rows, key=lambda r: (-r["n"], r["code"])):
            values = list(dict.fromkeys(c["value"] for c in r["comps"]))
            if len(values) > 1:                   # sixteen U.FLs named for their signals: the table's name for the part
                entries = parts_for(r["code"])
                values = [entries[0][1]["value"] or entries[0][1]["mpn"]] if entries else values
            fps = list(dict.fromkeys(c["fp"] for c in r["comps"]))
            note = ("CONSIGNED: %s, supplied by the customer (CONSIGNMENT.md), not from JLCPCB's stock"
                    % PARTS[r["consigned"]]["mpn"]) if r["consigned"] else ""
            w.writerow(["/".join(values), ",".join(c["ref"] for c in r["comps"]), fps[0], r["code"], note])
    return path


def write_excluded(comps, extra, out):
    with open(os.path.join(out, "excluded_from_assembly.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Footprint", "Why JLCPCB does not place it"])
        for c in sorted((c for c in comps if c["cls"] in ("none", "dnp", "hand")), key=lambda c: refkey(c["ref"])):
            w.writerow([c["ref"], c["value"], c["fp"], c["why"]])
        for ref, value, fp, why in extra:
            w.writerow([ref, value, fp, why])
    with open(os.path.join(out, "hand_solder_bom.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designator", "Value", "Footprint", "LCSC (to order loose)", "MPN", "Qty", "Digi-Key (the consignment's cart)",
                    "Digi-Key MPN", "Why"])
        for c in sorted((c for c in comps if c["cls"] == "hand"), key=lambda c: refkey(c["ref"])):
            dk = DIGIKEY_LOOSE.get(c["ref"], ("", "", 0, ""))
            w.writerow([c["ref"], c["value"], c["fp"], c["lcsc"], c["mpn"], "1 a board", dk[1], dk[0], HAND_SOLDER[c["ref"]]])
        for ref, value, fp, code, mpn, qty, why in LOOSE:
            dk = DIGIKEY_LOOSE.get(code, ("", "", 0, ""))
            w.writerow([ref, value, fp, code, mpn, qty, dk[1], dk[0], why])


def consignment_lines(rows, assembled):
    """One line per consigned part: what to buy and send."""
    out = []
    for r in sorted((r for r in rows if r["consigned"]), key=lambda r: r["code"]):
        key = r["consigned"]
        e = PARTS[key]
        dk = CE.DIGIKEY.get(key, {})
        qty = r["n"] * assembled + SPARES_EACH
        out.append(dict(key=key, mpn=e["mpn"], code=r["code"], jlc_model=r["model"], refs=[c["ref"] for c in r["comps"]],
                        n=r["n"], qty=qty, digikey=e["consign"].get("digikey", ""), mouser=e["consign"].get("mouser", ""),
                        legacy=e["consign"].get("legacy", ""), unit=dk.get("unit", 0.0), line=qty * dk.get("unit", 0.0),
                        seen=dk.get("seen") or e["consign"].get("seen", ""), jlc_stock=r["stock"], note=e["note"]))
    return out


def home_rows(assembled):
    """The loose parts for home (hand_solder_bom.csv), with their Digi-Key numbers."""
    out = ["| part | MPN | Digi-Key | buy | unit | why |", "|---|---|---|--:|--:|---|"]
    for key, n_board in (("J302", 1), ("C5305", 6)):
        mpn, dk, unit, why = DIGIKEY_LOOSE[key]
        buy = n_board * assembled + (1 if n_board == 1 else 8)
        out.append("| %s | %s | %s | %d | %s | %s |" % ("J302, the PYNQ-Z2 socket" if key == "J302" else "jumper shunts",
                                                         mpn, dk, buy, money(unit), why))
    return out


def fallback_text(assembled, rows):
    """The ADI chips' fallback and what a consignment really costs against the shelf (Jason, Prompt 31)."""
    fb = fallback()
    lo, hi, shelf = CE.consignment_cost(list(fb), assembled)
    seen = {r["code"]: r for r in rows}
    today = "; ".join("%s %s: JLCPCB %s in stock at %s" % (k, p["lcsc"], "{:,}".format(seen[p["lcsc"]]["stock"]) if p["lcsc"] in seen else "?",
                                                          money(seen[p["lcsc"]]["unit"]) if p["lcsc"] in seen and seen[p["lcsc"]]["unit"] else "?")
                      for k, p in fb.items())
    return ["**The fallback** (gen/parts.py consign=): %s.  Each is bought from JLCPCB's shelf while the shelf covers the "
            "order; if it is short on the day, mfg/make_release.py consigns that line and this file says what to buy.  "
            "Consigning both would mean %d pieces at Digi-Key, %d of them the spares JLCPCB asks for as attrition and never "
            "used, plus tax, Digi-Key's shipping and the shipment to Shenzhen: %s-%s against %s on the shelf for the %d "
            "pieces the boards need.  So for %d boards a shelf part up to %s-%s dearer than Digi-Key's price is still the "
            "cheaper buy, and with more boards the spares and the shipment are spread thinner (CLAUDE_PCB.md section 3)."
            % (today, len(fb) * (assembled + SPARES_EACH), len(fb) * SPARES_EACH, money(lo), money(hi), money(shelf),
               len(fb) * assembled, assembled, money(lo - shelf), money(hi - shelf))]


def write_consignment(lines, assembled, out, rows=()):
    if not lines:
        L = ["# %s rev %s: the consigned parts%s" % (BI.TITLE, BI.REV, " (DRAFT)" if draft() else ""), "",
             "Written by `mfg/make_release.py` on %s for %d assembled boards.  **Nothing is consigned on this order:** every "
             "part JLCPCB places is on its shelf, deep enough for the order (COST_ESTIMATE.md).  The balun is the TDK HHM1907B1 "
             "from JLCPCB's stock (Prompt 31; the Johanson 5400 the ADL5380's sheet uses has 0 there), and the two ADI chips "
             "are bought from JLCPCB's shelf.  No Parts Manager registration, no parcel to Shenzhen, no week of waiting."
             % (datetime.date.today(), assembled), ""]
        L += fallback_text(assembled, rows)
        L += ["", "**For home** (hand_solder_bom.csv; any distributor, or the drawer):", ""] + home_rows(assembled)
        open(os.path.join(out, "CONSIGNMENT.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
        return
    L = ["# %s rev %s: the consigned parts%s" % (BI.TITLE, BI.REV, " (DRAFT)" if draft() else ""), "",
         "Written by `mfg/make_release.py` on %s for %d assembled boards.  %d part%s JLCPCB's shelf could not cover on the "
         "day this release was written (the stock seen is in COST_ESTIMATE.md), so %s bought at Digi-Key and sent to "
         "JLCPCB, who fit %s like any other part (gen/parts.py's fallback, Prompt 31).  In `BOM_JLCPCB.csv` each sits "
         "under the LCSC code JLCPCB's consigned-parts process files it by, with CONSIGNED in its Note column."
         % (datetime.date.today(), assembled, len(lines), "s" if len(lines) != 1 else "",
            "they are" if len(lines) != 1 else "it is", "them" if len(lines) != 1 else "it"), "",
         "## What to buy", "",
         "| part | MPN | Digi-Key | Mouser | refs | a board | **send** | unit | line | stock seen |",
         "|---|---|---|---|---|--:|--:|--:|--:|---|"]
    total = 0.0
    for c in lines:
        total += c["line"]
        L.append("| %s | %s | %s | %s | %s | %d | **%d** | %s | %s | %s |"
                 % (c["key"], c["mpn"], c["digikey"], c["mouser"], " ".join(c["refs"]), c["n"], c["qty"],
                    money(c["unit"]) if c["unit"] else "?", money(c["line"]) if c["unit"] else "?", c["seen"]))
    L += ["", "The quantity to send is the placements on the %d assembled boards plus %d spares a line: JLCPCB asks for "
          "attrition on consigned parts, and a loose spare serves the bench.  Parts %s, plus %.1f %% sales tax and %s "
          "shipping: about %s (mfg/cost_estimate.py's Digi-Key bucket)."
          % (assembled, SPARES_EACH, money(total), CE.DIGIKEY_TAX * 100, money(CE.DIGIKEY_SHIPPING),
             money(total * (1 + CE.DIGIKEY_TAX) + CE.DIGIKEY_SHIPPING)), ""]
    L += ["**For home, in the same cart** (hand_solder_bom.csv; these stay with you, they do not go to JLCPCB):", ""] + home_rows(assembled)
    L += ["", "## How JLCPCB takes them", "",
          "1. Before the order, on jlcpcb.com under **Parts Manager > Consigned Parts** (their name for parts the "
          "customer supplies), register each part by its LCSC code below so the BOM line matches it:", ""]
    for c in lines:
        L.append("   - **%s** = %s (JLCPCB's model %s%s): %d pieces for %s" % (
            c["code"], c["mpn"], c["jlc_model"], "; the maker's new number is %s" % c["mpn"] if c["legacy"] else "",
            c["qty"], ", ".join(c["refs"])))
    L += ["", "2. JLCPCB gives the consignment a shipping label and the address of its consignment warehouse in Shenzhen "
          "(the Consigned Parts page shows both); send the reels' cut tape in one padded envelope, each bag labelled "
          "with its LCSC code and the order number (USPS Priority Mail International or FedEx: %s-%s, the estimate's range)."
          % (money(CE.CONSIGN_SHIP[0]), money(CE.CONSIGN_SHIP[1])),
          "3. In the order's BOM matching step, each of these lines must show the consigned stock as its source, not "
          "JLCPCB's shelf stock (JLCPCB had %s when this release was written: too few to cover the order)."
          % ", ".join("%d of %s" % (c["jlc_stock"], c["code"]) for c in lines),
          "4. Assembly starts when the parts have arrived and been counted; allow a week for the post.", "",
          "The parts, and why (gen/parts.py):", ""]
    for c in lines:
        L.append("- **%s** (%s): %s" % (c["key"], " ".join(c["refs"]), c["note"]))
    L += [""] + fallback_text(assembled, rows)
    L.append("")
    open(os.path.join(out, "CONSIGNMENT.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


# ---------------------------------------------------------------------------------------
# the board
# ---------------------------------------------------------------------------------------
def library_pads(short):
    """The project library's own pads for a footprint: {number: [(x, y)]}, or None."""
    path = os.path.join(LIBDIR, short + ".kicad_mod")
    if not os.path.exists(path):
        return None
    node = FC.sexp(open(path, encoding="utf-8").read())[0]
    out = collections.defaultdict(list)
    for p in FC.kids(node, "pad"):
        at = FC.nums(FC.kid(p, "at"), 2)
        out[p[1]].append((at[0], at[1]))
    return out


def bottom_storage(fp):
    """How the board file stores a bottom-side footprint: 'kicad' (KiCad's own flip: pads
    mirrored top-to-bottom, y negated), 'x-mirrored' (left-to-right: the same part then
    carries an angle 180 from KiCad's), or None when the library cannot tell."""
    lib = library_pads(fp["short"])
    if not lib:
        return None

    def err(sx, sy):
        worst = 0.0
        for p in fp["pads"]:
            cands = lib.get(p["number"])
            if not cands:
                return None
            worst = max(worst, min(math.hypot(p["x"] - sx * x, p["y"] - sy * y) for x, y in cands))
        return worst
    e_k, e_x = err(1, -1), err(-1, 1)
    if e_k is not None and e_k < 0.005:
        return "kicad"
    if e_x is not None and e_x < 0.005:
        return "x-mirrored"
    return None


def board_parts(pcb, comps):
    """The board's footprints, checked against the netlist.  Returns (board, by ref, extra
    footprints, failures)."""
    B = FC.read_board_full(pcb)
    fps = {}
    bad, extra = [], []
    for fp in B["fps"]:
        if fp["ref"] in fps:
            bad.append("two footprints on the board are called %s" % fp["ref"])
        fps[fp["ref"]] = fp
    net = {c["ref"]: c for c in comps}
    for c in comps:
        fp = fps.get(c["ref"])
        if c["no_board"] or not c["fp"]:
            continue
        if fp is None:
            bad.append("%s (%s) is in the netlist but not on the board" % (c["ref"], c["value"]))
            continue
        if fp["short"] != c["fp"]:
            bad.append("%s: the board has footprint %s, the schematic %s" % (c["ref"], fp["short"], c["fp"]))
        if c["cls"] in ("placed", "consigned"):
            code = fp["props"].get("LCSC", "")
            if code and c["cls"] == "placed" and code != c["lcsc"]:
                bad.append("%s: the board's LCSC field says %s, the schematic's %s" % (c["ref"], code, c["lcsc"]))
            if fp["dnp"]:
                bad.append("%s: do-not-populate on the board but not in the schematic" % c["ref"])
            if "exclude_from_pos_files" in fp["attrs"]:
                bad.append("%s: an ordered part marked 'exclude from position files' on the board" % c["ref"])
            if fp["layer"] == "B.Cu" and bottom_storage(fp) == "x-mirrored":
                bad.append("%s: stored on the bottom mirrored left-to-right, not as KiCad's own flip stores it "
                           "(FOOTPRINT.Flip or SetLayerAndFlip); every rotation rule here assumes KiCad's" % c["ref"])
    for ref, fp in sorted(fps.items(), key=lambda kv: refkey(kv[0])):
        if ref in net:
            continue
        if fp["props"].get("LCSC"):
            bad.append("%s (%s) carries LCSC code %s on the board but is not in the schematic"
                       % (ref, fp["short"], fp["props"]["LCSC"]))
            continue
        extra.append((ref, fp["value"], fp["short"], "a board feature, not a part (not in the schematic)"))
    return B, fps, extra, bad


def outline_box(B):
    pts = [p for e in B["edges"] for p in e]
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def to_cpl(x, y, aux):
    """Board millimetres (y down) to the CPL's and the gerbers' frame: from the drill/place
    origin, y up."""
    ox, oy = aux or (0.0, 0.0)
    return x - ox, oy - y


def kicad_turn(x, y, deg):
    """KiCad's rotation of a footprint-local point: counter-clockwise on screen, y down."""
    a = math.radians(deg)
    return x * math.cos(a) + y * math.sin(a), -x * math.sin(a) + y * math.cos(a)


def datum_shift(fp, fit):
    """Where JLCPCB's drawing has its origin, relative to ours, in board mm (y down).
    JLCPCB puts THEIR origin where the CPL says (every USB-C so far: 1.3-1.6 mm off).
    footprint_check.py's fit says where it sits in our footprint as the file stores it (for
    the bottom side, already mirrored), so KiCad's own rotation carries it onto the board on
    either side.  Only past DATUM_OK and when the fit is good."""
    if not fit or math.hypot(fit["dx"], fit["dy"]) <= FC.DATUM_OK or fit["worst"] > FC.LAND_OK:
        return 0.0, 0.0
    return kicad_turn(fit["dx"], fit["dy"], fp["at"][2])


def pad_spots(fp):
    """Distinct copper pad positions of a footprint on the board (unplated holes left out)."""
    return {(round(p["x"], 2), round(p["y"], 2)) for p in fp["pads"]
            if p["type"] != "np_thru_hole" and any(l.endswith(".Cu") for l in p["layers"])}


def predictions(fitted, fps, fits):
    """Per (code, footprint): the correction JLCPCB's own drawing predicts, from the quarter
    turn that laid it on our footprint by pin number (right on every part of GPiBridge's
    preview).  A fit at d degrees predicts 360 - d, on either side: KiCad stores a bottom
    footprint's pads mirrored top-to-bottom, and footprint_check.py mirrors JLCPCB's drawing
    the same way before fitting, so the turn comes out as on the top.  Two-pad parts get
    none: their polarity is a mark, not a pin number; nor do parts whose pins JLCPCB numbers
    unlike KiCad (a fit by position alone cannot see which way the body faces)."""
    out = {}
    for c in fitted:
        fp = fps[c["ref"]]
        key = (c["lcsc"], fp["short"])
        if key in out:
            continue
        cands = []
        for bottom in (False, True):
            fit = fits.get((c["lcsc"], bottom, fp["short"]))
            if fit and fit.get("how") == "by name" and fit.get("n", 0) >= 3 and fit["worst"] <= FC.LAND_WARN:
                cands.append(((360 - fit["deg"]) % 360, "bottom" if bottom else "top", fit))
        if not cands:
            some = fits.get((c["lcsc"], False, fp["short"])) or fits.get((c["lcsc"], True, fp["short"]))
            out[key] = (None, "two pads: polarity is a mark, not a pin number" if some and len(pad_spots(fp)) < 3
                        else "no fit by pin number (JLCPCB numbers its pads unlike ours, or the drawing is missing)")
        elif len({cd[0] for cd in cands}) > 1:
            out[key] = (None, "the top-side fit says %d and the bottom-side fit %d: they must agree"
                        % (cands[0][0], cands[1][0]))
        else:
            pred, side, fit = cands[0]
            out[key] = (pred, "JLCPCB's drawing turned %d to lie on ours (%s side, %d pads by number, worst %.2f mm)%s"
                        % (fit["deg"], side, fit["n"], fit["worst"],
                           "; the other side's fit agrees" if len(cands) == 2 else ""))
    return out


def jlc_pads_on_board(lp, row, aux):
    """Where JLCPCB puts the pads of their drawing `lp` for one CPL row, in board mm.
    Top: their drawing, turned counter-clockwise by the CPL's rotation.  Bottom (their
    convention, from the Icepi Zero's preview, jlc_rotation.BOTTOM_FLIP): the board seen
    from below, turned over left-to-right; the part as drawn, turned counter-clockwise in
    that view, then seen through the board from the top (x mirrored)."""
    ox, oy = aux or (0.0, 0.0)
    X, Y = row["X"] + ox, oy - row["Y"]
    out = []
    for p in lp["pads"]:
        u, v = kicad_turn(p["x"], p["y"], row["R"])
        out.append((p["number"], X + (u if row["side"] == "top" else -u), Y + v))
    return out


def simulate(fitted, fps, fits, cpl, aux):
    """JLCPCB's drawing of each chip, placed as the CPL says, must land on our pads pin for
    pin: the computed placement preview.  It is the bottom-side check that needs no preview,
    and it exercises the mirror rule, the corrections and the datum shift on both sides."""
    bad, ok = [], []
    for c in fitted:
        fp = fps[c["ref"]]
        fit = fits.get((c["lcsc"], fp["layer"].startswith("B."), fp["short"]))
        if not fit or fit.get("how") != "by name" or fit.get("n", 0) < 3 or fit["worst"] > FC.LAND_WARN:
            continue
        lp, _ = FC.land_pattern(c["lcsc"])
        ours = collections.defaultdict(list)
        for p in fp["pads"]:
            ours[p["number"]].append(FC.to_board(p["x"], p["y"], fp["at"], fp["layer"]))
        theirs = collections.defaultdict(list)                # JLCPCB's pads by number: a tab shares its lead's
        for num, x, y in jlc_pads_on_board(lp, cpl[c["ref"]], aux):
            theirs[num].append((x, y))
        worst, at = 0.0, ""
        for num, pts in theirs.items():
            if num not in ours:
                continue
            d = min(math.hypot(x - a, y - b) for x, y in pts for a, b in ours[num])
            if d > worst:
                worst, at = d, num
        # the fit's own residual, plus a datum offset too small to move the part for
        unmoved = 0.0 if datum_shift(fp, fit) != (0.0, 0.0) else math.hypot(fit["dx"], fit["dy"])
        if worst > fit["worst"] + unmoved + 0.02:
            bad.append("%s (%s, %s side): JLCPCB's drawing placed by the CPL misses our pad %s by %.2f mm"
                       % (c["ref"], c["lcsc"], cpl[c["ref"]]["side"], at, worst))
        else:
            ok.append(c["ref"])
    return bad, ok


def pos_export_check(pcb, cpl_native, scratch):
    """KiCad's own position export must agree with what this script read."""
    pos = os.path.join(scratch, "pos.csv")
    kienv.run_cli(["pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                   "--use-drill-file-origin", "-o", pos, pcb])
    bad, seen = [], set()
    for r in csv.DictReader(open(pos, encoding="utf-8")):
        ref = r["Ref"]
        if ref not in cpl_native:
            continue
        seen.add(ref)
        n = cpl_native[ref]
        if abs(float(r["PosX"]) - n["X"]) > 0.002 or abs(float(r["PosY"]) - n["Y"]) > 0.002 \
                or abs((float(r["Rot"]) - n["R"] + 180) % 360 - 180) > 0.01 or r["Side"] != n["side"]:
            bad.append("%s: KiCad's position file says (%s, %s) %s %s, this script (%.3f, %.3f) %g %s"
                       % (ref, r["PosX"], r["PosY"], r["Rot"], r["Side"], n["X"], n["Y"], n["R"], n["side"]))
    for ref in sorted(set(cpl_native) - seen, key=refkey):
        bad.append("%s: missing from KiCad's position file (excluded from position files?)" % ref)
    return bad


tht_joints = CE.pad_counts             # (SMD pads, through-hole joints): one count for the estimate and the release


def board_features(B, fps, box, parts=()):
    """What the board carries for the assembler: fiducials (three of its own, gen/placement.FIDUCIALS,
    and JLCPCB adds rails with more, the form's default), the mounting holes, any order-number marker (JLCPCB
    now asks that it NOT be added), and the parts that hang over the edge, which JLCPCB's
    rails must leave room for."""
    x0, y0, x1, y1 = box
    fid = [fp["ref"] for fp in fps.values() if "fiducial" in fp["short"].lower() or re.match(r"^FID\d+$", fp["ref"])]
    # the board's own fiducials are netless graphics (gen/board.marks), named by where they stand
    fid += ["(%.1f, %.1f)" % xy for xy in PL.FIDUCIALS]
    holes = []
    for fp in sorted(fps.values(), key=lambda f: refkey(f["ref"])):
        for p in fp["pads"]:
            if p["type"] == "np_thru_hole" and fp["ref"] not in parts:
                x, y = FC.to_board(p["x"], p["y"], fp["at"], fp["layer"])
                holes.append((fp["ref"], x - x0, y - y0, p["drill"]))
    jlc = [t for t in B["texts"] if "JLCJLCJLCJLC" in t[0]]
    lib = PL.load_footprints()
    over = []                                 # (ref, edge, mm) of courtyards past the outline
    for fp in sorted(fps.values(), key=lambda f: refkey(f["ref"])):
        court = (lib.get(fp["short"]) or {}).get("court")
        if not court or fp["ref"] not in parts:
            continue
        cx0, cy0, cx1, cy1 = court
        sy = -1.0 if fp["layer"].startswith("B.") else 1.0            # the file stores the bottom's pads y-mirrored
        pts = [kicad_turn(x, y * sy, fp["at"][2]) for x in (cx0, cx1) for y in (cy0, cy1)]
        xs = [fp["at"][0] + u for u, v in pts]
        ys = [fp["at"][1] + v for u, v in pts]
        for edge, d in (("top", y0 - min(ys)), ("bottom", max(ys) - y1), ("left", x0 - min(xs)), ("right", max(xs) - x1)):
            if d > 0.05:
                over.append((fp["ref"], edge, round(d, 2)))
    return dict(fiducials=fid, holes=holes, jlc_text=jlc, overhang=over)


# ---------------------------------------------------------------------------------------
# outputs from the board
# ---------------------------------------------------------------------------------------
def export_gerbers(pcb, out):
    gerb = os.path.join(out, "gerbers")
    os.makedirs(gerb)
    kienv.run_cli(["pcb", "export", "gerbers", "-o", gerb, "--layers", GERBER_LAYERS, "--no-protel-ext",
                   "--subtract-soldermask", "--use-drill-file-origin", pcb])
    kienv.run_cli(["pcb", "export", "drill", "-o", gerb + os.sep, "--format", "excellon", "--drill-origin", "plot",
                   "--excellon-units", "mm", "--excellon-zeros-format", "decimal", "--excellon-separate-th",
                   "--generate-map", "--map-format", "gerberx2", pcb])
    files = sorted(os.listdir(gerb))
    stem = os.path.splitext(os.path.basename(pcb))[0]
    missing = [g for g in GERBER_FILES if "%s-%s.gbr" % (stem, g) not in files]
    missing += [d for d in ("PTH.drl",) if "%s-%s" % (stem, d) not in files]
    if missing:
        raise Gate("gerber export is missing %s" % missing)
    zpath = os.path.join(out, NAME + "_gerbers.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in files:
            z.write(os.path.join(gerb, fn), fn)
    for side, layers, mirror in (("top", "F.Fab,F.Silkscreen,Edge.Cuts", False),
                                 ("bottom", "B.Fab,B.Silkscreen,Edge.Cuts", True)):
        p = os.path.join(out, "%s_assembly_%s.pdf" % (NAME, side))
        kienv.run_cli(["pcb", "export", "pdf", "-o", p, "--layers", layers, "--mode-single", "--exclude-value"]
                      + (["--mirror"] if mirror else []) + [pcb])
    return zpath, files


def gerber_box(path):
    """The extent of a gerber's coordinates (Edge.Cuts: the board's outline), in mm."""
    xs, ys = [], []
    scale = 1e-6
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"%FSLAX(\d)(\d)Y(\d)(\d)\*%", line)
        if m:
            scale = 10.0 ** -int(m.group(2))
        for m in re.finditer(r"X(-?\d+)Y(-?\d+)", line):
            xs.append(int(m.group(1)) * scale)
            ys.append(int(m.group(2)) * scale)
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def write_cpl(rows, out):
    for name, key in ((CPL_UPLOAD, "jlc"), (CPL_NATIVE, "native")):
        with open(os.path.join(out, name), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
            for ref in sorted(rows, key=refkey):
                r = rows[ref][key]
                w.writerow([ref, "%.3fmm" % r["X"], "%.3fmm" % r["Y"], r["side"].capitalize(), "%g" % r["R"]])


LOOK = {
    # what to look for in the preview, by footprint (pad 1 and the library's own marks)
    "QFN-24-1EP_4x4mm_P0.5mm_EP2.6x2.6mm": "pin 1 by the silk dot; JLCPCB's dot on it (the ADL5380, the ADL5375, the PE43711)",
    "QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm": "pin 1 by the silk dot; JLCPCB's dot on it (the MAX2871s)",
    "SKY65404-31_QFN-6_1.5x1.5mm": "pin 1 by the silk dot; three pads a side (the LNA)",
    "VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm": "pin 1 by the silk dot (the THS4541s)",
    "SOT-89-3": "the wide tab (pin 2, RFOUT side) one way, pins 1 and 3 the other (the ADL5611s)",
    "SOT-353_SC-70-5": "pin 1 by the silk mark: three pins one side, two the other",
    "SOT-363_SC-70-6": "pin 1 by the silk mark",
    "SOT-23-5": "pin 1 by the silk mark: three pins on one side, two on the other (the LDOs)",
    "SOT-23": "pin 1 by the silk mark: one pin alone on one side, two on the other (the P-FETs)",
    "VSSOP-8_3x3mm_P0.65mm": "pin 1 by the silk mark (the OPA2187)",
    "MSOP-10_3x3mm_P0.5mm": "pin 1 by the silk mark (the MCP4728s)",
    "TSSOP-10_3x3mm_P0.5mm": "pin 1 by the silk mark (the ADS1115)",
    "MSOP-8-1EP_3x3mm_P0.65mm_EP1.73x1.85mm": "pin 1 by the silk mark (the HMC536 switch)",
    "Crystal_SMD_3225-4Pin_3.2x2.5mm": "an OSCILLATOR, not a crystal: pin 1 by the silk mark; pin 1 VC/NC, 2 GND, 3 OUT, 4 VDD",
    "LED_0603_1608Metric": "the cathode (pad 1) at the silk bracket's end; JLCPCB marks the cathode",
    "D_SMA": "the cathode bar at pad 1 (the TVS: unidirectional, so it matters)",
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12": "the receptacle's mouth flush with the right edge, on its pads",
    "SMA_BWSMA-KWE-Z001": "the barrel points OFF the edge (read in rev A's preview, 2026-10-17: +0 is right; the predicted +90 lay them along the edge)",
    "U.FL_Hirose_U.FL-R-SMT-1_Vertical": "the signal pad (pin 1) on the track side",
    "RPi_Socket_2x20_P2.54mm_Underside": "ON THE BACK: pin 1 at the RIGHT-HAND end of the bottom edge, odd row outer "
                                         "(gen/placement.py); the socket is keyed by nothing but this",
    "PinHeader_1x02_P2.54mm_Vertical": "pin 1 at the square pad; a header is the same turned half round, not a quarter",
    "PinHeader_1x03_P2.54mm_Vertical": "pin 1 at the square pad; the three in a line along the board's edge",
    "Balun_Johanson_5400BL15B050": "pin 1 by the silk mark (Johanson's drawing)",
}


def placement_checks(out, fitted, fps, cpl, preds, moved, sim_ok, sim_bad, aux, feat):
    L = ["%s rev %s: PLACEMENT CHECKS for JLCPCB's preview (%s)" % (BI.TITLE, BI.REV, datetime.date.today()), ""]
    bottom = sorted((c["ref"] for c in fitted if cpl[c["ref"]]["jlc"]["side"] == "bottom"), key=refkey)
    if bottom:
        L += ["The board is assembled on BOTH sides: %s on the back, everything else on top.  JLCPCB's preview opens"
              % ", ".join(bottom),
              "on the top; check the back too (Jason, ECP5 2026-10-08: \"I almost forgot to check the back parts\").", ""]
    else:
        L += ["The board is assembled on the top only (%s, on the back, is soldered at home: hand_solder_bom.csv)."
              % (", ".join(sorted(HAND_SOLDER, key=refkey)) or "nothing"), ""]
    if moved:
        L += ["MOVED in " + CPL_UPLOAD + " to where JLCPCB's library puts the part's origin (their drawing's",
              "zero is not KiCad's; FOOTPRINT_CHECK.txt's 'datum').  In the preview each should sit squarely",
              "on its pads.  If one sits off them by about the same distance the other way, their library has",
              "changed: say so, and it goes into the code.", ""]
        for ref, dx, dy in moved:
            L.append("  %-6s %-10s %-6s %-44s moved (%+.3f, %+.3f) mm (x right, y up)"
                     % (ref, cpl[ref]["code"], cpl[ref]["jlc"]["side"], fps[ref]["short"][:44], dx, dy))
        L.append("")
    L += ["ROTATIONS.  " + CPL_UPLOAD + "'s rotation is KiCad's angle, mirrored for the bottom side",
          "(180 - angle: JLCPCB looks at the bottom from below, the board turned over left-to-right;",
          "jlc_rotation.BOTTOM_FLIP, read on ten bottom-side parts of the Icepi Zero), plus each part's",
          "correction: read in an earlier preview where somebody has looked, else PREDICTED from JLCPCB's",
          "own drawing of the part turned until its pads lie on ours by pin number.  Every part below that",
          "nobody has yet seen right is listed with its prediction: check its pin 1 or polarity mark",
          "(JLCPCB's dot) against the board, write down any that is wrong and by how much, and it goes",
          "into mfg/jlc_rotation.py.  Never turn or nudge a part in JLCPCB's viewer: the next upload loses it.", ""]
    L += ["Placed as the CPL says, JLCPCB's own drawing lands pin for pin on our pads for %d parts"
          % len(sim_ok), "(make_release.py's simulation of their placement, both sides)%s." %
          (": " + "; ".join(sim_bad) if sim_bad else ""), ""]
    groups = collections.OrderedDict()
    for c in sorted(fitted, key=lambda c: (c["lcsc"], refkey(c["ref"]))):
        groups.setdefault((c["lcsc"], fps[c["ref"]]["short"]), []).append(c)
    unread, read, na = [], [], []
    for (code, short), cs in groups.items():
        corr, conf, why = jlc_rotation.correction(short, code)
        if short in jlc_rotation.ROTATION_NA:
            na.append(short)
        elif jlc_rotation.checked(short, code):
            read.append((code, short, cs, corr, conf, why))
        else:
            unread.append((code, short, cs, corr, conf, why))
    L.append("NOT YET SEEN RIGHT in a preview (%d part numbers, %d placements):"
             % (len(unread), sum(len(g[2]) for g in unread)))
    for code, short, cs, corr, conf, why in unread:
        pred, pwhy = preds.get((code, short), (None, ""))
        tops = [c["ref"] for c in cs if cpl[c["ref"]]["jlc"]["side"] == "top"]
        bots = [c["ref"] for c in cs if cpl[c["ref"]]["jlc"]["side"] == "bottom"]
        L.append("  %-10s %-26s %s%s" % (code, "/".join(dict.fromkeys(c["value"] for c in cs))[:26], short,
                                         "  (CONSIGNED)" if cs[0]["consign"] else ""))
        if tops:
            L.append("      top:    " + " ".join(tops))
        if bots:
            L.append("      BOTTOM: " + " ".join(bots))
        if conf != "none":
            L.append("      correction %d (%s): %s" % (corr, conf, why))
            if pred is not None and pred != corr:
                L.append("      (JLCPCB's drawing by pin number would say %d: %s)" % (pred, pwhy))
        elif pred is not None:
            L.append("      correction %d, predicted: %s" % (pred, pwhy))
        else:
            L.append("      correction 0, NOT PREDICTED (%s): look at it hardest" % pwhy)
        if short in LOOK:
            L.append("      look for: %s" % LOOK[short])
    L += ["", "READ RIGHT in an earlier preview (the same part number, this footprint or its twin):"]
    for code, short, cs, corr, conf, why in read:
        pred, _ = preds.get((code, short), (None, ""))
        agree = "" if pred is None else ("; JLCPCB's drawing agrees" if pred == corr else
                                          "; JLCPCB's drawing says %d: LOOK" % pred)
        L.append("  %-10s %-40s correction %3d (%s)%s: %s" % (code, short[:40], corr, conf, agree,
                                                             " ".join(c["ref"] for c in cs)))
    L += ["", "No orientation to get wrong (two pads, no polarity): " + ", ".join(sorted(set(na))), ""]
    tht = [c["ref"] for c in fitted if tht_joints(fps[c["ref"]])[1]]
    if tht:
        L += ["THROUGH-HOLE parts JLCPCB fits by hand (they go in one way by their pins, but look):"]
        for ref in sorted(tht, key=refkey):
            fp = fps[ref]
            L.append("  %-6s %-6s %-46s %d joints%s" % (ref, cpl[ref]["jlc"]["side"], fp["short"][:46], tht_joints(fp)[1],
                                                       ("; " + LOOK[fp["short"]]) if fp["short"] in LOOK else ""))
        L.append("")
    if feat["overhang"]:
        L += ["OVER THE EDGE (JLCPCB's rails must leave room; said in the order's Assembly remark):"]
        for ref, edge, d in feat["overhang"]:
            L.append("  %-6s %.1f mm past the %s edge" % (ref, d, edge))
        L.append("")
    L += ["FRAME: Mid X and Mid Y are millimetres from the drill/place origin %s, y up, the same frame as"
          % ("(%.3f, %.3f) on KiCad's page: the board's bottom-left corner" % aux if aux else "(not set: KiCad's page origin)"),
          "the gerbers and the drill file.  Bottom-side X is NOT negated (JLCPCB reads both sides from the",
          "top).  KiCad's own position export agrees with every row of " + CPL_NATIVE + ".", ""]
    L += ["LAST: THE BACK.  Before confirming, look at the bottom side's part(s): %s." % (", ".join(
        "%s (%s)" % (r, fps[r]["short"]) for r in bottom) or "none")]
    open(os.path.join(out, "PLACEMENT_CHECKS.txt"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    return L


# ---------------------------------------------------------------------------------------
# cost and order settings
# ---------------------------------------------------------------------------------------
def money(x):
    return "$%.2f" % x


def pcb_price(w, h, boards):
    """The bare boards: mfg/cost_estimate.py's model (GPiBridge's cart for the fixed part,
    JLCPCB's published 4-layer area price and five times it, an ENIG allowance), as
    (estimate, low, high, how)."""
    M = CE.PCB_MODEL
    area = w * h / 100.0 * boards                                    # cm2
    fixed = M["ref_price"] - M["per_m2_low"] * M["ref_area_cm2"] * M["ref_boards"] / 1e4
    lo = fixed + M["per_m2_low"] * area / 1e4 + M["enig_extra"][0]
    hi = fixed + M["per_m2_high"] * area / 1e4 + M["enig_extra"][1]
    how = ("ESTIMATE, %s-%s: GPiBridge's cart (2026-10-06, 4 layers, ENIG: %s for 5 boards of 15.3 cm2) for the fixed "
           "part, plus %.0f cm2 at $%.1f-%.0f per m2 (JLCPCB's published 4-layer board charge, and five times it for a "
           "small order), plus $%.0f-%.0f for ENIG; the cart's number replaces it"
           % (money(lo), money(hi), money(M["ref_price"]), area, M["per_m2_low"], M["per_m2_high"],
              M["enig_extra"][0], M["enig_extra"][1]))
    return (lo + hi) / 2, lo, hi, how


def cost_md(out, rows, fps, boards, assembled, dims, thin, cons_lines):
    """COST_ESTIMATE.md: the order, fee by fee, as mfg/cost_estimate.py models it (the ECP5
    cart's calibrated fees, CLAUDE_PCB.md section 8), and every part's price and stock."""
    F = CE.FEES
    supplied = [r for r in rows if not r["consigned"]]
    ext = sorted((r for r in supplied if r["lib"] == "Extended"), key=lambda r: r["code"])
    pref = [r for r in supplied if r["lib"] == "Preferred"]
    basic = [r for r in supplied if r["lib"] == "Basic"]
    parts_raw = sum(r["unit"] * r["order"] for r in supplied)
    parts = parts_raw * F["parts_markup"]
    w, h = dims
    side_of = {c["ref"]: ("bottom" if fps[c["ref"]]["layer"].startswith("B.") else "top") for r in rows for c in r["comps"]}
    sides = set(side_of.values())
    smd = sum(tht_joints(fps[c["ref"]])[0] for r in rows for c in r["comps"])      # consigned parts are placed too
    tht = sum(tht_joints(fps[c["ref"]])[1] for r in rows for c in r["comps"])
    n_tht_parts = sum(1 for r in rows for c in r["comps"] if tht_joints(fps[c["ref"]])[1])
    pcb, pcb_lo, pcb_hi, pcb_how = pcb_price(w, h, boards)
    A = collections.OrderedDict([
        # per assembled side (the ECP5 cart's two-sided numbers halved, as the GPSDO's annotate_bom.py does)
        ("setup", (F["setup"] / 2.0 * len(sides), "Standard PCBA setup, %s" % ("both sides" if len(sides) == 2 else "one side"))),
        ("stencil", (F["stencil_both"] / 2.0 * len(sides), "stencils, one for each side" if len(sides) == 2 else "stencil, one side")),
        ("fixture", (F["fixture"], "PCB assembly fixture")),
        ("feeder", (F["feeder_per_extended"] * len(ext), "feeder loading, %d Extended codes x %s (Basic and Preferred parts are "
                                                          "free; the %d consigned lines may be charged the same)"
                    % (len(ext), money(F["feeder_per_extended"]), len(cons_lines)))),
        ("smt", ((F["smt_per_pad"] * smd + F["smt_per_board"]) * assembled,
                 "SMT, %d pads a board x $%.4f + %s a board, x %d" % (smd, F["smt_per_pad"], money(F["smt_per_board"]), assembled))),
        ("tht", ((F["hand_solder_labour"] + F["tht_per_joint"] * tht * assembled) if tht else 0.0,
                 "through-hole: %s labour an order + %d joints a board (%d parts) x %d x $%.4f"
                 % (money(F["hand_solder_labour"]), tht, n_tht_parts, assembled, F["tht_per_joint"]))),
        ("packaging", (F["packaging"], "packaging")),
        ("special", (F["special"], "special components")),
        ("depanel", (DEPANEL, "depanel: JLCPCB's assembly rails taken off before delivery (the ECP5 cart's $%.2f)" % DEPANEL)),
    ])
    asm = sum(v[0] for v in A.values())
    confirm = F["confirm_production"]
    goods = pcb + confirm + asm + parts
    duty = F["duty"] * goods
    jlc = (goods + duty + CE.SHIPPING[0], goods + duty + CE.SHIPPING[1])
    dk_parts = sum(c["line"] for c in cons_lines)
    dk_total = dk_parts * (1 + CE.DIGIKEY_TAX) + CE.DIGIKEY_SHIPPING if cons_lines else 0.0
    consign_ship = CE.CONSIGN_SHIP if cons_lines else (0.0, 0.0)
    other = (sum(o[1] for o in CE.OTHER), sum(o[2] for o in CE.OTHER))
    L = ["# %s rev %s: cost estimate%s" % (BI.TITLE, BI.REV, " (DRAFT)" if draft() else ""), "",
         "Written by `mfg/make_release.py` on %s.  Parts: JLCPCB's live prices and stock (their parts API, asked at the "
         "times in the table), with their attrition and minimum purchase, x %.4f as the cart charges.  Fees: JLCPCB's "
         "cart on the ECP5-2ADC-2DAC order of 2026-10-09 (`mfg/cost_estimate.py` FEES, CLAUDE_PCB.md section 8).  The "
         "bare boards: a model with a range until the cart gives the number." % (datetime.date.today(), F["parts_markup"]), "",
         "**The order:** %d bare boards of %.1f x %.1f mm, 4 layers, 1.6 mm, green, ENIG, %s; **%d of them assembled "
         "on %s** (Standard PCBA), %s; %s (CONSIGNMENT.md)."
         % (boards, w, h, STACKUP, assembled, "both sides" if len(sides) == 2 else "one side",
            ("%s soldered at home (hand_solder_bom.csv: the part to order loose, and the "
             "jumper shunts)" % ", ".join(sorted(HAND_SOLDER, key=refkey))) if HAND_SOLDER else "nothing hand-soldered",
            ("%d consigned part(s) bought at Digi-Key and sent to JLCPCB" % sum(c["n"] for c in cons_lines)) if cons_lines
            else "nothing consigned: every part from JLCPCB's shelf"), "",
         "## The three buckets", "",
         "| where | what | cost |", "|---|---|--:|",
         "| **JLCPCB** | %d bare boards: %s | %s |" % (boards, pcb_how, money(pcb)),
         "| | confirm production file | %s |" % money(confirm)]
    for k, (v, how) in A.items():
        L.append("| | %s | %s |" % (how, money(v)))
    L += ["| | their parts: %d BOM lines, %d placements a board, for %d boards with attrition, x %.4f | %s |"
          % (len(supplied), sum(r["n"] for r in supplied), assembled, F["parts_markup"], money(parts)),
          "| | **goods before duty and shipping** | **%s** |" % money(goods),
          "| | US duty, %.0f %% of the goods, collected under DDP | %s |" % (F["duty"] * 100, money(duty)),
          "| | shipping, UPS Express Saver DDP | %s-%s |" % (money(CE.SHIPPING[0]), money(CE.SHIPPING[1])),
          "| | **JLCPCB total** | **%s-%s** |" % (money(jlc[0]), money(jlc[1])),
          ("| **Digi-Key** | the consigned parts (CONSIGNMENT.md): %s, plus %.1f %% tax and %s shipping | **%s** |"
           % (money(dk_parts), CE.DIGIKEY_TAX * 100, money(CE.DIGIKEY_SHIPPING), money(dk_total))) if cons_lines
          else "| **Digi-Key** | nothing consigned (CONSIGNMENT.md): every part is on JLCPCB's shelf | **%s** |" % money(0.0),
          "| | shipping a consignment to JLCPCB | %s-%s |" % (money(consign_ship[0]), money(consign_ship[1])),
          "| **other** | the bench and the field (mfg/cost_estimate.py's list) | **%s-%s** |" % (money(other[0]), money(other[1])),
          "| | **everything** | **%s-%s** |" % (money(jlc[0] + dk_total + consign_ship[0] + other[0]),
                                                 money(jlc[1] + dk_total + consign_ship[1] + other[1])), "",
          "An assembled board: about %s of the JLCPCB goods%s.  The range on the bare "
          "boards moves the goods from %s to %s." % (money(goods / assembled), ", plus its share of the consignment" if cons_lines else "",
                                                     money(goods - pcb + pcb_lo), money(goods - pcb + pcb_hi)), ""]
    L += ["## Per-part fees: Basic, Preferred, Extended", "",
          "| library | distinct parts | placements a board |", "|---|--:|--:|",
          "| Basic | %d | %d |" % (len(basic), sum(r["n"] for r in basic)),
          "| Preferred | %d | %d |" % (len(pref), sum(r["n"] for r in pref)),
          "| **Extended** | **%d** | %d |" % (len(ext), sum(r["n"] for r in ext)),
          "| consigned | %d | %d |" % (len(cons_lines), sum(c["n"] for c in cons_lines)), "",
          "Feeder loading is the largest assembly fee after the setup: %d Extended codes x %s = %s.  Every value merged "
          "into another saves %s." % (len(ext), money(F["feeder_per_extended"]), money(A["feeder"][0]), money(F["feeder_per_extended"])), "",
          "The %d distinct Extended parts: %s." % (len(ext), ", ".join("%s (%s)" % (r["code"], r["model"]) for r in ext)), ""]
    flags = ["The bare boards are the least certain line (%s to %s): read the price off JLCPCB's cart"
             % (money(pcb_lo), money(pcb_hi))]
    for r in sorted(supplied, key=lambda r: -r["unit"] * r["order"])[:6]:
        if r["unit"] * r["order"] >= 10.0:
            flags.append("**%s %s** costs %s for the order (%d x %s)"
                         % (r["code"], r["model"], money(r["unit"] * r["order"]), r["order"], money(r["unit"])))
    for code in thin:
        r = next(r for r in rows if r["code"] == code)
        flags.append("**%s %s**: %d in stock against %d for this order: order soon, or it may run out"
                     % (code, r["model"], r["stock"], r["order"]))
    for r in rows:
        if r.get("short"):
            flags.append("**" + r["short"] + "**")
    flags += fallback_text(assembled, rows)
    flags.append("Not in the total: baking the moisture-sensitive parts (the QFNs are MSL 3; about $7.50 if ticked), "
                 "shipping, and duty beyond the 35 %")
    L += ["## What to look at", ""] + ["- " + f for f in flags] + [""]
    L += ["## Parts (%d BOM lines; the consigned ones at the end)" % len(rows), "",
          "| LCSC | part | a board | ordered | library | unit | line | stock | left after | asked |",
          "|---|---|--:|--:|---|--:|--:|--:|--:|---|"]
    for r in sorted(rows, key=lambda r: (bool(r["consigned"]), -r["unit"] * r["order"], r["code"])):
        L.append("| %s | %s (%s) | %d | %d | %s | %s | %s | %s | %s | %s |"
                 % (r["code"], r["model"], "/".join(dict.fromkeys(c["value"] for c in r["comps"]))[:24], r["n"],
                    r["order"], r["lib"], "$%.4f" % r["unit"] if not r["consigned"] else "Digi-Key",
                    money(r["unit"] * r["order"]) if not r["consigned"] else "-", "{:,}".format(r["stock"]),
                    "{:,}".format(r["stock"] - r["order"]) if not r["consigned"] else "-", r["asked"][:16].replace("T", " ")))
    L += ["", "\"ordered\" is what JLCPCB charges for: the placements on %d boards plus its attrition (`lossNumber`) or "
          "minimum purchase, at the price break for that quantity; for a consigned line it is what we send (CONSIGNMENT.md).  "
          "A Preferred part is an Extended part JLCPCB keeps on its machines." % assembled, ""]
    last = os.path.join(ROOT, "build", "cost.json")
    if os.path.exists(last):
        try:
            c = json.load(open(last))
            L += ["`mfg/cost_estimate.py`'s last run (build/COST_ESTIMATE.md) put the JLCPCB goods at %s (boards %s, assembly "
                  "%s, parts %s); this release %s.  The two share the fees, the prices and the pad count, so they "
                  "differ only when the prices were asked at different times."
                  % (money(c["pcb"][1] + c["assembly"] + c["parts"]), money(c["pcb"][1]), money(c["assembly"]),
                     money(c["parts"]), money(goods)), ""]
        except (KeyError, ValueError, TypeError):
            pass
    open(os.path.join(out, "COST_ESTIMATE.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    return dict(total=goods, pcb=pcb, pcb_lo=pcb_lo, pcb_hi=pcb_hi, parts=parts, ext=ext, asm=asm, smd=smd, tht=tht,
                sides=sides, duty=duty, jlc=jlc, dk=dk_total, n_lines=len(rows), n_supplied=len(supplied))


# JLCPCB's order form, field by field in the form's own order (CLAUDE_PCB.md section 8, as of
# 2026-10-09: the ECP5 board's mfg/make_fab.py lists, read off the page), and JLCPCB's defaults
# as the form opens.  A value that is not the default is marked, so that a late-night upload
# does not keep a default by mistake (Jason, 2026-10-09).  Placeholders in <> are filled from the
# board; nothing that the board decides is typed.
JLC_PCB_FORM = [
    ("PCB", "Base Material", "FR-4", ""),
    ("PCB", "Layers", "<layers>", "L1 RF and signals, L2 unbroken ground, L3 the supply pours, L4 signals under a ground fill (PLAN.md section 7)"),
    ("PCB", "Dimensions", "<dims>", "the board's outline, read from the board file's Edge.Cuts"),
    ("PCB", "PCB Qty", "<boards>", "JLCPCB's minimum; <assembled> of them assembled, the rest bare spares"),
    ("PCB", "Product Type", "Industrial/Consumer electronics", "the true one of the three (Aerospace, Medical): a research radio; duty is 35 %% whatever is chosen"),
    ("PCB Specifications", "Different Design", "1", ""),
    ("PCB Specifications", "Delivery Format", "Single PCB", "no panel; JLCPCB adds and removes its own assembly rails (Depanel below)"),
    ("PCB Specifications", "PCB Thickness", "1.6mm", "the stack-up below is JLCPCB's 1.6 mm 4-layer stack; if a Reminder dialog says its real thickness differs, answer Yes: nothing clamps the board's edge (the SMAs are through-hole, the socket is on the face) and the RF lines depend on the outer prepreg only"),
    ("PCB Specifications", "PCB Color", "Green", "green, not purple: Economic-compatible colour and the cheapest; the choice does not change the assembly (Standard is needed for the through-hole parts anyway)"),
    ("PCB Specifications", "Silkscreen", "White", ""),
    ("PCB Specifications", "Material Type", "FR4 TG135", "the 4-layer default; the board runs cool (about 7 W over 108 cm2) and nothing here needs TG155"),
    ("PCB Specifications", "Surface Finish", "ENIG", "not OSP: flat pads for the 0.5 mm QFNs with exposed pads, the reflow and the through-hole soldering after it (and the socket soldered at home), and the test pads probe well for years (CLAUDE_PCB.md section 8)"),
    ("PCB Specifications", "Gold Thickness", "1 U\"", "appears under ENIG; 2 U\" is for gold fingers and wearing contacts, and the board has none"),
    ("High-spec Options", "Outer Copper Weight", "1 oz", "the stack-up's; sim/rf_lines.py's line widths assume 35 um"),
    ("High-spec Options", "Inner Copper Weight", "0.5 oz", "the stack-up's"),
    ("High-spec Options", "Specify Layer Sequence", "No", "the Gerber names and the job file give the order"),
    ("High-spec Options", "Specify Stackup", "Yes: <stackup>", "the 50 ohm lines (sim/rf_lines.py: <rfw> mm CPWG with <rfgap> mm gaps over the L2 ground) are drawn for its 0.2104 mm of 7628 prepreg under L1.  It is JLCPCB's standard 4-layer 1.6 mm stack (no stack-up fee; 'No' builds the same), so choosing it only pins the prepreg.  If it is not offered, STOP and ask"),
    ("High-spec Options", "Impedance Control", "No requirement", "appears once a stack-up is chosen.  +-10%% obliges an impedance table in the zip or the order waits on an engineering question; 'No requirement' still holds width and spacing to +-20%% and the stack-up fixes the dielectric.  The RF lines are short against their edges (each a few mm to about 20 mm of <rfw> mm CPWG with <rfgap> mm gaps, sim/rf_lines.py; a quarter wave at 5.8 GHz is <qw> mm in this dielectric, and JLCPCB's own tool gives 0.345 mm for a 50 ohm microstrip on this stack), so a few ohms of mismatch costs a tenth of a dB"),
    ("High-spec Options", "Via Covering", "Tented or Plugged", "either is fine.  The form may say 'The Via Tented option is upgraded to Via Plugged for free' (rev A's order, 2026-10-17; its production record says 过孔塞油, plugged): take it.  Plugged ink in the exposed pads' thermal vias (0.45/0.25 mm) stops them wicking solder; tented they wick a little, which is also fine; no via-in-pad"),
    ("High-spec Options", "Min via hole size/diameter", "<minvia>", "the board's smallest via is <smallvia>: the option that covers a 0.25 mm drill.  The page may fill this in from the drill file; check that it agrees.  It may add a small charge for 4 layers; the cart says"),
    ("High-spec Options", "Board Outline Tolerance", "+-0.2mm (Regular)", ""),
    ("High-spec Options", "Confirm Production file", "Yes", "about $1: JLCPCB's production Gerbers come back to check before they make it"),
    ("High-spec Options", "Mark on PCB", "Remove Mark", "no order number printed; JLCPCB has added none by default since May 2026 and asks that JLCJLCJLCJLC not be put on the silkscreen<jlctext>"),
    ("High-spec Options", "Electrical Test", "Flying Probe Fully Test", ""),
    ("High-spec Options", "Gold Fingers", "No", ""),
    ("High-spec Options", "Castellated Holes", "No", ""),
    ("High-spec Options", "Press-Fit Hole", "No", ""),
    ("High-spec Options", "Edge Plating", "No", ""),
    ("High-spec Options", "Blind Slots", "No", ""),
    ("High-spec Options", "UL Marking", "No", ""),
    ("High-spec Options", "Backdrill", "No", ""),
    ("High-spec Options", "Humidity Indicator Card", "No", ""),
]
JLC_PCBA_FORM = [
    ("PCB Assembly", "PCB Assembly", "On", ""),
    ("PCB Assembly", "PCBA Type", "Standard", "the through-hole parts (the SMAs, the 2.54 mm headers), and any consigned ones: Economic takes neither"),
    ("PCB Assembly", "Assembly Side", "<sides>", "<sides_why>"),
    ("PCB Assembly", "PCBA Qty", "<assembled>", "of the <boards> boards; the other <spares> are bare spares"),
    ("PCB Assembly", "Edge Rails/Fiducials", "Added by JLCPCB", "the board carries no rails of its own<fiducials>; JLCPCB adds two rails with its fiducials, and Depanel below takes them off<overhang>"),
    ("PCB Assembly", "Confirm Parts Placement", "Yes", "free: the placement preview, read against PLACEMENT_CHECKS.txt (<unread> part numbers have predicted, unseen rotations)"),
    ("PCB Assembly", "Stencil Storage", "No", ""),
    ("PCB Assembly", "Fixture Storage", "No", ""),
    ("PCB Assembly", "Parts Selection", "By Customer (Self-Service)", "the BOM carries every LCSC code<ncons_how>"),
    ("Advanced Options", "Bake Components", "No", "the QFNs are MSL 3 and JLCPCB's parts come from its own dry storage; about $7.50 if ticked"),
    ("Advanced Options", "Photo Confirmation", "No", ""),
    ("Advanced Options", "Board Cleaning", "No", ""),
    ("Advanced Options", "Conformal Coating", "No", ""),
    ("Advanced Options", "Special stencil", "No", ""),
    ("Advanced Options", "Packaging", "Antistatic bubble film", "the default"),
    ("Advanced Options", "Depanel boards & edge rail before delivery", "Yes", "about $%.2f: the boards come without JLCPCB's rails; the board plugs onto the PYNQ-Z2 and the SMAs hang over its top edge, so its edges must be clean" % DEPANEL),
    ("Advanced Options", "Solder Paste", "High temp.", "the default, lead-free"),
    ("Advanced Options", "Flying Probe Test", "No", "the bare boards are already flying-probe tested"),
    ("Advanced Options", "Nitrogen reflow soldering", "No", "air reflow with SAC paste on ENIG wets 0.5 mm QFNs"),
    ("Advanced Options", "Function test", "No", ""),
    ("Advanced Options", "Assembly remark", "<remark>", "<remark_why>"),
    ("Stencil", "Stencil", "Off", "the assembly makes its own"),
    ("Files", "BOM", "BOM_JLCPCB.csv", "one line per LCSC code; the Note column flags the consigned lines"),
    ("Files", "CPL", CPL_UPLOAD, "not " + CPL_NATIVE + ", which is KiCad's own numbers for reference"),
]
# JLCPCB's defaults as the form opens (the ECP5 board's screenshots of 2026-10-09; Via Covering is
# "Tented" for 4 layers where the 6-layer form opens on "Epoxy Filled & Capped"; on some boards the form
# upgrades Tented to Plugged for free, so either is the default here and neither is flagged).
JLC_DEFAULTS = {
    "Layers": "2", "PCB Qty": "5", "Product Type": "Industrial/Consumer electronics", "Different Design": "1",
    "Delivery Format": "Single PCB", "PCB Thickness": "1.6mm", "PCB Color": "Green", "Silkscreen": "White",
    "Material Type": "FR4 TG135", "Surface Finish": "OSP", "Gold Thickness": "1 U\"", "Outer Copper Weight": "1 oz",
    "Inner Copper Weight": "0.5 oz", "Specify Layer Sequence": "No", "Specify Stackup": "No", "Impedance Control": "No requirement",
    "Via Covering": "Tented or Plugged", "Min via hole size/diameter": "0.3mm/(0.4/0.45mm)",
    "Board Outline Tolerance": "+-0.2mm (Regular)", "Confirm Production file": "No", "Mark on PCB": "Remove Mark",
    "Electrical Test": "Flying Probe Fully Test", "Gold Fingers": "No", "Castellated Holes": "No", "Press-Fit Hole": "No",
    "Edge Plating": "No", "Blind Slots": "No", "UL Marking": "No", "Backdrill": "No", "Humidity Indicator Card": "No",
    "PCB Assembly": "Off", "PCBA Type": "Economic", "Assembly Side": "Top Side", "PCBA Qty": "5",
    "Edge Rails/Fiducials": "Added by JLCPCB", "Confirm Parts Placement": "No", "Stencil Storage": "No", "Fixture Storage": "No",
    "Parts Selection": "By Customer (Self-Service)", "Bake Components": "No", "Photo Confirmation": "No",
    "Board Cleaning": "No", "Conformal Coating": "No", "Special stencil": "No", "Packaging": "Antistatic bubble film",
    "Depanel boards & edge rail before delivery": "No", "Solder Paste": "High temp.", "Flying Probe Test": "No",
    "Nitrogen reflow soldering": "No", "Function test": "No", "Assembly remark": "No", "Stencil": "Off",
}


def via_option(B):
    """JLCPCB's 'Min via hole size/diameter' option that covers the board's smallest via."""
    if not B["vias"]:
        return None, None
    v = min(B["vias"], key=lambda v: v[3])
    d = v[3]
    opt = ("0.3mm/(0.4/0.45mm)" if d >= 0.3 - 1e-6 else "0.25mm/(0.35/0.4mm)" if d >= 0.25 - 1e-6 else
           "0.2mm/(0.3/0.35mm)" if d >= 0.2 - 1e-6 else "0.15mm/(0.25/0.3mm)")
    return opt, v


def order_md(out, dims, boards, assembled, feat, B, cost, checks, n_unread, cons_lines):
    """ORDER_SETTINGS.md: what to choose on JLCPCB's order page, in the order it asks, every
    value that is not JLCPCB's default marked >> and in bold (CLAUDE_PCB.md section 8)."""
    w, h = dims
    opt, via = via_option(B)
    sides = cost["sides"]
    bottom_refs = cost.get("bottom", [])
    remark, over_txt = "", ""
    if feat["overhang"]:
        by_edge = collections.OrderedDict()
        for ref, edge, d in feat["overhang"]:
            by_edge.setdefault(edge, []).append((ref, d))
        over_txt = "; ".join("%s %s mm past the %s edge" % (
            ", ".join(sorted({r for r, _ in rs}, key=refkey)), "/".join("%.1f" % d for d in sorted({d for _, d in rs})), e)
            for e, rs in by_edge.items())
        remark = ("\"Parts hang over the board's edge: %s.  Put the assembly rails on the other edges or leave a gap "
                  "for them.\"" % over_txt)
    subs = {"<layers>": "%d" % len(B["copper"]), "<dims>": "%g x %g mm" % (w, h), "<boards>": str(boards),
            "<assembled>": str(assembled), "<spares>": str(boards - assembled), "<stackup>": STACKUP,
            "<rfw>": "%.2f" % RF.RF_W, "<rfgap>": "%.2f" % RF.RF_GAP, "<qw>": "%.1f" % RF.QUARTER_WAVE,
            "<minvia>": opt or "the default", "<smallvia>": ("%.2f mm across, %.2f mm drill" % (via[2], via[3])) if via else "(no vias)",
            "<sides>": "Both Sides" if len(sides) == 2 else ("Top Side" if sides == {"top"} else "Bottom Side"),
            "<sides_why>": ("parts on both sides: %s on the back, everything else on top" % ", ".join(bottom_refs))
                           if len(sides) == 2 else "every part on one side",
            "<fiducials>": ("; its %d fiducials (1 mm copper in 2 mm mask openings, at %s mm from the top-left corner) sit inside the outline"
                            % (len(feat["fiducials"]), ", ".join(feat["fiducials"]))) if feat["fiducials"] else ", nor fiducials",
            "<overhang>": (".  Parts hang over the edge (%s): the Assembly remark below says so" % over_txt) if over_txt else "",
            "<unread>": str(n_unread), "<ncons>": str(len(cons_lines)),
            "<ncons_how>": ("; the %d consigned lines are matched to the consigned stock registered beforehand (CONSIGNMENT.md)" % len(cons_lines)) if cons_lines else " and every line matches JLCPCB's shelf (nothing is consigned)",
            "<jlctext>": ("; this board still carries it: take it off" if feat["jlc_text"] else "; this board carries none"),
            "<remark>": remark or "No", "<remark_why>": ("the parts over the edge (PLACEMENT_CHECKS.txt)" if remark else "")}

    def fill(s):
        for k, v in subs.items():
            s = s.replace(k, v)
        return s.replace("%%", "%")
    L = ["# %s rev %s: JLCPCB order settings%s" % (BI.TITLE, BI.REV, " (DRAFT)" if draft() else ""), ""]
    if draft():
        L += ["**DRAFT:** %s.  Order once the build no longer says DRAFT." % draft(), ""]
    n_change = 0
    tables = []
    for title, form in (("The PCB", JLC_PCB_FORM), ("PCB Assembly", JLC_PCBA_FORM)):
        T = ["## " + title, ""]
        last = None
        for sec, field, value, why in form:
            if sec != last:
                if last is not None:
                    T.append("")
                T += ["### " + sec, "", "| field | choose | JLCPCB's default | why |", "|---|---|---|---|"]
                last = sec
            v = fill(value)
            d = JLC_DEFAULTS.get(field)
            change = d is not None and not v.startswith(d)
            n_change += change
            T.append("| %s%s | %s | %s | %s |" % (">> " if change else "", field, "**%s**" % v if change else v,
                                                  d if d is not None else "", fill(why)))
        tables += T + [""]
    L += ["Written by `mfg/make_release.py` on %s.  On jlcpcb.com, **Order now**, upload `%s_gerbers.zip`, then set the "
          "form top to bottom; the fields are in the form's own order (as of 2026-10-09, CLAUDE_PCB.md section 8).  "
          "**A row marked `>>` with its value in bold is NOT JLCPCB's default: change it, and do not leave the default "
          "named beside it.**  %d fields differ from the defaults.  Every dialog the form raises has its own row."
          % (datetime.date.today(), NAME, n_change), ""]
    L += tables
    L += ["Then upload `BOM_JLCPCB.csv` and `" + CPL_UPLOAD + "` (not `" + CPL_NATIVE + "`).  Every BOM line carries its "
          "LCSC code; %s; nothing should be left unmatched.  In the placement preview, "
          "go through `PLACEMENT_CHECKS.txt` before confirming."
          % (("the %d consigned lines (Note column) must match the consigned stock registered beforehand (CONSIGNMENT.md), "
              "the rest JLCPCB's shelf stock" % len(cons_lines)) if cons_lines else "every line matches JLCPCB's shelf stock (nothing is consigned)"), "",
          "**Shipping:** UPS Express Saver (DDP): a US individual must ship DDP, and JLCPCB collects the duty (35 %% of "
          "the PCBs and assembly).  Lead time: 4-layer PCBs 2-5 days, Standard assembly at least 4 more (+1 for the "
          "through-hole parts)%s, then 4-5 business days to the door." % (", the consignment's post before that" if cons_lines else ""), ""]
    L += ["## Numbers behind the choices", "",
          "- Board %.1f x %.1f mm, %d copper layers, %.1f mm; smallest track %s; %d vias%s."
          % (w, h, len(B["copper"]), B["thickness"] or 0.0, ("%.3f mm" % min(B["widths"])) if B["widths"] else "(none)",
             len(B["vias"]), (", all %.2f/%.2f mm" % (via[2], via[3])) if via and len({(v[2], v[3]) for v in B["vias"]}) == 1 else ""),
          "- Assembly: %d placements a board on %d BOM lines (%d Extended, %d consigned), %d SMD pads and %d through-hole "
          "joints a board, on %s." % (cost["n_place"], cost["n_lines"], len(cost["ext"]), len(cons_lines), cost["smd"],
                                      cost["tht"], " and ".join(sorted(sides, reverse=True))),
          "- Mounting holes: %s." % (", ".join("%s %.1f mm at (%.1f, %.1f)" % (r, d, x, y) for r, x, y, d in feat["holes"]) or "none"),
          "- Estimate: %s of goods before duty and shipping, JLCPCB %s-%s all in, Digi-Key %s (COST_ESTIMATE.md)."
          % (money(cost["total"]), money(cost["jlc"][0]), money(cost["jlc"][1]), money(cost["dk"]))]
    L += checks
    L += ["", "Sources: the ECP5-2ADC-2DAC order of 2026-10-09 (the form's fields and defaults, its cart's fees), "
          "jlcpcb.com/help/article/pcb-assembly-price, /capabilities/pcb-assembly-capabilities, "
          "/help/article/How-to-mark-on-PCB (2026-05-22), /help/article/us-tariff-policy-faq (2026-09-09).  The form "
          "changes; when a screenshot shows it has, update the lists in mfg/make_release.py and this date."]
    open(os.path.join(out, "ORDER_SETTINGS.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")


# ---------------------------------------------------------------------------------------
def drc_gate(pcb, skip):
    """DRC must be clean on the shipped file: tools/pcb_check.py (KiCad's DRC at every
    severity, with schematic parity) on the project's board; kicad-cli on a test copy."""
    if skip:
        return "NOT RUN (--skip-drc: a test, not a release)"
    if os.path.abspath(pcb) != os.path.abspath(BI.PCB):
        report = os.path.join(BI.SCRATCH, "drc_test.json")
        os.makedirs(BI.SCRATCH, exist_ok=True)
        for ext in (".kicad_pro", ".kicad_dru"):       # the project's rules beside the copy, or KiCad applies its defaults
            src, dst = os.path.splitext(BI.PCB)[0] + ext, os.path.splitext(pcb)[0] + ext
            if os.path.exists(src) and not os.path.exists(dst):
                shutil.copy(src, dst)
        kienv.run_cli(["pcb", "drc", "--format", "json", "--severity-all", "--units", "mm", "-o", report, pcb], ok=(0, 5))
    else:
        report = os.path.join(BI.CHECKS, "drc.json")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "pcb_check.py")], capture_output=True, text=True)
        sys.stdout.write(r.stdout[-2000:])
        if not os.path.exists(report) or os.path.getmtime(report) < os.path.getmtime(pcb):
            raise Gate("tools/pcb_check.py left no DRC report newer than the board file")
    d = json.load(open(report))
    n = {k: len(d.get(k, [])) for k in ("violations", "unconnected_items", "schematic_parity")}
    if any(n.values()):
        raise Gate("DRC is not clean: %d violations, %d unconnected, %d parity (tools/pcb_check.py)"
                   % (n["violations"], n["unconnected_items"], n["schematic_parity"]))
    return "0 violations, 0 unconnected, 0 parity"


def launch_gate(gdir):
    """The 5.8 GHz launches in the plotted gerbers: tools/launch_check.py (no inner rings at the SMA pins, the
    planes LAUNCH_R clear of them, In1 relieved under the RF pads).  Prompt 32."""
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "launch_check.py"), gdir], capture_output=True, text=True)
    sys.stdout.write(r.stdout[-2500:])
    if r.returncode:
        raise Gate("the RF launches are not as designed in the gerbers (tools/launch_check.py):\n    " + r.stdout.strip().split("\n")[-1])
    return r.stdout.strip().split("\n")[-1]


def label_gate(pcb, skip):
    """The connectors' labels on the shipped file: tools/label_check.py (every name printed, its own,
    big enough; each row one relation; the limits; the headers' pin labels).  Response 15."""
    if skip or os.path.abspath(pcb) != os.path.abspath(BI.PCB):
        return "NOT RUN (a test copy)"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "label_check.py")], capture_output=True, text=True)
    sys.stdout.write(r.stdout[-3000:])
    report = os.path.join(BI.CHECKS, "labels.json")
    if not os.path.exists(report) or os.path.getmtime(report) < os.path.getmtime(pcb):
        raise Gate("tools/label_check.py left no report newer than the board file")
    d = json.load(open(report))
    if d["violations"]:
        raise Gate("the connectors' labels break the row rule (tools/label_check.py):\n    " + "\n    ".join(d["violations"]))
    return "%d connectors, %d rows, 0 violations%s" % (d["connectors"], len(d["rows"]),
                                                       "; %d limit(s) left off on record" % len(d.get("exempt", [])) if d.get("exempt") else "")


def scan_paths(out):
    bad = []
    for dp, _, fns in os.walk(out):
        for fn in fns:
            p = os.path.join(dp, fn)
            data = open(p, "rb").read()
            if fn.endswith(".zip"):
                with zipfile.ZipFile(p) as z:
                    data = b"".join(z.read(n) for n in z.namelist())
            m = FORBIDDEN.search(data)
            if m:
                bad.append("%s names a place on this machine (%r)" % (os.path.relpath(p, out), m.group(0)))
    return bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--boards", type=int, default=5, help="bare boards ordered (JLCPCB's minimum, 5)")
    ap.add_argument("--assembled", type=int, default=2, help="of them, assembled by JLCPCB (their minimum, 2)")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--pcb", default=BI.PCB)
    ap.add_argument("--netlist", default=BI.NETLIST)
    ap.add_argument("--out", default=BI.RELEASE)
    ap.add_argument("--skip-drc", action="store_true", help="testing only")
    ap.add_argument("--accept-hole", action="append", default=[], help="testing only: an LCSC code")
    a = ap.parse_args(argv)
    test = os.path.abspath(a.pcb) != os.path.abspath(BI.PCB) or os.path.abspath(a.out) != os.path.abspath(BI.RELEASE)
    if (a.skip_drc or a.accept_hole) and not test:
        raise SystemExit("--skip-drc and --accept-hole are for a test board (--pcb, --out), never the release")
    if a.assembled > a.boards or a.assembled < 1:
        raise SystemExit("--assembled must be between 1 and --boards")
    accepted = dict(HOLE_ACCEPTED, **{c: "a test" for c in a.accept_hole})
    stage = os.path.join(BI.SCRATCH, "release_stage") if not test else os.path.abspath(a.out) + ".stage"
    scratch = os.path.join(BI.SCRATCH, "release_scratch")
    for d in (stage, scratch):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    failures = []

    # ---- the rules this release leans on still hold -----------------------------------
    if jlc_rotation.self_test():
        failures.append("mfg/jlc_rotation.py's bottom-side rule no longer satisfies the readings it came from")

    # ---- the netlist and the parts -----------------------------------------------------
    if not os.path.exists(a.netlist):
        return finish(["no netlist at %s (run the build's erc step)" % os.path.relpath(a.netlist, ROOT)], stage, a, test)
    comps = classify(read_netlist(a.netlist))
    nocode = [c["ref"] for c in comps if c["cls"] == "nocode"]
    if nocode:
        failures.append("components with no LCSC code that gen/parts.py does not call 'not a part' or consigned: %s"
                        % ", ".join(sorted(nocode, key=refkey)))
    placed = [c for c in comps if c["cls"] == "placed"]
    cons = [c for c in comps if c["cls"] == "consigned"]
    fitted = placed + cons                                     # everything JLCPCB puts on the board
    rows, bad, thin = parts_report(fitted, a.assembled, a.refresh)
    failures += bad
    write_bom(rows, stage)
    cons_lines = consignment_lines(rows, a.assembled)
    missing_dk = [c["key"] for c in cons_lines if not c["digikey"]]
    if missing_dk:
        failures.append("consigned parts without a Digi-Key number in gen/parts.py: %s" % ", ".join(missing_dk))
    if failures:
        return finish(failures, stage, a, test)

    # ---- the board ----------------------------------------------------------------------
    if not os.path.exists(a.pcb):
        return finish(["no board file at %s" % os.path.relpath(a.pcb, ROOT)], stage, a, test)
    B, fps, extra, bad = board_parts(a.pcb, comps)
    failures += bad
    if B["copper"] != COPPER:
        failures.append("the board's copper layers are %s, not %s" % (B["copper"], COPPER))
    if B["thickness"] is not None and abs(B["thickness"] - THICKNESS) > 0.01:
        failures.append("the board is %.2f mm thick, not %.1f" % (B["thickness"], THICKNESS))
    if not B["filled"]:
        failures.append("the board file has no filled zones: the gerbers would ship without the pours")
    box = outline_box(B)
    if not box:
        failures.append("the board has no Edge.Cuts outline")
    else:
        dims = (round(box[2] - box[0], 2), round(box[3] - box[1], 2))
        if abs(dims[0] - PL.BOARD["w"]) > 0.05 or abs(dims[1] - PL.BOARD["h"]) > 0.05:
            failures.append("the board's outline is %g x %g mm, gen/placement.py plans %g x %g"
                            % (dims[0], dims[1], PL.BOARD["w"], PL.BOARD["h"]))
    if not B["aux"]:
        failures.append("the board has no drill/place origin (aux_axis_origin): the gerbers and the CPL would not agree")
    if failures:
        return finish(failures, stage, a, test)
    try:
        drc = drc_gate(a.pcb, a.skip_drc)
        labels = label_gate(a.pcb, a.skip_drc)
    except Gate as e:
        return finish([str(e)], stage, a, test)
    feat = board_features(B, fps, box, parts={c["ref"] for c in fitted})

    # ---- does every ordered part fit its copper? -----------------------------------------
    nbad, fp_lines = FC.report(os.path.join(stage, "BOM_JLCPCB.csv"), a.refresh, False, pcb=a.pcb,
                               bom_label=os.path.join(os.path.basename(a.out), "BOM_JLCPCB.csv"))
    open(os.path.join(stage, "FOOTPRINT_CHECK.txt"), "w", encoding="utf-8").write("\n".join(fp_lines) + "\n")
    holes, code = [], ""
    for l in fp_lines:
        m = re.match(r"  (?:ok|!!) (C\d+)", l)
        if m:
            code = m.group(1)
        if l.startswith("       HOLE") and code not in accepted:
            holes.append("%s: %s" % (code, l.strip()))
    if holes:
        failures.append("a part wants a hole the board does not have (FOOTPRINT_CHECK.txt; once a person has compared "
                        "the maker's drawing with JLCPCB's, HOLE_ACCEPTED in mfg/make_release.py):\n    "
                        + "\n    ".join(holes))
    refs = [l.strip() for l in fp_lines if l.startswith("  ?  ")]
    if refs:
        failures.append("footprint_check.py could not check: " + "; ".join(refs))
    fits = FC.FITS
    # parts JLCPCB has no drawing of: their preview shows a checkerboard, nothing predicts a correction, and
    # the part goes in from the plain CPL (CLAUDE_PCB.md section 8, "Preview checkerboards")
    undrawn, code = set(), ""
    for l in fp_lines:
        m = re.match(r"  (?:ok|!!) (C\d+)", l)
        if m:
            code = m.group(1)
        if l.startswith("       NOFP"):
            undrawn.add(code)

    # ---- the CPL ----------------------------------------------------------------------------
    preds = predictions(fitted, fps, fits)
    for c in fitted:
        if c["lcsc"] in undrawn:
            preds[(c["lcsc"], fps[c["ref"]]["short"])] = (None, "JLCPCB has NO DRAWING of this part: the preview shows a "
                                                           "checkerboard, their engineer draws it from the datasheet at "
                                                           "review, and the CPL carries KiCad's angle")
    cpl, moved = {}, []
    for c in fitted:
        fp = fps[c["ref"]]
        side = "bottom" if fp["layer"].startswith("B.") else "top"
        X, Y = to_cpl(fp["at"][0], fp["at"][1], B["aux"])
        native = dict(X=X, Y=Y, side=side, R=round(fp["at"][2] % 360.0, 4))
        fit = fits.get((c["lcsc"], side == "bottom", fp["short"]))
        sx, sy = datum_shift(fp, fit)
        if sx or sy:
            moved.append((c["ref"], round(sx, 3), round(-sy, 3)))
        pred = preds.get((c["lcsc"], fp["short"]), (None, ""))[0]
        R = jlc_rotation.cpl_rotation(fp["at"][2], side, fp["short"], c["lcsc"], predicted=pred)
        cpl[c["ref"]] = dict(native=native, jlc=dict(X=X + sx, Y=Y - sy, side=side, R=R), code=c["lcsc"])
    # a part of three or more pads must not ship at KiCad's bare angle (CLAUDE_PCB.md section 8:
    # the ECP5 board's SMAs and Pmod sockets did, and lay the wrong way in the preview)
    unrotated = collections.OrderedDict()
    for c in fitted:
        fp = fps[c["ref"]]
        key = (c["lcsc"], fp["short"])
        if fp["short"] in jlc_rotation.ROTATION_NA or len(pad_spots(fp)) < 3 or c["lcsc"] in undrawn:
            continue
        corr, conf, _ = jlc_rotation.correction(fp["short"], c["lcsc"])
        if conf == "none" and preds.get(key, (None, ""))[0] is None:
            unrotated.setdefault(key, []).append(c["ref"])
    for (code, short), rs in unrotated.items():
        failures.append("no rotation for %s %s (%s): %s.  Read the body's direction off JLCPCB's drawing against "
                        "KiCad's courtyard and put it in mfg/jlc_rotation.py as 'predicted'"
                        % (code, short, " ".join(rs), preds.get((code, short), (None, "no prediction"))[1]))
    n_unread = sum(1 for (code, short) in {(c["lcsc"], fps[c["ref"]]["short"]) for c in fitted}
                   if short not in jlc_rotation.ROTATION_NA and not jlc_rotation.checked(short, code))
    jlc_rows = {ref: v["jlc"] for ref, v in cpl.items()}
    sim_bad, sim_ok = simulate(fitted, fps, fits, jlc_rows, B["aux"])
    failures += sim_bad
    failures += pos_export_check(a.pcb, {ref: v["native"] for ref, v in cpl.items()}, scratch)
    if failures:
        return finish(failures, stage, a, test)
    write_cpl(cpl, stage)
    placement_checks(stage, fitted, fps, cpl, preds, moved, sim_ok, sim_bad, B["aux"], feat)
    try:
        zpath, gfiles = export_gerbers(a.pcb, stage)
    except Gate as e:
        return finish([str(e)], stage, a, test)
    try:
        launches = launch_gate(os.path.join(stage, "gerbers"))
    except Gate as e:
        return finish([str(e)], stage, a, test)
    gb = gerber_box(os.path.join(stage, "gerbers", "%s-Edge_Cuts.gbr" % os.path.splitext(os.path.basename(a.pcb))[0]))
    want = (to_cpl(box[0], box[3], B["aux"]), to_cpl(box[2], box[1], B["aux"]))
    if not gb or max(abs(gb[0] - want[0][0]), abs(gb[1] - want[0][1]), abs(gb[2] - want[1][0]),
                     abs(gb[3] - want[1][1])) > 0.05:
        failures.append("the Edge.Cuts gerber spans %s, the board's outline %s in the CPL's frame" % (gb, want))

    # ---- the rest of the folder ----------------------------------------------------------------
    write_excluded(comps, extra, stage)
    write_consignment(cons_lines, a.assembled, stage, rows)
    cost = cost_md(stage, rows, fps, a.boards, a.assembled, dims, thin, cons_lines)
    cost.update(n_place=len(fitted), bottom=sorted((c["ref"] for c in fitted if cpl[c["ref"]]["jlc"]["side"] == "bottom"), key=refkey))
    checks = ["- Checks passed: DRC %s; the connectors' labels %s; the RF launches in the gerbers (%s); %d filled zone polygons; every netlist part on the board; every code matched "
              "(gen/parts.py's words, the value, the package, the MPN) and in stock; no ordered part wants a hole%s; "
              "every part of three or more pads has a read or predicted rotation; the CPL agrees with KiCad's position "
              "export, and JLCPCB's drawings placed by it land on our pads (%d parts, %s)."
              % (drc, labels, launches, B["filled"], " (accepted: %s)" % ", ".join(sorted(accepted)) if accepted else "", len(sim_ok),
                 " and ".join(sorted(cost["sides"], reverse=True)) + (" side" if len(cost["sides"]) == 1 else " sides"))]
    order_md(stage, dims, a.boards, a.assembled, feat, B, cost, checks, n_unread, cons_lines)
    failures += scan_paths(stage)
    return finish(failures, stage, a, test, rows=rows, cost=cost, moved=moved, n_unread=n_unread, drc=drc, cons_lines=cons_lines)


def finish(failures, stage, a, test, rows=None, cost=None, moved=(), n_unread=0, drc="", cons_lines=()):
    if failures:
        print("RELEASE FAILED: %d gate(s); %s was not changed" % (len(failures), a.out if test else os.path.relpath(a.out, ROOT)))
        for f in failures:
            print("  - " + f)
        return 1
    if os.path.isdir(a.out):
        shutil.rmtree(a.out)
    shutil.move(stage, a.out)
    ext = cost["ext"]
    print("release -> %s%s" % (os.path.relpath(a.out, ROOT) if not test else a.out, "  (TEST)" if test else ""))
    print("  %d BOM lines (%d consigned), %d placements a board on %s, %d distinct Extended parts: %s"
          % (len(rows), len(cons_lines), cost["n_place"], " and ".join(sorted(cost["sides"], reverse=True)), len(ext),
             " ".join(r["code"] for r in ext)))
    print("  %d SMD pads and %d through-hole joints a board; DRC %s" % (cost["smd"], cost["tht"], drc))
    print("  CPL: %d placement(s) moved to JLCPCB's origin%s; %d part number(s) with rotations not yet seen in a preview "
          "(PLACEMENT_CHECKS.txt)" % (len(moved), " (%s)" % ", ".join(r for r, _, _ in moved) if moved else "", n_unread))
    print("  consigned (CONSIGNMENT.md): %s" % ("; ".join("%s x%d" % (c["mpn"], c["qty"]) for c in cons_lines) or "nothing"))
    print("  estimate: JLCPCB goods %s (boards %s, assembly %s, parts %s), %s-%s with duty and shipping; Digi-Key %s "
          "(COST_ESTIMATE.md)" % (money(cost["total"]), money(cost["pcb"]), money(cost["asm"] + CE.FEES["confirm_production"]),
                                  money(cost["parts"]), money(cost["jlc"][0]), money(cost["jlc"][1]), money(cost["dk"])))
    if draft():
        print("  DRAFT: %s" % draft())
    return 0


if __name__ == "__main__":
    sys.exit(main())
