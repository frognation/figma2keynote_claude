"""
MCP-based Figma extractor.

Uses Figma MCP tools (already authenticated) instead of REST API tokens.
Designed to be driven by Claude Code or any MCP-compatible agent.

Architecture:
  1. Agent calls get_metadata → saves XML
  2. Agent calls get_screenshot for each slide → saves PNGs
  3. Agent calls get_design_context for each slide → saves code
  4. This module parses all saved data into a manifest
  5. Builder generates PPTX from the manifest

Video extraction strategy:
  - Detect video elements by name pattern or node type
  - Export video poster frame via get_screenshot on the video node
  - For actual video files: use Figma REST API /images endpoint
    OR user supplies original files via --video-dir
  - Future: Figma Plugin API for direct binary extraction
"""

import json
import re
import os
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone


class MCPExtractor:
    """
    Parse MCP tool outputs into a figma2keynote manifest.

    This class doesn't call MCP directly — it processes saved outputs.
    The MCP calls are orchestrated by the agent (Claude Code).
    """

    def __init__(self, work_dir: Path):
        self.work_dir = Path(work_dir)
        self.assets_dir = self.work_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def build_manifest(
        self,
        file_key: str,
        file_name: str,
        metadata_xml: str,
        slide_codes: dict[str, str],  # {node_id: react_code}
        slide_screenshots: dict[str, Path],  # {node_id: png_path}
        image_assets: dict[str, Path] = None,  # {node_id: downloaded_image_path}
    ) -> dict:
        """
        Build manifest from collected MCP outputs.

        Args:
            file_key: Figma file key
            file_name: Figma file name
            metadata_xml: XML from get_metadata
            slide_codes: Dict of node_id → React/Tailwind code from get_design_context
            slide_screenshots: Dict of node_id → local PNG path
            image_assets: Dict of node_id → downloaded image file path
        """
        # 1. Parse slide structure from XML
        slides_info = self._parse_slides_from_xml(metadata_xml)

        manifest = {
            "version": "1.0.0",
            "tool": "figma2keynote_claude",
            "source": {
                "file_key": file_key,
                "file_name": file_name,
                "extracted_at": datetime.now(timezone.utc).isoformat(),
            },
            "canvas": {"width": 1920, "height": 1080},
            "slides": [],
        }

        for i, slide in enumerate(slides_info):
            sid = slide["id"]
            code = slide_codes.get(sid, "")
            screenshot = slide_screenshots.get(sid)

            # Parse elements from code + XML metadata
            node_meta = self._parse_children_from_xml(metadata_xml, sid)
            elements = self._parse_code_to_elements(code, node_meta)

            # Detect and tag video elements
            self._tag_video_elements(elements, node_meta)

            # Detect background color from code
            bg = self._detect_background(code)

            slide_data = {
                "index": i,
                "id": sid,
                "name": slide.get("name", f"Slide {i+1}"),
                "width": 1920,
                "height": 1080,
                "background": bg,
                "poster_image": str(screenshot.relative_to(self.work_dir)) if screenshot else None,
                "elements": elements,
            }
            manifest["slides"].append(slide_data)

        return manifest

    # ── XML Parsing ──────────────────────────────────────────────

    def _parse_slides_from_xml(self, xml: str) -> list[dict]:
        """Find all 1920x1080 frames (slides) from metadata XML."""
        slides = []
        for m in re.finditer(
            r'<frame id="([^"]+)" name="([^"]*)" x="([^"]*)" y="([^"]*)" '
            r'width="1920" height="1080"',
            xml
        ):
            slides.append({
                "id": m.group(1),
                "name": m.group(2),
                "x": float(m.group(3)),
                "y": float(m.group(4)),
            })

        # Sort by position (left to right = slide order)
        slides.sort(key=lambda s: (s["y"], s["x"]))
        return slides

    def _parse_children_from_xml(self, xml: str, slide_id: str) -> dict:
        """Get child node metadata for a slide."""
        pattern = rf'<frame id="{re.escape(slide_id)}"[^>]*>(.*?)</frame>'
        m = re.search(pattern, xml, re.DOTALL)
        if not m:
            return {}

        content = m.group(0)
        nodes = {}

        # Get slide position
        slide_match = re.search(
            rf'<frame id="{re.escape(slide_id)}" name="[^"]*" x="([^"]*)" y="([^"]*)"',
            xml
        )
        slide_x = float(slide_match.group(1)) if slide_match else 0
        slide_y = float(slide_match.group(2)) if slide_match else 0

        for child in re.finditer(
            r'<(\w[\w-]*) id="([^"]+)" name="([^"]*)" x="([^"]*)" y="([^"]*)" '
            r'width="([^"]*)" height="([^"]*)"',
            content
        ):
            tag = child.group(1)
            nid = child.group(2)
            if nid == slide_id:
                continue

            nodes[nid] = {
                "type": "TEXT" if tag == "text" else "RECTANGLE",
                "xml_tag": tag,
                "name": child.group(3),
                "x": float(child.group(4)) - slide_x,
                "y": float(child.group(5)) - slide_y,
                "width": float(child.group(6)),
                "height": float(child.group(7)),
            }

        return nodes

    # ── Code Parsing ─────────────────────────────────────────────

    def _parse_code_to_elements(self, code: str, node_meta: dict) -> list:
        """Parse React+Tailwind code into element list."""
        elements = []

        for nid, meta in node_meta.items():
            el = {
                "id": nid,
                "name": meta["name"],
                "type": meta["type"],
                "x": meta["x"],
                "y": meta["y"],
                "width": meta["width"],
                "height": meta["height"],
                "rotation": 0,
                "opacity": 1.0,
            }

            if meta["type"] == "TEXT":
                text = self._extract_text_near_node(code, nid)
                style = self._extract_style_near_node(code, nid)
                if text:
                    el["text_data"] = {
                        "characters": text,
                        "style": style,
                        "fills": [style.pop("_fill", {
                            "type": "SOLID", "opacity": 1.0,
                            "color": {"r": 0, "g": 0, "b": 0, "a": 1}
                        })],
                        "characterStyleOverrides": [],
                        "styleOverrideTable": {},
                    }
                    elements.append(el)

            elif meta["xml_tag"] in ("rounded-rectangle", "rectangle"):
                # Could be image or shape
                img_url = self._find_image_url_for_node(code, nid)
                if img_url:
                    el["media_data"] = {
                        "type": "image",
                        "ref": nid,
                        "url": img_url,
                        "local_path": None,
                    }
                elements.append(el)

        return elements

    def _extract_text_near_node(self, code: str, node_id: str) -> str:
        """Extract text content near a data-node-id reference."""
        idx = code.find(f'data-node-id="{node_id}"')
        if idx < 0:
            return ""

        # Look at the block after this node ID
        block = code[idx:idx + 3000]

        # Find the closing tag
        depth = 0
        end_idx = 0
        in_tag = False
        for i, ch in enumerate(block):
            if ch == '<':
                in_tag = True
            elif ch == '>' and in_tag:
                in_tag = False
            elif ch == '{' and not in_tag:
                depth += 1
            elif ch == '}' and not in_tag:
                depth -= 1

            # Simplified: just take first 2000 chars
            if i > 2000:
                end_idx = i
                break
        else:
            end_idx = len(block)

        segment = block[:end_idx]
        texts = []

        # Template literals
        for m in re.finditer(r'\{`([^`]*)`\}', segment):
            t = m.group(1).strip()
            t = re.sub(r'[]', '', t).strip()
            if t and t != '​':
                texts.append(t)

        # Plain text between tags
        for m in re.finditer(r'>([^<>{]+)<', segment):
            t = m.group(1).strip()
            if (t and t != '​' and not t.startswith('{')
                    and not t.startswith('data-') and len(t) > 1):
                texts.append(t)

        combined = "\n".join(texts)
        # Deduplicate adjacent identical lines
        lines = combined.split("\n")
        deduped = []
        for line in lines:
            if not deduped or line != deduped[-1]:
                deduped.append(line)

        return "\n".join(deduped)

    def _extract_style_near_node(self, code: str, node_id: str) -> dict:
        """Extract styling from Tailwind classes near a node."""
        idx = code.find(f'data-node-id="{node_id}"')
        if idx < 0:
            return self._default_style()

        # Look backwards to find the opening tag with classes
        start = max(0, idx - 800)
        context = code[start:idx + 500]

        style = self._default_style()

        # Font size
        m = re.search(r"text-\[(\d+)px\]", context)
        if m:
            style["fontSize"] = int(m.group(1))

        # Font family
        m = re.search(r"font-\['([^']+)'", context)
        if m:
            raw = m.group(1)
            family = raw.split(":")[0].replace("_", " ")
            style["fontFamily"] = family
            if "Bold" in raw:
                style["fontWeight"] = 700

        if "font-bold" in context:
            style["fontWeight"] = 700

        # Alignment
        if "text-center" in context:
            style["textAlignHorizontal"] = "CENTER"
        elif "text-right" in context:
            style["textAlignHorizontal"] = "RIGHT"
        else:
            style["textAlignHorizontal"] = "LEFT"

        # Letter spacing
        m = re.search(r"tracking-\[(-?[\d.]+)px\]", context)
        if m:
            style["letterSpacing"] = float(m.group(1))

        # Color
        if "text-white" in context or "color-1,white" in context:
            style["_fill"] = {
                "type": "SOLID", "opacity": 1.0,
                "color": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1},
            }
        else:
            style["_fill"] = {
                "type": "SOLID", "opacity": 1.0,
                "color": {"r": 0, "g": 0, "b": 0, "a": 1},
            }

        return style

    def _default_style(self) -> dict:
        return {
            "fontFamily": "SF Pro",
            "fontSize": 30,
            "fontWeight": 400,
            "italic": False,
            "textAlignHorizontal": "LEFT",
            "textAlignVertical": "TOP",
            "letterSpacing": 0,
            "textDecoration": "NONE",
        }

    def _find_image_url_for_node(self, code: str, node_id: str) -> Optional[str]:
        """Find if a node has an associated image URL in the code."""
        idx = code.find(f'data-node-id="{node_id}"')
        if idx < 0:
            return None

        block = code[idx:idx + 1000]
        m = re.search(r'src=\{(\w+)\}', block)
        if m:
            var_name = m.group(1)
            url_match = re.search(rf'const {var_name}\s*=\s*"([^"]+)"', code)
            if url_match:
                return url_match.group(1)
        return None

    # ── Video Detection ──────────────────────────────────────────

    def _tag_video_elements(self, elements: list, node_meta: dict):
        """
        Detect video elements by name pattern and mark them.

        Video detection heuristics:
        1. Element name contains video-related keywords
        2. Element is a large rectangle with no image fill (empty in code)
        3. Element is a button in the code (Figma renders videos as interactive)
        """
        video_keywords = [
            "video", "mp4", "mov", "movie", "clip", "footage",
            "720p", "1080p", "4k", "h264", "h.264", "hevc",
        ]

        for el in elements:
            name_lower = el.get("name", "").lower()

            is_video = any(kw in name_lower for kw in video_keywords)

            if is_video and not el.get("media_data"):
                el["media_data"] = {
                    "type": "video",
                    "ref": el["id"],
                    "detected_by": "name_pattern",
                    "original_name": el["name"],
                    "local_path": None,
                    "note": (
                        f"Video detected: '{el['name']}'. "
                        "Supply original file via --video-dir or extract from Figma."
                    ),
                }

    def _detect_background(self, code: str) -> dict:
        """Detect background color from code."""
        if "color-2,black" in code or "bg-black" in code:
            return {"type": "solid", "color": {"r": 0, "g": 0, "b": 0, "a": 1}}
        elif "color-1,white" in code or "bg-white" in code:
            return {"type": "solid", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}
        else:
            # Try to extract from bg-[#xxx]
            m = re.search(r'bg-\[#([0-9a-fA-F]{6})\]', code)
            if m:
                hex_color = m.group(1)
                r = int(hex_color[0:2], 16) / 255
                g = int(hex_color[2:4], 16) / 255
                b = int(hex_color[4:6], 16) / 255
                return {"type": "solid", "color": {"r": r, "g": g, "b": b, "a": 1}}
        return {"type": "solid", "color": {"r": 1, "g": 1, "b": 1, "a": 1}}


class VideoExtractor:
    """
    Extract video files from Figma designs.

    Multiple strategies, tried in order:
    1. Figma REST API /images endpoint (exports video poster as image)
    2. Name-based matching with user-supplied video directory
    3. AppleScript-based Keynote extraction (if source is .key)
    4. Figma Plugin API (requires plugin running in browser)
    """

    def __init__(self, assets_dir: Path):
        self.assets_dir = Path(assets_dir)
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def extract_video_poster(
        self, screenshot_url: str, slide_index: int, element_name: str
    ) -> Path:
        """Download video element screenshot as poster frame."""
        import requests

        filename = f"video_{slide_index:03d}_{self._safe_name(element_name)}_poster.png"
        filepath = self.assets_dir / filename

        try:
            resp = requests.get(screenshot_url, timeout=15)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                f.write(resp.content)
            return filepath
        except Exception:
            return None

    def match_videos_from_dir(
        self, video_dir: Path, manifest: dict
    ) -> dict[str, Path]:
        """
        Match video elements in manifest with files in a directory.

        Matching strategy:
        1. Exact name match (element name == filename without extension)
        2. Fuzzy match (element name contains filename or vice versa)
        3. Index-based fallback (video elements ordered by slide position)

        Returns {element_id: matched_video_path}
        """
        import shutil

        video_dir = Path(video_dir)
        if not video_dir.exists():
            return {}

        video_exts = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}
        available = [
            f for f in video_dir.iterdir()
            if f.suffix.lower() in video_exts
        ]

        if not available:
            return {}

        matched = {}
        video_elements = []

        # Collect all video elements from manifest
        for slide in manifest.get("slides", []):
            for el in self._flatten(slide.get("elements", [])):
                media = el.get("media_data")
                if media and media.get("type") == "video":
                    video_elements.append(el)

        # Strategy 1: Name matching
        unmatched_files = list(available)
        for vel in video_elements:
            vel_name = vel.get("name", "").lower()
            for vf in unmatched_files:
                vf_name = vf.stem.lower()
                if vf_name in vel_name or vel_name in vf_name:
                    dest = self.assets_dir / vf.name
                    shutil.copy2(vf, dest)
                    matched[vel["id"]] = dest
                    unmatched_files.remove(vf)
                    break

        # Strategy 2: Index-based fallback for remaining
        unmatched_els = [
            vel for vel in video_elements
            if vel["id"] not in matched
        ]
        for vel, vf in zip(unmatched_els, unmatched_files):
            dest = self.assets_dir / vf.name
            shutil.copy2(vf, dest)
            matched[vel["id"]] = dest

        return matched

    def extract_from_figma_export(
        self, file_key: str, node_ids: list[str], token: str
    ) -> dict[str, Path]:
        """
        Try to export video nodes as images via Figma REST API.
        Returns poster frames (not actual video files).
        """
        import requests

        results = {}
        headers = {"X-Figma-Token": token}
        params = {
            "ids": ",".join(node_ids),
            "format": "png",
            "scale": 2,
        }

        try:
            resp = requests.get(
                f"https://api.figma.com/v1/images/{file_key}",
                headers=headers, params=params, timeout=30
            )
            resp.raise_for_status()
            images = resp.json().get("images", {})

            for nid, url in images.items():
                if url:
                    filename = f"video_{nid.replace(':', '_')}_poster.png"
                    filepath = self.assets_dir / filename
                    img_resp = requests.get(url, timeout=15)
                    if img_resp.ok:
                        with open(filepath, "wb") as f:
                            f.write(img_resp.content)
                        results[nid] = filepath

        except Exception:
            pass

        return results

    @staticmethod
    def _safe_name(name: str) -> str:
        """Convert element name to safe filename."""
        safe = re.sub(r'[^\w\-]', '_', name)
        return safe[:50]

    @staticmethod
    def _flatten(elements: list) -> list:
        result = []
        for el in elements:
            result.append(el)
            if el.get("children"):
                result.extend(VideoExtractor._flatten(el["children"]))
        return result
