"""SDC subset (sdc_subset.md), parsed line by line into a plain constraint object (R13).

Only the syntactic errors are raised here; the checks against the design are in
timer.check_sdc."""

import re

from sta_toy import P2Error, read_file

_NUMBER = re.compile(r"-?[0-9]+(\.[0-9]+)?$")

# command -> (options taking an argument, flags, object-list kinds, takes a value)
_COMMANDS = {
    "create_clock": (("-name", "-period"), (), ("get_ports",), False),
    "set_clock_transition": ((), (), ("get_clocks",), True),
    "set_clock_latency": ((), (), ("get_clocks", "get_pins"), True),
    "set_clock_uncertainty": ((), ("-setup", "-hold"), ("get_clocks",), True),
    "set_input_delay": (("-clock",), ("-min", "-max"), ("get_ports",), True),
    "set_output_delay": (("-clock",), ("-min", "-max"), ("get_ports",), True),
    "set_input_transition": ((), (), ("get_ports",), True),
    "set_load": ((), (), ("get_ports",), True),
}
# The facets a flag names; no flag names both.
_FACETS = {None: None, "-min": ("min",), "-max": ("max",), "-setup": ("setup",), "-hold": ("hold",)}


class Sdc:
    """Constraints with facets already merged in file order. A facet never set is absent
    from its dict (input/output delays) or 0 (clock values). `objects` lists every object
    named, as (line, command, kind, name) in file order, for the checks against the design."""

    def __init__(self, file):
        self.file = file
        self.last_line = 1
        self.clock_name = None
        self.clock_port = None
        self.period = None
        self.clock_transition = 0.0
        self.clock_latency = 0.0
        self.pin_latency = {}
        self.uncertainty = {"setup": 0.0, "hold": 0.0}
        self.input_delay = {}
        self.output_delay = {}
        self.input_transition = {}
        self.load = {}
        self.objects = []


def load(path):
    return parse(read_file(path), path)


def parse(text, filename):
    sdc = Sdc(filename)
    lines = text.split("\n")
    sdc.last_line = len(text.splitlines()) or 1
    for lineno, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if line:
            _command(sdc, lineno, line)
    return sdc


def _object_list(rest, kinds, error):
    """`rest` is the text after '['; return (kind, name)."""
    if not rest.endswith("]") or "[" in rest or rest.count("]") != 1:
        error("malformed object list [%s" % rest)
    parts = rest[:-1].split()
    if not parts or parts[0] not in kinds:
        error("malformed object list [%s: expected %s" % (rest, " or ".join("[%s NAME]" % k for k in kinds)))
    if len(parts) != 2:
        error("object list [%s must name exactly one object" % rest)
    if any(c in parts[1] for c in "*?{}"):
        error("object list [%s must name one literal object, without wildcards or braces" % rest)
    return parts[0], parts[1]


def _command(sdc, lineno, line):
    def error(message):
        raise P2Error(sdc.file, lineno, message)

    head, bracket, rest = line.partition("[")
    tokens = head.split()
    if not tokens or tokens[0] not in _COMMANDS:
        error("unknown command %s" % (tokens[0] if tokens else "[" + rest))
    cmd = tokens[0]
    options, flags, kinds, takes_value = _COMMANDS[cmd]
    args, flag, value = {}, None, None
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if _NUMBER.match(tok):
            if not takes_value or value is not None:
                error("unexpected value %s" % tok)
            value = float(tok)
        elif tok in flags:
            if flag is not None:
                error("%s and %s cannot be given together" % (flag, tok))
            flag = tok
        elif tok in options:
            if tok in args:
                error("option %s given twice" % tok)
            if i == len(tokens) or (tokens[i].startswith("-") and not _NUMBER.match(tokens[i])):
                error("missing value for %s" % tok)
            args[tok] = tokens[i]
            i += 1
        elif tok.startswith("-"):
            error("unknown option %s for %s" % (tok, cmd))
        else:
            error("unexpected token %s" % tok)
    if not bracket:
        error("missing object list")
    kind, name = _object_list(rest.strip(), kinds, error)
    if takes_value and value is None:
        error("missing value for %s" % cmd)
    for option in options:
        if option not in args:
            error("%s missing on %s" % (option, cmd))
    if cmd == "create_clock":
        if not _NUMBER.match(args["-period"]):
            error("missing value for -period")
        if sdc.clock_name is not None:
            error("second create_clock (clock %s is already defined)" % sdc.clock_name)
    clock = name if kind == "get_clocks" else args.get("-clock")
    if clock is not None and sdc.clock_name is None:
        error("clock %s is not defined" % clock)

    sdc.objects.append((lineno, cmd, kind, name))
    if "-clock" in args:
        sdc.objects.append((lineno, cmd, "get_clocks", args["-clock"]))
    facets = _FACETS[flag]
    if cmd == "create_clock":
        sdc.clock_name, sdc.clock_port, sdc.period = args["-name"], name, float(args["-period"])
    elif cmd == "set_clock_transition":
        sdc.clock_transition = value
    elif cmd == "set_clock_latency" and kind == "get_pins":
        sdc.pin_latency[name] = value
    elif cmd == "set_clock_latency":
        sdc.clock_latency = value
    elif cmd == "set_clock_uncertainty":
        for facet in facets or ("setup", "hold"):
            sdc.uncertainty[facet] = value
    elif cmd in ("set_input_delay", "set_output_delay"):
        delays = sdc.input_delay if cmd == "set_input_delay" else sdc.output_delay
        for facet in facets or ("min", "max"):
            delays.setdefault(name, {})[facet] = value
    elif cmd == "set_input_transition":
        sdc.input_transition[name] = value
    else:
        sdc.load[name] = value
