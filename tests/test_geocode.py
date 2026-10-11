"""Address cleanup before geocoding."""

import pytest

from src.description_gen import _clean_address


@pytest.mark.parametrize("raw, clean", [
    ("4280 N Oracle Rd, Ste 120, Tucson, AZ 85705", "4280 N Oracle Rd, Tucson, AZ 85705"),
    ("2617 N 1st Ave, Ste 2 (Golden Nugget Tavern), Tucson, AZ 85719", "2617 N 1st Ave, Tucson, AZ 85719"),
    ("1910 N La Cañada Dr # 4, Green Valley, AZ 85614", "1910 N La Cañada Dr, Green Valley, AZ 85614"),
    ("123 E Speedway Blvd Suite B, Tucson, AZ", "123 E Speedway Blvd, Tucson, AZ"),
    ("4500 W Ina Rd, Tucson, AZ 85741", "4500 W Ina Rd, Tucson, AZ 85741"),
])
def test_clean_address(raw, clean):
    assert _clean_address(raw) == clean
