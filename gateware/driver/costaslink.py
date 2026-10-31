"""costaslink.py: the CostasLink gateware's driver, for the PYNQ-Z2 and the Icepi Zero (Response 15).

    # on the PYNQ-Z2 (Jupyter, as root: the overlay's .bit and .hwh side by side)
    from costaslink import CostasLink, PynqBus
    cl = CostasLink(PynqBus("costaslink_top.bit"))

    # on a host with the Icepi Zero on its USB serial port (the UART at 1 Mbaud)
    from costaslink import CostasLink, UartBus
    cl = CostasLink(UartBus("/dev/ttyUSB0"))

    cl.info()                        # board, clock, samples a clock
    cl.i2c_scan()                    # BRINGUP stage 1.5: 0x0C, 0x48, 0x49, 0x60, 0x61
    cl.pll_init()                    # stage 2.1: both synthesizers at the words max2871_regs.py made
    s = SCHEMES["A3"]                # the plan's corners (PLAN.md section 18)
    cl.scheme(s)                     # the transmitter's points and the receiver's table for it
    cl.events(period=1000, count=10000); cl.rx_clear(); cl.tx_go()
    cl.rx_stats()                    # events, decisions, confirmations, latencies ...
    cl.loopback_turnaround("B1", path="sync")   # single-board loopback: RX ANT -> TX ANT through the board
    cl.loopback_turnaround("B1", path="fast")   # the same through the combinational fast path (PYNQ-Z2)
    cl.ring_run("B1")                # the fast path as a ring: one turnaround a hop

Everything goes through one register bus: register numbers and fields come from regmap.py (one level
up), the same file the Verilog's regmap.vh is generated from.  A bus is anything with read(reg) and
write(reg, value): PynqBus (AXI-Lite through MMIO), UartBus (the Icepi's ASCII protocol, uart_cmd.v),
PipeBus (the simulator, sim_pipe.py), or a fake in a test.

The driver knows nothing that the gateware's registers do not say, except the board's I2C parts and
their channels (gen/sch_rx.py, sch_slow.py, sch_win.py): the AD5696R at 0x0C (the four window
thresholds), the MCP4728s at 0x60 and 0x61 (TX references, trims, V_T2), the ADS1115 at 0x48 and the
detectors' ADS1115 at 0x49 (sheet 6).  The board's numbers (gains, levels, the detectors' scales) come from
board_constants.py, which the build generates from sim/budget.py.
"""
import math
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))           # gateware/: regmap.py, max2871_regs.py
import regmap                                      # noqa: E402
from board_constants import (RX_GAIN_DB, DEM_REG_DBM, A_REG_V, DSA_POWER_UP_DB, V_MID, G_SLOW, NF_CHAIN_DB,   # noqa: E402
                             ENBW_SLOW_HZ, ENBW_FAST_HZ, AD8310_SLOPE_V_DB, AD8310_INTERCEPT_DBV, LOG_TAP_DB, V5_DIV,
                             NTC_B, NTC_R25, NTC_RTOP, NTC_VDD, VR_I_V, VR_Q_V)

R = regmap.BY_NAME
ID_EXPECTED = 0x434C0005
ID_ACCEPTED = (0x434C0003, 0x434C0004, 0x434C0005)   # 3: no timing recovery for the BER check (the overlay of 2026-10-29);
                                                      # 4: no interference hold
BOARDS = {0: "simulation", 1: "PYNQ-Z2", 2: "Icepi Zero"}

# the fast comparators: their bit in the receiver's vectors (RX_IDLE, RX_LUT, RX_LAST), as rx_engine.v
CMP_I, CMP_QP, CMP_QN, CMP_IP, CMP_IN = 0, 1, 2, 3, 4
CMP_NAMES = ("CMP_I", "CMP_QP", "CMP_QN", "CMP_IP", "CMP_IN")
# the fast sample vector adds TRIG_IN as bit 5; the gate's inputs add the slow comparators as 6-8
FAST_INPUTS = CMP_NAMES + ("TRIG_IN",)
GATE_INPUTS = FAST_INPUTS + ("CMP_I_S", "CMP_QP_S", "CMP_QN_S")
# the capture word's 16 context bits, after the 6 x SER fast samples (capture.v)
CTX_BITS = ("MUX_RX", "MUX_TX", "CMP_I_S", "CMP_QP_S", "CMP_QN_S", "TR_A", "LOOP_HOLD", "TX_DIS",
            "I0", "I1", "Q0", "Q1", "TX_EVENT", "RX_EVENT", "RX_DECISION", "REPLY")
# with BUILD[13] / CAP_INFO[24] (the PYNQ-Z2) the ladder pads read back, 4 x SER bits after the context
TX_PIN_NAMES = ("TX_I0", "TX_I1", "TX_Q0", "TX_Q1")

# the I2C parts (the schematic generator's notes)
AD5696R = 0x0C              # A = V_TQP, B = V_TQN, C = V_TIP, D = V_TIN: 16 bits, 0-2.5 V
AD5696R_CH = {"QP": 0, "QN": 1, "IP": 2, "IN": 3}
AD5696R_VREF = 2.5
DAC1, DAC2 = 0x60, 0x61     # MCP4728: 12 bits, 0-VDD (3.3 V; the fast write keeps VREF = VDD, gain 1)
DAC1_CH = {"VR_I": 0, "VR_Q": 1, "Q_OFF_F": 2, "VC_OFF": 3}
DAC2_CH = {"V_T2": 0, "I_OFF": 1, "Q_OFF": 2, "I_OFF_F": 3}
MCP4728_VDD = 3.3
# Each MCP4728's power-up values (its EEPROM; the factory's is 0 V on every channel), and the shadows' start: the
# ladders' references at their own values, everything else mid-scale.  Not VR_I / VR_Q at mid-scale: 1.65 V there
# puts the I ladder's 11 point (the gateware's idle) at 2.0 V on IBBP and the Q ladder with TRIG IN high at 2.2 V,
# against the ADL5375's 0-2 V absolute maximum (its Table 2; found at bring-up, 2026-10-28)
DAC_DEFAULT_V = {DAC1: (VR_I_V, VR_Q_V, V_MID, V_MID), DAC2: (V_MID, V_MID, V_MID, V_MID)}
VR_MAX_V = 0.6              # the most dac() lets VR_I / VR_Q have: IBBP 1.18 V, QBBP 1.47 V at worst (every leg high)


def dac_code(volts):
    return max(0, min(4095, int(round(volts / MCP4728_VDD * 4096))))
ADS1115 = 0x48              # AIN0 I_P, AIN1 Q_P, AIN2 VC, AIN3 ERR: single-ended, +-4.096 V, 860 SPS
ADC_CH = {"I": 0, "Q": 1, "VC": 2, "ERR": 3}
ADC_LSB_V = 4.096 / 32768

# the received level (Prompt 18: "a received signal strength indicator"): no detector chip (PLAN.md section 4);
# once the loop is locked, I is the carrier's amplitude, and the DSA's setting is what the level needed.
# sim/budget.py sections 3 and 7: RX_GAIN_DB, DEM_REG_DBM, A_REG_V, DSA_POWER_UP_DB, V_MID (board_constants.py, generated)
# the interference survey (Prompt 26): no carrier, no lock; a window comparator against its threshold is the
# detector.  sim/budget.py sections 3 and 7b; ENBW "fast" from sim/wifi_channels.py (the ADL5380 and the arm)
SURVEY_ENBW_HZ = {"slow": ENBW_SLOW_HZ, "fast": ENBW_FAST_HZ}
SURVEY_LADDER_V = (0.0,) + tuple(0.0005 * 1.35 ** k for k in range(24))     # above V_MID: 0.5 mV to 0.5 V
# the interference detectors (Prompt 28, sheet 6): a second ADS1115 at 0x49 reads an AD8310 log amp on the fast
# Q arm (LOG_Q, and its peak hold PEAK_Q), +5V_RF halved (V5_MON) and an NTC (TEMP); the numbers: sim/budget.py section 8b
ADS1115_DET = 0x49
DET_CH = {"LOG_Q": 0, "PEAK_Q": 1, "V5_MON": 2, "TEMP": 3}
LOG_NOISE_DB = 2.5                   # a log amp reads Gaussian noise ~2.5 dB under a sine of the same rms (est: calibrate)

# the transmitter's ladders: a level per axis -> its two bits (tx_symbol.v: 00 = -a, 01 / 10 = 0, 11 = +a)
LEVEL_CODE = {1: 0b11, 0: 0b01, -1: 0b00}


def point_code(i, q):
    """The ladder point {Q1 Q0 I1 I0} for levels i, q in -1, 0, +1."""
    return (LEVEL_CODE[q] << 2) | LEVEL_CODE[i]


def code_levels(code):
    lv = {0b11: 1, 0b00: -1, 0b01: 0, 0b10: 0}
    return lv[code & 3], lv[(code >> 2) & 3]


def bits(value, hi, lo):
    return (value >> lo) & ((1 << (hi - lo + 1)) - 1)


# ---------------------------------------------------------------------------------------------------------
# the buses
# ---------------------------------------------------------------------------------------------------------
class PynqBus:
    """AXI-Lite through PYNQ's MMIO: register n at byte offset 4 n of the core's 4 KB.

    Goes through ip_dict, not `overlay.costaslink_0`: on PYNQ 3.0 a module reference's attribute returns
    an empty hierarchy (the GPSDO's driver found it, gateware/driver/dmtd.py attach()).  The overlay is
    downloaded unless one is passed in (Overlay(...) as root; PYNQ 3.1 on the PYNQ-Z2, Vivado 2024.1)."""

    def __init__(self, bitfile=None, overlay=None, name="costaslink_0", download=True):
        from pynq import MMIO, Overlay
        if overlay is None:
            if bitfile is None:
                bitfile = os.path.join(HERE, "costaslink_top.bit")
            overlay = Overlay(bitfile, download=download)
        self.overlay = overlay
        ip = overlay.ip_dict[name]
        self.mmio = MMIO(ip["phys_addr"], ip.get("addr_range", 4096))

    def read(self, reg):
        return self.mmio.read(4 * reg) & 0xFFFFFFFF

    def write(self, reg, value):
        self.mmio.write(4 * reg, int(value) & 0xFFFFFFFF)


class UartBus:
    """The Icepi Zero's UART (uart_cmd.v): "W aa dddddddd" -> "OK", "R aa" -> "dddddddd", 1 Mbaud 8N1."""

    def __init__(self, port, baud=1_000_000, timeout=0.5):
        import serial
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self.ser.reset_input_buffer()

    def _line(self, cmd):
        self.ser.write(cmd.encode("ascii"))
        reply = self.ser.readline().decode("ascii", "replace").strip()
        if not reply:
            raise IOError("no reply to %r" % cmd.strip())
        return reply

    def read(self, reg):
        reply = self._line("R %02X\n" % reg)
        try:
            return int(reply, 16)
        except ValueError:
            raise IOError("bad reply %r to R %02X" % (reply, reg))

    def write(self, reg, value):
        reply = self._line("W %02X %08X\n" % (reg, int(value) & 0xFFFFFFFF))
        if reply != "OK":
            raise IOError("bad reply %r to W %02X" % (reply, reg))


# ---------------------------------------------------------------------------------------------------------
# the schemes (PLAN.md section 18, sim/constellations.py), and the receiver's tables for them
# ---------------------------------------------------------------------------------------------------------
class Scheme:
    """An idle plus N messages, as the transmitter sends them and the receiver's comparators see them.

    idle, msgs: ladder points (I, Q) in levels -1, 0, +1, as the transmitter's TX_IDLE and TX_POINTS.
    pilot: the idle as it is on the air when it is not the ladder point itself (a weak pilot made by the
      VR_I / VR_Q trims with the ladders at zero), in the transmitter's units (a = 1).
    rot_deg: the receiver's frame against the transmitter's: its loop turns the idle (or the pilot) onto
      +I, so the pilot at 45 degrees is -45 here.  The Costas loop's 180-degree twin is rot_deg + 180.
    mask: the comparators that make events (bit numbers CMP_I ... CMP_IN).
    use: the comparators the settled decision reads (all five by default; one left out reads as either).
    t, t2: the window comparators' thresholds and the slow Q window's, as fractions of a (the hardware
      sets them by counting; here they only decide which side of each threshold a point is on).
    """

    def __init__(self, name, text, idle, msgs, mask, rot_deg=0.0, pilot=None, t=0.5, t2=0.1, use=None):
        self.name, self.text = name, text
        self.idle, self.msgs = tuple(idle), [tuple(m) for m in msgs]
        self.mask = sum(1 << b for b in mask)
        self.use = 0x1F if use is None else sum(1 << b for b in use)
        self.rot_deg, self.pilot, self.t, self.t2 = rot_deg, pilot, t, t2

    @property
    def n(self):
        return len(self.msgs)

    def rx_point(self, iq):
        r = math.radians(self.rot_deg)
        i, q = iq
        return (i * math.cos(r) - q * math.sin(r), i * math.sin(r) + q * math.cos(r))

    def rx_idle_point(self):
        return self.rx_point(self.pilot if self.pilot is not None else self.idle)

    # each comparator 1, 0 or None (the point sits on its threshold: noise decides)
    def fast(self, p, eps=1e-6):
        i, q = p

        def gt(x, th):
            return None if abs(x - th) < eps else int(x > th)
        return [gt(i, 0.0), gt(q, self.t), gt(-q, self.t), gt(i, self.t), gt(-i, self.t)]

    def slow(self, p, eps=1e-6):
        i, q = p

        def gt(x, th):
            return None if abs(x - th) < eps else int(x > th)
        return [gt(i, 0.0), gt(q, self.t2), gt(-q, self.t2)]

    def idle_vector(self):
        v = self.fast(self.rx_idle_point())
        if any(b is None for k, b in enumerate(v) if self.mask >> k & 1):
            raise ValueError("%s: the idle sits on a masked comparator's threshold" % self.name)
        return sum((b or 0) << k for k, b in enumerate(v))

    @staticmethod
    def _expand(tri):
        """every 5-bit vector a list of 1 / 0 / None allows"""
        out = [0]
        for k, b in enumerate(tri):
            if b is None:
                out = [x | (y << k) for x in out for y in (0, 1)]
            else:
                out = [x | (b << k) for x in out]
        return set(out)

    def settled_sets(self):
        """message k -> the vectors the five comparators can show once it has settled (a comparator the
        decision does not use reads as either: the decision samples all five)"""
        sets = []
        for m in self.msgs:
            tri = self.fast(self.rx_point(m))
            tri = [b if self.use >> k & 1 else None for k, b in enumerate(tri)]
            sets.append(self._expand(tri))
        return sets

    def changed_sets(self):
        """message k -> the masked comparators that may leave their idle value on its way"""
        iv = self.idle_vector()
        out = []
        for m in self.msgs:
            tri = self.fast(self.rx_point(m))
            s = 0
            for k, b in enumerate(tri):
                if self.mask >> k & 1 and (b is None or b != (iv >> k & 1)):
                    s |= 1 << k
            out.append(s)
        return out

    def lut(self, first_edge=False):
        """the 32-entry table {valid, message}: a vector (or a first-fired set) one message alone can
        make maps to it; one two can make, and the idle, stay invalid"""
        table = [0] * 32
        if first_edge:
            ch = self.changed_sets()
            for f in range(1, 32):
                owners = [k for k, s in enumerate(ch) if f & ~s == 0]
                if len(owners) == 1:
                    table[f] = 0x8 | owners[0]
        else:
            iv = self.idle_vector()
            sets = self.settled_sets()
            for v in range(32):
                owners = [k for k, s in enumerate(sets) if v in s]
                if len(owners) == 1 and v != iv:
                    table[v] = 0x8 | owners[0]
        return table

    def slow_exp(self):
        """RX_SLOW_EXP: message k in [4k+3:4k] = {care, CMP_QN_S, CMP_QP_S, CMP_I_S}"""
        w = 0
        for k, m in enumerate(self.msgs):
            s = self.slow(self.rx_point(m))
            if None in s:
                continue
            w |= (0x8 | s[2] << 2 | s[1] << 1 | s[0]) << (4 * k)
        return w

    def tx_points(self):
        w = 0
        for k, (i, q) in enumerate(self.msgs):
            w |= point_code(i, q) << (4 * k)
        return w

    def tx_idle(self):
        return point_code(*self.idle)

    def twin(self):
        """the same scheme seen through the Costas loop's other lock point (180 degrees)"""
        s = Scheme(self.name + "'", self.text + " (the loop's 180-degree twin)", self.idle, self.msgs, [],
                   self.rot_deg + 180.0, self.pilot, self.t, self.t2)
        s.mask, s.use = self.mask, self.use
        return s


RHO = 0.2                   # the weak pilot, a fraction of a (about -14 dBc: PLAN.md section 18's B2 choice)
_P45 = (RHO / math.sqrt(2), RHO / math.sqrt(2))
SCHEMES = {s.name: s for s in [
    Scheme("A1", "BPSK flip, an event and no bit, decided at zero by sign(I)", (1, 0), [(-1, 0)], [CMP_I]),
    Scheme("A1w", "the BPSK flip decided beside the idle: IP leaves its window (its threshold near the idle)",
           (1, 0), [(-1, 0)], [CMP_IP]),
    Scheme("A2", "1 bit: the Q step, QP / QN", (1, 0), [(1, 1), (1, -1)], [CMP_QP, CMP_QN]),
    Scheme("A3", "2 bits: the corners round a full idle (the plan's QPSK): QP / QN the event and the Q bit, "
           "sign(I) the I bit", (1, 0), [(1, 1), (1, -1), (-1, 1), (-1, -1)], [CMP_QP, CMP_QN]),
    Scheme("A4", "1 bit: the pilot at 45 degrees, TX (-1, 1) / (1, -1) onto +Q / -Q", (0, 0), [(-1, 1), (1, -1)],
           [CMP_QP, CMP_QN], rot_deg=-45.0, pilot=_P45),
    Scheme("B1", "2 bits: a weak pilot on +I and the four axis points, one window each", (0, 0),
           [(1, 0), (-1, 0), (0, 1), (0, -1)], [CMP_IP, CMP_IN, CMP_QP, CMP_QN], pilot=(RHO, 0.0)),
    Scheme("B2", "2 bits: the pilot at 45 degrees and the four corners onto the axes, one window each", (0, 0),
           [(1, 1), (-1, -1), (-1, 1), (1, -1)], [CMP_IP, CMP_IN, CMP_QP, CMP_QN], rot_deg=-45.0, pilot=_P45),
]}


# ---------------------------------------------------------------------------------------------------------
# the board
# ---------------------------------------------------------------------------------------------------------
class CostasLink:
    """The register bus with names, and the operations BRINGUP.md's stages are made of."""

    def __init__(self, bus, check=True):
        self.bus = bus
        self._dac = {d: [dac_code(v) for v in DAC_DEFAULT_V[d]] for d in (DAC1, DAC2)}
        self._pll = {0: (5800.0, 25.0, None), 1: (5800.0, 25.0, None)}   # the words PLL_INIT sends (max2871_words.vh)
        self._lo_mon = {0: False, 1: False}                                # RFOUTB, the LO MON jacks: off in PLL_INIT
        if check:
            ident = self.rd("ID")
            if ident not in ID_ACCEPTED:
                raise IOError("ID reads 0x%08X, not 0x%08X: wrong overlay, or no board" % (ident, ID_EXPECTED))
            self.cdr = ident >= 0x434C0004
            self.ihold_ok = ident >= 0x434C0005
        b = self.rd("BUILD")
        self.ser = bits(b, 7, 0) or 1
        self.board = bits(b, 11, 8)
        self.fast_path, self.tx_readback, self.early_lane = bits(b, 12, 12), bits(b, 13, 13), bits(b, 14, 14)
        self.reply_reg = bits(b, 15, 15)            # the synchronous reply a clock later (the Icepi Zero)
        self.clk_mhz = bits(b, 31, 16) or 100
        self.t_clk = 1e-6 / self.clk_mhz
        self.t_sample = self.t_clk / self.ser
        self._dsa_db = DSA_POWER_UP_DB
        self._i_zero = V_MID

    def wait_s(self, seconds):
        """wall time on a board; the simulator's clocks on a bus that has them (PipeBus)"""
        if hasattr(self.bus, "clocks"):
            self.bus.clocks(max(1, int(round(seconds / self.t_clk))))
        else:
            time.sleep(seconds)

    # ---- registers ----
    def rd(self, name):
        return self.bus.read(R[name])

    def wr(self, name, value):
        self.bus.write(R[name], value)

    def info(self):
        return {"board": BOARDS.get(self.board, self.board), "clock_MHz": self.clk_mhz, "samples_per_clock": self.ser,
                "sample_ns": self.t_sample * 1e9, "capture": self.cap_info(), "fast_path": self.fast_path,
                "tx_readback": self.tx_readback, "early_lane": self.early_lane, "reply_reg": self.reply_reg}

    def _wait(self, name, mask, timeout=1.0, want=0):
        t0 = time.time()
        while True:
            v = self.rd(name)
            if (v & mask) == want:
                return v
            if time.time() - t0 > timeout:
                raise TimeoutError("%s: 0x%08X still has 0x%X" % (name, v, mask))
            time.sleep(0.0005)

    # ---- the control pins (CTRL) ----
    CTRL_BITS = {"tx_dis": 0, "loop_hold": 1, "loop_sel": 2, "tr_a": 3, "id_enable": 6, "txq1_hiz": 8}

    def ctrl(self, **kw):
        """ctrl(tx_dis=0, loop_hold=0, ...): change the named CTRL bits, keep the others"""
        v = self.rd("CTRL")
        for k, on in kw.items():
            b = self.CTRL_BITS[k]
            v = (v | (1 << b)) if on else (v & ~(1 << b))
        self.wr("CTRL", v & ~0x80)
        return v

    def id_now(self):
        self.wr("CTRL", (self.rd("CTRL") | 0x80))

    def status(self):
        s = self.rd("STATUS")
        return {"mux_tx": s & 1, "mux_rx": s >> 1 & 1, "spi_busy": s >> 2 & 1, "i2c_busy": s >> 3 & 1,
                "id_active": s >> 4 & 1, "key_down": s >> 5 & 1}

    def cmp_state(self):
        v = self.rd("CMP_STATE")
        names = ("CMP_I", "CMP_QP", "CMP_QN", "CMP_I_S", "CMP_QP_S", "CMP_QN_S", "TRIG_IN", "MUX_TX", "MUX_RX",
                 "CMP_IP", "CMP_IN")
        return {n: v >> k & 1 for k, n in enumerate(names)}

    # ---- the triggers TRIG A / TRIG B (TRIG_CFG) ----
    def triggers(self, width=10, a="tx_event", b="rx_decision", b_rising_only=False):
        """TRIG A: 'symbol' (TX_MODE 0's changes), 'tx_event' or 'reply' (a synchronous reply's first clock,
        the fast path's first change); TRIG B: 'cmp_i' (its edges), 'rx_event', 'rx_decision' or 'rx_valid'.
        The marks of BRINGUP stage 3.4 and 4.2."""
        asrc = {"symbol": 0, "tx_event": 1, "reply": 2}[a]
        bsrc = {"cmp_i": 0, "rx_event": 1, "rx_decision": 2, "rx_valid": 3}[b]
        v = (width & 0xFF) | (1 << 8) | (1 << 9) | (int(b_rising_only) << 10) | (asrc << 11) | (bsrc << 13)
        self.wr("TRIG_CFG", v)

    # ---- SPI: the synthesizers and the DSA ----
    def spi(self, slave, word):
        """slave 0 TX PLL, 1 RX PLL, 2 DSA (8 bits, LSB first, D7 = 0)"""
        self._wait("SPI_CTRL", 0x3)
        self.wr("SPI_DATA", word)
        self.wr("SPI_CTRL", slave & 3)
        self._wait("SPI_CTRL", 0x3)

    def pll_init(self, timeout=1.0):
        """both synthesizers' power-up sequence (the words compiled in from max2871_regs.py)"""
        self.wr("PLL_INIT", 1)
        self._wait("PLL_INIT", 0x1, timeout)
        return bool(self.rd("PLL_INIT") & 2)

    def pll_tune(self, which, f_mhz, f_pfd=25.0, cp=None, lo_mon=None):
        """retune one synthesizer (0 TX, 1 RX) to f_mhz: the six words, register 5 first.  Integer-N from
        the 25 MHz reference: f_pfd 25 MHz (R = 1, the link's 25 MHz channels), or 5 MHz (R = 5, every WiFi
        centre, for the survey; cp 15 holds the loop's gain).  lo_mon: RFOUTB on (the LO MON jack), or None
        to keep what lo_mon() last set"""
        import max2871_regs
        if lo_mon is not None:
            self._lo_mon[which] = bool(lo_mon)
        kw = {} if cp is None else {"cp": cp}
        for w in max2871_regs.regs(f_mhz, f_pfd=f_pfd, rfb_en=self._lo_mon[which], **kw):
            self.spi(which, w)
        self._pll[which] = (f_mhz, f_pfd, cp)

    def lo_mon(self, which, on=True):
        """the LO MON jack of one synthesizer (0 TX: LO TX MON, 1 RX: LO RX MON) on or off: RFOUTB, which the
        power-up words (PLL_INIT) leave off, so the jacks are dark until this is called (BRINGUP stage 2.2).
        Resends the six words at the synthesizer's present frequency: a relock of a few ms."""
        f, f_pfd, cp = self._pll[which]
        self.pll_tune(which, f, f_pfd=f_pfd, cp=cp, lo_mon=on)

    def pll_locked(self):
        """both synthesizers' lock detect (their MUX pins), {'tx': 0/1, 'rx': 0/1}"""
        s = self.status()
        return {"tx": s["mux_tx"], "rx": s["mux_rx"]}

    def dsa(self, db):
        """the PE43711: 0-31.75 dB in 0.25 dB steps"""
        code = max(0, min(127, int(round(db / 0.25))))
        self.spi(2, code)
        self._dsa_db = code * 0.25
        return code * 0.25

    # ---- the received level and the AGC ----
    def rssi_zero(self, n=16):
        """I_P's level with no carrier (the far end muted): the arm's own centre, which received_dBm()
        measures the amplitude from (V_MID until this is called)"""
        self._i_zero = sum(self.adc("I") for _ in range(n)) / n
        return self._i_zero

    def received_dBm(self, n=8, ext_db=0.0):
        """The carrier's level (dBm), from the locked I arm (the ADC's I_P, n readings) and the DSA's
        setting: at RX ANT, or at the antenna when `ext_db` names the gain of what is between them (an
        LNA module +29, measured on the VNA; a pad -30).  Valid only with the loop locked (I is then the amplitude, at 0 or
        180 degrees); None when the arm reads less than two ADC steps.  Unlocked, read RX MON instead."""
        v = sum(self.adc("I") for _ in range(n)) / n
        a = 2.0 * abs(v - self._i_zero)                       # I_P is V_MID + I / 2
        if a < 2 * ADC_LSB_V:
            return None
        return DEM_REG_DBM + 20 * math.log10(a / A_REG_V) - RX_GAIN_DB + self._dsa_db - ext_db

    def agc(self, target_db=0.0, tol_db=0.5, steps=12, settle_s=0.01):
        """Step the DSA until the demodulator sits at the regulated level (+ target_db) within tol_db,
        which also sets the Costas loop's gain (Kd follows the level: PLAN.md section 10.1).  Returns
        (the DSA's dB, the level at RX ANT in dBm), or the last pair when the DSA runs out of range."""
        r = None
        for _ in range(steps):
            r = self.received_dBm()
            if r is None:                                     # nothing readable: open the DSA by 10 dB
                if self._dsa_db <= 0:
                    return self._dsa_db, None
                self.dsa(self._dsa_db - 10.0)
                self.wait_s(settle_s)
                continue
            dem = r + RX_GAIN_DB - self._dsa_db               # what the demodulator sees now
            err = dem - (DEM_REG_DBM + target_db)
            if abs(err) <= tol_db:
                break
            want = min(31.75, max(0.0, self._dsa_db + err))
            if abs(want - self._dsa_db) < 0.125:               # at an end of the DSA's range
                break
            self.dsa(want)
            self.wait_s(settle_s)
        return self._dsa_db, r

    # ---- I2C ----
    def i2c(self, addr, wbytes=b"", nread=0, timeout=0.1):
        """one transaction: up to 9 bytes written, then (repeated start) up to 2 read; returns the bytes
        read, or raises on a NACK.  No bytes either way is a probe."""
        wbytes = bytes(wbytes)
        assert len(wbytes) <= 9 and 0 <= nread <= 2
        buf = wbytes + bytes(9 - len(wbytes))
        self._wait("I2C_CTRL", 1 << 16, timeout)
        self.wr("I2C_WDATA0", int.from_bytes(buf[0:4], "big"))
        self.wr("I2C_WDATA1", int.from_bytes(buf[4:8], "big"))
        self.wr("I2C_WDATA2", buf[8] << 24)
        self.wr("I2C_CTRL", (addr & 0x7F) | (len(wbytes) << 8) | (nread << 12))
        v = self._wait("I2C_CTRL", 1 << 16, timeout)
        if v >> 19 & 1:
            raise IOError("I2C 0x%02X: SCL held low for 10 ms, the transaction abandoned (a stuck bus: SCL %d, SDA %d now)"
                          % (addr, v >> 20 & 1, v >> 21 & 1))
        if v >> 17 & 1:
            raise IOError("I2C 0x%02X: no acknowledge" % addr)
        r = self.rd("I2C_RDATA") & 0xFFFF
        return bytes([r >> 8, r & 0xFF]) if nread == 2 else bytes([r & 0xFF]) if nread == 1 else b""

    def i2c_lines(self):
        """the I2C lines as they are now (1 = high), and whether the last transaction was abandoned on a stuck SCL:
        both high when idle; SCL low with nothing driving it is a bridge or a dead part on the bus"""
        v = self.rd("I2C_CTRL")
        return {"scl": v >> 20 & 1, "sda": v >> 21 & 1, "busy": v >> 16 & 1, "timeout": v >> 19 & 1}

    def i2c_probe(self, addr):
        try:
            self.i2c(addr)
            return True
        except IOError:
            return False

    def i2c_scan(self, addrs=range(0x08, 0x78)):
        """BRINGUP stage 1.5: expect 0x0C (AD5696R), 0x48 and 0x49 (the ADS1115s), 0x60 and 0x61 (the MCP4728s)"""
        return [a for a in addrs if self.i2c_probe(a)]

    # the window thresholds: AD5696R, write-and-update (command 3) one channel
    def threshold(self, which, volts=None, code=None):
        """which: 'QP', 'QN', 'IP', 'IN'; volts (0-2.5 V; the arms' centre is 1.65 V) or a 16-bit code"""
        if code is None:
            code = int(round(volts / AD5696R_VREF * 65536))
        code = max(0, min(65535, int(code)))
        ch = AD5696R_CH[which]
        self.i2c(AD5696R, bytes([0x30 | (1 << ch), code >> 8, code & 0xFF]))
        return code

    def threshold_at(self, which, frac_a, a_volts):
        """a threshold frac_a of the arm's full step a (volts at the comparator) out from the centre, on
        the comparator's own side (QP, IP above V_MID; QN, IN: their arm leg is the inverted one, so also
        above V_MID: CMP_IN fires when I_N > V_TIN, i.e. I < -2 (V_TIN - V_MID))"""
        return self.threshold(which, V_MID + frac_a * a_volts / 2.0)

    # the MCP4728s: the fast write of all four channels (DAC_AB, DAC_CD, DAC_GO); a shadow of each
    def dac(self, which=DAC1, **channels):
        """dac(DAC1, VR_I=0.21, VC_OFF=1.65) in volts, or codes with code_ prefix (code_VR_I=260).  The ladders'
        references are board_constants.VR_I_V and VR_Q_V (they differ since Prompt 35: the Q ladder's third leg is TRIG IN)."""
        names = DAC1_CH if which == DAC1 else DAC2_CH
        sh = list(self._dac[which])
        for k, v in channels.items():
            if k.startswith("code_"):
                sh[names[k[5:]]] = max(0, min(4095, int(v)))
            else:
                sh[names[k]] = dac_code(v)
        if which == DAC1:                    # the ladders' references: DAC_DEFAULT_V's note
            for k in ("VR_I", "VR_Q"):
                if sh[names[k]] > dac_code(VR_MAX_V):
                    raise ValueError("%s %.3f V is over VR_MAX_V %.2f V (the ADL5375's baseband pins)"
                                     % (k, sh[names[k]] * MCP4728_VDD / 4096, VR_MAX_V))
        self._dac[which] = sh
        self._wait("DAC_GO", 1)
        self.wr("DAC_AB", sh[0] << 16 | sh[1])
        self.wr("DAC_CD", sh[2] << 16 | sh[3])
        self.wr("DAC_GO", 1 if which == DAC2 else 0)
        self._wait("DAC_GO", 1)
        return list(sh)

    def dac_eeprom(self, which=DAC1, codes=None):
        """BRINGUP stage 0.4 / 1.5: the power-up defaults (EEPROM) of all four channels: the sequential
        write from channel A (0b01010 00 0), VREF = VDD, gain 1, normal power, 9 bytes; the EEPROM takes
        up to 50 ms.  codes: DAC_DEFAULT_V's by default (the ladders' references at VR_I_V / VR_Q_V)"""
        if codes is None:
            codes = [dac_code(v) for v in DAC_DEFAULT_V[which]]
        if which == DAC1 and max(codes[0], codes[1]) > dac_code(VR_MAX_V):
            raise ValueError("VR_I / VR_Q over VR_MAX_V in an EEPROM default (the ADL5375's baseband pins)")
        b = [0x50]
        for c in codes:
            c = max(0, min(4095, int(c)))
            b += [c >> 8 & 0x0F, c & 0xFF]
        self.i2c(which, bytes(b))
        time.sleep(0.06)
        self._dac[which] = [int(c) for c in codes]

    def adc(self, ch, settle=0.003):
        """the ADS1115, single shot at 860 SPS: ch 'I', 'Q', 'VC', 'ERR' (or 0-3) -> volts"""
        c = ADC_CH.get(ch, ch)
        self._wait("I2C_CTRL", 1 << 16)
        self.wr("ADC_CFG", c)
        self._wait("I2C_CTRL", 1 << 16)
        time.sleep(settle)
        self.wr("ADC_READ", 1)
        self._wait("I2C_CTRL", 1 << 16)
        v = self.rd("ADC_READ")
        if not v >> 16 & 1:
            raise IOError("ADC: no valid conversion")
        raw = v & 0xFFFF
        if raw & 0x8000:
            raw -= 0x10000
        return raw * ADC_LSB_V

    def adc_all(self):
        return {k: self.adc(k) for k in ADC_CH}

    # ---- the first firmware's counters ----
    def counters(self):
        names = ("EDGE_CNT0", "EDGE_CNT1", "EDGE_CNT2", "EDGE_CNT3", "EDGE_CNT4", "EDGE_CNT5", "EDGE_CNT6", "EDGE_CNT7")
        labels = ("CMP_I", "CMP_QP", "CMP_QN", "CMP_I_S", "CMP_QP_S", "CMP_QN_S", "CMP_IP", "CMP_IN")
        return {lab: self.rd(n) for lab, n in zip(labels, names)}

    def counters_clear(self):
        self.wr("CNT_CTRL", 1)

    # ---- the transmitter (tx_engine.v) ----
    MODES = {"txsym": 0, "events": 1, "trig_in": 2, "prbs": 3, "rotate": 4, "hold": 5}
    SOURCES = {"fixed": 0, "count": 1, "prbs": 2}
    POLYS = {7: 0, 9: 1, 15: 2, 23: 3, 31: 4}

    def tx_mode(self, mode, n=None, source="count", backwards=False, gated=False):
        n = n or 1
        assert 1 <= n <= 8
        v = self.MODES[mode] | self.SOURCES[source] << 4 | (n - 1) << 8 | int(backwards) << 11 | int(gated) << 12
        self.wr("TX_MODE", v)

    def tx_points(self, idle, points):
        """idle and the message points as ladder codes {Q1 Q0 I1 I0} (point_code(i, q))"""
        self.wr("TX_IDLE", idle & 0xF)
        w = 0
        for k, p in enumerate(points):
            w |= (p & 0xF) << (4 * k)
        self.wr("TX_POINTS", w)

    def tx_timing(self, period=None, width=None, count=None):
        if period is not None:
            self.wr("TX_PERIOD", max(1, int(period)))
        if width is not None:
            self.wr("TX_WIDTH", max(1, int(width)))
        if count is not None:
            self.wr("TX_COUNT", int(count))

    def tx_prbs(self, poly=15, reseed=True):
        self.wr("TX_PRBS", self.POLYS[poly] | int(reseed) << 8)

    def tx_msg(self, k):
        self.wr("TX_MSG", k & 7)

    def tx_go(self):
        self.wr("TX_GO", 1)

    def tx_stop(self):
        self.wr("TX_GO", 2)

    def tx_one(self):
        self.wr("TX_GO", 4)

    def tx_stat(self):
        g, s = self.rd("TX_GO"), self.rd("TX_STAT")
        return {"running": g & 1, "in_event": g >> 1 & 1, "last_msg": s & 7, "sent": s >> 8,
                "evt_ts": self.rd("TX_EVT_TS")}

    def hold_point(self, i, q):
        """TX_MODE 5: one ladder point held (the arms' offsets, the carrier null with (0, 0), the scope)"""
        self.tx_points(point_code(1, 0), [point_code(i, q)])
        self.tx_msg(0)
        self.tx_mode("hold")

    # ---- the receiver (rx_engine.v) ----
    def rx_config(self, idle, mask, lut, slow_exp=0, delay=4, quiet=4, confirm=6, window=100, first_edge=False,
                  ref="tx", single=False, row="tx", enable=True):
        """the decoder: idle vector and event mask (5 bits each, CMP_I ... CMP_IN), the 32-entry table,
        the slow comparators' expectations, the decision delay (samples after the event), the quiet clocks
        before re-arming, the confirm delay (clocks after the decision), the reference window (clocks)"""
        self.wr("RX_IDLE", (idle & 0x1F) | (mask & 0x1F) << 8)
        w = 0
        for v, e in enumerate(lut):
            w |= (e & 0xF) << (4 * v)
        for k in range(4):
            self.wr("RX_LUT%d" % k, w >> (32 * k) & 0xFFFFFFFF)
        self.wr("RX_SLOW_EXP", slow_exp)
        self.wr("RX_TIMING", (delay & 0xFF) | (quiet & 0xFF) << 8 | (confirm & 0xFF) << 16)
        self.wr("RX_WINDOW", int(window))
        self._rx_ctrl = (int(enable) | int(first_edge) << 2 | int(ref == "trig_in") << 3 | int(single) << 4
                         | ((row & 7) << 16 if row != "tx" else 1 << 19))
        self.wr("RX_CTRL", self._rx_ctrl)

    def rx_clear(self, wait=True):
        """the counters, the confusion matrix and the histogram (the clear walks 1024 bins: 10 us)"""
        ctrl = getattr(self, "_rx_ctrl", self.rd("RX_CTRL") & ~2)
        self.wr("RX_CTRL", ctrl | 2)
        if wait:
            self.wait_s(1100 * self.t_clk)

    def rx_enable(self, on=True):
        ctrl = getattr(self, "_rx_ctrl", self.rd("RX_CTRL") & ~2)
        self._rx_ctrl = (ctrl | 1) if on else (ctrl & ~1)
        self.wr("RX_CTRL", self._rx_ctrl)

    def rx_stats(self):
        s = {k.lower(): self.rd("RX_" + k) for k in ("EVENTS", "DECIDED", "CONFIRM", "VETO", "FALSE", "MISSED", "REFS")}
        n = self.rd("RX_LAT_N")
        s["lat_n"] = n
        s["lat_min"] = self.rd("RX_LAT_MIN") & 0xFFFF
        s["lat_max"] = self.rd("RX_LAT_MAX") & 0xFFFF
        s["lat_mean"] = self.rd("RX_LAT_SUM") / n if n else None
        s["sample_ns"] = self.t_sample * 1e9
        return s

    def rx_last(self):
        v, lat = self.rd("RX_LAST"), self.rd("RX_LAST_LAT")
        return {"msg": v & 7, "valid": v >> 3 & 1, "vector": v >> 4 & 0x1F, "fired": v >> 9 & 0x1F,
                "confirmed": v >> 14 & 1, "vetoed": v >> 15 & 1, "had_ref": v >> 16 & 1,
                "ref_to_event": lat & 0xFFFF, "ref_to_decision": lat >> 16, "evt_ts": self.rd("RX_EVT_TS")}

    def confusion(self):
        """8 x 8: [sent][decoded]"""
        self.wr("RX_CM_ADDR", 0)
        cells = [self.rd("RX_CM_DATA") for _ in range(64)]
        return [cells[8 * r:8 * r + 8] for r in range(8)]

    def hist_config(self, what="ref_to_decision", shift=0):
        """what: 'ref_to_event', 'ref_to_decision' or 'event_to_event'; a bin is 2^shift samples"""
        self.wr("RX_HIST_CFG", {"ref_to_event": 0, "ref_to_decision": 1, "event_to_event": 2}[what] | (shift & 15) << 4)

    def histogram(self, bins=1024):
        self.wr("RX_HIST_ADDR", 0)
        return [self.rd("RX_HIST_DATA") for _ in range(bins)]

    def ber_config(self, poly=15, phase=None, invert=False, enable=True, cdr=False, gain=4, period=None):
        """the PRBS check on CMP_I, sampled `phase` samples into each symbol (TX_PERIOD clocks long).
        Enabling starts a new count; disabling keeps it, so stop the check before reading a snapshot.
        cdr: the symbol timing recovered from CMP_I's own edges (ID version 4: a transmitter on another clock),
        `phase` then the sampling point's distance from the edge, mid-symbol by default (period x SER / 2,
        the period TX_PERIOD's, given here or read back); gain: the recovery's loop gain, 2^-gain."""
        if cdr and not getattr(self, "cdr", False):
            raise IOError("this overlay has no timing recovery (ID version 4 has)")
        if phase is None:
            if cdr:
                period = period or self.rd("TX_PERIOD")
                phase = period * self.ser // 2
            else:
                phase = self.ser // 2
        self.wr("RX_BER_CFG", int(enable) | int(invert) << 1 | self.POLYS[poly] << 4 | (phase & 0xFFFF) << 8
                | int(bool(cdr)) << 24 | (gain & 0xF) << 25)

    def ihold(self, on=True, mask=(CMP_QP, CMP_QN), window=256, thresh=8, hold_s=1e-3, max_s=5.0):
        """the interference hold (ID version 5, ihold.v): LOOP_HOLD while the comparators in `mask` change in `thresh`
        or more of each `window` clocks (a power of 2, 8-1024), released hold_s after they were last busy; never longer
        than max_s at a time.  A hold starts only after a quiet window, so it catches an interferer arriving at a
        locked loop and never freezes a lost, beating one.  The defaults leave the link's
        own events and BPSK on I alone and catch an interferer's beat of 1 MHz and more from about -6 dB"""
        if not getattr(self, "ihold_ok", False):
            raise IOError("this overlay has no interference hold (ID version 5 has)")
        m = 0
        for c in mask:
            m |= 1 << c
        wlog = max(0, min(7, int(window).bit_length() - 1 - 3)) if window else 5
        self.wr("RX_IHOLD_HOLD", int(hold_s * self.clk_mhz * 1e6))
        self.wr("RX_IHOLD_MAX", int(max_s * self.clk_mhz * 1e6))
        self.wr("RX_IHOLD_CFG", int(bool(on)) | (wlog & 7) << 1 | (thresh & 0xFF) << 8 | (m & 0x1F) << 16)

    def shold(self, on=True, mask=(CMP_IP, CMP_IN, CMP_QP, CMP_QN), window=256, thresh=64, hold_s=1e-3, max_s=10.0):
        """the signal holdover (ID version 5, ihold.v LEVEL 1): LOOP_HOLD while fewer than `thresh` of each `window`
        clocks have a comparator of `mask` high (the carrier gone: someone in front of the antenna), released hold_s
        after it is back; never longer than max_s at a time.  With the windows at 0.5 a it holds from a fade of about
        6 dB, where the decisions stop anyway; a lost loop's beat keeps the windows busy, so it never holds a lost
        loop.  Switch it off while searching for the carrier"""
        if not getattr(self, "ihold_ok", False):
            raise IOError("this overlay has no signal holdover (ID version 5 has)")
        m = 0
        for c in mask:
            m |= 1 << c
        wlog = max(0, min(7, int(window).bit_length() - 1 - 3)) if window else 5
        self.wr("RX_SHOLD_HOLD", int(hold_s * self.clk_mhz * 1e6))
        self.wr("RX_SHOLD_MAX", int(max_s * self.clk_mhz * 1e6))
        self.wr("RX_SHOLD_CFG", int(bool(on)) | (wlog & 7) << 1 | (thresh & 0xFF) << 8 | (m & 0x1F) << 16)

    def shold_state(self):
        c = self.rd("RX_SHOLD_CFG")
        return {"on": c & 1, "holding": c >> 4 & 1, "last_count": c >> 24 & 0xFF, "holds": self.rd("RX_SHOLD_N"),
                "clocks": self.rd("RX_SHOLD_CLK"), "seconds": self.rd("RX_SHOLD_CLK") / (self.clk_mhz * 1e6)}

    def protect(self, on=True):
        """both holds with their defaults (the deployment's setting): on once locked, off while searching"""
        self.ihold(on)
        self.shold(on)

    def ihold_state(self):
        c = self.rd("RX_IHOLD_CFG")
        return {"on": c & 1, "holding": c >> 4 & 1, "last_count": c >> 24 & 0xFF, "holds": self.rd("RX_IHOLD_N"),
                "clocks": self.rd("RX_IHOLD_CLK"), "seconds": self.rd("RX_IHOLD_CLK") / (self.clk_mhz * 1e6)}

    def cdr_state(self):
        """the timing recovery since the last RX_BER_CFG write: its last edge error (samples), its corrections' sum
        (samples) and the edges seen"""
        e = self.rd("RX_CDR_ERR")
        sm = self.rd("RX_CDR_SUM")
        e = e - (1 << 32) if e & 0x80000000 else e
        sm = sm - (1 << 32) if sm & 0x80000000 else sm
        return {"err_samples": e / 16.0, "sum_samples": sm / 256.0, "edges": self.rd("RX_CDR_EDGES")}

    def ber(self):
        """the count so far (read BITS after ERR: while the check runs, ERR never exceeds BITS)"""
        e = self.rd("RX_BER_ERR")
        b = self.rd("RX_BER_BITS")
        return {"bits": b, "mismatches": e, "ber": (e / 3.0) / b if b else None}

    def scheme(self, s, first_edge=False, delay=None, quiet=4, confirm=6, window=100, n_tx=None):
        """the transmitter's points and the receiver's table for scheme s (a Scheme or a SCHEMES key)"""
        if isinstance(s, str):
            s = SCHEMES[s]
        self.tx_points(s.tx_idle(), [point_code(i, q) for i, q in s.msgs])
        if delay is None:
            delay = 2 * self.ser                     # two clocks of samples into the rise: a start
        self.rx_config(s.idle_vector(), s.mask, s.lut(first_edge), s.slow_exp(), delay=delay, quiet=quiet,
                       confirm=confirm, window=window, first_edge=first_edge)
        self._scheme = s
        return s

    def events(self, period=1000, width=20, count=0, source="count", n=None, gated=False, mode="events"):
        """TX_MODE 1 (or 'trig_in'): an event every `period` clocks (or on TRIG_IN), `width` clocks long"""
        n = n or getattr(getattr(self, "_scheme", None), "n", 1)
        self.tx_timing(period, width, count)
        self.tx_mode(mode, n=n, source=source, gated=gated)

    # ---- the sequencer and the counting gate (seq_gate.v) ----
    SEQ_BITS = {"tr_a": 0, "loop_hold": 1, "tx_dis": 2, "tx_gate": 3}

    def seq_program(self, steps, loop=False, enable=True):
        """steps: up to 8 of (clocks, {'tr_a': 1, 'loop_hold': 0, 'tx_dis': 1, 'tx_gate': 0}); missing bits
        are 1 (receive, held, muted: the safe state) except the TX gate"""
        assert 1 <= len(steps) <= 8
        for k, (clocks, outs) in enumerate(steps):
            v = 0
            for name, b in self.SEQ_BITS.items():
                if outs.get(name, 0 if name == "tx_gate" else 1):
                    v |= 1 << b
            self.wr("SEQ_SEL", k)
            self.wr("SEQ_OUT", v)
            self.wr("SEQ_DUR", max(1, int(clocks)))
        self._seq = (len(steps) - 1) << 8 | int(loop) << 1 | int(enable) << 11
        self.wr("SEQ_CTRL", self._seq)

    def seq_run(self):
        self.wr("SEQ_CTRL", getattr(self, "_seq", 1 << 11) | 1)

    def seq_stop(self):
        self.wr("SEQ_CTRL", getattr(self, "_seq", 1 << 11) | 4)

    def seq_state(self):
        v = self.rd("SEQ_CTRL")
        return {"running": v & 1, "step": v >> 8 & 7, "enable": v >> 11 & 1}

    def gate(self, clocks=None, seconds=None, inputs=GATE_INPUTS, timeout=None):
        """open the gate for `clocks` (or `seconds`) and return, per input, its edges and its high samples
        (fast inputs SER a clock), and the RX events: the counts every threshold is set by (stage 3.7)"""
        if clocks is None:
            clocks = int(round((seconds or 0.1) / self.t_clk))
        self.wr("GATE_LEN", int(clocks))
        self.wr("GATE_CTRL", 1)
        dt = clocks * self.t_clk
        self.wait_s(dt)
        self._wait("GATE_CTRL", 0x1, timeout or (dt + 1.0))
        out = {"clocks": clocks, "seconds": dt, "rx_events": self.rd("GATE_EVENTS")}
        for name in inputs:
            k = GATE_INPUTS.index(name)
            self.wr("GATE_SEL", k)
            per_clock = self.ser if k < 6 else 1
            e, h = self.rd("GATE_EDGES"), self.rd("GATE_HIGH")
            out[name] = {"edges": e, "high": h, "duty": h / float(clocks * per_clock), "rate_hz": e / dt}
        return out

    # ---- the capture buffer (capture.v) ----
    TRIGGERS = {"none": 0, "tx_event": 1, "rx_event": 2, "trig_in": 3, "any_change": 4, "rx_decision": 5,
                "seq_step": 6, "reply": 7}

    def cap_info(self):
        v = self.rd("CAP_INFO")
        return {"ser": v & 0xFF, "width": v >> 8 & 0xFF, "depth": 1 << (v >> 16 & 0xFF), "tx_readback": v >> 24 & 1}

    def cap_arm(self, trigger="tx_event", post=None):
        info = self.cap_info()
        if post is None:
            post = info["depth"] // 4
        self.wr("CAP_POST", int(post))
        self.wr("CAP_CTRL", self.TRIGGERS[trigger] << 4 | 1)

    def cap_force(self):
        self.wr("CAP_CTRL", (self.rd("CAP_CTRL") & 0x70) | 2)

    def cap_state(self):
        v = self.rd("CAP_CTRL")
        return {"armed": v & 1, "triggered": v >> 1 & 1, "done": v >> 2 & 1, "filled": v >> 3 & 1}

    def cap_read(self, timeout=1.0):
        """the buffer, oldest word first, once the capture is done: per fast input a list of samples (one
        per sample, SER per word), per context bit a list (one per word), where the trigger fell, and the
        first word this capture wrote (`valid_from`: the ones before it are older, stale).  With the ladder
        pads read back (the PYNQ-Z2): per pin a list of samples and TX_PINS, the code {Q1 Q0 I1 I0} per
        sample (`tx_pins_lag`: samples they lag the comparators' samples, SER in the simulator's model)."""
        self._wait("CAP_CTRL", 0x4, timeout, want=0x4)
        info = self.cap_info()
        ser, width, depth = info["ser"], info["width"], info["depth"]
        chunks = (width + 31) // 32
        self.wr("CAP_ADDR", 0)
        words = []
        for _ in range(depth):
            w = 0
            for c in range(chunks):
                w |= self.rd("CAP_DATA") << (32 * c)
            words.append(w)
        t = self.rd("CAP_TRIG")
        trig, nvalid = t & 0xFFFF, t >> 16
        out = {"trigger_word": trig, "trigger_sample": trig * ser, "sample_ns": self.t_sample * 1e9,
               "filled": self.cap_state()["filled"], "valid_from": max(0, depth - nvalid), "words": words}
        for k, name in enumerate(FAST_INPUTS):
            out[name] = [w >> (6 * s + k) & 1 for w in words for s in range(ser)]
        for k, name in enumerate(CTX_BITS):
            out[name] = [w >> (6 * ser + k) & 1 for w in words]
        if info["tx_readback"]:
            base = 6 * ser + 16
            for p, name in enumerate(TX_PIN_NAMES):
                out[name] = [w >> (base + 4 * s + p) & 1 for w in words for s in range(ser)]
            out["TX_PINS"] = [w >> (base + 4 * s) & 0xF for w in words for s in range(ser)]
            out["tx_pins_lag"] = ser if self.board == 0 else 0
        return out

    def capture(self, trigger="tx_event", post=None, start=None, timeout=1.0):
        """arm, run start() (a callable that makes the trigger happen, e.g. self.tx_one), read"""
        self.cap_arm(trigger, post)
        if start is not None:
            start()
        return self.cap_read(timeout)


    # ---- the receive-to-transmit paths and the turnaround counter (turnaround.v, Prompt 36) ----
    # Three ways to answer a received state, all measured the same way: in single-board loopback (TX ANT
    # cabled to RX ANT through an attenuator) this board's TX event is the stimulus, its echo is the
    # comparators' first ARRIVAL (a change after `guard` samples of quiet), the answer's echo the second,
    # and the difference is the turnaround from RX ANT to TX ANT plus the cable.
    #   * the synchronous reply (RP_*): rx_engine's decision, two clocks from the sampler's word to the pins;
    #   * the fast path (FP_*, the PYNQ-Z2): the comparators' pins through LUTs to the ladder pins, no clock;
    #   * the ring: the fast path with a permutation of the states, so the loop cycles one turnaround a hop.

    REARM = {None: 0, "tx": 1 << 2, "rx": 1 << 5}

    def reply_config(self, reply_map, width=40, once=True, rearm="tx", enable=True):
        """the synchronous reply: on RX's valid decision of message k the ladders take TX_POINTS[reply_map[k]]
        for `width` clocks, over whatever tx_engine sends.  reply_map: a list (k -> its reply) or a dict.
        once: disarm after a reply; rearm 'tx' on each of this board's TX events (the stimulus), 'rx' when
        RX re-arms (the link quiet at its idle: any stimulus, TRIG IN's or another board's), None by
        reply_arm() only.  So each stimulus is answered once and the answer's own echo is not (single-board
        loopback); once=False answers every decision (a prover facing another board)."""
        m = reply_map if isinstance(reply_map, dict) else dict(enumerate(reply_map))
        w = 0
        for k, r in m.items():
            w |= (int(r) & 7) << (4 * int(k))
        self.wr("RP_MAP", w)
        self.wr("RP_CTRL", int(enable) | int(once) << 1 | self.REARM[rearm] | (max(1, int(width)) & 0xFFFF) << 16)
        self.wait_s(40 * self.t_clk)                  # the composed table: one entry a clock

    def reply_off(self):
        self.wr("RP_CTRL", 0)

    def reply_arm(self, on=True):
        v = self.rd("RP_CTRL") & 0xFFFF0027
        self.wr("RP_CTRL", v | (0x8 if on else 0x10))

    def reply_stat(self):
        c, v = self.rd("RP_CTRL"), self.rd("RP_STAT")
        return {"enabled": c & 1, "once": c >> 1 & 1, "rearm_on_tx": c >> 2 & 1, "rearm_on_rx": c >> 5 & 1,
                "armed": c >> 8 & 1, "width": c >> 16, "last_msg": v & 7, "last_reply": v >> 4 & 7, "replies": v >> 8}

    def fast_config(self, entries, mode="oneshot", clocks=1, arm_on="tx"):
        """the fast path's table: entries {comparator vector: ladder point code} (every other vector lets
        the pins' register through); mode 'oneshot' (disarmed `clocks` after the first change it causes)
        or 'ring' (armed `clocks`); arm_on 'tx' arms it on each of this board's TX events, 'rx' when RX
        re-arms (the link quiet at its idle), None by fast_arm() only."""
        if not self.fast_path:
            raise RuntimeError("this build has no fast path (BUILD[12])")
        use, words = 0, [0, 0, 0, 0]
        for v, pt in entries.items():
            if pt is None:
                continue
            use |= 1 << v
            words[v >> 3] |= (pt & 0xF) << (4 * (v & 7))
        self.wr("FP_CTRL", 2)                          # disarmed while the table changes
        for k in range(4):
            self.wr("FP_MAP%d" % k, words[k])
        self.wr("FP_USE", use)
        self.wr("FP_TIME", max(1, int(clocks)))
        self._fp_mode = {"oneshot": 0, "ring": 1}[mode] << 2 | {None: 0, "tx": 1 << 3, "rx": 1 << 4}[arm_on]
        self.wr("FP_CTRL", self._fp_mode)
        # the tables shift into their LUTs for 32 clocks after the last write (an arming meanwhile waits)
        self.wait_s(40 * self.t_clk)
        self._wait("FP_CTRL", 1 << 5)

    def fast_arm(self):
        self.wr("FP_CTRL", getattr(self, "_fp_mode", 0) | 1)

    def fast_off(self):
        if self.fast_path:
            self.wr("FP_CTRL", 2)
            self.wr("FP_USE", 0)
            self._fp_mode = 0

    def fast_state(self):
        v = self.rd("FP_CTRL")
        return {"armed": v & 1, "drove": v >> 1 & 1, "ring": v >> 2 & 1, "arm_on_tx": v >> 3 & 1, "arm_on_rx": v >> 4 & 1,
                "loading": v >> 5 & 1, "built": v >> 8 & 1, "clocks": self.rd("FP_TIME")}

    @staticmethod
    def vector_owners(s, first_edge=True):
        """comparator vector -> the message it shows: the settled table's, else (first_edge) the message
        its masked changes from the idle belong to alone (Scheme.lut's two rules on the raw vector)"""
        s = SCHEMES[s] if isinstance(s, str) else s
        settled, fe = s.lut(False), s.lut(True)
        iv = s.idle_vector()
        own = {}
        for v in range(32):
            if settled[v] & 8:
                own[v] = settled[v] & 7
            elif first_edge:
                f = (v ^ iv) & s.mask
                if f and fe[f] & 8:
                    own[v] = fe[f] & 7
        return own

    @classmethod
    def fast_reply_entries(cls, s, reply_map, first_edge=True):
        """the fast path's table for a reply: every vector that shows message k drives reply_map[k]'s point"""
        s = SCHEMES[s] if isinstance(s, str) else s
        m = reply_map if isinstance(reply_map, dict) else dict(enumerate(reply_map))
        return {v: point_code(*s.msgs[m[k]]) for v, k in cls.vector_owners(s, first_edge).items() if k in m}

    @classmethod
    def ring_entries(cls, s, order=None, start="idle"):
        """the ring's table: a vector that shows message a drives the next one's point; a vector on the way
        from a to the next (each comparator at a's value or the next's) that nothing else owns keeps
        driving the next; the idle drives the first (start='idle') or lets the pins' register through
        (start='stimulus': a TX event starts it).  order: the cycle (default 0, 2, 1, 3 for four messages:
        B1's and B2's axis points in turn, so a hop moves both arms and their windows overlap)."""
        s = SCHEMES[s] if isinstance(s, str) else s
        if order is None:
            order = [0, 2, 1, 3] if s.n == 4 else list(range(s.n))
        nxt = {order[i]: order[(i + 1) % len(order)] for i in range(len(order))}
        own = cls.vector_owners(s, first_edge=True)
        iv = s.idle_vector()
        ent = {v: point_code(*s.msgs[nxt[k]]) for v, k in own.items() if k in nxt}
        sets = s.settled_sets()
        cand = {}
        for a in order:
            b = nxt[a]
            for va in sets[a]:
                for vb in sets[b]:
                    d = va ^ vb
                    sub = d
                    while True:                     # every subset of the comparators that differ
                        v = va ^ sub
                        if v not in own and v != iv:
                            cand.setdefault(v, set()).add(b)
                        if sub == 0:
                            break
                        sub = (sub - 1) & d
        for v, bs in cand.items():
            if len(bs) == 1:
                ent[v] = point_code(*s.msgs[bs.pop()])
        if start == "idle":
            ent[iv] = point_code(*s.msgs[order[0]])
        return ent

    def turnaround_config(self, mask=0x1F, guard=8, window=50, ring=False, enable=True, clear=True):
        """the counter: arrivals on the comparators in `mask` (a change after `guard` samples of quiet);
        after each of this board's TX events the first arrival -> the second within `window` clocks
        (0: no limit); ring: count arrivals only while the fast path is armed"""
        self.wr("RT_CFG", int(enable) | int(clear) << 1 | int(ring) << 2 | (mask & 0x1F) << 8 | (guard & 0xFF) << 16
                | (window & 0xFF) << 24)

    def turnaround_stats(self):
        """the counter's statistics: samples and ns"""
        ts = self.t_sample * 1e9
        n, last = self.rd("RT_N"), self.rd("RT_LAST")
        st = {"n": n, "miss": self.rd("RT_MISS"), "min": self.rd("RT_MIN") & 0xFFFF, "max": self.rd("RT_MAX") & 0xFFFF,
              "sum": self.rd("RT_SUM"), "last": last & 0xFFFF, "last_ref_to_arrival": last >> 16,
              "arrivals": self.rd("RT_MARKS"), "span": self.rd("RT_SPAN"), "sample_ns": ts}
        st["mean"] = st["sum"] / n if n else None
        for k in ("min", "max", "mean", "last", "last_ref_to_arrival"):
            st[k + "_ns"] = st[k] * ts if n else None
        return st

    def _turnaround_setup(self, scheme, path, reply_map, first_edge, delay, width, reply_width, fp_clocks,
                          stimulus="tx"):
        s = self.scheme(scheme, first_edge=first_edge, delay=delay)
        if stimulus == "trig_in":                     # RX's reference, and so the counter's: TRIG_IN's rise
            self._rx_ctrl |= 1 << 3
            self.wr("RX_CTRL", self._rx_ctrl)
        if reply_map is None:
            reply_map = [(k + 1) % s.n for k in range(s.n)]   # every answer differs from its stimulus
        self.tx_stop()
        rearm = "tx" if stimulus == "tx" else "rx"
        if path == "sync":
            self.fast_off()
            self.reply_config(reply_map, width=reply_width, once=True, rearm=rearm)
        elif path == "fast":
            self.reply_off()
            self.fast_config(self.fast_reply_entries(s, reply_map, first_edge), mode="oneshot", clocks=fp_clocks,
                             arm_on=rearm)
            if stimulus != "tx":
                self.fast_arm()
        else:
            raise ValueError("path: 'sync' or 'fast'")
        return s, reply_map

    def loopback_turnaround(self, scheme="B1", path="sync", reply_map=None, count=1000, period=1000, width=20,
                            first_edge=True, delay=None, reply_width=40, fp_clocks=1, guard=8, window=50, mask=0x1F,
                            stimulus="tx", seconds=1.0):
        """single-board loopback (TX ANT to RX ANT through a cable and an attenuator): `count` stimuli,
        each answered once by the synchronous reply (path='sync') or the fast path ('fast'), and the
        turnaround counter's statistics, from the stimulus's echo to the answer's: the board's turnaround
        from RX ANT to TX ANT, plus the cable.  The stimulus is held `width` clocks (the answer takes the
        pins over before it ends), the answer `reply_width` (sync) or until `fp_clocks` after its first
        change (fast).  stimulus 'tx': this board's TX events, on the clock's grid, so the synchronous
        reply's wait for the ISERDESE2's word is one fixed phase (one value of its 10 ns spread);
        'trig_in': a free-running generator on TRIG IN (it sums into the Q ladder on the board) makes the
        stimuli at every phase for `seconds`, RX's reference TRIG_IN, the paths re-armed when RX re-arms.
        Returns the counter's statistics in samples and ns, RX's and the reply's."""
        self._turnaround_setup(scheme, path, reply_map, first_edge, delay, width, reply_width, fp_clocks, stimulus)
        self.turnaround_config(mask=mask, guard=guard, window=window)
        self.rx_clear()
        if stimulus == "tx":
            self.events(period=period, width=width, count=count)
            self.tx_go()
            self.wait_s((period * count + 200) * self.t_clk)
        else:
            self.wait_s(seconds)
        st = self.turnaround_stats()
        st["path"] = path
        st["rx"] = self.rx_stats()
        st["reply"] = self.reply_stat() if path == "sync" else self.fast_state()
        if path == "sync":
            self.reply_off()
        else:
            self.fast_off()
        if stimulus != "tx":
            self._rx_ctrl &= ~(1 << 3)
            self.wr("RX_CTRL", self._rx_ctrl)
        return st

    def turnaround_from_capture(self, cap, guard=8, mask=0x1F):
        """the same turnaround from a capture (software, sample by sample): after the trigger (the
        stimulus's TX event) the comparators' first arrival t1 and second t3; with the ladder pins read
        back (BUILD[13]), also when the pads changed: the stimulus t0p and the answer t2, so t2 - t1 is the
        FPGA's pin to pin (both pads sampled by ISERDESE2s alike) and t3 - t2 the RF loop's."""
        ts = cap["sample_ns"]
        t0 = cap["trigger_sample"]
        vec = [sum(cap[name][i] << b for b, name in enumerate(CMP_NAMES)) & mask for i in range(len(cap["CMP_I"]))]
        arr, last = [], None
        for i in range(t0 + 1, len(vec)):
            if vec[i] != vec[i - 1]:
                if last is None or i - last >= guard:
                    arr.append(i)
                last = i
        out = {"arrivals": [a - t0 for a in arr], "sample_ns": ts}
        if len(arr) >= 2:
            out.update(t1=arr[0] - t0, t3=arr[1] - t0, turnaround=arr[1] - arr[0],
                       turnaround_ns=(arr[1] - arr[0]) * ts, ref_to_arrival_ns=(arr[0] - t0) * ts)
        if "TX_PINS" in cap and len(arr) >= 1:
            pins = cap["TX_PINS"]
            lag = cap.get("tx_pins_lag", 0)
            ch = [i - lag for i in range(t0 + 1, len(pins)) if pins[i] != pins[i - 1]]
            stim = [c for c in ch if c < arr[0]]
            ans = [c for c in ch if c >= arr[0]]
            if stim:
                out["t0p"] = stim[-1] - t0
                out["loop_ns"] = (arr[0] - stim[-1]) * ts
            if ans:
                out["t2"] = ans[0] - t0
                out["fpga_ns"] = (ans[0] - arr[0]) * ts
                if len(arr) >= 2:
                    out["loop2_ns"] = (arr[1] - ans[0]) * ts
        return out

    def turnaround_capture(self, scheme="B1", path="sync", reply_map=None, first_edge=True, delay=None, width=20,
                           reply_width=40, fp_clocks=1, post=256, guard=8, mask=0x1F):
        """one stimulus, captured: the comparators and (PYNQ-Z2) the ladder pads, sample by sample, and
        turnaround_from_capture's times; the capture itself under 'capture'"""
        self._turnaround_setup(scheme, path, reply_map, first_edge, delay, width, reply_width, fp_clocks)
        self.events(period=1000, width=width, count=1)
        cap = self.capture("tx_event", post=post, start=self.tx_go)
        out = self.turnaround_from_capture(cap, guard=guard, mask=mask)
        out["capture"] = cap
        if path == "sync":
            self.reply_off()
        else:
            self.fast_off()
        return out

    def ring_run(self, scheme="B1", order=None, clocks=2000, start="idle", guard=8, mask=0x1F):
        """the ring (PYNQ-Z2): the fast path armed `clocks` with a permutation of the scheme's states (no fixed
        point), so in single-board loopback the state cycles through the loop; the counter's arrivals while
        armed give the hops, and the span over hops - 1 is one turnaround, RX ANT to TX ANT plus the cable"""
        s = SCHEMES[scheme] if isinstance(scheme, str) else scheme
        self.tx_stop()
        self.reply_off()
        self.tx_points(s.tx_idle(), [point_code(i, q) for i, q in s.msgs])   # the idle the ring starts from
        self.fast_config(self.ring_entries(s, order, start), mode="ring", clocks=clocks, arm_on=None)
        self.turnaround_config(mask=mask, guard=guard, window=0, ring=True)
        self.wait_s(20 * self.t_clk)
        if start == "idle":
            self.fast_arm()
        else:
            self.tx_msg((order or ([0, 2, 1, 3] if s.n == 4 else [0]))[0])
            self.events(period=clocks + 100, width=clocks + 50, count=1, source="fixed")
            self.fast_arm()
            self.tx_go()
        self.wait_s((clocks + 50) * self.t_clk)
        st = self.turnaround_stats()
        hops = st["arrivals"]
        st["hops"] = hops
        st["turnaround"] = st["span"] / (hops - 1) if hops > 1 else None
        st["turnaround_ns"] = st["turnaround"] * st["sample_ns"] if hops > 1 else None
        st["fast"] = self.fast_state()
        self.fast_off()
        self.wr("RT_CFG", 0)
        return st

    # -----------------------------------------------------------------------------------------------------
    # experiments (BRINGUP.md)
    # -----------------------------------------------------------------------------------------------------
    def safe(self):
        """the power-up state: TX muted, loop held, receive, the engines stopped"""
        self.tx_stop()
        self.seq_stop()
        self.reply_off()
        self.fast_off()
        self.tx_mode("txsym")
        self.ctrl(tx_dis=1, loop_hold=1, tr_a=1, txq1_hiz=0)

    def bringup_stage1(self, eeprom=False, window_v=V_MID + 0.1):
        """stage 1.5: the I2C scan, the DACs at DAC_DEFAULT_V (also their EEPROM if asked: the ladders' references
        at VR_I_V / VR_Q_V, everything else mid-scale), the four window thresholds above the idle (the AD5696R
        starts at 1.25 V, under the arms' 1.65 V, which holds its comparators high: BRINGUP stage 1.5), the ADC's
        four channels and the detectors' (V5_MON, TEMP)"""
        found = self.i2c_scan()
        want = [AD5696R, ADS1115, ADS1115_DET, DAC1, DAC2]
        out = {"found": ["0x%02X" % a for a in found], "missing": ["0x%02X" % a for a in want if a not in found]}
        for d in (DAC1, DAC2):
            if d not in found:
                continue
            if eeprom:
                self.dac_eeprom(d)
            names = DAC1_CH if d == DAC1 else DAC2_CH
            self.dac(d, **dict(zip(names, DAC_DEFAULT_V[d])))
        out["dac_v"] = self.dac_volts()
        if AD5696R in found:
            for w in AD5696R_CH:
                self.threshold(w, window_v)
            out["window_v"] = window_v
        if ADS1115 in found:
            out["adc"] = self.adc_all()
        if ADS1115_DET in found:
            out["detectors"] = self.detectors()
        return out

    def dac_volts(self):
        """the eight MCP4728 channels as this driver last wrote them (the shadows), in volts"""
        out = {}
        for d, names in ((DAC1, DAC1_CH), (DAC2, DAC2_CH)):
            for k, ch in names.items():
                out[k] = round(self._dac[d][ch] * MCP4728_VDD / 4096, 4)
        return out

    def snapshot(self):
        """everything the board can say about itself at once, for the bring-up log: the control and status
        registers, the comparators, the counters, the synthesizers as last tuned, the DSA, the DACs' shadows,
        the ADC's four channels and the detectors (each part that does not answer reads as its error)"""
        out = {"time": time.time(), "info": self.info(), "ctrl": self.rd("CTRL"), "status": self.status(),
               "cmp_state": self.cmp_state(), "counters": self.counters(), "free_cnt": self.rd("FREE_CNT"),
               "pll_mhz": {("tx", "rx")[k]: v[0] for k, v in self._pll.items()}, "lo_mon": dict(self._lo_mon),
               "dsa_db": self._dsa_db, "dac_v": self.dac_volts(), "i2c_lines": self.i2c_lines()}
        for name, fn in (("adc", self.adc_all), ("detectors", self.detectors)):
            try:
                out[name] = fn()
            except (IOError, TimeoutError) as e:
                out[name] = "error: %s" % e
        return out

    def threshold_scan(self, which, volts, seconds=0.1, mask_input=None):
        """stage 3.7: step one window threshold across the idle and count its comparator's edges (the gate):
        returns [(volts, rate_hz, duty)].  ln(rate) against the threshold is Rice's downward parabola."""
        name = mask_input or {"QP": "CMP_QP", "QN": "CMP_QN", "IP": "CMP_IP", "IN": "CMP_IN"}[which]
        out = []
        for v in volts:
            self.threshold(which, v)
            g = self.gate(seconds=seconds, inputs=(name,))
            out.append((v, g[name]["rate_hz"], g[name]["duty"]))
        return out

    @staticmethod
    def rice_fit(points):
        """fit ln(rate) = ln(nu0) - (v - v0)^2 / (2 sigma^2) to [(volts, rate), ...] (rates > 0): returns
        (v0, sigma, nu0).  v0 is the comparator's offset (with the idle's level), sigma its noise."""
        pts = [(v, math.log(r)) for v, r, *_ in points if r > 0]
        if len(pts) < 3:
            raise ValueError("need three thresholds with edges")
        # least squares for y = a + b v + c v^2
        n = len(pts)
        sx = [sum(v ** k for v, _ in pts) for k in range(5)]
        sy = [sum(y * v ** k for v, y in pts) for k in range(3)]
        m = [[sx[0], sx[1], sx[2]], [sx[1], sx[2], sx[3]], [sx[2], sx[3], sx[4]]]

        def det(a):
            return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                    + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
        d = det(m)
        coef = []
        for k in range(3):
            mk = [row[:] for row in m]
            for r in range(3):
                mk[r][k] = sy[r]
            coef.append(det(mk) / d)
        a, b, c = coef
        if c >= 0:
            raise ValueError("no downward parabola: the scan did not cross the noise")
        v0 = -b / (2 * c)
        sigma = math.sqrt(-1 / (2 * c))
        nu0 = math.exp(a - b * b / (4 * c))
        _ = n
        return v0, sigma, nu0

    def threshold_servo(self, which, rate_hz=1.0 / 60, start_v=None, side=+1, seconds=None, steps=40,
                        lsb_per_step=64):
        """PLAN.md section 18's false-event servo: move one window threshold until its comparator's edge
        rate (the link idle) is the target (one a minute by default).  side +1 walks away from the idle
        while the rate is too high.  Returns (volts, rate)."""
        code = int(round((start_v if start_v is not None else V_MID + 0.1) / AD5696R_VREF * 65536))
        name = {"QP": "CMP_QP", "QN": "CMP_QN", "IP": "CMP_IP", "IN": "CMP_IN"}[which]
        if seconds is None:
            seconds = max(0.1, min(60.0, 3.0 / rate_hz))
        step = lsb_per_step
        rate = None
        for _ in range(steps):
            self.threshold(which, code=code)
            rate = self.gate(seconds=seconds, inputs=(name,))[name]["rate_hz"]
            if rate > rate_hz * 1.5:
                code += side * step
            elif rate < rate_hz / 1.5:
                code -= side * max(1, step // 2)
                step = max(1, step // 2)
            else:
                break
        return code / 65536.0 * AD5696R_VREF, rate

    def null_slow_offsets(self, seconds=0.05, steps=12):
        """stage 3.2: with no carrier (TX_DIS high, the loop held), move I_OFF / Q_OFF until CMP_I_S and
        CMP_QP_S are high half the time (a bisection on the DAC 2 codes)"""
        res = {}
        for dac_ch, inp in (("I_OFF", "CMP_I_S"), ("Q_OFF", "CMP_QP_S")):
            lo, hi = 0, 4095
            for _ in range(steps):
                mid = (lo + hi) // 2
                self.dac(DAC2, **{"code_" + dac_ch: mid})
                duty = self.gate(seconds=seconds, inputs=(inp,))[inp]["duty"]
                # a higher offset code raises the arm: the comparator is high more often
                if duty > 0.5:
                    hi = mid
                else:
                    lo = mid
            res[dac_ch] = (lo + hi) // 2
        return res

    # ---- the interference detectors (Prompt 28): no lock needed, nothing borrowed from the link ----
    def det_adc(self, ch, sps=860):
        """the second ADS1115 (0x49), single shot, +-4.096 V: ch 'LOG_Q', 'PEAK_Q', 'V5_MON', 'TEMP' (or 0-3)
        -> volts.  sps 8-860: its conversion averages over 1/sps, so a slow rate is a long average"""
        c = DET_CH.get(ch, ch)
        dr = {8: 0, 16: 1, 32: 2, 64: 3, 128: 4, 250: 5, 475: 6, 860: 7}[sps]
        cfg = (1 << 15) | ((4 + c) << 12) | (1 << 9) | (1 << 8) | (dr << 5) | 0b11
        self.i2c(ADS1115_DET, bytes([0x01, cfg >> 8, cfg & 0xFF]))
        self.wait_s(1.0 / sps + 0.0005)
        r = self.i2c(ADS1115_DET, b"\x00", 2)
        raw = int.from_bytes(r, "big")
        if raw & 0x8000:
            raw -= 0x10000
        return raw * ADC_LSB_V

    def _arm_dbm(self, v_rms_diff, gain=1.0):
        """a Q arm's differential rms (volts, before `gain`) -> dBm at RX ANT: noise splits evenly between I and Q,
        and A_REG_V is the arm's peak for the demodulator at DEM_REG_DBM (as sigma_to_dbm())"""
        if v_rms_diff <= 0:
            return None
        p_dem = DEM_REG_DBM + 20 * math.log10(math.sqrt(2.0) * (v_rms_diff / gain) / A_REG_V)
        return p_dem - RX_GAIN_DB + self._dsa_db

    def detectors(self, sps=860, cal_db=0.0):
        """Read the four detector channels and say what they mean (PLAN.md section 19, Prompt 28):
          log_dbm   the link band's (+-94 MHz) power at RX ANT from LOG_Q, the ADC's average of the log: the
                    floor, which bursts barely move (+ LOG_NOISE_DB for noise, est)
          peak_dbm  the same scale from PEAK_Q, held for ~47 ms: the strongest burst lately (our own events
                    lift it too: read it in a pause)
          *_inr_db  each over the receiver's own noise in the link band (thermal_dbm("fast"))
          v5_rf     +5V_RF (the ADL53xx and gain blocks want 4.75-5.25 V)
          temp_c    the board, from the NTC
        cal_db adds to the two levels (calibrate once against a known carrier).  The slow band's power is
        survey()'s, from the slow window comparator's statistics."""
        v = {k: self.det_adc(k, sps) for k in DET_CH}
        out = dict(volts=v)
        for k, name in (("LOG_Q", "log"), ("PEAK_Q", "peak")):
            dbv_in = v[k] / AD8310_SLOPE_V_DB + AD8310_INTERCEPT_DBV
            v_arm = 10 ** ((dbv_in + LOG_TAP_DB) / 20.0)
            d = self._arm_dbm(v_arm)
            out[name + "_dbm"] = None if d is None else d + cal_db + (LOG_NOISE_DB if name == "log" else 0.0)
        out["v5_rf"] = v["V5_MON"] / V5_DIV
        for name, band in (("log", "fast"), ("peak", "fast")):
            x = out[name + "_dbm"]
            out[name + "_inr_db"] = None if x is None else x - self.thermal_dbm(band)
        vt = v["TEMP"]
        if 0.0 < vt < NTC_VDD:
            r = NTC_RTOP * vt / (NTC_VDD - vt)
            out["temp_c"] = 1.0 / (1.0 / 298.15 + math.log(r / NTC_R25) / NTC_B) - 273.15
        else:
            out["temp_c"] = None
        return out

    # ---- the interference survey (PLAN.md section 19, Prompt 26): no carrier, no lock ----
    def noise_scan(self, path="slow", volts=None, seconds=0.005):
        """With no carrier, step one window threshold and read its comparator's duty (the gate's high
        samples): [(volts, duty)].  'slow' steps V_T2 against CMP_QP_S: the slow arm, a ~10 MHz wide view
        of RF that its own noise limits.  'fast' steps V_TQP against CMP_QP: the fast arm, ~190 MHz wide,
        whose comparator's floor is near -81 dBm at RX ANT (sim/budget.py)."""
        if volts is None:
            volts = [V_MID + d for d in SURVEY_LADDER_V]
        name = "CMP_QP_S" if path == "slow" else "CMP_QP"
        out = []
        for v in volts:
            if path == "slow":
                self.dac(DAC2, V_T2=v)
            else:
                self.threshold("QP", v)
            out.append((v, self.gate(seconds=seconds, inputs=(name,))[name]["duty"]))
        return out

    @staticmethod
    def probit_fit(points, lo=0.1, hi=0.9):
        """fit duty = Q((v - v0) / sigma), Gaussian noise past a threshold, to [(volts, duty)], using the
        duties between lo and hi (the central +-1.3 sigma, where bursts of a few per cent of the time
        barely move it): returns (v0, sigma).  A burst-free band is a line in (v, probit); WiFi's bursts
        lift the duty far past the line (survey()'s 'tail')"""
        nd = statistics.NormalDist()
        pts = [(v, nd.inv_cdf(1.0 - d)) for v, d in points if lo < d < hi]
        if len(pts) < 2 or len(set(round(z, 9) for _, z in pts)) < 2:
            raise ValueError("fewer than two thresholds inside the noise")
        n = len(pts)
        mz = sum(z for _, z in pts) / n
        mv = sum(v for v, _ in pts) / n
        szz = sum((z - mz) ** 2 for _, z in pts)
        szv = sum((z - mz) * (v - mv) for v, z in pts)
        sigma = szv / szz
        if sigma <= 0:
            raise ValueError("the duty does not fall with the threshold")
        return mv - sigma * mz, sigma

    def sigma_to_dbm(self, sigma_leg, path="slow"):
        """the noise and interference at RX ANT, dBm in the path's noise bandwidth, behind a comparator
        leg's sigma (volts): the leg is V_MID + x / 2 of the differential arm (as threshold_at()), power
        splits evenly between I and Q, the slow arm has G_SLOW more gain, and the DSA's setting is added
        back.  The gains are the budget's: calibrate once against a known carrier (survey's cal_db)."""
        g = G_SLOW if path == "slow" else 1.0
        sigma_diff = 2.0 * sigma_leg / g                       # at the fast arm, differential
        p_dem = DEM_REG_DBM + 20 * math.log10(math.sqrt(2.0) * sigma_diff / A_REG_V)
        return p_dem - RX_GAIN_DB + self._dsa_db

    @staticmethod
    def thermal_dbm(path="slow"):
        """the receiver's own noise at RX ANT in the path's noise bandwidth"""
        return -174.0 + 10 * math.log10(SURVEY_ENBW_HZ[path]) + NF_CHAIN_DB

    def survey(self, f_mhz, path="slow", seconds=0.005, f_pfd=5.0, settle_s=0.005, cal_db=0.0, restore_mhz=None):
        """The interference at each LO frequency, with no carrier and no lock (Jason, Prompt 26).  Ask the far
        transmitter to stop first (over Ethernet): this end's TX is disabled and the loop held (the VCXO at
        VC_OFF) during the scan, and both are restored after, with V_T2 and, given restore_mhz, the RX
        synthesizer.  Each frequency: retune the RX synthesizer (5 MHz steps by default), scan the window
        threshold, fit the leg's Gaussian.  One dict a frequency:
          sigma   volts at the comparator's leg (None when the scan did not resolve the noise)
          v0      the leg's centre (V_MID plus the offsets)
          dbm     at RX ANT in the path's noise bandwidth (7.5 MHz slow, 119 MHz fast), + cal_db
          inr_db  over the receiver's own noise in that bandwidth: what the CFAR window pays for
          tail    the duty at the first threshold past 4 sigma: ~3e-5 for noise alone; with bursts, their
                  share of the time times the chance a burst is out there, so a lower bound on the airtime
                  (bursts cost lost rounds, not ns: PLAN.md section 19)
        A strong band clips the arm: raise the DSA (dsa()) and survey again; dbm adds it back."""
        ctrl0 = self.rd("CTRL")
        vt2 = self._dac[DAC2][DAC2_CH["V_T2"]]
        self.ctrl(tx_dis=1, loop_hold=1)
        out = []
        try:
            for f in f_mhz:
                self.pll_tune(1, f, f_pfd=f_pfd, cp=15 if f_pfd < 25.0 else None)
                self.wait_s(settle_s)
                locked = bool(self.status()["mux_rx"])                 # the RX synthesizer's MUX: lock detect
                pts = self.noise_scan(path, seconds=seconds)
                row = dict(f_mhz=f, locked=locked, sigma=None, v0=None, dbm=None, inr_db=None, tail=None, points=pts)
                try:
                    v0, sigma = self.probit_fit(pts)
                except ValueError:
                    out.append(row)
                    continue
                dbm = self.sigma_to_dbm(sigma, path) + cal_db
                past = [d for v, d in pts if v > v0 + 4.0 * sigma]
                row.update(sigma=sigma, v0=v0, dbm=dbm, inr_db=dbm - self.thermal_dbm(path), tail=past[0] if past else None)
                out.append(row)
        finally:
            self.ctrl(tx_dis=ctrl0 >> self.CTRL_BITS["tx_dis"] & 1, loop_hold=ctrl0 >> self.CTRL_BITS["loop_hold"] & 1)
            self.dac(DAC2, code_V_T2=vt2)
            if restore_mhz is not None:
                self.pll_tune(1, restore_mhz)
        return out

    def loopback_latency(self, scheme="A1", period=2000, count=1000, first_edge=False, **kw):
        """stage 3.4-3.5: events through the loop, every reference this board's TX event; the latency
        statistics (samples) and the confusion matrix"""
        self.scheme(scheme, first_edge=first_edge, **kw)
        self.hist_config("ref_to_decision", 0)
        self.events(period=period, count=count)
        self.rx_clear()
        self.tx_go()
        self.wait_s((period * count + 200) * self.t_clk)
        st = self.rx_stats()
        st["confusion"] = self.confusion()
        return st

    def ber_run(self, seconds=1.0, poly=15, period=1, phase=None, n=2, invert=False):
        """stage 4.3: PRBS symbols (BPSK: N = 2; message 0 is the bit 0) every `period` clocks and the
        self-synchronising check on CMP_I; returns the bit count and the error rate.  `invert` when the
        message-0 point reads CMP_I high (the plan's BPSK: message 0 at +I)."""
        self.tx_timing(period=period)
        self.tx_prbs(poly)
        self.tx_mode("prbs", n=n)
        self.tx_go()
        self.wait_s(64 * period * self.t_clk)
        self.ber_config(poly, phase, invert=invert, enable=True)
        self.wait_s(seconds)
        self.ber_config(poly, phase, invert=invert, enable=False)
        r = self.ber()
        self.tx_stop()
        return r

    def hold_test(self, hold_ms=(1, 10, 100), settle_ms=50):
        """stage 3.8: the sequencer holds the loop (LOOP_HOLD high) for each time, the receiver otherwise
        locked; capture the comparators around the release (the capture's context has LOOP_HOLD)"""
        out = []
        for ms in hold_ms:
            clocks = int(ms * 1e-3 / self.t_clk)
            settle = int(settle_ms * 1e-3 / self.t_clk)
            self.seq_program([(settle, {"loop_hold": 0, "tx_dis": 0, "tr_a": 1}),
                              (clocks, {"loop_hold": 1, "tx_dis": 0, "tr_a": 1}),
                              (settle, {"loop_hold": 0, "tx_dis": 0, "tr_a": 1})])
            self.seq_run()
            self.wait_s((2 * settle + clocks) * self.t_clk + 0.01)
            out.append((ms, self.adc_all()))
        return out

    def time_division(self, rx_clocks, tx_clocks, guard_clocks=3, loop=True):
        """stage 4.4: receive (TR_A high, the loop closed), then hold the loop and transmit (TR_A low,
        LOOP_HOLD high, TX_DIS low, the TX gate open), with the switch's 30 ns as guards"""
        self.seq_program([
            (rx_clocks, {"tr_a": 1, "loop_hold": 0, "tx_dis": 1, "tx_gate": 0}),
            (guard_clocks, {"tr_a": 1, "loop_hold": 1, "tx_dis": 1, "tx_gate": 0}),
            (guard_clocks, {"tr_a": 0, "loop_hold": 1, "tx_dis": 1, "tx_gate": 0}),
            (tx_clocks, {"tr_a": 0, "loop_hold": 1, "tx_dis": 0, "tx_gate": 1}),
            (guard_clocks, {"tr_a": 0, "loop_hold": 1, "tx_dis": 1, "tx_gate": 0}),
            (guard_clocks, {"tr_a": 1, "loop_hold": 1, "tx_dis": 1, "tx_gate": 0}),
        ], loop=loop)
        self.seq_run()


def to_ns(samples, cl):
    return samples * cl.t_sample * 1e9
