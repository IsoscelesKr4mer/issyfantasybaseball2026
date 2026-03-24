/**
 * team-hover.js — Player tooltip on hover for roster pages.
 * Shows headshot, name, position, MLB team, stats, and injury status.
 */
(function () {
  'use strict';

  // ── Create tooltip element ─────────────────────────────────────────────────
  const tip = document.createElement('div');
  tip.className = 'player-tooltip';
  tip.setAttribute('aria-hidden', 'true');
  document.body.appendChild(tip);

  let activeRow = null;
  let showTimer = null;
  let hideTimer = null;

  // ── Stat label display names ───────────────────────────────────────────────
  const STAT_LABELS = {
    R: 'R', HR: 'HR', RBI: 'RBI', SB: 'SB', OBP: 'OBP',
    ERA: 'ERA', WHIP: 'WHIP', K: 'K', SV: 'SV', QS: 'QS', IP: 'IP',
  };

  function buildTooltip(row) {
    const name     = row.dataset.name    || '?';
    const pos      = row.dataset.pos     || '';
    const mlb      = row.dataset.mlb     || '';
    const headshot = row.dataset.headshot || '';
    const status   = row.dataset.status  || '';
    let   stats    = {};
    try { stats = JSON.parse(row.dataset.stats || '{}'); } catch (e) {}

    // ── Headshot ────────────────────────────────────────────────────────────
    const headshotHtml = headshot
      ? `<img class="tip-headshot" src="${headshot}" alt="${name}" loading="lazy" onerror="this.style.display='none'">`
      : `<div class="tip-headshot tip-headshot-fallback"><span>${name.charAt(0)}</span></div>`;

    // ── Injury badge ────────────────────────────────────────────────────────
    let injHtml = '';
    if (status) {
      const cls = status === 'IL' || status === '10-day IL' || status === '15-day IL' || status === '60-day IL' ? 'il' : 'dtd';
      injHtml = `<span class="inj-badge ${cls}">${status}</span>`;
    }

    // ── Stats grid ──────────────────────────────────────────────────────────
    const statEntries = Object.entries(stats).filter(([k]) => k in STAT_LABELS);
    let statsHtml = '';
    if (statEntries.length) {
      const cells = statEntries.map(([k, v]) =>
        `<div class="tip-stat-cell"><div class="tip-stat-val">${v === null || v === undefined || v === '' ? '—' : v}</div><div class="tip-stat-lbl">${STAT_LABELS[k]}</div></div>`
      ).join('');
      statsHtml = `<div class="tip-stats-grid">${cells}</div>`;
    } else {
      statsHtml = `<div class="tip-no-stats">No stats yet</div>`;
    }

    tip.innerHTML = `
      <div class="tip-inner">
        <div class="tip-header">
          ${headshotHtml}
          <div class="tip-header-info">
            <div class="tip-name">${name}</div>
            <div class="tip-meta">${pos}${mlb ? ' &bull; ' + mlb : ''}${injHtml ? ' ' : ''}${injHtml}</div>
          </div>
        </div>
        <div class="tip-divider"></div>
        ${statsHtml}
      </div>
    `;
  }

  function positionTooltip(e) {
    const OFFSET = 14;
    const TIP_W  = 220;
    const vw     = window.innerWidth;
    const vh     = window.innerHeight;

    tip.style.visibility = 'hidden';
    tip.style.display    = 'block';
    const tipH = tip.offsetHeight;
    tip.style.display    = '';
    tip.style.visibility = '';

    let x = e.clientX + OFFSET;
    let y = e.clientY + OFFSET;

    if (x + TIP_W > vw - 8) x = e.clientX - TIP_W - OFFSET;
    if (y + tipH  > vh - 8) y = e.clientY - tipH - OFFSET;
    if (x < 8) x = 8;
    if (y < 8) y = 8;

    tip.style.left = `${x + window.scrollX}px`;
    tip.style.top  = `${y + window.scrollY}px`;
  }

  function showTip(row, e) {
    clearTimeout(hideTimer);
    if (activeRow === row && tip.classList.contains('tip-visible')) {
      positionTooltip(e);
      return;
    }
    clearTimeout(showTimer);
    showTimer = setTimeout(() => {
      activeRow = row;
      buildTooltip(row);
      positionTooltip(e);
      tip.classList.add('tip-visible');
    }, 120);
  }

  function hideTip() {
    clearTimeout(showTimer);
    hideTimer = setTimeout(() => {
      tip.classList.remove('tip-visible');
      activeRow = null;
    }, 80);
  }

  // ── Event delegation on document ─────────────────────────────────────────
  document.addEventListener('mouseover', function (e) {
    const row = e.target.closest('.player-row');
    if (row) showTip(row, e);
  });

  document.addEventListener('mousemove', function (e) {
    if (activeRow && tip.classList.contains('tip-visible')) {
      positionTooltip(e);
    }
  });

  document.addEventListener('mouseout', function (e) {
    const row = e.target.closest('.player-row');
    if (row && !row.contains(e.relatedTarget)) hideTip();
  });

  // Hide on scroll to avoid stale positioning
  document.addEventListener('scroll', hideTip, { passive: true });
})();
