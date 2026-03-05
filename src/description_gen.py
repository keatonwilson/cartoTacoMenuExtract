"""AI description generation and web enrichment using Claude + web search."""

import json
import re
from dataclasses import dataclass, field

import anthropic

from src.config import get_anthropic_key, get_supabase_url, get_supabase_key, EXTRACTION_MODEL
from src.models import ExtractedEstablishment, SiteData, HoursData

SYSTEM_PROMPT = """\
You are a writer for CartoTaco, a guide to Mexican food in Tucson, AZ.
Your voice is casual, food-centric, and enthusiastic but not over-the-top.
Think friendly local food blogger who really knows their tacos.

You have access to a web search tool. Before writing, search for the restaurant to find
reviews, articles, blog posts, and local food coverage. Use what you find to add color,
vibe, and specific details that go beyond just listing menu items. Look for things like:
- What locals say about it (Yelp, Google, food blogs)
- Any press coverage or "best of" mentions
- History or backstory of the spot
- Atmosphere, neighborhood feel, standout experiences

After researching, write two descriptions:

**Short description** (10–150 characters):
- Punchy one-liner highlighting what makes this spot special
- Lead with the most interesting/signature items or reputation
- Keep it tight — this is a preview blurb

**Long description** (up to 500 characters):
- More detail about the vibe, standout dishes, and what makes it worth a visit
- Weave in insights from reviews and articles — what people actually love about it
- Reference Tucson/Sonoran context when relevant
- Mention notable proteins, tortilla style, or salsa game if noteworthy

After searching and gathering context, return ONLY a JSON object with two keys: \
"short" and "long". No markdown fences, no explanation — just the JSON.
"""


def _build_data_summary(ext: ExtractedEstablishment) -> str:
    """Build a plain-text summary of extracted data for the prompt."""
    parts = [f"Restaurant: {ext.restaurant_name}"]

    if ext.site.type:
        parts.append(f"Type: {ext.site.type}")
    if ext.site.address:
        parts.append(f"Address: {ext.site.address}")
    if ext.description.region:
        parts.append(f"Region: {ext.description.region}")

    # Menu items served
    menu_items = []
    for item in [
        "burro", "taco", "torta", "dog", "plate", "cocktail", "gordita",
        "huarache", "cemita", "flauta", "chalupa", "molote", "tostada",
        "enchilada", "tamale", "sope", "caldo",
    ]:
        if getattr(ext.menu, f"{item}_yes", False):
            menu_items.append(item)
    if menu_items:
        parts.append(f"Serves: {', '.join(menu_items)}")

    if ext.menu.flour_corn:
        parts.append(f"Tortilla: {ext.menu.flour_corn}")
    if ext.menu.handmade_tortilla:
        parts.append("Handmade tortillas")
    if ext.menu.specialty_items:
        parts.append(f"Specialty items: {', '.join(ext.menu.specialty_items)}")

    # Proteins
    proteins = []
    for prot in ["chicken", "beef", "pork", "fish", "veg"]:
        if getattr(ext.protein, f"{prot}_yes", False):
            styles = []
            for i in range(1, 4):
                s = getattr(ext.protein, f"{prot}_style_{i}", "")
                if s:
                    styles.append(s)
            label = prot + (f" ({', '.join(styles)})" if styles else "")
            proteins.append(label)
    if proteins:
        parts.append(f"Proteins: {', '.join(proteins)}")

    # Salsas
    salsa_info = []
    if ext.salsa.total_num:
        salsa_info.append(f"{ext.salsa.total_num} salsas")
    for s in ["verde", "rojo", "pico", "pickles", "chipotle", "avo", "molcajete", "macha"]:
        if getattr(ext.salsa, f"{s}_yes", False):
            salsa_info.append(s)
    if salsa_info:
        parts.append(f"Salsas: {', '.join(salsa_info)}")

    return "\n".join(parts)


def _fetch_example_descriptions() -> str:
    """Fetch a few existing descriptions from Supabase to use as style examples."""
    try:
        from supabase import create_client

        client = create_client(get_supabase_url(), get_supabase_key())
        resp = (
            client.table("descriptions")
            .select("short_descrip, long_descrip")
            .not_.is_("short_descrip", "null")
            .not_.is_("long_descrip", "null")
            .limit(5)
            .execute()
        )
        if not resp.data:
            return ""

        examples = []
        for row in resp.data:
            short = row.get("short_descrip", "")
            long_ = row.get("long_descrip", "")
            if short or long_:
                examples.append(f"Short: {short}\nLong: {long_}")
        if examples:
            return "\n\nHere are examples of existing CartoTaco descriptions for style reference:\n\n" + "\n---\n".join(examples)
    except Exception:
        pass
    return ""


def _extract_text_from_response(response: anthropic.types.Message) -> str:
    """Extract the final text content from a response that may include tool use blocks."""
    text_parts = []
    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
    return "\n".join(text_parts).strip()


def _strip_citation_tags(text: str) -> str:
    """Remove web search citation tags like <citeindex>, </citeindex>, etc."""
    return re.sub(r"</?cite[^>]*>", "", text).strip()


def _extract_json(text: str) -> dict:
    """Extract the first complete JSON object from text, handling nested braces."""
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON found in response: {text[:200]}")

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if escape:
            escape = False
            continue
        if c == "\\":
            escape = True
            continue
        if c == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start:i + 1])

    raise ValueError(f"Unterminated JSON object in response: {text[:200]}")


def _web_search_tools() -> list[dict]:
    """Return the web_search tool config shared by description gen and enrichment."""
    return [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 5,
        "user_location": {
            "type": "approximate",
            "city": "Tucson",
            "region": "Arizona",
            "country": "US",
            "timezone": "America/Phoenix",
        },
    }]


def generate_descriptions(ext: ExtractedEstablishment) -> tuple[str, str]:
    """Generate short and long descriptions using web search + extracted data.

    Uses Claude's web_search tool to find reviews, articles, and local coverage
    about the restaurant, then generates descriptions informed by both the
    extracted menu data and real-world context.

    Returns:
        (short_description, long_description)
    """
    data_summary = _build_data_summary(ext)
    examples = _fetch_example_descriptions()

    user_message = (
        f"Here is the extracted menu data for this restaurant:\n\n{data_summary}"
        f"{examples}\n\n"
        f"Search the web for reviews, articles, and local coverage about "
        f"\"{ext.restaurant_name}\" in Tucson, AZ. Then write the short and long descriptions."
    )

    client = anthropic.Anthropic(api_key=get_anthropic_key())
    response = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=_web_search_tools(),
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = _extract_text_from_response(response)
    result = _extract_json(raw_text)
    return _strip_citation_tags(result["short"]), _strip_citation_tags(result["long"])


# --- Web Enrichment ---

ENRICH_SYSTEM_PROMPT = """\
You are a data research assistant for CartoTaco, a guide to Mexican food in Tucson, AZ.

You have access to a web search tool. Search for the restaurant to find its business \
details: address, phone number, website, social media accounts, and operating hours.

Search Google, Yelp, the restaurant's own website, Facebook, and Instagram to find \
this information. Try multiple searches if needed.

Return ONLY a JSON object with the following structure (omit keys you can't find — \
do NOT guess or fabricate):

{
  "address": "full street address",
  "phone": "(520) 123-4567",
  "website": "https://example.com",
  "instagram": "handle_without_at",
  "facebook": "https://facebook.com/page or page name",
  "hours": {
    "mon_start": "HH:MM", "mon_end": "HH:MM",
    "tue_start": "HH:MM", "tue_end": "HH:MM",
    "wed_start": "HH:MM", "wed_end": "HH:MM",
    "thu_start": "HH:MM", "thu_end": "HH:MM",
    "fri_start": "HH:MM", "fri_end": "HH:MM",
    "sat_start": "HH:MM", "sat_end": "HH:MM",
    "sun_start": "HH:MM", "sun_end": "HH:MM"
  }
}

Use 24-hour format for all times (e.g. "08:00", "21:00").
For phone numbers, use format: (520) 123-4567.
For Instagram, just the handle without the @ symbol.
If the restaurant is closed on a day, omit that day's hours entirely.
No markdown fences, no explanation — just the JSON.
"""


@dataclass
class EnrichmentResult:
    """Fields discovered via web search. Only non-empty values were found."""
    address: str = ""
    phone: str = ""
    website: str = ""
    instagram: str = ""
    facebook: str = ""
    hours: dict[str, str] = field(default_factory=dict)


def enrich_from_web(restaurant_name: str, current_address: str = "") -> EnrichmentResult:
    """Search the web for a restaurant's business details.

    Args:
        restaurant_name: Name of the restaurant to search for.
        current_address: Optional current address for disambiguation.

    Returns:
        EnrichmentResult with any fields found online.
    """
    location_hint = f" near {current_address}" if current_address else " in Tucson, AZ"
    user_message = (
        f"Find business details for \"{restaurant_name}\"{location_hint}.\n"
        f"I need: address, phone, website, Instagram, Facebook, and operating hours."
    )

    client = anthropic.Anthropic(api_key=get_anthropic_key())
    response = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=4096,
        system=ENRICH_SYSTEM_PROMPT,
        tools=_web_search_tools(),
        messages=[{"role": "user", "content": user_message}],
    )

    raw_text = _extract_text_from_response(response)
    data = _extract_json(raw_text)

    # Clean citation tags from all string values
    result = EnrichmentResult(
        address=_strip_citation_tags(data.get("address", "")),
        phone=_strip_citation_tags(data.get("phone", "")),
        website=_strip_citation_tags(data.get("website", "")),
        instagram=_strip_citation_tags(data.get("instagram", "")).lstrip("@"),
        facebook=_strip_citation_tags(data.get("facebook", "")),
    )

    # Parse hours, normalizing through HoursData validator
    raw_hours = data.get("hours", {})
    if raw_hours:
        cleaned = {k: _strip_citation_tags(v) for k, v in raw_hours.items() if v}
        result.hours = cleaned

    return result
