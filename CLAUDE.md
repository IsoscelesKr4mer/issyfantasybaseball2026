# CLAUDE.md — Issaquah Swingers League Hub

This file is read by Claude at the start of every task. It contains everything needed
to generate weekly previews, recaps, and site updates without additional context.

---

## Project Overview

**Site:** https://issaquahswingers.com
**Repo:** https://github.com/IsoscelesKr4mer/issyfantasybaseball2026
**Hosting:** Vercel (static HTML, auto-deploys on git push)
**Stack:** Vanilla HTML/CSS/JS + Python scripts for data fetching + content generation

The site is the unofficial league hub for the Issaquah Swingers fantasy baseball league,
serving as a richer alternative to the Yahoo Fantasy league page with deeper stats,
matchup previews, weekly recaps, and running commentary.

---

## League Settings

| Setting       | Value                              |
|---------------|------------------------------------|
| Sport         | MLB Fantasy Baseball               |
| Format        | Head-to-Head Categories            |
| Teams         | 10                                 |
| Season        | 2026                               |
| Draft         | Sun Mar 22, 2026 (snake, 23 rnds)  |
| Playoffs      | 6 teams, Weeks 23–25               |

**Batting categories:** R, HR, RBI, SB, OBP
**Pitching categories:** SV, K, ERA, WHIP, QS

---

## Teams

| ID       | Team Name                      | Owner        | 2025 Rank | Draft Slot |
|----------|-------------------------------|--------------|-----------|------------|
| senga    | Busch Latte                   | Rose         | 7th       | 1          |
| skenes   | Skenes'n on deez Hoerners     | TylerR       | 10th      | 2          |
| glas     | The Ragans Administration     | TylerV       | 3rd       | 3          |
| lets     | Ete Crow                      | Jace Allison | 1st 🏆    | 4          |
| keanu    | Keanu Reeves                  | Duke Joe     | 6th       | 5          |
| vibes    | Good Vibes Only               | Michael      | 4th       | 6          |
| rain     | Rain City Bombers             | Taylor       | 9th       | 7          |
| buckner  | The Buckner Boots             | Michael      | 8th       | 8          |
| decoy    | Decoy                         | Mario        | 5th       | 9          |
| oneball  | One Ball Two Strikes          | Garth W      | 2nd       | 10         |

---

## Site Structure

```
/
├── index.html          ← HOME: live standings, recent transactions, current week snapshot
├── draft.html          ← DRAFT: full 2026 draft recap (migrated from original index.html)
├── week-01.html        ← WEEK 1: preview + recap (recap added Sunday night)
├── week-02.html
│   ...
├── week-25.html
├── season.html         ← SEASON RECAP: generated after Week 25
├── styles.css          ← Shared styles (dark theme, existing)
├── data.js             ← Static data constants (draft picks, grades, 2025 standings)
├── app.js              ← Shared render functions
├── scripts/
│   ├── yahoo_auth.py       ← One-time OAuth setup
│   ├── yahoo_api.py        ← Yahoo API client (token refresh, all API calls)
│   ├── monte_carlo.py      ← Monte Carlo simulation layer (10k sims/matchup)
│   ├── generate_week.py    ← Weekly preview + recap generator
│   └── generate_home.py    ← Home page standings + transactions updater
├── .env                ← Credentials (GITIGNORED)
├── tokens.json         ← OAuth tokens (GITIGNORED)
└── CLAUDE.md           ← This file
```

---

## Tone & Voice Guidelines

This is a **boys' league**. The writing voice should be:

- **Dry humor** — deadpan observations, mock-serious analysis, understated savagery
- **Occasionally vulgar** — extreme profanity is allowed — Shock value is appreciated.
- **Stats-forward** — every joke is grounded in actual data or matchup facts
- **Personally targeted** — call out specific managers by name for good/bad moves
- **Confident predictions** — don't hedge, make bold calls and own them
- **Short and punchy** — no paragraph-long wind-ups, get to the point

**Tone examples (what to aim for):**
- "Rain City Bombers once again proving that 17 roster moves in a full season is either peak zen or peak laziness. Given the results, probably the latter."
- "The Buckner Boots drafted Corey Seager in round 8. In 2025 they finished 8th. Correlation? Yes. Coincidence? No."
- "Vibes is starting 11 SPs again this week. The ERA category called. It's filing a restraining order."

**Avoid:** cringe corporate-speak, over-hedging ("this could potentially be..."), sycophantic lead-ins.

**Humanizer rules (writing style):**
- **No em dashes.** Never use `—` or `&mdash;` in generated prose. Rewrite the sentence instead. A comma, period, or colon almost always works better.

---

## Automation Schedule

**Every Sunday at 11:59 PM Pacific:**
1. Fetch final scores for week that just ended
2. Generate weekly recap section for `week-XX.html`
3. Fetch next week's matchups, rosters, injury reports
4. Generate weekly preview section for `week-XX+1.html`
5. Fetch current standings + recent transactions
6. Update `index.html` home page
7. Git commit + push to GitHub → auto-deploys via GitHub Pages

**Script:** `scripts/generate_week.py`
**Scheduled task:** configured in Cowork

---

## Yahoo API Reference

**Base URL:** `https://fantasysports.yahooapis.com/fantasy/v2/`
**Auth:** OAuth 2.0 with automatic refresh token rotation
**Format:** JSON (`?format=json` on all requests)

Key endpoints used:
| Endpoint | What it fetches |
|----------|----------------|
| `league/{key}` | League metadata |
| `league/{key}/standings` | Current standings |
| `league/{key}/scoreboard;week={n}` | Matchups for a week |
| `league/{key}/transactions` | Recent add/drops/trades |
| `league/{key}/teams` | All team rosters |
| `team/{key}/roster;week={n}` | Individual team roster for a specific week |
| `players;player_keys={keys};out=stats;type=projected_week;week={n}` | Projected week stats (Monte Carlo primary source) |
| `players;player_keys={keys};out=stats` | Season-to-date stats (Monte Carlo fallback) |

**League key format:** `mlb.l.{YAHOO_LEAGUE_ID}`
**Team key format:** `mlb.l.{YAHOO_LEAGUE_ID}.t.{1-10}`

---

## Credentials

Stored in `.env` (gitignored). Keys:
- `YAHOO_CLIENT_ID`
- `YAHOO_CLIENT_SECRET`
- `YAHOO_REFRESH_TOKEN` — populated after running `scripts/yahoo_auth.py` once
- `YAHOO_LEAGUE_ID` — your Yahoo league number (from the URL)
- `GITHUB_TOKEN` — Personal Access Token for auto-push
- `GITHUB_REPO` — `IsoscelesKr4mer/issyfantasybaseball2026`

---

## Git Workflow

After generating any content:
```bash
cd /path/to/repo
git add -A
git commit -m "auto: week {N} preview/recap — {date}"
git push
```
GitHub Pages deploys automatically within ~60 seconds of push.

---

## Content Accuracy Rules

**MANDATORY before writing any player-specific insights, sleeper picks, waiver wire targets, or injury notes:**

1. **Always call the Yahoo API first.** Fetch current rosters via `league/{key}/teams` or `team/{key}/roster` before making any claims about who is on a team, who is starting, who is on IL, or what a player's role is.
2. **Never fabricate player context.** Do not describe a player's role, status, or history from memory. If the API doesn't confirm it, don't say it.
3. **Cross-reference with live data.** Use the API response to verify starting rotation spots, injury status, and roster ownership before writing waiver/sleeper content.
4. **If API data is unavailable**, omit the player-specific section entirely rather than guessing. It's better to have no sleeper pick than a wrong one.

**Why this rule exists:** In Week 1 content, Emerson Hancock was incorrectly described as an "Opening Day starter with strikeout stuff" and Parker Messick was incorrectly described as being in the Opening Day rotation the prior year. Both were wrong. All insights must be grounded in verified data.

---

## Player News Data

`fetch_week_data()` also calls `api.get_player_news()` for every rostered player and stores the results in the data JSON under `matchups[i]['t0']['player_news']` and `matchups[i]['t1']['player_news']`. Structure:

```json
{
  "Ketel Marte": [
    {
      "headline": "Experiences lower-leg soreness",
      "summary": "Marte was scratched from Tuesday's exhibition game due to lower-leg soreness...",
      "url": "https://...",
      "timestamp": "Mar 25 05:15 AM"
    }
  ]
}
```

**How to use this data when writing analysis:**
- Read `player_news` for both teams before writing any team analysis or category edges.
- Use the news **to inform your confidence and framing**, not to generate a dedicated news section.
- If a key player has a DTD/IL note, factor it into category edges (e.g. "HR/RBI edge narrows if Marte misses games") and call it out naturally in the team analysis paragraph.
- If the note is minor ("no concern for Opening Day"), write about the player normally — don't flag it.
- If the note confirms a missed week or IL stint, treat that player as effectively absent for category projections.
- Never invent news; if `player_news` is empty for a player, don't speculate about their health.

**IL slots rule (critical for injury analysis):**
Teams have dedicated IL slots, so a player on the IL does NOT eliminate an active roster spot. The team can and will replace that player with a healthy roster addition. This means:
- 3 players on IL = team still fields a full active lineup, just with different players filling those spots.
- The damage from an IL injury is losing that specific player's production, not losing a roster slot entirely.
- Only injuries to players in **active slots** (not IL slots) actually shrink the active roster.
- When writing about a team's injuries, distinguish between "their ace is IL-stashed but they've backfilled the rotation" vs. "their 2B is actively hurt with no replacement yet." The first is manageable; the second actually hurts.

---

## Monte Carlo Simulation Layer

`scripts/monte_carlo.py` runs 10,000 per-matchup simulations using Yahoo's projected-week
stats to produce probabilistic category win estimates. These numbers are **not suggestions** —
Claude should treat them as ground truth inputs and write analysis that reflects them.

### How it works

1. `fetch_week_data()` calls `api.get_player_projected_stats(player_keys, week)` — Yahoo's
   `projected_week` endpoint — for every active player across all 10 rosters.
2. Players without projected-week data fall back to season-average stats scaled to one week
   (÷ 25 for batters; × weekly_IP/season_IP for pitchers).
3. For each simulation: sample every active player's stats from a distribution, sum to
   team totals, determine category winner.
   - Counting stats (R, HR, RBI, SB, K, SV, QS) → Poisson(λ = weekly projection)
   - OBP → Beta(α, β) anchored at projected OBP with 80 effective at-bats of "noise"
   - ERA/WHIP → derive ER and H+BB via Poisson, sample IP via Normal(proj_IP, 20% σ);
     team ERA = sum(ER)/sum(IP)×9, team WHIP = sum(H+BB)/sum(IP)
4. After 10,000 runs, record what fraction team0 wins each category.

### Output format (stored in `matchups[i]['simulation']`)

```json
{
  "cat_probs": {
    "R": 0.61, "HR": 0.74, "RBI": 0.68, "SB": 0.44, "OBP": 0.52,
    "SV": 0.91, "K": 0.58, "ERA": 0.38, "WHIP": 0.41, "QS": 0.55
  },
  "expected_score": [6.3, 3.7],
  "win_pct": 0.71
}
```

`cat_probs` values are **team0's win probability** per category (0 = team1 dominates, 1 = team0 dominates).

### How Claude uses simulation data when writing analysis

**Category edges (`cat_edges`):**
Use `cat_probs` to determine edge direction and label. Rule of thumb:
- `prob ≥ 0.60` → edge: 0 (team0). Label: "Team0 edge (XX%)"
- `prob ≤ 0.40` → edge: 1 (team1). Label: "Team1 edge (XX%)"
- `0.40 < prob < 0.60` → edge: -1 (even). Label: "Toss-up (XX%/XX%)"

Group correlated categories to stay within 6 display rows:
  HR/RBI/R, SB, OBP, K/QS, ERA/WHIP, SV

**Prediction format:**
Use `expected_score` as the score and `win_pct` to calibrate confidence.
- "TeamName 6.3–3.7. One punchy sentence." when `win_pct ≥ 0.65`
- "TeamName 5.8–4.2. Close matchup, lean TeamName because [specific reason]." when `win_pct` is 0.55–0.65
- Still round X+Y to 10.0 in the prediction text.

**Example:** `expected_score: [6.3, 3.7], win_pct: 0.71` → "One Ball Two Strikes 6–4. Their bullpen is a fire hydrant and the other team's closers are all named 'TBD.'"

**Don't:** mechanically paste probability numbers into the prose. Use them to anchor confidence and pick the right winners. The jokes and voice are yours; the math just tells you who to pick.

### Standalone testing

```bash
# After running dump to generate the data file:
python3 scripts/generate_week.py dump 1
python3 scripts/monte_carlo.py data/week-01-preview-data.json
```

---

## AI-Generated Matchup Analysis

Weekly preview analysis is written by **Claude directly** as part of the Cowork scheduled task — not via a separate API call. Claude IS the agent running the Sunday task, so no API key is needed.

**How it works:**
1. The scheduled task runs `python3 scripts/generate_week.py dump {N}` which fetches all Yahoo data and saves it to `data/week-NN-preview-data.json`
2. Claude reads that JSON — full rosters for both teams in every matchup, current W-L records, 2025 finish ranks, **and `player_news` for every rostered player**
3. Claude reads `player_news` for both teams in each matchup BEFORE writing any analysis — injury context shapes category edges and prose framing
4. Claude writes the analysis directly: team breakdowns, category edges, predictions, and 4 storyline paragraphs
5. Claude saves the analysis as `data/week-NN-analysis.json` then calls `generate_preview(api, week, analysis)` with that data
6. The HTML is rendered and pushed to GitHub

**What makes it accurate:**
- Every player mentioned is pulled from the actual Yahoo API roster response for that week
- Category edges reflect real roster composition — closer depth, SP quality, power vs. speed profile
- Player news (Rotowire/beat writer blurbs) informs injury framing — DTD vs. IL, severity, timeline
- Records and standings are live at generation time
- Claude has full context of all 5 matchups simultaneously, so storylines reference actual cross-matchup dynamics

**Tone:** Same voice as the rest of this file — dry, stats-forward, personally targeted, no hedging.

**Data file location:** `data/week-NN-preview-data.json` (gitignored — not committed to repo)

**What Claude writes per matchup:**
- `team0_analysis` — 2–3 sentences on that team's strengths/weaknesses this specific week
- `team1_analysis` — same for the opponent
- `cat_edges` — 6 rows: HR/RBI/R, SB, OBP, K/QS, ERA/WHIP, SV — each with edge (team0/team1/even) and short label derived from Monte Carlo `cat_probs`
- `prediction` — "TeamName X-Y. One punchy sentence." format, X+Y=10; X and Y come from Monte Carlo `expected_score` (rounded to nearest integer)

**Simulation data is already in the JSON** under `matchups[i]['simulation']`. Read it.
See the **Monte Carlo Simulation Layer** section above for exactly how to translate
`cat_probs` → edge labels and `expected_score`/`win_pct` → prediction score.

---

## Weekly Content Checklist

### Preview (generated Sunday night, before week starts)
- [ ] Fetch all 10 team rosters from Yahoo API BEFORE writing any content
- [ ] Read `player_news` for both teams in every matchup BEFORE writing any analysis
- [ ] All 5 matchups listed with team records
- [ ] Category-by-category strength comparison for each matchup — injury news informs edge confidence
- [ ] 3–5 "Storylines to Watch" with commentary
- [ ] Bold prediction for each matchup winner
- [ ] "Sleeper of the Week" player pick — must be verified via API roster data
- [ ] "Waiver Wire Moves to Make" section — players must be confirmed unowned via API

### Recap (generated Sunday night, after week ends)
- [ ] Final scores for all 5 matchups
- [ ] "Biggest Win" callout
- [ ] "Choke of the Week" for the most embarrassing loss
- [ ] Category leaders (who won HR, SV, ERA, etc.)
- [ ] "Move of the Week" — best transaction
- [ ] Updated standings table
- [ ] Running power rankings blurb
