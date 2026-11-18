// fp_lut5: a 5-input table looked up with no clock, reloaded 32 bits at a time (Prompt 36; turnaround.v's
// fast path).  o = table[a]; each clock with ce the table shifts one bit in at the bottom, table <=
// {table[30:0], cdi}, so 32 shifts load it entry 31 first.  This is the generic one (simulation, Yosys);
// the PYNQ-Z2 builds fp_lut5_7series.v instead, the same port on a CFGLUT5 (one LUT level), which shifts
// exactly so (its UNISIM model: data <= {data[30:0], CDI}, O6 = data[{I4,I3,I2,I1,I0}]).

module fp_lut5 (
    input  wire       clk,
    input  wire       ce,
    input  wire       cdi,
    input  wire [4:0] a,
    output wire       o
);
    /* verilator lint_off PROCASSINIT */
    reg [31:0] table_q = 32'd0;
    /* verilator lint_on PROCASSINIT */
    always @(posedge clk) if (ce) table_q <= {table_q[30:0], cdi};
    assign o = table_q[a];
endmodule
