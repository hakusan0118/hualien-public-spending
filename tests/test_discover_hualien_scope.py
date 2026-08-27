import datetime as dt
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from discover_hualien_scope import classify_candidate, non_json_skip_reason


def record(unit_id, unit_name, title, notice_type="決標公告"):
    return {
        "date": 20250106,
        "filename": "example",
        "brief": {"type": notice_type, "title": title},
        "job_number": "TEST-1",
        "unit_id": unit_id,
        "unit_name": unit_name,
        "url": "/example",
    }


class DiscoverHualienScopeTests(unittest.TestCase):
    def test_excludes_existing_hualien_prefix(self):
        self.assertIsNone(classify_candidate(record("3.76.55.51", "花蓮縣花蓮市公所", "測試採購")))

    def test_cross_county_agency_requires_review(self):
        candidate = classify_candidate(record(
            "3.15.8", "交通部觀光署花東縱谷國家風景區管理處", "清潔案"
        ))
        self.assertEqual(candidate["scope_review"], "cross_county_needs_review")

    def test_explicit_hualien_title_is_confirmed(self):
        candidate = classify_candidate(record("3.15.25", "交通部公路局", "花蓮縣道路改善工程"))
        self.assertEqual(candidate["scope_review"], "confirmed_hualien")

    def test_non_hualien_title_is_excluded(self):
        candidate = classify_candidate(record(
            "3.15.8", "交通部觀光署花東縱谷國家風景區管理處", "卑南利吉惡地改善工程"
        ))
        self.assertEqual(candidate["scope_review"], "exclude_non_hualien")

    def test_mixed_locations_require_review(self):
        candidate = classify_candidate(record(
            "3.15.8", "交通部觀光署花東縱谷國家風景區管理處", "花蓮縣及臺東縣設施改善"
        ))
        self.assertEqual(candidate["scope_review"], "cross_county_needs_review")

    def test_hualien_named_agency_is_confirmed(self):
        candidate = classify_candidate(record("3.11.94", "法務部矯正署花蓮監獄", "一般採購"))
        self.assertEqual(candidate["scope_review"], "confirmed_hualien")

    def test_ignores_non_award_notice(self):
        self.assertIsNone(classify_candidate(record(
            "3.15.25", "交通部公路局", "花蓮縣道路改善工程", "招標公告"
        )))

    def test_ignores_unrelated_record(self):
        self.assertIsNone(classify_candidate(record("3.79", "臺北市政府", "一般清潔採購")))

    def test_non_json_response_is_an_explicit_gap(self):
        self.assertEqual(
            non_json_skip_reason(dt.date(2025, 1, 11), ValueError("非 JSON 回應：text/html")),
            "weekend_non_json",
        )
        self.assertEqual(
            non_json_skip_reason(dt.date(2011, 2, 3), ValueError("非 JSON 回應：text/html")),
            "non_json_no_index",
        )
        self.assertIsNone(non_json_skip_reason(dt.date(2025, 1, 11), TimeoutError("timeout")))


if __name__ == "__main__":
    unittest.main()
