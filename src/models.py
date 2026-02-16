from pydantic import BaseModel, Field


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


class PageData(BaseModel):
    """One page/canvas of a document."""

    page_number: int = Field(alias="pageNumber")
    image_service: dict | None = Field(alias="imageService", default=None)
    image_url: str | None = Field(alias="imageUrl", default=None)
    page_width: int = Field(alias="pageWidth")
    page_height: int = Field(alias="pageHeight")
    text_lines: list[TextLine] = Field(alias="textLines", default=[])
    label: str = ""

    model_config = {"populate_by_name": True}


class ViewManifestResult(BaseModel):
    """Full manifest with all pages."""

    manifest_url: str = Field(alias="manifestUrl")
    title: str
    total_pages: int = Field(alias="totalPages")
    pages: list[PageData]

    model_config = {"populate_by_name": True}


class ViewDocumentResult(BaseModel):
    """Document from paired image_url + alto_url lists."""

    total_pages: int = Field(alias="totalPages")
    pages: list[PageData]

    model_config = {"populate_by_name": True}


class ViewDocumentError(BaseModel):
    """Error response when document fetching fails."""

    error: bool = True
    message: str

    model_config = {"populate_by_name": True}
