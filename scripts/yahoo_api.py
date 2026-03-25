#!/usr/bin/env python3
"""
yahoo_api.py — Yahoo Fantasy API client with automatic token refresh.

All other scripts import from this module. Never call the API directly.
"""

import os
import base64
import json
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
ENV_PATH = BASE_DIR / '.env'
TOKENS_PATH = BASE_DIR / 'tokens.json'
BASE_URL = 'https://fantasysports.yahooapis.com/fantasy/v2'

# ── Env loader ─────────────────────────────────────────────────────────────────
def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip()
    # Also pull from environment (for CI / scheduled tasks)
    for key in ['YAHOO_CLIENT_ID', 'YAHOO_CLIENT_SECRET', 'YAHOO_REFRESH_TOKEN',
                'YAHOO_LEAGUE_ID', 'GITHUB_TOKEN', 'GITHUB_REPO']:
        if key in os.environ:
            env[key] = os.environ[key]
    return env

def save_tokens(tokens: dict):
    TOKENS_PATH.write_text(json.dumps(tokens, indent=2))
    # Also update refresh token in .env if it changed
    if 'refresh_token' in tokens:
        content = ENV_PATH.read_text()
        lines = content.splitlines()
        new_lines = []
        for line in lines:
            if line.strip().startswith('YAHOO_REFRESH_TOKEN='):
                new_lines.append(f'YAHOO_REFRESH_TOKEN={tokens["refresh_token"]}')
            else:
                new_lines.append(line)
        ENV_PATH.write_text('\n'.join(new_lines) + '\n')

# ── Token refresh ──────────────────────────────────────────────────────────────
def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    """Exchange refresh token for a new access token. Returns new access token."""
    credentials = base64.b64encode(f'{client_id}:{client_secret}'.encode()).decode()
    data = urllib.parse.urlencode({
        'grant_type':    'refresh_token',
        'redirect_uri':  'https://localhost',
        'refresh_token': refresh_token,
    }).encode()

    req = urllib.request.Request(
        'https://api.login.yahoo.com/oauth2/get_token',
        data=data,
        headers={
            'Authorization': f'Basic {credentials}',
            'Content-Type':  'application/x-www-form-urlencoded',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read())
        save_tokens(tokens)
        return tokens['access_token']
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Token refresh failed ({e.code}): {e.read().decode()}')

# ── API client ─────────────────────────────────────────────────────────────────
class YahooFantasyAPI:
    def __init__(self):
        env = load_env()
        self.client_id     = env['YAHOO_CLIENT_ID']
        self.client_secret = env['YAHOO_CLIENT_SECRET']
        self.refresh_token = env['YAHOO_REFRESH_TOKEN']
        self.league_id     = env['YAHOO_LEAGUE_ID']
        self.league_key    = f'mlb.l.{self.league_id}'
        self._access_token = None

    def _get_token(self) -> str:
        if self._access_token:
            return self._access_token
        # Try cached tokens first
        if TOKENS_PATH.exists():
            try:
                tokens = json.loads(TOKENS_PATH.read_text())
                if tokens.get('access_token'):
                    self._access_token = tokens['access_token']
                    return self._access_token
            except Exception:
                pass
        # Refresh
        self._access_token = refresh_access_token(
            self.client_id, self.client_secret, self.refresh_token
        )
        return self._access_token

    def _get(self, endpoint: str, retried=False) -> dict:
        url = f'{BASE_URL}/{endpoint}'
        if '?' in url:
            url += '&format=json'
        else:
            url += '?format=json'

        req = urllib.request.Request(
            url,
            headers={'Authorization': f'Bearer {self._get_token()}'}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 401 and not retried:
                # Token expired — force a refresh and retry once
                self._access_token = refresh_access_token(
                    self.client_id, self.client_secret, self.refresh_token
                )
                return self._get(endpoint, retried=True)
            raise RuntimeError(f'API call failed ({e.code}) for {endpoint}: {e.read().decode()}')

    # ── Public methods ──────────────────────────────────────────────────────────

    def get_league_info(self) -> dict:
        """Basic league metadata."""
        data = self._get(f'league/{self.league_key}')
        return data['fantasy_content']['league'][0]

    def get_standings(self) -> list:
        """Returns list of teams with rank, record, points."""
        data = self._get(f'league/{self.league_key}/standings')
        league = data['fantasy_content']['league']
        teams_raw = league[1]['standings'][0]['teams']
        teams = []
        for i in range(int(teams_raw['count'])):
            t = teams_raw[str(i)]['team']
            meta = t[0]
            standings_data = t[2]['team_standings']

            # Extract fields from meta array
            team_key = meta[0]['team_key']
            team_id  = meta[1]['team_id']
            name     = meta[2]['name']
            logo     = next((m['team_logos'][0]['team_logo']['url']
                             for m in meta if 'team_logos' in m), '')
            managers = [mgr['manager']['nickname']
                        for m in meta if 'managers' in m
                        for mgr in m['managers']]

            record = standings_data.get('outcome_totals', {})
            rank   = standings_data.get('rank') or str(i + 1)
            pct    = standings_data.get('winning_pct') or record.get('percentage') or '.000'
            moves  = next((m['number_of_moves'] for m in meta if 'number_of_moves' in m), 0)

            teams.append({
                'team_key': team_key,
                'team_id':  team_id,
                'name':     name,
                'logo':     logo,
                'managers': managers,
                'rank':     int(rank),
                'wins':     int(record.get('wins', 0)),
                'losses':   int(record.get('losses', 0)),
                'ties':     int(record.get('ties', 0)),
                'pct':      pct if pct else '.000',
                'moves':    int(moves),
            })
        teams.sort(key=lambda t: t['rank'])
        return teams

    def get_scoreboard(self, week: int) -> list:
        """Returns list of matchups for the given week, including per-category stats."""
        data = self._get(f'league/{self.league_key}/scoreboard;week={week}')
        league = data['fantasy_content']['league']
        matchups_raw = league[1]['scoreboard']['0']['matchups']

        STAT_MAP = {
            '7': 'R', '12': 'HR', '13': 'RBI', '16': 'SB', '4': 'OBP',
            '26': 'ERA', '27': 'WHIP', '42': 'K', '32': 'SV', '83': 'QS',
        }
        # These stats: lower value = winning
        LOWER_BETTER = {'ERA', 'WHIP'}
        CAT_ORDER = ['R', 'HR', 'RBI', 'SB', 'OBP', 'SV', 'K', 'ERA', 'WHIP', 'QS']

        matchups = []
        for i in range(int(matchups_raw['count'])):
            m = matchups_raw[str(i)]['matchup']
            week_num  = m.get('week')
            status    = m.get('status', 'postevent')
            teams_raw = m['0']['teams']
            teams = []
            for j in range(int(teams_raw['count'])):
                t = teams_raw[str(j)]['team']
                meta        = t[0]
                team_pts    = t[1].get('team_points', {})
                team_proj   = t[1].get('team_projected_points', {})
                team_stats  = t[1].get('team_stats', {})

                name     = meta[2]['name']
                team_key = meta[0]['team_key']
                points   = team_pts.get('total', '0')
                projected = team_proj.get('total', '0')

                # Parse per-category stats
                cats = {}
                stats_raw = team_stats.get('stats', [])
                # Yahoo returns stats as a list of {"stat": {"stat_id": "N", "value": "V"}}
                if isinstance(stats_raw, list):
                    for s in stats_raw:
                        if isinstance(s, dict) and 'stat' in s:
                            sid = str(s['stat'].get('stat_id', ''))
                            val = s['stat'].get('value', '-')
                            if sid in STAT_MAP:
                                cats[STAT_MAP[sid]] = val if val not in ('', None) else '-'
                elif isinstance(stats_raw, dict):
                    for idx in range(int(stats_raw.get('count', 0))):
                        s = stats_raw.get(str(idx), {})
                        if isinstance(s, dict) and 'stat' in s:
                            sid = str(s['stat'].get('stat_id', ''))
                            val = s['stat'].get('value', '-')
                            if sid in STAT_MAP:
                                cats[STAT_MAP[sid]] = val if val not in ('', None) else '-'

                teams.append({
                    'team_key':  team_key,
                    'name':      name,
                    'points':    float(points),
                    'projected': float(projected),
                    'cats':      cats,
                })

            # Determine per-category winner: 0 = team0 wins, 1 = team1 wins, None = tie/-
            cat_winners = {}
            if len(teams) == 2:
                for cat in CAT_ORDER:
                    v0 = teams[0]['cats'].get(cat, '-')
                    v1 = teams[1]['cats'].get(cat, '-')
                    try:
                        f0, f1 = float(v0), float(v1)
                        if cat in LOWER_BETTER:
                            if f0 < f1:   cat_winners[cat] = 0
                            elif f1 < f0: cat_winners[cat] = 1
                            else:          cat_winners[cat] = None
                        else:
                            if f0 > f1:   cat_winners[cat] = 0
                            elif f1 > f0: cat_winners[cat] = 1
                            else:          cat_winners[cat] = None
                    except (ValueError, TypeError):
                        cat_winners[cat] = None

            # Tally category wins
            wins = [0, 0]
            for w in cat_winners.values():
                if w == 0: wins[0] += 1
                elif w == 1: wins[1] += 1

            matchups.append({
                'week':        week_num,
                'status':      status,
                'teams':       teams,
                'cat_winners': cat_winners,
                'cat_wins':    wins,   # [team0_wins, team1_wins]
                'cat_order':   CAT_ORDER,
            })
        return matchups

    def get_transactions(self, count: int = 25) -> list:
        """Returns recent transactions (adds, drops, trades)."""
        data = self._get(f'league/{self.league_key}/transactions;count={count}')
        league = data['fantasy_content']['league']
        trans_raw = league[1].get('transactions', {})
        if not trans_raw:
            return []
        transactions = []
        for i in range(int(trans_raw.get('count', 0))):
            t = trans_raw[str(i)]['transaction']
            # t is a list: [metadata_dict, players_dict]
            meta = t[0] if isinstance(t[0], dict) else {}
            players_container = t[1] if len(t) > 1 else {}
            players_raw = players_container.get('players', {}) if isinstance(players_container, dict) else {}

            tx_type = meta.get('type', '')
            tx_time = meta.get('timestamp', '')
            if tx_time:
                tx_time = datetime.fromtimestamp(int(tx_time)).strftime('%b %d')

            players = []
            for k in [str(n) for n in range(int(players_raw.get('count', 0)))]:
                p = players_raw[k]['player']
                p_meta_arr = p[0]   # list of dicts: [{player_key},{player_id},{name},{team},{display_position},...]
                p_txdata_raw = p[1].get('transaction_data', []) if isinstance(p[1], dict) else []

                # transaction_data can be a list (add) or a dict (drop) — normalize to dict
                if isinstance(p_txdata_raw, list):
                    tx_data = p_txdata_raw[0] if p_txdata_raw else {}
                else:
                    tx_data = p_txdata_raw  # already a dict

                # Extract name and position robustly
                p_name = '?'
                p_pos  = ''
                for item in p_meta_arr:
                    if isinstance(item, dict):
                        if 'name' in item:
                            p_name = item['name'].get('full', '?')
                        if 'display_position' in item:
                            p_pos = item['display_position']

                players.append({
                    'name': p_name,
                    'pos':  p_pos,
                    'type': tx_data.get('type', tx_type),
                    'destination_team': tx_data.get('destination_team_name', ''),
                    'source_team':      tx_data.get('source_team_name', 'FA'),
                })

            transactions.append({
                'type':    tx_type,
                'date':    tx_time,
                'players': players,
            })
        return transactions

    def get_team_roster(self, team_key: str, week: int = None) -> list:
        """Returns roster for a team (optionally for a specific week)."""
        endpoint = f'team/{team_key}/roster'
        if week:
            endpoint += f';week={week}'
        data = self._get(endpoint)
        team_data = data['fantasy_content']['team']
        players_raw = team_data[1]['roster']['0']['players']
        players = []
        for i in range(int(players_raw['count'])):
            p = players_raw[str(i)]['player']
            meta = p[0]
            # Extract fields by searching for the right key in each meta item
            name, pos, status, status_full, injury_note = '?', '', '', '', ''
            mlb_team, player_key, headshot_url = '', '', ''
            for item in meta:
                if not isinstance(item, dict):
                    continue
                if 'player_key' in item:
                    player_key = item['player_key']
                if 'name' in item:
                    name = item['name'].get('full', '?')
                if 'display_position' in item:
                    pos = item['display_position']
                if 'status' in item and item['status']:
                    status = item['status']
                if 'status_full' in item and item['status_full']:
                    status_full = item['status_full']
                if 'injury_note' in item and item['injury_note']:
                    injury_note = item['injury_note']
                if 'editorial_team_abbr' in item:
                    mlb_team = item['editorial_team_abbr']
                if 'headshot' in item:
                    headshot_url = item['headshot'].get('url', '')
            selected = ''
            sel_raw = p[1].get('selected_position', []) if isinstance(p[1], dict) else []
            for s in sel_raw:
                if isinstance(s, dict) and 'position' in s:
                    selected = s['position']
                    break
            players.append({
                'player_key':   player_key,
                'name':         name,
                'pos':          pos,
                'status':       status,
                'status_full':  status_full,   # e.g. "Day-to-Day", "15-Day IL"
                'injury_note':  injury_note,   # e.g. "Lower Leg", "Elbow"
                'mlb_team':     mlb_team,
                'headshot_url': headshot_url,
                'starting':     selected,
            })
        return players

    def get_player_stats_batch(self, player_keys: list) -> dict:
        """Fetch season stats for a list of player keys.
        Returns {player_key: {'R': val, 'HR': val, ...}}.
        Stat IDs: R=7, HR=12, RBI=13, SB=16, OBP=4,
                  ERA=26, WHIP=27, K=42, SV=32, QS=83, IP=50.
        """
        if not player_keys:
            return {}
        STAT_MAP = {
            '7': 'R', '12': 'HR', '13': 'RBI', '16': 'SB', '4': 'OBP',
            '26': 'ERA', '27': 'WHIP', '42': 'K', '32': 'SV', '83': 'QS', '50': 'IP',
        }
        result = {}
        for i in range(0, len(player_keys), 25):
            chunk = player_keys[i:i + 25]
            try:
                data = self._get(f'players;player_keys={",".join(chunk)};out=stats')
                players_out = data['fantasy_content']['players']
                for j in range(int(players_out.get('count', 0))):
                    pl = players_out[str(j)]['player']
                    p_key = next((m['player_key'] for m in pl[0] if isinstance(m, dict) and 'player_key' in m), '')
                    stats_raw = pl[1].get('player_stats', {}).get('stats', [])
                    stats = {STAT_MAP[str(s['stat']['stat_id'])]: s['stat'].get('value', '-')
                             for s in stats_raw if str(s['stat']['stat_id']) in STAT_MAP}
                    if p_key:
                        result[p_key] = stats
            except Exception as e:
                print(f'    ⚠️  Stats batch failed: {e}')
        return result

    def get_player_week_stats_batch(self, player_keys: list, week: int) -> dict:
        """Fetch per-player stats for a specific fantasy week.
        Returns {player_key: {cat_name: value, ...}}.
        Stat IDs: R=7, HR=12, RBI=13, SB=16, OBP=4,
                  ERA=26, WHIP=27, K=42, SV=32, QS=83, IP=50.
        """
        if not player_keys:
            return {}
        STAT_MAP = {
            '7': 'R', '12': 'HR', '13': 'RBI', '16': 'SB', '4': 'OBP',
            '26': 'ERA', '27': 'WHIP', '42': 'K', '32': 'SV', '83': 'QS', '50': 'IP',
        }
        result = {}
        for i in range(0, len(player_keys), 25):
            chunk = player_keys[i:i + 25]
            try:
                data = self._get(
                    f'players;player_keys={",".join(chunk)};out=stats;type=week;week={week}'
                )
                players_out = data['fantasy_content']['players']
                for j in range(int(players_out.get('count', 0))):
                    pl = players_out[str(j)]['player']
                    p_key = next(
                        (m['player_key'] for m in pl[0]
                         if isinstance(m, dict) and 'player_key' in m), ''
                    )
                    stats_raw = pl[1].get('player_stats', {}).get('stats', [])
                    stats = {}
                    if isinstance(stats_raw, list):
                        for s in stats_raw:
                            if isinstance(s, dict) and 'stat' in s:
                                sid = str(s['stat'].get('stat_id', ''))
                                val = s['stat'].get('value', '-')
                                if sid in STAT_MAP:
                                    stats[STAT_MAP[sid]] = val if val not in ('', None) else '-'
                    elif isinstance(stats_raw, dict):
                        for idx in range(int(stats_raw.get('count', 0))):
                            s = stats_raw.get(str(idx), {})
                            if isinstance(s, dict) and 'stat' in s:
                                sid = str(s['stat'].get('stat_id', ''))
                                val = s['stat'].get('value', '-')
                                if sid in STAT_MAP:
                                    stats[STAT_MAP[sid]] = val if val not in ('', None) else '-'
                    if p_key:
                        result[p_key] = stats
            except Exception as e:
                print(f'    ⚠️  Week stats batch failed (chunk {i}): {e}')
        return result

    def get_player_projected_stats(self, player_keys: list, week: int) -> dict:
        """Fetch Yahoo's projected-week stats for a list of players.

        Primary source for Monte Carlo simulation.
        Endpoint: players;out=stats;type=projected_week;week={N}

        Returns {player_key: {cat_name: value, ...}}.
        Stat IDs: R=7, HR=12, RBI=13, SB=16, OBP=4,
                  ERA=26, WHIP=27, K=42, SV=32, QS=83, IP=50.
        """
        if not player_keys:
            return {}
        STAT_MAP = {
            '7': 'R', '12': 'HR', '13': 'RBI', '16': 'SB', '4': 'OBP',
            '26': 'ERA', '27': 'WHIP', '42': 'K', '32': 'SV', '83': 'QS', '50': 'IP',
        }
        result = {}
        for i in range(0, len(player_keys), 25):
            chunk = player_keys[i:i + 25]
            try:
                data = self._get(
                    f'players;player_keys={",".join(chunk)};out=stats;type=projected_week;week={week}'
                )
                players_out = data['fantasy_content']['players']
                for j in range(int(players_out.get('count', 0))):
                    pl = players_out[str(j)]['player']
                    p_key = next(
                        (m['player_key'] for m in pl[0]
                         if isinstance(m, dict) and 'player_key' in m), ''
                    )
                    stats_raw = pl[1].get('player_stats', {}).get('stats', [])
                    stats = {}
                    if isinstance(stats_raw, list):
                        for s in stats_raw:
                            if isinstance(s, dict) and 'stat' in s:
                                sid = str(s['stat'].get('stat_id', ''))
                                val = s['stat'].get('value', '-')
                                if sid in STAT_MAP and val not in ('', None, '-', '0', 0):
                                    stats[STAT_MAP[sid]] = val
                    elif isinstance(stats_raw, dict):
                        for idx in range(int(stats_raw.get('count', 0))):
                            s = stats_raw.get(str(idx), {})
                            if isinstance(s, dict) and 'stat' in s:
                                sid = str(s['stat'].get('stat_id', ''))
                                val = s['stat'].get('value', '-')
                                if sid in STAT_MAP and val not in ('', None, '-', '0', 0):
                                    stats[STAT_MAP[sid]] = val
                    if p_key:
                        result[p_key] = stats
            except Exception as e:
                print(f'    ⚠️  Projected stats batch failed (chunk {i}): {e}')
        return result

    def get_player_news(self, player_keys: list) -> dict:
        """Fetch injury status and notes for a list of player keys.

        Yahoo's Fantasy API does not expose Rotowire blurbs directly.
        This method batch-fetches the default player resource and extracts
        status, status_full, and injury_note for any player with a flag.

        Returns {player_key: [{'headline': str, 'summary': str, 'url': str, 'timestamp': str}]}.
        Players with no injury status are omitted from the result.
        """
        if not player_keys:
            return {}
        result = {}
        for i in range(0, len(player_keys), 25):
            chunk = player_keys[i:i + 25]
            try:
                data = self._get(
                    f'players;player_keys={",".join(chunk)}'
                )
                players_out = data['fantasy_content']['players']
                for j in range(int(players_out.get('count', 0))):
                    pl = players_out[str(j)]['player']
                    meta = pl[0]
                    p_key, status, status_full, injury_note = '', '', '', ''
                    for item in meta:
                        if not isinstance(item, dict):
                            continue
                        if 'player_key' in item:
                            p_key = item['player_key']
                        if 'status' in item and item['status']:
                            status = item['status']
                        if 'status_full' in item and item['status_full']:
                            status_full = item['status_full']
                        if 'injury_note' in item and item['injury_note']:
                            injury_note = item['injury_note']
                    if p_key and status:
                        headline = status_full or status
                        summary  = injury_note or 'No body part listed.'
                        result[p_key] = [{
                            'headline':  headline,
                            'summary':   summary,
                            'url':       '',
                            'timestamp': '',
                        }]
            except Exception as e:
                print(f'    ⚠️  Player news batch failed (chunk {i}): {e}')
        return result

    def get_league_week(self) -> int:
        """Returns the current week number from the league."""
        info = self.get_league_info()
        return int(info.get('current_week', 1))


# ── CLI test ───────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    import sys
    api = YahooFantasyAPI()
    print(f'League key: {api.league_key}')

    cmd = sys.argv[1] if len(sys.argv) > 1 else 'info'

    if cmd == 'info':
        info = api.get_league_info()
        print(f"League: {info.get('name')}")
        print(f"Season: {info.get('season')}")
        print(f"Current week: {info.get('current_week')}")
        print(f"Start week: {info.get('start_week')}")
        print(f"End week: {info.get('end_week')}")

    elif cmd == 'standings':
        teams = api.get_standings()
        print(f'\n{"Rank":<5} {"Team":<35} {"W-L-T":<12} {"Pct":<6} {"Moves"}')
        print('─' * 70)
        for t in teams:
            record = f'{t["wins"]}-{t["losses"]}-{t["ties"]}'
            print(f'{t["rank"]:<5} {t["name"]:<35} {record:<12} {t["pct"]:<6} {t["moves"]}')

    elif cmd == 'scoreboard':
        week = int(sys.argv[2]) if len(sys.argv) > 2 else api.get_league_week()
        matchups = api.get_scoreboard(week)
        print(f'\nWeek {week} Matchups:')
        for m in matchups:
            t = m['teams']
            print(f'  {t[0]["name"]} ({t[0]["points"]}) vs {t[1]["name"]} ({t[1]["points"]})')

    elif cmd == 'transactions':
        txs = api.get_transactions(10)
        print(f'\nRecent transactions:')
        for tx in txs:
            for p in tx['players']:
                print(f'  [{tx["date"]}] {p["type"].upper()}: {p["name"]} ({p["pos"]}) → {p["destination_team"] or "dropped"}')

    elif cmd == 'week':
        print(f'Current week: {api.get_league_week()}')

    elif cmd == 'news':
        # Usage: python3 yahoo_api.py news <player_key> [<player_key2> ...]
        keys = sys.argv[2:] if len(sys.argv) > 2 else []
        if not keys:
            print('Usage: python3 yahoo_api.py news <player_key> [<player_key2> ...]')
        else:
            news = api.get_player_news(keys)
            if not news:
                print('No news found for the given player keys.')
            for pk, items in news.items():
                print(f'\n{pk}:')
                for it in items:
                    print(f'  [{it["timestamp"]}] {it["headline"]}')
                    print(f'  {it["summary"][:200]}...' if len(it["summary"]) > 200 else f'  {it["summary"]}')
