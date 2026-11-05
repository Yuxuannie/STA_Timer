"""Viewer themes (R29, viewer_p4.md): colour palettes with identical keys and font choice
from fallback chains. No Tk here; app.py applies them."""

# Roles: bg = canvas, panel = side panels and header, raised = cards / module bodies,
# head = module header strip, ink / muted / faint = text levels, line / strong = borders,
# wire = non-path wires, accent = the critical path, accent_soft / accent_ink = its badges,
# focus = the selected pin or stage, select = selected rows, ok / bad (+ _soft) = slack.
THEMES = {
    "light": {
        "bg": "#ffffff", "panel": "#f4f5f8", "raised": "#ffffff", "head": "#eef0f5",
        "ink": "#1d2330", "muted": "#5b6475", "faint": "#9aa1b0",
        "line": "#e3e6ee", "strong": "#c5cad6", "wire": "#aab2c2",
        "accent": "#e8590c", "accent_soft": "#fdeee4", "accent_ink": "#b8470a",
        "focus": "#3b5bdb", "select": "#e7edfc",
        "ok": "#2b8a3e", "ok_soft": "#e6f4ea", "bad": "#c92a2a", "bad_soft": "#fbe9e9",
    },
    "dark": {
        "bg": "#171a21", "panel": "#1e222b", "raised": "#242934", "head": "#2b313d",
        "ink": "#e6e9ef", "muted": "#a3abba", "faint": "#6b7385",
        "line": "#2e3440", "strong": "#3d4554", "wire": "#4f586a",
        "accent": "#ffa94d", "accent_soft": "#3a2c1c", "accent_ink": "#ffc078",
        "focus": "#74a7ff", "select": "#26324d",
        "ok": "#51cf66", "ok_soft": "#1f3326", "bad": "#ff6b6b", "bad_soft": "#3b2225",
    },
    "contrast": {
        "bg": "#ffffff", "panel": "#ffffff", "raised": "#ffffff", "head": "#e6e6e6",
        "ink": "#000000", "muted": "#1a1a1a", "faint": "#444444",
        "line": "#000000", "strong": "#000000", "wire": "#555555",
        "accent": "#0040d0", "accent_soft": "#dde6ff", "accent_ink": "#002a8a",
        "focus": "#c00000", "select": "#ffe066",
        "ok": "#006400", "ok_soft": "#dff5df", "bad": "#b00000", "bad_soft": "#ffe0e0",
    },
}
NAMES = ("light", "dark", "contrast")

UI_FONTS = ("SF Pro Text", "Helvetica Neue", "Segoe UI", "DejaVu Sans", "Helvetica")
MONO_FONTS = ("SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "Courier")


def pick_font(chain, available):
    """The first family of `chain` that is in `available`, else the last one of the chain."""
    for family in chain:
        if family in available:
            return family
    return chain[-1]
