"""Unit conversion for length, mass, temperature, and live currency rates."""
from __future__ import annotations

from ._http import get_json

DECLARATION = {
    "name": "convert_units",
    "description": (
        "Convert a value between units. Supports length (m, km, cm, mm, mi, ft, in, yd), "
        "mass (kg, g, mg, lb, oz, ton), temperature (c, f, k), and currency (3-letter codes "
        "like USD, EUR, PKR, GBP, JPY)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "value": {"type": "number", "description": "The amount to convert."},
            "from_unit": {"type": "string", "description": "Unit to convert from."},
            "to_unit": {"type": "string", "description": "Unit to convert to."},
        },
        "required": ["value", "from_unit", "to_unit"],
    },
}

# Everything expressed relative to a base unit.
_LENGTH = {  # base: metre
    "m": 1.0, "metre": 1.0, "meter": 1.0, "km": 1000.0, "cm": 0.01, "mm": 0.001,
    "mi": 1609.344, "mile": 1609.344, "ft": 0.3048, "foot": 0.3048, "feet": 0.3048,
    "in": 0.0254, "inch": 0.0254, "yd": 0.9144, "yard": 0.9144,
}
_MASS = {  # base: kilogram
    "kg": 1.0, "g": 0.001, "mg": 1e-6, "lb": 0.45359237, "lbs": 0.45359237,
    "pound": 0.45359237, "oz": 0.028349523125, "ounce": 0.028349523125, "ton": 1000.0,
    "tonne": 1000.0,
}
_TEMP = {"c", "celsius", "f", "fahrenheit", "k", "kelvin"}


def _norm(u: str) -> str:
    return u.strip().lower().rstrip(".")


def _temp_to_c(v: float, u: str) -> float:
    if u in ("c", "celsius"):
        return v
    if u in ("f", "fahrenheit"):
        return (v - 32) * 5 / 9
    return v - 273.15  # kelvin


def _c_to_temp(v: float, u: str) -> float:
    if u in ("c", "celsius"):
        return v
    if u in ("f", "fahrenheit"):
        return v * 9 / 5 + 32
    return v + 273.15


def _currency(value: float, frm: str, to: str) -> dict:
    frm, to = frm.upper(), to.upper()
    # open.er-api.com is keyless and covers ~160 currencies (incl. PKR).
    data = get_json(f"https://open.er-api.com/v6/latest/{frm}")
    if data.get("result") != "success":
        return {"error": f"Unsupported base currency '{frm}'."}
    rates = data.get("rates") or {}
    if to not in rates:
        return {"error": f"Unsupported currency '{to}'."}
    return {
        "value": value,
        "from": frm,
        "to": to,
        "result": round(value * rates[to], 4),
        "rate": rates[to],
        "rate_date": data.get("time_last_update_utc"),
        "kind": "currency",
    }


def run(value: float, from_unit: str, to_unit: str) -> dict:
    frm, to = _norm(from_unit), _norm(to_unit)

    for table, kind in ((_LENGTH, "length"), (_MASS, "mass")):
        if frm in table and to in table:
            result = value * table[frm] / table[to]
            return {"value": value, "from": frm, "to": to, "result": result, "kind": kind}

    if frm in _TEMP and to in _TEMP:
        result = _c_to_temp(_temp_to_c(value, frm), to)
        return {"value": value, "from": frm, "to": to, "result": result, "kind": "temperature"}

    if len(frm) == 3 and len(to) == 3 and frm.isalpha() and to.isalpha():
        try:
            return _currency(value, frm, to)
        except Exception as exc:  # noqa: BLE001
            return {"error": f"currency lookup failed: {exc}"}

    return {"error": f"Don't know how to convert '{from_unit}' to '{to_unit}'."}
