"""Duenner Client fuer die echte Kickbase v4 API (direkt per requests).

Das Paket `kickbase_api` (PyPI) spricht noch die alte, nicht mehr existierende
API ohne /v4-Prefix und mit anderen Feldnamen (z.B. Login-Body
{"email","password"} statt {"em","pass"}) - Login schlaegt damit fehl
(404/blanke KickbaseException). Deshalb hier ein direkter, minimaler Client
gegen die aktuelle v4-API, basierend auf github.com/kevinskyba/kickbase-api-doc
(Postman-Collection mit echten Beispiel-Responses).

WICHTIG - unbestaetigter Teil: Die Kickbase-API nutzt durchgehend sehr kurze,
kryptische Feldnamen (z.B. "st" fuer Status, "oui"/"u" fuer Owner-User-Id,
"prc" fuer Preis). Fuer Kader/Liga-Tabelle/Budget/Teams sind diese Felder
anhand echter Beispiel-Responses in der Doku (kevinskyba/kickbase-api-doc,
Postman-Collection) bestaetigt. Fuer den Transfermarkt (/market) enthielt
die Doku nur ein Beispiel mit LEERER Spielerliste (kein Spieler aktuell
gelistet) - die Top-Level-Felder der Response (it/nps/tv/mvud/dt/day) sind
dadurch bestaetigt, die Feldnamen einzelner Markt-Items (Preis/Anbieter/
Punkte) aber NICHT an einem echten populierten Marktangebot verifiziert.
Vor dem naechsten echten Lauf unbedingt pruefen (z.B. rohes JSON eines
get_market()-Items ausgeben lassen), ob die Zuordnung in _market_item_to_row
(src/fetcher.py) stimmt.

Ausserdem bestaetigt durch echte Beispiele: "st" (Status) zeigt in einem
Fall den Wert 128 bei einem sichtlich fitten/aktiven Spieler - eher eine
Bitmaske als der einfache Enum (1/2/4) des alten, verworfenen Clients.
status_label() gibt deshalb bewusst weiterhin nur die rohe Zahl aus, bis
das im echten Kickbase-Client gegengecheckt wurde.
"""

import os

import requests

BASE_URL = "https://api.kickbase.com"
TIMEOUT = 15

POSITION_LABELS = {
    1: "Torwart",
    2: "Abwehr",
    3: "Mittelfeld",
    4: "Sturm",
}


class KickbaseError(Exception):
    pass


class KickbaseAuthError(KickbaseError):
    pass


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _raise_for_status(response: requests.Response) -> None:
    if response.status_code == 401:
        raise KickbaseAuthError("Nicht autorisiert (401) - Token abgelaufen oder Login falsch?")
    if response.status_code >= 300:
        raise KickbaseError(f"HTTP {response.status_code} bei {response.url}: {response.text[:300]}")


def login(email: str, password: str) -> tuple[str, dict, list[dict]]:
    """Gibt (token, user_dict, leagues_list) zurueck. leagues_list-Eintraege
    haben u.a. 'id' und 'name'."""
    response = requests.post(
        f"{BASE_URL}/v4/user/login",
        json={"em": email, "pass": password},
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    if response.status_code == 401:
        raise KickbaseAuthError("Login fehlgeschlagen - E-Mail/Passwort falsch?")
    _raise_for_status(response)

    data = response.json()
    token = data["tkn"]
    user = data.get("u", {})
    leagues = data.get("srvl", [])
    return token, user, leagues


def select_league(leagues: list[dict]) -> dict:
    """Waehlt eine Liga aus login()s leagues-Liste - respektiert
    KICKBASE_LEAGUE_ID falls gesetzt (Accounts in mehreren Ligen), sonst die
    erste. Zentrale Stelle, damit ALLE Einstiegspunkte (fetcher.py,
    dashboard_export.py, market_predictor.py, player_valuation.py) dasselbe
    Verhalten haben - vorher pickte nur fetcher.py ueber diese Funktion
    korrekt, die anderen drei hatten je ihr eigenes, das Secret ignorierendes
    `leagues[0]` (live gefunden 2026-07-31: gesetztes KICKBASE_LEAGUE_ID-
    Secret hatte keine Wirkung, weil es in keinem der anderen Call-Sites
    gelesen wurde)."""
    league_id_override = os.environ.get("KICKBASE_LEAGUE_ID")
    if league_id_override:
        for league in leagues:
            if str(league.get("id")) == str(league_id_override):
                return league
        raise RuntimeError(
            f"KICKBASE_LEAGUE_ID={league_id_override} nicht unter den Ligen des Accounts gefunden"
        )
    if len(leagues) > 1:
        names = ", ".join(f"{l.get('name')} ({l.get('id')})" for l in leagues)
        print(
            f"Warnung: Account ist in {len(leagues)} Ligen ({names}), nehme die erste. "
            f"Setze KICKBASE_LEAGUE_ID um eine andere zu waehlen."
        )
    return leagues[0]


def get_squad(token: str, league_id: str) -> list[dict]:
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/squad", headers=_headers(token), timeout=TIMEOUT
    )
    _raise_for_status(response)
    return response.json().get("it", [])


def get_manager_squad(token: str, league_id: str, manager_id: str) -> dict:
    """Kader eines ANDEREN Liga-Managers (bestaetigt 27.07.2026). Gibt das
    komplette Response-Dict zurueck (nicht nur 'it'), weil 'nps'
    (Kadergroesse) fuer src/dashboard_export.py gebraucht wird.

    WICHTIG - abweichende Feldnamen ggue. get_squad()/get_team_squad():
    die Spieler-Items hier tragen die Spieler-Id/den Namen unter 'pi'/'pn',
    NICHT unter 'i'/'n' wie bei allen anderen Endpoints (bestaetigt
    27.07.2026 beim Aufbau eines ligaweiten Ownership-Abgleichs - ein
    Zugriff auf item['i'] liefert hier durchgehend None)."""
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/managers/{manager_id}/squad",
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    return response.json()


def get_market(token: str, league_id: str) -> dict:
    """Gibt das komplette Response-Dict zurueck (nicht nur 'it'!), da die
    Top-Level-Felder day/dt/mvud fuer die Saisonphase gebraucht werden
    (siehe Modul-Docstring)."""
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/market", headers=_headers(token), timeout=TIMEOUT
    )
    _raise_for_status(response)
    return response.json()


def get_ranking(token: str, league_id: str, day_number: int | None = None) -> dict:
    """Liga-Tabelle inkl. aller Manager (Name, Punkte, Teamwert, Platzierung).
    Enthaelt auch die eigenen Werte sowie Top-Level-Felder zur Saisonphase
    (day, sn). Mit day_number kann die Tabelle fuer einen einzelnen
    Spieltag abgefragt werden (fuer die Formkurve der Konkurrenz)."""
    params = {"dayNumber": day_number} if day_number is not None else None
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/ranking",
        headers=_headers(token),
        params=params,
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    return response.json()


def get_me(token: str, league_id: str) -> dict:
    """Eigener Kontostand etc. (Budget ist ueber die Liga-Tabelle nicht
    einsehbar, nur hier). Enthaelt auch 'cpi' (competitionId, z.B. "1" fuer
    Bundesliga), das fuer get_teams() gebraucht wird."""
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/me", headers=_headers(token), timeout=TIMEOUT
    )
    _raise_for_status(response)
    return response.json()


def get_teams(token: str, competition_id: str) -> dict[str, str]:
    """Gibt {team_id: team_name} zurueck, z.B. {"5": "Freiburg"}. Bestaetigt
    durch echtes Beispiel unter /v4/base/predictions/teams/{competitionId}
    (Feld 'tms', je Eintrag 'tid'/'tn')."""
    response = requests.get(
        f"{BASE_URL}/v4/base/predictions/teams/{competition_id}",
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    teams = response.json().get("tms", [])
    return {t["tid"]: t["tn"] for t in teams if t.get("tid") and t.get("tn")}


def get_market_value_history(
    token: str, league_id: str, player_id: str, timeframe: int = 92
) -> dict:
    """Echte Marktwert-Zeitreihe eines Spielers (bestaetigt durch echtes
    Beispiel: {"it": [{"dt": ..., "mv": ...}, ...], "lmv", "hmv", "trp",
    "idp"}). timeframe ist 92 (~3 Monate) oder 365 (1 Jahr) Tage. "dt" ist
    Tage seit Epoch 1970-01-01 (Integer, KEIN ISO-Timestamp) - bestaetigt am
    27.07.2026: dt=20660 entspricht 2026-07-26. Funktioniert auch fuer
    Spieler ausserhalb des eigenen Kaders/Markts (bestaetigt, siehe
    get_team_players/get_player_performance)."""
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/players/{player_id}/marketValue/{timeframe}",
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    return response.json()


def get_activities_feed(token: str, league_id: str, max_entries: int = 5000) -> list[dict]:
    """Liga-Activity-Feed (Trades, Login-Boni, Achievements) - Basis fuer die
    Budget-Schaetzung anderer Manager in src/manager_budgets.py.

    Teilweise UNBESTAETIGT gegen echte Daten (aus einem fremden Referenz-
    Client uebernommen, siehe github.com/LennardFe/Kickbase-Trading-Advisor):
    Response hat Feld "af" (Liste). Jeder Eintrag hat "t" (Activity-Typ) und
    "dt" (Datum). Typ 15 = Trade mit "data.trp" (Preis) - fehlt "byr" war es
    ein Systemverkauf, fehlt "slr" ein Systemkauf. Typ 22 = Login-Bonus mit
    "data.bn" (Betrag). Typ 26 = Achievement mit "data.t" (Achievement-Id).

    "data.byr"/"data.slr" sind KEINE User-Ids, sondern bereits die
    aufgeloesten Manager-Anzeigenamen als String - unabhaengig bestaetigt an
    echten Daten am 27.07.2026 (siehe src/manager_budgets.py, Modul-
    Docstring) und erneut am 03.08.2026 (siehe
    src/dashboard_export.py._build_recent_transfers()). Der Name matcht
    exakt das "name"-Feld aus der Liga-Ranking-Response.

    Alles andere hier ist weiterhin unbestaetigt: vor Vertrauen rohes JSON
    eines echten Laufs ausgeben und Typen/Felder gegenchecken."""
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/activitiesFeed",
        headers=_headers(token),
        params={"max": max_entries},
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    return response.json().get("af", [])


def get_achievement_reward(token: str, league_id: str, achievement_id: str) -> dict:
    """Rohes Achievement-Dict fuer den EIGENEN User ("ac" = Anzahl Treffer,
    "er" = Belohnung pro Treffer). Dient als Anker-Betrag: fuer Ids in
    manager_budgets._EXACT_ACHIEVEMENTS wird er anderen Managern exakt
    gutgeschrieben (Treffer/Nicht-Treffer), fuer alle anderen weiterhin nach
    Punkte-Verhaeltnis skaliert - da diese Route offenbar nur die eigenen
    Achievement-Zahlen liefert.
    Ebenfalls unbestaetigt, siehe get_activities_feed()."""
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/user/achievements/{achievement_id}",
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    return response.json()


def get_team_squad(token: str, competition_id: str, team_id: str) -> list[dict]:
    """Rohe Spieler-Liste eines Vereins, um an alle Liga-Spieler zu kommen -
    nicht nur die im eigenen Kader/Markt (siehe src/market_predictor.py,
    src/player_valuation.py). BESTAETIGT durch echtes Beispiel (27.07.2026,
    Team Bayern): {"tid","tn","it":[{"i","n","pos","mv","ap","tid",...}]}.
    Jedes Item hat Marktwert ("mv") und Punkteschnitt ("ap") direkt mit,
    aber KEINE Gesamtpunkte/Einsatzhistorie - dafuer get_player_performance()."""
    response = requests.get(
        f"{BASE_URL}/v4/competitions/{competition_id}/teams/{team_id}/teamprofile",
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    return response.json().get("it", [])


def get_team_players(token: str, competition_id: str, team_id: str) -> list[str]:
    """Nur die Spieler-Ids eines Vereins (String, z.B. "1685") - duenner
    Wrapper um get_team_squad() fuer Aufrufer, die nur die Ids brauchen."""
    return [item["i"] for item in get_team_squad(token, competition_id, team_id) if item.get("i")]


def get_player_performance(token: str, competition_id: str, player_id: str) -> dict:
    """Rohe Spieltag-Performance-Historie eines Spielers, ueber ALLE Saisons
    seit ca. 2015 gruppiert. BESTAETIGT durch echtes Beispiel (27.07.2026,
    Spieler 1685/Kimmich, Bayern - explizit ausserhalb des eigenen Kaders/
    Markts getestet, um zu pruefen ob die Kickbase-API das ueberhaupt
    herausgibt): {"it": [{"sid","ti","n","ph": [{"mi","day","md","p","mp",
    "t1","t2","t1g","t2g","pt","st","cur","mdst",...}]}]}. WICHTIG: enthaelt
    auch ZUKUENFTIGE, noch nicht gespielte Spieltage (dort fehlen "p"/"mp"/
    "t1g"/"t2g") - das wird fuer das days_to_next-Feature gebraucht. "mp" ist
    bei gespielten Spielen ein String wie "90'" (Minuten, muss geparst
    werden), "md" ist ein ISO-Timestamp (nicht Epoch-Tage wie bei
    get_market_value_history!)."""
    response = requests.get(
        f"{BASE_URL}/v4/competitions/{competition_id}/players/{player_id}/performance",
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    return response.json()


def position_label(pos: int) -> str:
    return POSITION_LABELS.get(pos, f"Position {pos}")


# Alle 3 direkt in der Kickbase-App gegengecheckt (User, 2026-07-29):
# 1 = "Verletzt" (rotes Kreuz, Tooltip "Injured"/"out for the time being"),
# 2 = "Angeschlagen" (Pillen-Symbol, Tooltip "Sick: Adductor problems -
# misses team training" - Kickbase nennt das intern "Sick", gemeint ist
# aber ein day-to-day-Wehwehchen ohne echten Ausfall, nicht Krankheit),
# 4 = "Im Aufbau" (Hantel-Symbol, Reha nach Verletzung).
STATUS_LABELS = {1: "Verletzt", 2: "Angeschlagen", 4: "Im Aufbau"}


def status_label(status_code: int) -> str | None:
    """0 (fit/unauffaellig) und die in STATUS_LABELS bestaetigten Codes haben
    echten Klartext, alles andere wird als rohe Nummer durchgereicht statt
    einen (moeglicherweise falschen) Status zu erfinden."""
    if status_code == 0:
        return None
    if status_code in STATUS_LABELS:
        return STATUS_LABELS[status_code]
    return f"Status-Code {status_code} (Bedeutung in v4-API nicht zweifelsfrei bestaetigt)"
