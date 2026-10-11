#!/usr/bin/env python3
"""Make everything, from the parts table to the checks, and stop at the first gate that fails
(CLAUDE_PCB.md section 10).

    python3 build.py                 every step, in order
    python3 build.py schematic       from one step on
    python3 build.py --only erc      just that step
    python3 build.py --clean         remove what the build makes and git does not keep

The steps, each a script that exits non-zero when its gate fails:

    budget     sim/budget.py          the design arithmetic, asserted; build/budget.json
    rates      sim/link_rates.py      range against error rate for every scheme and amplifier; build/link_rates.json
    library    gen/library.py         hardware/lib: every symbol, footprint, 3D model
    project    gen/project.py         the KiCad project: design rules, net classes
    schematic  gen/schematic.py       the root and the five sheets; its own touch/net/overlap checks
    erc        tools/sch_check.py     KiCad 10's format, ERC at every severity, the netlist
    netcheck   tools/net_check.py     power nets, one-pin nets, the signal paths walked
    gateware   gateware/gen_xdc.py    the PYNQ-Z2 and Icepi Zero constraints and the MAX2871 register words
    render     tools/render_sch.py    docs/images: the schematic as PDF and one PNG per sheet
    diagrams   docs/blockdiagram.py   docs/images/block_*.svg: the annotated block diagrams, numbers from the budget
    placement  gen/placement.py       where every part goes: build/placement.json, build/view/placement.png
    board      gen/board.py           the board: placement, the RF lines by plan, the router, the pours, the silkscreen
    drc        tools/pcb_check.py     KiCad's DRC at every severity, with schematic parity
    render_pcb tools/render_pcb.py    build/view/pcb_*.png: the copper layers as KiCad draws them
    release    mfg/make_release.py    (follows the board)

Needs KiCad 10 (tools/kienv.py finds it) and, for the release, network access to JLCPCB's parts
API and EasyEDA (answers are cached).  Everything a reviewer needs (hardware/, docs/) is
committed, so nothing has to be built to look at the design.
"""
import os, shutil, subprocess, sys, time

ROOT = os.path.dirname(os.path.abspath(__file__))


class Failed(Exception):
    pass


def py(script, *args, ok=(0,)):
    cmd = [sys.executable, os.path.join(ROOT, script)] + list(args)
    print("  $ %s" % " ".join([os.path.basename(sys.executable), script] + list(args)), flush=True)
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode not in ok:
        raise Failed("%s exited %d" % (script, r.returncode))


STEPS = [
    ("budget", lambda: py("sim/budget.py", "--json", "build/budget.json")),
    ("rates", lambda: py("sim/link_rates.py", "--json", "build/link_rates.json")),
    ("library", lambda: py("gen/library.py")),
    ("project", lambda: py("gen/project.py")),
    ("schematic", lambda: py("gen/schematic.py", ok=(0, 1))),     # text overlaps are reported, not yet fatal
    ("erc", lambda: py("tools/sch_check.py")),
    ("netcheck", lambda: py("tools/net_check.py")),
    ("gateware", lambda: (py("gateware/gen_xdc.py"), py("gateware/max2871_regs.py"))),
    ("render", lambda: py("tools/render_sch.py", "docs/images")),
    ("diagrams", lambda: py("docs/blockdiagram.py")),
    ("placement", lambda: py("gen/placement.py")),
    ("board", lambda: py("gen/board.py")),
    ("drc", lambda: py("tools/pcb_check.py", ok=(0, 1))),         # reported; the release gate is the one that fails
    ("render_pcb", lambda: py("tools/render_pcb.py")),
]
GENERATED = ["build", "hardware/lib", "hardware/checks", "hardware/sym-lib-table", "hardware/fp-lib-table",
             "hardware/CostasLink-PYNQ-Z2.kicad_sch", "hardware/rx.kicad_sch", "hardware/tx.kicad_sch", "hardware/pwr.kicad_sch", "hardware/ant.kicad_sch", "hardware/slow.kicad_sch", "hardware/win.kicad_sch",
             "hardware/CostasLink-PYNQ-Z2.kicad_pro", "hardware/CostasLink-PYNQ-Z2.kicad_dru", "hardware/CostasLink-PYNQ-Z2.kicad_prl",
             "hardware/CostasLink-PYNQ-Z2.kicad_pcb",
             "gateware/pynq_z2.xdc", "gateware/icepi_zero.lpf", "docs/images"]


def clean():
    n = 0
    for rel in GENERATED:
        p = os.path.join(ROOT, rel)
        if os.path.isdir(p):
            shutil.rmtree(p); n += 1
        elif os.path.exists(p):
            os.remove(p); n += 1
    print("removed %d generated files/directories" % n)


def main(argv):
    if "--clean" in argv:
        clean(); return 0
    os.makedirs(os.path.join(ROOT, "build"), exist_ok=True)
    names = [n for n, _ in STEPS]
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    start = next((a for a in argv if a in names), None)
    todo = [only] if only else names[names.index(start) if start else 0:]
    t0 = time.time()
    for name, fn in STEPS:
        if name not in todo:
            continue
        print("\n=== %s" % name, flush=True)
        try:
            fn()
        except Failed as e:
            print("\nFAILED at %s: %s" % (name, e))
            return 1
    print("\nbuild done in %.0f s" % (time.time() - t0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
