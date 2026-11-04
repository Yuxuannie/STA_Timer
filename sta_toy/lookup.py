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
