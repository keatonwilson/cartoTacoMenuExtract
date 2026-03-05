"""Tests for extraction module (unit tests, no API calls)."""

import io
from PIL import Image
from src.extraction import _resize_image


def test_resize_small_image_unchanged():
    """Images smaller than max_dim are not upscaled."""
    img = Image.new("RGB", (800, 600), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    original_bytes = buf.getvalue()

    resized = _resize_image(original_bytes, max_dim=1500)
    result = Image.open(io.BytesIO(resized))
    assert result.size[0] <= 1500
    assert result.size[1] <= 1500


def test_resize_large_image():
    """Large images are resized to fit max_dim."""
    img = Image.new("RGB", (4000, 3000), color="blue")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    resized = _resize_image(buf.getvalue(), max_dim=1500)
    result = Image.open(io.BytesIO(resized))
    assert max(result.size) <= 1500


def test_resize_preserves_aspect_ratio():
    """Aspect ratio is preserved after resize."""
    img = Image.new("RGB", (4000, 2000), color="green")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    resized = _resize_image(buf.getvalue(), max_dim=1000)
    result = Image.open(io.BytesIO(resized))
    ratio = result.size[0] / result.size[1]
    assert abs(ratio - 2.0) < 0.05
