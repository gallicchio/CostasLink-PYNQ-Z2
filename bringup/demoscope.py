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


def preset_B(s):
    """the receiver: the bits and the lock; the trigger on the recovered bit's edge; persistence for the eye"""
    s.timebase(scale=100e-9, delay=0.0)
    s.channel(2, on=True, scale=0.010, offset=place(0.010, 3, NOMINAL), coupling="DC", probe=1)       # I
    s.channel(3, on=True, scale=0.010, offset=place(0.010, 1, NOMINAL), coupling="DC", probe=1)       # Q
    s.channel(1, on=True, scale=0.2, offset=place(0.2, -1, 0.15), coupling="DC", probe=1)             # CMP I MON, the bit
    s.channel(4, on=True, scale=1.0, offset=place(1.0, -3, 1.65), coupling="DC", probe=1)             # VC MON, the lock
    s.trigger(source=1, level=0.15, slope="rising", mode="normal")
    s.w("PESU 1")                                                                                       # 1 s persistence
    s.w("PACU PKPK,C2")                                                                                 # the eye's height
    s.run()


def preset_A(s):
    """the sender: the ping and the pong on one baseline, the delay measured on screen; auto trigger so the return
    stream shows between exchanges"""
    s.timebase(scale=50e-9, delay=-6 * 50e-9)                                                         # the trigger 1 div from the left
    s.channel(2, on=True, scale=0.010, offset=place(0.010, 3, NOMINAL), coupling="DC", probe=1)       # I
    s.channel(3, on=True, scale=0.010, offset=place(0.010, 1, NOMINAL), coupling="DC", probe=1)       # Q
    s.channel(1, on=True, scale=1.0, offset=place(1.0, -2.5, 0.0), coupling="DC", probe=1)            # TRIG A, the ping
    s.channel(4, on=True, scale=1.0, offset=place(1.0, -2.5, 0.0), coupling="DC", probe=1)            # TRIG B, the pong
    s.trigger(source=1, level=0.85, slope="rising", mode="auto")
    s.w("PESU OFF")
    s.w("MEAD FRR,C1-C4")                                                                              # first rise of ch1 to first rise of ch4
    s.w("PASTAT ON")
    s.run()


def main():
    what, which = sys.argv[1], sys.argv[2]
    s = scope_e.open_scope(which)
    try:
        if what == "preset":
            (preset_A if which == "A" else preset_B)(s)
            print("scope %s: %s preset" % (which, s.idn))
        elif what == "shot":
            path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "plots", "demoscope_%s_%s.bmp" % (which, time.strftime("%Y%m%d_%H%M%S")))
            n = s.screenshot(path)
            print("%s (%d bytes)" % (path, n))
    finally:
        s.close()


if __name__ == "__main__":
    main()
