#!/usr/bin/env python3
"""Discover procurement notices potentially related to Hualien outside unit prefix 3.76.55."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from pathlib import Path

from fetch_procurement import API_BASE, is_in_scope, request_json, write_json

EXISTING_PREFIX = "3.76.55"

AGENCY_TERMS = (
    "花蓮",
    "太魯閣國家公園",
    "花東縱谷國家風景區",
    "東部發電廠",
)

TITLE_TERMS = (
    "花蓮縣",
    "花蓮市",
    "花蓮港",
    "太魯閣",
    "鳳林鎮",
    "玉里鎮",
    "新城鄉",
    "吉安鄉",
    "壽豐鄉",
    "光復鄉",
    "豐濱鄉",
    "瑞穗鄉",
    "富里鄉",
    "秀林鄉",
    "萬榮鄉",
    "卓溪鄉",
)


def date_range(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def classify_candidate(record: dict) -> dict | None:
    unit_id = str(record.get("unit_id", ""))
    if is_in_scope(unit_id, EXISTING_PREFIX):
        return None

    brief = record.get("brief", {})
    if not isinstance(brief, dict) or brief.get("type") != "決標公告":
        return None

    unit_name = str(record.get("unit_name", ""))
    title = str(brief.get("title", ""))
    agency_matches = matched_terms(unit_name, AGENCY_TERMS)
    title_matches = matched_terms(title, TITLE_TERMS)
    if not agency_matches and not title_matches:
        return None

    candidate = {
        "date": record.get("date"),
        "unit_id": unit_id,
        "unit_name": unit_name,
        "job_number": record.get("job_number"),
        "title": title,
        "filename": record.get("filename"),
        "url": record.get("url"),
        "match_reasons": [],
        "review_status": "unreviewed",
    }
    if agency_matches:
        candidate["match_reasons"].append({
            "field": "unit_name",
            "terms": agency_matches,
        })
    if title_matches:
        candidate["match_reasons"].append({
            "field": "title",
            "terms": title_matches,
        })
    return candidate


def discover(
    start: dt.date,
    end: dt.date,
    output: Path,
    delay: float,
    attempts: int,
) -> None:
    if start > end:
        raise ValueError("開始日期不得晚於結束日期")
    if (end - start).days > 30:
        raise ValueError("探索模式一次最多31天")

    candidates: dict[tuple, dict] = {}
    errors: list[dict[str, str]] = []
    scanned_records = 0
    decision_records = 0

    for day in date_range(start, end):
        stamp = day.strftime("%Y%m%d")
        try:
            payload = request_json(
                f"{API_BASE}/listbydate",
                {"date": stamp},
                attempts,
                delay,
            )
            records = payload.get("records", [])
            if not isinstance(records, list):
                raise ValueError("records 不是陣列")
            scanned_records += len(records)
            for record in records:
                brief = record.get("brief", {})
                if isinstance(brief, dict) and brief.get("type") == "決標公告":
                    decision_records += 1
                candidate = classify_candidate(record)
                if candidate is None:
                    continue
                key = (
                    candidate.get("date"),
                    candidate.get("unit_id"),
                    candidate.get("job_number"),
                    candidate.get("filename"),
                )
                candidates[key] = candidate
            print(f"{stamp}: scanned={len(records)} candidates_total={len(candidates)}", flush=True)
            time.sleep(delay)
        except Exception as exc:
            errors.append({"date": stamp, "error": str(exc)})
            print(f"::warning::{stamp} 索引掃描失敗：{exc}", flush=True)

    ordered = sorted(
        candidates.values(),
        key=lambda row: tuple(
            str(row.get(key, ""))
            for key in ("date", "unit_id", "job_number", "filename")
        ),
    )
    write_json(output, {
        "scope": "hualien_discovery_outside_3.76.55",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "existing_prefix_excluded": EXISTING_PREFIX,
        "scanned_record_count": scanned_records,
        "decision_record_count": decision_records,
        "candidate_count": len(ordered),
        "error_count": len(errors),
        "agency_terms": list(AGENCY_TERMS),
        "title_terms": list(TITLE_TERMS),
        "candidates": ordered,
        "errors": errors,
        "limitations": [
            "名稱或地名命中僅為候選訊號，必須人工確認。",
            "索引未提供可靠履約地點，未命中名稱的案件仍可能漏列。",
            "本檔不包含案件詳情，確認後才進行第二階段下載。",
        ],
    })
    print(
        f"complete: days={(end-start).days+1} scanned={scanned_records} "
        f"decisions={decision_records} candidates={len(ordered)} errors={len(errors)}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=dt.date.fromisoformat, required=True)
    parser.add_argument("--end-date", type=dt.date.fromisoformat, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay", type=float, default=1.5)
    parser.add_argument("--attempts", type=int, default=5)
    args = parser.parse_args()
    discover(args.start_date, args.end_date, args.output, args.delay, args.attempts)


if __name__ == "__main__":
    main()
