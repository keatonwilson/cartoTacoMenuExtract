"""Tests for salsa field notes (no API or database calls)."""

import io
from datetime import date

from PIL import Image
from streamlit.testing.v1 import AppTest

from src import salsa_field as sf


def _jpeg(img: Image.Image, exif: Image.Exif | None = None) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95, **({"exif": exif} if exif else {}))
    return buf.getvalue()


def _scene(cast=(1.0, 1.0, 1.0)) -> Image.Image:
    """A 'salsa' square and an 18% grey 'card' square on white, lit through a colour cast.

    The cast scales each channel in linear light, the way coloured or dim
    lighting actually does.
    """
    lit = lambda rgb: tuple(sf._to_srgb(sf._to_linear(c) * k) for c, k in zip(rgb, cast))
    img = Image.new("RGB", (400, 400), lit((255, 255, 255)))
    img.paste(lit((170, 140, 90)), (120, 120, 280, 280))  # salsa
    img.paste(lit((119, 119, 119)), (20, 20, 80, 80))  # card
    return img


SALSA = (0.35, 0.35, 0.65, 0.65)
CARD = (0.07, 0.07, 0.18, 0.18)


def _rgb(hex_code: str) -> tuple[int, ...]:
    return tuple(int(hex_code[i : i + 2], 16) for i in (1, 3, 5))


def test_palette_finds_the_dominant_colour():
    palette = sf.extract_palette(_scene(), SALSA, k=3)
    assert all(len(c) == 7 and c == c.lower() for c in palette)
    assert all(abs(a - b) <= 6 for a, b in zip(_rgb(palette[0]), (170, 140, 90)))


def test_white_balance_removes_a_colour_cast():
    """The same salsa under warm, dim light comes out the same once the card is neutralised."""
    truth = (170, 140, 90)
    warm = _scene(cast=(0.8, 0.55, 0.3))
    close = lambda rgb, tolerance: all(abs(a - b) <= tolerance for a, b in zip(rgb, truth))

    uncorrected = _rgb(sf.extract_palette(warm, SALSA, k=3)[0])
    assert not close(uncorrected, 25)  # the lighting really did move the colour

    # Known card value: cast and exposure are both recovered
    exact = sf.white_balance(warm, CARD, card_grey=sf.GREY_CARD_18)
    assert close(_rgb(sf.extract_palette(exact, SALSA, k=3)[0]), 4)
    assert all(abs(c - 119) <= 2 for c in exact.getpixel((50, 50)))

    # Unknown card value: the cast goes (the card is neutral, the salsa's
    # channel ratios are right) but the photo keeps its exposure
    cast_only = sf.white_balance(warm, CARD)
    card = cast_only.getpixel((50, 50))
    assert max(card) - min(card) <= 2
    r, g, b = (sf._to_linear(c) for c in _rgb(sf.extract_palette(cast_only, SALSA, k=3)[0]))
    tr, tg, tb = (sf._to_linear(c) for c in truth)
    assert abs(r / g - tr / tg) < 0.05 and abs(b / g - tb / tg) < 0.05


def test_degenerate_box_still_samples_something():
    assert len(sf.extract_palette(_scene(), (0.5, 0.5, 0.5, 0.5), k=3)) >= 1


def test_merge_palettes_takes_the_median_per_rank():
    merged = sf.merge_palettes(
        [["#b02820", "#401010"], ["#b42a1e", "#421212"], ["#ff00ff", "#000000"], []]  # third is a bad photo
    )
    assert merged == ["#b42820", "#401010"]
    assert sf.merge_palettes([]) == []


def test_pad_palette_meets_the_three_colour_minimum():
    assert sf.pad_palette(["#AA0000"]) == ["#aa0000"] * 3
    assert len(sf.pad_palette(["#111111"] * 7)) == 5
    assert sf.pad_palette([]) == []


def test_read_photo_meta_reads_date_and_gps():
    exif = Image.Exif()
    exif[306] = "2026:10:03 13:45:00"
    gps = exif.get_ifd(0x8825)
    gps[1], gps[2] = "N", (32.0, 13.0, 19.2)
    gps[3], gps[4] = "W", (110.0, 58.0, 12.0)
    meta = sf.read_photo_meta(_jpeg(_scene(), exif))
    assert meta["taken_on"] == date(2026, 10, 3)
    assert abs(meta["lat"] - 32.222) < 0.001
    assert abs(meta["lon"] - -110.97) < 0.001


def test_read_photo_meta_without_exif():
    assert sf.read_photo_meta(_jpeg(_scene())) == {"taken_on": None, "lat": None, "lon": None}
    assert sf.read_photo_meta(b"not an image")["lat"] is None


def test_read_photo_meta_ignores_gps_without_a_fix():
    """0/0 rationals (no GPS fix) become NaN in Pillow; they must not reach the distance maths."""
    from PIL.TiffImagePlugin import IFDRational

    nan = IFDRational(0, 0)
    for lat in ((nan, nan, nan), (132.0, 0.0, 0.0)):  # NaN, and out of range
        exif = Image.Exif()
        gps = exif.get_ifd(0x8825)
        gps[1], gps[2] = "N", lat
        gps[3], gps[4] = "W", (110.0, 58.0, 12.0)
        meta = sf.read_photo_meta(_jpeg(_scene(), exif))
        assert meta["lat"] is None and meta["lon"] is None


def test_nearest_sites_orders_by_distance_and_keeps_unplaced_last():
    sites = [
        {"est_id": 1, "name": "Far", "lat_1": 32.30, "lon_1": -110.90},
        {"est_id": 2, "name": "Near", "lat_1": 32.2221, "lon_1": -110.9701},
        {"est_id": 3, "name": "Unplaced", "lat_1": None, "lon_1": None},
    ]
    ranked = sf.nearest_sites(sites, 32.222, -110.97)
    # unplaced sites can't be ranked but must stay selectable, so they come last
    assert [s["name"] for s in ranked] == ["Near", "Far", "Unplaced"]
    assert ranked[0]["distance_m"] < 50
    assert ranked[2]["distance_m"] is None


def test_slugify_matches_atlas_slugs():
    assert sf.slugify("Salsa de Chiltepín") == "chiltepin"
    assert sf.slugify("Salsa Verde") == "verde"
    assert sf.slugify("Pico de Gallo") == "pico-de-gallo"
    assert sf.slugify("  Mole  Negro ") == "mole-negro"


def test_parse_locate_response():
    good = sf.parse_locate_response(
        '```json\n{"salsa_box": [0.2, 0.3, 0.6, 0.7], "card_box": null, "style_slug": "verde",'
        ' "visible_ingredients": ["seeds"], "chunk": 6.4}\n```',
        ["verde", "rojo"],
    )
    assert good["salsa_box"] == (0.2, 0.3, 0.6, 0.7)
    assert good["card_box"] is None and good["style_slug"] == "verde" and good["chunk"] == 6

    # Unknown slug, inverted box and junk all fall back safely
    bad = sf.parse_locate_response(
        '{"salsa_box": [0.9, 0.1, 0.2, 0.5], "card_box": [0, 0, 2, 2], "style_slug": "ketchup"}', ["verde"]
    )
    assert bad["salsa_box"] == sf.DEFAULT_SALSA_BOX
    assert bad["card_box"] == (0.0, 0.0, 1.0, 1.0)
    assert bad["style_slug"] is None
    assert sf.parse_locate_response("sorry, no", [])["salsa_box"] == sf.DEFAULT_SALSA_BOX

    # Valid JSON of the wrong shape, a bare fence, and non-finite numbers
    for junk in ("[]", "null", '"text"', "```", "```json", '{"chunk": NaN, "salsa_box": [NaN, 0, 1, 1]}',
                 '{"chunk": true, "visible_ingredients": "seeds"}'):
        parsed = sf.parse_locate_response(junk, ["verde"])
        assert parsed["salsa_box"] == sf.DEFAULT_SALSA_BOX, junk
        assert parsed["chunk"] is None and parsed["visible_ingredients"] == [], junk


def test_remove_sighting_clears_synced_links_and_deletes_hand_made_ones(monkeypatch):
    calls = []

    class Query:
        def __init__(self):
            self.op = None

        def update(self, data):
            self.op = ("update", data)
            return self

        def delete(self):
            self.op = ("delete", None)
            return self

        def eq(self, *_):
            return self

        def execute(self):
            calls.append(self.op)

    class Client:
        def table(self, name):
            assert name == "site_salsas"
            return Query()

    monkeypatch.setattr(sf, "get_client", lambda: Client())
    sf.remove_sighting({"est_id": 1, "style_id": 2, "synced": True})
    sf.remove_sighting({"est_id": 1, "style_id": 3, "synced": False})
    assert calls[0][0] == "update" and calls[0][1]["photo_url"] is None
    assert calls[1][0] == "delete"


STYLE = {
    "id": 1, "slug": "verde", "name": "Salsa Verde", "status": "published", "family": "cooked",
    "region": "central", "origin": "Central Mexico", "tagline": "Tart.", "history": None,
    "ingredients": ["Tomatillo"], "heat_min": 2, "heat_max": 6, "palette": ["#7a9a2e", "#a8b545", "#4f6b1f"],
    "smoke": 1, "acid": 8, "sweet": 2, "chunk": 3, "rich": 2, "img_url": None, "img_credit": None,
}
LINK = {
    "est_id": 6, "style_id": 1, "synced": True, "heat": 7, "house_name": None, "note": "bright",
    "photo_url": None, "palette": ["#7a9a2e", "#a8b545", "#4f6b1f", "#d9d27a"], "observed_at": "2026-10-03",
    "sites": {"name": "Tacos Apson"}, "salsa_styles": {"name": "Salsa Verde", "slug": "verde", "status": "published"},
}


def test_page_renders_with_data(monkeypatch):
    """The whole page runs top to bottom against fake data without raising."""
    monkeypatch.setattr(sf, "list_sites", lambda: [{"est_id": 6, "name": "Tacos Apson", "lat_1": 32.2, "lon_1": -110.9}])
    monkeypatch.setattr(sf, "list_styles", lambda: [STYLE, {**STYLE, "id": 2, "slug": "nueva", "name": "Nueva", "status": "draft"}])
    monkeypatch.setattr(sf, "list_sightings", lambda: [LINK])
    at = AppTest.from_file("pages/7_Salsa_Field_Notes.py", default_timeout=30).run()
    assert not at.exception, at.exception
    assert len(at.tabs) == 3


def _run_page(monkeypatch, links, styles=None):
    saves = []
    monkeypatch.setattr(sf, "list_sites", lambda: [{"est_id": 6, "name": "Tacos Apson", "lat_1": 32.2, "lon_1": -110.9}])
    monkeypatch.setattr(sf, "list_styles", lambda: styles or [STYLE])
    monkeypatch.setattr(sf, "list_sightings", lambda: links)
    monkeypatch.setattr(sf, "save_sighting", lambda est, style, fields: saves.append(fields))
    monkeypatch.setattr(sf, "update_style", lambda style_id, data: saves.append(data))
    at = AppTest.from_file("pages/7_Salsa_Field_Notes.py", default_timeout=30).run()
    assert not at.exception, at.exception
    return at, saves


def test_saving_a_sighting_keeps_a_heat_of_zero(monkeypatch):
    """Editing only the note on a link whose heat is 0 must not turn the heat into 5."""
    at, saves = _run_page(monkeypatch, [{**LINK, "heat": 0, "photo_url": "https://example.test/p.jpg"}])
    next(b for b in at.button if b.key == "link_6_1_save").click().run()
    assert saves[0]["heat"] == 0


def test_saving_a_draft_style_leaves_unset_heat_unset(monkeypatch):
    draft = {**STYLE, "status": "draft", "heat_min": None, "heat_max": None}
    at, saves = _run_page(monkeypatch, [], styles=[draft])
    next(b for b in at.button if b.key == "style_1_save").click().run()
    assert saves[0]["heat_min"] is None and saves[0]["heat_max"] is None


def test_draft_style_reuses_an_existing_slug(monkeypatch):
    """A retry after a failed save must not trip the slug UNIQUE constraint."""
    class Query:
        def select(self, *_): return self
        def eq(self, *_): return self
        def insert(self, *_): raise AssertionError("must not insert a duplicate slug")
        def execute(self): return type("R", (), {"data": [STYLE]})()

    monkeypatch.setattr(sf, "get_client", lambda: type("C", (), {"table": lambda self, name: Query()})())
    assert sf.draft_style_from_sighting("Salsa Verde", "cooked", "central", ["#7a9a2e"], None) == STYLE


def test_page_explains_missing_tables(monkeypatch):
    def boom():
        raise RuntimeError("relation salsa_styles does not exist")

    monkeypatch.setattr(sf, "list_sites", lambda: [])
    monkeypatch.setattr(sf, "list_styles", boom)
    at = AppTest.from_file("pages/7_Salsa_Field_Notes.py", default_timeout=30).run()
    assert not at.exception
    assert "036" in at.info[0].value
