from pydantic import BaseModel


class TextLine(BaseModel):
    id: str
    polygon: str
    transcription: str
    hpos: int
    vpos: int
    width: int
    height: int


class AltoData(BaseModel):
    text_lines: list[TextLine]
    page_width: int
    page_height: int
    full_text: str
