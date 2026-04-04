from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import DatasetSource, GoldSourceLink, MLModel, NewsCategory, User


def seed_default_admin(db: Session) -> None:
    if not settings.AUTO_SEED_ADMIN:
        return

    exists = db.query(User).filter(User.email == settings.DEFAULT_ADMIN_EMAIL).first()
    if exists:
        return

    now = datetime.now(timezone.utc)
    admin = User(
        name="System Admin",
        email=settings.DEFAULT_ADMIN_EMAIL,
        hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        role="admin",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(admin)
    db.commit()


def seed_default_models(db: Session) -> None:
    default_models = [
        {
            "code": "linear-price-v1",
            "name": "Linear Regression Price Baseline",
            "prediction_kind": "price",
            "provider": "builtin",
            "description": "Baseline linear forecast for SJC price",
            "config_json": {"strategy": "linear"},
            "metrics_json": {"mae": None, "rmse": None},
            "is_default": True,
            "is_active": True,
        },
        {
            "code": "momentum-price-v1",
            "name": "Momentum Price Baseline",
            "prediction_kind": "price",
            "provider": "builtin",
            "description": "Continues recent momentum using rolling deltas",
            "config_json": {"strategy": "momentum"},
            "metrics_json": {"mae": None, "rmse": None},
            "is_default": False,
            "is_active": True,
        },
        {
            "code": "mean-reversion-price-v1",
            "name": "Mean Reversion Price Baseline",
            "prediction_kind": "price",
            "provider": "builtin",
            "description": "Pulls prediction toward rolling average",
            "config_json": {"strategy": "mean_reversion"},
            "metrics_json": {"mae": None, "rmse": None},
            "is_default": False,
            "is_active": True,
        },
        {
            "code": "trend-slope-v1",
            "name": "Trend Slope Classifier",
            "prediction_kind": "trend",
            "provider": "builtin",
            "description": "Classifies trend from the predicted price path",
            "config_json": {"strategy": "slope"},
            "metrics_json": {"accuracy": None},
            "is_default": True,
            "is_active": True,
        },
        {
            "code": "lstm-price-v1",
            "name": "LSTM Price Model Placeholder",
            "prediction_kind": "price",
            "provider": "artifact",
            "artifact_path": settings.PRIMARY_PRICE_MODEL_ARTIFACT_PATH,
            "description": "Artifact-backed slot for a future LSTM or hybrid model",
            "config_json": {"strategy": "artifact_or_linear"},
            "metrics_json": {"mae": None, "rmse": None},
            "is_default": False,
            "is_active": False,
        },
    ]

    existing_codes = {model.code for model in db.query(MLModel).all()}
    for payload in default_models:
        if payload["code"] in existing_codes:
            continue
        db.add(MLModel(**payload))

    db.commit()


def seed_default_news_categories(db: Session, admin_id: int | None = None) -> None:
    categories = [
        {"slug": "economy", "name": "Kinh tế", "description": "Tin kinh tế vĩ mô và thị trường", "sort_order": 1},
        {"slug": "politics", "name": "Chính trị", "description": "Tin chính sách và địa chính trị", "sort_order": 2},
        {"slug": "gold", "name": "Giá vàng", "description": "Tin về SJC, PNJ và thị trường vàng", "sort_order": 3},
        {"slug": "related", "name": "Liên quan", "description": "Tin liên quan đến FX, lãi suất, hàng hóa", "sort_order": 4},
    ]

    existing_slugs = {item.slug for item in db.query(NewsCategory).all()}
    for payload in categories:
        if payload["slug"] in existing_slugs:
            continue
        db.add(NewsCategory(**payload, created_by_id=admin_id))

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

    existing_codes = {item.code for item in db.query(DatasetSource).all()}
    for payload in sources:
        if payload["code"] in existing_codes:
            continue
        db.add(DatasetSource(**payload, created_by_id=admin_id))

    db.commit()

