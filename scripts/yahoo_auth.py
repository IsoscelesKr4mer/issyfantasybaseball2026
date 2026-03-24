#!/usr/bin/env python3
"""
yahoo_auth.py — One-time OAuth setup for Yahoo Fantasy API.

Run this script ONCE to get your refresh token. After that,
all scheduled scripts use the refresh token automatically.

Usage:
    python3 scripts/yahoo_auth.py
"""

import os
import sys
import base64
import json
import urllib.parse
import urllib.request
from pathlib import Path

# ── Load .env ──────────────────────────────────────────────────────────────────
def load_env():
    env_path = Path(__file__).parent.parent / '.env'
    if not env_path.exists():
        print("❌  .env file not found. Expected at:", env_path)
        sys.exit(1)
    env = {}
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return env

def write_env_value(key, value):
    """Update a single key in the .env file."""
    env_path = Path(__file__).parent.parent / '.env'
    content = env_path.read_text()
    lines = content.splitlines()
    new_lines = []
    for line in lines:
        if line.strip().startswith(f'{key}=') or line.strip() == f'{key}=':
            new_lines.append(f'{key}={value}')
        else:
            new_lines.append(line)
    env_path.write_text('\n'.join(new_lines) + '\n')

# ── Step 1: Build auth URL ─────────────────────────────────────────────────────
def get_auth_url(client_id):
    params = urllib.parse.urlencode({
        'client_id':     client_id,
        'redirect_uri':  'https://localhost',
        'response_type': 'code',
        'language':      'en-us',
    })
    return f'https://api.login.yahoo.com/oauth2/request_auth?{params}'

# ── Step 2: Exchange code for tokens ──────────────────────────────────────────
def exchange_code(client_id, client_secret, code):
    credentials = base64.b64encode(
        f'{client_id}:{client_secret}'.encode()
    ).decode()

    data = urllib.parse.urlencode({
        'grant_type':   'authorization_code',
        'redirect_uri': 'https://localhost',
        'code':         code,
    }).encode()

    req = urllib.request.Request(
        'https://api.login.yahoo.com/oauth2/get_token',
        data=data,
        headers={
            'Authorization': f'Basic {credentials}',
            'Content-Type':  'application/x-www-form-urlencoded',
        },
        method='POST',
    )

    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f'❌  Token exchange failed ({e.code}): {body}')
        sys.exit(1)

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    env = load_env()
    client_id     = env.get('YAHOO_CLIENT_ID', '')
    client_secret = env.get('YAHOO_CLIENT_SECRET', '')

    if not client_id or not client_secret:
        print('❌  YAHOO_CLIENT_ID and YAHOO_CLIENT_SECRET must be set in .env')
        sys.exit(1)

    print('\n' + '═' * 60)
    print('  Issaquah Swingers — Yahoo OAuth Setup')
    print('═' * 60)
    print('\nStep 1: Open this URL in your browser (must be logged into')
    print('        the Yahoo account that owns the fantasy league):\n')
    print(' ', get_auth_url(client_id))
    print('\nStep 2: After you authorize the app, your browser will try')
    print('        to redirect to https://localhost and show an error.')
    print('        That\'s fine. Look at the URL bar — it will look like:')
    print('        https://localhost/?code=XXXXXXXX&...')
    print('\nStep 3: Copy just the code value (between "code=" and "&")')
    print('        and paste it below.\n')

    code = input('Paste the authorization code here: ').strip()
    if not code:
        print('❌  No code entered. Exiting.')
        sys.exit(1)

    print('\n⏳  Exchanging code for tokens...')
    tokens = exchange_code(client_id, client_secret, code)

    refresh_token = tokens.get('refresh_token', '')
    access_token  = tokens.get('access_token', '')

    if not refresh_token:
        print('❌  No refresh token in response:', json.dumps(tokens, indent=2))
        sys.exit(1)

    # Save refresh token to .env
    write_env_value('YAHOO_REFRESH_TOKEN', refresh_token)

    # Also save full token response for reference
    tokens_path = Path(__file__).parent.parent / 'tokens.json'
    tokens_path.write_text(json.dumps(tokens, indent=2))

    print('\n✅  Success!')
    print(f'    Refresh token saved to .env')
    print(f'    Full token response saved to tokens.json (gitignored)')
    print(f'\n    Access token (expires in ~1hr): {access_token[:40]}...')
    print(f'    Refresh token (long-lived):     {refresh_token[:40]}...')
    print('\nNext step: Set your YAHOO_LEAGUE_ID in .env')
    print('  → Go to baseball.fantasysports.yahoo.com')
    print('  → Click your league → look at the URL')
    print('  → e.g. /b1/123456 → league ID is 123456')
    print()

if __name__ == '__main__':
    main()
