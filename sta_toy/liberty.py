"""Liberty: a generic parser into a tree of groups and attributes (R1),
and the accessors that answer the stage-1 queries on that tree (R2)."""

from sta_toy import StaError, read_file

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
    p = _Parser(_tokenize(text, filename), filename)
    holder = Group("", [], 0)
    first = p.peek()
    p.statement(holder)
    if not holder.groups:
        p.error(first, "expected a top-level group")
    if p.peek()[0] != "eof":
        p.error(p.peek(), "unexpected %s after the top-level group" % _show(p.peek()))
    return holder.groups[0]


def _continuation_end(text, i):
    """If text[i] is a backslash ending its line, return the index after the newline."""
    j = i + 1
    while j < len(text) and text[j] in " \t\r":
        j += 1
    if j < len(text) and text[j] == "\n":
        return j + 1
    return None


def _tokenize(text, filename):
    """Return (kind, value, line) tuples; kind is a punctuation char, 'str', 'word' or 'eof'."""
    tokens = []
    i, line, n = 0, 1, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif c == "\\":
            j = _continuation_end(text, i)
            if j is None:
                raise StaError(filename, line, "unexpected '\\'")
            line += 1
            i = j
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise StaError(filename, line, "unterminated comment")
            line += text.count("\n", i, end)
            i = end + 2
        elif c == '"':
            start = line
            chars = []
            i += 1
            while True:
                if i >= n:
                    raise StaError(filename, start, "unterminated string")
                c = text[i]
                if c == '"':
                    i += 1
                    break
                if c == "\\":
                    j = _continuation_end(text, i)
                    if j is not None:
                        line += 1
                        i = j
                        continue
                if c == "\n":
                    line += 1
                chars.append(c)
                i += 1
            tokens.append(("str", "".join(chars), start))
        elif c in _PUNCT:
            tokens.append((c, c, line))
            i += 1
        else:
            j = i
            while (j < n and not text[j].isspace() and text[j] not in _PUNCT + '"\\'
                   and not text.startswith("/*", j)):
                j += 1
            tokens.append(("word", text[i:j], line))
            i = j
    tokens.append(("eof", "", line))
    return tokens


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

NLDM_TABLES = ("cell_rise", "cell_fall", "rise_transition", "fall_transition")


class Table:
    """An NLDM table: index_1/index_2 are lists of float ([] when absent), values a list of rows."""

    def __init__(self, template, index_1, index_2, values, line):
        self.template = template
        self.index_1 = index_1
        self.index_2 = index_2
        self.values = values
        self.line = line


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
                 timings, line):
        self.name = name
        self.direction = direction
        self.capacitance = capacitance
        self.rise_capacitance = rise_capacitance
        self.fall_capacitance = fall_capacitance
        self.timings = timings
        self.line = line


class Cell:
    def __init__(self, name, pins, line):
        self.name = name
        self.pins = pins
        self.line = line

    def pin(self, name):
        for p in self.pins:
            if p.name == name:
                return p
        return None


class Library:
    def __init__(self, name, cap_unit, cells):
        self.name = name
        self.cap_unit = cap_unit
        self.cells = cells


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
        if unit is None or len(unit.values) != 2:
            self.error(unit or root, "library %s: capacitive_load_unit must be (<value>, <unit>)"
                       % name)
        cap_unit = (self.numbers(unit, unit.values[0], "library " + name)[0], unit.values[1])
        templates = {}
        for g in root.find_groups("lu_table_template"):
            tname = self.names(g)[0]
            ctx = "lu_table_template " + tname
            templates[tname] = (self.index(g, "index_1", ctx, None),
                                self.index(g, "index_2", ctx, None))
        cells = {}
        for g in root.find_groups("cell"):
            cell = self.cell(g, templates)
            cells[cell.name] = cell
        return Library(name, cap_unit, cells)

    def cell(self, group, templates):
        name = self.names(group)[0]
        pin_names = [n for g in group.find_groups("pin") for n in self.names(g)]
        pins = [self.pin(g, pin_name, "cell %s pin %s" % (name, pin_name), templates, pin_names)
                for g in group.find_groups("pin") for pin_name in g.names]
        return Cell(name, pins, group.line)

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
        return Pin(name, direction, caps[0], caps[1], caps[2], timings, group.line)

    def timing(self, group, ctx, templates, pin_names):
        attr = self.first(group, "related_pin")
        related = " ".join(attr.values).split() if attr else []
        for name in related:
            if name not in pin_names:
                self.error(attr, "%s: related_pin %s is not a pin of the cell" % (ctx, name))
        tables = {}
        for g in group.groups:
            if g.header in NLDM_TABLES:
                tables[g.header] = self.table(g, "%s %s" % (ctx, g.header), templates)
        return Timing(related, self.text(group, "timing_sense", None),
                      self.text(group, "timing_type", "combinational"),
                      self.text(group, "when", ""), tables, group.line)

    def table(self, group, ctx, templates):
        template = group.names[0] if group.names else ""
        if template == "scalar":
            index_1 = index_2 = None
        elif template in templates:
            index_1, index_2 = templates[template]
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
        return Table(template, index_1 or [], index_2 or [], rows, group.line)
