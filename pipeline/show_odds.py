"""Show full detailed market odds from 1xBet + 12Play + API"""
import json, cloudscraper, re, time, tempfile
from pathlib import Path

BASE_DIR = Path("C:/Users/irfan/betting-dashboard")

# ═══ 1XBET ═══
print("=" * 80)
print("  1XBET MALAYSIA — FULL MARKET ODDS (via API)")
print("=" * 80)

scraper = cloudscraper.create_scraper()
scraper.headers.update({
    "User-Agent": "Mozilla/5.0 Chrome/132.0.0.0",
    "Accept": "*/*",
    "Referer": "https://1xbet-malaysia.mobi/en/line/football",
})

XMATCH = {
    "eng_nor_03": 734357671,
    "arg_sui_04": 734782375,
    "fra_spa_05": 735504550,
}
NAMES = {
    "eng_nor_03": ("Norway", "England"),
    "arg_sui_04": ("Argentina", "Switzerland"),
    "fra_spa_05": ("France", "Spain"),
}

def vig_free(odds):
    t = sum(1 / x for x in odds if x > 0)
    return [(1 / x) / t * 100 if x > 0 else 0 for x in odds] if t > 0 else [0] * len(odds)

def edge_icon(e):
    return "🚀" if e > 20 else "✅" if e >= 5 else "⚪" if e >= -5 else "❌"

def parse_xbet(value):
    e_arr = value.get("E", [])
    r = {"h1": 0, "hX": 0, "h2": 0, "ah_home": 0, "ah_away": 0, "over": 0, "under": 0, "ou_point": 2.5}
    for item in e_arr:
        t, g, c, p = item.get("T"), item.get("G"), item.get("C", 0), item.get("P")
        if g == 1 and t in (1, 2, 3):
            if t == 1: r["h1"] = c
            elif t == 2: r["hX"] = c
            elif t == 3: r["h2"] = c
        if p == 2.5:
            if t == 9: r["under"] = c
            elif t == 10: r["over"] = c
    h, d, a = r["h1"], r["hX"], r["h2"]
    if h > 0: r["ah_home"] = h
    if a > 0 and d > 0:
        imp = 1 / a + 1 / d
        r["ah_away"] = round(1 / imp, 3) if imp > 0 else a
    elif a > 0:
        r["ah_away"] = a
    return r

matches = []
for mid, aid in XMATCH.items():
    r = scraper.get(
        f"https://1xbet-malaysia.mobi/service-api/LineFeed/GetGameZip?id={aid}&lng=en",
        timeout=10,
    )
    d = r.json()
    if not d.get("Success"):
        print(f"  ❌ {mid}: API failed")
        continue
    odds = parse_xbet(d["Value"])
    h_name, a_name = NAMES[mid]
    matches.append({"id": mid, "home": h_name, "away": a_name, "odds": odds})

for m in matches:
    o = m["odds"]
    vf = vig_free([o["h1"], o["hX"], o["h2"]])
    vf_ou = vig_free([o["over"], o["under"]]) if o["over"] > 0 else [50, 50]

    ah_home_p = vf[0]
    ah_away_p = vf[1] + vf[2]
    over_p, under_p = vf_ou[0], vf_ou[1]

    he = round((ah_home_p / 100 * o["ah_home"] - 1) * 100, 1) if o["ah_home"] > 0 else 0
    ae = round((ah_away_p / 100 * o["ah_away"] - 1) * 100, 1) if o["ah_away"] > 0 else 0
    oe = round((over_p / 100 * o["over"] - 1) * 100, 1) if o["over"] > 0 else 0
    ue = round((under_p / 100 * o["under"] - 1) * 100, 1) if o["under"] > 0 else 0

    vig1 = round((1 / o["h1"] + 1 / o["hX"] + 1 / o["h2"] - 1) * 100, 2)

    print(f"\n{'─' * 70}")
    print(f"  {m['home']:15s} vs {m['away']:15s}  [{m['id']}]")
    print(f"{'─' * 70}")
    print(f"  {'MARKET':25s} {'ODDS':>8s} {'IMPLIED':>8s} {'FAIR':>8s} {'EDGE':>8s}")
    print(f"  {'─' * 60}")
    print(f"  {m['home']+' -0.5 (AH)':25s} {o['ah_home']:>8.3f} {100/o['ah_home']:>7.1f}% {ah_home_p:>7.1f}% {he:>+7.1f}%  {edge_icon(he)}")
    print(f"  {m['away']+' +0.5 (AH)':25s} {o['ah_away']:>8.3f} {100/o['ah_away']:>7.1f}% {ah_away_p:>7.1f}% {ae:>+7.1f}%  {edge_icon(ae)}")
    print(f"  {'─' * 60}")
    print(f"  {m['home']+' (W1)':25s} {o['h1']:>8.3f} {100/o['h1']:>7.1f}% {vf[0]:>7.1f}%")
    print(f"  {'Draw (X)':25s} {o['hX']:>8.3f} {100/o['hX']:>7.1f}% {vf[1]:>7.1f}%")
    print(f"  {m['away']+' (W2)':25s} {o['h2']:>8.3f} {100/o['h2']:>7.1f}% {vf[2]:>7.1f}%")
    print(f"  {'─' * 60}")
    if o["over"] > 0:
        print(f"  {'Over '+str(o['ou_point']):25s} {o['over']:>8.3f} {100/o['over']:>7.1f}% {over_p:>7.1f}% {oe:>+7.1f}%  {edge_icon(oe)}")
        print(f"  {'Under '+str(o['ou_point']):25s} {o['under']:>8.3f} {100/o['under']:>7.1f}% {under_p:>7.1f}% {ue:>+7.1f}%  {edge_icon(ue)}")
    print(f"  {'─' * 60}")
    print(f"  VIG (1X2): {vig1:.2f}%  |  VIG (O/U): {round((1/o['over']+1/o['under']-1)*100,2) if o['over']>0 else 0:.2f}%")
    print(f"  SOURCE: 1xBet Malaysia")

# ═══ 12PLAY ═══
print(f"\n{'=' * 80}")
print("  12PLAY MY — 12PSports Odds")
print("=" * 80)
print("(Attempting headless scrape...)")

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")
    ud = tempfile.mkdtemp()
    options.add_argument(f"--user-data-dir={ud}")

    driver = uc.Chrome(options=options, headless=True, use_subprocess=True, version_main=149)
    driver.get("https://www.12play21.com/en-MY/login")
    time.sleep(2)
    driver.find_element(By.NAME, "username").send_keys("lordirfan")
    driver.find_element(By.NAME, "password").send_keys("lordirfan")
    driver.find_element(By.XPATH, "//button[contains(text(), 'Login')]").click()
    time.sleep(3)
    driver.get("https://www.12psports.com/game.php?currency=MYR&platform_origin=www.12play21.com")

    found = False
    for i in range(10):
        html = driver.page_source
        body = re.sub(r"<[^>]+>", " ", html)
        body = re.sub(r"\s+", " ", body)
        pat = r"(Norway|England|Argentina|Switzerland|France|Spain|Belgium)\s+(Norway|England|Argentina|Switzerland|France|Spain|Belgium)\s+1\s+(-?[\d.]+)\s+X\s+(-?[\d.]+)\s+2\s+(-?[\d.]+)"
        matches = re.findall(pat, body)
        if matches:
            for mt in matches:
                def malay2dec(m):
                    v = float(m)
                    return round(1 + (1 / abs(v)), 3) if v < 0 else round(1 + v, 3)
                h_dec = malay2dec(mt[2])
                d_dec = malay2dec(mt[3])
                a_dec = malay2dec(mt[4])
                print(f"\n  {mt[0]:15s} vs {mt[1]:15s}")
                print(f"  {'─' * 50}")
                print(f"  Malay odds:   1={mt[2]:>8s}  X={mt[3]:>8s}  2={mt[4]:>8s}")
                print(f"  Decimal:      {h_dec:>8.3f}  {d_dec:>8.3f}  {a_dec:>8.3f}")
                vf12 = vig_free([h_dec, d_dec, a_dec])
                print(f"  Fair value:   {vf12[0]:>7.1f}%  {vf12[1]:>7.1f}%  {vf12[2]:>7.1f}%")
                print(f"  SOURCE: 12Play (12PSports)")
            found = True
            break
        time.sleep(3)

    if not found:
        print("  ⚠️ No odds data rendered (anti-bot detection)")
    driver.quit()
except Exception as e:
    print(f"  ⚠️ 12Play scrape failed: {e}")

# ═══ API ═══
print(f"\n{'=' * 80}")
print("  THE-ODDS-API (Pinnacle/Matchbook)")
print("=" * 80)
api_key = "b45c8f0693e8a7912baf2449e98d6fb8"
import requests
r = requests.get(
    f"https://api.the-odds-api.com/v4/sports/soccer_fifa_world_cup/odds/"
    f"?apiKey={api_key}&regions=eu&markets=h2h,spreads,totals&oddsFormat=decimal",
    timeout=15,
)
if r.status_code == 200:
    for m in r.json():
        ht, at = m["home_team"], m["away_team"]
        print(f"\n  {ht:15s} vs {at:15s}")
        best = None
        for bm in m.get("bookmakers", []):
            if bm["title"] in ("Pinnacle", "Matchbook", "BetOnline.ag"):
                best = bm
                break
        if best:
            print(f"  Bookmaker: {best['title']}")
            for mk in best.get("markets", []):
                outcomes = {o["name"]: o for o in mk["outcomes"]}
                if mk["key"] == "h2h":
                    h = outcomes.get(ht, {}).get("price", 0)
                    d = outcomes.get("Draw", {}).get("price", 0)
                    a = outcomes.get(at, {}).get("price", 0)
                    print(f"  1X2:  {h:.3f} / {d:.3f} / {a:.3f}")
                elif mk["key"] == "spreads":
                    hs = outcomes.get(ht, {})
                    aws = outcomes.get(at, {})
                    print(f"  AH:  {ht} {hs.get('point','?')} @ {hs.get('price','?'):<8s} | {at} {aws.get('point','?')} @ {aws.get('price','?')}")
                elif mk["key"] == "totals":
                    ov = outcomes.get("Over", {})
                    ud = outcomes.get("Under", {})
                    print(f"  O/U: {ov.get('point','2.5')} O @ {ov.get('price','?'):<8s} U @ {ud.get('price','?')}")
        else:
            print("  No Pinnacle/Matchbook data")
else:
    print(f"  HTTP {r.status_code}")

print(f"\n{'=' * 80}")
print("  DONE")
print(f"{'=' * 80}")
