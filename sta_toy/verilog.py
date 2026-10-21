"""Gate-level Verilog: one flat module with scalar nets and named connections (R3)."""

import re

from sta_toy import StaError, read_file

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_PUNCT = "(),;."
_KEYWORDS = ("module", "endmodule", "input", "output", "wire")


class Conn:
    """`.PIN(NET)`; `line` is the line of its `.PIN(`."""

    def __init__(self, pin, net, line):
        self.pin = pin
        self.net = net
        self.line = line


class Instance:
    """`CELL NAME ( ... );`; `line` is the line of the cell name."""

    def __init__(self, cell, name, line, conns):
        self.cell = cell
        self.name = name
        self.line = line
        self.conns = conns


class Netlist:
    """Ports in header order, declarations in file order; decl_lines maps a net to its first declaration line."""

    def __init__(self, file, name, ports):
        self.file = file
        self.name = name
        self.ports = ports
        self.inputs = []
        self.outputs = []
        self.wires = []
        self.decl_lines = {}
        self.instances = []


def load(path):
    return parse(read_file(path), path)


def parse(text, filename):
    return _Parser(_tokenize(text, filename), filename).module()


def _tokenize(text, filename):
    """Return (kind, value, line) tuples; kind is 'id', a punctuation char or 'eof'."""
    tokens = []
    i, line, n = 0, 1, len(text)
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c.isspace():
            i += 1
        elif text.startswith("//", i):
            end = text.find("\n", i)
            i = n if end < 0 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise StaError(filename, line, "unterminated comment")
            line += text.count("\n", i, end)
            i = end + 2
        elif c in _PUNCT:
            tokens.append((c, c, line))
            i += 1
        else:
            m = _IDENT.match(text, i)
            if not m:
                raise StaError(filename, line, "unexpected character '%s'" % c)
            tokens.append(("id", m.group(), line))
            i = m.end()
    tokens.append(("eof", "", line))
    return tokens


def _show(tok):
    return "end of file" if tok[0] == "eof" else "'%s'" % tok[1]


class _Parser:
    def __init__(self, tokens, filename):
        self.tokens = tokens
        self.pos = 0
        self.filename = filename
        self.kinds = {}  # net -> list of declaration kinds

    def error(self, tok, message):
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

    def keyword(self, word):
        tok = self.next()
        if tok[:2] != ("id", word):
            self.error(tok, "expected '%s', found %s" % (word, _show(tok)))

    def ident(self):
        tok = self.next()
        if tok[0] != "id" or tok[1] in _KEYWORDS:
            self.error(tok, "expected an identifier, found %s" % _show(tok))
        return tok

    def module(self):
        self.keyword("module")
        name = self.ident()[1]
        self.expect("(")
        port_toks = []
        if self.peek()[0] != ")":
            port_toks.append(self.ident())
            while self.peek()[0] == ",":
                self.next()
                port_toks.append(self.ident())
        self.expect(")")
        self.expect(";")
        net = Netlist(self.filename, name, [t[1] for t in port_toks])
        while self.peek()[:2] != ("id", "endmodule"):
            if self.peek()[0] == "id" and self.peek()[1] in ("input", "output", "wire"):
                self.declaration(net)
            else:
                self.instance(net)
        self.next()
        if self.peek()[0] != "eof":
            self.error(self.peek(), "unexpected %s after endmodule" % _show(self.peek()))
        for tok in port_toks:
            if tok[1] not in net.inputs and tok[1] not in net.outputs:
                self.error(tok, "port %s has no input/output declaration" % tok[1])
        return net

    def declaration(self, net):
        kind = self.next()[1]
        while True:
            tok = self.ident()
            self.declare(net, kind, tok)
            sep = self.next()
            if sep[0] == ";":
                return
            if sep[0] != ",":
                self.error(sep, "expected ',' or ';', found %s" % _show(sep))

    def declare(self, net, kind, tok):
        name = tok[1]
        prev = self.kinds.setdefault(name, [])
        allowed = {"input": [], "output": ["wire"], "wire": ["output"]}[kind]
        if any(k not in allowed for k in prev) or kind in prev:
            self.error(tok, "%s is already declared as %s" % (name, "/".join(prev)))
        if kind != "wire" and name not in net.ports:
            self.error(tok, "%s %s is not in the module port list" % (kind, name))
        prev.append(kind)
        net.decl_lines.setdefault(name, tok[2])
        {"input": net.inputs, "output": net.outputs, "wire": net.wires}[kind].append(name)

    def instance(self, net):
        cell = self.ident()
        name = self.ident()
        if any(i.name == name[1] for i in net.instances):
            self.error(name, "duplicate instance %s" % name[1])
        self.expect("(")
        conns = []
        while True:
            dot = self.next()
            if dot[0] == "id":
                self.error(dot, "positional connection %s in instance %s; use .PIN(NET)"
                           % (dot[1], name[1]))
            if dot[0] != ".":
                self.error(dot, "expected '.PIN(NET)', found %s" % _show(dot))
            pin = self.ident()[1]
            if any(c.pin == pin for c in conns):
                self.error(dot, "pin %s of instance %s is connected twice" % (pin, name[1]))
            self.expect("(")
            tok = self.next()
            if tok[0] == ")":
                self.error(tok, "empty connection .%s() in instance %s" % (pin, name[1]))
            if tok[0] != "id" or tok[1] in _KEYWORDS:
                self.error(tok, "expected a net name, found %s" % _show(tok))
            if tok[1] not in self.kinds:
                self.error(tok, "net %s is not a declared port or wire" % tok[1])
            self.expect(")")
            conns.append(Conn(pin, tok[1], dot[2]))
            sep = self.next()
            if sep[0] == ")":
                break
            if sep[0] != ",":
                self.error(sep, "expected ',' or ')', found %s" % _show(sep))
        self.expect(";")
        net.instances.append(Instance(cell[1], name[1], cell[2], conns))
