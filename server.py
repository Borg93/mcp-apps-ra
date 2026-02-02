"""
Riksarkivet Document Viewer MCP App Server

Interactive document viewer for Swedish National Archives with ALTO XML visualization.
"""

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import httpx
from mcp.server.fastmcp import FastMCP

DIST_DIR = Path(__file__).parent / "dist"
RESOURCE_URI = "ui://riksarkivet/mcp-app.html"
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"

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
    description="Visa ett dokument från Riksarkivet med interaktiv ALTO XML-visualisering. Ange image_id (t.ex. 'A0068523_00007')",
    meta={"ui": {"resourceUri": RESOURCE_URI}},
)
def view_document(
    image_id: Annotated[str, "Dokumentets bild-ID (t.ex. 'A0068523_00007')"],
) -> str:
    """View a document from Riksarkivet with interactive ALTO overlay."""
    document_id = image_id.split("_")[0]
    image_url = f"https://lbiiif.riksarkivet.se/arkis!{image_id}/full/max/0/default.jpg"
    alto_url = f"https://lbiiif.riksarkivet.se/download/current/alto/{document_id}?format=xml&imageid={image_id}"

    try:
        alto_xml = fetch_alto_xml(image_id)
        alto_data = parse_alto_xml(alto_xml)

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
            "imageUrl": image_url,
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
                "message": f"Fel vid laddning av dokument: {str(e)}",
            }
        )


@mcp.tool(
    name="view-document-custom",
    description="""Visa ett dokument med egen ALTO XML.

Alternativ för bild:
- image_url: Ange en URL till bilden
- riksarkivet_image_id: Ange Riksarkivet image_id (t.ex. 'A0068523_00007') för att använda deras bild

ALTO XML kan antingen laddas upp som fil till Claude eller klistras in som text.""",
    meta={"ui": {"resourceUri": RESOURCE_URI}},
)
def view_document_custom(
    alto_xml_content: Annotated[str, "ALTO XML-innehållet som text"],
    image_url: Annotated[str | None, "URL till dokumentbilden"] = None,
    riksarkivet_image_id: Annotated[str | None, "Riksarkivet image_id för att hämta bild därifrån"] = None,
    document_id: Annotated[str, "Dokument-ID för referens"] = "custom_document",
) -> str:
    """View a document with custom ALTO XML and flexible image source."""
    try:
        # Determine image URL
        if riksarkivet_image_id:
            final_image_url = f"https://lbiiif.riksarkivet.se/arkis!{riksarkivet_image_id}/full/max/0/default.jpg"
            document_id = riksarkivet_image_id
        elif image_url:
            final_image_url = image_url
        else:
            return json.dumps(
                {
                    "error": True,
                    "imageId": document_id,
                    "message": "Ange antingen image_url eller riksarkivet_image_id",
                }
            )

        alto_data = parse_alto_xml(alto_xml_content)

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
            "imageId": document_id,
            "imageUrl": final_image_url,
            "altoUrl": "content://provided-directly",
            "pageWidth": alto_data.page_width,
            "pageHeight": alto_data.page_height,
            "textLines": lines_data,
            "totalLines": len(lines_data),
            "fullText": alto_data.full_text[:800]
            + ("..." if len(alto_data.full_text) > 800 else ""),
        }

        return json.dumps(result)

    except Exception as e:
        return json.dumps(
            {
                "error": True,
                "imageId": document_id,
                "message": f"Fel vid parsning av ALTO XML: {str(e)}",
            }
        )


@mcp.tool(
    name="text-line-selected",
    description="Anropas när användaren klickar på en textrad. Returnerar beskuren bild och begär översättning.",
)
def text_line_selected(
    line_id: Annotated[str, "ID för textraden"],
    transcription: Annotated[str, "Den transkriberade texten"],
    document_id: Annotated[str, "Dokument-ID"],
    hpos: Annotated[int, "Horisontell position"],
    vpos: Annotated[int, "Vertikal position"],
    width: Annotated[int, "Bredd på textraden"],
    height: Annotated[int, "Höjd på textraden"],
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
        f"📍 Textrad vald\n\n"
        f"Dokument: {document_id}\n"
        f"Rad-ID: {line_id}\n\n"
        f"**Beskuren bild av textraden:**\n{crop_url}\n\n"
        f'**Original transkription (historisk svenska):**\n"{transcription}"\n\n'
        f"**UPPGIFT:** Titta på bilden ovan och översätt den historiska svenska texten till modern svenska. "
        f"Förklara vad texten betyder och ge kontext om det behövs."
    )


@mcp.tool(
    name="fetch-all-document-text",
    description="Hämtar all transkriberad text från dokumentet för översättning.",
)
def fetch_all_document_text(
    document_id: Annotated[str, "Dokument-ID"],
    total_lines: Annotated[int, "Totalt antal textrader"],
    transcriptions: Annotated[str, "JSON-array med transkriptioner"],
) -> str:
    """Fetch all document text for translation."""
    try:
        lines = json.loads(transcriptions)
        all_text = "\n".join(f"{i + 1}. {line['text']}" for i, line in enumerate(lines))
        full_text = " ".join(line["text"] for line in lines)

        return (
            f"📄 Full dokumenttext hämtad\n\n"
            f"Dokument: {document_id}\n"
            f"Totalt antal rader: {total_lines}\n\n"
            f"**Fullständig transkription (numrerade rader):**\n\n{all_text}\n\n"
            f"---\n\n"
            f"**Kontinuerlig text:**\n{full_text}\n\n"
            f"**UPPGIFT:** Översätt hela dokumentet till modern svenska och ge en sammanfattning av innehållet."
        )
    except json.JSONDecodeError:
        return "Fel: Kunde inte parsa transkriptionsdata"


@mcp.resource(uri=RESOURCE_URI, mime_type=RESOURCE_MIME_TYPE)
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
