"""RupeeWatch data pipeline: Extract -> Transform -> Load.
Runs inside GitHub Actions and writes its results into the /data folder."""
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

CURRENCIES = ["USD", "EUR", "GBP", "SGD", "AUD"]  # add or remove currency codes here
START_DATE = "2026-01-01"                          # history starts on this date
API = "https://api.frankfurter.dev/v2/rates"

# ---------- 1. EXTRACT: call the API (same GET request you test in Postman) ----------
def fetch(code):
    url = f"{API}?base={code}&quotes=INR&from={START_DATE}"
    req = urllib.request.Request(url, headers={"User-Agent": "rupeewatch-student-project"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)

raw = {code: fetch(code) for code in CURRENCIES}

os.makedirs("data/raw", exist_ok=True)
with open("data/raw/frankfurter_raw.json", "w") as f:  # raw layer: untouched API response
    json.dump(raw, f)

# ---------- 2. TRANSFORM: clean the data and add calculated columns ----------
series, rows = {}, []
for code, records in raw.items():
    clean = {}
    for r in records:  # drop empty or invalid rates, keep one value per date
        if r.get("quote") == "INR" and r.get("rate"):
            clean[r["date"]] = float(r["rate"])

    prev, window, out = None, [], []
    for day in sorted(clean):
        rate = clean[day]
        window = (window + [rate])[-7:]  # last 7 values for the moving average
        out.append({
            "date": day,
            "inr_per_unit": round(rate, 4),
            "change_pct": round((rate - prev) / prev * 100, 3) if prev else 0.0,
            "ma7": round(sum(window) / len(window), 4),
        })
        prev = rate

    if not out:  # data-quality check: stop so the Action run turns red
        sys.exit(f"No valid data for {code}. Stopping.")
    series[code] = out
    rows += [{"currency": code, **o} for o in out]

# ---------- 3. LOAD: save the clean data (this is what the website reads) ----------
with open("data/rates.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["date", "currency", "inr_per_unit", "change_pct", "ma7"])
    writer.writeheader()
    writer.writerows(rows)

with open("data/rates.json", "w") as f:
    json.dump({
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "unit": "INR per 1 unit of the currency",
        "series": series,
    }, f)

print(f"Saved {len(rows)} rows for {', '.join(CURRENCIES)}")
