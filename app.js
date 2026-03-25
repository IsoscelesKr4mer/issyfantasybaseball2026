// ═══════════════════════════════════════════
// RENDER FUNCTIONS & INITIALIZATION
// ═══════════════════════════════════════════

// Note: TEAM_LINKS, teamLink(), and linkTeamNames() are defined in nav.js
// which loads on every page before app.js.

function getGradeClass(g) {
  const m = { 'A+':'grade-A-plus','A':'grade-A','A-':'grade-A-minus','B+':'grade-B-plus','B':'grade-B','B-':'grade-B-minus','C+':'grade-C-plus','C':'grade-C','D':'grade-D' };
  return m[g] || 'grade-B';
}
function getPosClass(p) {
  if (!p) return '';
  const u = p.toUpperCase();
  if (u === 'SP') return 'pos-sp';
  if (u === 'RP' || u === 'CL') return 'pos-rp';
  if (u === 'C') return 'pos-c';
  if (u === 'SS') return 'pos-ss';
  if (['OF','LF','CF','RF'].includes(u)) return 'pos-of';
  return '';
}
function getPickClass(n) { return n === 1 ? 'pick1' : n === 2 ? 'pick2' : n === 3 ? 'pick3' : ''; }
function teamName(id) { return TEAMS.find(t => t.id === id)?.name || id; }

// ── Projected Starting Lineup ──
// Yahoo H2H standard slots: C, 1B, 2B, 3B, SS, OF, OF, OF, UTIL, UTIL, SP, SP, RP, RP
// Helper: check if player is eligible for a position (uses elig array if present, else falls back to pos)
function canPlay(p, positions) {
  const list = p.elig || [p.pos];
  return list.some(e => positions.includes(e));
}
function isBatter(p) { return !canPlay(p, ['SP','RP','CL']); }

// Actual league roster: C,1B,2B,3B,SS,OF,OF,OF,Util,Util,SP,SP,RP,RP,P,P,P,P,BN×5,IL×3,NA
const LINEUP_SLOTS = [
  { slot: 'C',    label: 'C',    match: p => canPlay(p, ['C']) },
  { slot: '1B',   label: '1B',   match: p => canPlay(p, ['1B']) },
  { slot: '3B',   label: '3B',   match: p => canPlay(p, ['3B']) },
  { slot: '2B',   label: '2B',   match: p => canPlay(p, ['2B']) },
  { slot: 'SS',   label: 'SS',   match: p => canPlay(p, ['SS']) },
  { slot: 'OF',   label: 'OF',   match: p => canPlay(p, ['OF','LF','CF','RF']) },
  { slot: 'OF',   label: 'OF',   match: p => canPlay(p, ['OF','LF','CF','RF']) },
  { slot: 'OF',   label: 'OF',   match: p => canPlay(p, ['OF','LF','CF','RF']) },
  { slot: 'UTIL', label: 'UTIL', match: p => isBatter(p) },
  { slot: 'UTIL', label: 'UTIL', match: p => isBatter(p) },
  { slot: 'SP',   label: 'SP',   match: p => canPlay(p, ['SP']) },
  { slot: 'SP',   label: 'SP',   match: p => canPlay(p, ['SP']) },
  { slot: 'RP',   label: 'RP',   match: p => canPlay(p, ['RP','CL']) },
  { slot: 'RP',   label: 'RP',   match: p => canPlay(p, ['RP','CL']) },
  { slot: 'P',    label: 'P',    match: p => canPlay(p, ['SP','RP','CL']) },
  { slot: 'P',    label: 'P',    match: p => canPlay(p, ['SP','RP','CL']) },
  { slot: 'P',    label: 'P',    match: p => canPlay(p, ['SP','RP','CL']) },
  { slot: 'P',    label: 'P',    match: p => canPlay(p, ['SP','RP','CL']) },
];

function buildLineup(teamId) {
  if (typeof DRAFT_PICKS === 'undefined') return { starters: [], bench: [] };
  const picks = DRAFT_PICKS.filter(p => p.teamId === teamId).sort((a, b) => a.round - b.round);
  const used = new Set();
  const starters = [];

  for (const slot of LINEUP_SLOTS) {
    const pick = picks.find(p => !used.has(p.overall) && slot.match(p));
    if (pick) {
      used.add(pick.overall);
      starters.push({ ...pick, slot: slot.label });
    } else {
      // Fill UTIL/OF with best remaining batter
      const fallback = picks.find(p => !used.has(p.overall) && isBatter(p));
      if (fallback && (slot.slot === 'UTIL' || slot.slot === 'OF')) {
        used.add(fallback.overall);
        starters.push({ ...fallback, slot: slot.label });
      } else {
        starters.push({ slot: slot.label, player: '—', pos: '', round: 0, cats: '' });
      }
    }
  }
  const bench = picks.filter(p => !used.has(p.overall));
  return { starters, bench };
}

function renderLineup(teamId) {
  if (typeof DRAFT_PICKS === 'undefined') return '';
  const { starters, bench } = buildLineup(teamId);
  const batters = starters.filter(s => !['SP','RP','P'].includes(s.slot));
  const pitchers = starters.filter(s => ['SP','RP','P'].includes(s.slot));

  const renderSlot = (s) => `
    <div class="lineup-slot">
      <span class="lineup-pos-tag">${s.slot}</span>
      <span class="lineup-player">${s.player}</span>
      ${s.round ? `<span class="lineup-round">R${s.round}</span>` : ''}
    </div>`;

  return `
    <div class="lineup-section">
      <div class="lineup-group">
        <div class="lineup-group-label">Batting</div>
        ${batters.map(renderSlot).join('')}
      </div>
      <div class="lineup-group">
        <div class="lineup-group-label">Pitching</div>
        ${pitchers.map(renderSlot).join('')}
      </div>
      <div class="lineup-bench-label">${bench.length} on bench</div>
    </div>`;
}

// ── Team Roster (within grade card) ──
function renderTeamRoster(teamId) {
  if (typeof DRAFT_PICKS === 'undefined') return '';
  const picks = DRAFT_PICKS.filter(p => p.teamId === teamId).sort((a, b) => a.round - b.round);
  if (!picks.length) return '';
  const rows = picks.map(p => `
    <li>
      <span class="pick-round">R${p.round}</span>
      <span class="pick-pos ${getPosClass(p.pos)}">${p.pos || '\u2014'}</span>
      <span class="pick-name">${p.player}</span>
      <span class="pick-cat">${p.cats || ''}</span>
    </li>`).join('');
  return `
    <div class="team-roster-toggle" onclick="this.classList.toggle('open');this.nextElementSibling.classList.toggle('open')">
      <span>Full Roster (${picks.length} picks)</span>
      <span class="roster-chevron">\u25BC</span>
    </div>
    <ul class="team-picks-list">${rows}</ul>`;
}

// ── Team Grades ──
function renderTeams() {
  const grid = document.getElementById('teamsGrid');
  grid.innerHTML = '';
  TEAM_GRADES.forEach(g => {
    const team = TEAMS.find(t => t.id === g.teamId);
    if (!team) return;
    const isFeatured = false;
    const standing = STANDINGS_2025.find(s => s.teamId === team.id);
    const repeats = REPEAT_PICKS.filter(r => r.teamId === team.id);

    const repeatHtml = repeats.length > 0 ?
      `<div style="margin-top:.5rem;font-size:.78rem;color:var(--muted)"><strong style="color:var(--text)">Returning:</strong> ${repeats.map(r => `${r.player} (R${r.r25}\u2192R${r.r26})`).join(', ')}</div>` :
      (g.teamId === 'skenes' ? '<div style="margin-top:.5rem;font-size:.78rem;color:var(--accent2)">Complete roster overhaul \u2014 zero returning players</div>' : '');

    const strengthTags = (g.strengths || []).map(s => `<span class="tag tag-green">${s}</span>`).join('');
    const weakTags = (g.weaknesses || []).map(s => `<span class="tag tag-red">${s}</span>`).join('');

    grid.innerHTML += `
      <div class="team-card reveal ${isFeatured ? 'featured' : ''}">
        <div class="team-header">
          <div class="team-pick ${getPickClass(team.pick)}">${team.pick}</div>
          <div class="team-info">
            <div class="team-name ${isFeatured ? 'featured-name' : ''}">${team.name}${isFeatured ? ' \u2b50' : ''}</div>
            <div class="team-manager">${standing ? `2025: #${standing.rank} (${standing.record})` : `Pick #${team.pick}`}</div>
          </div>
          <div class="grade-badge ${getGradeClass(g.grade)}">${g.grade}</div>
        </div>
        <div class="team-body">
          ${renderLineup(team.id)}
          <div class="team-analysis">
            ${g.analysis || ''}
            ${repeatHtml}
            ${strengthTags ? `<div class="team-strengths" style="margin-top:.5rem">${strengthTags}</div>` : ''}
            ${weakTags ? `<div class="team-weaknesses" style="margin-top:.4rem">${weakTags}</div>` : ''}
          </div>
          ${renderTeamRoster(team.id)}
        </div>
      </div>`;
  });
}

// ── Projected Standings ──
function renderProjectedStandings() {
  const tbody = document.querySelector('#projectedStandings tbody');
  tbody.innerHTML = PROJECTED.map((p, i) => {
    const team = TEAMS.find(t => t.id === p.teamId);
    const isPlayoff = i < 6;
    const isCutline = i === 5;
    const champPct = parseFloat(p.champ);
    const champColor = champPct >= 15 ? 'var(--green)' : champPct >= 5 ? 'var(--accent)' : champPct >= 1 ? 'var(--muted)' : 'var(--border)';
    return `<tr class="${isCutline ? 'cutline' : ''} ${!isPlayoff ? 'below-cut' : ''}">
      <td><span class="rank-badge ${i < 3 ? 'rank-' + (i+1) : ''}">${i+1}</span></td>
      <td>${teamLink(team?.name || p.teamId)}</td>
      <td>${p.w}-${p.l}-${p.t}</td>
      <td>${p.pct}</td>
      <td style="font-weight:700;${parseFloat(p.playoff) >= 80 ? 'color:var(--green)' : parseFloat(p.playoff) >= 40 ? 'color:var(--accent)' : 'color:var(--muted)'}">${p.playoff}</td>
      <td style="font-weight:900;color:${champColor}">${p.champ}</td>
    </tr>`;
  }).join('');
}

// ── Playoff Bracket ──
function renderPlayoffBracket() {
  const el = document.getElementById('playoffBracket');
  if (!el) return;

  el.innerHTML = `
    <div class="bracket-container">
      <div class="bracket">
        <!-- QUARTERFINALS -->
        <div class="bracket-round">
          <div class="bracket-round-label">Week 23 &mdash; QF</div>
          <div class="bracket-bye">
            <span class="seed">#1</span>
            <span class="team-label">One Ball Two Strikes</span>
            <span class="bye-label">Bye</span>
          </div>
          <div class="bracket-matchup">
            <div class="bracket-team winner">
              <span class="seed">#3</span>
              <span class="team-label">The Ragans Administration</span>
              <span class="score">6</span>
            </div>
            <div class="bracket-team">
              <span class="seed">#6</span>
              <span class="team-label">Keanu Reeves</span>
              <span class="score">4</span>
            </div>
          </div>
          <div class="bracket-matchup">
            <div class="bracket-team winner">
              <span class="seed">#4</span>
              <span class="team-label">The Buckner Boots</span>
              <span class="score">6</span>
            </div>
            <div class="bracket-team">
              <span class="seed">#5</span>
              <span class="team-label">Decoy</span>
              <span class="score">4</span>
            </div>
          </div>
          <div class="bracket-bye">
            <span class="seed">#2</span>
            <span class="team-label">Good Vibes Only</span>
            <span class="bye-label">Bye</span>
          </div>
        </div>

        <!-- Connector -->
        <div class="bracket-connector">
          <svg viewBox="0 0 32 300" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M0 75 H16 V150 H32" />
            <path d="M0 225 H16 V150" />
          </svg>
        </div>

        <!-- SEMIFINALS -->
        <div class="bracket-round">
          <div class="bracket-round-label">Week 24 &mdash; SF</div>
          <div class="bracket-matchup">
            <div class="bracket-team winner">
              <span class="seed">#1</span>
              <span class="team-label">One Ball Two Strikes</span>
              <span class="score">7</span>
            </div>
            <div class="bracket-team">
              <span class="seed">#4</span>
              <span class="team-label">The Buckner Boots</span>
              <span class="score">3</span>
            </div>
          </div>
          <div class="bracket-matchup">
            <div class="bracket-team winner">
              <span class="seed">#2</span>
              <span class="team-label">Good Vibes Only</span>
              <span class="score">6</span>
            </div>
            <div class="bracket-team">
              <span class="seed">#3</span>
              <span class="team-label">The Ragans Administration</span>
              <span class="score">4</span>
            </div>
          </div>
        </div>

        <!-- Connector -->
        <div class="bracket-connector">
          <svg viewBox="0 0 32 200" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M0 50 H16 V100 H32" />
            <path d="M0 150 H16 V100" />
          </svg>
        </div>

        <!-- CHAMPIONSHIP -->
        <div class="bracket-round">
          <div class="bracket-round-label">Week 25 &mdash; Final</div>
          <div class="bracket-matchup championship">
            <div class="bracket-team winner">
              <span class="seed">#1</span>
              <span class="team-label">One Ball Two Strikes</span>
              <span class="score">6</span>
            </div>
            <div class="bracket-team">
              <span class="seed">#2</span>
              <span class="team-label">Good Vibes Only</span>
              <span class="score">4</span>
            </div>
            <div class="champion-tag">\u{1F3C6} Predicted Champion</div>
          </div>
          <div style="margin-top:.75rem;font-size:.8rem;color:var(--text-secondary);line-height:1.6;max-width:240px;">
            One Ball's Skubal/Yamamoto/Eovaldi trio dominates K and QS across 8 pitching slots. Ram\u00edrez anchors all 5 batting categories. Vibes' OBP edge keeps it close, but One Ball's SV advantage (Bednar + Jansen + Burns) seals it.
          </div>
        </div>
      </div>
    </div>
  `;
}

// ── Loyalty Picks ──
function renderLoyaltyPicks() {
  const el = document.getElementById('loyaltyPicks');
  const sorted = [...REPEAT_PICKS].sort((a,b) => Math.abs(a.diff) - Math.abs(b.diff));
  el.innerHTML = sorted.map(r => {
    const arrow = r.diff < 0 ? '\u25B2' : r.diff > 0 ? '\u25BC' : '\u2594';
    const cls = r.diff < 0 ? 'arrow-up' : r.diff > 0 ? 'arrow-down' : 'arrow-same';
    const diffText = r.diff === 0 ? 'Same round' : r.diff < 0 ? `${Math.abs(r.diff)} rounds earlier` : `${r.diff} rounds later`;
    return `<div class="insight-row">
      <span class="insight-icon ${cls}">${arrow}</span>
      <div style="flex:1">
        <div class="insight-val">${r.player}</div>
        <div class="insight-label">${teamLink(teamName(r.teamId))} \u2014 R${r.r25} \u2192 R${r.r26} (${diffText})</div>
      </div>
    </div>`;
  }).join('');
}

// ── ADP Movers ──
function renderADPMovers() {
  const el = document.getElementById('adpMovers');
  const promos = [...REPEAT_PICKS].filter(r => r.diff < 0).sort((a,b) => a.diff - b.diff);
  const demos = [...REPEAT_PICKS].filter(r => r.diff > 0).sort((a,b) => b.diff - a.diff);

  let html = '<div style="margin-bottom:.5rem;font-size:.72rem;font-weight:800;color:var(--green);letter-spacing:1px;text-transform:uppercase">Biggest Promotions</div>';
  promos.forEach(r => {
    html += `<div class="insight-row">
      <span class="insight-icon arrow-up">\u25B2</span>
      <div style="flex:1">
        <div class="insight-val">${r.player} <span style="color:var(--green);font-size:.8rem;">+${Math.abs(r.diff)} rounds</span></div>
        <div class="insight-label">${teamLink(teamName(r.teamId))} \u2014 R${r.r25} \u2192 R${r.r26}</div>
      </div>
    </div>`;
  });

  html += '<div style="margin:.75rem 0 .5rem;font-size:.72rem;font-weight:800;color:var(--red);letter-spacing:1px;text-transform:uppercase">Biggest Demotions</div>';
  demos.slice(0, 4).forEach(r => {
    html += `<div class="insight-row">
      <span class="insight-icon arrow-down">\u25BC</span>
      <div style="flex:1">
        <div class="insight-val">${r.player} <span style="color:var(--red);font-size:.8rem;">-${r.diff} rounds</span></div>
        <div class="insight-label">${teamLink(teamName(r.teamId))} \u2014 R${r.r25} \u2192 R${r.r26}</div>
      </div>
    </div>`;
  });
  el.innerHTML = html;
}

// ── Turnover & Notable Movement ──
function renderTurnover() {
  const el = document.getElementById('turnoverInsights');
  const counts = {};
  TEAMS.forEach(t => { counts[t.id] = REPEAT_PICKS.filter(r => r.teamId === t.id).length; });
  const sorted = Object.entries(counts).sort((a,b) => a[1] - b[1]);

  el.innerHTML = sorted.map(([id, count]) => {
    const pct = Math.round(((23 - count) / 23) * 100);
    const color = count === 0 ? 'var(--accent2)' : count <= 1 ? 'var(--red)' : count >= 3 ? 'var(--green)' : 'var(--accent)';
    return `<div class="insight-row">
      <div style="flex:1">
        <div class="insight-val">${teamLink(teamName(id))}</div>
        <div class="insight-label">${count} returning player${count !== 1 ? 's' : ''} \u2014 ${pct}% new roster</div>
      </div>
      <div style="font-weight:900;font-size:1.1rem;color:${color}">${count}</div>
    </div>`;
  }).join('');
}

function renderNotableMovement() {
  const el = document.getElementById('notableMovement');
  const notables = [
    { player: 'Shohei Ohtani (Batter)', from: 'Decoy (R1)', to: 'Senga (R1)', note: 'Still goes #1 overall, new owner' },
    { player: 'Elly De La Cruz', from: 'One Ball (R1)', to: 'Ete Crow (R1)', note: 'Champion stole the runner-up\'s R1 pick' },
    { player: 'Bobby Witt Jr.', from: 'Ragans (R1)', to: "Skenes'n (R1)", note: 'New home, same round' },
    { player: 'Kyle Tucker', from: "Skenes'n (R2)", to: 'Buckner Boots (R1)', note: 'Our new cornerstone' },
    { player: 'Corbin Burnes', from: 'Vibes (R4)', to: 'Vibes (R23)', note: 'Same team, 19 rounds later!' },
    { player: 'Will Smith', from: 'Rain City (R13)', to: 'Rain City (R13)', note: 'Exact same round, same team' },
    { player: 'Cristopher S\u00e1nchez', from: 'Keanu (R14)', to: 'Keanu (R3)', note: 'Biggest promotion: +11 rounds' },
  ];
  el.innerHTML = notables.map(n => `<div class="insight-row">
    <div style="flex:1">
      <div class="insight-val">${n.player}</div>
      <div class="insight-label">${n.from} \u2192 ${n.to}</div>
    </div>
    <div style="font-size:.75rem;color:var(--accent2);max-width:140px;text-align:right">${n.note}</div>
  </div>`).join('');
}

// ── 2025 Standings ──
function renderStandings() {
  const tbody = document.getElementById('standingsBody');
  tbody.innerHTML = STANDINGS_2025.map(s => {
    const team = TEAMS.find(t => t.id === s.teamId);
    const grade = TEAM_GRADES.find(g => g.teamId === s.teamId);
    const rankClass = s.rank <= 3 ? `rank-${s.rank}` : '';
    return `<tr>
      <td><span class="rank-badge ${rankClass}">${s.rank}</span></td>
      <td>${teamLink(team?.name || s.teamId)}</td>
      <td>${s.record}</td>
      <td>${s.pct}</td>
      <td style="font-weight:700;${s.moves >= 80 ? 'color:var(--green)' : s.moves <= 36 ? 'color:var(--red)' : ''}">${s.moves}</td>
      <td><span class="grade-badge grade-badge-sm ${getGradeClass(grade?.grade || 'B')}">${grade?.grade || '\u2014'}</span></td>
    </tr>`;
  }).join('');
}

// ── Buckner Roster ──
function renderBucknerRoster() {
  const el = document.getElementById('bucknerRoster');
  if (!el) return;
  el.innerHTML = BUCKNER_2026.map(p => {
    const isBat = ['OF','SS','2B','3B','1B','C'].includes(p.pos);
    const isRP = p.pos === 'RP';
    const slotClass = isRP ? 'slot-rp' : isBat ? 'slot-bat' : 'slot-pitch';
    return `<div class="roster-slot ${slotClass}">
      <div class="slot-label">${p.pos} \u2014 R${p.round} (#${p.pick})</div>
      <div class="slot-player">${p.player}</div>
      ${p.note ? `<div class="slot-note">${p.note}</div>` : ''}
    </div>`;
  }).join('');
}

// ── Buckner Schedule ──
function renderBucknerSchedule() {
  const el = document.getElementById('bucknerSchedule');
  if (!el) return;
  const diffColors = { tough: 'var(--red)', even: 'var(--accent)', easy: 'var(--green)' };
  const diffLabels = { tough: 'TOUGH', even: 'EVEN', easy: 'EASY' };

  el.innerHTML = BUCKNER_SCHEDULE.map(s => {
    const team = TEAMS.find(t => t.id === s.opp);
    const grade = TEAM_GRADES.find(g => g.teamId === s.opp);
    return `<div style="display:flex;align-items:center;gap:.6rem;padding:.3rem 0;border-bottom:1px solid var(--border);font-size:.82rem;">
      <span style="color:var(--muted);width:32px;text-align:right;font-weight:700;flex-shrink:0">Wk${s.week}</span>
      <span style="flex:1;${s.opp === 'oneball' || s.opp === 'vibes' ? 'font-weight:700' : ''}">${teamLink(team?.name || s.opp)}</span>
      <span style="font-size:.68rem;font-weight:700;padding:1px 6px;border-radius:4px;background:rgba(${s.diff === 'tough' ? '244,68,68' : s.diff === 'easy' ? '62,207,142' : '79,142,247'},.15);color:${diffColors[s.diff]}">${diffLabels[s.diff]}</span>
    </div>`;
  }).join('');
}

// ── Scroll Reveal ──
function initScrollReveal() {
  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
      }
    });
  }, { threshold: 0.05, rootMargin: '0px 0px -40px 0px' });

  document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
}

// ── Active Nav Tracking ──
function initNavTracking() {
  const navLinks = document.querySelectorAll('nav a[href^="#"]:not(.nav-dropdown-toggle)');

  function updateActiveNav() {
    const scrollY = window.scrollY + 100; // offset for sticky nav
    let current = '';

    document.querySelectorAll('.section[id]').forEach(section => {
      if (section.offsetTop <= scrollY) {
        current = section.id;
      }
    });

    navLinks.forEach(link => {
      link.classList.toggle('active', link.getAttribute('href') === `#${current}`);
    });
  }

  window.addEventListener('scroll', updateActiveNav, { passive: true });
  updateActiveNav();
}

// ── Mobile Nav Toggle ──
function initMobileNav() {
  const toggle = document.querySelector('.nav-toggle');
  const links = document.querySelector('.nav-links');
  if (!toggle || !links) return;

  toggle.addEventListener('click', () => {
    links.classList.toggle('open');
  });

  links.querySelectorAll('a').forEach(a => {
    a.addEventListener('click', () => links.classList.remove('open'));
  });
}

// ── INIT ──
document.addEventListener('DOMContentLoaded', () => {
  renderTeams();
  renderProjectedStandings();
  renderPlayoffBracket();
  renderLoyaltyPicks();
  renderADPMovers();
  renderTurnover();
  renderNotableMovement();
  renderStandings();

  // Delayed init for scroll effects
  requestAnimationFrame(() => {
    initScrollReveal();
    initNavTracking();
    initMobileNav();
  });
});
