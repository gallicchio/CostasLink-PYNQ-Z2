"""test_sim.py: the driver against the RTL (Response 15).

    cd gateware && python3 -m unittest driver.test_sim -v      (or: make sim-driver)

TestSchemes needs nothing: the receiver's tables the driver computes for the plan's corners against the
constants tb_engines.v proves on the RTL.  TestOnRtl runs costaslink.py's operations through sim_pipe.py's
PipeBus against tb_pipe.v (the core, SER = 8 as on the PYNQ-Z2, and the loopback model: the pins come
back on the fast comparators 13 samples later, on the slow ones 40), the way BRINGUP.md's stages use them.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from costaslink import (CostasLink, SCHEMES, point_code, CMP_I, CMP_QP, CMP_QN, CMP_IP, CMP_IN)  # noqa: E402
from sim_pipe import PipeBus                                                              # noqa: E402

LAT, LAT_SLOW = 13, 40


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


class TestOnRtl(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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
        self.assertEqual(i["capture"], {"ser": 8, "width": 64, "depth": 1024})

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
