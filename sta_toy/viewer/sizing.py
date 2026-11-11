"""UI scale and window size (P5 R32, viewer_p4.md "Changes in P5"), without Tk: the pane
minimums at scale 1, the --scale value, the default scale, and the window's size, position
and minimum size on a given screen."""

from sta_toy import P2Error

LOW, HIGH = 0.6, 2.0
SCALE_ERROR = "--scale needs a number from 0.6 to 2.0"
WIDTH, HEIGHT = 1520, 940                     # the window at scale 1 on a large screen
MIN_LEFT, MIN_CENTER, MIN_RIGHT = 280, 460, 320     # narrowest panes whose columns still fit
MIN_HIST, MIN_LIST = 130, 120                 # left column: histogram over endpoint list
MIN_SUMMARY, MIN_VIEWS, MIN_TABLE = 90, 160, 80     # centre column, top to bottom
HEADER, STATUS, SASH = 52, 26, 3


def ipx(v, s):
    """v pixels at scale s as a whole number of pixels for a widget option (at least 1)."""
    return max(1, int(round(v * s)))


def parse_scale(text):
    """The --scale value: a number in [LOW, HIGH], else a P2Error."""
    try:
        s = float(text)
    except ValueError:
        raise P2Error(None, None, SCALE_ERROR)
    if not LOW <= s <= HIGH:                  # also rejects nan and inf
        raise P2Error(None, None, SCALE_ERROR)
    return s


def default_scale(windowing_system, tk_scaling):
    """1.0 on aqua; elsewhere `tk scaling` (pixels per point) * 72 / 96, clamped."""
    if windowing_system == "aqua":
        return 1.0
    return min(HIGH, max(LOW, tk_scaling * 72 / 96.0))


def minimum(s):
    """(width, height): the three panes side by side, and header + status bar + the taller
    of the left and centre columns, at their minimums and with their dividers."""
    width = ipx(MIN_LEFT, s) + ipx(MIN_CENTER, s) + ipx(MIN_RIGHT, s) + 2 * ipx(SASH, s)
    left = ipx(MIN_HIST, s) + ipx(MIN_LIST, s) + ipx(SASH, s)
    center = ipx(MIN_SUMMARY, s) + ipx(MIN_VIEWS, s) + ipx(MIN_TABLE, s) + 2 * ipx(SASH, s)
    return width, ipx(HEADER, s) + ipx(STATUS, s) + max(left, center)


def geometry(s, screen_w, screen_h):
    """(width, height, x, y, min_width, min_height): min(1520 s, 92 % of the screen) by
    min(940 s, 90 % of it), never below the minimum, centred (not above or left of 0)."""
    min_w, min_h = minimum(s)
    w = max(min_w, int(min(WIDTH * s, 0.92 * screen_w)))
    h = max(min_h, int(min(HEIGHT * s, 0.90 * screen_h)))
    return w, h, max(0, (screen_w - w) // 2), max(0, (screen_h - h) // 2), min_w, min_h


def wheel_buttons(windowing_system, tk_version):
    """R52: Tk 8.6 on X11 sends the mouse wheel as buttons 4 and 5, not <MouseWheel>."""
    return windowing_system == "x11" and tk_version < 8.7
