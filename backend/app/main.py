from fastapi import FastAPI
from app.api.predict_router import router as predict_router
from app.api.overview_router import router as overview_router
from app.core.config import settings

app = FastAPI(title=settings.APP_TITLE)

app.include_router(predict_router, prefix="/api/v1")
app.include_router(overview_router, prefix="/api/v1")

@app.get("/")
def root():
    return {"message": "Gold AI Agent is running 🚀"}