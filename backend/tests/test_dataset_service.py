from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.services.dataset_service import export_dataset_source_csv


class DatasetServiceExportTest(unittest.TestCase):
    def test_export_dataset_source_csv_falls_back_to_canonical_local_dataset(self) -> None:
        source = SimpleNamespace(
            csv_path="C:/does/not/exist/final_dataset_new.csv",
            code="sjc-history-csv",
        )

        result = export_dataset_source_csv(source)

        self.assertEqual(Path(result).resolve(), Path(settings.LOCAL_DATASET_PATH).resolve())


if __name__ == "__main__":
    unittest.main()