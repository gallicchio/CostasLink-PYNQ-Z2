"""The 5.8 GHz launches' geometry, shared by gen/routes.rf_voids (which draws the rule areas) and
tools/launch_check.py (which measures them in the gerbers); no KiCad import here so the check runs anywhere."""
LAUNCH_SMAS = ("J101", "J202", "J401", "J402", "J403")      # the 5.8 GHz SMAs (REF IN and the triggers are not)
LAUNCH_R = 2.2            # radius of the no-copper circle round each centre pin on In1, In2 and B.Cu, mm
RELIEF_PADS = [("J102", "1"), ("J201", "1"), ("J109", "1"), ("J204", "1"),          # the 5.8 GHz U.FL taps' centre pads
               ("U103", "1"), ("U103", "3"), ("U117", "1"), ("U117", "3"), ("U202", "1"), ("U202", "3")]   # the ADL5611s' RF pads
VOID_MARGIN = 0.2         # In1 relieved this far beyond each pad's edge, mm
# The SMA centre pad on F.Cu (and B.Cu), from the SyzygyRadioDrivers launch study (SMABridgeTestAnalysis/
# FIELD_SOLVER.md section 15) as re-simulated for this board's stack and connector (sim/launch/, docs/LAUNCH.md):
# a smaller pad, a short taper from the pad's edge to the line, and a wider clearance to the top pour than the
# line's CPWG gap.  Until the sweep decides, the values are JLCPCB's land pattern: 2.0 mm, no taper, the CPWG gap.
LAUNCH_PAD_OD = 2.0       # the centre pad's diameter, mm (JLCPCB's drawing: 2.0; the annulus on a 1.3 mm hole is 0.35)
LAUNCH_TAPER = 0.0        # a taper from the pad's edge down to the line's width, along the footprint's -x (where the lines leave), mm
LAUNCH_CLEAR = 0.25       # the pad's own clearance to the pour on the outer layers, mm (the CPWG gap keeps the line's)
LAUNCH_TRACE_W = 0.29     # sim/rf_lines.RF_W
