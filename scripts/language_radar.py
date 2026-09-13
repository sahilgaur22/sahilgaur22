#!/usr/bin/env python3
"""
Fetches real language byte-counts across all of a GitHub user's public,
non-fork repos and renders them as a radar-chart SVG (dark + light variants).

Run in CI (see .github/workflows/language-radar.yml) or locally:

    GITHUB_TOKEN=<token> python scripts/language_radar.py sahilgaur22
"""

import json
import math
import os
import sys
import urllib.request
from xml.sax.saxutils import escape as xml_escape

API = "https://api.github.com"

# Fixed set of languages always shown on the language-mix radar, in this order.
FIXED_LANGUAGES = ["Python", "Java", "JavaScript", "TypeScript", "HTML", "CSS", "SQL"]


def gh_get(path, token):
    req = urllib.request.Request(f"{API}{path}")
    req.add_header("Accept", "application/vnd.github+json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get_all_repos(username, token):
    repos, page = [], 1
    while True:
        batch = gh_get(f"/users/{username}/repos?per_page=100&page={page}&type=owner", token)
        if not batch:
            break
        repos.extend(r for r in batch if not r.get("fork"))
        page += 1
    return repos


def aggregate_languages(username, repos, token):
    totals = {}
    for repo in repos:
        try:
            langs = gh_get(f"/repos/{username}/{repo['name']}/languages", token)
        except Exception:
            continue
        for lang, byte_count in langs.items():
            totals[lang] = totals.get(lang, 0) + byte_count
    return totals


def fixed_language_percentages(totals, languages=FIXED_LANGUAGES):
    """
    Returns (language, score) for exactly the given languages, in the given
    order — score is out of 100, scaled relative to your most-used language
    among this fixed set (that language = 100, others proportional to it).
    """
    values = {lang: totals.get(lang, 0) for lang in languages}
    max_val = max(values.values()) or 1
    return [(lang, round((bytes_ / max_val) * 100, 1)) for lang, bytes_ in values.items()]


def render_radar_svg(data, title, dark=True, axis_max=100):
    """data: list of (label, value 0-100) tuples. axis_max controls how far
    the outer ring represents (purely visual scaling — labels always show
    the real value)."""
    width, height = 580, 460
    cx, cy = width / 2 + 10, height / 2 + 5
    radius = 125
    n = len(data)

    bg = "#0d1117" if dark else "#ffffff"
    grid = "#30363d" if dark else "#d0d7de"
    text_color = "#c9d1d9" if dark else "#24292f"
    title_color = "#f0f6fc" if dark else "#1f2328"
    line_color = "#39D353"
    fill_color = "rgba(57,211,83,0.28)"

    def point(i, value_pct, r=radius):
        angle = -math.pi / 2 + (2 * math.pi * i / n)
        d = r * (value_pct / axis_max)
        return cx + d * math.cos(angle), cy + d * math.sin(angle)

    def label_point(i, r=radius + 34):
        angle = -math.pi / 2 + (2 * math.pi * i / n)
        return cx + r * math.cos(angle), cy + r * math.sin(angle)

    svg = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'font-family="JetBrains Mono, monospace">',
        f'<rect width="100%" height="100%" fill="{bg}" rx="10"/>',
        f'<text x="{cx}" y="28" text-anchor="middle" font-size="15" font-weight="700" '
        f'fill="{title_color}">{xml_escape(title)}</text>',
    ]

    # Grid rings
    for ring in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{point(i, ring * axis_max)[0]:.1f},{point(i, ring * axis_max)[1]:.1f}" for i in range(n))
        svg.append(f'<polygon points="{pts}" fill="none" stroke="{grid}" stroke-width="1"/>')

    # Axis spokes
    for i in range(n):
        x, y = point(i, axis_max)
        svg.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="{grid}" stroke-width="1"/>')

    # Data polygon
    data_pts = " ".join(f"{point(i, v)[0]:.1f},{point(i, v)[1]:.1f}" for i, (_, v) in enumerate(data))
    svg.append(f'<polygon points="{data_pts}" fill="{fill_color}" stroke="{line_color}" stroke-width="2"/>')
    for i, (_, v) in enumerate(data):
        x, y = point(i, v)
        svg.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{line_color}"/>')

    # Labels + values
    for i, (label, v) in enumerate(data):
        lx, ly = label_point(i)
        anchor = "middle"
        if lx < cx - 10:
            anchor = "end"
        elif lx > cx + 10:
            anchor = "start"
        svg.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" font-size="12" '
            f'font-weight="600" fill="{text_color}">{xml_escape(label)}</text>'
        )
        svg.append(
            f'<text x="{lx:.1f}" y="{ly + 14:.1f}" text-anchor="{anchor}" font-size="10" '
            f'fill="{grid}">{v:g}</text>'
        )

    svg.append("</svg>")
    return "\n".join(svg)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "self-rated":
        generate_self_rated_radar()
        return
    if len(sys.argv) > 1 and sys.argv[1] == "language-score":
        generate_language_score_radar()
        return

    username = sys.argv[1] if len(sys.argv) > 1 else "sahilgaur22"
    token = os.environ.get("GITHUB_TOKEN")

    repos = get_all_repos(username, token)
    totals = aggregate_languages(username, repos, token)
    data = fixed_language_percentages(totals)

    os.makedirs("assets", exist_ok=True)
    title = f"{username} · language mix"

    # Visual-only scaling: rings represent a nice round ceiling above the
    # largest language share, so the chart isn't cramped near the center
    # when no single language dominates. Labels always show the real %.
    top_value = max((v for _, v in data), default=0)
    axis_max = min(100, max(20, math.ceil((top_value * 1.2) / 5) * 5)) if top_value else 100

    with open("assets/radar-langs-dark.svg", "w") as f:
        f.write(render_radar_svg(data, title, dark=True, axis_max=axis_max))
    with open("assets/radar-langs-light.svg", "w") as f:
        f.write(render_radar_svg(data, title, dark=False, axis_max=axis_max))

    print("Wrote assets/radar-langs-dark.svg and assets/radar-langs-light.svg")
    print(data)


def generate_self_rated_radar():
    """
    Regenerate the self-rated skills radar (assets/radar-skills-*.svg).
    Edit the `data` list below to update your ratings (each value is 0-100).
    """
    data = [
        ("AI/ML Engineering", 90),
        ("Backend & APIs", 80),
        ("DSA & DBMS", 80),
        ("RAG / LLM Systems", 90),
        ("MLOps & Deployment", 70),
        ("Data Engineering", 75),
    ]
    os.makedirs("assets", exist_ok=True)
    title = "Skills Radar (self-rated)"
    with open("assets/radar-skills-dark.svg", "w") as f:
        f.write(render_radar_svg(data, title, dark=True))
    with open("assets/radar-skills-light.svg", "w") as f:
        f.write(render_radar_svg(data, title, dark=False))
    print("Wrote assets/radar-skills-dark.svg and assets/radar-skills-light.svg")


def generate_language_score_radar():
    """
    Regenerate the language-mix radar (assets/radar-langs-*.svg) using fixed,
    self-rated scores (0-100) instead of live GitHub byte counts. Edit the
    `data` list below to update your ratings.
    """
    data = [
        ("Python", 98),
        ("Java", 85),
        ("JavaScript", 82),
        ("TypeScript", 80),
        ("HTML", 83),
        ("CSS", 82),
        ("SQL", 88),
    ]
    os.makedirs("assets", exist_ok=True)
    title = "sahilgaur22 · language mix"
    with open("assets/radar-langs-dark.svg", "w") as f:
        f.write(render_radar_svg(data, title, dark=True))
    with open("assets/radar-langs-light.svg", "w") as f:
        f.write(render_radar_svg(data, title, dark=False))
    print("Wrote assets/radar-langs-dark.svg and assets/radar-langs-light.svg")


if __name__ == "__main__":
    main()
