import base64
import json
import logging
from pathlib import Path
from typing import Annotated

import httpx
from fastmcp.server.apps import AppConfig, ResourceCSP
from fastmcp.tools import ToolResult
from mcp import types

from src import mcp
from src.alto import fetch_alto_xml_from_url, parse_alto_xml

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

DIST_DIR = Path(__file__).parent.parent / "dist"
RESOURCE_URI = "ui://riksarkivet/mcp-app.html"
MAX_CHUNK_BYTES = 512 * 1024  # 512KB per chunk

_CSP = ResourceCSP(
    resource_domains=["https://lbiiif.riksarkivet.se", "https://sok.riksarkivet.se"],
    connect_domains=["https://lbiiif.riksarkivet.se", "https://sok.riksarkivet.se"],
)

# Simple in-memory cache for image bytes (avoids re-fetching for each chunk)
_image_cache: dict[str, bytes] = {}


def _get_image_bytes(url: str) -> bytes:
    """Fetch image bytes with caching for chunked reads."""
    if url not in _image_cache:
        logger.info(f"Fetching image: {url}")
        resp = httpx.get(url, timeout=30.0)
        resp.raise_for_status()
        _image_cache[url] = resp.content
        logger.info(f"Cached image: {len(resp.content)} bytes")
    return _image_cache[url]


# =============================================================================
# Tool: view-document (model-visible) — returns tiny config, app loads data
# =============================================================================

@mcp.tool(
    name="view-document",
    description="Display document pages with zoomable images and ALTO text overlays. Provide paired lists of image URLs and ALTO XML URLs (image_urls[i] pairs with alto_urls[i]).",
    app=AppConfig(resource_uri=RESOURCE_URI, csp=_CSP),
)
def view_document(
    image_urls: Annotated[list[str], "List of image URLs. Each pairs with the corresponding alto_url."],
    alto_urls: Annotated[list[str], "List of ALTO XML URLs. Each pairs with the corresponding image_url."],
) -> ToolResult:
    """View document pages with zoomable images and ALTO overlays."""
    if len(image_urls) != len(alto_urls):
        return ToolResult(
            content=[types.TextContent(type="text", text=f"Mismatched: {len(image_urls)} images vs {len(alto_urls)} ALTO files")],
        )

    data = {"imageUrls": image_urls, "altoUrls": alto_urls}
    logger.info(f"view-document: {len(image_urls)} page(s)")
    return ToolResult(
        content=[types.TextContent(type="text", text=json.dumps(data))],
        structured_content=data,
    )


# =============================================================================
# Tool: read-image-bytes (app-only) — streams image data in chunks
# =============================================================================

@mcp.tool(
    name="read-image-bytes",
    description="Read image bytes from a URL in chunks (max 512KB per request).",
    app=AppConfig(resource_uri=RESOURCE_URI, visibility=["app"]),
)
def read_image_bytes(
    url: Annotated[str, "Image URL to fetch"],
    offset: Annotated[int, "Byte offset"] = 0,
    byte_count: Annotated[int, "Bytes to read (max 512KB)"] = MAX_CHUNK_BYTES,
) -> ToolResult:
    """Fetch image bytes in chunks for the viewer app."""
    clamped = min(byte_count, MAX_CHUNK_BYTES)
    try:
        full_data = _get_image_bytes(url)
        total_bytes = len(full_data)

        start = min(offset, total_bytes)
        end = min(start + clamped, total_bytes)
        chunk = full_data[start:end]

        b64 = base64.b64encode(chunk).decode("ascii")
        has_more = end < total_bytes

        # Clean cache after last chunk
        if not has_more and url in _image_cache:
            del _image_cache[url]

        return ToolResult(
            content=[types.TextContent(type="text", text=f"{len(chunk)} bytes at {offset}/{total_bytes}")],
            structured_content={
                "bytes": b64,
                "offset": offset,
                "byteCount": len(chunk),
                "totalBytes": total_bytes,
                "hasMore": has_more,
            },
        )
    except Exception as e:
        logger.error(f"read-image-bytes error: {e}", exc_info=True)
        return ToolResult(
            content=[types.TextContent(type="text", text=f"Error: {e}")],
        )


# =============================================================================
# Tool: read-alto (app-only) — fetches and parses ALTO XML server-side
# =============================================================================

@mcp.tool(
    name="read-alto",
    description="Fetch and parse ALTO XML, returning text lines with polygon coordinates.",
    app=AppConfig(resource_uri=RESOURCE_URI, visibility=["app"]),
)
def read_alto(
    url: Annotated[str, "ALTO XML URL to fetch and parse"],
) -> ToolResult:
    """Fetch and parse ALTO XML for the viewer app."""
    try:
        xml = fetch_alto_xml_from_url(url)
        data = parse_alto_xml(xml)

        text_lines = [
            {
                "id": line.id,
                "polygon": line.polygon,
                "transcription": line.transcription,
                "hpos": line.hpos,
                "vpos": line.vpos,
                "width": line.width,
                "height": line.height,
            }
            for line in data.text_lines
        ]

        logger.info(f"read-alto: {len(text_lines)} lines, {data.page_width}x{data.page_height}")
        return ToolResult(
            content=[types.TextContent(type="text", text=f"{len(text_lines)} text lines, {data.page_width}x{data.page_height}")],
            structured_content={
                "textLines": text_lines,
                "pageWidth": data.page_width,
                "pageHeight": data.page_height,
            },
        )
    except Exception as e:
        logger.error(f"read-alto error: {e}", exc_info=True)
        return ToolResult(
            content=[types.TextContent(type="text", text=f"Error: {e}")],
        )


# =============================================================================
# Resource: UI HTML
# =============================================================================

@mcp.resource(uri=RESOURCE_URI, app=AppConfig(csp=_CSP))
def get_ui_resource() -> str:
    html_path = DIST_DIR / "mcp-app.html"
    if not html_path.exists():
        raise FileNotFoundError(f"UI resource not found: {html_path}")
    return html_path.read_text(encoding="utf-8")
