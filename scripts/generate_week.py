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
    'Busch Latte':                  {'2025_rank': 7,  'draft_slot': 1,  'img': 'busch-latte.jpg'},
    "Skenes'n on deez Hoerners":    {'2025_rank': 10, 'draft_slot': 2,  'img': 'skenes.jpeg'},
    '877-Glas-Now':                 {'2025_rank': 3,  'draft_slot': 3,  'img': ''},
    'LetsPlayMajorLeagueBaseball':  {'2025_rank': 1,  'draft_slot': 4,  'img': 'ragans.jpeg'},
    'The Ragans Administration':    {'2025_rank': 1,  'draft_slot': 4,  'img': 'ragans.jpeg'},
    'Keanu Reeves':                 {'2025_rank': 6,  'draft_slot': 5,  'img': 'keanu.jpeg'},
    'Good Vibes Only':              {'2025_rank': 4,  'draft_slot': 6,  'img': 'good-vibes.jpeg'},
    'Rain City Bombers':            {'2025_rank': 9,  'draft_slot': 7,  'img': 'rain-city.jpeg'},
    'The Buckner Boots':            {'2025_rank': 8,  'draft_slot': 8,  'img': 'buckner.jpeg'},
    'Decoy':                        {'2025_rank': 5,  'draft_slot': 9,  'img': 'decoy.jpeg'},
    'One Ball Two Strikes':         {'2025_rank': 2,  'draft_slot': 10, 'img': 'one-ball.png'},
    'Ete Crow':                     {'2025_rank': 3,  'draft_slot': 3,  'img': 'ete-crow.jpeg'},
}

def _summarize_roster(roster: list) -> dict:
    """Split a roster into batters/pitchers/closers."""
    PITCHER_SLOTS = {'SP', 'RP', 'P'}
    BENCH_SLOTS   = {'BN', 'IL', 'IL+', 'NA'}
    batters, starters, relievers, bench = [], [], [], []
    for p in roster:
        slot   = p.get('selected_position', '')
        pos    = p.get('display_position', '')
        name   = p.get('name', 'Unknown')
        status = p.get('status', '')
        label  = f"{name} ({pos})" + (f" [{status}]" if status else '')
        is_pitcher = slot in PITCHER_SLOTS or (slot in BENCH_SLOTS and ('SP' in pos or 'RP' in pos))
        is_bench   = slot in BENCH_SLOTS
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

def fetch_week_data(api: YahooFantasyAPI, week: int) -> dict:
    """Fetch all matchup + roster data for a week. Returns structured dict and saves to JSON.

    This is the data-gathering phase. Claude (running as the scheduled task agent)
    reads this JSON and writes the actual analysis content — no separate API call needed.
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
            try:
                roster = api.get_team_roster(t.get('team_key', ''))
                info['roster_summary'] = _summarize_roster(roster)
            except Exception as ex:
                print(f'    ⚠️  Roster fetch failed for {t["name"]}: {ex}')
                info['roster_summary'] = {}
            s = stand_by_name.get(t['name'], {})
            info['record'] = f"{s.get('wins',0)}-{s.get('losses',0)}-{s.get('ties',0)}"
            info['meta']   = TEAM_META.get(t['name'], {})
            return info
        matchups_data.append({'t0': enrich(t0_raw), 't1': enrich(t1_raw)})

    data = {'week': week, 'matchups': matchups_data, 'standings': standings}

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
      <!-- AUTO:LIVE_SCORE_{i+1}_START -->
      <!-- AUTO:LIVE_SCORE_{i+1}_END -->
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
  <title>Week {week} — Issaquah Swingers 2026</title>
  <meta property="og:title" content="Week {week} — Issaquah Swingers 2026" />
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
