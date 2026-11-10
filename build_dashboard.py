#!/usr/bin/env python3
"""Build the public GitHub Pages dashboard (docs/index.html).

Reads the local, private summaries and writes a self-contained page with a
privacy-filtered data blob embedded in it.

Usage:  python3 build_dashboard.py
Needs:  summary/ (summarize_health.py), parkrun/parkrun_results.csv, plan/marathon_plan.md
Output: docs/index.html   (preview: python3 -m http.server -d docs)

PRIVACY - what is deliberately NOT published:
  * GPS routes, heart-rate samples, workout start times (dates only)
  * Workout source / device names, parkrun venue names and URLs
  * Body weight, steps, energy, sleep stages, any raw Apple Health records
Published: the full training plan document, weekly run totals (from 2015, incl. Strava-only runs), daily 7/28-day averages of resting HR, HRV and sleep,
monthly VO2 max, per-run date/distance/pace/avg HR (last 12 months), parkrun
date/time/position, race results, and the training plan.
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
PLAN_START = date(2026, 11, 9)  # Monday of plan week 1
RACES = [
    {"date": "2026-10-18", "name": "Marathon (completed)", "result": "3:35:36"},
    {"date": "2027-01-30", "name": "Gate 1: all-out 5k parkrun", "result": None},
    {"date": "2027-03-28", "name": "Gate 2: MK Festival of Running half", "result": None},
    {"date": "2027-05-03", "name": "MK Marathon", "result": None},
]


def r(x, n=2):
    return None if pd.isna(x) else round(float(x), n)


def parse_plan():
    rows = []
    for line in (ROOT / "plan" / "marathon_plan.md").read_text().splitlines():
        m = re.match(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*(.*?)\s*\|$", line)
        if not m:
            continue
        wk = int(m.group(1))
        long_km = re.match(r"\d+", m.group(5))
        rows.append({
            "week": wk,
            "start": (PLAN_START + timedelta(weeks=wk - 1)).isoformat(),
            "phase": m.group(3),
            "km": int(m.group(4)),
            "long_km": int(long_km.group()) if long_km else None,
            "long": m.group(5),
            "key": m.group(6).replace("**", ""),
        })
    if len(rows) != 25:
        raise SystemExit(f"Expected 25 plan weeks, parsed {len(rows)}; check the table in plan/marathon_plan.md")
    return rows


def parse_plan_doc():
    """Whole plan document as sections of paragraph / bullet / table blocks (rendered with textContent)."""
    text = (ROOT / "plan" / "marathon_plan.md").read_text().replace(" (see `CLAUDE.md`)", "")
    sections, cur, lines = [], {"title": "Overview", "blocks": []}, text.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if ln.startswith("# "):
            pass
        elif ln.startswith("## "):
            if cur["blocks"] or cur["title"] != "Overview":
                sections.append(cur)
            cur = {"title": ln[3:].strip(), "blocks": []}
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r"-+", c) for c in cells):
                    rows.append(cells)
                i += 1
            i -= 1
            cur["blocks"].append({"t": "table", "head": rows[0], "rows": rows[1:]})
        elif ln.startswith("- "):
            items = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:].strip())
                i += 1
            i -= 1
            cur["blocks"].append({"t": "ul", "items": items})
        elif ln.strip():
            cur["blocks"].append({"t": "p", "text": ln.strip()})
        i += 1
    sections.append(cur)
    if not any(x["title"].startswith("The 25 weeks") for x in sections):
        raise SystemExit("plan/marathon_plan.md: missing the 'The 25 weeks' section")
    return sections


def parse_daily():
    """Day-by-day schedule from plan/daily_schedule.md -> [{week, phase, km, days:[{d, session, km}]}]."""
    weeks, cur = [], None
    for ln in (ROOT / "plan" / "daily_schedule.md").read_text().splitlines():
        m = re.match(r"^## Week (\d+): (.+?) \(w/c [^)]*\), ([\d.]+) km$", ln)
        if m:
            cur = {"week": int(m.group(1)), "phase": m.group(2), "km": float(m.group(3)), "days": []}
            weeks.append(cur)
            continue
        m = re.match(r"^\| (Mon|Tue|Wed|Thu|Fri|Sat|Sun) \| [^|]+ \| (.+) \| ([\d.]+|-) \| ([^|]+) \|$", ln)
        if m and cur is not None:
            i = len(cur["days"])
            d = PLAN_START + timedelta(weeks=cur["week"] - 1, days=i)
            cur["days"].append({"d": d.isoformat(), "session": m.group(2),
                                "km": 0 if m.group(3) == "-" else float(m.group(3)),
                                "time": "" if m.group(4).strip() == "-" else m.group(4).strip()})
    if len(weeks) != 25 or any(len(w["days"]) != 7 for w in weeks):
        raise SystemExit("plan/daily_schedule.md: expected 25 weeks x 7 days; run build_schedule.py")
    return weeks


def main():
    s = ROOT / "summary"
    weekly = pd.read_csv(s / "weekly_running.csv", parse_dates=["week_start"])
    weekly = weekly[weekly.week_start >= "2015-01-01"]
    daily = pd.read_csv(s / "daily_recovery.csv", parse_dates=["date"])
    daily = daily[daily.date >= "2022-01-01"]
    monthly = pd.read_csv(s / "monthly_fitness.csv", parse_dates=["month"])
    runs = pd.read_csv(s / "runs.csv", parse_dates=["date"])
    pk = pd.read_csv(ROOT / "parkrun" / "parkrun_results.csv", parse_dates=["date"])

    as_of = runs["date"].max()
    cutoff = as_of - pd.Timedelta(days=365)
    recent = runs[runs.date > cutoff].sort_values("date", ascending=False)

    data = {
        "as_of": as_of.date().isoformat(),
        "built": date.today().isoformat(),
        "weekly": [{"d": w.week_start.date().isoformat(), "km": r(w.km, 1), "runs": int(w.runs),
                    "long": r(w.long_run_km, 1)} for w in weekly.itertuples()],
        "daily": [{"d": x.date.date().isoformat(), "rhr7": r(x.resting_hr_7d, 1), "rhr28": r(x.resting_hr_28d, 1),
                   "hrv7": r(x.hrv_ms_7d, 1), "hrv28": r(x.hrv_ms_28d, 1), "sleep7": r(x.sleep_hours_7d, 2)}
                  for x in daily.itertuples()],
        "vo2": [{"d": m.month.date().isoformat(), "v": r(m.vo2max, 1)} for m in monthly.itertuples() if pd.notna(m.vo2max)],
        "parkruns": [{"d": p.date.date().isoformat(), "sec": int(p.time_seconds), "t": p.time, "pos": int(p.position)}
                     for p in pk.itertuples()],
        "runs": [{"d": x.date.date().isoformat(), "km": r(x.distance_km, 2), "pace": r(x.pace_min_km, 3),
                  "hr": r(x.avg_hr, 0)} for x in recent.itertuples()],
        "plan": parse_plan(),
        "plan_doc": parse_plan_doc(),
        "schedule": parse_daily(),
        "races": RACES,
    }
    blob = json.dumps(data, separators=(",", ":"))
    tpl = (ROOT / "dashboard" / "template.html").read_text()
    if "/*__DATA__*/" not in tpl:
        raise SystemExit("template.html is missing the /*__DATA__*/ placeholder")
    out = ROOT / "docs"
    out.mkdir(exist_ok=True)
    (out / "index.html").write_text(tpl.replace("/*__DATA__*/null", blob))
    (out / ".nojekyll").write_text("")
    print(f"docs/index.html written ({len(blob)/1024:.0f} KB of data; data through {data['as_of']})")


if __name__ == "__main__":
    main()
