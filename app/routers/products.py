"""DATA-03 공시 상품 비교 API."""
from fastapi import APIRouter, Depends, HTTPException

from app.deps import require_onboarded
from app.models import User
from app.services import savings_products

router = APIRouter(prefix="/api")

@router.get("/products/compare")
def compare(term_months: int = 12, product_type: str = "savings", user: User = Depends(require_onboarded)):
    try:
        return savings_products.compare_savings_products(term_months, product_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except savings_products.ProductAPIError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
