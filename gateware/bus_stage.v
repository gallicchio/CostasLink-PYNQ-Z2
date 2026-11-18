// bus_stage: the register bus and the reset, registered once (Response 15).  costaslink_core.v puts one
// beside each block, so no block's decoder or read mux hangs straight off the bridge's registers across the
// chip: the Icepi's path from uart_cmd's address to rx_engine's read mux was 8.7 ns of routing, and one
// reset flip-flop driving ~5000 resets was the PYNQ build's worst path.  keep_hierarchy keeps the copies
// apart: Yosys merges identical flip-flops even when they are marked keep (Vivado honours either).

(* keep_hierarchy = "yes" *)
module bus_stage (
    input  wire        clk,
    input  wire        rst,
    input  wire [7:0]  addr,
    input  wire [31:0] wdata,
    input  wire        we,
    input  wire        re,
    output reg         rst_q,
    output reg  [7:0]  addr_q,
    output reg  [31:0] wdata_q,
    output reg         we_q,
    output reg         re_q
);
    always @(posedge clk) begin
        rst_q   <= rst;
        addr_q  <= addr;
        wdata_q <= wdata;
        we_q    <= we && !rst;
        re_q    <= re && !rst;
    end
endmodule
