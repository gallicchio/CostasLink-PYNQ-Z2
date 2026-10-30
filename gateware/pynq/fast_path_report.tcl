# fast_path_report.tcl: the receive-to-transmit paths' delays from the routed design (Prompt 36), sourced by
# build.tcl after open_run.  costaslink_fast_path.xdc segments the fast path at the ISERDESE2s' O and the
# ladder IOBUFs' output buffers' I (the generated XDC's false paths cover the ports), which makes O a
# startpoint and I an endpoint, so a pin-to-pin delay is summed, all at one corner, from:
#   the input port -> the ISERDESE2's D (the input buffer and its route: a timed path),
#   D -> O (the ISERDESE2's combinational arc),
#   O -> the OBUFT's I (the fabric, the path the constraint holds),
#   I -> O of the OBUFT (its arc: LVCMOS33, 8 mA, FAST; to the pad, unloaded).
# Max is the slow corner's, min the fast corner's.  The registered paths: from the clock pin of the
# flip-flops that drive the ladders (tx_engine's pins register, the fast path's arm and table copies) to
# the pad, the synchronous paths' last step.
#
#     fast_path_report <file>      writes the tables, returns a one-line summary

proc fp_seg {from to type} {
    set p [get_timing_paths -from $from -to $to -delay_type $type -max_paths 1 -nworst 1]
    if {[llength $p] == 0} { return "" }
    return [get_property DATAPATH_DELAY $p]
}

proc fp_arc {from to type} {
    set a [get_timing_arcs -from $from -to $to]
    if {[llength $a] == 0} { return "" }
    if {$type eq "max"} {
        return [expr {max([get_property DELAY_SLOW_MAX_RISE $a], [get_property DELAY_SLOW_MAX_FALL $a])}]
    }
    return [expr {min([get_property DELAY_FAST_MIN_RISE $a], [get_property DELAY_FAST_MIN_FALL $a])}]
}

proc fast_path_report {file} {
    set cmps {cmp_i cmp_qp cmp_qn cmp_ip cmp_in}
    set lads {tx_i0 tx_i1 tx_q0 tx_q1}
    set ladc {u_lad_i0 u_lad_i1 u_lad_q0 u_lad_q1}
    foreach c [get_cells -hierarchical -filter {REF_NAME == ISERDESE2 && NAME =~ *u_fs/*}] {
        if {[regexp {g_in\[([0-9])\]} [get_property NAME $c] -> k]} {
            set dpin($k) [get_pins -of_objects $c -filter {REF_PIN_NAME == D}]
            set opin($k) [get_pins -of_objects $c -filter {REF_PIN_NAME == O}]
        }
    }
    for {set j 0} {$j < 4} {incr j} {
        set ob [get_cells -hierarchical -filter "REF_NAME =~ OBUF* && NAME =~ *[lindex $ladc $j]/*"]
        set ipin($j) [get_pins -of_objects $ob -filter {REF_PIN_NAME == I}]
        set qpin($j) [get_pins -of_objects $ob -filter {REF_PIN_NAME == O}]
        foreach t {max min} { set out($j,$t) [fp_arc $ipin($j) $qpin($j) $t] }
    }
    for {set k 0} {$k < 5} {incr k} {
        set cp [lindex $cmps $k]
        foreach t {max min} {
            set a [fp_seg [get_ports $cp] $dpin($k) $t]
            set b [fp_arc $dpin($k) $opin($k) $t]
            set in($k,$t) [expr {($a eq "" || $b eq "") ? "" : $a + $b}]
        }
    }
    set fh [open $file w]
    puts $fh "CostasLink fast path: pin-to-pin delays (ns) of the routed design (Vivado [version -short], xc7z020clg400-1)"
    puts $fh "max: the slow corner's; min: the fast corner's.  = port -> ISERDESE2 D -> O + the fabric + OBUFT I -> O.\n"
    set all_max 0.0; set all_min 1e9; set worst ""; set best ""; set fab_max 0.0; set fab_min 1e9
    set head [format "%-8s" "from"]
    foreach l $lads { append head [format " %17s" "$l max/min"] }
    puts $fh $head
    for {set k 0} {$k < 5} {incr k} {
        set cp [lindex $cmps $k]
        set row [format "%-8s" $cp]
        for {set j 0} {$j < 4} {incr j} {
            set lp [lindex $lads $j]
            set f_max [fp_seg $opin($k) $ipin($j) max]
            set f_min [fp_seg $opin($k) $ipin($j) min]
            if {$in($k,max) eq "" || $f_max eq "" || $out($j,max) eq "" || $f_min eq "" || $in($k,min) eq "" || $out($j,min) eq ""} {
                append row [format " %17s" "-"]
                continue
            }
            set tmax [expr {$in($k,max) + $f_max + $out($j,max)}]
            set tmin [expr {$in($k,min) + $f_min + $out($j,min)}]
            append row [format " %8.3f/%-8.3f" $tmax $tmin]
            if {$f_max > $fab_max} { set fab_max $f_max }
            if {$f_min < $fab_min} { set fab_min $f_min }
            if {$tmax > $all_max} { set all_max $tmax; set worst "$cp -> $lp" }
            if {$tmin < $all_min} { set all_min $tmin; set best "$cp -> $lp" }
        }
        puts $fh $row
    }
    puts $fh [format "\nworst (max) %.3f ns: %s;  best (min) %.3f ns: %s" $all_max $worst $all_min $best]
    puts $fh [format "the fabric's segment (ISERDESE2 O -> OBUFT I): max %.3f, min %.3f ns" $fab_max $fab_min]
    puts $fh "\nthe fixed parts:"
    for {set k 0} {$k < 5} {incr k} {
        puts $fh [format "  %-6s -> ISERDESE2 O (input buffer, route, D -> O): max %.3f, min %.3f" \
            [lindex $cmps $k] $in($k,max) $in($k,min)]
    }
    for {set j 0} {$j < 4} {incr j} {
        puts $fh [format "  OBUFT I -> %-5s (LVCMOS33 8 mA FAST): max %.3f, min %.3f" [lindex $lads $j] $out($j,max) $out($j,min)]
    }
    # the registered paths: tx_engine's pins register (every synchronous mode and the reply) and the fast
    # path's arm, each from its flip-flop's clock pin to the pad
    set pins_ff [get_cells -hierarchical -filter {REF_NAME =~ FD* && (NAME =~ *u_tx/tx_i_reg* || NAME =~ *u_tx/tx_q_reg*)}]
    set arm_ff  [get_cells -hierarchical -filter {REF_NAME =~ FD* && NAME =~ *u_lat/fp_arm_c_reg*}]
    set c2p_max 0.0; set c2p_min 1e9
    foreach {what ffl} [list "the pins' register" $pins_ff "the fast path's arm" $arm_ff] {
        puts $fh "\n$what -> the ladder pad (clock-to-pad, from the clock at the flip-flop):"
        if {[llength $ffl] == 0} { puts $fh "  (no such flip-flops)"; continue }
        for {set j 0} {$j < 4} {incr j} {
            set lp [lindex $lads $j]
            set r_max [fp_seg $ffl $ipin($j) max]
            set r_min [fp_seg $ffl $ipin($j) min]
            if {$r_max eq "" || $r_min eq ""} { puts $fh "  $lp: no path"; continue }
            set pm [get_timing_paths -from $ffl -to $ipin($j) -delay_type max -max_paths 1]
            set src [get_property STARTPOINT_PIN $pm]
            set cmax [expr {$r_max + $out($j,max)}]
            set cmin [expr {$r_min + $out($j,min)}]
            puts $fh [format "  %-5s: max %.3f, min %.3f  (%s)" $lp $cmax $cmin $src]
            if {$what eq "the pins' register"} {
                if {$cmax > $c2p_max} { set c2p_max $cmax }
                if {$cmin < $c2p_min} { set c2p_min $cmin }
            }
        }
    }
    puts $fh [format "  the pins' register, all four: max %.3f, min %.3f ns" $c2p_max $c2p_min]
    puts $fh "\nthe pads' sites:"
    for {set k 0} {$k < 5} {incr k} {
        set c [get_cells -of_objects $opin($k)]
        puts $fh [format "  %-6s %s %s" [lindex $cmps $k] [get_property PACKAGE_PIN [get_ports [lindex $cmps $k]]] [get_property LOC $c]]
    }
    for {set j 0} {$j < 4} {incr j} {
        puts $fh [format "  %-6s %s %s" [lindex $lads $j] [get_property PACKAGE_PIN [get_ports [lindex $lads $j]]] \
            [get_property LOC [get_cells -of_objects $ipin($j)]]]
    }
    close $fh
    return [format "fast path pin-to-pin max %.3f ns (%s), min %.3f ns (%s); ladder clock-to-pad max %.3f, min %.3f ns" \
        $all_max $worst $all_min $best $c2p_max $c2p_min]
}
