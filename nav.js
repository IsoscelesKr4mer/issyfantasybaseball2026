/**
 * nav.js — Shared dropdown + mobile drawer handling for all pages.
 * Also defines TEAM_LINKS, teamLink(), and linkTeamNames() globally
 * so they are available on every page (index, week-XX, draft, teams).
 */

// ── Team Links (global — used by app.js render functions too) ──
var TEAM_LINKS = {
  'One Ball Two Strikes':        '/teams/one-ball.html',
  'The Buckner Boots':           '/teams/buckner.html',
  'The Ragans Administration':   '/teams/ragans.html',
  'Rain City Bombers':           '/teams/rain-city.html',
  'Decoy':                       '/teams/decoy.html',
  'Ete Crow':                    '/teams/ete-crow.html',
  'Good Vibes Only':             '/teams/good-vibes.html',
  'Busch Latte':                 '/teams/busch-latte.html',
  'Keanu Reeves':                '/teams/keanu.html',
  "Skenes'n on deez Hoerners":   '/teams/skenes.html',
};

function teamLink(name) {
  var href = TEAM_LINKS[name];
  if (!href) return name;
  return '<a href="' + href + '" class="team-link">' + name + '</a>';
}

function linkTeamNames() {
  var selectors = [
    '.matchup-team-name',
    '.matchup-detail-team',
    '.team-cell-name',
    '.mdc-score-name',
    '.team-label',
  ];
  selectors.forEach(function (sel) {
    document.querySelectorAll(sel).forEach(function (el) {
      if (el.closest('a')) return;
      // Normalize curly apostrophe → straight so Skenes lookup works
      var name = el.textContent.trim().replace(/\u2019/g, "'");
      var href = TEAM_LINKS[name];
      if (!href) return;
      el.innerHTML = '<a href="' + href + '" class="team-link">' + el.textContent.trim() + '</a>';
    });
  });

  // Make entire matchup-detail-team-block (headshot + name) clickable as a unit
  document.querySelectorAll('.matchup-detail-team-block').forEach(function (block) {
    var nameEl = block.querySelector('.matchup-detail-team a, .matchup-detail-team');
    if (!nameEl) return;
    var name = nameEl.textContent.trim().replace(/\u2019/g, "'");
    var href = TEAM_LINKS[name];
    if (!href) return;
    block.style.cursor = 'pointer';
    block.addEventListener('click', function (e) {
      if (!e.target.closest('a')) window.location.href = href;
    });
  });

  // Make entire home-page matchup-team block (headshot + name) clickable as a unit
  document.querySelectorAll('.matchup-team').forEach(function (block) {
    var nameEl = block.querySelector('.matchup-team-name a, .matchup-team-name');
    if (!nameEl) return;
    var name = nameEl.textContent.trim().replace(/\u2019/g, "'");
    var href = TEAM_LINKS[name];
    if (!href) return;
    block.style.cursor = 'pointer';
    block.addEventListener('click', function (e) {
      if (!e.target.closest('a')) window.location.href = href;
    });
  });
}

document.addEventListener('DOMContentLoaded', linkTeamNames);

// ── Player Headshots on Team Pages ──
// The generator stores headshot URLs in data-headshot on each .player-row.
// This injects the <img> as the first child so it appears before the name.
function renderPlayerHeadshots() {
  document.querySelectorAll('.player-row[data-headshot]').forEach(function (row) {
    var url = row.getAttribute('data-headshot');
    if (!url) return;
    var img = document.createElement('img');
    img.src = url;
    img.alt = row.getAttribute('data-name') || '';
    img.className = 'player-row-img';
    img.onerror = function () { this.style.display = 'none'; };
    row.insertBefore(img, row.firstChild);
  });
}

document.addEventListener('DOMContentLoaded', renderPlayerHeadshots);

(function () {
  'use strict';

  // Desktop dropdown toggles
  document.querySelectorAll('.nav-dropdown-toggle').forEach(function (toggle) {
    toggle.addEventListener('click', function (e) {
      e.preventDefault();
      var dropdown = this.closest('.nav-dropdown');
      var isOpen = dropdown.classList.contains('open');
      // Close all dropdowns first
      document.querySelectorAll('.nav-dropdown').forEach(function (d) {
        d.classList.remove('open');
      });
      // Then open this one if it wasn't already open
      if (!isOpen) dropdown.classList.add('open');
    });
  });

  // Close any open dropdown when clicking outside the nav
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.nav-dropdown')) {
      document.querySelectorAll('.nav-dropdown').forEach(function (d) {
        d.classList.remove('open');
      });
    }
  });

  // Mobile hamburger — slide-down drawer
  var navToggle = document.querySelector('.nav-toggle');
  var navLinks = document.querySelector('.nav-links');
  if (navToggle && navLinks) {
    navToggle.addEventListener('click', function (e) {
      e.stopPropagation();
      navLinks.classList.toggle('nav-open');
    });
  }

  // Close drawer on outside click
  document.addEventListener('click', function (e) {
    if (navLinks && !e.target.closest('nav')) {
      navLinks.classList.remove('nav-open');
    }
  });

  // Close drawer on Escape key
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && navLinks) {
      navLinks.classList.remove('nav-open');
    }
  });
})();
