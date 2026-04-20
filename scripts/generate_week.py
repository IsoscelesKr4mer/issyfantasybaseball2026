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
    pattern = re.compile(rf'(<!-- AUTO:{tag}_START -->).*?(<!-- AUTO:{tag}_END -->)', re.DOTALL)
    # Use a callable so backslashes in new_content are never misread as backreferences
    def _sub(m):
        return m.group(1) + '\n' + new_content + '\n    ' + m.group(2)
    result = pattern.sub(_sub, html)
    if result == html:
        print(f'  ⚠️  Tag AUTO:{tag} not found')
    return result

def extract_live_scores(html: str) -> dict:
    """Extract existing LIVE_SCORE content from HTML before a PREVIEW replacement wipes it."""
    scores = {}
    for n in range(1, 6):
        pattern = rf'<!-- AUTO:LIVE_SCORE_{n}_START -->(.*?)<!-- AUTO:LIVE_SCORE_{n}_END -->'
        m = re.search(pattern, html, re.DOTALL)
        if m:
            scores[n] = m.group(1)
    return scores

def reinject_live_scores(html: str, scores: dict) -> str:
    """Re-inject saved LIVE_SCORE content after PREVIEW was replaced with empty tags."""
    for n, content in scores.items():
        if not content.strip():
            continue  # nothing to restore
        html = replace_section(html, f'LIVE_SCORE_{n}', content.strip())
    return html

def render_week_links(current_week: int, recap_week: int = 0) -> str:
    """Desktop dropdown: grouped week label + Preview / Recap sub-links.

    recap_week: the last week that has a completed recap (0 = none yet).
    Weeks <= recap_week get both sub-links; current_week gets Preview only.
    """
    groups = []
    for w in range(1, current_week + 1):
        dates    = WEEK_DATES.get(w, ('', ''))
        start    = fmt_date(dates[0]) if dates[0] else ''
        end      = fmt_date(dates[1]) if dates[1] else ''
        date_str = f'{start}&ndash;{end}' if start else ''
        label_active = ' active' if w == current_week else ''
        has_recap    = w < current_week  # completed weeks have recaps
        groups.append(
            f'        <div class="week-nav-group">'
            f'<span class="week-nav-label{label_active}">Week {w} &mdash; {date_str}</span>'
            f'<div class="week-nav-sub">'
            f'<a href="week-{w:02d}.html#preview">Preview</a>'
            + (f'<a href="week-{w:02d}.html#recap">Recap</a>' if has_recap else '')
            + f'</div></div>'
        )
    return '\n'.join(groups)


def render_weeks_sheet_items(current_week: int) -> str:
    """Mobile bottom-sheet: grouped week header + Preview / Recap pill buttons."""
    groups = []
    for w in range(1, current_week + 1):
        dates    = WEEK_DATES.get(w, ('', ''))
        start    = fmt_date(dates[0]) if dates[0] else ''
        end      = fmt_date(dates[1]) if dates[1] else ''
        date_str = f'{start}&ndash;{end}' if start else ''
        header_active = ' active' if w == current_week else ''
        has_recap     = w < current_week
        recap_html    = (f'<a href="week-{w:02d}.html#recap" class="week-sheet-sub-link">Recap</a>'
                         if has_recap else '')
        groups.append(
            f'      <div class="week-sheet-group">'
            f'<div class="week-sheet-header{header_active}">Week {w} &mdash; {date_str}</div>'
            f'<div class="week-sheet-sub">'
            f'<a href="week-{w:02d}.html#preview" class="week-sheet-sub-link">Preview</a>'
            + recap_html
            + f'</div></div>'
        )
    return '\n'.join(groups)

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
    'Allahu Alvarez':    {'2025_rank': 10, 'draft_slot': 2,  'img': 'skenes.jpeg'},
    'The Ragans Administration':    {'2025_rank': 3,  'draft_slot': 3,  'img': 'ragans.jpeg'},
    'Keanu Reeves':                 {'2025_rank': 6,  'draft_slot': 5,  'img': 'keanu.jpeg'},
    'Good Vibes Only':              {'2025_rank': 4,  'draft_slot': 6,  'img': 'good-vibes.jpeg'},
    'Rain City Bombers':            {'2025_rank': 9,  'draft_slot': 7,  'img': 'rain-city.jpeg'},
    'The Buckner Boots':            {'2025_rank': 8,  'draft_slot': 8,  'img': 'buckner.jpeg'},
    'Ray Donovan':                        {'2025_rank': 5,  'draft_slot': 9,  'img': 'decoy.jpeg'},
    'Nick-fil-A':                         {'2025_rank': 5,  'draft_slot': 9,  'img': 'decoy.jpeg'},
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

    all_play = {name: {'w': 0, 'l': 0, 't': 0, 'cat_w': 0, 'cat_l': 0, 'cat_t': 0}
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
            all_play[t0]['cat_t'] += tie

    # Return sorted by all-play wins desc, cat_w as tiebreaker
    return dict(
        sorted(all_play.items(),
               key=lambda x: (x[1]['w'], x[1]['cat_w']),
               reverse=True)
    )


# ── CUMULATIVE POWER RANKINGS ─────────────────────────────────────────────────

def update_power_rankings(week: int, all_play: dict, save_snapshot: bool = True) -> dict:
    """Merge this week's all-play data into the cumulative power-rankings.json.

    Loads data/power-rankings.json (or seeds it fresh), appends this week's
    all-play record to each team's history, re-sorts by cumulative cat_w,
    computes rank deltas, assigns tiers, and saves back to disk.

    Idempotent: if last_updated_week >= week, returns existing data unchanged.

    Returns the updated rankings dict (same shape as power-rankings.json).
    """
    TIERS = {1: 'elite', 2: 'elite', 3: 'contender', 4: 'contender',
             5: 'contender', 6: 'mid', 7: 'mid', 8: 'mid',
             9: 'cellar', 10: 'cellar'}

    pr_path = BASE_DIR / 'data' / 'power-rankings.json'

    if pr_path.exists():
        pr = json.loads(pr_path.read_text())
    else:
        pr = {'last_updated_week': 0, 'methodology': '', 'rankings': []}

    if pr.get('last_updated_week', 0) >= week:
        print(f'  ℹ️  Power rankings already updated through Week {week} — skipping')
        return pr

    # Build a lookup keyed by team name from existing rankings
    by_name = {r['name']: r for r in pr.get('rankings', [])}

    # Merge this week's all-play into each team's record
    for name, ap in all_play.items():
        if name not in by_name:
            # First time we've seen this team (fresh file or new team)
            by_name[name] = {
                'name': name,
                'rank': 0, 'prev_rank': 0, 'delta': 0, 'tier': 'mid',
                'cumulative_ap':   {'w': 0, 'l': 0, 't': 0},
                'cumulative_cats': {'w': 0, 'l': 0, 't': 0},
                'history': [],
                'analysis': '',
            }
        entry = by_name[name]

        # Snapshot prev rank before we re-sort
        entry['prev_rank'] = entry.get('rank', 0)

        # Accumulate
        entry['cumulative_ap']['w']   += ap['w']
        entry['cumulative_ap']['l']   += ap['l']
        entry['cumulative_ap']['t']   += ap.get('t', 0)
        entry['cumulative_cats']['w'] += ap['cat_w']
        entry['cumulative_cats']['l'] += ap['cat_l']
        entry['cumulative_cats']['t'] += ap.get('cat_t', 0)

        # Append weekly snapshot
        entry['history'].append({
            'week': week,
            'rank': 0,  # filled in after re-sort below
            'ap':   {'w': ap['w'], 'l': ap['l'], 't': ap.get('t', 0)},
            'cats': {'w': ap['cat_w'], 'l': ap['cat_l'], 't': ap.get('cat_t', 0)},
        })

    # Compute recency-weighted score for each team.
    # Decay factor 0.95 per week back: most recent week = 1.0x, one week ago = 0.95x,
    # two weeks ago = 0.90x, etc.  At a full 25-week season week 1 still counts ~29%
    # as much as the current week — enough history still matters, enough to reward
    # teams that are actually improving right now.
    DECAY = 0.95
    for entry in by_name.values():
        score = 0.0
        for i, h in enumerate(reversed(entry['history'])):
            score += h['cats']['w'] * (DECAY ** i)
        entry['weighted_score'] = round(score, 2)

    # Sort by weighted_score desc; cumulative AP wins as tiebreaker
    ranked = sorted(by_name.values(),
                    key=lambda x: (x['weighted_score'], x['cumulative_ap']['w']),
                    reverse=True)

    # Assign ranks, deltas, tiers, and fill in this week's rank in history
    for i, entry in enumerate(ranked):
        new_rank = i + 1
        entry['rank']  = new_rank
        entry['delta'] = entry['prev_rank'] - new_rank  # positive = moved up
        entry['tier']  = TIERS.get(new_rank, 'mid')
        # Backfill the rank into the week snapshot we just appended
        if entry['history']:
            entry['history'][-1]['rank'] = new_rank

    # Save a weekly snapshot so power.html can show historical views.
    # Only saved when save_snapshot=True (i.e. the scoreboard is postevent).
    # Preview-week dumps skip snapshot creation so partial data never appears
    # as a historical tab.
    pr.setdefault('weekly_snapshots', [])
    if save_snapshot and not any(s['week'] == week for s in pr['weekly_snapshots']):
        snap_entries = []
        for e in ranked:
            last_h = e['history'][-1] if e['history'] else {}
            snap_entries.append({
                'rank':            e['rank'],
                'prev_rank':       e['prev_rank'],
                'delta':           e['delta'],
                'tier':            e['tier'],
                'name':            e['name'],
                'cumulative_ap':   dict(e['cumulative_ap']),
                'cumulative_cats': dict(e['cumulative_cats']),
                'week_ap':         dict(last_h.get('ap',   {'w':0,'l':0,'t':0})),
                'week_cats':       dict(last_h.get('cats', {'w':0,'l':0,'t':0})),
                'analysis':        e.get('analysis', ''),
            })
        pr['weekly_snapshots'].append({'week': week, 'rankings': snap_entries})

    pr['last_updated_week'] = week
    pr['methodology'] = (
        'Ranked by recency-weighted category wins (decay=0.95/week). '
        'Most recent week counts full value; each prior week counts 5% less. '
        'At 25 weeks, week 1 still counts ~29% of current — history matters, '
        'but teams playing well right now get the edge. '
        'Cumulative AP wins used as tiebreaker.'
    )
    pr['rankings'] = ranked
    pr_path.write_text(json.dumps(pr, indent=2))
    print(f'  📊  Power rankings updated through Week {week} → {pr_path.name}')
    return pr


def generate_power_rankings_page(pr: dict):
    """Regenerate power.html from the current power-rankings.json data.

    Rewrites the AUTO-delimited sections in power.html so the page stays
    in sync with the JSON without a full rebuild each time.

    Sections updated:
      AUTO:PR_UPDATED_START / END  — "Updated through Week N" badge
      AUTO:PR_STRIP_START / END    — Season snapshot stat strip
      AUTO:PR_RANKINGS_START / END — The full ranked list HTML
      AUTO:PR_WEEK_LINKS_START / END — Bottom weekly breakdown links
    """
    power_path = BASE_DIR / 'power.html'
    if not power_path.exists():
        print('  ⚠️  power.html not found — skipping page regeneration')
        return

    last_week = pr.get('last_updated_week', 0)
    rankings  = pr.get('rankings', [])

    # ── Updated-through badge ──────────────────────────────────────────────
    updated_html = f'    <div class="pr-updated-badge">Updated through Week {last_week}</div>\n    '

    # ── Season stat strip ──────────────────────────────────────────────────
    leader    = rankings[0]['name'] if rankings else 'TBD'
    leader_cats = rankings[0]['cumulative_cats'] if rankings else {'w': 0, 'l': 0, 't': 0}
    leader_str  = f"{leader_cats['w']}&ndash;{leader_cats['l']}&ndash;{leader_cats['t']}"
    # Biggest riser and faller (by delta, excluding teams with prev_rank=0)
    movers = [r for r in rankings if r.get('prev_rank', 0) > 0]
    riser  = max(movers, key=lambda x: x.get('delta', 0), default=None) if movers else None
    faller = min(movers, key=lambda x: x.get('delta', 0), default=None) if movers else None
    strip_html = f'''  <div class="pr-season-strip">
    <div class="pr-season-cell">
      <div class="pr-season-val gold">{leader}</div>
      <div class="pr-season-lbl">#1 overall</div>
    </div>
    <div class="pr-season-cell">
      <div class="pr-season-val">{leader_str}</div>
      <div class="pr-season-lbl">Leader season cats</div>
    </div>
    <div class="pr-season-cell">
      <div class="pr-season-val green">{riser['name'] if riser and riser.get('delta',0) > 0 else '&mdash;'}</div>
      <div class="pr-season-lbl">Biggest riser ({'+' + str(riser['delta']) if riser and riser.get('delta',0) > 0 else '&mdash;'})</div>
    </div>
    <div class="pr-season-cell">
      <div class="pr-season-val red">{faller['name'] if faller and faller.get('delta',0) < 0 else '&mdash;'}</div>
      <div class="pr-season-lbl">Biggest faller ({str(faller['delta']) if faller and faller.get('delta',0) < 0 else '&mdash;'})</div>
    </div>
  </div>'''

    # ── Rankings rows ──────────────────────────────────────────────────────
    TIER_LABELS = {
        'elite':     '<div class="pr-tier-label pr-tier-elite reveal"><span class="pr-tier-dot"></span> Elite Tier</div>',
        'contender': '<div class="pr-tier-label pr-tier-contender reveal"><span class="pr-tier-dot"></span> Contenders</div>',
        'mid':       '<div class="pr-tier-label pr-tier-mid reveal"><span class="pr-tier-dot"></span> Middle of the Pack</div>',
        'cellar':    '<div class="pr-tier-label pr-tier-cellar reveal"><span class="pr-tier-dot"></span> Cellar Dwellers</div>',
    }
    BAR_WIDTHS = {1:100,2:82,3:77,4:75,5:70,6:68,7:52,8:51,9:42,10:33}
    DELAYS     = {1:.05,2:.1,3:.15,4:.2,5:.25,6:.3,7:.35,8:.4,9:.45,10:.5}

    rows_html  = ['    <div class="power-rankings-container">']
    prev_tier  = None
    for entry in rankings:
        rank      = entry['rank']
        tier      = entry['tier']
        name      = entry.get('name', '')
        delta     = entry.get('delta', 0)
        prev_rank = entry.get('prev_rank', 0)
        cum_ap    = entry['cumulative_ap']
        cum_cats  = entry['cumulative_cats']
        analysis  = entry.get('analysis', '')
        history   = entry.get('history', [])

        if tier != prev_tier:
            rows_html.append('')
            rows_html.append(f'      {TIER_LABELS.get(tier, "")}')
            prev_tier = tier

        # Delta badge
        if delta > 0:
            delta_html = f'<span class="pr-delta up">&#8593;{delta}</span>'
        elif delta < 0:
            delta_html = f'<span class="pr-delta down">&#8595;{abs(delta)}</span>'
        elif prev_rank == 0:
            delta_html = '<span class="pr-delta new">NEW</span>'
        else:
            delta_html = '<span class="pr-delta even">&mdash;</span>'

        # Movement line item — explicit rank change sentence
        held_weeks = sum(1 for h in history if h.get('rank') == rank)
        if prev_rank == 0:
            move_cls  = 'new'
            move_text = 'First week in the books'
        elif delta > 0:
            move_cls  = 'up'
            move_text = f'&#8593;{delta} &mdash; climbed from #{prev_rank} last week'
        elif delta < 0:
            move_cls  = 'down'
            move_text = f'&#8595;{abs(delta)} &mdash; dropped from #{prev_rank} last week'
        elif held_weeks > 1:
            move_cls  = 'hold'
            move_text = f'Held at #{rank} for {held_weeks} straight weeks'
        else:
            move_cls  = 'hold'
            move_text = f'Held at #{rank}'
        movement_html = f'          <div class="pr-movement {move_cls}">{move_text}</div>'

        # Week history pills
        history_parts = []
        for i, hw in enumerate(history):
            wk_rank = hw.get('rank', 0)
            wk_num  = hw.get('week', i + 1)
            history_parts.append(
                f'            <div class="pr-history-week">'
                f'<span class="pr-hw-label">Wk {wk_num}</span>'
                f'<span class="pr-hw-rank" data-rank="{wk_rank}">#{wk_rank}</span>'
                f'</div>'
            )
            if i < len(history) - 1:
                history_parts.append('            <span class="pr-history-arrow">&#8594;</span>')
        history_html = '\n'.join(history_parts)

        ap_str   = f"{cum_ap['w']}&ndash;{cum_ap['l']}&ndash;{cum_ap['t']}"
        cats_str = f"{cum_cats['w']}&ndash;{cum_cats['l']}&ndash;{cum_cats['t']}"
        bar_w    = BAR_WIDTHS.get(rank, 30)
        delay    = DELAYS.get(rank, .5)

        row = f'''
      <div class="pr-row reveal" data-rank="{rank}" data-tier="{tier}" style="transition-delay:{delay}s;--bar-w:{bar_w}%">
        <div class="pr-rank">{rank}</div>
        <div class="pr-content">
          <div class="pr-header">
            <span class="pr-team-name">{name}</span>
            <span class="pr-record-badge">{cats_str} cats</span>
            <span class="pr-cats-badge">{ap_str} AP</span>
            {delta_html}
          </div>
{movement_html}
          <div class="pr-history">
{history_html}
          </div>
          <div class="pr-bar-container"><div class="pr-bar-fill"></div></div>
          <div class="pr-analysis">{analysis}</div>
        </div>
      </div>'''
        rows_html.append(row)

    rows_html.append('')
    rows_html.append('    </div>')
    rankings_html = '\n'.join(rows_html)

    # ── Week links ─────────────────────────────────────────────────────────
    week_link_parts = []
    for wk in range(1, last_week + 1):
        dates = WEEK_DATES.get(wk, ('', ''))
        start = fmt_date(dates[0]) if dates[0] else f'Week {wk}'
        end   = fmt_date(dates[1]) if dates[1] else ''
        label = f'{start}&ndash;{end}' if end else start
        week_link_parts.append(
            f'      <a href="week-{wk:02d}.html#recap" style="display:inline-flex;align-items:center;gap:.4rem;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:.55rem 1rem;font-size:.82rem;font-weight:600;color:var(--text-secondary);text-decoration:none;">\n'
            f'        <span style="color:var(--muted);font-size:.72rem;">Wk {wk}</span>\n'
            f'        <span>{label}</span>\n'
            f'        <span style="color:var(--accent);font-size:.72rem;">View &#8594;</span>\n'
            f'      </a>'
        )
    week_links_html = '\n'.join(week_link_parts)

    # ── Update week-dropdown in nav (mirror of other pages) ───────────────
    # Build week nav group entries matching the site's existing format.
    # Completed weeks (1..last_week) get Preview + Recap links.
    # The active/current playing week is last_week + 1 — it gets Preview only.
    # We only include the preview week if its HTML file exists on disk.
    active_week = last_week + 1
    active_week_exists = (BASE_DIR / f'week-{active_week:02d}.html').exists()
    max_week = active_week if active_week_exists else last_week
    week_nav_items = []
    for wk in range(1, max_week + 1):
        dates  = WEEK_DATES.get(wk, ('', ''))
        start  = fmt_date(dates[0]) if dates[0] else ''
        end    = fmt_date(dates[1]) if dates[1] else ''
        label  = f'{start}&ndash;{end}'
        active_cls = ' active' if wk == active_week else ''
        sub_links = f'<a href="week-{wk:02d}.html#preview">Preview</a>'
        if wk <= last_week:
            # Completed week — has a recap
            sub_links += f'<a href="week-{wk:02d}.html#recap">Recap</a>'
        week_nav_items.append(
            f'        <div class="week-nav-group"><span class="week-nav-label{active_cls}">Week {wk} &mdash; {label}</span>'
            f'<div class="week-nav-sub">{sub_links}</div></div>'
        )
    week_nav_html = '\n'.join(week_nav_items)

    # ── Inject all sections using AUTO markers ─────────────────────────────
    html = power_path.read_text()

    def _replace(content, start_marker, end_marker, new_inner):
        pattern = re.compile(
            r'(<!--\s*' + re.escape(start_marker) + r'\s*-->).*?(<!--\s*' + re.escape(end_marker) + r'\s*-->)',
            re.DOTALL
        )
        # Use a callable to avoid re.sub misinterpreting \2 or backslashes in new_inner
        def _sub(m):
            return m.group(1) + '\n' + new_inner + '\n    ' + m.group(2)
        return pattern.sub(_sub, content)

    # ── Week selector buttons ──────────────────────────────────────────────
    btn_parts = ['      <button class="pr-week-btn active" data-week="-1" onclick="prSwitchView(-1)">Current</button>']
    for s in pr.get('weekly_snapshots', []):
        wk = s['week']
        btn_parts.append(f'      <button class="pr-week-btn" data-week="{wk}" onclick="prSwitchView({wk})">Wk {wk}</button>')
    selector_html = '\n'.join(btn_parts)

    # ── Snapshots JSON for JS renderer ────────────────────────────────────
    import json as _json
    snapshots_js_html = (
        f'<script id="pr-snapshots-data" type="application/json">'
        f'{_json.dumps(pr.get("weekly_snapshots", []))}'
        f'</script>'
    )

    html = _replace(html, 'AUTO:PR_UPDATED_START', 'AUTO:PR_UPDATED_END', f'    {updated_html}')
    html = _replace(html, 'AUTO:PR_STRIP_START', 'AUTO:PR_STRIP_END', strip_html)
    html = _replace(html, 'AUTO:PR_WEEK_SELECTOR_START', 'AUTO:PR_WEEK_SELECTOR_END', selector_html)
    html = _replace(html, 'AUTO:PR_RANKINGS_START', 'AUTO:PR_RANKINGS_END', rankings_html)
    html = _replace(html, 'AUTO:PR_WEEK_LINKS_START', 'AUTO:PR_WEEK_LINKS_END', week_links_html)
    html = _replace(html, 'AUTO:PR_SNAPSHOTS_START', 'AUTO:PR_SNAPSHOTS_END', snapshots_js_html)
    # Top-of-page Weeks dropdown nav (mirror of every other page's nav).
    # This was previously skipped, which is why power.html's Weeks menu
    # never picked up new weeks until manually edited.
    html = _replace(html, 'AUTO:WEEK_LINKS_START', 'AUTO:WEEK_LINKS_END', week_nav_html)

    power_path.write_text(html)
    print(f'  ✅  power.html regenerated → Week {last_week}')


# ── ROTO STANDINGS (fantasy-of-a-fantasy roto view) ──────────────────────────

ROTO_CATS        = ['R', 'HR', 'RBI', 'SB', 'OBP', 'K', 'QS', 'SV', 'ERA', 'WHIP']
ROTO_COUNTING    = {'R', 'HR', 'RBI', 'SB', 'K', 'QS', 'SV'}
ROTO_RATE        = {'OBP', 'ERA', 'WHIP'}
ROTO_LOW_IS_GOOD = {'ERA', 'WHIP'}


def _roto_assign_points(pairs, low_is_good):
    """Given [(team_key, value), ...], return {team_key: points} with
    standard rotisserie scoring: best gets N points, worst gets 1,
    ties share the average of their tied positions.
    """
    n = len(pairs)
    # Sort so that "worst" is first and "best" is last.
    # For high-is-good cats: ascending puts low (worst) first.
    # For low-is-good cats:  descending puts high (worst) first.
    pairs_sorted = sorted(pairs, key=lambda p: p[1], reverse=low_is_good)
    out = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and pairs_sorted[j + 1][1] == pairs_sorted[i][1]:
            j += 1
        # Positions i..j (0-indexed) map to point values (i+1)..(j+1)
        group_points = list(range(i + 1, j + 2))
        avg = sum(group_points) / len(group_points)
        for k in range(i, j + 1):
            out[pairs_sorted[k][0]] = avg
        i = j + 1
    return out


def compute_roto_standings(history_by_team: dict, n_teams: int = 10) -> list:
    """Given season-to-date weekly stat history, compute rotisserie standings.

    history_by_team shape:
      { team_key: { 'name': str,
                    'weeks': [ {'week': n, 'cats': {R: 17, HR: 6, ...}}, ... ] } }

    Counting cats (R, HR, RBI, SB, K, QS, SV) are summed across weeks.
    Rate cats (OBP, ERA, WHIP) use the average of weekly values — we do not
    have access to raw components (AB, IP, ER, H+BB) to weight by volume,
    so this averages weekly rate performance.

    Returns a list of standings entries, sorted by total roto points desc:
      [{team_key, name, totals, roto_points, total_points, rank}, ...]
    """
    # Aggregate per-team totals
    team_totals = {}
    for tk, tdata in history_by_team.items():
        tot_counting = {c: 0.0 for c in ROTO_COUNTING}
        rate_samples = {c: [] for c in ROTO_RATE}
        for wk in tdata.get('weeks', []):
            cats = wk.get('cats', {})
            for c in ROTO_COUNTING:
                try:
                    tot_counting[c] += float(cats.get(c, 0) or 0)
                except (TypeError, ValueError):
                    pass
            for c in ROTO_RATE:
                v = cats.get(c)
                if v in (None, '-', ''):
                    continue
                try:
                    tot_counting  # unused
                    fv = float(v)
                    rate_samples[c].append(fv)
                except (TypeError, ValueError):
                    pass
        totals = {}
        for c in ROTO_COUNTING:
            totals[c] = round(tot_counting[c], 1)
        for c in ROTO_RATE:
            samples = rate_samples[c]
            if samples:
                totals[c] = round(sum(samples) / len(samples), 3)
            else:
                # No data: give them the "worst" placeholder so they rank last
                totals[c] = 99.99 if c in ROTO_LOW_IS_GOOD else 0.0
        team_totals[tk] = {'name': tdata.get('name', ''), 'totals': totals}

    # Rank each category and assign roto points
    roto_points = {tk: {} for tk in team_totals}
    for cat in ROTO_CATS:
        pairs = [(tk, team_totals[tk]['totals'].get(cat, 0.0)) for tk in team_totals]
        pts = _roto_assign_points(pairs, low_is_good=(cat in ROTO_LOW_IS_GOOD))
        for tk, p in pts.items():
            roto_points[tk][cat] = round(p, 1)

    # Build standings list
    standings = []
    for tk, data in team_totals.items():
        pts = roto_points[tk]
        total = sum(pts.values())
        standings.append({
            'team_key':      tk,
            'name':          data['name'],
            'totals':        data['totals'],
            'roto_points':   pts,
            'total_points':  round(total, 1),
        })

    # Sort by total_points desc; tiebreak: more #1 category finishes
    def _tiebreak(entry):
        max_pts = n_teams
        firsts = sum(1 for p in entry['roto_points'].values() if p >= max_pts - 0.01)
        return (entry['total_points'], firsts)

    standings.sort(key=_tiebreak, reverse=True)
    for i, s in enumerate(standings):
        s['rank'] = i + 1
    return standings


def update_roto_standings(week: int, matchups: list, save_snapshot: bool = True) -> dict:
    """Merge a week's scoreboard cats into data/roto-standings.json and re-rank.

    Appends each team's weekly cat line to their history, recomputes
    rotisserie points, saves prev_rank/delta, and writes the file.

    Idempotent: if last_updated_week >= week, returns unchanged data.
    """
    roto_path = BASE_DIR / 'data' / 'roto-standings.json'

    if roto_path.exists():
        roto = json.loads(roto_path.read_text())
    else:
        roto = {
            'last_updated_week': 0,
            'weeks_played':      0,
            'methodology':       '',
            'history_by_team':   {},
            'standings':         [],
        }

    if roto.get('last_updated_week', 0) >= week:
        print(f'  ℹ️  Roto standings already updated through Week {week} — skipping')
        return roto

    history = roto.setdefault('history_by_team', {})

    # Build prev_rank lookup before we re-sort
    prev_ranks = {s['team_key']: s.get('rank', 0) for s in roto.get('standings', [])}

    # Append this week's cats per team
    for m in matchups:
        for tk in ('t0', 't1'):
            t        = m[tk]
            team_key = t.get('team_key', '')
            name     = t.get('name', '')
            cats     = t.get('cats') or {}
            if not team_key or not cats:
                continue
            entry = history.setdefault(team_key, {'name': name, 'weeks': []})
            entry['name'] = name  # keep current name
            # Skip if we already have this week
            if any(w.get('week') == week for w in entry['weeks']):
                continue
            entry['weeks'].append({'week': week, 'cats': cats})

    # Recompute standings
    standings = compute_roto_standings(history)

    # Preserve analysis blurbs that already exist, keyed by team_key
    prev_analysis = {s['team_key']: s.get('analysis', '') for s in roto.get('standings', [])}
    for s in standings:
        s['prev_rank'] = prev_ranks.get(s['team_key'], 0)
        s['delta']     = s['prev_rank'] - s['rank'] if s['prev_rank'] else 0
        s['analysis']  = prev_analysis.get(s['team_key'], '')

    # Save weekly snapshot
    roto.setdefault('weekly_snapshots', [])
    if save_snapshot and not any(snap['week'] == week for snap in roto['weekly_snapshots']):
        roto['weekly_snapshots'].append({
            'week':     week,
            'rankings': [
                {'rank': s['rank'], 'team_key': s['team_key'], 'name': s['name'],
                 'total_points': s['total_points']}
                for s in standings
            ]
        })

    roto['last_updated_week'] = week
    weeks_played = max((len(v.get('weeks', [])) for v in history.values()), default=0)
    roto['weeks_played']      = weeks_played
    roto['methodology']       = (
        'Standard 10-category rotisserie scoring. Each category is ranked 1-10 '
        'across the league — best in category gets 10 points, worst gets 1, ties '
        'share the average of their tied positions. For ERA and WHIP the order '
        'is inverted (lower is better). Counting stats (R, HR, RBI, SB, K, QS, SV) '
        'are summed across every completed week. Rate stats (OBP, ERA, WHIP) are '
        'the average of each team\'s weekly rate values. Not weighted by at-bats '
        'or innings, because your league doesn\'t actually play roto. This whole '
        'page is a hypothetical.'
    )
    roto['standings'] = standings

    roto_path.write_text(json.dumps(roto, indent=2))
    print(f'  📊  Roto standings updated through Week {week} → {roto_path.name}')
    return roto


def generate_roto_page(roto: dict):
    """Regenerate roto.html from the current data/roto-standings.json.

    Sections updated (all delimited by AUTO comments):
      AUTO:ROTO_UPDATED  — "Updated through Week N" badge
      AUTO:ROTO_STRIP    — Top/bottom/strongest-cat snapshot
      AUTO:ROTO_TABLE    — The full standings table
      AUTO:ROTO_BLURBS   — Per-team short blurbs
      AUTO:WEEK_LINKS    — Shared week dropdown (mirrors other pages)
      AUTO:NAV_BADGE     — Shared nav badge
    """
    roto_path = BASE_DIR / 'roto.html'
    if not roto_path.exists():
        print('  ⚠️  roto.html not found — skipping page regeneration')
        return

    last_week    = roto.get('last_updated_week', 0)
    weeks_played = roto.get('weeks_played', 0)
    standings    = roto.get('standings', [])

    # ── Updated badge ─────────────────────────────────────────────────────
    updated_html = f'    <div class="roto-updated-badge">Updated through Week {last_week}</div>'

    # ── Snapshot strip ────────────────────────────────────────────────────
    leader   = standings[0] if standings else {'name': 'TBD', 'total_points': 0}
    cellar   = standings[-1] if standings else {'name': 'TBD', 'total_points': 0}
    # Biggest riser / faller by delta
    movers   = [s for s in standings if s.get('prev_rank', 0) > 0]
    riser    = max(movers, key=lambda x: x.get('delta', 0), default=None) if movers else None
    faller   = min(movers, key=lambda x: x.get('delta', 0), default=None) if movers else None
    strip_html = f'''  <div class="roto-season-strip">
    <div class="roto-season-cell">
      <div class="roto-season-val gold">{leader['name']}</div>
      <div class="roto-season-lbl">Hypothetical #1 &middot; {leader['total_points']} pts</div>
    </div>
    <div class="roto-season-cell">
      <div class="roto-season-val">{weeks_played}</div>
      <div class="roto-season-lbl">Weeks counted</div>
    </div>
    <div class="roto-season-cell">
      <div class="roto-season-val green">{riser['name'] if riser and riser.get('delta',0) > 0 else '&mdash;'}</div>
      <div class="roto-season-lbl">Biggest riser ({'+' + str(riser['delta']) if riser and riser.get('delta',0) > 0 else '&mdash;'})</div>
    </div>
    <div class="roto-season-cell">
      <div class="roto-season-val red">{cellar['name']}</div>
      <div class="roto-season-lbl">Hypothetical last &middot; {cellar['total_points']} pts</div>
    </div>
  </div>'''

    # ── Standings table ──────────────────────────────────────────────────
    def _fmt(val, cat):
        if cat == 'OBP':
            try: return f'{float(val):.3f}'.lstrip('0')
            except Exception: return str(val)
        if cat in ('ERA', 'WHIP'):
            try: return f'{float(val):.2f}'
            except Exception: return str(val)
        try: return str(int(round(float(val))))
        except Exception: return str(val)

    def _fmt_pts(p):
        # Show .5 for ties, otherwise integer
        if abs(p - round(p)) < 0.01:
            return str(int(round(p)))
        return f'{p:.1f}'

    table_rows = []
    for s in standings:
        rank  = s['rank']
        name  = s['name']
        total = s['total_points']
        delta = s.get('delta', 0)
        prev  = s.get('prev_rank', 0)

        if prev == 0:
            delta_cell = '<span class="roto-delta new">NEW</span>'
        elif delta > 0:
            delta_cell = f'<span class="roto-delta up">&#8593;{delta}</span>'
        elif delta < 0:
            delta_cell = f'<span class="roto-delta down">&#8595;{abs(delta)}</span>'
        else:
            delta_cell = '<span class="roto-delta even">&mdash;</span>'

        cat_cells = []
        for cat in ROTO_CATS:
            val = s['totals'].get(cat, 0)
            pts = s['roto_points'].get(cat, 0)
            max_pts = len(standings) or 10
            # Color: 1 = worst (red), N = best (green)
            pct = (pts - 1) / max(max_pts - 1, 1)
            if pts >= max_pts - 0.01:
                cell_class = 'roto-cat-cell roto-cell-best'
            elif pts <= 1.01:
                cell_class = 'roto-cat-cell roto-cell-worst'
            elif pct >= 0.66:
                cell_class = 'roto-cat-cell roto-cell-good'
            elif pct <= 0.33:
                cell_class = 'roto-cat-cell roto-cell-bad'
            else:
                cell_class = 'roto-cat-cell roto-cell-mid'
            cat_cells.append(
                f'<td class="{cell_class}">'
                f'<div class="roto-cat-val">{_fmt(val, cat)}</div>'
                f'<div class="roto-cat-pts">{_fmt_pts(pts)}</div>'
                f'</td>'
            )

        row = (
            f'      <tr class="roto-row reveal" data-rank="{rank}">\n'
            f'        <td class="roto-rank-cell">{rank}</td>\n'
            f'        <td class="roto-team-cell"><span class="team-label">{name}</span></td>\n'
            f'        <td class="roto-total-cell"><strong>{_fmt_pts(total)}</strong></td>\n'
            f'        <td class="roto-delta-cell">{delta_cell}</td>\n'
            + ''.join(f'        {c}\n' for c in cat_cells)
            + f'      </tr>'
        )
        table_rows.append(row)

    table_html = '\n'.join(table_rows)

    # ── Team blurbs ──────────────────────────────────────────────────────
    blurb_items = []
    for s in standings:
        blurb = s.get('analysis', '') or '<em class="muted">Blurb pending &mdash; Claude will write this on Sunday.</em>'
        blurb_items.append(
            f'      <div class="roto-blurb reveal">\n'
            f'        <div class="roto-blurb-head">\n'
            f'          <span class="roto-blurb-rank">#{s["rank"]}</span>\n'
            f'          <span class="roto-blurb-team team-label">{s["name"]}</span>\n'
            f'          <span class="roto-blurb-pts">{_fmt_pts(s["total_points"])} pts</span>\n'
            f'        </div>\n'
            f'        <div class="roto-blurb-body">{blurb}</div>\n'
            f'      </div>'
        )
    blurbs_html = '\n'.join(blurb_items)

    # ── Week dropdown + nav badge (shared with other pages) ─────────────
    week_nav_items = []
    for wk in range(1, last_week + 1):
        dates = WEEK_DATES.get(wk, ('', ''))
        start = fmt_date(dates[0]) if dates[0] else ''
        end   = fmt_date(dates[1]) if dates[1] else ''
        label = f'{start}&ndash;{end}'
        sub   = f'<a href="week-{wk:02d}.html#preview">Preview</a><a href="week-{wk:02d}.html#recap">Recap</a>'
        week_nav_items.append(
            f'        <div class="week-nav-group"><span class="week-nav-label">Week {wk} &mdash; {label}</span>'
            f'<div class="week-nav-sub">{sub}</div></div>'
        )
    week_links_html = '\n'.join(week_nav_items)

    nav_badge_html = f'  <div class="nav-badge">Week {last_week}</div>'

    # ── Inject all sections ──────────────────────────────────────────────
    html = roto_path.read_text()

    def _replace(content, start_marker, end_marker, new_inner):
        pattern = re.compile(
            r'(<!--\s*' + re.escape(start_marker) + r'\s*-->).*?(<!--\s*' + re.escape(end_marker) + r'\s*-->)',
            re.DOTALL
        )
        def _sub(m):
            return m.group(1) + '\n' + new_inner + '\n    ' + m.group(2)
        return pattern.sub(_sub, content)

    html = _replace(html, 'AUTO:ROTO_UPDATED_START', 'AUTO:ROTO_UPDATED_END', updated_html)
    html = _replace(html, 'AUTO:ROTO_STRIP_START',   'AUTO:ROTO_STRIP_END',   strip_html)
    html = _replace(html, 'AUTO:ROTO_TABLE_START',   'AUTO:ROTO_TABLE_END',   table_html)
    html = _replace(html, 'AUTO:ROTO_BLURBS_START',  'AUTO:ROTO_BLURBS_END',  blurbs_html)
    html = _replace(html, 'AUTO:WEEK_LINKS_START',   'AUTO:WEEK_LINKS_END',   week_links_html)
    html = _replace(html, 'AUTO:NAV_BADGE_START',    'AUTO:NAV_BADGE_END',    nav_badge_html)

    roto_path.write_text(html)
    print(f'  ✅  roto.html regenerated → Week {last_week}')


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

    # ── Cumulative power rankings (season-to-date) ────────────────────────────
    # Only update (and save a snapshot) when the week's scoreboard is fully
    # finalized. Yahoo signals this via matchup status = 'postevent'.
    # If any matchup is still in-progress or pre-event (e.g. this is a preview
    # dump for next week), we skip the snapshot entirely so partial data never
    # appears as a historical week tab on power.html.
    try:
        statuses  = [m.get('status', '') for m in matchups_data]
        is_final  = statuses and all(s == 'postevent' for s in statuses)
        pr_data   = update_power_rankings(week, all_play, save_snapshot=is_final)
        generate_power_rankings_page(pr_data)
        if not is_final:
            print(f'  ℹ️  Week {week} scoreboard not final — power rankings updated but no snapshot saved')
    except Exception as e:
        print(f'    ⚠️  Power rankings update failed: {e}')

    # ── Rotisserie standings (fantasy-of-a-fantasy view) ──────────────────────
    # Same gating as power rankings: only accumulate the week if the scoreboard
    # is fully finalized. Writes data/roto-standings.json and rebuilds roto.html.
    try:
        statuses_r = [m.get('status', '') for m in matchups_data]
        is_final_r = statuses_r and all(s == 'postevent' for s in statuses_r)
        if is_final_r:
            roto_data = update_roto_standings(week, matchups_data, save_snapshot=True)
            generate_roto_page(roto_data)
        else:
            print(f'  ℹ️  Week {week} scoreboard not final — skipping roto standings update')
    except Exception as e:
        print(f'    ⚠️  Roto standings update failed: {e}')

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
    return f'''  <section class="section" id="preview">
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
    <div class="nav-dropdown">
      <a href="#" class="nav-dropdown-toggle">Teams &#9662;</a>
      <div class="nav-dropdown-menu">
        <a href="teams/busch-latte.html">Busch Latte</a>
        <a href="teams/skenes.html">Allahu Alvarez</a>
        <a href="teams/ete-crow.html">Ete Crow</a>
        <a href="teams/ragans.html">The Ragans Administration</a>
        <a href="teams/keanu.html">Keanu Reeves</a>
        <a href="teams/good-vibes.html">Good Vibes Only</a>
        <a href="teams/rain-city.html">Rain City Bombers</a>
        <a href="teams/buckner.html">The Buckner Boots</a>
        <a href="teams/decoy.html">Ray Donovan</a>
        <a href="teams/one-ball.html">One Ball Two Strikes</a>
      </div>
    </div>
    <div class="nav-dropdown">
      <a href="week-{week:02d}.html" class="nav-dropdown-toggle active">Weeks &#9662;</a>
      <div class="nav-dropdown-menu" id="weekDropdown">
        <!-- AUTO:WEEK_LINKS_START -->
        <div class="week-nav-group"><span class="week-nav-label active">Week {week} &mdash; {date_str}</span><div class="week-nav-sub"><a href="week-{week:02d}.html#preview">Preview</a></div></div>
        <!-- AUTO:WEEK_LINKS_END -->
      </div>
    </div>
    <div class="nav-sep"></div>
    <a href="power.html" class="nav-pr-link">Power Rankings</a>
    <div class="nav-sep"></div>
    <div class="nav-dropdown">
      <a href="draft.html" class="nav-dropdown-toggle">Draft &#9662;</a>
      <div class="nav-dropdown-menu">
        <a href="draft.html">Full Draft Report</a>
        <a href="draft.html#grades">Draft Grades</a>
        <a href="draft.html#predictions">Predictions</a>
        <a href="draft.html#insights">Insights</a>
        <a href="draft.html#standings">2025 Recap</a>
      </div>
    </div>
  </div>
  <div class="nav-badge week-badge">Week {week}</div>
</nav>
<script src="nav.js"></script>

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

<script src="nav.js"></script>
<script>
// Highlight Preview/Recap nav sub-links based on URL hash
(function() {{
  var page = window.location.pathname.split('/').pop() || '';
  var hash = window.location.hash || '#preview';
  var target = page + hash;
  document.querySelectorAll('.week-nav-sub a, .week-sheet-sub-link').forEach(function(a) {{
    var href = (a.getAttribute('href') || '').replace(/^\.\//, '');
    if (href === target) a.classList.add('active');
  }});
}})();

const obs = new IntersectionObserver(entries => entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add('visible'); }}), {{threshold:.06}});
document.querySelectorAll('.reveal').forEach(el => obs.observe(el));
</script>

<nav class="bottom-nav" aria-label="Mobile navigation">
  <div class="bottom-nav-inner">
    <a href="index.html" class="bottom-nav-item">
      <svg class="bottom-nav-icon" viewBox="0 0 24 24"><path d="M3 9.5L12 3l9 6.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9.5z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
      <span>Home</span>
    </a>
    <a href="#" class="bottom-nav-item active" id="weeks-nav-btn">
      <svg class="bottom-nav-icon" viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
      <span>Weeks</span>
    </a>
    <a href="draft.html" class="bottom-nav-item">
      <svg class="bottom-nav-icon" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
      <span>Draft</span>
    </a>
    <a href="#" class="bottom-nav-item" id="teams-nav-btn">
      <svg class="bottom-nav-icon" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
      <span>Teams</span>
    </a>
  </div>
</nav>

<!-- Teams bottom sheet (mobile) -->
<div class="teams-sheet" id="teamsSheet">
  <div class="teams-sheet-backdrop" id="teamsSheetBackdrop"></div>
  <div class="teams-sheet-panel">
    <div class="teams-sheet-handle"></div>
    <div class="teams-sheet-title">Teams</div>
    <div class="teams-sheet-list">
      <a href="teams/busch-latte.html" class="teams-sheet-item"><img src="img/headshots/busch-latte.jpg" class="headshot headshot-sm" alt="" /> Busch Latte</a>
      <a href="teams/skenes.html" class="teams-sheet-item"><img src="img/headshots/skenes.jpeg" class="headshot headshot-sm" alt="" /> Allahu Alvarez</a>
      <a href="teams/ete-crow.html" class="teams-sheet-item"><img src="img/headshots/ete-crow.jpeg" class="headshot headshot-sm" alt="" /> Ete Crow</a>
      <a href="teams/ragans.html" class="teams-sheet-item"><img src="img/headshots/ragans.jpeg" class="headshot headshot-sm" alt="" /> The Ragans Administration</a>
      <a href="teams/keanu.html" class="teams-sheet-item"><img src="img/headshots/keanu.jpeg" class="headshot headshot-sm" alt="" /> Keanu Reeves</a>
      <a href="teams/good-vibes.html" class="teams-sheet-item"><img src="img/headshots/good-vibes.jpeg" class="headshot headshot-sm" alt="" /> Good Vibes Only</a>
      <a href="teams/rain-city.html" class="teams-sheet-item"><img src="img/headshots/rain-city.jpeg" class="headshot headshot-sm" alt="" /> Rain City Bombers</a>
      <a href="teams/buckner.html" class="teams-sheet-item"><img src="img/headshots/buckner.jpeg" class="headshot headshot-sm" alt="" /> The Buckner Boots</a>
      <a href="teams/decoy.html" class="teams-sheet-item"><img src="img/headshots/decoy.jpeg" class="headshot headshot-sm" alt="" /> Nick-fil-A</a>
      <a href="teams/one-ball.html" class="teams-sheet-item"><img src="img/headshots/one-ball.png" class="headshot headshot-sm" alt="" /> One Ball Two Strikes</a>
    </div>
  </div>
</div>
<script>
(function() {{
  var btn = document.getElementById('teams-nav-btn');
  var sheet = document.getElementById('teamsSheet');
  var backdrop = document.getElementById('teamsSheetBackdrop');
  function toggle(e) {{ if (e) e.preventDefault(); sheet.classList.toggle('open'); }}
  if (btn && sheet && backdrop) {{ btn.addEventListener('click', toggle); backdrop.addEventListener('click', toggle); }}
}})();
</script>

<!-- Weeks bottom sheet (mobile) -->
<div class="teams-sheet" id="weeksSheet">
  <div class="teams-sheet-backdrop" id="weeksSheetBackdrop"></div>
  <div class="teams-sheet-panel">
    <div class="teams-sheet-handle"></div>
    <div class="teams-sheet-title">Weeks</div>
    <div class="teams-sheet-list">
      <!-- AUTO:WEEKS_SHEET_START -->
      <a href="week-{week:02d}.html" class="teams-sheet-item active">Week {week} &mdash; {date_str}</a>
      <!-- AUTO:WEEKS_SHEET_END -->
    </div>
  </div>
</div>
<script>
(function() {{
  var btn = document.getElementById('weeks-nav-btn');
  var sheet = document.getElementById('weeksSheet');
  var backdrop = document.getElementById('weeksSheetBackdrop');
  function toggle(e) {{ if (e) e.preventDefault(); sheet.classList.toggle('open'); }}
  if (btn && sheet && backdrop) {{ btn.addEventListener('click', toggle); backdrop.addEventListener('click', toggle); }}
}})();
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
        html = replace_section(html, 'WEEKS_SHEET', render_weeks_sheet_items(recap_week))
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
            saved_scores = extract_live_scores(html)
            analysis_path = BASE_DIR / 'data' / f'week-{preview_week:02d}-analysis.json'
            analysis = json.loads(analysis_path.read_text()) if analysis_path.exists() else None
            preview_html = generate_preview(api, preview_week, analysis)
            html = replace_section(html, 'PREVIEW', preview_html)
            html = reinject_live_scores(html, saved_scores)
            html = replace_section(html, 'WEEK_LINKS', render_week_links(preview_week))
            html = replace_section(html, 'WEEKS_SHEET', render_weeks_sheet_items(preview_week))
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
