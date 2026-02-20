import logging
import re

import httpx

from src.models import AltoData, TextLine

logger = logging.getLogger(__name__)


def fetch_alto_xml_from_url(url: str) -> str:
    """Fetch ALTO XML from a URL."""
    logger.debug("Fetching ALTO XML: %s", url)
    response = httpx.get(url, timeout=30.0)
    response.raise_for_status()
    logger.debug("ALTO fetched: status=%d, length=%d", response.status_code, len(response.text))
    return response.text


def parse_alto_xml(xml_string: str) -> AltoData:
    """Parse ALTO XML and extract text lines with polygons."""
    text_lines: list[TextLine] = []
    transcription_lines: list[str] = []

    # Extract page dimensions
    page_match = re.search(r'<Page[^>]*WIDTH="(\d+)"[^>]*HEIGHT="(\d+)"', xml_string)
    if page_match:
        page_width = int(page_match.group(1))
        page_height = int(page_match.group(2))
    else:
        page_width = 6192
        page_height = 5432
        logger.warning("No <Page> dimensions found, using defaults: %dx%d", page_width, page_height)

    # Extract all TextLine elements
    text_line_pattern = re.compile(
        r'<TextLine[^>]*ID="([^"]*)"[^>]*HPOS="(\d+)"[^>]*VPOS="(\d+)"[^>]*HEIGHT="(\d+)"[^>]*WIDTH="(\d+)"[^>]*>([\s\S]*?)</TextLine>',
        re.MULTILINE,
    )

    skipped_no_polygon = 0
    skipped_no_transcription = 0

    for match in text_line_pattern.finditer(xml_string):
        line_id = match.group(1)
        hpos = int(match.group(2))
        vpos = int(match.group(3))
        height = int(match.group(4))
        width = int(match.group(5))
        line_content = match.group(6)

        polygon_match = re.search(r'<Polygon[^>]*POINTS="([^"]*)"', line_content)
        polygon = polygon_match.group(1) if polygon_match else ""

        word_matches = re.findall(r'<String[^>]*?CONTENT="([^"]*)"[^>]*>', line_content)
        wc_matches = re.findall(r'<String[^>]*?WC="([^"]*)"[^>]*>', line_content)
        transcription = " ".join(word_matches)

        # Compute line confidence as average of word WC values
        line_confidence: float | None = None
        if wc_matches:
            try:
                wc_values = [float(w) for w in wc_matches]
                line_confidence = sum(wc_values) / len(wc_values)
            except (ValueError, ZeroDivisionError):
                line_confidence = None

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
                    confidence=line_confidence,
                )
            )
            transcription_lines.append(transcription)

    logger.info("ALTO parsed: %d text lines, page %dx%d", len(text_lines), page_width, page_height)
    if skipped_no_polygon:
        logger.warning("Skipped %d lines with no polygon", skipped_no_polygon)
    if skipped_no_transcription:
        logger.warning("Skipped %d lines with no transcription", skipped_no_transcription)

    return AltoData(
        text_lines=text_lines,
        page_width=page_width,
        page_height=page_height,
        full_text="\n".join(transcription_lines),
    )


def parse_page_xml(xml_string: str) -> AltoData:
    """Parse PAGE XML and extract text lines with polygons."""
    text_lines: list[TextLine] = []
    transcription_lines: list[str] = []

    # Extract page dimensions
    page_match = re.search(r'<Page[^>]*imageWidth="(\d+)"[^>]*imageHeight="(\d+)"', xml_string)
    if page_match:
        page_width = int(page_match.group(1))
        page_height = int(page_match.group(2))
    else:
        page_width = 6192
        page_height = 5432
        logger.warning("No <Page> dimensions found, using defaults: %dx%d", page_width, page_height)

    # Extract all TextLine elements
    text_line_pattern = re.compile(
        r'<TextLine\s+id="([^"]*)"[^>]*>([\s\S]*?)</TextLine>',
        re.MULTILINE,
    )

    skipped_no_polygon = 0
    skipped_no_transcription = 0

    for match in text_line_pattern.finditer(xml_string):
        line_id = match.group(1)
        line_content = match.group(2)

        # Extract polygon from Coords points
        coords_match = re.search(r'<Coords\s+points="([^"]*)"', line_content)
        polygon = coords_match.group(1) if coords_match else ""

        # Extract transcription from TextEquiv > Unicode
        unicode_match = re.search(r'<Unicode>([\s\S]*?)</Unicode>', line_content)
        transcription = unicode_match.group(1).strip() if unicode_match else ""

        # Extract confidence from TextEquiv conf attribute
        conf_match = re.search(r'<TextEquiv\s+conf="([^"]*)"', line_content)
        line_confidence: float | None = None
        if conf_match:
            try:
                line_confidence = float(conf_match.group(1))
            except ValueError:
                line_confidence = None

        # Compute bounding box from polygon points
        hpos = vpos = width = height = 0
        if polygon:
            try:
                points = [tuple(int(v) for v in p.split(",")) for p in polygon.split()]
                xs = [p[0] for p in points]
                ys = [p[1] for p in points]
                hpos = min(xs)
                vpos = min(ys)
                width = max(xs) - hpos
                height = max(ys) - vpos
            except (ValueError, IndexError):
                pass

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
                    confidence=line_confidence,
                )
            )
            transcription_lines.append(transcription)

    logger.info("PAGE XML parsed: %d text lines, page %dx%d", len(text_lines), page_width, page_height)
    if skipped_no_polygon:
        logger.warning("Skipped %d lines with no polygon", skipped_no_polygon)
    if skipped_no_transcription:
        logger.warning("Skipped %d lines with no transcription", skipped_no_transcription)

    return AltoData(
        text_lines=text_lines,
        page_width=page_width,
        page_height=page_height,
        full_text="\n".join(transcription_lines),
    )


def detect_and_parse(xml_string: str) -> AltoData:
    """Auto-detect XML format (ALTO vs PAGE) and parse accordingly."""
    header = xml_string[:500]
    if "<PcGts" in header:
        return parse_page_xml(xml_string)
    return parse_alto_xml(xml_string)
