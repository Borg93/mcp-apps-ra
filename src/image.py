import base64

import httpx


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
