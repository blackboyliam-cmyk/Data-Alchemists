"""Reference crop/market metadata. Does not include live mandi prices or weather."""

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Crop,
    CropSeason,
    Farmer,
    Market,
    ProductionCost,
    ScoringWeights,
    StorageCrop,
    StorageFacility,
    TransportConfig,
    User,
)
from app.security import hash_password

settings = get_settings()

CROPS = [
    {
        "name_en": "Tomato",
        "name_hi": "टमाटर",
        "name_mr": "टोमॅटो",
        "agmarknet_names": "Tomato,Tomato Local",
        "category": "vegetable",
        "spoilage_risk": "high",
        "seasons": [
            {"season": "kharif", "sowing_month_start": 6, "sowing_month_end": 8, "harvest_month_start": 9, "harvest_month_end": 12, "weather_notes": "Avoid waterlogging; needs regular moisture."},
            {"season": "rabi", "sowing_month_start": 10, "sowing_month_end": 12, "harvest_month_start": 1, "harvest_month_end": 4, "weather_notes": "Protect from frost in cooler districts."},
        ],
        "cost": {"seed_cost": 12000, "fertilizer_cost": 18000, "pesticide_cost": 9000, "labour_cost": 35000, "irrigation_cost": 12000, "machinery_cost": 8000, "other_cost": 5000, "yield": 200},
    },
    {
        "name_en": "Onion",
        "name_hi": "प्याज",
        "name_mr": "कांदा",
        "agmarknet_names": "Onion,Onion Big,Onion Small",
        "category": "vegetable",
        "spoilage_risk": "medium",
        "seasons": [
            {"season": "kharif", "sowing_month_start": 5, "sowing_month_end": 7, "harvest_month_start": 9, "harvest_month_end": 11, "weather_notes": "Heavy rain at harvest increases spoilage."},
            {"season": "rabi", "sowing_month_start": 10, "sowing_month_end": 12, "harvest_month_start": 2, "harvest_month_end": 4, "weather_notes": "Main onion season in many Maharashtra districts."},
        ],
        "cost": {"seed_cost": 15000, "fertilizer_cost": 16000, "pesticide_cost": 7000, "labour_cost": 28000, "irrigation_cost": 10000, "machinery_cost": 6000, "other_cost": 4000, "yield": 180},
    },
    {
        "name_en": "Wheat",
        "name_hi": "गेहूँ",
        "name_mr": "गहू",
        "agmarknet_names": "Wheat",
        "category": "cereal",
        "spoilage_risk": "low",
        "seasons": [
            {"season": "rabi", "sowing_month_start": 10, "sowing_month_end": 12, "harvest_month_start": 3, "harvest_month_end": 5, "weather_notes": "Needs cool growing period; unseasonal rain at harvest can damage grain."},
        ],
        "cost": {"seed_cost": 4000, "fertilizer_cost": 9000, "pesticide_cost": 2500, "labour_cost": 12000, "irrigation_cost": 5000, "machinery_cost": 8000, "other_cost": 2000, "yield": 35},
    },
    {
        "name_en": "Rice",
        "name_hi": "धान",
        "name_mr": "तांदूळ",
        "agmarknet_names": "Rice,Paddy(Dhan)(Common),Paddy(Dhan)(Basmati)",
        "category": "cereal",
        "spoilage_risk": "low",
        "seasons": [
            {"season": "kharif", "sowing_month_start": 6, "sowing_month_end": 7, "harvest_month_start": 10, "harvest_month_end": 12, "weather_notes": "Needs standing water during tillering."},
        ],
        "cost": {"seed_cost": 3500, "fertilizer_cost": 10000, "pesticide_cost": 3000, "labour_cost": 18000, "irrigation_cost": 7000, "machinery_cost": 9000, "other_cost": 2500, "yield": 40},
    },
    {
        "name_en": "Soyabean",
        "name_hi": "सोयाबीन",
        "name_mr": "सोयाबीन",
        "agmarknet_names": "Soyabean,Soybean",
        "category": "oilseed",
        "spoilage_risk": "low",
        "seasons": [
            {"season": "kharif", "sowing_month_start": 6, "sowing_month_end": 7, "harvest_month_start": 9, "harvest_month_end": 11, "weather_notes": "Excess rain at harvest increases moisture and quality loss."},
        ],
        "cost": {"seed_cost": 5000, "fertilizer_cost": 8000, "pesticide_cost": 4000, "labour_cost": 10000, "irrigation_cost": 2000, "machinery_cost": 7000, "other_cost": 2000, "yield": 18},
    },
    {
        "name_en": "Cotton",
        "name_hi": "कपास",
        "name_mr": "कापूस",
        "agmarknet_names": "Cotton,Cotton (Lint)",
        "category": "fibre",
        "spoilage_risk": "low",
        "seasons": [
            {"season": "kharif", "sowing_month_start": 5, "sowing_month_end": 7, "harvest_month_start": 10, "harvest_month_end": 2, "weather_notes": "Long duration crop; pest pressure rises in humid weather."},
        ],
        "cost": {"seed_cost": 8000, "fertilizer_cost": 14000, "pesticide_cost": 12000, "labour_cost": 22000, "irrigation_cost": 6000, "machinery_cost": 8000, "other_cost": 4000, "yield": 12},
    },
    {
        "name_en": "Potato",
        "name_hi": "आलू",
        "name_mr": "बटाटा",
        "agmarknet_names": "Potato",
        "category": "vegetable",
        "spoilage_risk": "high",
        "seasons": [
            {"season": "rabi", "sowing_month_start": 10, "sowing_month_end": 12, "harvest_month_start": 1, "harvest_month_end": 3, "weather_notes": "Needs cool weather; high spoilage without cold storage."},
        ],
        "cost": {"seed_cost": 25000, "fertilizer_cost": 15000, "pesticide_cost": 6000, "labour_cost": 20000, "irrigation_cost": 8000, "machinery_cost": 7000, "other_cost": 4000, "yield": 220},
    },
    {
        "name_en": "Tur",
        "name_hi": "अरहर",
        "name_mr": "तूर",
        "agmarknet_names": "Arhar (Tur/Red Gram)(Whole),Arhar Dal(Tur Dal)",
        "category": "pulse",
        "spoilage_risk": "low",
        "seasons": [
            {"season": "kharif", "sowing_month_start": 6, "sowing_month_end": 7, "harvest_month_start": 12, "harvest_month_end": 2, "weather_notes": "Drought tolerant but flowers poorly in extreme heat."},
        ],
        "cost": {"seed_cost": 2500, "fertilizer_cost": 4000, "pesticide_cost": 3500, "labour_cost": 9000, "irrigation_cost": 1500, "machinery_cost": 4000, "other_cost": 1500, "yield": 10},
    },
    {
        "name_en": "Bajra",
        "name_hi": "बाजरा",
        "name_mr": "बाजरी",
        "agmarknet_names": "Bajra(Pearl Millet/Cumbu)",
        "category": "cereal",
        "spoilage_risk": "low",
        "seasons": [
            {"season": "kharif", "sowing_month_start": 6, "sowing_month_end": 7, "harvest_month_start": 9, "harvest_month_end": 10, "weather_notes": "Suited to low rainfall and light soils."},
        ],
        "cost": {"seed_cost": 1500, "fertilizer_cost": 3500, "pesticide_cost": 1200, "labour_cost": 6000, "irrigation_cost": 1000, "machinery_cost": 3500, "other_cost": 1000, "yield": 15},
    },
    {
        "name_en": "Jowar",
        "name_hi": "ज्वार",
        "name_mr": "ज्वारी",
        "agmarknet_names": "Jowar(Sorghum)",
        "category": "cereal",
        "spoilage_risk": "low",
        "seasons": [
            {"season": "kharif", "sowing_month_start": 6, "sowing_month_end": 7, "harvest_month_start": 9, "harvest_month_end": 11, "weather_notes": "Performs in semi-arid zones."},
            {"season": "rabi", "sowing_month_start": 9, "sowing_month_end": 10, "harvest_month_start": 1, "harvest_month_end": 3, "weather_notes": "Rabi jowar is important in Maharashtra."},
        ],
        "cost": {"seed_cost": 1800, "fertilizer_cost": 4000, "pesticide_cost": 1500, "labour_cost": 7000, "irrigation_cost": 1200, "machinery_cost": 4000, "other_cost": 1200, "yield": 16},
    },
]

# Approximate public coordinates for APMC / market yards. Not prices.
MARKETS = [
    {"name": "Panvel", "state": "Maharashtra", "district": "Raigad", "latitude": 18.9894, "longitude": 73.1175, "storage_available": True, "market_charges_percent": 1.0},
    {"name": "Vashi", "state": "Maharashtra", "district": "Thane", "latitude": 19.0771, "longitude": 73.0128, "storage_available": True, "market_charges_percent": 1.2},
    {"name": "Pune", "state": "Maharashtra", "district": "Pune", "latitude": 18.5204, "longitude": 73.8567, "storage_available": True, "market_charges_percent": 1.0},
    {"name": "Nashik", "state": "Maharashtra", "district": "Nashik", "latitude": 19.9975, "longitude": 73.7898, "storage_available": True, "market_charges_percent": 1.0},
    {"name": "Lasalgaon", "state": "Maharashtra", "district": "Nashik", "latitude": 20.1426, "longitude": 74.2396, "storage_available": True, "market_charges_percent": 1.0},
    {"name": "Nagpur", "state": "Maharashtra", "district": "Nagpur", "latitude": 21.1458, "longitude": 79.0882, "storage_available": True, "market_charges_percent": 1.0},
    {"name": "Aurangabad", "state": "Maharashtra", "district": "Chhatrapati Sambhajinagar", "latitude": 19.8762, "longitude": 75.3433, "storage_available": False, "market_charges_percent": 1.0},
    {"name": "Solapur", "state": "Maharashtra", "district": "Solapur", "latitude": 17.6599, "longitude": 75.9064, "storage_available": True, "market_charges_percent": 1.0},
    {"name": "Kolhapur", "state": "Maharashtra", "district": "Kolhapur", "latitude": 16.7050, "longitude": 74.2433, "storage_available": False, "market_charges_percent": 1.0},
    {"name": "Ahmednagar", "state": "Maharashtra", "district": "Ahmednagar", "latitude": 19.0948, "longitude": 74.7480, "storage_available": True, "market_charges_percent": 1.0},
    {"name": "Bengaluru", "state": "Karnataka", "district": "Bangalore", "latitude": 12.9716, "longitude": 77.5946, "storage_available": True, "market_charges_percent": 1.0},
    {"name": "Indore", "state": "Madhya Pradesh", "district": "Indore", "latitude": 22.7196, "longitude": 75.8577, "storage_available": True, "market_charges_percent": 1.0},
]

STORAGE = [
    {"name": "Panvel APMC Godown", "state": "Maharashtra", "district": "Raigad", "latitude": 18.9900, "longitude": 73.1180, "storage_type": "godown", "capacity_quintals": 5000, "cost_per_day": 250, "availability": "limited"},
    {"name": "Pune Market Yard Cold Store", "state": "Maharashtra", "district": "Pune", "latitude": 18.5089, "longitude": 73.8553, "storage_type": "cold_storage", "capacity_quintals": 2000, "cost_per_day": 800, "availability": "unknown"},
    {"name": "Lasalgaon Onion Storage", "state": "Maharashtra", "district": "Nashik", "latitude": 20.1450, "longitude": 74.2400, "storage_type": "ventilated_godown", "capacity_quintals": 8000, "cost_per_day": 180, "availability": "available"},
    {"name": "Nagpur Warehouse", "state": "Maharashtra", "district": "Nagpur", "latitude": 21.1498, "longitude": 79.0806, "storage_type": "godown", "capacity_quintals": 4000, "cost_per_day": 220, "availability": "available"},
]


def seed_if_empty(db: Session) -> None:
    if db.query(User).count() == 0:
        admin = User(
            email=settings.admin_email.lower(),
            password_hash=hash_password(settings.admin_password),
            role="admin",
            full_name="Administrator",
            preferred_language="en",
        )
        farmer_user = User(
            email=settings.demo_farmer_email.lower(),
            password_hash=hash_password(settings.demo_farmer_password),
            role="farmer",
            full_name="Demo Farmer",
            preferred_language="mr",
            phone="9999999999",
        )
        db.add_all([admin, farmer_user])
        db.flush()
        farmer = Farmer(user_id=farmer_user.id)
        db.add(farmer)

    if db.query(Crop).count() == 0:
        for item in CROPS:
            crop = Crop(
                name_en=item["name_en"],
                name_hi=item["name_hi"],
                name_mr=item["name_mr"],
                agmarknet_names=item["agmarknet_names"],
                category=item["category"],
                spoilage_risk=item["spoilage_risk"],
            )
            db.add(crop)
            db.flush()
            for s in item["seasons"]:
                db.add(CropSeason(crop_id=crop.id, **s))
            c = item["cost"]
            total = (
                c["seed_cost"]
                + c["fertilizer_cost"]
                + c["pesticide_cost"]
                + c["labour_cost"]
                + c["irrigation_cost"]
                + c["machinery_cost"]
                + c["other_cost"]
            )
            db.add(
                ProductionCost(
                    crop_id=crop.id,
                    season=item["seasons"][0]["season"],
                    state="Maharashtra",
                    seed_cost=c["seed_cost"],
                    fertilizer_cost=c["fertilizer_cost"],
                    pesticide_cost=c["pesticide_cost"],
                    labour_cost=c["labour_cost"],
                    irrigation_cost=c["irrigation_cost"],
                    machinery_cost=c["machinery_cost"],
                    other_cost=c["other_cost"],
                    estimated_total=total,
                    expected_yield_quintal_per_hectare=c["yield"],
                    notes="Default cost estimate per hectare. Administrators should update with local figures. Not a live market price.",
                )
            )

    if db.query(Market).count() == 0:
        for m in MARKETS:
            db.add(Market(**m, source="seed_metadata"))

    if db.query(StorageFacility).count() == 0:
        crops = db.query(Crop).all()
        for s in STORAGE:
            fac = StorageFacility(**s)
            db.add(fac)
            db.flush()
            for crop in crops:
                if crop.spoilage_risk == "high" and fac.storage_type == "godown" and "Onion" not in fac.name:
                    continue
                db.add(StorageCrop(storage_id=fac.id, crop_id=crop.id))

    if db.query(TransportConfig).count() == 0:
        db.add(
            TransportConfig(
                cost_per_km=25.0,
                truck_capacity_quintals=80.0,
                notes="Default: ₹25 per km per trip. Change this in the admin panel to match local tempos/trucks.",
            )
        )

    if db.query(ScoringWeights).count() == 0:
        db.add(ScoringWeights())

    db.commit()
