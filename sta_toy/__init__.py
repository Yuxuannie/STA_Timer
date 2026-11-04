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


class P2Error(StaError):
    """An error introduced in stage P2 (cli_p2.md): printed as '<file>:<line>: <message>',
    or 'error: <message>' when no file is known, without stage 1's 'ERROR ' prefix."""

    def __str__(self):
        if self.file is None:
            return "error: %s" % self.message
        return StaError.__str__(self)


def read_file(path):
    """Return the text of `path`; an unreadable file is a StaError with no line."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        raise StaError(path, None, "cannot read file: %s" % (getattr(e, "strerror", None) or e))
