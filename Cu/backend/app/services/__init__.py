from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional, Tuple


def to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        n = float(str(value).replace(",", "").strip())
        if n != n:  # NaN
            return None
        return n
    except (TypeError, ValueError):
        return None


def parse_price_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def validate_price_row(record: dict) -> Tuple[Optional[dict], Optional[str]]:
    state = (record.get("state") or record.get("State") or "").strip()
    district = (record.get("district") or record.get("District") or "").strip()
    market = (record.get("market") or record.get("Market") or "").strip()
    commodity = (record.get("commodity") or record.get("Commodity") or "").strip()
    variety = (record.get("variety") or record.get("Variety") or "FAQ").strip() or "FAQ"
    grade = (record.get("grade") or record.get("Grade") or "").strip()
    arrival_date = parse_price_date(
        record.get("arrival_date")
        or record.get("Arrival_Date")
        or record.get("arrivalDate")
        or record.get("date")
    )
    min_p = to_float(record.get("min_price") or record.get("Min_Price") or record.get("minPrice"))
    max_p = to_float(record.get("max_price") or record.get("Max_Price") or record.get("maxPrice"))
    modal = to_float(record.get("modal_price") or record.get("Modal_Price") or record.get("modalPrice"))
    arrivals = to_float(
        record.get("arrival")
        or record.get("arrivals")
        or record.get("Arrival")
        or record.get("arrival_quantity")
    )

    if not state or not district or not market:
        return None, "Missing state, district, or market name."
    if not commodity:
        return None, "Missing commodity name."
    if not arrival_date:
        return None, "Missing or invalid arrival date."
    tomorrow = date.today() + timedelta(days=1)
    if arrival_date > tomorrow:
        return None, f"Date {arrival_date} is in the future."
    if modal is None and min_p is None and max_p is None:
        return None, "No price values present."
    for label, val in (("min", min_p), ("max", max_p), ("modal", modal)):
        if val is not None and val < 0:
            return None, f"Negative {label} price."
        if val is not None and val > 10_000_000:
            return None, f"Unrealistic {label} price."
    if min_p is not None and max_p is not None and min_p > max_p:
        return None, "Minimum price is higher than maximum price."
    if modal is not None and min_p is not None and modal < min_p * 0.5:
        return None, "Modal price is far below minimum; likely a data error."
    if modal is not None and max_p is not None and modal > max_p * 1.5:
        return None, "Modal price is far above maximum; likely a data error."
    if arrivals is not None and arrivals < 0:
        return None, "Negative arrival quantity."

    quality = "actual"
    if modal is None and min_p is not None and max_p is not None:
        modal = (min_p + max_p) / 2
        quality = "estimated"

    cleaned = {
        "state": state.title(),
        "district": district.title(),
        "market": market.strip(),
        "commodity": commodity.strip(),
        "variety": variety[:120],
        "grade": grade[:80],
        "price_date": arrival_date,
        "min_price": min_p,
        "max_price": max_p,
        "modal_price": modal,
        "arrival_quantity": arrivals,
        "data_quality": quality,
    }
    return cleaned, None


def decimal_or_none(value) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def stale_days(last: Optional[datetime], days: int = 2) -> bool:
    if last is None:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last > timedelta(days=days)
