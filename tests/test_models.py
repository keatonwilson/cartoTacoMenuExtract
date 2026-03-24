"""Tests for Pydantic models."""

import json
import pytest
from src.models import (
    ExtractedEstablishment,
    SiteData,
    MenuData,
    ProteinData,
    HoursData,
    SalsaData,
    DescriptionData,
    normalize_time,
)


def test_extracted_establishment_defaults():
    """Minimal valid extraction has just a restaurant_name."""
    ext = ExtractedEstablishment(restaurant_name="Test Tacos")
    assert ext.restaurant_name == "Test Tacos"
    assert ext.menu.taco_yes is False
    assert ext.protein.beef_yes is False
    assert ext.hours.mon_start == ""
    assert ext.salsa.total_num is None
    assert ext.description.short_descrip == ""


def test_full_extraction_roundtrip():
    """Full data round-trips through JSON serialization."""
    ext = ExtractedEstablishment(
        restaurant_name="El Guero Canelo",
        site=SiteData(
            name="El Guero Canelo",
            type="Brick and Mortar",
            address="5201 S 12th Ave",
            phone="(520) 295-9005",
        ),
        menu=MenuData(
            taco_yes=True,
            dog_yes=True,
            burro_yes=True,
            flour_corn="Both",
            handmade_tortilla=True,
            specialty_items=["Sonoran Hot Dog"],
        ),
        protein=ProteinData(
            beef_yes=True,
            pork_yes=True,
            beef_style_1="carne asada",
            pork_style_1="al pastor",
        ),
        hours=HoursData(mon_start="10:00", mon_end="22:00"),
        salsa=SalsaData(total_num=4, verde_yes=True, rojo_yes=True),
        description=DescriptionData(
            short_descrip="Iconic Sonoran hot dogs and tacos",
            region="South Tucson",
        ),
    )

    json_str = ext.model_dump_json()
    parsed = json.loads(json_str)
    restored = ExtractedEstablishment.model_validate(parsed)

    assert restored.restaurant_name == "El Guero Canelo"
    assert restored.menu.taco_yes is True
    assert restored.menu.specialty_items == ["Sonoran Hot Dog"]
    assert restored.protein.beef_style_1 == "carne asada"
    assert restored.salsa.total_num == 4


def test_json_schema_generation():
    """Schema generates without error and contains expected keys."""
    schema = ExtractedEstablishment.model_json_schema()
    assert "properties" in schema
    assert "restaurant_name" in schema["properties"]


def test_partial_data_validation():
    """Models accept partial data gracefully."""
    data = {
        "restaurant_name": "Test Place",
        "menu": {"taco_yes": True},
        "protein": {"beef_yes": True, "beef_style_1": "carne asada"},
    }
    ext = ExtractedEstablishment.model_validate(data)
    assert ext.menu.taco_yes is True
    assert ext.menu.burro_yes is False
    assert ext.protein.beef_style_1 == "carne asada"
    assert ext.hours.mon_start == ""


# --- Time normalization tests ---


class TestNormalizeTime:
    def test_am_with_space(self):
        assert normalize_time("10 am") == "10:00"

    def test_pm_no_space(self):
        assert normalize_time("10pm") == "22:00"

    def test_am_with_minutes(self):
        assert normalize_time("8:30 AM") == "08:30"

    def test_pm_with_minutes(self):
        assert normalize_time("3:30 pm") == "15:30"

    def test_already_valid_24h(self):
        assert normalize_time("22:00") == "22:00"

    def test_already_valid_single_digit(self):
        assert normalize_time("8:00") == "08:00"

    def test_empty_string(self):
        assert normalize_time("") == ""

    def test_whitespace_only(self):
        assert normalize_time("   ") == ""

    def test_midnight_12am(self):
        assert normalize_time("12am") == "00:00"

    def test_noon_12pm(self):
        assert normalize_time("12pm") == "12:00"

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            normalize_time("not a time")

    def test_hours_model_normalizes(self):
        """HoursData auto-normalizes on construction."""
        h = HoursData(mon_start="10 am", mon_end="10pm")
        assert h.mon_start == "10:00"
        assert h.mon_end == "22:00"

    def test_hours_model_passthrough(self):
        """Already-valid times pass through unchanged."""
        h = HoursData(mon_start="08:30", mon_end="22:00")
        assert h.mon_start == "08:30"
        assert h.mon_end == "22:00"


# --- Percentage field tests ---


class TestPercFields:
    def test_menu_perc_defaults_to_none(self):
        m = MenuData()
        assert m.taco_perc is None
        assert m.burro_perc is None

    def test_menu_perc_valid_values(self):
        m = MenuData(taco_perc=0.5, burro_perc=0.3)
        assert m.taco_perc == 0.5
        assert m.burro_perc == 0.3

    def test_menu_perc_boundary_values(self):
        m = MenuData(taco_perc=0.0, burro_perc=1.0)
        assert m.taco_perc == 0.0
        assert m.burro_perc == 1.0

    def test_menu_perc_rejects_over_1(self):
        with pytest.raises(Exception):
            MenuData(taco_perc=1.5)

    def test_menu_perc_rejects_negative(self):
        with pytest.raises(Exception):
            MenuData(taco_perc=-0.1)

    def test_protein_perc_defaults_to_none(self):
        p = ProteinData()
        assert p.chicken_perc is None
        assert p.beef_perc is None

    def test_protein_perc_valid_values(self):
        p = ProteinData(chicken_perc=0.4, beef_perc=0.6)
        assert p.chicken_perc == 0.4
        assert p.beef_perc == 0.6

    def test_protein_perc_rejects_over_1(self):
        with pytest.raises(Exception):
            ProteinData(beef_perc=2.0)

    def test_existing_rows_without_perc_fields(self):
        """Existing staging data without _perc fields should load fine."""
        data = {"taco_yes": True, "burro_yes": False}
        m = MenuData.model_validate(data)
        assert m.taco_yes is True
        assert m.taco_perc is None
