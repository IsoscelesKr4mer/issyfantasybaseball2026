# CLAUDE.md — Issaquah Swingers League Hub

This file is read by Claude at the start of every task. It contains everything needed
to generate weekly previews, recaps, and site updates without additional context.

---

## Project Overview

**Site:** https://isosceleskr4mer.github.io/issyfantasybaseball2026/
**Repo:** https://github.com/IsoscelesKr4mer/issyfantasybaseball2026
**Hosting:** GitHub Pages (static HTML)
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

| ID       | Team Name                      | Owner    | 2025 Rank | Draft Slot |
|----------|-------------------------------|----------|-----------|------------|
| senga    | Busch Latte                   | TBD      | 7th       | 1          |
| skenes   | Skenes'n on deez Hoerners     | TBD      | 10th      | 2          |
| glas     | 877-Glas-Now                  | TBD      | 3rd       | 3          |
| lets     | LetsPlayMajorLeagueBaseball   | TBD      | 1st 🏆    | 4          |
| keanu    | Keanu Reeves                  | TBD      | 6th       | 5          |
| vibes    | Good Vibes Only               | TBD      | 4th       | 6          |
| rain     | Rain City Bombers             | TBD      | 9th       | 7          |
| buckner  | The Buckner Boots             | Michael  | 8th       | 8          |
| decoy    | Decoy                         | TBD      | 5th       | 9          |
| oneball  | One Ball Two Strikes          | TBD      | 2nd       | 10         |

*Note: Update owner names as they become available from Yahoo API.*

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
- **Occasionally vulgar** — mild to moderate profanity is fine, think locker room not shock value
- **Stats-forward** — every joke is grounded in actual data or matchup facts
- **Personally targeted** — call out specific managers by team name for good/bad moves
- **Confident predictions** — don't hedge, make bold calls and own them
- **Short and punchy** — no paragraph-long wind-ups, get to the point

**Tone examples (what to aim for):**
- "Rain City Bombers once again proving that 17 roster moves in a full season is either peak zen or peak laziness. Given the results, probably the latter."
- "The Buckner Boots drafted Corey Seager in round 8. In 2025 they finished 8th. Correlation? Yes. Coincidence? No."
- "Vibes is starting 11 SPs again this week. The ERA category called. It's filing a restraining order."

**Avoid:** cringe corporate-speak, over-hedging ("this could potentially be..."), sycophantic lead-ins.

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
| `team/{key}/roster` | Individual team roster |

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

## Weekly Content Checklist

### Preview (generated Sunday night, before week starts)
- [ ] Fetch all 10 team rosters from Yahoo API BEFORE writing any content
- [ ] All 5 matchups listed with team records
- [ ] Category-by-category strength comparison for each matchup
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
