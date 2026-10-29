#!/usr/bin/env python3
"""Deterministic checks for generated GitHub profile graphics."""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from PIL import Image
from xml.etree import ElementTree as ET
import importlib.util
import re

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
SVG = "{http://www.w3.org/2000/svg}"
spec = importlib.util.spec_from_file_location("render_stats", ROOT / "scripts" / "render_stats.py")
generator = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(generator)

def parse(path):
    root = ET.parse(ASSETS / path).getroot()
    assert root.tag == SVG + "svg", f"Not an SVG: {path}"
    assert "viewBox" in root.attrib, f"No viewBox: {path}"
    assert int(root.attrib["width"]) >= 800, f"Unexpected width: {path}"
    assert int(root.attrib["height"]) >= 200, f"Unexpected height: {path}"
    return root

def check_heatmap(root):
    animated = [r for r in root.iter(SVG + "rect") if r.find(SVG + "animate") is not None]
    assert len(animated) >= 300, f"Only {len(animated)} animated cells"
    for cell in animated:
        assert cell.attrib.get("opacity") == "1", "Static fallback must show the cell"
        a = cell.find(SVG + "animate")
        assert a.attrib.get("attributeName") == "opacity"
        assert a.attrib.get("fill") == "freeze"
        times = [float(v) for v in a.attrib.get("keyTimes", "").split(";")]
        assert len(times) == 4 and times[0] == 0 and times[-1] == 1
        assert times == sorted(times), "Animation timing must be monotonic"
    labels = "".join(t.text or "" for t in root.iter(SVG + "text"))
    assert "CONTRIBUTION ACTIVITY" in labels
    assert "PENDING" not in labels

def check_terminal(root):
    labels = " ".join(t.text or "" for t in root.iter(SVG + "text"))
    for label in ("PUBLIC REPOSITORIES", "STARS RECEIVED", "FOLLOWERS", "YEARLY CONTRIBUTIONS", "SOURCE: GITHUB"):
        assert label in labels, f"Missing stat: {label}"
    assert "SYNC PENDING" not in labels
    ascii_lines = generator.ascii_portrait()
    assert len(ascii_lines) == 40 and all(len(x) == 64 for x in ascii_lines)

def main():
    # Check source generator's pure formatting even without network access.
    end = date(2026, 10, 29)
    sample = {(end-timedelta(days=k)).isoformat(): (k % 8) for k in range(370)}
    sample_svg = generator.calendar_svg(sample, 150)
    ET.fromstring(sample_svg)
    assert 'opacity="1"' in sample_svg

    for path in ("banner.svg", "contributions.svg", "terminal.svg"):
        parse(path)
    check_heatmap(parse("contributions.svg"))
    check_terminal(parse("terminal.svg"))
    with Image.open(ASSETS / "avatar-hd.png") as im:
        assert im.width >= 256 and im.height >= 256, "Avatar resolution too low"
        assert im.mode in ("RGBA", "P"), "Avatar requires transparent background"
        im.verify()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for expected in ("بلاصتي ميش هنا", "T-Flow", "dz-dashboard", "khotwa", "contributions.svg", "terminal.svg"):
        assert expected in readme, f"README missing {expected}"
    print("PASS: SVG XML, data panels, ASCII dimensions, static heatmap fallback, image and README")

if __name__ == "__main__":
    main()
