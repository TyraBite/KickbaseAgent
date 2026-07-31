import os
from icons4 import FILES, ALTERNATIVES

TARGET = "/mnt/user-data/outputs/icons-preview.html"
BY_NAME = {name: markup for name, markup, *_ in FILES + ALTERNATIVES}

def sized(key, px, markup=None):
    source = markup if markup is not None else BY_NAME[key]
    return source.replace("<svg ", f'<svg style="width:{px}px;height:{px}px" ', 1)

POSITIONS = [("position-torwart.svg", "Torwart", "TW", "Manuel Neuer"),
             ("position-abwehr.svg", "Abwehr", "ABW", "David Raum"),
             ("position-mittelfeld.svg", "Mittelfeld", "MF", "Jamie Leweling"),
             ("position-sturm.svg", "Sturm", "ST", "Conrad Harder")]

COMPARE = [("position-torwart.svg", "torwart-ohne-netz",
            "Tor mit Netz gegen Tor ohne Netz"),
           ("position-abwehr.svg", "abwehr-vorher",
            "Schild spitzer gegen die Version von vorher"),
           ("position-mittelfeld.svg", "mittelfeld-ohne-nummer",
            "Trikot von hinten mit 10 gegen ohne Nummer")]

FITNESS = [("status-verletzt.svg", "Verletzt", "#fee2e2", "#b91c1c", "#450a0a", "#fca5a5"),
           ("status-angeschlagen.svg", "Angeschlagen", "#fef3c7", "#b45309", "#451a03", "#fcd34d"),
           ("status-aufbau.svg", "Im Aufbau", "#e0f2fe", "#0369a1", "#082f49", "#7dd3fc"),
           ("status-fit.svg", "Fit", "#d1fae5", "#047857", "#022c22", "#6ee7b7")]

def position_table(mode):
    rows = []
    for file_key, label, short, player in POSITIONS:
        rows.append(
            f'<tr><td class="lbl">{label}<span>{short}</span></td>'
            f'<td><span class="player">{sized(file_key, 16)}{player}</span></td>'
            f'<td>{sized(file_key, 16)}</td>'
            f'<td>{sized(file_key, 20)}</td>'
            f'<td>{sized(file_key, 24)}</td>'
            f'<td>{sized(file_key, 64)}</td></tr>')
    return (f'<table class="grid {mode}"><thead><tr><th>Position</th>'
            f'<th>12px Text</th><th>16px</th><th>20px</th><th>24px</th>'
            f'<th>64px</th></tr></thead>{"".join(rows)}</table>')

def compare_table(mode):
    rows = []
    for a, b, caption in COMPARE:
        rows.append(
            f'<tr><td class="lbl">{caption}</td>'
            f'<td>{sized(a, 16)}{sized(a, 24)}{sized(a, 64)}</td>'
            f'<td class="sep">{sized(b, 16)}{sized(b, 24)}{sized(b, 64)}</td></tr>')
    return (f'<table class="grid {mode}"><thead><tr><th>Vergleich</th>'
            f'<th>in den Dateien</th><th class="sep">Alternative</th></tr></thead>'
            f'{"".join(rows)}</table>')

def pitch_table(mode):
    rows = []
    for key, label in (("pitch-torwart", "Torwart"), ("pitch-abwehr", "Abwehr"),
                       ("pitch-mittelfeld", "Mittelfeld"), ("pitch-sturm", "Sturm")):
        rows.append(f'<tr><td class="lbl">{label}</td>'
                    f'<td>{sized(key, 16)}</td><td>{sized(key, 24)}</td>'
                    f'<td>{sized(key, 64)}</td></tr>')
    return (f'<table class="grid {mode}"><thead><tr><th>Spielfeldzone</th>'
            f'<th>16px</th><th>24px</th><th>64px</th></tr></thead>'
            f'{"".join(rows)}</table>')

def fitness_table(mode):
    rows = []
    for key, label, bg_l, fg_l, bg_d, fg_d in FITNESS:
        bg, fg = (bg_l, fg_l) if mode == "light" else (bg_d, fg_d)
        rows.append(
            f'<tr><td class="lbl">{label}</td>'
            f'<td><span class="pill" style="background:{bg};color:{fg}">'
            f'{sized(key, 12)}{label}</span></td>'
            f'<td><span class="pill" style="background:{bg};color:{fg}">'
            f'{sized(key, 14)}{label}</span></td>'
            f'<td style="color:{fg}">{sized(key, 56)}</td></tr>')
    return (f'<table class="grid {mode}"><thead><tr><th>Zustand</th>'
            f'<th>Icon 12px</th><th>Icon 14px</th><th>56px</th></tr></thead>'
            f'{"".join(rows)}</table>')

def empty_panel(mode):
    grey = "#94a3b8" if mode == "light" else "#64748b"
    return (f'<div class="panel {mode}"><div class="listbox" style="color:{grey}">'
            f'{sized("empty-state.svg", 48)}<p>Noch keine Eintr&auml;ge.</p></div>'
            f'<div class="scale" style="color:{grey}">'
            f'{sized("empty-state.svg", 48)}{sized("empty-state.svg", 64)}'
            f'{sized("empty-state.svg", 112)}</div></div>')

def logo_panel(mode):
    return (f'<div class="panel {mode}">'
            f'<div class="brandrow">{sized("logo.svg", 40)}'
            f'<span class="brandname">KickbaseAgent</span>'
            f'<span class="tag">logo.svg</span></div>'
            f'<div class="scale">{sized("logo.svg", 40)}{sized("logo.svg", 96)}</div></div>')

STYLE = """
 body { font: 14px/1.5 system-ui, sans-serif; margin: 0; padding: 28px; background: #fff;
        color: #0f172a; }
 h1 { font-size: 18px; margin: 0 0 6px; }
 h2 { font-size: 13px; margin: 32px 0 4px; text-transform: uppercase;
      letter-spacing: .05em; color: #475569; }
 p.lead, p.note { max-width: 86ch; color: #475569; margin: 0 0 10px; }
 p.note { font-size: 12px; color: #64748b; }
 .pair { display: flex; gap: 18px; flex-wrap: wrap; align-items: flex-start; }
 .grid { border-collapse: collapse; border-radius: 10px; overflow: hidden; }
 .grid th { font-size: 10px; text-transform: uppercase; letter-spacing: .04em;
            font-weight: 600; padding: 7px 12px; text-align: left; opacity: .55; }
 .grid td { padding: 9px 12px; vertical-align: middle; }
 .grid td.lbl { font-size: 12px; font-weight: 600; white-space: nowrap; }
 .grid td.lbl span { display: block; font-weight: 400; opacity: .5; font-size: 10px; }
 .grid .sep { border-left: 1px solid rgba(128,128,128,.35); }
 .grid.light { background: #f8fafc; color: #334155; }
 .grid.dark { background: #020617; color: #cbd5e1; }
 .player { display: inline-flex; align-items: center; gap: 5px; font-size: 12px;
           white-space: nowrap; }
 .pill { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px;
         border-radius: 9999px; font-size: 12px; font-weight: 500; white-space: nowrap; }
 .panel { padding: 18px; border-radius: 10px; flex: 1 1 330px; }
 .panel.light { background: #f8fafc; }
 .panel.dark { background: #020617; }
 .listbox { border: 1px dashed currentColor; border-radius: 10px; padding: 22px;
            text-align: center; }
 .listbox p { margin: 8px 0 0; font-size: 13px; }
 .scale { display: flex; align-items: flex-end; gap: 16px; margin-top: 16px; }
 .brandrow { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
 .brandname { font-size: 17px; font-weight: 700; letter-spacing: -.01em; }
 .panel.light .brandname { color: #0f172a; }
 .panel.dark .brandname { color: #f8fafc; }
 .tag { font-size: 10px; opacity: .5; font-family: ui-monospace, monospace; }
 .panel.dark .tag, .panel.dark .listbox p { color: #94a3b8; }
"""

def build():
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<title>Icons &mdash; Vorschau 4</title><style>{STYLE}</style></head>
<body>
<h1>KickbaseAgent &mdash; Icon-Vorschau, vierter Durchgang</h1>
<p class="lead">Alle Icons inline im DOM, weil <code>currentColor</code> nur so erbt.
Die 64px- und 56px-Spalten dienen der Formkontrolle, so wird nichts angezeigt.</p>

<h2>1 &mdash; Positionen, vierter Durchgang</h2>
<p class="note">Tor jetzt mit Netz (2 &times; 2 Maschen), Schild l&auml;uft unten spitz
zusammen, Trikot von hinten mit flachem Nackenausschnitt und der 10 im oberen Drittel.
Die Spalten 16 / 20 / 24px zeigen, wo Netz und Nummer kippen.</p>
<div class="pair">{position_table("light")}{position_table("dark")}</div>

<h2>1b &mdash; direkte Vergleiche</h2>
<p class="note">Netz 0,80px bei 16px, Ziffernstrich 0,90px bei 16px &mdash; beide unter
einem Pixel. Bei 24px sind es 1,20px und 1,36px. Hier siehst du, ob das bei 16px noch
tr&auml;gt oder nur Unruhe macht.</p>
<div class="pair">{compare_table("light")}{compare_table("dark")}</div>

<h2>1c &mdash; Spielfeldzone, weiterhin als Option</h2>
<div class="pair">{pitch_table("light")}{pitch_table("dark")}</div>

<h2>2 &mdash; Fitness-Status (unver&auml;ndert)</h2>
<div class="pair">{fitness_table("light")}{fitness_table("dark")}</div>

<h2>3 &mdash; Empty-State (unver&auml;ndert)</h2>
<div class="pair">{empty_panel("light")}{empty_panel("dark")}</div>

<h2>4 &mdash; Logo: Agent</h2>
<p class="note">Unver&auml;ndert seit der letzten Runde.</p>
<div class="pair">{logo_panel("light")}{logo_panel("dark")}</div>
</body></html>
"""

if __name__ == "__main__":
    with open(TARGET, "w", encoding="utf-8") as handle:
        handle.write(build())
    print(f"{TARGET}: {os.path.getsize(TARGET) / 1024:.0f} KB")
