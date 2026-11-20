"""Tests for the staging → prod atlas copy (no network)."""

from scripts import promote_atlas as pa

SRC = pa.public_prefix("https://staging.supabase.co/")
DST = pa.public_prefix("https://prod.supabase.co")

STAGING_SPECS = [{"id": 7, "name": "Salsa de Arbol"}]
PROD_SPECS = [{"id": 3, "name": "Salsa de Arbol"}]
STAGING_STYLES = [
    {"id": 1, "slug": "verde", "status": "published", "spec_id": None, "img_url": None, "tagline": "Tart.", "created_at": "x"},
    {"id": 2, "slug": "arbol", "status": "published", "spec_id": 7, "img_url": SRC + "styles/a.jpg", "tagline": "Hot."},
    {"id": 3, "slug": "cilantro-crema", "status": "published", "spec_id": None, "img_url": None, "tagline": "New."},
    {"id": 4, "slug": "mole-negro", "status": "draft", "spec_id": None, "img_url": None, "tagline": "Dark."},
    {"id": 5, "slug": "nueva", "status": "draft", "spec_id": None, "img_url": None, "tagline": "Draft."},
]
PROD_STYLES = [
    {"id": 11, "slug": "verde", "status": "published", "spec_id": None, "img_url": None, "tagline": "Tart."},
    {"id": 12, "slug": "arbol", "status": "published", "spec_id": 3, "img_url": None, "tagline": "Hot."},
    {"id": 14, "slug": "mole-negro", "status": "published", "spec_id": None, "img_url": None, "tagline": "Dark."},
]
LINK = {"heat": None, "house_name": None, "note": None, "photo_url": None, "palette": None, "observed_at": None}


def test_rewrite_url_moves_only_staging_bucket_urls():
    assert pa.rewrite_url(SRC + "sightings/6/a.jpg", SRC, DST) == "https://prod.supabase.co/storage/v1/object/public/salsas/sightings/6/a.jpg"
    assert pa.rewrite_url("https://example.org/photo.jpg", SRC, DST) == "https://example.org/photo.jpg"
    assert pa.rewrite_url(None, SRC, DST) is None


def test_walk_descends_into_subfolders():
    tree = {
        "sightings": [{"name": "6", "id": None}, {"name": "9", "id": None}],
        "sightings/6": [{"name": "a.jpg", "id": "u1", "metadata": {"size": 10, "mimetype": "image/jpeg"}}],
        "sightings/9": [{"name": "b.jpg", "id": "u2", "metadata": {"size": 5, "mimetype": "image/jpeg"}}],
    }
    assert pa.walk(lambda f: tree.get(f, []), "sightings") == [
        ("sightings/6/a.jpg", 10, "image/jpeg"), ("sightings/9/b.jpg", 5, "image/jpeg"),
    ]


def test_plan_styles_upserts_by_slug_with_prod_spec_id_and_host():
    rows, inserts, updates = pa.plan_styles(STAGING_STYLES, PROD_STYLES, STAGING_SPECS, PROD_SPECS, SRC, DST)
    by_slug = {r["slug"]: r for r in rows}
    assert all("id" not in r and "created_at" not in r for r in rows)
    assert by_slug["arbol"]["spec_id"] == 3 and by_slug["arbol"]["img_url"] == DST + "styles/a.jpg"
    assert inserts == ["cilantro-crema"]
    # an unchanged style isn't sent; a style drafted on staging is drafted on prod; a new draft isn't copied
    assert "verde" not in by_slug and updates == {"arbol": ["img_url"], "mole-negro": ["status"]}
    assert "nueva" not in by_slug


def test_plan_links_maps_style_ids_through_slug_and_skips():
    links = [
        {**LINK, "est_id": 6, "style_id": 1, "synced": True},  # already on prod, unchanged
        {**LINK, "est_id": 6, "style_id": 2, "synced": False, "photo_url": SRC + "sightings/6/a.jpg", "observed_at": "2026-10-03"},
        {**LINK, "est_id": 6, "style_id": 3, "synced": False, "observed_at": "2026-10-03"},  # new style
        {**LINK, "est_id": 6, "style_id": 4, "synced": True},  # draft style
        {**LINK, "est_id": 8, "style_id": 1, "synced": True},  # closed spot
    ]
    prod_links = [{**LINK, "est_id": 6, "style_id": 11, "synced": True}, {**LINK, "est_id": 6, "style_id": 12, "synced": True}]
    prod_ids = {"verde": 11, "arbol": 12, "mole-negro": 14}

    rows, inserts, updates, skipped = pa.plan_links(links, STAGING_STYLES, prod_ids, {6}, prod_links, SRC, DST)
    assert [r["style_id"] for r in updates] == [12] and updates[0]["photo_url"] == DST + "sightings/6/a.jpg"
    assert updates[0]["synced"] is False
    assert [r["style_id"] for r in inserts] == [None]  # dry run: cilantro-crema has no prod id yet
    assert skipped == {"draft style": 1, "spot not live on prod": 1}

    rows, inserts, _, _ = pa.plan_links(links, STAGING_STYLES, {**prod_ids, "cilantro-crema": 15}, {6}, prod_links, SRC, DST)
    assert [r["style_id"] for r in inserts] == [15]


def test_live_spots_are_vetted_and_open():
    sites = [
        {"est_id": 1, "vetting_status": "vetted", "closed_at": None},
        {"est_id": 2, "vetting_status": "pending", "closed_at": None},
        {"est_id": 3, "vetting_status": "vetted", "closed_at": "2026-05-01"},
        {"est_id": 4, "vetting_status": None, "closed_at": None},  # predates the column's default
    ]
    assert pa.live_est_ids(sites) == {1, 4}


def test_preflight_passes_and_names_each_problem():
    sites = [{"est_id": 6}]
    objects = [("styles/a.jpg", 10, "image/jpeg")]
    sighting = {**LINK, "est_id": 6, "style_id": 2, "synced": False}
    assert pa.preflight(STAGING_STYLES, [sighting], STAGING_SPECS, PROD_SPECS, sites, objects, SRC) == []

    problems = pa.preflight(
        STAGING_STYLES,
        [{**sighting, "est_id": 99}, {**LINK, "est_id": 98, "style_id": 1, "synced": True},  # synced, unsighted: skipped later, fine
         {**sighting, "photo_url": SRC + "sightings/6/gone.jpg"}],
        STAGING_SPECS, [], sites, objects, SRC,
    )
    assert len(problems) == 3
    assert "spot 99" in problems[0] and "salsa_spec 7" in problems[1] and "gone.jpg" in problems[2]


def test_preflight_catches_schema_drift_and_foreign_hosts():
    sites = [{"est_id": 6}]
    elsewhere = {**LINK, "est_id": 6, "style_id": 2, "synced": False, "photo_url": "http://other.supabase.co/storage/v1/object/public/salsas/x.jpg"}
    problems = pa.preflight(STAGING_STYLES, [elsewhere], STAGING_SPECS, PROD_SPECS, sites, [], SRC,
                            prod_styles=[{"id": 1}], prod_links=[dict(elsewhere)])
    assert "salsa_styles: prod has no column" in problems[0] and "other than staging" in problems[-1]


def test_specs_match_by_normalized_name():
    assert pa.resolve_spec_id(7, STAGING_SPECS, [{"id": 4, "name": "  salsa de  ARBOL"}]) == 4


def test_expected_counts_merge_prod_links_with_copied_ones():
    style_rows, _, _ = pa.plan_styles(STAGING_STYLES, PROD_STYLES, STAGING_SPECS, PROD_SPECS, SRC, DST)
    prod_links = [{**LINK, "est_id": 6, "style_id": 11, "synced": True}, {**LINK, "est_id": 7, "style_id": 14, "synced": True}]
    staging_links = [
        {**LINK, "est_id": 6, "style_id": 1, "synced": True, "photo_url": "x"},
        {**LINK, "est_id": 6, "style_id": 3, "synced": False, "observed_at": "2026-10-03"},
    ]
    counts = pa.expected_counts(style_rows, PROD_STYLES, prod_links, STAGING_STYLES, staging_links, {6, 7})
    assert counts["verde"] == ("published", 1, 1, 0, 1)
    assert counts["cilantro-crema"] == ("published", 1, 0, 1, 1)
    assert counts["mole-negro"] == ("draft", 1, 1, 0, 0)
    assert "nueva" not in counts


class FakeDB:
    """Just enough of a supabase client for main(): tables, upserts and a bucket."""

    def __init__(self, tables, objects=None):
        self.tables, self.objects, self.writes = tables, objects or {}, []

    def table(self, name):
        db = self

        class Query:
            def select(self, *_): return self
            def limit(self, *_): return self
            def upsert(self, rows, on_conflict):
                db.writes.append((name, on_conflict, rows))
                if name == "salsa_styles":  # the database hands new styles an id
                    known = {s["slug"] for s in db.tables[name]}
                    db.tables[name] += [{**r, "id": 100 + i} for i, r in enumerate(rows) if r["slug"] not in known]
                return self
            def execute(self): return type("R", (), {"data": db.tables[name]})()

        return Query()

    @property
    def storage(self):
        db = self

        class Bucket:
            def list(self, folder, _opts):
                names = {p[len(folder) + 1:].split("/")[0] for p in db.objects if p.startswith(folder + "/")}
                return [{"name": n, "id": None} if f"{folder}/{n}" not in db.objects
                        else {"name": n, "id": n, "metadata": {"size": len(db.objects[f"{folder}/{n}"]), "mimetype": "image/jpeg"}}
                        for n in sorted(names)]
            def download(self, path): return db.objects[path]
            def upload(self, path, data, opts): db.writes.append(("storage", path, data))

        return type("S", (), {"from_": lambda self, _: Bucket(), "get_bucket": lambda self, _: None})()


def test_apply_copies_photos_then_styles_then_links(monkeypatch, capsys):
    staging = FakeDB({
        "salsa_styles": STAGING_STYLES, "salsa_spec": STAGING_SPECS,
        "site_salsas": [{**LINK, "est_id": 6, "style_id": 3, "synced": False, "photo_url": SRC + "sightings/6/a.jpg"}],
    }, {"sightings/6/a.jpg": b"jpeg", "styles/a.jpg": b"img"})
    prod = FakeDB({
        "salsa_styles": [dict(s) for s in PROD_STYLES], "salsa_spec": PROD_SPECS, "site_salsas": [],
        "sites": [{"est_id": 6, "vetting_status": "vetted", "closed_at": None}],
    })
    monkeypatch.setenv("SUPABASE_URL", "https://prod.supabase.co")
    monkeypatch.setenv("SUPABASE_STAGING_URL", "https://staging.supabase.co/")
    monkeypatch.setattr(pa, "_client", lambda url_var, _: prod if url_var == "SUPABASE_URL" else staging)

    pa.main([])
    assert prod.writes == [] and "Dry run" in capsys.readouterr().out

    pa.main(["--apply"])
    kinds = [w[0] for w in prod.writes]
    assert kinds == ["storage", "storage", "salsa_styles", "site_salsas"]
    (_, conflict, links) = prod.writes[-1]
    assert conflict == "est_id,style_id"
    new_id = next(s["id"] for s in prod.tables["salsa_styles"] if s["slug"] == "cilantro-crema")
    assert links == [{**LINK, "est_id": 6, "style_id": new_id, "synced": False, "photo_url": DST + "sightings/6/a.jpg"}]


def test_refuses_to_promote_staging_onto_itself(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://staging.supabase.co")
    monkeypatch.setenv("SUPABASE_STAGING_URL", "https://staging.supabase.co/")
    try:
        pa.main([])
    except SystemExit as e:
        assert "points at staging" in str(e)
    else:
        raise AssertionError("expected SystemExit")
