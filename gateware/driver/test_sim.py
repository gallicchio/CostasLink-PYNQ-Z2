"""test_sim.py: the driver against the RTL (Response 15).

    cd gateware && python3 -m unittest driver.test_sim -v      (or: make sim-driver)

TestSchemes needs nothing: the receiver's tables the driver computes for the plan's corners against the
constants tb_engines.v proves on the RTL.  TestOnRtl runs costaslink.py's operations through sim_pipe.py's
PipeBus against tb_pipe.v (the core, SER = 8 as on the PYNQ-Z2, and the loopback model: the pins come
back on the fast comparators 13 samples later, on the slow ones 40), the way BRINGUP.md's stages use them;
the core is the PYNQ-Z2's otherwise too (the early reply lane, the fast path, the ladder pins read back),
so the turnaround measurements run here exactly, with the model's 13 samples of loop and no delay of the
fast path's own (Prompt 36).
"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from costaslink import (CostasLink, SCHEMES, point_code, CMP_I, CMP_QP, CMP_QN, CMP_IP, CMP_IN)  # noqa: E402
from sim_pipe import PipeBus                                                              # noqa: E402

LAT, LAT_SLOW = 13, 40
SER = 8
# the synchronous reply's samples after the comparators' change in this model: the lane takes the word the
# change is in a clock early, the point is on the pins at the next edge (tb_engines.v's RP_LAT)
RP_LAT = (LAT // SER + 1) * SER - LAT


class TestSchemes(unittest.TestCase):
    def test_a3_matches_tb_engines(self):
        s = SCHEMES["A3"]
        self.assertEqual(s.idle_vector(), 0b01001)                     # tb_engines.v V_IDLE: CMP_I and CMP_IP
        lut = s.lut()
        for v, k in ((0b01011, 0), (0b01101, 1), (0b10010, 2), (0b10100, 3)):     # V0 ... V3
            self.assertEqual(lut[v], 0x8 | k)
        self.assertEqual(lut[0b01001], 0)                              # the idle decides nothing
        self.assertEqual(s.slow_exp(), 0xCADB)                         # {1100, 1010, 1101, 1011}
        self.assertEqual(s.tx_points(), 0x0C3F)                        # P3 P2 P1 P0 = 0000 1100 0011 1111
        self.assertEqual(s.tx_idle(), 0b0111)
        self.assertEqual(s.mask, 1 << CMP_QP | 1 << CMP_QN)

    def test_first_edge_one_comparator_each(self):
        # B1 and B2: each message moves its own window comparator, so the first-fired set alone decides
        for name, order in (("B1", (CMP_IP, CMP_IN, CMP_QP, CMP_QN)), ("B2", (CMP_IP, CMP_IN, CMP_QP, CMP_QN))):
            lut = SCHEMES[name].lut(first_edge=True)
            for k, c in enumerate(order):
                self.assertEqual(lut[1 << c], 0x8 | k, name)
            self.assertEqual(lut[1 << CMP_IP | 1 << CMP_QP], 0, name)  # two messages' comparators: invalid

    def test_a3_first_edge_cannot_tell_i(self):
        # A3's events are QP / QN: the first edge carries the Q bit only, so every first-fired set is shared
        self.assertTrue(all(e == 0 for e in SCHEMES["A3"].lut(first_edge=True)))

    def test_twin(self):
        # the Costas loop's other lock point turns every message by 180 degrees: A1's flip becomes the idle side
        t = SCHEMES["A3"].twin()
        self.assertEqual(t.idle_vector(), 0b10000)                     # I negative: CMP_IN only

    def test_point_codes(self):
        self.assertEqual(point_code(1, 0), 0b0111)
        self.assertEqual(point_code(-1, -1), 0b0000)
        self.assertEqual(point_code(1, 1), 0b1111)


class TestReceivedLevel(unittest.TestCase):
    """received_dBm() and agc() against a model of the arm: a carrier at RX ANT, the DSA, the ADC's I_P"""

    def make(self, p_ant):
        import costaslink as CLM

        class Bus:
            def read(self, reg):
                return 0
            def write(self, reg, value):
                pass
        cl = CostasLink(Bus(), check=False)
        cl.spi = lambda which, word: None
        cl.wait_s = lambda s_: None

        def adc(ch, settle=0.0):
            dem = p_ant + CLM.RX_GAIN_DB - cl._dsa_db            # dBm at the demodulator
            a = CLM.A_REG_V * 10 ** ((dem - CLM.DEM_REG_DBM) / 20.0)
            return CLM.V_MID + min(a, 2.9) / 2.0                 # the locked arm, its legs clip at the rails
        cl.adc = adc
        return cl

    def test_reading(self):
        for p_ant in (-75.0, -59.2, -40.0):
            cl = self.make(p_ant)
            cl.dsa(max(0.0, p_ant + 59.2))
            self.assertAlmostEqual(cl.received_dBm(), p_ant, places=1)

    def test_agc(self):
        for p_ant in (-70.0, -50.0, -35.0):
            cl = self.make(p_ant)                                # the DSA starts at its power-up 31.75 dB
            db, r = cl.agc()
            self.assertAlmostEqual(r, p_ant, delta=0.3)
            self.assertAlmostEqual(db, max(0.0, min(31.75, p_ant + 59.2)), delta=0.6)


class TestSurvey(unittest.TestCase):
    """the interference survey (Prompt 26) against a model of the slow window comparator: Gaussian noise
    of a known level at each frequency, and WiFi's bursts at one of them"""

    def test_survey_recovers_levels_and_bursts(self):
        import costaslink as CLM
        from statistics import NormalDist
        nd = NormalDist()
        p_ant = {5745: -95.0, 5775: -101.0, 5800: -101.0}        # dBm at RX ANT in the slow path's 7.5 MHz
        burst = {5800: 0.05}                                     # 5 % of the time, 20 dB above the rest

        class Bus:
            def read(self, reg):
                return 0
            def write(self, reg, value):
                pass
        cl = CostasLink(Bus(), check=False)
        cl.wait_s = lambda s_: None
        cl.dsa(0.0)
        state = {"f": None, "vt2": None}
        cl.pll_tune = lambda which, f, f_pfd=25.0, cp=None: state.update(f=f)

        def dac(which=CLM.DAC1, **ch):
            if "V_T2" in ch:
                state["vt2"] = ch["V_T2"]
            return []
        cl.dac = dac

        def leg_sigma(dbm):
            # sigma_to_dbm() inverted
            p_dem = dbm + CLM.RX_GAIN_DB - cl._dsa_db
            sigma_diff = CLM.A_REG_V * 10 ** ((p_dem - CLM.DEM_REG_DBM) / 20.0) / math.sqrt(2.0)
            return sigma_diff * CLM.G_SLOW / 2.0

        def gate(seconds=None, inputs=()):
            f, v = state["f"], state["vt2"]
            s0 = leg_sigma(p_ant[f])
            d = 1.0 - nd.cdf((v - CLM.V_MID - 0.002) / s0)      # a 2 mV offset on the leg
            if f in burst:
                d = (1 - burst[f]) * d + burst[f] * (1.0 - nd.cdf((v - CLM.V_MID - 0.002) / (10 * s0)))
            return {inputs[0]: {"duty": d}}
        cl.gate = gate
        res = {r["f_mhz"]: r for r in cl.survey([5745, 5775, 5800])}
        self.assertAlmostEqual(res[5745]["dbm"], -95.0, delta=0.3)
        self.assertAlmostEqual(res[5775]["dbm"], -101.0, delta=0.3)
        self.assertAlmostEqual(res[5775]["v0"], CLM.V_MID + 0.002, delta=0.0005)
        self.assertAlmostEqual(res[5775]["inr_db"], -101.0 - cl.thermal_dbm("slow"), delta=0.3)
        self.assertLess(res[5745]["tail"], 1e-3)                # Gaussian past 4 sigma
        self.assertGreater(res[5800]["tail"], 0.005)            # the bursts show: 0.05 x P(burst > 4 sigma) ~ 0.017
        self.assertAlmostEqual(res[5800]["dbm"], -101.0, delta=1.5)  # and barely moves the fit
        self.assertEqual(state["vt2"] is not None, True)


class TestDetectors(unittest.TestCase):
    """the detector channels (Prompt 28) against the circuit's arithmetic: a known level in, the same level out"""

    def test_levels_and_temperature(self):
        import costaslink as CLM

        class Bus:
            def read(self, reg):
                return 0
            def write(self, reg, value):
                pass
        cl = CostasLink(Bus(), check=False)
        cl.wait_s = lambda s_: None
        cl.dsa(0.0)
        p_fast, v5, temp = -70.0, 4.93, 40.0
        v_arm = lambda p, g=1.0: CLM.A_REG_V * 10 ** ((p + CLM.RX_GAIN_DB - CLM.DEM_REG_DBM) / 20.0) / math.sqrt(2.0) * g
        dbv = 20 * math.log10(v_arm(p_fast) / 3.0) - CLM.LOG_NOISE_DB     # a log amp under-reads noise
        r_ntc = CLM.NTC_R25 * math.exp(CLM.NTC_B * (1.0 / (temp + 273.15) - 1.0 / 298.15))
        volts = {0: (dbv - CLM.AD8310_INTERCEPT_DBV) * CLM.AD8310_SLOPE_V_DB,
                 1: (dbv + CLM.LOG_NOISE_DB + 20.0 - CLM.AD8310_INTERCEPT_DBV) * CLM.AD8310_SLOPE_V_DB,   # a burst 20 dB up
                 2: v5 / 2.0,
                 3: CLM.NTC_VDD * r_ntc / (CLM.NTC_RTOP + r_ntc)}
        state = {}

        def i2c(addr, wbytes=b"", nread=0, timeout=0.1):
            self.assertEqual(addr, CLM.ADS1115_DET)
            if len(wbytes) == 3:
                state["ch"] = ((int.from_bytes(wbytes[1:], "big") >> 12) & 0x7) - 4      # MUX 1xx: AINx against GND
                return b""
            raw = int(round(volts[state["ch"]] / CLM.ADC_LSB_V))
            return raw.to_bytes(2, "big")
        cl.i2c = i2c
        d = cl.detectors()
        self.assertAlmostEqual(d["log_dbm"], p_fast, delta=0.05)
        self.assertAlmostEqual(d["peak_dbm"], p_fast + 20.0, delta=0.05)
        self.assertAlmostEqual(d["v5_rf"], v5, delta=0.002)
        self.assertAlmostEqual(d["temp_c"], temp, delta=0.1)
        self.assertAlmostEqual(d["log_inr_db"], p_fast - cl.thermal_dbm("fast"), delta=0.05)


class TestBoardConstants(unittest.TestCase):
    """board_constants.py is generated from build/budget.json (gateware/gen_constants.py): a hand edit, or a
    budget changed and not rebuilt, shows here.  Skipped where build/ is absent (on the PYNQ)."""
    def test_matches_the_build(self):
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if not os.path.exists(os.path.join(root, "build", "budget.json")):
            self.skipTest("no build/budget.json")
        sys.path.insert(0, os.path.join(root, "gateware"))
        import gen_constants
        import board_constants
        want = {name: v[0] for name, v in gen_constants.C if v is not None}
        have = {name: getattr(board_constants, name) for name in want}
        self.assertEqual(have, want)


class TestOnRtl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import shutil
        if shutil.which("iverilog") is None:
            raise unittest.SkipTest("no Icarus Verilog")
        cls.bus = PipeBus(ser=8)
        cls.cl = CostasLink(cls.bus)

    @classmethod
    def tearDownClass(cls):
        cls.bus.close()

    def setUp(self):
        self.cl.tx_stop()
        self.bus.clocks(50)

    def test_info(self):
        i = self.cl.info()
        self.assertEqual((i["board"], i["samples_per_clock"], i["clock_MHz"]), ("simulation", 8, 100))
        self.assertEqual(i["capture"], {"ser": 8, "width": 96, "depth": 1024, "tx_readback": 1})
        self.assertEqual((i["fast_path"], i["tx_readback"], i["early_lane"], i["reply_reg"]), (1, 1, 1, 0))

    def test_i2c_nack(self):
        # the testbench loops the I2C pins back: nothing acknowledges, and the driver says so without hanging
        self.assertFalse(self.cl.i2c_probe(0x48))

    def run_events(self, scheme, count=40, period=100, first_edge=False):
        cl = self.cl
        cl.scheme(scheme, first_edge=first_edge, window=50)
        cl.hist_config("ref_to_decision", 0)
        cl.events(period=period, width=20, count=count)
        cl.rx_clear()
        cl.tx_go()
        cl.wait_s((count * period + 200) * cl.t_clk)
        return cl.rx_stats()

    def test_loopback_a3(self):
        st = self.run_events("A3")
        delay = 2 * self.cl.ser
        self.assertEqual((st["refs"], st["events"], st["decided"], st["false"], st["missed"]), (40, 40, 40, 0, 0))
        self.assertEqual(st["confirm"], 40)
        self.assertEqual((st["lat_min"], st["lat_max"]), (LAT + delay, LAT + delay))
        cm = self.cl.confusion()
        for r in range(4):
            self.assertEqual(cm[r][r], 10)
        self.assertEqual(sum(map(sum, cm)), 40)
        h = self.cl.histogram(64)
        self.assertEqual(h[LAT + delay], 40)
        self.assertEqual(sum(h), 40)

    def test_loopback_b1_first_edge(self):
        st = self.run_events("B1", first_edge=True)
        self.assertEqual((st["events"], st["decided"], st["false"], st["missed"]), (40, 40, 0, 0))
        cm = self.cl.confusion()
        self.assertEqual([cm[r][r] for r in range(4)], [10, 10, 10, 10])

    def test_false_events_from_noise(self):
        # the comparators flip at random with nothing sent: every event is false, the gate counts them
        cl, bus = self.cl, self.bus
        cl.scheme("A3", window=50)
        cl.rx_clear()
        bus.knob("noise_mask", 1 << CMP_QP)
        bus.knob("noise_ppm", 1000)
        g = cl.gate(clocks=10000, inputs=("CMP_QP",))
        bus.knob("noise_ppm", 0)
        n = g["CMP_QP"]["high"]                                         # 80000 samples x 1e-3: about 80
        self.assertTrue(40 < n < 140, n)
        self.assertTrue(n <= g["CMP_QP"]["edges"] <= 2 * n)
        st = cl.rx_stats()
        self.assertEqual(st["refs"], 0)
        self.assertGreater(st["false"], 10)
        self.assertEqual(st["false"], st["events"])

    def test_capture_tx_event(self):
        cl = self.cl
        cl.scheme("A3")
        cl.tx_msg(0)
        cl.events(period=1000, width=20, count=1, source="fixed")
        cap = cl.capture("tx_event", post=64, start=cl.tx_go)
        t = cap["trigger_word"]
        self.assertEqual(t, 1024 - 1 - 64)
        self.assertEqual(cap["TX_EVENT"][t], 1)
        self.assertEqual(cap["TX_EVENT"][t - 1], 0)
        first = next(i for i in range(t * 8, len(cap["CMP_QP"])) if cap["CMP_QP"][i])
        self.assertEqual(first - cap["trigger_sample"], LAT)          # message 0 is (+1, +1): QP rises

    def test_ber(self):
        cl, bus = self.cl, self.bus
        cl.tx_points(point_code(1, 0), [point_code(1, 0), point_code(-1, 0)])   # BPSK on I: message 0 at +I
        ser = cl.ser
        phase = (LAT + ser // 2) % ser                                  # mid-symbol after the loop's delay
        # message 0 (the bit 0) reads CMP_I high: the check inverts
        r = cl.ber_run(seconds=2000 * cl.t_clk, poly=15, period=1, phase=phase, invert=True)
        self.assertEqual(r["mismatches"], 0)
        self.assertGreater(r["bits"], 1900)
        r = cl.ber_run(seconds=500 * cl.t_clk, poly=15, period=1, phase=phase, invert=False)
        self.assertGreater(r["mismatches"], 400)                       # the wrong polarity: every bit
        self.assertLessEqual(r["mismatches"], r["bits"])
        # one symbol flipped: a self-synchronising check counts it three times
        cl.tx_go()
        bus.clocks(64)
        cl.ber_config(15, phase, invert=True)
        bus.clocks(200)
        bus.knob("flip", 1)
        bus.clocks(1)
        bus.knob("flip", 0)
        bus.clocks(200)
        cl.ber_config(15, phase, invert=True, enable=False)
        self.assertEqual(cl.ber()["mismatches"], 3)
        cl.tx_stop()

    def test_capture_on_sequencer_step(self):
        # BRINGUP 3.8: trigger on the step that releases the hold; LOOP_HOLD falls in the trigger word
        cl = self.cl
        cl.seq_program([(40, {"loop_hold": 1}), (60, {"loop_hold": 0})], loop=False)
        cl.wr("CAP_POST", 100)
        cl.wr("CAP_CTRL", cl.TRIGGERS["seq_step"] << 4 | 1)
        cl.seq_run()
        cap = cl.cap_read()
        t = cap["trigger_word"]
        # the first step's start triggers (LOOP_HOLD rises there from the CTRL default, which is high too)
        self.assertEqual(cap["LOOP_HOLD"][t], 1)
        self.assertEqual(sum(1 for b in cap["LOOP_HOLD"][t:t + 100] if b == 0), 60)
        cl.seq_stop()

    def test_sequencer_tr_a(self):
        cl = self.cl
        cl.seq_program([(50, {"tr_a": 0}), (30, {"tr_a": 1})], loop=False)
        cl.cap_arm("none", post=600)
        cl.seq_run()
        cl.cap_force()
        cap = cl.cap_read()
        self.assertFalse(cap["filled"])
        v = cap["valid_from"]
        self.assertTrue(400 < v < cap["trigger_word"], v)            # armed a few clocks before the force
        self.assertEqual(sum(1 for b in cap["TR_A"][v:] if b == 0), 50)
        cl.seq_stop()

    # ---- the receive-to-transmit paths (Prompt 36) ----
    def test_sync_reply_turnaround(self):
        # B1, first edge: each stimulus answered once, the counter from its echo to the answer's
        st = self.cl.loopback_turnaround("B1", path="sync", count=20, period=200)
        self.assertEqual((st["n"], st["miss"]), (20, 0))
        self.assertEqual((st["min"], st["max"]), (LAT + RP_LAT, LAT + RP_LAT))
        self.assertAlmostEqual(st["mean_ns"], (LAT + RP_LAT) * 1.25)
        self.assertEqual(st["last_ref_to_arrival"], LAT)
        self.assertEqual(st["reply"]["replies"], 20)
        self.assertEqual(st["reply"]["last_reply"], (st["reply"]["last_msg"] + 1) % 4)
        rx = st["rx"]
        self.assertEqual((rx["events"], rx["decided"], rx["false"], rx["missed"]), (20, 20, 0, 0))

    def test_sync_reply_settled_a3(self):
        # A3 needs the settled vector (its first edge cannot tell I): two samples after the event, the
        # same clock (in the event's word); two clocks of samples after it, a clock later for each word on
        st = self.cl.loopback_turnaround("A3", path="sync", count=8, period=200, first_edge=False, delay=2)
        self.assertEqual((st["n"], st["min"], st["max"]), (8, LAT + RP_LAT, LAT + RP_LAT))
        st = self.cl.loopback_turnaround("A3", path="sync", count=8, period=200, first_edge=False, delay=2 * SER)
        late = SER * ((LAT % SER + 2 * SER) // SER)                     # a clock for each word the sample is on
        self.assertEqual((st["n"], st["min"], st["max"]), (8, LAT + RP_LAT + late, LAT + RP_LAT + late))

    def test_fast_turnaround(self):
        # the fast path has no delay of its own in the model: the turnaround is the loop's
        st = self.cl.loopback_turnaround("B1", path="fast", count=20, period=200)
        self.assertEqual((st["n"], st["miss"], st["min"], st["max"]), (20, 0, LAT, LAT))
        self.assertEqual((st["reply"]["drove"], st["reply"]["armed"]), (1, 0))
        self.assertEqual(st["rx"]["decided"], 20)

    def test_turnaround_capture(self):
        cl = self.cl
        r = cl.turnaround_capture("B1", path="sync")
        self.assertEqual((r["t1"], r["turnaround"]), (LAT, LAT + RP_LAT))
        self.assertEqual(r["t0p"], 0)                                   # the stimulus on the pads with its TX event
        self.assertAlmostEqual(r["loop_ns"], LAT * 1.25)
        self.assertAlmostEqual(r["fpga_ns"], RP_LAT * 1.25)            # comparator sample -> ladder sample
        self.assertAlmostEqual(r["loop2_ns"], LAT * 1.25)
        cap = r["capture"]
        t = cap["trigger_word"]
        self.assertEqual(cap["TX_EVENT"][t], 1)
        self.assertEqual(sum(cap["REPLY"][t:t + 10]), 1)                # the reply's first clock
        r = cl.turnaround_capture("B1", path="fast")
        self.assertEqual((r["turnaround"], r["fpga_ns"]), (LAT, 0.0))
        self.assertEqual(r["capture"]["REPLY"][r["capture"]["trigger_word"] + 1], 1)   # armed by the TX event

    def test_ring(self):
        # A3's corners in a ring started from the idle: one turnaround a hop
        st = self.cl.ring_run("A3", clocks=300)
        self.assertEqual(st["hops"], (300 * SER - 1) // LAT)
        self.assertEqual(st["turnaround"], LAT)
        self.assertEqual(st["fast"]["armed"], 0)
        # B1 has no pilot in the model (the idle's CMP_I differs): a stimulus starts it instead
        st = self.cl.ring_run("B1", clocks=300, start="stimulus")
        self.assertGreater(st["hops"], 150)
        self.assertEqual(st["turnaround"], LAT)

    def test_ring_entries(self):
        # no fixed point, and the idle starts it
        s = SCHEMES["B2"]
        ent = CostasLink.ring_entries(s)
        own = CostasLink.vector_owners(s)
        pts = [point_code(*m) for m in s.msgs]
        for v, k in own.items():
            self.assertNotEqual(ent[v], pts[k])
        self.assertEqual(ent[s.idle_vector()], pts[0])

    def test_trig_in_reference(self):
        cl, bus = self.cl, self.bus
        cl.scheme("A3", window=50)
        cl.rx_config(SCHEMES["A3"].idle_vector(), SCHEMES["A3"].mask, SCHEMES["A3"].lut(),
                     SCHEMES["A3"].slow_exp(), delay=2 * cl.ser, window=50, ref="trig_in")
        cl.tx_msg(0)
        cl.events(period=30, width=20, count=0, source="fixed", mode="trig_in")
        cl.tx_go()
        cl.rx_clear()
        bus.trig(sample=2, clocks=2)
        bus.clocks(100)
        last = cl.rx_last()
        # TRIG_IN at sample 2; the event on the pins three clocks later (rx_engine's stage 1, tx_engine's
        # start, the pins' register); the comparators LAT samples after the pins
        self.assertEqual(last["ref_to_event"], 3 * cl.ser - 2 + LAT)
        self.assertEqual(last["had_ref"], 1)


if __name__ == "__main__":
    unittest.main()
