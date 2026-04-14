from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from app.crawler.GetVietNameseGoldPrice.merge_outputs import (
    MergePaths,
    OZ_PER_LUONG,
    build_final_uso_with_vn_gold_vnd_thousand_imputed,
)


class MergeOutputsTest(unittest.TestCase):
    def test_vnd_thousand_conversion_aligns_fx_by_date(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            final_uso_usd_path = root / "final_uso_usd_with_vn_gold_usd_oz_imputed.csv"
            fx_cache_path = root / "usd_vnd_close_yf.csv"
            output_path = root / "final_uso_with_vn_gold_vnd_thousand_imputed.csv"

            pd.DataFrame(
                [
                    {
                        "Date": "2026-01-01",
                        "Open": 20.0,
                        "Adj Close": 21.0,
                        "Volume": 1000.0,
                        "PNJ_gia_mua": 100.0,
                        "SJC_gia_ban": 110.0,
                    },
                    {
                        "Date": "2026-01-02",
                        "Open": 22.0,
                        "Adj Close": 23.0,
                        "Volume": 2000.0,
                        "PNJ_gia_mua": 101.0,
                        "SJC_gia_ban": 111.0,
                    },
                ]
            ).to_csv(final_uso_usd_path, index=False)

            pd.DataFrame(
                [
                    {"Date": "2026-01-01", "USDVND_Close": 25_000.0},
                    {"Date": "2026-01-02", "USDVND_Close": 26_000.0},
                ]
            ).to_csv(fx_cache_path, index=False)

            paths = MergePaths(
                root_dir=root,
                gold_csv=root / "gia_vang_pnj_sjc.csv",
                xauusd_cache_csv=root / "xauusd_stooq_d.csv",
                usd_vnd_cache_csv=fx_cache_path,
                final_uso_csv=root / "final_uso.csv",
                vn_gold_usd_oz_csv=root / "gia_vang_pnj_sjc_usd_oz.csv",
                final_uso_usd_with_vn_gold_usd_oz_csv=final_uso_usd_path,
                final_uso_usd_with_vn_gold_usd_oz_imputed_csv=final_uso_usd_path,
                final_uso_with_vn_gold_vnd_thousand_imputed_csv=output_path,
            )

            result_path = build_final_uso_with_vn_gold_vnd_thousand_imputed(paths)

            self.assertEqual(result_path, output_path)
            result = pd.read_csv(result_path)
            self.assertFalse(result[["Open", "Adj Close", "PNJ_gia_mua", "SJC_gia_ban"]].isna().any().any())
            self.assertEqual(result.loc[0, "Volume"], 1000.0)
            self.assertAlmostEqual(result.loc[0, "Open"], 20.0 * 25_000.0 / 1000.0)
            self.assertAlmostEqual(result.loc[1, "Adj Close"], 23.0 * 26_000.0 / 1000.0)
            self.assertAlmostEqual(result.loc[0, "PNJ_gia_mua"], 100.0 * 25_000.0 * OZ_PER_LUONG / 1000.0)
            self.assertAlmostEqual(result.loc[1, "SJC_gia_ban"], 111.0 * 26_000.0 * OZ_PER_LUONG / 1000.0)


if __name__ == "__main__":
    unittest.main()