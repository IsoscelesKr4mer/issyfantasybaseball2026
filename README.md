# Issaquah Swingers — 2026 Fantasy Baseball Draft Analysis

A static web app for post-draft analysis of the Issaquah Swingers fantasy baseball league.

## Live Site

Deploy to GitHub Pages:
1. Push this repo to GitHub
2. Go to **Settings → Pages → Source → main branch / root**
3. Your site will be live at `https://yourusername.github.io/fantasy-baseball-2026/`

## Files

- `index.html` — Main draft analysis website
- `README.md` — This file

## After the Draft

Open `index.html` in a text editor and update the two data arrays near the bottom of the `<script>` tag:

### 1. `DRAFT_PICKS` — Add every pick:
```js
{ overall: 1, round: 1, pickInRound: 1, teamId: 'senga', player: 'Shohei Ohtani', pos: 'DH', cats: 'HR/R/RBI/OBP' },
{ overall: 8, round: 1, pickInRound: 8, teamId: 'buckner', player: 'YOUR PICK', pos: 'OF', cats: 'HR/SB/R' },
// ... all 230 picks
```

### 2. `TEAM_GRADES` — Add grades after analysis:
```js
{ teamId: 'buckner', grade: 'A', analysis: 'Built around power and SB...', strengths: ['HR','SB','OBP'], weaknesses: ['ERA'] },
```

## Team IDs
| ID | Team Name |
|----|-----------|
| senga | Senga man watchu smokin? |
| skenes | Skenes'n on deez Hoerners |
| glas | 877-Glas-Now |
| lets | LetsPlayMajorLeagueBaseball |
| keanu | Keanu Reeves |
| vibes | Good Vibes Only |
| rain | Rain City Bombers |
| buckner | The Buckner Boots ⭐ |
| decoy | Decoy |
| oneball | One Ball Two Strikes |

## League Settings
- **Format:** Head-to-Head Categories
- **Batting:** R, HR, RBI, SB, OBP
- **Pitching:** SV, K, ERA, WHIP, QS
- **Teams:** 10 | **Rounds:** 23 | **Draft:** Sun Mar 22, 2026
