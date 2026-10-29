#!/usr/bin/env python3
"""Create animated profile SVGs from observed GitHub information. Never invent activity."""
from __future__ import annotations
from datetime import timedelta, date
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance
import html, json, os, re, urllib.request

USER = os.environ.get("GH_PROFILE_LOGIN", "fahdbenayad2-hash")
TOKEN = os.environ.get("GH_STATS_TOKEN", "")
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"

# Premium dark + emerald palette
GREEN, WHITE, MUTED, BG = "#3cf18f", "#ecfaf4", "#8fa39c", "#0b1110"
PALETTE = ["#15221c", "#155832", "#217d48", "#30b86c", "#53efa0"]
FRAME_STROKE = "#274c3a"
PANEL_BG = "#0a1512"
PANEL_STROKE = "#234c38"

def get(url, payload=None):
    headers = {
        "User-Agent": "fahd-github-profile/2.0",
        "Accept": "application/vnd.github+json" if "api.github.com" in url else "text/html",
    }
    if TOKEN:
        headers["Authorization"] = "Bearer " + TOKEN
    if payload is not None:
        headers["Content-Type"] = "application/json"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, headers=headers, data=data)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()

def graph_contributions():
    query = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
    d = json.loads(get("https://api.github.com/graphql", {"query": query, "variables": {"login": USER}}))
    if d.get("errors"):
        raise RuntimeError(str(d["errors"])[:300])
    cal = d["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    counts = {
        day["date"]: int(day["contributionCount"])
        for week in cal["weeks"]
        for day in week["contributionDays"]
    }
    if len(counts) < 240:
        raise RuntimeError("GitHub GraphQL calendar too short")
    return counts, int(cal["totalContributions"])

class GitHubCalendarParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.counts = {}
        self.text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        stamp = a.get("data-date", "")
        value = a.get("data-count")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
            if value is not None:
                try:
                    self.counts[stamp] = int(value)
                except ValueError:
                    pass
            elif a.get("data-level") is not None:
                try:
                    self.counts[stamp] = (int(a["data-level"]), "level")
                except ValueError:
                    pass

    def handle_data(self, data):
        self.text.append(data)

def html_contributions():
    p = GitHubCalendarParser()
    p.feed(get(f"https://github.com/users/{USER}/contributions"))
    if len(p.counts) < 240:
        raise RuntimeError(f"GitHub HTML calendar too short: {len(p.counts)}")
    s = " ".join(p.text)
    m = re.search(r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year", s, re.I)
    total = int(m.group(1).replace(",", "")) if m else None
    return p.counts, total

def contributions():
    errors = []
    if TOKEN:
        try:
            return graph_contributions()
        except Exception as e:
            errors.append("GraphQL: " + str(e))
    try:
        return html_contributions()
    except Exception as e:
        errors.append("HTML: " + str(e))
    raise RuntimeError("Could not verify real contribution history. " + " | ".join(errors))

def public_stats():
    user = json.loads(get(f"https://api.github.com/users/{USER}"))
    if user.get("login", "").lower() != USER.lower():
        raise RuntimeError("Invalid profile API response")
    repos, page = [], 1
    while page <= 10:
        data = json.loads(
            get(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner")
        )
        if not isinstance(data, list):
            raise RuntimeError("Repository API did not return list")
        repos += [r for r in data if not r.get("fork") and not r.get("private")]
        if len(data) < 100:
            break
        page += 1
    if page > 10:
        raise RuntimeError("Repository pagination limit exceeded")
    return {
        "repos": user["public_repos"],
        "stars": sum(int(r.get("stargazers_count", 0)) for r in repos),
        "followers": user["followers"],
    }

def esc(v):
    return html.escape(str(v), quote=True)

def txt(x, y, val, size=16, color=WHITE, bold=False, anchor="start"):
    weight = 700 if bold else 400
    return (
        f'<text x="{x}" y="{y}" fill="{color}" '
        f'font-family="DejaVu Sans Mono,Consolas,monospace" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}" xml:space="preserve">{esc(val)}</text>'
    )

def frame(w, h, command):
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">',
        f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="18" fill="{BG}" stroke="{FRAME_STROKE}" stroke-width="2"/>',
    ]
    for i, c in enumerate(["#ff6058", "#ffbe2f", "#27c93f"]):
        parts.append(f'<circle cx="{28 + i * 18}" cy="28" r="5" fill="{c}"/>')
    parts.append(txt(130, 33, "fahd@github ~ $ " + command, 14, GREEN, True))
    return parts

def cell_level(v, maximum):
    if isinstance(v, tuple):
        return max(0, min(4, v[0]))
    if v <= 0:
        return 0
    if maximum <= 1:
        return 2
    return max(1, min(4, int(1 + 3 * v / max(1, maximum))))

def calendar_svg(counts, total):
    out = frame(1060, 248, "./contributions.sh")
    out.append(txt(28, 72, "CONTRIBUTION ACTIVITY  //  GITHUB", 15, WHITE, True))
    desc = f"{total:,} contributions / last year" if total is not None else "GitHub contribution calendar"
    out.append(txt(1032, 72, desc, 12, GREEN, False, "end"))

    today = max(date.fromisoformat(x) for x in counts)
    start = today - timedelta(days=364)
    start -= timedelta(days=(start.weekday() + 1) % 7)
    vals = [v for v in counts.values() if isinstance(v, int)]
    mx = max(vals) if vals else 1

    weeks = []
    for i in range(53):
        d = start + timedelta(days=i * 7)
        if d > today:
            break
        weeks.append([d + timedelta(days=j) for j in range(7)])
    weeks = weeks[-53:]

    for i, week in enumerate(weeks):
        for j, d in enumerate(week):
            if d > today:
                continue
            v = counts.get(d.isoformat(), 0)
            level = cell_level(v, mx)
            x, y = 56 + i * 17.9, 108 + j * 16.5
            delay = i * 0.016 + j * 0.005
            out.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" rx="2.2" width="12.2" height="12.2" '
                f'fill="{PALETTE[level]}" opacity="0">'
                f'<animate attributeName="opacity" values="0;1" dur="0.28s" begin="{delay:.3f}s" fill="freeze"/>'
                f"</rect>"
            )

    for j, name in [(1, "M"), (3, "W"), (5, "F")]:
        out.append(txt(26, 118 + j * 16.5, name, 11, MUTED))

    recent = None
    for i, week in enumerate(weeks):
        month = week[0].strftime("%b")
        if month != recent and i < len(weeks) - 1:
            out.append(txt(56 + i * 17.9, 100, month, 11, MUTED))
            recent = month

    out.append(txt(930, 236, "LESS", 10, MUTED))
    for i, c in enumerate(PALETTE):
        out.append(f'<rect x="{968 + i * 15}" y="226" width="11" height="11" rx="2" fill="{c}"/>')
    out.append("</svg>")
    return "".join(out)

def ascii_portrait():
    """Higher-contrast ASCII from the illustrated portrait. Preserves recognizable features."""
    picture = Image.open(ASSETS / "avatar.jpg").convert("L")
    picture = ImageOps.autocontrast(picture, cutoff=1)
    picture = picture.resize((64, 40), Image.Resampling.LANCZOS)
    picture = ImageEnhance.Contrast(picture).enhance(1.25)
    palette = " .:-=+*#%@"
    lines = []
    for y in range(40):
        row = []
        for x in range(64):
            px = picture.getpixel((x, y))
            idx = min(9, px * 10 // 256)
            row.append(palette[idx])
        lines.append("".join(row))
    return lines

def terminal_svg(stats, total):
    out = frame(1060, 520, "whoami")
    out += [
        txt(26, 72, "IDENTITY // TERMINAL PORTRAIT", 15, WHITE, True),
        f'<rect x="20" y="90" width="500" height="400" rx="12" fill="{PANEL_BG}" stroke="{PANEL_STROKE}"/>',
        f'<rect x="530" y="90" width="510" height="400" rx="12" fill="{PANEL_BG}" stroke="{PANEL_STROKE}"/>',
        txt(36, 112, "> image_to_ascii --portrait fahd", 11, GREEN),
        txt(546, 112, "> github_activity --verified", 11, GREEN),
    ]

    for i, line in enumerate(ascii_portrait()):
        out.append(txt(40, 132 + i * 8.4, line, 8.0, "#6fa58b"))

    items = [
        ("PUBLIC REPOSITORIES", stats["repos"]),
        ("STARS RECEIVED", stats["stars"]),
        ("FOLLOWERS", stats["followers"]),
        ("YEARLY CONTRIBUTIONS", total if total is not None else "N/A"),
    ]
    for i, (k, v) in enumerate(items):
        y = 160 + i * 70
        out.append(txt(548, y, k, 13, MUTED))
        val = f"{v:,}" if isinstance(v, int) else str(v)
        out.append(txt(1018, y + 6, val, 28, GREEN if i == 0 else WHITE, True, "end"))
        out.append(f'<path d="M548 {y + 20}h450" stroke="#234433"/>')

    out += [
        txt(548, 460, "SOURCE: GITHUB  ·  NO FABRICATED COUNTS", 11, GREEN),
        '<rect x="1008" y="448" width="8" height="14" fill="#3cf18f">'
        '<animate attributeName="opacity" values="1;0;1" dur="1.1s" repeatCount="indefinite"/>'
        "</rect>",
        txt(40, 478, "FAHD BENAYAD  //  AI · AUTOMATION · PRODUCT", 10, GREEN),
        "</svg>",
    ]
    return "".join(out)

def main():
    counts, total = contributions()
    stats = public_stats()
    a = calendar_svg(counts, total)
    b = terminal_svg(stats, total)
    # Atomic: both succeed before any write
    (ASSETS / "contributions.svg").write_text(a, encoding="utf-8")
    (ASSETS / "terminal.svg").write_text(b, encoding="utf-8")
    print("Verified GitHub stats:", stats, "contribution days:", len(counts), "yearly:", total)

if __name__ == "__main__":
    main()
