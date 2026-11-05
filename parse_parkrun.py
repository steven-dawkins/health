#!/usr/bin/env python3
"""Turn a saved parkrun "all results" page into a CSV.

parkrun.org.uk blocks automated requests (HTTP 403), so this script does not
fetch anything. Save the page from your own browser instead:

  1. Log in (if needed) and open https://www.parkrun.org.uk/parkrunner/576042/all/
  2. File > Save Page As... > "Webpage, HTML only" (or "Complete") -> parkrun/all.html
  3. python3 parse_parkrun.py parkrun/all.html parkrun/parkrun_results.csv

Uses only the standard library. The results table is found by its headers
(it needs at least "Event", "Run Date" and "Time" columns), so minor layout
changes by parkrun should not break it.
"""
import csv
import re
import sys
from datetime import datetime
from html.parser import HTMLParser


class TableParser(HTMLParser):
    """Collect every table as a list of rows; each cell is (text, first_href)."""

    def __init__(self):
        super().__init__()
        self.tables = []      # finished tables
        self._stack = []      # open tables (handles nesting)
        self._row = None
        self._cell = None     # [text_parts, href]

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = [[], None]
        elif tag == "a" and self._cell is not None and self._cell[1] is None:
            self._cell[1] = dict(attrs).get("href")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell[0].append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell[0]).split())
            self._row.append((text, self._cell[1]))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._stack:
            self._stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            self.tables.append(self._stack.pop())


def find_results_table(tables):
    for t in tables:
        for i, row in enumerate(t[:3]):  # header is in the first rows
            heads = [c[0].strip().lower() for c in row]
            if "event" in heads and "time" in heads and any("date" in h for h in heads):
                return heads, t[i + 1:]
    return None, None


def col(heads, *names):
    for n in names:
        for i, h in enumerate(heads):
            if n in h:
                return i
    return None


def to_seconds(t):
    parts = t.strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return ""
    sec = 0
    for n in nums:
        sec = sec * 60 + n
    return sec


def to_iso(d):
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(d.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return d


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "parkrun_results.csv"
    with open(src, encoding="utf-8", errors="replace") as f:
        html = f.read()
    p = TableParser()
    p.feed(html)
    heads, rows = find_results_table(p.tables)
    if heads is None:
        sys.exit("Could not find the results table (looked for Event / Run Date / Time columns). "
                 "Make sure you saved the 'All results' page, not a single event page.")

    i_ev, i_date = col(heads, "event"), col(heads, "date")
    i_num, i_pos = col(heads, "run number", "run no"), col(heads, "pos")
    i_time, i_ag = col(heads, "time"), col(heads, "age grade", "age-grade")
    i_pb = col(heads, "pb")

    def get(row, i):
        return row[i][0] if i is not None and i < len(row) else ""

    seen, records = set(), []
    for row in rows:
        if i_time >= len(row) or not re.match(r"^\d+:\d{2}", get(row, i_time)):
            continue  # skip summary / blank rows
        rec = {
            "date": to_iso(get(row, i_date)),
            "event": get(row, i_ev),
            "event_url": (row[i_ev][1] or "") if i_ev is not None and i_ev < len(row) else "",
            "run_number": get(row, i_num),
            "position": get(row, i_pos),
            "time": get(row, i_time),
            "time_seconds": to_seconds(get(row, i_time)),
            "age_grade": get(row, i_ag).replace("%", "").strip(),
            "pb": "1" if get(row, i_pb).strip() else "0",
        }
        key = (rec["date"], rec["event"], rec["time"])
        if key not in seen:  # drop duplicates (e.g. page saved twice / repeated rows)
            seen.add(key)
            records.append(rec)
    records.sort(key=lambda r: r["date"])

    fields = ["date", "event", "event_url", "run_number", "position", "time",
              "time_seconds", "age_grade", "pb"]
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)

    secs = [r["time_seconds"] for r in records if r["time_seconds"] != ""]
    print(f"{len(records)} parkruns written to {out}")
    if records:
        best = min(records, key=lambda r: r["time_seconds"] if r["time_seconds"] != "" else 10**9)
        print(f"  {records[0]['date']} -> {records[-1]['date']}, best {best['time']} ({best['date']}, {best['event']})")
        print(f"  events: {len({r['event'] for r in records})}")


if __name__ == "__main__":
    main()
