#!/usr/bin/env python3
"""
generate_week.py — Generate or update a weekly page.

For the recap: fetches final scores + category winners, writes the recap section.
For the preview: fetches next week's matchups + rosters, writes the preview section.

This script is called by the scheduled Sunday-night task.

Usage:
    python3 scripts/generate_week.py              # auto-detect current week
    python3 scripts/generate_week.py recap 3      # force recap for week 3
    python3 scripts/generate_week.py preview 4    # force preview for week 4
"""

import sys
import re
import json
import subprocess
from pathlib import Path
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent))
from yahoo_api import YahooFantasyAPI
import monte_carlo
import fangraphs_projections as fg

BASE_DIR = Path(__file__).parent.parent

WEEK_DATES = {
    1:  ('2026-03-25', '2026-03-29'),
    2:  ('2026-03-30', '2026-04-05'),
    3:  ('2026-04-06', '2026-04-12'),
    4:  ('2026-04-13', '2026-04-19'),
    5:  ('2026-04-20', '2026-04-26'),
    6:  ('2026-04-27', '2026-05-03'),
    7:  ('2026-05-04', '2026-05-10'),
    8:  ('2026-05-11', '2026-05-17'),
    9:  ('2026-05-18', '2026-05-24'),
    10: ('2026-05-25', '2026-05-31'),
    11: ('2026-06-01', '2026-06-07'),
    12: ('2026-06-08', '2026-06-14'),
    13: ('2026-06-15', '2026-06-21'),
    14: ('2026-06-22', '2026-06-28'),
    15: ('2026-06-29', '2026-07-05'),
    16: ('2026-07-06', '2026-07-12'),
    17: ('2026-07-13', '2026-07-19'),
    18: ('2026-07-20', '2026-07-26'),
    19: ('2026-07-27', '2026-08-02'),
    20: ('2026-08-03', '2026-08-09'),
    21: ('2026-08-10', '2026-08-16'),
    22: ('2026-08-17', '2026-08-23'),
    23: ('2026-08-24', '2026-08-30'),
    24: ('2026-08-31', '2026-09-06'),
    25: ('2026-09-07', '2026-09-13'),
}

STAT_NAMES = {
    '7':  'R',
    '12': 'HR',
    '13': 'RBI',
    '16': 'SB',
    '4':  'OBP',
    '32': 'SV',
    '42': 'K',
    '26': 'ERA',
    '27': 'WHIP',
    '48': 'QS',
}

def fmt_date(iso: str) -> str:
    """'2026-03-25' → 'Mar 25'"""
    d = datetime.strptime(iso, '%Y-%m-%d')
    return d.strftime('%b %-d')

def replace_section(html: str, tag: str, new_content: str) -> str:
    pattern = rf'(<!-- AUTO:{tag}_START -->).*?(<!-- AUTO:{tag}_END -->)'
    replacement = rf'\1\n{new_content}\n    \2'
    result = re.sub(pattern, replacement, html, flags=re.DOTALL)
    if result == html:
        print(f'  ⚠️  Tag AUTO:{tag} not found')
    return result

def render_week_links(current_week: int) -> str:
    from generate_home import WEEK_DATES as WD
    links = []
    for w in range(1, current_week + 1):
        dates = WD.get(w, ('', ''))
        start = fmt_date(dates[0]) if dates[0] else ''
        end   = fmt_date(dates[1]) if dates[1] else ''
        date_str = f'{start}&ndash;{end}' if start else ''
        active = ' class="active"' if w == current_week else ''
        links.append(f'        <a href="week-{w:02d}.html"{active}>Week {w} &mdash; {date_str}</a>')
    return '\n'.join(links)

# ── RECAP GENERATOR ───────────────────────────────────────────────────────────
def generate_recap(api: YahooFantasyAPI, week: int) -> str:
    """Fetch final scores and generate recap HTML for the given week."""
    matchups = api.get_scoreboard(week)

    results = []
    biggest_win = None
    biggest_win_margin = 0
    choke = None
    choke_detail = ''

    for m in matchups:
        teams = m['teams']
        t0, t1 = teams[0], teams[1]
        score0, score1 = t0['points'], t1['points']
        if score0 >= score1:
            winner, loser = t0, t1
            wscore, lscore = score0, score1
        else:
            winner, loser = t1, t0
            wscore, lscore = score1, score0
        margin = wscore - lscore
        results.append({'winner': winner, 'loser': loser, 'wscore': wscore, 'lscore': lscore, 'margin': margin})
        if margin > biggest_win_margin:
            biggest_win_margin = margin
            biggest_win = results[-1]
        # Choke = closest loss by highest-projected team (simplistic)
        if choke is None:
            choke = results[-1]
            choke_detail = f'{loser["name"]} dropped {wscore:.0f}–{lscore:.0f} to {winner["name"]}.'

    # Final scores table
    score_rows = []
    for r in results:
        score_rows.append(
            f'          <div class="recap-matchup-row">'
            f'<span class="recap-team-winner">{r["winner"]["name"]}</span>'
            f'<span class="recap-score">{r["wscore"]:.0f} &ndash; {r["lscore"]:.0f}</span>'
            f'<span class="recap-team-loser">{r["loser"]["name"]}</span>'
            f'</div>'
        )

    bw = biggest_win
    biggest_win_html = (
        f'      <div class="callout-card callout-win">\n'
        f'        <div class="callout-label">&#127942; Biggest Win</div>\n'
        f'        <strong>{bw["winner"]["name"]}</strong> rolled {bw["wscore"]:.0f}–{bw["lscore"]:.0f} '
        f'over {bw["loser"]["name"]}. A {bw["margin"]:.0f}-point margin. '
        f'{bw["loser"]["name"]} will be fine. Probably.\n'
        f'      </div>'
    )
    choke_html = (
        f'      <div class="callout-card callout-choke">\n'
        f'        <div class="callout-label">&#128165; Choke of the Week</div>\n'
        f'        {choke_detail}\n'
        f'      </div>'
    )

    # Updated standings
    teams = api.get_standings()
    stand_rows = []
    for t in teams:
        rec = f'{t["wins"]}&ndash;{t["losses"]}&ndash;{t["ties"]}'
        stand_rows.append(
            f'            <tr><td class="rank-cell">{t["rank"]}</td>'
            f'<td>{t["name"]}</td>'
            f'<td>{rec}</td>'
            f'<td>{t["pct"]}</td></tr>'
        )

    generated_at  = datetime.now().strftime('%b %d at %-I:%M %p')
    scores_html   = '\n'.join(score_rows)
    standings_html = '\n'.join(stand_rows)
    return f'''  <section class="section" id="recap">
    <h2 class="section-title">
      <span class="section-icon">&#128202;</span> Week {week} Recap
    </h2>

    <div class="card reveal" style="margin-bottom:1.5rem;">
      <div class="card-title">Final Scores</div>
{scores_html}
    </div>

{biggest_win_html}
{choke_html}

    <div class="card reveal" style="margin-top:1.5rem;">
      <div class="card-title">Updated Standings</div>
      <div class="table-wrapper">
        <table class="standings-table standings-live">
          <thead><tr><th>Rank</th><th>Team</th><th>Record</th><th>Pct</th></tr></thead>
          <tbody>
{standings_html}
          </tbody>
        </table>
      </div>
    </div>

    <div class="card reveal" style="margin-top:1.5rem;">
      <p class="muted" style="font-size:.8rem;">Generated {generated_at} Pacific</p>
    </div>
  </section>'''

# ── TEAM METADATA ─────────────────────────────────────────────────────────────
TEAM_META = {
    'Busch Latte':                  {'2025_rank': 7,  'draft_slot': 1,  'img': 'busch-latte.png'},
    "Skenes'n on deez Hoerners":    {'2025_rank': 10, 'draft_slot': 2,  'img': 'skenes.jpeg'},
    'The Ragans Administration':    {'2025_rank': 3,  'draft_slot': 3,  'img': 'ragans.jpeg'},
    'Keanu Reeves':                 {'2025_rank': 6,  'draft_slot': 5,  'img': 'keanu.jpeg'},
    'Good Vibes Only':              {'2025_rank': 4,  'draft_slot': 6,  'img': 'good-vibes.jpeg'},
    'Rain City Bombers':            {'2025_rank': 9,  'draft_slot': 7,  'img': 'rain-city.jpeg'},
    'The Buckner Boots':            {'2025_rank': 8,  'draft_slot': 8,  'img': 'buckner.jpeg'},
    'Ray Donovan':                        {'2025_rank': 5,  'draft_slot': 9,  'img': 'decoy.jpeg'},
    'One Ball Two Strikes':         {'2025_rank': 2,  'draft_slot': 10, 'img': 'one-ball.png'},
    'Ete Crow':                     {'2025_rank': 1,  'draft_slot': 4,  'img': 'ete-crow.jpeg'},
}

def _summarize_roster(roster: list) -> dict:
    """Split a roster into active batters/starters/relievers and bench/IL.

    Uses 'starting' (selected slot) and 'pos' (eligible positions) from
    get_team_roster() output. IL/IL+/NA slots are bench; BN is bench.
    """
    PITCHER_SLOTS = {'SP', 'RP', 'P'}
    BENCH_SLOTS   = {'BN', 'IL', 'IL+', 'NA'}
    batters, starters, relievers, bench = [], [], [], []
    for p in roster:
        slot        = p.get('starting', '')       # actual rostered slot (C, 1B, SP, IL, BN, ...)
        pos         = p.get('pos', '')            # eligible positions (e.g. "SP", "2B,SS", "RP")
        name        = p.get('name', 'Unknown')
        status      = p.get('status', '')
        injury_note = p.get('injury_note', '')
        status_tag  = f"{status}: {injury_note}" if (status and injury_note) else status
        label  = f"{name} ({pos})" + (f" [{status_tag}]" if status_tag else '')
        is_bench   = slot in BENCH_SLOTS
        is_pitcher = slot in PITCHER_SLOTS or (is_bench and ('SP' in pos or 'RP' in pos))
        if is_pitcher:
            if 'SP' in pos:
                (bench if is_bench else starters).append(label)
            else:
                relievers.append(label)
        else:
            (bench if is_bench else batters).append(label)
    return {'batters': batters, 'starters': starters, 'relievers': relievers, 'bench': bench}

def _render_cat_edges(cat_edges: list) -> str:
    edge_map = {0: 'edge-away', 1: 'edge-home', -1: 'edge-even'}
    rows = []
    for e in cat_edges:
        css   = edge_map.get(e.get('edge', -1), 'edge-even')
        label = e.get('label', 'Even')
        cats  = e.get('cats', '')
        rows.append(
            f'          <div class="cat-row">'
            f'<span class="cat-name">{cats}</span>'
            f'<span class="cat-edge {css}">{label}</span>'
            f'</div>'
        )
    return '\n'.join(rows)

def compute_all_play(matchups: list) -> dict:
    """Compute all-play record for every team in a single week's matchups.

    For each team, simulate its category stats against every OTHER team's stats.
    Returns {team_name: {w, l, t, cat_w, cat_l}} sorted by all-play wins.

    This is the correct basis for weekly power rankings — it measures how strong
    a team's week actually was, independent of the luck of the H2H draw.

    A team that goes 7-2 all-play but loses its H2H matchup had a great week and
    drew a tough opponent. A team that wins H2H but goes 2-7 all-play got lucky.
    """
    CATS        = ['R', 'HR', 'RBI', 'SB', 'OBP', 'SV', 'K', 'ERA', 'WHIP', 'QS']
    LOW_IS_GOOD = {'ERA', 'WHIP'}

    # Build {team_name: cats_dict} for all teams in these matchups
    team_cats = {}
    for m in matchups:
        for tk in ('t0', 't1'):
            t    = m[tk]
            name = t.get('name', '')
            cats = t.get('cats', {})
            if name and name not in team_cats:
                team_cats[name] = cats

    all_play = {name: {'w': 0, 'l': 0, 't': 0, 'cat_w': 0, 'cat_l': 0}
                for name in team_cats}

    names = list(team_cats.keys())
    for i, t0 in enumerate(names):
        for j, t1 in enumerate(names):
            if i == j:
                continue
            c0, c1 = team_cats[t0], team_cats[t1]
            w = l = tie = 0
            for cat in CATS:
                v0, v1 = c0.get(cat), c1.get(cat)
                if v0 is None or v1 is None:
                    continue
                try:
                    f0, f1 = float(v0), float(v1)
                except (TypeError, ValueError):
                    continue
                if cat in LOW_IS_GOOD:
                    if f0 < f1:   w   += 1
                    elif f0 > f1: l   += 1
                    else:          tie += 1
                else:
                    if f0 > f1:   w   += 1
                    elif f0 < f1: l   += 1
                    else:          tie += 1
            if w > l:
                all_play[t0]['w'] += 1
            elif l > w:
                all_play[t0]['l'] += 1
            else:
                all_play[t0]['t'] += 1
            all_play[t0]['cat_w'] += w
            all_play[t0]['cat_l'] += l

    # Return sorted by all-play wins desc, cat_w as tiebreaker
    return dict(
        sorted(all_play.items(),
               key=lambda x: (x[1]['w'], x[1]['cat_w']),
               reverse=True)
    )


def fetch_recent_results(api: YahooFantasyAPI, current_week: int, n_weeks: int = 2) -> dict:
    """Fetch the last n completed weeks of results for every team.

    Returns a dict keyed by team_key:
    {
        "469.l.61583.t.10": {
            "team_name": "The Buckner Boots",
            "recent_weeks": [
                {
                    "week": 1,
                    "result": "W",          # W / L / T
                    "score": "6-4",         # categories won by each side
                    "cats_won":  ["R", "HR", "OBP", ...],
                    "cats_lost": ["SB", "SV", ...],
                    "cats_tied": [],
                    "opponent":  "One Ball Two Strikes",
                    "stats": {"R": 20, "HR": 7, ...}  # team's actual week totals
                }
            ]
        }
    }

    Weeks still in progress (status != 'postevent') are included with a
    status flag so Claude can treat them as partial context.
    """
    results = {}

    for w in range(max(1, current_week - n_weeks), current_week):
        try:
            scoreboard = api.get_scoreboard(w)
        except Exception as e:
            print(f'  ⚠️  Could not fetch scoreboard for week {w}: {e}')
            continue

        for matchup in scoreboard:
            status    = matchup.get('status', '')
            teams     = matchup.get('teams', [])
            cat_winners = matchup.get('cat_winners', {})
            cat_wins  = matchup.get('cat_wins', [0, 0])
            if len(teams) != 2:
                continue

            for idx in range(2):
                opp_idx = 1 - idx
                team    = teams[idx]
                opp     = teams[opp_idx]
                tk      = team.get('team_key', '')
                my_cats = cat_wins[idx]
                opp_cats = cat_wins[opp_idx]

                # Determine W/L/T
                if status != 'postevent':
                    result = 'in_progress'
                elif my_cats > opp_cats:
                    result = 'W'
                elif my_cats < opp_cats:
                    result = 'L'
                else:
                    result = 'T'

                # Which categories did this team win/lose/tie?
                cats_won, cats_lost, cats_tied = [], [], []
                for cat, winner in cat_winners.items():
                    if winner == idx:
                        cats_won.append(cat)
                    elif winner == (1 - idx):
                        cats_lost.append(cat)
                    else:
                        cats_tied.append(cat)

                entry = {
                    'week':      w,
                    'status':    status,
                    'result':    result,
                    'score':     f'{my_cats}-{opp_cats}',
                    'cats_won':  cats_won,
                    'cats_lost': cats_lost,
                    'cats_tied': cats_tied,
                    'opponent':  opp.get('name', '?'),
                    'stats':     team.get('cats', {}),
                }

                if tk not in results:
                    results[tk] = {
                        'team_name':    team.get('name', '?'),
                        'recent_weeks': []
                    }
                results[tk]['recent_weeks'].append(entry)

    return results


def fetch_player_week_stats(api: YahooFantasyAPI, week: int) -> dict:
    """Fetch individual player stats for a completed week across all 10 teams.

    Returns {player_key: {name, team_name, pos, stats}} where stats contains
    the categories we score:
      Batters:  R, HR, RBI, SB, OBP
      Pitchers: SV, K  (ERA/WHIP/QS are only reliable at team level from scoreboard)

    Stat IDs confirmed via Yahoo API:
      Batters:  R=7, HR=12, RBI=13, SB=16, OBP=4
      Pitchers: SV=32, K=35

    Note: pitcher K (stat_id 35) and SV (stat_id 32) are the most reliable
    individual pitcher stats available per-player. ERA/WHIP/QS are best read
    from team-level scoreboard totals, not summed from individual player stats.
    """
    # Stat IDs → category name
    BATTER_IDS  = {'7': 'R', '12': 'HR', '13': 'RBI', '16': 'SB', '4': 'OBP'}
    PITCHER_IDS = {'32': 'SV', '35': 'K'}
    ALL_IDS     = {**BATTER_IDS, **PITCHER_IDS}

    # Collect all players across all 10 teams
    all_players = []
    team_names  = {}
    for t_num in range(1, 11):
        team_key = f'mlb.l.{api.league_id}.t.{t_num}'
        try:
            roster = api.get_team_roster(team_key, week)
        except Exception:
            continue
        for p in roster:
            if p.get('starting') not in ('BN', 'IL', 'IL+', 'NA'):
                p['_team_key'] = team_key
                all_players.append(p)

    # Fetch team names from standings for attribution
    try:
        for s in api.get_standings():
            team_names[s.get('team_key', '')] = s.get('name', '')
    except Exception:
        pass

    result = {}
    batch_size = 25
    for i in range(0, len(all_players), batch_size):
        batch = all_players[i:i + batch_size]
        keys  = ','.join(p['player_key'] for p in batch)
        # Build key → player meta lookup for this batch
        meta = {p['player_key']: p for p in batch}
        try:
            r  = api._get(f'players;player_keys={keys};out=stats;type=week;week={week}')
            pb = r.get('fantasy_content', {}).get('players', {})
        except Exception:
            continue

        j = 0
        while str(j) in pb:
            items = pb[str(j)].get('player', [])
            pkey, pname, ppos = None, None, None
            pstats = {}
            for item in items:
                if isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, dict):
                            if 'player_key' in sub:
                                pkey = sub['player_key']
                            if 'name' in sub:
                                pname = sub['name'].get('full')
                            if 'display_position' in sub:
                                ppos = sub['display_position']
                elif isinstance(item, dict) and 'player_stats' in item:
                    for s in item['player_stats'].get('stats', []):
                        st  = s.get('stat', {})
                        sid = str(st.get('stat_id', ''))
                        if sid in ALL_IDS:
                            try:
                                pstats[ALL_IDS[sid]] = float(st.get('value', 0) or 0)
                            except (TypeError, ValueError):
                                pass
            if pkey:
                pm = meta.get(pkey, {})
                is_pitcher = any(x in (ppos or '') for x in ('SP', 'RP', 'P'))
                # Only store the relevant stat group
                if is_pitcher:
                    filtered = {k: v for k, v in pstats.items() if k in ('SV', 'K')}
                else:
                    filtered = {k: v for k, v in pstats.items() if k in ('R', 'HR', 'RBI', 'SB', 'OBP')}
                result[pkey] = {
                    'name':      pname,
                    'pos':       ppos,
                    'team_key':  pm.get('_team_key', ''),
                    'stats':     filtered,
                }
            j += 1

    matched = sum(1 for v in result.values() if v['stats'])
    print(f'    Player week stats: {matched}/{len(result)} players with data')
    return result


def fetch_week_data(api: YahooFantasyAPI, week: int) -> dict:
    """Fetch all matchup + roster data for a week, run Monte Carlo simulations,
    and save to JSON.

    This is the data-gathering phase. Claude (running as the scheduled task agent)
    reads this JSON and writes the actual analysis content — no separate API call needed.

    Monte Carlo simulation is injected into each matchup under the 'simulation' key:
        matchups[i]['simulation'] = {
            'cat_probs':      {'R': 0.61, 'HR': 0.74, ...},
            'expected_score': [6.3, 3.7],
            'win_pct':        0.71,
        }
    """
    print(f'  Fetching scoreboard + standings for Week {week}...')
    matchups  = api.get_scoreboard(week)
    try:
        standings = api.get_standings()
    except Exception:
        standings = []

    stand_by_name = {s['name']: s for s in standings}

    print(f'  Fetching rosters for all matchup teams...')
    matchups_data = []
    for m in matchups:
        teams = m['teams']
        t0_raw, t1_raw = teams[0], teams[1]
        def enrich(t):
            info = dict(t)
            raw_roster = []
            try:
                raw_roster = api.get_team_roster(t.get('team_key', ''), week)
                info['roster_summary'] = _summarize_roster(raw_roster)
            except Exception as ex:
                print(f'    ⚠️  Roster fetch failed for {t["name"]}: {ex}')
                info['roster_summary'] = {}
            # _raw_roster is used for simulation below; stripped before JSON save
            info['_raw_roster'] = raw_roster
            s = stand_by_name.get(t['name'], {})
            info['record'] = f"{s.get('wins',0)}-{s.get('losses',0)}-{s.get('ties',0)}"
            info['meta']   = TEAM_META.get(t['name'], {})
            return info
        matchups_data.append({'t0': enrich(t0_raw), 't1': enrich(t1_raw)})

    # ── Monte Carlo simulation ─────────────────────────────────────────────────
    print(f'  Running Monte Carlo simulations ({monte_carlo.N_SIMS:,} runs/matchup)...')

    # Collect all unique player keys across every active roster
    all_player_keys = []
    seen_keys = set()
    for m in matchups_data:
        for tk in ('t0', 't1'):
            for p in m[tk].get('_raw_roster', []):
                pk = p.get('player_key', '')
                if pk and pk not in seen_keys:
                    all_player_keys.append(pk)
                    seen_keys.add(pk)

    # Primary: FanGraphs steamerr (rest-of-season) projections scaled to this week.
    # steamerr updates throughout the season with actual performance, so it
    # responds to career years, role changes, and nagging injuries automatically.
    # Yahoo's projected_week endpoint returns current-week actuals during the week,
    # not forward projections, so it is no longer used as the primary source.
    projected_stats = {}
    try:
        projected_stats = fg.get_projections_for_all_matchups(
            matchups_data, week, api, force=False
        )
    except Exception as e:
        print(f'    ⚠️  FanGraphs projection fetch failed: {e}')

    # Fallback: Yahoo season stats (scaled to one week) for any player FanGraphs missed.
    # FanGraphs covers ~98% of active players; this catches rookies and call-ups
    # not yet in Steamer.
    missing_keys = [k for k in all_player_keys if not projected_stats.get(k)]
    if missing_keys:
        print(f'    Falling back to Yahoo season stats for {len(missing_keys)} unmatched players...')
        player_lookup = {}
        for m in matchups_data:
            for tk in ('t0', 't1'):
                for p in m[tk].get('_raw_roster', []):
                    player_lookup[p.get('player_key', '')] = p
        try:
            season = api.get_player_stats_batch(missing_keys)
            for pk, stats in season.items():
                if not projected_stats.get(pk):
                    is_p = monte_carlo._is_pitcher(player_lookup.get(pk, {}))
                    projected_stats[pk] = monte_carlo._scale_to_week(stats, is_p)
        except Exception as e:
            print(f'    ⚠️  Yahoo season stats fallback failed: {e}')

    # ── Player news ───────────────────────────────────────────────────────────
    print(f'  Fetching player news...')
    player_news_by_key = {}
    if all_player_keys:
        try:
            player_news_by_key = api.get_player_news(all_player_keys)
            print(f'    News: {len(player_news_by_key)} players have recent notes')
        except Exception as e:
            print(f'    ⚠️  Player news fetch failed: {e}')

    # Build a name → [news items] lookup from raw rosters before we pop them.
    # Stored per-team so Claude can see "Ketel Marte has X note" when writing
    # about The Buckner Boots without needing to cross-reference player keys.
    for m in matchups_data:
        for tk in ('t0', 't1'):
            news_for_team = {}
            for p in m[tk].get('_raw_roster', []):
                pk   = p.get('player_key', '')
                name = p.get('name', '')
                if pk and name and pk in player_news_by_key:
                    news_for_team[name] = player_news_by_key[pk]
            m[tk]['player_news'] = news_for_team  # persists in JSON

    # Simulate each matchup; pop _raw_roster before saving JSON
    for m in matchups_data:
        t0_roster = m['t0'].pop('_raw_roster', [])
        t1_roster = m['t1'].pop('_raw_roster', [])
        try:
            sim = monte_carlo.simulate_matchup(t0_roster, t1_roster, projected_stats)
            m['simulation'] = sim
            exp = sim['expected_score']
            t0n = m['t0'].get('name', '?')
            t1n = m['t1'].get('name', '?')
            print(f'    {t0n}  {exp[0]}–{exp[1]}  {t1n}  (t0 win% {sim["win_pct"]:.0%})')
        except Exception as e:
            print(f'    ⚠️  Simulation failed for matchup: {e}')
            m['simulation'] = None

    # ── Recent results (last 2 completed weeks) ───────────────────────────────
    # Gives Claude context on form, category trends, and hot/cold streaks
    # when writing matchup analysis and storylines.
    print(f'  Fetching recent results (last 2 weeks)...')
    recent_results = {}
    try:
        recent_results = fetch_recent_results(api, week, n_weeks=2)
        print(f'    Loaded results for {len(recent_results)} teams')
    except Exception as e:
        print(f'    ⚠️  Recent results fetch failed: {e}')

    # ── Player week stats (for recap: individual HR, RBI, K, SV leaders) ─────────
    # Fetched for the CURRENT week so when the Sunday night task runs after the
    # week ends, Claude has per-player stat lines to call out in the recap.
    # Batter stats (R, HR, RBI, SB, OBP) and pitcher K/SV are reliable.
    # ERA/WHIP/QS are only available at team level from the scoreboard.
    print(f'  Fetching player week stats (for recap analysis)...')
    player_week_stats = {}
    try:
        player_week_stats = fetch_player_week_stats(api, week)
    except Exception as e:
        print(f'    ⚠️  Player week stats fetch failed: {e}')

    # ── All-play power rankings ───────────────────────────────────────────────
    # Compare every team's category stats against every other team's stats.
    # This normalizes for H2H luck: a team that goes 7-2 all-play but lost
    # their actual matchup had a great week and drew a tough opponent.
    all_play = compute_all_play(matchups_data)

    data = {
        'week':              week,
        'matchups':          matchups_data,
        'standings':         standings,
        'recent_results':    recent_results,
        'player_week_stats': player_week_stats,
        'all_play':          all_play,
    }

    # Save JSON so the Cowork scheduled task (Claude) can read it
    out_path = BASE_DIR / 'data' / f'week-{week:02d}-preview-data.json'
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f'  ✅  Data saved → {out_path}')
    return data

# ── PREVIEW GENERATOR ─────────────────────────────────────────────────────────

def generate_preview(api: YahooFantasyAPI, week: int, analysis: dict = None) -> str:
    """Generate the preview HTML for a week.

    If `analysis` is provided (a dict with 'storylines' and 'matchups' keys written
    by Claude after reading the data JSON), it is injected into the cards.
    Otherwise builds the scaffold with placeholder markers so Claude can fill it in.
    """
    data     = fetch_week_data(api, week)
    dates    = WEEK_DATES.get(week, ('', ''))
    start    = fmt_date(dates[0]) if dates[0] else ''
    end      = fmt_date(dates[1]) if dates[1] else ''
    date_str = f'{start}&ndash;{end}' if start else f'Week {week}'

    matchup_cards = []
    for i, m in enumerate(data['matchups']):
        t0, t1 = m['t0'], m['t1']
        ai     = (analysis or {}).get('matchups', [{}] * 5)
        ai_m   = ai[i] if i < len(ai) else {}

        t0_analysis = ai_m.get('team0_analysis', '<!-- Claude analysis pending -->')
        t1_analysis = ai_m.get('team1_analysis', '<!-- Claude analysis pending -->')
        prediction  = ai_m.get('prediction', 'TBD.')
        cat_edges   = ai_m.get('cat_edges', [])

        cats_html = _render_cat_edges(cat_edges) if cat_edges else \
            '          <div class="cat-row"><span class="cat-name muted">Category breakdown pending</span></div>'

        t0_img = TEAM_META.get(t0['name'], {}).get('img', '')
        t1_img = TEAM_META.get(t1['name'], {}).get('img', '')
        t0_hs  = f'<img src="img/headshots/{t0_img}" class="headshot" alt="{t0["name"]}" />' if t0_img else ''
        t1_hs  = f'<img src="img/headshots/{t1_img}" class="headshot" alt="{t1["name"]}" />' if t1_img else ''

        matchup_cards.append(f'''    <div class="matchup-detail-card reveal" id="matchup-{i+1}">
      <div class="matchup-detail-header">
        <div class="matchup-detail-teams">
          <div class="matchup-detail-team-block">
            {t0_hs}
            <span class="matchup-detail-team">{t0["name"]}</span>
          </div>
          <span class="matchup-detail-vs">vs</span>
          <div class="matchup-detail-team-block">
            {t1_hs}
            <span class="matchup-detail-team">{t1["name"]}</span>
          </div>
        </div>
        <div class="matchup-detail-meta">Week {week} &bull; {date_str}</div>
      </div>
      <!-- AUTO:LIVE_SCORE_{i+1}_START -->
      <!-- AUTO:LIVE_SCORE_{i+1}_END -->
      <div class="matchup-detail-body">
        <div class="matchup-detail-analysis">
          <p>{t0_analysis}</p>
          <p>{t1_analysis}</p>
        </div>
        <div class="matchup-detail-cats">
{cats_html}
        </div>
      </div>
      <div class="matchup-prediction">
        <span class="prediction-label">Prediction:</span>
        <span class="prediction-text">{prediction}</span>
      </div>
      <!-- AUTO:ROSTER_{i+1}_START -->
      <!-- AUTO:ROSTER_{i+1}_END -->
    </div>''')

    if analysis and analysis.get('storylines'):
        storylines_html = '\n        '.join(analysis['storylines'])
    else:
        storylines_html = '<p><em>Preview analysis pending — Claude will fill this in as part of the scheduled task.</em></p>'

    generated_at = datetime.now().strftime('%b %d at %-I:%M %p')
    return f'''  <section class="section">
    <h2 class="section-title">
      <span class="section-icon">&#128270;</span> Week {week} Preview &mdash; {date_str}
    </h2>
    <div class="card reveal" style="margin-bottom:1.5rem;">
      <div class="card-title">&#128218; Storylines to Watch</div>
      <div class="storyline">
        {storylines_html}
      </div>
    </div>

    <h3 class="subsection-title">Matchup Breakdown</h3>
{chr(10).join(matchup_cards)}
    <p class="muted" style="font-size:.75rem;margin-top:1rem;">Generated {generated_at} Pacific</p>
  </section>'''

# ── PAGE CREATOR ──────────────────────────────────────────────────────────────
def create_week_page(week: int):
    """Create a week-XX.html file from the base template if it doesn't exist."""
    dates = WEEK_DATES.get(week, ('', ''))
    start = fmt_date(dates[0]) if dates[0] else f'Week {week} Start'
    end   = fmt_date(dates[1]) if dates[1] else f'Week {week} End'
    date_str = f'{start}&ndash;{end}'

    page_path = BASE_DIR / f'week-{week:02d}.html'
    if page_path.exists():
        return  # Already exists

    template = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Week {week} Preview — Issaquah Swingers 2026</title>
  <meta name="description" content="Week {week} matchup previews and Monte Carlo predictions for the Issaquah Swingers fantasy baseball league. {start}&#x2013;{end}, 2026." />
  <link rel="canonical" href="https://issaquahswingers.com/week-{week:02d}.html" />

  <!-- Open Graph -->
  <meta property="og:type" content="article" />
  <meta property="og:title" content="Week {week} Preview — Issaquah Swingers 2026" />
  <meta property="og:description" content="Week {week} matchup previews, Monte Carlo predictions, and storylines for the Issaquah Swingers fantasy baseball league. {start}&#x2013;{end}, 2026." />
  <meta property="og:image" content="https://issaquahswingers.com/preview.png" />
  <meta property="og:url" content="https://issaquahswingers.com/week-{week:02d}.html" />
  <meta property="og:site_name" content="Issaquah Swingers Fantasy Baseball" />

  <!-- Twitter / X -->
  <meta name="twitter:card" content="summary_large_image" />
  <meta name="twitter:title" content="Week {week} Preview — Issaquah Swingers 2026" />
  <meta name="twitter:description" content="Week {week} matchup previews and Monte Carlo predictions. {start}&#x2013;{end}, 2026." />
  <meta name="twitter:image" content="https://issaquahswingers.com/preview.png" />

  <!-- JSON-LD -->
  <script type="application/ld+json">
  {{
    "@context": "https://schema.org",
    "@type": "Article",
    "headline": "Issaquah Swingers Week {week} Fantasy Baseball Preview — {start}&#x2013;{end}, 2026",
    "description": "Week {week} matchup previews and Monte Carlo predictions for the Issaquah Swingers fantasy baseball league.",
    "url": "https://issaquahswingers.com/week-{week:02d}.html",
    "publisher": {{
      "@type": "Organization",
      "name": "Issaquah Swingers Fantasy Baseball"
    }},
    "datePublished": "{dates[0]}"
  }}
  </script>

  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🍍</text></svg>" />
  <link rel="stylesheet" href="styles.css" />
</head>
<body>

<nav>
  <a href="index.html" class="nav-logo">&#9918; Issaquah <span>Swingers</span></a>
  <button class="nav-toggle" aria-label="Toggle navigation">&#9776;</button>
  <div class="nav-links">
    <a href="index.html">Home</a>
    <a href="draft.html">Draft</a>
    <div class="nav-dropdown">
      <a href="week-{week:02d}.html" class="nav-dropdown-toggle active">Week {week} &#9662;</a>
      <div class="nav-dropdown-menu" id="weekDropdown">
        <!-- AUTO:WEEK_LINKS_START -->
        <a href="week-{week:02d}.html" class="active">Week {week} &mdash; {date_str}</a>
        <!-- AUTO:WEEK_LINKS_END -->
      </div>
    </div>
    <a href="season.html" class="muted">Season</a>
  </div>
  <div class="nav-badge week-badge">Week {week}</div>
</nav>

<header class="hero hero-week">
  <div class="hero-content">
    <div class="hero-tag">Week {week}</div>
    <h1>Week {week}<br/><span>{date_str}</span></h1>
    <p class="hero-sub">5 Matchups <span class="sep"></span> H2H Categories</p>
  </div>
</header>

<div class="container">

  <!-- AUTO:PREVIEW_START -->
  <section class="section section-locked">
    <div class="card reveal recap-pending">
      <div class="recap-pending-icon">&#128270;</div>
      <div class="recap-pending-text">Week {week} preview will be generated Sunday night before the week starts.</div>
    </div>
  </section>
  <!-- AUTO:PREVIEW_END -->

  <!-- AUTO:RECAP_START -->
  <section class="section section-locked" id="recap">
    <h2 class="section-title"><span class="section-icon">&#128202;</span> Week {week} Recap</h2>
    <div class="card reveal recap-pending">
      <div class="recap-pending-icon">&#9203;</div>
      <div class="recap-pending-text">Week {week} ends {end}. Recap drops Sunday night.</div>
    </div>
  </section>
  <!-- AUTO:RECAP_END -->

</div>

<footer>
  <p>Issaquah Swingers Fantasy Baseball &middot; 2026 Season</p>
</footer>

<script>
document.querySelector('.nav-toggle').addEventListener('click', function() {{
  document.querySelector('.nav-links').classList.toggle('nav-open');
}});
const dt = document.querySelector('.nav-dropdown-toggle');
if (dt) {{
  dt.addEventListener('click', function(e) {{ e.preventDefault(); this.closest('.nav-dropdown').classList.toggle('open'); }});
  document.addEventListener('click', function(e) {{ if (!e.target.closest('.nav-dropdown')) document.querySelectorAll('.nav-dropdown').forEach(d => d.classList.remove('open')); }});
}}
const obs = new IntersectionObserver(entries => entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }}), {{threshold:.06}});
document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
</script>
</body>
</html>'''
    page_path.write_text(template)
    print(f'  📄  Created week-{week:02d}.html')
    update_sitemap(week)

def update_sitemap(week: int):
    """Add a new week URL to sitemap.xml if not already present."""
    sitemap_path = BASE_DIR / 'sitemap.xml'
    if not sitemap_path.exists():
        return
    sitemap = sitemap_path.read_text(encoding='utf-8')
    url = f'https://issaquahswingers.com/week-{week:02d}.html'
    if url in sitemap:
        return  # Already in sitemap
    new_entry = f'''  <url>
    <loc>{url}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.8</priority>
  </url>'''
    # Insert before </urlset>
    sitemap = sitemap.replace('</urlset>', f'{new_entry}\n\n</urlset>')
    sitemap_path.write_text(sitemap, encoding='utf-8')
    print(f'  🗺️  Added week-{week:02d} to sitemap.xml')

# ── GIT PUSH ──────────────────────────────────────────────────────────────────
def git_push(week: int, action: str):
    from pathlib import Path
    env_path = BASE_DIR / '.env'
    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

    repo   = env.get('GITHUB_REPO', '')
    token  = env.get('GITHUB_TOKEN', '')

    if not repo or not token:
        print('  ⚠️  GITHUB_REPO or GITHUB_TOKEN not set — skipping push')
        return

    try:
        # Set remote with token
        remote_url = f'https://{token}@github.com/{repo}.git'
        subprocess.run(['git', 'remote', 'set-url', 'origin', remote_url],
                       cwd=BASE_DIR, check=True, capture_output=True)

        subprocess.run(['git', 'add', '-A'], cwd=BASE_DIR, check=True)

        commit_msg = f'auto: week {week} {action} — {datetime.now().strftime("%Y-%m-%d")}'
        result = subprocess.run(
            ['git', 'commit', '-m', commit_msg],
            cwd=BASE_DIR, capture_output=True, text=True
        )
        if 'nothing to commit' in result.stdout:
            print('  ℹ️  Nothing to commit')
            return

        try:
            subprocess.run(['git', 'push', 'origin', 'main'],
                           cwd=BASE_DIR, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            # Remote is ahead — fetch + merge (never rebase; rebase leaves
            # lock files the sandbox cannot clean up), then push again.
            print('  ↩️  Remote ahead — fetching and merging...')
            subprocess.run(['git', 'fetch', 'origin'],
                           cwd=BASE_DIR, check=True, capture_output=True)
            subprocess.run(['git', 'merge', '--no-edit', 'origin/main'],
                           cwd=BASE_DIR, check=True, capture_output=True)
            subprocess.run(['git', 'push', 'origin', 'main'],
                           cwd=BASE_DIR, check=True, capture_output=True)
        print(f'  ✅  Pushed: {commit_msg}')
    except subprocess.CalledProcessError as e:
        print(f'  ❌  Git push failed: {e}')

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    api = YahooFantasyAPI()
    current_week = api.get_league_week()

    # Parse args: [mode] [week]
    mode = sys.argv[1] if len(sys.argv) > 1 else 'auto'
    week = int(sys.argv[2]) if len(sys.argv) > 2 else current_week

    print(f'\n🗓  Running generate_week.py — mode={mode}, week={week}')

    if mode == 'dump':
        # Just fetch and save roster/matchup data — Claude reads the JSON and writes analysis
        print(f'\n📦  Dumping Week {week} data...')
        fetch_week_data(api, week)
        print(f'\n✅  Done. Read data/week-{week:02d}-preview-data.json to write analysis.')
        return

    if mode == 'recap' or mode == 'auto':
        # Generate recap for the week that just ended
        recap_week = week if mode == 'recap' else current_week
        print(f'\n📋  Generating recap for Week {recap_week}...')
        page_path = BASE_DIR / f'week-{recap_week:02d}.html'
        if not page_path.exists():
            create_week_page(recap_week)
        html = page_path.read_text()
        recap_html = generate_recap(api, recap_week)
        html = replace_section(html, 'RECAP', recap_html)
        html = replace_section(html, 'WEEK_LINKS', render_week_links(recap_week))
        page_path.write_text(html)
        print(f'  ✅  week-{recap_week:02d}.html recap updated')

    if mode == 'preview' or mode == 'auto':
        # Generate preview for next week
        preview_week = week if mode == 'preview' else current_week + 1
        if preview_week <= 25:
            print(f'\n👁  Generating preview for Week {preview_week}...')
            create_week_page(preview_week)
            page_path = BASE_DIR / f'week-{preview_week:02d}.html'
            html = page_path.read_text()
            preview_html = generate_preview(api, preview_week)
            html = replace_section(html, 'PREVIEW', preview_html)
            html = replace_section(html, 'WEEK_LINKS', render_week_links(preview_week))
            page_path.write_text(html)
            print(f'  ✅  week-{preview_week:02d}.html preview updated')

    # Update home page
    print('\n🏠  Updating home page...')
    import generate_home
    generate_home.main()

    # Git push
    print('\n📤  Pushing to GitHub...')
    git_push(week, mode)

    print('\n✅  Done.')

if __name__ == '__main__':
    main()
