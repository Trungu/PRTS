# tools/toolcalls/unit_converter.py — engineering unit conversion tool for the LLM agent.
#
# All conversions go through the SI base unit for each physical quantity.
# Temperature is handled separately (affine / offset conversion).
# Lookup is case-insensitive after whitespace stripping.
#
# HOW TO ADD A NEW UNIT
# ---------------------
# 1. Find the matching category table below (e.g. _PRESSURE).
# 2. Add "symbol": factor_to_SI_base.
# 3. That's it — _register() flattens it into the lookup automatically.

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Conversion tables
# ---------------------------------------------------------------------------
# Format: "symbol_lower": factor_that_multiplies_value_to_SI_base_unit
#
# Base units used:
#   length      → m          mass     → kg         time       → s
#   temperature → K (special) pressure → Pa        force      → N
#   energy      → J          power    → W          velocity   → m/s
#   area        → m²         volume   → m³         angle      → rad
#   frequency   → Hz

_LENGTH: dict[str, float] = {
    "m": 1.0,         "meter": 1.0,           "meters": 1.0,
    "km": 1e3,        "kilometer": 1e3,        "kilometers": 1e3,
    "cm": 1e-2,       "centimeter": 1e-2,      "centimeters": 1e-2,
    "mm": 1e-3,       "millimeter": 1e-3,      "millimeters": 1e-3,
    "um": 1e-6,       "micrometer": 1e-6,      "micrometers": 1e-6,
    "nm": 1e-9,       "nanometer": 1e-9,       "nanometers": 1e-9,
    "in": 0.0254,     "inch": 0.0254,          "inches": 0.0254,
    "ft": 0.3048,     "foot": 0.3048,          "feet": 0.3048,
    "yd": 0.9144,     "yard": 0.9144,          "yards": 0.9144,
    "mi": 1609.344,   "mile": 1609.344,        "miles": 1609.344,
    "nmi": 1852.0,    "nautical_mile": 1852.0,
    "au": 1.495978707e11,  "astronomical_unit": 1.495978707e11,
}

# Temperature is a special case — affine (offset) conversion.
# Handled by _convert_temperature(); _TEMP_NAMES is used only as a guard.
_TEMP_NAMES: frozenset[str] = frozenset(
    {"c", "celsius", "f", "fahrenheit", "k", "kelvin", "r", "rankine"}
)

_MASS: dict[str, float] = {
    "kg": 1.0,            "kilogram": 1.0,       "kilograms": 1.0,
    "g": 1e-3,            "gram": 1e-3,           "grams": 1e-3,
    "mg": 1e-6,           "milligram": 1e-6,      "milligrams": 1e-6,
    "ug": 1e-9,           "microgram": 1e-9,      "micrograms": 1e-9,
    "lb": 0.45359237,     "lbs": 0.45359237,      "pound": 0.45359237,    "pounds": 0.45359237,
    "oz": 0.028349523125, "ounce": 0.028349523125, "ounces": 0.028349523125,
    "t": 1000.0,          "tonne": 1000.0,        "metric_ton": 1000.0,   "tonnes": 1000.0,
    "ton": 907.18474,     "tons": 907.18474,      "short_ton": 907.18474,
    "long_ton": 1016.0469088,
    "slug": 14.593903,
}

_TIME: dict[str, float] = {
    "s": 1.0,       "sec": 1.0,         "second": 1.0,      "seconds": 1.0,
    "ms": 1e-3,     "millisecond": 1e-3, "milliseconds": 1e-3,
    "us": 1e-6,     "microsecond": 1e-6, "microseconds": 1e-6,
    "ns": 1e-9,     "nanosecond": 1e-9,  "nanoseconds": 1e-9,
    "min": 60.0,    "minute": 60.0,      "minutes": 60.0,
    "h": 3600.0,    "hr": 3600.0,        "hour": 3600.0,     "hours": 3600.0,
    "day": 86400.0, "days": 86400.0,
    "week": 604800.0, "weeks": 604800.0,
    "year": 31557600.0, "yr": 31557600.0, "years": 31557600.0,
}

_PRESSURE: dict[str, float] = {
    "pa": 1.0,          "pascal": 1.0,
    "kpa": 1e3,         "kilopascal": 1e3,
    "mpa": 1e6,         "megapascal": 1e6,
    "gpa": 1e9,         "gigapascal": 1e9,
    "hpa": 1e2,         "hectopascal": 1e2,
    "bar": 1e5,
    "mbar": 1e2,        "millibar": 1e2,
    "atm": 101325.0,    "atmosphere": 101325.0,
    "psi": 6894.757293168,
    "psf": 47.8802589,
    "torr": 133.322387415,   "mmhg": 133.322387415,
    "inhg": 3386.389,        "inh2o": 249.0889,
}

_FORCE: dict[str, float] = {
    "n": 1.0,       "newton": 1.0,          "newtons": 1.0,
    # Note: "kn" → kilonewton here; use "knot" / "knots" / "kt" for speed.
    "kn": 1e3,      "kilonewton": 1e3,      "kilonewtons": 1e3,
    "mn": 1e6,      "meganewton": 1e6,
    "lbf": 4.4482216152605,  "pound_force": 4.4482216152605,
    "kip": 4448.2216152605,  "kips": 4448.2216152605,
    "kgf": 9.80665,          "kilogram_force": 9.80665,
    "dyn": 1e-5,             "dyne": 1e-5,            "dynes": 1e-5,
    "pdl": 0.138254954376,   "poundal": 0.138254954376,
}

_ENERGY: dict[str, float] = {
    "j": 1.0,       "joule": 1.0,           "joules": 1.0,
    "kj": 1e3,      "kilojoule": 1e3,       "kilojoules": 1e3,
    "mj": 1e6,      "megajoule": 1e6,
    "gj": 1e9,      "gigajoule": 1e9,
    "cal": 4.184,   "calorie": 4.184,       "calories": 4.184,
    "kcal": 4184.0, "kilocalorie": 4184.0,  "kilocalories": 4184.0,
    "btu": 1055.05585262,    "british_thermal_unit": 1055.05585262,
    "kwh": 3.6e6,            "kilowatt_hour": 3.6e6,
    "mwh": 3.6e9,            "megawatt_hour": 3.6e9,
    "wh": 3600.0,            "watt_hour": 3600.0,
    "ev": 1.602176634e-19,   "electronvolt": 1.602176634e-19,
    "ft_lbf": 1.3558179483,  "foot_pound": 1.3558179483,
    "therm": 1.05505585262e8,
}

_POWER: dict[str, float] = {
    "w": 1.0,       "watt": 1.0,            "watts": 1.0,
    "kw": 1e3,      "kilowatt": 1e3,        "kilowatts": 1e3,
    "mw": 1e6,      "megawatt": 1e6,
    "gw": 1e9,      "gigawatt": 1e9,
    "hp": 745.69987158227,   "horsepower": 745.69987158227,
    # ps = Pferdestärke (metric horsepower); distinct from time unit picosecond.
    "ps": 735.49875,         "metric_horsepower": 735.49875,
    "btu/hr": 0.29307107017,
}

_VELOCITY: dict[str, float] = {
    "m/s": 1.0,       "mps": 1.0,         "meter_per_second": 1.0,
    "km/h": 1 / 3.6,  "kph": 1 / 3.6,     "kmh": 1 / 3.6,
    "mph": 0.44704,    "mile_per_hour": 0.44704,
    "ft/s": 0.3048,    "fps": 0.3048,      "feet_per_second": 0.3048,
    # Use knot/knots/kt — not "kn" (reserved for kilonewton in _FORCE).
    "knot": 0.514444,  "knots": 0.514444,  "kt": 0.514444, "kts": 0.514444,
    "mach": 343.0,     # standard atmosphere, 20 °C sea level
}

_AREA: dict[str, float] = {
    "m2": 1.0,         "sqm": 1.0,          "square_meter": 1.0,
    "km2": 1e6,        "square_kilometer": 1e6,
    "cm2": 1e-4,       "square_centimeter": 1e-4,
    "mm2": 1e-6,       "square_millimeter": 1e-6,
    "ft2": 0.09290304, "sqft": 0.09290304,  "square_foot": 0.09290304,
    "in2": 6.4516e-4,  "sqin": 6.4516e-4,   "square_inch": 6.4516e-4,
    "yd2": 0.83612736, "square_yard": 0.83612736,
    "mi2": 2589988.110336, "square_mile": 2589988.110336,
    "ac": 4046.8564224, "acre": 4046.8564224, "acres": 4046.8564224,
    "ha": 10000.0,     "hectare": 10000.0,  "hectares": 10000.0,
}

_VOLUME: dict[str, float] = {
    "m3": 1.0,          "cubic_meter": 1.0,
    "l": 1e-3,          "liter": 1e-3,      "liters": 1e-3,
                        "litre": 1e-3,      "litres": 1e-3,
    "ml": 1e-6,         "milliliter": 1e-6, "milliliters": 1e-6,
    "cl": 1e-5,         "centiliter": 1e-5,
    "dl": 1e-4,         "deciliter": 1e-4,
    "cm3": 1e-6,        "cc": 1e-6,         "cubic_centimeter": 1e-6,
    "mm3": 1e-9,        "cubic_millimeter": 1e-9,
    "ft3": 0.028316846592, "cubic_foot": 0.028316846592,
    "in3": 1.6387064e-5,   "cubic_inch": 1.6387064e-5,
    "yd3": 0.764554857984, "cubic_yard": 0.764554857984,
    "gal": 0.003785411784, "gallon": 0.003785411784, "gallons": 0.003785411784,
    "usgal": 0.003785411784,
    "ukgal": 0.00454609, "imp_gallon": 0.00454609,
    "qt": 9.46352946e-4, "quart": 9.46352946e-4,
    "pt": 4.73176473e-4, "pint": 4.73176473e-4,
    "fl_oz": 2.95735296e-5, "fluid_ounce": 2.95735296e-5,
    "bbl": 0.158987295,  "barrel": 0.158987295, "barrels": 0.158987295,
}

_ANGLE: dict[str, float] = {
    "rad": 1.0,      "radian": 1.0,      "radians": 1.0,
    "deg": math.pi / 180,  "degree": math.pi / 180,  "degrees": math.pi / 180,
    "grad": math.pi / 200, "gradian": math.pi / 200, "gradians": math.pi / 200,
    "rev": 2 * math.pi,    "revolution": 2 * math.pi, "turn": 2 * math.pi,
    "arcmin": math.pi / 10800,  "arcminute": math.pi / 10800,
    "arcsec": math.pi / 648000, "arcsecond": math.pi / 648000,
}

_FREQUENCY: dict[str, float] = {
    "hz": 1.0,     "hertz": 1.0,
    "khz": 1e3,    "kilohertz": 1e3,
    "mhz": 1e6,    "megahertz": 1e6,
    "ghz": 1e9,    "gigahertz": 1e9,
    "rpm": 1 / 60,
    "rps": 1.0,    "rev_per_sec": 1.0,
}

# ---------------------------------------------------------------------------
# Build the flat lookup: unit_string_lower → (category_label, factor_to_SI)
# ---------------------------------------------------------------------------

_ALL_UNITS: dict[str, tuple[str, float]] = {}


def _register(table: dict[str, float], category: str) -> None:
    for sym, factor in table.items():
        _ALL_UNITS[sym.lower()] = (category, factor)


_register(_LENGTH,    "length")
_register(_MASS,      "mass")
_register(_TIME,      "time")
_register(_PRESSURE,  "pressure")
_register(_FORCE,     "force")
_register(_ENERGY,    "energy")
_register(_POWER,     "power")
_register(_VELOCITY,  "velocity")
_register(_AREA,      "area")
_register(_VOLUME,    "volume")
_register(_ANGLE,     "angle")
_register(_FREQUENCY, "frequency")


# ---------------------------------------------------------------------------
# Temperature helper (affine conversion — cannot use a simple scale factor)
# ---------------------------------------------------------------------------

def _convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert *value* between temperature scales via Kelvin as the pivot."""
    f = from_unit.lower()
    if f in ("c", "celsius"):
        k = value + 273.15
    elif f in ("f", "fahrenheit"):
        k = (value + 459.67) * 5.0 / 9.0
    elif f in ("k", "kelvin"):
        k = value
    elif f in ("r", "rankine"):
        k = value * 5.0 / 9.0
    else:
        raise ValueError(f"Unknown temperature unit: '{from_unit}'")

    t = to_unit.lower()
    if t in ("c", "celsius"):
        return k - 273.15
    elif t in ("f", "fahrenheit"):
        return k * 9.0 / 5.0 - 459.67
    elif t in ("k", "kelvin"):
        return k
    elif t in ("r", "rankine"):
        return k * 9.0 / 5.0
    else:
        raise ValueError(f"Unknown temperature unit: '{to_unit}'")


# ---------------------------------------------------------------------------
# Formatting helper
# ---------------------------------------------------------------------------

def _fmt(n: float) -> str:
    """Format *n* cleanly: scientific notation for very large/small values,
    otherwise up to 10 significant digits with trailing zeros stripped."""
    if n == 0.0:
        return "0"
    abs_n = abs(n)
    if abs_n >= 1e10 or abs_n < 1e-5:
        return f"{n:.6e}"
    return f"{n:.10g}"


# ---------------------------------------------------------------------------
# Public tool function
# ---------------------------------------------------------------------------

def unit_converter(value: float, from_unit: str, to_unit: str) -> str:
    """Convert *value* from *from_unit* to *to_unit*.

    Parameters
    ----------
    value:
        Numeric value to convert.
    from_unit:
        Source unit string (e.g. ``'ft'``, ``'psi'``, ``'C'``).
    to_unit:
        Target unit string (e.g. ``'m'``, ``'Pa'``, ``'K'``).

    Returns
    -------
    str
        Human-readable result such as ``"1 ft = 0.3048 m"``, or an error
        message prefixed with ``"Error:"`` for unknown or incompatible units.
    """
    from_lower = from_unit.strip().lower()
    to_lower   = to_unit.strip().lower()

    # ── Temperature (affine conversion) ──────────────────────────────────────
    from_is_temp = from_lower in _TEMP_NAMES
    to_is_temp   = to_lower   in _TEMP_NAMES

    if from_is_temp or to_is_temp:
        if not from_is_temp:
            return (f"Error: '{from_unit}' is not a temperature unit "
                    f"but '{to_unit}' is.")
        if not to_is_temp:
            return (f"Error: '{to_unit}' is not a temperature unit "
                    f"but '{from_unit}' is.")
        try:
            result = _convert_temperature(value, from_lower, to_lower)
            return f"{_fmt(value)} {from_unit} = {_fmt(result)} {to_unit}"
        except ValueError as exc:
            return f"Error: {exc}"

    # ── Standard multiplicative conversion ───────────────────────────────────
    if from_lower not in _ALL_UNITS:
        return (f"Error: unknown unit '{from_unit}'. "
                f"Check the tool description for supported units.")
    if to_lower not in _ALL_UNITS:
        return (f"Error: unknown unit '{to_unit}'. "
                f"Check the tool description for supported units.")

    from_cat, from_factor = _ALL_UNITS[from_lower]
    to_cat,   to_factor   = _ALL_UNITS[to_lower]

    if from_cat != to_cat:
        return (f"Error: cannot convert '{from_unit}' ({from_cat}) "
                f"to '{to_unit}' ({to_cat}) — incompatible physical quantities.")

    # value × from_factor = SI value;  SI value ÷ to_factor = result
    result = (value * from_factor) / to_factor
    return f"{_fmt(value)} {from_unit} = {_fmt(result)} {to_unit}"


# ---------------------------------------------------------------------------
# OpenAI-style tool definition (read by llm_api agentic loop)
# ---------------------------------------------------------------------------

TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "unit_converter",
        "description": (
            "Convert a numeric value from one engineering or scientific unit to another. "
            "ALWAYS use this instead of mental unit arithmetic — it eliminates errors. "
            "Supported categories and example symbols:\n"
            "  length      : m, km, cm, mm, in, ft, yd, mi, nmi\n"
            "  mass        : kg, g, mg, lb, oz, t, ton, slug\n"
            "  time        : s, ms, us, ns, min, h, day, year\n"
            "  temperature : C, F, K, R  (Celsius/Fahrenheit/Kelvin/Rankine)\n"
            "  pressure    : Pa, kPa, MPa, GPa, bar, atm, psi, psf, torr, mmHg, inHg\n"
            "  force       : N, kN, MN, lbf, kip, kgf, dyn\n"
            "  energy      : J, kJ, MJ, GJ, cal, kcal, BTU, kWh, eV, ft_lbf\n"
            "  power       : W, kW, MW, GW, hp, ps\n"
            "  velocity    : m/s, km/h, mph, ft/s, knot, mach\n"
            "  area        : m2, km2, cm2, ft2, in2, sqft, ac, ha\n"
            "  volume      : m3, L, mL, cm3, ft3, in3, gal, bbl\n"
            "  angle       : rad, deg, grad, rev, arcmin, arcsec\n"
            "  frequency   : Hz, kHz, MHz, GHz, rpm"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "value": {
                    "type": "number",
                    "description": "The numeric value to convert.",
                },
                "from_unit": {
                    "type": "string",
                    "description": (
                        "Source unit. Case-insensitive. "
                        "Examples: 'ft', 'psi', 'C', 'kWh', 'rpm', 'gal', 'mph', 'kip'."
                    ),
                },
                "to_unit": {
                    "type": "string",
                    "description": "Target unit. Same format as from_unit.",
                },
            },
            "required": ["value", "from_unit", "to_unit"],
        },
    },
}
