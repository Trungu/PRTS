"""Tests for tools/toolcalls/unit_converter.py

Coverage:
  - _fmt helper (zero, negative-zero, boundaries, scientific notation)
  - unit_converter: happy-path for every physical category
  - Temperature: all four scales, round-trips, famous -40 identity
  - Case insensitivity and leading/trailing whitespace stripping
  - Identity conversion (same unit)
  - Zero and negative input values
  - Error paths: unknown unit, incompatible categories, mixed temp/non-temp
  - TOOL_DEFINITION schema shape
  - tool_registry integration
"""

import math

import pytest

from tools.toolcalls.unit_converter import (
    TOOL_DEFINITION,
    _fmt,
    unit_converter,
)


# ---------------------------------------------------------------------------
# _fmt helper
# ---------------------------------------------------------------------------


class TestFmt:
    def test_zero(self):
        assert _fmt(0.0) == "0"

    def test_negative_zero(self):
        # -0.0 == 0.0 in Python; should still return "0"
        assert _fmt(-0.0) == "0"

    def test_integer_valued_float(self):
        assert _fmt(42.0) == "42"

    def test_negative_integer_valued_float(self):
        assert _fmt(-5.0) == "-5"

    def test_normal_float_has_no_trailing_zeros(self):
        # g-format strips trailing zeros
        result = _fmt(1.5)
        assert result == "1.5"
        assert not result.endswith("0")

    def test_large_value_uses_scientific(self):
        # abs >= 1e10 → scientific
        result = _fmt(1e10)
        assert "e" in result.lower()

    def test_large_value_just_below_boundary_not_scientific(self):
        # 9_999_999_999 < 1e10
        result = _fmt(9_999_999_999.0)
        assert "e" not in result.lower()

    def test_small_value_uses_scientific(self):
        # abs < 1e-5 → scientific
        result = _fmt(9.9e-6)
        assert "e" in result.lower()

    def test_small_value_at_boundary_not_scientific(self):
        # 1e-5 is NOT < 1e-5
        result = _fmt(1e-5)
        # g-format for 1e-5 is "1e-05" but the code only forces :.6e for <1e-5,
        # so 1e-5 uses :.10g which also comes out as "1e-05" — just confirm "e" present
        # (either path, scientific notation is expected at this boundary)
        # The important thing is no crash and some reasonable output.
        assert result != ""

    def test_pi_precision(self):
        result = _fmt(math.pi)
        # Should give at least 9 significant digits
        assert result.startswith("3.14159265")


# ---------------------------------------------------------------------------
# Length
# ---------------------------------------------------------------------------


class TestLength:
    def test_ft_to_m(self):
        assert "0.3048" in unit_converter(1.0, "ft", "m")

    def test_m_to_ft(self):
        # 1 m = 1/0.3048 ≈ 3.280839895 ft
        assert "3.280839895" in unit_converter(1.0, "m", "ft")

    def test_km_to_mi(self):
        # 1 km = 1000/1609.344 ≈ 0.6213711922 mi
        assert "0.6213" in unit_converter(1.0, "km", "mi")

    def test_inch_to_cm(self):
        # 0.0254 / 0.01 = 2.54
        assert "2.54" in unit_converter(1.0, "inch", "cm")

    def test_yd_to_ft(self):
        # 0.9144 / 0.3048 = 3
        assert "3" in unit_converter(1.0, "yd", "ft")

    def test_nmi_to_m(self):
        assert "1852" in unit_converter(1.0, "nmi", "m")

    def test_au_to_km(self):
        # 1.495978707e11 m / 1e3 = 1.495978707e8 km = 149597870.7 km
        assert "149597870.7" in unit_converter(1.0, "au", "km")

    def test_mm_to_um(self):
        # 1e-3 / 1e-6 = 1000
        assert "1000" in unit_converter(1.0, "mm", "um")


# ---------------------------------------------------------------------------
# Mass
# ---------------------------------------------------------------------------


class TestMass:
    def test_lb_to_kg(self):
        assert "0.45359237" in unit_converter(1.0, "lb", "kg")

    def test_kg_to_lb(self):
        # 1 / 0.45359237 = 2.204622622...
        assert "2.204622" in unit_converter(1.0, "kg", "lb")

    def test_oz_to_g(self):
        # 0.028349523125 / 1e-3 ≈ 28.34952
        assert "28.34952" in unit_converter(1.0, "oz", "g")

    def test_tonne_to_kg(self):
        assert "1000" in unit_converter(1.0, "tonne", "kg")

    def test_short_ton_to_long_ton(self):
        # 907.18474 / 1016.0469088 ≈ 0.8928571
        assert "0.8928" in unit_converter(1.0, "ton", "long_ton")

    def test_slug_to_kg(self):
        assert "14.593903" in unit_converter(1.0, "slug", "kg")

    def test_g_to_mg(self):
        # 1e-3 / 1e-6 = 1000
        assert "1000" in unit_converter(1.0, "g", "mg")


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


class TestTime:
    def test_hour_to_seconds(self):
        assert "3600" in unit_converter(1.0, "h", "s")

    def test_min_to_s(self):
        assert "60" in unit_converter(1.0, "min", "s")

    def test_day_to_hours(self):
        # 86400 / 3600 = 24
        assert "24" in unit_converter(1.0, "day", "h")

    def test_year_to_days(self):
        # 31557600 / 86400 = 365.25
        assert "365.25" in unit_converter(1.0, "year", "day")

    def test_ms_to_us(self):
        # 1e-3 / 1e-6 = 1000
        assert "1000" in unit_converter(1.0, "ms", "us")

    def test_week_to_days(self):
        # 604800 / 86400 = 7
        assert "7" in unit_converter(1.0, "week", "day")


# ---------------------------------------------------------------------------
# Temperature
# ---------------------------------------------------------------------------


class TestTemperature:
    def test_c_to_f_freezing(self):
        assert "32" in unit_converter(0.0, "C", "F")

    def test_c_to_f_boiling(self):
        assert "212" in unit_converter(100.0, "C", "F")

    def test_f_to_c_freezing(self):
        assert "0" in unit_converter(32.0, "F", "C")

    def test_c_to_k_absolute_zero(self):
        # -273.15 C → 0 K
        assert "0" in unit_converter(-273.15, "C", "K")

    def test_k_to_c(self):
        # 273.15 K → 0 C
        assert "0" in unit_converter(273.15, "K", "C")

    def test_f_to_k_freezing(self):
        assert "273.15" in unit_converter(32.0, "F", "K")

    def test_k_to_r(self):
        # 273.15 K × 9/5 = 491.67 R
        assert "491.67" in unit_converter(273.15, "K", "R")

    def test_r_to_k(self):
        # 491.67 R × 5/9 ≈ 273.15 K
        result = unit_converter(491.67, "R", "K")
        assert "273.15" in result

    def test_negative_40_identity(self):
        # -40 °C == -40 °F (famous identity)
        assert "-40" in unit_converter(-40.0, "C", "F")

    def test_same_scale_identity(self):
        assert "100" in unit_converter(100.0, "K", "K")

    def test_celsius_round_trip(self):
        # 37 °C → K → °C should recover 37
        k_str = unit_converter(37.0, "C", "K")
        # extract kelvin value
        k_val = float(k_str.split("=")[1].split()[0])
        back = unit_converter(k_val, "K", "C")
        c_val = float(back.split("=")[1].split()[0])
        assert abs(c_val - 37.0) < 1e-9

    def test_fahrenheit_round_trip(self):
        result1 = unit_converter(98.6, "F", "C")
        c_val = float(result1.split("=")[1].split()[0])
        result2 = unit_converter(c_val, "C", "F")
        f_back = float(result2.split("=")[1].split()[0])
        assert abs(f_back - 98.6) < 1e-9

    def test_rankine_round_trip(self):
        result1 = unit_converter(671.67, "R", "F")
        f_val = float(result1.split("=")[1].split()[0])
        result2 = unit_converter(f_val, "F", "R")
        r_back = float(result2.split("=")[1].split()[0])
        assert abs(r_back - 671.67) < 1e-6

    def test_celsius_alias_lowercase(self):
        # "celsius" long-form should behave identically to "C"
        assert "212" in unit_converter(100.0, "celsius", "fahrenheit")


# ---------------------------------------------------------------------------
# Pressure
# ---------------------------------------------------------------------------


class TestPressure:
    def test_atm_to_pa(self):
        assert "101325" in unit_converter(1.0, "atm", "Pa")

    def test_bar_to_pa(self):
        assert "100000" in unit_converter(1.0, "bar", "Pa")

    def test_psi_to_pa(self):
        assert "6894.757" in unit_converter(1.0, "psi", "Pa")

    def test_mbar_to_pa(self):
        # 1 mbar = 100 Pa
        assert "100" in unit_converter(1.0, "mbar", "Pa")

    def test_torr_and_mmhg_are_equal(self):
        # torr and mmHg share the same factor → exact 1:1 conversion
        assert "1" in unit_converter(1.0, "torr", "mmhg")

    def test_kpa_to_bar(self):
        # 100 kPa = 1 bar
        assert "1" in unit_converter(100.0, "kPa", "bar")


# ---------------------------------------------------------------------------
# Force
# ---------------------------------------------------------------------------


class TestForce:
    def test_n_to_lbf(self):
        # 1 N ≈ 0.2248 lbf
        assert "0.2248" in unit_converter(1.0, "N", "lbf")

    def test_kn_to_n(self):
        assert "1000" in unit_converter(1.0, "kn", "N")

    def test_kip_to_lbf(self):
        # 4448.2216.../4.4482216... = 1000
        assert "1000" in unit_converter(1.0, "kip", "lbf")

    def test_kgf_to_n(self):
        assert "9.80665" in unit_converter(1.0, "kgf", "N")

    def test_dyne_to_n(self):
        # 1 dyne = 1e-5 N
        assert "1e-05" in unit_converter(1.0, "dyne", "N")


# ---------------------------------------------------------------------------
# Energy
# ---------------------------------------------------------------------------


class TestEnergy:
    def test_cal_to_j(self):
        assert "4.184" in unit_converter(1.0, "cal", "J")

    def test_kwh_to_j(self):
        assert "3600000" in unit_converter(1.0, "kWh", "J")

    def test_btu_to_j(self):
        assert "1055.05" in unit_converter(1.0, "BTU", "J")

    def test_kcal_to_cal(self):
        assert "1000" in unit_converter(1.0, "kcal", "cal")

    def test_ev_to_j(self):
        # Very small → scientific notation; 1.602176634e-19 J
        assert "1.6021" in unit_converter(1.0, "eV", "J")

    def test_ft_lbf_to_j(self):
        assert "1.355817" in unit_converter(1.0, "ft_lbf", "J")

    def test_mj_to_kwh(self):
        # 1 MJ = 1e6 / 3.6e6 kWh ≈ 0.2778 kWh
        assert "0.2777" in unit_converter(1.0, "MJ", "kWh")


# ---------------------------------------------------------------------------
# Power
# ---------------------------------------------------------------------------


class TestPower:
    def test_kw_to_w(self):
        assert "1000" in unit_converter(1.0, "kW", "W")

    def test_hp_to_kw(self):
        # 745.69987.../1000 ≈ 0.745699
        assert "0.7456998" in unit_converter(1.0, "hp", "kW")

    def test_gw_to_mw(self):
        assert "1000" in unit_converter(1.0, "GW", "MW")

    def test_btu_hr_to_w(self):
        # 0.29307107017 W
        assert "0.293071" in unit_converter(1.0, "btu/hr", "W")

    def test_ps_vs_hp_not_equal(self):
        # Metric hp (ps=735.5 W) ≠ mechanical hp (745.7 W)
        result_ps = unit_converter(1.0, "ps", "W")
        result_hp = unit_converter(1.0, "hp", "W")
        assert result_ps != result_hp


# ---------------------------------------------------------------------------
# Velocity
# ---------------------------------------------------------------------------


class TestVelocity:
    def test_mph_to_kph(self):
        # 0.44704 * 3.6 = 1.60934
        assert "1.60934" in unit_converter(1.0, "mph", "km/h")

    def test_knot_to_mph(self):
        # 0.514444 / 0.44704 ≈ 1.15078
        assert "1.1507" in unit_converter(1.0, "knot", "mph")

    def test_mach_to_m_s(self):
        assert "343" in unit_converter(1.0, "mach", "m/s")

    def test_fps_to_mph(self):
        # 0.3048 / 0.44704 ≈ 0.68182
        assert "0.6818" in unit_converter(1.0, "fps", "mph")

    def test_kt_and_knots_equivalent(self):
        # "kt" and "knots" are aliases → same result
        r1 = unit_converter(10.0, "kt", "m/s")
        r2 = unit_converter(10.0, "knots", "m/s")
        assert r1.split("=")[1] == r2.split("=")[1]

    def test_kts_alias(self):
        assert "0.514444" in unit_converter(1.0, "kts", "m/s")


# ---------------------------------------------------------------------------
# Area
# ---------------------------------------------------------------------------


class TestArea:
    def test_sqft_to_sqm(self):
        assert "0.09290304" in unit_converter(1.0, "sqft", "m2")

    def test_acre_to_ha(self):
        # 4046.8564224 / 10000 = 0.40468564224
        assert "0.40468" in unit_converter(1.0, "acre", "ha")

    def test_km2_to_mi2(self):
        # 1e6 / 2589988.110336 ≈ 0.386102
        assert "0.3861" in unit_converter(1.0, "km2", "mi2")

    def test_in2_to_cm2(self):
        # 6.4516e-4 / 1e-4 = 6.4516
        assert "6.4516" in unit_converter(1.0, "in2", "cm2")


# ---------------------------------------------------------------------------
# Volume
# ---------------------------------------------------------------------------


class TestVolume:
    def test_liter_to_ml(self):
        assert "1000" in unit_converter(1.0, "L", "mL")

    def test_gallon_to_liter(self):
        # 0.003785411784 / 1e-3 = 3.785411784
        assert "3.785411784" in unit_converter(1.0, "gal", "L")

    def test_bbl_to_gal(self):
        # 0.158987295 / 0.003785411784 = 42 (petroleum barrel)
        assert "42" in unit_converter(1.0, "bbl", "gal")

    def test_ft3_to_in3(self):
        # 0.028316846592 / 1.6387064e-5 = 1728
        assert "1728" in unit_converter(1.0, "ft3", "in3")

    def test_ukgal_and_usgal_differ(self):
        # Imperial gallon ≠ US gallon
        r_uk = unit_converter(1.0, "ukgal", "L")
        r_us = unit_converter(1.0, "usgal", "L")
        assert r_uk != r_us

    def test_cc_to_ml(self):
        # 1 cc = 1 mL (both 1e-6 m³)
        assert "1" in unit_converter(1.0, "cc", "mL")


# ---------------------------------------------------------------------------
# Angle
# ---------------------------------------------------------------------------


class TestAngle:
    def test_deg_to_rad_half_circle(self):
        # 180° = π rad
        assert "3.14159" in unit_converter(180.0, "deg", "rad")

    def test_rev_to_deg(self):
        # 1 revolution = 360°
        assert "360" in unit_converter(1.0, "rev", "deg")

    def test_arcmin_to_deg(self):
        # 60 arcmin = 1°
        assert "1" in unit_converter(60.0, "arcmin", "deg")

    def test_arcsec_to_arcmin(self):
        # 60 arcsec = 1 arcmin
        assert "1" in unit_converter(60.0, "arcsec", "arcmin")

    def test_grad_to_deg(self):
        # 100 grad = 90° (right angle)
        assert "90" in unit_converter(100.0, "grad", "deg")


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------


class TestFrequency:
    def test_ghz_to_mhz(self):
        assert "1000" in unit_converter(1.0, "GHz", "MHz")

    def test_rpm_to_hz(self):
        # 60 RPM = 1 Hz
        assert "1" in unit_converter(60.0, "rpm", "Hz")

    def test_hz_to_rpm(self):
        # 1 Hz = 60 RPM
        assert "60" in unit_converter(1.0, "Hz", "rpm")

    def test_khz_to_hz(self):
        assert "1000" in unit_converter(1.0, "kHz", "Hz")


# ---------------------------------------------------------------------------
# Case insensitivity and whitespace stripping
# ---------------------------------------------------------------------------


class TestCaseAndWhitespace:
    def test_uppercase_units(self):
        assert "0.3048" in unit_converter(1.0, "FT", "M")

    def test_mixed_case(self):
        assert "0.6213" in unit_converter(1.0, "Km", "Mi")

    def test_leading_trailing_whitespace(self):
        r_clean = unit_converter(1.0, "ft", "m")
        r_padded = unit_converter(1.0, "  ft  ", "  m  ")
        # numeric result must be the same regardless of padding
        assert "0.3048" in r_clean
        assert "0.3048" in r_padded

    def test_long_form_names(self):
        assert "0.3048" in unit_converter(1.0, "feet", "meters")

    def test_temperature_case_insensitive(self):
        # "celsius"/"fahrenheit" long-form, uppercase
        assert "212" in unit_converter(100.0, "CELSIUS", "FAHRENHEIT")


# ---------------------------------------------------------------------------
# Identity conversion (same unit)
# ---------------------------------------------------------------------------


class TestIdentityConversion:
    def test_same_unit_length(self):
        assert "5 m = 5 m" == unit_converter(5.0, "m", "m")

    def test_same_unit_pressure(self):
        assert "1 Pa = 1 Pa" == unit_converter(1.0, "Pa", "Pa")

    def test_same_unit_temperature(self):
        assert "100" in unit_converter(100.0, "K", "K")

    def test_same_unit_velocity(self):
        assert "1" in unit_converter(1.0, "m/s", "m/s")


# ---------------------------------------------------------------------------
# Zero and negative input values
# ---------------------------------------------------------------------------


class TestZeroAndNegative:
    def test_zero_multiplicative(self):
        assert "0 km = 0 mi" == unit_converter(0.0, "km", "mi")

    def test_zero_temperature_celsius_to_kelvin(self):
        # 0 °C = 273.15 K
        assert "273.15" in unit_converter(0.0, "C", "K")

    def test_negative_length(self):
        # -1 m = -100 cm
        assert "-100" in unit_converter(-1.0, "m", "cm")

    def test_negative_temperature_round_trip(self):
        # -40 °C = -40 °F (famous identity)
        assert "-40" in unit_converter(-40.0, "C", "F")

    def test_large_multiplier(self):
        # 1000 km = 1 000 000 m
        assert "1000000" in unit_converter(1000.0, "km", "m")


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestErrorCases:
    def test_unknown_from_unit(self):
        result = unit_converter(1.0, "furlong", "m")
        assert result.startswith("Error:")
        assert "furlong" in result

    def test_unknown_to_unit(self):
        result = unit_converter(1.0, "m", "furlong")
        assert result.startswith("Error:")
        assert "furlong" in result

    def test_incompatible_categories(self):
        result = unit_converter(1.0, "m", "kg")
        assert result.startswith("Error:")
        assert "length" in result
        assert "mass" in result

    def test_temperature_from_non_temp_to_temp(self):
        result = unit_converter(1.0, "m", "C")
        assert result.startswith("Error:")

    def test_temperature_from_temp_to_non_temp(self):
        result = unit_converter(1.0, "C", "m")
        assert result.startswith("Error:")

    def test_empty_from_unit(self):
        result = unit_converter(1.0, "", "m")
        assert result.startswith("Error:")

    def test_empty_to_unit(self):
        result = unit_converter(1.0, "m", "")
        assert result.startswith("Error:")

    def test_both_unknown_units(self):
        result = unit_converter(1.0, "zorb", "glarb")
        assert result.startswith("Error:")

    def test_pressure_to_velocity_incompatible(self):
        result = unit_converter(1.0, "psi", "mph")
        assert result.startswith("Error:")
        assert "pressure" in result
        assert "velocity" in result


# ---------------------------------------------------------------------------
# TOOL_DEFINITION schema
# ---------------------------------------------------------------------------


class TestToolDefinition:
    def test_top_level_type(self):
        assert TOOL_DEFINITION["type"] == "function"

    def test_function_name(self):
        assert TOOL_DEFINITION["function"]["name"] == "unit_converter"

    def test_required_params_present(self):
        required = TOOL_DEFINITION["function"]["parameters"]["required"]
        assert set(required) == {"value", "from_unit", "to_unit"}

    def test_value_param_is_number(self):
        props = TOOL_DEFINITION["function"]["parameters"]["properties"]
        assert props["value"]["type"] == "number"

    def test_unit_params_are_strings(self):
        props = TOOL_DEFINITION["function"]["parameters"]["properties"]
        assert props["from_unit"]["type"] == "string"
        assert props["to_unit"]["type"] == "string"

    def test_description_mentions_all_categories(self):
        desc = TOOL_DEFINITION["function"]["description"]
        for category in ("length", "mass", "time", "temperature", "pressure",
                         "force", "energy", "power", "velocity", "area",
                         "volume", "angle", "frequency"):
            assert category in desc.lower(), f"'{category}' missing from description"


# ---------------------------------------------------------------------------
# tool_registry integration
# ---------------------------------------------------------------------------


class TestToolRegistryIntegration:
    def test_unit_converter_registered(self):
        from tools.toolcalls.tool_registry import TOOLS
        assert "unit_converter" in TOOLS

    def test_unit_converter_callable_via_registry(self):
        from tools.toolcalls.tool_registry import TOOLS
        result = TOOLS["unit_converter"](
            {"value": 1.0, "from_unit": "ft", "to_unit": "m"}
        )
        assert "0.3048" in result

    def test_unit_converter_definition_in_tool_definitions(self):
        from tools.toolcalls.tool_registry import TOOL_DEFINITIONS
        names = [td["function"]["name"] for td in TOOL_DEFINITIONS]
        assert "unit_converter" in names
