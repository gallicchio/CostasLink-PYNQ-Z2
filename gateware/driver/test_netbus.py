"""test_netbus.py: netbus.py's server and client end to end, the server's CostasLink on the RTL (tb_pipe.v through
PipeBus, as test_sim.py), the client over a real TCP socket on localhost.

    cd gateware/driver && python3 -m unittest test_netbus -v
"""
import os
import shutil
import sys
import threading
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from costaslink import CostasLink, DAC1, DAC_DEFAULT_V, VR_MAX_V, dac_code, ID_EXPECTED   # noqa: E402
from netbus import Server, RemoteCostasLink, RemoteError                                 # noqa: E402
from sim_pipe import PipeBus                                                             # noqa: E402


@unittest.skipUnless(shutil.which("iverilog"), "needs Icarus Verilog (the OSS CAD Suite) on PATH")
class TestNetbus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipe = PipeBus(ser=8)
        cls.local = CostasLink(cls.pipe)
        cls.tcp = Server(cls.local).tcp_server("127.0.0.1", 0, quiet=True)
        cls.thread = threading.Thread(target=cls.tcp.serve_forever, daemon=True)
        cls.thread.start()
        cls.cl = RemoteCostasLink("127.0.0.1", cls.tcp.server_address[1], timeout=60)

    @classmethod
    def tearDownClass(cls):
        cls.cl.close()
        cls.tcp.shutdown()
        cls.tcp.server_close()
        cls.pipe.close()

    def test_registers(self):
        self.assertEqual(self.cl.rd("ID"), ID_EXPECTED)
        self.assertEqual(self.cl.bus.read(0x00), ID_EXPECTED)
        self.cl.wr("TX_PERIOD", 1234)
        self.assertEqual(self.cl.rd("TX_PERIOD"), 1234)

    def test_values_and_methods(self):
        self.assertEqual(self.cl.ser, 8)
        info = self.cl.info()
        self.assertEqual(info["samples_per_clock"], 8)
        self.assertIn("depth", info["capture"])
        self.assertIn("uptime_s", self.cl.bus.ping())

    def test_method_as_argument(self):
        """a capture whose start is the board's own tx_one: the trigger word, the TX_EVENT context bit set"""
        self.cl.scheme("A1")
        self.cl.events(period=500, width=20, count=0)
        cap = self.cl.capture("tx_event", post=64, start=self.cl.tx_one)
        self.assertEqual(len(cap["words"]), self.cl.cap_info()["depth"])
        self.assertTrue(any(cap["TX_EVENT"][cap["trigger_word"]:]))

    def test_remote_errors(self):
        with self.assertRaises(RemoteError):
            self.cl.threshold("XX", 1.0)                   # no such window
        with self.assertRaises(AttributeError):
            self.cl._dac                                    # private names stay on the board
        with self.assertRaises(RemoteError):
            self.cl.bus.request({"op": "get", "name": "_dac"})

    def test_stage1_safe_dacs(self):
        """stage 1.5 on a bus with no I2C parts (the simulation's SDA is its own echo: every address NACKs):
        nothing found, nothing written, no exception; the shadows hold the ladders' references, not mid-scale"""
        r = self.cl.bringup_stage1()
        self.assertEqual(r["found"], [])
        self.assertEqual(len(r["missing"]), 5)
        self.assertAlmostEqual(r["dac_v"]["VR_I"], DAC_DEFAULT_V[DAC1][0], places=2)
        self.assertAlmostEqual(r["dac_v"]["VR_Q"], DAC_DEFAULT_V[DAC1][1], places=2)
        self.assertAlmostEqual(r["dac_v"]["VC_OFF"], 1.65, places=2)

    def test_vr_guard(self):
        """dac() refuses a ladder reference over VR_MAX_V before anything reaches the bus"""
        before = self.cl.dac_volts()
        with self.assertRaises(RemoteError):
            self.cl.dac(DAC1, VR_I=1.65)
        self.assertEqual(self.cl.dac_volts(), before)
        self.assertLess(dac_code(VR_MAX_V) * 3.3 / 4096, 0.61)

    def test_lo_mon_words(self):
        """lo_mon() resends the six words with RFB_EN set; pll_tune keeps it for later retunes"""
        import max2871_regs
        sent = []
        real_spi = self.local.spi
        self.local.spi = lambda slave, word: sent.append((slave, word))
        try:
            self.cl.lo_mon(1, True)
            self.cl.pll_tune(1, 5825.0)
        finally:
            self.local.spi = real_spi
        self.assertEqual(len(sent), 12)
        for slave, w in sent:
            self.assertEqual(slave, 1)
        r4_first, r4_second = sent[1][1], sent[7][1]          # register 4 is the second word of each set
        self.assertEqual(max2871_regs.decode([0, r4_first, 0, 0, 0, 0])["RFB_EN"], 1)
        self.assertEqual(max2871_regs.decode([0, r4_second, 0, 0, 0, 0])["RFB_EN"], 1)
        self.assertEqual(self.cl.snapshot()["pll_mhz"]["rx"], 5825.0)
        self.cl.lo_mon(1, False)


if __name__ == "__main__":
    unittest.main()
