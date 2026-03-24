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

BASE_DIR = Path(__file__).parent.parent

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
        rows.append(
            f'            <tr{style}>'
            f'<td class="rank-cell">{rank}</td>'
            f'<td>{name}</td>'
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

# ── Render matchups HTML ──────────────────────────────────────────────────────
def render_matchups(matchups: list, week: int) -> str:
    cards = []
    for i, m in enumerate(matchups):
        teams = m['teams']
        t0, t1 = teams[0], teams[1]
        is_motw = i == 0  # First matchup is matchup of the week

        meta_html = '<div class="matchup-meta">Matchup of the Week</div>\n        ' if is_motw else ''

        # Show score if live/post, projected if pre
        def score_display(t):
            if m['status'] == 'preevent':
                return '0&ndash;0&ndash;0'
            return str(int(t['points'])) if t['points'] else '0'

        cards.append(f'''      <div class="matchup-card reveal">
        {meta_html}<div class="matchup-teams">
          <div class="matchup-team">
            <div class="matchup-team-name">{t0["name"]}</div>
            <div class="matchup-record">{score_display(t0)}</div>
          </div>
          <div class="matchup-vs">VS</div>
          <div class="matchup-team">
            <div class="matchup-team-name">{t1["name"]}</div>
            <div class="matchup-record">{score_display(t1)}</div>
          </div>
        </div>
        <div class="matchup-preview-link"><a href="week-{week:02d}.html#matchup-{i+1}">Preview &rarr;</a></div>
      </div>''')

    return '    <div class="matchups-grid">\n' + '\n\n'.join(cards) + '\n\n    </div>'

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

    # Update the dropdown toggle label on nav
    html = re.sub(
        r'(<a href="week-\d+\.html" class="nav-dropdown-toggle">)Week \d+ &#9662;',
        rf'\1Week {current_week} &#9662;',
        html
    )
    html = re.sub(
        r'(<a href=")week-\d+(\.html" class="nav-dropdown-toggle">)',
        rf'\1week-{current_week:02d}\2',
        html
    )

    index_path.write_text(html)
    print(f'  ✅  index.html updated (Week {current_week}, {updated_at})')

if __name__ == '__main__':
    main()
