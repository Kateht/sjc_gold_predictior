from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.crawler.GetVietNameseGoldPrice.build_final_dataset import _build_backup_path, _merge_with_existing_output, _write_and_return


class FinalDatasetMergeTest(unittest.TestCase):
    def test_merge_updates_overlapping_rows_and_keeps_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "final_dataset.csv"
            pd.DataFrame(
                [
                    {"Date": "2025-12-30", "SJC": 35.0, "Interest": 0.1},
                    {"Date": "2025-12-31", "SJC": 35.1, "Interest": 0.1},
                ]
            ).to_csv(output_path, index=False)

            new_slice = pd.DataFrame(
                [
                    {"Date": "2025-12-31", "SJC": 35.9, "Interest": 0.2},
                    {"Date": "2026-01-02", "SJC": 36.2, "Interest": 0.2},
                ]
            )

            merged = _merge_with_existing_output(new_slice, output_path)

            self.assertEqual(list(merged["Date"]), ["2025-12-30", "2025-12-31", "2026-01-02"])
            self.assertAlmostEqual(float(merged.loc[0, "SJC"]), 35.0)
            self.assertAlmostEqual(float(merged.loc[1, "SJC"]), 35.9)
            self.assertAlmostEqual(float(merged.loc[2, "SJC"]), 36.2)

    def test_write_and_return_writes_backup_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "final_dataset.csv"
            frame = pd.DataFrame(
                [
                    {"Date": "2026-01-01", "SJC": 40.0, "Interest": 0.2},
                ]
            )

            written_path = _write_and_return(frame, output_path)
            backup_path = output_path.with_suffix(".bak.csv")

            self.assertEqual(written_path, output_path)
            self.assertTrue(output_path.exists())
            self.assertTrue(backup_path.exists())
            self.assertEqual(output_path.read_text(encoding="utf-8"), backup_path.read_text(encoding="utf-8"))

    def test_backup_path_does_not_double_suffix(self) -> None:
        output_path = Path("/tmp/final_dataset.bak.csv")

        self.assertEqual(_build_backup_path(output_path), output_path)


if __name__ == "__main__":
    unittest.main()