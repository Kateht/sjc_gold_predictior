from __future__ import annotations

import unittest
from datetime import date

from app.schemas.crawler import CrawlerRunCreate, CrawlerTask
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
