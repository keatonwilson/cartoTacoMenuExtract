"""Pydantic models mirroring CartoTaco production tables."""

import re

from pydantic import BaseModel, Field, field_validator


def normalize_time(value: str) -> str:
    """Normalize free-text time input to HH:MM 24-hour format.

    Handles: "10 am", "10am", "10:00 AM", "8:30pm", "22:00", etc.
    Returns empty string for empty input.
    Raises ValueError for unparseable input.
    """
    if not value or not value.strip():
        return ""

    text = value.strip().lower()

    # Already valid HH:MM 24-hour format
    if re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", text):
        h, m = text.split(":")
        return f"{int(h):02d}:{m}"

    # Parse optional hours:minutes with am/pm
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$", text)
    if m:
        hour = int(m.group(1))
        minute = m.group(2) or "00"
        period = m.group(3)

        if hour < 1 or hour > 12:
            raise ValueError(f"Invalid hour in time: {value}")

        if period == "am":
            hour = 0 if hour == 12 else hour
        else:  # pm
            hour = hour if hour == 12 else hour + 12

        return f"{hour:02d}:{minute}"

    raise ValueError(f"Cannot parse time: {value}")


class SiteData(BaseModel):
    name: str = ""
    type: str = Field(default="", description="'Brick and Mortar', 'Stand', or 'Truck'")
    address: str = ""
    phone: str = Field(default="", description="Format: (520) 123-4567")
    website: str = ""
    instagram: str = Field(default="", description="Handle without @ symbol")
    facebook: str = ""
    contact: str = ""
    lat_1: float | None = None
    lon_1: float | None = None
    days_loc_1: str = ""
    lat_2: float | None = None
    lon_2: float | None = None
    days_loc_2: str = ""


class MenuData(BaseModel):
    burro_yes: bool = False
    burro_perc: float | None = Field(default=None, ge=0, le=1)
    taco_yes: bool = False
    taco_perc: float | None = Field(default=None, ge=0, le=1)
    torta_yes: bool = False
    torta_perc: float | None = Field(default=None, ge=0, le=1)
    dog_yes: bool = False
    dog_perc: float | None = Field(default=None, ge=0, le=1)
    plate_yes: bool = False
    plate_perc: float | None = Field(default=None, ge=0, le=1)
    cocktail_yes: bool = False
    cocktail_perc: float | None = Field(default=None, ge=0, le=1)
    gordita_yes: bool = False
    gordita_perc: float | None = Field(default=None, ge=0, le=1)
    huarache_yes: bool = False
    huarache_perc: float | None = Field(default=None, ge=0, le=1)
    cemita_yes: bool = False
    cemita_perc: float | None = Field(default=None, ge=0, le=1)
    flauta_yes: bool = False
    flauta_perc: float | None = Field(default=None, ge=0, le=1)
    chalupa_yes: bool = False
    chalupa_perc: float | None = Field(default=None, ge=0, le=1)
    molote_yes: bool = False
    molote_perc: float | None = Field(default=None, ge=0, le=1)
    tostada_yes: bool = False
    tostada_perc: float | None = Field(default=None, ge=0, le=1)
    enchilada_yes: bool = False
    enchilada_perc: float | None = Field(default=None, ge=0, le=1)
    tamale_yes: bool = False
    tamale_perc: float | None = Field(default=None, ge=0, le=1)
    sope_yes: bool = False
    sope_perc: float | None = Field(default=None, ge=0, le=1)
    caldo_yes: bool = False
    caldo_perc: float | None = Field(default=None, ge=0, le=1)
    flour_corn: str = Field(default="", description="'Flour', 'Corn', or 'Both'")
    handmade_tortilla: bool = False
    specialty_items: list[str] = Field(
        default_factory=list,
        description="Notable specialty items (text only, FK linking done manually)",
    )


class ProteinData(BaseModel):
    chicken_yes: bool = False
    chicken_perc: float | None = Field(default=None, ge=0, le=1)
    beef_yes: bool = False
    beef_perc: float | None = Field(default=None, ge=0, le=1)
    pork_yes: bool = False
    pork_perc: float | None = Field(default=None, ge=0, le=1)
    fish_yes: bool = False
    fish_perc: float | None = Field(default=None, ge=0, le=1)
    veg_yes: bool = False
    veg_perc: float | None = Field(default=None, ge=0, le=1)
    chicken_style_1: str = ""
    chicken_style_2: str = ""
    chicken_style_3: str = ""
    beef_style_1: str = ""
    beef_style_2: str = ""
    beef_style_3: str = ""
    pork_style_1: str = ""
    pork_style_2: str = ""
    pork_style_3: str = ""
    fish_style_1: str = ""
    fish_style_2: str = ""
    fish_style_3: str = ""
    veg_style_1: str = ""
    veg_style_2: str = ""
    veg_style_3: str = ""
    protein_specs: list[str] = Field(
        default_factory=list,
        description="Notable specialty proteins (text only, FK linking done manually)",
    )


class HoursData(BaseModel):
    mon_start: str = ""
    mon_end: str = ""
    tue_start: str = ""
    tue_end: str = ""
    wed_start: str = ""
    wed_end: str = ""
    thu_start: str = ""
    thu_end: str = ""
    fri_start: str = ""
    fri_end: str = ""
    sat_start: str = ""
    sat_end: str = ""
    sun_start: str = ""
    sun_end: str = ""

    @field_validator("*", mode="before")
    @classmethod
    def _normalize_times(cls, v: object) -> object:
        if isinstance(v, str):
            return normalize_time(v)
        return v


class SalsaData(BaseModel):
    total_num: int | None = None
    heat_overall: int | None = Field(default=None, ge=1, le=10)
    verde_yes: bool = False
    rojo_yes: bool = False
    pico_yes: bool = False
    pickles_yes: bool = False
    chipotle_yes: bool = False
    avo_yes: bool = False
    molcajete_yes: bool = False
    macha_yes: bool = False
    other_1_name: str = ""
    other_1_descrip: str = ""
    other_2_name: str = ""
    other_2_descrip: str = ""
    other_3_name: str = ""
    other_3_descrip: str = ""
    salsa_specs: list[str] = Field(
        default_factory=list,
        description="Notable specialty salsas (text only, FK linking done manually)",
    )


class DescriptionData(BaseModel):
    short_descrip: str = ""
    long_descrip: str = ""
    region: str = ""


class ExtractedEstablishment(BaseModel):
    """Top-level model returned by Claude Vision extraction."""

    restaurant_name: str
    site: SiteData = Field(default_factory=SiteData)
    menu: MenuData = Field(default_factory=MenuData)
    protein: ProteinData = Field(default_factory=ProteinData)
    hours: HoursData = Field(default_factory=HoursData)
    salsa: SalsaData = Field(default_factory=SalsaData)
    description: DescriptionData = Field(default_factory=DescriptionData)
