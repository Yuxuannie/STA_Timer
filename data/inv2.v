// inv2 - two inverters in series (appendix A of the walkthrough: rise/fall split).
// a -> U1 (INV) -> U2 (INV) -> FF1/D ; FF1/Q -> U3 (BUF) -> y.
// U3 is a BUF with load-dependent tables so that set_load on y is observable.
module inv2 (clk, a, y);
  input clk;
  input a;
  output y;
  wire y1;
  wire y2;
  wire q;
  INV U1  (.A(a),    .Y(y1));
  INV U2  (.A(y1),   .Y(y2));
  DFF FF1 (.CK(clk), .D(y2), .Q(q));
  BUF U3  (.A(q),    .Y(y));
endmodule
