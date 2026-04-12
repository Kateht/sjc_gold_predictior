from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.ai.metrics import get_price_model_metrics
from app.core.config import settings
from app.core.security import hash_password
from app.db.models import DatasetSource, GoldSourceLink, MLModel, NewsArticle, NewsCategory, User


logger = logging.getLogger(__name__)


def seed_default_admin(db: Session) -> None:
    if not settings.AUTO_SEED_ADMIN:
        return

    hashed_password = hash_password(settings.DEFAULT_ADMIN_PASSWORD)
    admin = db.query(User).filter(User.email == settings.DEFAULT_ADMIN_EMAIL).first()
    if admin:
        admin.name = "Admin"
        admin.hashed_password = hashed_password
        admin.role = "admin"
        admin.is_active = True
    else:
        db.add(
            User(
                name="Admin",
                email=settings.DEFAULT_ADMIN_EMAIL,
                hashed_password=hashed_password,
                role="admin",
                is_active=True,
            )
        )

    db.commit()


def seed_default_models(db: Session) -> None:
    try:
        price_model_metrics = get_price_model_metrics()
    except Exception as exc:
        logger.warning("Could not compute price metrics during seeding; using placeholders: %s", exc)
        price_model_metrics = {
            "lstm-k10-price-v1": {"mae": None, "rmse": None, "mape": None, "r2": None},
            "gru-price-v1": {"mae": None, "rmse": None, "mape": None, "r2": None},
        }

    default_models = [
        {
            "code": "lstm-k10-price-v1",
            "name": "LSTM K10 Price Model",
            "prediction_kind": "price",
            "provider": "artifact",
            "artifact_path": "app/models/lstm_k10.keras",
            "description": "Sequence model trained on a 10-step lookback window",
            "config_json": {"lookback": 10},
            "metrics_json": dict(price_model_metrics["lstm-k10-price-v1"]),
            "is_default": True,
            "is_active": True,
        },
        {
            "code": "gru-price-v1",
            "name": "Best GRU Price Model",
            "prediction_kind": "price",
            "provider": "artifact",
            "artifact_path": "app/models/best_gru.h5",
            "description": "Artifact-backed GRU model for price forecasting",
            "config_json": {"strategy": "gru", "feature_count": 28, "lookback": 1},
            "metrics_json": dict(price_model_metrics["gru-price-v1"]),
            "is_default": False,
            "is_active": True,
        },
        {
            "code": "sjc-classification-v1",
            "name": "SJC Direction Classifier",
            "prediction_kind": "trend",
            "provider": "artifact",
            "artifact_path": "app/models/xgb_classifier_sjc.joblib",
            "description": "Artifact-backed XGBoost classifier for direction bias on the SJC series",
            "config_json": {"feature_window": 1, "feature_count": 13, "strategy": "xgb_classifier"},
            "metrics_json": {"accuracy": None},
            "is_default": True,
            "is_active": True,
        },
    ]

    canonical_codes = {payload["code"] for payload in default_models}

    def _artifact_exists(artifact_path: str | None) -> bool:
        if not artifact_path:
            return False
        path = Path(artifact_path)
        if not path.is_absolute():
            path = Path(settings.PROJECT_ROOT) / path
        return path.exists()

    for model in db.query(MLModel).all():
        if model.code not in canonical_codes:
            db.delete(model)
            continue
        if model.provider == "artifact" and not _artifact_exists(model.artifact_path):
            db.delete(model)

    db.flush()

    existing_models = {model.code: model for model in db.query(MLModel).filter(MLModel.code.in_(canonical_codes)).all()}
    for payload in default_models:
        model = existing_models.get(payload["code"])
        if model:
            for field_name, field_value in payload.items():
                setattr(model, field_name, field_value)
            continue
        db.add(MLModel(**payload))

    db.commit()


def seed_default_news_categories(db: Session, admin_id: int | None = None) -> None:
    categories = [
        {"slug": "economy", "name": "Macro Economy", "description": "Macroeconomic releases and market context", "sort_order": 1},
        {"slug": "politics", "name": "Central Banks", "description": "Policy, rates, and geopolitical headlines", "sort_order": 2},
        {"slug": "gold", "name": "Gold Market", "description": "SJC, PNJ, and bullion market updates", "sort_order": 3},
        {"slug": "related", "name": "FX & Commodities", "description": "USD/VND, yields, and cross-asset context", "sort_order": 4},
    ]

    existing_categories = {item.slug: item for item in db.query(NewsCategory).all()}
    for payload in categories:
        category = existing_categories.get(payload["slug"])
        if category:
            for field_name, field_value in payload.items():
                setattr(category, field_name, field_value)
            if admin_id is not None:
                category.created_by_id = admin_id
            continue
        db.add(NewsCategory(**payload, created_by_id=admin_id))

    db.commit()


def seed_default_news_articles(db: Session, admin_id: int | None = None) -> None:
    now = datetime.now(timezone.utc)
    categories = {item.slug: item for item in db.query(NewsCategory).all()}
    articles = [
        {
            "slug": "gold-holds-firm-as-yields-ease",
            "category_slug": "politics",
            "title": "Gold Holds Firm as Yields Ease",
            "summary": "A softer yield backdrop keeps bullion supported while traders wait for the next policy signal.",
            "content": "US yields eased modestly and that gave gold a stable bid through the session. Market participants are watching whether that calm continues into the next data release.",
            "source_name": "Market Brief",
            "source_url": None,
            "image_url": None,
            "published_at": now - timedelta(hours=4),
            "is_featured": True,
            "is_active": True,
        },
        {
            "slug": "sjc-premium-stays-elevated",
            "category_slug": "gold",
            "title": "SJC Premium Stays Elevated Ahead of Local Demand",
            "summary": "Domestic SJC quotes remain above the implied world-price conversion, keeping the local spread in focus.",
            "content": "The SJC market is still trading with a meaningful premium versus the world price after currency conversion. Buyers continue to track both local liquidity and the next move in USD/VND.",
            "source_name": "Research Desk",
            "source_url": None,
            "image_url": None,
            "published_at": now - timedelta(hours=9),
            "is_featured": True,
            "is_active": True,
        },
        {
            "slug": "macro-data-keeps-safe-haven-demand-in-view",
            "category_slug": "economy",
            "title": "Macro Data Keeps Safe-Haven Demand in View",
            "summary": "Mixed macro signals leave room for defensive positioning across precious metals.",
            "content": "Investors are balancing softer growth indicators against still-sticky inflation expectations. That combination can keep safe-haven demand alive even without a sharp risk-off shock.",
            "source_name": "Macro Monitor",
            "source_url": None,
            "image_url": None,
            "published_at": now - timedelta(days=1, hours=2),
            "is_featured": True,
            "is_active": True,
        },
        {
            "slug": "usd-vnd-stability-keeps-import-costs-visible",
            "category_slug": "related",
            "title": "USD/VND Stability Keeps Import Costs Visible",
            "summary": "A steady FX backdrop limits volatility in the converted domestic gold price.",
            "content": "When USD/VND stays stable, local gold tends to move more directly with bullion and domestic demand. Traders are watching whether the next macro print changes that balance.",
            "source_name": "FX Watch",
            "source_url": None,
            "image_url": None,
            "published_at": now - timedelta(days=1, hours=6),
            "is_featured": False,
            "is_active": True,
        },
        {
            "slug": "central-bank-clarity-keeps-market-calm",
            "category_slug": "politics",
            "title": "Central Bank Clarity Keeps the Market Calm",
            "summary": "Clearer rate expectations reduce the odds of a sudden swing in bullion pricing.",
            "content": "Rate guidance remains the biggest macro variable for gold traders. The more predictable the policy path, the easier it is to frame a short-term forecast.",
            "source_name": "Policy Desk",
            "source_url": None,
            "image_url": None,
            "published_at": now - timedelta(days=2),
            "is_featured": True,
            "is_active": True,
        },
        {
            "slug": "retail-flow-keeps-the-gold-window-open",
            "category_slug": "gold",
            "title": "Retail Flow Keeps the Gold Window Open",
            "summary": "Seasonal buying interest is helping keep local gold demand resilient.",
            "content": "Retail demand does not need to be explosive to matter. Even a steady flow of buying can help support domestic premiums and keep the chart from flattening too early.",
            "source_name": "Retail Pulse",
            "source_url": None,
            "image_url": None,
            "published_at": now - timedelta(days=2, hours=5),
            "is_featured": False,
            "is_active": True,
        },
    ]

    existing_articles = {item.slug: item for item in db.query(NewsArticle).all()}
    for payload in articles:
        category = categories.get(payload["category_slug"])
        if category is None:
            continue

        article_payload = {key: value for key, value in payload.items() if key != "category_slug"}
        existing = existing_articles.get(article_payload["slug"])
        if existing:
            for field_name, field_value in article_payload.items():
                setattr(existing, field_name, field_value)
            existing.category_id = category.id
            if admin_id is not None:
                existing.created_by_id = admin_id
            continue

        db.add(NewsArticle(category_id=category.id, created_by_id=admin_id, **article_payload))

    db.commit()


def seed_default_gold_sources(db: Session, admin_id: int | None = None) -> None:
    sources = [
        {
            "code": "sjc-official",
            "name": "SJC Official",
            "source_url": "https://sjc.com.vn",
            "source_type": "official",
            "description": "Nguồn giá vàng SJC chính thức",
            "region": "Vietnam",
            "sort_order": 1,
        },
        {
            "code": "pnj-official",
            "name": "PNJ Official",
            "source_url": "https://www.pnj.com.vn",
            "source_type": "official",
            "description": "Nguồn giá vàng PNJ chính thức",
            "region": "Vietnam",
            "sort_order": 2,
        },
        {
            "code": "goldprice-reference",
            "name": "GoldPrice Reference",
            "source_url": "https://goldprice.org",
            "source_type": "reference",
            "description": "Nguồn tham chiếu giá vàng thế giới",
            "region": "Global",
            "sort_order": 3,
        },
        {
            "code": "fx-reference",
            "name": "FX Reference",
            "source_url": "https://www.vietcombank.com.vn",
            "source_type": "reference",
            "description": "Nguồn tham chiếu tỷ giá USD/VND",
            "region": "Vietnam",
            "sort_order": 4,
        },
    ]

    existing_codes = {item.code for item in db.query(GoldSourceLink).all()}
    for payload in sources:
        if payload["code"] in existing_codes:
            continue
        db.add(GoldSourceLink(**payload, created_by_id=admin_id))

    db.commit()


def seed_default_dataset_sources(db: Session, admin_id: int | None = None) -> None:
    sources = [
        {
            "code": "sjc-history-csv",
            "name": "SJC Historical CSV",
            "source_type": "csv",
            "csv_path": settings.LOCAL_DATASET_PATH,
            "source_url": None,
            "file_format": "csv",
            "description": "Dataset lịch sử giá vàng SJC cho biểu đồ và dự báo",
            "is_default": True,
            "is_active": True,
        },
        {
            "code": "crawler-export-csv",
            "name": "Crawler Export CSV",
            "source_type": "crawler",
            "csv_path": settings.CRAWLER_DATASET_PATH,
            "source_url": None,
            "file_format": "csv",
            "description": "Dữ liệu CSV sinh ra từ crawler vàng",
            "is_default": False,
            "is_active": True,
        },
        {
            "code": "merged-market-csv",
            "name": "Merged Market CSV",
            "source_type": "csv",
            "csv_path": "app/crawler/GetVietNameseGoldPrice/final_uso_with_vn_gold_vnd_thousand_imputed.csv",
            "source_url": None,
            "file_format": "csv",
            "description": "Dataset hợp nhất phục vụ feature engineering",
            "is_default": False,
            "is_active": True,
        },
    ]

    default_code = next((payload["code"] for payload in sources if payload.get("is_default")), None)
    if default_code:
        db.query(DatasetSource).filter(DatasetSource.is_default.is_(True)).update({DatasetSource.is_default: False})

    existing_sources = {item.code: item for item in db.query(DatasetSource).all()}
    for payload in sources:
        existing = existing_sources.get(payload["code"])
        if existing:
            for field_name, field_value in payload.items():
                setattr(existing, field_name, field_value)
            continue

        db.add(DatasetSource(**payload, created_by_id=admin_id))

    db.commit()

