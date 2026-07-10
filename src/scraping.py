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
import re
import unicodedata

import anthropic

from src.config import get_anthropic_key, EXTRACTION_MODEL
from src.description_gen import (
    _extract_json,
    _extract_text_from_response,
    _strip_citation_tags,
    _web_search_tools,
)
from src.models import DiscoveredCandidate, ScrapedSpot
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
        max_tokens=16000,
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


# --- Discovery: find candidate spots we don't track yet ---

DISCOVER_SYSTEM_PROMPT = """\
You are a scout for CartoTaco, a guide to Mexican food in Tucson, AZ.

Your job: find taco spots currently operating in Tucson that are MISSING from the
list we already track — taquerias, taco trucks, stands, and Sonoran/Mexican
restaurants with a real taco menu.

You have access to a web search tool. Search local coverage ("new taco spots
Tucson", "best taquerias Tucson", neighborhood roundups, recent openings) and
cross-check against the provided list.

Rules:
- Only include spots you can confirm exist from a current source. Skip anything
  that appears closed.
- Skip national chains and fast-food (no Taco Bell, Chipotle, etc.). Local
  mini-chains with a few Tucson locations are fine.
- Do NOT include spots from the already-tracked list, including obvious
  name variants of them ("El Ejemplo" vs "Tacos El Ejemplo" is the same spot).
- Prefer: recently opened spots, well-reviewed neighborhood spots, and trucks or
  stands with a persistent location.
- For each candidate give the best source URL you found (its own site/social if
  possible, otherwise the article/listing that mentions it).

Return ONLY a JSON object (no markdown fences, no explanation):

{
  "candidates": [
    {
      "name": "spot name",
      "area": "neighborhood or street, e.g. 'South 12th Ave' or 'Menlo Park'",
      "url": "best source URL",
      "note": "one line on why it's promising"
    }
  ]
}
"""


def _normalize_name(name: str) -> str:
    """Normalize a spot name for duplicate comparison: lowercase, strip accents
    and punctuation, collapse whitespace."""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return re.sub(r"\s+", " ", name).strip()


def mark_known_candidates(
    candidates: list[DiscoveredCandidate], known_names: list[str]
) -> list[DiscoveredCandidate]:
    """Flag candidates whose name matches an already-tracked spot.

    Match = normalized equality, or containment either way for names long
    enough that containment is meaningful ("El Ejemplo" ⊂ "Tacos El Ejemplo").
    """
    normalized_known = [_normalize_name(k) for k in known_names if k]
    for c in candidates:
        n = _normalize_name(c.name)
        c.already_known = any(
            n == k or (len(n) > 4 and len(k) > 4 and (n in k or k in n))
            for k in normalized_known
        )
    return candidates


def _known_spot_names() -> list[str]:
    """All names we already track: production sites + non-rejected staging rows."""
    client = get_client()
    prod = client.table("sites").select("name").execute().data
    staging = (
        client.table("staging_extractions")
        .select("restaurant_name")
        .neq("status", "rejected")
        .execute()
        .data
    )
    names = {r["name"] for r in prod if r.get("name")}
    names |= {r["restaurant_name"] for r in staging if r.get("restaurant_name")}
    return sorted(names)


def discover_candidates(limit: int = 20, focus: str = "") -> tuple[list[DiscoveredCandidate], dict]:
    """One city-wide search pass: candidate spots we don't track yet.

    Args:
        limit: Max candidates to return.
        focus: Optional steer, e.g. "south side", "birria", "food trucks".

    Returns:
        (candidates flagged via mark_known_candidates, raw JSON dict)

    The already-tracked list goes into the prompt so Claude skips known spots,
    and the same diff runs again client-side (mark_known_candidates) as a
    belt-and-suspenders check — search output isn't trusted to dedupe.
    """
    known_names = _known_spot_names()

    user_message = f"Find up to {limit} taco spots in Tucson, AZ that we don't track yet."
    if focus.strip():
        user_message += f"\nFocus on: {focus.strip()}"
    user_message += "\n\nAlready tracked (do not include these):\n" + "\n".join(
        f"- {n}" for n in known_names
    )

    client = anthropic.Anthropic(api_key=get_anthropic_key())
    response = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=16000,
        system=DISCOVER_SYSTEM_PROMPT,
        tools=_web_search_tools(),
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = _extract_text_from_response(response)
    raw_dict = _clean_strings(_extract_json(raw_text))

    candidates = [
        DiscoveredCandidate.model_validate(c) for c in raw_dict.get("candidates", [])[:limit]
    ]
    return mark_known_candidates(candidates, known_names), raw_dict


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
