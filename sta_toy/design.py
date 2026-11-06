"""Loading a design, shared by the CLI and the viewer: libraries, netlist, stage 1 link,
then (with an SDC file) the P2 timing run. Errors keep the order of p2_semantics.md §10."""

from sta_toy import graph, liberty, sdc, timer, verilog


def load(lib_paths, verilog_path):
    """(library, netlist, linked stage 1 graph). Repeated libraries: first cell wins."""
    libs = [liberty.load(path) for path in lib_paths]
    lib = libs[0]
    for other in libs[1:]:
        for name, cell in other.cells.items():
            lib.cells.setdefault(name, cell)
    netlist = verilog.load(verilog_path)
    return lib, netlist, graph.link(netlist, lib)


def timed(lib, netlist, linked, sdc_path, grid=None, log=None):
    """The timed P2 graph; g.sdc, g.lib and g.netlist are attached. `grid`, `log`: timer.run."""
    g = timer.run(linked, netlist, lib, sdc.load(sdc_path), grid=grid, log=log)
    g.lib, g.netlist = lib, netlist
    return g
