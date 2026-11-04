#!/usr/bin/env python3
"""bench.py: the rev A bring-up from the bench PC (2026-10-28): the lab instruments (~/lab-instrument-control) and the
board (gateware/driver/netbus.py, the driver running on the PYNQ) in one place, and every reading appended to the
board's log, bringup/data/board_<X>/<date>.jsonl, with the time, the stage, the instrument's settings and the verdict.

    python3 bringup/bench.py check                      # who answers: each instrument's *IDN? only, and the board
    python3 bringup/bench.py note "J302 soldered" --stage 1.0
    python3 bringup/bench.py psu smoke                  # stage 1.1: 5.15 V at a 0.10 A limit for 3 s, then off
    python3 bringup/bench.py psu on                     # stage 1.2 on: 5.15 V, 1.5 A, OVP 5.5 V
    python3 bringup/bench.py psu read --n 5
    python3 bringup/bench.py psu log --seconds 600      # stage 1.4: V and I (and the board's NTC if it answers)
    python3 bringup/bench.py psu off
    python3 bringup/bench.py dmm +3V3_ANA               # one rail on the Fluke 45, against the stage's limits
    python3 bringup/bench.py sa peak --center 5.8e9 --span 10e6 --label "LO TX MON"
    python3 bringup/bench.py board snapshot             # everything the board says about itself
    python3 bringup/bench.py board call detectors       # any CostasLink method, its result logged
    python3 bringup/bench.py run stage2.lo --which tx   # a procedure of stages.py
    python3 bringup/bench.py show [--n 20]              # the log's last entries

The board is `--board A` (or $COSTAS_BOARD, or bench_config.json's "board"): mark the two assembled boards A and B.
The addresses are bench_config.json's (written with defaults the first time; edit it, or run `check`).  Nothing here
changes an instrument except the command that says so; `check` sends *IDN? and nothing else.
"""
import argparse
import atexit
import datetime as dt
import fcntl
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(HERE)
LIC = os.path.expanduser(os.environ.get("LAB_INSTRUMENT_CONTROL", "~/lab-instrument-control"))
for sub in ("", "hp", "fluke", "rigol", "siglent"):
    sys.path.insert(0, os.path.join(LIC, sub))
sys.path.insert(0, os.path.join(PROJECT, "gateware", "driver"))
sys.path.insert(0, os.path.join(PROJECT, "gateware"))

# another bench's instruments (a laptop in the lab: bench_config_laptop.json) without editing the bench PC's file
CONFIG = os.environ.get("COSTAS_BENCH_CONFIG") or os.path.join(HERE, "bench_config.json")
DEFAULTS = {
    "board": "A",
    "pynq_host": "192.168.2.99",          # PYNQ's static fallback address; the lab LAN gives it a DHCP one too
    "pynq_port": 5800,
    # the board's 5 V: an E3632A (0-15 V, 7 A, OVP and OCP) or an E3646A (two outputs, 0-8 V 3 A, OVP only, one
    # output switch for both) on RS-232 (find the port: python3 scpi_link.py identify)
    # pynq_out: the E3646A's other output powers the PYNQ (since 2026-11-01): the one switch stays on for it, and the
    # board is switched by its own output's voltage (psu_output); None while the PYNQ has its own adapter
    # pynq_serial: the PYNQ on a supply of its own (an E3632A on RS-232, output 1; the lab laptop, 2026-11-03): then
    # the board's supply switches the board alone, and psu up / cycle / pynq-on / pynq-off drive the PYNQ's supply
    "psu": {"serial": None, "gpib": None, "out": 1, "pynq_out": None, "pynq_serial": None},
    "dmm": {"serial": None},              # the Fluke 45 on RS-232
    "sa": {"host": "192.168.8.114", "usb": False},     # the Rigol DSA875 (9 kHz-7.5 GHz): N input, +30 dBm max
    "scope": {"host": "192.168.8.203"},  # the Siglent SDS2104X Plus
    "gen": {"host": "192.168.8.246"},    # the Siglent SDG1032X
}

# the board's 5 V (BRINGUP stage 1 and "What to have on the bench")
SUPPLY_V = 5.15          # 5.10-5.25 V at the plug: the PTC, the FET and the bead drop up to 0.21 V before +5V_RF
SUPPLY_A = 1.5           # the board draws 1.37 A with both synthesizers running
SMOKE_A = 0.10           # stage 1.1's first limit
OVP_V = 5.5              # the ADL5375's / ADL5380's VPOS absolute maximum (5.5 V); the E36xxA's OVP is a crowbar
OTHER_A = 0.02           # an E3646A's other output, sharing the one switch: 0 V and this limit while ours is on
PYNQ_V = 12.0            # the PYNQ-Z2's DC1 jack: 7-15 V, 12 V recommended, centre positive (when psu.pynq_out is set)
PYNQ_A = 1.5             # the E3646A's 20 V range tops out at 1.5 A; the PYNQ draws 0.15-0.2 A
PYNQ_OVP_V = 13.5
PYNQ_BOOT_S = 240        # psu up: the PYNQ's boot, boot.py's base overlay, then ours (about 90 s on 2026-11-01)

# stage 1.2's rails: their test pads (the bottom-right strip, TP308 GND) and U.FL monitors (through 1 k), from the board file
RAIL_PADS = {"+5V_IN": ("TP301", "J390"), "+5V_RF": ("TP302", "J391"), "+3V3_PLL_TX": ("TP303", "J394"),
             "+3V3_PLL_RX": ("TP304", "J395"), "+3V3_ANA": ("TP305", "J392"), "+3V3_DIG": ("TP306", "J393"),
             "+3V3_OSC": ("TP307", "J396")}
# and their limits: (low, high) in volts, or the supply's own reading less the input path's drop
RAILS = {
    "+5V_IN": "within 0.15 V of the supply",
    "+5V_RF": (4.85, 5.25),
    "+3V3_PLL_TX": (3.25, 3.35),
    "+3V3_PLL_RX": (3.25, 3.35),
    "+3V3_ANA": (3.25, 3.35),
    "+3V3_DIG": (3.25, 3.35),
    "+3V3_OSC": (3.25, 3.35),
}


def now_iso():
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def load_config():
    if not os.path.exists(CONFIG):
        with open(CONFIG, "w") as f:
            json.dump(DEFAULTS, f, indent=1)
            f.write("\n")
    with open(CONFIG) as f:
        cfg = json.load(f)
    for k, v in DEFAULTS.items():
        cfg.setdefault(k, v)
    return cfg


class Log:
    """append-only JSON lines, one file a board a day; every entry has t, board, stage, kind"""

    def __init__(self, board):
        self.board = board
        d = os.path.join(HERE, "data", "board_%s" % board)
        os.makedirs(d, exist_ok=True)
        self.path = os.path.join(d, dt.date.today().isoformat() + ".jsonl")

    def add(self, kind, stage=None, **fields):
        e = {"t": now_iso(), "board": self.board, "stage": stage, "kind": kind}
        e.update(fields)
        with open(self.path, "a") as f:
            f.write(json.dumps(e, default=repr) + "\n")
        return e

    def tail(self, n=20):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            lines = f.readlines()[-n:]
        return [json.loads(x) for x in lines]


def reachable(host, port, timeout=2.0):
    """a TCP connect, quickly: an instrument that is off or elsewhere otherwise costs the kernel's two minutes of SYNs"""
    import socket
    try:
        socket.create_connection((host, port), timeout=timeout).close()
        return True
    except OSError:
        return False


WATCH_PAUSE = os.path.join(HERE, "data", "watch_pause")     # an epoch time: the watchdog counts no silence until then


def watch_paused():
    """the watchdog told to expect a silent server (bench.py pause --minutes N, before a deliberate restart)"""
    try:
        with open(WATCH_PAUSE) as f:
            return time.time() < float(f.read().strip() or 0)
    except (OSError, ValueError):
        return False


def _need(host, port, what):
    if not reachable(host, port):
        raise IOError("%s: nothing answers at %s:%d (off, unplugged, or another address: bench_config.json)" % (what, host, port))


def verdict(value, lo, hi):
    return value is not None and lo <= value <= hi


class Locked:
    """An instrument on a serial line that several bench.py processes share (the watchdog and a stage): every call
    holds an exclusive lock on the port, and so does opening it, so two processes' messages never interleave.  On
    2026-10-29 they did: a stage's psu_read and the watchdog's, both on the E3646A, and the watchdog died on a reply
    that was the other's *IDN?.  The lock is bringup/.locks/<port>.lock (git-ignored)."""

    def __init__(self, port, factory):
        d = os.path.join(HERE, ".locks")
        os.makedirs(d, exist_ok=True)
        self._lockf = open(os.path.join(d, os.path.basename(port) + ".lock"), "a")
        with self:
            self._inst = factory()

    def __enter__(self):
        fcntl.flock(self._lockf, fcntl.LOCK_EX)
        return self

    def __exit__(self, *exc):
        fcntl.flock(self._lockf, fcntl.LOCK_UN)

    def __getattr__(self, name):
        a = getattr(self._inst, name)
        if not callable(a):
            return a

        def locked(*args, **kwargs):
            with self:
                return a(*args, **kwargs)
        return locked

    def close(self):
        try:
            with self:
                self._inst.close()
        finally:
            self._lockf.close()


class Bench:
    """the instruments, opened when first used; the board through netbus; the log"""

    def __init__(self, board=None, stage=None):
        self.cfg = load_config()
        self.cfg["pynq_host"] = os.environ.get("COSTAS_PYNQ_HOST", self.cfg["pynq_host"])    # e.g. 127.0.0.1 for --sim
        self.board_name = board or os.environ.get("COSTAS_BOARD") or self.cfg["board"]
        self.stage = stage
        self.log = Log(self.board_name)
        self._open = {}
        atexit.register(self.close)          # any script that opened the analyser leaves it live (sa_live), not paused

    # ---- the instruments ----
    def _get(self, name, factory):
        if name not in self._open:
            self._open[name] = factory()
        return self._open[name]

    @property
    def psu(self):
        def make():
            from agilent_E36xxA import AgilentE36xxA
            c = self.cfg["psu"]
            if c.get("serial"):
                return Locked(c["serial"], lambda: AgilentE36xxA(serial=c["serial"]))
            if c.get("gpib") is not None:
                return AgilentE36xxA(int(c["gpib"]))
            raise IOError("bench_config.json: psu has no serial port or GPIB address (python3 %s/scpi_link.py identify)" % LIC)
        return self._get("psu", make)

    @property
    def dmm(self):
        def make():
            from fluke_45 import Fluke45
            c = self.cfg["dmm"]
            if not c.get("serial"):
                raise IOError("bench_config.json: dmm has no serial port (python3 %s/scpi_link.py identify)" % LIC)
            m = Locked(c["serial"], lambda: Fluke45(serial=c["serial"]))
            m.function("VDC")
            return m
        return self._get("dmm", make)

    @property
    def sa(self):
        def make():
            from rigol_DSA875 import DSA875, usbtmc_node, USB_VENDOR, USB_PRODUCT
            c = self.cfg["sa"]
            if c.get("usb"):
                return DSA875(usb=usbtmc_node(USB_VENDOR, USB_PRODUCT))
            _need(c["host"], 5555, "DSA875")                 # its raw SCPI socket
            return DSA875(c["host"])
        return self._get("sa", make)

    @property
    def scope(self):
        def make():
            from siglent_SDS2104X import SDS2104X
            _need(self.cfg["scope"]["host"], 111, "SDS2104X")   # VXI-11's portmapper
            return SDS2104X(self.cfg["scope"]["host"])
        return self._get("scope", make)

    @property
    def gen(self):
        def make():
            from siglent_SDG1032X import SDG1032X
            _need(self.cfg["gen"]["host"], 111, "SDG1032X")
            return SDG1032X(self.cfg["gen"]["host"], vlimit=3.4)     # nothing on this board takes more than 3.3 V
        return self._get("gen", make)

    @property
    def cl(self):
        def make():
            from netbus import RemoteCostasLink
            _need(self.cfg["pynq_host"], self.cfg["pynq_port"], "the PYNQ's netbus server")
            return RemoteCostasLink(self.cfg["pynq_host"], self.cfg["pynq_port"])
        return self._get("cl", make)

    def close(self):
        if "sa" in self._open:
            try:
                self.sa_live()
            except Exception:                                           # noqa: BLE001 - closing what is open
                pass
        for k, inst in list(self._open.items()):
            try:
                inst.close()
            except Exception:                                           # noqa: BLE001 - closing what is open
                pass
            del self._open[k]

    # ---- recording ----
    def note(self, text, **kw):
        return self.log.add("note", self.stage, text=text, **kw)

    def record(self, kind, **kw):
        return self.log.add(kind, self.stage, **kw)

    # ---- the supply ----
    def pynq_supply(self):
        """The PYNQ's supply and output: the E3646A's other output (psu.pynq_out), a supply of its own (psu.pynq_serial,
        output 1), or (None, None) while the PYNQ has its own adapter."""
        c = self.cfg["psu"]
        if c.get("pynq_serial"):
            def make():
                from agilent_E36xxA import AgilentE36xxA
                return Locked(c["pynq_serial"], lambda: AgilentE36xxA(serial=c["pynq_serial"]))
            return self._get("pynq_psu", make), 1
        if c.get("pynq_out"):
            return self.psu, c["pynq_out"]
        return None, None

    def _board_zero(self):
        """The board unpowered before the PYNQ's power changes: its output at 0 V on a shared E3646A, its own supply's
        output off otherwise."""
        c = self.cfg["psu"]
        if c.get("pynq_out"):
            self.psu.select(c.get("out", 1))
            self.psu.w("VOLTage 0")
        else:
            self.psu.output(False)

    def board_on(self):
        """The board's output live: the switch on and, when the PYNQ shares the supply, the board's setting above 0 V."""
        p = self.psu
        if p.q("OUTPut?") != "1":
            return False
        return not self.cfg["psu"].get("pynq_out") or p.setting(self.cfg["psu"].get("out", 1))["volts"] > 0.05

    def psu_setup(self, volts=SUPPLY_V, amps=SUPPLY_A, ovp=OVP_V):
        p = self.psu
        out = self.cfg["psu"].get("out", 1)
        pynq = self.cfg["psu"].get("pynq_out")
        low = p.ranges[0]                            # E3632A P15V (7 A), E3646A P8V (3 A)
        if p.setting(out)["range"] != low:
            if self.board_on():                      # a range change under load would glitch the board
                raise IOError("%s output is on in range %s: turn it off (psu off) before setting it up"
                              % (p.model, p.setting(out)["range"]))
            p.set_range(low, out=out)
        for other in range(1, p.outputs + 1):        # the E3646A's one switch turns on both outputs
            if other not in (out, pynq):
                self.record("psu_other_output", out=other, setting=p.set(0.0, OTHER_A, out=other))
        s = p.set_ovp(ovp, on=True, out=out)
        if getattr(p, "has_ocp", False):
            s = p.set_ocp(on=False)                  # the current limit (CC) is the protection; OCP would trip at 0.1 A
        self._board_set = (volts, amps)
        # with the PYNQ keeping the switch on, an unpowered board waits at 0 V for psu_output(True)
        s = p.set(volts if not pynq or self.board_on() else 0.0, amps, out=out)
        self.record("psu_setting", model=p.model, idn=p.idn, setting=s)
        return s

    def psu_read(self, label=None):
        p = self.psu
        out = self.cfg["psu"].get("out", 1)
        v, i = p.measure(out=out)
        mode = p.mode(out=out)
        return self.record("psu", label=label, volts=v, amps=i, mode=mode, watts=v * i)

    def psu_output(self, on):
        """The board's power.  With the PYNQ on the E3646A's other output (psu.pynq_out) the one switch stays on for
        it and the board's output is switched by its voltage: psu_setup's, or 0 V.  On only with the PYNQ's server
        up: the board powered into an unpowered Zynq drives its clamp diodes (REVB R3), and the overlay is loaded
        first so TX_EN is held low from the start (install_service.sh)."""
        pynq = self.cfg["psu"].get("pynq_out")
        if not pynq:
            if on and self.cfg["psu"].get("pynq_serial"):          # the PYNQ on its own supply: the same interlock
                s, o = self.pynq_supply()
                if s.q("OUTPut?") != "1" or s.setting(o)["volts"] < PYNQ_V - 1:
                    raise IOError("the PYNQ's supply is off: psu up (or psu pynq-on) first")
                if not reachable(self.cfg["pynq_host"], self.cfg["pynq_port"], timeout=3):
                    raise IOError("the PYNQ's server does not answer: the board is powered once its overlay is loaded")
            got = self.psu.output(on)
            self.record("psu_output", on=bool(on), got=got)
            return got
        p, out = self.psu, self.cfg["psu"].get("out", 1)
        if on:
            if p.q("OUTPut?") != "1" or p.setting(pynq)["volts"] < PYNQ_V - 1:
                raise IOError("the PYNQ (output %d) is unpowered: psu up (or psu pynq-on) first" % pynq)
            if not reachable(self.cfg["pynq_host"], self.cfg["pynq_port"], timeout=3):
                raise IOError("the PYNQ's server does not answer: the board is powered once its overlay is loaded")
            if getattr(self, "_board_set", None) is None:
                raise IOError("psu_setup first: the board's voltage is not set in this process")
            p.set(*self._board_set, out=out)
        else:
            p.select(out)
            p.w("VOLTage 0")
        got = self.board_on()
        self.record("psu_output", on=bool(on), got=got, out=out, pynq_left_on=True)
        return got

    def psu_pynq(self, on, volts=PYNQ_V, amps=PYNQ_A, ovp=PYNQ_OVP_V):
        """The PYNQ's output (psu.pynq_out, or its own supply: psu.pynq_serial).  On: the board's output at 0 V, the PYNQ's set up (20 V range, OVP) at
        1.5 V and 0.1 A first (a plug reversed conducts there; the right way round draws about 1 mA), the switch on,
        then 12 V, its draw checked (CV, 0.03-1.2 A).  Off: the board's output to 0 V first, then the switch (both).
        Anything out of bounds switches both off and raises."""
        p, pynq = self.pynq_supply()           # the E3646A and its other output, or the PYNQ's own supply and 1
        if p is None:
            raise IOError("bench_config.json: neither psu.pynq_out nor psu.pynq_serial is set (the PYNQ is on its own adapter)")

        def check(label, ok):
            v, i = p.measure(out=pynq)
            m = p.mode(out=pynq)
            r = self.record("psu", label=label, out=pynq, volts=v, amps=i, mode=m, watts=v * i)
            if not ok(v, i, m):
                self.psu_pynq(False)
                raise IOError("the PYNQ's output %s: %.3f V %.4f A %s; both outputs switched off" % (label, v, i, m))
            return r

        if not on:
            self._board_zero()
            time.sleep(1.0)
            got = p.output(False)
            self.record("psu_pynq", on=False, got=got)
            return got
        if p.q("OUTPut?") == "1" and p.setting(pynq)["volts"] >= volts - 0.05:
            return check("already on", lambda v, i, m: True)
        self._board_zero()
        p.set(0.0, 0.10, out=pynq)
        if p.setting(pynq)["range"] != p.ranges[1]:
            p.set_range(p.ranges[1], out=pynq)
        p.set_ovp(ovp, on=True, out=pynq)
        p.set(1.5, 0.10, out=pynq)
        p.output(True)
        time.sleep(1.5)
        check("polarity, 1.5 V", lambda v, i, m: m == "CV" and i < 0.05)
        p.set(volts, amps, out=pynq)
        time.sleep(2.0)
        r = check("on", lambda v, i, m: m == "CV" and 0.03 <= i <= 1.2 and abs(v - volts) < 0.2)
        self.record("psu_pynq", on=True, setting=p.setting(pynq))
        return r

    def pynq_ready(self, timeout_s=PYNQ_BOOT_S):
        """Wait for the PYNQ's server with our overlay loaded (its ID one the driver accepts), up to timeout_s."""
        import costaslink
        t_end = time.time() + timeout_s
        while time.time() < t_end:
            if reachable(self.cfg["pynq_host"], self.cfg["pynq_port"], timeout=3):
                try:
                    ident = self.cl.rd("ID")
                    if ident in costaslink.ID_ACCEPTED:
                        return ident
                except Exception:                                       # noqa: BLE001 - the server still starting
                    pass
                old = self._open.pop("cl", None)
                if old is not None:
                    try:
                        old.close()
                    except Exception:                                   # noqa: BLE001
                        pass
            time.sleep(5)
        return None

    def psu_up(self, volts=SUPPLY_V, amps=SUPPLY_A):
        """The cold start in its order: the PYNQ, its overlay (the server answering with our ID), then the board."""
        self.psu_pynq(True)
        ident = self.pynq_ready()
        if ident is None:
            raise IOError("the PYNQ's server did not answer with our overlay in %d s: the board left off" % PYNQ_BOOT_S)
        self.note("the PYNQ's server up, ID 0x%08X: the board powered" % ident)
        self.psu_setup(volts, amps)
        self.psu_output(True)
        time.sleep(1.0)
        return self.psu_read("up")

    # ---- the meter ----
    def dmm_read(self, label, settle=2, n=3, supply_v=None):
        m = self.dmm
        vals = [m.read(settle=settle if k == 0 else 0) for k in range(n)]
        v = sum(vals) / len(vals)
        lim = RAILS.get(label)
        lo = hi = None
        if lim == "within 0.15 V of the supply":
            if supply_v is None:
                supply_v = self.psu_read("for " + label)["volts"]
            lo, hi = supply_v - 0.15, supply_v + 0.01
        elif isinstance(lim, tuple):
            lo, hi = lim
        ok = None if lo is None else verdict(v, lo, hi)
        return self.record("dmm", label=label, pads=RAIL_PADS.get(label), volts=v, readings=vals, limits=[lo, hi], ok=ok)

    # ---- the analyser ----
    def sa_setup(self, center, span, rbw=None, vbw=None, ref=10.0, att="auto"):
        sa = self.sa
        f = sa.frequency(center=center, span=span)
        bw = sa.bandwidth(rbw=rbw if rbw is not None else "auto", vbw=vbw if vbw is not None else "auto")
        a = sa.amplitude(ref_level=ref, attenuation=att)
        return {"frequency": f, "bandwidth": bw, "amplitude": a}

    def sa_live(self, center=None, span=None):
        """Leave the analyser sweeping continuously, the whole 9 kHz-7.5 GHz unless a centre and span are given, the
        bandwidths coupled, the reference level and attenuator as the last measurement had them (a strong input stays
        safe).  Every run that used it ends here (close()): Jason, 2026-10-29: "When you leave the spectrum analyzer and
        wait for me to do something that might take a while, try to leave it with a live view, preferably of its
        entire spectral range ... But please don't leave it paused."
        """
        sa = self.sa
        if center is None:
            sa.frequency(start=9e3, stop=7.5e9)
        else:
            sa.frequency(center=center, span=span)
        sa.bandwidth(rbw="auto", vbw="auto")
        sa.run()

    def sa_peak(self, center, span, rbw=None, vbw=None, ref=10.0, label=None, record=True):
        settings = self.sa_setup(center, span, rbw, vbw, ref)
        self.sa.single()
        f, dbm = self.sa.peak()
        if not record:
            return f, dbm
        return self.record("sa_peak", label=label, hz=f, dbm=dbm, settings=settings)

    def sa_trace(self, center, span, rbw=None, label=None, ref=10.0, att="auto"):
        settings = self.sa_setup(center, span, rbw, None, ref, att)
        f, dbm = self.sa.trace(fresh=True, binary=True)
        d = os.path.join(os.path.dirname(self.log.path), "traces")
        os.makedirs(d, exist_ok=True)
        name = "%s_%s.csv" % (dt.datetime.now().strftime("%Y%m%d_%H%M%S"), (label or "trace").replace(" ", "_"))
        with open(os.path.join(d, name), "w") as fh:
            fh.write("# %s %s\n# hz,dbm\n" % (label, json.dumps(settings)))
            for x, y in zip(f, dbm):
                fh.write("%.1f,%.3f\n" % (x, y))
        k = max(range(len(dbm)), key=lambda j: dbm[j])
        return self.record("sa_trace", label=label, file=os.path.relpath(os.path.join(d, name), HERE),
                           peak_hz=float(f[k]), peak_dbm=float(dbm[k]), settings=settings)

    # ---- the board ----
    def board_call(self, name, *args, **kwargs):
        t0 = time.time()
        r = getattr(self.cl, name)(*args, **kwargs)
        self.record("board", call=name, args=list(args), kwargs=kwargs, result=r, seconds=time.time() - t0)
        return r

    # ---- who answers ----
    def check(self):
        out = {}
        for name in ("psu", "dmm", "sa", "scope", "gen"):
            try:
                inst = getattr(self, name)
                out[name] = getattr(inst, "idn", None) or getattr(getattr(inst, "link", None), "idn", "open")
            except Exception as e:                                       # noqa: BLE001 - a report of what failed
                out[name] = "no: %s: %s" % (type(e).__name__, e)
        if self.cfg["psu"].get("pynq_serial"):
            try:
                out["pynq_psu"] = getattr(self.pynq_supply()[0], "idn", "open")
            except Exception as e:                                       # noqa: BLE001
                out["pynq_psu"] = "no: %s: %s" % (type(e).__name__, e)
        try:
            out["board"] = {"ping": self.cl.bus.ping(), "info": self.cl.info()}
        except Exception as e:                                           # noqa: BLE001
            out["board"] = "no: %s: %s" % (type(e).__name__, e)
        self.record("check", result=out)
        return out


def _fmt(e):
    keep = {k: v for k, v in e.items() if k not in ("t", "board", "kind", "stage")}
    s = json.dumps(keep, default=repr)
    return "%s [%s] %s %s" % (e["t"][11:19], e.get("stage") or "-", e["kind"], s if len(s) < 400 else s[:400] + " ...")


def main():
    ap = argparse.ArgumentParser(description="CostasLink rev A bring-up: instruments + board, every reading logged")
    ap.add_argument("--board", help="A or B (the two assembled boards)")
    ap.add_argument("--stage", help="the BRINGUP.md stage this belongs to, e.g. 1.2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    n = sub.add_parser("note")
    n.add_argument("text")
    p = sub.add_parser("psu")
    p.add_argument("action", choices=["smoke", "on", "off", "read", "log", "setup", "up", "pynq-on", "pynq-off", "cycle"],
                   help="with the PYNQ on the supply (psu.pynq_out): up = the PYNQ, its overlay, then the board; "
                        "pynq-off = the board, then both; cycle = pynq-off, 10 s, up; off = the board only")
    p.add_argument("--volts", type=float, default=SUPPLY_V)
    p.add_argument("--amps", type=float, default=SUPPLY_A)
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--dt", type=float, default=2.0)
    p.add_argument("--seconds", type=float, default=600.0)
    p.add_argument("--with-board", action="store_true", help="psu log: the board's detectors (NTC, +5V_RF) too")
    d = sub.add_parser("dmm")
    d.add_argument("label", help="the rail or node: %s, or any name" % ", ".join(RAILS))
    s = sub.add_parser("sa")
    s.add_argument("action", choices=["peak", "trace"])
    s.add_argument("--center", type=float, default=5.8e9)
    s.add_argument("--span", type=float, default=10e6)
    s.add_argument("--rbw", type=float)
    s.add_argument("--ref", type=float, default=10.0)
    s.add_argument("--label")
    b = sub.add_parser("board")
    b.add_argument("action", choices=["snapshot", "call", "ping"])
    b.add_argument("name", nargs="?")
    b.add_argument("args", nargs="*", help="JSON values (numbers, strings in quotes, lists)")
    r = sub.add_parser("run", help="a procedure in stages.py (python3 bringup/stages.py lists them)")
    r.add_argument("proc")
    r.add_argument("opts", nargs=argparse.REMAINDER, help="--key value pairs for the procedure")
    pz = sub.add_parser("pause", help="the watchdog counts no PYNQ silence for this long (a deliberate restart)")
    pz.add_argument("--minutes", type=float, default=10.0)
    sh = sub.add_parser("show")
    sh.add_argument("--n", type=int, default=20)
    a = ap.parse_args()

    bench = Bench(a.board, a.stage)
    try:
        if a.cmd == "check":
            print(json.dumps(bench.check(), indent=1, default=repr))
        elif a.cmd == "note":
            print(_fmt(bench.note(a.text)))
        elif a.cmd == "psu":
            import stages
            if a.action == "smoke":
                print(json.dumps(stages.smoke(bench, volts=a.volts), indent=1, default=repr))
            elif a.action == "setup":
                print(json.dumps(bench.psu_setup(a.volts, a.amps), indent=1))
            elif a.action == "on":
                bench.psu_setup(a.volts, a.amps)
                bench.psu_output(True)
                time.sleep(1.0)
                print(_fmt(bench.psu_read("on")))
            elif a.action == "off":
                bench.psu_output(False)
                print("the board's output at 0 V (the PYNQ left on)" if bench.cfg["psu"].get("pynq_out") else "output off")
            elif a.action == "pynq-on":
                print(_fmt(bench.psu_pynq(True)))
            elif a.action == "pynq-off":
                bench.psu_pynq(False)
                print("the board's output at 0 V, then the switch off: both off" if bench.cfg["psu"].get("pynq_out")
                      else "the board's supply off, then the PYNQ's: both off")
            elif a.action in ("up", "cycle"):
                if a.action == "cycle":
                    bench.psu_pynq(False)
                    time.sleep(10.0)
                print(_fmt(bench.psu_up(a.volts, a.amps)))
            elif a.action == "read":
                for k in range(a.n):
                    print(_fmt(bench.psu_read()))
                    if k + 1 < a.n:
                        time.sleep(a.dt)
            elif a.action == "log":
                stages.heat_log(bench, seconds=a.seconds, dt_s=a.dt, with_board=a.with_board)
        elif a.cmd == "dmm":
            print(_fmt(bench.dmm_read(a.label)))
        elif a.cmd == "sa":
            if a.action == "peak":
                print(_fmt(bench.sa_peak(a.center, a.span, a.rbw, ref=a.ref, label=a.label)))
            else:
                print(_fmt(bench.sa_trace(a.center, a.span, a.rbw, label=a.label, ref=a.ref)))
        elif a.cmd == "board":
            if a.action == "ping":
                print(json.dumps(bench.cl.bus.ping(), indent=1))
            elif a.action == "snapshot":
                print(json.dumps(bench.board_call("snapshot"), indent=1, default=repr))
            else:
                args = [json.loads(x) for x in a.args]
                print(json.dumps(bench.board_call(a.name, *args), indent=1, default=repr))
        elif a.cmd == "run":
            import stages
            kw = {}
            it = iter(a.opts)
            for k in it:
                v = next(it)
                try:
                    v = json.loads(v)
                except ValueError:
                    pass
                kw[k.lstrip("-").replace("-", "_")] = v
            print(json.dumps(stages.run(bench, a.proc, **kw), indent=1, default=repr))
        elif a.cmd == "pause":
            os.makedirs(os.path.dirname(WATCH_PAUSE), exist_ok=True)
            with open(WATCH_PAUSE, "w") as f:
                f.write("%.0f\n" % (time.time() + 60 * a.minutes))
            print(_fmt(bench.note("the watchdog paused for %.0f min (no PYNQ silence counted)" % a.minutes)))
        elif a.cmd == "show":
            for e in bench.log.tail(a.n):
                print(_fmt(e))
    finally:
        bench.close()


if __name__ == "__main__":
    main()
