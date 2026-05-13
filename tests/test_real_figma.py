#!/usr/bin/env python3
"""
End-to-end test: Real Figma data → PPTX generation.
Uses pre-fetched MCP data from the test design file.

Test file: figmatokeynote_test_0513 (design file copy)
File key: PSayE0KkSPlY6VxOuGc4Wt
"""

import sys
import json
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from keynote_builder.builder import KeynoteBuilder


def parse_tailwind_code_to_elements(code: str, node_metadata: dict) -> list:
    """
    Parse React+Tailwind code from Figma MCP into element dicts.
    Extracts text content, font sizes, colors, positions from Tailwind classes.
    """
    elements = []

    # Extract data-node-id and data-name
    node_blocks = re.finditer(
        r'data-node-id="([^"]+)"(?:\s+data-name="([^"]*)")?',
        code
    )

    for match in node_blocks:
        node_id = match.group(1)
        node_name = match.group(2) or ""

        # Skip the root frame itself
        meta = node_metadata.get(node_id)
        if not meta:
            continue

        el = {
            "id": node_id,
            "name": meta.get("name", node_name),
            "type": meta.get("type", "TEXT"),
            "x": meta.get("x", 0),
            "y": meta.get("y", 0),
            "width": meta.get("width", 100),
            "height": meta.get("height", 50),
            "rotation": 0,
            "opacity": 1.0,
        }

        # Find the surrounding context to extract text and style
        start = max(0, match.start() - 500)
        end = min(len(code), match.end() + 2000)
        context = code[start:end]

        # Extract text content
        text = _extract_text_from_jsx(context, node_id)
        if text:
            style = _extract_style_from_tailwind(context)
            el["type"] = "TEXT"
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

        # Check for image
        elif "img" in context and "src={" in context:
            img_match = re.search(r'src=\{(\w+)\}', context)
            if img_match:
                var_name = img_match.group(1)
                # Find URL in the full code
                url_match = re.search(
                    rf'const {var_name}\s*=\s*"([^"]+)"', code
                )
                if url_match:
                    el["type"] = "FRAME"
                    el["media_data"] = {
                        "type": "image",
                        "ref": var_name,
                        "url": url_match.group(1),
                        "local_path": None,
                    }
                    elements.append(el)

        # Check for video (button with empty div = video placeholder)
        elif "button" in context and ("Video" in node_name or "video" in node_name.lower()):
            el["type"] = "FRAME"
            el["media_data"] = {
                "type": "video",
                "ref": node_name,
                "local_path": None,
                "note": "Video element detected. Supply original file.",
            }
            elements.append(el)

    return elements


def _extract_text_from_jsx(context: str, node_id: str) -> str:
    """Extract plain text from JSX template literals and text nodes."""
    # Find the block after this node-id
    idx = context.find(f'data-node-id="{node_id}"')
    if idx < 0:
        return ""

    block = context[idx:]

    # Collect text from template literals {`...`} and plain text
    texts = []

    # Template literals
    for m in re.finditer(r'\{`([^`]*)`\}', block):
        t = m.group(1).replace("\\n", "\n").strip()
        # Remove unicode private use chars
        t = re.sub(r'[]', '', t).strip()
        if t:
            texts.append(t)

    # Plain text between tags (simplified)
    for m in re.finditer(r'>([^<>{]+)<', block):
        t = m.group(1).strip()
        if t and t not in ('​', '') and not t.startswith('{'):
            texts.append(t)

    return "\n".join(texts) if texts else ""


def _extract_style_from_tailwind(context: str) -> dict:
    """Extract font style from Tailwind classes in context."""
    style = {
        "fontFamily": "SF Pro",
        "fontSize": 30,
        "fontWeight": 400,
        "italic": False,
        "textAlignHorizontal": "CENTER",
        "textAlignVertical": "TOP",
        "letterSpacing": 0,
        "textDecoration": "NONE",
    }

    # Font size: text-[60px]
    m = re.search(r"text-\[(\d+)px\]", context)
    if m:
        style["fontSize"] = int(m.group(1))

    # Font family
    m = re.search(r"font-\['([^']+)'", context)
    if m:
        raw = m.group(1)
        # "SF_Pro:Bold" → "SF Pro"
        family = raw.split(":")[0].replace("_", " ")
        style["fontFamily"] = family

        if "Bold" in raw or "bold" in raw:
            style["fontWeight"] = 700
        if "Light" in raw:
            style["fontWeight"] = 300

    # Font weight
    if "font-bold" in context:
        style["fontWeight"] = 700
    elif "font-light" in context:
        style["fontWeight"] = 300

    # Text alignment
    if "text-center" in context:
        style["textAlignHorizontal"] = "CENTER"
    elif "text-right" in context:
        style["textAlignHorizontal"] = "RIGHT"
    elif "text-left" in context:
        style["textAlignHorizontal"] = "LEFT"

    # Letter spacing
    m = re.search(r"tracking-\[(-?[\d.]+)px\]", context)
    if m:
        style["letterSpacing"] = float(m.group(1))

    # Text color
    if "text-white" in context:
        style["_fill"] = {
            "type": "SOLID", "opacity": 1.0,
            "color": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1},
        }
    elif "text-black" in context:
        style["_fill"] = {
            "type": "SOLID", "opacity": 1.0,
            "color": {"r": 0, "g": 0, "b": 0, "a": 1},
        }
    else:
        # Default black
        style["_fill"] = {
            "type": "SOLID", "opacity": 1.0,
            "color": {"r": 0, "g": 0, "b": 0, "a": 1},
        }

    return style


def parse_metadata_xml_for_slide(xml_text: str, slide_id: str) -> dict:
    """Extract child node metadata from XML for a specific slide frame."""
    # Find the frame block
    pattern = rf'<frame id="{re.escape(slide_id)}"[^>]*>(.*?)</frame>'
    m = re.search(pattern, xml_text, re.DOTALL)
    if not m:
        return {}

    content = m.group(0)
    nodes = {}

    # Parse all child elements
    for child in re.finditer(
        r'<(\w[\w-]*) id="([^"]+)" name="([^"]*)" x="([^"]*)" y="([^"]*)" width="([^"]*)" height="([^"]*)"',
        content
    ):
        tag = child.group(1)
        nid = child.group(2)
        name = child.group(3)
        # Positions are absolute in the XML — we need relative to slide
        x = float(child.group(4))
        y = float(child.group(5))
        w = float(child.group(6))
        h = float(child.group(7))

        # Get slide position for relative calculation
        slide_match = re.search(
            rf'<frame id="{re.escape(slide_id)}" name="[^"]*" x="([^"]*)" y="([^"]*)"',
            xml_text
        )
        if slide_match:
            slide_x = float(slide_match.group(1))
            slide_y = float(slide_match.group(2))
            x -= slide_x
            y -= slide_y

        node_type = "TEXT" if tag == "text" else "RECTANGLE"
        nodes[nid] = {
            "type": node_type,
            "name": name,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
        }

    return nodes


def build_real_manifest():
    """Build manifest from actual Figma MCP data."""
    project_dir = Path(__file__).parent.parent
    test_dir = project_dir / "tests" / "real_test"
    assets_dir = test_dir / "assets"

    # Read the saved metadata XML
    metadata_file = Path(
        "/Users/jisungmacbook/.claude/projects/"
        "-Users-jisungmacbook-Dropbox--Personal--Moltbot-OBS-Projects-Apple-Giftcard/"
        "8b4fa440-f33e-43b6-9554-f90782201af0/tool-results/"
        "mcp-Figma-get_metadata-1778684088741.txt"
    )

    with open(metadata_file) as f:
        raw = json.load(f)
    xml_text = raw[0]["text"]

    # Slide definitions with MCP design context data
    slides_data = [
        {
            "id": "1:74",
            "index": 0,
            "name": "Title — Project Rufus",
            "bg_color": {"r": 1, "g": 1, "b": 1, "a": 1},
            "code": SLIDE_0_CODE,
        },
        {
            "id": "1:78",
            "index": 1,
            "name": "Intro Letter",
            "bg_color": {"r": 1, "g": 1, "b": 1, "a": 1},
            "code": SLIDE_1_CODE,
        },
        {
            "id": "1:80",
            "index": 2,
            "name": "Challenge & Ambition",
            "bg_color": {"r": 0, "g": 0, "b": 0, "a": 1},
            "code": SLIDE_2_CODE,
        },
        {
            "id": "1:470",
            "index": 3,
            "name": "Geometry of Magic (Video)",
            "bg_color": {"r": 0, "g": 0, "b": 0, "a": 1},
            "code": SLIDE_3_CODE,
        },
    ]

    manifest = {
        "version": "1.0.0",
        "tool": "figma2keynote_claude",
        "source": {
            "file_key": "PSayE0KkSPlY6VxOuGc4Wt",
            "file_name": "figmatokeynote_test_0513",
            "extracted_at": "2026-05-13T10:56:00+00:00",
        },
        "canvas": {"width": 1920, "height": 1080},
        "slides": [],
    }

    for sd in slides_data:
        # Parse metadata for this slide's children
        node_meta = parse_metadata_xml_for_slide(xml_text, sd["id"])

        # Parse code to extract elements
        elements = parse_tailwind_code_to_elements(sd["code"], node_meta)

        poster_path = assets_dir / f"slide_{sd['index']:03d}_poster.png"

        slide = {
            "index": sd["index"],
            "id": sd["id"],
            "name": sd["name"],
            "width": 1920,
            "height": 1080,
            "background": {
                "type": "solid",
                "color": sd["bg_color"],
            },
            "poster_image": str(poster_path.relative_to(test_dir)) if poster_path.exists() else None,
            "elements": elements,
        }
        manifest["slides"].append(slide)

    return manifest


# ── MCP Design Context code snippets (pre-fetched) ──────────────

SLIDE_0_CODE = '''
export default function Frame() {
  return (
    <div className="bg-[var(--color-1,white)] font-['SF_Pro:Regular',sans-serif] font-normal relative size-full text-[color:var(--color-2,black)] text-center" data-node-id="1:74" data-name="Frame">
      <p className="-translate-x-1/2 absolute leading-[0] left-[calc(50%+0.2px)] text-[0px] top-[calc(50%-132px)] tracking-[-2.2px] w-[2006.4px]" data-node-id="1:75" style={{ fontVariationSettings: "'wdth' 100" }}>
        <span className="font-['SF_Pro:Bold',sans-serif] font-bold leading-[1.2] text-[220px] text-black" style={{ fontVariationSettings: "'wdth' 100" }}>{`\\uF8FF `}</span>
        <span className="leading-[1.2] text-[220px]">Project Rufus</span>
      </p>
      <p className="-translate-x-1/2 absolute leading-[1.2] left-[calc(50%+4.5px)] text-[40px] top-[calc(95.83%-45px)] tracking-[-0.8px] whitespace-nowrap" data-node-id="1:76" style={{ fontVariationSettings: "'wdth' 100" }}>
        Base
      </p>
      <p className="-translate-x-1/2 absolute leading-[1.2] left-1/2 text-[30px] top-[calc(4.17%+3px)] tracking-[-0.6px] w-[1920px]" data-node-id="1:77" style={{ fontVariationSettings: "'wdth' 100" }}>
        May 13, 2026
      </p>
    </div>
  );
}
'''

SLIDE_1_CODE = '''
export default function Frame() {
  return (
    <div className="bg-[var(--color-1,white)] relative size-full" data-node-id="1:78" data-name="Frame">
      <div className="-translate-x-1/2 absolute font-['SF_Pro:Regular',sans-serif] font-normal leading-[0] left-1/2 text-[60px] text-[color:var(--color-2,black)] text-center top-[calc(45.83%-246px)] tracking-[-0.6px] w-[1904px] whitespace-pre-wrap" data-node-id="1:79" style={{ fontVariationSettings: "'wdth' 100" }}>
        <p className="leading-none mb-0">
          {`Hi Team`}
        </p>
        <p className="leading-none mb-0">{`Thank you for considering us for the `}</p>
        <p className="leading-none mb-0">opportunity to collaborate on Project Rufus.</p>
        <p className="leading-none mb-0">
          {`Five days of `}
          exploration, synthesis, and learning.
        </p>
        <p className="leading-none">Approach over fidelity.</p>
      </div>
    </div>
  );
}
'''

SLIDE_2_CODE = '''
export default function Frame() {
  return (
    <div className="bg-[var(--color-2,black)] font-['SF_Pro:Regular',sans-serif] font-normal relative size-full text-[color:var(--color-1,white)] text-center" data-node-id="1:80" data-name="Frame">
      <div className="-translate-x-1/2 absolute leading-[0] left-1/2 text-[0px] top-[calc(45.83%-263px)] w-[1824px] whitespace-pre-wrap" data-node-id="1:81" style={{ fontVariationSettings: "'wdth' 100" }}>
        <p className="leading-[1.1] mb-0 text-[40px] text-white">Challenge</p>
        <p className="leading-[1.1] mb-0 text-[90px]">
          AGC is often perceived as being limited
          to Apple products alone.
        </p>
        <p className="leading-[1.1] mb-0 text-[40px] text-white">
          Success
        </p>
        <p className="leading-[1.1] text-[90px]">
          Shift the perception of AGC from too
          niche to everyday appeal.
        </p>
      </div>
      <p className="-translate-x-1/2 absolute leading-[1.2] left-1/2 text-[30px] top-[calc(4.17%+3px)] w-[1920px]" data-node-id="1:82" style={{ fontVariationSettings: "'wdth' 100" }}>{`CHALLENGE & AMBITION`}</p>
    </div>
  );
}
'''

SLIDE_3_CODE = '''
const img684630Ac = "https://www.figma.com/api/mcp/asset/faaf6131-05d0-44b1-9ef5-2954d4661210";

export default function Frame() {
  return (
    <div className="bg-[var(--color-2,black)] relative size-full" data-node-id="1:470" data-name="Frame">
      <p className="-translate-x-1/2 absolute font-['SF_Pro:Regular',sans-serif] font-normal leading-[1.2] left-1/2 text-[30px] text-[color:var(--color-1,white)] text-center top-[calc(4.17%+3px)] whitespace-nowrap" data-node-id="1:471" style={{ fontVariationSettings: "'wdth' 100" }}>{`GEOMETRY OF MAGIC `}</p>
      <button className="absolute block cursor-pointer h-[523px] left-[48px] top-[calc(8.33%+77px)] w-[932px]" data-node-id="1:472" data-name="Grizzly Bear - gun-shy [Official Music Video] - Grizzly Bear (720p, h264) 1">
        <div className="absolute inset-0 overflow-hidden" />
      </button>
      <div className="absolute aspect-[423/674] left-[52.66%] right-[25.31%] top-[calc(8.33%+77px)]" data-node-id="1:473" data-name="684630ac-848d-446c-a8e8-d02688152332 1">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <img alt="" className="absolute h-[111.28%] left-0 max-w-none top-0 w-full" src={img684630Ac} />
        </div>
      </div>
      <ol className="absolute block font-['BaseGrotesk:Regular',sans-serif] leading-[0] left-[calc(20.83%-368px)] list-decimal not-italic text-[45px] text-[color:var(--color-1,white)] top-[calc(70.83%-46px)] w-[900px]" data-node-id="1:474" start="1">
        <li className="ms-[67.5px] whitespace-pre-wrap">
          <span className="leading-none">
            {`Systemic & mathematical cards creating magical patterns.`}
          </span>
        </li>
      </ol>
      <ol className="absolute block font-['BaseGrotesk:Regular',sans-serif] leading-[0] left-[calc(62.5%-207px)] list-decimal not-italic text-[45px] text-[color:var(--color-1,white)] top-[calc(91.67%-102px)] w-[445px]" data-node-id="1:475" start="2">
        <li className="ms-[67.5px]">
          <span className="leading-none">{`All elements sharing uniform card sizes `}</span>
        </li>
      </ol>
      <button className="absolute block cursor-pointer h-[666px] left-[calc(75%+46px)] top-[calc(8.33%+77px)] w-[375px]" data-node-id="1:476" data-name="original_fb505271f65edbc901e4178bd3dc50ef 5">
        <div className="absolute inset-0 overflow-hidden" />
      </button>
      <ol className="absolute block font-['BaseGrotesk:Regular',sans-serif] leading-[0] left-[calc(87.5%-229px)] list-decimal not-italic text-[45px] text-[color:var(--color-1,white)] top-[calc(91.67%-102px)] w-[445px]" data-node-id="1:477" start="3">
        <li className="ms-[67.5px] whitespace-pre-wrap">
          <span className="leading-none">
            {`Inspired by Cardistry, but not mimicking`}
          </span>
        </li>
      </ol>
    </div>
  );
}
'''


def main():
    print("=" * 60)
    print("figma2keynote_claude — Real Figma Test (4 slides)")
    print("=" * 60)

    project_dir = Path(__file__).parent.parent
    test_dir = project_dir / "tests" / "real_test"
    assets_dir = test_dir / "assets"

    # 1. Build manifest from MCP data
    print("\n[1/4] Building manifest from Figma MCP data...")
    manifest = build_real_manifest()

    manifest_path = test_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    slide_count = len(manifest["slides"])
    total_elements = sum(len(s.get("elements", [])) for s in manifest["slides"])
    print(f"  {slide_count} slides, {total_elements} elements")

    # Print element breakdown
    for s in manifest["slides"]:
        text_els = [e for e in s["elements"] if e.get("text_data")]
        media_els = [e for e in s["elements"] if e.get("media_data")]
        print(f"  Slide {s['index']}: {s['name']} — "
              f"{len(text_els)} text, {len(media_els)} media")

    # 2. Download image assets from Figma MCP URLs
    print("\n[2/4] Downloading image assets...")
    import requests
    for slide in manifest["slides"]:
        for el in slide.get("elements", []):
            media = el.get("media_data")
            if media and media.get("type") == "image" and media.get("url"):
                filename = f"slide_{slide['index']:03d}_img_{el['id'].replace(':', '_')}.png"
                filepath = assets_dir / filename
                try:
                    resp = requests.get(media["url"], timeout=15)
                    resp.raise_for_status()
                    with open(filepath, "wb") as f:
                        f.write(resp.content)
                    media["local_path"] = str(filepath.relative_to(test_dir))
                    print(f"  Downloaded: {filename} ({len(resp.content):,} bytes)")
                except Exception as e:
                    print(f"  Failed: {filename} — {e}")

    # 3. Build PPTX
    print("\n[3/4] Building PPTX...")
    builder = KeynoteBuilder()
    output_path = test_dir / "figma_test_output.key"
    result = builder.build_from_manifest(manifest, assets_dir, output_path)

    print(f"  Output: {result}")
    print(f"  Size: {result.stat().st_size:,} bytes")

    # Verify
    import zipfile
    is_valid = zipfile.is_zipfile(str(result))
    print(f"  Valid PPTX: {is_valid}")

    # 4. Save updated manifest
    print("\n[4/4] Saving manifest...")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"  Manifest: {manifest_path}")

    print(f"\n{'=' * 60}")
    print(f"TEST COMPLETE — open {result} in Keynote to verify")
    print(f"{'=' * 60}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
