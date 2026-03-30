#!/usr/bin/env python3
"""
monte_carlo.py — Monte Carlo simulation for weekly H2H matchup predictions.

For each matchup, runs N_SIMS simulations by sampling per-player stat distributions
and aggregating to team category totals. Returns win probabilities per category and
an expected score like [6.3, 3.7].

Primary data source : Yahoo projected_week stats (via get_player_projected_stats).
Fallback            : Season-total stats scaled to a single week (via _scale_to_week).

Distribution choices
--------------------
  Counting stats (R, HR, RBI, SB, K, SV, QS) : Poisson(λ)  where λ = weekly projection
  OBP (rate)                                   : Beta(α, β) where mean = projected OBP
  ERA / WHIP (rate · IP)                       : Simulate ER and H+BB as Poisson,
                                                 IP as truncated Normal; derive team
                                                 totals as sum(ER)/sum(IP)*9 and
                                                 sum(H+BB)/sum(IP).

Usage (standalone)
------------------
  python3 scripts/monte_carlo.py <data_json_path>

  Reads week-NN-preview-data.json, prints simulation results to stdout.
  Useful for ad-hoc testing without running the full pipeline.
"""

import json
import math
import random
import sys
from pathlib import Path

# ── Constants ──────────────────────────────────────────────────────────────────

N_SIMS      = 10_000
CATS        = ['R', 'HR', 'RBI', 'SB', 'OBP', 'SV', 'K', 'ERA', 'WHIP', 'QS']
LOWER_BETTER = {'ERA', 'WHIP'}
ACTIVE_BENCH = {'IL', 'IL+', 'NA'}  # BN removed — bench pitchers rotate in on start days

# Effective sample size for Beta distribution on OBP.
# Higher = tighter distribution (less game-to-game variance).
OBP_EFF_N    = 80.0

# Standard deviation for pitcher IP sampling, expressed as a fraction of projected IP.
IP_CV        = 0.20   # 20 % coefficient of variation

# Weeks in a full season — used to scale season totals to one week.
SEASON_WEEKS = 25.0

# ── Stdlib-only distribution samplers ─────────────────────────────────────────

def _poisson(lam: float) -> int:
    """Sample from Poisson(lam).  Normal approximation for lam > 30."""
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, round(random.gauss(lam, math.sqrt(lam))))
    L = math.exp(-lam)
    k, p = 0, 1.0
    while p > L:
        k += 1
        p *= random.random()
    return k - 1


def _beta_mean(mean: float, n_eff: float = OBP_EFF_N) -> float:
    """Sample from Beta with given mean and effective sample size n_eff."""
    mean = max(0.001, min(0.999, mean))
    a = mean * n_eff
    b = (1.0 - mean) * n_eff
    return random.betavariate(a, b)


def _safe(val, default: float = 0.0) -> float:
    """Parse a value to float; return default on failure or non-finite result."""
    try:
        f = float(val)
        return f if math.isfinite(f) else default
    except (TypeError, ValueError):
        return default

# ── Roster helpers ─────────────────────────────────────────────────────────────

def _is_pitcher(player: dict) -> bool:
    """True if the player's display_position includes SP, RP, or bare P."""
    pos = player.get('pos', player.get('display_position', ''))
    return 'SP' in pos or 'RP' in pos or pos.strip() == 'P'


def _active_pitchers(roster: list) -> list:
    """Return all pitchers not on IL/NA.

    Includes bench (BN) pitchers — in Yahoo Fantasy, managers keep SPs on
    bench and activate them only on start days, so ALL non-IL/NA pitchers
    contribute innings over the course of the week.
    """
    return [
        p for p in roster
        if _is_pitcher(p)
        and p.get('starting', p.get('selected_position', '')) not in ACTIVE_BENCH
    ]


def _optimal_batters(roster: list, projected_stats: dict) -> list:
    """Return the optimal batter lineup for simulation.

    Selects the best N non-IL/NA batters by projected weekly value, where N is
    the number of active (non-BN) batter slots — i.e. how many batters the
    roster config allows to score each week.  This lets bench batters compete
    with active batters so the sim reflects what a smart manager would actually
    start.
    """
    # Count active batter slots (filled C/1B/2B/3B/SS/OF/Util spots) to get the cap.
    n_slots = sum(
        1 for p in roster
        if not _is_pitcher(p)
        and p.get('starting', p.get('selected_position', '')) not in ACTIVE_BENCH
        and p.get('starting', p.get('selected_position', '')) != 'BN'
    )
    if n_slots == 0:
        n_slots = 9  # fallback if roster data is missing

    # Collect all available batters: active slots + bench, excluding IL/NA.
    available = [
        p for p in roster
        if not _is_pitcher(p)
        and p.get('starting', p.get('selected_position', '')) not in ACTIVE_BENCH
    ]

    # Sort by projected counting-stat value so the best available batters start.
    def _batter_score(p: dict) -> float:
        pk = p.get('player_key', '')
        s  = projected_stats.get(pk, {})
        return (
            _safe(s.get('R',   0))
            + _safe(s.get('HR',  0)) * 3.0  # weight HR more heavily
            + _safe(s.get('RBI', 0))
            + _safe(s.get('SB',  0))
        )

    available.sort(key=_batter_score, reverse=True)
    return available[:n_slots]


# Keep _active_players as a legacy shim so any external callers don't break.
def _active_players(roster: list) -> list:
    """Legacy shim — prefer _active_pitchers() + _optimal_batters() for new code."""
    return [
        p for p in roster
        if p.get('starting', p.get('selected_position', '')) not in ACTIVE_BENCH
    ]

# ── Season-total → weekly projection scaler ───────────────────────────────────

def _scale_to_week(stats: dict, is_pitcher: bool) -> dict:
    """
    Convert season-total stats to a single-week projection.

    For pitchers, counting stats are scaled by (7 IP per week / season IP).
    For batters, counting stats are divided by SEASON_WEEKS (≈ 25).
    Rate stats (OBP, ERA, WHIP) are kept as-is.
    """
    out = {}
    if is_pitcher:
        season_ip = _safe(stats.get('IP', 0))
        # Assume a typical pitcher throws ~7 IP per week; if they've pitched
        # some meaningful number of innings this season, use the ratio.
        if season_ip >= 10:
            scale = 7.0 / season_ip
        else:
            scale = 1.0 / SEASON_WEEKS  # early-season guess

        for cat in ('K', 'SV', 'QS'):
            out[cat] = _safe(stats.get(cat, 0)) * scale
        out['ERA']  = _safe(stats.get('ERA',  4.00), 4.00)
        out['WHIP'] = _safe(stats.get('WHIP', 1.30), 1.30)
        out['IP']   = 7.0 * (season_ip / (season_ip + 1))  # approach 7 as IP grows; 0 if no data
        if season_ip < 1:
            out['IP'] = 0.0   # not enough data — skip this pitcher in sim
    else:
        for cat in ('R', 'HR', 'RBI', 'SB'):
            out[cat] = _safe(stats.get(cat, 0)) / SEASON_WEEKS
        out['OBP'] = _safe(stats.get('OBP', 0.0))
    return out

# ── Per-team simulation ────────────────────────────────────────────────────────

def _simulate_team(active_players: list, proj: dict) -> dict:
    """
    Simulate one week of stats for a team.

    active_players : list of player dicts with 'player_key' and 'pos' fields.
    proj           : {player_key: {cat: projected_weekly_value, ...}}

    Returns {cat: simulated_team_total} for all 10 H2H categories.
    """
    # Batting aggregates
    R = HR = RBI = SB = 0
    obp_vals = []

    # Pitching aggregates — ERA/WHIP computed from raw ER, H+BB, IP
    K = SV = QS = 0
    total_ip   = 0.0
    total_er   = 0.0
    total_hbb  = 0.0  # H + BB (numerator for WHIP)

    for p in active_players:
        key   = p.get('player_key', '')
        pstat = proj.get(key, {})
        if not pstat:
            continue

        if _is_pitcher(p):
            proj_ip   = _safe(pstat.get('IP',   0))
            proj_era  = _safe(pstat.get('ERA',  4.00), 4.00)
            proj_whip = _safe(pstat.get('WHIP', 1.30), 1.30)
            proj_k    = _safe(pstat.get('K',    0))
            proj_sv   = _safe(pstat.get('SV',   0))
            proj_qs   = _safe(pstat.get('QS',   0))

            if proj_ip <= 0:
                # No innings projection — skip this pitcher entirely
                continue

            # Sample IP with Normal noise (coefficient of variation = IP_CV)
            sim_ip = max(0.1, random.gauss(proj_ip, proj_ip * IP_CV))

            # ER ~ Poisson( ERA * IP / 9 )
            sim_er  = _poisson(proj_era * sim_ip / 9.0)

            # H+BB ~ Poisson( WHIP * IP )
            sim_hbb = _poisson(proj_whip * sim_ip)

            # K rate preserved across actual IP
            k_per_ip = proj_k / proj_ip if proj_ip > 0 else 0
            sim_k    = _poisson(k_per_ip * sim_ip)

            sim_sv   = _poisson(proj_sv)
            sim_qs   = _poisson(proj_qs)

            total_ip  += sim_ip
            total_er  += sim_er
            total_hbb += sim_hbb
            K  += sim_k
            SV += sim_sv
            QS += sim_qs

        else:
            # Batter — counting stats via Poisson, OBP via Beta
            R   += _poisson(_safe(pstat.get('R',   0)))
            HR  += _poisson(_safe(pstat.get('HR',  0)))
            RBI += _poisson(_safe(pstat.get('RBI', 0)))
            SB  += _poisson(_safe(pstat.get('SB',  0)))
            obp = _safe(pstat.get('OBP', 0.0))
            if obp > 0.100:   # ignore clearly missing/zero projections
                obp_vals.append(_beta_mean(obp))

    # Team OBP = equal-weight mean of sampled player OBPs.
    # (True OBP is PA-weighted; without PA data this is the best approximation.)
    team_obp = (sum(obp_vals) / len(obp_vals)) if obp_vals else 0.0

    # Team ERA and WHIP from raw aggregates
    if total_ip >= 0.1:
        team_era  = total_er  / total_ip * 9.0
        team_whip = total_hbb / total_ip
    else:
        # No pitching innings — assign catastrophically bad values so the
        # opponent wins both ERA and WHIP categories in this simulation.
        team_era  = 99.0
        team_whip = 9.99

    return {
        'R':    R,
        'HR':   HR,
        'RBI':  RBI,
        'SB':   SB,
        'OBP':  team_obp,
        'SV':   SV,
        'K':    K,
        'ERA':  team_era,
        'WHIP': team_whip,
        'QS':   QS,
    }

# ── Public API ─────────────────────────────────────────────────────────────────

def simulate_matchup(
    t0_roster:       list,
    t1_roster:       list,
    projected_stats: dict,
    n_sims:          int  = N_SIMS,
    seed:            int  = None,
    verbose:         bool = False,
) -> dict:
    """
    Run Monte Carlo simulation for one H2H matchup.

    Parameters
    ----------
    t0_roster       : list of player dicts for team 0 (from get_team_roster)
    t1_roster       : list of player dicts for team 1
    projected_stats : {player_key: {cat: weekly_projected_value, ...}}
                      Build this via get_player_projected_stats() with
                      _scale_to_week() fallback for missing players.
    n_sims          : number of Monte Carlo simulations (default 10,000)
    seed            : optional RNG seed for reproducibility

    Returns
    -------
    {
      "cat_probs":      {"R": 0.61, "HR": 0.74, ...},  # team0 win probability per category
      "expected_score": [6.3, 3.7],                    # expected category wins
      "win_pct":        0.71                            # team0 majority-win probability
    }

    Notes
    -----
    • cat_probs values are team0's probability of winning that category.
      E.g. 0.74 means team0 wins HR 74 % of simulations.
    • expected_score always sums to 10.0 (the number of H2H categories).
    • win_pct is the fraction of simulations where team0 wins > 5 categories.
    • Ties per category are not awarded to either team.
    """
    if seed is not None:
        random.seed(seed)

    t0_active = _active_pitchers(t0_roster) + _optimal_batters(t0_roster, projected_stats)
    t1_active = _active_pitchers(t1_roster) + _optimal_batters(t1_roster, projected_stats)

    if verbose:
        t0_p = len(_active_pitchers(t0_roster))
        t1_p = len(_active_pitchers(t1_roster))
        t0_b = len(t0_active) - t0_p
        t1_b = len(t1_active) - t1_p
        print(f'  📊  Simulation: {n_sims:,} runs | '
              f't0 {len(t0_active)} players ({t0_p}P/{t0_b}B)  '
              f't1 {len(t1_active)} players ({t1_p}P/{t1_b}B)')

    # Counters
    cat_wins_t0     = {cat: 0 for cat in CATS}
    matchup_wins_t0 = 0

    for _ in range(n_sims):
        s0 = _simulate_team(t0_active, projected_stats)
        s1 = _simulate_team(t1_active, projected_stats)

        sim_t0_cats = 0
        sim_t1_cats = 0

        for cat in CATS:
            v0, v1 = s0[cat], s1[cat]
            if cat in LOWER_BETTER:
                if v0 < v1:
                    cat_wins_t0[cat] += 1
                    sim_t0_cats      += 1
                elif v1 < v0:
                    sim_t1_cats      += 1
            else:
                if v0 > v1:
                    cat_wins_t0[cat] += 1
                    sim_t0_cats      += 1
                elif v1 > v0:
                    sim_t1_cats      += 1

        if sim_t0_cats > sim_t1_cats:
            matchup_wins_t0 += 1

    cat_probs  = {cat: round(cat_wins_t0[cat] / n_sims, 3) for cat in CATS}
    exp_t0     = round(sum(cat_probs.values()), 1)
    exp_t1     = round(len(CATS) - exp_t0, 1)
    win_pct    = round(matchup_wins_t0 / n_sims, 3)

    return {
        'cat_probs':      cat_probs,
        'expected_score': [exp_t0, exp_t1],
        'win_pct':        win_pct,
    }

# ── CLI convenience (standalone test) ─────────────────────────────────────────

def _cat_bar(prob: float, width: int = 20) -> str:
    """ASCII probability bar for terminal output."""
    filled = round(prob * width)
    return '█' * filled + '░' * (width - filled)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python3 monte_carlo.py <week-NN-preview-data.json>')
        sys.exit(1)

    data_path = Path(sys.argv[1])
    if not data_path.exists():
        print(f'File not found: {data_path}')
        sys.exit(1)

    data = json.loads(data_path.read_text())
    week = data.get('week', '?')
    print(f'\n🎲  Monte Carlo — Week {week} Matchup Simulations')
    print(f'    {N_SIMS:,} simulations per matchup\n')

    # We need projected_stats — for standalone testing, build a placeholder
    # by extracting any stats already embedded in the data JSON.
    # (Real usage: projected_stats come from yahoo_api.get_player_projected_stats.)
    proj = data.get('projected_stats', {})

    for i, m in enumerate(data.get('matchups', [])):
        t0 = m.get('t0', {})
        t1 = m.get('t1', {})
        # If simulation was already stored, just display it
        sim = m.get('simulation')
        if sim:
            print(f'  Matchup {i+1}: {t0.get("name","?")} vs {t1.get("name","?")}')
            print(f'    Expected score : {sim["expected_score"][0]} – {sim["expected_score"][1]}')
            print(f'    Win probability: {sim["win_pct"]:.1%}')
            print()
            for cat in CATS:
                p = sim['cat_probs'].get(cat, 0.5)
                bar = _cat_bar(p)
                arrow = '←' if p > 0.55 else ('→' if p < 0.45 else '~')
                print(f'    {cat:<5} {bar}  {p:.0%}  {arrow}')
            print()
        else:
            print(f'  Matchup {i+1}: {t0.get("name","?")} vs {t1.get("name","?")} — no simulation data')
            print()
