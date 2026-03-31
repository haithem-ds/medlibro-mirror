#!/usr/bin/env python3
"""
Convert curriculum *.json (array or { "questions": [...] }) to *.jsonl (one question per line).

Docker/Render: run at image build with ijson so a single huge file never fully loads into RAM.
Local: pip install ijson optional; without it, uses json.load (needs enough RAM for that file).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import ijson  # type: ignore
except ImportError:
    ijson = None


def _yield_questions_stdlib(path: Path):
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                yield item
    elif isinstance(raw, dict) and isinstance(raw.get("questions"), list):
        for item in raw["questions"]:
            if isinstance(item, dict):
                yield item


def _yield_questions_ijson(path: Path):
    with open(path, "rb") as f:
        head = f.read(8000)
        f.seek(0)
        stripped = head.lstrip()
        if stripped.startswith(b"["):
            prefix = "item"
        else:
            prefix = "questions.item"
        for item in ijson.items(f, prefix):
            if isinstance(item, dict):
                yield item


def iter_questions(path: Path):
    if ijson is not None:
        yield from _yield_questions_ijson(path)
    else:
        yield from _yield_questions_stdlib(path)


def convert_file(json_path: Path, drop_json: bool) -> int:
    out_path = json_path.with_suffix(".jsonl")
    tmp = out_path.with_suffix(".jsonl.tmp")
    n = 0
    try:
        with open(tmp, "w", encoding="utf-8") as out:
            for item in iter_questions(json_path):
                out.write(json.dumps(item, ensure_ascii=False) + "\n")
                n += 1
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    tmp.replace(out_path)
    print(f"[OK] {json_path.name} -> {out_path.name} ({n} rows)")
    if drop_json:
        json_path.unlink()
        print(f"[OK] Removed {json_path.name} (--drop-json)")
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Build *.jsonl from curriculum *.json for low-RAM serving.")
    ap.add_argument("--data-dir", type=Path, required=True, help="Folder containing 1st.json, …")
    ap.add_argument(
        "--drop-json",
        action="store_true",
        help="Delete each source .json after successful .jsonl (Docker: saves image size; local: keep backup unless intended).",
    )
    args = ap.parse_args()
    data_dir: Path = args.data_dir.resolve()
    if not data_dir.is_dir():
        print(f"[ERROR] Not a directory: {data_dir}", file=sys.stderr)
        return 1
    if ijson:
        print("[INFO] Using ijson for streaming conversion.")
    else:
        print("[WARN] ijson not installed; using json.load per file (high RAM for large files). pip install ijson")
    converted = 0
    for p in sorted(data_dir.glob("*.json")):
        if p.name.startswith("."):
            continue
        out = p.with_suffix(".jsonl")
        if not p.is_file():
            continue
        if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
            if args.drop_json:
                p.unlink()
                print(f"[OK] Removed {p.name} (--drop-json; {out.name} already fresh)")
            else:
                print(f"[SKIP] Up to date: {out.name}")
            continue
        convert_file(p, args.drop_json)
        converted += 1
    if converted == 0 and not any(data_dir.glob("*.jsonl")):
        print("[WARN] No *.jsonl produced. Check --data-dir has *.json or prebuilt *.jsonl.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
