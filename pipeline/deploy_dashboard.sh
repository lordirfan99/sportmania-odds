#!/bin/bash
# pipeline/deploy_dashboard.sh — Build + Deploy betting dashboard to Netlify
# Called by odds_pipeline.py or directly from cron

set -e
cd "$(dirname "$0")/.."

echo "=== Deploy Dashboard ==="
echo "Dir: $(pwd)"
echo "Time: $(date -u +%Y-%m-%dT%H:%M:%SZ)"

# 1. Ensure data.json exists
if [ ! -f public/data.json ]; then
    echo "ERROR: public/data.json not found!"
    exit 1
fi
echo "data.json: $(wc -c < public/data.json) bytes"

# 2. Build
echo "=== npm run build ==="
npm run build 2>&1 || { echo "BUILD FAILED"; exit 1; }

# 3. Deploy
echo "=== netlify deploy ==="
npx netlify deploy --prod --dir=dist 2>&1

echo "=== DONE ==="
