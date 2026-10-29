# ---------------------------------------------------------------------------
# Build the CostasLink overlay for a PYNQ-Z2, from nothing, in one command (Response 15):
#
#     source <Vivado 2024.1>/settings64.sh
#     cd gateware && vivado -mode batch -source pynq/build.tcl [-tclargs -bench | -synth_only | -jobs N]
#
# Vivado 2024.1: the release PYNQ v3.1 (the newest image for the PYNQ-Z2, kernel xilinx-v2024.1) is built
# on.  The GPSDO's 2022.1 bitstream loaded unchanged on PYNQ 3.1.1 too, so 2022.1 would also do; 2024.1 is
# the one its tutorials and its board files match.
#
# After GPSDO-PYNQ-Z2/gateware/build.tcl: everything scripted (the project, the block design, the address
# map, synthesis, implementation, the handoff files), so the result is reviewable as a diff.  The block
# design is a real IP Integrator design: `vivado gateware/build/pynq/costaslink/costaslink.xpr` draws it,
# and build/pynq/costaslink_top_block_diagram.pdf is drawn from it every build (pynq/bd_diagram.tcl).
#
#   PS7 (the board preset) --M_AXI_GP0--> SmartConnect --> costaslink_pynq (module reference: AXI-Lite,
#   the ISERDESE2 sampler, the core) <--> the header pins
#   FCLK_CLK0 100 MHz --> clock wizard (MMCM) --> 100 MHz: the AXI and the fabric
#                                             --> 400 MHz: the ISERDES (800 Ms/s, DDR)
#   proc_sys_reset holds everything until the PS's reset lifts and the MMCM locks.
#
# Options:
#     -bench       the bring-up variant: plus a JTAG-to-AXI master (the register map from Vivado's hardware
#                  manager over the PYNQ's USB cable, with no Linux): build/pynq/bench/, never overlay/
#     -synth_only  stop after synthesis
#     -jobs N      parallel jobs (default 8)
# Outputs: build/pynq/overlay/costaslink_top.{bit,hwh,xsa}: PYNQ loads the .bit with the .hwh beside it.
# A design that fails timing is refused: no .bit is published.
# ---------------------------------------------------------------------------

set script_dir [file normalize [file dirname [info script]]]
set gw_dir     [file dirname $script_dir]
set build_dir  [file normalize $gw_dir/../build/pynq]
set proj_name  costaslink
set bd_name    costaslink_top

set synth_only 0
set bench      0
set jobs       8
for {set i 0} {$i < [llength $argv]} {incr i} {
    switch -- [lindex $argv $i] {
        -synth_only { set synth_only 1 }
        -bench      { set bench 1 }
        -jobs       { incr i; set jobs [lindex $argv $i] }
    }
}
if {$bench} { set proj_name costaslink_bench }
puts "=== CostasLink overlay (Vivado [version -short]) ==="

# ---- 1. constraints, from gen/pins.py ---------------------------------------
set xdc $script_dir/costaslink_pynq.xdc
if {[catch {exec python3 $gw_dir/gen_xdc.py} msg]} { puts "WARNING: gen_xdc.py: $msg (using the checked-in XDC)" }
if {![file exists $xdc]} { error "no constraints at $xdc" }

# ---- 2. the project ------------------------------------------------------------
file mkdir $build_dir
if {[file exists $build_dir/$proj_name]} { file delete -force $build_dir/$proj_name }
create_project $proj_name $build_dir/$proj_name -part xc7z020clg400-1 -force
set_property board_part_repo_paths [list $script_dir/board_files] [current_project]
set_property board_part tul.com.tw:pynq-z2:part0:1.0 [current_project]
set_property target_language Verilog [current_project]

set rtl {costaslink_pynq.v axil_bridge.v fast_sampler_7series.v costaslink_core.v bus_stage.v costaslink_regs.v spi_master.v
         max2871_init.v i2c_master.v tx_symbol.v tx_engine.v rx_engine.v count_ram.v prbs.v capture.v seq_gate.v
         cmp_monitor.v morse_keyer.v}
foreach f $rtl { add_files -norecurse $gw_dir/$f }
add_files -norecurse $gw_dir/regmap.vh $gw_dir/max2871_words.vh
set_property file_type {Verilog Header} [get_files regmap.vh]
set_property file_type {Verilog Header} [get_files max2871_words.vh]
set_property include_dirs [list $gw_dir] [current_fileset]
add_files -fileset constrs_1 -norecurse $xdc
update_compile_order -fileset sources_1

# ---- 3. the block design ------------------------------------------------------------
create_bd_design $bd_name
current_bd_design $bd_name

set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ {100} CONFIG.PCW_EN_CLK0_PORT {1}] $ps

# the clocks: 100 MHz for the fabric and the AXI, 400 MHz for the ISERDES, from one MMCM
set cw [create_bd_cell -type ip -vlnv xilinx.com:ip:clk_wiz clk_wiz_0]
set_property -dict [list \
    CONFIG.PRIM_IN_FREQ {100.000} \
    CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {100.000} \
    CONFIG.CLKOUT2_USED {true} CONFIG.CLKOUT2_REQUESTED_OUT_FREQ {400.000} \
    CONFIG.USE_LOCKED {true} CONFIG.USE_RESET {true} CONFIG.RESET_TYPE {ACTIVE_LOW} \
] $cw
connect_bd_net [get_bd_pins ps7/FCLK_CLK0] [get_bd_pins clk_wiz_0/clk_in1]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins clk_wiz_0/resetn]

set rst [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset rst_100M]
set sc  [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect axi_sc]
set_property -dict [list CONFIG.NUM_SI [expr {$bench ? 2 : 1}] CONFIG.NUM_MI {1}] $sc
if {$bench} {
    set jax [create_bd_cell -type ip -vlnv xilinx.com:ip:jtag_axi jtag_axi_0]
    set_property -dict [list CONFIG.PROTOCOL {2}] $jax
}

# the CostasLink core as a module reference: one file's top, no IP repository
set cl [create_bd_cell -type module -reference costaslink_pynq costaslink_0]

set clk100 [get_bd_pins clk_wiz_0/clk_out1]
connect_bd_net $clk100 [get_bd_pins ps7/M_AXI_GP0_ACLK] [get_bd_pins axi_sc/aclk] \
                       [get_bd_pins rst_100M/slowest_sync_clk] [get_bd_pins costaslink_0/s_axi_aclk]
connect_bd_net [get_bd_pins clk_wiz_0/clk_out2] [get_bd_pins costaslink_0/clk_fast]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N] [get_bd_pins rst_100M/ext_reset_in]
connect_bd_net [get_bd_pins clk_wiz_0/locked] [get_bd_pins rst_100M/dcm_locked]
connect_bd_net [get_bd_pins rst_100M/peripheral_aresetn] [get_bd_pins axi_sc/aresetn] [get_bd_pins costaslink_0/s_axi_aresetn]
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0] [get_bd_intf_pins axi_sc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_sc/M00_AXI] [get_bd_intf_pins costaslink_0/S_AXI]
if {$bench} {
    connect_bd_net $clk100 [get_bd_pins jtag_axi_0/aclk]
    connect_bd_net [get_bd_pins rst_100M/peripheral_aresetn] [get_bd_pins jtag_axi_0/aresetn]
    connect_bd_intf_net [get_bd_intf_pins jtag_axi_0/M_AXI] [get_bd_intf_pins axi_sc/S01_AXI]
}

# every header pin of the module reference, external under its own name (the XDC's)
foreach p [get_bd_pins -of_objects $cl] {
    set n [get_property NAME $p]
    if {[string match "s_axi_*" $n] || $n eq "clk_fast"} { continue }
    make_bd_pins_external -name $n $p
}

assign_bd_address
set seg [get_bd_addr_segs -of_objects [get_bd_addr_spaces ps7/Data] -filter {NAME =~ "*costaslink_0*"}]
set_property offset 0x43C00000 $seg
set_property range 4K $seg
if {$bench} {
    set jseg [get_bd_addr_segs -of_objects [get_bd_addr_spaces jtag_axi_0/Data] -filter {NAME =~ "*costaslink_0*"}]
    set_property offset 0x43C00000 $jseg
    set_property range 4K $jseg
}
validate_bd_design
save_bd_design

set tag [expr {$bench ? "bench_" : ""}]
write_bd_tcl -force $build_dir/${tag}${bd_name}_bd.tcl
source $script_dir/bd_diagram.tcl
bd_diagram $build_dir/${tag}${bd_name}.dot $build_dir/${tag}${bd_name}_block_diagram.pdf "CostasLink overlay - $bd_name"

# ---- 4. wrapper, synthesis, implementation --------------------------------------------
# Synthesize the block design with the top (global), not each cell out of context: out of context, the module
# reference's tristate pins (I2C SCL and SDA, TX_Q1's input mode) lost their 1'bz ("[Synth 8-5799] Converted
# tricell instance to logic", a critical warning nobody read): every PYNQ build to 2026-10-29 drove them, so I2C
# never worked on the board (rev A bring-up, board A).  Globally they reach the pins and infer IOBUFs; step 5
# refuses a bitstream in which they did not.
set_property synth_checkpoint_mode None [get_files $bd_name.bd]
make_wrapper -files [get_files $bd_name.bd] -top
set wrapper ""
foreach cand [list $build_dir/$proj_name/${proj_name}.gen/sources_1/bd/$bd_name/hdl/${bd_name}_wrapper.v \
                   $build_dir/$proj_name/${proj_name}.srcs/sources_1/bd/$bd_name/hdl/${bd_name}_wrapper.v] {
    if {[file exists $cand]} { set wrapper $cand; break }
}
if {$wrapper eq ""} { error "cannot find the generated BD wrapper" }
add_files -norecurse $wrapper
set_property top ${bd_name}_wrapper [current_fileset]
update_compile_order -fileset sources_1

launch_runs synth_1 -jobs $jobs
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] != "100%"} { error "SYNTHESIS FAILED: $build_dir/$proj_name/${proj_name}.runs/synth_1" }
puts "--- synthesis complete"
if {$synth_only} { puts "--- -synth_only: stopping"; exit 0 }

launch_runs impl_1 -to_step write_bitstream -jobs $jobs
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] != "100%"} { error "IMPLEMENTATION FAILED: $build_dir/$proj_name/${proj_name}.runs/impl_1" }

# ---- 5. timing, and what PYNQ loads ---------------------------------------------------------
open_run impl_1
set wns [get_property SLACK [get_timing_paths -delay_type max]]
set whs [get_property SLACK [get_timing_paths -delay_type min]]
puts "--- TIMING: WNS = $wns ns   WHS = $whs ns"
report_utilization -file $build_dir/${tag}utilization.rpt
report_timing_summary -file $build_dir/${tag}timing_summary.rpt
if {$wns < 0 || $whs < 0} {
    error "timing not met (WNS $wns ns, WHS $whs ns): refusing to publish the overlay; $build_dir/${tag}timing_summary.rpt"
}
# the tristate pins must end in a tristate buffer (IOBUF, or the OBUFT it becomes), not a plain OBUF or IBUF
foreach p {i2c_scl i2c_sda tx_q1} {
    set refs [get_property REF_NAME [get_cells -of_objects [get_pins -leaf -of_objects [get_nets -of_objects [get_ports $p]]]]]
    if {[lsearch -regexp $refs {^(IOBUF|OBUFT)}] < 0} {
        error "port $p is driven by '$refs', not a tristate buffer: its 1'bz was lost in synthesis; refusing to publish"
    }
    puts "--- $p: $refs"
}
set bit [glob -nocomplain $build_dir/$proj_name/${proj_name}.runs/impl_1/*.bit]
set hwh [glob -nocomplain $build_dir/$proj_name/${proj_name}.gen/sources_1/bd/$bd_name/hw_handoff/$bd_name.hwh]
set out [expr {$bench ? "$build_dir/bench" : "$build_dir/overlay"}]
file mkdir $out
if {$bit ne ""} { file copy -force [lindex $bit 0] $out/$bd_name.bit }
if {$hwh ne ""} { file copy -force [lindex $hwh 0] $out/$bd_name.hwh }
if {!$bench} { write_hw_platform -fixed -include_bit -force $out/$bd_name.xsa }
if {[file isdirectory [pwd]/NA]} { file delete -force [pwd]/NA }
puts "\n=== DONE: $out/$bd_name.bit + .hwh   (WNS $wns ns, WHS $whs ns) ==="
exit 0
