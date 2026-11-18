#!/usr/bin/env python3
"""What Jason's usual order costs ("5 PCBs, 2 assembled"), in the three places the money goes:
JLCPCB (the boards, the assembly, their parts, duty and shipping), Digi-Key (the consigned parts)
and the rest (the bench and the field).

    python3 mfg/cost_estimate.py [--boards 5] [--assembled 2] [--refresh]

Parts come live from JLCPCB's parts API (tools/jlc_api.py, cached with the time asked), with
their attrition and minimum purchase at that quantity's price break.  The fees are JLCPCB's cart
as the ECP5-2ADC-2DAC order calibrated it on 2026-10-09 (CLAUDE_PCB.md section 8: components x
1.0066; feeder loading $2.70 per Extended code; SMT $0.0017 a pad + $1.50 a board; through-hole
$0.0157 a joint; Standard PCBA setup $51.50, stencil $16.54 both sides, fixture $16.54,
hand-soldering labour $3.61, packaging $0.51); the bare boards are a model with a range until the
cart gives the number.  Writes build/COST_ESTIMATE.md.
"""
import argparse, collections, datetime, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "gen")):
    sys.path.insert(0, p)
import jlc_api
import board_info as BI
import placement as PL
from parts import PARTS, consigned, fallback
from sexp import parse, kids, kid, val

FEES = dict(                                   # ECP5's cart, 2026-10-09 (CLAUDE_PCB.md section 8)
    parts_markup=1.0066, feeder_per_extended=2.70, smt_per_pad=0.0017, smt_per_board=1.50, tht_per_joint=0.0157,
    setup=51.50, stencil_both=16.54, fixture=16.54, hand_solder_labour=3.61, packaging=0.51, special=0.12,
    confirm_production=1.05, duty=0.35,
    depanel=2.32,                              # "Depanel boards & edge rail before delivery": the release's form says Yes
)
# the bare boards: 4 layers, ENIG, green, JLC04161H-7628 (the default 4-layer stack, no stack-up
# fee), no impedance requirement.  GPiBridge's cart (2026-10-06): $24.80 for 5 of 60 x 25.5 mm; the
# area part at JLCPCB's published $70.6 per m2 for 4 layers and five times it for a small order.
PCB_MODEL = dict(ref_price=24.80, ref_area_cm2=15.3, ref_boards=5, per_m2_low=70.6, per_m2_high=350.0, enig_extra=(0.0, 20.0))
SHIPPING = (25.0, 40.0)                        # UPS Express Saver DDP to California, one parcel

# The parts with a Digi-Key consignment (gen/parts.py consign=): since Prompt 31 all of them are JLCPCB shelf
# parts first, consigned only when the shelf cannot cover the order on the day (make_release.py decides on the
# live stock; this estimate decides the same way).  A consigned line is the placements on the assembled boards
# plus CONSIGN_SPARES: JLCPCB's "attrition on consigned parts" and one for the bench, pieces that are never
# used, so they are part of a consignment's true cost (Jason, Prompt 31), with the shipment to Shenzhen.
DIGIKEY = {k: dict(unit=p["consign"]["dk_unit"], seen=p["consign"]["seen"]) for k, p in {**consigned(), **fallback()}.items()}
CONSIGN_SPARES = 2                             # per line: JLCPCB's attrition and one for the bench (Jason)
DIGIKEY_SHIPPING, DIGIKEY_TAX, CONSIGN_SHIP = 8.0, 0.095, (35.0, 60.0)     # CA sales tax; USPS Priority International to FedEx


def consignment_cost(lines, assembled):
    """What a consignment of these gen/parts.py keys really costs over buying the same parts on JLCPCB's shelf
    (Jason, Prompt 31): the pieces for the boards at Digi-Key's price, the CONSIGN_SPARES a line that are never
    used, tax and Digi-Key's shipping, and the shipment to Shenzhen; against the shelf's price for the pieces
    alone (JLCPCB's attrition on its own parts is 0 for these chips).  Returns (consign_lo, consign_hi, shelf)."""
    dk = sum(DIGIKEY[k]["unit"] * (assembled + CONSIGN_SPARES) for k in lines)
    shelf = sum((PARTS[k]["consign"].get("jlc_unit") or 0.0) * assembled for k in lines)
    cons = dk * (1 + DIGIKEY_TAX) + DIGIKEY_SHIPPING
    return cons + CONSIGN_SHIP[0], cons + CONSIGN_SHIP[1], shelf

OTHER = [
    ("SMA attenuators: 30 dB (loopback), 20 dB x 2 (in front of the PA modules)", 30.0, 50.0),
    ("U.FL-to-SMA pigtails, 10", 12.0, 18.0),
    ("MMCX-to-SMA leads, 5 (REF OUT and the four MMCX monitors: ERR, VC, TRIG IN, I SLOW; Response 10)", 12.5, 20.0),
    ("5.8 GHz whips, SMA, x 4", 16.0, 24.0),
    ("SMA leads: 3 x 150 mm, 2 x 1 m; 50 ohm terminations x 2", 20.0, 35.0),
    ("USB-C PD power banks 5 V / 3 A x 2 (the amplifiers in the field)", 40.0, 60.0),
    ("M3 standoffs and screws (nylon kit)", 6.0, 10.0),
    ("a heatsink or fan for the 2 W PA module (it dissipates about 9 W)", 5.0, 12.0),
    ("a second PA ($29 with shipping) and LNA ($13) module for the far end, when the tests demand", 0.0, 42.0),
]


# soldered at home, not by JLCPCB (mfg/make_release.py HAND_SOLDER says why; Jason, Prompt 15: the Pi socket
# when fitting it costs more than a few dollars).  J302 is the only part on the back, so the order is one-sided.
HAND_SOLDER_REFS = ("J302",)


def pad_counts(fp):
    """(SMD pads, through-hole joints) of a footprint as the board has it (footprint_check.read_board_full):
    each pad by its own type, so an edge SMA's SMD centre pad and its through-hole legs both count.  A plated
    hole numbered like an SMD pad is a via in that pad (an exposed pad's thermal vias), not a lead.  The one
    count for the estimate here and the release's (mfg/make_release.py)."""
    smd = {p["number"] for p in fp["pads"] if p["type"] == "smd"}
    return (sum(1 for p in fp["pads"] if p["type"] == "smd" and p["number"]),
            sum(1 for p in fp["pads"] if p["type"] == "thru_hole" and p["number"] not in smd and p["number"]))


def read_netlist():
    doc = parse(open(BI.NETLIST, encoding="utf-8").read())[0]
    out = {}
    for c in kids(kid(doc, "components"), "comp"):
        ref = val(kid(c, "ref"))
        fields = {}
        fl = kid(c, "fields")
        for f in kids(fl, "field") if fl else []:
            if len(f) > 2:
                fields[val(kid(f, "name"))] = val(f, 2)
        props = {}
        for p in kids(c, "property"):
            nm = kid(p, "name")
            if nm:
                props[val(nm)] = ""
        fp = val(kid(c, "footprint"))
        if not fp or fp.endswith(":"):
            continue
        out[ref] = dict(value=val(kid(c, "value")), fp=fp.split(":")[-1], lcsc=fields.get("LCSC", ""), mpn=fields.get("MPN", ""), dnp="dnp" in props)
    return out


def money(x):
    return "$%.2f" % x


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", type=int, default=5)
    ap.add_argument("--assembled", type=int, default=2)
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args(argv)
    comps = read_netlist()
    fps = PL.load_footprints()
    consign_keys = {p["mpn"]: k for k, p in consigned().items()}
    fallback_keys = {p["lcsc"]: k for k, p in fallback().items()}
    placed = {r: c for r, c in comps.items() if c["lcsc"] and not c["dnp"] and r not in HAND_SOLDER_REFS}
    # the sides JLCPCB assembles: from the placement (build/placement.json), per placed part
    import json
    place = json.load(open(os.path.join(ROOT, "build", "placement.json")))["place"]
    sides = {"bottom" if (place.get(r) or [0, 0, 0, "F"])[3] == "B" else "top" for r in placed}
    cons = {r: c for r, c in comps.items() if not c["lcsc"] and not c["dnp"] and c["mpn"] in consign_keys}
    by_code = collections.defaultdict(list)
    for r, c in placed.items():
        by_code[c["lcsc"]].append(r)
    rows = []
    thin = []
    shelf_short = []                            # fallback parts JLCPCB's shelf cannot cover: consigned instead
    for code, refs in sorted(by_code.items()):
        part, asked = jlc_api.by_code(code, refresh=a.refresh)
        if not part:
            rows.append(dict(code=code, refs=refs, n=len(refs), order=0, unit=0.0, line=0.0, lib="?", stock=0, model=comps[refs[0]]["value"], asked=asked or ""))
            continue
        need = len(refs) * a.assembled
        if code in fallback_keys and int(part.get("stockCount") or 0) < jlc_api.order_qty(part, need):
            shelf_short.append((fallback_keys[code], code, int(part.get("stockCount") or 0), jlc_api.order_qty(part, need)))
            for r in refs:
                cons[r] = comps[r]
            continue
        order = jlc_api.order_qty(part, need)
        unit = jlc_api.unit_price(part, order)
        lib = jlc_api.library_type(part)
        stock = int(part.get("stockCount") or 0)
        if stock < order * 3:
            thin.append((code, part.get("componentModelEn"), stock, order))
        rows.append(dict(code=code, refs=refs, n=len(refs), order=order, unit=unit, line=unit * order, lib=lib, stock=stock,
                         model=part.get("componentModelEn") or "", asked=asked or ""))
    parts_cost = sum(r["line"] for r in rows) * FEES["parts_markup"]
    ext = [r for r in rows if r["lib"] == "Extended"]
    # joints, from the board's own footprints
    import footprint_check as FC
    on_board = {fp["ref"]: fp for fp in FC.read_board_full(BI.PCB)["fps"]}
    smt_pads = tht_joints = 0
    for r in list(placed) + list(cons):
        if r in on_board:
            s_, t_ = pad_counts(on_board[r])
            smt_pads += s_
            tht_joints += t_
    F = FEES
    asm = dict(setup=F["setup"] / 2.0 * len(sides), stencil=F["stencil_both"] / 2.0 * len(sides), fixture=F["fixture"],
               feeder=F["feeder_per_extended"] * len(ext),
               smt=(F["smt_per_pad"] * smt_pads + F["smt_per_board"]) * a.assembled,
               tht=F["hand_solder_labour"] + F["tht_per_joint"] * tht_joints * a.assembled,
               packaging=F["packaging"], special=F["special"], confirm=F["confirm_production"], depanel=F["depanel"])
    asm_total = sum(asm.values())
    # the bare boards
    W, H = PL.BOARD["w"], PL.BOARD["h"]
    area = W * H / 100.0 * a.boards
    M = PCB_MODEL
    fixed = M["ref_price"] - M["per_m2_low"] * M["ref_area_cm2"] * M["ref_boards"] / 1e4
    pcb_lo = fixed + M["per_m2_low"] * area / 1e4 + M["enig_extra"][0]
    pcb_hi = fixed + M["per_m2_high"] * area / 1e4 + M["enig_extra"][1]
    pcb = (pcb_lo + pcb_hi) / 2
    jlc_goods = pcb + asm_total + parts_cost
    duty = F["duty"] * jlc_goods
    jlc_total = (jlc_goods + duty + SHIPPING[0], jlc_goods + duty + SHIPPING[1])
    # Digi-Key
    dk_lines = []
    for key, p in {**consigned(), **fallback()}.items():
        refs = [r for r, c in cons.items() if c["mpn"] == p["mpn"]]
        if not refs:
            continue
        qty = len(refs) * a.assembled + CONSIGN_SPARES
        unit = DIGIKEY[key]["unit"]
        dk_lines.append((key, p["mpn"], p["consign"].get("digikey", ""), len(refs), qty, unit, qty * unit, DIGIKEY[key]["seen"]))
    dk_parts = sum(l[6] for l in dk_lines)
    dk_total = dk_parts * (1 + DIGIKEY_TAX) + DIGIKEY_SHIPPING if dk_lines else 0.0
    consign_ship = CONSIGN_SHIP if dk_lines else (0.0, 0.0)
    other_lo, other_hi = sum(o[1] for o in OTHER), sum(o[2] for o in OTHER)
    # the report
    L = ["# %s rev %s: what the first order costs" % (BI.TITLE, BI.REV), "",
         "Written by `mfg/cost_estimate.py` on %s for %d bare boards, %d of them assembled by JLCPCB on the top "
         "(Standard PCBA for the through-hole SMAs and headers; the 2x20 socket on the back is soldered at home).  Parts: JLCPCB's parts API at the "
         "times in the table.  Fees: the ECP5-2ADC-2DAC cart of 2026-10-09 (CLAUDE_PCB.md section 8).  The bare boards and the "
         "shipping are estimates with a range; the cart replaces them." % (datetime.date.today(), a.boards, a.assembled), "",
         "## The three buckets", "",
         "| where | what | cost |", "|---|---|--:|",
         "| **JLCPCB** | %d bare boards %.0f x %.0f mm, 4 layers, ENIG: model %s-%s | %s |" % (a.boards, W, H, money(pcb_lo), money(pcb_hi), money(pcb)),
         "| | assembly: setup %s, stencils %s, fixture %s, feeder loading %d Extended codes x %s = %s, SMT %d pads x %d boards, "
         "through-hole %d joints x %d, packaging, confirmation, depanel | %s |"
         % (money(asm["setup"]), money(asm["stencil"]), money(asm["fixture"]), len(ext), money(F["feeder_per_extended"]), money(asm["feeder"]),
            smt_pads, a.assembled, tht_joints, a.assembled, money(asm_total)),
         "| | their parts: %d BOM lines, %d placements a board, with attrition, x %.4f | %s |" % (len(rows), sum(r["n"] for r in rows), F["parts_markup"], money(parts_cost)),
         "| | US duty, 35 %% of the above, collected under DDP | %s |" % money(duty),
         "| | shipping, UPS Express Saver DDP | %s-%s |" % (money(SHIPPING[0]), money(SHIPPING[1])),
         "| | **JLCPCB total** | **%s-%s** |" % (money(jlc_total[0]), money(jlc_total[1])),
         ("| **Digi-Key** | the consigned parts (table below): %s, plus %.1f %% tax and %s shipping | **%s** |" % (money(dk_parts), DIGIKEY_TAX * 100, money(DIGIKEY_SHIPPING), money(dk_total)))
         if dk_lines else "| **Digi-Key** | nothing consigned: every part is on JLCPCB's shelf (the ADI chips' fallback below is unused) | **%s** |" % money(0.0),
         "| | shipping the consignment to JLCPCB (USPS Priority International to FedEx) | %s-%s |" % (money(consign_ship[0]), money(consign_ship[1])),
         "| **other** | the bench and the field (table below) | **%s-%s** |" % (money(other_lo), money(other_hi)),
         "| | **everything** | **%s-%s** |" % (money(jlc_total[0] + dk_total + consign_ship[0] + other_lo), money(jlc_total[1] + dk_total + consign_ship[1] + other_hi)), ""]
    L += ["## Digi-Key: the consigned parts", ""]
    if dk_lines:
        L += ["| key | MPN | Digi-Key number | a board | order | unit | line | seen |", "|---|---|---|--:|--:|--:|--:|---|"]
        for key, mpn, dk, n, qty, unit, line, seen in dk_lines:
            L.append("| %s | %s | %s | %d | %d | %s | %s | %s |" % (key, mpn, dk, n, qty, money(unit), money(line), seen))
        L += ["", "The order is the placements on the assembled boards plus %d spares a line: JLCPCB's attrition and one for the bench." % CONSIGN_SPARES]
    else:
        L += ["None.  The balun is the TDK HHM1907B1 from JLCPCB's shelf (Prompt 31; the Johanson 5400 the ADL5380's sheet uses "
              "has 0 there), and the two ADI chips are bought from their shelf while it covers the order."]
    fb = fallback()
    lo, hi, shelf = consignment_cost(list(fb), a.assembled)
    L += ["", "**The ADI chips' fallback** (gen/parts.py consign=): %s.  If either shelf cannot cover the order on the day, "
          "that line is consigned (CONSIGNMENT.md then says what to buy).  What that costs, Jason's way of counting it "
          "(Prompt 31): consigning both means %d pieces at Digi-Key, %d of them spares that are never used, plus tax, "
          "Digi-Key's shipping and the shipment to Shenzhen: %s-%s against %s on JLCPCB's shelf for the %d pieces the "
          "boards need; so the shelf wins by %s-%s for %d boards, and a shelf part is worth buying up to that much "
          "dearer than Digi-Key's price.  With more boards assembled the spares and the shipment are spread thinner."
          % ("; ".join("%s %s, %s" % (k, p["consign"]["lcsc"], p["consign"].get("jlc_seen", "")) for k, p in fb.items()),
             len(fb) * (a.assembled + CONSIGN_SPARES), len(fb) * CONSIGN_SPARES, money(lo), money(hi), money(shelf),
             len(fb) * a.assembled, money(lo - shelf), money(hi - shelf), a.assembled)]
    if shelf_short:
        L += ["", "**Short today:** " + "; ".join("%s (%s): %d in stock, the order needs %d, so it is consigned above" % s for s in shelf_short)]
    L += [""]
    L += ["## Other: the bench and the field", "", "| item | low | high |", "|---|--:|--:|"]
    for what, lo, hi in OTHER:
        L.append("| %s | %s | %s |" % (what, money(lo), money(hi)))
    L += ["", "## What to look at", ""]
    for code, model, stock, order in thin:
        L.append("- **%s %s**: %d in stock against %d for this order" % (code, model, stock, order))
    L.append("- Feeder loading is the largest assembly fee after the setup: %d Extended codes x %s = %s.  Every value merged saves %s."
             % (len(ext), money(F["feeder_per_extended"]), money(asm["feeder"]), money(F["feeder_per_extended"])))
    L.append("- Hand-soldering the 2x20 socket (J302, alone on the back) makes the order one-sided: half the setup and the "
             "stencil, its feeder and joints, about $38 before duty.  Economic PCBA would not take the through-hole SMAs "
             "and headers, so Standard it stays.")
    L += ["", "## Parts (%d BOM lines)" % len(rows), "",
          "| LCSC | part | a board | ordered | library | unit | line | stock | asked |", "|---|---|--:|--:|---|--:|--:|--:|---|"]
    for r in sorted(rows, key=lambda r: (-r["line"], r["code"])):
        L.append("| %s | %s (%s) | %d | %d | %s | $%.4f | %s | %s | %s |"
                 % (r["code"], r["model"][:28], "/".join(dict.fromkeys(comps[x]["value"] for x in r["refs"]))[:20], r["n"], r["order"], r["lib"],
                    r["unit"], money(r["line"]), "{:,}".format(r["stock"]), r["asked"][:16].replace("T", " ")))
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    out = os.path.join(ROOT, "build", "COST_ESTIMATE.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    summary = dict(pcb=(pcb_lo, pcb, pcb_hi), assembly=asm_total, parts=parts_cost, duty=duty, jlc=jlc_total, digikey=dk_total,
                   consign_ship=consign_ship, other=(other_lo, other_hi), ext=len(ext), lines=len(rows), smt_pads=smt_pads, tht_joints=tht_joints, thin=thin)
    json.dump(summary, open(os.path.join(ROOT, "build", "cost.json"), "w"), indent=1)
    print("cost: JLCPCB %s-%s (boards %s, assembly %s, parts %s on %d lines / %d Extended, duty %s); Digi-Key %s + %s-%s to ship the "
          "consignment (none when nothing is consigned); other %s-%s -> build/COST_ESTIMATE.md"
          % (money(jlc_total[0]), money(jlc_total[1]), money(pcb), money(asm_total), money(parts_cost), len(rows), len(ext), money(duty),
             money(dk_total), money(consign_ship[0]), money(consign_ship[1]), money(other_lo), money(other_hi)))
    for code, model, stock, order in thin:
        print("   thin: %s %s: %d in stock, %d wanted" % (code, model, stock, order))
    return 0


if __name__ == "__main__":
    sys.exit(main())
