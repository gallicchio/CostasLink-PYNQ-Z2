"""The two scopes' fixed views for the courtyard demo (DEMO_COURTYARD.md section 5a), set once, and scope B's cycle:
    python3 demoscope.py preset B      the receiver: I (ch1), Q (ch2), the bit (CMP I MON, ch3), the lock (VC MON, ch4)
    python3 demoscope.py preset A      the sender: I (ch2), Q (ch3), the ping (TRIG A, ch1), the pong (TRIG B, ch4)
    python3 demoscope.py cycle B [--time 5 --xy 5]   scope B for ever: the time view, then the I/Q constellation (XY),
                                       the two views in turn; Ctrl-C leaves the time view
    python3 demoscope.py shot A|B [path]   the screen to a BMP (default plots/demoscope_<which>_<stamp>.bmp)
    --bench     the bench's cabling (I on ch2, Q on ch3, ch1 the far board's TRIG A, ch4 this board's TRIG B): the trigger
                on ch4, and XY shows ch1 against ch2, so no constellation there
    --scale V   I and Q volts a division at the scope (0.010 through the 50 ohm feed-through and the 1 k tap; 0.050
                with the feed-throughs off, 1 Mohm)
This firmware's XY mode plots channel 1 (X) against channel 2 (Y) and nothing else (tried 11-08 10:48), which is why
scope B's I and Q sit on ch1 and ch2 for the demo.  The scopes are found by serial as in twoscope (scope_e.open_scope)."""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scope_e                                            # noqa: E402

GAIN = 21.0                                               # the 1 k tap into 50 ohm
NOMINAL = 1.65 / GAIN                                     # an arm's centre at the scope
V_LOCK = 1.65                                             # VC MON at lock (the integrator's middle)


def place(scale, centre_div, dc=0.0):
    """the offset that puts a trace whose DC is `dc` at `centre_div` divisions from the screen's middle"""
    return -dc + centre_div * scale


def arm_dc(scale):
    """an arm's DC at the scope: 1.65 V through the tap into 50 ohm, or the whole 1.65 V into 1 Mohm"""
    return NOMINAL if scale <= 0.02 else 1.65


def preset_B(s, bench=False, scale=0.010):
    """the receiver: I and Q, the recovered bit, the lock; the trigger on the bit's edge; persistence for the eye and
    for the constellation.  In XY the I and Q offsets put the idle's centre at the screen's middle"""
    dc = arm_dc(scale)
    s.timebase(scale=100e-9, delay=0.0)
    if bench:
        s.channel(2, on=True, scale=scale, offset=place(scale, 3, dc), coupling="DC", probe=1)         # I
        s.channel(3, on=True, scale=scale, offset=place(scale, 1, dc), coupling="DC", probe=1)         # Q
        s.channel(1, on=True, scale=1.0, offset=place(1.0, -1, 0.0), coupling="DC", probe=1)           # the far TRIG A (off)
        s.channel(4, on=True, scale=1.0, offset=place(1.0, -3, 0.0), coupling="DC", probe=1)           # this board's TRIG B
        s.trigger(source=4, level=0.85, slope="rising", mode="normal")
    else:
        s.channel(1, on=True, scale=scale, offset=place(scale, 0, dc), coupling="DC", probe=1)         # I: the middle (XY's X)
        s.channel(2, on=True, scale=scale, offset=place(scale, 0, dc), coupling="DC", probe=1)         # Q: the middle (XY's Y)
        s.channel(3, on=True, scale=0.2, offset=place(0.2, -2, 0.15), coupling="DC", probe=1)          # CMP I MON, the bit
        s.channel(4, on=True, scale=1.0, offset=place(1.0, -3.5, V_LOCK), coupling="DC", probe=1)      # VC MON, the lock
        s.trigger(source=3, level=0.15, slope="rising", mode="normal")
    s.w("XYDS OFF")
    s.w("PESU 1")                                                                                       # 1 s persistence
    s.w("PACU PKPK,C%d" % (2 if bench else 1))                                                          # the eye's height
    s.run()


def preset_A(s, bench=False, scale=0.010):
    """the sender: the ping and the pong on one baseline, the delay measured on screen; the pair every 500 ns"""
    dc = arm_dc(scale)
    s.timebase(scale=50e-9, delay=-6 * 50e-9)                                                         # the trigger 1 div from the left
    s.channel(2, on=True, scale=scale, offset=place(scale, 3, dc), coupling="DC", probe=1)             # I
    s.channel(3, on=True, scale=scale, offset=place(scale, 1, dc), coupling="DC", probe=1)             # Q
    s.channel(1, on=True, scale=1.0, offset=place(1.0, -2.5, 0.0), coupling="DC", probe=1)            # TRIG A, the ping
    s.channel(4, on=True, scale=1.0, offset=place(1.0, -2.5, 0.0), coupling="DC", probe=1)            # TRIG B, the pong
    s.trigger(source=4 if bench else 1, level=0.85, slope="rising", mode="auto")
    s.w("XYDS OFF")
    s.w("PESU OFF")
    s.w("MEAD FRR,C1-C4")                                                                              # first rise of ch1 to first rise of ch4
    s.w("PASTAT ON")
    s.run()


def cycle_B(s, t_time=5.0, t_xy=5.0, bench=False):
    """the time view and the constellation in turn, for ever; the view's name is printed at each change.  A SIGTERM
    (or Ctrl-C) leaves the time view: without the handler `timeout` left the scope in XY (11-08 11:21)"""
    import signal

    def leave(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, leave)
    try:
        while True:
            s.w("XYDS OFF")
            print(time.strftime("%H:%M:%S"), "time view", flush=True)
            time.sleep(t_time)
            s.w("XYDS ON")
            print(time.strftime("%H:%M:%S"), "XY: I against Q" if not bench else "XY (the bench: ch1 against ch2)", flush=True)
            time.sleep(t_xy)
    finally:
        s.w("XYDS OFF")


def main():
    what, which = sys.argv[1], sys.argv[2]
    bench = "--bench" in sys.argv
    scale = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 0.010
    s = scope_e.open_scope(which)
    try:
        if what == "preset":
            (preset_A if which == "A" else preset_B)(s, bench=bench, scale=scale)
            print("scope %s: %s preset%s" % (which, s.idn, " (the bench's cabling)" if bench else ""))
        elif what == "cycle":
            t_time = float(sys.argv[sys.argv.index("--time") + 1]) if "--time" in sys.argv else 5.0
            t_xy = float(sys.argv[sys.argv.index("--xy") + 1]) if "--xy" in sys.argv else 5.0
            print("scope %s: %s; the time view %.0f s, XY %.0f s, in turn" % (which, s.idn, t_time, t_xy))
            cycle_B(s, t_time, t_xy, bench=bench)
        elif what == "shot":
            path = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else os.path.join(HERE, "plots", "demoscope_%s_%s.bmp" % (which, time.strftime("%Y%m%d_%H%M%S")))
            n = s.screenshot(path)
            print("%s (%d bytes)" % (path, n))
    finally:
        s.close()


if __name__ == "__main__":
    main()
