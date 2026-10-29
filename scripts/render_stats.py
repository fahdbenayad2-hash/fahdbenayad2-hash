#!/usr/bin/env python3
"""Create animated profile SVGs from observed GitHub information, never fake activity."""
from __future__ import annotations
from datetime import datetime, timedelta, date, timezone
from html.parser import HTMLParser
from pathlib import Path
from PIL import Image, ImageOps
import html, json, os, re, sys, urllib.request

USER = os.environ.get("GH_PROFILE_LOGIN", "fahdbenayad2-hash")
TOKEN = os.environ.get("GH_STATS_TOKEN", "")
ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
GREEN, WHITE, MUTED, BG = "#3cf18f", "#ecfaf4", "#9eb1ab", "#0b1110"
PALETTE = ["#15221c", "#155832", "#217d48", "#30b86c", "#53efa0"]

def get(url, payload=None):
    headers = {"User-Agent": "fahd-github-profile/1.0", "Accept": "application/vnd.github+json" if "api.github.com" in url else "text/html"}
    if TOKEN: headers["Authorization"] = "Bearer " + TOKEN
    if payload is not None: headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode() if payload is not None else None)
    with urllib.request.urlopen(req, timeout=30) as resp: return resp.read().decode()

def graph_contributions():
    query = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{totalContributions weeks{contributionDays{date contributionCount}}}}}}"""
    d = json.loads(get("https://api.github.com/graphql", {"query": query, "variables": {"login": USER}}))
    if d.get("errors"): raise RuntimeError(str(d["errors"])[:300])
    cal = d["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    counts = {day["date"]: int(day["contributionCount"]) for week in cal["weeks"] for day in week["contributionDays"]}
    if len(counts) < 240: raise RuntimeError("GitHub GraphQL calendar too short")
    return counts, int(cal["totalContributions"])

class GitHubCalendarParser(HTMLParser):
    def __init__(self): super().__init__(); self.counts = {}; self.text = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        stamp = a.get("data-date", "")
        value = a.get("data-count")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
            if value is not None:
                try: self.counts[stamp] = int(value)
                except ValueError: pass
            elif a.get("data-level") is not None:
                try: self.counts[stamp] = (int(a["data-level"]), "level")
                except ValueError: pass
    def handle_data(self, data): self.text.append(data)

def html_contributions():
    p = GitHubCalendarParser()
    p.feed(get(f"https://github.com/users/{USER}/contributions"))
    if len(p.counts) < 240: raise RuntimeError(f"GitHub HTML calendar too short: {len(p.counts)}")
    s = " ".join(p.text)
    m = re.search(r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year", s, re.I)
    return p.counts, (int(m.group(1).replace(",", "")) if m else None)

def contributions():
    errors = []
    if TOKEN:
        try: return graph_contributions()
        except Exception as e: errors.append("GraphQL: " + str(e))
    try: return html_contributions()
    except Exception as e: errors.append("HTML: " + str(e))
    raise RuntimeError("Could not verify real contribution history. " + " | ".join(errors))

def public_stats():
    user = json.loads(get(f"https://api.github.com/users/{USER}"))
    if user.get("login", "").lower() != USER.lower(): raise RuntimeError("Invalid profile API response")
    repos, page = [], 1
    while page <= 10:
        data = json.loads(get(f"https://api.github.com/users/{USER}/repos?per_page=100&page={page}&type=owner"))
        if not isinstance(data, list): raise RuntimeError("Repository API did not return list")
        repos += [r for r in data if not r.get("fork") and not r.get("private")]
        if len(data) < 100: break
        page += 1
    if page > 10: raise RuntimeError("Repository pagination limit exceeded")
    return {"repos": user["public_repos"], "stars": sum(int(r.get("stargazers_count",0)) for r in repos), "followers": user["followers"]}

def esc(v): return html.escape(str(v), quote=True)

def txt(x, y, val, size=16, color=WHITE, bold=False, anchor="start"):
    return f'<text x="{x}" y="{y}" fill="{color}" font-family="DejaVu Sans Mono,Consolas,monospace" font-size="{size}" font-weight="{700 if bold else 400}" text-anchor="{anchor}" xml:space="preserve">{esc(val)}</text>'

def frame(w, h, command):
    return [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">',
            f'<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="22" fill="{BG}" stroke="#274c3a" stroke-width="2"/>',
            *[f'<circle cx="{29+i*19}" cy="31" r="5.5" fill="{c}"/>' for i,c in enumerate(["#ff6058","#ffbe2f","#27c93f"])],
            txt(140,37,"fahd@github ~ $ "+command,16,GREEN,True)]

def cell_level(v, maximum):
    if isinstance(v, tuple): return max(0, min(4, v[0]))
    if v <= 0: return 0
    if maximum <= 1: return 2
    return max(1,min(4, int(1+3*v/max(1,maximum))))

def calendar_svg(counts, total):
    out = frame(1060,264,"./contributions.sh")
    out.append(txt(30,81,"CONTRIBUTION ACTIVITY  //  GITHUB",17,WHITE,True))
    desc = f"{total:,} contributions / last year" if total is not None else "GitHub contribution calendar"
    out.append(txt(1023,81,desc,13,GREEN,False,"end"))
    today = max(date.fromisoformat(x) for x in counts)
    start = today-timedelta(days=364)
    start -= timedelta(days=(start.weekday()+1)%7)
    vals = [v for v in counts.values() if isinstance(v,int)]
    mx = max(vals) if vals else 1
    weeks = []
    for i in range(53):
        d = start+timedelta(days=i*7)
        if d > today: break
        weeks.append([d+timedelta(days=j) for j in range(7)])
    weeks = weeks[-53:]
    for i,week in enumerate(weeks):
        for j,d in enumerate(week):
            v=counts.get(d.isoformat(),0)
            level=cell_level(v,mx)
            x,y=60+i*17.7,121+j*17
            if d>today: continue
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" rx="2.5" width="12.4" height="12.4" fill="{PALETTE[level]}" opacity="0"><animate attributeName="opacity" values="0;1" dur=".3s" begin="{i*.017+j*.006:.3f}s" fill="freeze"/></rect>')
    for j,name in [(1,"M"),(3,"W"),(5,"F")]: out.append(txt(28,132+j*17,name,12,MUTED))
    recent = None
    for i,week in enumerate(weeks):
        month = week[0].strftime("%b")
        if month != recent and i < len(weeks)-1:
            out.append(txt(60+i*17.7,113,month,12,MUTED))
            recent = month
    out.append(txt(933,250,"LESS",11,MUTED))
    for i,c in enumerate(PALETTE): out.append(f'<rect x="{974+i*16}" y="239" width="12" height="12" rx="2" fill="{c}"/>')
    out.append("</svg>")
    return "".join(out)

def ascii_portrait():
    picture = Image.open(ASSETS/"avatar.jpg").convert("L")
    picture = ImageOps.autocontrast(picture).resize((62,39))
    palette = " .:-=+*#%@"
    return ["".join(palette[min(9,px*10//256)] for px in [picture.getpixel((x,y)) for x in range(62)]) for y in range(39)]

def terminal_svg(stats, total):
    out = frame(1060,505,"whoami")
    out += [txt(28,82,"IDENTITY // TERMINAL PORTRAIT",16,WHITE,True),
            '<rect x="22" y="101" width="492" height="376" rx="12" fill="#0a1512" stroke="#234c38"/>',
            '<rect x="528" y="101" width="511" height="376" rx="12" fill="#0a1512" stroke="#234c38"/>',
            txt(40,123,"> image_to_ascii --portrait fahd",12,GREEN),
            txt(549,123,"> github_activity --verified",12,GREEN)]
    for i,line in enumerate(ascii_portrait()):
        out.append(txt(44,143+i*7.5,line,8.1,"#6fa58b"))
    items=[("PUBLIC REPOSITORIES",stats["repos"]),("STARS RECEIVED",stats["stars"]),("FOLLOWERS",stats["followers"]),("YEARLY CONTRIBUTIONS",total if total is not None else "N/A")]
    for i,(k,v) in enumerate(items):
        y=174+i*65
        out.append(txt(550,y,k,14,MUTED))
        out.append(txt(1010,y+5,f"{v:,}" if isinstance(v,int) else v,27,GREEN if i==0 else WHITE,True,"end"))
        out.append(f'<path d="M550 {y+17}h460" stroke="#234433"/>')
    out += [txt(551,452,"SOURCE: GITHUB  /  NO FABRICATED COUNTS",11,GREEN),
            '<rect x="1003" y="440" width="9" height="15" fill="#3cf18f"><animate attributeName="opacity" values="1;0;1" dur="1s" repeatCount="indefinite"/></rect>',
            txt(43,466,"FAHD BENAYAD  //  AI + AUTOMATION",10,GREEN),
            "</svg>"]
    return "".join(out)

def main():
    counts,total=contributions()
    stats=public_stats()
    a=calendar_svg(counts,total)
    b=terminal_svg(stats,total)
    # Both renders succeed before any of the files are overwritten.
    (ASSETS/"contributions.svg").write_text(a,encoding="utf-8")
    (ASSETS/"terminal.svg").write_text(b,encoding="utf-8")
    print("Verified GitHub stats:",stats,"contribution days:",len(counts),"yearly:",total)

if __name__=="__main__": main()
