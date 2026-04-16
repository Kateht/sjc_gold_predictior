from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from app.crawler.GetVietNameseGoldPrice import Update_gia_vang as ug


class XauusdCacheFallbackTest(unittest.TestCase):
    def test_invalid_stooq_response_creates_empty_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "xauusd_stooq_d.csv"

            with patch.object(ug, "_fetch_text", return_value="not a csv"):
                result = ug.load_xauusd_ohlc_cache(
                    date(2026, 4, 1),
                    date(2026, 4, 2),
                    max_file_age_hours=0,
                    cache_path=str(cache_path),
                )

            self.assertEqual(result, {})
            self.assertTrue(cache_path.exists())
            self.assertTrue(cache_path.read_text(encoding="utf-8").startswith("Date,Open,High,Low,Close"))


if __name__ == "__main__":
    unittest.main()
