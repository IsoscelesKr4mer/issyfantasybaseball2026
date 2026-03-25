/**
 * nav.js — Shared dropdown + mobile drawer handling for all pages.
 */
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
