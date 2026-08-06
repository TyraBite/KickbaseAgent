# News-Sentiment: Negations-Bug + Signed Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Zwei in `HANDOFF.md` dokumentierte, live verifizierte Technische Schulden in `src/news_sentiment.py` beheben: (1) ein Ausschluss-/Dementi-Fund wie "Wechsel ... definitiv ausgeschlossen" wird von `germansentiment` als `negative` fehlklassifiziert, weil das Modell auf das Reizwort "ausgeschlossen" reagiert, ohne die Verneinung zu invertieren (live verifiziert 2026-08-04, Amiri-Headline, Score 0.92); (2) es wird nur die Argmax-Konfidenz des vorhergesagten Labels gespeichert, nicht die volle 3-Klassen-Verteilung — ein kontinuierlicher `signed_score = p(positive) - p(negative)` würde auch innerhalb eines als "neutral" gelabelten Bereichs Gradient erhalten (live beobachtet: Amiri-Gerüchtephase vs. danach, beide "neutral" gelabelt, aber unterschiedlich signiert).

**Architecture:** Beide Fixes in `classify_sentiment()` (`src/news_sentiment.py`) verzahnt: die Funktion extrahiert jetzt alle drei Klassen-Wahrscheinlichkeiten statt nur der Argmax-Wahrscheinlichkeit, berechnet daraus `signed_score`, und wendet danach eine schlanke, bewusst enge Negations-Override-Heuristik an (ein einziger live verifizierter Trigger-Begriff, mit explizitem Kollisions-Schutz gegen die entgegengesetzte Bedeutung im selben Themenfeld). Der Override betrifft Label UND `signed_score` gemeinsam, damit er auch das nachgelagerte ML-Feature erreicht (`market_predictor.py::_sentiment_features_as_of()`), das ab jetzt `signed_score` statt der groben Label-Zuordnung mittelt — mit Rückfall auf die alte Zuordnung für bereits in Firestore liegende Alt-Artikel ohne `signed_score`-Feld (Firestore ist schemalos, keine Migration nötig).

**Tech Stack:** Python, `unittest` (Tests laufen komplett gegen gemockte `germansentiment`-Aufrufe, kein echtes ~440MB BERT-Modell/Torch nötig).

## Global Constraints

- **Kein Fix ohne Nutzennachweis des Gesamtfeatures** (`HANDOFF.md`) gilt weiterhin für das große Ganze (Cold-Start: aktuell 3.276 Artikel/333 Spieler/11 Tage Historie, live geprüft 2026-08-06) — dieser Plan behebt NUR die zwei dokumentierten Technischen Schulden, nicht die strukturelle Blindstelle bei "Spieler bleibt"-Meldungen ohne explizites Reizwort oder das Presse-Coverage-Loch bei Bankspielern (`HANDOFF.md`, Abschnitt "Offen aus feedback/current"). Diese bleiben offen und werden NICHT in diesem Plan adressiert.
- Negations-Override bewusst NUR mit dem einen live verifizierten Cue-Begriff ("ausgeschlossen") — keine weiteren, unverifizierten Cue-Wörter (z.B. "dementiert") erfinden. `CLAUDE.md`: "Keine Bedeutung erfinden, die nicht verifiziert ist."
- Override dämpft `negative` auf `neutral`, dreht NIEMALS auf `positive` — wir wissen nur, dass es nicht sicher negativ ist, keine positive Färbung erfinden (`CLAUDE.md`: "ehrliche Daten schlagen vollständige Daten").
- Kollisions-Schutz ist Pflicht: "ausgeschlossen" im Kader-/Startelf-/Aufstellungs-Kontext ("aus dem Kader ausgeschlossen") ist die ECHTE negative Bedeutung (Verletzung/Formkrise/Streit) und darf NICHT überschrieben werden. Ohne den entsprechenden Test gilt der Fix als nicht abgeschlossen.
- `FEATURES` in `market_predictor.py` bleibt unverändert (`"avg_sentiment_7d"`, `"news_volume_7d"` sind bereits aktive Features) — nur die Berechnung ändert sich, kein neues Feature.
- `player_news_log` ist schemalos (Firestore) — Alt-Dokumente ohne `sentiment_signed_score` sind erwartet und brauchen KEINE Backfill-Migration, nur einen Fallback-Pfad im Lesecode.
- Jeder Bugfix braucht einen automatisierten Test (TDD: erst rot, dann grün) plus Mutation-Check (Fix temporär zurücknehmen → Test muss rot werden).
- Immer `python -m pytest` (nicht bares `pytest`) — `tests/` hat kein `__init__.py`.

---

## File Structure

- Modify: `src/news_sentiment.py` — `classify_sentiment()`, neue Helper `_has_negation_override_cue()`, `collect_news_sentiment()`.
- Modify: `tests/test_news_sentiment.py` — `ClassifySentimentTests`, `CollectNewsSentimentTests`.
- Modify: `src/market_predictor.py` — `_sentiment_features_as_of()`, neue Helper `_article_signed_score()`.
- Modify: `tests/test_market_predictor.py` — Tests rund um `_sentiment_features_as_of`.

---

### Task 1: `classify_sentiment()` — signed_score + Negations-Override-Heuristik

**Files:**
- Modify: `src/news_sentiment.py:118-133` (bestehende `classify_sentiment()`), Zeilen 184-196 (`collect_news_sentiment()`'s `entries.append(...)`-Block)
- Modify: `tests/test_news_sentiment.py:188-246` (`ClassifySentimentTests`, `CollectNewsSentimentTests::test_builds_entry_with_article_hash_and_sentiment`)

**Interfaces:**
- `classify_sentiment(model, texts)` gibt jetzt pro Text `{"label": str, "score": float | None, "signed_score": float}` zurück (bisher nur `label`/`score`) — Aufrufer ist ausschließlich `collect_news_sentiment()` im selben Modul.
- `collect_news_sentiment()`s zurückgegebene Entry-Dicts bekommen ein neues Feld `sentiment_signed_score` (analog zu bestehendem `sentiment_score`/`sentiment_label`) — landet unverändert über `upsert_history_entries()` in `player_news_log`.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_news_sentiment.py`, `ClassifySentimentTests` komplett ersetzen durch:

```python
class ClassifySentimentTests(unittest.TestCase):
    def test_empty_texts_returns_empty_list_without_calling_model(self):
        model = MagicMock()
        self.assertEqual(classify_sentiment(model, []), [])
        model.predict_sentiment.assert_not_called()

    def test_batch_call_maps_label_score_and_signed_score(self):
        model = MagicMock()
        model.predict_sentiment.return_value = (
            ["positive", "negative"],
            [
                [["positive", 0.9761], ["negative", 0.0235], ["neutral", 0.0003]],
                [["positive", 0.01], ["negative", 0.95], ["neutral", 0.04]],
            ],
        )

        result = classify_sentiment(model, ["Text A", "Text B"])

        self.assertEqual(result, [
            {"label": "positive", "score": 0.9761, "signed_score": 0.9761 - 0.0235},
            {"label": "negative", "score": 0.95, "signed_score": 0.01 - 0.95},
        ])
        model.predict_sentiment.assert_called_once_with(["Text A", "Text B"], output_probabilities=True)

    def test_negation_override_downgrades_known_exclusion_headline_to_neutral(self):
        # Live verifizierter Fund (2026-08-04, siehe HANDOFF.md): diese exakte
        # Schlagzeile wurde von germansentiment als "negative" (Score 0.92)
        # eingestuft, obwohl ein ausgeschlossener Wechsel neutrale/gute News ist.
        model = MagicMock()
        headline = "Amiri, Sano, Nebel weg aus Mainz? Für Heidel 'definitiv ausgeschlossen'"
        model.predict_sentiment.return_value = (
            ["negative"],
            [[["positive", 0.03], ["negative", 0.92], ["neutral", 0.05]]],
        )

        result = classify_sentiment(model, [headline])

        self.assertEqual(result, [{"label": "neutral", "score": 0.05, "signed_score": 0.0}])

    def test_negation_override_does_not_trigger_without_cue(self):
        model = MagicMock()
        model.predict_sentiment.return_value = (
            ["negative"],
            [[["positive", 0.05], ["negative", 0.9], ["neutral", 0.05]]],
        )

        result = classify_sentiment(model, ["Spieler fällt wochenlang verletzt aus"])

        self.assertEqual(result, [{"label": "negative", "score": 0.9, "signed_score": 0.05 - 0.9}])

    def test_negation_override_does_not_trigger_for_squad_exclusion_context(self):
        # Kollisions-Schutz: 'ausgeschlossen' im Kader-/Startelf-Kontext ist
        # die GEGENTEILIGE, echte negative Bedeutung (Verletzung/Formkrise) -
        # darf NICHT ueberschrieben werden, nur weil das Reizwort uebereinstimmt.
        model = MagicMock()
        model.predict_sentiment.return_value = (
            ["negative"],
            [[["positive", 0.05], ["negative", 0.85], ["neutral", 0.1]]],
        )

        result = classify_sentiment(model, ["Spieler X aus dem Kader ausgeschlossen"])

        self.assertEqual(result, [{"label": "negative", "score": 0.85, "signed_score": 0.05 - 0.85}])

    def test_negation_override_only_applies_to_negative_label(self):
        # Cue-Wort allein reicht nicht - nur ein vom Modell als "negative"
        # klassifizierter Text wird ueberhaupt geprueft.
        model = MagicMock()
        model.predict_sentiment.return_value = (
            ["neutral"],
            [[["positive", 0.2], ["negative", 0.3], ["neutral", 0.5]]],
        )

        result = classify_sentiment(model, ["Wechsel ausgeschlossen, sagt Trainer"])

        self.assertEqual(result, [{"label": "neutral", "score": 0.5, "signed_score": 0.2 - 0.3}])
```

In `CollectNewsSentimentTests::test_builds_entry_with_article_hash_and_sentiment`, nach der bestehenden `self.assertEqual(entry["sentiment_score"], 0.9)`-Zeile eine Zeile ergänzen:

```python
        self.assertEqual(entry["sentiment_signed_score"], 0.9 - 0.05)
```

(Das bestehende Mock-Return `[[["positive", 0.9], ["negative", 0.05], ["neutral", 0.05]]]` bleibt unverändert — es liefert bereits alle drei Klassen.)

- [ ] **Step 2: Tests laufen lassen, rot bestätigen**

```bash
python -m pytest tests/test_news_sentiment.py -v -k ClassifySentimentTests
```
Expected: FAIL — `classify_sentiment()` gibt bisher kein `signed_score`-Feld zurück, `KeyError`/`AssertionError`.

- [ ] **Step 3: `src/news_sentiment.py` ändern**

Direkt vor `classify_sentiment()` (aktuell Zeile 118) einfügen:

```python
NEGATION_OVERRIDE_CUES = ("ausgeschlossen",)
SQUAD_EXCLUSION_CONTEXT_WORDS = ("kader", "startelf", "aufstellung")


def _has_negation_override_cue(title: str) -> bool:
    """Schlanke, bewusst enge Heuristik gegen EINEN live verifizierten
    Fehlklassifikations-Fall (2026-08-04, siehe HANDOFF.md): germansentiment
    stuft Ausschluss-/Dementi-Meldungen ('Wechsel ... definitiv
    ausgeschlossen') als negativ ein, weil es auf das Reizwort
    'ausgeschlossen' reagiert, ohne die Verneinung/den Kontext zu
    invertieren - tatsaechlich ist ein ausgeschlossener Wechsel neutrale bis
    gute News (Spieler bleibt). SQUAD_EXCLUSION_CONTEXT_WORDS schuetzt vor
    der Kollision mit der GEGENTEILIGEN Bedeutung von 'ausgeschlossen' im
    selben Themenfeld - 'aus dem Kader/der Startelf ausgeschlossen' IST
    echte schlechte News (Verletzung/Formkrise/Streit) und darf NICHT
    ueberschrieben werden. Bewusst nur EIN verifizierter Trigger-Begriff,
    kein breiteres Verneinungs-Set - diese Heuristik deckt nur bekannte
    Formulierungsmuster ab, keine allgemeine Negationserkennung."""
    lowered = title.lower()
    has_cue = any(cue in lowered for cue in NEGATION_OVERRIDE_CUES)
    has_squad_context = any(word in lowered for word in SQUAD_EXCLUSION_CONTEXT_WORDS)
    return has_cue and not has_squad_context
```

Bestehende `classify_sentiment()` (Zeilen 118-133) komplett ersetzen durch:

```python
def classify_sentiment(model: "SentimentModel", texts: list[str]) -> list[dict]:
    """Batch-Klassifikation ueber germansentiment - gibt pro Text
    {label, score, signed_score} zurueck. Batch statt Einzelaufruf pro
    Artikel, da germansentiment.predict_sentiment() nativ Listen akzeptiert
    - spart Modell-Overhead pro Aufruf. score ist die Wahrscheinlichkeit DES
    vorhergesagten Labels (Argmax-Konfidenz). signed_score ist
    p(positive) - p(negative) aus der vollen 3-Klassen-Verteilung - ein
    kontinuierlicher Wert, der auch innerhalb eines als 'neutral' gelabelten
    Bereichs Richtung/Gradient erhaelt (live beobachtet 2026-08-04: in der
    Amiri-Geruechtephase vor der Verbleib-Verkuendung lag der signierte
    Score klar negativer als danach, obwohl beide Phasen als 'neutral'
    gelabelt waren). Wendet zusaetzlich die enge Negations-Override-
    Heuristik an (siehe _has_negation_override_cue): ein als 'negative'
    klassifizierter Text mit passendem Cue wird auf 'neutral' gedaempft
    (NICHT auf 'positive' gedreht - wir wissen nur, dass es nicht sicher
    negativ ist, keine positive Faerbung erfinden, siehe CLAUDE.md
    'ehrliche Daten schlagen vollstaendige Daten') und signed_score wird
    fuer diesen Fall auf 0.0 gekappt, damit der Override auch das
    nachgelagerte ML-Feature (avg_sentiment_7d in market_predictor.py)
    tatsaechlich erreicht."""
    if not texts:
        return []
    labels, probabilities = model.predict_sentiment(texts, output_probabilities=True)
    results = []
    for text, label, probs in zip(texts, labels, probabilities):
        prob_by_label = {p[0]: float(p[1]) for p in probs}
        score = prob_by_label.get(label)
        signed_score = prob_by_label.get("positive", 0.0) - prob_by_label.get("negative", 0.0)
        if label == "negative" and _has_negation_override_cue(text):
            label = "neutral"
            score = prob_by_label.get("neutral")
            signed_score = 0.0
        results.append({"label": label, "score": score, "signed_score": signed_score})
    return results
```

In `collect_news_sentiment()` (aktuell Zeilen 186-196), im `entries.append({...})`-Block nach der Zeile `"sentiment_score": sentiment["score"],` ergänzen:

```python
            "sentiment_signed_score": sentiment["signed_score"],
```

- [ ] **Step 4: Tests laufen lassen, grün bestätigen**

```bash
python -m pytest tests/test_news_sentiment.py -v
```
Expected: PASS, alle Tests in der Datei (nicht nur `ClassifySentimentTests`) - stellt sicher, dass `collect_news_sentiment()`s andere Tests (Artikel-Hash, Skip-Logik etc.) nicht kollateral gebrochen sind.

- [ ] **Step 5: Mutation-Check**

Kommentiere im Override-Zweig temporär `label = "neutral"` aus (oder setze `_has_negation_override_cue` fest auf `return False`), laufe `test_negation_override_downgrades_known_exclusion_headline_to_neutral` erneut - MUSS rot werden. Danach den Fix wiederherstellen und alle Tests der Datei erneut grün bestätigen.

- [ ] **Step 6: Commit**

```bash
git add src/news_sentiment.py tests/test_news_sentiment.py
git commit -m "news_sentiment: signed_score (p(pos)-p(neg)) + enge Negations-Override-Heuristik fuer Ausschluss-Meldungen"
```

---

### Task 2: `market_predictor.py::_sentiment_features_as_of()` — signed_score mit Legacy-Fallback

**Files:**
- Modify: `src/market_predictor.py:97, 254-275`
- Modify: `tests/test_market_predictor.py` (neue Tests direkt neben den bestehenden `_sentiment_features_as_of`-Tests, ca. Zeile 705-782)

**Interfaces:**
- Consumes: Artikel-Dicts aus `player_news_log` (`{"pub_date": ..., "sentiment_label": ..., "sentiment_signed_score": <optional>}`) - `sentiment_signed_score` fehlt auf allen vor Task 1 geschriebenen Alt-Dokumenten (Firestore ist schemalos).
- Bestehende Aufrufer (`_fetch_player_training_frame()`, alle Call-Sites in `tests/test_market_predictor.py`) bleiben unveraendert - Rueckgabeform von `_sentiment_features_as_of()` (`{"avg_sentiment_7d": float, "news_volume_7d": int}`) aendert sich nicht, nur die interne Berechnung.

- [ ] **Step 1: Failing Tests schreiben**

In `tests/test_market_predictor.py`, direkt nach den bestehenden `_sentiment_features_as_of`-Tests (nach der Methode, die `test_unknown_sentiment_label_raises_key_error` heisst, ca. Zeile 782) ergaenzen:

```python
    def test_uses_signed_score_when_present_instead_of_label(self):
        articles = [
            {"pub_date": "2026-08-01", "sentiment_label": "neutral", "sentiment_signed_score": -0.6},
            {"pub_date": "2026-08-01", "sentiment_label": "neutral", "sentiment_signed_score": -0.4},
        ]
        result = _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
        self.assertAlmostEqual(result["avg_sentiment_7d"], -0.5)

    def test_falls_back_to_label_score_for_legacy_articles_without_signed_score(self):
        # Firestore ist schemalos - Artikel, die VOR diesem Fix geschrieben
        # wurden, haben kein 'sentiment_signed_score'-Feld. Keine Migration
        # geplant, der Lesecode muss den Fall abfangen.
        articles = [{"pub_date": "2026-08-01", "sentiment_label": "negative"}]
        result = _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
        self.assertEqual(result["avg_sentiment_7d"], -1)

    def test_mixes_signed_score_and_legacy_label_fallback_in_same_window(self):
        articles = [
            {"pub_date": "2026-08-01", "sentiment_label": "positive", "sentiment_signed_score": 0.4},
            {"pub_date": "2026-08-01", "sentiment_label": "negative"},
        ]
        result = _sentiment_features_as_of(articles, datetime.date(2026, 8, 2))
        self.assertAlmostEqual(result["avg_sentiment_7d"], (0.4 + -1) / 2)
```

- [ ] **Step 2: Tests laufen lassen, rot bestätigen**

```bash
python -m pytest tests/test_market_predictor.py -v -k SentimentFeaturesAsOf
```
(Falls die Testklasse anders heisst als im Beispielnamen: die drei neuen Test-Methodennamen direkt mit `-k` filtern, z.B. `-k "test_uses_signed_score_when_present_instead_of_label or test_falls_back_to_label_score_for_legacy_articles_without_signed_score or test_mixes_signed_score_and_legacy_label_fallback_in_same_window"`.)
Expected: FAIL - `sentiment_signed_score` wird von der aktuellen Implementierung ignoriert, `avg_sentiment_7d` kommt weiterhin nur aus der Label-Zuordnung (Test 1 erwartet -0.5, bekommt 0 fuer zwei "neutral"-Artikel).

- [ ] **Step 3: `src/market_predictor.py` ändern**

Direkt vor `_sentiment_features_as_of()` (aktuell Zeile 254) einfuegen:

```python
def _article_signed_score(article: dict) -> float:
    """Bevorzugt den kontinuierlichen signed_score (p(positive) -
    p(negative), siehe news_sentiment.py::classify_sentiment()) - faellt
    auf die grobe Label-Zuordnung SENTIMENT_LABEL_SCORE zurueck fuer
    Artikel aus player_news_log, die VOR diesem Fix geschrieben wurden und
    deshalb noch kein 'sentiment_signed_score'-Feld haben (Firestore ist
    schemalos, keine Migration bestehender Dokumente geplant)."""
    signed_score = article.get("sentiment_signed_score")
    if signed_score is not None:
        return signed_score
    return SENTIMENT_LABEL_SCORE[article["sentiment_label"]]
```

In `_sentiment_features_as_of()` die Zeile

```python
    avg_sentiment = sum(SENTIMENT_LABEL_SCORE[a["sentiment_label"]] for a in relevant) / len(relevant)
```

ersetzen durch:

```python
    avg_sentiment = sum(_article_signed_score(a) for a in relevant) / len(relevant)
```

Docstring von `_sentiment_features_as_of()` um einen Satz ergaenzen, der auf `_article_signed_score()` verweist (Formulierung dem bestehenden Stil anpassen, kein Pflichtwortlaut).

- [ ] **Step 4: Tests laufen lassen, grün bestätigen**

```bash
python -m pytest tests/test_market_predictor.py -v
```
Expected: PASS fuer die GESAMTE Datei, nicht nur die neuen Tests - insbesondere `test_unknown_sentiment_label_raises_key_error` und alle bestehenden `_sentiment_features_as_of`/`_fetch_player_training_frame`-Tests (die ausschliesslich `sentiment_label` ohne `sentiment_signed_score` verwenden) muessen weiterhin unveraendert gruen bleiben - sie testen jetzt implizit den Fallback-Pfad.

- [ ] **Step 5: Mutation-Check**

Setze `_article_signed_score()` temporaer fest auf `return SENTIMENT_LABEL_SCORE[article["sentiment_label"]]` (alter Pfad, signed_score ignorieren), laufe die drei neuen Tests aus Step 1 erneut - `test_uses_signed_score_when_present_instead_of_label` MUSS rot werden (erwartet -0.5, bekommt 0). Danach den Fix wiederherstellen und die volle Datei erneut gruen bestaetigen.

- [ ] **Step 6: Vollen Backend-Testlauf**

```bash
python -m pytest tests/ -v
```
Expected: PASS fuer die gesamte Suite (bestaetigt, dass kein anderes Modul von der geaenderten internen Berechnung betroffen ist).

- [ ] **Step 7: Commit**

```bash
git add src/market_predictor.py tests/test_market_predictor.py
git commit -m "market_predictor: avg_sentiment_7d nutzt kontinuierlichen signed_score statt grober Label-Zuordnung, mit Legacy-Fallback"
```

---

## Nach Abschluss (Haupt-Thread, kein Subagent)

- `HANDOFF.md` aktualisieren: die beiden Punkte unter "Technische Schulden" (Negations-Bug, "speichert nur Argmax-Konfidenz") entfernen — beide durch diesen Plan behoben. Der `6b08e2cf`-Punkt unter "Offen aus feedback/current" bleibt UNVERÄNDERT stehen (Cold-Start-Grund und strukturelle Blindstelle bei "Spieler bleibt"-Meldungen ohne Reizwort sind von diesem Fix nicht betroffen) — NICHT auf `status:"done"` setzen.
- Kein Live-Smoke-Test gegen das echte `germansentiment`-Modell nötig für diesen Fix (Tests sind vollständig gegen Mocks TDD-verifiziert, kein Netz-/Modell-Verhalten geändert) — anders als bei den Live-RSS-/Firestore-Funden vom 2026-08-02/04, hier ist die Modell-Schnittstelle (`predict_sentiment()`-Aufruf-Signatur) unverändert, nur die Nachverarbeitung ihrer Rückgabe.
