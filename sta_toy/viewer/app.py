"""Tk window (R29, viewer_p4.md). One focus: the selected endpoint's worst path.

Header (endpoint, check, slack, SETUP|HOLD, previous / next endpoint, WNS / TNS / NVP, theme),
the endpoint list, the path schematic (cells as modules, wired pin to pin), the stage table
(one row per pin, then the capture side), an inspector for the selected pin or cell, and a
status bar. Themes switch at runtime by rebuilding the widgets; the state is kept."""

import tkinter as tk
import tkinter.font as tkfont

from sta_toy.tsv import fmt4
from sta_toy.viewer import model, theme

ROW = 26
TABLE = [("#", 34, "e"), ("pin", 120, "w"), ("cell", 64, "w"), ("arc", 64, "w"), ("rf", 50, "w"),
         ("Δ", 76, "e"), ("AT", 80, "e"), ("slew", 70, "e"), ("", 170, "w")]
HINT = ("←/→ step pin to pin   ↑/↓ endpoint   click ⊕ to expand a side input   "
        "drag to pan   ⌘/Ctrl-scroll to zoom   F fit")


def _num(v):
    return "NA" if v is None else fmt4(v)


def _rounded(canvas, x0, y0, x1, y1, r, **kw):
    """A rounded rectangle as a smoothed polygon."""
    r = min(r, (x1 - x0) / 2.0, (y1 - y0) / 2.0)
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
           x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return canvas.create_polygon(pts, smooth=True, splinesteps=12, **kw)


class App:
    def __init__(self, root, source, theme_name="light"):
        self.root, self.source = root, source
        self.endpoints = model.EndpointList(source.rows())
        self.check, self.endpoint, self.paths = "setup", None, {"setup": None, "hold": None}
        self.expansions = {}      # (endpoint, check) -> side inputs expanded, in order
        self.selected, self.stage = None, None
        self.zoom, self.layout, self.rows = 1.0, None, []
        self.errors = []
        root.report_callback_exception = lambda *exc: self.errors.append(exc[1])
        families = set(tkfont.families(root))
        self.ui = theme.pick_font(theme.UI_FONTS, families)
        self.mono = theme.pick_font(theme.MONO_FONTS, families)
        self.fonts = {
            "title": tkfont.Font(root, family=self.ui, size=17, weight="bold"),
            "ui": tkfont.Font(root, family=self.ui, size=13),
            "ui_b": tkfont.Font(root, family=self.ui, size=13, weight="bold"),
            "small": tkfont.Font(root, family=self.ui, size=11),
            "small_b": tkfont.Font(root, family=self.ui, size=11, weight="bold"),
            "mono": tkfont.Font(root, family=self.mono, size=12),
            "mono_b": tkfont.Font(root, family=self.mono, size=12, weight="bold"),
            "mono_s": tkfont.Font(root, family=self.mono, size=11)}
        self.zfonts = {}
        root.title("STA Timer — %s" % source.design_name)
        root.geometry("1440x880")
        root.minsize(1000, 620)
        self.set_theme(theme_name)
        first = self.endpoints.neighbour(None, 0)
        if first:
            self.select_endpoint(first)
        self._bind_keys()

    # ------------------------------------------------------------------ widgets

    def set_theme(self, name):
        self.theme_name = name
        self.c = theme.THEMES[name]
        for w in self.root.winfo_children():
            w.destroy()
        self._build()
        if self.endpoint:
            self.refresh(fit=False)

    def _label(self, parent, text="", font="ui", fg="ink", bg="panel", **kw):
        return tk.Label(parent, text=text, font=self.fonts[font], fg=self.c[fg], bg=self.c[bg], **kw)

    def _button(self, parent, text, command, bg="panel", fg="ink", font="small_b", padx=10):
        b = self._label(parent, text, font=font, fg=fg, bg=bg, padx=padx, pady=4, cursor="hand2")
        b.bind("<Button-1>", lambda e: command())
        return b

    def _build(self):
        c, root = self.c, self.root
        root.configure(bg=c["bg"])
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)

        head = tk.Frame(root, bg=c["panel"], highlightthickness=0)
        head.grid(row=0, column=0, sticky="ew")
        tk.Frame(root, bg=c["line"], height=1).grid(row=0, column=0, sticky="sew")
        self.title = self._label(head, font="title")
        self.title.pack(side="left", padx=(18, 8), pady=10)
        self.chip = self._label(head, font="small_b", padx=10, pady=3)
        self.chip.pack(side="left", padx=4)
        self.info = self._label(head, font="small", fg="muted")
        self.info.pack(side="left", padx=12)
        menu_button = tk.Menubutton(head, text="Theme: %s" % self.theme_name, font=self.fonts["small"],
                                    fg=c["ink"], bg=c["panel"], activebackground=c["select"],
                                    relief="flat", highlightthickness=0, cursor="hand2")
        menu = tk.Menu(menu_button, tearoff=0)
        for name in theme.NAMES:
            menu.add_command(label=name, command=lambda n=name: self.set_theme(n))
        menu_button.configure(menu=menu)
        menu_button.pack(side="right", padx=(6, 16))
        self.summary = self._label(head, font="mono_s", fg="muted")
        self.summary.pack(side="right", padx=10)
        nav = tk.Frame(head, bg=c["panel"])
        nav.pack(side="right", padx=6)
        self._button(nav, "◀", lambda: self.next_endpoint(-1)).pack(side="left")
        self._button(nav, "▶", lambda: self.next_endpoint(1)).pack(side="left")
        seg = tk.Frame(head, bg=c["strong"], padx=1, pady=1)
        seg.pack(side="right", padx=10)
        self.seg = {}
        for check in ("setup", "hold"):
            self.seg[check] = self._button(seg, check.upper(), lambda k=check: self.set_check(k), padx=14)
            self.seg[check].pack(side="left")

        body = tk.PanedWindow(root, orient="horizontal", sashwidth=1, bg=c["line"], bd=0,
                              sashrelief="flat", showhandle=False)
        body.grid(row=1, column=0, sticky="nsew")

        left = tk.Frame(body, bg=c["panel"])
        self._label(left, "ENDPOINTS", font="small_b", fg="faint").pack(anchor="w", padx=16, pady=(14, 6))
        self.filter_var = tk.StringVar(value=self.endpoints.text)
        entry = tk.Entry(left, textvariable=self.filter_var, font=self.fonts["ui"], bg=c["raised"],
                         fg=c["ink"], insertbackground=c["ink"], relief="flat",
                         highlightthickness=1, highlightbackground=c["strong"], highlightcolor=c["focus"])
        entry.pack(fill="x", padx=14, pady=(0, 8), ipady=4)
        self.filter_var.trace_add("write", lambda *a: self.set_filter(self.filter_var.get()))
        self.elist = tk.Canvas(left, bg=c["panel"], highlightthickness=0, bd=0, width=250)
        self.elist.pack(fill="both", expand=True)
        self.elist.bind("<Button-1>", self._on_list_click)
        self._wheel(self.elist, vertical_only=True)
        body.add(left, minsize=200, width=260, stretch="never")

        center = tk.PanedWindow(body, orient="vertical", sashwidth=1, bg=c["line"], bd=0,
                                sashrelief="flat")
        top = tk.Frame(center, bg=c["bg"])
        bar = tk.Frame(top, bg=c["bg"])
        bar.pack(fill="x")
        self.path_title = self._label(bar, font="small_b", fg="faint", bg="bg")
        self.path_title.pack(side="left", padx=16, pady=(10, 4))
        for text, cmd in (("Fit", self.fit), ("−", lambda: self.set_zoom(self.zoom / 1.2)),
                          ("+", lambda: self.set_zoom(self.zoom * 1.2)), ("Collapse", self.collapse)):
            self._button(bar, text, cmd, bg="bg", fg="muted").pack(side="right", padx=2, pady=(8, 2))
        self.sch = tk.Canvas(top, bg=c["bg"], highlightthickness=0, bd=0)
        self.sch.pack(fill="both", expand=True)
        self.sch.bind("<ButtonPress-1>", self._on_sch_press)
        self.sch.bind("<B1-Motion>", lambda e: self.sch.scan_dragto(e.x, e.y, gain=1))
        self.sch.bind("<Configure>", lambda e: self._fit_once())
        self._wheel(self.sch)
        center.add(top, minsize=220, height=470, stretch="always")

        bottom = tk.Frame(center, bg=c["bg"])
        tk.Frame(bottom, bg=c["line"], height=1).pack(fill="x")
        self.thead = tk.Canvas(bottom, bg=c["bg"], highlightthickness=0, bd=0, height=ROW + 6)
        self.thead.pack(fill="x")
        self.table = tk.Canvas(bottom, bg=c["bg"], highlightthickness=0, bd=0)
        self.table.pack(fill="both", expand=True)
        self.table.bind("<Button-1>", self._on_table_click)
        self._wheel(self.table, vertical_only=True)
        center.add(bottom, minsize=150, stretch="never")
        body.add(center, minsize=500, stretch="always")

        right = tk.Frame(body, bg=c["panel"])
        self._label(right, "INSPECTOR", font="small_b", fg="faint").pack(anchor="w", padx=16, pady=(14, 6))
        self.inspector = tk.Text(right, bg=c["panel"], fg=c["ink"], font=self.fonts["mono_s"],
                                 relief="flat", highlightthickness=0, wrap="none", width=34,
                                 padx=14, pady=4, cursor="arrow")
        self.inspector.pack(fill="both", expand=True)
        for tag, opts in (("h", {"font": self.fonts["title"]}),
                          ("sub", {"font": self.fonts["small"], "foreground": c["muted"]}),
                          ("eye", {"font": self.fonts["small_b"], "foreground": c["faint"]}),
                          ("ok", {"foreground": c["ok"]}), ("bad", {"foreground": c["bad"]}),
                          ("muted", {"foreground": c["muted"]}), ("b", {"font": self.fonts["mono_b"]})):
            self.inspector.tag_configure(tag, **opts)
        self.inspector.configure(state="disabled")
        body.add(right, minsize=240, width=300, stretch="never")

        self.status = self._label(root, HINT, font="small", fg="faint", anchor="w", padx=16, pady=5)
        self.status.grid(row=2, column=0, sticky="ew")
        self._fitted = False

    def _wheel(self, canvas, vertical_only=False):
        canvas.configure(xscrollincrement=1, yscrollincrement=1)

        def scroll(event, horizontal=False):
            # Tk 9 reports 120 per wheel notch; scroll in pixels like Tk's own text widget.
            px = int(-event.delta / 4.0) or (-1 if event.delta > 0 else 1)
            (canvas.xview_scroll if horizontal else canvas.yview_scroll)(px, "units")

        def touchpad(event):
            # <TouchpadScroll>: dx in the high 16 bits, dy in the signed low 16 bits.
            d = int(event.delta)
            dx, dy = d >> 16, ((d & 0xFFFF) ^ 0x8000) - 0x8000
            if not vertical_only and dx:
                canvas.xview_scroll(-dx, "units")
            if dy:
                canvas.yview_scroll(-dy, "units")
        try:
            canvas.bind("<TouchpadScroll>", touchpad)
        except tk.TclError:                     # Tk 8.6 has no touchpad events
            pass

        def zoom(event):
            self.set_zoom(self.zoom * (1.1 if event.delta > 0 else 1 / 1.1))
        canvas.bind("<MouseWheel>", scroll)
        if not vertical_only:
            canvas.bind("<Shift-MouseWheel>", lambda e: scroll(e, True))
            canvas.bind("<Command-MouseWheel>" if self.root.tk.call("tk", "windowingsystem") == "aqua"
                        else "<Control-MouseWheel>", zoom)

    def _bind_keys(self):
        def unless_typing(fn):
            return lambda e: None if isinstance(e.widget, tk.Entry) else fn()
        self.root.bind("<Left>", unless_typing(lambda: self.step(-1)))
        self.root.bind("<Right>", unless_typing(lambda: self.step(1)))
        self.root.bind("<Up>", unless_typing(lambda: self.next_endpoint(-1)))
        self.root.bind("<Down>", unless_typing(lambda: self.next_endpoint(1)))
        self.root.bind("<Key-f>", unless_typing(self.fit))

    # ------------------------------------------------------------------ state changes

    @property
    def expanded(self):
        return self.expansions.setdefault((self.endpoint, self.check), [])

    def select_endpoint(self, pin):
        self.endpoint = pin
        self.paths = self.source.paths(pin)
        self.selected = pin
        path = self.path()
        self.stage = len(path["points"]) - 1 if path else None
        self.refresh(fit=True)

    def set_check(self, check):
        self.check = check
        self.endpoints.check = check
        path = self.path()
        self.stage = len(path["points"]) - 1 if path else None
        self.selected = self.endpoint
        self.refresh(fit=True)

    def set_filter(self, text):
        self.endpoints.text = text
        self._draw_list()

    def next_endpoint(self, step):
        pin = self.endpoints.neighbour(self.endpoint, step)
        if pin:
            self.select_endpoint(pin)

    def path(self):
        return self.paths.get(self.check)

    def step(self, delta):
        path = self.path()
        if not path:
            return
        last = len(path["points"]) - 1
        self.stage = max(0, min(last, (self.stage if self.stage is not None else 0) + delta))
        self.selected = path["points"][self.stage]["pin"]
        self.refresh(fit=False)
        self._see(self.selected)

    def select_stage(self, index):
        path = self.path()
        self.stage = index
        self.selected = path["points"][index]["pin"]
        self.refresh(fit=False)
        self._see(self.selected)

    def select_pin(self, pin):
        self.selected = pin
        path = self.path()
        pins = [p["pin"] for p in path["points"]] if path else []
        self.stage = pins.index(pin) if pin in pins else None
        self.refresh(fit=False)
        self._see(pin)

    def select_cell(self, inst):
        self.selected = "cell:" + inst
        self.stage = None
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
        self.zoom = max(0.35, min(2.5, z))
        self._draw_schematic()

    def fit(self):
        if not self.layout:
            return
        w, h = self.sch.winfo_width(), self.sch.winfo_height()
        bw, bh = self.layout["bbox"][2], self.layout["bbox"][3]
        if w > 10 and h > 10:
            # Never below a readable size: long paths are panned instead (arrow keys auto-pan).
            self.zoom = max(0.7, min(1.2, w / float(bw), h / float(bh)))
        self._draw_schematic()
        self.sch.xview_moveto(0)
        self.sch.yview_moveto(0)

    def _fit_once(self):
        if self.layout and not self._fitted:
            self._fitted = True
            self.fit()

    # ------------------------------------------------------------------ drawing

    def refresh(self, fit=False):
        path = self.path()
        self.layout = model.schematic(path, self.source, self.expanded) if path else None
        if self.layout:
            self.expanded[:] = self.layout["expanded"]
        self.rows = model.stages(path) if path else []
        self._draw_header()
        self._draw_list()
        if fit:
            self._fitted = False
            self.root.update_idletasks()
            self._fit_once()
        else:
            self._draw_schematic()
        self._draw_table()
        self._draw_inspector()

    def _draw_header(self):
        c, path = self.c, self.path()
        self.title.configure(text=self.endpoint or "")
        if path:
            met = not fmt4(path["slack"]).startswith("-")
            self.chip.configure(text="%s slack %s  %s" % (self.check.upper(), fmt4(path["slack"]),
                                                          "MET" if met else "VIOLATED"),
                                fg=c["ok"] if met else c["bad"], bg=c["ok_soft"] if met else c["bad_soft"])
        else:
            self.chip.configure(text="%s: no path" % self.check.upper(), fg=c["muted"], bg=c["head"])
        self.info.configure(text="%s · %s %s ns" % (self.source.design_name, self.source.clock_name,
                                                    fmt4(self.source.period)))
        s = self.source.summary(self.check)
        self.summary.configure(text="" if s is None else "WNS %s   TNS %s   NVP %d" % (
            _num(s["wns"]), fmt4(s["tns"]), s["nvp"]))
        for check, b in self.seg.items():
            on = check == self.check
            b.configure(bg=c["focus"] if on else c["raised"], fg=c["bg"] if on else c["muted"])
        self.path_title.configure(text="WORST %s PATH  ·  %s" % (self.check.upper(), self.endpoint or ""))

    def _draw_list(self):
        c, cv = self.c, self.elist
        cv.delete("all")
        key = self.check + "_slack"
        width = max(cv.winfo_width(), 240)
        for i, r in enumerate(self.endpoints.view()):
            y = i * 38
            on = r["pin"] == self.endpoint
            if on:
                _rounded(cv, 8, y + 2, width - 8, y + 36, 8, fill=c["raised"], outline=c["strong"])
                cv.create_rectangle(8, y + 10, 11, y + 28, fill=c["accent"], outline="")
            cv.create_text(22, y + 19, text=r["pin"], anchor="w", fill=c["ink"],
                           font=self.fonts["ui_b" if on else "ui"], tags=("ep:" + r["pin"],))
            cv.create_text(118, y + 19, text="FLOP" if r["kind"] == "D" else "PORT", anchor="w",
                           fill=c["faint"], font=self.fonts["small"])
            v = r[key]
            colour = c["faint"] if v is None else (c["bad"] if fmt4(v).startswith("-") else c["ok"])
            cv.create_text(width - 18, y + 19, text=_num(v), anchor="e", fill=colour, font=self.fonts["mono"])
            cv.create_rectangle(0, y, width, y + 38, fill="", outline="", tags=("ep:" + r["pin"],))
        cv.configure(scrollregion=(0, 0, width, 38 * len(self.endpoints.view()) + 10))

    def _zfont(self, name, size, bold=False):
        size = max(6, int(round(size * self.zoom)))
        key = (name, size, bold)
        if key not in self.zfonts:
            family = self.mono if name == "mono" else self.ui
            self.zfonts[key] = tkfont.Font(self.root, family=family, size=size,
                                           weight="bold" if bold else "normal")
        return self.zfonts[key]

    def _draw_schematic(self):
        cv, c, z = self.sch, self.c, self.zoom
        cv.delete("all")
        lay = self.layout
        if not lay:
            cv.create_text(40, 40, text="No %s path for this endpoint." % self.check, anchor="nw",
                           fill=c["muted"], font=self.fonts["ui"])
            return
        path = self.path()
        S = lambda v: v * z
        focus = self.selected
        on_path = set(p["pin"] for e in lay["elements"] for p in e["pins"] if p["on_path"])
        hop = self.rows[self.stage] if self.stage is not None and self.rows else None
        cv.configure(scrollregion=(0, 0, S(lay["bbox"][2]), S(lay["bbox"][3])))
        for wire in sorted(lay["wires"], key=lambda w: w["on_path"]):
            pts = [S(v) for xy in wire["points"] for v in xy]
            hot = hop is not None and hop["kind"] == "net" and wire["to"] == hop["pin"] and wire["on_path"]
            cv.create_line(*pts, fill=c["focus"] if hot else (c["accent"] if wire["on_path"] else c["wire"]),
                           width=S(3.5 if hot else (2.5 if wire["on_path"] else 1.5)),
                           arrow="last" if wire["on_path"] else None,
                           arrowshape=(S(9), S(10), S(4)), capstyle="round", joinstyle="round")
        for e in lay["elements"]:
            on_cell = "cell:%s" % e["name"] == focus
            if e["kind"] == "port":
                on = e["pins"][0]["on_path"]
                _rounded(cv, S(e["x0"]), S(e["y0"]), S(e["x1"]), S(e["y1"]), S(14), fill=c["raised"],
                         outline=c["accent"] if on else c["strong"], width=S(1.5))
                cv.create_text(S((e["x0"] + e["x1"]) / 2), S((e["y0"] + e["y1"]) / 2), text=e["name"],
                               fill=c["ink"], font=self._zfont("ui", 13, True), tags=("pin:" + e["name"],))
                cv.create_text(S((e["x0"] + e["x1"]) / 2), S(e["y0"] - 9), text="IN" if e["direction"] == "in" else "OUT",
                               fill=c["faint"], font=self._zfont("ui", 9, True))
            else:
                _rounded(cv, S(e["x0"] + 2), S(e["y0"] + 3), S(e["x1"] + 2), S(e["y1"] + 3), S(10),
                         fill=c["line"], outline="")
                _rounded(cv, S(e["x0"]), S(e["y0"]), S(e["x1"]), S(e["y1"]), S(10), fill=c["raised"],
                         outline=c["focus"] if on_cell else c["strong"], width=S(2 if on_cell else 1))
                _rounded(cv, S(e["x0"]), S(e["y0"]), S(e["x1"]), S(e["y0"] + model.HEAD), S(10),
                         fill=c["head"], outline="", tags=("cell:" + e["name"],))
                cv.create_rectangle(S(e["x0"] + 1), S(e["y0"] + model.HEAD - 10), S(e["x1"] - 1),
                                    S(e["y0"] + model.HEAD), fill=c["head"], outline="", tags=("cell:" + e["name"],))
                cv.create_text(S(e["x0"] + 10), S(e["y0"] + model.HEAD / 2.0), text=e["name"], anchor="w",
                               fill=c["ink"], font=self._zfont("ui", 13, True), tags=("cell:" + e["name"],))
                cv.create_text(S(e["x1"] - 10), S(e["y0"] + model.HEAD / 2.0), text=e["cell"], anchor="e",
                               fill=c["muted"], font=self._zfont("mono", 10), tags=("cell:" + e["name"],))
                if e["arc"]:
                    a, b = e["arc"]["from"], e["arc"]["to"]
                    pa = [p for p in e["pins"] if p["pin"] == a][0]
                    pb = [p for p in e["pins"] if p["pin"] == b][0]
                    hot = hop is not None and hop["pin"] == b and hop["kind"] in ("cell", "ckq")
                    cv.create_line(S(pa["x"] + 24), S(pa["y"]), S(pb["x"] - 24), S(pb["y"]),
                                   fill=c["focus"] if hot else c["accent"], width=S(2.5 if hot else 1.5),
                                   dash=(4, 3), arrow="last", arrowshape=(S(7), S(8), S(3)))
                    cv.create_text(S((pa["x"] + pb["x"]) / 2.0), S(min(pa["y"], pb["y"]) - 9),
                                   text="+" + fmt4(e["arc"]["delay"]), fill=c["accent_ink"],
                                   font=self._zfont("mono", 10, True))
                for p in e["pins"]:
                    inside = 10 if p["side"] == "in" else -10
                    if p["clock"]:
                        cv.create_polygon(S(p["x"]), S(p["y"] - 5), S(p["x"] + 8), S(p["y"]), S(p["x"]),
                                          S(p["y"] + 5), fill="", outline=c["muted"])
                        inside = 13
                    cv.create_text(S(p["x"] + inside), S(p["y"]), text=p["name"],
                                   anchor="w" if p["side"] == "in" else "e",
                                   fill=c["ink"] if p["on_path"] else c["muted"],
                                   font=self._zfont("ui", 12, p["on_path"]), tags=("pin:" + p["pin"],))
            for p in e["pins"]:
                r = 4.5
                cv.create_oval(S(p["x"] - r), S(p["y"] - r), S(p["x"] + r), S(p["y"] + r),
                               fill=c["accent"] if p["on_path"] else c["raised"],
                               outline=c["accent"] if p["on_path"] else c["strong"], width=S(1.5),
                               tags=("pin:" + p["pin"],))
                if p["pin"] == focus and (p["on_path"] or focus not in on_path):
                    cv.create_oval(S(p["x"] - 9), S(p["y"] - 9), S(p["x"] + 9), S(p["y"] + 9),
                                   outline=c["focus"], width=S(2.5))
        for st in lay["stubs"]:
            x, y = st["x"], st["y"]
            if st["state"] == "clock":
                cv.create_line(S(x - 40), S(y), S(x - 5), S(y), fill=c["wire"], dash=(2, 3), width=S(1.2))
                cv.create_text(S(x - 44), S(y), text="clk  %s" % (st["at"] or ""), anchor="e",
                               fill=c["muted"], font=self._zfont("mono", 10))
                continue
            cv.create_line(S(x - model.STUB), S(y), S(x - 5), S(y), fill=c["wire"], width=S(1.5))
            hx = x - model.STUB - 7
            if st["state"] == "expand":
                cv.create_oval(S(hx - 7), S(y - 7), S(hx + 7), S(y + 7), fill=c["raised"],
                               outline=c["focus"], width=S(1.5), tags=("expand:" + st["pin"],))
                cv.create_text(S(hx), S(y), text="+", fill=c["focus"], font=self._zfont("ui", 12, True),
                               tags=("expand:" + st["pin"],))
            elif st["state"] == "link":
                cv.create_text(S(hx), S(y), text="↺", fill=c["focus"], font=self._zfont("ui", 13, True),
                               tags=("pin:" + st["driver"],))
            else:
                cv.create_text(S(hx), S(y), text="·", fill=c["faint"], font=self._zfont("ui", 13, True))
            label = st["driver"] or ("outside bundle" if self.source.mode == "bundle" else "unconnected")
            cv.create_text(S(x - 8), S(y - 9), text=label, anchor="se", fill=c["faint"],
                           font=self._zfont("ui", 10), tags=("pin:" + st["driver"],) if st["state"] == "link" else ())
            if st["at"]:
                cv.create_text(S(x - 8), S(y + 8), text=st["at"], anchor="ne", fill=c["muted"],
                               font=self._zfont("mono", 9))
        for b in lay["badges"]:
            t = cv.create_text(S(b["x"]), S(b["y"]), text=b["text"], anchor=b["anchor"],
                               fill=c["accent_ink"], font=self._zfont("mono", 10, True))
            x0, y0, x1, y1 = cv.bbox(t)
            bg = _rounded(cv, x0 - S(5), y0 - S(1), x1 + S(5), y1 + S(1), S(8), fill=c["accent_soft"], outline="")
            cv.tag_lower(bg, t)

    def _see(self, pin):
        if not self.layout:
            return
        pins = [p for e in self.layout["elements"] for p in e["pins"] if p["pin"] == pin]
        if not pins:
            return
        p = sorted(pins, key=lambda q: not q["on_path"])[0]   # the on-path copy first
        bw, bh = self.layout["bbox"][2] * self.zoom, self.layout["bbox"][3] * self.zoom
        w, h = self.sch.winfo_width(), self.sch.winfo_height()
        x, y = p["x"] * self.zoom, p["y"] * self.zoom
        if bw > w:
            self.sch.xview_moveto(max(0.0, (x - w / 2.0) / bw))
        if bh > h:
            self.sch.yview_moveto(max(0.0, (y - h / 2.0) / bh))

    def _draw_table(self):
        c = self.c
        for cv in (self.thead, self.table):
            cv.delete("all")
        x = 12
        xs = []
        for title, w, anchor in TABLE:
            xs.append((x, w, anchor))
            self.thead.create_text(x + (w - 8 if anchor == "e" else 0), ROW / 2 + 4, text=title.upper(),
                                   anchor=anchor, fill=c["faint"], font=self.fonts["small_b"])
            x += w
        path = self.path()
        if not path:
            return
        cv = self.table
        width = max(cv.winfo_width(), x + 20)
        for i, r in enumerate(self.rows):
            y = i * ROW
            if i == self.stage:
                cv.create_rectangle(0, y, width, y + ROW, fill=c["select"], outline="")
                cv.create_rectangle(0, y + 4, 3, y + ROW - 4, fill=c["focus"], outline="")
            cell = r["kind"] in ("cell", "ckq")
            values = [str(i), r["pin"], r["cell"] or "port", r["arc"], r["rf"],
                      ("+" if i else "") + fmt4(r["delta"]), fmt4(r["at"]), fmt4(r["slew"])]
            for k, (v, (cx, w, anchor)) in enumerate(zip(values, xs)):
                font = "mono_b" if (k == 5 and cell) else ("ui_b" if k == 1 and i == self.stage else
                                                        ("ui" if k in (1, 2, 3) else "mono"))
                colour = c["accent_ink"] if (k == 5 and cell) else (
                    c["faint"] if k == 0 or (k == 5 and r["kind"] == "net") else c["ink"])
                cv.create_text(cx + (w - 8 if anchor == "e" else 0), y + ROW / 2, text=v, anchor=anchor,
                               fill=colour, font=self.fonts[font])
            bx, bw, _ = xs[-1]
            if cell or i == 0:
                cv.create_rectangle(bx, y + 8, bx + max(2, (bw - 20) * (r["share"] if cell else 0.04)),
                                    y + ROW - 8, fill=c["accent"] if cell else c["strong"], outline="")
            cv.create_line(0, y + ROW, width, y + ROW, fill=c["line"])
            cv.create_rectangle(0, y, width, y + ROW, fill="", outline="", tags=("row:%d" % i,))
        y = len(self.rows) * ROW + 10
        _, w_label, _ = xs[1]
        for r in model.capture_rows(path):
            strong = r["label"] in ("required",) or r["label"].startswith("slack")
            colour = c["muted"]
            if r["label"].startswith("slack"):
                colour = c["bad"] if "VIOLATED" in r["label"] else c["ok"]
            elif strong:
                colour = c["ink"]
            cv.create_text(xs[1][0], y + ROW / 2, text=r["label"], anchor="w", fill=colour,
                           font=self.fonts["ui_b" if strong else "ui"])
            if r["delta"] is not None:
                cv.create_text(xs[5][0] + xs[5][1] - 8, y + ROW / 2, text="%+.4f" % r["delta"] if fmt4(r["delta"]) != "0.0000" else "0.0000",
                               anchor="e", fill=c["muted"], font=self.fonts["mono"])
            cv.create_text(xs[6][0] + xs[6][1] - 8, y + ROW / 2, text=fmt4(r["value"]), anchor="e", fill=colour,
                           font=self.fonts["mono_b" if strong else "mono"])
            y += ROW
        cv.configure(scrollregion=(0, 0, width, y + 10))

    def _draw_inspector(self):
        t, c = self.inspector, self.c
        t.configure(state="normal")
        t.delete("1.0", "end")
        sel = self.selected
        if sel and sel.startswith("cell:"):
            inst = sel[5:]
            info = self.source.instance(inst)
            t.insert("end", inst + "\n", "h")
            t.insert("end", "%s · %d pins\n\n" % (info["cell"], len(info["pins"])), "sub")
            t.insert("end", "TIMING ARCS (late)\n", "eye")
            for a in self.source.arcs(inst):
                t.insert("end", "%s → %s  %s\n" % (a["from"].split("/")[-1], a["to"].split("/")[-1], a["kind"]), "b")
                for ab, v in sorted(a["delay"]["late"].items()):
                    if v is not None:
                        t.insert("end", "  %s→%s  %s\n" % (ab[0], ab[1], fmt4(v)))
        elif sel:
            info = self.source.pin(sel)
            t.insert("end", sel + "\n", "h")
            if info is None:
                t.insert("end", "not in this bundle\n", "sub")
            else:
                kind = {"PI": "input port", "PO": "output port", "CK": "clock pin", "D": "data pin (endpoint)",
                        "clock_port": "clock port"}.get(info["kind"])
                if kind is None:
                    pins = self.source.instance(sel.split("/")[0])["pins"]
                    kind = [p["direction"] for p in pins if p["name"] == sel.split("/")[1]][0] + " pin"
                t.insert("end", "%s%s\n\n" % ((info["cell"] + " · ") if info["cell"] else "", kind), "sub")
                t.insert("end", "%-5s %15s %15s\n" % ("", "late".center(15), "early".center(15)), "eye")
                t.insert("end", "%-5s %7s %7s %7s %7s\n" % ("", "r", "f", "r", "f"), "eye")
                for label in ("at", "rat", "slew"):
                    vals = info[label]
                    t.insert("end", "%-5s %7s %7s %7s %7s\n" % (label.upper(), _num(vals["late"]["r"]),
                                                               _num(vals["late"]["f"]), _num(vals["early"]["r"]),
                                                               _num(vals["early"]["f"])))
                t.insert("end", "\n")
                for check in ("setup", "hold"):
                    v = info["slack"][check]
                    t.insert("end", "%-12s " % (check + " slack"), "muted")
                    t.insert("end", _num(v) + "\n", "muted" if v is None else ("bad" if fmt4(v).startswith("-") else "ok"))
                if info["load"] is not None:
                    t.insert("end", "%-12s %s\n" % ("load", fmt4(info["load"])), "muted")
                driver = self.source.driver(sel)
                if driver:
                    t.insert("end", "%-12s %s\n" % ("driven by", driver), "muted")
        t.configure(state="disabled")

    # ------------------------------------------------------------------ mouse

    def _tag(self, canvas, prefix):
        for tag in canvas.gettags("current"):
            if tag.startswith(prefix):
                return tag[len(prefix):]
        return None

    def _on_sch_press(self, event):
        for prefix, action in (("expand:", self.expand), ("pin:", self.select_pin), ("cell:", self.select_cell)):
            hit = self._tag(self.sch, prefix)
            if hit:
                action(hit)
                return
        self.sch.scan_mark(event.x, event.y)

    def _on_list_click(self, event):
        pin = self._tag(self.elist, "ep:")
        if pin:
            self.select_endpoint(pin)

    def _on_table_click(self, event):
        row = self._tag(self.table, "row:")
        if row is not None:
            self.select_stage(int(row))
