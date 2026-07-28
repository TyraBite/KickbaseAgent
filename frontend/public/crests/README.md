# Vereinswappen

Self-hosted, damit keine Drittanbieter-URL bricht (Repo ist öffentlich).
Dateiname = `team_id` (z.B. `9.svg` für Stuttgart), nicht der Vereinsname
(robuster gegen Sonderzeichen wie "M'gladbach").

Fehlt eine Datei, fällt `TeamCrest` (`frontend/src/components/SpekulationTab.tsx`)
automatisch auf einen Initialen-Badge zurück — Wappen können nach und nach
ergänzt werden, kein Big-Bang nötig.

Bekannte `team_id`/Verein-Paare (aus `market_listings`, 27.07.2026):
13 Augsburg, 10 Bremen, 3 Dortmund, 77 Elversberg, 4 Frankfurt, 5 Freiburg,
6 Hamburg, 14 Hoffenheim, 28 Köln, 43 Leipzig, 7 Leverkusen, 15 M'gladbach,
18 Mainz, 29 Paderborn, 8 Schalke, 9 Stuttgart, 40 Union Berlin.
