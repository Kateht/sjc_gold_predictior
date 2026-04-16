from __future__ import annotations

import unittest
from datetime import date

from app.schemas.crawler import CrawlerRunCreate, CrawlerStartMode, CrawlerTask
from app.services.crawler_service import _build_crawler_command


class CrawlerServiceCommandTest(unittest.TestCase):
    def test_pipeline_command_omits_end_date(self) -> None:
        payload = CrawlerRunCreate(
            task=CrawlerTask.pipeline,
            start=date(2026, 4, 1),
            end=date(2026, 4, 10),
        )

        command = _build_crawler_command(payload)

        self.assertIn("pipeline", command)
        self.assertIn("--start", command)
        self.assertIn("2026-04-01", command)
        self.assertNotIn("--end", command)
        self.assertNotIn("2026-04-10", command)

    def test_report_command_keeps_end_date(self) -> None:
        payload = CrawlerRunCreate(
            task=CrawlerTask.report,
            start=date(2026, 4, 1),
            end=date(2026, 4, 10),
        )

        command = _build_crawler_command(payload)

        self.assertIn("report", command)
        self.assertIn("--start", command)
        self.assertIn("--end", command)
        self.assertIn("2026-04-10", command)

    def test_report_command_includes_report_output_path(self) -> None:
        payload = CrawlerRunCreate(
            task=CrawlerTask.report,
            start=date(2026, 4, 1),
            end=date(2026, 4, 10),
        )

        command = _build_crawler_command(payload, report_output_path="/tmp/crawler-report.txt")

        self.assertIn("--report-output", command)
        self.assertIn("/tmp/crawler-report.txt", command)

    def test_command_includes_log_file_and_start_mode(self) -> None:
        payload = CrawlerRunCreate(
            task=CrawlerTask.update,
            start=date(2026, 4, 1),
        )

        payload.start_mode = CrawlerStartMode.nearest_data
        command = _build_crawler_command(payload, log_file_path="/tmp/crawler-run.log")

        self.assertIn("--log-file", command)
        self.assertIn("/tmp/crawler-run.log", command)
        self.assertIn("--start-mode", command)
        self.assertIn("nearest-data", command)
