from __future__ import annotations

import asyncio
import csv
import io
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.db.models import MLModel, PredictionRecord, User
from app.services.prediction_export_service import (
    CSV_HEADERS,
    _datetime_end,
    _datetime_start,
    _row_from_record,
    build_prediction_export_query,
    export_prediction_history_csv,
)


class RecordingQuery:
    def __init__(self, rows: list[tuple[object, object, object]] | None = None) -> None:
        self.rows = list(rows or [])
        self.outerjoin_calls: list[tuple[object, ...]] = []
        self.filter_calls: list[object] = []
        self.order_by_args: tuple[object, ...] = ()
        self.execution_options_kwargs: dict[str, object] = {}
        self.yield_per_calls: list[int] = []

    def outerjoin(self, *args):
        self.outerjoin_calls.append(args)
        return self

    def filter(self, *args):
        self.filter_calls.extend(args)
        return self

    def order_by(self, *args):
        self.order_by_args = args
        return self

    def execution_options(self, **kwargs):
        self.execution_options_kwargs = kwargs
        return self

    def yield_per(self, chunk_size: int):
        self.yield_per_calls.append(chunk_size)
        for row in self.rows:
            yield row


class FakeSession:
    def __init__(self, query: RecordingQuery) -> None:
        self.query_result = query
        self.query_args: tuple[object, ...] | None = None

    def query(self, *entities):
        self.query_args = entities
        return self.query_result


async def _read_streaming_response(response) -> str:
    parts: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, (bytes, bytearray)):
            parts.append(bytes(chunk).decode("utf-8"))
        else:
            parts.append(str(chunk))
    return "".join(parts)


class PredictionExportServiceTest(unittest.TestCase):
    def test_row_from_record_handles_empty_forecast_json(self) -> None:
        record = SimpleNamespace(
            id=101,
            created_at=datetime(2026, 4, 4, 10, 30, tzinfo=timezone.utc),
            user_id=None,
            prediction_kind="price",
            source="sjc",
            model_id=None,
            selected_model_key=None,
            days=7,
            input_range=None,
            trend_label=None,
            used_fallback=False,
            forecast_json={},
        )

        row = _row_from_record(record, None, None)

        self.assertEqual(row["record_id"], 101)
        self.assertEqual(row["created_at"], "2026-04-04T10:30:00+00:00")
        self.assertEqual(row["user_id"], "")
        self.assertEqual(row["user_email"], "")
        self.assertEqual(row["model_code"], "")
        self.assertEqual(row["model_name"], "")
        self.assertEqual(row["future_start_date"], "")
        self.assertEqual(row["future_end_date"], "")
        self.assertEqual(row["predictions_count"], 0)
        self.assertEqual(row["first_prediction"], "")
        self.assertEqual(row["last_prediction"], "")
        self.assertEqual(row["min_prediction"], "")
        self.assertEqual(row["max_prediction"], "")
        self.assertEqual(row["trend_predictions"], "")
        self.assertEqual(row["trend_scores"], "")
        self.assertEqual(row["strategy"], "")

    def test_row_from_record_uses_prediction_payload_and_relationships(self) -> None:
        record = SimpleNamespace(
            id=202,
            created_at=datetime(2026, 4, 4, 11, 45, tzinfo=timezone.utc),
            user_id=7,
            prediction_kind="trend",
            source="sjc",
            model_id=9,
            selected_model_key="fallback-model",
            days=14,
            input_range="30d",
            trend_label="up",
            used_fallback=True,
            forecast_json={
                "predicted_prices": [1000, "1001.5", "not-a-number"],
                "future_dates": ["2026-04-05", "2026-04-06"],
                "trend_predictions": ["up", "flat"],
                "trend_scores": [0.2, "0.8"],
                "strategy": "gru",
            },
        )
        user = SimpleNamespace(email="tester@example.com")
        model = SimpleNamespace(code="gru-v2", name="GRU Model V2")

        row = _row_from_record(record, user, model)

        self.assertEqual(row["user_email"], "tester@example.com")
        self.assertEqual(row["model_code"], "gru-v2")
        self.assertEqual(row["model_name"], "GRU Model V2")
        self.assertEqual(row["future_start_date"], "2026-04-05")
        self.assertEqual(row["future_end_date"], "2026-04-06")
        self.assertEqual(row["predictions_count"], 2)
        self.assertEqual(row["first_prediction"], 1000.0)
        self.assertEqual(row["last_prediction"], 1001.5)
        self.assertEqual(row["min_prediction"], 1000.0)
        self.assertEqual(row["max_prediction"], 1001.5)
        self.assertEqual(row["trend_predictions"], "up|flat")
        self.assertEqual(row["trend_scores"], "0.2|0.8")
        self.assertEqual(row["strategy"], "gru")
        self.assertTrue(row["used_fallback"])

    def test_build_prediction_export_query_applies_filters_and_streams(self) -> None:
        query = RecordingQuery()
        session = FakeSession(query)
        from_date = date(2026, 4, 1)
        to_date = date(2026, 4, 3)

        result = build_prediction_export_query(
            session,
            user_id=7,
            prediction_kind="trend",
            source="sjc",
            model="12",
            from_date=from_date,
            to_date=to_date,
            used_fallback=True,
        )

        self.assertIs(result, query)
        self.assertEqual(session.query_args, (PredictionRecord, User, MLModel))
        self.assertEqual(len(query.outerjoin_calls), 2)
        self.assertIs(query.outerjoin_calls[0][0], User)
        self.assertIs(query.outerjoin_calls[1][0], MLModel)
        self.assertEqual(len(query.filter_calls), 7)
        self.assertEqual(query.filter_calls[0].left.name, "user_id")
        self.assertEqual(query.filter_calls[0].right.value, 7)
        self.assertEqual(query.filter_calls[1].left.name, "prediction_kind")
        self.assertEqual(query.filter_calls[1].right.value, "trend")
        self.assertEqual(query.filter_calls[2].left.name, "source")

        model_clause = query.filter_calls[3]
        model_names = {clause.left.name for clause in model_clause.clauses}
        self.assertEqual(model_names, {"selected_model_key", "code", "id"})

        self.assertEqual(query.filter_calls[4].left.name, "created_at")
        self.assertEqual(query.filter_calls[4].right.value, _datetime_start(from_date))
        self.assertEqual(query.filter_calls[5].left.name, "created_at")
        self.assertEqual(query.filter_calls[5].right.value, _datetime_end(to_date))
        self.assertEqual(query.filter_calls[6].left.name, "used_fallback")
        self.assertEqual(query.filter_calls[6].operator.__name__, "is_")
        self.assertEqual(query.execution_options_kwargs, {"stream_results": True})
        self.assertEqual(len(query.order_by_args), 2)
        self.assertEqual(query.order_by_args[0].element.name, "created_at")
        self.assertEqual(query.order_by_args[1].element.name, "id")

    def test_export_prediction_history_csv_streams_header_and_rows(self) -> None:
        record_one = SimpleNamespace(
            id=11,
            created_at=datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc),
            user_id=5,
            prediction_kind="price",
            source="sjc",
            model_id=3,
            selected_model_key="gru-v1",
            days=7,
            input_range="30d",
            trend_label="bullish",
            used_fallback=False,
            forecast_json={
                "predictions": [1000, 1001.25],
                "future_dates": ["2026-04-05", "2026-04-06"],
                "trend_predictions": ["up", "flat"],
                "trend_scores": [0.6, 0.4],
                "strategy": "knn",
            },
        )
        user_one = SimpleNamespace(email="owner@example.com")
        model_one = SimpleNamespace(code="gru-v1", name="GRU v1")

        record_two = SimpleNamespace(
            id=12,
            created_at=datetime(2026, 4, 4, 12, 5, tzinfo=timezone.utc),
            user_id=None,
            prediction_kind="trend",
            source="sjc",
            model_id=None,
            selected_model_key="fallback-model",
            days=3,
            input_range=None,
            trend_label=None,
            used_fallback=True,
            forecast_json=None,
        )

        query = RecordingQuery(rows=[(record_one, user_one, model_one), (record_two, None, None)])

        response = export_prediction_history_csv(query, filename="prediction-history-user-5.csv")
        content = asyncio.run(_read_streaming_response(response))

        self.assertEqual(response.headers["content-disposition"], 'attachment; filename="prediction-history-user-5.csv"')
        self.assertEqual(response.media_type, "text/csv; charset=utf-8")

        reader = csv.DictReader(io.StringIO(content))
        self.assertEqual(reader.fieldnames, CSV_HEADERS)

        rows = list(reader)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["record_id"], "11")
        self.assertEqual(rows[0]["user_email"], "owner@example.com")
        self.assertEqual(rows[0]["model_code"], "gru-v1")
        self.assertEqual(rows[0]["predictions_count"], "2")
        self.assertEqual(rows[0]["first_prediction"], "1000.0")
        self.assertEqual(rows[0]["last_prediction"], "1001.25")
        self.assertEqual(rows[0]["trend_predictions"], "up|flat")
        self.assertEqual(rows[0]["trend_scores"], "0.6|0.4")

        self.assertEqual(rows[1]["record_id"], "12")
        self.assertEqual(rows[1]["user_email"], "")
        self.assertEqual(rows[1]["model_code"], "fallback-model")
        self.assertEqual(rows[1]["predictions_count"], "0")
        self.assertEqual(rows[1]["first_prediction"], "")
        self.assertEqual(rows[1]["last_prediction"], "")
        self.assertEqual(rows[1]["trend_predictions"], "")
        self.assertEqual(rows[1]["trend_scores"], "")


if __name__ == "__main__":
    unittest.main()