// R40 smallest case: one register between an input and an output port.
module reg1 (clk, d, q);
  input clk;
  input d;
  output q;
  wire q1;
  DFF FF1 (.CK(clk), .D(d), .Q(q1));
  BUF U1  (.A(q1), .Y(q));
endmodule
