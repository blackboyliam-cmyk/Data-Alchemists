from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Crop, ProductionCost, User
from app.security import get_current_user

router = APIRouter(tags=["crops"])


@router.get("/api/crops")
def list_crops(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    crops = db.query(Crop).filter(Crop.is_active.is_(True)).order_by(Crop.name_en).all()
    out = []
    for c in crops:
        cost = db.query(ProductionCost).filter(ProductionCost.crop_id == c.id).first()
        out.append(
            {
                "id": c.id,
                "name_en": c.name_en,
                "name_hi": c.name_hi,
                "name_mr": c.name_mr,
                "category": c.category,
                "spoilage_risk": c.spoilage_risk,
                "unit": c.unit,
                "seasons": [
                    {
                        "season": s.season,
                        "sowing_month_start": s.sowing_month_start,
                        "sowing_month_end": s.sowing_month_end,
                        "harvest_month_start": s.harvest_month_start,
                        "harvest_month_end": s.harvest_month_end,
                        "weather_notes": s.weather_notes,
                    }
                    for s in c.seasons
                ],
                "production_cost_estimate": None
                if not cost
                else {
                    "total_per_hectare": float(cost.estimated_total),
                    "yield_quintal_per_hectare": float(cost.expected_yield_quintal_per_hectare),
                    "source": "admin estimate",
                    "notes": cost.notes,
                },
            }
        )
    return out
