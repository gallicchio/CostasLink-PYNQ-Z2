# gateware/Makefile: lint, synthesise, simulate and (for the Icepi Zero) place-and-route the first firmware.
#
#   make lint     Verilator --lint-only -Wall on the RTL (no warnings allowed): the generic top, and the core
#                 with the PYNQ-Z2's parameters (SER 8, the early reply lane, the fast path, the read-back)
#   make synth    Yosys synth_ecp5 of costaslink_top: prints the cell counts; the netlist goes to the scratch dir
#   make sim      Icarus Verilog: tb_costaslink.v against the words max2871_regs.py computes
#   make sim-engines  Icarus Verilog: tb_engines.v, the experiment engines against a loopback model
#   make sim-axil Icarus Verilog: tb_axil.v, the PYNQ-Z2's AXI-Lite bridge and the core
#   make sim-driver  the Python driver (driver/costaslink.py) against the RTL: driver/test_sim.py through
#                 tb_pipe.v (Icarus, two named pipes), the bring-up operations on the loopback model
#   make pnr      nextpnr-ecp5 + ecppack for the Icepi Zero (LFE5U-25F, CABGA256, icepi_zero.lpf): a .bit
#   make pnr-icepi  the Icepi Zero's own top (top_icepi.v): PLL 100 MHz, IDDRX1F 200 Ms/s, UART 1 Mbaud
#   make words    regenerate max2871_words.vh from max2871_regs.py (it is committed; rerun after editing the script)
#   make clean
#
# The tools come from an OSS CAD Suite: either on PATH or `make BIN=path/to/oss-cad-suite/bin ...`.
# Everything written goes to ../build/gateware_scratch/; nothing else in the tree changes.

BIN ?=
P := $(if $(BIN),$(BIN)/,)
VERILATOR := $(P)verilator
YOSYS     := $(P)yosys
IVERILOG  := $(P)iverilog
VVP       := $(P)vvp
NEXTPNR   := $(P)nextpnr-ecp5
ECPPACK   := $(P)ecppack
PYTHON    ?= python3

SCRATCH := ../build/gateware_scratch
TOP     := costaslink_top
CORE    := costaslink_core.v bus_stage.v costaslink_regs.v spi_master.v max2871_init.v i2c_master.v tx_symbol.v \
           tx_engine.v rx_engine.v ber_cdr.v ihold.v count_ram.v prbs.v capture.v seq_gate.v cmp_monitor.v morse_keyer.v turnaround.v fp_lut5.v
RTL     := costaslink_top.v fast_sampler_flop.v uart_rx.v uart_tx.v uart_cmd.v $(CORE)
TB      := tb_costaslink.v

.PHONY: all lint synth sim sim-engines sim-axil sim-driver pnr pnr-icepi words clean

all: lint synth sim sim-engines sim-axil sim-driver

words:
	$(PYTHON) max2871_regs.py --verilog

$(SCRATCH):
	mkdir -p $@

lint:
	$(VERILATOR) --lint-only -Wall -I. --top-module $(TOP) $(RTL)
	@# the core as the PYNQ-Z2 builds it: 8 samples a clock, the reply lane early, the fast path, the read-back
	$(VERILATOR) --lint-only -Wall -I. --top-module costaslink_core -GSER=8 -GBOARD=1 -GEARLY=1 -GFAST_PATH=1 -GTXFB=1 -GRP_REG=0 $(CORE)
	@echo "lint: clean"

synth: | $(SCRATCH)
	$(YOSYS) -q -l $(SCRATCH)/synth_ecp5.log \
	    -p "read_verilog -I. $(RTL); synth_ecp5 -top $(TOP) -json $(SCRATCH)/$(TOP).json"
	@awk '/=== design hierarchy ===/{f=1} f' $(SCRATCH)/synth_ecp5.log | sed -n '1,40p'

sim: | $(SCRATCH)
	$(PYTHON) max2871_regs.py --hex > $(SCRATCH)/max2871_expected.hex
	$(IVERILOG) -g2005 -Wall -Wno-timescale -I. -o $(SCRATCH)/tb_costaslink.vvp \
	    -DEXPECTED_HEX='"$(SCRATCH)/max2871_expected.hex"' $(TB) $(RTL)
	$(VVP) -N $(SCRATCH)/tb_costaslink.vvp

sim-engines: | $(SCRATCH)
	$(IVERILOG) -g2005 -Wall -Wno-timescale -I. -o $(SCRATCH)/tb_engines.vvp tb_engines.v $(CORE)
	$(VVP) -N $(SCRATCH)/tb_engines.vvp
	@# and with the Icepi Zero's reply lane (RP_REG = 1: the reply registered once more)
	$(IVERILOG) -g2005 -Wall -Wno-timescale -I. -Ptb_engines.RP_REG=1 -o $(SCRATCH)/tb_engines_rp1.vvp tb_engines.v $(CORE)
	$(VVP) -N $(SCRATCH)/tb_engines_rp1.vvp

pnr: synth
	$(NEXTPNR) --25k --package CABGA256 --speed 6 --freq 50 --json $(SCRATCH)/$(TOP).json \
	    --lpf icepi_zero.lpf --textcfg $(SCRATCH)/$(TOP).config --log $(SCRATCH)/nextpnr.log
	$(ECPPACK) --compress $(SCRATCH)/$(TOP).config $(SCRATCH)/$(TOP)_icepi.bit
	@grep -E "Max frequency|Device utilisation|TRELLIS_SLICE|TRELLIS_IO|DP16KD|MULT18X18D|EHXPLLL" $(SCRATCH)/nextpnr.log | tail -12

sim-axil: | $(SCRATCH)
	$(IVERILOG) -g2005 -Wall -Wno-timescale -I. -o $(SCRATCH)/tb_axil.vvp tb_axil.v axil_bridge.v $(CORE)
	$(VVP) -N $(SCRATCH)/tb_axil.vvp

sim-driver: | $(SCRATCH)
	cd driver && $(PYTHON) -m unittest test_sim test_netbus -v

# the Icepi Zero's own top: PLL to 100 MHz, IDDRX1F (2 samples a clock), UART at 1 Mbaud
ICEPI_SEEDS ?= 1 2 3 4 5 6 7 8
ICEPI := top_icepi.v fast_sampler_ecp5.v uart_rx.v uart_tx.v uart_cmd.v $(CORE)
pnr-icepi: | $(SCRATCH)
	$(YOSYS) -q -l $(SCRATCH)/synth_icepi.log -p "read_verilog -I. $(ICEPI); synth_ecp5 -top top_icepi -json $(SCRATCH)/top_icepi.json"
	@# 100 MHz closes with some placements and not others (Response 15: seeds 1, 2, 5, 6 of six): try seeds
	@for seed in $(ICEPI_SEEDS); do \
	    if $(NEXTPNR) --25k --package CABGA256 --speed 6 --json $(SCRATCH)/top_icepi.json --seed $$seed \
	        --lpf icepi_zero.lpf --textcfg $(SCRATCH)/top_icepi.config --log $(SCRATCH)/nextpnr_icepi.log \
	        > /dev/null 2>&1; then echo "nextpnr: seed $$seed meets 100 MHz"; break; fi; \
	    echo "nextpnr: seed $$seed misses 100 MHz ($$(grep -o '[0-9.]* MHz (FAIL' $(SCRATCH)/nextpnr_icepi.log | tail -1))"; \
	    if [ $$seed = $(lastword $(ICEPI_SEEDS)) ]; then exit 1; fi; \
	done
	$(ECPPACK) --compress $(SCRATCH)/top_icepi.config $(SCRATCH)/top_icepi.bit
	@grep -E "Max frequency|TRELLIS_SLICE|TRELLIS_IO|DP16KD|EHXPLLL|IDDRX1F" $(SCRATCH)/nextpnr_icepi.log | tail -10

clean:
	rm -rf $(SCRATCH)
