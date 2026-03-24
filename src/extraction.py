"""Claude Vision extraction: menu photo → structured data."""

import base64
import io
import json

from PIL import Image
import anthropic

from src.config import get_anthropic_key, EXTRACTION_MODEL, MAX_IMAGE_DIMENSION
from src.models import ExtractedEstablishment


SYSTEM_PROMPT = """\
You are a data extraction assistant for CartoTaco, a guide to Mexican food in Tucson, AZ.

Given photo(s) of a restaurant menu, extract structured information into the JSON schema below.
Only include information you can clearly see or confidently infer from the menu.
Leave fields empty/false if the information is not present.

For protein styles, use common short names like "carne asada", "al pastor", "carnitas",
"pollo asado", "birria", "lengua", "cabeza", "buche", "chorizo", "chicharron", etc.
Categorize each protein under the correct category (chicken, beef, pork, fish, veg).

For hours, use 24-hour format like "08:00", "21:00".

For tortilla type, use "Flour", "Corn", or "Both".

For site type, use "Brick and Mortar", "Stand", or "Truck" if you can determine it.

For each menu item type and protein category that is present (_yes = true), estimate a
_perc value as a proportion (0.0 to 1.0) representing how prominent that item is on the
menu relative to other items. Base this on the number of variations/dishes featuring
that item. The _perc values for menu items should sum to 1.0, and the _perc values for
proteins should separately sum to 1.0. For example, if tacos dominate the menu,
taco_perc might be 0.5-0.7, while a minor item might be 0.05. Leave _perc as null if
the item is not present (_yes = false).

Return ONLY valid JSON matching this schema (no markdown, no explanation):

"""


def _resize_image(image_bytes: bytes, max_dim: int = MAX_IMAGE_DIMENSION) -> bytes:
    """Resize image so largest dimension <= max_dim. Returns JPEG bytes."""
    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")

    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _encode_image(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode("utf-8")


def extract_from_images(
    image_files: list[tuple[str, bytes]],
) -> tuple[ExtractedEstablishment, dict]:
    """Extract structured data from menu photo(s).

    Args:
        image_files: List of (filename, bytes) tuples.

    Returns:
        (validated_model, raw_json_dict)
    """
    schema_json = json.dumps(
        ExtractedEstablishment.model_json_schema(), indent=2
    )

    content: list[dict] = []
    for filename, raw_bytes in image_files:
        resized = _resize_image(raw_bytes)
        b64 = _encode_image(resized)
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": b64,
                },
            }
        )
        content.append({"type": "text", "text": f"(Image: {filename})"})

    content.append(
        {
            "type": "text",
            "text": "Extract all information you can see from the menu photo(s) above.",
        }
    )

    client = anthropic.Anthropic(api_key=get_anthropic_key())
    response = client.messages.create(
        model=EXTRACTION_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT + schema_json,
        messages=[{"role": "user", "content": content}],
    )

    raw_text = response.content[0].text.strip()
    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        if raw_text.endswith("```"):
            raw_text = raw_text[: raw_text.rfind("```")]
        raw_text = raw_text.strip()

    raw_dict = json.loads(raw_text)
    validated = ExtractedEstablishment.model_validate(raw_dict)
    return validated, raw_dict
