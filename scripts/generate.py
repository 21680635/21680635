#!/usr/bin/env python3
"""Genera una tarjeta SVG animada con tu calendario de contribuciones de GitHub.

Un gato pixelado recorre el calendario fila por fila, seguido de tres gatitos,
y va "limpiando" los cuadros mientras el contador de arriba sube.

Uso (en GitHub Actions):
    GITHUB_TOKEN=... python scripts/generate.py TU_USUARIO dist

Sin dependencias: solo la biblioteca estándar de Python 3.
"""
import json
import os
import sys
import urllib.request

# ───────────────────────── Ajustes que puedes cambiar ─────────────────────────
SPEED = 210          # velocidad del gato, en px por segundo
PAUSE = 2.5          # segundos de pausa antes de repetir la animación
FOLLOWERS = 3        # cuántos gatitos siguen al gato
GAP = 27             # separación entre personajes, en px

THEMES = {
    "light": {
        "bg": "#ffffff", "text": "#24292f", "muted": "#8c959f",
        "levels": ["#e9eaea", "#bdbfc1", "#929497", "#616569", "#24292f"],
        "leader": "#bc4c00", "follower": "#c15f3c",
    },
    "dark": {
        "bg": "#161b22", "text": "#c9d1d9", "muted": "#616e7f",
        "levels": ["#282d34", "#4c5259", "#70767e", "#979ea6", "#c9d1d9"],
        "leader": "#f76e0a", "follower": "#d97757",
    },
}
# ──────────────────────────────────────────────────────────────────────────────

W, H = 1018, 224
X0, Y0, PITCH, CELL = 53, 63, 18, 14
ROWS = 7
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# Sprite original: cara de gato de 9x8 píxeles (X = pixel, . = vacío)
CAT = [
    "X.......X",
    "XX.....XX",
    "XXXXXXXXX",
    "XXXXXXXXX",
    "XX.XXX.XX",
    "XXXXXXXXX",
    "XXXX.XXXX",
    ".XXXXXXX.",
]
EYES = [(2, 4), (6, 4)]

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date weekday contributionCount contributionLevel } }
      }
    }
  }
}"""


def fetch(login, token):
    body = json.dumps({"query": QUERY, "variables": {"login": login}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": "contribution-card"})
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.load(res)
    if data.get("errors") or not data.get("data", {}).get("user"):
        sys.exit(f"Error de la API de GitHub: {data.get('errors') or 'usuario no encontrado'}")
    return data["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def n(v):
    """Número corto para el SVG."""
    return f"{v:.2f}".rstrip("0").rstrip(".")


def sprite_path(px):
    """Convierte el mapa de píxeles en un path centrado en (0,0)."""
    w, h = len(CAT[0]) * px, len(CAT) * px
    d = []
    for r, row in enumerate(CAT):
        c = 0
        while c < len(row):
            if row[c] == "X":
                start = c
                while c < len(row) and row[c] == "X":
                    c += 1
                d.append(f"M{n(start * px - w / 2)} {n(r * px - h / 2)}"
                         f"h{n((c - start) * px)}v{n(px)}h{n(-(c - start) * px)}z")
            else:
                c += 1
    return "".join(d)


def eyes_path(px):
    w, h = len(CAT[0]) * px, len(CAT) * px
    return "".join(f"M{n(c * px - w / 2)} {n(r * px - h / 2)}h{n(px)}v{n(px)}h{n(-px)}z"
                   for c, r in EYES)


class Route:
    """Recorrido en zigzag: fila 0 hacia la derecha, fila 1 hacia la izquierda, etc."""

    def __init__(self, cols):
        self.xl = X0 + CELL / 2
        self.xr = X0 + (cols - 1) * PITCH + CELL / 2
        lead_in = 30 + FOLLOWERS * GAP
        pts = [(-lead_in, self.row_y(0))]
        for r in range(ROWS):
            end = self.xr if r % 2 == 0 else self.xl
            pts.append((end, self.row_y(r)))
            if r < ROWS - 1:
                pts.append((end, self.row_y(r + 1)))
        last_x = pts[-1][0]
        out = W + lead_in if last_x == self.xr else -lead_in
        pts.append((out, self.row_y(ROWS - 1)))
        self.pts = pts
        self.dist = [0.0]
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            self.dist.append(self.dist[-1] + abs(x2 - x1) + abs(y2 - y1))
        self.total = self.dist[-1]

    @staticmethod
    def row_y(r):
        return Y0 + r * PITCH + CELL / 2

    def cell_dist(self, col, row):
        """Distancia recorrida al llegar al centro del cuadro (col, row)."""
        x = X0 + col * PITCH + CELL / 2
        base = self.dist[1 + 2 * (row - 1) + 1] if row > 0 else 0.0
        if row == 0:
            return x - self.pts[0][0]
        return base + (self.xr - x if row % 2 else x - self.xl)

    def at(self, d):
        d = max(0.0, min(self.total, d))
        for i in range(len(self.pts) - 1):
            if d <= self.dist[i + 1]:
                (x1, y1), (x2, y2) = self.pts[i], self.pts[i + 1]
                seg = self.dist[i + 1] - self.dist[i]
                f = (d - self.dist[i]) / seg if seg else 0
                return x1 + (x2 - x1) * f, y1 + (y2 - y1) * f
        return self.pts[-1]

    def waypoints(self, d_start, d_end):
        ds = [d_start] + [d for d in self.dist if d_start < d < d_end] + [d_end]
        return [(d, self.at(d)) for d in ds]


def build(calendar, theme, frame=None):
    """Devuelve el SVG. `frame` (segundos) dibuja un instante fijo, para pruebas."""
    t = THEMES[theme]
    weeks = calendar["weeks"]
    cols = len(weeks)
    route = Route(cols)
    lead = FOLLOWERS * GAP                      # ventaja del gato sobre el último gatito
    travel = route.total - lead
    move = travel / SPEED
    dur = move + PAUSE
    anim = frame is None

    def frac(seconds):
        return f"{min(seconds / dur, 1):.5f}"

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
         f'viewBox="0 0 {W} {H}" font-family="Consolas,Menlo,Monaco,monospace">',
         "<style>.px{shape-rendering:crispEdges}</style>",
         f'<defs><rect id="d" width="{CELL}" height="{CELL}" rx="3"/></defs>',
         f'<rect width="{W}" height="{H}" rx="15" fill="{t["bg"]}"/>']

    # Cuadros con contribuciones, en el orden en que el gato los alcanza
    active = []
    for c, week in enumerate(weeks):
        for day in week["contributionDays"]:
            level = LEVELS.get(day["contributionLevel"], 0)
            if level:
                r = day["weekday"]
                at = (route.cell_dist(c, r) - lead) / SPEED
                active.append((at, c, r, level, day["contributionCount"]))
    active.sort()

    # Contador del título
    def label(count):
        return f"{count:,} contribution{'' if count == 1 else 's'} in the last year"

    steps, running = [(0.0, 0)], 0
    for at, _, _, _, count in active:
        running += count
        steps.append((at, running))
    # El título va en una sola línea, sin saltos entre <tspan>: Firefox los
    # interpreta como renglones nuevos y empuja el texto hacia abajo.
    title = []
    for i, (at, count) in enumerate(steps):
        nxt = steps[i + 1][0] if i + 1 < len(steps) else None
        if not anim:
            if at <= frame and (nxt is None or frame < nxt):
                title.append(f'<tspan x="15" y="29">{label(count)}</tspan>')
            continue
        if i == 0:
            vals, keys = "visible;hidden", f"0;{frac(nxt)}" if nxt is not None else None
            if keys is None:
                title.append(f'<tspan x="15" y="29">{label(count)}</tspan>')
                continue
            vis = "visible"
        elif nxt is None:
            vals, keys, vis = "hidden;visible", f"0;{frac(at)}", "hidden"
        else:
            vals, keys, vis = "hidden;visible;hidden", f"0;{frac(at)};{frac(nxt)}", "hidden"
        title.append(f'<tspan x="15" y="29" visibility="{vis}"><animate attributeName="visibility" '
                 f'values="{vals}" keyTimes="{keys}" dur="{n(dur)}s" calcMode="discrete" '
                 f'repeatCount="indefinite"/>{label(count)}</tspan>')
    o.append(f'<text font-size="14" fill="{t["text"]}">' + "".join(title) + "</text>")

    # Etiquetas de meses y días
    o.append(f'<g font-size="12" fill="{t["muted"]}">')
    prev, last_x = None, -99
    for c, week in enumerate(weeks):
        month = int(week["contributionDays"][0]["date"][5:7])
        x = X0 + c * PITCH
        if month != prev and x - last_x >= 2 * PITCH:
            o.append(f'<text x="{x}" y="55">{MONTHS[month - 1]}</text>')
            last_x = x
        prev = month
    for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        o.append(f'<text x="15" y="{n(Y0 + r * PITCH + 11.2)}">{name}</text>')
    lx = W - 15 - 44 - 5 * PITCH
    o.append(f'<text x="{lx - 6}" y="209" text-anchor="end">Less</text>')
    o.append(f'<text x="{lx + 5 * PITCH + 2}" y="209">More</text></g>')
    for i, color in enumerate(t["levels"]):
        o.append(f'<rect x="{lx + i * PITCH}" y="198" width="{CELL}" height="{CELL}" rx="3" fill="{color}"/>')

    # Cuadros vacíos de fondo
    o.append(f'<g fill="{t["levels"][0]}">')
    for c, week in enumerate(weeks):
        for day in week["contributionDays"]:
            o.append(f'<use href="#d" x="{X0 + c * PITCH}" y="{Y0 + day["weekday"] * PITCH}"/>')
    o.append("</g>")

    # Cuadros con contribuciones: se vacían cuando pasa el gato
    for at, c, r, level, _ in active:
        x, y = X0 + c * PITCH, Y0 + r * PITCH
        color = t["levels"][level]
        if not anim:
            if frame < at:
                o.append(f'<use href="#d" x="{x}" y="{y}" fill="{color}"/>')
            continue
        o.append(f'<use href="#d" x="{x}" y="{y}" fill="{color}"><animate attributeName="fill" '
                 f'values="{color};{t["levels"][0]}" keyTimes="0;{frac(at)}" dur="{n(dur)}s" '
                 f'calcMode="discrete" repeatCount="indefinite"/></use>')

    # Personajes: k = 0 es el gato, el resto son los gatitos
    o.append('<g class="px">')
    for k in range(FOLLOWERS, -1, -1):
        d_start = lead - k * GAP
        px = 2 if k == 0 else 1.5
        color = t["leader"] if k == 0 else t["follower"]
        body = f'<path d="{sprite_path(px)}"/>'
        if not anim:
            x, y = route.at(d_start + min(frame, move) * SPEED)
            o.append(f'<g transform="translate({n(x)},{n(y)})" fill="{color}">{body}</g>')
            continue
        way = route.waypoints(d_start, d_start + travel)
        vals = ";".join(f"{n(x)},{n(y)}" for _, (x, y) in way)
        keys = ";".join(frac((d - d_start) / SPEED) for d, _ in way)
        last = way[-1][1]
        vals += f";{n(last[0])},{n(last[1])}"
        keys += ";1"
        blink = (f'<path d="{eyes_path(px)}" opacity="0"><animate attributeName="opacity" '
                 f'values="0;1;0" keyTimes="0;0.93;0.98" dur="{n(2.4 + k * 0.5)}s" '
                 f'calcMode="discrete" repeatCount="indefinite"/></path>')
        hop = "" if k == 0 else (
            f'<animateTransform attributeName="transform" type="translate" values="0,0;0,-1.5" '
            f'keyTimes="0;0.5" dur="{n(0.3 + k * 0.04)}s" calcMode="discrete" repeatCount="indefinite"/>')
        o.append(f'<g><animateTransform attributeName="transform" type="translate" values="{vals}" '
                 f'keyTimes="{keys}" dur="{n(dur)}s" repeatCount="indefinite"/>'
                 f'<g fill="{color}">{hop}{body}{blink}</g></g>')
    o.append("</g></svg>")
    return "\n".join(o)


def main():
    if len(sys.argv) < 2:
        sys.exit("Uso: generate.py USUARIO [carpeta_de_salida]")
    login = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "dist"
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Falta la variable de entorno GITHUB_TOKEN")
    calendar = fetch(login, token)
    os.makedirs(out, exist_ok=True)
    for theme, name in (("light", "contributions.svg"), ("dark", "contributions-dark.svg")):
        path = os.path.join(out, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(build(calendar, theme))
        print(f"listo: {path}")


if __name__ == "__main__":
    main()
