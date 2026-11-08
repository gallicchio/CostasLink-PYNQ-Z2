"""The two scopes' fixed views for the courtyard demo (DEMO_COURTYARD.md section 5a), set once:
    python3 demoscope.py preset B      the receiver's view: I, Q, the bit (CMP I MON on ch1), the lock (VC MON on ch4)
    python3 demoscope.py preset A      the sender's view: I, Q, the ping (TRIG A on ch1), the pong (TRIG B on ch4)
    python3 demoscope.py shot A|B [path]   the screen to a BMP (default plots/demoscope_<which>_<stamp>.bmp)
The scopes are found by serial as in twoscope (scope_e.open_scope).  All inputs through 50 ohm feed-throughs."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scope_e                                            # noqa: E402

GAIN = 21.0                                               # the 1 k tap into 50 ohm
NOMINAL = 1.65 / GAIN                                     # an arm's centre at the scope
DIV = 8                                                   # vertical divisions


def place(scale, centre_div, dc=0.0):
    """the offset that puts a trace whose DC is `dc` at `centre_div` divisions from the screen's middle"""
    return -dc + centre_div * scale


def preset_B(s, trig=1, scale=0.010):
    """the receiver: the bits and the lock; the trigger on the recovered bit's edge; persistence for the eye.
    trig: the trigger channel (1 = CMP I MON; 4 on the bench, where ch4 is TRIG B's decision pulse and ch1 is the far
    board's TRIG A)"""
    s.timebase(scale=100e-9, delay=0.0)
    s.channel(2, on=True, scale=scale, offset=place(scale, 3, NOMINAL), coupling="DC", probe=1)       # I
    s.channel(3, on=True, scale=scale, offset=place(scale, 1, NOMINAL), coupling="DC", probe=1)       # Q
    s.channel(1, on=True, scale=0.2, offset=place(0.2, -1, 0.15), coupling="DC", probe=1)             # CMP I MON, the bit
    s.channel(4, on=True, scale=1.0, offset=place(1.0, -3, 1.65), coupling="DC", probe=1)             # VC MON, the lock
    if trig == 4:
        s.channel(4, on=True, scale=1.0, offset=place(1.0, -3, 0.0), coupling="DC", probe=1)          # the bench: TRIG B
    s.trigger(source=trig, level=0.15 if trig == 1 else 0.85, slope="rising", mode="normal")
    s.w("PESU 1")                                                                                       # 1 s persistence
    s.w("PACU PKPK,C2")                                                                                 # the eye's height
    s.run()


def preset_A(s, trig=1, scale=0.010):
    """the sender: the ping and the pong on one baseline, the delay measured on screen; auto trigger so the return
    stream shows between exchanges.  trig 4 on the bench (ch1 is the far board's TRIG A there)"""
    s.timebase(scale=50e-9, delay=-6 * 50e-9)                                                         # the trigger 1 div from the left
    s.channel(2, on=True, scale=scale, offset=place(scale, 3, NOMINAL), coupling="DC", probe=1)       # I
    s.channel(3, on=True, scale=scale, offset=place(scale, 1, NOMINAL), coupling="DC", probe=1)       # Q
    s.channel(1, on=True, scale=1.0, offset=place(1.0, -2.5, 0.0), coupling="DC", probe=1)            # TRIG A, the ping
    s.channel(4, on=True, scale=1.0, offset=place(1.0, -2.5, 0.0), coupling="DC", probe=1)            # TRIG B, the pong
    s.trigger(source=trig, level=0.85, slope="rising", mode="auto")
    s.w("PESU OFF")
    s.w("MEAD FRR,C1-C4")                                                                              # first rise of ch1 to first rise of ch4
    s.w("PASTAT ON")
    s.run()


def main():
    what, which = sys.argv[1], sys.argv[2]
    trig = int(sys.argv[sys.argv.index("--trig") + 1]) if "--trig" in sys.argv else 1
    scale = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 0.010
    s = scope_e.open_scope(which)
    try:
        if what == "preset":
            (preset_A if which == "A" else preset_B)(s, trig=trig, scale=scale)
            print("scope %s: %s preset" % (which, s.idn))
        elif what == "shot":
            path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "plots", "demoscope_%s_%s.bmp" % (which, time.strftime("%Y%m%d_%H%M%S")))
            n = s.screenshot(path)
            print("%s (%d bytes)" % (path, n))
    finally:
        s.close()


if __name__ == "__main__":
    main()
