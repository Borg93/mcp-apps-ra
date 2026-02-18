"""IIIF manifest and image service utilities."""

import logging

import httpx

logger = logging.getLogger(__name__)


def fetch_iiif_info(image_url: str) -> dict | None:
    """Fetch info.json for a IIIF image URL.

    Tries to derive the info.json endpoint from the image URL.
    Returns the parsed JSON dict, or None if not a IIIF image.
    """
    # Strip trailing segments to get the base image service URL
    # e.g. https://lbiiif.riksarkivet.se/arkis!A0068523_00007/full/1000,/0/default.jpg
    #   -> https://lbiiif.riksarkivet.se/arkis!A0068523_00007/info.json
    info_url = _derive_info_url(image_url)
    logger.info(f"fetch_iiif_info: image_url={image_url} -> info_url={info_url}")
    if not info_url:
        logger.warning(f"fetch_iiif_info: could not derive info.json URL")
        return None

    try:
        resp = httpx.get(info_url, timeout=15.0)
        logger.info(f"fetch_iiif_info: status={resp.status_code}")
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"fetch_iiif_info: got IIIF info, id={data.get('id') or data.get('@id', 'N/A')}, "
                     f"width={data.get('width')}, height={data.get('height')}")
        return data
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"fetch_iiif_info: failed with {type(e).__name__}: {e}")
        return None


def _derive_info_url(image_url: str) -> str | None:
    """Derive info.json URL from a IIIF image URL or base URL."""
    url = image_url.rstrip("/")

    # Already an info.json URL
    if url.endswith("/info.json"):
        return url

    # IIIF Image API URL: {base}/{region}/{size}/{rotation}/{quality}.{format}
    # Try stripping /full/.../0/default.jpg pattern
    parts = url.split("/")
    for i, part in enumerate(parts):
        if part == "full" and i >= 1:
            base = "/".join(parts[:i])
            return f"{base}/info.json"

    # Maybe it's already just the base identifier URL
    return f"{url}/info.json"


def fetch_manifest(manifest_url: str) -> dict:
    """Fetch and return a IIIF Presentation manifest."""
    resp = httpx.get(manifest_url, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def parse_manifest_pages(manifest: dict) -> list[dict]:
    """Extract page data from a IIIF Presentation manifest.

    Returns a list of dicts with:
        - page_number: 1-indexed page number
        - label: canvas label
        - image_service: IIIF tile config for OSD
        - page_width: canvas width
        - page_height: canvas height
        - image_id: extracted image identifier for ALTO fetching
    """
    pages = []

    # Handle both Presentation API 2 and 3
    canvases = manifest.get("sequences", [{}])[0].get("canvases", []) if "sequences" in manifest else manifest.get("items", [])

    for idx, canvas in enumerate(canvases):
        width = canvas.get("width", 0)
        height = canvas.get("height", 0)
        label = _extract_label(canvas.get("label", ""))

        # Get image resource and service
        image_service, image_id = _extract_image_service(canvas)

        if image_service:
            pages.append({
                "page_number": idx + 1,
                "label": label or f"Page {idx + 1}",
                "image_service": image_service,
                "page_width": width,
                "page_height": height,
                "image_id": image_id,
            })

    return pages


def _extract_label(label) -> str:
    """Extract a string label from various IIIF label formats."""
    if isinstance(label, str):
        return label
    if isinstance(label, dict):
        # Presentation 3: {"en": ["Page 1"]}
        for values in label.values():
            if isinstance(values, list) and values:
                return str(values[0])
    if isinstance(label, list) and label:
        return str(label[0])
    return ""


def _extract_image_service(canvas: dict) -> tuple[dict, str]:
    """Extract IIIF image service config and image_id from a canvas.

    Handles both Presentation API 2 and 3 structures.
    Returns (service_config, image_id).
    """
    # Presentation API 2: canvas.images[].resource.service
    images = canvas.get("images", [])
    if images:
        resource = images[0].get("resource", {})
        service = resource.get("service")
        if isinstance(service, list):
            service = service[0] if service else None
        if isinstance(service, dict):
            return _build_service_config(service, resource)

    # Presentation API 3: canvas.items[].items[].body.service
    items = canvas.get("items", [])
    for annotation_page in items:
        for annotation in annotation_page.get("items", []):
            body = annotation.get("body", {})
            service = body.get("service")
            if isinstance(service, list):
                service = service[0] if service else None
            if isinstance(service, dict):
                return _build_service_config(service, body)

    return {}, ""


def _build_service_config(service: dict, resource: dict) -> tuple[dict, str]:
    """Build an OSD-compatible tile source config from a IIIF service."""
    service_id = service.get("@id") or service.get("id", "")
    image_id = _extract_image_id_from_service(service_id)

    # Build a config OSD can consume directly as a tile source
    config = {
        "@context": service.get("@context", "http://iiif.io/api/image/2/context.json"),
        "@id": service_id,
        "protocol": "http://iiif.io/api/image",
        "profile": service.get("profile", "http://iiif.io/api/image/2/level1.json"),
    }

    # Copy dimensions from resource if available
    width = resource.get("width") or service.get("width")
    height = resource.get("height") or service.get("height")
    if width:
        config["width"] = width
    if height:
        config["height"] = height

    # Copy tile info if present
    if "tiles" in service:
        config["tiles"] = service["tiles"]
    if "sizes" in service:
        config["sizes"] = service["sizes"]

    return config, image_id


def _extract_image_id_from_service(service_id: str) -> str:
    """Extract the Riksarkivet image ID from a service URL.

    e.g. 'https://lbiiif.riksarkivet.se/arkis!A0068523_00007'
    -> 'A0068523_00007'
    """
    if "arkis!" in service_id:
        return service_id.split("arkis!")[-1].rstrip("/")
    # Fallback: last path segment
    return service_id.rstrip("/").rsplit("/", 1)[-1]
