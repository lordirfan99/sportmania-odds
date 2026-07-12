"""auto_scraper_v2.py — Clean pipeline using Odds-API.io (Betfair Exchange + 1xBet).

Sources:
  1. Odds-API.io  — Betfair Exchange (back/lay midpoint) + 1xBet odds
     - 5,000 requests/hour free tier
     - 266 bookmakers, including Betfair Exchange with back/lay prices
     - Covers 590+ football leagues

Pipeline: scrape → compute edges → write data.json → deploy
"""

import json
import os
import subprocess
import sys
import hashlib
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# ─── Paths ───
BASE_DIR = Path(__file__).resolve().parent.parent
PUBLIC_DIR = BASE_DIR / "public"
DATA_FILE = PUBLIC_DIR / "data.json"
DIST_DIR = BASE_DIR / "dist"

# ─── Odds-API.io scraper ───
sys.path.insert(0, str(BASE_DIR / "pipeline"))
from scraper_oddsapi import scrape_all, compute_edges


def fmt_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def merge_with_existing(new_matches):
    """Merge new matches into existing data.json, preserving bet history & narratives."""
    existing = {"system_status": {}, "bet_history": [], "matches": []}
    if DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Preserve bet history
    bet_history = existing.get("bet_history", [])

    # Compute stats
    settled = [b for b in bet_history if b.get("settled") and b.get("outcome") in ("WON", "LOST")]
    won = [b for b in settled if b["outcome"] == "WON"]
    total_profit = sum(b.get("profit_rm", 0) for b in settled)
    total_stake = sum(b.get("stake_rm", 0) for b in settled)
    bankroll = existing.get("system_status", {}).get("bankroll_rm", 34.2)

    output = {
        "system_status": {
            "last_updated": fmt_now(),
            "bankroll_rm": bankroll,
            "total_profit_rm": total_profit,
            "total_bets": len(settled),
            "won_bets": len(won),
            "win_rate_pct": round(len(won) / max(len(settled), 1) * 100, 1) if settled else 0,
        },
        "bet_history": bet_history,
        "matches": new_matches,
    }

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\n✅ Written to {DATA_FILE} ({len(new_matches)} matches)")
    return output


def deploy():
    """Build + deploy to Netlify."""
    print(f"\n{'─'*40}")
    print("DEPLOY")
    print(f"{'─'*40}")

    # Copy data.json to dist
    import shutil
    shutil.copy2(DATA_FILE, DIST_DIR / "data.json")

    # Build
    build = subprocess.run(
        "node ./node_modules/vite/bin/vite.js build",
        cwd=str(BASE_DIR),
        capture_output=True, text=True, timeout=120, shell=True,
    )
    if build.returncode != 0:
        print(f"[DEPLOY] ❌ Build failed: {build.stderr[:300]}")
        return False
    print("[DEPLOY] ✅ Build OK")

    # Deploy via Netlify API
    token = os.environ.get("NETLIFY_AUTH_TOKEN", "nfp_fGAN5ehwsHaD87oZmJ24AF2Gvi473ZnQ216c")
    site_id = "3d225a22-04e0-40fa-9629-0fb0f9cb8d40"
    headers = {"Authorization": f"Bearer {token}"}

    # Read files
    file_map = {}
    for root, dirs, fnames in os.walk(str(DIST_DIR)):
        for fname in fnames:
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, str(DIST_DIR)).replace("\\", "/")
            with open(fpath, "rb") as f:
                content = f.read()
            sha1 = hashlib.sha1(content).hexdigest()
            file_map[relpath] = (content, sha1)

    # Create deploy
    files_manifest = {k: v[1] for k, v in file_map.items()}
    r = requests.post(
        f"https://api.netlify.com/api/v1/sites/{site_id}/deploys",
        headers={**headers, "Content-Type": "application/json"},
        json={"files": files_manifest},
        timeout=30,
    )
    d = r.json()
    deploy_id = d.get("id")
    if not deploy_id:
        print(f"[DEPLOY] ❌ Failed: {d.get('error_message', '?')}")
        return False

    # Upload required files
    required = d.get("required", [])
    if required:
        sha_to_path = {v[1]: k for k, v in file_map.items()}
        for sha in required:
            relpath = sha_to_path.get(sha)
            if not relpath:
                continue
            content = file_map[relpath][0]
            put_r = requests.put(
                f"https://api.netlify.com/api/v1/deploys/{deploy_id}/files/{relpath}",
                headers={**headers, "Content-Type": "application/octet-stream"},
                data=content,
                timeout=30,
            )
            if put_r.status_code != 200:
                print(f"  ⚠️ Upload {relpath}: HTTP {put_r.status_code}")

    # Lock deploy
    lock_r = requests.post(
        f"https://api.netlify.com/api/v1/deploys/{deploy_id}/lock",
        headers=headers,
        timeout=15,
    )
    if lock_r.status_code == 200:
        print("[DEPLOY] ✅ Locked")
    else:
        print(f"[DEPLOY] ⚠️ Lock: HTTP {lock_r.status_code}")

    # Wait for ready
    for attempt in range(12):
        time.sleep(5)
        check = requests.get(
            f"https://api.netlify.com/api/v1/deploys/{deploy_id}",
            headers=headers, timeout=10,
        )
        state = check.json().get("state", "")
        print(f"  [{attempt + 1}] {state}")
        if state == "ready":
            pub_time = check.json().get("published_at", "?")
            print(f"\n📡 https://sportmania-betting.netlify.app")
            return True
        if state in ("error", "failed"):
            break
    print("[DEPLOY] ❌ Timed out")
    return False


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    dry_run = "--dry-run" in sys.argv
    do_deploy = "--deploy" in sys.argv
    force = "--force" in sys.argv

    print(f"{'='*60}")
    print(f"AUTO SCRAPER V2 — {fmt_now()}")
    print(f"{'='*60}")

    # Freshness check
    if not force and DATA_FILE.exists():
        try:
            existing = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            last_upd = existing.get("system_status", {}).get("last_updated", "")
            if last_upd:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(last_upd.replace("Z", "+00:00"))
                if age < timedelta(minutes=45):
                    print(f"⏳ Data is {age.seconds//60} min fresh. Use --force to override.\n")
                    return
        except Exception:
            pass

    # ── Scrape ──
    print(f"\n{'─'*40}")
    print("SOURCE: Odds-API.io (Betfair Exchange + 1xBet)")
    print(f"{'─'*40}")

    session = requests.Session()
    session.headers.update({"User-Agent": "SportmaniaOdds/1.0"})

    all_matches = scrape_all(session)
    if not all_matches:
        print("⚠️ No matches from Odds-API.io. Using existing data if available.")
        if DATA_FILE.exists():
            print("📁 Keeping existing data.json")
        return

    # ── Compute edges ──
    print(f"\n{'─'*40}")
    print("COMPUTING EDGES (1xBet vs Betfair Exchange)")
    print(f"{'─'*40}")
    all_matches = compute_edges(all_matches)

    # Print summary
    print(f"\n✅ Merged {len(all_matches)} matches:")
    for m in all_matches[:20]:
        edges = m["analysis"].get("edge_summary", [])
        best = max(edges, key=lambda e: e["edge"]) if edges else None
        edge_str = f"best edge: {best['edge']:+.1f}%" if best else "no edges"
        print(f"  {m['home_team']:25s} vs {m['away_team']:25s} | {m['league_name'][:20]:20s} | {edge_str}")

    # ── Write ──
    if dry_run:
        print("\n⚠️ Dry run — not writing")
        return

    merge_with_existing(all_matches)

    # ── Deploy ──
    if do_deploy:
        deploy()

    print(f"\n{'='*60}")
    print(f"✅ DONE — {fmt_now()}")
    print(f"{'='*60}")


if __name__ == "__main__":
    sys.exit(main())
