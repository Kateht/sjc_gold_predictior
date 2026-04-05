from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.predict_router import router as predict_router

from app.api.admin_router import router as admin_router
from app.api.admin_crawler_router import router as admin_crawler_router
from app.api.admin_dataset_router import router as admin_dataset_router
from app.api.admin_prediction_router import router as admin_prediction_router
from app.api.auth_router import router as auth_router
from app.api.history_router import router as history_router
from app.api.market_router import router as market_router
from app.api.model_router import router as model_router
from app.api.news_router import router as news_router
from app.api.overview_router import router as overview_router
from app.api.predict_router import router as predict_router
from app.api.source_router import router as source_router
from app.core.config import settings
from app.core.exception_handlers import register_exception_handlers
from app.db.seed import run_seed


app = FastAPI(title=settings.APP_TITLE)

allow_origins = settings.get_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=allow_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)


@app.on_event("startup")
def bootstrap_database():
    run_seed()


app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(model_router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_dataset_router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_crawler_router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_prediction_router, prefix=settings.API_V1_PREFIX)
app.include_router(history_router, prefix=settings.API_V1_PREFIX)
app.include_router(market_router, prefix=settings.API_V1_PREFIX)
app.include_router(news_router, prefix=settings.API_V1_PREFIX)
app.include_router(source_router, prefix=settings.API_V1_PREFIX)
app.include_router(predict_router, prefix=settings.API_V1_PREFIX)
app.include_router(overview_router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    return {"message": "Gold Prediction System is running 🚀"}
