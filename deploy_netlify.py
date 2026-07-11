"""Deploy to Netlify — manifest + file upload + lock."""
import hashlib, os, sys, requests, time

TOKEN = os.environ.get("NETLIFY_AUTH_TOKEN", "nfp_fGAN5ehwsHaD87oZmJ24AF2Gvi473ZnQ216c")
SITE_ID = "3d225a22-04e0-40fa-9629-0fb0f9cb8d40"
DIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")

ha = {"Authorization": f"Bearer {TOKEN}"}

# Read all files
print("=== Reading files ===")
file_map = {}  # path -> (content, sha256)
for root, dirs, fnames in os.walk(DIST_DIR):
    for fname in fnames:
        fpath = os.path.join(root, fname)
        relpath = os.path.relpath(fpath, DIST_DIR).replace("\\", "/")
        with open(fpath, "rb") as f:
            content = f.read()
        sha256 = hashlib.sha256(content).hexdigest()
        file_map[relpath] = (content, sha256)
        print(f"  {relpath}: {sha256[:16]}... ({len(content)} bytes)")

# Create deploy
files_manifest = {k: v[1] for k, v in file_map.items()}
print(f"\n=== Creating deploy ({len(files_manifest)} files) ===")
resp = requests.post(
    f"https://api.netlify.com/api/v1/sites/{SITE_ID}/deploys",
    headers={**ha, "Content-Type": "application/json"},
    json={"files": files_manifest},
    timeout=30
)
d = resp.json()
deploy_id = d.get("id")
print(f"Deploy ID: {deploy_id}")
print(f"State: {d.get('state')}")
print(f"Required: {d.get('required')}")
print(f"Error: {d.get('error_message', '(none)')}")

if not deploy_id or d.get("error_message"):
    print("❌ Failed to create deploy")
    sys.exit(1)

# Upload required files
required = d.get("required", [])
if required:
    # Build reverse map: sha256 -> path
    sha_to_path = {v[1]: k for k, v in file_map.items()}
    
    # Check all SHAs are known
    missing = [sha for sha in required if sha not in sha_to_path]
    if missing:
        print(f"⚠️  Unknown SHA hashes: {len(missing)}")
    
    print(f"\n=== Uploading {len(required)} files ===")
    uploaded = 0
    for sha in required:
        relpath = sha_to_path.get(sha)
        if not relpath:
            print(f"  SKIP (no path): {sha[:16]}...")
            continue
        content = file_map[relpath][0]
        put_resp = requests.put(
            f"https://api.netlify.com/api/v1/deploys/{deploy_id}/files/{sha}",
            headers={**ha, "Content-Type": "application/octet-stream"},
            data=content,
            timeout=30
        )
        if put_resp.status_code == 200:
            uploaded += 1
            print(f"  ✅ {relpath} (by SHA)")
        else:
            # Try uploading by path
            put_resp2 = requests.put(
                f"https://api.netlify.com/api/v1/deploys/{deploy_id}/files/{relpath}",
                headers={**ha, "Content-Type": "application/octet-stream"},
                data=content,
                timeout=30
            )
            if put_resp2.status_code == 200:
                uploaded += 1
                print(f"  ✅ {relpath} (by path)")
            else:
                print(f"  ❌ {relpath}: SHA={put_resp.status_code} Path={put_resp2.status_code}")
                print(f"     SHA err: {put_resp.text[:100]}")
                print(f"     Path err: {put_resp2.text[:100]}")
    print(f"\nUploaded {uploaded}/{len(required)}")
else:
    print("\n=== No files need uploading (cached) ===")

# Lock to trigger processing
print("\n=== Locking deploy ===")
lock_resp = requests.post(
    f"https://api.netlify.com/api/v1/deploys/{deploy_id}/lock",
    headers=ha,
    timeout=30
)
if lock_resp.status_code == 200:
    print("  ✅ Locked")
else:
    print(f"  ⚠️ Lock response: {lock_resp.status_code} {lock_resp.text[:200]}")

# Wait for ready
print("\n=== Waiting for deploy ===")
for i in range(30):
    time.sleep(4)
    r = requests.get(f"https://api.netlify.com/api/v1/deploys/{deploy_id}", headers=ha)
    rd = r.json()
    s = rd.get("state", "")
    pub = rd.get("published_at")
    err = rd.get("error_message")
    print(f"  [{i+1}] {s}" + (f" ✅ pub={pub}" if pub else "") + (f" ❌ {err}" if err else ""))
    if s == "ready" or pub:
        break
    if err:
        break

print(f"\n📡 https://sportmania-betting.netlify.app")
