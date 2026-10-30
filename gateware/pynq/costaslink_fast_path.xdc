# costaslink_fast_path.xdc: the receive-to-transmit paths' timing (Prompt 36; turnaround.v).  Written by
# hand, not by gen_xdc.py: it names no pin and changes no pin's standard.  Implementation only (build.tcl).
#
# The fast path: the five comparators through their ISERDESE2s' combinational O (fast_sampler_7series.v),
# per ladder bit two reloadable 5-input LUTs (fp_lut5_7series.v: CFGLUT5, which Vivado places as SRLC32E)
# and one LUT with the arm and the registered pin, to the four ladder pins' output buffers (the IOBUFs
# u_lad_* in costaslink_pynq.v): pin to pin, no clock.  The generated costaslink_pynq.xdc makes every path
# from an input port and to an output port false, and a false path outranks set_max_delay (Vivado 2024.1
# has no reset_path), so the constraint goes on the fabric's segment, from the ISERDESE2s' O to the output
# buffers' I: set_max_delay there makes both pins timing endpoints (path segmentation; Vivado says so with
# critical warnings 18-514 and 18-515, expected).  The buffers' own delays are fixed by the I/O standard
# and the pins; fast_path_report.tcl adds them back (port -> D -> O, O -> I, I -> O).
#
# The pins are on two sides of the die: CMP_I, CMP_QP, CMP_QN, CMP_IN and TX_I0, TX_Q0, TX_Q1 on bank 13
# (the left column, X0), CMP_IP on bank 35 and TX_I1 on bank 34 (the right, X1).  A path across is several
# ns of routing that no placement removes.  With one number for all, the placer balances each bit's LUTs
# between its far input and its near ones, mid-die, and every path comes out ~12 ns; so each group has its
# own number, and the same-side paths keep their LUTs by their pads.  (g_in?k? is g_in[k]: brackets do not
# match in a filter.)
#
# The ladder pins' register (tx_engine's tx_i / tx_q, with the synchronous reply in it) and the fast path's
# arm copies get the same: the register's clock-to-pad is the synchronous reply's last step, and it was
# unconstrained (any route at all).  The fast path's tables are static (loaded with it disarmed): a clock.
#
# The numbers are a few tenths of a ns over what this design reached with them set out of reach (the
# fabric's segment at the slow corner: left -> left 4.36 ns, left -> TX_I1 7.86, CMP_IP -> left 8.43,
# CMP_IP -> TX_I1 5.61; a register to its buffer 3.74), so the placer and router keep them and a change
# that loses them fails the build (build.tcl refuses a design with negative slack).
set o_left  [get_pins -of_objects [get_cells -hierarchical -filter {REF_NAME == ISERDESE2 && (NAME =~ *u_fs/g_in?0?.u_iserdes || NAME =~ *u_fs/g_in?1?.u_iserdes || NAME =~ *u_fs/g_in?2?.u_iserdes || NAME =~ *u_fs/g_in?4?.u_iserdes)}] -filter {REF_PIN_NAME == O}]
set o_right [get_pins -of_objects [get_cells -hierarchical -filter {REF_NAME == ISERDESE2 && NAME =~ *u_fs/g_in?3?.u_iserdes}] -filter {REF_PIN_NAME == O}]
set i_left  [get_pins -of_objects [get_cells -hierarchical -filter {REF_NAME =~ OBUF* && (NAME =~ *u_lad_i0/* || NAME =~ *u_lad_q0/* || NAME =~ *u_lad_q1/*)}] -filter {REF_PIN_NAME == I}]
set i_right [get_pins -of_objects [get_cells -hierarchical -filter {REF_NAME =~ OBUF* && NAME =~ *u_lad_i1/*}] -filter {REF_PIN_NAME == I}]
set_max_delay 4.6 -from $o_left  -to $i_left
set_max_delay 8.2 -from $o_left  -to $i_right
set_max_delay 8.8 -from $o_right -to $i_left
set_max_delay 6.0 -from $o_right -to $i_right
set_min_delay 0.0 -from $o_left  -to $i_left
set_min_delay 0.0 -from $o_left  -to $i_right
set_min_delay 0.0 -from $o_right -to $i_left
set_min_delay 0.0 -from $o_right -to $i_right

set lad_tab [get_cells -hierarchical -filter {(REF_NAME == CFGLUT5 || REF_NAME =~ SRL*) && NAME =~ *u_lat/g_fast*}]
set lad_ff  [get_cells -hierarchical -filter {REF_NAME =~ FD* && (NAME =~ *u_tx/tx_i_reg* || NAME =~ *u_tx/tx_q_reg* || NAME =~ *u_lat/fp_arm_c_reg*)}]
set_max_delay -datapath_only 10.0 -from $lad_tab -to $i_left
set_max_delay -datapath_only 10.0 -from $lad_tab -to $i_right
set_max_delay -datapath_only 4.0  -from $lad_ff  -to $i_left
set_max_delay -datapath_only 4.0  -from $lad_ff  -to $i_right
set_min_delay 0.0 -from $lad_ff -to $i_left
set_min_delay 0.0 -from $lad_ff -to $i_right
