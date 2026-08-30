from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Farm, Farmer, User
from app.security import get_current_user


def farmer_for(user: User, db: Session) -> Farmer:
    farmer = db.query(Farmer).filter(Farmer.user_id == user.id).first()
    if not farmer:
        farmer = Farmer(user_id=user.id)
        db.add(farmer)
        db.commit()
        db.refresh(farmer)
    return farmer


def get_farm(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Farm:
    farmer = farmer_for(user, db)
    farm = db.query(Farm).filter(Farm.farmer_id == farmer.id).order_by(Farm.id.asc()).first()
    if not farm:
        raise HTTPException(400, "Please save your farm location first.")
    return farm
