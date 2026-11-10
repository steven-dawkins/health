# Marathon plan

A personalised training plan for the **MK Marathon, Monday 3 May 2027**, built from my own Apple Health, parkrun and Strava history, plus a public dashboard that tracks progress against it.

Live dashboard: https://steven-dawkins.github.io/health/

## What's in it

- **Data pipeline.** Raw Apple Health exports are turned into per-metric CSVs, then into run, weekly, recovery and monthly summaries. Strava runs fill gaps in the Apple history, and parkrun results are matched to workouts.
- **The plan.** 25 weeks from Mon 9 Nov 2026, with two decision gates (a 5k on 30 Jan 2027 and a half marathon on 28 Mar 2027) that set the goal time. See `plan/marathon_plan.md` for the strategy and `plan/daily_schedule.md` for the day-by-day schedule with estimated times.
- **Dashboard.** A static, dependency-free HTML page (overview, recovery, fitness, plan, day-by-day, runs) published from `docs/` with GitHub Pages.

`CLAUDE.md` has the detailed design notes and data caveats.

## Layout

| Path | Purpose |
|---|---|
| `extract_health.py` | Streams Apple Health zips into one CSV per metric (`health_data/`) |
| `summarize_health.py` | Builds run, weekly, recovery and monthly summaries (`summary/`) |
| `parse_parkrun.py` | Parses a saved parkrun results page into `parkrun/parkrun_results.csv` |
| `parse_strava.py` | Reads runs from the Strava bulk-export zip into `strava_data/strava_runs.csv` |
| `compare_parkrun.py` | Matches parkruns to Apple workouts |
| `analyze_run.py` | Per-km splits for one run from its GPX route |
| `build_schedule.py` | Generates `plan/daily_schedule.md` |
| `build_dashboard.py` + `dashboard/template.html` | Builds `docs/index.html` |
| `plan/` | The plan and day-by-day schedule |
| `docs/` | Published dashboard (public) |

## Requirements

Python 3 and `pandas`. Everything else is the standard library.

## View the dashboard locally

```bash
python3 build_dashboard.py       # rebuild docs/index.html (needs summary/ and parkrun/)
python3 -m http.server -d docs   # then open http://localhost:8000
```

Tabs can be opened directly, for example `http://localhost:8000/#daily`. You can also open `docs/index.html` in a browser without a server.

## Updating

Raw data is personal and git-ignored: `apple_health/`, `health_data/`, `summary/`, `parkrun/` and `strava_data/` are never committed.

**New Apple Health export**

1. Drop the zip into `apple_health/` (keep older exports; the newest wins and older ones fill gaps).
2. Run:

   ```bash
   python3 extract_health.py apple_health health_data   # ~3 min
   python3 summarize_health.py health_data summary      # ~1 min
   python3 build_dashboard.py
   ```

**New parkrun results.** Save the "all results" page from your browser as `parkrun/all.html` (parkrun blocks scripts), then:

```bash
python3 parse_parkrun.py parkrun/all.html parkrun/parkrun_results.csv
python3 compare_parkrun.py
python3 summarize_health.py health_data summary
python3 build_dashboard.py
```

**New Strava export.** Put the bulk-export zip in `strava_data/`, then:

```bash
python3 parse_strava.py
python3 summarize_health.py health_data summary
python3 build_dashboard.py
```

**Changing the plan**

- Weekly structure: edit `plan/marathon_plan.md` and the `W`/`FIXED` dicts in `build_schedule.py` (not the generated `plan/daily_schedule.md`), then run `python3 build_schedule.py` and `python3 build_dashboard.py`. Weekly km in the two must match.
- Dashboard layout or styling: edit `dashboard/template.html`, then `python3 build_dashboard.py`.

## Publishing

`docs/` on `main` is served by GitHub Pages. After rebuilding, commit `docs/index.html` and push; the site updates in a couple of minutes.

`docs/` is public. `build_dashboard.py` uses a strict allowlist so only aggregates, per-run date/distance/pace/heart rate, parkrun times and the plan are published. Never add routes, locations, start times, device names, body weight or raw samples.
