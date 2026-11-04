"""Viewer data sources without Tk (R28, viewer_p4.md "Start"): the in-process engine, or
one saved bundle (bundle_v1.md)."""

import json

from sta_toy import P2Error, design
from sta_toy.viewer.model import EndpointTable

SCHEMA = "sta_toy.bundle/1"


class EngineSource:
    """Runs the engine once; bundles are built per endpoint on demand."""

    mode = "engine"

    def __init__(self, lib_paths, verilog_path, sdc_path):
        lib, netlist, linked = design.load(lib_paths, verilog_path)
        self.g = design.timed(lib, netlist, linked, sdc_path)
        self.clock_name = self.g.sdc.clock_name

    def rows(self):
        return EndpointTable.from_graph(self.g).rows

    def bundle(self, endpoint, depth=3, max_nodes=300):
        from sta_toy import bundle
        return bundle.debug_bundle(self.g, endpoint, depth, max_nodes)


class BundleSource:
    """One saved bundle; only its endpoint is listed and it is returned as saved."""

    mode = "bundle"

    def __init__(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError) as e:
            raise P2Error(None, None, "cannot read %s: %s" % (path, getattr(e, "strerror", None) or e))
        try:
            data = json.loads(text)
        except ValueError:
            raise P2Error(None, None, "%s is not JSON" % path)
        if not isinstance(data, dict) or data.get("schema") != SCHEMA:
            raise P2Error(None, None, "%s is not a %s bundle" % (path, SCHEMA))
        self.data = data
        self.clock_name = data["clock"]["name"]

    def rows(self):
        return EndpointTable.from_bundle(self.data).rows

    def bundle(self, endpoint, depth=3, max_nodes=300):
        return self.data
