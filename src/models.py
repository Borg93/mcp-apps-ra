from dataclasses import dataclass


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
