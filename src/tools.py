"""
Document Viewer MCP App — Tools

Tools:
  - view-document: entry point, fetches first page, returns URL list for pagination
  - load-page: fetches a single page on demand (called by View via callServerTool)
  - load-thumbnails: batch-fetches thumbnail images (called by View via callServerTool)

Images are base64-encoded and sent through MCP because the image URLs can be
from any domain (unknown at CSP registration time). The lru_cache on fetch
helpers avoids re-downloading the same URL from the remote server.
"""

import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Annotated

import httpx
from PIL import Image
from fastmcp.server.apps import AppConfig
from fastmcp.tools import ToolResult
from mcp import types

from src import mcp
from src.alto import fetch_alto_xml_from_url, parse_alto_xml

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

DIST_DIR = Path(__file__).parent.parent / "dist"
RESOURCE_URI = "ui://document-viewer/mcp-app.html"


@lru_cache(maxsize=32)
def _fetch_image_as_data_url(url: str) -> str:
    """Fetch image and return as base64 data URL. Cached by URL."""
    logger.info(f"Fetching image: {url}")
    resp = httpx.get(url, timeout=60.0, follow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "image/jpeg")
    b64 = base64.b64encode(resp.content).decode("ascii")
    logger.info(f"Image fetched: {len(resp.content)} bytes, {content_type}")
    return f"data:{content_type};base64,{b64}"


@lru_cache(maxsize=128)
def _fetch_image_as_thumbnail_data_url(url: str, max_width: int = 150) -> str:
    """Fetch image, resize to thumbnail with Pillow, return as base64 data URL. Cached by URL."""
    logger.info(f"Fetching thumbnail: {url}")
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
    logger.info(f"Thumbnail generated: {max_width}x{new_height}, {len(buf.getvalue())} bytes")
    return f"data:image/jpeg;base64,{b64}"


@lru_cache(maxsize=32)
def _fetch_and_parse_alto(url: str) -> dict:
    """Fetch ALTO XML and parse into structured text line data. Cached by URL."""
    logger.info(f"Fetching ALTO: {url}")
    xml = fetch_alto_xml_from_url(url)
    data = parse_alto_xml(xml)
    logger.info(f"ALTO parsed: {len(data.text_lines)} lines, {data.page_width}x{data.page_height}")
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
            }
            for line in data.text_lines
        ],
        "pageWidth": data.page_width,
        "pageHeight": data.page_height,
    }


def _build_page_data(index: int, image_url: str, alto_url: str) -> tuple[dict, list[str]]:
    """Fetch image + ALTO for a single page. Returns (page_dict, errors)."""
    page: dict = {"index": index}
    errors: list[str] = []

    try:
        page["imageDataUrl"] = _fetch_image_as_data_url(image_url)
    except Exception as e:
        logger.error(f"Image fetch failed for page {index}: {e}")
        errors.append(f"Page {index + 1} image: {e}")
        page["imageDataUrl"] = ""

    try:
        page["alto"] = _fetch_and_parse_alto(alto_url)
    except Exception as e:
        logger.error(f"ALTO fetch failed for page {index}: {e}")
        errors.append(f"Page {index + 1} ALTO: {e}")
        page["alto"] = {"textLines": [], "pageWidth": 0, "pageHeight": 0}

    return page, errors


@mcp.tool(
    name="view-document",
    description=(
        "Display document pages with zoomable images and ALTO text overlays. "
        "Provide paired lists: image_urls[i] pairs with alto_urls[i]. "
        "Only the first page is fetched immediately; remaining pages load on demand via pagination."
    ),
    app=AppConfig(resource_uri=RESOURCE_URI),
)
def view_document(
    image_urls: Annotated[list[str], "List of image URLs (one per page)."],
    alto_urls: Annotated[list[str], "List of ALTO XML URLs (one per page, paired with image_urls)."],
) -> ToolResult:
    """View document pages with zoomable images and ALTO overlays."""
    if len(image_urls) != len(alto_urls):
        return ToolResult(
            content=[types.TextContent(
                type="text",
                text=f"Error: mismatched URL counts ({len(image_urls)} images vs {len(alto_urls)} ALTO files)",
            )],
        )

    # Build URL list for all pages
    page_urls = [
        {"image": img_url, "alto": alto_url}
        for img_url, alto_url in zip(image_urls, alto_urls)
    ]

    # Fetch only the first page
    first_page, errors = _build_page_data(0, image_urls[0], alto_urls[0])

    total_lines = len(first_page.get("alto", {}).get("textLines", []))
    summary = f"Loaded page 1 of {len(page_urls)} with {total_lines} text lines."
    if errors:
        summary += f" Errors: {'; '.join(errors)}"

    logger.info(f"view-document: {summary}")
    return ToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structured_content={
            "pageUrls": page_urls,
            "firstPage": first_page,
        },
    )


@mcp.tool(
    name="load-page",
    description="Load a single document page (image + ALTO). Used by the viewer for pagination.",
    app=AppConfig(resource_uri=RESOURCE_URI, visibility=["app"]),
)
def load_page(
    image_url: Annotated[str, "Image URL for the page."],
    alto_url: Annotated[str, "ALTO XML URL for the page."],
    page_index: Annotated[int, "Zero-based page index."],
) -> ToolResult:
    """Fetch a single page on demand."""
    page, errors = _build_page_data(page_index, image_url, alto_url)

    total_lines = len(page.get("alto", {}).get("textLines", []))
    summary = f"Page {page_index + 1}: {total_lines} text lines."
    if errors:
        summary += f" Errors: {'; '.join(errors)}"

    logger.info(f"load-page: {summary}")
    return ToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structured_content={"page": page},
    )


@mcp.tool(
    name="load-thumbnails",
    description="Load thumbnail images for a batch of document pages. Used by the viewer for lazy-loading the thumbnail strip.",
    app=AppConfig(resource_uri=RESOURCE_URI, visibility=["app"]),
)
def load_thumbnails(
    image_urls: Annotated[list[str], "Image URLs for the pages to thumbnail."],
    page_indices: Annotated[list[int], "Zero-based page indices corresponding to image_urls."],
) -> ToolResult:
    """Fetch and resize a batch of page images into thumbnails (parallel)."""
    thumbnails: list[dict] = []
    errors: list[str] = []

    def _fetch_one(url: str, idx: int) -> dict | None:
        try:
            data_url = _fetch_image_as_thumbnail_data_url(url)
            return {"index": idx, "dataUrl": data_url}
        except Exception as e:
            logger.error(f"Thumbnail failed for page {idx}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=min(len(image_urls), 4)) as pool:
        futures = {
            pool.submit(_fetch_one, url, idx): idx
            for url, idx in zip(image_urls, page_indices)
        }
        for future in futures:
            result = future.result()
            if result:
                thumbnails.append(result)
            else:
                idx = futures[future]
                errors.append(f"Page {idx + 1}: failed")

    # Sort by index so they arrive in order
    thumbnails.sort(key=lambda t: t["index"])

    summary = f"Generated {len(thumbnails)} thumbnails."
    if errors:
        summary += f" Errors: {'; '.join(errors)}"

    logger.info(f"load-thumbnails: {summary}")
    return ToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structured_content={"thumbnails": thumbnails},
    )


@mcp.resource(uri=RESOURCE_URI)
def get_ui_resource() -> str:
    html_path = DIST_DIR / "mcp-app.html"
    if not html_path.exists():
        raise FileNotFoundError(f"UI resource not found: {html_path}")
    return html_path.read_text(encoding="utf-8")
