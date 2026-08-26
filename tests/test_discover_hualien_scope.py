import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from discover_hualien_scope import classify_candidate


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
        row = record("3.76.55.51", "花蓮縣花蓮市公所", "測試採購")
        self.assertIsNone(classify_candidate(row))

    def test_matches_central_agency_name(self):
        row = record("3.15.8", "交通部觀光署花東縱谷國家風景區管理處", "清潔案")
        candidate = classify_candidate(row)
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["match_reasons"][0]["field"], "unit_name")

    def test_matches_hualien_location_in_title(self):
        row = record("3.15.25", "交通部公路局", "花蓮縣道路改善工程")
        candidate = classify_candidate(row)
        self.assertIsNotNone(candidate)
        fields = [reason["field"] for reason in candidate["match_reasons"]]
        self.assertIn("title", fields)

    def test_ignores_non_award_notice(self):
        row = record("3.15.25", "交通部公路局", "花蓮縣道路改善工程", "招標公告")
        self.assertIsNone(classify_candidate(row))

    def test_ignores_unrelated_record(self):
        row = record("3.79", "臺北市政府", "一般清潔採購")
        self.assertIsNone(classify_candidate(row))


if __name__ == "__main__":
    unittest.main()
