// ISCAS-85 c17, rewritten as a mapped gate-level netlist (named connections).
module c17 ( N1, N2, N3, N6, N7, N22, N23 );
  input  N1, N2, N3, N6, N7;
  output N22, N23;
  wire   N10, N11, N16, N19;

  ND2D1 U1 ( .A1(N1),  .A2(N3),  .ZN(N10) );
  ND2D1 U2 ( .A1(N3),  .A2(N6),  .ZN(N11) );
  ND2D1 U3 ( .A1(N2),  .A2(N11), .ZN(N16) );
  ND2D1 U4 ( .A1(N11), .A2(N7),  .ZN(N19) );
  ND2D1 U5 ( .A1(N10), .A2(N16), .ZN(N22) );
  /* last stage */
  ND2D1 U6 ( .A1(N16), .A2(N19),
             .ZN(N23) );
endmodule
