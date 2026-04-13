from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(32), nullable=False, default="user", server_default="user")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    refresh_tokens = relationship("RefreshToken", back_populates="user", cascade="all, delete-orphan")
    predictions = relationship("PredictionRecord", back_populates="user")
    created_models = relationship("MLModel", back_populates="created_by")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_jti = Column(String(64), unique=True, nullable=False, index=True)
    token_hash = Column(String(255), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="refresh_tokens")


class MLModel(Base):
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(120), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    prediction_kind = Column(String(32), nullable=False, index=True)
    provider = Column(String(32), nullable=False, default="builtin")
    artifact_path = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    config_json = Column(JSON, nullable=True)
    metrics_json = Column(JSON, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    created_by = relationship("User", back_populates="created_models")
    predictions = relationship("PredictionRecord", back_populates="model")


class PredictionRecord(Base):
    __tablename__ = "prediction_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    model_id = Column(Integer, ForeignKey("ml_models.id", ondelete="SET NULL"), nullable=True, index=True)
    prediction_kind = Column(String(32), nullable=False, index=True)
    source = Column(String(50), nullable=False, default="sjc")
    input_range = Column(String(32), nullable=True)
    days = Column(Integer, nullable=False)
    selected_model_key = Column(String(120), nullable=True)
    forecast_json = Column(JSON, nullable=False)
    trend_label = Column(String(32), nullable=True)
    used_fallback = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    user = relationship("User", back_populates="predictions")
    model = relationship("MLModel", back_populates="predictions")


class PriceHistoryPoint(Base):
    __tablename__ = "price_history_points"

    id = Column(Integer, primary_key=True, index=True)
    series_key = Column(String(50), nullable=False, index=True)
    series_name = Column(String(120), nullable=False)
    symbol = Column(String(50), nullable=True)
    gold_source_link_id = Column(Integer, ForeignKey("gold_source_links.id"), nullable=False, index=True)
    observed_at = Column(DateTime(timezone=True), nullable=False, index=True)
    price = Column(Float, nullable=False)
    source = Column(String(120), nullable=False)
    raw_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    gold_source_link = relationship("GoldSourceLink", back_populates="price_history_points")

    __table_args__ = (UniqueConstraint("series_key", "observed_at", name="uq_series_key_observed_at"),)


class NewsCategory(Base):
    __tablename__ = "news_categories"

    id = Column(Integer, primary_key=True, index=True)
    slug = Column(String(120), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    articles = relationship("NewsArticle", back_populates="category", cascade="all, delete-orphan")
    created_by = relationship("User")


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    category_id = Column(Integer, ForeignKey("news_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    slug = Column(String(180), unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    source_name = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    image_url = Column(String(500), nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True, index=True)
    is_featured = Column(Boolean, nullable=False, default=False, server_default="false")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    category = relationship("NewsCategory", back_populates="articles")
    created_by = relationship("User")


class GoldSourceLink(Base):
    __tablename__ = "gold_source_links"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(120), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    source_url = Column(String(500), nullable=False)
    source_type = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    region = Column(String(120), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    price_history_points = relationship("PriceHistoryPoint", back_populates="gold_source_link")
    created_by = relationship("User")


class DatasetSource(Base):
    __tablename__ = "dataset_sources"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(120), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), nullable=False)
    csv_path = Column(String(500), nullable=False)
    source_url = Column(String(500), nullable=True)
    file_format = Column(String(20), nullable=False, default="csv", server_default="csv")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    is_default = Column(Boolean, nullable=False, default=False, server_default="false")
    last_synced_at = Column(DateTime(timezone=True), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    created_by = relationship("User")


class CrawlerRun(Base):
    __tablename__ = "crawler_runs"

    id = Column(Integer, primary_key=True, index=True)
    task = Column(String(50), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", server_default="pending")
    trigger_source = Column(String(50), nullable=False, default="admin_web", server_default="admin_web")
    params_json = Column(JSON, nullable=True)
    exit_code = Column(Integer, nullable=True)
    output_text = Column(Text, nullable=True)
    error_text = Column(Text, nullable=True)
    log_path = Column(String(500), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    created_by = relationship("User")