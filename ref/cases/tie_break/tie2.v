// R40 smallest case: two equal-delay routes into one NAND2.
module tie2 (clk, a, b, y);
  input clk;
  input a;
  input b;
  output y;
  wire n;
  NAND2 U1  (.A(a), .B(b), .Y(n));
  DFF   FF1 (.CK(clk), .D(n), .Q(y));
endmodule
