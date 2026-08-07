"""Schritt 1: Kickbase-Daten abrufen und als Tages-Snapshot in SQLite ablegen."""

import datetime
import os
import sys

from dotenv import load_dotenv

from src import db, manager_budgets
from src.kickbase_client import (
    KickbaseError,
    get_achievement_reward,
    get_activities_feed,
    get_market,
    get_market_value_history,
    get_me,
    get_ranking,
    get_squad,
    get_teams,
    login,
    position_label,
    select_league,
    status_label,
)

# Wie viele vergangene Spieltage fuer die Formkurve der Liga-Konkurrenz
# zusaetzlich abgefragt werden (siehe _fetch_recent_matchday_points).
FORM_CURVE_MATCHDAYS = 5

# Grenzwert fuer die Plausibilitaetspruefung der Spieltagspunkte - grosszuegig
# gewaehlt, soll nur eindeutig kaputte Werte abfangen (z.B. Verwechslung mit
# Spieler-IDs), keine echten Grenzfaelle.
IMPLAUSIBLE_MATCHDAY_POINTS = 5000

# Wie viele Activity-Feed-Eintraege maximal abgefragt werden (fuer die
# Budget-Schaetzung in manager_budgets.py). Reines Tuning, kein Liga-
# spezifischer Wert, daher keine Env-Variable.
ACTIVITIES_FEED_MAX = 5000

# Startbudget einer neuen Kickbase-Liga (Plattform-Standard). Ueberschreibbar
# per KICKBASE_LEAGUE_START_BUDGET, falls die eigene Liga einen anderen Wert
# eingestellt hat.
DEFAULT_START_BUDGET = 50_000_000

# Grenzwert fuer die Plausibilitaetspruefung geschaetzter Budgets - ein
# Vielfaches des Startbudgets, soll nur eindeutig kaputte Werte (z.B.
# Vorzeichenfehler bei Kauf/Verkauf) abfangen, keine echten Grenzfaelle.
IMPLAUSIBLE_BUDGET_MULTIPLE = 20


def _squad_item_to_row(item: dict, team_names_by_id: dict) -> dict:
    status_code = item.get("st") or 0
    team_id = item.get("tid")
    return {
        "player_id": item.get("i"),
        "name": item.get("n"),
        "position": position_label(item.get("pos")),
        "status_code": status_code,
        "status_label": status_label(status_code),
        "market_value": item.get("mv"),
        "market_value_trend": item.get("mvt"),
        "market_value_change_7d": None,
        "market_value_low_92d": None,
        "market_value_high_92d": None,
        "market_value_in_drop_phase": None,
        "average_points": item.get("ap"),
        "total_points": item.get("p"),
        "team_id": team_id,
        "team_name": team_names_by_id.get(team_id),
        # Roher Kickbase-Rang ("prob"), UNBESTAETIGT: Musterbeobachtung an
        # echten Teamprofil-Beispielen (27.07.2026) spricht fuer einen
        # Startelf-Rang (1 = wahrscheinlichster Stammspieler seiner Position,
        # hoehere Werte unwahrscheinlicher) - keine offizielle Bestaetigung.
        "starting_rank": item.get("prob"),
        # "mvgl" (Market-Value-Gain/Loss seit Kauf) - live verifiziert
        # 2026-07-31 gegen 6 unabhaengig aus bid_premium_history
        # rekonstruierte Preise, exakte Uebereinstimmung. mv - mvgl ist der
        # tatsaechlich gezahlte Kaufpreis, deckt ALLE Kaderspieler ab (nicht
        # nur Systemangebot-Kaeufe wie bid_premium_history).
        "purchase_price": (item["mv"] - item["mvgl"]) if item.get("mv") is not None and item.get("mvgl") is not None else None,
    }


def _parse_kickbase_dt(raw: str | None) -> datetime.datetime | None:
    if not raw:
        return None
    try:
        return datetime.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=datetime.timezone.utc
        )
    except ValueError:
        return None


def _compute_expiry(exs_seconds, now: datetime.datetime) -> tuple[str | None, bool]:
    """Gibt (expires_at, is_estimate) zurueck.

    Live bestaetigt 27.07.2026 an echten Beispielen (u.a. Stage, exs=175
    Sekunden bei einem Angebot, das der User in der App bei "laeuft in 4 Min.
    ab" sah): Kickbase-Systemangebote liefern ein Feld 'exs' (Sekunden bis
    Ablauf) - IMMER, auch ohne Gebot (Beispiel Mittelstädt, ofc=0,
    exs=70986). Die fruehere Annahme "Systemangebote haben kein Zeitlimit"
    war falsch - sie beruhte auf dem Angebots-ALTER ('dt'), das tatsaechlich
    nichts mit der Restzeit zu tun hat. 'exs' ist die tatsaechliche,
    sekundengenaue Restzeit, keine Schaetzung.

    Mitspieler-Angebote liefern 'exs' dagegen NIE (auch nicht mit Gebot
    drauf, live geprueft an Harder mit ofc=1). Frueher wurde hier ersatzweise
    "gelistet + Liga-Feld 'mpst' Tage" geschaetzt - live widerlegt 2026-07-30:
    ein Mitspieler-Angebot war 5 Tage nach dem Listing ueber die echte
    Kickbase-API noch abrufbar, obwohl die mpst=3-Schaetzung es laengst als
    abgelaufen auswies (das Feld bedeutet offenbar etwas anderes als
    Listing-Lebensdauer). Ohne 'exs' gibt es keine verlaessliche Restzeit -
    lieber ehrlich unbekannt als eine falsche "abgelaufen"-Anzeige."""
    if exs_seconds is not None:
        expires = now + datetime.timedelta(seconds=int(exs_seconds))
        return expires.strftime("%Y-%m-%dT%H:%M:%SZ"), False
    return None, False


def _market_item_to_row(
    item: dict,
    names_by_user_id: dict,
    team_names_by_id: dict,
    own_user_id: str | None = None,
    now: datetime.datetime | None = None,
) -> dict:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    status_code = item.get("st") or 0

    # Bestaetigt an echten Beispielen (25.07.2026): ist ein Spieler von einem
    # Mitspieler angeboten, steckt der Anbieter unter "u" als VERSCHACHTELTES
    # Objekt {"i": ..., "n": ...} (nicht als flache ID/String wie zunaechst
    # angenommen - das war der Grund fuer den "unhashable type: dict"-Absturz).
    # Ist der Spieler ein freier/System-Spieler, fehlt "u" komplett, dafuer
    # gibt es "uoid"/"uop" (fuehrendes Gebot: User-Id/Preis) und "ofs"
    # (Liste aller Gebote, dort "u"/"unm" als flache Felder).
    owner = item.get("u")
    if isinstance(owner, dict):
        offering_user_id = owner.get("i")
        offering_username = owner.get("n") or names_by_user_id.get(offering_user_id)
    elif isinstance(owner, str):
        # Fallback, falls die API das doch mal als flache ID liefert.
        offering_user_id = owner
        offering_username = names_by_user_id.get(owner)
    else:
        offering_user_id = None
        offering_username = None

    offers = item.get("ofs") or []
    leading_bid_user_id = item.get("uoid")
    leading_bid_price = item.get("uop")
    leading_bid_username = None
    for offer in offers:
        if offer.get("u") == leading_bid_user_id:
            leading_bid_username = offer.get("unm")
            break
    is_own_leading_bid = bool(own_user_id) and leading_bid_user_id == own_user_id

    market_value = item.get("mv")
    price = item.get("prc")
    price_delta_pct = None
    if market_value and price is not None:
        price_delta_pct = round((price - market_value) / market_value * 100, 1)
    team_id = item.get("tid")
    is_system_offer = not offering_user_id
    listed_at = item.get("dt")
    expires_at, expiry_is_estimate = _compute_expiry(item.get("exs"), now)
    return {
        "player_id": item.get("i") or item.get("pi"),
        "name": item.get("n") or item.get("pn"),
        "position": position_label(item.get("pos")),
        "status_code": status_code,
        "status_label": status_label(status_code),
        "market_value": market_value,
        "market_value_change_7d": None,
        "market_value_low_92d": None,
        "market_value_high_92d": None,
        "market_value_in_drop_phase": None,
        "price": price,
        "price_delta_pct": price_delta_pct,
        "average_points": item.get("ap"),
        "total_points": item.get("p"),
        "team_id": team_id,
        "team_name": team_names_by_id.get(team_id),
        "offering_user_id": offering_user_id,
        "offering_username": offering_username,
        "is_system_offer": 1 if is_system_offer else 0,
        "pending_offers_count": len(offers),
        "leading_bid_username": leading_bid_username,
        "leading_bid_price": leading_bid_price,
        "is_own_leading_bid": 1 if is_own_leading_bid else 0,
        "starting_rank": item.get("prob"),
        "listed_at": listed_at,
        "expires_at": expires_at,
        "expiry_is_estimate": 1 if expiry_is_estimate else 0,
    }


def _apply_market_value_history(token: str, league_id: str, row: dict) -> None:
    """Ergaenzt eine Kader-/Markt-Row um die echte Marktwert-Historie (echter
    API-Call, nur fuer Spieler ohne heutigen Cache-Treffer - siehe
    _apply_or_reuse_market_value_history/db.get_market_value_history_cache).
    Ein einzelner fehlgeschlagener Call darf den ganzen Lauf nicht abbrechen,
    daher try/except pro Spieler."""
    player_id = row.get("player_id")
    if not player_id:
        return
    try:
        history = get_market_value_history(token, league_id, player_id)
    except KickbaseError as exc:
        print(
            f"Warnung: Marktwert-Historie fuer Spieler {player_id} ({row.get('name')}) "
            f"fehlgeschlagen: {exc}",
            file=sys.stderr,
        )
        return

    entries = history.get("it") or []
    if len(entries) >= 8:
        row["market_value_change_7d"] = entries[-1].get("mv") - entries[-8].get("mv")
    row["market_value_low_92d"] = history.get("lmv")
    row["market_value_high_92d"] = history.get("hmv")
    row["market_value_in_drop_phase"] = 1 if history.get("idp") else 0


def _apply_or_reuse_market_value_history(
    token: str, league_id: str, row: dict, cache: dict[str, dict]
) -> None:
    """Nutzt einen bereits heute abgerufenen Cache-Treffer (siehe
    db.get_market_value_history_cache) statt erneut die Kickbase-API zu
    fragen - die echte Historie aendert sich ohnehin nur ~1x/Tag, ein
    2h-Cron braucht sie nicht 12x/Tag identisch neu abzurufen."""
    cached = cache.get(row.get("player_id"))
    if cached:
        row.update(cached)
    else:
        _apply_market_value_history(token, league_id, row)


def _fetch_activities_feed(token: str, league_id: str) -> list[dict] | None:
    """Holt den Liga-Activity-Feed fuer die Budget-Schaetzung. Schlaegt der
    Call fehl, wird die komplette Budget-Schaetzung fuer den Tag
    uebersprungen (Warnung, kein Abbruch des restlichen Laufs) - analog zum
    bestehenden get_teams()-Try/Except in run()."""
    try:
        activities = get_activities_feed(token, league_id, max_entries=ACTIVITIES_FEED_MAX)
    except KickbaseError as exc:
        print(f"Warnung: Activity-Feed nicht ladbar, Budget-Schaetzung wird uebersprungen: {exc}", file=sys.stderr)
        return None
    if len(activities) >= ACTIVITIES_FEED_MAX:
        print(
            f"Warnung: Activity-Feed evtl. abgeschnitten (>= {ACTIVITIES_FEED_MAX} Eintraege) - "
            "Budget-Schaetzung kann unvollstaendige Historie verwenden.",
            file=sys.stderr,
        )
    return activities


def _fetch_achievement_rewards(token: str, league_id: str, achievement_ids: set) -> list[dict]:
    """Fragt jede (deduplizierte) Achievement-Id einmal ab. Ein einzelner
    fehlgeschlagener Call darf die Budget-Schaetzung nicht komplett
    verhindern, daher try/except pro Id, analog _apply_market_value_history.
    Gibt pro Id ein Dict {id, ac, er} zurueck - die Granularitaet bleibt bis
    manager_budgets.estimate_all() erhalten, damit dort pro Achievement
    exakt statt nur pauschal skaliert werden kann (siehe
    manager_budgets._EXACT_ACHIEVEMENTS)."""
    rewards = []
    for achievement_id in achievement_ids:
        try:
            reward = get_achievement_reward(token, league_id, achievement_id)
        except KickbaseError as exc:
            print(
                f"Warnung: Achievement-Reward fuer Id {achievement_id} fehlgeschlagen: {exc}",
                file=sys.stderr,
            )
            continue
        rewards.append(
            {"id": achievement_id, "ac": reward.get("ac") or 0, "er": reward.get("er") or 0}
        )
    return rewards


def _fetch_recent_matchday_points(
    token: str, league_id: str, current_matchday: int | None, known_user_ids: set
) -> dict[str, list]:
    """Baut je Manager eine Punkte-Liste der letzten FORM_CURVE_MATCHDAYS
    Spieltage (echte Formkurve statt des fuer diesen Zweck ungeeigneten
    'lp'-Felds, das tatsaechlich Spieler-IDs der Aufstellung enthaelt, siehe
    Modul-Docstring in kickbase_client.py)."""
    points_by_user: dict[str, list] = {uid: [] for uid in known_user_ids}
    if not current_matchday or current_matchday <= 0:
        return points_by_user

    start_day = max(1, current_matchday - (FORM_CURVE_MATCHDAYS - 1))
    for day in range(start_day, current_matchday + 1):
        try:
            day_ranking = get_ranking(token, league_id, day_number=day)
        except KickbaseError as exc:
            print(f"Warnung: Formkurve Spieltag {day} nicht ladbar: {exc}", file=sys.stderr)
            continue
        for u in day_ranking.get("us", []):
            uid = u.get("i")
            if uid in points_by_user:
                points_by_user[uid].append(u.get("mdp"))
    return points_by_user


def _match_own_ranking_user(
    ranking_users: list[dict], own_user_id: str | None, own_name: str | None
) -> dict | None:
    """Login liefert die eigene ID unter 'id', die Ranking-Response listet
    Manager unter 'i' - beide sollten denselben Wert tragen, muessen es aber
    nicht zwingend (unterschiedliche ID-Raeume moeglich). Fallback per Name,
    damit Teamwert/Platzierung nicht lautlos None bleiben."""
    for u in ranking_users:
        if u.get("i") == own_user_id:
            return u
    if own_name:
        for u in ranking_users:
            if u.get("n") == own_name:
                return u
    return None


def run() -> str:
    """Fuehrt einen kompletten Fetch-Lauf aus, gibt das Snapshot-Datum zurueck."""
    load_dotenv()

    email = os.environ.get("KICKBASE_EMAIL")
    password = os.environ.get("KICKBASE_PASSWORD")
    if not email or not password:
        raise RuntimeError(
            "KICKBASE_EMAIL/KICKBASE_PASSWORD fehlen (lokal: .env, GitHub Actions: Secrets)"
        )

    token, user, leagues = login(email, password)
    if not leagues:
        raise RuntimeError("Account ist in keiner Liga Mitglied")
    league = select_league(leagues)
    league_id = league["id"]

    me = get_me(token, league_id)
    budget = me.get("b")
    competition_id = me.get("cpi") or "1"

    team_names_by_id: dict[str, str] = {}
    try:
        team_names_by_id = get_teams(token, competition_id)
    except KickbaseError as exc:
        print(f"Warnung: Vereinsnamen konnten nicht geladen werden: {exc}", file=sys.stderr)

    ranking = get_ranking(token, league_id)
    ranking_users = ranking.get("us", [])
    names_by_user_id = {u.get("i"): u.get("n") for u in ranking_users if u.get("i")}
    current_matchday = ranking.get("day")
    season_name = ranking.get("sn")
    # "lfmd" (last finished matchday) == 0 heisst: noch kein Spieltag dieser
    # Saison abgeschlossen (Vorsaison). In dem Fall fehlen Teamwert/Punkte/
    # Platzierung fuer ALLE Manager in der Ranking-Response - kein Bug,
    # sondern erwartete Datenluecke (siehe _sanity_check).
    last_finished_matchday = ranking.get("lfmd")

    own_user_id = user.get("id")
    own_name = user.get("name")
    matched_ranking_user = _match_own_ranking_user(ranking_users, own_user_id, own_name)
    if matched_ranking_user is not None:
        # Ranking-'i' als kanonische ID uebernehmen, damit der DB-Join in
        # prompt_builder.py auch greift, falls Login-'id' und Ranking-'i'
        # unterschiedliche ID-Raeume sind.
        own_user_id = matched_ranking_user.get("i")
    else:
        print(
            f"Warnung: Eigener Ranking-Eintrag nicht gefunden (user_id={own_user_id!r}, "
            f"name={own_name!r}) - Teamwert/Platzierung bleiben leer",
            file=sys.stderr,
        )

    fetched_at = datetime.date.today().isoformat()

    squad_items = get_squad(token, league_id)
    own_squad_rows = [_squad_item_to_row(item, team_names_by_id) for item in squad_items]

    market_response = get_market(token, league_id)
    market_fetched_at = datetime.datetime.now(datetime.timezone.utc)
    market_items = market_response.get("it", [])
    market_rows = [
        _market_item_to_row(item, names_by_user_id, team_names_by_id, own_user_id, market_fetched_at)
        for item in market_items
    ]

    # /market lieferte im ersten echten Testlauf offenbar eine Spieler-
    # Referenzliste statt ausschliesslich echter Angebote - alle 15 eigenen
    # Kaderspieler tauchten dort identisch (Preis == Marktwert) nochmal auf.
    # Sicherheitsnetz: eigene Kaderspieler aus der Marktliste ausschliessen,
    # unabhaengig davon ob die genaue Endpoint-Semantik je geklaert wird.
    own_player_ids = {row["player_id"] for row in own_squad_rows}
    market_rows = [row for row in market_rows if row["player_id"] not in own_player_ids]

    # Cache-Lookup gegen die HEUTIGEN, noch nicht ueberschriebenen Zeilen
    # (replace_own_squad/replace_market_listings loeschen sie erst weiter
    # unten) - vermeidet identische Wiederholungs-Requests innerhalb
    # desselben Tages, siehe db.get_market_value_history_cache.
    history_cache_conn = db.connect()
    try:
        history_cache = db.get_market_value_history_cache(history_cache_conn, fetched_at)
    finally:
        history_cache_conn.close()

    for row in own_squad_rows + market_rows:
        _apply_or_reuse_market_value_history(token, league_id, row, history_cache)

    recent_matchday_points = _fetch_recent_matchday_points(
        token, league_id, current_matchday, set(names_by_user_id)
    )

    ranking_rows = [
        {
            "user_id": u.get("i"),
            "name": u.get("n"),
            "season_points": u.get("sp"),
            "matchday_points": u.get("mdp"),
            "team_value": u.get("tv"),
            "season_placement": u.get("spl"),
            "matchday_placement": u.get("mdpl"),
            "current_lineup_player_ids": ",".join(str(p) for p in (u.get("lp") or []) if p is not None),
            "recent_matchday_points": ",".join(
                str(p) for p in recent_matchday_points.get(u.get("i"), []) if p is not None
            ),
        }
        for u in ranking_users
    ]

    activities = _fetch_activities_feed(token, league_id)
    if activities is not None:
        achievement_rewards = _fetch_achievement_rewards(
            token, league_id, manager_budgets.unique_achievement_ids(activities)
        )
        start_budget = float(
            os.environ.get("KICKBASE_LEAGUE_START_BUDGET", DEFAULT_START_BUDGET)
        )
        league_start_date = os.environ.get("KICKBASE_LEAGUE_START_DATE") or None
        manager_budget_rows = manager_budgets.estimate_all(
            activities=activities,
            ranking_rows=ranking_rows,
            own_name=own_name,
            own_budget=budget,
            start_budget=start_budget,
            league_start_date=league_start_date,
            achievement_rewards=achievement_rewards,
        )
    else:
        manager_budget_rows = []

    next_deadline_at = market_response.get("dt")
    season_context = {
        "season_name": season_name,
        "current_matchday": current_matchday,
        "next_deadline_at": next_deadline_at,
        "days_until_next_deadline": _days_until(next_deadline_at),
        "market_value_updated_at": market_response.get("mvud"),
    }

    _sanity_check(
        own_squad_rows, ranking_rows, matched_ranking_user, last_finished_matchday, manager_budget_rows
    )

    conn = db.connect()
    try:
        db.upsert_league_users(
            conn, [{"user_id": uid, "name": name} for uid, name in names_by_user_id.items()]
        )
        db.replace_own_squad(conn, fetched_at, own_squad_rows)
        db.replace_market_listings(conn, fetched_at, market_rows)
        db.replace_league_ranking(conn, fetched_at, ranking_rows)
        db.upsert_own_budget(conn, fetched_at, own_user_id, budget)
        db.upsert_season_context(conn, fetched_at, season_context)
        db.replace_manager_budgets(conn, fetched_at, manager_budget_rows)
    finally:
        conn.close()

    print(
        f"Snapshot {fetched_at}: {len(own_squad_rows)} eigene Spieler, "
        f"{len(market_rows)} Marktangebote, {len(ranking_rows)} Liga-Manager, "
        f"{len(manager_budget_rows)} geschaetzte Budgets"
    )
    return fetched_at


def _days_until(iso_timestamp: str | None) -> int | None:
    if not iso_timestamp:
        return None
    try:
        target = datetime.datetime.fromisoformat(iso_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    return (target - now).days


def _sanity_check(
    own_squad_rows: list[dict],
    ranking_rows: list[dict],
    matched_ranking_user: dict | None,
    last_finished_matchday: int | None,
    manager_budget_rows: list[dict],
) -> None:
    """Nicht blockierende Plausibilitaetspruefung - soll verhindern, dass ein
    erneuter Feldnamen-Bug (wie die Spieler-IDs im 'lp'-Feld, die als
    Spieltagspunkte bis 13.479 im Prompt auftauchten) unbemerkt durchlaeuft."""
    # Vor dem ersten abgeschlossenen Spieltag (Vorsaison) fehlen tv/sp/mdp/mdpl
    # bei JEDEM Manager in der Ranking-Response - erwartete Datenluecke, kein
    # Matching-Bug. Warnung nur nach Saisonstart aussagekraeftig.
    if (
        last_finished_matchday
        and own_squad_rows
        and matched_ranking_user is not None
        and matched_ranking_user.get("tv") is None
    ):
        print(
            "Warnung: Teamwert ist None trotz vorhandenem Kader und bereits gespielten "
            "Spieltagen - Feldnamen in get_ranking()/_match_own_ranking_user pruefen",
            file=sys.stderr,
        )

    for row in ranking_rows:
        matchday_points = row.get("matchday_points")
        if isinstance(matchday_points, (int, float)) and matchday_points > IMPLAUSIBLE_MATCHDAY_POINTS:
            print(
                f"Warnung: unplausibel hohe Spieltagspunkte ({matchday_points}) fuer "
                f"{row.get('name')} - Feldnamen pruefen",
                file=sys.stderr,
            )
        season_points = row.get("season_points")
        if isinstance(season_points, (int, float)) and season_points < 0:
            print(
                f"Warnung: negative Saisonpunkte ({season_points}) fuer {row.get('name')}",
                file=sys.stderr,
            )

    implausible_budget_abs = DEFAULT_START_BUDGET * IMPLAUSIBLE_BUDGET_MULTIPLE
    for row in manager_budget_rows:
        estimated_budget = row.get("estimated_budget")
        if (
            isinstance(estimated_budget, (int, float))
            and abs(estimated_budget) > implausible_budget_abs
        ):
            print(
                f"Warnung: unplausibel hohes geschaetztes Budget ({estimated_budget}) fuer "
                f"{row.get('name')} - Trade-Parsing in manager_budgets.py pruefen",
                file=sys.stderr,
            )


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:  # noqa: BLE001 - Skript-Entrypoint, Fehler soll sichtbar sein
        print(f"Fetcher fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
