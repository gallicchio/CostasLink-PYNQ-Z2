"""sim_pipe.py: PipeBus, the register bus of the simulated core (tb_pipe.v under Icarus), so the driver's
experiments run against the RTL with the loopback model (Response 15).

    from sim_pipe import PipeBus
    from costaslink import CostasLink
    with PipeBus() as bus:               # compiles tb_pipe.v (SER = 8) into a temporary directory and runs it
        cl = CostasLink(bus)
        cl.scheme("A3"); ...
        bus.knob("noise_ppm", 100)       # the model: false events

The bus speaks tb_pipe.v's line protocol through two named pipes; `clocks(n)` runs the simulation n
clocks (CostasLink.wait_s uses it in place of wall time).
"""
import os
import shutil
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GW = os.path.dirname(HERE)
CORE = ("costaslink_core.v bus_stage.v costaslink_regs.v spi_master.v max2871_init.v i2c_master.v tx_symbol.v "
        "tx_engine.v rx_engine.v ber_cdr.v ihold.v lockmon.v count_ram.v prbs.v capture.v seq_gate.v cmp_monitor.v morse_keyer.v turnaround.v fp_lut5.v").split()


class PipeBus:
    def __init__(self, ser=8, workdir=None, iverilog="iverilog", vvp="vvp"):
        if workdir is None:                 # beside the other build products, not in /tmp
            base = os.path.join(os.path.dirname(GW), "build", "gateware_scratch")
            os.makedirs(base, exist_ok=True)
            workdir = tempfile.mkdtemp(prefix="sim_pipe_", dir=base)
            self._own_dir = True
        else:
            self._own_dir = False
        self.dir = workdir
        out = os.path.join(self.dir, "tb_pipe.vvp")
        subprocess.run([iverilog, "-g2005", "-Wno-timescale", "-I", GW, "-P", "tb_pipe.SER=%d" % ser, "-o", out,
                        os.path.join(GW, "tb_pipe.v")] + [os.path.join(GW, f) for f in CORE], check=True)
        self.cmd_path = os.path.join(self.dir, "cmd.fifo")
        self.rsp_path = os.path.join(self.dir, "rsp.fifo")
        os.mkfifo(self.cmd_path)
        os.mkfifo(self.rsp_path)
        self.proc = subprocess.Popen([vvp, "-N", out, "+cmd=" + self.cmd_path, "+rsp=" + self.rsp_path],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=self.dir)
        self.cmd = open(self.cmd_path, "w")
        self.rsp = open(self.rsp_path, "r")

    def _line(self, text):
        self.cmd.write(text + "\n")
        self.cmd.flush()
        reply = self.rsp.readline().strip()
        if not reply:
            raise IOError("the simulation ended (%r)" % text)
        return reply

    def read(self, reg):
        # a block RAM word never written is X in the simulator and 0 on the FPGA (both power up so)
        return int(self._line("R %02x" % reg).translate(str.maketrans("xXzZ", "0000")), 16)

    def write(self, reg, value):
        assert self._line("W %02x %08x" % (reg, int(value) & 0xFFFFFFFF)) == "OK"

    def clocks(self, n):
        assert self._line("C %d" % int(n)) == "OK"

    def knob(self, name, value):
        assert self._line("M %s %d" % (name, int(value))) == "OK"

    def trig(self, sample=0, clocks=2):
        """TRIG_IN rises at `sample` of the next clock, high `clocks` clocks"""
        assert self._line("T %d %d" % (sample, clocks)) == "OK"

    def close(self):
        try:
            self.cmd.write("Q\n")
            self.cmd.flush()
        except (BrokenPipeError, ValueError):
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        for f in (self.cmd, self.rsp):
            try:
                f.close()
            except (BrokenPipeError, ValueError):
                pass
        if self._own_dir:
            shutil.rmtree(self.dir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
