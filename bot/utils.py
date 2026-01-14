def format_value(val, val_type="num", precision=3, zero_is_none=False):
    """
    Универсальный форматтер чисел, валют и единиц времени.
    """
    unit_map = {
        "weeks": "недель", "week": "неделя",
        "days": "дней", "day": "день",
        "months": "месяцев", "month": "месяц",
        "years": "лет", "year": "год"
    }

    if val_type == "num":
        try:
            val = float(val)
            if zero_is_none and val == 0:
                return "—"
            return str(int(val)) if val == int(val) else str(round(val, precision))
        except (ValueError, TypeError):
            return "—"

    elif val_type == "currency":
        price, currency = val
        try:
            if price is None or float(price) == 0:
                return currency or "—"
            price_val = float(price)
            price_val = int(price_val) if price_val == int(price_val) else round(price_val, precision)
            return f"{price_val} {currency}".strip()
        except (ValueError, TypeError):
            return currency or "—"

    elif val_type == "unit":
        return unit_map.get(str(val or "").lower(), val or "")

    return val or "—"
