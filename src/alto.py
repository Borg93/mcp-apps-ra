import logging
import re

import httpx

from src.models import AltoData, TextLine

logger = logging.getLogger(__name__)


def fetch_alto_xml(image_id: str) -> str:
    """Fetch ALTO XML from Riksarkivet by image ID."""
    document_id = image_id.split("_")[0]
    alto_url = f"https://lbiiif.riksarkivet.se/download/current/alto/{document_id}?format=xml&imageid={image_id}"
    logger.info(f"fetch_alto_xml: image_id={image_id}, url={alto_url}")

    response = httpx.get(alto_url, timeout=30.0)
    logger.info(f"fetch_alto_xml: status={response.status_code}, content_length={len(response.text)}")
    response.raise_for_status()
    return response.text


def fetch_alto_xml_from_url(url: str) -> str:
    """Fetch ALTO XML from an arbitrary URL."""
    logger.info(f"fetch_alto_xml_from_url: url={url}")
    response = httpx.get(url, timeout=30.0)
    logger.info(f"fetch_alto_xml_from_url: status={response.status_code}, content_length={len(response.text)}")
    response.raise_for_status()
    return response.text


def fetch_alto_for_page(image_id: str) -> list[TextLine]:
    """Fetch and parse ALTO for a page, returning TextLine list.

    Silently returns empty list on error (page may not have ALTO).
    """
    try:
        xml = fetch_alto_xml(image_id)
        data = parse_alto_xml(xml)
        logger.info(f"fetch_alto_for_page({image_id}): got {len(data.text_lines)} text lines")
        return data.text_lines
    except (httpx.HTTPError, Exception) as e:
        logger.warning(f"fetch_alto_for_page({image_id}): failed with {type(e).__name__}: {e}")
        return []


def parse_alto_xml(xml_string: str) -> AltoData:
    """Parse ALTO XML and extract text lines with polygons."""
    text_lines: list[TextLine] = []
    transcription_lines: list[str] = []

    logger.info(f"parse_alto_xml: input length={len(xml_string)} chars")

    # Extract page dimensions
    page_match = re.search(r'<Page[^>]*WIDTH="(\d+)"[^>]*HEIGHT="(\d+)"', xml_string)
    if page_match:
        page_width = int(page_match.group(1))
        page_height = int(page_match.group(2))
        logger.info(f"  Page dimensions found: {page_width}x{page_height}")
    else:
        page_width = 6192
        page_height = 5432
        logger.warning(f"  No <Page> dimensions found, using defaults: {page_width}x{page_height}")

    # Extract all TextLine elements
    text_line_pattern = re.compile(
        r'<TextLine[^>]*ID="([^"]*)"[^>]*HPOS="(\d+)"[^>]*VPOS="(\d+)"[^>]*HEIGHT="(\d+)"[^>]*WIDTH="(\d+)"[^>]*>([\s\S]*?)</TextLine>',
        re.MULTILINE,
    )

    raw_matches = list(text_line_pattern.finditer(xml_string))
    logger.info(f"  TextLine regex matches: {len(raw_matches)}")

    # Also check: are there TextLine elements at all in the XML?
    simple_count = len(re.findall(r'<TextLine\b', xml_string))
    logger.info(f"  Raw <TextLine> tags in XML: {simple_count}")
    if simple_count > 0 and len(raw_matches) == 0:
        # The regex is not matching! Let's see why
        first_tl = re.search(r'<TextLine[^>]*>', xml_string)
        if first_tl:
            logger.warning(f"  REGEX MISMATCH! First <TextLine> tag: {first_tl.group(0)[:300]}")

    skipped_no_polygon = 0
    skipped_no_transcription = 0

    for match in raw_matches:
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

        if not polygon:
            skipped_no_polygon += 1
        if not transcription:
            skipped_no_transcription += 1

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

    logger.info(f"  Final result: {len(text_lines)} text lines with polygon+transcription")
    if skipped_no_polygon:
        logger.warning(f"  Skipped {skipped_no_polygon} lines with no polygon")
    if skipped_no_transcription:
        logger.warning(f"  Skipped {skipped_no_transcription} lines with no transcription")
    if text_lines:
        logger.info(f"  First line: '{text_lines[0].transcription[:80]}'")

    return AltoData(
        text_lines=text_lines,
        page_width=page_width,
        page_height=page_height,
        full_text="\n".join(transcription_lines),
    )
