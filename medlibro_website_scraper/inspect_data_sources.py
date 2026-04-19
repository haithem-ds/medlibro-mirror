#!/usr/bin/env python3
"""
Inspect scraped question JSON for QCM exam-year metadata (sourcesYears, RATT labels).

Usage:
  set MEDLIBRO_DATA_DIR=C:\\path\\to\\Data
  python inspect_data_sources.py

Prints counts of rows with meta.sourcesYears, distinct years, and sample meta keys.
"""

import json
import os
import sys
from collections import Counter
from pathlib import Path


def iter_items(year_obj):
    if isinstance(year_obj, list):
        return year_obj
    if isinstance(year_obj, dict) and "questions" in year_obj:
        return year_obj["questions"]
    return []


def main():
    root = Path(os.environ.get("MEDLIBRO_DATA_DIR", "")).expanduser()
    if not root.is_dir():
        print("Set MEDLIBRO_DATA_DIR to the folder containing 1st.json, 2nd.json, …", file=sys.stderr)
        sys.exit(1)

    json_files = sorted(root.glob("*.json"))
    if not json_files:
        print(f"No *.json under {root}", file=sys.stderr)
        sys.exit(1)

    total_rows = 0
    with_sources_years = 0
    year_hist = Counter()
    label_samples = Counter()
    meta_keys = Counter()

    for fp in json_files[:8]:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[skip] {fp}: {e}", file=sys.stderr)
            continue
        stem = fp.stem
        for item in iter_items(data):
            if not isinstance(item, dict):
                continue
            total_rows += 1
            meta = item.get("meta") if isinstance(item.get("meta"), dict) else item
            if not isinstance(meta, dict):
                continue
            for k in meta.keys():
                meta_keys[k] += 1
            sy = meta.get("sourcesYears")
            if isinstance(sy, list) and len(sy) > 0:
                with_sources_years += 1
                for y in sy:
                    year_hist[str(y)] += 1
            for lbl in ("sourceLabel", "source", "examSource", "rattLabel"):
                v = meta.get(lbl)
                if isinstance(v, str) and v.strip():
                    label_samples[v[:80]] += 1

    print(f"Files scanned (max 8): {[p.name for p in json_files[:8]]}")
    print(f"Question rows scanned: {total_rows}")
    print(f"Rows with non-empty meta.sourcesYears: {with_sources_years}")
    print(f"Distinct meta.sourcesYears values (stringified): {len(year_hist)}")
    if year_hist:
        print("Top values:", year_hist.most_common(15))
    print(f"Distinct source-like labels (sample): {len(label_samples)}")
    if label_samples:
        print("Examples:", list(label_samples.most_common(10)))
    print("Most common meta keys:", meta_keys.most_common(40))


if __name__ == "__main__":
    main()
