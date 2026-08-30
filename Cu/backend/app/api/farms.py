from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import farmer_for, get_farm
from app.models import Farm, FarmerCostOverride, User
from app.schemas import CostOverrideIn, FarmIn, FarmOut
from app.security import get_current_user

router = APIRouter(prefix="/api", tags=["farms"])


@router.post("/farms", response_model=FarmOut)
def create_farm(body: FarmIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farmer = farmer_for(user, db)
    farm = db.query(Farm).filter(Farm.farmer_id == farmer.id).first()
    if farm:
        for k, v in body.model_dump().items():
            setattr(farm, k, v)
    else:
        farm = Farm(farmer_id=farmer.id, **body.model_dump())
        db.add(farm)
    db.commit()
    db.refresh(farm)
    return farm


@router.get("/farms", response_model=list[FarmOut])
def list_farms(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farmer = farmer_for(user, db)
    return db.query(Farm).filter(Farm.farmer_id == farmer.id).all()


@router.put("/farms/{farm_id}", response_model=FarmOut)
def update_farm(farm_id: int, body: FarmIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farmer = farmer_for(user, db)
    farm = db.query(Farm).filter(Farm.id == farm_id, Farm.farmer_id == farmer.id).first()
    if not farm:
        raise HTTPException(404, "Farm not found.")
    for k, v in body.model_dump().items():
        setattr(farm, k, v)
    db.commit()
    db.refresh(farm)
    return farm


@router.post("/farms/costs")
def save_costs(body: CostOverrideIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    farm = get_farm(db, user)
    row = (
        db.query(FarmerCostOverride)
        .filter(
            FarmerCostOverride.farm_id == farm.id,
            FarmerCostOverride.crop_id == body.crop_id,
            FarmerCostOverride.season == body.season,
        )
        .first()
    )
    if not row:
        row = FarmerCostOverride(farm_id=farm.id, crop_id=body.crop_id, season=body.season)
        db.add(row)
    row.total_production_cost = body.total_production_cost
    row.expected_yield_quintal_per_hectare = body.expected_yield_quintal_per_hectare
    row.notes = body.notes
    db.commit()
    return {"ok": True}
