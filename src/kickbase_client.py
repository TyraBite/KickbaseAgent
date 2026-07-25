"""Duenner Wrapper um das kickbase_api-Paket.

Reduziert auf die Daten, die fuer den taeglichen Report gebraucht werden.
Macht bewusst wenige Requests pro Lauf (sparsame Nutzung der inoffiziellen API):
login, league_users, league_me, league_user_players (eigener Kader),
market, league_stats.
"""

import os

from kickbase_api.kickbase import Kickbase
from kickbase_api.models.league_data import LeagueData
from kickbase_api.models.market_player import MarketPlayer
from kickbase_api.models.player import Player


def _position_name(position) -> str:
    return getattr(position, "name", "UNKNOWN")


def _status_name(status) -> str:
    return getattr(status, "name", "UNKNOWN")


def _player_to_dict(player: Player) -> dict:
    return {
        "player_id": player.id,
        "first_name": player.first_name,
        "last_name": player.last_name,
        "position": _position_name(player.position),
        "status": _status_name(player.status),
        "market_value": player.market_value,
        "market_value_trend": player.market_value_trend,
        "average_points": player.average_points,
        "total_points": getattr(player, "totalPoints", None),
        "team_id": player.team_id,
    }


def _market_player_to_dict(mp: MarketPlayer) -> dict:
    offering_user_id = mp.user_id or None
    offering_username = mp.username or None
    return {
        "player_id": mp.id,
        "first_name": mp.first_name,
        "last_name": mp.last_name,
        "position": _position_name(mp.position),
        "status": _status_name(mp.status),
        "market_value": mp.market_value,
        "price": mp.price,
        "expiry": mp.expiry,
        "average_points": mp.average_points,
        "total_points": getattr(mp, "totalPoints", None),
        "offering_user_id": offering_user_id,
        "offering_username": offering_username,
        # kein user_id/username auf dem Angebot => Kickbase-Systemangebot,
        # kein anderer Manager bietet den Spieler an.
        "is_system_offer": 1 if not offering_user_id else 0,
    }


class KickbaseData:
    """Ergebnis eines kompletten Fetch-Laufs, bereit fuer die DB."""

    def __init__(self):
        self.league_users: list[dict] = []
        self.own_squad: list[dict] = []
        self.market_listings: list[dict] = []
        self.matchday_stats: list[dict] = []
        self.own_status: dict = {}


def _select_league(leagues: list[LeagueData]) -> LeagueData:
    league_id_override = os.environ.get("KICKBASE_LEAGUE_ID")
    if league_id_override:
        for league in leagues:
            if league.id == league_id_override:
                return league
        raise RuntimeError(
            f"KICKBASE_LEAGUE_ID={league_id_override} nicht unter den Ligen des Accounts gefunden"
        )
    if len(leagues) > 1:
        print(
            f"Warnung: Account ist in {len(leagues)} Ligen, nehme die erste "
            f"({leagues[0].name}). Setze KICKBASE_LEAGUE_ID um eine andere zu waehlen."
        )
    return leagues[0]


def fetch_all(email: str, password: str) -> KickbaseData:
    kb = Kickbase()
    user, leagues = kb.login(email, password)
    if not leagues:
        raise RuntimeError("Account ist in keiner Liga Mitglied")
    league = _select_league(leagues)

    data = KickbaseData()

    league_users = kb.league_users(league)
    data.league_users = [{"user_id": u.id, "name": u.name} for u in league_users]

    own_players = kb.league_user_players(league, user)
    data.own_squad = [_player_to_dict(p) for p in own_players]

    market = kb.market(league)
    data.market_listings = [_market_player_to_dict(mp) for mp in market.players]

    # Hinweis: Kontostaende anderer Manager sind ueber die API nicht einsehbar
    # (nur der eigene Kontostand via league_me). league_stats liefert dafuer
    # Teamwert/Punkte/Platzierung aller Manager je Spieltag - das reicht fuer
    # die Liga-Konkurrenzeinschaetzung.
    league_stats = kb.league_stats(league)
    for day, day_users in league_stats.match_days.items():
        for day_stats in day_users:
            data.matchday_stats.append(
                {
                    "day": day,
                    "user_id": day_stats.user_id,
                    "day_points": day_stats.day_points,
                    "day_placement": day_stats.day_placement,
                    "team_value": day_stats.team_value,
                    "points": day_stats.points,
                    "placement": day_stats.placement,
                }
            )

    me = kb.league_me(league)
    data.own_status = {
        "budget": me.budget,
        "team_value": me.team_value,
        "placement": me.placement,
        "points": me.points,
    }

    return data
