from pathlib import Path
from typing import Annotated

import httpx
from fastmcp.server.apps import AppConfig

from src import mcp
from src.alto import fetch_alto_xml, parse_alto_xml
from src.image import fetch_image_as_data_url

DIST_DIR = Path(__file__).parent.parent / "dist"
RESOURCE_URI = "ui://riksarkivet/mcp-app.html"


@mcp.tool(
    name="view-document",
    description="Display a document from Riksarkivet with interactive ALTO XML visualization. Provide image_id (e.g. 'A0068523_00007')",
    app=AppConfig(resource_uri=RESOURCE_URI),
)
def view_document(
    image_id: Annotated[str, "Document image ID (e.g. 'A0068523_00007')"],
) -> dict:
    """View a document from Riksarkivet with interactive ALTO overlay."""
    document_id = image_id.split("_")[0]
    alto_url = f"https://lbiiif.riksarkivet.se/download/current/alto/{document_id}?format=xml&imageid={image_id}"

    try:
        # Fetch ALTO XML for text line data
        alto_xml = fetch_alto_xml(image_id)
        alto_data = parse_alto_xml(alto_xml)

        # Fetch image and convert to data URL (CSP requires data: for img-src)
        # Use a reasonable size for web viewing (1000px wide)
        image_data_url = fetch_image_as_data_url(image_id, size="1000,")

        # Convert text lines to JSON for the frontend
        lines_data = [
            {
                "id": line.id,
                "polygon": line.polygon,
                "transcription": line.transcription,
                "hpos": line.hpos,
                "vpos": line.vpos,
                "width": line.width,
                "height": line.height,
            }
            for line in alto_data.text_lines
        ]

        return {
            "imageId": image_id,
            "imageUrl": image_data_url,
            "altoUrl": alto_url,
            "pageWidth": alto_data.page_width,
            "pageHeight": alto_data.page_height,
            "textLines": lines_data,
            "totalLines": len(lines_data),
            "fullText": alto_data.full_text[:800]
            + ("..." if len(alto_data.full_text) > 800 else ""),
        }

    except httpx.HTTPError as e:
        return {
            "error": True,
            "imageId": image_id,
            "message": f"Error loading document: {str(e)}",
        }


@mcp.tool(
    name="upload-document",
    description="Open the document viewer with upload functionality. User can upload ALTO XML and image files directly in the interface.",
    app=AppConfig(resource_uri=RESOURCE_URI),
)
def upload_document() -> dict:
    """Open the document viewer with upload functionality."""
    return {
        "mode": "upload",
        "message": "Upload ALTO XML file and image file to view the document.",
    }


@mcp.resource(uri=RESOURCE_URI)
def get_ui_resource() -> str:
    html_path = DIST_DIR / "mcp-app.html"
    if not html_path.exists():
        raise FileNotFoundError(f"UI resource not found: {html_path}")
    return html_path.read_text(encoding="utf-8")
