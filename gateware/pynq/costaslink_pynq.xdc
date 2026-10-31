# CostasLink-PYNQ-Z2 on the PYNQ-Z2's Raspberry Pi header.  Made by gateware/gen_xdc.py from gen/pins.py.
# Header pin -> Zynq package pin from the GPSDO-PYNQ-Z2 board's verified table (TUL schematic sheet 4).
# Clock-capable header pins on this board: [10, 11, 13, 18, 26, 31, 35, 40] (18 and 26 are also clock-capable on the Icepi Zero).

# header  3  IO_L22P_T3_34              I2C to the DAC and ADC; 2k2 pull-up on the PYNQ
set_property PACKAGE_PIN W18 [get_ports {i2c_sda}]
set_property IOSTANDARD LVCMOS33 [get_ports {i2c_sda}]
set_property PULLUP true [get_ports {i2c_sda}]

# header  5  IO_L22N_T3_34              I2C clock; 2k2 pull-up on the PYNQ
set_property PACKAGE_PIN W19 [get_ports {i2c_scl}]
set_property IOSTANDARD LVCMOS33 [get_ports {i2c_scl}]
set_property PULLUP true [get_ports {i2c_scl}]

# header  7  IO_L17P_T2_34              TX I ladder, bit 1
set_property PACKAGE_PIN Y18 [get_ports {tx_i1}]
set_property IOSTANDARD LVCMOS33 [get_ports {tx_i1}]
set_property DRIVE 8 [get_ports {tx_i1}]
set_property SLEW FAST [get_ports {tx_i1}]

# header  8  IO_L22P_T3_13              comparator: Q < -Vth
set_property PACKAGE_PIN V6 [get_ports {cmp_qn}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmp_qn}]

# header 10  IO_L13N_T2_MRCC_13         comparator: Q > +Vth (MRCC N of the pair with pin 18)
set_property PACKAGE_PIN Y6 [get_ports {cmp_qp}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmp_qp}]

# header 11  IO_L11P_T1_SRCC_13         TX I ladder, bit 0
set_property PACKAGE_PIN U7 [get_ports {tx_i0}]
set_property IOSTANDARD LVCMOS33 [get_ports {tx_i0}]
set_property DRIVE 8 [get_ports {tx_i0}]
set_property SLEW FAST [get_ports {tx_i0}]

# header 12  IO_L1P_T0_AD0P_35          the Costas switch's select when JP1 is set to FPGA
set_property PACKAGE_PIN C20 [get_ports {loop_sel}]
set_property IOSTANDARD LVCMOS33 [get_ports {loop_sel}]
set_property DRIVE 4 [get_ports {loop_sel}]
set_property SLEW SLOW [get_ports {loop_sel}]

# header 13  IO_L11N_T1_SRCC_13         TX Q ladder, bit 1 (rpio_27: absent from the stock XDC)
set_property PACKAGE_PIN V7 [get_ports {tx_q1}]
set_property IOSTANDARD LVCMOS33 [get_ports {tx_q1}]
set_property DRIVE 8 [get_ports {tx_q1}]
set_property SLEW FAST [get_ports {tx_q1}]

# header 15  IO_L17N_T2_13              TX Q ladder, bit 0
set_property PACKAGE_PIN U8 [get_ports {tx_q0}]
set_property IOSTANDARD LVCMOS33 [get_ports {tx_q0}]
set_property DRIVE 8 [get_ports {tx_q0}]
set_property SLEW FAST [get_ports {tx_q0}]

# header 16  IO_L22N_T3_13              I window, - side: I_N above V_TIN (fast; the PYNQ's 2k2 pull-up here is a harmless load)
set_property PACKAGE_PIN W6 [get_ports {cmp_in}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmp_in}]

# header 18  IO_L13P_T2_MRCC_13         comparator: sign(I) = the data (clock-capable on both boards)
set_property PACKAGE_PIN Y7 [get_ports {cmp_i}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmp_i}]

# header 19  IO_L15P_T2_DQS_13          high opens the Costas integrator's input (VC frozen)
set_property PACKAGE_PIN V8 [get_ports {loop_hold}]
set_property IOSTANDARD LVCMOS33 [get_ports {loop_hold}]
set_property DRIVE 4 [get_ports {loop_hold}]
set_property SLEW SLOW [get_ports {loop_hold}]

# header 21  IO_L21N_T3_DQS_13          MAX2871 (TX) latch enable
set_property PACKAGE_PIN V10 [get_ports {le_pll_tx}]
set_property IOSTANDARD LVCMOS33 [get_ports {le_pll_tx}]
set_property DRIVE 4 [get_ports {le_pll_tx}]
set_property SLEW SLOW [get_ports {le_pll_tx}]

# header 22  IO_L15N_T2_DQS_AD12N_35    I window, + side: I_P above V_TIP (fast; sheet 7, Response 14)
set_property PACKAGE_PIN F20 [get_ports {cmp_ip}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmp_ip}]

# header 23  IO_L16P_T2_13              MAX2871 (TX) MUX: lock detect or register readback
set_property PACKAGE_PIN W10 [get_ports {mux_tx}]
set_property IOSTANDARD LVCMOS33 [get_ports {mux_tx}]

# header 24  IO_L15P_T2_DQS_AD12P_35    TX enable, high = transmit: U206 inverts it onto the ADL5375's DSOP; 1 k to ground here, so a host that is off, unconfigured or not driving it leaves the modulator off
set_property PACKAGE_PIN F19 [get_ports {tx_en}]
set_property IOSTANDARD LVCMOS33 [get_ports {tx_en}]
set_property DRIVE 4 [get_ports {tx_en}]
set_property SLEW SLOW [get_ports {tx_en}]

# header 26  IO_L12N_T1_MRCC_34         external trigger (a detector pulse) through the Schmitt buffer (clock-capable on both)
set_property PACKAGE_PIN U19 [get_ports {trig_in}]
set_property IOSTANDARD LVCMOS33 [get_ports {trig_in}]

# header 27  IO_L7P_T1_34               antenna switch control A; B = not A is made on the board (also on J303; 2k2 pull-up on the PYNQ)
set_property PACKAGE_PIN Y16 [get_ports {tr_a}]
set_property IOSTANDARD LVCMOS33 [get_ports {tr_a}]
set_property DRIVE 8 [get_ports {tr_a}]
set_property SLEW FAST [get_ports {tr_a}]

# header 28  IO_L7N_T1_34               slow path: Q < -Vth2
set_property PACKAGE_PIN Y17 [get_ports {cmp_qn_s}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmp_qn_s}]

# header 29  IO_L17N_T2_34              SPI data to the MAX2871s and the PE43711
set_property PACKAGE_PIN Y19 [get_ports {spi_sdata}]
set_property IOSTANDARD LVCMOS33 [get_ports {spi_sdata}]
set_property DRIVE 4 [get_ports {spi_sdata}]
set_property SLEW SLOW [get_ports {spi_sdata}]

# header 31  IO_L12P_T1_MRCC_34         SPI clock: both MAX2871s and the PE43711
set_property PACKAGE_PIN U18 [get_ports {spi_sclk}]
set_property IOSTANDARD LVCMOS33 [get_ports {spi_sclk}]
set_property DRIVE 4 [get_ports {spi_sclk}]
set_property SLEW SLOW [get_ports {spi_sclk}]

# header 32  IO_L1N_T0_AD0N_35          slow path: Q > +Vth2
set_property PACKAGE_PIN B20 [get_ports {cmp_qp_s}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmp_qp_s}]

# header 33  IO_L15N_T2_DQS_13          MAX2871 (RX) latch enable
set_property PACKAGE_PIN W8 [get_ports {le_pll_rx}]
set_property IOSTANDARD LVCMOS33 [get_ports {le_pll_rx}]
set_property DRIVE 4 [get_ports {le_pll_rx}]
set_property SLEW SLOW [get_ports {le_pll_rx}]

# header 35  IO_L14N_T2_SRCC_13         MAX2871 (RX) MUX (Icepi bank 0: no GDDRX2)
set_property PACKAGE_PIN Y8 [get_ports {mux_rx}]
set_property IOSTANDARD LVCMOS33 [get_ports {mux_rx}]

# header 36  IO_L2P_T0_AD8P_35          PE43711 latch enable
set_property PACKAGE_PIN B19 [get_ports {le_dsa}]
set_property IOSTANDARD LVCMOS33 [get_ports {le_dsa}]
set_property DRIVE 4 [get_ports {le_dsa}]
set_property SLEW SLOW [get_ports {le_dsa}]

# header 37  IO_L16N_T2_13              trigger out A (buffered to its SMA) (Icepi bank 0: no GDDRX2)
set_property PACKAGE_PIN W9 [get_ports {trig_a}]
set_property IOSTANDARD LVCMOS33 [get_ports {trig_a}]
set_property DRIVE 8 [get_ports {trig_a}]
set_property SLEW FAST [get_ports {trig_a}]

# header 38  IO_L2N_T0_AD8N_35          trigger out B (buffered to its SMA)
set_property PACKAGE_PIN A20 [get_ports {trig_b}]
set_property IOSTANDARD LVCMOS33 [get_ports {trig_b}]
set_property DRIVE 8 [get_ports {trig_b}]
set_property SLEW FAST [get_ports {trig_b}]

# header 40  IO_L14P_T2_SRCC_13         slow path: sign(I) through the 5 MHz stage (confirms or vetoes CMP_I)
set_property PACKAGE_PIN Y9 [get_ports {cmp_i_s}]
set_property IOSTANDARD LVCMOS33 [get_ports {cmp_i_s}]

# the PYNQ-Z2's own LEDs (ID version 8, lockmon.v; the board file part0_pins.xml): LD0..LD3, and the two RGB
# LEDs, rgb_led[0..2] = LD4 B, G, R and rgb_led[3..5] = LD5 B, G, R
set_property PACKAGE_PIN R14 [get_ports {led[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[0]}]
set_property PACKAGE_PIN P14 [get_ports {led[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[1]}]
set_property PACKAGE_PIN N16 [get_ports {led[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[2]}]
set_property PACKAGE_PIN M14 [get_ports {led[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {led[3]}]
set_property PACKAGE_PIN L15 [get_ports {rgb_led[0]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgb_led[0]}]
set_property PACKAGE_PIN G17 [get_ports {rgb_led[1]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgb_led[1]}]
set_property PACKAGE_PIN N15 [get_ports {rgb_led[2]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgb_led[2]}]
set_property PACKAGE_PIN G14 [get_ports {rgb_led[3]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgb_led[3]}]
set_property PACKAGE_PIN L14 [get_ports {rgb_led[4]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgb_led[4]}]
set_property PACKAGE_PIN M15 [get_ports {rgb_led[5]}]
set_property IOSTANDARD LVCMOS33 [get_ports {rgb_led[5]}]

# the overlay's outputs need no timing to the board: the comparators are asynchronous to every clock here,
# and the slow outputs (SPI, I2C, the control pins) change at kHz rates
set_false_path -to [get_ports -filter {DIRECTION == OUT || DIRECTION == INOUT}]
set_false_path -from [get_ports -filter {DIRECTION == IN || DIRECTION == INOUT}]

