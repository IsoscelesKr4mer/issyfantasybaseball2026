/**
 * api/refresh.js — Vercel serverless function
 *
 * Triggered by the "Refresh Scores" button on the frontend.
 * Fires a repository_dispatch event on GitHub, which kicks off
 * .github/workflows/refresh.yml to pull fresh Yahoo data and redeploy.
 *
 * GITHUB_TOKEN must be set in Vercel project environment variables.
 * It needs repo scope so it can trigger workflow dispatches.
 */

const COOLDOWN_MS = 15 * 60 * 1000; // 15 minutes

// Simple in-memory cooldown so rapid button mashes don't hammer GitHub.
// This resets on cold starts (fine for our purposes).
let lastTriggered = 0;

module.exports = async function handler(req, res) {
  // Only accept POST
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  // Server-side cooldown guard (belt + suspenders alongside the client-side one)
  const now = Date.now();
  const remaining = lastTriggered + COOLDOWN_MS - now;
  if (remaining > 0) {
    return res.status(429).json({
      error: 'Cooldown active',
      retryAfterSeconds: Math.ceil(remaining / 1000),
    });
  }

  const token = process.env.GITHUB_TOKEN;
  const repo  = process.env.GITHUB_REPO || 'IsoscelesKr4mer/issyfantasybaseball2026';

  if (!token) {
    console.error('GITHUB_TOKEN is not set in Vercel environment variables.');
    return res.status(500).json({ error: 'Server not configured' });
  }

  try {
    const response = await fetch(`https://api.github.com/repos/${repo}/dispatches`, {
      method: 'POST',
      headers: {
        Authorization:   `Bearer ${token}`,
        Accept:          'application/vnd.github.v3+json',
        'Content-Type':  'application/json',
        'User-Agent':    'IssaquahSwingers-RefreshBot/1.0',
      },
      body: JSON.stringify({ event_type: 'refresh-scores' }),
    });

    if (response.status === 204) {
      lastTriggered = now;
      return res.status(200).json({ ok: true });
    }

    const body = await response.text();
    console.error('GitHub dispatch failed:', response.status, body);
    return res.status(502).json({ error: 'Failed to trigger refresh' });

  } catch (err) {
    console.error('Fetch error:', err);
    return res.status(500).json({ error: 'Internal error' });
  }
}
