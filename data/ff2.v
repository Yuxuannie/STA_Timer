// ff2 - the two-camera example from the setup/hold walkthrough.
// x -> U1 (BUF) -> U2/B ; FF1/Q -> U2/A ; U2 (NAND2) -> FF2/D ; FF2/Q -> y and FF1/D.
// Flat, named port connections, scalar nets.
module ff2 (clk, x, y);
  input clk;
  input x;
  output y;
  wire n1;
  wire n2;
  wire q1;
  BUF   U1  (.A(x),    .Y(n1));
  NAND2 U2  (.A(q1),   .B(n1), .Y(n2));
  DFF   FF1 (.CK(clk), .D(y),  .Q(q1));
  DFF   FF2 (.CK(clk), .D(n2), .Q(y));
endmodule
