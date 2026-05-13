#!/usr/bin/env python3
"""
Test the Keynote builder with a mock manifest (no Figma API needed).
Verifies that the PPTX output is generated correctly.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from keynote_builder.builder import KeynoteBuilder


def create_mock_manifest():
    """Create a realistic mock manifest for testing."""
    return {
        "version": "1.0.0",
        "tool": "figma2keynote_claude",
        "source": {
            "file_key": "TEST_KEY",
            "file_name": "Test Presentation",
            "extracted_at": "2026-05-13T00:00:00+00:00",
        },
        "canvas": {
            "width": 1920,
            "height": 1080,
        },
        "slides": [
            {
                "index": 0,
                "id": "slide-001",
                "name": "Title Slide",
                "width": 1920,
                "height": 1080,
                "background": {
                    "type": "solid",
                    "color": {"r": 0.1, "g": 0.1, "b": 0.15, "a": 1},
                },
                "poster_image": None,
                "elements": [
                    {
                        "id": "title-text",
                        "name": "Title",
                        "type": "TEXT",
                        "x": 200,
                        "y": 350,
                        "width": 1520,
                        "height": 120,
                        "rotation": 0,
                        "opacity": 1.0,
                        "text_data": {
                            "characters": "Hello from figma2keynote",
                            "style": {
                                "fontFamily": "Helvetica Neue",
                                "fontSize": 64,
                                "fontWeight": 700,
                                "italic": False,
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "CENTER",
                                "letterSpacing": -1.5,
                                "lineHeightPx": 76,
                                "textDecoration": "NONE",
                                "textCase": "ORIGINAL",
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "opacity": 1.0,
                                    "color": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1},
                                }
                            ],
                            "characterStyleOverrides": [],
                            "styleOverrideTable": {},
                        },
                    },
                    {
                        "id": "subtitle-text",
                        "name": "Subtitle",
                        "type": "TEXT",
                        "x": 300,
                        "y": 500,
                        "width": 1320,
                        "height": 60,
                        "rotation": 0,
                        "opacity": 0.7,
                        "text_data": {
                            "characters": "Figma Slides to Keynote with full media support",
                            "style": {
                                "fontFamily": "Helvetica Neue",
                                "fontSize": 24,
                                "fontWeight": 300,
                                "italic": False,
                                "textAlignHorizontal": "CENTER",
                                "textAlignVertical": "TOP",
                                "letterSpacing": 0,
                                "lineHeightPx": 32,
                                "textDecoration": "NONE",
                                "textCase": "ORIGINAL",
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "opacity": 1.0,
                                    "color": {"r": 0.7, "g": 0.7, "b": 0.8, "a": 1},
                                }
                            ],
                            "characterStyleOverrides": [],
                            "styleOverrideTable": {},
                        },
                    },
                    {
                        "id": "rect-bg",
                        "name": "Background Shape",
                        "type": "RECTANGLE",
                        "x": 100,
                        "y": 700,
                        "width": 1720,
                        "height": 200,
                        "rotation": 0,
                        "opacity": 0.3,
                        "shape_data": {
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "opacity": 0.3,
                                    "color": {"r": 0.2, "g": 0.4, "b": 0.8, "a": 1},
                                }
                            ],
                            "strokes": [],
                            "strokeWeight": 0,
                            "cornerRadius": 16,
                        },
                    },
                ],
            },
            {
                "index": 1,
                "id": "slide-002",
                "name": "Content Slide",
                "width": 1920,
                "height": 1080,
                "background": {
                    "type": "solid",
                    "color": {"r": 1, "g": 1, "b": 1, "a": 1},
                },
                "poster_image": None,
                "elements": [
                    {
                        "id": "heading",
                        "name": "Heading",
                        "type": "TEXT",
                        "x": 120,
                        "y": 80,
                        "width": 800,
                        "height": 60,
                        "rotation": 0,
                        "opacity": 1.0,
                        "text_data": {
                            "characters": "Key Features",
                            "style": {
                                "fontFamily": "Helvetica Neue",
                                "fontSize": 40,
                                "fontWeight": 700,
                                "italic": False,
                                "textAlignHorizontal": "LEFT",
                                "textAlignVertical": "TOP",
                                "letterSpacing": -0.5,
                                "textDecoration": "NONE",
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "opacity": 1.0,
                                    "color": {"r": 0.1, "g": 0.1, "b": 0.15, "a": 1},
                                }
                            ],
                            "characterStyleOverrides": [],
                            "styleOverrideTable": {},
                        },
                    },
                    {
                        "id": "body",
                        "name": "Body Text",
                        "type": "TEXT",
                        "x": 120,
                        "y": 180,
                        "width": 800,
                        "height": 400,
                        "rotation": 0,
                        "opacity": 1.0,
                        "text_data": {
                            "characters": "Editable text preserved\nVideo files embedded\nLayout coordinates mapped 1:1\nIncremental sync support",
                            "style": {
                                "fontFamily": "Helvetica Neue",
                                "fontSize": 24,
                                "fontWeight": 400,
                                "italic": False,
                                "textAlignHorizontal": "LEFT",
                                "textAlignVertical": "TOP",
                                "letterSpacing": 0,
                                "lineHeightPx": 36,
                                "textDecoration": "NONE",
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "opacity": 1.0,
                                    "color": {"r": 0.3, "g": 0.3, "b": 0.35, "a": 1},
                                }
                            ],
                            "characterStyleOverrides": [],
                            "styleOverrideTable": {},
                        },
                    },
                ],
            },
            {
                "index": 2,
                "id": "slide-003",
                "name": "Mixed Styles Slide",
                "width": 1920,
                "height": 1080,
                "background": {
                    "type": "solid",
                    "color": {"r": 0.95, "g": 0.95, "b": 0.97, "a": 1},
                },
                "poster_image": None,
                "elements": [
                    {
                        "id": "mixed-text",
                        "name": "Mixed Format Text",
                        "type": "TEXT",
                        "x": 120,
                        "y": 200,
                        "width": 1680,
                        "height": 300,
                        "rotation": 0,
                        "opacity": 1.0,
                        "text_data": {
                            "characters": "Bold and italic mixed formatting test",
                            "style": {
                                "fontFamily": "Helvetica Neue",
                                "fontSize": 32,
                                "fontWeight": 400,
                                "italic": False,
                                "textAlignHorizontal": "LEFT",
                                "textAlignVertical": "TOP",
                                "letterSpacing": 0,
                                "textDecoration": "NONE",
                            },
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "opacity": 1.0,
                                    "color": {"r": 0.15, "g": 0.15, "b": 0.2, "a": 1},
                                }
                            ],
                            "characterStyleOverrides": [
                                1, 1, 1, 1,  # "Bold"
                                0, 0, 0, 0, 0,  # " and "
                                2, 2, 2, 2, 2, 2,  # "italic"
                                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                            ],
                            "styleOverrideTable": {
                                "1": {
                                    "fontWeight": 700,
                                },
                                "2": {
                                    "italic": True,
                                    "fills": [
                                        {
                                            "type": "SOLID",
                                            "opacity": 1.0,
                                            "color": {"r": 0.2, "g": 0.4, "b": 0.9, "a": 1},
                                        }
                                    ],
                                },
                            },
                        },
                    },
                    {
                        "id": "ellipse",
                        "name": "Circle",
                        "type": "ELLIPSE",
                        "x": 1400,
                        "y": 400,
                        "width": 300,
                        "height": 300,
                        "rotation": 0,
                        "opacity": 0.8,
                        "shape_data": {
                            "fills": [
                                {
                                    "type": "SOLID",
                                    "opacity": 1.0,
                                    "color": {"r": 0.9, "g": 0.3, "b": 0.3, "a": 1},
                                }
                            ],
                            "strokes": [
                                {
                                    "type": "SOLID",
                                    "opacity": 1.0,
                                    "color": {"r": 0.7, "g": 0.1, "b": 0.1, "a": 1},
                                }
                            ],
                            "strokeWeight": 3,
                            "cornerRadius": 0,
                        },
                    },
                ],
            },
        ],
    }


def test_pptx_generation():
    """Test that PPTX is generated from mock manifest."""
    project_dir = Path(__file__).parent.parent
    output_dir = project_dir / "tests" / "output"
    output_dir.mkdir(exist_ok=True)
    assets_dir = output_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    manifest = create_mock_manifest()

    # Save manifest for inspection
    with open(output_dir / "test_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Build PPTX (no template → PPTX mode)
    builder = KeynoteBuilder()
    result = builder.build_from_manifest(
        manifest,
        assets_dir,
        output_dir / "test_output.key",
    )

    print(f"\n=== Test Results ===")
    print(f"Output file: {result}")
    print(f"File exists: {result.exists()}")
    print(f"File size: {result.stat().st_size:,} bytes")

    # Verify it's a valid PPTX (ZIP)
    import zipfile
    is_valid = zipfile.is_zipfile(str(result))
    print(f"Valid ZIP/PPTX: {is_valid}")

    if is_valid:
        with zipfile.ZipFile(str(result)) as zf:
            slide_files = [n for n in zf.namelist() if "slide" in n.lower()]
            print(f"Slide entries in archive: {len(slide_files)}")

    return result.exists() and is_valid


def test_diff_engine():
    """Test the diff engine with two manifests."""
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from diff_engine.differ import ManifestDiffer

    old = create_mock_manifest()

    # Create modified version
    import copy
    new = copy.deepcopy(old)

    # Modify text in slide 1
    new["slides"][0]["elements"][0]["text_data"]["characters"] = "Updated Title!"

    # Add a new slide
    new["slides"].append({
        "index": 3,
        "id": "slide-004",
        "name": "New Slide",
        "width": 1920,
        "height": 1080,
        "background": {"type": "solid", "color": {"r": 1, "g": 1, "b": 1, "a": 1}},
        "poster_image": None,
        "elements": [],
    })

    # Remove slide 3
    del new["slides"][2]

    differ = ManifestDiffer()
    result = differ.diff(old, new)

    print(f"\n=== Diff Test ===")
    print(result.summary())

    assert result.has_changes, "Should detect changes"
    assert "slide-004" in result.added, "Should detect new slide"
    assert "slide-003" in result.removed, "Should detect removed slide"
    assert "slide-001" in result.modified, "Should detect modified slide"
    print("\nAll diff assertions passed!")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("figma2keynote_claude — Builder & Diff Test")
    print("=" * 60)

    ok1 = test_pptx_generation()
    ok2 = test_diff_engine()

    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
