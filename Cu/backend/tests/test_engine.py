from app.services import validate_price_row
from app.services.profit import profit_for_market
from app.services.risk import _band, apply_relative_levels, combine_risk


def test_rejects_negative_price():
    cleaned, err = validate_price_row(
        {
            "state": "Maharashtra",
            "district": "Pune",
            "market": "Pune",
            "commodity": "Onion",
            "arrival_date": "01/01/2026",
            "min_price": -1,
            "max_price": 10,
            "modal_price": 5,
        }
    )
    assert cleaned is None
    assert "Negative" in err


def test_accepts_agmarknet_shape():
    cleaned, err = validate_price_row(
        {
            "state": "Maharashtra",
            "district": "Nashik",
            "market": "Lasalgaon",
            "commodity": "Onion",
            "variety": "Red",
            "arrival_date": "25/08/2026",
            "min_price": "1800",
            "max_price": "2200",
            "modal_price": "2000",
        }
    )
    assert err is None
    assert cleaned["modal_price"] == 2000.0
    assert cleaned["data_quality"] == "actual"


def test_profit_prefers_net_not_raw_price():
    # Higher raw price can lose after a longer, costlier trip.
    near = profit_for_market(4, 2100, 2000, 500, 0, 1.0, 0, 1)
    far = profit_for_market(4, 2350, 2000, 1700, 0, 1.0, 0, 1)
    assert far["price_used"] > near["price_used"]
    assert near["expected_net_profit"] > far["expected_net_profit"]


def test_break_even_and_roi():
    result = profit_for_market(
        yield_quintals=20,
        modal_price=2000,
        production_cost=20000,
        transport_cost=1000,
        storage_cost=0,
        market_charges_percent=1,
        area_hectares=1,
    )
    assert result["break_even_price"] > 0
    assert result["price_kind"] == "modal"
    assert result["expected_revenue"] == 40000


def test_unrealistic_yield_is_ignored():
    near = profit_for_market(12 * 5, 6500, 74000 * 5, 500, 0, 1.0, 0, 5)
    bogus = profit_for_market(10000 * 5, 6500, 6000 * 5, 500, 0, 1.0, 0, 5)
    assert near["expected_net_profit"] < 500_000
    assert bogus["expected_net_profit"] > 10_000_000


def test_risk_bands():
    assert _band(10) == "low"
    assert _band(32.9) == "low"
    assert _band(33) == "med"
    assert _band(66.9) == "med"
    assert _band(67) == "high"


class _Crop:
    id = 1
    name_en = "Onion"


def test_risk_combines_three_parts(monkeypatch):
    stats = {"count": 20, "volatility_ratio": 0.04}
    demand = {"score_0_to_100": 50}
    monkeypatch.setattr("app.services.risk.series_for", lambda *a, **k: [(None, 2000.0)] * 25)
    monkeypatch.setattr("app.services.risk._prediction_score", lambda *a, **k: 20.0)
    monkeypatch.setattr("app.services.risk._demand_score", lambda *a, **k: 25.0)
    risk = combine_risk(None, _Crop(), 1, stats, demand, 2000)
    assert risk["level"] == "low"
    assert risk["parts"]["price_volatility"]["score"] is not None
    assert 0 <= risk["score_0_to_100"] <= 100

    monkeypatch.setattr("app.services.risk._prediction_score", lambda *a, **k: 90.0)
    monkeypatch.setattr("app.services.risk._demand_score", lambda *a, **k: 90.0)
    high = combine_risk(None, _Crop(), 1, {"count": 20, "volatility_ratio": 0.4}, demand, 2000)
    assert high["level"] == "high"


def test_relative_risk_spreads_levels():
    risks = [
        {"score_0_to_100": 12, "parts": {"price_volatility": {"level": "low"}, "prediction_uncertainty": {"level": "low"}, "demand_variability": {"level": "low"}}},
        {"score_0_to_100": 18, "parts": {"price_volatility": {"level": "low"}, "prediction_uncertainty": {"level": "med"}, "demand_variability": {"level": "low"}}},
        {"score_0_to_100": 22, "parts": {"price_volatility": {"level": "med"}, "prediction_uncertainty": {"level": "low"}, "demand_variability": {"level": "high"}}},
    ]
    apply_relative_levels(risks)
    assert [r["level"] for r in risks] == ["low", "med", "high"]
    assert "versus the other mandis" in risks[0]["why"]
