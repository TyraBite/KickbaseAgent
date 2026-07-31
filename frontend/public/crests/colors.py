PAGE_LIGHT = "#f8fafc"
PAGE_DARK = "#020617"
RING = "#64748b"
TEXT_LIGHT = "#ffffff"
TEXT_DARK = "#020617"

BRAND = {"brand-400": "#22dd80", "brand-500": "#0fc46a", "brand-600": "#0a9d55",
         "brand-700": "#0a7a45"}

CLUB_COLORS = [
    ("FCB", "Bayern München", "#DF2127", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("FCA", "FC Augsburg", "#BA3733", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("SVW", "Werder Bremen", "#009556", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("BVB", "Borussia Dortmund", "#FFE800", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("SVE", "SV Elversberg", "#1A1A1A", "Vereinsseite: Vereinsfarben Schwarz/Weiss, kein Hex veroeffentlicht"),
    ("SGE", "Eintracht Frankfurt", "#CE291F", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("SCF", "SC Freiburg", "#1A1A1A", "Adobe + sportcolorcodes: Hauptfarbe Schwarz"),
    ("HSV", "Hamburger SV", "#004087", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("TSG", "TSG Hoffenheim", "#1C63B7", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("KOE", "1. FC Köln", "#EB2206", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("RBL", "RB Leipzig", "#E0223C", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("B04", "Bayer 04 Leverkusen", "#E4210B", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("BMG", "Borussia Mönchengladbach", "#1A1A1A", "Adobe + sportcolorcodes: Hauptfarbe Schwarz"),
    ("M05", "1. FSV Mainz 05", "#E62100", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("SCP", "SC Paderborn 07", "#005CA8", "encycolorpedia: Farbe des SCP-Logos"),
    ("S04", "FC Schalke 04", "#0063AA", "Adobe (#0063aa); brandcolorcode nennt #004B9C"),
    ("VFB", "VfB Stuttgart", "#F22B1A", "Adobe-Farbcodes der Bundesliga (Logo 2017/18)"),
    ("FCU", "1. FC Union Berlin", "#EB1923", "teamcolorcodes, Pantone 1788 C"),
]

def rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))

def luminance(value):
    def channel(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b

def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)

def distance(a, b):
    return sum((x - y) ** 2 for x, y in zip(rgb(a), rgb(b))) ** 0.5

def foreground(bg):
    return TEXT_DARK if contrast(bg, TEXT_LIGHT) < 3.0 else TEXT_LIGHT

CLUBS = [(code, name, bg, foreground(bg)) for code, name, bg, _ in CLUB_COLORS]
