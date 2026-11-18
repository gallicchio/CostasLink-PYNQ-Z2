// count_ram: an array of counters in block RAM (Response 15): the receiver's confusion matrix and its
// latency histogram.  One increment at a time, at least four clocks apart (the receiver's decisions are:
// decide, confirm, quiet, armed, decide); the read, a register after the block RAM's 5.6 ns clock-to-out
// (the ECP5's), the add and the write take a clock each;
// the bus reads through `rd_addr` / `rd_data`, which follows mem[rd_addr] whenever no increment is
// using the read port.  `clear` zeroes every counter, one a clock (`clearing` meanwhile); increments
// during a clear are dropped.  Plain inferred RAM: block RAM on both Vivado and Yosys (DP16KD).

module count_ram #(
    parameter integer AW = 10,
    parameter integer DW = 32
) (
    input  wire          clk,
    input  wire          rst,
    input  wire          clear,
    output reg           clearing,
    input  wire          inc,
    input  wire [AW-1:0] inc_addr,
    input  wire [AW-1:0] rd_addr,
    output reg  [DW-1:0] rd_data
);
    reg [DW-1:0] mem [0:(1<<AW)-1];
    reg [AW-1:0] ra, wa, pa, pa2, ca;
    reg [DW-1:0] q, q2, wd;
    reg          we, pend, pend2, rdcyc;

    always @(posedge clk) begin
        q <= mem[ra];
        if (we) mem[wa] <= wd;
    end

    always @* begin
        ra = (inc && !clearing) ? inc_addr : rd_addr;
    end

    always @(posedge clk) begin
        if (rst) begin
            clearing <= 1'b0; ca <= {AW{1'b0}}; we <= 1'b0; pend <= 1'b0; pend2 <= 1'b0; rdcyc <= 1'b0;
            pa <= {AW{1'b0}}; pa2 <= {AW{1'b0}}; wa <= {AW{1'b0}}; wd <= {DW{1'b0}}; q2 <= {DW{1'b0}};
            rd_data <= {DW{1'b0}};
        end else begin
            we <= 1'b0;
            q2 <= q;
            if (clear) begin
                clearing <= 1'b1; ca <= {AW{1'b0}}; pend <= 1'b0; pend2 <= 1'b0;
            end else if (clearing) begin
                we <= 1'b1; wa <= ca; wd <= {DW{1'b0}};
                ca <= ca + 1'b1;
                if (ca == {AW{1'b1}}) clearing <= 1'b0;
            end else begin
                // the increment's third clock: q2 holds mem[pa2]
                if (pend2) begin
                    we <= 1'b1; wa <= pa2; wd <= q2 + 1'b1;
                end
                pend2 <= pend; pa2 <= pa;
                pend <= inc;
                if (inc) pa <= inc_addr;
            end
            // the bus's copy: q is mem[rd_addr] when the last clock's read was the bus's
            if (rdcyc) rd_data <= q;
            rdcyc <= !(inc && !clearing);
        end
    end
endmodule
