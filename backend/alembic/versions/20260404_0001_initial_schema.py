"""initial schema

Revision ID: 20260404_0001
Revises:
Create Date: 2026-04-04 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), server_default=sa.text("'user'"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_jti", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_jti", name="uq_refresh_tokens_token_jti"),
    )

    op.create_table(
        "ml_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("prediction_kind", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), server_default=sa.text("'builtin'"), nullable=False),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code", name="uq_ml_models_code"),
    )

    op.create_table(
        "prediction_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("model_id", sa.Integer(), nullable=True),
        sa.Column("prediction_kind", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=50), server_default=sa.text("'sjc'"), nullable=False),
        sa.Column("input_range", sa.String(length=32), nullable=True),
        sa.Column("days", sa.Integer(), nullable=False),
        sa.Column("selected_model_key", sa.String(length=120), nullable=True),
        sa.Column("forecast_json", sa.JSON(), nullable=False),
        sa.Column("trend_label", sa.String(length=32), nullable=True),
        sa.Column("used_fallback", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["model_id"], ["ml_models.id"], ondelete="SET NULL"),
    )

    op.create_table(
        "price_history_points",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("series_key", sa.String(length=50), nullable=False),
        sa.Column("series_name", sa.String(length=120), nullable=False),
        sa.Column("symbol", sa.String(length=50), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("series_key", "observed_at", name="uq_series_key_observed_at"),
    )

    op.create_table(
        "news_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("slug", name="uq_news_categories_slug"),
    )

    op.create_table(
        "news_articles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("slug", sa.String(length=180), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["news_categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("slug", name="uq_news_articles_slug"),
    )

    op.create_table(
        "gold_source_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("region", sa.String(length=120), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code", name="uq_gold_source_links_code"),
    )

    op.create_table(
        "dataset_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("csv_path", sa.String(length=500), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("file_format", sa.String(length=20), server_default=sa.text("'csv'"), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_default", sa.Boolean(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("code", name="uq_dataset_sources_code"),
    )

    op.create_table(
        "crawler_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=32), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("trigger_source", sa.String(length=50), server_default=sa.text("'admin_web'"), nullable=False),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("output_text", sa.Text(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("log_path", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_ml_models_created_by_id", "ml_models", ["created_by_id"])
    op.create_index("ix_ml_models_prediction_kind", "ml_models", ["prediction_kind"])
    op.create_index("ix_prediction_records_user_id", "prediction_records", ["user_id"])
    op.create_index("ix_prediction_records_model_id", "prediction_records", ["model_id"])
    op.create_index("ix_prediction_records_prediction_kind", "prediction_records", ["prediction_kind"])
    op.create_index("ix_price_history_points_series_key", "price_history_points", ["series_key"])
    op.create_index("ix_price_history_points_observed_at", "price_history_points", ["observed_at"])
    op.create_index("ix_news_categories_created_by_id", "news_categories", ["created_by_id"])
    op.create_index("ix_news_articles_category_id", "news_articles", ["category_id"])
    op.create_index("ix_news_articles_published_at", "news_articles", ["published_at"])
    op.create_index("ix_gold_source_links_created_by_id", "gold_source_links", ["created_by_id"])
    op.create_index("ix_dataset_sources_created_by_id", "dataset_sources", ["created_by_id"])
    op.create_index("ix_crawler_runs_task", "crawler_runs", ["task"])
    op.create_index("ix_crawler_runs_created_by_id", "crawler_runs", ["created_by_id"])


def downgrade() -> None:
    op.drop_index("ix_crawler_runs_created_by_id", table_name="crawler_runs")
    op.drop_index("ix_crawler_runs_task", table_name="crawler_runs")
    op.drop_index("ix_dataset_sources_created_by_id", table_name="dataset_sources")
    op.drop_index("ix_gold_source_links_created_by_id", table_name="gold_source_links")
    op.drop_index("ix_news_articles_published_at", table_name="news_articles")
    op.drop_index("ix_news_articles_category_id", table_name="news_articles")
    op.drop_index("ix_news_categories_created_by_id", table_name="news_categories")
    op.drop_index("ix_price_history_points_observed_at", table_name="price_history_points")
    op.drop_index("ix_price_history_points_series_key", table_name="price_history_points")
    op.drop_index("ix_prediction_records_prediction_kind", table_name="prediction_records")
    op.drop_index("ix_prediction_records_model_id", table_name="prediction_records")
    op.drop_index("ix_prediction_records_user_id", table_name="prediction_records")
    op.drop_index("ix_ml_models_prediction_kind", table_name="ml_models")
    op.drop_index("ix_ml_models_created_by_id", table_name="ml_models")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")

    op.drop_table("crawler_runs")
    op.drop_table("dataset_sources")
    op.drop_table("gold_source_links")
    op.drop_table("news_articles")
    op.drop_table("news_categories")
    op.drop_table("price_history_points")
    op.drop_table("prediction_records")
    op.drop_table("ml_models")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
