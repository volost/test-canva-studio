"""Shared helpers for the Canva-side script tests: fixtures and a tiny synthetic design."""
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FX = Path(__file__).parent / "fixtures"
CANVA = ROOT / "canva"


def load(name):
    return json.loads((FX / name).read_text(encoding="utf-8"))


def run_cli(script, *args):
    """Run `python -I canva/<script>` and return the finished process (stdout/stderr as text)."""
    return subprocess.run([sys.executable, "-I", str(CANVA / script), *map(str, args)],
                          capture_output=True, text=True, cwd="/")


def region(text, color="#000000", font="FONT1", size=20.0, align="center"):
    return {"chars": text, "color": color, "fontRef": font, "fontSize": size, "weight": "normal",
            "style": "normal", "align": align, "lh": 1.2, "ls": 0, "link": "", "decoration": "none"}


def text_rec(text, color="#000000", page="PGmini01", box=(10.0, 20.0, 600.0, 50.0), order=0):
    return {"type": "text", "page": page, "section": "SEC1", "parent": None, "order": order, "box": list(box),
            "rotation": 0.0, "opacity": 1, "locked": False, "regions": [region(text, color)], "text": text}


def cell_rec(text, page="PGmini01"):
    regs = [region(text, size=12.0)] if text else []
    return {"type": "cell", "page": page, "section": "SEC1", "parent": "TBL", "cell": "A1", "regions": regs,
            "text": text, "span": [1, 1]}


def rect_rec(media, page="PGmini01", box=(100.0, 100.0, 300.0, 200.0), recoloring=None, order=1):
    return {"type": "rect", "page": page, "section": "SEC1", "parent": None, "order": order, "box": list(box),
            "rotation": 0.0, "opacity": 1, "locked": False,
            "fill": {"color": None, "flip": [False, False], "imageBox": [0.0, 0.0, box[2], box[3], 0.0],
                     "media": media, "mediaType": "image", "recoloring": recoloring},
            "stroke": {"color": "#000000", "weight": 0}}


def shape_rec(color, page="PGmini01", box=(0.0, 0.0, 50.0, 50.0), order=2, stroke="#000000"):
    return {"type": "shape", "page": page, "section": "SEC1", "parent": None, "order": order, "box": list(box),
            "rotation": 0.0, "opacity": 1, "locked": False, "innerText": [""],
            "paths": [{"d": "abc", "dlen": 3, "fill": {"color": color, "flip": [False, False]}, "round": 0,
                       "stroke": {"color": stroke, "weight": 1}}]}


def line_rec(color, page="PGmini01", order=3):
    return {"type": "line", "page": page, "section": "SEC1", "parent": None, "order": order,
            "box": [5.0, 5.0, 100.0, 6.0], "rotation": 0.0, "opacity": 1, "locked": False,
            "stroke": {"color": color, "weight": 6}, "geometry": "straight", "ends": [["NONE", 0, 0], ["NONE", 1, 1]]}


def section_rec(media=None, page="PGmini01", elements=()):
    return {"type": "section", "page": page, "section": "SEC1", "size": [1000, 700],
            "background": {"color": None, "flip": [False, False], "imageBox": [0, 0, 1000, 700, 0.0],
                           "media": media, "mediaType": "image", "recoloring": None} if media else None,
            "elements": list(elements)}


def mini_map():
    return copy.deepcopy(load("map_min.json"))


def mini_style():
    s = copy.deepcopy(load("style_min.json"))
    s["colour_roles"]["heading"] = "ink"
    return s


def mini_facts():
    """Synthetic facts for tests/fixtures/map_min.json (symbolic locators, page id PGmini01)."""
    return {
        "p1/text/names": text_rec("ANNA & BEN", order=0),
        "p1/text/intro": text_rec("Together with their families, they invite you to celebrate their wedding day.", order=1),
        "p1/text/footer": text_rec("Made with love", order=2),
        "p1/cell/day": cell_rec("17"),
        "p1/colour/background": shape_rec("#ffffff"),
        "p1/image/hero": rect_rec("MAOLD1"),
        "p1/image/florals": rect_rec("MAOLD2"),
        "p1/image/env-cover": rect_rec("MAOLD3"),
        "p1/image/env-flap": rect_rec("MAOLD4"),
        "p1/image/seal": rect_rec("MAOLD5", box=(50.0, 50.0, 200.0, 200.0)),
    }


def mini_texts():
    return {"p1/text/names": "CLARA & DAVID", "p1/text/intro":
            "Together with their families, they invite you to celebrate their wedding day.",
            "p1/cell/day": "18"}
