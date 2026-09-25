"""Render Veyro sprites (frontend/src/art/sprites.json) to SVG strings.

Used to build design-canvas artboards and previews. The React app has its own
renderer in frontend/src/art/Sprite.tsx that follows the same rules.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "frontend/src/art/sprites.json").read_text(encoding="utf-8"))
W, H = DATA["size"]


def _row(r):
    if len(r) == 12:
        # mirror, but keep the eye shine on the same side for both eyes
        return r + r[::-1].replace("wk", "kw")
    assert len(r) == 24, (r, len(r))
    return r


def grid(name, frame="down", blink=False, talk=False):
    c = DATA["characters"][name]
    g = [["."] * W for _ in range(H)]
    back = c.get("back")
    if back:
        for i, r in enumerate(back["rows"]):
            for x, ch in enumerate(_row(r)):
                if ch != ".":
                    g[back["row"] + i][x] = ch
    for i, r in enumerate(DATA["bodies"][frame]):
        r = _row(r)
        if c.get("stripes") and i in (2, 4):
            r = r.replace("S", "T")
        for x, ch in enumerate(r):
            if ch != ".":
                g[16 + i][x] = ch
    for y, r in enumerate(c["head"]):
        for x, ch in enumerate(_row(r)):
            if ch != ".":
                g[y][x] = ch
    if blink:
        def near_k(x, y):
            return any(0 <= x + dx < W and 0 <= y + dy < 16 and g[y + dy][x + dx] == "k"
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        eyes = [(x, y) for y in range(16) for x in range(W)
                if g[y][x] == "k" or (g[y][x] == "w" and near_k(x, y))]
        if eyes:
            bottom = max(y for _, y in eyes)
            for x, y in eyes:
                g[y][x] = "o" if y == bottom else "@lid"
    if talk:
        mx, my, mw = c["mouth"]
        for x in range(mx, mx + mw):
            g[my][x] = "@mouth"
    return g


def color(name, ch):
    c = DATA["characters"][name]
    if ch == "@lid":
        return c["lid"]
    if ch == "@mouth":
        return "#7A2E2E"
    return c["colors"].get(ch) or DATA["palette"].get(ch) or c["colors"].get("H")


def rects(name, **kw):
    g = grid(name, **kw)
    out = []
    for y in range(H):
        x = 0
        while x < W:
            ch = g[y][x]
            if ch == ".":
                x += 1
                continue
            s = x
            while x < W and g[y][x] == ch:
                x += 1
            out.append(f'<rect x="{s}" y="{y}" width="{x - s}" height="1" fill="{color(name, ch)}"></rect>')
    return "".join(out)


def svg(name, px=5, cls="", **kw):
    return (f'<svg class="{cls}" width="{W * px}" height="{H * px}" viewBox="0 0 {W} {H}" '
            f'shape-rendering="crispEdges" aria-hidden="true">{rects(name, **kw)}</svg>')


if __name__ == "__main__":
    parts = ['<html><body style="background:#F2E2C0;display:flex;flex-wrap:wrap;gap:18px;font:12px sans-serif">']
    for n in DATA["characters"]:
        for f, kw in [("down", {}), ("typeA", {}), ("typeB", {}), ("wave", {"talk": True}), ("down", {"blink": True})]:
            parts.append(f'<div>{svg(n, 6, frame=f, **kw)}<div>{n} {f}{" blink" if kw.get("blink") else ""}</div></div>')
    out = ROOT / "design/extracted/sprites_v2_preview.html"
    out.write_text("".join(parts), encoding="utf-8")
    print(out)


def paths(name, **kw):
    """Compact SVG body: one <path> per colour, one h-run per pixel strip."""
    g = grid(name, **kw)
    runs = {}
    for y in range(H):
        x = 0
        while x < W:
            ch = g[y][x]
            if ch == ".":
                x += 1
                continue
            s = x
            while x < W and g[y][x] == ch:
                x += 1
            runs.setdefault(color(name, ch), []).append(f"M{s} {y}h{x - s}v1h-{x - s}z")
    return "".join(f'<path fill="{c}" d="{"".join(d)}"></path>' for c, d in runs.items())


def svg_compact(name, px=5, cls="", **kw):
    return (f'<svg class="{cls}" width="{W * px}" height="{H * px}" viewBox="0 0 {W} {H}" '
            f'shape-rendering="crispEdges" aria-hidden="true">{paths(name, **kw)}</svg>')
