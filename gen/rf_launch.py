"""The 5.8 GHz launches' geometry, shared by gen/routes.rf_voids (which draws the rule areas) and
tools/launch_check.py (which measures them in the gerbers); no KiCad import here so the check runs anywhere."""
LAUNCH_SMAS = ("J101", "J202", "J401", "J402", "J403")      # the 5.8 GHz SMAs (REF IN and the triggers are not)
LAUNCH_R = 2.2            # radius of the no-copper circle round each centre pin on In1, In2 and B.Cu, mm
RELIEF_PADS = [("J102", "1"), ("J201", "1"), ("J109", "1"), ("J204", "1"),          # the 5.8 GHz U.FL taps' centre pads
               ("U103", "1"), ("U103", "3"), ("U117", "1"), ("U117", "3"), ("U202", "1"), ("U202", "3")]   # the ADL5611s' RF pads
VOID_MARGIN = 0.2         # In1 relieved this far beyond each pad's edge, mm
# The SMA centre pad on F.Cu (and B.Cu), from the SyzygyRadioDrivers launch study (SMABridgeTestAnalysis/
# FIELD_SOLVER.md section 15) re-simulated for this board's stack and connector (sim/launch/, docs/LAUNCH.md section 5):
# the pour kept 0.9 mm from the pad instead of the line's 0.25 mm CPWG gap is the one lever left after the voids
# (29 -> 19 % reflected at 5.8 GHz); the study's smaller pad is worth 2 % here and its taper nothing (a 1 mm taper
# from the pad's edge: -7.11 against -7.14 dB without, docs/LAUNCH.md 4.1; the study's own 1.0 mm taper was hidden
# inside its pad disc), so the pad is JLCPCB's plain 2.0 mm circle, symmetric under rotation.  The sweep that decided it: docs/LAUNCH.md section 4.
LAUNCH_PAD_OD = 2.0       # the centre pad's diameter, mm (JLCPCB's drawing: 2.0; the annulus on a 1.3 mm hole is 0.35)
LAUNCH_CLEAR = 0.9        # the top pour's clearance to the centre pad, mm: an F.Cu rule area (the line keeps its CPWG gap)
LAUNCH_TRACE_W = 0.29     # sim/rf_lines.RF_W
