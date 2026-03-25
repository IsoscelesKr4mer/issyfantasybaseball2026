/**
 * nav.js — Shared dropdown handling for all pages.
 * Handles open/close for every .nav-dropdown-toggle on the page.
 */
(function () {
  'use strict';

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
})();
