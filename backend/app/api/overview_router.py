from fastapi import APIRouter
from app.services.overview_service import get_overview_data
from app.models.overview import OverviewResponse

router = APIRouter()

@router.get("/overview", response_model=OverviewResponse)
def api_get_overview():
    """Lấy thông tin tổng quan giá vàng SJC và Thế giới."""
    data = get_overview_data()
    return data