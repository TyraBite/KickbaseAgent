# Vereinswappen

Self-hosted, damit keine Drittanbieter-URL bricht (Repo ist öffentlich).
Dateiname = offizielles 3-Buchstaben-TV-Kürzel (`TEAM_ABBR` in
`frontend/src/components/SpekulationTab.tsx`), z.B. `BVB.svg` für
Dortmund — nicht `team_id` oder der volle Vereinsname (robuster gegen
Sonderzeichen wie "M'gladbach").

Fehlt eine Datei, fällt `TeamCrest` automatisch auf das Kürzel-Badge
zurück — Wappen können nach und nach ergänzt werden, kein Big-Bang nötig.

Bekannte Kürzel/Verein-Paare (aus `data/kickbase.db`, `own_squad` +
`market_listings`, alle `fetched_at`, Stand 28.07.2026), per WebSearch
gegengecheckt:

| Kürzel | Verein |
|--------|--------|
| FCB | Bayern |
| FCA | Augsburg |
| SVW | Bremen |
| BVB | Dortmund |
| SVE | Elversberg |
| SGE | Frankfurt |
| SCF | Freiburg |
| HSV | Hamburg |
| TSG | Hoffenheim |
| KOE | Köln |
| RBL | Leipzig |
| B04 | Leverkusen |
| BMG | M'gladbach |
| M05 | Mainz |
| SCP | Paderborn |
| S04 | Schalke |
| VFB | Stuttgart |
| FCU | Union Berlin |
