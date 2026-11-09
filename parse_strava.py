#!/usr/bin/env python3
"""Extract runs from a Strava bulk export zip into strava_data/strava_runs.csv.

Usage: python3 parse_strava.py [strava_data/export_*.zip] [strava_data/strava_runs.csv]

Reads activities.csv from the zip in place (nothing else in the archive is touched:
messages, contacts, routes and media are ignored). Columns kept: start (UTC), km,
minutes, pace, avg/max HR, name omitted on purpose.
"""
import csv, glob, io, sys, zipfile
from datetime import datetime

# activities.csv has duplicate header names, so use positions (verified against the header).
COLS = {"date": 1, "type": 3, "elapsed_s": 5, "dist_km": 6, "moving_s": 16, "avg_hr": 31}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else (sorted(glob.glob("strava_data/export_*.zip")) or [None])[-1]
    out = sys.argv[2] if len(sys.argv) > 2 else "strava_data/strava_runs.csv"
    if not src:
        sys.exit("No strava_data/export_*.zip found")
    with zipfile.ZipFile(src) as z:
        rows = list(csv.reader(io.StringIO(z.read("activities.csv").decode("utf-8"))))
    h = rows[0]
    expect = {1: "Activity Date", 3: "Activity Type", 5: "Elapsed Time", 6: "Distance", 16: "Moving Time", 31: "Average Heart Rate"}
    for i, name in expect.items():
        if h[i] != name:
            sys.exit(f"Unexpected activities.csv layout: column {i} is {h[i]!r}, expected {name!r}")
    n = 0
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["startDate", "distance_km", "minutes", "pace_min_km", "avg_hr"])
        for r in rows[1:]:
            if r[3] != "Run":
                continue
            try:
                start = datetime.strptime(r[1], "%b %d, %Y, %I:%M:%S %p")
                km = float(r[6].replace(",", "")) if r[6] else 0.0
                secs = float(r[16] or r[5] or 0)
            except ValueError:
                continue
            if km <= 0.5 or secs < 180:
                continue
            hr = r[31].strip()
            mins = secs / 60
            w.writerow([start.strftime("%Y-%m-%d %H:%M:%S"), f"{km:.3f}", f"{mins:.2f}", f"{mins / km:.3f}", hr])
            n += 1
    print(f"{n} runs -> {out}")


if __name__ == "__main__":
    main()
