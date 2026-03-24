#!/usr/bin/env python3
"""
generate_teams.py — Regenerate each team's landing page with live roster,
standings, and team-specific transactions pulled from the Yahoo Fantasy API.

Run standalone or imported and called from generate_home.py.

Usage:
    python3 scripts/generate_teams.py
"""

import sys
import re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from yahoo_api import YahooFantasyAPI

BASE_DIR = Path(__file__).parent.parent
TEAMS_DIR = BASE_DIR / 'teams'

# ── Team config ────────────────────────────────────────────────────────────────
# slug matches the html filename and headshot filename convention
TEAM_CONFIG = [
    {'id': 'senga',   'slug': 'busch-latte',  'name': 'Busch Latte',                'headshot': '../img/headshots/busch-latte.jpg'},
    {'id': 'skenes',  'slug': 'skenes',        'name': 'Skenes\u2019n on deez Hoerners',  'headshot': '../img/headshots/skenes.jpeg'},
    {'id': 'glas',    'slug': 'ete-crow',      'name': 'Ete Crow',                   'headshot': '../img/headshots/ete-crow.jpeg'},
    {'id': 'lets',    'slug': 'ragans',        'name': 'The Ragans Administration',  'headshot': '../img/headshots/ragans.jpeg'},
    {'id': 'keanu',   'slug': 'keanu',         'name': 'Keanu Reeves',               'headshot': '../img/headshots/keanu.jpeg'},
    {'id': 'vibes',   'slug': 'good-vibes',    'name': 'Good Vibes Only',            'headshot': '../img/headshots/good-vibes.jpeg'},
    {'id': 'rain',    'slug': 'rain-city',     'name': 'Rain City Bombers',          'headshot': '../img/headshots/rain-city.jpeg'},
    {'id': 'buckner', 'slug': 'buckner',       'name': 'The Buckner Boots',          'headshot': '../img/headshots/buckner.jpeg'},
    {'id': 'decoy',   'slug': 'decoy',         'name': 'Decoy',                      'headshot': '../img/headshots/decoy.jpeg'},
    {'id': 'oneball', 'slug': 'one-ball',      'name': 'One Ball Two Strikes',       'headshot': '../img/headshots/one-ball.png'},
]

# ── HTML replacement helper ────────────────────────────────────────────────────
def replace_section(html: str, tag: str, new_content: str) -> str:
    pattern = rf'(<!-- AUTO:{tag}_START -->).*?(<!-- AUTO:{tag}_END -->)'
    replacement = rf'\1\n{new_content}\n    \2'
    result = re.sub(pattern, replacement, html, flags=re.DOTALL)
    if result == html:
        print(f'  ⚠️  tag AUTO:{tag} not found')
    return result

# ── Render team record + rank badge ───────────────────────────────────────────
def render_team_record(team_data: dict) -> str:
    if not team_data:
        return '<div class="team-record-badge">Season not started</div>'
    rec  = f'{team_data["wins"]}&ndash;{team_data["losses"]}&ndash;{team_data["ties"]}'
    rank = team_data['rank']
    suffix = {1:'st',2:'nd',3:'rd'}.get(rank if rank <= 3 else 0, 'th')
    pct  = team_data['pct']
    return (
        f'<div class="team-record-badge">{rec} &middot; '
        f'<span class="rank-tag">#{rank}{suffix}</span>'
        f' &middot; {pct}</div>'
    )

# ── Render roster HTML ─────────────────────────────────────────────────────────
PITCHER_POSITIONS = {'SP', 'RP', 'P'}
BATTER_POSITIONS  = {'C', '1B', '2B', '3B', 'SS', 'OF', 'Util', 'DH', 'LF', 'CF', 'RF', 'MI', 'CI'}

def _slot_badge(slot: str) -> str:
    if slot in ('BN', 'Bench'):
        return f'<span class="roster-slot-badge bench">BN</span>'
    if slot in ('IL', 'IL10', 'IL15', 'IL60'):
        return f'<span class="roster-slot-badge il">IL</span>'
    return f'<span class="roster-slot-badge">{slot}</span>'

def _status_badge(status: str) -> str:
    if not status:
        return ''
    s = status.upper()
    if 'DTD' in s:
        return '<span class="status-badge dtd">DTD</span>'
    if s.startswith('IL') or s.startswith('DL') or 'INJ' in s:
        return '<span class="status-badge il">IL</span>'
    return f'<span class="status-badge dtd">{status}</span>'

def render_roster(players: list) -> str:
    batters  = [p for p in players if p['pos'].split(',')[0].strip() not in PITCHER_POSITIONS]
    pitchers = [p for p in players if p['pos'].split(',')[0].strip() in PITCHER_POSITIONS]

    def player_rows(group):
        if not group:
            return '<tr><td colspan="4" class="team-tx-empty">No players found.</td></tr>'
        rows = []
        for p in group:
            name   = p['name']
            pos    = p['pos']
            slot   = p.get('starting', '')
            status = p.get('status', '')
            rows.append(
                f'          <tr>'
                f'<td class="player-name">{name}</td>'
                f'<td><span class="roster-pos-badge">{pos}</span></td>'
                f'<td>{_slot_badge(slot)}</td>'
                f'<td>{_status_badge(status)}</td>'
                f'</tr>'
            )
        return '\n'.join(rows)

    def roster_table(group, title):
        return (
            f'      <div class="card">\n'
            f'        <div class="roster-col-title">{title}</div>\n'
            f'        <table class="roster-table">\n'
            f'          <thead><tr><th>Player</th><th>Pos</th><th>Slot</th><th>Status</th></tr></thead>\n'
            f'          <tbody>\n'
            f'{player_rows(group)}\n'
            f'          </tbody>\n'
            f'        </table>\n'
            f'      </div>'
        )

    return (
        f'    <div class="roster-grid">\n'
        f'{roster_table(batters, "Batters")}\n'
        f'{roster_table(pitchers, "Pitchers")}\n'
        f'    </div>'
    )

# ── Render mini standings table ────────────────────────────────────────────────
def render_standings(teams: list, highlight_name: str) -> str:
    rows = []
    for t in teams:
        rank   = t['rank']
        name   = t['name']
        mgr    = t['managers'][0] if t['managers'] else '—'
        rec    = f'{t["wins"]}&ndash;{t["losses"]}&ndash;{t["ties"]}'
        pct    = t['pct']
        moves  = t['moves']
        is_cut = rank == 6
        is_me  = name == highlight_name
        row_class = ''
        if is_cut: row_class += ' class="playoff-cutline"'
        if is_me:  row_class = f' class="{"playoff-cutline " if is_cut else ""}standings-highlight"'
        # Link team name to their page
        slug_map = {cfg['name']: cfg['slug'] for cfg in TEAM_CONFIG}
        slug = slug_map.get(name, '')
        link = f'<a href="{slug}.html">{name}</a>' if slug else name
        rows.append(
            f'          <tr{row_class}>'
            f'<td class="rank-cell">{rank}</td>'
            f'<td>{link}</td>'
            f'<td class="muted-cell">{mgr}</td>'
            f'<td>{rec}</td>'
            f'<td>{pct}</td>'
            f'<td>{moves}</td>'
            f'</tr>'
        )
    header = (
        '        <table class="standings-table standings-live">\n'
        '          <thead><tr>'
        '<th>Rank</th><th>Team</th><th>Manager</th>'
        '<th>W&ndash;L&ndash;T</th><th>Pct</th><th>Moves</th>'
        '</tr></thead>\n'
        '          <tbody>\n'
    )
    return header + '\n'.join(rows) + '\n          </tbody>\n        </table>'

# ── Render team-specific transactions ─────────────────────────────────────────
def render_team_transactions(all_txs: list, team_name: str) -> str:
    rows = []
    for tx in all_txs:
        for p in tx['players']:
            dest = p.get('destination_team', '')
            src  = p.get('source_team', '')
            p_type = p.get('type', tx['type'])
            # Include if this team added or dropped
            if dest == team_name or src == team_name:
                action_label = p_type.upper()
                if p_type == 'add':
                    meta = f'from {src}' if src and src != 'FA' else 'from FA'
                elif p_type == 'drop':
                    meta = 'to FA'
                elif p_type == 'trade':
                    meta = f'via trade'
                else:
                    meta = ''
                type_class = {'add': 'tx-type-add', 'drop': 'tx-type-drop', 'trade': 'tx-type-trade'}.get(p_type, 'tx-type-add')
                rows.append(
                    f'        <div class="team-tx-row">'
                    f'<span class="team-tx-date">{tx["date"]}</span>'
                    f'<span class="tx-type {type_class}">{action_label}</span>'
                    f'<span class="team-tx-player">{p["name"]}'
                    f'<span style="color:var(--muted);font-size:.78rem;font-weight:400"> ({p["pos"]})</span></span>'
                    f'<span class="team-tx-meta">{meta}</span>'
                    f'</div>'
                )
    if not rows:
        return '      <div class="team-tx-list"><div class="team-tx-empty">No transactions yet this season.</div></div>'
    return '      <div class="team-tx-list">\n' + '\n'.join(rows) + '\n      </div>'

# ── Render week nav links (for team pages, prefixed with ../) ─────────────────
WEEK_DATES = {
    1:  ('Mar 25', 'Mar 29'), 2:  ('Mar 30', 'Apr 5'),  3:  ('Apr 6',  'Apr 12'),
    4:  ('Apr 13', 'Apr 19'), 5:  ('Apr 20', 'Apr 26'), 6:  ('Apr 27', 'May 3'),
    7:  ('May 4',  'May 10'), 8:  ('May 11', 'May 17'), 9:  ('May 18', 'May 24'),
    10: ('May 25', 'May 31'), 11: ('Jun 1',  'Jun 7'),  12: ('Jun 8',  'Jun 14'),
    13: ('Jun 15', 'Jun 21'), 14: ('Jun 22', 'Jun 28'), 15: ('Jun 29', 'Jul 5'),
    16: ('Jul 6',  'Jul 12'), 17: ('Jul 13', 'Jul 19'), 18: ('Jul 20', 'Jul 26'),
    19: ('Jul 27', 'Aug 2'),  20: ('Aug 3',  'Aug 9'),  21: ('Aug 10', 'Aug 16'),
    22: ('Aug 17', 'Aug 23'), 23: ('Aug 24', 'Aug 30'), 24: ('Aug 31', 'Sep 6'),
    25: ('Sep 7',  'Sep 13'),
}

def render_week_links(current_week: int) -> str:
    links = []
    for w in range(1, current_week + 1):
        dates = WEEK_DATES.get(w, ('', ''))
        date_str = f'{dates[0]}&ndash;{dates[1]}' if dates[0] else ''
        active = ' class="active"' if w == current_week else ''
        links.append(f'        <a href="../week-{w:02d}.html"{active}>Week {w} &mdash; {date_str}</a>')
    return '\n'.join(links)

# ── Update a single team page ──────────────────────────────────────────────────
def update_team_page(slug: str, team_name: str, team_data: dict,
                     roster: list, all_standings: list,
                     all_txs: list, current_week: int, updated_at: str):
    page_path = TEAMS_DIR / f'{slug}.html'
    if not page_path.exists():
        print(f'  ⚠️  {slug}.html not found — skipping')
        return

    html = page_path.read_text()

    html = replace_section(html, 'TEAM_RECORD',     render_team_record(team_data))
    html = replace_section(html, 'ROSTER',          render_roster(roster))
    html = replace_section(html, 'TEAM_STANDINGS',  render_standings(all_standings, team_name))
    html = replace_section(html, 'TEAM_TRANSACTIONS', render_team_transactions(all_txs, team_name))
    html = replace_section(html, 'UPDATED_AT',
        f'<span class="muted">Updated {updated_at} Pacific</span>')
    html = replace_section(html, 'WEEK_LINKS',      render_week_links(current_week))
    html = replace_section(html, 'NAV_BADGE',
        f'  <div class="nav-badge">Week {current_week}</div>')

    # Update week dropdown toggle label + href
    html = re.sub(
        r'(<a href="\.\./week-\d+\.html" class="nav-dropdown-toggle">)Week \d+ &#9662;',
        rf'\1Week {current_week} &#9662;',
        html
    )
    html = re.sub(
        r'(<a href="\.\.)(/week-)\d+(\.html" class="nav-dropdown-toggle">)',
        rf'\1\2{current_week:02d}\3',
        html
    )

    page_path.write_text(html)
    print(f'  ✅  teams/{slug}.html updated')

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print('\n🔄  Updating team pages...')
    api = YahooFantasyAPI()

    current_week = api.get_league_week()
    print(f'  Week: {current_week}')

    print('  Fetching standings...')
    all_standings = api.get_standings()

    print('  Fetching transactions...')
    all_txs = api.get_transactions(100)  # large fetch to cover full team history

    updated_at = datetime.now().strftime('%b %d at %-I:%M %p')

    # Build name→standings lookup
    standings_by_name = {t['name']: t for t in all_standings}

    for cfg in TEAM_CONFIG:
        name = cfg['name']
        slug = cfg['slug']
        print(f'  Fetching roster: {name}...')

        # Get team_key from standings
        team_data = standings_by_name.get(name, {})
        team_key  = team_data.get('team_key', '')

        if team_key:
            try:
                roster = api.get_team_roster(team_key)
            except Exception as e:
                print(f'    ⚠️  Roster fetch failed for {name}: {e}')
                roster = []
        else:
            print(f'    ⚠️  team_key not found for {name} in standings')
            roster = []

        update_team_page(
            slug=slug,
            team_name=name,
            team_data=team_data,
            roster=roster,
            all_standings=all_standings,
            all_txs=all_txs,
            current_week=current_week,
            updated_at=updated_at,
        )

    print(f'\n✅  All team pages updated ({updated_at})')

if __name__ == '__main__':
    main()
