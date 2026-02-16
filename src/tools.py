from pathlib import Path
from typing import Annotated

import httpx
from fastmcp.server.apps import AppConfig, ResourceCSP

from src import mcp
from src.alto import fetch_alto_for_page, fetch_alto_xml_from_url, parse_alto_xml
from src.iiif import fetch_iiif_info, fetch_manifest, parse_manifest_pages
from src.models import (
    PageData,
    ViewDocumentError,
    ViewDocumentResult,
    ViewManifestResult,
)

DIST_DIR = Path(__file__).parent.parent / "dist"
RESOURCE_URI = "ui://riksarkivet/mcp-app.html"

_CSP = ResourceCSP(
    resource_domains=["https://lbiiif.riksarkivet.se"],
    connect_domains=["https://lbiiif.riksarkivet.se"],
)


@mcp.tool(
    name="view-manifest",
    description="Display a full IIIF manifest with page navigation, zoomable tiles, and ALTO text overlays. Provide a IIIF manifest URL from Riksarkivet.",
    app=AppConfig(resource_uri=RESOURCE_URI, csp=_CSP),
)
def view_manifest(
    manifest_url: Annotated[str, "IIIF Presentation manifest URL (e.g. 'https://lbiiif.riksarkivet.se/arkis!R0000560/manifest')"],
) -> ViewManifestResult | ViewDocumentError:
    """View a multi-page document from a IIIF manifest with page navigation."""
    try:
        manifest = fetch_manifest(manifest_url)

        title = ""
        label = manifest.get("label", "")
        if isinstance(label, str):
            title = label
        elif isinstance(label, dict):
            for values in label.values():
                if isinstance(values, list) and values:
                    title = str(values[0])
                    break
        title = title or "Untitled"

        raw_pages = parse_manifest_pages(manifest)

        pages: list[PageData] = []
        for p in raw_pages:
            image_id = p.get("image_id", "")
            text_lines = fetch_alto_for_page(image_id) if image_id else []
            pages.append(
                PageData(
                    pageNumber=p["page_number"],
                    imageService=p["image_service"],
                    pageWidth=p["page_width"],
                    pageHeight=p["page_height"],
                    textLines=text_lines,
                    label=p.get("label", f"Page {p['page_number']}"),
                )
            )

        return ViewManifestResult(
            manifestUrl=manifest_url,
            title=title,
            totalPages=len(pages),
            pages=pages,
        )

    except httpx.HTTPError as e:
        return ViewDocumentError(message=f"Error loading manifest: {e}")
    except Exception as e:
        return ViewDocumentError(message=f"Error parsing manifest: {e}")


@mcp.tool(
    name="view-document",
    description="Display document pages with zoomable images and ALTO text overlays. Provide paired lists of image URLs and ALTO XML URLs (image_urls[i] pairs with alto_urls[i]).",
    app=AppConfig(resource_uri=RESOURCE_URI, csp=_CSP),
)
def view_document(
    image_urls: Annotated[list[str], "List of image URLs (IIIF or direct). Each pairs with the corresponding alto_url."],
    alto_urls: Annotated[list[str], "List of ALTO XML URLs. Each pairs with the corresponding image_url."],
) -> ViewDocumentResult | ViewDocumentError:
    """View document pages with zoomable images and ALTO overlays."""
    if len(image_urls) != len(alto_urls):
        return ViewDocumentError(
            message=f"Mismatched URL counts: {len(image_urls)} images vs {len(alto_urls)} ALTO files"
        )

    try:
        pages: list[PageData] = []
        for idx, (img_url, alt_url) in enumerate(zip(image_urls, alto_urls)):
            # Fetch and parse ALTO
            alto_xml = fetch_alto_xml_from_url(alt_url)
            alto_data = parse_alto_xml(alto_xml)

            # Try to get IIIF info for tile-based viewing
            iiif_info = fetch_iiif_info(img_url)

            pages.append(
                PageData(
                    pageNumber=idx + 1,
                    imageService=iiif_info if iiif_info else None,
                    imageUrl=img_url if not iiif_info else None,
                    pageWidth=alto_data.page_width,
                    pageHeight=alto_data.page_height,
                    textLines=alto_data.text_lines,
                    label=f"Page {idx + 1}",
                )
            )

        return ViewDocumentResult(
            totalPages=len(pages),
            pages=pages,
        )

    except httpx.HTTPError as e:
        return ViewDocumentError(message=f"Error loading document: {e}")
    except Exception as e:
        return ViewDocumentError(message=f"Error processing document: {e}")


@mcp.resource(uri=RESOURCE_URI)
def get_ui_resource() -> str:
    html_path = DIST_DIR / "mcp-app.html"
    if not html_path.exists():
        raise FileNotFoundError(f"UI resource not found: {html_path}")
    return html_path.read_text(encoding="utf-8")
