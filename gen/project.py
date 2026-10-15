#!/usr/bin/env python3
"""The KiCad project file: design rules at least as strict as JLCPCB's for the JLC04161H-7628
4-layer stack-up, the net classes, and the ERC settings.

    python3 gen/project.py      writes hardware/CostasLink-PYNQ-Z2.kicad_pro and .kicad_dru

JLCPCB's limits for 4-layer boards (capabilities page): track and space 0.09 mm, via 0.15 mm
hole in a 0.25 mm pad, hole to hole 0.2 mm, copper to a routed edge 0.2 mm.  Ours are stricter
everywhere (GPiBridge's rules).  The RF class is the 50 ohm grounded coplanar line of
sim/rf_lines.py.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "sim"))
import board_info as BI
import rf_lines

LIMITS = {
    "min_clearance": 0.127,
    "min_track_width": 0.127,
    "min_via_diameter": 0.45,
    "min_through_hole_diameter": 0.25,
    "min_via_annular_width": 0.1,
    "min_microvia_diameter": 0.3,
    "min_microvia_drill": 0.1,
    "min_hole_clearance": 0.2,
    "min_hole_to_hole": 0.25,
    "min_silk_clearance": 0.0,
    "min_text_height": 0.8,
    "min_text_thickness": 0.15,
    "min_copper_edge_clearance": 0.3,
    "min_connection": 0.0,
    "min_resolved_spokes": 1,
    "solder_mask_clearance": 0.0,
    "solder_mask_min_width": 0.0,
}

# name, track, clearance, via dia, via drill, diff-pair width, diff-pair gap
CLASSES = [
    ("Default", 0.15, 0.15, 0.45, 0.25, 0.15, 0.15),
    # 50 ohm CPWG on L1 over L2.  The clearance to other tracks and pads is the default's (a 0.5 mm pitch
    # RF pin is 0.25 mm from its neighbours); the gap to the ground pour is the "CPWG gap" rule below
    ("RF", rf_lines.RF_W, 0.15, 0.45, 0.25, rf_lines.RF_W, rf_lines.RF_GAP),
    ("LO", rf_lines.RF_W, 0.15, 0.45, 0.25, rf_lines.RF_W, rf_lines.RF_GAP),   # the synthesizers' differential outputs
    ("Baseband", 0.2, 0.15, 0.45, 0.25, 0.2, 0.15),       # I/Q from the demodulator to the comparators
    ("Power", 0.5, 0.15, 0.6, 0.3, 0.5, 0.2),             # 3.3 V rails and VC
    ("Power_5V", 0.8, 0.15, 0.6, 0.3, 0.8, 0.2),          # +5V_IN, +5V_RF: 1.3 A
    ("GND", 0.5, 0.15, 0.6, 0.3, 0.5, 0.2),
]
PATTERNS = [
    ("GND", "GND"),
    ("Power_5V", "/^\\+5V_/"), ("Power_5V", "VBUS"),
    ("Power", "/^\\+3V3_/"), ("Power", "/^VC($|_)/"),
    ("Baseband", "/^(I|Q)_(HI|LO|P|N)$/"), ("Baseband", "/^BB_/"),
]

# The RF and LO classes bind their nets by name: gen/routes.write_classes lists the nets its walks lay
# (build/netclasses.json; the board step writes the project again once it exists).  Name patterns
# ("/^RF_/", "/^LO_/") had matched none of them: the nets are "Net-(U101-RF_IN)", "/Receiver and Costas
# loop/LO_RX_P" (the design review).
CLASSES_JSON = os.path.join(BI.ROOT, "build", "netclasses.json")


def class_patterns():
    if not os.path.exists(CLASSES_JSON):
        return []
    named = json.load(open(CLASSES_JSON))
    return [(c, n) for c in ("RF", "LO") for n in named.get(c, [])]


DRU = '''(version 1)
# Written by gen/project.py.  Edit that, not this.
# (no silk_clearance rule: KiCad 10 then reports every designator against Fab text and
#  courtyards as a silkscreen overlap; its built-in silk checks stay on)
# The 50 ohm lines' CPWG gap: the ground pour keeps %.2f mm from every RF and LO track and pad.
# (The LO legs' equal length is gen/board.lo_skew's gate: each leg is three nets through two DC
#  blocks, which KiCad's skew constraint cannot add up.)
(rule "CPWG gap"
    (constraint clearance (min %.2fmm))
    (condition "(A.NetClass == 'RF' || A.NetClass == 'LO') && B.Type == 'Zone'"))
# The SMA launches (review B, Prompt 31): the centre pin keeps no copper ring on the inner and back layers
# (gen/footprints.sma), and the planes there stay 1.35 mm from its 1.3 mm hole, a 4 mm antipad, so the
# pin's capacitance to ground through the board is a small fraction of what a 2.5 mm antipad allowed.
(rule "SMA launch antipad, inner"
    (constraint hole_clearance (min 1.35mm))
    (condition "A.Pad_Type == 'Through-hole' && A.NetClass == 'RF' && B.Type == 'Zone'")
    (layer inner))
(rule "SMA launch antipad, back"
    (constraint hole_clearance (min 1.35mm))
    (condition "A.Pad_Type == 'Through-hole' && A.NetClass == 'RF' && B.Type == 'Zone'")
    (layer "B.Cu"))
''' % (rf_lines.RF_GAP, rf_lines.RF_GAP)


def write(hw):
    path = os.path.join(hw, BI.NAME + ".kicad_pro")
    pro = {}
    if os.path.exists(path):
        try:
            pro = json.load(open(path))
        except Exception:
            pro = {}
    pro["meta"] = {"filename": BI.NAME + ".kicad_pro", "version": 3}
    board = pro.setdefault("board", {})
    ds = board.setdefault("design_settings", {})
    ds.setdefault("defaults", {})
    ds["rules"] = LIMITS
    sev = ds.setdefault("rule_severities", {})
    for k in ("silk_over_copper", "silk_overlap", "silk_edge_clearance", "text_height", "text_thickness",
              "copper_edge_clearance", "holes_co_located", "solder_mask_bridge", "courtyards_overlap",
              "duplicate_footprints", "missing_footprint", "extra_footprint", "unresolved_variable",
              "net_conflict", "invalid_outline", "malformed_outline", "through_hole_pad_without_hole",
              "lib_footprint_mismatch"):
        sev[k] = "error"
    for k in ("lib_footprint_issues", "footprint_symbol_mismatch", "footprint_type_mismatch", "padstack"):
        sev[k] = "ignore"
    sev["isolated_copper"] = "warning"
    ds["drc_exclusions"] = []
    net = pro.setdefault("net_settings", {})
    net["classes"] = [{"name": n, "track_width": tw, "clearance": cl, "via_diameter": vd, "via_drill": vdr,
                       "diff_pair_width": dw, "diff_pair_gap": dg, "diff_pair_via_gap": dg, "bus_width": 12,
                       "wire_width": 6, "line_style": 0, "microvia_diameter": 0.3, "microvia_drill": 0.1,
                       "pcb_color": "rgba(0, 0, 0, 0.000)", "schematic_color": "rgba(0, 0, 0, 0.000)",
                       "priority": 2147483647 if n == "Default" else 0, "tuning_profile": ""}
                      for n, tw, cl, vd, vdr, dw, dg in CLASSES]
    net["netclass_patterns"] = [{"netclass": c, "pattern": p} for c, p in PATTERNS + class_patterns()]
    net.setdefault("meta", {"version": 4})
    sch = pro.setdefault("schematic", {})
    sch.setdefault("meta", {"version": 1})
    erc = sch.setdefault("erc", {})
    erc.setdefault("rule_severities", {})
    pro.setdefault("libraries", {"pinned_footprint_libs": [], "pinned_symbol_libs": []})
    pro.setdefault("pcbnew", {"last_paths": {}, "page_layout_descr_file": ""})
    pro.setdefault("sheets", [])
    pro["text_variables"] = {"REV": BI.REV, "DATE": BI.DATE}
    with open(path, "w") as f:
        json.dump(pro, f, indent=2)
    with open(os.path.join(hw, BI.NAME + ".kicad_dru"), "w") as f:
        f.write(DRU)
    return path


if __name__ == "__main__":
    print(write(BI.HW))
