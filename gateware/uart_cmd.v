// uart_cmd: the ASCII command parser that turns UART lines into register-bus cycles.
//
// Board signal: none; it is the host side of the register file (costaslink_regs.v).  On the Icepi
// Zero the host is a terminal or a Python script on the FTDI port; on the PYNQ-Z2 an AXI-Lite bridge
// will drive the same bus (addr / wdata / we / re / rdata) from the PS later.
//
// Protocol (one command per line, one command at a time: wait for the reply):
//   "W aa dddddddd\n"   write register 0xaa (1-2 hex digits) with 0xdddddddd (1-8 hex digits): reply "OK\n"
//   "R aa\n"            read register 0xaa:                                             reply "dddddddd\n"
//   anything else:                                                                      reply "?\n"
// Letters may be lower case, '\r' counts as a line end, extra spaces are ignored.  Characters that
// arrive while a reply is being sent are dropped.

module uart_cmd (
    input  wire        clk,
    input  wire        rst,
    // from uart_rx / to uart_tx
    input  wire [7:0]  rx_data,
    input  wire        rx_valid,
    output reg  [7:0]  tx_data,
    output reg         tx_start,
    input  wire        tx_busy,
    // the register bus
    output reg  [7:0]  bus_addr,
    output reg  [31:0] bus_wdata,
    output reg         bus_we,       // one-cycle pulse
    output reg         bus_re,       // one-cycle pulse; bus_rdata is sampled the cycle after (the address has
                                     // stood since the line's digits: the core's two-clock read is long done)
    input  wire [31:0] bus_rdata
);
    localparam [3:0] P_IDLE = 4'd0,  // waiting for 'R' or 'W'
                     P_ADDR = 4'd1,  // hex digits of the address
                     P_DATA = 4'd2,  // hex digits of the data (writes)
                     P_END  = 4'd3,  // a read, after its address: only spaces until the line end
                     P_ERR  = 4'd4,  // swallowing a bad line up to its end
                     P_DO_W = 4'd5,
                     P_DO_R = 4'd6,
                     P_RD_L = 4'd7,  // latch bus_rdata
                     P_REPL = 4'd8;  // sending the reply

    localparam [1:0] REP_HEX = 2'd0, REP_OK = 2'd1, REP_ERR = 2'd2;

    reg [3:0]  st;
    reg        is_write;
    reg        have_digit;
    reg [1:0]  rep_kind;
    reg [3:0]  rep_idx;
    reg [31:0] rep_val;             // the value being printed, consumed a nibble at a time from the top

    // ---- character classes --------------------------------------------------------------------
    wire c_nl    = (rx_data == 8'h0A) || (rx_data == 8'h0D);
    wire c_space = (rx_data == 8'h20) || (rx_data == 8'h09);
    wire c_hex   = (rx_data >= 8'h30 && rx_data <= 8'h39) ||
                   (rx_data >= 8'h41 && rx_data <= 8'h46) ||
                   (rx_data >= 8'h61 && rx_data <= 8'h66);
    wire [3:0] nib = (rx_data <= 8'h39) ? rx_data[3:0] : (rx_data[3:0] + 4'd9);   // 'A'/'a' = 0x_1 -> 10
    wire c_w = (rx_data == 8'h57) || (rx_data == 8'h77);
    wire c_r = (rx_data == 8'h52) || (rx_data == 8'h72);

    function [7:0] hexchar;
        input [3:0] v;
        begin
            hexchar = (v < 4'd10) ? (8'h30 + {4'd0, v}) : (8'h37 + {4'd0, v});    // '0'..'9', 'A'..'F'
        end
    endfunction

    always @(posedge clk) begin
        bus_we   <= 1'b0;
        bus_re   <= 1'b0;
        tx_start <= 1'b0;
        if (rst) begin
            st         <= P_IDLE;
            is_write   <= 1'b0;
            have_digit <= 1'b0;
            bus_addr   <= 8'd0;
            bus_wdata  <= 32'd0;
            rep_kind   <= REP_OK;
            rep_idx    <= 4'd0;
            rep_val    <= 32'd0;
            tx_data    <= 8'd0;
        end else begin
            case (st)
            P_IDLE: if (rx_valid) begin
                if (c_w || c_r) begin
                    is_write   <= c_w;
                    bus_addr   <= 8'd0;
                    bus_wdata  <= 32'd0;
                    have_digit <= 1'b0;
                    st         <= P_ADDR;
                end else if (!(c_space || c_nl)) begin
                    st <= P_ERR;
                end
            end

            P_ADDR: if (rx_valid) begin
                if (c_hex) begin
                    bus_addr   <= {bus_addr[3:0], nib};
                    have_digit <= 1'b1;
                end else if (c_space) begin
                    if (have_digit) begin
                        have_digit <= 1'b0;
                        st         <= is_write ? P_DATA : P_END;
                    end
                end else if (c_nl) begin
                    if (have_digit && !is_write) st <= P_DO_R;
                    else begin rep_kind <= REP_ERR; rep_idx <= 4'd0; st <= P_REPL; end
                end else begin
                    st <= P_ERR;
                end
            end

            P_DATA: if (rx_valid) begin
                if (c_hex) begin
                    bus_wdata  <= {bus_wdata[27:0], nib};
                    have_digit <= 1'b1;
                end else if (c_nl) begin
                    if (have_digit) st <= P_DO_W;
                    else begin rep_kind <= REP_ERR; rep_idx <= 4'd0; st <= P_REPL; end
                end else if (!c_space) begin
                    st <= P_ERR;
                end
            end

            P_END: if (rx_valid) begin
                if (c_nl)         st <= P_DO_R;
                else if (!c_space) st <= P_ERR;
            end

            P_ERR: if (rx_valid && c_nl) begin
                rep_kind <= REP_ERR;
                rep_idx  <= 4'd0;
                st       <= P_REPL;
            end

            P_DO_W: begin
                bus_we   <= 1'b1;
                rep_kind <= REP_OK;
                rep_idx  <= 4'd0;
                st       <= P_REPL;
            end

            P_DO_R: begin
                bus_re <= 1'b1;
                st     <= P_RD_L;
            end

            P_RD_L: begin
                rep_val  <= bus_rdata;
                rep_kind <= REP_HEX;
                rep_idx  <= 4'd0;
                st       <= P_REPL;
            end

            P_REPL: if (!tx_busy && !tx_start) begin
                tx_start <= 1'b1;
                rep_idx  <= rep_idx + 1'b1;
                case (rep_kind)
                REP_HEX: begin
                    if (rep_idx == 4'd8) begin tx_data <= 8'h0A; st <= P_IDLE; end
                    else begin tx_data <= hexchar(rep_val[31:28]); rep_val <= {rep_val[27:0], 4'd0}; end
                end
                REP_OK: begin
                    if (rep_idx == 4'd0)      tx_data <= 8'h4F;                      // 'O'
                    else if (rep_idx == 4'd1) tx_data <= 8'h4B;                      // 'K'
                    else begin tx_data <= 8'h0A; st <= P_IDLE; end
                end
                default: begin
                    if (rep_idx == 4'd0) tx_data <= 8'h3F;                           // '?'
                    else begin tx_data <= 8'h0A; st <= P_IDLE; end
                end
                endcase
            end

            default: st <= P_IDLE;
            endcase
        end
    end
endmodule
