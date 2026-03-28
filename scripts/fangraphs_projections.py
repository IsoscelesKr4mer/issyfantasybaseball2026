#!/usr/bin/env python3
"""
fangraphs_projections.py -- FanGraphs projection fetcher and weekly scaler.

Fetches Steamer rest-of-season (steamerr) projections from FanGraphs and
scales them to per-week projections based on the MLB schedule for that week.

steamerr is used instead of steamer because it updates throughout the season
with actual performance data -- a player having a career year or nursing a
nagging injury will see their projections drift accordingly, rather than being
permanently anchored to pre-season expectations.

Yahoo's projected_week endpoint returns current-week actuals during the week,
not forward projections. This module replaces it as the Monte Carlo data source.

Usage:
    python3 scripts/fangraphs_projections.py [week_number]
    python3 scripts/fangraphs_projections.py refresh    # force-refresh cache
    python3 scripts/fangraphs_projections.py 3          # test week 3
"""

import json
import os
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DATA_DIR    = Path(__file__).parent.parent / 'data'
WEEKS_CACHE = DATA_DIR / 'yahoo_game_weeks.json'

# Projection type: 'steamerr' (rest-of-season, updates with actuals) is the
# default. 'steamer' is the full-season pre-season projection. steamerr is
# preferred because it responds to career years, injuries, and role changes.
DEFAULT_PROJ_TYPE = 'steamerr'

CACHE_MAX_HOURS      = 24   # FanGraphs projections: refresh daily
SCHEDULE_CACHE_HOURS = 48   # MLB schedule: refresh every 2 days
WEEKS_CACHE_HOURS    = 168  # Yahoo week dates: refresh weekly (they never change)

FG_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept':     'application/json',
    'Referer':    'https://www.fangraphs.com/projections.aspx',
}

# Aliases: Yahoo team abbrev -> standard MLB abbrev used by FanGraphs / MLB Stats API
YAHOO_TO_STD = {
    'AZ':  'ARI',
    'WAS': 'WSH',
    'CHW': 'CWS',
}

# MLB Stats API team ID -> standard abbreviation (all 30 teams, IDs are stable)
MLB_ID_TO_ABBR = {
    108: 'LAA', 109: 'ARI', 110: 'BAL', 111: 'BOS', 112: 'CHC',
    113: 'CIN', 114: 'CLE', 115: 'COL', 116: 'DET', 117: 'HOU',
    118: 'KCR', 119: 'LAD', 120: 'WSH', 121: 'NYM', 133: 'OAK',
    134: 'PIT', 135: 'SD',  136: 'SEA', 137: 'SF',  138: 'STL',
    139: 'TB',  140: 'TEX', 141: 'TOR', 142: 'MIN', 143: 'PHI',
    144: 'ATL', 145: 'CWS', 146: 'MIA', 147: 'NYY', 158: 'MIL',
}

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _normalize(name: str) -> str:
    """Lowercase, strip accents/combining chars, collapse whitespace."""
    nfkd = unicodedata.normalize('NFKD', name)
    ascii_str = ''.join(c for c in nfkd if not unicodedata.combining(c))
    return ' '.join(ascii_str.lower().split())


def _fresh(path: Path, max_hours: float) -> bool:
    if not path.exists():
        return False
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < max_hours


def _get_url(url: str, headers: dict = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()


# ---------------------------------------------------------------------------
# Yahoo week dates
# ---------------------------------------------------------------------------

def fetch_yahoo_week_dates(api, force: bool = False) -> dict:
    """Return {week_int: (start_date, end_date)} from Yahoo game_weeks endpoint.

    Caches to data/yahoo_game_weeks.json.
    """
    DATA_DIR.mkdir(exist_ok=True)
    if not force and _fresh(WEEKS_CACHE, WEEKS_CACHE_HOURS):
        return {int(k): tuple(v) for k, v in json.loads(WEEKS_CACHE.read_text()).items()}

    print('[weeks] Fetching Yahoo game week dates...')
    raw = api._get('game/mlb/game_weeks')
    game_weeks_block = raw['fantasy_content']['game'][1]['game_weeks']

    weeks = {}
    for i in range(int(game_weeks_block.get('@count', len(game_weeks_block)))):
        entry = game_weeks_block.get(str(i), {}).get('game_week', {})
        if entry:
            w = int(entry['week'])
            weeks[w] = (entry['start'], entry['end'])

    WEEKS_CACHE.write_text(json.dumps(weeks))
    print(f'[weeks] Cached {len(weeks)} weeks')
    return weeks


# ---------------------------------------------------------------------------
# FanGraphs Steamer fetch
# ---------------------------------------------------------------------------

def fetch_steamer(force: bool = False, proj_type: str = DEFAULT_PROJ_TYPE) -> tuple:
    """Return (bat_rows, pit_rows) for the given projection type.

    proj_type options:
      'steamerr' -- Steamer rest-of-season (default). Updates with actual
                    performance throughout the season. Best for in-season use.
      'steamer'  -- Full-season Steamer. Pure pre-season expectations.

    Results are cached per projection type to avoid redundant fetches.
    """
    DATA_DIR.mkdir(exist_ok=True)
    bat_cache = DATA_DIR / f'{proj_type}_bat.json'
    pit_cache = DATA_DIR / f'{proj_type}_pit.json'

    if not force and _fresh(bat_cache, CACHE_MAX_HOURS) and _fresh(pit_cache, CACHE_MAX_HOURS):
        bat = json.loads(bat_cache.read_text())
        pit = json.loads(pit_cache.read_text())
        print(f'[fg] Using cached {proj_type} ({len(bat)} batters, {len(pit)} pitchers)')
        return bat, pit

    print(f'[fg] Fetching {proj_type} projections from FanGraphs...')
    bat_url = (f'https://www.fangraphs.com/api/projections'
               f'?type={proj_type}&stats=bat&pos=all&team=0&players=0&lg=all')
    pit_url = (f'https://www.fangraphs.com/api/projections'
               f'?type={proj_type}&stats=pit&pos=all&team=0&players=0&lg=all')

    bat = json.loads(_get_url(bat_url, FG_HEADERS))
    pit = json.loads(_get_url(pit_url, FG_HEADERS))

    bat_cache.write_text(json.dumps(bat))
    pit_cache.write_text(json.dumps(pit))
    print(f'[fg] Fetched and cached {len(bat)} batters, {len(pit)} pitchers ({proj_type})')
    return bat, pit


def build_lookups(bat: list, pit: list) -> tuple:
    """Return (bat_lup, pit_lup) as {normalized_name: row} dicts."""
    bat_lup = {}
    for row in bat:
        name = _normalize(row.get('PlayerName', ''))
        if name:
            bat_lup[name] = row

    pit_lup = {}
    for row in pit:
        name = _normalize(row.get('PlayerName', ''))
        if name:
            pit_lup[name] = row

    return bat_lup, pit_lup


# ---------------------------------------------------------------------------
# MLB schedule -- game counts per team per week
# ---------------------------------------------------------------------------

def fetch_team_game_counts(week: int, week_dates: dict, force: bool = False) -> dict:
    """Return {team_abbrev: game_count} for the given fantasy week.

    Pulls from the MLB Stats API schedule endpoint and caches per-week.
    """
    cache_path = DATA_DIR / f'schedule_week{week:02d}.json'
    DATA_DIR.mkdir(exist_ok=True)

    if not force and _fresh(cache_path, SCHEDULE_CACHE_HOURS):
        data = json.loads(cache_path.read_text())
        print(f'[sched] Using cached schedule for week {week}')
        return data

    if week not in week_dates:
        print(f'[sched] Week {week} not found in week_dates, using default 5 games')
        return {}

    start, end = week_dates[week]
    # No fields filter -- the schedule endpoint returns team id/name/link by default
    url = (f'https://statsapi.mlb.com/api/v1/schedule'
           f'?sportId=1&startDate={start}&endDate={end}&gameType=R')

    print(f'[sched] Fetching MLB schedule for week {week} ({start} to {end})...')
    try:
        raw = json.loads(_get_url(url))
    except Exception as e:
        print(f'[sched] Schedule fetch failed: {e}. Using empty counts.')
        return {}

    counts = {}
    for date_block in raw.get('dates', []):
        for game in date_block.get('games', []):
            # Skip postponed/cancelled games
            state = game.get('status', {}).get('detailedState', '')
            if state in ('Postponed', 'Cancelled', 'Suspended'):
                continue
            for side in ('home', 'away'):
                team_id = (game.get('teams', {})
                               .get(side, {})
                               .get('team', {})
                               .get('id'))
                abbr = MLB_ID_TO_ABBR.get(team_id, '')
                if abbr:
                    counts[abbr] = counts.get(abbr, 0) + 1

    cache_path.write_text(json.dumps(counts))
    print(f'[sched] Game counts week {week}: {counts}')
    return counts


# ---------------------------------------------------------------------------
# Scaling logic
# ---------------------------------------------------------------------------

def _scale_batter(row: dict, team_games: int) -> dict:
    """Scale full-season batter projection to one week."""
    proj_g = float(row.get('G') or 1)
    scale  = team_games / proj_g

    return {
        'R':   round(float(row.get('R')   or 0) * scale, 2),
        'HR':  round(float(row.get('HR')  or 0) * scale, 2),
        'RBI': round(float(row.get('RBI') or 0) * scale, 2),
        'SB':  round(float(row.get('SB')  or 0) * scale, 2),
        'OBP': round(float(row.get('OBP') or 0), 3),  # rate stat: no scaling
    }


def _scale_pitcher(row: dict, team_games: int) -> dict:
    """Scale full-season pitcher projection to one week.

    SPs: scale by expected starts (GS / 162 * team_games).
    RPs: scale by expected appearances (G / 162 * team_games).
    ERA/WHIP are rate stats -- use season projection directly.
    """
    SEASON_GAMES = 162.0

    proj_gs   = float(row.get('GS')   or 0)
    proj_g    = float(row.get('G')    or 1)
    proj_ip   = float(row.get('IP')   or 0)
    proj_so   = float(row.get('SO')   or 0)
    proj_sv   = float(row.get('SV')   or 0)
    proj_qs   = float(row.get('QS')   or 0)
    proj_era  = float(row.get('ERA')  or 0)
    proj_whip = float(row.get('WHIP') or 0)

    if proj_gs > 0:
        # Starter: expected starts this week
        starts_this_week = (proj_gs / SEASON_GAMES) * team_games
        ip_per_start     = proj_ip / proj_gs
        weekly_ip  = ip_per_start * starts_this_week
        weekly_k   = (proj_so / proj_gs) * starts_this_week
        weekly_qs  = (proj_qs / proj_gs) * starts_this_week
        weekly_sv  = 0.0
    else:
        # Reliever: expected appearances this week
        apps_this_week = (proj_g / SEASON_GAMES) * team_games
        ip_per_app     = proj_ip / proj_g if proj_g else 0
        weekly_ip  = ip_per_app * apps_this_week
        weekly_k   = (proj_so / proj_g) * apps_this_week if proj_g else 0
        weekly_qs  = 0.0
        weekly_sv  = (proj_sv / proj_g) * apps_this_week if proj_g else 0

    return {
        'K':    round(weekly_k,   2),
        'SV':   round(weekly_sv,  2),
        'QS':   round(weekly_qs,  2),
        'ERA':  round(proj_era,   4),   # rate stat
        'WHIP': round(proj_whip,  4),   # rate stat
        'IP':   round(weekly_ip,  2),
    }


# ---------------------------------------------------------------------------
# Main projection builder
# ---------------------------------------------------------------------------

def get_player_weekly_projections(
    roster: list,
    week: int,
    bat_lup: dict,
    pit_lup: dict,
    game_counts: dict,
    default_games: int = 5,
) -> dict:
    """Given a Yahoo roster (from get_team_roster()), return weekly projections.

    Returns {player_key: {cat: weekly_value}}.
    Empty dict for any player not matched in FanGraphs.
    Categories: R, HR, RBI, SB, OBP (batters); K, SV, QS, ERA, WHIP, IP (pitchers).
    """
    result = {}

    for player in roster:
        key       = player.get('player_key', '')
        name_raw  = player.get('name', '')
        pos       = player.get('pos', '')
        yahoo_tm  = player.get('mlb_team', '')
        team      = YAHOO_TO_STD.get(yahoo_tm, yahoo_tm)

        team_games = game_counts.get(team, default_games)
        is_pitcher = any(p in pos for p in ('SP', 'RP', 'P'))
        norm_name  = _normalize(name_raw)

        if is_pitcher:
            row = pit_lup.get(norm_name)
            if not row:
                result[key] = {}
            else:
                result[key] = _scale_pitcher(row, team_games)
        else:
            row = bat_lup.get(norm_name)
            if not row:
                result[key] = {}
            else:
                result[key] = _scale_batter(row, team_games)

    return result


# ---------------------------------------------------------------------------
# Public entry points (used by generate_week.py and monte_carlo.py)
# ---------------------------------------------------------------------------

def get_projections_for_roster(
    roster: list,
    week: int,
    api,
    force: bool = False,
    proj_type: str = DEFAULT_PROJ_TYPE,
) -> dict:
    """Return weekly projections for a single roster.

    Args:
        roster:    list of player dicts from api.get_team_roster()
        week:      fantasy week number
        api:       YahooFantasyAPI instance (used to fetch week dates)
        force:     if True, bypass all caches
        proj_type: 'steamerr' (default) or 'steamer'

    Returns:
        {player_key: {cat: weekly_value}}
    """
    bat, pit         = fetch_steamer(force=force, proj_type=proj_type)
    bat_lup, pit_lup = build_lookups(bat, pit)
    week_dates       = fetch_yahoo_week_dates(api, force=force)
    game_counts      = fetch_team_game_counts(week, week_dates, force=force)
    return get_player_weekly_projections(roster, week, bat_lup, pit_lup, game_counts)


def get_projections_for_all_matchups(
    matchups_data: list,
    week: int,
    api,
    force: bool = False,
    proj_type: str = DEFAULT_PROJ_TYPE,
) -> dict:
    """Return weekly projections for every active player across all matchups.

    This is the primary entry point for generate_week.py. It fetches projections
    once and returns a single {player_key: {cat: value}} dict covering all teams.

    Args:
        matchups_data: list of matchup dicts with '_raw_roster' on t0/t1
        week:          fantasy week number (the PREVIEW week, i.e. next week)
        api:           YahooFantasyAPI instance
        force:         bypass all caches
        proj_type:     'steamerr' (default) or 'steamer'

    Returns:
        {player_key: {cat: weekly_value}} -- empty dict for unmatched players
    """
    print(f'[fg] Building {proj_type} projections for week {week}...')
    bat, pit         = fetch_steamer(force=force, proj_type=proj_type)
    bat_lup, pit_lup = build_lookups(bat, pit)
    week_dates       = fetch_yahoo_week_dates(api, force=force)
    game_counts      = fetch_team_game_counts(week, week_dates, force=force)

    projected_stats = {}
    for m in matchups_data:
        for tk in ('t0', 't1'):
            roster = m[tk].get('_raw_roster', [])
            active = [p for p in roster
                      if p.get('starting') not in ('BN', 'IL', 'IL+', 'NA')]
            proj = get_player_weekly_projections(
                active, week, bat_lup, pit_lup, game_counts
            )
            projected_stats.update(proj)

    matched = sum(1 for v in projected_stats.values() if v)
    total   = len(projected_stats)
    print(f'[fg] Projections: {matched}/{total} players matched ({100*matched//max(total,1)}%)')
    return projected_stats


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).parent))
    from yahoo_api import YahooFantasyAPI

    force     = 'refresh' in sys.argv
    week      = next((int(a) for a in sys.argv[1:] if a.isdigit()), None)
    proj_type = next((a for a in sys.argv[1:] if a in ('steamer', 'steamerr')), DEFAULT_PROJ_TYPE)

    api = YahooFantasyAPI()
    if week is None:
        week = api.get_league_week()

    print(f'\nFanGraphs {proj_type} weekly projection test -- week {week}')
    print('=' * 60)

    bat, pit         = fetch_steamer(force=force, proj_type=proj_type)
    bat_lup, pit_lup = build_lookups(bat, pit)
    week_dates       = fetch_yahoo_week_dates(api, force=force)
    game_counts      = fetch_team_game_counts(week, week_dates, force=force)

    print(f'\nWeek {week} dates: {week_dates.get(week)}')
    print(f'Game counts this week: {game_counts}\n')

    # Test all 10 teams
    total_players = 0
    total_matched = 0

    for team_num in range(1, 11):
        team_key = f'mlb.l.61583.t.{team_num}'
        roster   = api.get_team_roster(team_key, week)
        active   = [p for p in roster if p.get('starting') not in ('BN', 'IL', 'IL+', 'NA')]

        proj = get_player_weekly_projections(active, week, bat_lup, pit_lup, game_counts)
        matched = sum(1 for v in proj.values() if v)
        total_players += len(active)
        total_matched += matched
        print(f'  Team {team_num:2d}: {matched:2d}/{len(active):2d} active players matched')

    print(f'\nOverall: {total_matched}/{total_players} active players matched '
          f'({100*total_matched//total_players}%)')

    # Show a sample -- team 1 batters
    print('\n--- Sample: Team 1 batters ---')
    roster = api.get_team_roster('mlb.l.61583.t.1', week)
    active = [p for p in roster if p.get('starting') not in ('BN', 'IL', 'IL+', 'NA')]
    proj   = get_player_weekly_projections(active, week, bat_lup, pit_lup, game_counts)

    for p in active:
        k     = p['player_key']
        stats = proj.get(k, {})
        pos   = p.get('pos', '')
        is_p  = any(x in pos for x in ('SP', 'RP', 'P'))
        if not is_p and stats:
            print(f"  {p['name']:25s} | R={stats.get('R','?'):5} HR={stats.get('HR','?'):5} "
                  f"RBI={stats.get('RBI','?'):5} SB={stats.get('SB','?'):5} OBP={stats.get('OBP','?')}")
        elif not is_p:
            print(f"  {p['name']:25s} | NOT MATCHED")

    print('\n--- Sample: Team 1 pitchers ---')
    for p in active:
        k     = p['player_key']
        stats = proj.get(k, {})
        pos   = p.get('pos', '')
        is_p  = any(x in pos for x in ('SP', 'RP', 'P'))
        if is_p and stats:
            print(f"  {p['name']:25s} | IP={stats.get('IP','?'):5} K={stats.get('K','?'):5} "
                  f"ERA={stats.get('ERA','?'):6} WHIP={stats.get('WHIP','?'):6} "
                  f"QS={stats.get('QS','?'):5} SV={stats.get('SV','?')}")
        elif is_p:
            print(f"  {p['name']:25s} | NOT MATCHED")
