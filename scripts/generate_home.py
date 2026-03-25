#!/usr/bin/env python3
"""
generate_home.py — Regenerate index.html with live standings, transactions,
and current week matchup snapshot. Run every Sunday night.

Usage:
    python3 scripts/generate_home.py
"""

import sys
import re
from pathlib import Path
from datetime import datetime

# Add parent dir to path so we can import yahoo_api
sys.path.insert(0, str(Path(__file__).parent))
from yahoo_api import YahooFantasyAPI
import generate_teams

BASE_DIR = Path(__file__).parent.parent

# ── Headshot mapping (team name → relative img path) ─────────────────────────
TEAM_HEADSHOTS = {
    'One Ball Two Strikes':       'img/headshots/one-ball.png',
    'The Ragans Administration':  'img/headshots/ragans.jpeg',
    'Decoy':                      'img/headshots/decoy.jpeg',
    'Good Vibes Only':            'img/headshots/good-vibes.jpeg',
    'Keanu Reeves':               'img/headshots/keanu.jpeg',
    'Ete Crow':                   'img/headshots/ete-crow.jpeg',
    'Rain City Bombers':          'img/headshots/rain-city.jpeg',
    'Busch Latte':                'img/headshots/busch-latte.jpg',
    'Skenes\u2019n on deez Hoerners':  'img/headshots/skenes.jpeg',
    'The Buckner Boots':          'img/headshots/buckner.jpeg',
}

def headshot_img(team_name: str, size_class: str = '') -> str:
    src = TEAM_HEADSHOTS.get(team_name, 'img/headshots/one-ball.png')
    cls = f'headshot {size_class}'.strip()
    return f'<img src="{src}" alt="{team_name}" class="{cls}" />'

# ── Week dates lookup (add as season progresses) ──────────────────────────────
WEEK_DATES = {
    1:  ('Mar 25', 'Mar 29'),
    2:  ('Mar 30', 'Apr 5'),
    3:  ('Apr 6',  'Apr 12'),
    4:  ('Apr 13', 'Apr 19'),
    5:  ('Apr 20', 'Apr 26'),
    6:  ('Apr 27', 'May 3'),
    7:  ('May 4',  'May 10'),
    8:  ('May 11', 'May 17'),
    9:  ('May 18', 'May 24'),
    10: ('May 25', 'May 31'),
    11: ('Jun 1',  'Jun 7'),
    12: ('Jun 8',  'Jun 14'),
    13: ('Jun 15', 'Jun 21'),
    14: ('Jun 22', 'Jun 28'),
    15: ('Jun 29', 'Jul 5'),
    16: ('Jul 6',  'Jul 12'),
    17: ('Jul 13', 'Jul 19'),
    18: ('Jul 20', 'Jul 26'),
    19: ('Jul 27', 'Aug 2'),
    20: ('Aug 3',  'Aug 9'),
    21: ('Aug 10', 'Aug 16'),
    22: ('Aug 17', 'Aug 23'),
    23: ('Aug 24', 'Aug 30'),
    24: ('Aug 31', 'Sep 6'),
    25: ('Sep 7',  'Sep 13'),
}

# ── HTML replacement helper ───────────────────────────────────────────────────
def replace_section(html: str, tag: str, new_content: str) -> str:
    """Replace content between <!-- AUTO:TAG_START --> and <!-- AUTO:TAG_END -->"""
    pattern = rf'(<!-- AUTO:{tag}_START -->).*?(<!-- AUTO:{tag}_END -->)'
    replacement = rf'\1\n{new_content}\n    \2'
    result = re.sub(pattern, replacement, html, flags=re.DOTALL)
    if result == html:
        print(f'  ⚠️  Warning: tag AUTO:{tag} not found in HTML')
    return result

# ── Render standings HTML ─────────────────────────────────────────────────────
def render_standings(teams: list) -> str:
    rows = []
    for i, t in enumerate(teams):
        rank = t['rank']
        name = t['name']
        mgr  = t['managers'][0] if t['managers'] else '—'
        rec  = f'{t["wins"]}&ndash;{t["losses"]}&ndash;{t["ties"]}'
        pct  = t['pct'] if t['pct'] else '.000'
        moves = t['moves']
        # Add playoff cutline marker after 6th team
        style = ' class="playoff-cutline"' if rank == 6 else ''
        img = headshot_img(name, 'headshot-sm')
        rows.append(
            f'            <tr{style}>'
            f'<td class="rank-cell">{rank}</td>'
            f'<td><div class="team-cell">{img}<span class="team-cell-name">{name}</span></div></td>'
            f'<td class="muted-cell">{mgr}</td>'
            f'<td>{rec}</td>'
            f'<td>{pct}</td>'
            f'<td>{moves}</td>'
            f'</tr>'
        )
    header = '''        <table class="standings-table standings-live">
          <thead>
            <tr>
              <th>Rank</th><th>Team</th><th>Manager</th>
              <th>W&ndash;L&ndash;T</th><th>Pct</th><th>Moves</th>
            </tr>
          </thead>
          <tbody>\n'''
    return header + '\n'.join(rows) + '\n          </tbody>\n        </table>'

# ── Category score helpers ────────────────────────────────────────────────────
CAT_ORDER = ['R', 'HR', 'RBI', 'SB', 'OBP', 'SV', 'K', 'ERA', 'WHIP', 'QS']

def _cats_have_data(matchup: dict) -> bool:
    """Return True if at least one team has a non-zero category value."""
    for t in matchup.get('teams', []):
        for v in t.get('cats', {}).values():
            try:
                if float(v) != 0:
                    return True
            except (ValueError, TypeError):
                pass
    return False

def _render_cat_table(matchup: dict) -> str:
    """Compact 10-cat table for a home-page matchup card."""
    teams = matchup['teams']
    t0, t1 = teams[0], teams[1]
    cat_winners = matchup.get('cat_winners', {})
    cat_wins    = matchup.get('cat_wins', [0, 0])

    w0_cls = ' mc-score-lead' if cat_wins[0] > cat_wins[1] else ''
    w1_cls = ' mc-score-lead' if cat_wins[1] > cat_wins[0] else ''

    score_line = (
        f'<div class="mc-score-tally">'
        f'<span class="mc-score-num{w0_cls}">{cat_wins[0]}</span>'
        f'<span class="mc-score-dash">&ndash;</span>'
        f'<span class="mc-score-num{w1_cls}">{cat_wins[1]}</span>'
        f'</div>'
    )

    rows = []
    for cat in CAT_ORDER:
        v0 = t0['cats'].get(cat, '—')
        v1 = t1['cats'].get(cat, '—')
        w  = cat_winners.get(cat)
        c0 = ' mc-cat-lead' if w == 0 else ''
        c1 = ' mc-cat-lead' if w == 1 else ''
        rows.append(
            f'<div class="mc-cat-row">'
            f'<span class="mc-cat-val{c0}">{v0 if v0 not in ("", None) else "—"}</span>'
            f'<span class="mc-cat-name">{cat}</span>'
            f'<span class="mc-cat-val{c1}">{v1 if v1 not in ("", None) else "—"}</span>'
            f'</div>'
        )

    return (
        f'<div class="mc-cats">'
        f'{score_line}'
        f'<div class="mc-cat-rows">{"".join(rows)}</div>'
        f'</div>'
    )


# ── Render matchups HTML ──────────────────────────────────────────────────────
def render_matchups(matchups: list, week: int) -> str:
    cards = []
    for i, m in enumerate(matchups):
        teams = m['teams']
        t0, t1 = teams[0], teams[1]
        is_motw = i == 0
        has_data = _cats_have_data(m)

        meta_html = '        <div class="matchup-meta">&#11088; Matchup of the Week</div>\n' if is_motw else ''

        img0 = headshot_img(t0['name'], 'headshot-sm')
        img1 = headshot_img(t1['name'], 'headshot-sm')

        # Win tally badge next to team name when data is live
        def tally(idx):
            if not has_data: return ''
            wins = m.get('cat_wins', [0, 0])[idx]
            lead = wins > m.get('cat_wins', [0, 0])[1 - idx]
            cls  = ' mc-tally-lead' if lead else ''
            return f'<span class="mc-tally{cls}">{wins}</span>'

        if has_data:
            cat_table_html = _render_cat_table(m)
        elif m['status'] == 'preevent':
            cat_table_html = '<div class="mc-cats mc-cats-pending">Season starts Mar 25 &mdash; live scores update every 4 hours</div>'
        else:
            cat_table_html = ''

        cards.append(f'''      <div class="matchup-card reveal">
{meta_html}        <div class="matchup-teams">
          <div class="matchup-team">
            {img0}
            <div class="matchup-team-info">
              <div class="matchup-team-name">{t0["name"]}</div>
            </div>
            {tally(0)}
          </div>
          <div class="matchup-team">
            {img1}
            <div class="matchup-team-info">
              <div class="matchup-team-name">{t1["name"]}</div>
            </div>
            {tally(1)}
          </div>
        </div>
        {cat_table_html}
        <div class="matchup-preview-link"><a href="week-{week:02d}.html#matchup-{i+1}">Full Preview &rarr;</a></div>
      </div>''')

    return '    <div class="matchups-grid">\n' + '\n\n'.join(cards) + '\n\n    </div>'


# ── Per-card live score strip (embedded in matchup-detail-card) ───────────────
BATTING_CATS  = ['R', 'HR', 'RBI', 'SB', 'OBP']
PITCHING_CATS = ['SV', 'K', 'ERA', 'WHIP', 'QS']

# ── Roster rendering ──────────────────────────────────────────────────────────
_PITCHER_SLOTS = {'SP', 'RP', 'P'}
_BENCH_SLOTS   = {'BN', 'IL', 'IL+', 'NA'}
_SLOT_ORDER_BAT = ['C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'Util', 'DH', 'BN', 'IL', 'IL+', 'NA']
_SLOT_ORDER_PIT = ['SP', 'RP', 'P', 'BN', 'IL', 'IL+', 'NA']

def _player_is_pitcher(slot: str, pos: str) -> bool:
    s = slot.upper()
    if any(x in s for x in ['SP', 'RP']):
        return True
    if s in ('C', '1B', '2B', '3B', 'SS', 'OF', 'LF', 'CF', 'RF', 'UTIL', 'DH'):
        return False
    p = pos.upper()
    return any(x in p for x in ['SP', 'RP'])

def _slot_sort(slot: str, pitcher: bool) -> int:
    order = _SLOT_ORDER_PIT if pitcher else _SLOT_ORDER_BAT
    try:    return order.index(slot)
    except ValueError:
        return 99

def _roster_player_row(player: dict, cats: list) -> str:
    slot   = player.get('starting', '')
    pos    = player.get('pos', '')
    name   = player.get('name', '?')
    mlb    = player.get('mlb_team', '').upper()
    status = player.get('status', '')
    hs     = player.get('headshot_url', '')
    stats  = player.get('stats', {})
    bench  = slot in _BENCH_SLOTS

    img = (f'<img src="{hs}" class="mdc-rost-img" onerror="this.style.display=\'none\'" />'
           if hs else
           f'<span class="mdc-rost-img mdc-rost-img-ph">{(name[0] if name else "?").upper()}</span>')

    badge = ''
    if status in ('IL', 'IL+', 'DL', 'DTD'):
        badge = f'<span class="mdc-rost-badge badge-il">{status}</span>'
    elif status == 'NA':
        badge = '<span class="mdc-rost-badge badge-na">NA</span>'

    stat_cells = ''.join(
        f'<span class="mdc-rost-stat">{stats.get(c, "-")}</span>' for c in cats
    )
    row_cls = ' mdc-rost-row-bench' if bench else ''
    return (
        f'<div class="mdc-rost-row{row_cls}">'
        f'{img}'
        f'<span class="mdc-rost-slot">{slot or pos}</span>'
        f'<span class="mdc-rost-name">{name}{badge}</span>'
        f'<span class="mdc-rost-mlb">{mlb}</span>'
        f'<div class="mdc-rost-stats">{stat_cells}</div>'
        f'</div>'
    )

def _roster_team_col(players: list, team_name: str) -> str:
    pitcher_flag = {p.get('player_key',''): _player_is_pitcher(p.get('starting',''), p.get('pos',''))
                    for p in players}
    batters  = sorted([p for p in players if not pitcher_flag[p.get('player_key','')]],
                      key=lambda p: _slot_sort(p.get('starting',''), False))
    pitchers = sorted([p for p in players if pitcher_flag[p.get('player_key','')]],
                      key=lambda p: _slot_sort(p.get('starting',''), True))

    def subhdr(label, cats):
        lbls = ''.join(f'<span>{c}</span>' for c in cats)
        return (f'<div class="mdc-rost-subhdr">'
                f'<span class="mdc-rost-subhdr-lbl">{label}</span>'
                f'<div class="mdc-rost-stat-lbls">{lbls}</div>'
                f'</div>')

    bat_rows = ''.join(_roster_player_row(p, BATTING_CATS)  for p in batters)
    pit_rows = ''.join(_roster_player_row(p, PITCHING_CATS) for p in pitchers)
    return (
        f'<div class="mdc-rost-col">'
        f'<div class="mdc-rost-team-hdr">{team_name}</div>'
        f'{subhdr("BATTING", BATTING_CATS)}{bat_rows}'
        f'{subhdr("PITCHING", PITCHING_CATS)}{pit_rows}'
        f'</div>'
    )

def render_roster_section(roster0: list, roster1: list, name0: str, name1: str) -> str:
    """Expandable two-team roster strip for a matchup card."""
    if not roster0 and not roster1:
        return ''
    col0 = _roster_team_col(roster0, name0)
    col1 = _roster_team_col(roster1, name1)
    toggle_js = ("var r=this.closest('.mdc-rost');"
                 "r.classList.toggle('open');"
                 "this.querySelector('.mdc-rost-chevron').textContent="
                 "r.classList.contains('open')?'\u25b4':'\u25be';")
    return (
        f'<div class="mdc-rost">'
        f'<button class="mdc-rost-toggle" onclick="{toggle_js}">'
        f'<span>Show Rosters</span>'
        f'<span class="mdc-rost-chevron">&#9662;</span>'
        f'</button>'
        f'<div class="mdc-rost-body">'
        f'<div class="mdc-rost-grid">{col0}{col1}</div>'
        f'</div>'
        f'</div>'
    )

def get_rosters_for_week(api, ordered_matchups: list, week: int) -> list:
    """Fetch rosters + current-week stats for every team in the matchup list.
    Returns [(roster0, roster1), ...] aligned with ordered_matchups."""
    # Collect unique team keys preserving matchup order
    all_keys = []
    for m in ordered_matchups:
        if m:
            for t in m['teams']:
                k = t.get('team_key', '')
                if k and k not in all_keys:
                    all_keys.append(k)

    # Fetch each team's roster
    rosters_by_key = {}
    for tk in all_keys:
        try:
            rosters_by_key[tk] = api.get_team_roster(tk, week)
        except Exception as e:
            print(f'    ⚠️  Roster fetch failed for {tk}: {e}')
            rosters_by_key[tk] = []

    # Batch-fetch week stats for every player across all rosters
    all_player_keys = [p['player_key'] for players in rosters_by_key.values()
                       for p in players if p.get('player_key')]
    print(f'  Fetching week {week} player stats ({len(all_player_keys)} players)...')
    stats_map = api.get_player_week_stats_batch(all_player_keys, week)

    # Inject stats into each player dict
    for players in rosters_by_key.values():
        for p in players:
            p['stats'] = stats_map.get(p.get('player_key', ''), {})

    # Pair rosters to matchups
    result = []
    for m in ordered_matchups:
        if m is None:
            result.append(([], []))
        else:
            t0k = m['teams'][0].get('team_key', '')
            t1k = m['teams'][1].get('team_key', '')
            result.append((rosters_by_key.get(t0k, []), rosters_by_key.get(t1k, [])))
    return result

def _ordered_matchups_for_week(week_html: str, api_matchups: list) -> list:
    """Return API matchups re-ordered and re-paired to match the week HTML card order.
    Uses team names in headshot alt attributes to find the right matchup for each card.
    Returns a list of length 5; None entries mean no matching API matchup found."""
    name_to_matchup = {}
    for m in api_matchups:
        for t in m['teams']:
            name_to_matchup[t['name']] = m

    ordered = []
    for n in range(1, 6):
        # Extract the two headshot alt attributes from this card
        block_m = re.search(
            rf'id="matchup-{n}"(.*?)(?:id="matchup-{n+1}"|<!-- SLEEPER|</section>)',
            week_html, re.DOTALL
        )
        if not block_m:
            ordered.append(None)
            continue
        block = block_m.group(1)
        alts = re.findall(r'class="headshot[^"]*"[^>]*alt="([^"]+)"', block)
        if len(alts) < 2:
            ordered.append(None)
            continue
        card_name0, card_name1 = alts[0], alts[1]
        # Find the API matchup that contains either team
        found = None
        for m in api_matchups:
            api_names = {t['name'] for t in m['teams']}
            if card_name0 in api_names or card_name1 in api_names:
                found = m
                break
        if found is None:
            ordered.append(None)
            continue
        # Re-pair so team order matches the card (left=card_name0, right=card_name1)
        t_by_name = {t['name']: t for t in found['teams']}
        t0 = t_by_name.get(card_name0, found['teams'][0])
        t1 = t_by_name.get(card_name1, found['teams'][1])
        entry = dict(found)
        entry['teams'] = [t0, t1]
        # Recalculate cat_winners and cat_wins with the new team ordering
        LOWER_BETTER = {'ERA', 'WHIP'}
        cat_winners = {}
        for cat in CAT_ORDER:
            v0 = t0['cats'].get(cat, '-')
            v1 = t1['cats'].get(cat, '-')
            try:
                f0, f1 = float(v0), float(v1)
                if cat in LOWER_BETTER:
                    cat_winners[cat] = 0 if f0 < f1 else (1 if f1 < f0 else None)
                else:
                    cat_winners[cat] = 0 if f0 > f1 else (1 if f1 > f0 else None)
            except (ValueError, TypeError):
                cat_winners[cat] = None
        wins = [sum(1 for w in cat_winners.values() if w == 0),
                sum(1 for w in cat_winners.values() if w == 1)]
        entry['cat_winners'] = cat_winners
        entry['cat_wins']    = wins
        ordered.append(entry)
    return ordered


def render_matchup_live_score(matchup: dict, updated_at: str) -> str:
    """Compact two-row score strip for one matchup card."""
    if matchup is None:
        return ''
    if not _cats_have_data(matchup):
        t0, t1 = matchup['teams'][0], matchup['teams'][1]
        return (
            '<div class="mdc-live">'
            '<div class="mdc-live-header">'
            '<span class="mdc-live-status status-upcoming">Pre-Game</span>'
            '<span class="mdc-score-block">'
            f'<span class="mdc-score-name">{t0["name"]}</span>'
            '<span class="mdc-score-num">0</span>'
            '<span class="mdc-score-dash">&mdash;</span>'
            '<span class="mdc-score-num">0</span>'
            f'<span class="mdc-score-name">{t1["name"]}</span>'
            '</span>'
            '</div>'
            '</div>'
        )

    t0, t1 = matchup['teams'][0], matchup['teams'][1]
    cat_winners = matchup.get('cat_winners', {})
    cat_wins    = matchup.get('cat_wins', [0, 0])
    status      = matchup.get('status', 'midevent')

    status_text = 'Final' if status == 'postevent' else 'Live'
    status_cls  = 'status-final' if status == 'postevent' else 'status-live'
    w0_cls = ' score-lead' if cat_wins[0] > cat_wins[1] else ''
    w1_cls = ' score-lead' if cat_wins[1] > cat_wins[0] else ''

    def cat_row_html(cats):
        cells = []
        for cat in cats:
            v0 = t0['cats'].get(cat, '—') or '—'
            v1 = t1['cats'].get(cat, '—') or '—'
            w  = cat_winners.get(cat)
            c0 = ' mdc-lead' if w == 0 else ''
            c1 = ' mdc-lead' if w == 1 else ''
            cells.append(
                f'<span class="mdc-cell">'
                f'<span class="mdc-cat">{cat}</span>'
                f'<span class="mdc-val{c0}">{v0}</span>'
                f'<span class="mdc-sep">/</span>'
                f'<span class="mdc-val{c1}">{v1}</span>'
                f'</span>'
            )
        return f'<div class="mdc-cat-row">{"".join(cells)}</div>'

    return (
        f'<div class="mdc-live">'
        f'<div class="mdc-live-header">'
        f'<span class="mdc-live-status {status_cls}">{status_text}</span>'
        f'<span class="mdc-score-block">'
        f'<span class="mdc-score-name">{t0["name"]}</span>'
        f'<span class="mdc-score-num{w0_cls}">{cat_wins[0]}</span>'
        f'<span class="mdc-score-dash">&mdash;</span>'
        f'<span class="mdc-score-num{w1_cls}">{cat_wins[1]}</span>'
        f'<span class="mdc-score-name">{t1["name"]}</span>'
        f'</span>'
        f'<span class="mdc-updated">{updated_at}</span>'
        f'</div>'
        f'{cat_row_html(BATTING_CATS)}'
        f'{cat_row_html(PITCHING_CATS)}'
        f'</div>'
    )

# ── Render transactions HTML ──────────────────────────────────────────────────
def render_transactions(transactions: list) -> str:
    if not transactions:
        return '      <div class="transactions-list"><div class="tx-empty">No recent transactions.</div></div>'

    rows = []
    for tx in transactions[:20]:
        for p in tx['players'][:1]:  # One row per transaction
            tx_type = p.get('type', tx['type'])
            type_class = {'add': 'tx-type-add', 'drop': 'tx-type-drop', 'trade': 'tx-type-trade'}.get(tx_type, 'tx-type-add')
            dest = p.get('destination_team') or p.get('source_team', 'FA')
            rows.append(
                f'        <div class="tx-row">'
                f'<span class="tx-date">{tx["date"]}</span>'
                f'<span class="tx-type {type_class}">{tx_type}</span>'
                f'<span class="tx-player">{p["name"]}</span>'
                f'<span class="tx-team">&rarr; {dest}</span>'
                f'</div>'
            )

    return '      <div class="transactions-list">\n' + '\n'.join(rows) + '\n      </div>'

# ── Render week archive HTML ──────────────────────────────────────────────────
def render_week_archive(current_week: int) -> str:
    tiles = []
    for w in range(1, 26):
        dates = WEEK_DATES.get(w, ('', ''))
        date_str = f'{dates[0]}&ndash;{dates[1]}' if dates[0] else ''
        is_playoff = w >= 23

        if w < current_week:
            # Completed week
            tile = (f'      <a href="week-{w:02d}.html" class="week-tile">\n'
                    f'        <div class="week-tile-num">Week {w}</div>\n'
                    f'        <div class="week-tile-dates">{date_str}</div>\n'
                    f'        <div class="week-tile-status status-recap">Recap</div>\n'
                    f'      </a>')
        elif w == current_week:
            # Current week
            tile = (f'      <a href="week-{w:02d}.html" class="week-tile week-tile-active">\n'
                    f'        <div class="week-tile-num">Week {w}</div>\n'
                    f'        <div class="week-tile-dates">{date_str}</div>\n'
                    f'        <div class="week-tile-status status-preview">Preview</div>\n'
                    f'      </a>')
        else:
            # Future week
            playoff_class = ' playoff-tile' if is_playoff else ''
            playoff_icon = ' &#127942;' if is_playoff else ''
            tile = f'      <div class="week-tile week-tile-locked{playoff_class}">Week {w}{playoff_icon}</div>'

        tiles.append(tile)

    return '\n'.join(tiles)

# ── Render week nav dropdown links ────────────────────────────────────────────
def render_week_links(current_week: int) -> str:
    links = []
    for w in range(1, current_week + 1):
        dates = WEEK_DATES.get(w, ('', ''))
        date_str = f'{dates[0]}&ndash;{dates[1]}' if dates[0] else ''
        active = ' class="active"' if w == current_week else ''
        links.append(f'        <a href="week-{w:02d}.html"{active}>Week {w} &mdash; {date_str}</a>')
    return '\n'.join(links)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print('\n🔄  Updating index.html...')

    api = YahooFantasyAPI()
    print('  Fetching league data...')

    current_week = api.get_league_week()
    dates = WEEK_DATES.get(current_week, ('', ''))
    date_str = f'{dates[0]}&ndash;{dates[1]}' if dates[0] else f'Week {current_week}'

    print(f'  Current week: {current_week}')

    teams       = api.get_standings()
    matchups    = api.get_scoreboard(current_week)
    transactions = api.get_transactions(25)

    updated_at = datetime.now().strftime('%b %d at %-I:%M %p')

    # Read current index.html
    index_path = BASE_DIR / 'index.html'
    html = index_path.read_text()

    # Update each section
    html = replace_section(html, 'STANDINGS',
        render_standings(teams))
    html = replace_section(html, 'STANDINGS_UPDATED',
        f'        <span class="muted">Updated {updated_at} Pacific</span>')
    html = replace_section(html, 'MATCHUPS',
        render_matchups(matchups, current_week))
    html = replace_section(html, 'MATCHUP_TITLE',
        f'      Week {current_week} Matchups &mdash; {date_str}')
    html = replace_section(html, 'TRANSACTIONS',
        render_transactions(transactions))
    html = replace_section(html, 'WEEK_ARCHIVE',
        render_week_archive(current_week))
    html = replace_section(html, 'WEEK_LINKS',
        render_week_links(current_week))
    html = replace_section(html, 'NAV_BADGE',
        f'  <div class="nav-badge">Week {current_week}</div>')
    html = replace_section(html, 'HERO_WEEK',
        f'      Week {current_week} &mdash; {date_str}')

    # Update the Weeks dropdown href to point to the current week page
    html = re.sub(
        r'(<a href=")week-\d+(\.html" class="nav-dropdown-toggle">)',
        rf'\1week-{current_week:02d}\2',
        html
    )

    index_path.write_text(html)
    print(f'  ✅  index.html updated (Week {current_week}, {updated_at})')

    # Update per-matchup live score + roster strips on the current week page
    week_path = BASE_DIR / f'week-{current_week:02d}.html'
    if week_path.exists():
        print(f'\n🔄  Updating week-{current_week:02d}.html...')
        week_html = week_path.read_text()
        ordered = _ordered_matchups_for_week(week_html, matchups)

        # Live scores
        for n, m in enumerate(ordered, start=1):
            week_html = replace_section(week_html, f'LIVE_SCORE_{n}',
                render_matchup_live_score(m, updated_at))

        # Rosters with week stats
        roster_pairs = get_rosters_for_week(api, ordered, current_week)
        for n, (m, (r0, r1)) in enumerate(zip(ordered, roster_pairs), start=1):
            if m:
                roster_html = render_roster_section(
                    r0, r1,
                    m['teams'][0]['name'],
                    m['teams'][1]['name']
                )
            else:
                roster_html = ''
            week_html = replace_section(week_html, f'ROSTER_{n}', roster_html)

        week_path.write_text(week_html)
        print(f'  ✅  week-{current_week:02d}.html updated (live scores + rosters)')
    else:
        print(f'  ⚠️  week-{current_week:02d}.html not found, skipping')

    # Also regenerate all team pages with live data
    print('\n🔄  Regenerating team pages...')
    generate_teams.main()

if __name__ == '__main__':
    main()
