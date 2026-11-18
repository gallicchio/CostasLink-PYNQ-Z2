# sim_sampler.tcl: check fast_sampler_7series.v's sample order and latency against the UNISIM ISERDESE2
# (Response 15), and fp_lut5_7series.v's CFGLUT5 against fp_lut5.v's rule (Prompt 36).
#     cd gateware && vivado -mode batch -source pynq/sim_sampler.tcl
# (or with xvlog / xelab / xsim directly, as below).  Prints "SAMPLER: ... PASS" and "FP_LUT5: ... PASS".
set here [file normalize [file dirname [info script]]]
set gw [file dirname $here]
set out [file normalize $gw/../build/gateware_scratch/xsim_sampler]
file mkdir $out
cd $out
exec xvlog $gw/fast_sampler_7series.v $gw/tb_sampler_7series.v $gw/fp_lut5_7series.v $gw/tb_fp_lut5_7series.v \
    $::env(XILINX_VIVADO)/data/verilog/src/glbl.v >@ stdout
exec xelab -L unisims_ver -L secureip -timescale 1ps/1ps -debug off tb_sampler_7series glbl -s tb_sampler >@ stdout
exec xsim tb_sampler -runall >@ stdout
exec xelab -L unisims_ver -L secureip -timescale 1ps/1ps -debug off tb_fp_lut5_7series glbl -s tb_fp_lut5 >@ stdout
exec xsim tb_fp_lut5 -runall >@ stdout
