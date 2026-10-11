#!/usr/bin/env python3
"""Make hardware/lib/: every symbol, footprint and 3D model the board uses, so the project opens
and builds on a machine whose KiCad has no libraries (CLAUDE_PCB.md section 2).

    hardware/lib/CostasLink.kicad_sym     KiCad's symbols (flattened) + ours (gen/symbols.py)
    hardware/lib/CostasLink.pretty/       KiCad's footprints + the ones drawn in gen/footprints.py
    hardware/lib/CostasLink.3dshapes/     KiCad's 3D models, the vendored ones (gen/vendored), and
                                          plain boxes where KiCad's library names a model it never drew
    hardware/sym-lib-table, fp-lib-table

KiCad's own libraries are read from the KiCad install (tools/kienv.py); they are CC-BY-SA 4.0
with an exception for designs that use them.  After GPiBridge's and OWLternating Current's.

    python3 gen/library.py
"""
import os, re, shutil, sys, uuid
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import kienv, kisch
from sexp import parse, head, kids, kid, val, ser
import symbols
import footprints
import board_info as BI
from parts import PARTS, LIB

kisch.POWER_LIB = LIB
HW = BI.HW
LIBDIR = os.path.join(HW, "lib")
PRETTY = os.path.join(LIBDIR, LIB + ".pretty")
SHAPES = os.path.join(LIBDIR, LIB + ".3dshapes")
MODEL_PATH = "${KIPRJMOD}/lib/" + LIB + ".3dshapes/"
VENDORED = footprints.VENDORED

# The HRO USB-C's silkscreen is trimmed behind the board edge (GPiBridge, learned on the Lorenz
# board: board edge = upper shell tab + 5.79 mm; JLCPCB pulls silk 0.2 mm back).
USBC_EDGE_Y = -3.13 + 5.79
USBC_SILK_LIMIT = USBC_EDGE_Y - 0.45

# KiCad names a model its library never drew: a stock model of the same body, or a box of the
# part's size.  (lib, model) -> (model, lib); lib BOX makes the box: (w, l, h) mm, colour.
BOX = "box"
STAND_IN = {
    ("Package_DFN_QFN", "QFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm.step"): ("QFN-32-1EP_5x5mm_P0.5mm_EP3.3x3.3mm.step", "Package_DFN_QFN"),
    ("Package_DFN_QFN", "VQFN-16-1EP_3x3mm_P0.5mm_EP1.68x1.68mm.step"): ("QFN-16-1EP_3x3mm_P0.5mm_EP1.7x1.7mm.step", "Package_DFN_QFN"),
    ("Fuse", "Fuse_1812_4532Metric.step"): ("Fuse_1812_box.wrl", (BOX, (4.5, 3.2, 1.0), (0.78, 0.66, 0.42))),
    ("TestPoint", "TestPoint_Pad_D1.5mm.step"): (None, None),
    ("Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12.step"): ("USB_C_Receptacle_HRO_TYPE-C-31-M-12.wrl", VENDORED),
    ("Connector_USB", "USB_C_Receptacle_HRO_TYPE-C-31-M-12.wrl"): ("USB_C_Receptacle_HRO_TYPE-C-31-M-12.wrl", VENDORED),
}


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ------------------------------------------------------------------------------------------
def _rename_symbol(node, old, new):
    """Rename a stock symbol and its unit sub-symbols.  A sub-symbol may carry the name of a
    parent the stock symbol extends (OPA2189xDGK's units are OPA2189xD_1_1 ...), so the unit
    suffix is kept and whatever precedes it replaced."""
    node = list(node)
    node[1] = ("str", new)
    out = []
    for c in node:
        if isinstance(c, list) and head(c) == "symbol":
            c = list(c)
            m = re.match(r"^(.*)_(\d+)_(\d+)$", val(c))
            c[1] = ("str", "%s_%s_%s" % (new, m.group(2), m.group(3)) if m else val(c).replace(old, new, 1))
        out.append(c)
    return out


def _set_prop(node, name, value):
    for c in node:
        if isinstance(c, list) and head(c) == "property" and val(c) == name:
            c[2] = ("str", value)


def build_symbols(share):
    entries = []
    for name, stock_id in sorted(symbols.STOCK.items()):
        node = kisch.SYMS.stock(stock_id, os.path.join(share, "symbols"))
        node = _rename_symbol(node, stock_id.split(":")[1], name)
        if name == "OPA2388":
            _set_prop(node, "Value", "OPA2388")
        entries.append((name, node))
    for name, fn in sorted(symbols.CUSTOM.items()):
        text, _ = fn()
        entries.append((name, parse(text)[0]))
    for net, down in sorted(symbols.RAILS.items()):
        lib_id = kisch.power_lib_id(net)
        kisch.make_power(lib_id, net, down=down)
        node, _ = kisch.SYMS.get(lib_id)
        entries.append((lib_id.split(":", 1)[1], node))
    for name, node in entries:
        _set_prop(node, "Footprint", "")
    write(os.path.join(LIBDIR, LIB + ".kicad_sym"), kisch.library_text(entries))
    return len(entries)


# ------------------------------------------------------------------------------------------
def _set_model(node, model):
    rest = [c for c in node if not (isinstance(c, list) and head(c) == "model")]
    node[:] = rest
    if model:
        node.append([("atom", "model"), ("str", MODEL_PATH + model),
                     [("atom", "offset"), [("atom", "xyz"), ("atom", "0"), ("atom", "0"), ("atom", "0")]],
                     [("atom", "scale"), [("atom", "xyz"), ("atom", "1"), ("atom", "1"), ("atom", "1")]],
                     [("atom", "rotate"), [("atom", "xyz"), ("atom", "0"), ("atom", "0"), ("atom", "0")]]])


def _box_wrl(size, rgb):
    """A box of size (w, l, h) mm standing on the board, in VRML (KiCad's units: 2.54 mm)."""
    w, l, h = (v / 2.54 for v in size)
    return ("#VRML V2.0 utf8\n# a stand-in made by gen/library.py: the part's size, no detail\n"
            "Transform { translation 0 0 %.4f children [ Shape {\n"
            "  appearance Appearance { material Material { diffuseColor %.3f %.3f %.3f specularColor 0.2 0.2 0.2"
            " shininess 0.3 } }\n  geometry Box { size %.4f %.4f %.4f } } ] }\n"
            % (h / 2, rgb[0], rgb[1], rgb[2], w, l, h))


def _stock_model(node):
    m = kid(node, "model")
    return os.path.basename(val(m)) if m else None


def _trim_usbc_silk(node):
    keep = []
    for c in node:
        if isinstance(c, list) and head(c) == "fp_line" and val(kid(c, "layer")) in ("F.SilkS", "F.Silkscreen"):
            s, e = kid(c, "start"), kid(c, "end")
            ys = [float(val(s, 2)), float(val(e, 2))]
            if min(ys) >= USBC_SILK_LIMIT:
                continue
            for p in (s, e):
                if float(val(p, 2)) > USBC_SILK_LIMIT:
                    p[2] = ("atom", "%.2f" % USBC_SILK_LIMIT)
            if abs(float(val(s, 1)) - float(val(e, 1))) + abs(float(val(s, 2)) - float(val(e, 2))) < 0.3:
                continue
        keep.append(c)
    node[:] = keep


def build_footprints(share, models_needed):
    if os.path.isdir(PRETTY):
        shutil.rmtree(PRETTY)
    os.makedirs(PRETTY)
    done = set()
    gen = footprints.generated()
    for key, p in sorted(PARTS.items()):
        src = p.get("fp_src")
        name = p["fp"].split(":", 1)[1] if p.get("fp") else ""
        if not src or not name or name in done:
            continue
        if src.startswith("stock:"):
            lib = src.split(":", 1)[1]
            path = os.path.join(share, "footprints", lib + ".pretty", name + ".kicad_mod")
            node = parse(open(path, encoding="utf-8").read())[0]
            model = _stock_model(node)
            if name.startswith("USB_C_Receptacle_HRO"):
                _trim_usbc_silk(node)
            mlib = os.path.basename(os.path.dirname(val(kid(node, "model")) or "")).replace(".3dshapes", "") \
                if kid(node, "model") else lib
            if model and (mlib, model) in STAND_IN:
                model, mlib = STAND_IN[(mlib, model)]
            _set_model(node, model)
            if model:
                models_needed[model] = mlib
            write(os.path.join(PRETTY, name + ".kicad_mod"), ser(node) + "\n")
        elif src == "gen":
            node = parse(gen[name])[0]
            model, mlib = footprints.MODELS.get(name, (None, None))
            if model and mlib is None:
                mlib = VENDORED
            _set_model(node, model)
            if model:
                models_needed[model] = mlib
            write(os.path.join(PRETTY, name + ".kicad_mod"), ser(node) + "\n")
        else:
            raise SystemExit("unknown footprint source %r for %s" % (src, key))
        done.add(name)
    # fiducials: netless marks on the board (CLAUDE_PCB.md section 5); a footprint here only so
    # that KiCad's stock drawing is at hand for gen/board.py
    path = os.path.join(share, "footprints", "Fiducial.pretty", "Fiducial_1mm_Mask2mm.kicad_mod")
    write(os.path.join(PRETTY, "Fiducial_1mm_Mask2mm.kicad_mod"), open(path, encoding="utf-8").read())
    done.add("Fiducial_1mm_Mask2mm")
    return len(done)


def copy_models(share, models_needed):
    if os.path.isdir(SHAPES):
        shutil.rmtree(SHAPES)
    os.makedirs(SHAPES)
    have, missing = 0, []
    for model, lib in sorted(models_needed.items(), key=lambda kv: kv[0]):
        base = os.path.splitext(model)[0]
        if isinstance(lib, tuple) and lib[0] == BOX:
            write(os.path.join(SHAPES, model), _box_wrl(lib[1], lib[2]))
            have += 1
            continue
        if lib == VENDORED:
            found = False
            for ext in (".wrl", ".step"):
                src = os.path.join(VENDORED, base + ext)
                if os.path.exists(src):
                    shutil.copy(src, os.path.join(SHAPES, base + ext))
                    found = True
            have += found
            if not found:
                missing.append("vendored/" + model)
            continue
        found = False
        for m in (model, base + ".step", base + ".wrl"):
            src = os.path.join(share, "3dmodels", lib + ".3dshapes", m)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(SHAPES, os.path.basename(m)))
                found = True
        have += found
        if not found:
            missing.append("%s/%s" % (lib, model))
    return have, missing


LIB_README = """# hardware/lib: everything the board is drawn with

Made by `gen/library.py`; do not edit by hand.

- `CostasLink.kicad_sym`: KiCad's own symbols (flattened, so nothing points at a library you
  may not have), plus the ones drawn for this board in `gen/symbols.py` (MAX2871, ADL5380,
  ADL5375, PE43711, ADL5611, SKY65404-31, THS4541, TLV3601, the two analog switches, the
  oscillators, the balun, the power flags).
- `CostasLink.pretty/`: KiCad's own footprints, and four from `gen/footprints.py`: the LNA
  (JLCPCB's land pattern), the balun (Johanson's drawing), the 2x20 socket (the GPSDO board's
  drawing) and the SMA (the ECP5 board's copy of JLCPCB's drawing).
- `CostasLink.3dshapes/`: KiCad's models, the SMA's and the USB-C's (vendored from the earlier
  boards), and plain boxes where KiCad names a model it never drew (`STAND_IN`).

Licences: KiCad's libraries are CC-BY-SA 4.0 with the KiCad libraries' exception (using them in
a design does not put the design under CC-BY-SA).  The rest is this project's (`LICENSE`).
"""


def lib_tables():
    write(os.path.join(HW, "sym-lib-table"),
          '(sym_lib_table\n\t(version 7)\n\t(lib (name "%s") (type "KiCad") (uri "${KIPRJMOD}/lib/%s.kicad_sym") '
          '(options "") (descr "Every symbol CostasLink uses"))\n)\n' % (LIB, LIB))
    write(os.path.join(HW, "fp-lib-table"),
          '(fp_lib_table\n\t(version 7)\n\t(lib (name "%s") (type "KiCad") (uri "${KIPRJMOD}/lib/%s.pretty") '
          '(options "") (descr "Every footprint CostasLink uses"))\n)\n' % (LIB, LIB))
    write(os.path.join(LIBDIR, "README.md"), LIB_README)


def fixed_uuids(directory):
    """KiCad's upgrade gives every item a fresh random UUID on every run; replace them with ones
    derived from the file name and the item's order, so rebuilding the library changes nothing
    git can see unless a footprint really changed."""
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".kicad_mod"):
            continue
        path = os.path.join(directory, name)
        text = open(path).read()
        n = iter(range(10 ** 6))
        text = re.sub(r'\(uuid "[0-9a-f-]+"\)',
                      lambda m: '(uuid "%s")' % uuid.uuid5(uuid.NAMESPACE_URL, "costaslink/%s/%d" % (name, next(n))), text)
        write(path, text)


def main():
    share = kienv.share()
    ns = build_symbols(share)
    models = {}
    nf = build_footprints(share, models)
    have, missing = copy_models(share, models)
    lib_tables()
    # KiCad 10's format for every footprint (the drawn ones are written in an older one)
    kienv.run_cli(["fp", "upgrade", "--force", PRETTY])
    fixed_uuids(PRETTY)
    if missing:
        raise SystemExit("no 3D model for: %s" % ", ".join(missing))
    print("library: %d symbols, %d footprints, %d 3D models" % (ns, nf, have))
    return 0


if __name__ == "__main__":
    sys.exit(main())
