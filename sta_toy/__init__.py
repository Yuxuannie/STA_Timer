"""Toy STA, stage 1: Liberty + gate-level Verilog -> flat timing graph."""


class StaError(Exception):
    """An input error. str() is '<file>:<line>: <message>', or '<file>: <message>' without a line."""

    def __init__(self, file, line, message):
        Exception.__init__(self, message)
        self.file = file
        self.line = line
        self.message = message

    def __str__(self):
        if self.line is None:
            return "%s: %s" % (self.file, self.message)
        return "%s:%d: %s" % (self.file, self.line, self.message)


def read_file(path):
    """Return the text of `path`; an unreadable file is a StaError with no line."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise StaError(path, None, "cannot read file: %s" % (getattr(e, "strerror", None) or e))
