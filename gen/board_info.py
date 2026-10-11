"""The board's identity, in one place: the schematic's title block, the silkscreen, the
release files and the gateware read it.  Every path a step reads or writes comes from here.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FAMILY = "CostasLink"
NAME = "CostasLink-PYNQ-Z2"            # its files' name
TITLE = "CostasLink-PYNQ-Z2"           # what it calls itself
TAGLINE = "5.8 GHz PSK / FSK / QPSK link with a hardware Costas loop, for the PYNQ-Z2"
REV = "A"
DATE = "2026-10-09"          # the design date; a release made before it is ordered is a DRAFT
AUTHORS = "Jason Gallicchio and Claude"
URL = "github.com/QuantumQuasars/OpticsPCBs/CostasLink-PYNQ-Z2"
LICENCE = "Hardware CERN-OHL-P-2.0, software MIT"

HW = os.path.join(ROOT, "hardware")
PCB = os.path.join(HW, NAME + ".kicad_pcb")
SCH = os.path.join(HW, NAME + ".kicad_sch")
CHECKS = os.path.join(HW, "checks")
NETLIST = os.path.join(CHECKS, "netlist.net")
RELEASE = os.path.join(ROOT, "mfg", "release")
IMAGE_PREFIX = ""
SCRATCH = os.path.join(ROOT, "build", NAME)
LIB = "CostasLink"                     # the project library's nickname (hardware/lib/CostasLink.*)
ORIGIN = (25.0, 25.0)                  # the board's top-left corner on KiCad's page (gen/board.py, tools/pcb_check.py)
