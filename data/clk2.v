// clk2 - two clock domains (clk_a, clk_b) with 2- and 3-stage BUF clock trees (R50, R51):
// same-domain, cross-domain (a->b, b->a), port-to-reg and reg-to-port paths, outputs
// assigned from internal nets (R48). Shaped like a real generated netlist.
module clk2 ( clk_a, clk_b, din0, din1, dout0, dout1 );
  input clk_a, clk_b;
  input din0, din1;
  output dout0, dout1;
  assign dout0 = w20;
  assign dout1 = w21;
  BUF ca1 ( .A(clk_a), .Y(a1) );
  BUF ca2 ( .A(a1), .Y(a2) );
  BUF ca3 ( .A(a2), .Y(a3) );
  BUF cb1 ( .A(clk_b), .Y(b1) );
  BUF cb2 ( .A(b1), .Y(b2) );
  BUF cb3 ( .A(b2), .Y(b3) );
  DFF ra1 ( .CK(a3), .D(din0), .Q(q1) );
  NAND2 u1 ( .A(q1), .B(din1), .Y(w1) );
  DFF ra2 ( .CK(a3), .D(w1), .Q(q2) );
  INV u2 ( .A(q2), .Y(w2) );
  DFF rb1 ( .CK(b3), .D(w2), .Q(q3) );
  AND2 u3 ( .A(q3), .B(q1), .Y(w3) );
  DFF rb2 ( .CK(b2), .D(w3), .Q(q4) );
  OR2 u4 ( .A(q4), .B(q2), .Y(w4) );
  DFF ra3 ( .CK(a2), .D(w4), .Q(q5) );
  BUF u5 ( .A(q5), .Y(w20) );
  NOR2 u6 ( .A(q4), .B(q5), .Y(w21) );
endmodule
