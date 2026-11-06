"""Tk window (R29, viewer_p4.md v3): a timing-debug workstation for one design.

Left: the endpoint slack histogram and the endpoint list (triage). Centre: for the selected
endpoint and check, a summary card with the slack formula term by term, two views of the
worst path (gate-level schematic, waveform with setup and hold windows), and
the path table in three sections. Right: an inspector for the selected pin — its AT / RAT /
slew, the table lookup behind its delay, and which input set its arrival and which fanout
set its required time. Everything is drawn on canvases so every theme colours it fully.

Scale (P5, R32): every pixel constant goes through px() (times the UI scale s) and every font
through font(); model coordinates stay at scale 1 and the schematic is drawn at zoom * s."""

import math
import tkinter as tk
import tkinter.font as tkfont

from sta_toy.tsv import fmt4
from sta_toy.viewer import model, sizing, theme
from sta_toy.viewer.sizing import MIN_CENTER, MIN_LEFT, MIN_RIGHT

# Type scale (points at scale 1): 9 tracked capitals for labels, 10-11 captions and dense rows,
# 12 body, 13 the header mark, 16-18 titles, 28 the slack figure. Words in the UI font, every
# number in the monospaced one; bold only for titles, totals and the current selection.
# Pixel constants below are at scale 1.
ROW = 26
THIN = "\u2009"
TABS = ("schematic", "waveform", "trace")
DRAWN = ("schematic", "trace")          # views that draw the schematic (pan, zoom, fit)
TABLE = [("pin", 128, "w"), ("cell", 62, "w"), ("arc", 58, "w"), ("rf", 44, "w"), ("load", 66, "e"),
         ("fanout", 66, "e"), ("slew", 66, "e"), ("incr", 72, "e"), ("AT", 76, "e"), ("RAT", 76, "e"),
         ("pin slack", 100, "e")]
HINT = ("←/→ step pin to pin   ↑/↓ endpoint   S/H setup/hold   1/2/3 views   [ / ] hide panels   "
        "drag a divider to resize   click ⊕ to open the driving cell   ⌘-scroll zoom   F fit")


def _num(v):
    return "—" if v is None else fmt4(v)


def _neg(v):
    return v is not None and fmt4(v).startswith("-")


def _rounded(canvas, x0, y0, x1, y1, r, **kw):
    """A rounded rectangle as a smoothed polygon (each corner point doubled)."""
    r = max(0.0, min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0))
    pts = [x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y0 + r,
           x1, y1 - r, x1, y1 - r, x1, y1, x1 - r, y1, x1 - r, y1, x0 + r, y1, x0 + r, y1,
           x0, y1, x0, y1 - r, x0, y1 - r, x0, y0 + r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, splinesteps=10, **kw)


def _arc_points(cx, cy, r, a0, a1, n=16):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / float(n))),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / float(n)))) for i in range(n + 1)]


def _bezier(p0, p1, p2, n=12):
    return [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
             (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])
            for t in (i / float(n) for i in range(n + 1))]


class App:
    def __init__(self, root, source, theme_name="light", scale=None):
        self.root, self.source = root, source
        s0 = sizing.default_scale(root.tk.call("tk", "windowingsystem"), float(root.tk.call("tk", "scaling")))
        self.s = s0 if scale is None else scale
        self.font_scale = self.s / s0        # Tk already scales points by the display (tk scaling)
        self.endpoints = model.EndpointList(source.rows())
        self.check, self.endpoint, self.tab = "setup", None, "schematic"
        self.paths, self.path_cache = {"setup": None, "hold": None}, {}
        self.expansions = {}
        self.selected, self.stage, self.bin = None, None, None
        self.zoom, self.layout, self._fitted = 1.0, None, False
        self.replays, self.trace_truncated = {}, False
        self.errors, self.hits = [], {}
        self.sizes = dict((k, self.ipx(v)) for k, v in (("left", 300), ("right", 320), ("hist", 214),
                                                        ("summary", 168), ("table", 300)))
        self.show_left, self.show_right, self._static_job, self.body = True, True, None, None
        root.report_callback_exception = lambda *exc: self.errors.append(exc[1])
        families = set(tkfont.families(root))
        if root.tk.call("tk", "windowingsystem") == "aqua":     # the system font, SF Pro
            ui = tkfont.Font(root, name="TkDefaultFont", exists=True).actual("family")
        else:
            ui = theme.pick_font(theme.UI_FONTS, families)
        mono = theme.pick_font(theme.MONO_FONTS, families)
        self.family = {"ui": ui, "mono": mono}
        self._font_cache = {}
        root.title("STA Timer — %s" % source.design_name)
        w, h, x, y, min_w, min_h = sizing.geometry(self.s, root.winfo_screenwidth(), root.winfo_screenheight())
        self.min_width = min_w
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))
        root.minsize(min_w, min_h)
        self.set_theme(theme_name)
        first = self.endpoints.neighbour(None, 0)
        if first:
            self.select_endpoint(first)
        self._bind_keys()

    # ------------------------------------------------------------------ fonts and widgets

    def px(self, v):
        """v pixels at scale 1 in pixels at the UI scale."""
        return v * self.s

    def ipx(self, v):
        """px(v) as a whole number for a widget option."""
        return sizing.ipx(v, self.s)

    def font(self, kind="ui", size=12, bold=False):
        """`size` points at scale 1, at the UI scale."""
        key = (kind, int(round(size * self.font_scale)), bold)
        if key not in self._font_cache:
            self._font_cache[key] = tkfont.Font(self.root, family=self.family[kind], size=max(6, key[1]),
                                                weight="bold" if bold else "normal")
        return self._font_cache[key]

    def _canvas(self, parent, bg="bg", **kw):
        cv = tk.Canvas(parent, bg=self.c[bg], highlightthickness=0, bd=0, **kw)
        cv.bind("<Button-1>", lambda e, c=cv: self._click(c, e))
        return cv

    def set_theme(self, name):
        if getattr(self, "body", None) is not None:
            self._remember_panes()
        self.theme_name = name
        self.c = theme.THEMES[name]
        for w in self.root.winfo_children():
            w.destroy()
        self._build()
        if self.endpoint:
            self.refresh(fit=False)

    def _paned(self, parent, orient):
        """A resizable split; its background is the colour of the draggable divider."""
        return tk.PanedWindow(parent, orient=orient, sashwidth=self.ipx(sizing.SASH), sashrelief="flat", sashpad=0, bd=0,
                              bg=self.c["line"], opaqueresize=True, showhandle=False)

    def _remember_panes(self):
        for key, widget, attr in (("left", self.left_pane, "winfo_width"), ("right", self.insp, "winfo_width"),
                                  ("hist", self.hist, "winfo_height"), ("summary", self.summary_cv, "winfo_height"),
                                  ("table", self.table, "winfo_height")):
            try:
                if widget.winfo_ismapped() and getattr(widget, attr)() > self.px(20):
                    self.sizes[key] = getattr(widget, attr)()
            except tk.TclError:
                pass

    def _build(self):
        c, root, ipx = self.c, self.root, self.ipx
        root.configure(bg=c["panel"])
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)
        self.header = self._canvas(root, "panel", height=ipx(sizing.HEADER))
        self.header.grid(row=0, column=0, sticky="ew")
        self.body = body = self._paned(root, "horizontal")
        body.grid(row=1, column=0, sticky="nsew")

        self.left_pane = left = self._paned(body, "vertical")
        self.hist = self._canvas(left, "panel")
        left.add(self.hist, height=self.sizes["hist"], minsize=ipx(sizing.MIN_HIST), stretch="never")
        lst = tk.Frame(left, bg=c["panel"])
        self.list_head = self._canvas(lst, "panel", height=ipx(30))
        self.list_head.pack(fill="x")
        box = tk.Frame(lst, bg=c["panel"])
        box.pack(fill="x", padx=ipx(18), pady=(0, ipx(4)))
        self.filter_var = tk.StringVar(value=self.endpoints.text)
        entry = tk.Entry(box, textvariable=self.filter_var, font=self.font("ui", 12), bg=c["raised"],
                         fg=c["ink"], insertbackground=c["ink"], insertwidth=ipx(1), relief="flat",
                         highlightthickness=ipx(1), highlightbackground=c["line"], highlightcolor=c["strong"])
        entry.pack(fill="x", ipady=ipx(5), ipadx=ipx(4))
        self.filter_var.trace_add("write", lambda *a: self.set_filter(self.filter_var.get()))
        self.plist = self._canvas(lst, "panel")
        self.plist.pack(fill="both", expand=True)
        self._scrollable(self.plist)
        left.add(lst, minsize=ipx(sizing.MIN_LIST), stretch="always")
        body.add(left, width=self.sizes["left"], minsize=ipx(MIN_LEFT), stretch="never")

        self.center = center = self._paned(body, "vertical")
        self.summary_cv = self._canvas(center, "bg")
        center.add(self.summary_cv, height=self.sizes["summary"], minsize=ipx(sizing.MIN_SUMMARY), stretch="never")
        views = tk.Frame(center, bg=c["bg"])
        self.tabs = self._canvas(views, "bg", height=ipx(40))
        self.tabs.pack(fill="x")
        self.view = self._canvas(views, "bg")
        self.view.pack(fill="both", expand=True)
        self.view.bind("<ButtonPress-1>", self._view_press)
        self.view.bind("<B1-Motion>", lambda e: self.tab in DRAWN and self.view.scan_dragto(e.x, e.y, gain=1))
        self.view.bind("<Configure>", lambda e: self._on_view_resize())
        self._scrollable(self.view, zoom=True)
        center.add(views, minsize=ipx(sizing.MIN_VIEWS), stretch="always")
        self.table = self._canvas(center, "bg")
        center.add(self.table, height=self.sizes["table"], minsize=ipx(sizing.MIN_TABLE), stretch="never")
        self._scrollable(self.table)
        body.add(center, minsize=ipx(MIN_CENTER), stretch="always")

        self.insp = self._canvas(body, "panel")
        self._scrollable(self.insp)
        body.add(self.insp, width=self.sizes["right"], minsize=ipx(MIN_RIGHT), stretch="never")
        body.paneconfigure(left, hide=not self.show_left)
        body.paneconfigure(self.insp, hide=not self.show_right)
        self.status = self._canvas(root, "panel", height=ipx(sizing.STATUS))
        self.status.grid(row=2, column=0, sticky="ew")
        for cv in (self.header, self.hist, self.list_head, self.plist, self.summary_cv, self.tabs, self.table,
                   self.insp, self.status):
            cv.bind("<Configure>", lambda e: self._schedule_static())

    def toggle_panel(self, side):
        """Show or hide the left (histogram + endpoints) or right (inspector) panel."""
        pane = self.left_pane if side == "left" else self.insp
        shown = not (self.show_left if side == "left" else self.show_right)
        if not shown:
            self._remember_panes()
        if side == "left":
            self.show_left = shown
        else:
            self.show_right = shown
        self.body.paneconfigure(pane, hide=not shown)
        if shown:
            self.body.paneconfigure(pane, width=self.sizes[side])
        self._schedule_static()
        self._draw_header()

    def _schedule_static(self):
        """Redraw the static panels once the sizes settle (dragging a divider sends many events)."""
        if self._static_job is not None:
            self.root.after_cancel(self._static_job)
        self._static_job = self.root.after(20, self._run_static)

    def _run_static(self):
        self._static_job = None
        self._redraw_static()

    def _scrollable(self, canvas, zoom=False):
        canvas.configure(xscrollincrement=1, yscrollincrement=1)

        def wheel(event, horizontal=False):
            px = int(-event.delta / 4.0) or (-1 if event.delta > 0 else 1)
            (canvas.xview_scroll if horizontal else canvas.yview_scroll)(px, "units")

        def touchpad(event):
            d = int(event.delta)
            dx, dy = d >> 16, ((d & 0xFFFF) ^ 0x8000) - 0x8000
            if dx:
                canvas.xview_scroll(-dx, "units")
            if dy:
                canvas.yview_scroll(-dy, "units")
        canvas.bind("<MouseWheel>", wheel)
        canvas.bind("<Shift-MouseWheel>", lambda e: wheel(e, True))
        try:
            canvas.bind("<TouchpadScroll>", touchpad)
        except tk.TclError:                     # Tk 8.6 has no touchpad events
            pass
        if zoom:
            mod = "Command" if self.root.tk.call("tk", "windowingsystem") == "aqua" else "Control"
            canvas.bind("<%s-MouseWheel>" % mod,
                        lambda e: self.set_zoom(self.zoom * (1.1 if e.delta > 0 else 1 / 1.1)))

    def _bind_keys(self):
        def key(fn):
            return lambda e: None if isinstance(e.widget, tk.Entry) else fn()
        for k, fn in (("<Left>", lambda: self.step(-1)), ("<Right>", lambda: self.step(1)),
                      ("<Up>", lambda: self.next_endpoint(-1)), ("<Down>", lambda: self.next_endpoint(1)),
                      ("<Key-s>", lambda: self.set_check("setup")), ("<Key-h>", lambda: self.set_check("hold")),
                      ("<Key-1>", lambda: self.set_tab("schematic")), ("<Key-2>", lambda: self.set_tab("waveform")),
                      ("<Key-3>", lambda: self.set_tab("trace")),
                      ("<Key-f>", self.fit),
                      ("<Key-bracketleft>", lambda: self.toggle_panel("left")),
                      ("<Key-bracketright>", lambda: self.toggle_panel("right"))):
            self.root.bind(k, key(fn))

    # ------------------------------------------------------------------ state

    @property
    def expanded(self):
        return self.expansions.setdefault((self.endpoint, self.check), [])

    def path(self):
        return self.paths.get(self.check)

    def _paths_of(self, pin):
        if pin not in self.path_cache:
            self.path_cache[pin] = self.source.paths(pin)
        return self.path_cache[pin]

    def select_endpoint(self, pin):
        self.endpoint = pin
        self.paths = self._paths_of(pin)
        path = self.path()
        self.stage = len(path["points"]) - 1 if path else None
        self.selected = pin
        self.refresh(fit=True)

    def set_check(self, check):
        self.check = check
        self.endpoints.check = check
        self.bin = None
        path = self.path()
        self.stage = len(path["points"]) - 1 if path else None
        self.selected = self.endpoint
        self.refresh(fit=True)

    def set_tab(self, tab):
        if tab == "trace" and self.source.mode != "engine":
            return                      # R41: the trace replays the engine's log
        self.tab = tab
        self.refresh(fit=tab in DRAWN)

    @property
    def replay(self):
        """R41: the replay of the current endpoint's trace (engine mode), made on first use."""
        if self.source.mode != "engine" or self.endpoint is None:
            return None
        if self.endpoint not in self.replays:
            self.replays[self.endpoint] = model.Replay(self.source.trace(self.endpoint))
        return self.replays[self.endpoint]

    def trace_step(self, delta):
        self.replay.step(delta)
        self.refresh(fit=False)
        self._see(self.replay.current["pin"] if self.replay.current else None)

    def trace_end(self):
        self.replay.run_to_end()
        self.refresh(fit=False)
        self._see(self.replay.current["pin"] if self.replay.current else None)

    def set_filter(self, text):
        self.endpoints.text = text
        self._draw_list()

    def filter_bin(self, index):
        self.bin = None if self.bin == index else index
        self._draw_hist()
        self._draw_list()

    def next_endpoint(self, step):
        pin = self.endpoints.neighbour(self.endpoint, step)
        rows = [r["pin"] for r in self._list_rows()]
        if rows and pin not in rows:
            pin = rows[0]
        if pin:
            self.select_endpoint(pin)

    def step(self, delta):
        path = self.path()
        if path:
            last = len(path["points"]) - 1
            self.select_stage(max(0, min(last, (self.stage if self.stage is not None else last) + delta)))

    def select_stage(self, index):
        self.stage = index
        self.selected = self.path()["points"][index]["pin"]
        self.refresh(fit=False)
        self._see(self.selected)

    def select_pin(self, pin):
        path = self.path()
        pins = [q["pin"] for q in path["points"]] if path else []
        self.stage = pins.index(pin) if pin in pins else None
        self.selected = pin
        self.refresh(fit=False)
        self._see(pin)

    def select_cell(self, inst):
        self.selected, self.stage = "cell:" + inst, None
        self.refresh(fit=False)

    def expand(self, pin):
        if pin not in self.expanded:
            self.expanded.append(pin)
        self.selected = pin
        self.refresh(fit=False)

    def collapse(self):
        del self.expanded[:]
        self.refresh(fit=True)

    def set_zoom(self, z):
        self.zoom = max(0.45, min(2.0, z))
        self._draw_view()
        self._draw_tabs()

    def fit(self):
        if self.tab not in DRAWN or not self.layout:
            self._draw_view()
            return
        w, h = self.view.winfo_width(), self.view.winfo_height()
        bw, bh = self.layout["bbox"][2] * self.s, self.layout["bbox"][3] * self.s
        if w > 10 and h > 10:
            # Never below a readable size: long paths are panned (arrow keys follow the signal).
            self.zoom = max(0.95, min(1.25, w / float(bw), h / float(bh)))
        self._draw_view()
        self._draw_tabs()
        self.view.xview_moveto(0)
        self.view.yview_moveto(0)

    def _on_view_resize(self):
        if not self._fitted and self.layout:
            self._fitted = True
            self.fit()
        else:
            self._draw_view()

    def _see(self, pin):
        if self.tab not in DRAWN or not self.layout:
            return
        pins = sorted([p for e in self.layout["elements"] for p in e["pins"] if p["pin"] == pin],
                      key=lambda q: not q["on_path"])
        if not pins:
            return
        z = self.zoom * self.s
        bw, bh = self.layout["bbox"][2] * z, self.layout["bbox"][3] * z
        w, h = self.view.winfo_width(), self.view.winfo_height()
        x, y = pins[0]["x"] * z, pins[0]["y"] * z
        if bw > w:
            self.view.xview_moveto(max(0.0, (x - w / 2.0) / bw))
        if bh > h:
            self.view.yview_moveto(max(0.0, (y - h / 2.0) / bh))

    # ------------------------------------------------------------------ hit testing

    def _hit(self, canvas, item, action):
        self.hits[(str(canvas), item)] = action

    def _click(self, canvas, event):
        for item in reversed(canvas.find_overlapping(canvas.canvasx(event.x) - 1, canvas.canvasy(event.y) - 1,
                                                     canvas.canvasx(event.x) + 1, canvas.canvasy(event.y) + 1)):
            action = self.hits.get((str(canvas), item))
            if action:
                action()
                return True
        return False

    def _view_press(self, event):
        if not self._click(self.view, event) and self.tab in DRAWN:
            self.view.scan_mark(event.x, event.y)

    # ------------------------------------------------------------------ drawing

    def refresh(self, fit=False):
        path = self.path()
        self.trace_truncated = False
        if path and self.tab == "trace":        # R41: the whole cone, user expansions untouched
            self.layout, self.trace_truncated = model.auto_expand(path, self.source)
        else:
            self.layout = model.schematic(path, self.source, self.expanded) if path else None
            if self.layout:
                self.expanded[:] = self.layout["expanded"]
        if fit:
            self._fitted = False
            self.root.update_idletasks()
            if self.view.winfo_width() > 10:
                self._fitted = True
                self.fit()
            else:                       # not laid out yet: draw now, fit on the first resize
                self._draw_view()
        else:
            self._draw_view()
        self._redraw_static()

    def _redraw_static(self):
        self._draw_header()
        self._draw_hist()
        self._draw_list()
        self._draw_summary()
        self._draw_tabs()
        self._draw_table()
        self._draw_inspector()
        self._draw_status()

    def _clear(self, cv):
        for key in [k for k in self.hits if k[0] == str(cv)]:
            del self.hits[key]
        cv.delete("all")

    def _text(self, cv, x, y, text, kind="ui", size=12, bold=False, fill="ink", anchor="w", **kw):
        return cv.create_text(x, y, text=text, font=self.font(kind, size, bold), fill=self.c.get(fill, fill),
                              anchor=anchor, **kw)

    def _caps(self, text):
        """Small capitals tracked out with thin spaces."""
        return THIN.join(text.upper())

    def _eyebrow(self, cv, x, y, text, anchor="w", fill="faint"):
        return self._text(cv, x, y, self._caps(text), "ui", 9, True, fill, anchor)

    def _width(self, parts):
        return sum(self.font(k, s, b).measure(t) + self.px(g) for t, k, s, b, _, g in parts) - self.px(parts[-1][5])

    def _run(self, cv, x, y, parts, anchor="w"):
        """Draw (text, kind, size, bold, colour, gap after) parts left to right on one baseline;
        anchor "e" ends the run at x; gaps are pixels at scale 1. Returns (x0, x1, items)."""
        width = self._width(parts)
        x0 = x - width if anchor == "e" else x
        x, items = x0, []
        for text, kind, size, bold, colour, gap in parts:
            items.append(self._text(cv, x, y, text, kind, size, bold, colour))
            x += self.font(kind, size, bold).measure(text) + self.px(gap)
        return x0, x0 + width, items

    def _section(self, cv, y, title, w):
        """A hairline and a small-caps title; returns the y of the first row under it."""
        P = self.px
        cv.create_line(P(20), y, w - P(20), y, fill=self.c["line"])
        self._eyebrow(cv, P(20), y + P(20), title)
        return y + P(44)

    # header ----------------------------------------------------------------------------

    def _draw_header(self):
        cv, c, P = self.header, self.c, self.px
        self._clear(cv)
        w, y = max(cv.winfo_width(), self.min_width), P(26)
        cv.create_line(0, self.ipx(sizing.HEADER) - 1, w, self.ipx(sizing.HEADER) - 1, fill=c["line"])
        self._panel_icon(cv, P(18), y, "left", self.show_left)
        brand = self._text(cv, P(52), y, "STA Timer", "ui", 13, True, "ink")
        x = cv.bbox(brand)[2] + P(16)
        cv.create_line(x, y - P(9), x, y + P(9), fill=c["strong"])
        _, x, _ = self._run(cv, x + P(16), y, [
            (self.source.design_name, "ui", 12, False, "muted", 16),
            ("clock", "ui", 11, False, "faint", 5), (self.source.clock_name, "ui", 12, False, "muted", 16),
            ("period", "ui", 11, False, "faint", 5), ("%s ns" % fmt4(self.source.period), "mono", 11, False, "muted", 0)])
        self._panel_icon(cv, w - P(36), y, "right", self.show_right)
        left = self._theme_switch(cv, w - P(58), y)
        limit = self._segmented(cv, left - P(22), y, anchor="e") - P(28)
        start = max(P(440), x + P(48))
        groups = [(k, n, self.source.summary(k)) for k, n in (("setup", ("WNS", "TNS", "NVP")),
                                                               ("hold", ("WHS", "THS", "NVP")))]
        groups = [g for g in groups if g[2] is not None]
        for compact in (False, True):          # every figure if it fits, else only the worst slack
            runs = [self._metric_parts(k, n, s, compact) for k, n, s in groups]
            if start + sum(self._width(p) + P(36) for p in runs) - P(36) <= limit or compact:
                break
        x = start
        for (check, _, _), parts in zip(groups, runs):
            x0, x1, _ = self._run(cv, x, y, parts)
            hit = cv.create_rectangle(x0 - P(6), y - P(14), x1 + P(6), y + P(14), outline="", fill="")
            self._hit(cv, hit, lambda k=check: self.set_check(k))
            x = x1 + P(36)

    def _metric_parts(self, check, names, s, compact):
        parts = [(check.capitalize(), "ui", 12, False, "ink" if check == self.check else "muted", 12)]
        values = [(names[0], _num(s["wns"]), "bad" if _neg(s["wns"]) else "ok")]
        if not compact:
            values += [(names[1], fmt4(s["tns"]), "bad" if _neg(s["tns"]) else "muted"),
                       (names[2], str(s["nvp"]), "bad" if s["nvp"] else "muted")]
        for name, value, colour in values:
            parts += [(name, "ui", 10, False, "faint", 5), (value, "mono", 11, False, colour, 14)]
        return parts

    def _panel_icon(self, cv, x, y, side, on):
        """The sidebar glyph, a framed window whose left or right third is filled while that
        panel shows; x is its left edge."""
        P, colour = self.px, self.c["muted"] if on else self.c["faint"]
        _rounded(cv, x, y - P(7), x + P(18), y + P(7), P(3), fill="", outline=colour, width=P(1.2))
        split = x + P(6 if side == "left" else 12)
        cv.create_line(split, y - P(7), split, y + P(7), fill=colour, width=P(1.2))
        if on:
            a, b = (x + P(2), split - P(1)) if side == "left" else (split + P(1), x + P(16))
            cv.create_rectangle(a, y - P(5), b, y + P(5), fill=colour, outline="")
        hit = cv.create_rectangle(x - P(8), y - P(14), x + P(26), y + P(14), outline="", fill="")
        self._hit(cv, hit, lambda: self.toggle_panel(side))

    def _theme_switch(self, cv, x, y):
        """`◐ Light` ending at x; a click moves to the next theme. Returns its left edge."""
        c, P = self.c, self.px
        nxt = theme.NAMES[(theme.NAMES.index(self.theme_name) + 1) % len(theme.NAMES)]
        x0, _, _ = self._run(cv, x, y, [(self.theme_name.capitalize(), "ui", 12, False, "muted", 0)], "e")
        cx = x0 - P(13)
        cv.create_oval(cx - P(6), y - P(6), cx + P(6), y + P(6), outline=c["muted"], width=P(1.2))
        cv.create_arc(cx - P(6), y - P(6), cx + P(6), y + P(6), start=90, extent=180, fill=c["muted"], outline="")
        hit = cv.create_rectangle(cx - P(10), y - P(14), x + P(4), y + P(14), outline="", fill="")
        self._hit(cv, hit, lambda: self.set_theme(nxt))
        return cx - P(8)

    def _segmented(self, cv, x, y, anchor="w"):
        """Setup | Hold: a recessed track with the active half raised; returns its left edge."""
        P = self.px
        c, w, h = self.c, P(128), P(26)
        x0 = x - w if anchor == "e" else x
        _rounded(cv, x0, y - h / 2.0, x0 + w, y + h / 2.0, P(7), fill=c["head"], outline="")
        for i, check in enumerate(("setup", "hold")):
            on = check == self.check
            bx = x0 + P(2) + i * (w - P(4)) / 2.0
            if on:
                _rounded(cv, bx, y - h / 2.0 + P(2), bx + (w - P(4)) / 2.0, y + h / 2.0 - P(2), P(5),
                         fill=c["raised"], outline=c["strong"])
            t = self._text(cv, bx + (w - P(4)) / 4.0, y, check.capitalize(), "ui", 11, on,
                           "ink" if on else "muted", "center")
            hit = cv.create_rectangle(bx, y - h / 2.0, bx + (w - P(4)) / 2.0, y + h / 2.0, outline="", fill="")
            self._hit(cv, hit, lambda k=check: self.set_check(k))
            self._hit(cv, t, lambda k=check: self.set_check(k))
        return x0

    # left: histogram and list --------------------------------------------------------------

    def _list_rows(self):
        rows = self.endpoints.view()
        if self.bin is not None:
            bins = model.histogram([r[self.check + "_slack"] for r in self.endpoints.rows])
            if self.bin < len(bins):
                b = bins[self.bin]
                last = self.bin == len(bins) - 1
                rows = [r for r in rows if r[self.check + "_slack"] is not None and
                        b["lo"] <= r[self.check + "_slack"] and (r[self.check + "_slack"] < b["hi"] or last)]
        return rows

    def _draw_hist(self):
        cv, c, P = self.hist, self.c, self.px
        self._clear(cv)
        w = max(cv.winfo_width(), P(MIN_LEFT))
        h = max(cv.winfo_height(), P(sizing.MIN_HIST))
        self._eyebrow(cv, P(20), P(26), "%s slack" % self.check)
        values = [r[self.check + "_slack"] for r in self.endpoints.rows]
        bins = model.histogram(values)
        if not bins:
            self._text(cv, w / 2.0, h / 2.0, "no %s checks" % self.check, "ui", 11, False, "faint", "center")
            return
        top = max(b["count"] for b in bins)
        x0, x1, y0 = P(20), w - P(20), P(60)
        y1 = max(y0 + P(20), h - P(66))  # from the bottom: caption, axis labels, then the bars
        bw = (x1 - x0) / float(len(bins))
        lo, hi = bins[0]["lo"], bins[-1]["hi"]
        for i, b in enumerate(bins):
            bh = (y1 - y0) * b["count"] / float(top) if b["count"] else 0
            if self.bin is None:
                colour = c["bad"] if b["hi"] <= 0 else c["wire"]
            elif self.bin == i:
                colour = c["bad"] if b["hi"] <= 0 else c["ink"]
            else:
                colour = c["strong"]
            bar = cv.create_rectangle(x0 + i * bw + P(2.5), y1 - max(bh, P(2) if b["count"] else 0),
                                      x0 + (i + 1) * bw - P(2.5), y1, fill=colour if b["count"] else c["line"], outline="")
            hit = cv.create_rectangle(x0 + i * bw, y0 - P(8), x0 + (i + 1) * bw, y1 + P(4), outline="", fill="")
            if b["count"]:
                self._text(cv, x0 + (i + 0.5) * bw, y1 - bh - P(8), str(b["count"]), "mono", 9, False, "faint", "center")
            for item in (bar, hit):
                self._hit(cv, item, lambda k=i: self.filter_bin(k))
        cv.create_line(x0, y1, x1, y1, fill=c["strong"])
        self._text(cv, x0, y1 + P(13), fmt4(lo), "mono", 9, False, "faint", "w")
        self._text(cv, x1, y1 + P(13), fmt4(hi), "mono", 9, False, "faint", "e")
        if lo < 0 < hi:
            zx = x0 + (0 - lo) / (hi - lo) * (x1 - x0)
            cv.create_line(zx, y0 - P(8), zx, y1 + P(4), fill=c["muted"], dash=(2, 3))
            if x0 + P(40) < zx < x1 - P(40):
                self._text(cv, zx, y1 + P(13), "0", "mono", 9, False, "muted", "center")
        defined = [v for v in values if v is not None]
        worst = min(defined)
        parts = [("worst", "ui", 10, False, "faint", 5), (fmt4(worst), "mono", 10, False, "bad" if _neg(worst) else "ok", 14),
                 ("%d endpoints" % len(defined), "ui", 10, False, "faint", 14)]
        if self.bin is not None:
            parts.append(("one bin shown", "ui", 10, False, "ink", 0))
        self._run(cv, P(20), h - P(22), parts)

    def _draw_list(self):
        cv, c, P = self.plist, self.c, self.px
        self._clear(cv)
        self._clear(self.list_head)
        w = max(cv.winfo_width(), P(MIN_LEFT))
        key = self.check + "_slack"
        rows = self._list_rows()
        self._eyebrow(self.list_head, P(20), P(16), "endpoints")
        self._text(self.list_head, w - P(20), P(16), "%d / %d" % (len(rows), len(self.endpoints.rows)), "mono", 9, False,
                   "faint", "e")
        cols = ((P(20), "w"), (P(154), "e"), (P(176), "w"), (w - P(20), "e"))
        for (x, anchor), title in zip(cols, ("endpoint", "slack", "from", "levels")):
            self._text(cv, x, P(16), title, "ui", 10, False, "faint", anchor)
        y = P(30)
        for r in rows:
            on = r["pin"] == self.endpoint
            if on:
                _rounded(cv, P(8), y, w - P(8), y + P(34), P(6), fill=c["select"], outline="")
            p = self._paths_of(r["pin"]).get(self.check)
            v = r[key]
            self._text(cv, P(20), y + P(17), r["pin"], "ui", 12, on, "ink")
            self._text(cv, P(154), y + P(17), _num(v), "mono", 11, False,
                       "faint" if v is None else ("bad" if _neg(v) else "ok"), "e")
            self._text(cv, P(176), y + P(17), p["start"] if p else "—", "ui", 11, False, "muted")
            self._text(cv, w - P(20), y + P(17), str(model.summary(p)["levels"]) if p else "", "mono", 11, False, "faint",
                       "e")
            hit = cv.create_rectangle(0, y, w, y + P(34), outline="", fill="")
            self._hit(cv, hit, lambda k=r["pin"]: self.select_endpoint(k))
            y += P(36)
        cv.configure(scrollregion=(0, 0, w, y + P(10)))

    # centre: summary, tabs ---------------------------------------------------------------

    def _draw_summary(self):
        """The endpoint, its slack, and the slack worked out term by term like a receipt."""
        cv, c, P = self.summary_cv, self.c, self.px
        self._clear(cv)
        w = max(cv.winfo_width(), P(MIN_CENTER))
        path = self.path()
        self._text(cv, P(24), P(32), self.endpoint or "", "ui", 18, True, "ink")
        if not path:
            self._text(cv, P(24), P(58), "No %s path ends here (the check is not constrained)." % self.check,
                       "ui", 12, False, "muted")
            return
        s = model.summary(path)
        f = model.formula(path)
        bad = _neg(s["slack"])
        status = "bad" if bad else "ok"
        sub = ["%s path from %s" % (self.check, s["start"]), "%d logic levels" % s["levels"]]
        if s["skew"] is not None:
            sub.append("clock skew %s" % fmt4(s["skew"]))
        hero = self._text(cv, w - P(24), P(34), fmt4(s["slack"]), "ui", 28, False, status, "e")
        x0, _, _ = self._run(cv, w - P(24), P(62), [(self._caps("%s slack" % self.check), "ui", 9, True, "faint", 8),
                                              (self._caps("violated" if bad else "met"), "ui", 9, True, status, 0)], "e")
        limit, lines = min(x0, cv.bbox(hero)[0]) - P(20) - P(24), [sub[0]]
        for part in sub[1:]:             # wrap before the slack figure
            if self.font("ui", 11).measure(lines[-1] + "   ·   " + part) <= limit:
                lines[-1] += "   ·   " + part
            else:
                lines.append(part)
        for i, line in enumerate(lines[:2]):
            self._text(cv, P(24), P(57 + 17 * i), line, "ui", 11, False, "muted")
        right = min(w - P(24), P(940))   # totals end here; the "=" column sits before them
        eq = right - P(104)
        y = P(96 if len(lines) == 1 else 106)
        for label, terms, total in (("arrival", f["arrival"], s["arrival"]), ("required", f["required"], s["required"])):
            self._text(cv, P(24), y, label, "ui", 11, False, "faint")
            y = self._terms(cv, P(104), y, [t for t in terms if t[1] is not None], eq - P(18))
            self._text(cv, eq, y, "=", "mono", 11, False, "faint", "center")
            self._text(cv, right, y, fmt4(total), "mono", 12, True, "ink", "e")
            y += P(24)
        cv.create_line(P(104), y - P(11), right, y - P(11), fill=c["strong"])
        self._text(cv, P(24), y + P(2), "slack", "ui", 11, False, "faint")
        self._text(cv, P(104), y + P(2), "required − arrival" if self.check == "setup" else "arrival − required",
                   "ui", 11, False, "muted")
        self._text(cv, eq, y + P(2), "=", "mono", 11, False, "faint", "center")
        self._text(cv, right, y + P(2), fmt4(s["slack"]), "mono", 12, True, status, "e")
        need = int(y + P(24))            # never cut the receipt: the strip grows to hold it
        if int(self.center.panecget(cv, "minsize")) != need:
            self.center.paneconfigure(cv, minsize=need)
        if cv.winfo_height() < need:
            self.center.paneconfigure(cv, height=need)

    def _terms(self, cv, x, y, terms, limit):
        """name value + name value ...; a term that would pass `limit` starts an indented new
        line. Returns the y of the last line."""
        start = x
        for i, (name, value) in enumerate(terms):
            parts = []
            if i:
                parts.append(("−" if math.copysign(1.0, value) < 0 else "+", "mono", 11, False, "faint", 10))
                value = abs(value)
            parts += [(name, "ui", 11, False, "muted", 5), (fmt4(value), "mono", 11, False, "ink", 0)]
            if i and x + self._width(parts) > limit:
                x, y = start + self.px(14), y + self.px(18)
            x = self._run(cv, x, y, parts)[1] + self.px(10)
        return y

    def _draw_tabs(self):
        cv, c, P = self.tabs, self.c, self.px
        self._clear(cv)
        w = max(cv.winfo_width(), P(MIN_CENTER))
        base = self.ipx(40) - 1
        x = P(24)
        for tab in TABS:
            on = tab == self.tab
            off = tab == "trace" and self.source.mode != "engine"     # R41: engine mode only
            t = self._text(cv, x, P(20), tab.capitalize(), "ui", 12, on, "ink" if on else ("faint" if off else "muted"))
            x0, y0, x1, y1 = cv.bbox(t)
            if on:
                cv.create_rectangle(x0, base - P(2), x1, base, fill=c["ink"], outline="")
            if not off:
                hit = cv.create_rectangle(x0 - P(8), P(4), x1 + P(8), base - P(1), outline="", fill="")
                self._hit(cv, hit, lambda k=tab: self.set_tab(k))
            x = x1 + P(26)
        tabs_end = x
        rows = self._trace_controls(cv, w, base + P(17), tabs_end) if self.tab == "trace" else 1
        height = self.ipx((40, 72, 96)[rows - 1])
        if int(cv.cget("height")) != height:
            cv.configure(height=height)
        cv.create_line(0, height - 1, w, height - 1, fill=c["line"])
        if self.tab != "schematic":
            return
        controls = [("Collapse", self.collapse), ("Fit", self.fit), ("+", lambda: self.set_zoom(self.zoom * 1.2)),
                    ("%d%%" % round(self.zoom * 100), None), ("−", lambda: self.set_zoom(self.zoom / 1.2))]
        width = lambda: sum(self.font("ui" if fn else "mono", 12 if fn else 10).measure(label) + P(20)
                            for label, fn in controls)
        for optional in (3, 1):          # when narrow, drop the zoom readout, then Fit (the F key stays)
            if w - P(24) - width() < tabs_end:
                del controls[optional]
        x = w - P(24)
        for label, fn in controls:
            t = self._text(cv, x, P(20), label, "ui" if fn else "mono", 12 if fn else 10, False,
                           "muted" if fn else "faint", "e")
            x0, y0, x1, y1 = cv.bbox(t)
            if fn:
                hit = cv.create_rectangle(x0 - P(6), P(6), x1 + P(6), P(34), outline="", fill="")
                self._hit(cv, hit, fn)
            x = x0 - P(20 if label in ("Collapse", "Fit") else 10)
        if self.expanded and x - P(10) - self.font("ui", 10).measure("9 opened") > tabs_end + P(20):
            self._text(cv, x - P(10), P(20), "%d opened" % len(self.expanded), "ui", 10, False, "faint", "e")

    def _trace_controls(self, cv, w, y, tabs_end):
        """R41: the replay's step controls on the tab strip's second row, the phase label at
        its right end, else at the right of the tab row, else on a third row. Returns the
        number of rows used."""
        P, replay = self.px, self.replay
        x = P(24)
        for label, fn in (("◀ step back", lambda: self.trace_step(-1)), ("▶ step", lambda: self.trace_step(1)),
                          ("▶▶ run to end", self.trace_end)):
            t = self._text(cv, x, y, label, "ui", 11, False, "muted")
            x0, y0, x1, y1 = cv.bbox(t)
            hit = cv.create_rectangle(x0 - P(6), y - P(12), x1 + P(6), y + P(12), outline="", fill="")
            for it in (t, hit):
                self._hit(cv, it, fn)
            x = x1 + P(20)
        parts = [(replay.label, "mono", 10, False, "ink", 0)]
        if self.trace_truncated:
            parts = [("truncated", "ui", 10, False, "bad", 12)] + parts
        n = len(replay.entries)          # place by the widest label, so the strip keeps its height
        widest = [("backward · %d of %d" % (n, n), "mono", 10, False, "ink", 0)] + parts[:-1]
        rows, width = 2, self._width(widest)
        if x + width > w - P(24):
            if tabs_end + width <= w - P(24):
                y = P(20)
            else:
                rows, y = 3, y + P(24)
        self._run(cv, w - P(24), y, parts, "e")
        return rows

    # centre: views -------------------------------------------------------------------------

    def _draw_view(self):
        cv = self.view
        self._clear(cv)
        if not self.path():
            self._text(cv, self.px(30), self.px(30), "No %s path for %s." % (self.check, self.endpoint), "ui", 12, False, "muted")
            cv.configure(scrollregion=(0, 0, cv.winfo_width(), cv.winfo_height()))
            return
        getattr(self, "_draw_" + self.tab)()

    def _draw_trace(self):
        """R41: the auto-expanded schematic, the current entry's pin ringed, only replayed numbers."""
        self._draw_schematic()

    def _replayed(self, pin):
        """(AT, rf) of an on-path pin from the replay, in the path's mode and rf; None if not reached."""
        point = [q for q in self.path()["points"] if q["pin"] == pin]
        f = self.replay.forward(pin, model.MODE[self.check], point[0]["rf"]) if point else None
        return (f, point[0]["rf"]) if f else None

    def _draw_schematic(self):
        """Neutral line art; only the critical path (wires, leads, pins, AT labels) in the accent."""
        cv, c, z, lay = self.view, self.c, self.zoom, self.layout
        trace = self.tab == "trace"
        current = self.replay.current if trace else None
        ring = (current["pin"] if current else None) if trace else self.selected
        S = lambda v: v * z * self.s     # model pixels at zoom 1 and scale 1
        w, h = max(cv.winfo_width(), self.px(200)), max(cv.winfo_height(), self.px(200))
        bw, bh = S(lay["bbox"][2]), S(lay["bbox"][3])
        ox = -(w - bw) / 2.0 if bw < w else 0       # centre a drawing smaller than the view
        oy = -(h - bh) / 2.0 if bh < h else 0
        cv.configure(scrollregion=(ox, oy, ox + max(w, bw), oy + max(h, bh)))
        hop = model.stages(self.path())[self.stage] if self.stage is not None and not trace else None
        on_path = set(p["pin"] for e in lay["elements"] for p in e["pins"] if p["on_path"])
        for wire in sorted(lay["wires"], key=lambda x: x["on_path"]):
            hot = hop is not None and hop["kind"] == "net" and wire["to"] == hop["pin"] and wire["on_path"]
            colour = c["focus"] if hot else (c["accent"] if wire["on_path"] else c["wire"])
            cv.create_line(*[S(v) for xy in wire["points"] for v in xy], fill=colour,
                           width=S(2.6 if hot else (2.0 if wire["on_path"] else 1.1)), capstyle="round",
                           joinstyle="round")
        for e in lay["elements"]:
            if e["kind"] == "port":
                self._draw_port(e, S)
            else:
                self._draw_gate(e, S, hop)
            for p in e["pins"]:
                if p["pin"] == ring and (p["on_path"] or ring not in on_path):
                    cv.create_oval(S(p["x"] - 7), S(p["y"] - 7), S(p["x"] + 7), S(p["y"] + 7),
                                   outline=c["focus"], width=S(1.6), tags=("ring", p["pin"]))
        base = dict((e["name"], p["y"]) for e in lay["elements"] for p in e["pins"] if p["on_path"] and p["side"] == "in")
        for st in lay["stubs"]:          # labels move away from the path: under the stubs below it
            self._draw_stub(st, S, st["y"] > base.get(st["pin"].split("/")[0], st["y"]))
        for b in lay["badges"]:          # knocked out of whatever runs behind them
            text = b["text"]
            if trace:                    # R41: only what the replay has reached, from the log
                got = self._replayed(b["pin"])
                if got is None:
                    continue
                text = "%s %s" % (fmt4(got[0]["at"]), got[1])
            t = self._text(cv, S(b["x"]), S(b["y"]), text, "mono", 9 * z, False, "accent_ink", b["anchor"])
            x0, y0, x1, y1 = cv.bbox(t)
            bg = cv.create_rectangle(x0 - S(2), y0, x1 + S(2), y1, fill=c["bg"], outline="")
            cv.tag_lower(bg, t)

    def _draw_port(self, e, S):
        cv, c = self.view, self.c
        on = e["pins"][0]["on_path"]
        x0, y0, x1, y1 = e["x0"], e["y0"], e["x1"], e["y1"]
        mid = (y0 + y1) / 2.0
        if e["direction"] == "in":
            pts = [x0, y0, x1 - 12, y0, x1, mid, x1 - 12, y1, x0, y1]
        else:
            pts = [x0, mid, x0 + 12, y0, x1, y0, x1, y1, x0 + 12, y1]
        item = cv.create_polygon(*[S(v) for v in pts], fill=c["raised"], outline=c["ink"] if on else c["faint"],
                                 width=S(1.3))
        t = self._text(cv, S((x0 + x1) / 2.0 + (-4 if e["direction"] == "in" else 4)), S(mid), e["name"],
                       "ui", 11 * self.zoom, True, "ink", "center")
        self._text(cv, S(x0), S(y0 - 10), self._caps("input" if e["direction"] == "in" else "output"), "ui",
                   8 * self.zoom, False, "faint", "w")
        for it in (item, t):
            self._hit(cv, it, lambda k=e["name"]: self.select_pin(k))

    def _draw_gate(self, e, S, hop):
        cv, c, z = self.view, self.c, self.zoom
        info = self.source.instance(e["name"])
        kind = model.symbol(info)
        on = e["arc"] is not None or any(p["on_path"] for p in e["pins"])
        selected = self.selected == "cell:" + e["name"]
        outline = c["ink"] if on or selected else c["faint"]
        fill = c["select"] if selected else c["raised"]
        x0, y0, x1, y1 = e["x0"], e["y0"], e["x1"], e["y1"]
        name = self._text(cv, S(x0 + 4), S(y0 + 12), e["name"], "ui", 11 * z, True, "ink" if on else "muted")
        cell = self._text(cv, S(x1 - 4), S(y0 + 12), e["cell"], "mono", 9 * z, False, "faint", "e")
        for it in (name, cell):
            self._hit(cv, it, lambda k=e["name"]: self.select_cell(k))
        bx0, by0, bx1, by1 = x0 + 24, y0 + model.HEAD - 2, x1 - 24, y1 - model.PAD + 2
        mid = (by0 + by1) / 2.0
        bubble = kind in ("inv", "nand", "nor", "xnor")
        if bubble:
            bx1 -= 8
        stroke = S(2.0 if selected else 1.3)
        pts = self._gate_points(kind, bx0, by0, bx1, by1)
        body = cv.create_polygon(*[S(v) for xy in pts for v in xy], fill=fill, outline=outline, width=stroke,
                                 smooth=False)
        self._hit(cv, body, lambda k=e["name"]: self.select_cell(k))
        if kind in ("xor", "xnor"):
            back = _bezier((bx0 - 7, by0), (bx0 + (bx1 - bx0) * 0.25 - 7, mid), (bx0 - 7, by1))
            cv.create_line(*[S(v) for xy in back for v in xy], fill=outline, width=stroke, smooth=True)
        if bubble:
            cv.create_oval(S(bx1), S(mid - 4), S(bx1 + 8), S(mid + 4), fill=fill, outline=outline, width=stroke)
        for p in e["pins"]:
            colour = c["accent"] if p["on_path"] else c["wire"]
            lead = S(2.0 if p["on_path"] else 1.1)
            if p["side"] == "in":
                edge = self._body_edge(kind, bx0, by0, bx1, by1, p["y"])
                cv.create_line(S(x0), S(p["y"]), S(edge), S(p["y"]), fill=colour, width=lead)
                if kind == "flop":
                    self._text(cv, S(bx0 + 5), S(p["y"]), "▷" if p["clock"] else p["name"], "ui", 10 * z,
                               False, "ink" if p["on_path"] else "muted")
                else:
                    self._text(cv, S(x0 + 3), S(p["y"] - 7), p["name"], "ui", 9 * z, False,
                               "ink" if p["on_path"] else "faint")
            else:
                start = bx1 + (8 if bubble else 0)
                cv.create_line(S(start), S(p["y"]), S(x1), S(p["y"]), fill=colour, width=lead)
                label_x = (bx1 - 5) if kind == "flop" else (x1 - 3)
                self._text(cv, S(label_x), S(p["y"] - (0 if kind == "flop" else 7)), p["name"], "ui",
                           (10 if kind == "flop" else 9) * z, False, "ink" if p["on_path"] else "faint", "e")
            r = 3 if p["on_path"] else 2.5
            dot = cv.create_oval(S(p["x"] - r), S(p["y"] - r), S(p["x"] + r), S(p["y"] + r),
                                 fill=c["accent"] if p["on_path"] else c["raised"],
                                 outline=c["accent"] if p["on_path"] else c["strong"], width=S(1.1))
            self._hit(cv, dot, lambda k=p["pin"]: self.select_pin(k))
        if e["arc"]:
            hot = hop is not None and hop["pin"] == e["arc"]["to"] and hop["kind"] in ("cell", "ckq")
            label = "+" + fmt4(e["arc"]["delay"])
            if self.tab == "trace":      # R41: the winner delay once replayed
                got = self._replayed(e["arc"]["to"])
                label = "+" + fmt4(got[0]["delay"]) if got and got[0]["delay"] is not None else " "
            t = self._text(cv, S((x0 + x1) / 2.0), S(y1 + 9), label, "mono", 10 * z, hot,
                           "ink" if hot else "muted", "center")
            self._hit(cv, t, lambda k=e["arc"]["to"]: self.select_pin(k))

    def _gate_points(self, kind, x0, y0, x1, y1):
        mid, h = (y0 + y1) / 2.0, (y1 - y0)
        if kind in ("buf", "inv"):
            return [(x0, y0 + h * 0.12), (x1, mid), (x0, y1 - h * 0.12)]
        if kind in ("and", "nand"):
            r = h / 2.0
            return [(x0, y0), (x1 - r, y0)] + _arc_points(x1 - r, mid, r, -90, 90) + [(x1 - r, y1), (x0, y1)]
        if kind in ("or", "nor", "xor", "xnor"):
            w = x1 - x0
            front_top = _bezier((x0, y0), (x0 + w * 0.65, y0), (x1, mid))
            front_bot = _bezier((x1, mid), (x0 + w * 0.65, y1), (x0, y1))
            back = _bezier((x0, y1), (x0 + w * 0.25, mid), (x0, y0))
            return front_top + front_bot[1:] + back[1:]
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]

    def _body_edge(self, kind, x0, y0, x1, y1, y):
        """x where an input lead meets the gate body. The OR-family back is the quadratic curve
        (x0, y1) -> (x0 + w/4, mid) -> (x0, y0): y is linear in t, x = x0 + w/2 * t * (1 - t)."""
        if kind in ("or", "nor", "xor", "xnor") and y1 > y0:
            t = min(1.0, max(0.0, (y1 - y) / float(y1 - y0)))
            return x0 + (x1 - x0) / 2.0 * t * (1 - t)
        return x0

    def _draw_stub(self, st, S, below=False):
        cv, c, z = self.view, self.c, self.zoom
        x, y = st["x"], st["y"]
        ly, anchor = (y + 7, "ne") if below else (y - 7, "se")
        if st["state"] == "clock":
            cv.create_line(S(x - 26), S(y), S(x - 4), S(y), fill=c["wire"], dash=(2, 3), width=S(1.1))
            at = "" if self.tab == "trace" else (st["at"] or "")       # R41: no unreplayed numbers
            self._text(cv, S(x - 4), S(ly), "clk %s" % at, "mono", 8 * z, False, "faint", anchor)
            return
        cv.create_line(S(x - model.STUB), S(y), S(x - 4), S(y), fill=c["wire"], width=S(1.1))
        hx = x - model.STUB - 7
        if st["state"] == "expand":
            ring = cv.create_oval(S(hx - 5.5), S(y - 5.5), S(hx + 5.5), S(y + 5.5), fill=c["raised"],
                                  outline=c["muted"], width=S(1.1))
            plus = self._text(cv, S(hx), S(y), "+", "ui", 9 * z, True, "muted", "center")
            for it in (ring, plus):
                self._hit(cv, it, lambda k=st["pin"]: self.expand(k))
        elif st["state"] == "link":
            t = self._text(cv, S(hx), S(y), "↺", "ui", 11 * z, False, "muted", "center")
            self._hit(cv, t, lambda k=st["driver"]: self.select_pin(k))
        else:
            self._text(cv, S(hx), S(y), "·", "ui", 11 * z, True, "faint", "center")
        if st["state"] == "none":
            label = "outside bundle" if self.source.mode == "bundle" else "unconnected"
        else:
            label = "" if self.tab == "trace" else (st["at"] or "")
        t = self._text(cv, S(x - 4), S(ly), label, "mono", 8 * z, False, "faint", anchor)
        self._hit(cv, t, lambda k=st["pin"]: self.select_pin(k))

    def _time_axis(self, cv, t0, t1, x0, x1, y, ticks=8):
        c, P = self.c, self.px
        cv.create_line(x0, y, x1, y, fill=c["strong"])
        step = (t1 - t0) / float(ticks)
        mag = 10 ** math.floor(math.log10(step)) if step > 0 else 1
        step = min((m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= step), default=step)
        t = math.ceil(t0 / step) * step
        X = lambda v: x0 + (v - t0) / (t1 - t0) * (x1 - x0)
        while t <= t1 + 1e-9:
            cv.create_line(X(t), y, X(t), y + P(4), fill=c["strong"])
            self._text(cv, X(t), y + P(14), ("%g" % round(t, 6)), "mono", 9, False, "faint", "center")
            t += step
        return X

    def _draw_waveform(self):
        """Walkthrough §6: both clocks, the data at the endpoint between its earliest and latest
        arrival, the hold and setup windows, and both slacks, each in its own lane."""
        cv, c, P = self.view, self.c, self.px
        w = max(cv.winfo_width(), P(700))
        args = (self.paths.get("setup"), self.paths.get("hold"), self.source.period, self.check)
        t0, t1 = model.waveform(*args)["span"]
        label_w = lambda text: self.font("mono", 9).measure(text) + P(6)
        x0, x1 = P(236), w - max(P(40), label_w(fmt4(t1)) + P(4))     # the last edge label still fits
        wave = model.waveform(*args, text_width=label_w, axis_px=x1 - x0)
        X = lambda v: x0 + (v - t0) / (t1 - t0) * (x1 - x0)
        self._eyebrow(cv, P(24), P(18), "timing diagram · setup and hold of %s" % self.endpoint)
        lanes = {"launch": P(64), "capture": P(120), "data": P(180)}
        clocks = [r for r in wave["rows"] if r["kind"] == "clock"]
        data = [r for r in wave["rows"] if r["kind"] == "data"][0]
        arrows = sorted(wave["marks"], key=lambda m: m["kind"] != "hold")
        arrow_y = dict((m["kind"], P(238 + 46 * i)) for i, m in enumerate(arrows))
        axis_y = P(238 + 46 * len(arrows) + 2)
        cv.configure(scrollregion=(0, 0, w, max(axis_y + P(40), cv.winfo_height())))
        top, bottom = lanes["capture"] - P(18), lanes["data"] + P(10)
        for m in wave["marks"]:          # windows first, under everything
            wa, wb = X(min(m["window"])), X(max(m["window"]))
            cv.create_rectangle(wa, top, max(wb, wa + P(2)), bottom, fill=c[m["kind"] + "_soft"], outline="")
            cv.create_line(X(m["required"]), top, X(m["required"]), arrow_y[m["kind"]] + P(6), fill=c[m["kind"]],
                           dash=(4, 3), width=P(1.2))
        for row, lane in zip(clocks, (lanes["launch"], lanes["capture"])):
            self._text(cv, P(24), lane - P(6), row["name"], "ui", 12, False, "ink")
            self._text(cv, P(24), lane + P(10), row["pin"] or "", "ui", 10, False, "faint")
            hi, lo = lane - P(14), lane + P(6)
            period = row["period"]
            t = row["edges"][0] - period * math.ceil((row["edges"][0] - t0) / period)
            pts = [(x0, lo)]
            while t < t1:
                for a, level in ((t, hi), (t + period / 2.0, lo)):
                    if t0 <= a <= t1:
                        pts += [(X(a), pts[-1][1]), (X(a), level)]
                t += period
            for t, text, anchor in row["labels"]:
                self._text(cv, X(t) + P(3 if anchor == "w" else -3), lo + P(11), text, "mono", 9, False, "faint", anchor)
            pts.append((x1, pts[-1][1]))
            cv.create_line(*[v for xy in pts for v in xy], fill=c["muted"], width=P(1.4))
        lane = lanes["data"]
        self._text(cv, P(24), lane - P(6), data["name"], "ui", 12, False, "ink")
        self._text(cv, P(24), lane + P(10), "old → new data", "ui", 10, False, "faint")
        early, late = data["early"], data["late"]
        a = X(early) if early is not None else X(late)
        b = X(late) if late is not None else X(early)
        hi, lo = lane - P(12), lane + P(8)
        for xa, xb, label in ((x0, a, "old data"), (b, x1, "new data")):
            if xb > xa:
                cv.create_line(xa, hi, xb, hi, fill=c["ink"], width=P(1.3))
                cv.create_line(xa, lo, xb, lo, fill=c["ink"], width=P(1.3))
                if xb - xa > P(80):
                    self._text(cv, (xa + xb) / 2.0, lane - P(2), label, "ui", 10, False, "faint", "center")
        if b > a:
            cv.create_rectangle(a, hi, b, lo, fill=c["head"], outline="")
            xs = a
            while xs < b:
                cv.create_line(xs, lo, min(b, xs + P(10)), hi, fill=c["strong"])
                xs += P(7)
            if b - a > P(130):
                t = self._text(cv, (a + b) / 2.0, lane - P(2), "changing", "ui", 10, False, "muted", "center")
                x0_, y0_, x1_, y1_ = cv.bbox(t)
                cv.tag_lower(cv.create_rectangle(x0_ - P(4), y0_, x1_ + P(4), y1_, fill=c["head"], outline=""), t)
        for x in (a, b):
            cv.create_line(x, hi, x, lo, fill=c["ink"], width=P(1.3))
        for x, value, word, kind, side in ((a, early, "earliest", "hold", "ne"), (b, late, "latest", "setup", "nw")):
            if value is None:
                continue
            label = "%s %s" % (word, fmt4(value))
            half = self.font("mono", 9).measure(label) / 2.0
            anchor = side if b - a < P(160) else "n"        # apart when the edges are close
            if x + half * (2 if anchor == "nw" else 1) > w - P(8):
                anchor = "ne"
            self._text(cv, x, lo + P(11), label, "mono", 9, False, kind, anchor)
        for m in arrows:
            y = arrow_y[m["kind"]]
            colour = "bad" if _neg(m["slack"]) else m["kind"]
            ra, ar = X(m["required"]), X(m["arrival"])
            cv.create_line(min(ra, ar), y, max(ra, ar), y, fill=c[colour], width=P(1.6), arrow="both",
                           arrowshape=(P(7), P(8), P(3)))
            label = "%s slack %s" % (m["kind"], fmt4(m["slack"]))
            self._text(cv, P(24), y, "%s check" % m["kind"], "ui", 12, False, "ink")
            if abs(ra - ar) > P(150):
                self._text(cv, (ra + ar) / 2.0, y - P(10), label, "mono", 10, True, colour, "center")
            elif max(ra, ar) + P(10) + self.font("mono", 10, True).measure(label) < w - P(8):
                self._text(cv, max(ra, ar) + P(10), y, label, "mono", 10, True, colour, "w")
            else:
                self._text(cv, min(ra, ar) - P(10), y, label, "mono", 10, True, colour, "e")
            self._text(cv, ra, y + P(12), "req %s" % fmt4(m["required"]), "mono", 9, False, m["kind"],
                       "ne" if ra < ar or ra > x1 - P(100) else "nw")
        self._time_axis(cv, t0, t1, x0, x1, axis_y)
        self._text(cv, P(24), axis_y + P(6), "time (ns)", "ui", 10, False, "faint")

    # centre: path table ---------------------------------------------------------------

    def _draw_table(self):
        """Three sections, no row rules: whitespace and one strong rule above the slack."""
        cv, c, P = self.table, self.c, self.px
        self._clear(cv)
        w = max(cv.winfo_width(), P(700))
        path = self.path()
        if not path:
            return
        xs, x, row_h = [], P(24), P(ROW)
        for title, width, anchor in TABLE:
            xs.append((x, P(width), anchor))
            self._text(cv, x + (P(width - 6) if anchor == "e" else 0), P(20), self._caps(title), "ui", 9, True, "faint",
                       anchor)
            x += P(width)
        right = x
        cv.create_line(P(24), P(34), max(w - P(24), right), P(34), fill=c["line"])
        num = lambda k: xs[k][0] + xs[k][1] - P(6)       # right edge of a number column
        trace = self.tab == "trace"
        sections, slack = model.path_table(path, self.source), path["slack"]
        if trace:                        # R41: replayed numbers only; not reached = blank
            sections, slack = model.trace_table(sections, path, self.replay)
        blank = lambda v, f=fmt4: "" if v is None else f(v)
        signed = lambda v: "" if v is None else ("+" if v >= 0 else "") + fmt4(v)
        y = P(42)
        for sec in sections:
            self._eyebrow(cv, P(24), y + P(12), sec["title"])
            rows = sec["rows"]
            if sec["title"] == "Data path" and rows and not trace:
                self._text(cv, num(8), y + P(12), "Σ " + fmt4(model.summary(path)["data_path"]), "mono", 10, False,
                           "faint", "e")
            y += P(26)
            for r in rows:
                idx = r.get("index")
                on = idx is not None and idx == self.stage
                mid = y + row_h / 2.0
                if on:
                    _rounded(cv, P(12), y + P(1), max(w - P(12), right), y + row_h - P(1), P(5), fill=c["select"],
                             outline="")
                if "arc" in r:
                    cell_row = r["kind"] in ("cell", "ckq")
                    values = [r["label"], r["cell"] or "port", r["arc"], r["rf"],
                              _num(r["load"]) if r["load"] is not None else "",
                              "" if r["fanout"] is None else str(r["fanout"]),
                              blank(r["slew"]) if trace else _num(r["slew"]), signed(r["incr"]), blank(r["value"]),
                              blank(r["rat"]) if trace else _num(r["rat"]), blank(r["slack"]) if trace else _num(r["slack"])]
                    for k, (v, (cx, cw, anchor)) in enumerate(zip(values, xs)):
                        colour = "ink"
                        if k in (1, 2, 3, 4, 5, 6, 9):
                            colour = "muted"
                        elif k == 7 and not cell_row:
                            colour = "faint"
                        elif k == 10 and r["slack"] is not None:
                            colour = "bad" if _neg(r["slack"]) else "ok"
                        bold = (k == 0 and on) or (k == 7 and r["largest"])
                        self._text(cv, cx + (cw - P(6) if anchor == "e" else 0), mid, v, "ui" if k < 4 else "mono",
                                   12 if k < 4 else 11, bold, colour, anchor)
                    hit = cv.create_rectangle(0, y, w, y + row_h, outline="", fill="")
                    self._hit(cv, hit, lambda k=idx: self.select_stage(k))
                else:
                    label = r["label"] + ("  (%s)" % r["cell"] if r.get("cell") else "")
                    self._text(cv, xs[0][0], mid, label, "ui", 12, False, "ink" if r.get("cell") else "muted")
                    if r.get("incr") is not None:
                        self._text(cv, num(7), mid, signed(r["incr"]), "mono", 11, False, "muted", "e")
                    if r["value"] is not None:
                        self._text(cv, num(8), mid, fmt4(r["value"]), "mono", 11, r["label"] == "required", "ink", "e")
                    if idx is not None:
                        hit = cv.create_rectangle(0, y, w, y + row_h, outline="", fill="")
                        self._hit(cv, hit, lambda k=idx: self.select_stage(k))
                y += row_h
            y += P(10)
        bad = slack is not None and _neg(slack)
        cv.create_line(P(24), y, right, y, fill=c["strong"])
        mid = y + row_h / 2.0 + P(4)
        parts = [("slack", "ui", 12, True, "ink", 10)]
        if slack is not None:
            parts.append((self._caps("violated" if bad else "met"), "ui", 9, True, "bad" if bad else "ok", 0))
            self._text(cv, num(8), mid, fmt4(slack), "mono", 12, True, "bad" if bad else "ok", "e")
        self._run(cv, P(24), mid, parts)
        note = self._text(cv, right + P(12), mid, "pin slack: the worst slack through the pin", "ui", 10, False, "faint")
        cv.configure(scrollregion=(0, 0, max(w, cv.bbox(note)[2] + P(12)), y + row_h + P(24)))

    # right: inspector -----------------------------------------------------------------------

    def _draw_inspector(self):
        cv, c, P = self.insp, self.c, self.px
        self._clear(cv)
        w = max(cv.winfo_width(), P(MIN_RIGHT))
        sel = self.selected
        y = P(34)
        if self.tab == "trace" and self.replay is not None:
            self._inspect_step(y)
            return
        if not sel:
            return
        if sel.startswith("cell:"):
            self._inspect_cell(sel[5:], y)
            return
        info = self.source.pin(sel)
        self._text(cv, P(20), y, sel, "ui", 16, True, "ink")
        y += P(22)
        path = self.path()
        point = None
        if path and self.stage is not None and path["points"][self.stage]["pin"] == sel:
            point = path["points"][self.stage]
        if info is None:
            self._text(cv, P(20), y, "not in this bundle", "ui", 11, False, "muted")
            return
        kind = {"PI": "input port", "PO": "output port", "CK": "clock pin", "D": "data pin · endpoint",
                "clock_port": "clock port"}.get(info["kind"])
        if kind is None:
            pins = self.source.instance(sel.split("/")[0])["pins"]
            kind = [p["direction"] for p in pins if p["name"] == sel.split("/")[1]][0] + " pin"
        self._text(cv, P(20), y, "%s%s" % ((info["cell"] + " · ") if info["cell"] else "", kind), "ui", 11, False,
                   "muted")
        y += P(28)
        y = self._values_card(info, y)
        if point is not None:
            y = self._lookup_card(point, y)
        rf = point["rf"] if point is not None else (self.source.arrival(sel, self.check) or (None, "r"))[1]
        y = self._merge_card("arrival set by", self.source.fanin(sel, self.check, rf), "from", rf, y)
        y = self._merge_card("required set by", self.source.fanout(sel, self.check, rf), "to", rf, y)
        cv.configure(scrollregion=(0, 0, w, y + P(20)))

    def _inspect_step(self, y):
        """R41: the current trace entry - its pin's values as far as the replay has reached
        (blank otherwise), then the entry itself, candidates winner first."""
        P, cv, replay = self.px, self.insp, self.replay
        w = max(cv.winfo_width(), P(MIN_RIGHT))
        x = replay.current
        if x is None:
            self._text(cv, P(20), y, replay.label, "ui", 12, False, "muted")
            return
        pin = x["pin"]
        self._text(cv, P(20), y, pin, "ui", 16, True, "ink")
        how = x.get("mode") or x.get("kind")
        self._text(cv, P(20), y + P(22), " · ".join(v for v in (how, x.get("rf"), replay.label) if v), "ui", 11, False,
                   "muted")
        y += P(50)
        info = self.source.pin(pin) or {"load": None}
        values = {"at": {}, "rat": {}, "slew": {}, "load": info["load"], "fanout": info.get("fanout"),
                  "slack": {}}
        for m in ("late", "early"):
            for key in ("at", "rat", "slew"):
                values[key][m] = {}
            for rf in ("r", "f"):
                f = replay.forward(pin, m, rf) or {}
                values["at"][m][rf], values["slew"][m][rf] = f.get("at"), f.get("slew")
                values["rat"][m][rf] = replay.rat(pin, m, rf)
        for kind in ("setup", "hold"):
            p = self.paths.get(kind)
            end = p["points"][-1] if p and p["points"][-1]["pin"] == pin else None
            values["slack"][kind] = replay.slack(pin, kind, end["rf"]) if end else None
        y = self._values_card(values, y, blank=True)
        rows = []                        # (left, right, bold): every number from the entry
        if x["phase"] == "forward":
            title = "forward · %s %s" % (x["mode"], x["rf"])
            rows.append(("AT", fmt4(x["at"]), True))
            rows.append(("slew (worst)", fmt4(x["slew"]), False))
            if x["source"]:
                rows.append(("source", x["source"], False))
        elif x["phase"] == "backward":
            title = "backward · %s %s" % (x["mode"], x["rf"])
            rows.append(("RAT", fmt4(x["rat"]), True))
        elif x["phase"] == "check":
            title = "check · %s %s" % (x["kind"], x["rf"])
            rows.append(("RAT", fmt4(x["rat"]), True))
            terms = (("ck_at", x["ck_at"]), ("period", x["period"] if x["kind"] == "setup" else None), ("t", x["t"]),
                     ("uncertainty", x["uncertainty"]), ("output_delay", x["output_delay"]),
                     ("d_slew", x["d_slew"]), ("ck_slew", x["ck_slew"]))
            rows += [(name, fmt4(v), False) for name, v in terms if v is not None]
            if x["ck"]:
                rows.append(("clock pin", x["ck"], False))
        elif x["phase"] == "slack":
            title = "slack · %s %s" % (x["kind"], x["rf"])
            rows += [("AT", _num(x["at"]), False), ("RAT", _num(x["rat"]), False), ("slack", _num(x["slack"]), True)]
        else:
            title = "worst %s path" % x["kind"]
            rows += [("%d" % (i + 1), "%s %s" % (n, rf), False) for i, (n, rf) in enumerate(x["points"])]
        y = self._section(cv, y, title, w)
        for left, right, bold in rows:
            self._text(cv, P(20), y, left, "ui", 11, False, "muted")
            self._text(cv, w - P(20), y, right, "mono", 11, bold, "ink", "e")
            y += P(22)
        cands = model.Replay.ordered(x)
        if cands:
            forward = x["phase"] == "forward"
            y = self._section(cv, y + P(8), "candidates · %d · winner first" % len(cands), w)
            for i, cand in enumerate(cands):
                self._text(cv, P(20), y, "●" if i == 0 else "○", "ui", 8, False, "ink" if i == 0 else "faint")
                self._text(cv, P(34), y, "%s  %s" % (cand["src"] if forward else cand["dst"], cand["rf"]), "ui", 12,
                           i == 0, "ink" if i == 0 else "muted")
                self._text(cv, w - P(20), y, fmt4(cand["value"]), "mono", 11, i == 0, "ink" if i == 0 else "muted", "e")
                expr = ("AT %s + %s" if forward else "RAT %s − %s") % (fmt4(cand["at" if forward else "rat"]),
                                                                       fmt4(cand["delay"]))
                self._text(cv, P(34), y + P(17), expr, "mono", 10, False, "faint")
                y += P(44)
        cv.configure(scrollregion=(0, 0, w, y + P(20)))

    def _values_card(self, info, y, blank=False):
        """AT / RAT / slew, slacks, load; `blank`: None is drawn empty (R41: not reached)."""
        _num = (lambda v: "" if v is None else fmt4(v)) if blank else globals()["_num"]
        P = self.px
        cv, w = self.insp, max(self.insp.winfo_width(), P(MIN_RIGHT))
        y = self._section(cv, y, "timing", w)
        x = [w - P(206), w - P(144), w - P(82), w - P(20)]     # right edges: late r, late f, early r, early f
        self._eyebrow(cv, x[1], y - P(2), "late", "e")
        self._eyebrow(cv, x[3], y - P(2), "early", "e")
        for i, rf in enumerate(("r", "f", "r", "f")):
            self._text(cv, x[i], y + P(16), rf, "mono", 9, False, "faint", "e")
        yy = y + P(38)
        for label, vals in (("AT", info["at"]), ("RAT", info["rat"]), ("slew", info["slew"])):
            self._text(cv, P(20), yy, label, "ui", 11, False, "muted")
            for i, (m, rf) in enumerate((("late", "r"), ("late", "f"), ("early", "r"), ("early", "f"))):
                self._text(cv, x[i], yy, _num(vals[m][rf]), "mono", 10, False, "ink", "e")
            yy += P(22)
        yy += P(10)
        for label, v in (("setup slack", info["slack"]["setup"]), ("hold slack", info["slack"]["hold"]), ("load", info["load"])):
            if v is None and label == "load":
                continue
            colour = "ink" if label == "load" else ("faint" if v is None else ("bad" if _neg(v) else "ok"))
            self._text(cv, P(20), yy, label, "ui", 11, False, "muted")
            self._text(cv, w - P(20), yy, _num(v), "mono", 11, False, colour, "e")
            if label == "load" and info.get("fanout") is not None:
                self._run(cv, w - P(170), yy, [("fanout", "ui", 10, False, "faint", 5),
                                               (str(info["fanout"]), "mono", 11, False, "ink", 0)])
            yy += P(22)
        return yy + P(8)

    def _lookup_card(self, point, y):
        """Why this stage costs what it costs: the table lookup behind the delay (walkthrough §10)."""
        P = self.px
        cv, w = self.insp, max(self.insp.winfo_width(), P(MIN_RIGHT))
        path = self.path()
        pts = path["points"]
        k = self.stage
        if point["arc"] in ("cell", "ckq"):
            prev = pts[k - 1]
            title = "delay lookup · %s %s→%s" % (point["cell"], prev["pin"].split("/")[-1], point["pin"].split("/")[-1])
            lines = [("input slew", "%s  %s %s" % (fmt4(prev["slew"]), prev["pin"], prev["rf"])),
                     ("output load", _num(point["cap"])),
                     ("→ delay", "%s  %s→%s" % (fmt4(point["incr"]), prev["rf"], point["rf"])),
                     ("→ output slew", fmt4(point["slew"]))]
        elif k == len(pts) - 1 and path["capture"]["pin"] is not None:
            ck = self.source.pin(path["capture"]["pin"])
            mode = model.MODE[self.check]
            title = "constraint lookup · %s" % ("setup_rising" if self.check == "setup" else "hold_rising")
            lines = [("D slew", "%s  %s" % (fmt4(point["slew"]), point["rf"])),
                     ("CK slew", _num(ck["slew"][mode]["r"]) if ck else "—"),
                     ("→ t_%s" % self.check, fmt4(path["capture"]["check"]))]
        elif point["arc"] == "net":
            title = "net"
            lines = [("delay", "0, ideal wire"), ("slew", "copied from the driver")]
        else:
            title = "launch"
            lines = [("start", "%s at %s" % (point["pin"], fmt4(point["at"])))]
        grids = dict(model.lookups(path, self.source, k))      # engine mode only
        yy = self._section(cv, y, title, w)
        for label, value in lines:
            result = label.startswith("→")
            self._text(cv, P(20), yy, label, "ui", 11, False, "ink" if result else "muted")
            self._text(cv, w - P(20), yy, value, "mono", 11, result, "ink", "e")
            yy += P(22)
            if result and label[2:] in grids:
                yy = self._lookup_grid(grids[label[2:]], yy - P(2))
        return yy + P(8)

    def _lookup_grid(self, d, y):
        """One lookup.lookup_detail block under its result line: each axis (row = the table's
        first variable, col = its second) with its query value and, when outside the grid,
        `extrapolated below / above`; then the four corner values under the bracketing index
        values."""
        P = self.px
        cv, w = self.insp, max(self.insp.winfo_width(), P(MIN_RIGHT))
        for tag, name, query, side in zip(("row", "col"), d["axes"], d["query"], d["extrapolated"]):
            _, x, _ = self._run(cv, P(34), y, [(tag, "ui", 9, False, "faint", 6), (name, "ui", 10, False, "muted", 0)])
            if x + P(8) > w - P(20) - self.font("mono", 10).measure(fmt4(query)):
                y += P(16)               # a long axis name: its value goes under it
            self._text(cv, w - P(20), y, fmt4(query), "mono", 10, False, "ink", "e")
            y += P(16)
            if side:
                self._text(cv, P(58), y, "extrapolated " + side, "ui", 10, False, "bad")
                y += P(16)
        cols = (w - P(96), w - P(20))
        (row_lo, row_hi), (col_lo, col_hi) = d["bracket"]
        for x, v in zip(cols, (col_lo, col_hi)):
            self._text(cv, x, y, fmt4(v), "mono", 10, False, "faint", "e")
        y += P(16)
        for i, v in enumerate((row_lo, row_hi)):
            self._text(cv, w - P(172), y, fmt4(v), "mono", 10, False, "faint", "e")
            for x, corner in zip(cols, d["corners"][i]):
                self._text(cv, x, y, fmt4(corner), "mono", 10, False, "ink", "e")
            y += P(16)
        return y + P(8)

    def _merge_card(self, title, cands, key, rf, y):
        P = self.px
        cv, w = self.insp, max(self.insp.winfo_width(), P(MIN_RIGHT))
        if not cands:
            return y
        mode_word = ("max" if self.check == "setup" else "min") if key == "from" else ("min" if self.check == "setup" else "max")
        limit = model.near_critical(self.source.period)
        yy = self._section(cv, y, "%s · %s of %d · %s" % (title, mode_word, len(cands), rf), w)
        self._text(cv, P(20), yy - P(6), "near-critical: margin < %s" % fmt4(limit), "mono", 9, False, "faint")
        yy += P(16)
        for i, cand in enumerate(cands):
            pin = cand[key]
            win = i == 0
            self._text(cv, P(20), yy, "●" if win else "○", "ui", 8, False, "ink" if win else "faint")
            t = self._text(cv, P(34), yy, "%s  %s" % (pin, cand["rf"]), "ui", 12, win, "ink" if win else "muted")
            self._text(cv, w - P(20), yy, fmt4(cand["value"]), "mono", 11, win, "ink" if win else "muted", "e")
            if key == "from":
                expr = "AT %s + %s %s" % (fmt4(cand["at"]), cand["kind"], fmt4(cand["delay"]))
            else:
                expr = "RAT %s − %s %s" % (fmt4(cand["rat"]), cand["kind"], fmt4(cand["delay"]))
            e = self._text(cv, P(34), yy + P(17), expr, "mono", 10, False, "faint")
            extra = 0                    # the margin goes under the expression when both do not fit
            if not win:
                near = model.is_near(cand["margin"], self.source.period)
                margin = "Δ %s" % fmt4(cand["margin"])
                if cv.bbox(e)[2] + P(8) > w - P(20) - self.font("mono", 10).measure(margin):
                    extra = P(15)
                self._text(cv, w - P(20), yy + P(17) + extra, margin, "mono", 10, False, "bad" if near else "faint", "e")
            hit = cv.create_rectangle(P(12), yy - P(12), w - P(12), yy + P(26) + extra, outline="", fill="")
            for it in (t, hit):
                self._hit(cv, it, lambda k=pin: self.select_pin(k))
            yy += P(44) + extra
        return yy

    def _inspect_cell(self, inst, y):
        P = self.px
        cv, w = self.insp, max(self.insp.winfo_width(), P(MIN_RIGHT))
        info = self.source.instance(inst)
        self._text(cv, P(20), y, inst, "ui", 16, True, "ink")
        self._text(cv, P(20), y + P(22), "%s · %s" % (info["cell"], model.symbol(info)), "ui", 11, False, "muted")
        y += P(50)
        for a in self.source.arcs(inst):
            late = [(ab, v) for ab, v in sorted(a["delay"]["late"].items()) if v is not None]
            yy = self._section(cv, y, "%s → %s · %s" % (a["from"].split("/")[-1], a["to"].split("/")[-1], a["kind"]), w)
            for ab, v in late:
                self._text(cv, P(20), yy, "late %s→%s" % (ab[0], ab[1]), "ui", 11, False, "muted")
                self._text(cv, w - P(20), yy, fmt4(v), "mono", 11, False, "ink", "e")
                yy += P(22)
            y = yy + P(4)
        cv.configure(scrollregion=(0, 0, w, y + P(20)))

    def _draw_status(self):
        cv, c = self.status, self.c
        self._clear(cv)
        w = max(cv.winfo_width(), self.min_width)
        cv.create_line(0, 0, w, 0, fill=c["line"])
        self._text(cv, self.px(20), self.px(13), HINT, "ui", 10, False, "faint")
