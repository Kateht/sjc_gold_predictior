from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services import news_service


class NewsServiceRateLimitTest(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_last_request_at = news_service._LAST_GDELT_REQUEST_AT
        self.addCleanup(self._restore_state)

    def _restore_state(self) -> None:
        news_service._LAST_GDELT_REQUEST_AT = self._previous_last_request_at

    def test_fetch_gdelt_articles_throttles_back_to_back_calls(self) -> None:
        response = SimpleNamespace(
            status_code=200,
            text='{"articles": []}',
            json=lambda: {"articles": []},
            raise_for_status=lambda: None,
        )

        with patch("app.services.news_service.requests.get", return_value=response) as get_mock, patch(
            "app.services.news_service.time.sleep"
        ) as sleep_mock:
            news_service._LAST_GDELT_REQUEST_AT = datetime.now(timezone.utc)

            articles = news_service._fetch_gdelt_articles("central bank fed rates policy gold", limit=8)

            self.assertEqual(articles, [])
            self.assertTrue(sleep_mock.called)
            self.assertGreaterEqual(float(sleep_mock.call_args.args[0]), 4.9)
            get_mock.assert_called_once()

    def test_fetch_gdelt_articles_retries_on_rate_limit_message(self) -> None:
        rate_limit_response = SimpleNamespace(
            status_code=200,
            text="Please limit requests to one every 5 seconds or contact kalev.leetaru5@gmail.com for larger queries.",
            json=lambda: {},
            raise_for_status=lambda: None,
        )
        ok_response = SimpleNamespace(
            status_code=200,
            text='{"articles": []}',
            json=lambda: {"articles": []},
            raise_for_status=lambda: None,
        )
        responses = [rate_limit_response, ok_response]

        def fake_get(*args, **kwargs):
            return responses.pop(0)

        with patch("app.services.news_service.requests.get", side_effect=fake_get) as get_mock, patch(
            "app.services.news_service.time.sleep"
        ) as sleep_mock:
            news_service._LAST_GDELT_REQUEST_AT = None

            articles = news_service._fetch_gdelt_articles("central bank fed rates policy gold", limit=8)

            self.assertEqual(articles, [])
            self.assertEqual(get_mock.call_count, 2)
            self.assertGreaterEqual(sleep_mock.call_count, 1)


if __name__ == "__main__":
    unittest.main()
