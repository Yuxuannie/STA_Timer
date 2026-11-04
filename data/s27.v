// s27 - ISCAS-89 benchmark, connectivity from the public .bench description,
// rewritten as a mapped netlist on toy2.lib.  Instance names keep the
// benchmark's net numbers (U8 drives G8, FF5 drives G5, ...).
module s27 (clk, G0, G1, G2, G3, G17);
  input clk;
  input G0;
  input G1;
  input G2;
  input G3;
  output G17;
  wire G5;
  wire G6;
  wire G7;
  wire G8;
  wire G9;
  wire G10;
  wire G11;
  wire G12;
  wire G13;
  wire G14;
  wire G15;
  wire G16;
  DFF   FF5 (.CK(clk), .D(G10), .Q(G5));
  DFF   FF6 (.CK(clk), .D(G11), .Q(G6));
  DFF   FF7 (.CK(clk), .D(G13), .Q(G7));
  INV   U14 (.A(G0),   .Y(G14));
  INV   U17 (.A(G11),  .Y(G17));
  AND2  U8  (.A(G14),  .B(G6),  .Y(G8));
  OR2   U15 (.A(G12),  .B(G8),  .Y(G15));
  OR2   U16 (.A(G3),   .B(G8),  .Y(G16));
  NAND2 U9  (.A(G16),  .B(G15), .Y(G9));
  NOR2  U10 (.A(G14),  .B(G11), .Y(G10));
  NOR2  U11 (.A(G5),   .B(G9),  .Y(G11));
  NOR2  U12 (.A(G1),   .B(G7),  .Y(G12));
  NOR2  U13 (.A(G2),   .B(G12), .Y(G13));
endmodule
