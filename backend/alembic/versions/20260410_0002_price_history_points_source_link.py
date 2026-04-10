"""link price history points to gold source links

Revision ID: 20260410_0002
Revises: 20260404_0001
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260410_0002"
down_revision = "20260404_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("price_history_points", sa.Column("gold_source_link_id", sa.Integer(), nullable=True))

    connection = op.get_bind()

    gold_source_links = sa.table(
        "gold_source_links",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("source_url", sa.String()),
        sa.column("source_type", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("region", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )

    canonical_sources = [
        {
            "code": "sjc-official",
            "name": "SJC Official",
            "source_url": "https://sjc.com.vn",
            "source_type": "official",
            "description": "Nguon gia vang SJC chinh thuc",
            "region": "Vietnam",
            "sort_order": 1,
            "is_active": True,
        },
        {
            "code": "goldprice-reference",
            "name": "GoldPrice Reference",
            "source_url": "https://goldprice.org",
            "source_type": "reference",
            "description": "Nguon tham chieu gia vang the gioi",
            "region": "Global",
            "sort_order": 3,
            "is_active": True,
        },
    ]

    existing_codes = {
        row.code for row in connection.execute(sa.select(gold_source_links.c.code)).all()
    }
    rows_to_insert = [payload for payload in canonical_sources if payload["code"] not in existing_codes]
    if rows_to_insert:
        connection.execute(gold_source_links.insert(), rows_to_insert)

    source_rows = connection.execute(sa.select(gold_source_links.c.id, gold_source_links.c.code)).all()
    source_id_by_code = {row.code: row.id for row in source_rows}

    price_history_points = sa.table(
        "price_history_points",
        sa.column("id", sa.Integer()),
        sa.column("series_key", sa.String()),
        sa.column("gold_source_link_id", sa.Integer()),
    )

    series_code_by_key = {
        "sjc": "sjc-official",
        "world": "goldprice-reference",
    }

    history_rows = connection.execute(
        sa.select(price_history_points.c.id, price_history_points.c.series_key).where(
            price_history_points.c.gold_source_link_id.is_(None)
        )
    ).all()

    for row in history_rows:
        series_key = (row.series_key or "").strip().lower()
        source_code = series_code_by_key.get(series_key, "sjc-official")
        source_id = source_id_by_code[source_code]
        connection.execute(
            price_history_points.update()
            .where(price_history_points.c.id == row.id)
            .values(gold_source_link_id=source_id)
        )

    with op.batch_alter_table("price_history_points") as batch_op:
        batch_op.alter_column("gold_source_link_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_price_history_points_gold_source_link_id_gold_source_links",
            "gold_source_links",
            ["gold_source_link_id"],
            ["id"],
        )

    op.create_index("ix_price_history_points_gold_source_link_id", "price_history_points", ["gold_source_link_id"])


def downgrade() -> None:
    op.drop_index("ix_price_history_points_gold_source_link_id", table_name="price_history_points")

    with op.batch_alter_table("price_history_points") as batch_op:
        batch_op.drop_constraint(
            "fk_price_history_points_gold_source_link_id_gold_source_links",
            type_="foreignkey",
        )
        batch_op.drop_column("gold_source_link_id")
