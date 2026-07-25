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


def get_squad(token: str, league_id: str) -> list[dict]:
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/squad", headers=_headers(token), timeout=TIMEOUT
    )
    _raise_for_status(response)
    return response.json().get("it", [])


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
    "idp"}). timeframe ist 92 (~3 Monate) oder 365 (1 Jahr) Tage."""
    response = requests.get(
        f"{BASE_URL}/v4/leagues/{league_id}/players/{player_id}/marketValue/{timeframe}",
        headers=_headers(token),
        timeout=TIMEOUT,
    )
    _raise_for_status(response)
    return response.json()


def position_label(pos: int) -> str:
    return POSITION_LABELS.get(pos, f"Position {pos}")


def status_label(status_code: int) -> str | None:
    """Nur der Fall 0 (fit/unauffaellig) ist aus den Beispiel-Responses
    zweifelsfrei bestaetigt. Alles andere wird als rohe Nummer durchgereicht,
    statt einen (moeglicherweise falschen) Klartext-Status zu erfinden."""
    if status_code == 0:
        return None
    return f"Status-Code {status_code} (Bedeutung in v4-API nicht zweifelsfrei bestaetigt)"
