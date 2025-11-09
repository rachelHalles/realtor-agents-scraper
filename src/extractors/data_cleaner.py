import logging
from typing import Any, Dict, Iterable, List, Optional

LOGGER = logging.getLogger("realtor_agents_scraper.data_cleaner")

def _clean_phone(phone: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    number = str(phone.get("number", "")).strip()
    if not number:
        return None

    # Normalize common phone patterns a bit
    cleaned = []
    for ch in number:
        if ch.isdigit():
            cleaned.append(ch)
        elif ch in ("+",):
            cleaned.append(ch)
    normalized_number = "".join(cleaned) or number

    phone_type = phone.get("type") or None
    if isinstance(phone_type, str):
        phone_type = phone_type.strip() or None

    result: Dict[str, Any] = {"number": normalized_number}
    if phone_type:
        result["type"] = phone_type
    if "ext" in phone and phone["ext"]:
        result["ext"] = str(phone["ext"]).strip()
    return result

def _dedupe_list(items: List[Any]) -> List[Any]:
    seen = set()
    result = []
    for item in items:
        key = repr(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result

def _to_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value)
        digits = "".join(ch for ch in text if ch.isdigit())
        return int(digits) if digits else None
    except Exception:
        return None

def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    try:
        text = str(value).strip().replace(",", ".")
        parts = []
        dot_seen = False
        for ch in text:
            if ch.isdigit():
                parts.append(ch)
            elif ch == "." and not dot_seen:
                parts.append(ch)
                dot_seen = True
        return float("".join(parts)) if parts else None
    except Exception:
        return None

def _clean_office(office: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    if "name" in office and office["name"]:
        cleaned["name"] = str(office["name"]).strip()
    if "website" in office and office["website"]:
        cleaned["website"] = str(office["website"]).strip()
    if "raw_address" in office and office["raw_address"]:
        cleaned["address"] = {"raw": " ".join(str(office["raw_address"]).split())}
    if "address" in office and isinstance(office["address"], dict):
        cleaned["address"] = office["address"]
    return cleaned

def _clean_address(address: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}
    for key in ("line", "city", "state", "postal_code", "raw"):
        if key in address and address[key]:
            cleaned[key] = " ".join(str(address[key]).split())
    return cleaned

def clean_agent_record(agent: Dict[str, Any]) -> Dict[str, Any]:
    cleaned: Dict[str, Any] = {}

    # Simple scalar fields
    for field in ("description", "experience", "web_url", "title", "photo", "advertiser_id"):
        if field in agent and agent[field]:
            cleaned[field] = " ".join(str(agent[field]).split())

    # Numeric conversions
    first_year = _to_int(agent.get("first_year"))
    if first_year:
        cleaned["first_year"] = first_year

    review_count = _to_int(agent.get("review_count"))
    if review_count is not None:
        cleaned["review_count"] = review_count

    rating = _to_float(agent.get("agent_rating"))
    if rating is not None:
        cleaned["agent_rating"] = rating

    # Phones
    raw_phones = agent.get("phones") or []
    phones: List[Dict[str, Any]] = []
    if isinstance(raw_phones, list):
        for raw in raw_phones:
            if not isinstance(raw, dict):
                continue
            cleaned_phone = _clean_phone(raw)
            if cleaned_phone:
                phones.append(cleaned_phone)
    if phones:
        cleaned["phones"] = _dedupe_list(phones)

    # Address
    if isinstance(agent.get("address"), dict):
        addr = _clean_address(agent["address"])
        if addr:
            cleaned["address"] = addr

    # Office
    if isinstance(agent.get("office"), dict):
        office = _clean_office(agent["office"])
        if office:
            cleaned["office"] = office

    # Lists
    specs = agent.get("specializations") or []
    if isinstance(specs, list):
        cleaned_specs = [str(s).strip() for s in specs if s]
        if cleaned_specs:
            cleaned["specializations"] = _dedupe_list(cleaned_specs)

    # Broker
    if isinstance(agent.get("broker"), dict):
        broker_cleaned = {
            k: " ".join(str(v).split())
            for k, v in agent["broker"].items()
            if v
        }
        if broker_cleaned:
            cleaned["broker"] = broker_cleaned

    # Activity blocks (keep structure but normalize numeric values where obvious)
    if isinstance(agent.get("recently_sold"), dict):
        rs = agent["recently_sold"].copy()
        if "count" in rs:
            rs["count"] = _to_int(rs["count"])
        cleaned["recently_sold"] = rs

    if isinstance(agent.get("for_sale_price"), dict):
        fs = agent["for_sale_price"].copy()
        for key in ("min", "max", "count"):
            if key in fs:
                fs[key] = _to_int(fs[key])
        cleaned["for_sale_price"] = fs

    # Reviews (truncate very long comments to avoid bloating exports)
    if isinstance(agent.get("reviews"), list):
        cleaned_reviews = []
        for review in agent["reviews"]:
            if not isinstance(review, dict):
                continue
            r: Dict[str, Any] = {}
            if "rating" in review:
                r_val = _to_float(review["rating"])
                if r_val is not None:
                    r["rating"] = r_val
            if "comment" in review and review["comment"]:
                text = str(review["comment"]).strip()
                if len(text) > 2000:
                    text = text[:2000] + "..."
                r["comment"] = text
            if r:
                cleaned_reviews.append(r)
        if cleaned_reviews:
            cleaned["reviews"] = cleaned_reviews

    # Recommendations (kept mostly as-is)
    if isinstance(agent.get("recommendations"), list):
        recs = []
        for rec in agent["recommendations"]:
            if isinstance(rec, dict):
                recs.append(rec)
        if recs:
            cleaned["recommendations"] = recs

    return cleaned

def clean_agents(agents: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned_list: List[Dict[str, Any]] = []
    for idx, agent in enumerate(agents):
        if not isinstance(agent, dict):
            LOGGER.debug("Skipping non-dict agent at index %d", idx)
            continue
        cleaned = clean_agent_record(agent)
        if not cleaned:
            LOGGER.debug("Skipping empty cleaned agent at index %d", idx)
            continue
        cleaned_list.append(cleaned)
    return cleaned_list