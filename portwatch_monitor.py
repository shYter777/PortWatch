"""
PortWatch - monitoring ship transits through chokepoint6 (Strait of Hormuz)
Runs continuously, checks every 5-15 sec, alerts when new data arrives.
Update time: Tuesdays 9 AM ET = 13:00 UTC = 15:00 Madrid

Usage: python portwatch_monitor.py
Stop:  Ctrl+C
"""

import urllib.request
import urllib.parse
import json
import random
import time
from datetime import date, datetime, timezone

# --- Settings -----------------------------------------------------------------

BASE_URL = (
    "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
    "/Daily_Chokepoints_Data/FeatureServer/0/query"
)

CHOKEPOINT_ID   = "chokepoint6"
SHOW_LAST_DAYS  = 14
TIMEOUT         = 30

WEEK_START      = "2026-04-06"
WEEK_END        = "2026-04-12"

# --- HTTP ---------------------------------------------------------------------

def fetch_json(params):
    full_url = BASE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        full_url,
        headers={"User-Agent": "Mozilla/5.0 PortWatch-Monitor/1.0"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode())

def ms_to_date(ms):
    return datetime.utcfromtimestamp(ms / 1000).strftime("%Y-%m-%d")

# --- API calls ----------------------------------------------------------------

def get_latest_date():
    """Quick check - only fetches 1 record."""
    data = fetch_json({
        "where":             f"portid='{CHOKEPOINT_ID}'",
        "outFields":         "date",
        "orderByFields":     "date DESC",
        "resultRecordCount": 1,
        "returnGeometry":    "false",
        "f":                 "json",
    })
    if "error" in data:
        raise RuntimeError(f"API error: {data['error']}")
    feats = data.get("features", [])
    if not feats:
        raise RuntimeError("No data")
    return ms_to_date(feats[0]["attributes"]["date"])


def get_recent_data():
    """Full fetch - last N days with all vessel counts."""
    data = fetch_json({
        "where":             f"portid='{CHOKEPOINT_ID}'",
        "outFields":         "date,n_total,n_container,n_dry_bulk,"
                             "n_general_cargo,n_roro,n_tanker",
        "orderByFields":     "date DESC",
        "resultRecordCount": SHOW_LAST_DAYS,
        "returnGeometry":    "false",
        "f":                 "json",
    })
    if "error" in data:
        raise RuntimeError(f"API error: {data['error']}")

    rows = []
    for f in data.get("features", []):
        a = f["attributes"]
        total = a.get("n_total") or (
            (a.get("n_container")     or 0) +
            (a.get("n_dry_bulk")      or 0) +
            (a.get("n_general_cargo") or 0) +
            (a.get("n_roro")          or 0) +
            (a.get("n_tanker")        or 0)
        )
        rows.append({
            "date":  ms_to_date(a["date"]),
            "total": int(total),
            "cont":  int(a.get("n_container")     or 0),
            "bulk":  int(a.get("n_dry_bulk")      or 0),
            "gnrl":  int(a.get("n_general_cargo") or 0),
            "roro":  int(a.get("n_roro")          or 0),
            "tank":  int(a.get("n_tanker")        or 0),
        })
    rows.reverse()
    return rows

# --- Display ------------------------------------------------------------------

def show_full_report(rows):
    today   = date.today()
    latest  = rows[-1]["date"]
    lag     = (today - datetime.strptime(latest, "%Y-%m-%d").date()).days
    lag_str = {0: "today", 1: "yesterday"}.get(lag, f"{lag} days ago")

    print(f"\nPortWatch Monitor [{CHOKEPOINT_ID}]  |  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print(f"Latest date in DB : {latest}  ({lag_str})")
    print()

    max_total = max(r["total"] for r in rows) or 1
    print(f"{'Date':<12} {'Total':>5}  {'cont':>4} {'bulk':>4} {'gnrl':>4} {'roro':>4} {'tank':>4}   Chart")
    print("-" * 60)
    for row in rows:
        d   = row["date"]
        n   = row["total"]
        bar = "=" * int(n / max_total * 20)
        mrk = " <--" if d == latest else ""
        print(f"{d:<12} {n:>5}  {row['cont']:>4} {row['bulk']:>4} {row['gnrl']:>4} {row['roro']:>4} {row['tank']:>4}   {bar}{mrk}")

    # --- Polymarket week block ------------------------------------------------
    week_rows  = [r for r in rows if WEEK_START <= r["date"] <= WEEK_END]
    week_total = sum(r["total"] for r in week_rows)
    missing    = 7 - len(week_rows)

    print("=" * 60)
    print(f"  Polymarket week {WEEK_START} - {WEEK_END}")
    print(f"  ---------------------------------------------------")
    if week_rows:
        print(f"  Days with data : {len(week_rows)}/7")
        for r in week_rows:
            print(f"    {r['date']}  {r['total']:>3} ships")
        print(f"  ---------------------------------------------------")
        print(f"  TOTAL so far   : {week_total}")
        if missing > 0:
            avg = week_total / len(week_rows)
            est = int(week_total + avg * missing)
            print(f"  Missing days   : {missing}  (avg {avg:.1f}/day)")
            print(f"  Projected total: ~{est}")
        else:
            print(f"  WEEK COMPLETE  : {week_total} ships")
    else:
        print(f"  No data for this week yet")
    print("=" * 60)

    # macOS notification
    if lag <= 3:
        try:
            import subprocess
            subprocess.run([
                "osascript", "-e",
                f'display notification "New data up to {latest}" with title "PortWatch {CHOKEPOINT_ID}"'
            ], capture_output=True)
        except Exception:
            pass

# --- Main loop ----------------------------------------------------------------

if __name__ == "__main__":
    print("PortWatch continuous monitor")
    print(f"Chokepoint : {CHOKEPOINT_ID} (Strait of Hormuz)")
    print(f"Polymarket : {WEEK_START} to {WEEK_END}")
    print(f"Update time: Tuesday 9 AM ET = 13:00 UTC = 15:00 Madrid/Girona")
    print("Press Ctrl+C to stop\n")

    last_seen = None

    while True:
        try:
            latest = get_latest_date()
            now    = datetime.now().strftime("%H:%M:%S")

            if latest != last_seen:
                # New data - show full report
                rows = get_recent_data()
                show_full_report(rows)
                last_seen = latest

                # Stop if full week is available
                if latest >= WEEK_END:
                    print("\nFull week data available. Monitoring complete.")
                    break
            else:
                print(f"[{now}] No update. Latest: {latest}", end="\r", flush=True)

        except KeyboardInterrupt:
            print("\nStopped.")
            break
        except Exception as e:
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n[{now}] Error: {e} - retrying in 30s")
            time.sleep(30)
            continue

        # Random delay 5-15 seconds
        delay = random.uniform(5, 15)
        time.sleep(delay)