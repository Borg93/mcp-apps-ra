"""
Riksarkivet Document Viewer MCP App Server

Interactive document viewer for Swedish National Archives with ALTO XML visualization.
"""

import argparse
import base64
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import httpx
from fastmcp import FastMCP
from fastmcp.server.apps import ToolUI

DIST_DIR = Path(__file__).parent / "dist"
RESOURCE_URI = "ui://riksarkivet/mcp-app.html"

mcp = FastMCP(name="Riksarkivet Document Viewer")


@dataclass
class TextLine:
    id: str
    polygon: str
    transcription: str
    hpos: int
    vpos: int
    width: int
    height: int


@dataclass
class AltoData:
    text_lines: list[TextLine]
    page_width: int
    page_height: int
    full_text: str


def fetch_alto_xml(image_id: str) -> str:
    """Fetch ALTO XML from Riksarkivet."""
    document_id = image_id.split("_")[0]
    alto_url = f"https://lbiiif.riksarkivet.se/download/current/alto/{document_id}?format=xml&imageid={image_id}"

    response = httpx.get(alto_url, timeout=30.0)
    response.raise_for_status()
    return response.text


def fetch_image_as_data_url(image_id: str, size: str = "1000,") -> str:
    """Fetch image from Riksarkivet and return as base64 data URL.

    MCP Apps CSP restricts img-src to data: only, so we must fetch
    the image server-side and convert to a data URL.

    Args:
        image_id: Document image ID (e.g. 'A0068523_00007')
        size: IIIF size parameter (default "1000," = 1000px wide, proportional height)
    """
    # IIIF URL: /{identifier}/{region}/{size}/{rotation}/{quality}.{format}
    image_url = f"https://lbiiif.riksarkivet.se/arkis!{image_id}/full/{size}/0/default.jpg"

    response = httpx.get(image_url, timeout=60.0)
    response.raise_for_status()

    # Get content type (should be image/jpeg)
    content_type = response.headers.get("content-type", "image/jpeg")

    # Encode to base64
    b64_data = base64.b64encode(response.content).decode("utf-8")

    return f"data:{content_type};base64,{b64_data}"


def parse_alto_xml(xml_string: str) -> AltoData:
    """Parse ALTO XML and extract text lines with polygons."""
    text_lines: list[TextLine] = []
    transcription_lines: list[str] = []

    # Extract page dimensions
    page_match = re.search(r'<Page[^>]*WIDTH="(\d+)"[^>]*HEIGHT="(\d+)"', xml_string)
    page_width = int(page_match.group(1)) if page_match else 6192
    page_height = int(page_match.group(2)) if page_match else 5432

    # Extract all TextLine elements
    text_line_pattern = re.compile(
        r'<TextLine[^>]*ID="([^"]*)"[^>]*HPOS="(\d+)"[^>]*VPOS="(\d+)"[^>]*HEIGHT="(\d+)"[^>]*WIDTH="(\d+)"[^>]*>([\s\S]*?)</TextLine>',
        re.MULTILINE,
    )

    for match in text_line_pattern.finditer(xml_string):
        line_id = match.group(1)
        hpos = int(match.group(2))
        vpos = int(match.group(3))
        height = int(match.group(4))
        width = int(match.group(5))
        line_content = match.group(6)

        # Extract polygon points
        polygon_match = re.search(r'<Polygon[^>]*POINTS="([^"]*)"', line_content)
        polygon = polygon_match.group(1) if polygon_match else ""

        # Extract all String elements (words)
        words = re.findall(r'<String[^>]*CONTENT="([^"]*)"', line_content)
        transcription = " ".join(words)

        if polygon and transcription:
            text_lines.append(
                TextLine(
                    id=line_id,
                    polygon=polygon,
                    transcription=transcription,
                    hpos=hpos,
                    vpos=vpos,
                    width=width,
                    height=height,
                )
            )
            transcription_lines.append(transcription)

    return AltoData(
        text_lines=text_lines,
        page_width=page_width,
        page_height=page_height,
        full_text="\n".join(transcription_lines),
    )


@mcp.tool(
    name="view-document",
    description="Display a document from Riksarkivet with interactive ALTO XML visualization. Provide image_id (e.g. 'A0068523_00007')",
    ui=ToolUI(resource_uri=RESOURCE_URI),
)
def view_document(
    image_id: Annotated[str, "Document image ID (e.g. 'A0068523_00007')"],
) -> str:
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

        result = {
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

        return json.dumps(result)

    except httpx.HTTPError as e:
        return json.dumps(
            {
                "error": True,
                "imageId": image_id,
                "message": f"Error loading document: {str(e)}",
            }
        )


@mcp.tool(
    name="upload-document",
    description="Open the document viewer with upload functionality. User can upload ALTO XML and image files directly in the interface.",
    ui=ToolUI(resource_uri=RESOURCE_URI),
)
def upload_document() -> str:
    """Open the document viewer with upload functionality."""
    return json.dumps(
        {
            "mode": "upload",
            "message": "Upload ALTO XML file and image file to view the document.",
        }
    )


@mcp.tool(
    name="text-line-selected",
    description="Called when user clicks on a text line. Returns cropped image and requests translation.",
)
def text_line_selected(
    line_id: Annotated[str, "Text line ID"],
    transcription: Annotated[str, "The transcribed text"],
    document_id: Annotated[str, "Document ID"],
    hpos: Annotated[int, "Horizontal position"],
    vpos: Annotated[int, "Vertical position"],
    width: Annotated[int, "Text line width"],
    height: Annotated[int, "Text line height"],
) -> str:
    """Handle text line selection - return cropped image and request translation."""
    # Build IIIF crop URL: /{region}/{size}/{rotation}/{quality}.{format}
    # Add padding around the text line for better visibility
    padding = 20
    crop_x = max(0, hpos - padding)
    crop_y = max(0, vpos - padding)
    crop_w = width + (padding * 2)
    crop_h = height + (padding * 2)

    crop_url = f"https://lbiiif.riksarkivet.se/arkis!{document_id}/{crop_x},{crop_y},{crop_w},{crop_h}/max/0/default.jpg"

    return (
        f"📍 Text line selected\n\n"
        f"Document: {document_id}\n"
        f"Line ID: {line_id}\n\n"
        f"**Cropped image of text line:**\n{crop_url}\n\n"
        f'**Original transcription (historical Swedish):**\n"{transcription}"\n\n'
        f"**TASK:** Look at the image above and translate the historical Swedish text to modern Swedish. "
        f"Explain what the text means and provide context if needed."
    )


@mcp.resource(uri=RESOURCE_URI)
def get_ui_resource() -> str:
    html_path = DIST_DIR / "mcp-app.html"
    if not html_path.exists():
        raise FileNotFoundError(f"UI resource not found: {html_path}")
    return html_path.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="MCP Demo Counter App Server")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run with stdio transport (default is HTTP)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("PORT", "3001")),
        help="Port for HTTP server (default: 3001)",
    )
    args = parser.parse_args()

    if args.stdio:
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = "0.0.0.0"
        mcp.settings.port = args.port
        mcp.settings.streamable_http_path = "/mcp"
        print(f"MCP Demo Server listening on http://localhost:{args.port}/mcp")
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
