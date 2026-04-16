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
            crawler_root = temp_path / "crawler"
            dataset_root = temp_path / "dataset"
            output_path = temp_path / "crawler-report.txt"
            raw_path = crawler_root / "raw.csv"
            cache_path = crawler_root / "stooq_cache" / "xauusd_stooq_d.csv"
            snapshot_path = dataset_root / "final_dataset.bak.csv"
            for path in (raw_path, cache_path, snapshot_path):
                path.parent.mkdir(parents=True, exist_ok=True)

            raw_path.write_text(
                "Date,Value\n"
                "2026-04-01,1\n"
                "2026-04-03,3\n",
                encoding="utf-8",
            )
            cache_path.write_text(
                "Date,Close\n"
                "2026-04-01,2000\n"
                "2026-04-02,2001\n",
                encoding="utf-8",
            )
            snapshot_path.write_text(
                "Date,Value\n"
                "2026-03-30,9\n"
                "2026-03-31,10\n",
                encoding="utf-8",
            )

            config = {
                "csv_path": str(raw_path),
                "log_dir": str(temp_path),
                "default_start_date": "01/01/2026",
            }
            args = SimpleNamespace(start="2026-04-01", end="2026-04-10", report_output=str(output_path))

            with patch(
                "app.crawler.GetVietNameseGoldPrice.gold_cli._collect_report_targets",
                return_value=[raw_path, cache_path, snapshot_path],
            ):
                result_path = gold_cli.cmd_report(args, config)

            self.assertEqual(result_path, output_path)
            self.assertTrue(output_path.exists())
            report_text = output_path.read_text(encoding="utf-8")
            self.assertIn("Crawler audit report", report_text)
            self.assertIn("Requested window: 01/04/2026 -> 10/04/2026", report_text)
            self.assertIn("Primary data files:", report_text)
            self.assertIn("Cache files:", report_text)
            self.assertIn("Dataset snapshots:", report_text)
            self.assertIn("data range: 2026-04-01 -> 2026-04-03", report_text)
            self.assertIn("calendar gaps: 1", report_text)
            self.assertIn("missing date preview: 2026-04-02", report_text)
            self.assertIn("status: needs-attention (calendar gaps=1)", report_text)
            self.assertIn("status: snapshot (backup/copy snapshot)", report_text)


if __name__ == "__main__":
    unittest.main()
