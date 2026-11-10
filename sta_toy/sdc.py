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
    "set_propagated_clock": ((), (), ("get_clocks",), False),
}
# The facets a flag names; no flag names both.
_FACETS = {None: None, "-min": ("min",), "-max": ("max",), "-setup": ("setup",), "-hold": ("hold",)}


class Clock:
    """One create_clock and the values set on it by name (R51): transition, latency,
    uncertainty (0 until set) and `propagated` (set_propagated_clock, R50)."""

    def __init__(self, name, port, period, line):
        self.name = name
        self.port = port
        self.period = period
        self.line = line
        self.transition = 0.0
        self.latency = 0.0
        self.uncertainty = {"setup": 0.0, "hold": 0.0}
        self.propagated = False


class Sdc:
    """Constraints with facets already merged in file order. A facet never set is absent
    from its dict (input/output delays) or 0 (clock values). `clocks` maps each clock's
    name to its Clock, in create_clock order; `input_clock` / `output_clock` map a port to
    the -clock of its last delay command. `objects` lists every object named, as (line,
    command, kind, name) in file order, for the checks against the design.
    clock_name ... uncertainty are those of the first clock (P2's single clock)."""

    def __init__(self, file):
        self.file = file
        self.last_line = 1
        self.clocks = {}
        self.pin_latency = {}
        self.input_delay = {}
        self.output_delay = {}
        self.input_clock = {}
        self.output_clock = {}
        self.input_transition = {}
        self.load = {}
        self.objects = []

    def _first(self, attr, default):
        return getattr(next(iter(self.clocks.values())), attr) if self.clocks else default

    clock_name = property(lambda self: self._first("name", None))
    clock_port = property(lambda self: self._first("port", None))
    period = property(lambda self: self._first("period", None))
    clock_transition = property(lambda self: self._first("transition", 0.0))
    clock_latency = property(lambda self: self._first("latency", 0.0))
    uncertainty = property(lambda self: self._first("uncertainty", {"setup": 0.0, "hold": 0.0}))


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
        if args["-name"] in sdc.clocks:
            error("clock %s is already defined" % args["-name"])
        for other in sdc.clocks.values():
            if other.port == name:
                error("port %s already has clock %s" % (name, other.name))
    clock = name if kind == "get_clocks" else args.get("-clock")
    if clock is not None and not sdc.clocks:
        error("clock %s is not defined" % clock)

    sdc.objects.append((lineno, cmd, kind, name))
    if "-clock" in args:
        sdc.objects.append((lineno, cmd, "get_clocks", args["-clock"]))
    facets = _FACETS[flag]
    # A clock named before its create_clock is left alone here; timer.check_sdc reports it.
    target = sdc.clocks.get(name) if kind == "get_clocks" else None
    if cmd == "create_clock":
        sdc.clocks[args["-name"]] = Clock(args["-name"], name, float(args["-period"]), lineno)
    elif cmd == "set_clock_latency" and kind == "get_pins":
        sdc.pin_latency[name] = value
    elif target is None and kind == "get_clocks":
        pass
    elif cmd == "set_clock_transition":
        target.transition = value
    elif cmd == "set_clock_latency":
        target.latency = value
    elif cmd == "set_clock_uncertainty":
        for facet in facets or ("setup", "hold"):
            target.uncertainty[facet] = value
    elif cmd == "set_propagated_clock":
        target.propagated = True
    elif cmd in ("set_input_delay", "set_output_delay"):
        delays = sdc.input_delay if cmd == "set_input_delay" else sdc.output_delay
        for facet in facets or ("min", "max"):
            delays.setdefault(name, {})[facet] = value
        (sdc.input_clock if cmd == "set_input_delay" else sdc.output_clock)[name] = args["-clock"]
    elif cmd == "set_input_transition":
        sdc.input_transition[name] = value
    else:
        sdc.load[name] = value
