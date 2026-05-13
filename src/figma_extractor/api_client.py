"""
Figma REST API client for extracting slide data.

Handles:
- File/node tree fetching
- Image export (PNG/SVG)
- Text node extraction with full style info
- Video/media detection and URL extraction
"""

import os
import json
import hashlib
import requests
from pathlib import Path
from typing import Optional


class FigmaClient:
    """Thin wrapper around Figma REST API."""

    BASE_URL = "https://api.figma.com/v1"

    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("FIGMA_ACCESS_TOKEN", "")
        if not self.token:
            raise ValueError(
                "Figma access token required. "
                "Set FIGMA_ACCESS_TOKEN env var or pass token= argument."
            )
        self.session = requests.Session()
        self.session.headers.update({"X-Figma-Token": self.token})

    # ── File & Node Tree ──────────────────────────────────────────

    def get_file(self, file_key: str, **params) -> dict:
        """Fetch full file JSON."""
        resp = self.session.get(f"{self.BASE_URL}/files/{file_key}", params=params)
        resp.raise_for_status()
        return resp.json()

    def get_file_nodes(self, file_key: str, node_ids: list[str], **params) -> dict:
        """Fetch specific nodes from a file."""
        params["ids"] = ",".join(node_ids)
        resp = self.session.get(f"{self.BASE_URL}/files/{file_key}/nodes", params=params)
        resp.raise_for_status()
        return resp.json()

    # ── Image Export ──────────────────────────────────────────────

    def export_images(
        self,
        file_key: str,
        node_ids: list[str],
        fmt: str = "png",
        scale: float = 2.0,
    ) -> dict[str, str]:
        """
        Export nodes as images. Returns {node_id: image_url}.
        fmt: 'png', 'jpg', 'svg', 'pdf'
        """
        params = {
            "ids": ",".join(node_ids),
            "format": fmt,
            "scale": scale,
        }
        resp = self.session.get(f"{self.BASE_URL}/images/{file_key}", params=params)
        resp.raise_for_status()
        return resp.json().get("images", {})

    def download_image(self, url: str, dest_path: Path) -> Path:
        """Download an image URL to local file."""
        resp = requests.get(url, stream=True)
        resp.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        return dest_path

    # ── Image Fill References ────────────────────────────────────

    def get_image_fills(self, file_key: str) -> dict[str, str]:
        """Get URLs for all image fills in a file. Returns {image_ref: url}."""
        resp = self.session.get(f"{self.BASE_URL}/files/{file_key}/images")
        resp.raise_for_status()
        return resp.json().get("meta", {}).get("images", {})


class SlideExtractor:
    """
    Extracts structured slide data from a Figma file.

    Produces a manifest JSON + downloads all media to an asset folder.
    """

    def __init__(self, client: FigmaClient, output_dir: Path):
        self.client = client
        self.output_dir = Path(output_dir)
        self.assets_dir = self.output_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def extract(self, file_key: str, node_id: Optional[str] = None) -> dict:
        """
        Main extraction entry point.
        Returns manifest dict and saves it + assets to output_dir.
        """
        # 1. Fetch file tree
        file_data = self.client.get_file(file_key, geometry="paths")
        document = file_data.get("document", {})
        file_name = file_data.get("name", "Untitled")

        # 2. Get image fills map (for resolving image refs → URLs)
        image_fills = self.client.get_image_fills(file_key)

        # 3. Find slide frames (top-level frames in pages, or specific node)
        slides = self._find_slides(document, node_id)

        # 4. Export each slide as high-res PNG (for fallback / poster)
        slide_node_ids = [s["id"] for s in slides]
        if slide_node_ids:
            slide_images = self.client.export_images(file_key, slide_node_ids)
        else:
            slide_images = {}

        # 5. Build manifest
        manifest = {
            "version": "1.0.0",
            "tool": "figma2keynote_claude",
            "source": {
                "file_key": file_key,
                "file_name": file_name,
                "extracted_at": self._now_iso(),
            },
            "canvas": {
                "width": 1920,
                "height": 1080,
            },
            "slides": [],
        }

        for i, slide in enumerate(slides):
            slide_data = self._process_slide(
                slide, i, file_key, image_fills, slide_images
            )
            manifest["slides"].append(slide_data)

        # 6. Save manifest
        manifest_path = self.output_dir / "manifest.json"
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        # 7. Save checksum for diff detection
        checksum = self._compute_manifest_checksum(manifest)
        manifest["_checksum"] = checksum

        return manifest

    # ── Internal: Slide Discovery ────────────────────────────────

    def _find_slides(self, document: dict, target_node_id: Optional[str] = None) -> list[dict]:
        """
        Find slide frames in the document.
        Figma Slides uses SLIDE type; regular files use top-level FRAME nodes.
        """
        slides = []

        for page in document.get("children", []):
            for child in page.get("children", []):
                # Figma Slides native type
                if child.get("type") in ("SLIDE", "FRAME"):
                    if target_node_id and child["id"] != target_node_id:
                        continue
                    slides.append(child)

        # Sort by vertical position (top to bottom) as slide order
        slides.sort(key=lambda s: (
            s.get("absoluteBoundingBox", {}).get("y", 0),
            s.get("absoluteBoundingBox", {}).get("x", 0),
        ))

        return slides

    # ── Internal: Slide Processing ───────────────────────────────

    def _process_slide(
        self, node: dict, index: int, file_key: str,
        image_fills: dict, slide_images: dict
    ) -> dict:
        """Process a single slide frame into manifest format."""
        bbox = node.get("absoluteBoundingBox", {})

        slide_data = {
            "index": index,
            "id": node["id"],
            "name": node.get("name", f"Slide {index + 1}"),
            "width": bbox.get("width", 1920),
            "height": bbox.get("height", 1080),
            "background": self._extract_background(node),
            "elements": [],
            "poster_image": None,
        }

        # Download slide poster image
        img_url = slide_images.get(node["id"])
        if img_url:
            poster_path = self.assets_dir / f"slide_{index:03d}_poster.png"
            self.client.download_image(img_url, poster_path)
            slide_data["poster_image"] = str(poster_path.relative_to(self.output_dir))

        # Recursively extract elements
        self._extract_elements(
            node, slide_data["elements"], bbox, file_key, image_fills, index
        )

        return slide_data

    def _extract_elements(
        self, node: dict, elements: list, slide_bbox: dict,
        file_key: str, image_fills: dict, slide_index: int,
        depth: int = 0
    ):
        """Recursively extract all elements from a node tree."""
        for child in node.get("children", []):
            if not child.get("visible", True):
                continue

            el_type = child.get("type", "")
            bbox = child.get("absoluteBoundingBox", {})

            # Calculate position relative to slide
            rel_x = bbox.get("x", 0) - slide_bbox.get("x", 0)
            rel_y = bbox.get("y", 0) - slide_bbox.get("y", 0)

            element = {
                "id": child["id"],
                "name": child.get("name", ""),
                "type": el_type,
                "x": rel_x,
                "y": rel_y,
                "width": bbox.get("width", 0),
                "height": bbox.get("height", 0),
                "rotation": child.get("rotation", 0),
                "opacity": child.get("opacity", 1.0),
            }

            if el_type == "TEXT":
                element["text_data"] = self._extract_text(child)
                elements.append(element)

            elif el_type in ("RECTANGLE", "ELLIPSE", "VECTOR", "STAR",
                             "LINE", "REGULAR_POLYGON", "BOOLEAN_OPERATION"):
                element["shape_data"] = self._extract_shape(child)
                # Check for image/video fills
                media = self._extract_media_fill(
                    child, image_fills, slide_index, len(elements)
                )
                if media:
                    element["media_data"] = media
                elements.append(element)

            elif el_type == "GROUP":
                element["children"] = []
                self._extract_elements(
                    child, element["children"], slide_bbox,
                    file_key, image_fills, slide_index, depth + 1
                )
                elements.append(element)

            elif el_type == "FRAME" or el_type == "COMPONENT" or el_type == "INSTANCE":
                # Nested frame — could contain media
                media = self._extract_media_fill(
                    child, image_fills, slide_index, len(elements)
                )
                if media:
                    element["media_data"] = media

                element["children"] = []
                self._extract_elements(
                    child, element["children"], slide_bbox,
                    file_key, image_fills, slide_index, depth + 1
                )
                elements.append(element)

            else:
                # Unknown type — still record position for fallback
                element["fallback"] = True
                elements.append(element)

    # ── Internal: Text Extraction ────────────────────────────────

    def _extract_text(self, node: dict) -> dict:
        """Extract text content with full style information."""
        style = node.get("style", {})
        char_styles = node.get("characterStyleOverrides", [])
        style_map = node.get("styleOverrideTable", {})

        text_data = {
            "characters": node.get("characters", ""),
            "style": {
                "fontFamily": style.get("fontFamily", "Helvetica"),
                "fontPostScriptName": style.get("fontPostScriptName"),
                "fontSize": style.get("fontSize", 16),
                "fontWeight": style.get("fontWeight", 400),
                "italic": style.get("italic", False),
                "textAlignHorizontal": node.get("textAlignHorizontal", "LEFT"),
                "textAlignVertical": node.get("textAlignVertical", "TOP"),
                "letterSpacing": style.get("letterSpacing", 0),
                "lineHeightPx": style.get("lineHeightPx"),
                "lineHeightPercent": style.get("lineHeightPercent"),
                "textDecoration": style.get("textDecoration", "NONE"),
                "textCase": style.get("textCase", "ORIGINAL"),
            },
            "fills": self._extract_fills(node.get("fills", [])),
            # Character-level style overrides for mixed formatting
            "characterStyleOverrides": char_styles,
            "styleOverrideTable": {
                str(k): self._extract_char_style_override(v)
                for k, v in style_map.items()
            } if style_map else {},
        }
        return text_data

    def _extract_char_style_override(self, override: dict) -> dict:
        """Extract a single character style override entry."""
        result = {}
        if "fontFamily" in override:
            result["fontFamily"] = override["fontFamily"]
        if "fontSize" in override:
            result["fontSize"] = override["fontSize"]
        if "fontWeight" in override:
            result["fontWeight"] = override["fontWeight"]
        if "italic" in override:
            result["italic"] = override["italic"]
        if "fills" in override:
            result["fills"] = self._extract_fills(override["fills"])
        if "letterSpacing" in override:
            result["letterSpacing"] = override["letterSpacing"]
        if "textDecoration" in override:
            result["textDecoration"] = override["textDecoration"]
        return result

    # ── Internal: Shape & Fill Extraction ────────────────────────

    def _extract_shape(self, node: dict) -> dict:
        """Extract shape properties."""
        return {
            "fills": self._extract_fills(node.get("fills", [])),
            "strokes": self._extract_fills(node.get("strokes", [])),
            "strokeWeight": node.get("strokeWeight", 0),
            "cornerRadius": node.get("cornerRadius", 0),
            "rectangleCornerRadii": node.get("rectangleCornerRadii"),
        }

    def _extract_fills(self, fills: list) -> list:
        """Extract fill/stroke info."""
        result = []
        for fill in fills:
            if not fill.get("visible", True):
                continue
            fill_data = {
                "type": fill.get("type", "SOLID"),
                "opacity": fill.get("opacity", 1.0),
            }
            if fill["type"] == "SOLID":
                color = fill.get("color", {})
                fill_data["color"] = {
                    "r": color.get("r", 0),
                    "g": color.get("g", 0),
                    "b": color.get("b", 0),
                    "a": color.get("a", 1),
                }
            elif fill["type"] == "IMAGE":
                fill_data["imageRef"] = fill.get("imageRef")
                fill_data["scaleMode"] = fill.get("scaleMode", "FILL")
            elif fill["type"] == "VIDEO":
                fill_data["videoRef"] = fill.get("videoRef")
            elif fill["type"] in ("GRADIENT_LINEAR", "GRADIENT_RADIAL",
                                  "GRADIENT_ANGULAR", "GRADIENT_DIAMOND"):
                fill_data["gradientStops"] = fill.get("gradientStops", [])
                fill_data["gradientHandlePositions"] = fill.get(
                    "gradientHandlePositions", []
                )
            result.append(fill_data)
        return result

    def _extract_media_fill(
        self, node: dict, image_fills: dict, slide_idx: int, el_idx: int
    ) -> Optional[dict]:
        """Detect and extract image/video fills, download assets."""
        fills = node.get("fills", [])
        for fill in fills:
            if not fill.get("visible", True):
                continue

            if fill.get("type") == "IMAGE" and fill.get("imageRef"):
                ref = fill["imageRef"]
                url = image_fills.get(ref)
                if url:
                    filename = f"slide_{slide_idx:03d}_img_{el_idx:03d}.png"
                    local_path = self.assets_dir / filename
                    self.client.download_image(url, local_path)
                    return {
                        "type": "image",
                        "ref": ref,
                        "local_path": str(local_path.relative_to(self.output_dir)),
                        "scale_mode": fill.get("scaleMode", "FILL"),
                    }

            if fill.get("type") == "VIDEO" and fill.get("videoRef"):
                # Video fills — the REST API may not provide direct download
                # We record the ref; the user may need to supply the file manually
                return {
                    "type": "video",
                    "ref": fill["videoRef"],
                    "local_path": None,  # To be filled by user or plugin
                    "note": "Video binary not available via REST API. "
                            "Supply the original video file manually.",
                }

        return None

    # ── Internal: Background ─────────────────────────────────────

    def _extract_background(self, node: dict) -> dict:
        """Extract slide background."""
        bg = node.get("backgroundColor") or node.get("background", [{}])
        if isinstance(bg, dict):
            return {
                "type": "solid",
                "color": {
                    "r": bg.get("r", 1), "g": bg.get("g", 1),
                    "b": bg.get("b", 1), "a": bg.get("a", 1),
                },
            }
        elif isinstance(bg, list) and bg:
            return self._extract_fills(bg)[0] if bg else {"type": "solid", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}
        return {"type": "solid", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}

    # ── Utilities ────────────────────────────────────────────────

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _compute_manifest_checksum(manifest: dict) -> str:
        """Compute a content hash for diff detection."""
        content = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
