"""Liberty: a generic parser into a tree of groups and attributes (R1),
and the accessors that answer the stage-1 queries on that tree (R2)."""

import re
from fractions import Fraction

from sta_toy import P2Error, StaError, read_file

_PUNCT = "(){}:;,"


class Attr:
    """`name : value ;` or `name ( v1, v2, ... ) ;`. Values are strings, quotes removed."""

    def __init__(self, name, values, line):
        self.name = name
        self.values = values
        self.line = line


class Group:
    """`header ( names ) { ... }` with its attributes and child groups, each in file order."""

    def __init__(self, header, names, line):
        self.header = header
        self.names = names
        self.line = line
        self.attrs = []
        self.groups = []

    def find_attrs(self, name):
        return [a for a in self.attrs if a.name == name]

    def find_groups(self, header):
        return [g for g in self.groups if g.header == header]


def parse_file(path):
    return parse(read_file(path), path)


def parse(text, filename):
    """Parse Liberty text into its single top-level group."""
    p = _Parser(list(_tokenize(text, filename)), filename)
    holder = Group("", [], 0)
    first = p.peek()
    p.statement(holder)
    if not holder.groups:
        p.error(first, "expected a top-level group")
    if p.peek()[0] != "eof":
        p.error(p.peek(), "unexpected %s after the top-level group" % _show(p.peek()))
    return holder.groups[0]


_TOKEN = re.compile(r'(?P<ws>\s+)|(?P<word>(?:[^\s(){}:;,"\\/]|/(?!\*))+)|(?P<punct>[(){}:;,])'
                    r'|(?P<cmt>/\*)|(?P<str>")|(?P<bs>\\)')
_CONT = re.compile(r"\\[ \t\r]*\n")


def _tokenize(text, filename):
    """Yield (kind, value, line) tuples; kind is a punctuation char, 'str', 'word' or 'eof'.
    One regex match per token (R42); the output, errors included, is that of the character
    loop it replaced (kept as tests/test_tokenizer.py `_tokenize_reference`)."""
    i, line, n = 0, 1, len(text)
    match = _TOKEN.match
    while i < n:
        m = match(text, i)
        kind = m.lastgroup
        if kind == "ws":
            line += m.group().count("\n")
        elif kind == "word":
            yield ("word", m.group(), line)
        elif kind == "punct":
            yield (m.group(), m.group(), line)
        elif kind == "cmt":
            end = text.find("*/", i + 2)
            if end < 0:
                raise StaError(filename, line, "unterminated comment")
            line += text.count("\n", i, end)
            i = end + 2
            continue
        elif kind == "str":
            end = text.find('"', i + 1)
            if end < 0:
                raise StaError(filename, line, "unterminated string")
            body = text[i + 1:end]
            yield ("str", _CONT.sub("", body), line)       # a backslash-newline inside is dropped
            line += body.count("\n")
            i = end + 1
            continue
        else:
            c = _CONT.match(text, i)
            if c is None:
                raise StaError(filename, line, "unexpected '\\'")
            line += 1
            i = c.end()
            continue
        i = m.end()
    yield ("eof", "", line)


def _show(tok):
    if tok[0] == "eof":
        return "end of file"
    if tok[0] == "str":
        return '"%s"' % tok[1]
    return "'%s'" % tok[1]


def _describe(group):
    return "%s (%s)" % (group.header, ", ".join(group.names))


class _Parser:
    def __init__(self, tokens, filename):
        self.tokens = tokens
        self.pos = 0
        self.filename = filename
        self.open_groups = []

    def error(self, tok, message):
        # Running out of input inside a group is reported at that group's header.
        if tok[0] == "eof" and self.open_groups:
            group = self.open_groups[-1]
            raise StaError(self.filename, group.line, "unclosed group %s" % _describe(group))
        raise StaError(self.filename, tok[2], message)

    def peek(self):
        return self.tokens[self.pos]

    def next(self):
        tok = self.tokens[self.pos]
        if tok[0] != "eof":
            self.pos += 1
        return tok

    def expect(self, kind):
        tok = self.next()
        if tok[0] != kind:
            self.error(tok, "expected '%s', found %s" % (kind, _show(tok)))
        return tok

    def value(self):
        tok = self.next()
        if tok[0] not in ("word", "str"):
            self.error(tok, "expected a value, found %s" % _show(tok))
        return tok[1]

    def value_list(self):
        """Comma-separated values up to and including the closing ')'."""
        values = []
        if self.peek()[0] == ")":
            self.next()
            return values
        while True:
            values.append(self.value())
            tok = self.next()
            if tok[0] == ")":
                return values
            if tok[0] != ",":
                self.error(tok, "expected ',' or ')', found %s" % _show(tok))

    def statement(self, parent):
        name = self.next()
        if name[0] != "word":
            self.error(name, "expected a name, found %s" % _show(name))
        tok = self.next()
        if tok[0] == ":":
            value = self.value()
            self.expect(";")
            parent.attrs.append(Attr(name[1], [value], name[2]))
        elif tok[0] == "(":
            values = self.value_list()
            tok = self.next()
            if tok[0] == "{":
                group = Group(name[1], values, name[2])
                self.body(group)
                parent.groups.append(group)
            elif tok[0] == ";":
                parent.attrs.append(Attr(name[1], values, name[2]))
            else:
                self.error(tok, "expected '{' or ';' after %s (...), found %s"
                           % (name[1], _show(tok)))
        else:
            self.error(tok, "expected ':' or '(' after %s, found %s" % (name[1], _show(tok)))

    def body(self, group):
        self.open_groups.append(group)
        while self.peek()[0] != "}":
            self.statement(group)
        self.next()
        self.open_groups.pop()


# ---------------------------------------------------------------------------
# R2: accessors. Everything is built and validated when the library is loaded.

# Delay and transition tables (stage 1), plus the setup/hold constraint tables (R10).
TABLE_KINDS = ("cell_rise", "cell_fall", "rise_transition", "fall_transition",
               "rise_constraint", "fall_constraint")


class Table:
    """A lookup table: index_1/index_2 are lists of float ([] when absent), values a list of rows.
    `variables` names what index_1 and index_2 stand for, from the template's
    variable_1/variable_2 (() for `scalar`)."""

    def __init__(self, template, index_1, index_2, values, line, variables):
        self.template = template
        self.index_1 = index_1
        self.index_2 = index_2
        self.values = values
        self.line = line
        self.variables = variables


class Timing:
    """One timing () group: arcs from each related pin to the owner pin."""

    def __init__(self, related_pins, timing_sense, timing_type, when, tables, line):
        self.related_pins = related_pins
        self.timing_sense = timing_sense
        self.timing_type = timing_type
        self.when = when
        self.tables = tables
        self.line = line


class Pin:
    def __init__(self, name, direction, capacitance, rise_capacitance, fall_capacitance,
                 timings, line, is_clock, function=None):
        self.name = name
        self.direction = direction
        self.capacitance = capacitance
        self.rise_capacitance = rise_capacitance
        self.fall_capacitance = fall_capacitance
        self.timings = timings
        self.line = line
        self.is_clock = is_clock
        self.function = function


class Cell:
    """`sequential` is true for a cell with an `ff` or `latch` group."""

    def __init__(self, name, pins, line, file, sequential=False):
        self.name = name
        self.pins = pins
        self.line = line
        self.file = file
        self.sequential = sequential

    def pin(self, name):
        for p in self.pins:
            if p.name == name:
                return p
        return None


class Library:
    """`time_unit` is the attribute's text ("1ns"), `cap_unit` (value, unit) or None when
    the library does not declare it (R37: an error at design load, not here)."""

    def __init__(self, name, cap_unit, cells, time_unit=None):
        self.name = name
        self.cap_unit = cap_unit
        self.cells = cells
        self.time_unit = time_unit


# R37 (cli_p5.md "Library units"): unit names as exact powers of ten (of s and F).
TIME_UNITS = {"fs": -15, "ps": -12, "ns": -9, "us": -6, "ms": -3, "s": 0}
CAP_UNITS = {"ff": -15, "pf": -12, "nf": -9, "uf": -6, "mf": -3, "f": 0}


def units(lib, path):
    """(time unit in s, cap unit in F) as exact Fractions; a missing or unknown unit is
    the P2Error of cli_p5.md."""

    def error(message):
        raise P2Error(path, None, "library %s: %s" % (lib.name, message))

    if lib.time_unit is None:
        error("missing time_unit")
    if lib.cap_unit is None:
        error("missing capacitive_load_unit")
    m = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]+)\s*$", lib.time_unit)
    if not m or m.group(2).lower() not in TIME_UNITS:
        error("unknown time_unit %s" % lib.time_unit)
    time = Fraction(m.group(1)) * Fraction(10) ** TIME_UNITS[m.group(2).lower()]
    value, unit = lib.cap_unit
    if unit.lower() not in CAP_UNITS:
        error("unknown capacitive_load_unit %s" % unit)
    return time, Fraction(repr(value)) * Fraction(10) ** CAP_UNITS[unit.lower()]


def _scaled(values, factor):
    return [v * factor.numerator / factor.denominator for v in values]


def convert(lib, time_factor, cap_factor):
    """Scale the built cells of `lib` in place: times by time_factor, capacitances by
    cap_factor (cli_p5.md). The generic tree is not touched; shared template index lists
    are replaced, never modified."""
    for cell in lib.cells.values():
        for pin in cell.pins:
            for name in ("capacitance", "rise_capacitance", "fall_capacitance"):
                if getattr(pin, name) is not None:
                    setattr(pin, name, _scaled([getattr(pin, name)], cap_factor)[0])
            for timing in pin.timings:
                for table in timing.tables.values():
                    table.values = [_scaled(row, time_factor) for row in table.values]
                    for k, var in enumerate(table.variables):
                        attr = "index_%d" % (k + 1)
                        if var.endswith("_transition"):
                            setattr(table, attr, _scaled(getattr(table, attr), time_factor))
                        elif var.endswith("_capacitance"):
                            setattr(table, attr, _scaled(getattr(table, attr), cap_factor))


def load(path):
    return loads(read_file(path), path)


def loads(text, filename):
    return _Builder(filename).library(parse(text, filename))


class _Builder:
    def __init__(self, filename):
        self.filename = filename

    def error(self, node, message):
        raise StaError(self.filename, node.line, message)

    def first(self, group, name):
        attrs = group.find_attrs(name)
        return attrs[0] if attrs else None

    def text(self, group, name, default):
        attr = self.first(group, name)
        return attr.values[0] if attr and attr.values else default

    def names(self, group):
        if not group.names:
            self.error(group, "%s group has no name" % group.header)
        return group.names

    def numbers(self, attr, text, ctx):
        try:
            return [float(x) for x in text.split(",")]
        except ValueError:
            self.error(attr, "%s: %s is not a list of numbers: \"%s\"" % (ctx, attr.name, text))

    def number(self, attr, ctx):
        numbers = self.numbers(attr, ",".join(attr.values), ctx)
        if len(numbers) != 1:
            self.error(attr, "%s: %s needs one number" % (ctx, attr.name))
        return numbers[0]

    def index(self, group, name, ctx, default):
        attr = self.first(group, name)
        if attr is None:
            return default
        return [x for v in attr.values for x in self.numbers(attr, v, ctx)]

    def library(self, root):
        name = self.names(root)[0]
        unit = self.first(root, "capacitive_load_unit")
        cap_unit = None
        if unit is not None:
            if len(unit.values) != 2:
                self.error(unit, "library %s: capacitive_load_unit must be (<value>, <unit>)"
                           % name)
            cap_unit = (self.numbers(unit, unit.values[0], "library " + name)[0], unit.values[1])
        templates = {}
        for g in root.find_groups("lu_table_template"):
            tname = self.names(g)[0]
            ctx = "lu_table_template " + tname
            variables = tuple(a.values[0] for n in ("variable_1", "variable_2")
                              for a in g.find_attrs(n)[:1])
            templates[tname] = (self.index(g, "index_1", ctx, None),
                                self.index(g, "index_2", ctx, None), variables)
        cells = {}
        for g in root.find_groups("cell"):
            cell = self.cell(g, templates)
            cells[cell.name] = cell
        return Library(name, cap_unit, cells, self.text(root, "time_unit", None))

    def cell(self, group, templates):
        name = self.names(group)[0]
        pin_names = [n for g in group.find_groups("pin") for n in self.names(g)]
        pins = [self.pin(g, pin_name, "cell %s pin %s" % (name, pin_name), templates, pin_names)
                for g in group.find_groups("pin") for pin_name in g.names]
        sequential = bool(group.find_groups("ff") or group.find_groups("latch"))
        return Cell(name, pins, group.line, self.filename, sequential)

    def pin(self, group, name, ctx, templates, pin_names):
        attr = self.first(group, "direction")
        if attr is None:
            self.error(group, "%s: missing direction" % ctx)
        direction = " ".join(attr.values)
        if direction not in ("input", "output"):
            self.error(attr, "%s: direction must be input or output, not %s" % (ctx, direction))
        caps = []
        for cap_name in ("capacitance", "rise_capacitance", "fall_capacitance"):
            attr = self.first(group, cap_name)
            caps.append(None if attr is None else self.number(attr, ctx))
        if direction == "input" and caps[0] is None:
            self.error(group, "%s: input pin has no capacitance" % ctx)
        timings = [self.timing(g, ctx, templates, pin_names) for g in group.find_groups("timing")]
        is_clock = self.text(group, "clock", "false") == "true"
        return Pin(name, direction, caps[0], caps[1], caps[2], timings, group.line, is_clock,
                   self.text(group, "function", None))

    def timing(self, group, ctx, templates, pin_names):
        attr = self.first(group, "related_pin")
        related = " ".join(attr.values).split() if attr else []
        for name in related:
            if name not in pin_names:
                self.error(attr, "%s: related_pin %s is not a pin of the cell" % (ctx, name))
        tables = {}
        for g in group.groups:
            if g.header in TABLE_KINDS:
                tables[g.header] = self.table(g, "%s %s" % (ctx, g.header), templates)
        return Timing(related, self.text(group, "timing_sense", None),
                      self.text(group, "timing_type", "combinational"),
                      self.text(group, "when", ""), tables, group.line)

    def table(self, group, ctx, templates):
        template = group.names[0] if group.names else ""
        if template == "scalar":
            index_1 = index_2 = None
            variables = ()
        elif template in templates:
            index_1, index_2, variables = templates[template]
        else:
            self.error(group, "%s: unknown template '%s'" % (ctx, template))
        index_1 = self.index(group, "index_1", ctx, index_1)
        index_2 = self.index(group, "index_2", ctx, index_2)
        attr = self.first(group, "values")
        if attr is None:
            self.error(group, "%s: missing values" % ctx)
        rows = [self.numbers(attr, v, ctx) for v in attr.values]
        if index_1 is None:
            expected = None if index_2 is not None else [1]
        elif index_2 is None:
            expected = [len(index_1)]
        else:
            expected = [len(index_2)] * len(index_1)
        if [len(r) for r in rows] != expected:
            self.error(attr, "%s: values shape %s does not match the indices (expected %s)"
                       % (ctx, [len(r) for r in rows], expected))
        return Table(template, index_1 or [], index_2 or [], rows, group.line, variables)
