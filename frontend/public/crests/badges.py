import os
import xml.etree.ElementTree as ET
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.misc.transform import Transform
from colors import CLUBS, RING

FONT_FILE = "/mnt/skills/examples/canvas-design/canvas-fonts/BigShoulders-Bold.ttf"
BOX = 64.0
RING_RADIUS = 31.0
RING_WIDTH = 2.0
TRACKING = 0.03
SAFE_WIDTH = 50.5
MAX_CAP = 24.0

class Face:
    def __init__(self, path):
        self.font = TTFont(path)
        self.upm = self.font["head"].unitsPerEm
        self.glyphset = self.font.getGlyphSet()
        self.cmap = self.font.getBestCmap()
        self.cap = self.font["OS/2"].sCapHeight

    def advance(self, char):
        return self.glyphset[self.cmap[ord(char)]].width

    def record(self, char):
        pen = RecordingPen()
        self.glyphset[self.cmap[ord(char)]].draw(pen)
        return pen

    def string_width(self, text):
        return (sum(self.advance(c) for c in text)
                + TRACKING * self.upm * (len(text) - 1))

FACE = Face(FONT_FILE)
SCALE = min(MAX_CAP / FACE.cap,
            SAFE_WIDTH / max(FACE.string_width(code) for code, *_ in CLUBS))
CAP_RENDERED = FACE.cap * SCALE
BASELINE = BOX / 2 + CAP_RENDERED / 2

def string_path(text):
    x = (BOX - FACE.string_width(text) * SCALE) / 2
    segments = []
    for char in text:
        sink = SVGPathPen(None, ntos=lambda v: f"{v:.2f}")
        FACE.record(char).replay(
            TransformPen(sink, Transform(SCALE, 0, 0, -SCALE, x, BASELINE)))
        segments.append(sink.getCommands())
        x += (FACE.advance(char) + TRACKING * FACE.upm) * SCALE
    return " ".join(segments)

def build_svg(code, name, bg, fg):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64" '
        f'role="img" aria-label="{name}">\n'
        f'  <title>{name}</title>\n'
        f'  <circle cx="32" cy="32" r="32" fill="{bg}"/>\n'
        f'  <path d="{string_path(code)}" fill="{fg}"/>\n'
        f'  <circle cx="32" cy="32" r="{RING_RADIUS:g}" fill="none" stroke="{RING}" '
        f'stroke-width="{RING_WIDTH:g}"/>\n'
        f'</svg>\n'
    )

def write(target):
    os.makedirs(target, exist_ok=True)
    written = []
    for code, name, bg, fg in CLUBS:
        markup = build_svg(code, name, bg, fg)
        ET.fromstring(markup)
        destination = os.path.join(target, f"{code}.svg")
        with open(destination, "w", encoding="utf-8") as handle:
            handle.write(markup)
        written.append(destination)
    return written

if __name__ == "__main__":
    files = write("/mnt/user-data/outputs/wappen")
    print(f"Versalhöhe {CAP_RENDERED:.2f}/64, Grundlinie {BASELINE:.2f}, "
          f"{len(files)} Dateien")
