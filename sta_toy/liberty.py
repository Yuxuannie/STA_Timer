"""Liberty: a generic parser into a tree of groups and attributes (R1)."""

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
