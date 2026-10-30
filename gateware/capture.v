// capture: a logic analyser in block RAM (Response 15; registers 0x78-0x7D).
//
// One word a clock: every fast sample of the six fast inputs (6 x SER bits, sample s of input k at bit
// 6s + k: CMP_I, CMP_QP, CMP_QN, CMP_IP, CMP_IN, TRIG_IN), then 16 bits of context:
//   [+0] MUX_RX  [+1] MUX_TX  [+2] CMP_I_S  [+3] CMP_QP_S  [+4] CMP_QN_S
//   [+5] TR_A  [+6] LOOP_HOLD  [+7] TX_DIS  [+11:+8] the ladder pins' register {Q1 Q0 I1 I0}
//   [+12] TX event  [+13] RX event  [+14] RX decision  [+15] REPLY: a synchronous reply's first clock, or
//   the fast path armed (turnaround.v)
// and, with TXFB (the PYNQ-Z2), the four ladder pins as the pads drive them, read back through their own
// ISERDESE2s sample by sample (4 x SER bits after the context, sample s of pin p at 16 + 6 SER + 4s + p:
// I0, I1, Q0, Q1): the fast path's output, which no register holds, and every register's own pad time.
// So a capture shows what went out, what came back and what the decoder made of it, sample by sample:
// the in-FPGA scope every experiment of BRINGUP.md stages 3-6 starts from.  Arm, then the trigger
// (TX event, RX event, TRIG_IN's rising edge, any fast comparator's change, RX decision, a sequencer
// step's start: the hold's release, the T/R switch; a reply: the synchronous one's first clock or the
// fast path's first change; or the bus)
// stops the writing CAP_POST words later; the buffer is read from its oldest word, CAP_TRIG says where
// the trigger fell, CAP_TRIG[31:16] how many words were written since the arming (the newest that many
// are this capture's; older ones are stale), CAP_CTRL[3] that a whole buffer was.
//
// A word over 32 bits reads as 32-bit chunks (CAP_ADDR[17:16] the first; 3 for the PYNQ-Z2's 96-bit word).
// A read's side effect (the next chunk, the next word) takes place at the clock edge that sees bus_re:
// costaslink_core.v registers bus_rdata at that same edge, so the read returns the word before the step.
// The block RAM's output goes through a second register (rd_q: its clock-to-out is 5.8 ns on the ECP5),
// so the next word is ready 3 clocks after a read; both bridges read slower than that (the test bench's
// back-to-back reads are 3 clocks apart).
//
// The word and the trigger go through one register before the buffer (word_d, tsel_d), so the trigger's
// logic (any comparator's change across the clock's samples) has a clock of its own: the Icepi's 100 MHz.
// Both are delayed alike, so the trigger word is still the word that triggered.  After the stop, wp is
// the oldest word (the next to be overwritten): the buffer reads from there, CAP_POST words follow the
// trigger word (none for 0), and the trigger word sits 2^AW - 1 - CAP_POST from the oldest.

module capture #(
    parameter integer SER  = 8,
    parameter integer AW   = 12,                // depth 2^AW words
    parameter integer TXFB = 0                  // 1: the ladder pins' read-back samples are in the word
) (
    input  wire             clk,
    input  wire             rst,
    input  wire [7:0]       bus_addr,
    input  wire [31:0]      bus_wdata,
    input  wire             bus_we,
    input  wire             bus_re,
    output reg  [31:0]      bus_rdata,
    input  wire [6*SER-1:0] fs,
    input  wire [15:0]      ctx,                // the context bits above
    input  wire [4*SER-1:0] fs_tx,              // the ladder pins' samples, sample s of pin p at 4s + p (TXFB)
    input  wire             t_tx, t_rxev, t_trig, t_rxdec, t_seq, t_reply
);
`include "regmap.vh"
    localparam integer W    = 6 * SER + 16 + ((TXFB != 0) ? 4 * SER : 0);
    localparam integer NCH  = (W + 31) / 32;    // 32-bit chunks a word (1 to 3)
    localparam integer LASTCI = NCH - 1;
    localparam [1:0]   LASTC = LASTCI[1:0];
    localparam [7:0]   SER_W = SER[7:0];
    localparam [7:0]   W_W   = W[7:0];
    localparam [7:0]   AW_W  = AW[7:0];

    reg [W-1:0]  mem [0:(1<<AW)-1];
    reg [AW-1:0] wp, tp;
    reg [31:0]   post, left;
    reg          armed, trig, done;
    reg [AW:0]   nvalid;                        // words written since the arming, to 2^AW
    wire         filled = nvalid[AW];
    reg [2:0]    src;
    reg          force_;
    reg [15:0]   rd_idx;
    reg [1:0]    rd_chunk;
    reg [W-1:0]  rd_word, rd_q;

    // any fast comparator changed between consecutive samples (the previous clock's last counts)
    reg [4:0]    last_vec;
    reg [4:0]    prev_v;
    reg          any_change;
    integer      s;
    always @* begin
        any_change = 1'b0;
        for (s = 0; s < SER; s = s + 1) begin
            if (s == 0) prev_v = last_vec;
            else        prev_v = fs[6*s - 6 +: 5];
            if (fs[6*s +: 5] != prev_v) any_change = 1'b1;
        end
    end

    wire tsel = (src == 3'd1) ? t_tx : (src == 3'd2) ? t_rxev : (src == 3'd3) ? t_trig :
                (src == 3'd4) ? any_change : (src == 3'd5) ? t_rxdec : (src == 3'd6) ? t_seq : t_reply;

    reg [W-1:0] word_d;
    reg         tsel_d;
    generate
        if (TXFB != 0) begin : g_rb
            always @(posedge clk) word_d <= {fs_tx, ctx, fs};
        end else begin : g_norb
            always @(posedge clk) word_d <= {ctx, fs};
            wire _unused_rb = &{1'b0, fs_tx};
        end
    endgenerate
    always @(posedge clk) tsel_d <= tsel;

    wire          writing = armed || (trig && !done);
    wire [AW-1:0] rd_phys = wp + rd_idx[AW-1:0];

    always @(posedge clk) begin
        if (writing) mem[wp] <= word_d;
        rd_word <= mem[rd_phys];
        rd_q    <= rd_word;
    end

    always @(posedge clk) begin
        if (rst) begin
            wp <= {AW{1'b0}}; tp <= {AW{1'b0}}; post <= 32'd1024; left <= 32'd0;
            armed <= 1'b0; trig <= 1'b0; done <= 1'b0; nvalid <= {(AW+1){1'b0}}; src <= 3'd1; force_ <= 1'b0;
            rd_idx <= 16'd0; rd_chunk <= 2'd0; last_vec <= 5'd0;
        end else begin
            force_ <= 1'b0;
            last_vec <= fs[6*(SER-1) +: 5];
            if (bus_we) begin
                case (bus_addr)
                R_CAP_CTRL: begin
                    src <= bus_wdata[6:4];
                    if (bus_wdata[0]) begin armed <= 1'b1; trig <= 1'b0; done <= 1'b0; nvalid <= {(AW+1){1'b0}}; end
                    force_ <= bus_wdata[1];
                end
                R_CAP_POST: post <= bus_wdata;
                R_CAP_ADDR: begin rd_idx <= bus_wdata[15:0]; rd_chunk <= bus_wdata[17:16]; end
                default: ;
                endcase
            end
            if (bus_re && bus_addr == R_CAP_DATA) begin
                if (NCH == 1 || rd_chunk == LASTC || &rd_chunk) begin rd_chunk <= 2'd0; rd_idx <= rd_idx + 1'b1; end
                else rd_chunk <= rd_chunk + 1'b1;
            end
            if (writing) begin
                wp <= wp + 1'b1;
                if (!filled) nvalid <= nvalid + 1'b1;
            end
            // armed and trig never stand together (arming clears trig), so these two are independent
            if (armed && (tsel_d || force_)) begin
                armed <= 1'b0; trig <= 1'b1; tp <= wp; left <= post;
                if (post == 32'd0) done <= 1'b1;
            end
            if (trig && !done) begin
                if (~|left[31:1]) done <= 1'b1;
                left <= left - 1'b1;
            end
        end
    end

    wire [AW-1:0] trig_from_oldest = tp - wp;
    wire [95:0]   rd_pad;
    generate
        if (W < 96) begin : g_pad
            assign rd_pad = {{(96 - W){1'b0}}, rd_q};
        end else begin : g_full
            assign rd_pad = rd_q;
        end
    endgenerate
    localparam TXFB1 = (TXFB != 0);

    always @* begin
        case (bus_addr)
        R_CAP_CTRL: bus_rdata = {25'd0, src, filled, done, trig, armed};
        R_CAP_POST: bus_rdata = post;
        R_CAP_ADDR: bus_rdata = {14'd0, rd_chunk, rd_idx};
        R_CAP_DATA: bus_rdata = (rd_chunk == 2'd2) ? rd_pad[95:64] : (rd_chunk == 2'd1) ? rd_pad[63:32] : rd_pad[31:0];
        R_CAP_INFO: bus_rdata = {7'd0, TXFB1, AW_W, W_W, SER_W};
        R_CAP_TRIG: bus_rdata = {{(15 - AW){1'b0}}, nvalid, {(16 - AW){1'b0}}, trig_from_oldest};
        default:    bus_rdata = 32'hDEAD_0000 | {24'd0, bus_addr};
        endcase
    end
endmodule
