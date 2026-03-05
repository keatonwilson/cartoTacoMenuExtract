"""Tests for Pydantic models."""

import json
from src.models import (
    ExtractedEstablishment,
    SiteData,
    MenuData,
    ProteinData,
    HoursData,
    SalsaData,
    DescriptionData,
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
