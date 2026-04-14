from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.crawler.GetVietNameseGoldPrice import gold_cli


class GoldCliReportTest(unittest.TestCase):
    def test_cmd_report_writes_downloadable_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "crawler-report.txt"
            config = {
                "csv_path": str(temp_path / "raw.csv"),
                "log_dir": str(temp_path),
                "default_start_date": "01/01/2026",
            }
            args = SimpleNamespace(start="2026-04-01", end="2026-04-10", report_output=str(output_path))

            with patch("app.crawler.GetVietNameseGoldPrice.gold_cli.ug.report_missing_dates") as report_mock:
                report_mock.side_effect = lambda *unused_args, **unused_kwargs: print("Khoảng kiểm tra: 01/04/2026 -> 10/04/2026")

                result_path = gold_cli.cmd_report(args, config)

            self.assertEqual(result_path, output_path)
            self.assertTrue(output_path.exists())
            report_text = output_path.read_text(encoding="utf-8")
            self.assertIn("Crawler audit report", report_text)
            self.assertIn("Khoảng kiểm tra: 01/04/2026 -> 10/04/2026", report_text)


if __name__ == "__main__":
    unittest.main()
