"""Tests for the pending-spot (web scouting) pipeline: model, promotion paths,
vetting flip, and retraction. No network or DB — Supabase client is faked."""

from unittest.mock import patch

import pytest

from src.models import DiscoveredCandidate, ScrapedSpot
from src.promotion import promote, retract_pending_site
from src.scraping import _normalize_name, mark_known_candidates


# --- Fake Supabase client ---

class _Result:
    def __init__(self, data):
        self.data = data


class _FakeTable:
    def __init__(self, name, db):
        self.name = name
        self.db = db
        self._op = "select"
        self._payload = None
        self._filters = {}

    def select(self, *args, **kwargs):
        self._op = "select"
        return self

    def eq(self, col, val):
        self._filters[col] = val
        return self

    def neq(self, col, val):
        return self

    def ilike(self, col, pat):
        return self

    def limit(self, n):
        return self

    def order(self, col, desc=False):
        return self

    def upsert(self, row, on_conflict=None):
        self._op = "upsert"
        self._payload = row
        return self

    def update(self, row):
        self._op = "update"
        self._payload = row
        return self

    def delete(self):
        self._op = "delete"
        return self

    def insert(self, row):
        self._op = "insert"
        self._payload = row
        return self

    def execute(self):
        if self._op == "upsert":
            self.db.writes.append((self.name, self._payload))
            return _Result([self._payload])
        if self._op == "update":
            self.db.updates.append((self.name, self._payload, dict(self._filters)))
            return _Result([])
        if self._op == "delete":
            self.db.deletes.append((self.name, dict(self._filters)))
            return _Result([])
        if self._op == "insert":
            self.db.inserts.append((self.name, self._payload))
            return _Result([{**self._payload, "id": "fake-id"}])
        data = self.db.select_data.get(self.name, [])
        for col, val in self._filters.items():
            data = [r for r in data if r.get(col) == val]
        return _Result(data)


class FakeClient:
    def __init__(self, select_data=None):
        self.select_data = select_data or {}
        self.writes = []  # (table, row) upserts
        self.updates = []
        self.deletes = []
        self.inserts = []

    def table(self, name):
        return _FakeTable(name, self)

    def written_tables(self):
        return {t for t, _ in self.writes}

    def write_for(self, table):
        return next(row for t, row in self.writes if t == table)


# --- Fixtures ---

def scraped_row(hours=None, description=None):
    return {
        "id": "row-1",
        "pipeline": "web_scrape",
        "restaurant_name": "Tacos El Ejemplo",
        "created_at": "2026-07-06T10:00:00Z",
        "site_data": {
            "name": "Tacos El Ejemplo",
            "type": "Truck",
            "address": "123 S 4th Ave, Tucson, AZ",
            "phone": "",
            "website": "https://tacoselejemplo.com",
            "instagram": "tacoselejemplo",
            "facebook": "",
            "lat_1": 32.2,
            "lon_1": -110.96,
            "days_loc_1": "",
        },
        "hours_data": hours if hours is not None else {"mon_start": "10:00", "mon_end": "20:00"},
        "description_data": description
        if description is not None
        else {"short_descrip": "Scouted truck on 4th Ave", "long_descrip": "", "region": ""},
        "source_urls": ["https://tacoselejemplo.com", "https://instagram.com/tacoselejemplo"],
    }


def menu_photo_row():
    return {
        "id": "row-2",
        "restaurant_name": "Tacos El Ejemplo",
        "site_data": {"name": "Tacos El Ejemplo", "type": "Truck"},
        "menu_data": {"taco_yes": True, "taco_perc": 1.0, "specialty_items": []},
        "protein_data": {"beef_yes": True, "beef_perc": 1.0, "protein_specs": []},
        "hours_data": {"mon_start": "10:00", "mon_end": "20:00"},
        "salsa_data": {"total_num": 3, "salsa_specs": []},
        "description_data": {"short_descrip": "Vetted!", "long_descrip": "", "region": ""},
    }


# --- ScrapedSpot model ---

def test_scraped_spot_normalizes_hours():
    spot = ScrapedSpot(
        restaurant_name="Test",
        hours={"mon_start": "10 am", "mon_end": "8:30pm"},
    )
    assert spot.hours.mon_start == "10:00"
    assert spot.hours.mon_end == "20:30"


def test_scraped_spot_defaults_are_empty():
    spot = ScrapedSpot(restaurant_name="Test")
    assert spot.site.name == ""
    assert spot.confidence == {}
    assert spot.evidence_urls == []


# --- Discovery: known-name diffing ---

def test_normalize_name_strips_accents_punctuation_case():
    assert _normalize_name("Taquería “El Güero”!") == "taqueria el guero"
    assert _normalize_name("  TACOS   APSON ") == "tacos apson"


def test_mark_known_flags_exact_and_containment_matches():
    candidates = [
        DiscoveredCandidate(name="Tacos El Ejemplo"),   # containment of known
        DiscoveredCandidate(name="Taquería Pico de Gallo"),  # exact (accent-insensitive)
        DiscoveredCandidate(name="Birria Nueva"),        # genuinely new
    ]
    known = ["El Ejemplo", "Taqueria Pico de Gallo", "Seis Kitchen"]

    marked = mark_known_candidates(candidates, known)
    assert [c.already_known for c in marked] == [True, True, False]


def test_mark_known_short_names_require_exact_match():
    # "Rollies" ⊄ flagged by containment against "Rollies Mexican Patio"? It is
    # long enough (7 chars) — but a tiny name like "Taco" must not match everything
    candidates = [DiscoveredCandidate(name="Taco")]
    marked = mark_known_candidates(candidates, ["Tacos Apson", "El Taco Tote"])
    assert marked[0].already_known is False


# --- Promotion: web_scrape path ---

def test_scraped_promotion_writes_pending_site():
    client = FakeClient(select_data={"sites": [{"est_id": 41}]})
    with patch("src.promotion.get_client", return_value=client), \
         patch("src.promotion.get_extraction", return_value=scraped_row()), \
         patch("src.promotion.set_status") as set_status:
        est_id = promote("row-1")

    assert est_id == 42  # max existing + 1
    site = client.write_for("sites")
    assert site["vetting_status"] == "pending"
    assert site["source"] == "web_scrape"
    assert site["source_url"] == "https://tacoselejemplo.com"
    assert site["scraped_at"] == "2026-07-06T10:00:00Z"
    assert site["est_id"] == 42
    # hours + descriptions written, editorial tables untouched
    assert client.written_tables() == {"sites", "hours", "descriptions"}
    set_status.assert_called_once_with("row-1", "promoted")


def test_scraped_promotion_skips_empty_hours_and_descriptions():
    row = scraped_row(hours={"mon_start": "", "mon_end": ""}, description={"short_descrip": ""})
    client = FakeClient(select_data={"sites": []})
    with patch("src.promotion.get_client", return_value=client), \
         patch("src.promotion.get_extraction", return_value=row), \
         patch("src.promotion.set_status"):
        est_id = promote("row-1")

    assert est_id == 1
    assert client.written_tables() == {"sites"}


def test_scraped_row_with_hand_filled_menu_takes_full_path_and_vets():
    # Admin hand-entered menu/protein data on a scouted row: promotion must
    # write all six tables and flip the pending target to vetted.
    row = scraped_row()
    row["menu_data"] = {"quesadilla_yes": True, "quesadilla_perc": 1.0, "specialty_items": []}
    row["protein_data"] = {"chicken_yes": True, "chicken_perc": 1.0, "protein_specs": []}
    row["salsa_data"] = {"total_num": 2, "salsa_specs": []}
    client = FakeClient(select_data={"sites": [{"est_id": 21, "vetting_status": "pending"}]})
    with patch("src.promotion.get_client", return_value=client), \
         patch("src.promotion.get_extraction", return_value=row), \
         patch("src.promotion.set_status"):
        est_id = promote("row-1", est_id=21)

    assert est_id == 21
    assert client.written_tables() == {"sites", "menu", "protein", "hours", "salsa", "descriptions"}
    site = client.write_for("sites")
    assert site["vetting_status"] == "vetted"
    assert client.write_for("menu")["quesadilla_yes"] is True


# --- Promotion: menu_photo path + vetting flip ---

def test_menu_photo_promotion_flips_pending_to_vetted():
    client = FakeClient(select_data={"sites": [{"est_id": 5, "vetting_status": "pending"}]})
    with patch("src.promotion.get_client", return_value=client), \
         patch("src.promotion.get_extraction", return_value=menu_photo_row()), \
         patch("src.promotion.set_status"):
        est_id = promote("row-2", est_id=5)

    assert est_id == 5
    site = client.write_for("sites")
    assert site["vetting_status"] == "vetted"
    assert site["vetted_at"]
    # Full promotion writes all six tables
    assert {"sites", "menu", "protein", "hours", "salsa", "descriptions"} <= client.written_tables()


def test_menu_photo_promotion_leaves_vetted_sites_alone():
    client = FakeClient(select_data={"sites": [{"est_id": 5, "vetting_status": "vetted"}]})
    with patch("src.promotion.get_client", return_value=client), \
         patch("src.promotion.get_extraction", return_value=menu_photo_row()), \
         patch("src.promotion.set_status"):
        promote("row-2", est_id=5)

    site = client.write_for("sites")
    assert "vetting_status" not in site
    assert "vetted_at" not in site


# --- Retraction ---

def test_retract_deletes_pending_site_and_children():
    client = FakeClient(select_data={"sites": [{"est_id": 7, "vetting_status": "pending"}]})
    with patch("src.promotion.get_client", return_value=client):
        retract_pending_site(7)

    deleted_tables = [t for t, _ in client.deletes]
    assert set(deleted_tables) == {"descriptions", "hours", "menu", "protein", "salsa", "sites"}
    assert all(f == {"est_id": 7} for _, f in client.deletes)


def test_retract_refuses_vetted_site():
    client = FakeClient(select_data={"sites": [{"est_id": 7, "vetting_status": "vetted"}]})
    with patch("src.promotion.get_client", return_value=client):
        with pytest.raises(ValueError, match="vetted"):
            retract_pending_site(7)
    assert client.deletes == []


def test_retract_unknown_est_id():
    client = FakeClient(select_data={"sites": []})
    with patch("src.promotion.get_client", return_value=client):
        with pytest.raises(ValueError, match="No site"):
            retract_pending_site(99)
