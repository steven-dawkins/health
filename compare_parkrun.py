#!/usr/bin/env python3
"""Match parkrun results to Apple Watch workouts (needs summary/runs.csv).

Usage: python3 compare_parkrun.py [parkrun_csv] [runs_csv] [out_csv]
Defaults: parkrun/parkrun_results.csv summary/runs.csv summary/parkrun_vs_workouts.csv

Apple timestamps are UTC, so they are converted to Europe/London before matching.
A parkrun is matched to the 4.5-5.6 km run starting within 45 min of 09:00 local.
Earlier/shorter runs that day are reported as the warm-up/cool-down.
"""
import sys
import pandas as pd

pk_f = sys.argv[1] if len(sys.argv) > 1 else "parkrun/parkrun_results.csv"
runs_f = sys.argv[2] if len(sys.argv) > 2 else "summary/runs.csv"
out_f = sys.argv[3] if len(sys.argv) > 3 else "summary/parkrun_vs_workouts.csv"

pk = pd.read_csv(pk_f, parse_dates=["date"])
runs = pd.read_csv(runs_f, parse_dates=["startDate"])
runs["local"] = runs.startDate.dt.tz_localize("UTC").dt.tz_convert("Europe/London").dt.tz_localize(None)
runs["ld"] = runs.local.dt.normalize()
rec = runs[runs.startDate > runs.startDate.max() - pd.Timedelta(days=1095)]
hrmax = rec.max_hr.quantile(0.995)  # reference max HR from the last 3 years of runs
print(f"Reference max HR (99.5th pct of run max HR, last 3y): {hrmax:.0f}")

def pace(m):
    return f"{int(m)}:{int(round((m % 1) * 60)):02d}"

rows = []
for _, p in pk.iterrows():
    day = runs[runs.ld == p.date]
    start = p.date + pd.Timedelta(hours=9)
    c = day[day.distance_km.between(4.5, 5.6) & ((day.local - start).abs() <= pd.Timedelta(minutes=45))]
    if c.empty:
        continue
    w = c.iloc[(c.local - start).abs().argsort()].iloc[0]
    extras = day.drop(w.name)
    rows.append(dict(date=p.date.date(), official_time=p.time, official_pace_km=pace(p.time_seconds / 60 / 5),
                     start_local=w.local.strftime("%H:%M"), watch_km=round(w.distance_km, 2),
                     watch_min=round(w.minutes, 1), watch_pace=pace(w.pace_min_km),
                     avg_hr=w.avg_hr, max_hr=w.max_hr,
                     avg_hr_pct_max=round(w.avg_hr / hrmax * 100) if pd.notna(w.avg_hr) else None,
                     other_runs_that_day="; ".join(f"{r.distance_km:.1f}km@{r.local:%H:%M}" for _, r in extras.iterrows())))
out = pd.DataFrame(rows)
out.to_csv(out_f, index=False)
print(out.to_string(index=False))
print(f"\nMatched {len(out)}/{len(pk)} parkruns -> {out_f}")
print("Unmatched ones usually pre-date Apple Watch data, or the workout wasn't ~5 km near 09:00.")
