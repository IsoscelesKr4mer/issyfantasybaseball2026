"""Push live refresh files to GitHub via API (avoids git push to prevent user branch divergence)."""
import os
import sys
import json
import base64
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
env = {}
with open(env_path) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

GITHUB_TOKEN = env["GITHUB_TOKEN"]
GITHUB_REPO = env["GITHUB_REPO"]
REPO_ROOT = Path(__file__).parent.parent

# Files to push
CURRENT_WEEK = int(sys.argv[1]) if len(sys.argv) > 1 else 4
files_to_push = [
    "index.html",
    f"week-{CURRENT_WEEK:02d}.html",
    "teams/buckner.html",
    "teams/busch-latte.html",
    "teams/decoy.html",
    "teams/ete-crow.html",
    "teams/good-vibes.html",
    "teams/keanu.html",
    "teams/one-ball.html",
    "teams/ragans.html",
    "teams/rain-city.html",
    "teams/skenes.html",
]

now_pt = datetime.now()  # sandbox is already PT-aware enough for the commit msg
commit_msg = f"auto: live refresh — {now_pt.strftime('%Y-%m-%d %I:%M %p')} PT"


def gh_api(method, path, data=None):
    url = f"https://api.github.com/repos/{GITHUB_REPO}{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "issy-swingers-refresh",
    }
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.headers.get("Content-Type", "").startswith("application/json") else {"error": str(e)}


def put_file(repo_path, local_path):
    # Get current sha (if file exists on remote)
    status, resp = gh_api("GET", f"/contents/{repo_path}")
    sha = resp.get("sha") if status == 200 else None

    with open(local_path, "rb") as f:
        content_b64 = base64.b64encode(f.read()).decode()

    # Compare: skip if unchanged
    if sha and resp.get("content", "").replace("\n", "") == content_b64:
        return "skipped (unchanged)"

    payload = {
        "message": commit_msg,
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha
    status, resp = gh_api("PUT", f"/contents/{repo_path}", payload)
    if status in (200, 201):
        return f"ok ({resp.get('commit', {}).get('sha', '')[:7]})"
    return f"FAIL {status}: {resp}"


print(f"Pushing {len(files_to_push)} files to {GITHUB_REPO}")
print(f"Commit: {commit_msg}")
print()

results = []
for f in files_to_push:
    local = REPO_ROOT / f
    if not local.exists():
        print(f"  ⚠️  {f} — not found locally, skipping")
        continue
    result = put_file(f, local)
    print(f"  {f}: {result}")
    results.append((f, result))

print()
pushed = sum(1 for _, r in results if r.startswith("ok"))
skipped = sum(1 for _, r in results if r.startswith("skipped"))
failed = sum(1 for _, r in results if r.startswith("FAIL"))
print(f"Done: {pushed} pushed, {skipped} unchanged, {failed} failed")
