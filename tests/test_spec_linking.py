"""Tests for spec name -> id linking at promotion time. No network or DB."""

from unittest.mock import patch

from src.promotion import promote
from src.spec_tables import build_spec_index, normalize_spec_name, resolve_spec_id
from tests.test_scouting import FakeClient, menu_photo_row

SPECS = {
    "item_spec": [{"id": 1, "name": "Sonoran Hot Dog"}, {"id": 2, "name": "Caramelo"}],
    "protein_spec": [
        {"id": 10, "name": "Cabeza"},
        {"id": 11, "name": "Birria"},
        {"id": 12, "name": "birria "},  # case/space duplicate -> ambiguous
    ],
    "salsa_spec": [{"id": 20, "name": "Salsa Macha"}],
}


def _promote(row):
    client = FakeClient(select_data={"sites": [{"est_id": 41}], **SPECS})
    with patch("src.promotion.get_client", return_value=client), \
         patch("src.promotion.get_extraction", return_value=row), \
         patch("src.promotion.set_status"):
        promote("row-2")
    return client


def test_normalize_spec_name():
    assert normalize_spec_name("  Sonoran   HOT\tdog ") == "sonoran hot dog"
    assert normalize_spec_name(None) == ""


def test_resolve_requires_exactly_one_match():
    client = FakeClient(select_data=SPECS)
    index = build_spec_index(client, "protein_spec")
    assert resolve_spec_id(index, "CABEZA") == 10
    assert resolve_spec_id(index, "Birria") is None  # ambiguous
    assert resolve_spec_id(index, "Lengua") is None  # no match


def test_menu_specs_link_case_insensitively_and_empty_slots_clear():
    row = menu_photo_row()
    row["menu_data"]["specialty_items"] = ["  sonoran hot  dog", "caramelo"]
    menu = _promote(row).write_for("menu")
    assert menu["spec_id_1"] == 1
    assert menu["spec_id_2"] == 2
    assert menu["spec_id_3"] is None


def test_unresolved_name_leaves_existing_link_untouched():
    row = menu_photo_row()
    row["protein_data"]["protein_specs"] = ["Lengua", "Birria", "Cabeza"]
    prot = _promote(row).write_for("protein")
    # Omitted keys mean the upsert keeps whatever link is already stored
    assert "spec_id_1" not in prot
    assert "spec_id_2" not in prot
    assert prot["spec_id_3"] == 10


def test_salsa_specs_are_linked():
    row = menu_photo_row()
    row["salsa_data"]["salsa_specs"] = ["salsa macha"]
    salsa = _promote(row).write_for("salsa")
    assert salsa["salsa_spec_1"] == "salsa macha"
    assert salsa["spec_id_1"] == 20
    assert salsa["spec_id_2"] is None


def test_same_spec_is_not_linked_twice():
    row = menu_photo_row()
    row["menu_data"]["specialty_items"] = ["Caramelo", "CARAMELO"]
    menu = _promote(row).write_for("menu")
    assert menu["spec_id_1"] == 2
    assert "spec_id_2" not in menu


def test_health_summary_zero_fills_and_counts():
    from src.data_health import summarize

    rows = [{"severity": "error"}, {"severity": "error"}, {"severity": "info"}]
    assert summarize(rows) == {"error": 2, "warn": 0, "info": 1}
