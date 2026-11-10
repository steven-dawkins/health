#!/usr/bin/env python3
"""Generate plan/daily_schedule.md (day-by-day) from the weekly structure in plan/marathon_plan.md.

Weekly totals, long runs and key sessions are defined in WEEKS below and mirror the
"The 25 weeks" table. Easy days (Wed/Fri/Sat) are filled so each week hits its km total.
Run: python3 build_schedule.py
"""
import re
from datetime import date, timedelta
from pathlib import Path

START = date(2026, 11, 9)  # Monday, week 1
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# week: phase, total km, long (desc, km), Tue (desc, km), Thu (desc, km)
# Session km include ~2 km warm-up and ~2 km cool-down where the session is quality.
W = {
    1: ("Rebuild", 40, ("Long easy", 14), ("Easy + 6x20 s strides", 8), ("Easy + 6x20 s strides", 6)),
    2: ("Rebuild", 45, ("Long easy", 16), ("Easy + 6x10 s hill sprints (walk down)", 8), ("Easy + 6x20 s strides", 7)),
    3: ("Rebuild", 50, ("Long easy", 18), ("8x1 min fartlek @5k effort, 1 min easy", 9), ("Easy + 6x20 s strides", 8)),
    4: ("Rebuild (down)", 42, ("Long easy", 14), ("Easy + 6x20 s strides", 8), ("Easy", 7)),
    5: ("Speed", 52, ("Long easy", 18), ("10x400 @5k (4:10-4:15/km), 60 s jog", 10), ("3x8 min threshold (4:30-4:35), 2 min jog", 10)),
    6: ("Speed", 58, ("Long easy", 20), ("6x800 @5k, 90 s jog", 10), ("4x8 min threshold, 2 min jog", 12)),
    7: ("Speed", 62, ("Long easy", 22), ("5x1000 @5k, 2 min jog", 11), ("3x10 min threshold, 2 min jog", 11)),
    8: ("Speed (down)", 50, ("Long easy", 16), ("8x400 @3:55-4:05/km, 200 m jog", 9), ("Easy + 6x20 s strides", 8)),
    9: ("Speed", 62, ("Long easy", 22), ("6x1000 @5k, 2 min jog", 12), ("2x15 min threshold, 2 min jog", 11)),
    10: ("Speed", 66, ("Long easy", 24), ("5x1200 @5k, 2 min jog", 12), ("25 min tempo (4:35-4:40)", 10)),
    11: ("Speed", 70, ("Long easy", 26), ("4x1600 @5k, 2.5 min jog", 12), ("3x12 min threshold, 2 min jog", 13)),
    13: ("Speed-strength", 68, ("Long easy", 24), ("6x3 min @10k (~4:25), 2 min jog", 10), ("5 km tempo (4:35-4:40)", 9)),
    14: ("Speed-strength", 74, ("Long easy", 26), ("5x1200 @10k-5k, 2 min jog", 12), ("2x20 min threshold, 2 min jog", 13)),
    15: ("Speed-strength", 78, ("Long run, last 6 km @MP", 28), ("6x1000 @5k, 2 min jog", 12), ("14 km with 10 km @MP (5:00)", 14)),
    16: ("Strength (down)", 62, ("Long easy", 20), ("8x400 @5k, 200 m jog", 9), ("Easy", 8)),
    17: ("Marathon-specific", 80, ("Long run with 10 km @MP", 28), ("4x2 km threshold, 90 s jog", 13), ("16 km with 12 km @MP", 16)),
    18: ("Marathon-specific", 86, ("Long run with 12 km @MP", 30), ("5x1.6 km threshold, 90 s jog", 14), ("21 km: 3x5 km @MP, 1 km float between", 21)),
    19: ("Marathon-specific", 90, ("Long run with 16 km @ provisional MP", 32), ("6x1 km @10k, 90 s jog", 12), ("16 km with 10 km @MP", 16)),
    22: ("Peak", 92, ("Long run, last 10 km @MP", 32), ("5x1 km @10k, 90 s jog", 11), ("18 km with 12 km @MP, race shoes + fuel", 18)),
    23: ("Taper", 75, ("Long run with 6 km @MP", 22), ("5x1 km @10k, 90 s jog", 11), ("12 km with 8 km @MP", 12)),
    24: ("Taper", 58, ("Long run with 4 km @MP", 16), ("4x1 km @10k, 90 s jog", 10), ("9 km with 5 km @MP", 9)),
}

# Weeks laid out by hand: day index (0=Mon) -> (session, km). Missing days are rest.
FIXED = {
    12: ("Speed (down / test)", {
        1: ("5x400 sharp @3:55-4:05, 200 m jog (2 km warm-up/cool-down)", 8),
        2: ("Easy-medium", 10),
        3: ("Easy + 6x20 s strides", 10),
        4: ("REST (full rest before the test)", 0),
        5: ("**GATE 1: all-out 5k parkrun.** 2 km warm-up + 4 strides, race the 5k, 2 km cool-down", 10),
        6: ("Long easy", 16),
    }),
    20: ("Marathon-specific (race)", {
        1: ("Sharpener: 6x400 @5k, 200 m jog (2 km warm-up/cool-down)", 9),
        2: ("Easy-medium", 10),
        3: ("Easy + 4x20 s strides", 10),
        4: ("REST (Good Friday)", 0),
        5: ("20 min easy + 4 strides", 4),
        6: ("**GATE 2: Milton Keynes Festival of Running half, 10:45 start.** 2 km warm-up, race 21.1 km, 1.5 km cool-down. Race fuel and shoes as for the marathon", 24.6),
    }),
    21: ("Marathon-specific", {
        0: ("REST (Easter Monday)", 0),
        1: ("Easy recovery", 10),
        2: ("4x1 km @10k, 90 s jog (2 km warm-up/cool-down)", 12),
        3: ("Easy-medium", 10),
        4: ("10 km @ final MP (2 km warm-up/cool-down)", 14),
        5: ("Easy", 6),
        6: ("Long run with 14 km @ final MP", 30),
    }),
    25: ("Taper / race week", {
        1: ("4x800 @5k, 90 s jog (2 km warm-up/cool-down)", 9),
        2: ("Easy-medium", 10),
        3: ("4 km @MP (2 km warm-up/cool-down)", 8),
        4: ("Easy", 6),
        5: ("20 min easy + 4 strides", 4),
        6: ("15 min shakeout + 3 strides. Lay out kit, carb up, early night", 3),
    }),
}

STRENGTH_ONE = {12, 20, 21, 24}  # one light strength session instead of two
STRENGTH_NONE = {25}


EASY = 5.75  # min/km, middle of the 5:30-6:00 easy range
MP = 5.0     # provisional marathon pace
QUAL = 4.9   # average over a quality session's non-warm-up part, including jog recoveries


def est_min(desc, km):
    """Rough estimated time in minutes for a run. A guide from the paces in the plan, not a target."""
    if not km:
        return 0
    d = desc.lower()
    if "gate 1" in d:
        return 2 * EASY + 21.5 * 1 + (km - 7) * EASY  # ~21:30 race + 2 km warm-up + 2 km cool-down
    if "gate 2" in d:
        return 2 * EASY + 100 + 1.5 * EASY  # ~1:40 race plus warm-up and cool-down
    m = re.search(r"(\d+) km (?:@ ?(?:final |provisional )?mp)|(\d+) km @ (?:final |provisional )?mp|(?:last|with) (\d+) km @", d)
    mp = next((int(g) for g in m.groups() if g), 0) if m else 0
    if mp:
        return mp * MP + (km - mp) * EASY
    if re.search(r"\d+x|min threshold|tempo|fartlek|sharpener|hill sprints", d) and "strides" not in d.split("+")[0] or re.search(r"\dx\d+ ?(m|km|min)", d):
        warm = min(4, km)
        return warm * EASY + (km - warm) * QUAL
    if "parkrun" in d:
        return km * 5.25
    if "strides" in d:
        return km * EASY + 1
    return km * EASY


def hm(mins):
    mins = round(mins)
    return f"{mins // 60}:{mins % 60:02d}" if mins >= 60 else f"{mins} min"


def fuel(week, km):
    if week < 13 or km < 24:
        return ""
    if week <= 14:
        g = "60 g carb/h"
    elif week <= 17:
        g = "60-70 g carb/h"
    elif week <= 20:
        g = "75 g carb/h"
    else:
        g = "75-90 g carb/h (race plan)"
    return f" Fuel: {g}."


def fill(week, total, long_km, tue_km, thu_km):
    rem = total - long_km - tue_km - thu_km
    wed, fri = round(rem * 0.42), round(rem * 0.22)
    if fri < 5:
        fri = 0
        wed = round(rem * 0.55)
    sat = rem - wed - fri
    return wed, fri, sat


def build_week(week):
    if week in FIXED:
        phase, days = FIXED[week]
        rows = {i: days.get(i, ("REST", 0)) for i in range(7)}
        total = sum(v[1] for v in rows.values())
        return phase, rows, total
    phase, total, (ldesc, lkm), (tdesc, tkm), (bdesc, bkm) = W[week]
    wed, fri, sat = fill(week, total, lkm, tkm, bkm)
    rows = {
        0: ("REST (or 30 min easy cycling/walk)", 0),
        1: (tdesc, tkm),
        2: ("Easy-medium (5:30-5:50/km)", wed),
        3: (bdesc, bkm),
        4: ("Easy short (5:40-6:00/km)" if fri else "REST (or short easy 5 km)", fri),
        5: (("parkrun, controlled (5:10-5:20/km), with warm-up/cool-down" if sat >= 7 else "Easy"), sat),
        6: (ldesc + "." + fuel(week, lkm), lkm),
    }
    return phase, rows, total


def strength_days(week, rows):
    if week in STRENGTH_NONE:
        return set()
    if week in STRENGTH_ONE:
        return {2}
    return {2, 4}


def main():
    out = [
        "# Day-by-day schedule: MK Marathon, Monday 3 May 2027\n",
        "Generated by `build_schedule.py` from the weekly structure in `marathon_plan.md`. Read that file first for the strategy, decision gates and safeguards. Distances are total run km for the day including warm-up and cool-down. Est. time is a rough guide from the plan's paces (easy 5:45/km, MP 5:00/km), not a target.\n",
        "**Conventions.** Easy = 5:30-6:00/km, HR under ~140. Steady 5:10-5:20. MP is a provisional 5:00/km until Gate 2 (Sun 28 Mar 2027) sets the final figure. Threshold 4:30-4:35, 10k ~4:25, 5k 4:10-4:15. Quality sessions start with ~2 km easy and finish with ~2 km easy. **Strength** (30 min: single-leg squats, step-ups, calf raises, hip stability) goes after the run on Wed and Fri, or on its own if the day is a rest run day.\n",
        "**Recovery rule.** If resting HR is 4+ bpm above ~47 for 3 days, or 7-day HRV is below ~50 ms, swap that week's Tuesday or Thursday session for easy running. Skip a hard session before skipping a down week. Any niggle over 3 days: cut quality first, then the long run.\n",
        "**Christmas.** Fri 25 Dec and Sat 26 Dec are in week 7. Run them as scheduled (Friday easy, Saturday easy or a controlled Boxing Day parkrun if one is on).\n",
    ]
    grand = 0
    summary = []
    for wk in range(1, 26):
        phase, rows, total = build_week(wk)
        mon = START + timedelta(weeks=wk - 1)
        sd = strength_days(wk, rows)
        out.append(f"\n## Week {wk}: {phase} (w/c {mon:%a} {mon.day} {mon:%b}), {total:g} km\n")
        out.append("| Day | Date | Session | km | Est. time |")
        out.append("|---|---|---|---|---|")
        for i in range(7):
            d = mon + timedelta(days=i)
            desc, km = rows[i]
            if i in sd:
                desc += " + strength" if km else " Strength session only."
                if not km and desc.startswith("REST"):
                    desc = "Strength session only (no run)"
            out.append(f"| {DAYS[i]} | {d.day} {d:%b} | {desc} | {km:g} | {hm(est_min(desc, km))} |" if km else f"| {DAYS[i]} | {d.day} {d:%b} | {desc} | - | - |")
        grand += total
        summary.append((wk, mon, phase, total))
    race = START + timedelta(weeks=25)
    out.append(f"\n## Race day: {race:%A} {race.day} {race:%B %Y}\n")
    out.append("MK Marathon. Start time per organisers (check the marathon page). Run the first 30 km at goal pace or a touch slower, then hold form: short quick steps, upright, fuel on schedule. Stick to the pace set at Gate 2.\n")
    out.append(f"\nPlanned running total: {grand:g} km across 25 weeks.\n")
    path = Path(__file__).parent / "plan" / "daily_schedule.md"
    path.write_text("\n".join(out))
    print(f"wrote {path} ({grand:g} km)")
    for wk, mon, phase, total in summary:
        print(wk, mon, phase, total)


if __name__ == "__main__":
    main()
