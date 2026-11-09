#!/usr/bin/env python3
"""Summarize the CSVs produced by extract_health.py for marathon planning.

Usage:
    python3 summarize_health.py [data_dir] [out_dir]
Defaults: ./health_data -> ./summary

Writes (to out_dir):
    runs.csv              one row per run: distance, pace, avg HR, efficiency
    weekly_running.csv    weekly volume, long run, runs, avg HR
    daily_recovery.csv    resting HR, HRV, sleep with rolling baselines
    monthly_fitness.csv   VO2 max + running form/power monthly means
    data_coverage.csv     first/last date and sample count for each metric
    report.txt            human-readable summary (also printed)
"""
import json
import os
import sys

import pandas as pd

MILES_TO_KM = 1.609344
ASLEEP = {
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
}


def read(data_dir, name, **kw):
    path = os.path.join(data_dir, f"{name}.csv")
    if not os.path.exists(path):
        return pd.DataFrame()
    df = pd.read_csv(path, **kw)
    for c in ("startDate", "endDate"):
        if c in df:
            # keep wall-clock time as recorded (drop the +0000 suffix)
            df[c] = pd.to_datetime(df[c].str[:19])
    return df


def fmt_pace(min_per_km):
    if pd.isna(min_per_km) or min_per_km <= 0:
        return "-"
    m = int(min_per_km)
    s = int(round((min_per_km - m) * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{m}:{s:02d}/km"


# ---------------------------------------------------------------- runs
def build_runs(data_dir):
    w = read(data_dir, "workouts_raw")
    w = w[w["workoutActivityType"] == "HKWorkoutActivityTypeRunning"].copy()
    stats = w["statistics"].apply(lambda s: json.loads(s) if isinstance(s, str) else {})

    def distance_km(row, st):
        if pd.notna(row["totalDistance"]):
            unit = str(row["totalDistanceUnit"]).lower()
            return row["totalDistance"] * (MILES_TO_KM if unit.startswith("mi") else 1)
        d = st.get("DistanceWalkingRunning_sum")
        return float(d) if d is not None else float("nan")  # old Strava imports are km

    w["distance_km"] = [distance_km(r, s) for (_, r), s in zip(w.iterrows(), stats)]
    w["minutes"] = pd.to_numeric(w["duration"], errors="coerce")
    w["avg_hr"] = [float(s["HeartRate_average"]) if "HeartRate_average" in s else float("nan")
                   for s in stats]
    w["max_hr"] = [float(s["HeartRate_maximum"]) if "HeartRate_maximum" in s else float("nan")
                   for s in stats]
    w["pace_min_km"] = w["minutes"] / w["distance_km"]
    # metres covered per heartbeat: higher = more aerobically efficient
    w["efficiency_m_per_beat"] = (w["distance_km"] * 1000) / (w["minutes"] * w["avg_hr"])
    w["date"] = w["startDate"].dt.normalize()
    runs = w[["date", "startDate", "distance_km", "minutes", "pace_min_km", "avg_hr", "max_hr",
              "efficiency_m_per_beat", "sourceName"]].sort_values("startDate")
    runs = runs[(runs["distance_km"] > 0.5) & (runs["minutes"] > 3)].reset_index(drop=True)
    return drop_double_imports(drop_walks(runs))


def drop_walks(runs, max_pace=12.0):
    """Walks logged as runs (slower than 12 min/km) distort pace and are not training runs."""
    slow = runs["minutes"] / runs["distance_km"] > max_pace
    if slow.any():
        print(f"Dropped {int(slow.sum())} workouts slower than {max_pace:.0f} min/km (walks logged as runs)")
    return runs[~slow].reset_index(drop=True)


def drop_double_imports(runs):
    """Some old runs exist twice in Apple Health (e.g. Strava import plus a second sync, starting
    seconds apart with ~identical distance). Keep one: the first, or the one with heart rate."""
    keep, last = [], None
    for i, r in runs.sort_values("startDate").iterrows():
        if last is not None and (r["startDate"] - last["startDate"]) <= pd.Timedelta(minutes=5) \
                and abs(r["distance_km"] / last["distance_km"] - 1) < 0.05:
            if pd.isna(last["avg_hr"]) and pd.notna(r["avg_hr"]):
                keep[-1] = i
                last = r
            continue
        keep.append(i)
        last = r
    dropped = len(runs) - len(keep)
    if dropped:
        print(f"Dropped {dropped} double-imported runs (same start +-5 min, distance within 5%)")
    return runs.loc[keep].sort_values("startDate").reset_index(drop=True)


def build_weekly(runs):
    r = runs.set_index("startDate")
    g = r.resample("W-SUN", label="left", closed="left")  # week starting Monday
    weekly = pd.DataFrame({
        "runs": g["distance_km"].count(),
        "km": g["distance_km"].sum(),
        "hours": g["minutes"].sum() / 60,
        "long_run_km": g["distance_km"].max(),
        "avg_hr": g["avg_hr"].mean(),
    })
    weekly["avg_pace_min_km"] = weekly["hours"] * 60 / weekly["km"].where(weekly["km"] > 0)
    weekly["km_4wk_avg"] = weekly["km"].rolling(4, min_periods=1).mean()
    weekly["change_vs_prev_wk_pct"] = weekly["km"].pct_change().replace(
        [float("inf"), -float("inf")], float("nan")) * 100
    weekly.index.name = "week_start"
    return weekly.round(2)


# ------------------------------------------------------------ recovery
def build_daily_recovery(data_dir):
    rhr = read(data_dir, "resting_heart_rate")
    hrv = read(data_dir, "hrv_sdnn")
    sleep = read(data_dir, "sleep")
    parts = {}
    if len(rhr):
        parts["resting_hr"] = rhr.groupby(rhr["startDate"].dt.normalize())["value"].mean()
    if len(hrv):
        parts["hrv_ms"] = hrv.groupby(hrv["startDate"].dt.normalize())["value"].mean()
    if len(sleep):
        s = sleep[sleep["value"].isin(ASLEEP)].copy()
        s["night"] = s["endDate"].dt.normalize()  # night is dated by the morning you woke
        hours = {}
        for night, grp in s.groupby("night"):
            # union overlapping intervals so phone + watch don't double count
            iv = list(grp.sort_values("startDate")[["startDate", "endDate"]].itertuples(index=False, name=None))
            total, cur_s, cur_e = 0.0, iv[0][0], iv[0][1]
            for a, b in iv[1:]:
                if a <= cur_e:
                    cur_e = max(cur_e, b)
                else:
                    total += (cur_e - cur_s).total_seconds()
                    cur_s, cur_e = a, b
            total += (cur_e - cur_s).total_seconds()
            hours[night] = total / 3600
        parts["sleep_hours"] = pd.Series(hours)
    df = pd.DataFrame(parts).sort_index()
    df = df.asfreq("D")
    for c in ("resting_hr", "hrv_ms", "sleep_hours"):
        if c in df:
            df[f"{c}_7d"] = df[c].rolling(7, min_periods=3).mean()
            df[f"{c}_28d"] = df[c].rolling(28, min_periods=10).mean()
    df.index.name = "date"
    return df.round(2)


def build_monthly_fitness(data_dir):
    cols = {}
    for name, label in [("vo2max", "vo2max"), ("running_power", "run_power_w"),
                        ("running_stride_length", "stride_length"),
                        ("running_vertical_oscillation", "vertical_osc"),
                        ("running_ground_contact_time", "ground_contact_ms"),
                        ("running_speed", "run_speed")]:
        df = read(data_dir, name)
        if len(df):
            cols[label] = df.set_index("startDate")["value"].resample("MS").mean()
    out = pd.DataFrame(cols)
    out.index.name = "month"
    return out.round(2)


def coverage(data_dir):
    rows = []
    for f in sorted(os.listdir(data_dir)):
        if not f.endswith(".csv"):
            continue
        name = f[:-4]
        df = read(data_dir, name, usecols=lambda c: c in ("startDate", "workoutActivityType"))
        if len(df):
            rows.append({"metric": name, "samples": len(df),
                         "first": df["startDate"].min().date(), "last": df["startDate"].max().date()})
    return pd.DataFrame(rows)


# -------------------------------------------------------------- report
def trend_line(series, as_of, label, unit="", decimals=1):
    s = series.dropna()
    if s.empty:
        return f"  {label}: no data"
    last28 = s[s.index > as_of - pd.Timedelta(days=28)]
    prev90 = s[(s.index <= as_of - pd.Timedelta(days=28)) & (s.index > as_of - pd.Timedelta(days=118))]
    msg = f"  {label}: last 28d avg {last28.mean():.{decimals}f}{unit}" if len(last28) else \
          f"  {label}: nothing in last 28d (last reading {s.index.max().date()})"
    if len(last28) and len(prev90):
        d = last28.mean() - prev90.mean()
        msg += f"  | prior 90d avg {prev90.mean():.{decimals}f}{unit} ({d:+.{decimals}f})"
    return msg


def make_report(runs, weekly, daily, monthly, cov):
    as_of = runs["startDate"].max().normalize()
    L = [f"MARATHON TRAINING DATA SUMMARY (data through {as_of.date()})", "=" * 60, ""]

    L.append("RUNNING VOLUME - last 16 weeks (Mon-start)")
    L.append(f"  {'week':<11}{'runs':>5}{'km':>8}{'long':>7}{'pace':>11}{'avgHR':>7}{'chg%':>7}")
    recent = weekly[weekly.index >= as_of - pd.Timedelta(weeks=16)]
    for wk, r in recent.iterrows():
        chg = f"{r['change_vs_prev_wk_pct']:+.0f}" if pd.notna(r["change_vs_prev_wk_pct"]) else "-"
        hr = f"{r['avg_hr']:.0f}" if pd.notna(r["avg_hr"]) else "-"
        L.append(f"  {wk.date()!s:<11}{int(r['runs']):>5}{r['km']:>8.1f}"
                 f"{(r['long_run_km'] if pd.notna(r['long_run_km']) else 0):>7.1f}"
                 f"{fmt_pace(r['avg_pace_min_km']):>11}{hr:>7}{chg:>7}")
    last8 = weekly[weekly.index >= as_of - pd.Timedelta(weeks=8)]
    last12 = weekly[weekly.index >= as_of - pd.Timedelta(weeks=12)]
    yr = runs[runs["startDate"] > as_of - pd.Timedelta(days=365)]
    L += ["",
          f"  Avg weekly km: last 8 wks {last8['km'].mean():.1f} | last 12 wks {last12['km'].mean():.1f}"
          f" | peak week in last 12 months {weekly[weekly.index > as_of - pd.Timedelta(days=365)]['km'].max():.1f}",
          f"  Longest run: last 12 wks {runs[runs['startDate'] > as_of - pd.Timedelta(weeks=12)]['distance_km'].max():.1f} km"
          f" | last 12 months {yr['distance_km'].max():.1f} km"
          f" | all time {runs['distance_km'].max():.1f} km ({runs.loc[runs['distance_km'].idxmax(), 'date'].date()})"]
    gaps = weekly[(weekly.index > as_of - pd.Timedelta(days=365)) & (weekly["runs"] == 0)]
    L.append(f"  Weeks with zero runs in last 12 months: {len(gaps)}"
             + (f" (most recent {gaps.index.max().date()})" if len(gaps) else ""))

    L += ["", "AEROBIC EFFICIENCY (runs >= 20 min with HR; metres per heartbeat, higher = fitter)"]
    e = runs[(runs["minutes"] >= 20) & runs["efficiency_m_per_beat"].notna()].set_index("startDate")
    if len(e):
        q = e["efficiency_m_per_beat"].resample("QS").median().dropna().tail(8)
        for d, v in q.items():
            L.append(f"  {d.date()}  {v:.3f}")
    else:
        L.append("  no runs with heart rate data")

    L += ["", "RECOVERY (28d avg vs prior 90d)"]
    L.append(trend_line(daily["resting_hr"], as_of, "Resting HR", " bpm"))
    L.append(trend_line(daily["hrv_ms"], as_of, "HRV (SDNN)", " ms"))
    L.append(trend_line(daily["sleep_hours"], as_of, "Sleep", " h", 2))
    last7 = daily[daily.index > as_of - pd.Timedelta(days=7)]
    if len(last7):
        L.append(f"  Last 7 days: RHR {last7['resting_hr'].mean():.1f}, HRV {last7['hrv_ms'].mean():.1f},"
                 f" sleep {last7['sleep_hours'].mean():.2f} h")

    L += ["", "VO2 MAX (monthly mean, last 12 months)"]
    if "vo2max" in monthly:
        for d, v in monthly["vo2max"].dropna().tail(12).items():
            L.append(f"  {d.strftime('%Y-%m')}  {v:.1f}")

    L += ["", "DATA COVERAGE (check for gaps from deleted history)"]
    for _, r in cov.iterrows():
        L.append(f"  {r['metric']:<32}{r['samples']:>9,}  {r['first']} -> {r['last']}")
    return "\n".join(L)


def add_strava(runs, path="strava_data/strava_runs.csv"):
    """Append Strava runs that Apple Health lacks (older history, gaps). Apple wins on overlap:
    same start within 10 min, or same date with distance within 8%."""
    if not os.path.exists(path):
        return runs.assign(source="apple")
    s = pd.read_csv(path, parse_dates=["startDate"])
    s = drop_walks(s.assign(minutes=s["minutes"]))
    a = runs.copy()
    a["_d"], s["_d"] = a["startDate"].dt.date, s["startDate"].dt.date
    keep = []
    by_day = {d: g for d, g in a.groupby("_d")}
    for _, r in s.iterrows():
        g = by_day.get(r["_d"])
        dup = g is not None and (
            ((g["startDate"] - r["startDate"]).abs() <= pd.Timedelta(minutes=10)).any()
            or ((g["distance_km"] / r["distance_km"] - 1).abs() < 0.08).any())
        keep.append(not dup)
    s = s[keep].copy()
    s["date"] = s["startDate"].dt.normalize()
    s["max_hr"] = float("nan")
    s["efficiency_m_per_beat"] = (s["distance_km"] * 1000) / (s["minutes"] * s["avg_hr"])
    s["sourceName"] = "Strava"
    a["source"], s["source"] = "apple", "strava"
    cols = list(runs.columns) + ["source"]
    out = pd.concat([a[cols], s[cols]]).sort_values("startDate").reset_index(drop=True)
    print(f"Strava: added {len(s)} runs not in Apple Health ({s['startDate'].min().date()} to {s['startDate'].max().date()})")
    return out


def main():
    data_dir = sys.argv[1] if len(sys.argv) > 1 else "health_data"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "summary"
    os.makedirs(out_dir, exist_ok=True)

    runs = add_strava(build_runs(data_dir))
    weekly = build_weekly(runs)
    daily = build_daily_recovery(data_dir)
    monthly = build_monthly_fitness(data_dir)
    cov = coverage(data_dir)

    runs.to_csv(os.path.join(out_dir, "runs.csv"), index=False)
    weekly.to_csv(os.path.join(out_dir, "weekly_running.csv"))
    daily.to_csv(os.path.join(out_dir, "daily_recovery.csv"))
    monthly.to_csv(os.path.join(out_dir, "monthly_fitness.csv"))
    cov.to_csv(os.path.join(out_dir, "data_coverage.csv"), index=False)

    report = make_report(runs, weekly, daily, monthly, cov)
    with open(os.path.join(out_dir, "report.txt"), "w") as f:
        f.write(report + "\n")
    print(report)
    print(f"\nFiles written to {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    main()
