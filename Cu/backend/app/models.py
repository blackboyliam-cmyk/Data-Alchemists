from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), index=True)  # farmer | admin
    preferred_language: Mapped[str] = mapped_column(String(8), default="en")
    full_name: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    farmer_profile: Mapped[Optional["Farmer"]] = relationship(back_populates="user", uselist=False)


class Farmer(Base):
    __tablename__ = "farmers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="farmer_profile")
    farms: Mapped[list["Farm"]] = relationship(back_populates="farmer")


class Farm(Base):
    __tablename__ = "farms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("farmers.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200), default="My farm")
    state: Mapped[str] = mapped_column(String(100), index=True)
    district: Mapped[str] = mapped_column(String(100), index=True)
    village: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    area_hectares: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    farmer: Mapped[Farmer] = relationship(back_populates="farms")


class Crop(Base):
    __tablename__ = "crops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name_en: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name_hi: Mapped[str] = mapped_column(String(120), default="")
    name_mr: Mapped[str] = mapped_column(String(120), default="")
    agmarknet_names: Mapped[str] = mapped_column(Text, default="")  # comma-separated aliases
    category: Mapped[str] = mapped_column(String(80), default="other")
    spoilage_risk: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high
    unit: Mapped[str] = mapped_column(String(40), default="quintal")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    seasons: Mapped[list["CropSeason"]] = relationship(back_populates="crop")


class CropSeason(Base):
    __tablename__ = "crop_seasons"
    __table_args__ = (UniqueConstraint("crop_id", "season", name="uq_crop_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id", ondelete="CASCADE"), index=True)
    season: Mapped[str] = mapped_column(String(40))  # kharif | rabi | zaid | perennial
    sowing_month_start: Mapped[int] = mapped_column(Integer)
    sowing_month_end: Mapped[int] = mapped_column(Integer)
    harvest_month_start: Mapped[int] = mapped_column(Integer)
    harvest_month_end: Mapped[int] = mapped_column(Integer)
    weather_notes: Mapped[str] = mapped_column(Text, default="")

    crop: Mapped[Crop] = relationship(back_populates="seasons")


class Market(Base):
    __tablename__ = "markets"
    __table_args__ = (
        UniqueConstraint("name", "district", "state", name="uq_market_place"),
        Index("ix_markets_geo", "state", "district"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    state: Mapped[str] = mapped_column(String(100), index=True)
    district: Mapped[str] = mapped_column(String(100), index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    market_charges_percent: Mapped[float] = mapped_column(Float, default=1.0)
    storage_available: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(80), default="admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MarketCommodity(Base):
    __tablename__ = "market_commodities"
    __table_args__ = (UniqueConstraint("market_id", "crop_id", name="uq_market_crop"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id", ondelete="CASCADE"), index=True)


class MarketPrice(Base):
    __tablename__ = "market_prices"
    __table_args__ = (
        UniqueConstraint(
            "market_id",
            "commodity_raw",
            "variety",
            "grade",
            "price_date",
            name="uq_price_observation",
        ),
        Index("ix_prices_crop_date", "crop_id", "price_date"),
        Index("ix_prices_market_date", "market_id", "price_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crops.id", ondelete="SET NULL"), nullable=True, index=True)
    commodity_raw: Mapped[str] = mapped_column(String(200), index=True)
    variety: Mapped[str] = mapped_column(String(120), default="FAQ")
    grade: Mapped[str] = mapped_column(String(80), default="")
    price_date: Mapped[date] = mapped_column(Date, index=True)
    min_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    max_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    modal_price: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    arrival_quantity: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    unit: Mapped[str] = mapped_column(String(40), default="Rs/quintal")
    source: Mapped[str] = mapped_column(String(80), default="data.gov.in / AGMARKNET")
    data_quality: Mapped[str] = mapped_column(String(20), default="actual")  # actual | estimated
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    market: Mapped[Market] = relationship()
    crop: Mapped[Optional[Crop]] = relationship()


class WeatherData(Base):
    __tablename__ = "weather_data"
    __table_args__ = (
        Index("ix_weather_loc_time", "latitude", "longitude", "observed_at"),
        UniqueConstraint(
            "latitude", "longitude", "observed_at", "is_forecast", name="uq_weather_point"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[Optional[int]] = mapped_column(ForeignKey("farms.id", ondelete="SET NULL"), nullable=True, index=True)
    latitude: Mapped[float] = mapped_column(Float)
    longitude: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_forecast: Mapped[bool] = mapped_column(Boolean, default=False)
    temperature_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature_min_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temperature_max_c: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rainfall_mm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    humidity_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_speed_kmh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    conditions: Mapped[str] = mapped_column(String(120), default="")
    weather_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(80), default="Open-Meteo")
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProductionCost(Base):
    __tablename__ = "production_costs"
    __table_args__ = (UniqueConstraint("crop_id", "season", "state", name="uq_prod_cost"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id", ondelete="CASCADE"), index=True)
    season: Mapped[str] = mapped_column(String(40), default="kharif")
    state: Mapped[str] = mapped_column(String(100), default="Maharashtra")
    seed_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    fertilizer_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    pesticide_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    labour_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    irrigation_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    machinery_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    other_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    estimated_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    expected_yield_quintal_per_hectare: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    cost_basis: Mapped[str] = mapped_column(String(40), default="per_hectare")
    notes: Mapped[str] = mapped_column(Text, default="Administrator estimate. Farmers can override.")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    crop: Mapped[Crop] = relationship()


class FarmerCostOverride(Base):
    __tablename__ = "farmer_cost_overrides"
    __table_args__ = (UniqueConstraint("farm_id", "crop_id", "season", name="uq_farmer_cost"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id", ondelete="CASCADE"), index=True)
    season: Mapped[str] = mapped_column(String(40), default="kharif")
    total_production_cost: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    expected_yield_quintal_per_hectare: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StorageFacility(Base):
    __tablename__ = "storage_facilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(100), index=True)
    district: Mapped[str] = mapped_column(String(100), index=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    storage_type: Mapped[str] = mapped_column(String(80), default="godown")
    capacity_quintals: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    cost_per_day: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    availability: Mapped[str] = mapped_column(String(40), default="unknown")
    notes: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class StorageCrop(Base):
    __tablename__ = "storage_crops"
    __table_args__ = (UniqueConstraint("storage_id", "crop_id", name="uq_storage_crop"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    storage_id: Mapped[int] = mapped_column(ForeignKey("storage_facilities.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id", ondelete="CASCADE"), index=True)


class TransportConfig(Base):
    __tablename__ = "transport_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cost_per_km: Mapped[float] = mapped_column(Numeric(10, 2), default=25.0)
    truck_capacity_quintals: Mapped[float] = mapped_column(Numeric(10, 2), default=80.0)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    notes: Mapped[str] = mapped_column(Text, default="Administrator-configured transport assumption.")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TransportRoute(Base):
    __tablename__ = "transport_routes"
    __table_args__ = (
        UniqueConstraint("farm_id", "market_id", name="uq_farm_market_route"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id", ondelete="CASCADE"), index=True)
    distance_km: Mapped[float] = mapped_column(Float)
    distance_type: Mapped[str] = mapped_column(String(20))  # road | estimate
    cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScoringWeights(Base):
    __tablename__ = "scoring_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    expected_profit: Mapped[float] = mapped_column(Float, default=0.25)
    historical_price: Mapped[float] = mapped_column(Float, default=0.10)
    current_price: Mapped[float] = mapped_column(Float, default=0.10)
    volatility: Mapped[float] = mapped_column(Float, default=0.08)
    demand: Mapped[float] = mapped_column(Float, default=0.10)
    expected_yield: Mapped[float] = mapped_column(Float, default=0.08)
    production_cost: Mapped[float] = mapped_column(Float, default=0.08)
    weather: Mapped[float] = mapped_column(Float, default=0.12)
    transport: Mapped[float] = mapped_column(Float, default=0.05)
    storage: Mapped[float] = mapped_column(Float, default=0.04)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)  # running | success | failed | partial
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    records_ok: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str] = mapped_column(Text, default="")
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)


class ImportFailure(Base):
    __tablename__ = "import_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sync_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (Index("ix_rec_farm_created", "farm_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id", ondelete="CASCADE"), index=True)
    crop_id: Mapped[Optional[int]] = mapped_column(ForeignKey("crops.id", ondelete="SET NULL"), nullable=True)
    market_id: Mapped[Optional[int]] = mapped_column(ForeignKey("markets.id", ondelete="SET NULL"), nullable=True)
    rec_type: Mapped[str] = mapped_column(String(40), index=True)  # crop | market | sell_store | dashboard
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
