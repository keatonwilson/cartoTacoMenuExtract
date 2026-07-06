"""Web scouting for unvetted (pending) spots.

Researches a candidate taco spot with Claude's web_search tool and returns a
thin ScrapedSpot (site/hours/description only — menu data enters exclusively
through the vetted photo pipeline). Also provides duplicate detection against
production sites and the staging table.

Compliance: research goes through Claude's web_search tool (same pattern as
description_gen.enrich_from_web) — the app itself fetches nothing, honors no
robots.txt of its own, and never copies review text. Descriptions are written
original from gathered facts.
"""

import json
import math

import anthropic

from src.config import get_anthropic_key, EXTRACTION_MODEL
from src.description_gen import (
    _extract_json,
    _extract_text_from_response,
    _strip_citation_tags,
    _web_search_tools,
)
from src.models import ScrapedSpot
from src.supabase_client import get_client

# Two spots within this distance are treated as probable duplicates
DUPLICATE_RADIUS_M = 150

SCOUT_SYSTEM_PROMPT = """\
You are a research scout for CartoTaco, a guide to Mexican food in Tucson, AZ.

Your job: gather PRELIMINARY business details for a taco spot we have NOT visited
yet. This data appears publicly flagged as "pending vetting", so accuracy matters
more than completeness — include only facts you can verify from your searches, and
omit anything you cannot confirm. Never guess or fabricate.

You have access to a web search tool. Search the spot's own website, its Instagram
or Facebook pages, and local coverage. Do NOT rely on a single source for hours.

Collect:
- Business details: name, type ("Brick and Mortar", "Stand", or "Truck"), full
  street address, phone ((520) 123-4567 format), website, Instagram handle
  (no @), Facebook page.
- Operating hours in 24-hour HH:MM format. If a day is closed or unknown, omit it.
  For trucks/stands with roaming locations, put the typical spot in days_loc_1.
- A short_descrip (10-150 chars) and long_descrip (up to 400 chars): write these
  YOURSELF from the facts you found — original text, never copied from reviews.
  Keep the tone factual and lightly enthusiastic; this spot is unvetted, so do not
  invent opinions about food quality we haven't tasted.
- confidence: for each of "site", "hours", "description", rate "high" (stated on
  an official/current source), "medium" (secondary source), or "low" (thin or
  conflicting evidence).
- evidence_urls: the URLs you actually drew facts from, most authoritative first.

Return ONLY a JSON object matching this schema (no markdown fences, no explanation):

"""


def scout_spot(name: str, hint_urls: list[str] | None = None) -> tuple[ScrapedSpot, dict]:
    """Research a candidate spot on the web and return structured preliminary data.

    Args:
        name: The spot's name (e.g. "Tacos El Ejemplo").
        hint_urls: Optional URLs the admin already found (own site, Instagram, …)
            to steer the search.

    Returns:
        (validated ScrapedSpot, raw JSON dict)
    """
    schema_json = json.dumps(ScrapedSpot.model_json_schema(), indent=2)

    user_message = f'Scout the taco spot "{name}" in Tucson, AZ.'
    if hint_urls:
        user_message += "\nStart with these known sources:\n" + "\n".join(
            f"- {u}" for u in hint_urls
        )

    client = anthropic.Anthropic(api_key=get_anthropic_key())
    response = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=4096,
        system=SCOUT_SYSTEM_PROMPT + schema_json,
        tools=_web_search_tools(),
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = _extract_text_from_response(response)
    raw_dict = _extract_json(raw_text)
    raw_dict = _clean_strings(raw_dict)
    validated = ScrapedSpot.model_validate(raw_dict)

    # Keep any admin-supplied hints in the evidence list
    for url in hint_urls or []:
        if url not in validated.evidence_urls:
            validated.evidence_urls.append(url)

    return validated, raw_dict


def _clean_strings(value):
    """Recursively strip web-search citation tags from all string values."""
    if isinstance(value, str):
        return _strip_citation_tags(value)
    if isinstance(value, list):
        return [_clean_strings(v) for v in value]
    if isinstance(value, dict):
        return {k: _clean_strings(v) for k, v in value.items()}
    return value


# --- Duplicate detection ---

def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance between two points in meters."""
    r = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def find_duplicates(name: str, lat: float | None = None, lon: float | None = None) -> dict:
    """Check a candidate spot against production and staging before staging it.

    Returns {'production': [...], 'staging': [...]} where production entries are
    matched by name substring or by proximity (within DUPLICATE_RADIUS_M), and
    staging entries are non-rejected rows with a similar restaurant_name.
    """
    client = get_client()

    production: dict[int, dict] = {}
    if name.strip():
        by_name = (
            client.table("sites")
            .select("est_id, name, address, vetting_status")
            .ilike("name", f"%{name.strip()}%")
            .execute()
            .data
        )
        for m in by_name:
            production[m["est_id"]] = {**m, "match": "name"}

    if lat is not None and lon is not None:
        all_sites = (
            client.table("sites")
            .select("est_id, name, address, vetting_status, lat_1, lon_1")
            .execute()
            .data
        )
        for s in all_sites:
            if s.get("lat_1") is None or s.get("lon_1") is None:
                continue
            dist = _haversine_m(lat, lon, s["lat_1"], s["lon_1"])
            if dist <= DUPLICATE_RADIUS_M and s["est_id"] not in production:
                production[s["est_id"]] = {**s, "match": f"within {round(dist)} m"}

    staging = []
    if name.strip():
        staging = (
            client.table("staging_extractions")
            .select("id, restaurant_name, status, pipeline, created_at")
            .ilike("restaurant_name", f"%{name.strip()}%")
            .neq("status", "rejected")
            .execute()
            .data
        )

    return {"production": list(production.values()), "staging": staging}
