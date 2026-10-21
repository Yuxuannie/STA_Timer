# Toy STA, stage 1

Parses a Liberty library and a flat gate-level Verilog netlist, links them into a
pin-level timing graph and prints it as text. Python 3.8+, standard library only.

    python -m sta_toy --lib data/toy.lib --verilog data/c17.v
    python -m unittest discover -s tests

Run both from the repo root. Errors go to stderr as `ERROR <file>:<line>: <message>`, exit code 1.
