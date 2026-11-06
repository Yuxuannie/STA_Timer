"""2-D table lookup: bilinear interpolation, linear extrapolation outside the grid (R11)."""


def _segment(axis, p):
    """Index i of the grid segment [axis[i], axis[i+1]] used for p (end segments outside)."""
    if p < axis[0]:
        return 0
    for i in range(len(axis) - 1):
        if axis[i] <= p <= axis[i + 1]:
            return i
    return len(axis) - 2


def bilinear(x, y, v, p, q):
    """Value at (p, q) of the table with axes x (rows of v) and y (columns of v)."""
    i, j = _segment(x, p), _segment(y, q)
    s = (p - x[i]) / (x[i + 1] - x[i])
    t = (q - y[j]) / (y[j + 1] - y[j])
    return ((1 - s) * (1 - t) * v[i][j] + s * (1 - t) * v[i + 1][j]
            + (1 - s) * t * v[i][j + 1] + s * t * v[i + 1][j + 1])


def lookup(table, args):
    """Look up a liberty.Table; `args` maps each template variable name to its query value."""
    return bilinear(table.index_1, table.index_2, table.values,
                    args[table.variables[0]], args[table.variables[1]])


def _side(axis, p):
    """None inside [axis[0], axis[-1]], else "below" / "above"."""
    if p < axis[0]:
        return "below"
    if p > axis[-1]:
        return "above"
    return None


def lookup_detail(table, args):
    """lookup() with the grid cell it used (P5 interface): value, axes, query,
    segment, bracket, corners and per-axis extrapolation side."""
    x, y, v = table.index_1, table.index_2, table.values
    p, q = args[table.variables[0]], args[table.variables[1]]
    i, j = _segment(x, p), _segment(y, q)
    return {
        "value": lookup(table, args),
        "axes": [table.variables[0], table.variables[1]],
        "query": [p, q],
        "segment": [i, j],
        "bracket": [[x[i], x[i + 1]], [y[j], y[j + 1]]],
        "corners": [[v[i][j], v[i][j + 1]], [v[i + 1][j], v[i + 1][j + 1]]],
        "extrapolated": [_side(x, p), _side(y, q)],
    }
