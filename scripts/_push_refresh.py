#!/usr/bin/env python3
"""Push live refresh files to GitHub via Contents API."""
import os, sys, base64, json, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
env = {}
for line in (ROOT / ".env").read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()

TOKEN = env["GITHUB_TOKEN"]
REPO = env["GITHUB_REPO"]
WEEK = int(sys.argv[1]) if len(sys.argv) > 1 else 4

files = ["index.html", f"week-{WEEK:02d}.html"] + [f"teams/{n}" for n in sorted(os.listdir(ROOT / "teams")) if n.endswith(".html")]

now = datetime.now().strftime("%Y-%m-%d %I:%M %p PT")
msg = f"auto: live refresh — {now}"

def api(method, path, data=None):
    url = f"https://api.github.com/repos/{REPO}/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

for rel in files:
    fp = ROOT / rel
    if not fp.exists():
        print(f"skip {rel} (missing)")
        continue
    content_b64 = base64.b64encode(fp.read_bytes()).decode()
    existing = api("GET", f"contents/{rel}")
    payload = {"message": msg, "content": content_b64}
    if existing and "sha" in existing:
        if existing.get("content", "").replace("\n", "") == content_b64:
            print(f"unchanged {rel}")
            continue
        payload["sha"] = existing["sha"]
    api("PUT", f"contents/{rel}", payload)
    print(f"pushed   {rel}")
