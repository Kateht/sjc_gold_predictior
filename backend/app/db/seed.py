from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.init_db import (
    seed_default_admin,
    seed_default_dataset_sources,
    seed_default_gold_sources,
    seed_default_models,
    seed_default_news_categories,
)
from app.db.models import User
from app.db.session import SessionLocal


def seed_database(db: Session) -> None:
    seed_default_admin(db)
    admin = db.query(User).filter(User.email == settings.DEFAULT_ADMIN_EMAIL).first()
    seed_default_models(db)
    seed_default_news_categories(db, admin_id=admin.id if admin else None)
    seed_default_gold_sources(db, admin_id=admin.id if admin else None)
    seed_default_dataset_sources(db, admin_id=admin.id if admin else None)


def run_seed() -> None:
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
