"""
Cached HTTP fetchers for document images, thumbnails, and ALTO XML.

All fetch functions use @lru_cache keyed by URL so the same remote resource
is downloaded at most once per server process, regardless of which tool or
page index requests it.

Custom OTEL spans are created via fastmcp's tracer. These are automatic no-ops
when no SDK is configured — the parent ra-mcp package handles SDK initialization.
"""

import base64
import io
import logging
from functools import lru_cache

import httpx
from fastmcp.telemetry import get_tracer
from PIL import Image

from src.parser import detect_and_parse, fetch_alto_xml_from_url

logger = logging.getLogger(__name__)
tracer = get_tracer()


@lru_cache(maxsize=32)
def fetch_image_as_data_url(url: str) -> str:
    """Fetch image and return as base64 data URL. Cached by URL."""
    with tracer.start_as_current_span("fetch_image", attributes={"url": url}):
        logger.debug("Fetching image: %s", url)
        resp = httpx.get(url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg")
        b64 = base64.b64encode(resp.content).decode("ascii")
        logger.info("Image fetched: %d bytes (%s)", len(resp.content), content_type)
        return f"data:{content_type};base64,{b64}"


@lru_cache(maxsize=128)
def fetch_thumbnail_as_data_url(url: str, max_width: int = 150) -> str:
    """Fetch image, resize to thumbnail, return as base64 data URL. Cached by URL."""
    with tracer.start_as_current_span("fetch_thumbnail", attributes={"url": url, "max_width": max_width}):
        logger.debug("Fetching thumbnail: %s", url)
        resp = httpx.get(url, timeout=60.0, follow_redirects=True)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        logger.info("Thumbnail: %dx%d, %d bytes", max_width, new_height, len(buf.getvalue()))
        return f"data:image/jpeg;base64,{b64}"


@lru_cache(maxsize=32)
def fetch_and_parse_alto(url: str) -> dict:
    """Fetch ALTO XML and parse into structured text line data. Cached by URL."""
    with tracer.start_as_current_span("fetch_alto", attributes={"url": url}):
        xml = fetch_alto_xml_from_url(url)
        data = detect_and_parse(xml)
        return {
            "textLines": [
                {
                    "id": line.id,
                    "polygon": line.polygon,
                    "transcription": line.transcription,
                    "hpos": line.hpos,
                    "vpos": line.vpos,
                    "width": line.width,
                    "height": line.height,
                    "confidence": line.confidence,
                }
                for line in data.text_lines
            ],
            "pageWidth": data.page_width,
            "pageHeight": data.page_height,
        }


def build_page_data(index: int, image_url: str, alto_url: str) -> tuple[dict, list[str]]:
    """Fetch image + ALTO for a single page. Returns (page_dict, errors)."""
    page: dict = {"index": index}
    errors: list[str] = []

    try:
        page["imageDataUrl"] = fetch_image_as_data_url(image_url)
    except Exception as e:
        logger.error("Image fetch failed for page %d: %s", index, e)
        errors.append(f"Page {index + 1} image: {e}")
        page["imageDataUrl"] = ""

    if alto_url:
        try:
            page["alto"] = fetch_and_parse_alto(alto_url)
        except Exception as e:
            logger.error("ALTO fetch failed for page %d: %s", index, e)
            errors.append(f"Page {index + 1} ALTO: {e}")
            page["alto"] = {"textLines": [], "pageWidth": 0, "pageHeight": 0}
    else:
        page["alto"] = {"textLines": [], "pageWidth": 0, "pageHeight": 0}

    return page, errors
