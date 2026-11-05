"""Viewer themes (R29, viewer_p4.md): colour palettes with identical keys and font choice
from fallback chains. No Tk here; app.py applies them."""

# One neutral scale and a single accent. Roles: bg = canvas, panel = side panels and header,
# raised = elevated surfaces (gate bodies, the filter box, the active segment), head = recessed
# tracks, ink / muted / faint = text levels, line = hairlines, strong = heavier rules,
# wire = non-path wires, accent = the critical path (accent_soft / accent_ink: its tint and
# its labels), focus = the selected pin, hop or row marker, select = selected rows,
# ok / bad (+ _soft) = slack figures only, setup / hold (+ _soft) = the two checks in the
# waveform.
THEMES = {
    "light": {
        "bg": "#ffffff", "panel": "#fafafa", "raised": "#ffffff", "head": "#f1f1f4",
        "ink": "#18181b", "muted": "#63636e", "faint": "#a1a1aa",
        "line": "#ececf0", "strong": "#d4d4da", "wire": "#bdbdc6",
        "accent": "#5b5bd6", "accent_soft": "#eeeefc", "accent_ink": "#4949b8",
        "focus": "#18181b", "select": "#f0f0f3",
        "ok": "#18794e", "ok_soft": "#e9f6ef", "bad": "#d1242f", "bad_soft": "#fdecec",
        "setup": "#5b5bd6", "setup_soft": "#efeffc", "hold": "#0b8a7e", "hold_soft": "#e5f4f2",
    },
    "dark": {
        "bg": "#111113", "panel": "#161618", "raised": "#232327", "head": "#1c1c1f",
        "ink": "#ededf0", "muted": "#a0a0aa", "faint": "#62626c",
        "line": "#242428", "strong": "#38383f", "wire": "#4a4a52",
        "accent": "#8d8cf6", "accent_soft": "#24244a", "accent_ink": "#a9a8ff",
        "focus": "#ededf0", "select": "#222226",
        "ok": "#3dd68c", "ok_soft": "#13291e", "bad": "#ff6369", "bad_soft": "#3a1a1d",
        "setup": "#8d8cf6", "setup_soft": "#1d1d38", "hold": "#2fc8b8", "hold_soft": "#112b28",
    },
    "contrast": {
        "bg": "#ffffff", "panel": "#ffffff", "raised": "#ffffff", "head": "#e6e6e6",
        "ink": "#000000", "muted": "#1a1a1a", "faint": "#444444",
        "line": "#000000", "strong": "#000000", "wire": "#555555",
        "accent": "#0040d0", "accent_soft": "#dde6ff", "accent_ink": "#002a8a",
        "focus": "#c00000", "select": "#ffe066",
        "ok": "#006400", "ok_soft": "#dff5df", "bad": "#b00000", "bad_soft": "#ffe0e0",
        "setup": "#6a00c8", "setup_soft": "#efe0ff", "hold": "#005f5f", "hold_soft": "#d9f2f2",
    },
}
NAMES = ("light", "dark", "contrast")

# Words use the platform's UI font (on macOS Tk's default font, SF Pro, which families() does
# not list); this chain is the fallback elsewhere. Every number uses the monospaced chain so
# columns line up.
UI_FONTS = ("SF Pro Text", "Helvetica Neue", "Segoe UI", "DejaVu Sans", "Helvetica")
MONO_FONTS = ("SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "Courier")


def pick_font(chain, available):
    """The first family of `chain` that is in `available`, else the last one of the chain."""
    for family in chain:
        if family in available:
            return family
    return chain[-1]
