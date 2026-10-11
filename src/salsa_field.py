"""Salsa field notes: turn a photo taken at a spot into a sighting for the Salsa Atlas.

A sighting is "this spot serves this salsa": the photo, the colours sampled from
it, heat, the house name and a note. It lives on cartoTaco's `site_salsas`
table (migration 036). New styles are created as drafts on `salsa_styles` and
stay off the public site until published.

The image functions are pure (Pillow only) and tested; the Supabase and Claude
calls are thin wrappers around them.
"""

import base64
import io
import json
import math
import re
import unicodedata
import uuid
from datetime import datetime
from statistics import median

import anthropic
from PIL import Image, ImageDraw, ImageOps

from src.config import EXTRACTION_MODEL, get_anthropic_key
from src.supabase_client import get_client

try:  # iPhone photos are HEIC unless exported; optional so the app runs without it
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

BUCKET = "salsas"
PHOTO_MAX_DIM = 1600
PALETTE_SIZE = 4

# Keep in sync with the CHECK constraints in cartoTaco migration 036
FAMILIES = ["fresca", "cooked", "dried-chile", "oil", "creamy", "pickled", "mole"]
REGIONS = ["north", "west", "central", "south", "everywhere"]
FLAVOUR_AXES = ["smoke", "acid", "sweet", "chunk", "rich"]

# sRGB value of a standard 18% grey card
GREY_CARD_18 = 119

# A box is (x0, y0, x1, y1) as fractions of the image, so it survives resizing
Box = tuple[float, float, float, float]
DEFAULT_SALSA_BOX: Box = (0.3, 0.3, 0.7, 0.7)


# ── Photo ────────────────────────────────────────────────────────────────────

def load_photo(image_bytes: bytes) -> Image.Image:
    """Open a photo upright (EXIF rotation applied) as RGB."""
    return ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")


def _to_degrees(dms, ref: str) -> float:
    degrees = float(dms[0]) + float(dms[1]) / 60 + float(dms[2]) / 3600
    return -degrees if ref in ("S", "W") else degrees


def read_photo_meta(image_bytes: bytes) -> dict:
    """When and where the photo was taken, from EXIF. Missing values are None."""
    meta = {"taken_on": None, "lat": None, "lon": None}
    try:
        exif = Image.open(io.BytesIO(image_bytes)).getexif()
    except Exception:
        return meta

    taken = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
    if taken:
        try:
            meta["taken_on"] = datetime.strptime(str(taken)[:10], "%Y:%m:%d").date()
        except ValueError:
            pass

    gps = exif.get_ifd(0x8825)
    try:
        if gps.get(2) and gps.get(4):
            lat = _to_degrees(gps[2], gps.get(1, "N"))
            lon = _to_degrees(gps[4], gps.get(3, "E"))
            # A phone with no fix can write 0/0 rationals, which come out as NaN
            if math.isfinite(lat) and math.isfinite(lon) and abs(lat) <= 90 and abs(lon) <= 180:
                meta["lat"], meta["lon"] = lat, lon
    except (TypeError, ValueError, ZeroDivisionError, IndexError):
        pass
    return meta


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin(math.radians(lat2 - lat1) / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def nearest_sites(sites: list[dict], lat: float, lon: float) -> list[dict]:
    """Every site, nearest first, each with `distance_m` added.

    Sites without coordinates can't be ranked but must stay selectable, so they
    follow the ranked ones with `distance_m` None.
    """
    has_coords = lambda s: s.get("lat_1") is not None and s.get("lon_1") is not None
    ranked = sorted(
        ({**s, "distance_m": haversine_m(lat, lon, s["lat_1"], s["lon_1"])} for s in sites if has_coords(s)),
        key=lambda s: s["distance_m"],
    )
    return ranked + [{**s, "distance_m": None} for s in sites if not has_coords(s)]


# ── Colour ───────────────────────────────────────────────────────────────────

def _crop(img: Image.Image, box: Box) -> Image.Image:
    w, h = img.size
    x0, y0, x1, y1 = box
    left, top = int(min(x0, x1) * w), int(min(y0, y1) * h)
    # at least one pixel, so a degenerate box can't produce an empty crop
    right, bottom = max(left + 1, int(max(x0, x1) * w)), max(top + 1, int(max(y0, y1) * h))
    return img.crop((left, top, right, bottom))


def _to_linear(v: float) -> float:
    """sRGB byte (0–255) → linear light (0–1)."""
    c = v / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _to_srgb(x: float) -> int:
    """Linear light (0–1) → sRGB byte, clipped."""
    x = min(1.0, max(0.0, x))
    return round(255 * (x * 12.92 if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055))


# Rec. 709 weights: how much each channel contributes to perceived brightness
_LUMA = (0.2126, 0.7152, 0.0722)


def white_balance(img: Image.Image, card_box: Box, card_grey: int | None = None) -> Image.Image:
    """Remove the lighting's colour cast, using a neutral grey/white card in the frame.

    Each channel is scaled, in linear light, so the card comes out neutral
    (equal R, G and B). Without this, the same salsa photographed under warm
    taquería bulbs and in daylight gives very different hex codes.

    `card_grey` is the card's true sRGB value when known (an 18% grey card is
    119). Given it, exposure is corrected too: a dim photo is brightened until
    the card reads that value. Without it the card keeps its own brightness and
    only the cast is removed.
    """
    card = _crop(img, card_box)
    card.thumbnail((64, 64))
    data = card.tobytes()  # RGBRGB…
    means = [sum(_to_linear(v) for v in data[c::3]) / (len(data) // 3) for c in range(3)]
    target = _to_linear(card_grey) if card_grey is not None else sum(m * w for m, w in zip(means, _LUMA))
    bands = [
        band.point([_to_srgb(_to_linear(v) * target / max(mean, 1e-4)) for v in range(256)])
        for band, mean in zip(img.split(), means)
    ]
    return Image.merge("RGB", bands)


def extract_palette(img: Image.Image, box: Box, k: int = PALETTE_SIZE) -> list[str]:
    """The k dominant colours inside `box`, most common first, as lowercase hex."""
    region = _crop(img, box)
    region.thumbnail((200, 200))
    quantized = region.quantize(colors=k, method=Image.Quantize.MEDIANCUT, kmeans=2)
    flat = quantized.getpalette()
    counts = sorted(quantized.getcolors(), reverse=True)  # [(pixel count, palette index)]
    return ["#%02x%02x%02x" % tuple(flat[i * 3 : i * 3 + 3]) for _, i in counts]


def merge_palettes(palettes: list[list[str]]) -> list[str]:
    """One palette from several sightings: the per-channel median at each rank.

    Rank 0 is every sighting's most dominant colour, and so on, so the result
    is the typical dominant colour, the typical second colour, etc. Median, not
    mean: one badly lit photo shouldn't drag the catalog colour.
    """
    palettes = [p for p in palettes if p]
    if not palettes:
        return []
    merged = []
    for rank in range(min(len(p) for p in palettes)):
        rgbs = [tuple(int(p[rank][i : i + 2], 16) for i in (1, 3, 5)) for p in palettes]
        merged.append("#%02x%02x%02x" % tuple(round(median(channel)) for channel in zip(*rgbs)))
    return merged


def annotate(img: Image.Image, salsa_box: Box, card_box: Box | None) -> Image.Image:
    """Copy of the photo with the sampled regions outlined, for the review step."""
    out = img.copy()
    draw = ImageDraw.Draw(out)
    w, h = out.size
    width = max(3, w // 250)
    for box, colour in ((salsa_box, "#ff2d55"), (card_box, "#00c7ff")):
        if box:
            draw.rectangle((box[0] * w, box[1] * h, box[2] * w, box[3] * h), outline=colour, width=width)
    return out


def to_jpeg(img: Image.Image, max_dim: int = PHOTO_MAX_DIM) -> bytes:
    img = img.copy()
    img.thumbnail((max_dim, max_dim))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def slugify(name: str) -> str:
    """'Salsa de Chiltepín' → 'chiltepin' (matches the atlas's URL slugs)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    ascii_name = re.sub(r"^salsa\s+(de\s+)?", "", ascii_name.strip().lower())
    return re.sub(r"[^a-z0-9]+", "-", ascii_name).strip("-")


# ── Claude Vision: find the card and the salsa ───────────────────────────────

LOCATE_PROMPT = """\
This photo was taken at a taquería to record one salsa. It should contain the salsa
(in a bowl, cup, squeeze bottle or on a taco) and may contain a neutral grey or white
photographic reference card.

Return ONLY valid JSON, no markdown:
{
  "salsa_box": [x0, y0, x1, y1],
  "card_box": [x0, y0, x1, y1] or null,
  "style_slug": one of the known slugs below or null,
  "visible_ingredients": ["..."],
  "chunk": 0-10
}

Boxes are fractions of the image width and height (0-1), origin top-left.
- salsa_box: a tight box INSIDE the salsa's surface, excluding the container rim,
  glare, and anything that is not salsa. Smaller and clean beats larger.
- card_box: a box inside the reference card's flat grey/white area, or null if there
  is no card. Do not use a napkin, plate or table as the card.
- style_slug: only if you are reasonably confident; otherwise null.
- visible_ingredients: only what you can actually see (seeds, herbs, charred skin...).
- chunk: 0 = completely smooth, 10 = coarsely chopped.

Known style slugs: """


def _valid_box(value) -> Box | None:
    try:
        box = tuple(float(v) for v in value)
    except (TypeError, ValueError):
        return None
    if len(box) != 4 or not all(math.isfinite(v) for v in box):
        return None
    box = tuple(min(1.0, max(0.0, v)) for v in box)
    return box if box[2] > box[0] and box[3] > box[1] else None


def parse_locate_response(raw_text: str, known_slugs: list[str]) -> dict:
    """Validate Claude's answer. Anything malformed falls back to a safe default."""
    text = re.sub(r"^```[a-z]*\s*|\s*```$", "", raw_text.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    chunk = data.get("chunk")
    ingredients = data.get("visible_ingredients")
    ingredients = ingredients if isinstance(ingredients, list) else []
    is_number = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
    return {
        "salsa_box": _valid_box(data.get("salsa_box")) or DEFAULT_SALSA_BOX,
        "card_box": _valid_box(data.get("card_box")),
        "style_slug": data.get("style_slug") if data.get("style_slug") in known_slugs else None,
        "visible_ingredients": [str(i) for i in ingredients][:12],
        "chunk": min(10, max(0, round(chunk))) if is_number(chunk) else None,
    }


def locate_regions(img: Image.Image, known_slugs: list[str]) -> dict:
    """Ask Claude where the salsa and the reference card are in the photo."""
    b64 = base64.standard_b64encode(to_jpeg(img, 1500)).decode()
    client = anthropic.Anthropic(api_key=get_anthropic_key(), timeout=90.0)
    response = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=16000,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": LOCATE_PROMPT + ", ".join(known_slugs)},
                ],
            }
        ],
    )
    raw_text = next(b.text for b in response.content if b.type == "text")
    return parse_locate_response(raw_text, known_slugs)


# ── Supabase ─────────────────────────────────────────────────────────────────

def list_sites() -> list[dict]:
    return (
        get_client()
        .table("sites")
        .select("est_id, name, lat_1, lon_1, vetting_status, closed_at")
        .order("name")
        .execute()
        .data
    )


def list_styles() -> list[dict]:
    return get_client().table("salsa_styles").select("*").order("name").execute().data


def create_style(data: dict) -> dict:
    return get_client().table("salsa_styles").insert(data).execute().data[0]


def update_style(style_id: int, data: dict) -> dict:
    return get_client().table("salsa_styles").update(data).eq("id", style_id).execute().data[0]


def upload_photo(jpeg_bytes: bytes, folder: str) -> str:
    """Upload to the public `salsas` bucket and return the public URL."""
    client = get_client()
    path = f"{folder}/{uuid.uuid4().hex}.jpg"
    client.storage.from_(BUCKET).upload(path, jpeg_bytes, {"content-type": "image/jpeg"})
    return client.storage.from_(BUCKET).get_public_url(path)


def list_sightings() -> list[dict]:
    """Every spot↔salsa link, with the spot and style names joined in."""
    return (
        get_client()
        .table("site_salsas")
        .select("*, sites(name), salsa_styles(name, slug, status)")
        .order("observed_at", desc=True, nullsfirst=False)
        .execute()
        .data
    )


def save_sighting(est_id: int, style_id: int, fields: dict) -> dict:
    """Create or update the link between a spot and a style.

    `synced` is deliberately never sent: a link the database's sync created
    stays synced (and keeps following the salsa table), and a new link takes
    the column default (hand-made, never removed by the sync).
    """
    row = {"est_id": est_id, "style_id": style_id, **fields}
    row.pop("synced", None)
    return get_client().table("site_salsas").upsert(row, on_conflict="est_id,style_id").execute().data[0]


def remove_sighting(link: dict) -> None:
    """Undo a sighting.

    A hand-made link is deleted. A synced link exists because the spot's salsa
    row says it serves that salsa, and the sync would only recreate it, so the
    field data is cleared and the link is left alone.
    """
    query = get_client().table("site_salsas")
    if link.get("synced"):
        cleared = {"photo_url": None, "palette": None, "observed_at": None, "heat": None, "house_name": None, "note": None}
        query.update(cleared).eq("est_id", link["est_id"]).eq("style_id", link["style_id"]).execute()
    else:
        query.delete().eq("est_id", link["est_id"]).eq("style_id", link["style_id"]).execute()


def draft_style_from_sighting(name: str, family: str, region: str, palette: list[str], chunk: int | None) -> dict:
    """A new catalog entry, hidden from the public site until published.

    Flavour scores start in the middle (texture from the photo if Claude gave
    one); they and the editorial text are filled in on the Catalog tab.
    """
    slug = slugify(name)
    existing = get_client().table("salsa_styles").select("*").eq("slug", slug).execute().data
    if existing:
        # A retry after a failed save, or a name that already exists: use it
        return existing[0]

    scores = {axis: 5 for axis in FLAVOUR_AXES}
    if chunk is not None:
        scores["chunk"] = chunk
    return create_style(
        {
            "slug": slug,
            "name": name.strip(),
            "family": family,
            "region": region,
            "tagline": "",
            "palette": pad_palette(palette),
            "status": "draft",
            **scores,
        }
    )


def pad_palette(palette: list[str]) -> list[str]:
    """salsa_styles.palette must hold 3–5 colours; repeat the last to reach 3."""
    palette = [c.lower() for c in palette][:5]
    return palette + [palette[-1]] * (3 - len(palette)) if palette else palette
