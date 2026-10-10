import hashlib
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "assets/project-template/scripts"))
from content_decay_report import bundle
from fetch_content_decay import collect, default_window, fetch_day


class ContentDecayTests(unittest.TestCase):
    def test_window_uses_finalized_day_not_local_month(self):
        self.assertEqual(default_window(date(2026, 10, 2)), (date(2025, 9, 1), date(2026, 9, 29)))
        self.assertEqual(default_window(date(2026, 10, 10)), (date(2025, 10, 1), date(2026, 10, 7)))

    def test_fetch_uses_final_page_grain(self):
        service = MagicMock()
        service.searchanalytics().query().execute.return_value = {"responseAggregationType": "byPage", "rows": []}
        self.assertEqual(fetch_day(service, "sc-domain:example.com", date(2026, 8, 1)), [])
        body = service.searchanalytics().query.call_args.kwargs["body"]
        self.assertEqual(body["dimensions"], ["date", "page"])
        self.assertEqual(body["dataState"], "final")
        self.assertEqual(body["startDate"], body["endDate"])

    def test_collect_binds_empty_days_and_exact_csv(self):
        service = MagicMock()
        service.searchanalytics().query().execute.return_value = {"responseAggregationType": "byPage", "rows": []}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "data.csv"
            result = collect(service, "sc-domain:example.com", date(2026, 8, 1), date(2026, 8, 2), output)
            manifest = json.loads(result.read_bytes())
            self.assertEqual(manifest["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
            self.assertEqual(len(manifest["days"]), 2)
            self.assertEqual(manifest["row_count"], 0)

    def test_fetch_paginates_and_stops_at_daily_cap(self):
        service = MagicMock()
        row = {"keys": ["2026-08-01", "/a"], "clicks": 1, "impressions": 2, "ctr": .5, "position": 3}
        execute = service.searchanalytics().query().execute
        execute.return_value = {"responseAggregationType": "byPage", "rows": [row] * 25000}
        self.assertEqual(len(fetch_day(service, "sc-domain:example.com", date(2026, 8, 1))), 50000)
        self.assertEqual(execute.call_count, 2)
        self.assertEqual(service.searchanalytics().query.call_args.kwargs["body"]["startRow"], 25000)

    def test_failure_preserves_previous_artifacts(self):
        service = MagicMock()
        service.searchanalytics().query().execute.side_effect = RuntimeError("network")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "data.csv"
            output.write_text("old")
            manifest = output.with_suffix(".manifest.json")
            manifest.write_text("old manifest")
            with self.assertRaises(RuntimeError):
                collect(service, "sc-domain:example.com", date(2026, 8, 1), date(2026, 8, 2), output)
            self.assertEqual(output.read_text(), "old")
            self.assertEqual(manifest.read_text(), "old manifest")

    def test_report_self_contained_and_escapes_script_breakout(self):
        html = bundle(ROOT / "assets/project-template/decay", {"text": '</script><script>alert("x")</script>'})
        self.assertNotIn('<script src=', html)
        self.assertNotIn('href="style.css"', html)
        self.assertIn('\\u003c/script>', html)
        self.assertIn("connect-src 'none'", html)
        self.assertNotIn('<script>alert("x")', html)


if __name__ == "__main__":
    unittest.main()
