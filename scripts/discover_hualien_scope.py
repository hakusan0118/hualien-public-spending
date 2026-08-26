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

# These are review signals, not a complete nationwide place-name gazetteer.
NON_HUALIEN_TERMS = (
    "臺東縣",
    "台東縣",
    "臺東市",
    "台東市",
    "卑南",
    "利吉惡地",
)

CROSS_COUNTY_AGENCY_TERMS = (
    "太魯閣國家公園",
    "花東縱谷國家風景區",
)


def date_range(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    return [term for term in terms if term in text]


def scope_review(unit_name: str, title: str, title_matches: list[str]) -> tuple[str, list[str]]:
    """Return a conservative geographic classification and its evidence."""
    hualien_evidence = list(title_matches)
    outside_evidence = matched_terms(title, NON_HUALIEN_TERMS)
    cross_agency_evidence = matched_terms(unit_name, CROSS_COUNTY_AGENCY_TERMS)

    if hualien_evidence and outside_evidence:
        return "cross_county_needs_review", hualien_evidence + outside_evidence
    if outside_evidence:
        return "exclude_non_hualien", outside_evidence
    if hualien_evidence:
        return "confirmed_hualien", hualien_evidence
    if cross_agency_evidence:
        return "cross_county_needs_review", cross_agency_evidence
    if "花蓮" in unit_name or "東部發電廠" in unit_name:
        return "confirmed_hualien", matched_terms(unit_name, AGENCY_TERMS)
    return "cross_county_needs_review", []


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

    review_status, review_evidence = scope_review(unit_name, title, title_matches)
    candidate = {
        "date": record.get("date"),
        "unit_id": unit_id,
        "unit_name": unit_name,
        "job_number": record.get("job_number"),
        "title": title,
        "filename": record.get("filename"),
        "url": record.get("url"),
        "match_reasons": [],
        "scope_review": review_status,
        "scope_review_evidence": review_evidence,
        "review_status": "unreviewed",
    }
    if agency_matches:
        candidate["match_reasons"].append({"field": "unit_name", "terms": agency_matches})
    if title_matches:
        candidate["match_reasons"].append({"field": "title", "terms": title_matches})
    return candidate


def is_weekend_non_json(day: dt.date, exc: Exception) -> bool:
    """Identify the API's observed weekend no-index response without hiding it."""
    return day.weekday() >= 5 and "非 JSON 回應" in str(exc)


def discover(start: dt.date, end: dt.date, output: Path, delay: float, attempts: int) -> None:
    if start > end:
        raise ValueError("開始日期不得晚於結束日期")
    if (end - start).days > 30:
        raise ValueError("探索模式一次最多31天")

    candidates: dict[tuple, dict] = {}
    errors: list[dict[str, str]] = []
    skipped_dates: list[dict[str, str]] = []
    scanned_records = 0
    decision_records = 0

    for day in date_range(start, end):
        stamp = day.strftime("%Y%m%d")
        try:
            payload = request_json(f"{API_BASE}/listbydate", {"date": stamp}, attempts, delay)
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
                key = tuple(candidate.get(key) for key in ("date", "unit_id", "job_number", "filename"))
                candidates[key] = candidate
            print(f"{stamp}: scanned={len(records)} candidates_total={len(candidates)}", flush=True)
            time.sleep(delay)
        except Exception as exc:
            if is_weekend_non_json(day, exc):
                skipped_dates.append({
                    "date": stamp,
                    "reason": "weekend_non_json",
                    "detail": str(exc),
                })
                print(f"::notice::{stamp} 週末索引未提供 JSON，已明確標記為未掃描", flush=True)
            else:
                errors.append({"date": stamp, "error": str(exc)})
                print(f"::warning::{stamp} 索引掃描失敗：{exc}", flush=True)

    ordered = sorted(candidates.values(), key=lambda row: tuple(
        str(row.get(key, "")) for key in ("date", "unit_id", "job_number", "filename")
    ))
    review_counts = {
        status: sum(row["scope_review"] == status for row in ordered)
        for status in ("confirmed_hualien", "cross_county_needs_review", "exclude_non_hualien")
    }
    write_json(output, {
        "scope": "hualien_discovery_outside_3.76.55",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "existing_prefix_excluded": EXISTING_PREFIX,
        "scanned_record_count": scanned_records,
        "decision_record_count": decision_records,
        "candidate_count": len(ordered),
        "scope_review_counts": review_counts,
        "error_count": len(errors),
        "skipped_date_count": len(skipped_dates),
        "agency_terms": list(AGENCY_TERMS),
        "title_terms": list(TITLE_TERMS),
        "candidates": ordered,
        "skipped_dates": skipped_dates,
        "errors": errors,
        "limitations": [
            "名稱或地名命中僅為候選訊號，必須人工確認。",
            "scope_review 是保守的初步分類，不代表最終納入或排除決定。",
            "skipped_dates 仍屬資料缺口，不可視為該日零案件。",
            "索引未提供可靠履約地點，未命中名稱的案件仍可能漏列。",
            "本檔不包含案件詳情，確認後才進行第二階段下載。",
        ],
    })
    print(
        f"complete: days={(end-start).days+1} scanned={scanned_records} decisions={decision_records} "
        f"candidates={len(ordered)} skipped={len(skipped_dates)} errors={len(errors)}",
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
