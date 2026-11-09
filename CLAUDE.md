# Marathon plan

Goal: build a personalised marathon training plan from the owner's Apple Health history. This repo holds the data pipeline (raw exports -> clean CSVs -> summary) that the plan is based on. See "Target race" below for the race and plan.

## Target race

- **MK Marathon, Monday 3 May 2027** (bank holiday; stadium finish at StadiumMK). Chosen by the owner. Start time not confirmed on the site.
- The MK Half is on the **same day**, so it cannot be a tune-up. Tune-up race (confirmed by the owner): **Milton Keynes Festival of Running, Sunday 28 Mar 2027** (Easter Sunday; half 10:45, 20 Mile 09:50; road, mostly flat, ~165 m climbing). The owner has **chosen the half** (not yet confirmed as entered).
- Goal time deliberately **not fixed**: the owner wants to build speed first. Decision gates are an all-out 5k parkrun on Sat 30 Jan 2027 (owner confirmed available) and the tune-up half on 28 Mar 2027. Plan: `plan/marathon_plan.md` (25 weeks from 9 Nov 2026).
- No injuries after the 18 Oct 2026 marathon. Owner is free to exercise every day and can train as normal over Christmas; the plan uses 6 runs/week plus one rest day.

## Layout

| Path | What it is | In git? |
|---|---|---|
| `apple_health/*.zip` | Raw Apple Health exports (1.4-2.3 GB `export.xml` each). Several overlapping exports, because the owner deletes old data from their phone to free space, so older exports contain data the newest lacks. | No |
| `extract_health.py` | Streams `export.xml` out of every zip, dedupes across exports, writes one CSV per metric. | Yes |
| `health_data/` | Output of `extract_health.py` (~930 MB). One CSV per metric plus `workouts_raw.csv`. | No |
| `summarize_health.py` | Reads `health_data/`, writes per-run, weekly, recovery and monthly summaries plus `report.txt`. | Yes |
| `analyze_run.py` | Per-km/5 km splits for one run from its GPX route + HR/power/form data. Usage: `python3 analyze_run.py <route.gpx> health_data` (extract the single GPX from the zip into a scratch dir first; it lives in `apple_health_export/workout-routes/`). | Yes |
| `parse_parkrun.py` | Parses a parkrun "all results" page **saved from the browser** (`parkrun/all.html`) into `parkrun/parkrun_results.csv`. parkrun.org.uk returns 403 to scripts, so it cannot be fetched automatically; don't try to bypass that. Verified on the real page (40 results, all Abingdon, 2013-2026). | Yes |
| `compare_parkrun.py` | Matches parkruns to Apple workouts (UK local time) -> `summary/parkrun_vs_workouts.csv`. Needs `summary/runs.csv` and `parkrun/parkrun_results.csv`. | Yes |
| `build_schedule.py` | Generates `plan/daily_schedule.md`, the day-by-day schedule (25 weeks x 7 days) whose weekly km match the table in `plan/marathon_plan.md`. Edit the `W`/`FIXED` dicts in the script, not the generated file. | Yes |
| `build_dashboard.py` | Builds the public dashboard `docs/index.html` from `summary/`, `parkrun/` and `plan/marathon_plan.md`, embedding a privacy-filtered data blob in `dashboard/template.html`. Run `python3 build_dashboard.py`, preview with `python3 -m http.server -d docs`. Re-run after each new health export, parkrun update or plan change. | Yes |
| `dashboard/template.html` | Hand-written HTML/SVG/JS dashboard (no external libraries; light + dark; table view per chart). Charts follow the dataviz skill: palette validated, one axis per chart. | Yes |
| `docs/` | **Published to GitHub Pages** (public). Contains only aggregates plus per-run date/distance/pace/avg HR, parkrun date/time/position and the plan. | Yes |
| `summary/` | Output of `summarize_health.py`. Read `summary/report.txt` first for a quick overview. | No |

## Commands

```bash
python3 extract_health.py apple_health health_data   # ~3 min; rerun when a new export is added
python3 summarize_health.py health_data summary      # ~1 min; needs pandas
```

Both default to those paths when run with no arguments from the repo root. Do not extract the zips to disk; the scripts read them in place.

## How the pipeline works (non-obvious decisions)

- **Newest export wins.** Exports are sorted by the `ExportDate` inside each file (not the filename; `export-28-10-26 v2.zip` is newer than `export-28-10-26.zip`). A sample's dedupe key is `(type, startDate, endDate, value, sourceName)`. Anything present only in older exports is still kept.
- Only top-level `<Record>` elements are read (Correlation children are skipped as they duplicate top-level records).
- The set of metrics is `RECORD_TYPES` in `extract_health.py`. Add a HealthKit identifier there to extract more.
- Timestamps are kept as wall-clock time from the export (the `+0000` suffix is dropped). Sleep is assigned to the date you woke up.
- Sleep is the union of overlapping "asleep" intervals (Core/Deep/REM/Unspecified) so iPhone and Watch sources are not double counted. `InBed` and `Awake` are excluded.
- Run distance comes from `totalDistance` when present, otherwise `DistanceWalkingRunning_sum` from the workout statistics (old Strava imports; assumed km). Runs under 0.5 km or 3 min are dropped.
- **Aerobic efficiency** = metres per heartbeat (`distance / (minutes * avg HR)`); higher means fitter. Compared per quarter using runs of 20+ min.
- Weeks start on Monday.

## Data caveats

- Coverage starts at different dates per metric (see `summary/data_coverage.csv`): workouts 2014, sleep 2017, resting HR and heart rate 2020, VO2 max / HRV 2022, running power and form metrics 2023. Don't draw conclusions about trends before a metric's start date.
- Deleted history means gaps are possible even inside the covered range; check coverage before trusting a long-range trend.
- Apple's VO2 max is an estimate: use direction, not absolute values. Resting HR and HRV matter as trends against the 28-day baseline, not single days.
- `active_energy.csv` is ~1M rows (mostly from the oldest export) and is only a rough load measure.

## Training context learned from the data (as of 2026-10-31)

- Recent volume: about 63-64 km/week average over the last 8-12 weeks, peak week 94.8 km (week of 2026-09-13), typically 5-6 runs/week.
- 2026-10-18 was a **race** (confirmed by the owner): a 42.6 km run at 5:04/km, avg HR 154, the longest run on record. The low-mileage weeks since are post-race recovery, so the next plan should build up from there, not start at the 60-90 km weeks. The workout record says 42.6 km but the GPS track measures 42.17 km (the course), so true average pace is ~5:06/km, official finish 3:35:36 (watch recorded 3:35:30). Which race it was is not recorded yet.
- VO2 max rose from ~50 to ~56 over 2025-11 to 2026-07 and has been ~55 since.
- Resting HR is ~47 bpm; HRV ~55-58 ms.

## parkrun history

40 parkruns at Abingdon, 2013-07-06 to 2026-03-28 (`parkrun/parkrun_results.csv`; sparse, none since 2026-03-28). PB 19:43 (2013-07-20). Most recent: 21:16 (2026-03-14) and 21:18 (2026-03-28), ~4:15/km. Workout data shows these are hard efforts (see below), so they are a reasonable 5 km fitness marker.

Parkrun vs Apple workouts (18 of 40 matched; older ones pre-date Watch data): parkruns are genuine hard efforts (avg HR 85-94% of ~187 max, ~1.8 km warm-up first). The 2026-03-14 21:16 was the hardest (avg HR 176, 94%); 2026-03-28 gave 21:18 at HR 163, so 5 km fitness was ~21:15 or slightly better in March 2026. Watch GPS reads ~4.85-4.95 km on the course, so official pace is ~4:15/km vs the ~4:22 shown.

## Race analysis (2026-10-18)

Even ~5:00/km to km 30, slight fade km 31-34 (5:05), then collapse from km 35 (5:17 -> 5:52 by km 42; last 7 km ~5:30). HR fell (164 -> 154 bpm) while power fell 240 -> 210 W and stride shortened 1.16 -> 0.98 m with cadence unchanged (~173 spm) and ground contact rising: leg fatigue/durability, not a cardiovascular ceiling. HR climbed ~20 bpm at constant pace between km 20 and 29 (cardiac drift). Km 6-10 HR (165-169) looks like a sensor artifact. Cost ~4-5 min vs holding 4:59. Fuelling cannot be judged from this data.

## Conventions

- `docs/` is public by design; keep `build_dashboard.py`'s privacy allowlist strict: never add routes, locations/venues, start times, device or source names, body weight or raw samples to it.
- The health data is personal. Never commit `apple_health/`, `health_data/`, `summary/` or `parkrun/` (they are in `.gitignore`), and don't paste raw rows into issues or messages.
- Keep scripts dependency-light: standard library for extraction, pandas for summarising.
