from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    language: str


class RegisterIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=2, max_length=200)
    phone: Optional[str] = None
    preferred_language: str = "en"


class LoginIn(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    preferred_language: str
    phone: Optional[str] = None

    class Config:
        from_attributes = True


class FarmIn(BaseModel):
    name: str = "My farm"
    state: str
    district: str
    village: Optional[str] = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    area_hectares: float = Field(gt=0, le=10000)


class FarmOut(FarmIn):
    id: int
    farmer_id: int

    class Config:
        from_attributes = True


class CostOverrideIn(BaseModel):
    crop_id: int
    season: str = "kharif"
    total_production_cost: Optional[float] = Field(default=None, ge=0)
    expected_yield_quintal_per_hectare: Optional[float] = Field(default=None, ge=0, le=400)
    notes: str = ""


class CropIn(BaseModel):
    name_en: str
    name_hi: str = ""
    name_mr: str = ""
    agmarknet_names: str = ""
    category: str = "other"
    spoilage_risk: str = "medium"
    unit: str = "quintal"
    is_active: bool = True


class MarketIn(BaseModel):
    name: str
    state: str
    district: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    market_charges_percent: float = 1.0
    storage_available: bool = False
    is_active: bool = True


class ProductionCostIn(BaseModel):
    crop_id: int
    season: str = "kharif"
    state: str = "Maharashtra"
    seed_cost: float = 0
    fertilizer_cost: float = 0
    pesticide_cost: float = 0
    labour_cost: float = 0
    irrigation_cost: float = 0
    machinery_cost: float = 0
    other_cost: float = 0
    expected_yield_quintal_per_hectare: float = 0
    notes: str = ""


class StorageIn(BaseModel):
    name: str
    state: str
    district: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    storage_type: str = "godown"
    capacity_quintals: Optional[float] = None
    cost_per_day: float = 0
    availability: str = "unknown"
    notes: str = ""
    crop_ids: List[int] = []


class TransportConfigIn(BaseModel):
    cost_per_km: float = Field(gt=0)
    truck_capacity_quintals: float = Field(gt=0)
    notes: str = ""


class DataFreshness(BaseModel):
    last_updated: Optional[str] = None
    source: str
    quality: str  # actual | estimated | predicted | missing
    stale: bool = False
    message: str = ""
