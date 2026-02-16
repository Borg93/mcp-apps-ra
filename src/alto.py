import re

import httpx

from src.models import AltoData, TextLine


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
