"""The two scopes' fixed views for the courtyard demo (DEMO_COURTYARD.md section 5a), set once, and scope B's cycle:
    python3 demoscope.py preset B      the receiver: I (ch1), Q (ch2), the bit (CMP I MON, ch3), the lock (VC MON, ch4,
                                       no feed-through)
    python3 demoscope.py preset A      the sender: I (ch1), Q (ch2), the ping (TRIG A, ch3), the pong (TRIG B, ch4)
    python3 demoscope.py cycle A|B [--time 5 --xy 5]   for ever: the time view, then the I/Q constellation (XY), the
                                       two views in turn (--time 0: XY only); Ctrl-C leaves the time view
    python3 demoscope.py shot A|B [path]   the screen to a BMP (default plots/demoscope_<which>_<stamp>.bmp)
    --bench     the bench's cabling (I on ch2, Q on ch3, ch1 the far board's TRIG A, ch4 this board's TRIG B): the trigger
                on ch4, and XY shows ch1 against ch2, so no constellation there
    --scale V   I and Q volts a division at the scope (0.010 through the 50 ohm feed-through and the 1 k tap; 0.050
                with the feed-throughs off, 1 Mohm)
This firmware's XY mode plots channel 1 (X) against channel 2 (Y) and nothing else (tried 11-08 10:48), which is why
both scopes' I and Q sit on ch1 and ch2 for the demo (scope A's too since 11-10, Jason: the constellation on A as well).  Everything goes through the lab driver (siglent_SDS1104XE, found by
serial: scope_e.open_scope), the display too since 11-09 (xy, persistence, show_measurement, show_delay, statistics; they
were raw XYDS / PESU / PACU / MEAD / PASTAT before the driver had them).  Scope A's firmware (8.1.6.1.26) cannot clear its
measurements remotely (it ignores MEACL): a preset adds its own if missing, and the front panel's Measure, Clear removes
the rest."""
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


# each scope's two views (Jason 11-08: 5 s of time traces, 5 s of the constellation; scope A too since 11-10).  Only
# ch1 / ch2's offsets differ: in the time view I and Q sit apart (I high, Q under it); in XY both at the middle, so the
# idle's dot is near the centre.  Scope A's time view keeps its lower half for the ping and the pong.
VIEW_TIME = {"A": {1: 3.0, 2: 1.0}, "B": {1: 2.5, 2: 0.5}}     # divisions from the middle: I, Q
VIEW_XY = {1: 0.0, 2: 0.0}


def b_offsets(s, scale, view):
    """ch1 / ch2's offsets for a view ({channel: divisions from the middle})"""
    dc = arm_dc(scale)
    for ch, div in view.items():
        s.channel(ch, offset=place(scale, div, dc))                # the lab driver's channel(): only the offset changes


def shown(how, *args):
    """a measurement under the traces; on a scope whose five places are full (scope A's firmware cannot clear them remotely)
    a note instead of a failed preset"""
    try:
        how(*args)
    except ValueError as e:
        print("  (not shown: %s)" % e)


def preset_B(s, bench=False, scale=0.010):
    """the receiver: I and Q, the recovered bit, the lock; the trigger on the bit's edge; persistence for the eye and
    for the constellation.  ch1 I MON and ch2 Q MON through 50 ohm feed-throughs at 10 mV/div (or none, --scale 0.05);
    ch3 CMP I MON through a feed-through (its /10 output is made for 50 ohm: 0.33 V); ch4 VC MON with NO feed-through
    (1 Mohm: its full 1.65 V, as on the bench since 10-30, 4.0's cabling)"""
    dc = arm_dc(scale)
    s.timebase(scale=100e-9, delay=0.0)
    if bench:
        s.channel(2, on=True, scale=scale, offset=place(scale, 3, dc), coupling="DC", probe=1)         # I
        s.channel(3, on=True, scale=scale, offset=place(scale, 1, dc), coupling="DC", probe=1)         # Q
        s.channel(1, on=True, scale=1.0, offset=place(1.0, -1, 0.0), coupling="DC", probe=1)           # the far TRIG A (off)
        s.channel(4, on=True, scale=1.0, offset=place(1.0, -3, 0.0), coupling="DC", probe=1)           # this board's TRIG B
        s.trigger(source=4, level=0.85, slope="rising", mode="normal")
    else:
        s.channel(1, on=True, scale=scale, offset=place(scale, VIEW_TIME["B"][1], dc), coupling="DC", probe=1)   # I (XY's X)
        s.channel(2, on=True, scale=scale, offset=place(scale, VIEW_TIME["B"][2], dc), coupling="DC", probe=1)   # Q (XY's Y)
        s.channel(3, on=True, scale=0.5, offset=place(0.5, -1.3, 0.0), coupling="DC", probe=1)              # CMP I MON, the bit
        s.channel(4, on=True, scale=1.0, offset=place(1.0, -2.5, V_LOCK), coupling="DC", probe=1)           # VC MON, the lock
        s.trigger(source=3, level=0.15, slope="rising", mode="normal")
    s.xy(False)
    s.persistence(1)                                                                                    # 1 s persistence
    shown(s.show_measurement, "PKPK", 2 if bench else 1)                                                # the eye's height
    s.run()


def preset_A(s, bench=False, scale=0.010):
    """the sender: the ping and the pong on one baseline, the delay measured on screen; the pair every 500 ns.  Since
    11-10 I and Q on ch1 / ch2 (XY plots ch1 against ch2 only) and the ping / pong on ch3 / ch4; --bench keeps the
    bench's cabling (I ch2, Q ch3, the far board's TRIG A on ch1, the trigger on ch4)"""
    dc = arm_dc(scale)
    s.timebase(scale=50e-9, delay=-6 * 50e-9)                                                         # the trigger 1 div from the left
    if bench:
        i_ch, q_ch, ping, pong, trig = 2, 3, 1, 4, 4
    else:
        i_ch, q_ch, ping, pong, trig = 1, 2, 3, 4, 3
    s.channel(i_ch, on=True, scale=scale, offset=place(scale, VIEW_TIME["A"][1], dc), coupling="DC", probe=1)   # I
    s.channel(q_ch, on=True, scale=scale, offset=place(scale, VIEW_TIME["A"][2], dc), coupling="DC", probe=1)   # Q
    s.channel(ping, on=True, scale=1.0, offset=place(1.0, -2.5, 0.0), coupling="DC", probe=1)         # TRIG A, the ping
    s.channel(pong, on=True, scale=1.0, offset=place(1.0, -2.5, 0.0), coupling="DC", probe=1)         # TRIG B, the pong
    s.trigger(source=trig, level=0.85, slope="rising", mode="auto")
    s.xy(False)
    s.persistence("OFF")
    shown(s.show_delay, "FRR", ping, pong)                                                             # the ping's first rise to the pong's
    s.statistics(True)
    s.run()


def cycle(s, which="B", t_time=5.0, t_xy=5.0, bench=False, scale=0.010):
    """the time view and the constellation in turn, for ever (t_time 0: the constellation only); the view's name is
    printed at each change.  Scope A's time view has persistence off (the ping and the pong crisp), its XY 1 s (the
    constellation builds up), as scope B's both.  A SIGTERM (or Ctrl-C) leaves the time view: without the handler
    `timeout` left the scope in XY (11-08 11:21)"""
    import signal

    def leave(signum, frame):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, leave)
    t_view = VIEW_TIME[which]

    def time_view():
        s.xy(False)
        if not bench:
            b_offsets(s, scale, t_view)
        if which == "A":
            s.persistence("OFF")

    def xy_view():
        if not bench:
            b_offsets(s, scale, VIEW_XY)
        if which == "A":
            s.persistence(1)
        s.xy(True)
    try:
        if t_time <= 0:
            xy_view()
            print(time.strftime("%H:%M:%S"), "XY only: I against Q", flush=True)
            while True:
                time.sleep(60)
        while True:
            time_view()
            print(time.strftime("%H:%M:%S"), "time view", flush=True)
            time.sleep(t_time)
            xy_view()
            print(time.strftime("%H:%M:%S"), "XY: I against Q" if not bench else "XY (the bench: ch1 against ch2)", flush=True)
            time.sleep(t_xy)
    finally:
        time_view()


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ("preset", "cycle", "shot") or sys.argv[2] not in ("A", "B"):
        print(__doc__.split("\nThis firmware")[0])
        sys.exit(0 if any(a in ("-h", "--help") for a in sys.argv[1:]) else 2)
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
            cycle(s, which, t_time, t_xy, bench=bench, scale=scale)
        elif what == "shot":
            path = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else os.path.join(HERE, "plots", "demoscope_%s_%s.bmp" % (which, time.strftime("%Y%m%d_%H%M%S")))
            n = s.screenshot(path)
            print("%s (%d bytes)" % (path, n))
    finally:
        s.close()


if __name__ == "__main__":
    main()
