from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.crawler.GetVietNameseGoldPrice import gold_cli
from app.crawler.GetVietNameseGoldPrice import Update_gia_vang as ug


class GoldCliReportTest(unittest.TestCase):
    def test_cmd_report_writes_downloadable_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            output_path = temp_path / "crawler-report.txt"
            raw_path = temp_path / "raw.csv"
            final_dataset_path = temp_path / "dataset" / "final_dataset.csv"
            backup_path = final_dataset_path.with_suffix(".bak.csv")
            merged_market_path = temp_path / "app" / "crawler" / "GetVietNameseGoldPrice" / "final_uso_with_vn_gold_vnd_thousand_imputed.csv"

            raw_path.parent.mkdir(parents=True, exist_ok=True)
            final_dataset_path.parent.mkdir(parents=True, exist_ok=True)
            merged_market_path.parent.mkdir(parents=True, exist_ok=True)

            raw_value_row = ",".join(str(index + 1) for index in range(len(ug.ALL_COLS)))
            raw_blank_row = ",".join("" for _ in ug.ALL_COLS)
            raw_path.write_text(
                "Ngày," + ",".join(ug.ALL_COLS) + "\n"
                f"01/01/2006,{raw_value_row}\n"
                f"02/01/2006,{raw_blank_row}\n"
                f"03/01/2006,5,{','.join([''] * (len(ug.ALL_COLS) - 1))}\n",
                encoding="utf-8",
            )
            final_dataset_path.write_text(
                "Date,SJC,Interest\n"
                "2026-04-15,100,0.5\n"
                "2026-04-16,101,0.6\n",
                encoding="utf-8",
            )
            backup_path.write_text(
                "Date,SJC,Interest\n"
                "2026-04-15,100,0.5\n"
                "2026-04-16,101,0.6\n",
                encoding="utf-8",
            )
            merged_market_path.write_text(
                "Date,Final\n"
                "2026-04-15,1\n"
                "2026-04-16,2\n",
                encoding="utf-8",
            )

            config = {
                "csv_path": str(raw_path),
                "log_dir": str(temp_path),
                "default_start_date": "01/01/2006",
            }
            args = SimpleNamespace(start="01/01/2006", end="03/01/2006", report_output=str(output_path))

            with patch.object(gold_cli.settings, "LOCAL_DATASET_PATH", str(final_dataset_path)), \
                patch.object(gold_cli.settings, "CRAWLER_DATASET_PATH", str(raw_path)), \
                patch.object(gold_cli.settings, "PROJECT_ROOT", str(temp_path)):
                result_path = gold_cli.cmd_report(args, config)

            self.assertEqual(result_path, output_path)
            self.assertTrue(output_path.exists())
            report_text = output_path.read_text(encoding="utf-8")
            self.assertIn("Crawler audit report", report_text)
            self.assertIn("Source CSV:", report_text)
            self.assertIn("Range: 01/01/2006 -> 03/01/2006", report_text)
            self.assertIn("Raw source audit:", report_text)
            self.assertIn("days missing all checked columns: 1", report_text)
            self.assertIn("days missing at least one checked column: 2", report_text)
            self.assertIn("Training dataset:", report_text)
            self.assertIn("final_dataset.csv", report_text)
            self.assertIn("final_dataset.bak.csv", report_text)
            self.assertIn("Export datasets:", report_text)
            self.assertIn("sjc-history-csv", report_text)
            self.assertIn("crawler-export-csv", report_text)
            self.assertIn("merged-market-csv", report_text)


if __name__ == "__main__":
    unittest.main()
