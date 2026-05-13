#!/usr/bin/env python3
"""
figma2keynote_claude — Figma Slides → Keynote converter

Usage:
    # Full export
    python main.py export --file-key <FIGMA_FILE_KEY> --output presentation.key

    # With specific node
    python main.py export --file-key <KEY> --node-id <NODE_ID> --output out.key

    # Incremental update (only changed slides)
    python main.py sync --file-key <KEY> --output presentation.key

    # Diff check (dry run)
    python main.py diff --file-key <KEY>

    # Extract only (manifest + assets, no .key build)
    python main.py extract --file-key <KEY> --output-dir ./extracted

Environment:
    FIGMA_ACCESS_TOKEN - Your Figma personal access token
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from figma_extractor.api_client import FigmaClient, SlideExtractor
from keynote_builder.builder import KeynoteBuilder
from diff_engine.differ import ManifestDiffer, ManifestStore


def cmd_export(args):
    """Full export: Figma → manifest → .key/.pptx"""
    print(f"[figma2keynote] Starting full export...")
    print(f"  File key: {args.file_key}")
    print(f"  Output:   {args.output}")

    # 1. Extract from Figma
    client = FigmaClient(token=args.token)
    output_dir = Path(args.output).parent / f".figma2keynote_work"
    output_dir.mkdir(parents=True, exist_ok=True)

    extractor = SlideExtractor(client, output_dir)
    manifest = extractor.extract(args.file_key, node_id=args.node_id)

    slide_count = len(manifest.get("slides", []))
    print(f"  Extracted {slide_count} slide(s)")

    # Count media
    media_count = _count_media(manifest)
    print(f"  Media files: {media_count['images']} images, {media_count['videos']} videos")

    # 2. Handle video files that need manual supply
    video_gaps = _find_video_gaps(manifest)
    if video_gaps:
        print(f"\n  [!] {len(video_gaps)} video(s) need manual file supply:")
        for vg in video_gaps:
            print(f"      Slide {vg['slide']}, element {vg['element']}: ref={vg['ref']}")
        if args.video_dir:
            _try_match_videos(manifest, args.video_dir, output_dir / "assets")

    # 3. Build Keynote/PPTX
    template_path = Path(args.template) if args.template else None
    builder = KeynoteBuilder(template_path=template_path)

    output_path = Path(args.output)
    result_path = builder.build_from_manifest(
        manifest,
        output_dir / "assets",
        output_path,
    )

    print(f"\n  Output: {result_path}")

    # 4. Save manifest snapshot for future diffs
    store = ManifestStore(output_path.parent)
    store.save_snapshot(manifest, "latest")

    # 5. Copy assets to organized folder if requested
    if args.assets_dir:
        _organize_assets(output_dir / "assets", Path(args.assets_dir))
        print(f"  Assets copied to: {args.assets_dir}")

    print(f"[figma2keynote] Export complete!")
    return 0


def cmd_sync(args):
    """Incremental sync: only update changed slides."""
    print(f"[figma2keynote] Starting incremental sync...")

    # 1. Extract fresh manifest
    client = FigmaClient(token=args.token)
    output_dir = Path(args.output).parent / f".figma2keynote_work"
    output_dir.mkdir(parents=True, exist_ok=True)

    extractor = SlideExtractor(client, output_dir)
    new_manifest = extractor.extract(args.file_key, node_id=args.node_id)

    # 2. Load previous manifest
    store = ManifestStore(Path(args.output).parent)
    old_manifest = store.load_snapshot("latest")

    if old_manifest is None:
        print("  No previous snapshot found. Running full export instead.")
        args_copy = argparse.Namespace(**vars(args))
        return cmd_export(args_copy)

    # 3. Diff
    differ = ManifestDiffer()
    diff_result = differ.diff(old_manifest, new_manifest)

    print(diff_result.summary())

    if not diff_result.has_changes:
        print("\n[figma2keynote] No changes. Skipping rebuild.")
        return 0

    # 4. Rebuild (for now, full rebuild — selective update is Phase 3)
    template_path = Path(args.template) if args.template else None
    builder = KeynoteBuilder(template_path=template_path)

    if args.video_dir:
        _try_match_videos(new_manifest, args.video_dir, output_dir / "assets")

    output_path = Path(args.output)
    result_path = builder.build_from_manifest(
        new_manifest,
        output_dir / "assets",
        output_path,
    )

    # 5. Save new snapshot
    store.save_snapshot(new_manifest, "latest")

    # Archive old snapshot
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    store.save_snapshot(old_manifest, f"archive_{timestamp}")

    # Save diff report
    diff_path = store.store_dir / f"diff_{timestamp}.json"
    with open(diff_path, "w", encoding="utf-8") as f:
        json.dump(diff_result.to_dict(), f, indent=2, ensure_ascii=False)

    print(f"\n  Output: {result_path}")
    print(f"  Diff report: {diff_path}")
    print(f"[figma2keynote] Sync complete!")
    return 0


def cmd_diff(args):
    """Dry-run diff check without rebuilding."""
    print(f"[figma2keynote] Checking for changes...")

    client = FigmaClient(token=args.token)
    output_dir = Path(args.output_dir or ".") / ".figma2keynote_work"
    output_dir.mkdir(parents=True, exist_ok=True)

    extractor = SlideExtractor(client, output_dir)
    new_manifest = extractor.extract(args.file_key, node_id=args.node_id)

    store = ManifestStore(Path(args.output_dir or "."))
    old_manifest = store.load_snapshot("latest")

    if old_manifest is None:
        print("  No previous snapshot. All slides are new.")
        for s in new_manifest.get("slides", []):
            print(f"  + {s.get('name', s['id'])}")
        return 0

    differ = ManifestDiffer()
    diff_result = differ.diff(old_manifest, new_manifest)
    print(diff_result.summary())

    return 0


def cmd_extract(args):
    """Extract only: manifest + assets, no .key build."""
    print(f"[figma2keynote] Extracting from Figma...")

    client = FigmaClient(token=args.token)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    extractor = SlideExtractor(client, output_dir)
    manifest = extractor.extract(args.file_key, node_id=args.node_id)

    slide_count = len(manifest.get("slides", []))
    media_count = _count_media(manifest)

    print(f"  {slide_count} slide(s) extracted")
    print(f"  {media_count['images']} images, {media_count['videos']} videos")
    print(f"  Manifest: {output_dir / 'manifest.json'}")
    print(f"  Assets:   {output_dir / 'assets'}/")
    print(f"[figma2keynote] Extraction complete!")
    return 0


# ── Helpers ──────────────────────────────────────────────────────

def _count_media(manifest: dict) -> dict:
    """Count media files in manifest."""
    counts = {"images": 0, "videos": 0}
    for slide in manifest.get("slides", []):
        for el in _flatten(slide.get("elements", [])):
            media = el.get("media_data")
            if media:
                if media["type"] == "image":
                    counts["images"] += 1
                elif media["type"] == "video":
                    counts["videos"] += 1
    return counts


def _find_video_gaps(manifest: dict) -> list:
    """Find videos that need manual file supply."""
    gaps = []
    for slide in manifest.get("slides", []):
        for el in _flatten(slide.get("elements", [])):
            media = el.get("media_data")
            if media and media["type"] == "video" and not media.get("local_path"):
                gaps.append({
                    "slide": slide.get("name", slide["id"]),
                    "element": el.get("name", el["id"]),
                    "ref": media.get("ref"),
                })
    return gaps


def _try_match_videos(manifest: dict, video_dir: str, assets_dir: Path):
    """Try to match video refs with files in a user-supplied directory."""
    video_dir = Path(video_dir)
    if not video_dir.exists():
        return

    video_files = list(video_dir.glob("*.mp4")) + list(video_dir.glob("*.mov")) + \
                  list(video_dir.glob("*.m4v")) + list(video_dir.glob("*.webm"))

    import shutil
    for slide in manifest.get("slides", []):
        for el in _flatten(slide.get("elements", [])):
            media = el.get("media_data")
            if media and media["type"] == "video" and not media.get("local_path"):
                # Try name matching (element name or slide name)
                el_name = el.get("name", "").lower().replace(" ", "_")
                matched = None

                for vf in video_files:
                    if el_name and el_name in vf.stem.lower():
                        matched = vf
                        break

                if not matched and video_files:
                    # Fall back to index-based matching
                    slide_idx = slide.get("index", 0)
                    if slide_idx < len(video_files):
                        matched = video_files[slide_idx]

                if matched:
                    dest = assets_dir / matched.name
                    shutil.copy2(matched, dest)
                    media["local_path"] = str(dest.relative_to(assets_dir.parent))
                    print(f"  [*] Matched video: {matched.name} → {el.get('name')}")


def _organize_assets(src_dir: Path, dest_dir: Path):
    """Copy and organize assets into categorized folders."""
    import shutil

    categories = {
        "images": [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"],
        "videos": [".mp4", ".mov", ".m4v", ".webm", ".avi"],
        "posters": [],  # matched by name pattern
    }

    for cat in categories:
        (dest_dir / cat).mkdir(parents=True, exist_ok=True)

    for f in src_dir.iterdir():
        if not f.is_file():
            continue

        if "poster" in f.stem.lower():
            shutil.copy2(f, dest_dir / "posters" / f.name)
        elif f.suffix.lower() in categories["images"]:
            shutil.copy2(f, dest_dir / "images" / f.name)
        elif f.suffix.lower() in categories["videos"]:
            shutil.copy2(f, dest_dir / "videos" / f.name)
        else:
            shutil.copy2(f, dest_dir / f.name)


def _flatten(elements: list) -> list:
    """Flatten nested elements."""
    result = []
    for el in elements:
        result.append(el)
        if el.get("children"):
            result.extend(_flatten(el["children"]))
    return result


# ── CLI ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="figma2keynote",
        description="Convert Figma Slides to Apple Keynote presentations",
    )
    parser.add_argument(
        "--token", "-t",
        help="Figma access token (or set FIGMA_ACCESS_TOKEN env var)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # export
    p_export = subparsers.add_parser("export", help="Full export")
    p_export.add_argument("--file-key", "-f", required=True)
    p_export.add_argument("--node-id", "-n", default=None)
    p_export.add_argument("--output", "-o", required=True)
    p_export.add_argument("--template", help="Path to .key template")
    p_export.add_argument("--video-dir", help="Directory containing video files")
    p_export.add_argument("--assets-dir", help="Directory to organize assets into")

    # sync
    p_sync = subparsers.add_parser("sync", help="Incremental sync")
    p_sync.add_argument("--file-key", "-f", required=True)
    p_sync.add_argument("--node-id", "-n", default=None)
    p_sync.add_argument("--output", "-o", required=True)
    p_sync.add_argument("--template", help="Path to .key template")
    p_sync.add_argument("--video-dir", help="Directory containing video files")

    # diff
    p_diff = subparsers.add_parser("diff", help="Check for changes (dry run)")
    p_diff.add_argument("--file-key", "-f", required=True)
    p_diff.add_argument("--node-id", "-n", default=None)
    p_diff.add_argument("--output-dir", "-d", default=".")

    # extract
    p_extract = subparsers.add_parser("extract", help="Extract only (no build)")
    p_extract.add_argument("--file-key", "-f", required=True)
    p_extract.add_argument("--node-id", "-n", default=None)
    p_extract.add_argument("--output-dir", "-d", required=True)

    args = parser.parse_args()

    commands = {
        "export": cmd_export,
        "sync": cmd_sync,
        "diff": cmd_diff,
        "extract": cmd_extract,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
