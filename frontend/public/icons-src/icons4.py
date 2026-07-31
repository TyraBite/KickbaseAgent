from icons import polygon, circle_path, rounded_rect, path, injured, doubtful, building, fit
from icons2 import wrap, sturm, empty_state, pitch
from icons3 import NUMERALS, logo_spark

NET = 1.2

def torwart():
    post = 2.9
    left_x, right_x = 2.8, 18.3
    top, bottom = 4.4, 19.6
    inner_left, inner_right = left_x + post, right_x
    inner_top = top + post
    columns = [inner_left + (inner_right - inner_left) * i / 3 for i in (1, 2)]
    rows = [inner_top + (bottom - inner_top) * i / 3 for i in (1, 2)]
    mesh = [rounded_rect(x - NET / 2, inner_top, NET, bottom - inner_top, 0)
            for x in columns]
    mesh += [rounded_rect(inner_left, y - NET / 2, inner_right - inner_left, NET, 0)
             for y in rows]
    frame = [rounded_rect(left_x, top, right_x - left_x + post, post, 0.7),
             rounded_rect(left_x, top, post, bottom - top, 0.7),
             rounded_rect(right_x, top, post, bottom - top, 0.7)]
    body = "".join(path(m) for m in mesh) + "".join(path(f) for f in frame)
    return wrap(24, body, label="Torwart")

def abwehr():
    d = ("M3.9 2.5 H20.1 V12.0 "
         "C20.1 16.4 13.4 18.0 12 21.5 "
         "C10.6 18.0 3.9 16.4 3.9 12.0 Z")
    return wrap(24, path(d), label="Abwehr")

BACK_JERSEY = ("M9.2 2.8 H14.8 L21.7 6.4 L19.3 11.7 L17.5 10.8 V21.6 "
               "H6.5 V10.8 L4.7 11.7 L2.3 6.4 Z")
BACK_COLLAR = "M9.2 2.5 Q12 5.6 14.8 2.5 Z"

def mittelfeld(cap=8.4, center_y=14.2, number="10"):
    digits, width = NUMERALS.text_path(number, cap, 12.0, center_y, tracking=0.02)
    body = (f'<path fill-rule="evenodd" clip-rule="evenodd" '
            f'd="{BACK_JERSEY} {BACK_COLLAR} {digits}"/>')
    return wrap(24, body, label="Mittelfeld"), width, cap, center_y

def mittelfeld_blank():
    body = (f'<path fill-rule="evenodd" clip-rule="evenodd" '
            f'd="{BACK_JERSEY} {BACK_COLLAR}"/>')
    return wrap(24, body, label="Mittelfeld")


JERSEY, NUMBER_WIDTH, NUMBER_CAP, NUMBER_Y = mittelfeld()

FILES = [
    ("position-torwart.svg", torwart(), 24, 16),
    ("position-abwehr.svg", abwehr(), 24, 16),
    ("position-mittelfeld.svg", JERSEY, 24, 16),
    ("position-sturm.svg", sturm(), 24, 16),
    ("status-verletzt.svg", injured(), 16, 12),
    ("status-angeschlagen.svg", doubtful(), 16, 12),
    ("status-aufbau.svg", building(), 16, 12),
    ("status-fit.svg", fit(), 16, 12),
    ("empty-state.svg", empty_state(), 48, 48),
    ("logo.svg", logo_spark(), 40, 40),
]

ALTERNATIVES = [
    ("mittelfeld-ohne-nummer", mittelfeld_blank(), 24, 16),
    ("abwehr-vorher", wrap(24, path("M3.9 3.0 H20.1 V11.4 C20.1 16.5 16.6 19.4 12 21.0 "
                                    "C7.4 19.4 3.9 16.5 3.9 11.4 Z"),
                           label="Abwehr vorher"), 24, 16),
    ("torwart-ohne-netz", wrap(24, "".join(path(d) for d in [
        rounded_rect(2.8, 4.4, 18.4, 2.9, 0.7),
        rounded_rect(2.8, 4.4, 2.9, 15.2, 0.7),
        rounded_rect(18.3, 4.4, 2.9, 15.2, 0.7)]), label="Torwart ohne Netz"), 24, 16),
    ("pitch-torwart", pitch("Torwart"), 24, 16),
    ("pitch-abwehr", pitch("Abwehr"), 24, 16),
    ("pitch-mittelfeld", pitch("Mittelfeld"), 24, 16),
    ("pitch-sturm", pitch("Sturm"), 24, 16),
]
