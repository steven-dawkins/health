#!/usr/bin/env python3
"""Merge several Apple Health export zips into deduplicated per-metric CSVs.

Streams export.xml straight out of each zip (no extraction, low memory).
Files are processed newest export first, so if the same sample appears in more
than one export, the most recent copy wins; samples that only exist in older
exports are still kept.

Usage:
    python3 extract_health.py [zip_dir] [out_dir]
Defaults: ./apple_health  ->  ./health_data
"""
import csv
import json
import glob
import os
import sys
import zipfile
import xml.etree.ElementTree as ET

# HealthKit identifier -> output file name
RECORD_TYPES = {
    # fitness / load
    "HKQuantityTypeIdentifierVO2Max": "vo2max",
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_heart_rate",
    "HKQuantityTypeIdentifierWalkingHeartRateAverage": "walking_heart_rate_avg",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv_sdnn",
    "HKQuantityTypeIdentifierHeartRateRecoveryOneMinute": "heart_rate_recovery_1min",
    # recovery
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep",
    "HKQuantityTypeIdentifierRespiratoryRate": "respiratory_rate",
    "HKQuantityTypeIdentifierOxygenSaturation": "oxygen_saturation",
    # running form
    "HKQuantityTypeIdentifierRunningSpeed": "running_speed",
    "HKQuantityTypeIdentifierRunningPower": "running_power",
    "HKQuantityTypeIdentifierRunningStrideLength": "running_stride_length",
    "HKQuantityTypeIdentifierRunningVerticalOscillation": "running_vertical_oscillation",
    "HKQuantityTypeIdentifierRunningGroundContactTime": "running_ground_contact_time",
    # volume / body
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance_walking_running",
    "HKQuantityTypeIdentifierStepCount": "step_count",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_energy",
    "HKQuantityTypeIdentifierBodyMass": "body_mass",
}

RECORD_FIELDS = ["startDate", "endDate", "value", "unit", "sourceName", "device", "creationDate"]
WORKOUT_FIELDS = [
    "workoutActivityType", "startDate", "endDate", "duration", "durationUnit",
    "totalDistance", "totalDistanceUnit", "totalEnergyBurned", "totalEnergyBurnedUnit",
    "sourceName", "creationDate",
]


def export_date(zf):
    """Read <ExportDate value=.../> from the first lines of export.xml."""
    with zf.open("apple_health_export/export.xml") as f:
        for _ in range(500):
            line = f.readline().decode("utf-8", "replace")
            if "<ExportDate" in line:
                return line.split('value="')[1].split('"')[0]
    return ""


def stream(zf, writers, seen, counts):
    depth = 0
    with zf.open("apple_health_export/export.xml") as f:
        for event, el in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                depth += 1
                continue
            depth -= 1
            tag = el.tag
            if tag == "Record" and depth == 1:  # top-level only (skip Correlation children)
                name = RECORD_TYPES.get(el.get("type"))
                if name:
                    key = (name, el.get("startDate"), el.get("endDate"),
                           el.get("value"), el.get("sourceName"))
                    if key in seen:
                        counts[name]["dup"] += 1
                    else:
                        seen.add(key)
                        writers[name].writerow([el.get(k, "") for k in RECORD_FIELDS])
                        counts[name]["new"] += 1
            elif tag == "Workout" and depth == 1:
                key = ("workout", el.get("workoutActivityType"), el.get("startDate"),
                       el.get("endDate"), el.get("sourceName"))
                if key in seen:
                    counts["workouts"]["dup"] += 1
                else:
                    seen.add(key)
                    row = [el.get(k, "") for k in WORKOUT_FIELDS]
                    stats = {}
                    for s in el.findall("WorkoutStatistics"):
                        t = s.get("type", "").replace("HKQuantityTypeIdentifier", "")
                        for field in ("average", "minimum", "maximum", "sum"):
                            if s.get(field) is not None:
                                stats[f"{t}_{field}"] = s.get(field)
                    writers["workouts"].writerow(row + [json.dumps(stats)])
                    counts["workouts"]["new"] += 1
            if depth <= 1:
                el.clear()  # free memory for each finished top-level element


def main():
    zip_dir = sys.argv[1] if len(sys.argv) > 1 else "apple_health"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "health_data"
    os.makedirs(out_dir, exist_ok=True)

    zips = glob.glob(os.path.join(zip_dir, "*.zip"))
    if not zips:
        sys.exit(f"No zip files found in {zip_dir}")
    dated = []
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            dated.append((export_date(zf), z))
    dated.sort(reverse=True)  # newest export first
    print("Processing order (newest first):")
    for d, z in dated:
        print(f"  {d}  {os.path.basename(z)}")

    handles, writers = {}, {}
    names = list(RECORD_TYPES.values())
    for n in names:
        handles[n] = open(os.path.join(out_dir, f"{n}.csv"), "w", newline="")
        writers[n] = csv.writer(handles[n])
        writers[n].writerow(RECORD_FIELDS)
    handles["workouts"] = open(os.path.join(out_dir, "workouts_raw.csv"), "w", newline="")
    writers["workouts"] = csv.writer(handles["workouts"])
    writers["workouts"].writerow(WORKOUT_FIELDS + ["statistics"])

    seen = set()
    counts = {n: {"new": 0, "dup": 0} for n in names + ["workouts"]}
    try:
        for d, z in dated:
            print(f"\nReading {os.path.basename(z)} ...", flush=True)
            before = {n: c["new"] for n, c in counts.items()}
            with zipfile.ZipFile(z) as zf:
                stream(zf, writers, seen, counts)
            print("  new rows contributed:")
            for n, c in counts.items():
                added = c["new"] - before[n]
                if added:
                    print(f"    {n:32s} {added}")
    finally:
        for h in handles.values():
            h.close()

    print("\nFinal unique rows per metric:")
    for n, c in counts.items():
        print(f"  {n:32s} {c['new']:>9}  (duplicates skipped: {c['dup']})")
    print(f"\nWritten to {os.path.abspath(out_dir)}")


if __name__ == "__main__":
    main()
