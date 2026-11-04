"""Tk debug viewer window (R29, viewer_p4.md "Window"): the endpoints, path and cone views
of an EngineSource or a BundleSource. The only viewer module that imports tkinter."""

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk

from sta_toy import StaError
from sta_toy.tsv import fmt4
from sta_toy.viewer import model

PAGE = 50
MODE = {"setup": "late", "hold": "early"}
HEADINGS = {"pin": "Pin", "kind": "Kind", "setup_slack": "Setup slack", "hold_slack": "Hold slack"}
BOX_W, BOX_H = 190, 54
COL_GAP, ROW_GAP = 260, 70
MARGIN = BOX_W // 2 + 50  # room for the in-column edge curves
RED, GREEN, BLUE = "#c92a2a", "#2b8a3e", "#1c7ed6"
PATH_COLOR, EDGE_COLOR, CHECK_COLOR = "#e8590c", "#adb5bd", "#7048e8"


def negative(v):
    """A slack shown as VIOLATED (report_p3.md §4: fmt4 starts with '-')."""
    return v is not None and fmt4(v).startswith("-")


def worst_at_rat(node, check):
    """(AT, RAT) of the node's worst transition for `check` (ties to r); the worst AT and
    None when no transition has both."""
    m = MODE[check]
    best = None
    for rf in ("r", "f"):
        at, rat = node["at"][m][rf], node["rat"][m][rf]
        if at is not None and rat is not None:
            s = rat - at if check == "setup" else at - rat
            if best is None or s < best[0] - 1e-9:
                best = (s, at, rat)
    if best is not None:
        return best[1], best[2]
    ats = [node["at"][m][rf] for rf in ("r", "f") if node["at"][m][rf] is not None]
    return ((max if check == "setup" else min)(ats) if ats else None), None


class App:
    """The viewer window on `root` for a source (viewer/source.py)."""

    def __init__(self, root, source):
        self.root, self.source = root, source
        self.table = model.EndpointTable(source.rows())
        self.table.sort("setup_slack")
        self.page_no = 0
        self.endpoint = self.node = self.data = self.layout = None
        self.items = {}
        self.check = tk.StringVar(root, "setup")
        self.depth = tk.StringVar(root, "3")
        self.max_nodes = tk.StringVar(root, "300")
        self.filter_text = tk.StringVar(root, "")
        self.page_label = tk.StringVar(root, "")
        self.status = tk.StringVar(root, "")
        family = tkfont.nametofont("TkFixedFont").actual("family")
        self.mono = tkfont.Font(root=root, family=family, size=12)
        self.small = tkfont.Font(root=root, family=family, size=10)
        self.small_bold = tkfont.Font(root=root, family=family, size=10, weight="bold")
        self.bold = tkfont.Font(root=root, size=13, weight="bold")
        root.title("sta_toy viewer - %s mode - clock %s" % (source.mode, source.clock_name))
        root.geometry("1400x880")
        ttk.Style(root).configure("Treeview", rowheight=22)
        self._build()
        self.refresh_table()
        rows = self.table.page(0, PAGE)
        if rows:
            self.select_endpoint(rows[0]["pin"])
        else:
            self.status.set("no endpoints")

    # ---- layout -----------------------------------------------------------------------

    def _build(self):
        ttk.Label(self.root, textvariable=self.status, anchor="w", relief="sunken",
                  padding=(6, 2)).pack(side="bottom", fill="x")
        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True)
        main.add(self._build_endpoints(main), weight=1)
        right = ttk.PanedWindow(main, orient="vertical")
        main.add(right, weight=4)
        right.add(self._build_path(right), weight=2)
        right.add(self._build_cone(right), weight=3)

    def _build_endpoints(self, parent):
        f = ttk.Frame(parent, padding=4)
        ttk.Label(f, text="Endpoints", font=self.bold).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(f, text="Filter:").grid(row=1, column=0, sticky="w")
        ttk.Entry(f, textvariable=self.filter_text).grid(row=1, column=1, columnspan=2, sticky="ew")
        self.filter_text.trace_add("write", lambda *a: self.set_filter(self.filter_text.get()))
        self.tree = ttk.Treeview(f, columns=model.COLUMNS, show="headings", selectmode="browse")
        for c in model.COLUMNS:
            self.tree.heading(c, text=HEADINGS[c], command=lambda c=c: self.sort_by(c))
            self.tree.column(c, width=150 if c == "pin" else (50 if c == "kind" else 95),
                             anchor="w" if c in ("pin", "kind") else "e")
        self.tree.tag_configure("negative", foreground=RED)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        bar = ttk.Scrollbar(f, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.grid(row=2, column=0, columnspan=3, sticky="nsew")
        bar.grid(row=2, column=3, sticky="ns")
        self.prev_button = ttk.Button(f, text="< Prev", command=self.prev_page)
        self.prev_button.grid(row=3, column=0, sticky="w")
        ttk.Label(f, textvariable=self.page_label, anchor="center").grid(row=3, column=1, sticky="ew")
        self.next_button = ttk.Button(f, text="Next >", command=self.next_page)
        self.next_button.grid(row=3, column=2, sticky="e")
        f.columnconfigure(1, weight=1)
        f.rowconfigure(2, weight=1)
        return f

    def _build_path(self, parent):
        f = ttk.Frame(parent, padding=4)
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Path", font=self.bold).pack(side="left")
        for check in ("setup", "hold"):
            ttk.Radiobutton(top, text=check, value=check, variable=self.check,
                            command=lambda: self.show_check(self.check.get())).pack(side="left", padx=6)
        self.timeline_canvas = tk.Canvas(f, height=150, background="white", highlightthickness=0)
        self.timeline_canvas.pack(side="bottom", fill="x")
        self.timeline_canvas.bind("<Configure>", lambda e: self._draw_timeline())
        box = ttk.Frame(f)
        box.pack(fill="both", expand=True)
        self.path_text = self._text(box, height=14)
        self.path_text.tag_configure("bad", foreground=RED, font=self.mono)
        self.path_text.tag_configure("good", foreground=GREEN)
        return f

    def _build_cone(self, parent):
        f = ttk.Frame(parent, padding=4)
        top = ttk.Frame(f)
        top.pack(fill="x")
        ttk.Label(top, text="Cone", font=self.bold).pack(side="left")
        state = "normal" if self.source.mode == "engine" else "disabled"
        ttk.Label(top, text="Depth").pack(side="left", padx=(12, 2))
        self.depth_box = tk.Spinbox(top, from_=0, to=50, width=4, textvariable=self.depth, state=state)
        self.depth_box.pack(side="left")
        ttk.Label(top, text="Max nodes").pack(side="left", padx=(12, 2))
        self.max_box = tk.Spinbox(top, from_=1, to=100000, increment=50, width=7,
                                  textvariable=self.max_nodes, state=state)
        self.max_box.pack(side="left")
        self.reload_button = ttk.Button(top, text="Reload", command=self.reload_cone, state=state)
        self.reload_button.pack(side="left", padx=6)
        ttk.Label(top, text="orange = selected path, red = negative slack, dashed = check arc",
                  foreground="#495057").pack(side="left", padx=12)
        self.banner = tk.Label(f, text="", foreground="white", background=RED, font=self.bold)
        panes = self.cone_panes = ttk.PanedWindow(f, orient="horizontal")
        panes.pack(side="bottom", fill="both", expand=True)
        box = ttk.Frame(panes)
        panes.add(box, weight=3)
        self.cone = tk.Canvas(box, width=600, height=380, background="white", highlightthickness=0)
        ys = ttk.Scrollbar(box, orient="vertical", command=self.cone.yview)
        xs = ttk.Scrollbar(box, orient="horizontal", command=self.cone.xview)
        self.cone.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.cone.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        box.rowconfigure(0, weight=1)
        box.columnconfigure(0, weight=1)
        self.cone.tag_bind("node", "<Button-1>", self._on_node_click)
        self.cone.bind("<Configure>", lambda e: self._draw_cone())
        self.cone.bind("<MouseWheel>", lambda e: self.cone.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.cone.bind("<Shift-MouseWheel>",
                       lambda e: self.cone.xview_scroll(-1 if e.delta > 0 else 1, "units"))
        side = ttk.Frame(panes)
        panes.add(side, weight=1)
        self.details = self._text(side, width=48)
        return f

    def _text(self, parent, **options):
        """A read-only Text with both scrollbars, gridded into `parent`."""
        t = tk.Text(parent, wrap="none", font=self.mono, state="disabled", **options)
        ys = ttk.Scrollbar(parent, orient="vertical", command=t.yview)
        xs = ttk.Scrollbar(parent, orient="horizontal", command=t.xview)
        t.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        t.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        return t

    def _set_text(self, widget, lines):
        """Replace the text of a read-only Text with (line, tags) pairs."""
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        for line, tags in lines:
            widget.insert("end", line + "\n", tags)
        widget.configure(state="disabled")

    # ---- endpoints view ---------------------------------------------------------------

    def refresh_table(self):
        pages = self.table.pages(PAGE)
        self.page_no = max(0, min(self.page_no, pages - 1))
        self.tree.delete(*self.tree.get_children())
        for r in self.table.page(self.page_no, PAGE):
            bad = negative(r["setup_slack"]) or negative(r["hold_slack"])
            self.tree.insert("", "end", iid=r["pin"], tags=("negative",) if bad else (),
                             values=(r["pin"], r["kind"], fmt4(r["setup_slack"]), fmt4(r["hold_slack"])))
        for c in model.COLUMNS:
            arrow = (" v" if self.table.descending else " ^") if c == self.table.column else ""
            self.tree.heading(c, text=HEADINGS[c] + arrow)
        self.page_label.set("page %d / %d" % (self.page_no + 1, pages))
        self.prev_button.configure(state="normal" if self.page_no > 0 else "disabled")
        self.next_button.configure(state="normal" if self.page_no < pages - 1 else "disabled")
        self._mark_endpoint()

    def _mark_endpoint(self):
        if self.endpoint is not None and self.tree.exists(self.endpoint):
            if self.tree.selection() != (self.endpoint,):
                self.tree.selection_set(self.endpoint)
            self.tree.see(self.endpoint)

    def sort_by(self, column):
        """Heading click: sort by `column`; the same column again reverses."""
        self.table.sort(column, column == self.table.column and not self.table.descending)
        self.page_no = 0
        self.refresh_table()

    def set_filter(self, text):
        if self.filter_text.get() != text:
            self.filter_text.set(text)  # the trace calls back here
            return
        self.table.filter(text)
        self.page_no = 0
        self.refresh_table()

    def next_page(self):
        self.page_no += 1
        self.refresh_table()

    def prev_page(self):
        self.page_no -= 1
        self.refresh_table()

    def _on_tree_select(self, event):
        selected = self.tree.selection()
        if selected and selected[0] != self.endpoint:
            self.select_endpoint(selected[0])

    def select_endpoint(self, pin):
        """Load endpoint `pin` into the path and cone views."""
        self.endpoint, self.node = pin, None
        self._mark_endpoint()
        self._load()

    # ---- path and cone views ----------------------------------------------------------

    def _load(self):
        try:
            depth, max_nodes = int(self.depth.get()), int(self.max_nodes.get())
            if depth < 0 or max_nodes < 1:
                raise ValueError
        except ValueError:
            self.status.set("error: depth must be an integer >= 0 and max nodes an integer >= 1")
            return
        try:
            self.data = self.source.bundle(self.endpoint, depth, max_nodes)
        except StaError as e:
            self.status.set(str(e))
            return
        pins = [n["pin"] for n in self.data["nodes"]]
        if self.node not in pins:
            self.node = self.endpoint if self.endpoint in pins else None
        self.show_check(self.check.get())

    def reload_cone(self, depth=None, max_nodes=None):
        """Rebuild the bundle of the current endpoint (new limits if given)."""
        if depth is not None:
            self.depth.set(str(depth))
        if max_nodes is not None:
            self.max_nodes.set(str(max_nodes))
        if self.endpoint is not None:
            self._load()

    def show_check(self, check):
        """Show the setup or hold path of the current endpoint."""
        self.check.set(check)
        if self.data is None:
            return
        self._show_path()
        self._draw_timeline()
        self._draw_cone()
        self._show_details()
        self._show_status()

    def select_node(self, pin):
        """Highlight cone node `pin` and show its details."""
        self.node = pin
        self._draw_cone()
        self._show_details()
        self._show_status()

    def path(self):
        """The bundle's path object for the selected check, or None."""
        if self.data is None:
            return None
        found = [p for p in self.data["paths"] if p["check"] == self.check.get()]
        return found[0] if found else None

    def _show_path(self):
        from sta_toy import report
        p = self.path()
        if p is None:
            lines = [("No %s path to %s." % (self.check.get(), self.endpoint), ())]
        else:
            lines = [(line, ("bad",) if line.startswith("slack (VIOLATED)") else
                      ("good",) if line.startswith("slack (MET)") else ())
                     for line in report.format_path(p).splitlines()]
        self._set_text(self.path_text, lines)

    def _draw_timeline(self):
        c = self.timeline_canvas
        c.delete("all")
        p = self.path()
        if p is None:
            return
        width = max(c.winfo_width(), 600)
        items = model.timeline(p, width)
        c.create_line(40, 75, width - 40, 75, fill="#495057")
        label_y = {"launch_edge": 12, "capture_edge": 12, "required": 28, "arrival": 124,
                   "data": 108, "window": 140}
        for it in sorted(items, key=lambda it: it["kind"] != "window"):
            kind, x0, x1 = it["kind"], it["x0"], it["x1"]
            if kind == "window":
                c.create_rectangle(x0, 55, x1, 95, fill="#ffe8cc", outline=PATH_COLOR)
            elif kind == "data":
                c.create_rectangle(x0, 67, x1, 83, fill="#74c0fc", outline=BLUE)
            else:
                color = {"arrival": BLUE, "required": RED if negative(p["slack"]) else GREEN}.get(kind, "#495057")
                c.create_line(x0, 20, x0, 116, fill=color, width=2,
                              dash=(4, 3) if kind.endswith("edge") else None)
            x = min(max((x0 + x1) / 2.0, 90), width - 90)
            c.create_text(x, label_y[kind], text=it["label"], font=self.small)

    def _draw_cone(self):
        c = self.cone
        c.delete("all")
        self.items = {}
        if self.data is None:
            return
        p = self.path()
        view = dict(self.data, paths=[p] if p else [])
        counts = {}
        for n in self.data["nodes"]:
            counts[n["depth"]] = counts.get(n["depth"], 0) + 1
        width = max(c.winfo_width(), 400, 2 * MARGIN + (max(counts) * COL_GAP if counts else 0))
        height = max(c.winfo_height(), 300,
                     2 * MARGIN + ((max(counts.values()) - 1) * ROW_GAP if counts else 0))
        c.configure(scrollregion=(0, 0, width, height))
        if self.data["truncated"]:
            self.banner.configure(text="TRUNCATED: only the first %d nodes by (depth, name) are shown"
                                  % self.data["max_nodes"])
            self.banner.pack(fill="x", pady=2, before=self.cone_panes)
        else:
            self.banner.configure(text="")
            self.banner.pack_forget()
        if not counts:
            return
        self.layout = layout = model.cone_layout(view, width, height, MARGIN)
        pos = layout["nodes"]
        for u, v, kind, on_path in sorted(layout["edges"], key=lambda e: e[3]):
            (xu, yu), (xv, yv) = pos[u], pos[v]
            half = BOX_W / 2.0
            if abs(xu - xv) < 1:
                points = (xu - half, yu, xu - half - 40, (yu + yv) / 2.0, xv - half, yv)
            elif xu < xv:
                points = (xu + half, yu, xv - half, yv)
            else:
                points = (xu - half, yu, xv + half, yv)
            color = PATH_COLOR if on_path else (CHECK_COLOR if kind == "check" else EDGE_COLOR)
            c.create_line(*points, fill=color, width=3 if on_path else 1, arrow="last",
                          smooth=len(points) > 4, dash=(5, 3) if kind == "check" else None)
        check = self.check.get()
        for n in self.data["nodes"]:
            pin = n["pin"]
            x, y = pos[pin]
            at, rat = worst_at_rat(n, check)
            slack = n["slack"][check]
            bad = negative(slack)
            fill = "#ffe3e3" if bad else ("#fff3bf" if pin == self.endpoint else "white")
            if pin == self.node:
                outline, line = BLUE, 3
            elif pin in layout["path_pins"]:
                outline, line = PATH_COLOR, 3
            else:
                outline, line = "#495057", 1
            ids = [c.create_rectangle(x - BOX_W / 2.0, y - BOX_H / 2.0, x + BOX_W / 2.0, y + BOX_H / 2.0,
                                      fill=fill, outline=outline, width=line, tags=("node",)),
                   c.create_text(x, y - 15, text=pin, font=self.small_bold, tags=("node",)),
                   c.create_text(x, y + 1, text="AT %s RAT %s" % (fmt4(at), fmt4(rat)),
                                 font=self.small, tags=("node",)),
                   c.create_text(x, y + 16, text="slack %s" % fmt4(slack), font=self.small,
                                 fill=RED if bad else "black", tags=("node",))]
            for i in ids:
                self.items[i] = pin

    def _on_node_click(self, event):
        current = self.cone.find_withtag("current")
        if current and current[0] in self.items:
            self.select_node(self.items[current[0]])

    def _show_details(self):
        if self.node is None or self.data is None:
            self._set_text(self.details, [])
            return
        lines = [(self.node, ("title",)), ("", ())]
        lines += [(line, ()) for line in model.node_details(self.data, self.node)]
        lines += [("", ()), ("fan-in edges in the cone:", ())]
        lines += [("  %s  (%s)" % (e["u"], e["kind"]), ()) for e in self.data["edges"] if e["v"] == self.node]
        self.details.tag_configure("title", font=self.bold)
        self._set_text(self.details, lines)

    def _show_status(self):
        check = self.check.get()
        p = self.path()
        parts = ["%s mode" % self.source.mode, "clock %s" % self.source.clock_name,
                 "endpoint %s" % self.endpoint]
        if p is not None:
            parts.append("%s slack %s (%s)" % (check, fmt4(p["slack"]),
                                               "VIOLATED" if negative(p["slack"]) else "MET"))
        else:
            parts.append("no %s path" % check)
        parts.append("cone %d nodes, depth %d, max %d%s" % (
            len(self.data["nodes"]), self.data["depth"], self.data["max_nodes"],
            ", TRUNCATED" if self.data["truncated"] else ""))
        if self.node is not None:
            parts.append("node %s" % self.node)
        self.status.set("  |  ".join(parts))
