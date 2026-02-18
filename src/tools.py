"""
Document Viewer MCP App — Tool & resource registrations.

Tools:
  - view-document: entry point, fetches first page, returns URL list for pagination
  - load-page: fetches a single page on demand (called by View via callServerTool)
  - load-thumbnails: batch-fetches thumbnail images (called by View via callServerTool)
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Annotated

from fastmcp import Context
from fastmcp.server.apps import AppConfig, UI_EXTENSION_ID
from fastmcp.tools import ToolResult
from mcp import types

from src import mcp
from src.fetchers import build_page_data, fetch_and_parse_alto, fetch_thumbnail_as_data_url

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

DIST_DIR = Path(__file__).parent.parent / "dist"
RESOURCE_URI = "ui://document-viewer/mcp-app.html"


@mcp.tool(
    name="view-document",
    description=(
        "Display document pages with zoomable images and ALTO text overlays. "
        "Provide paired lists: image_urls[i] pairs with alto_urls[i]. "
        "Only the first page is fetched immediately; remaining pages load on demand via pagination."
    ),
    app=AppConfig(resource_uri=RESOURCE_URI),
)
async def view_document(
    image_urls: Annotated[list[str], "List of image URLs (one per page)."],
    alto_urls: Annotated[list[str], "List of ALTO XML URLs (one per page, paired with image_urls)."],
    ctx: Context,
) -> ToolResult:
    """View document pages with zoomable images and ALTO overlays."""
    if len(image_urls) != len(alto_urls):
        return ToolResult(
            content=[types.TextContent(
                type="text",
                text=f"Error: mismatched URL counts ({len(image_urls)} images vs {len(alto_urls)} ALTO files)",
            )],
        )

    has_ui = ctx.client_supports_extension(UI_EXTENSION_ID)

    # Build model-visible transcription of first page
    first_alto = fetch_and_parse_alto(alto_urls[0])
    text_lines = first_alto.get("textLines", [])
    transcription = "\n".join(line["transcription"] for line in text_lines)

    summary_parts = [f"Displaying {len(image_urls)}-page document. Page 1 transcription:"]
    if transcription:
        summary_parts.append(transcription)
    else:
        summary_parts.append("(no transcribed text on this page)")
    summary = "\n".join(summary_parts)

    # Plain-text fallback for hosts without UI support
    if not has_ui:
        logger.info(f"view-document (text fallback): {len(image_urls)} pages")
        return ToolResult(
            content=[types.TextContent(type="text", text=summary)],
        )

    # Full UI path: fetch image + ALTO for first page
    page_urls = [
        {"image": img_url, "alto": alto_url}
        for img_url, alto_url in zip(image_urls, alto_urls)
    ]
    first_page, errors = build_page_data(0, image_urls[0], alto_urls[0])

    if errors:
        summary += f"\nErrors: {'; '.join(errors)}"

    logger.info(f"view-document: {len(page_urls)} pages, {len(text_lines)} lines on page 1")
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
    page, errors = build_page_data(page_index, image_url, alto_url)

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
            data_url = fetch_thumbnail_as_data_url(url)
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
