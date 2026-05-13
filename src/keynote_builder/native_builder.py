"""
Native Keynote builder via AppleScript.

Instead of generating PPTX and asking Keynote to import it (fragile),
this builder drives Keynote directly through its AppleScript dictionary:
- make new document (sized to canvas)
- make new slide (one per manifest slide)
- make new text item (with object text + font/size/color)
- make new image (file path + position/size)
- make new movie (file path + position/size) ← NATIVE VIDEO EMBEDDING

The output is a real .key file that Keynote produces — no PPTX intermediate,
no conversion step, no compatibility issues.

Sandbox consideration:
  Keynote v15 is App-Sandboxed. AppleScript-driven `save` can only write to:
  - ~/Library/Containers/com.apple.Keynote/Data/Documents/
  - Locations the user has interactively granted (via Save dialog)
  Our solution: save to the sandbox path, then move/copy to the user's
  desired output location (which our non-sandboxed Python script can do).
"""

import os
import shutil
import subprocess
import json
from pathlib import Path
from typing import Optional


# Keynote v15 bundle ID. v14 uses com.apple.iWork.Keynote (older path).
KEYNOTE_BUNDLE_NEW = "com.apple.Keynote"
KEYNOTE_BUNDLE_OLD = "com.apple.iWork.Keynote"

# Sandbox-accessible Documents folder for the new Keynote app
SANDBOX_DOCS = Path.home() / "Library/Containers/com.apple.Keynote/Data/Documents"


class NativeKeynoteBuilder:
    """Build a native .key file by driving Keynote via AppleScript."""

    def __init__(self, bundle_id: Optional[str] = None):
        self.bundle_id = bundle_id or self._detect_keynote()

    @staticmethod
    def _detect_keynote() -> str:
        """Pick the newest available Keynote install."""
        for bid in (KEYNOTE_BUNDLE_NEW, KEYNOTE_BUNDLE_OLD):
            try:
                r = subprocess.run(
                    ["osascript", "-e", f'tell application id "{bid}" to version'],
                    capture_output=True, text=True, timeout=5,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return bid
            except Exception:
                continue
        return KEYNOTE_BUNDLE_NEW

    # ── AppleScript Execution ────────────────────────────────────

    def _run_script(self, script: str, timeout: int = 60) -> tuple[bool, str]:
        """
        Execute AppleScript via stdin (avoids shell escaping issues).
        Returns (success, output_or_error).
        """
        try:
            result = subprocess.run(
                ["osascript", "-"],
                input=script,
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                return True, result.stdout.strip()
            return False, result.stderr.strip()
        except subprocess.TimeoutExpired:
            return False, "Script timed out"
        except Exception as e:
            return False, str(e)

    @staticmethod
    def _escape_text_for_applescript(text: str) -> str:
        """
        Make text safe for embedding in an AppleScript string literal.
        - Strip Private Use Area Unicode (Apple logo etc.) — AppleScript can't handle them in literals
        - Escape backslashes and double quotes
        - Replace newlines with AppleScript's `return` concatenation handled separately
        """
        # Strip PUA chars (U+E000–U+F8FF) — they break AppleScript parsing
        cleaned = "".join(c for c in text if not (0xE000 <= ord(c) <= 0xF8FF))
        # Escape special AppleScript string chars
        cleaned = cleaned.replace("\\", "\\\\").replace('"', '\\"')
        # AppleScript string literals can contain real newlines, but we use \n as escape inside
        # We'll handle this by replacing newlines with a marker that becomes "return" in AS
        # For simplicity, just replace newlines with space (Keynote text frame wraps)
        cleaned = cleaned.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        return cleaned

    # ── Build Pipeline ───────────────────────────────────────────

    def build_from_manifest(
        self,
        manifest: dict,
        assets_dir: Path,
        output_path: Path,
        progress_callback=None,
    ) -> Optional[Path]:
        """
        Build a .key file from manifest.
        Returns the output path on success, None on failure.
        """
        assets_dir = Path(assets_dir).resolve()
        output_path = Path(output_path).resolve()

        # 1. Stage all media into a sandbox-accessible location
        # (Keynote needs to read the files; symlinks to ~/ paths work)
        staging_dir = SANDBOX_DOCS / "figma2keynote_staging"
        staging_dir.mkdir(parents=True, exist_ok=True)
        self._stage_media(assets_dir, staging_dir)

        # 2. Determine sandbox output path
        sandbox_output = SANDBOX_DOCS / output_path.name
        if not sandbox_output.suffix == ".key":
            sandbox_output = sandbox_output.with_suffix(".key")
        if sandbox_output.exists():
            shutil.rmtree(sandbox_output) if sandbox_output.is_dir() else sandbox_output.unlink()

        # 3. Create document
        canvas = manifest.get("canvas", {})
        width = int(canvas.get("width", 1920))
        height = int(canvas.get("height", 1080))

        if not self._create_document(width, height):
            return None

        # 4. Build each slide
        slides = manifest.get("slides", [])
        for i, slide_data in enumerate(slides):
            if progress_callback:
                progress_callback(i, len(slides), slide_data.get("name", ""))
            self._build_slide(slide_data, i, staging_dir, is_first=(i == 0))

        # 5. Save
        if not self._save_document(sandbox_output):
            return None

        # 6. Move to final location
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists():
            if output_path.is_dir():
                shutil.rmtree(output_path)
            else:
                output_path.unlink()
        shutil.move(str(sandbox_output), str(output_path))

        # 7. Clean up staging
        # (Keep media for debugging — uncomment to clean)
        # shutil.rmtree(staging_dir, ignore_errors=True)

        return output_path

    def _stage_media(self, assets_dir: Path, staging_dir: Path):
        """Copy/link all media assets into sandbox-accessible staging."""
        if not assets_dir.exists():
            return
        for src in assets_dir.iterdir():
            if src.is_file() and src.suffix.lower() in (
                ".png", ".jpg", ".jpeg", ".gif", ".webp",
                ".mp4", ".mov", ".m4v", ".webm", ".avi",
            ):
                dest = staging_dir / src.name
                if dest.exists():
                    dest.unlink()
                shutil.copy2(src, dest)

    # ── Document/Slide Creation ─────────────────────────────────

    def _create_document(self, width: int, height: int) -> bool:
        """Create new Keynote document with given dimensions."""
        # Use White theme for minimal interference
        script = f'''
        tell application id "{self.bundle_id}"
            activate
            try
                set newDoc to make new document with properties {{width:{width}, height:{height}}}
            on error
                set newDoc to make new document
            end try
            delay 1
            return "OK"
        end tell
        '''
        ok, _ = self._run_script(script, timeout=15)
        return ok

    def _build_slide(
        self,
        slide_data: dict,
        index: int,
        staging_dir: Path,
        is_first: bool,
    ) -> bool:
        """Build a single slide with all its elements."""
        idx_1based = index + 1

        # First slide already exists from document creation
        # Subsequent slides need to be added with Blank layout
        if not is_first:
            add_script = f'''
            tell application id "{self.bundle_id}"
                tell front document
                    set newSlide to make new slide at end of slides
                end tell
                return "OK"
            end tell
            '''
            self._run_script(add_script, timeout=15)

        # Set the slide to use the Blank layout + hide all default placeholders
        blank_layout_script = f'''
        tell application id "{self.bundle_id}"
            tell front document
                try
                    set base slide of slide {idx_1based} to slide layout "Blank"
                end try
                tell slide {idx_1based}
                    try
                        set title showing to false
                    end try
                    try
                        set body showing to false
                    end try
                end tell
            end tell
            return "OK"
        end tell
        '''
        self._run_script(blank_layout_script, timeout=10)

        # Add elements
        elements = slide_data.get("elements", [])
        for el in elements:
            self._add_element(el, idx_1based, staging_dir)

        # Cleanup: remove any empty text items that may have been left from placeholders
        cleanup_script = f'''
        tell application id "{self.bundle_id}"
            tell slide {idx_1based} of front document
                set toDelete to {{}}
                repeat with t in text items
                    try
                        if (object text of t as text) is "" then
                            set end of toDelete to t
                        end if
                    end try
                end repeat
                repeat with t in toDelete
                    try
                        delete t
                    end try
                end repeat
            end tell
            return "OK"
        end tell
        '''
        self._run_script(cleanup_script, timeout=10)

        return True

    def _add_element(self, el: dict, slide_num: int, staging_dir: Path):
        """Dispatch element creation by type."""
        el_type = el.get("type", "")
        media = el.get("media_data")

        if el_type == "TEXT" and el.get("text_data"):
            self._add_text(el, slide_num)
        elif media and media.get("type") == "image" and media.get("local_path"):
            local_name = Path(media["local_path"]).name
            staged = staging_dir / local_name
            if staged.exists():
                self._add_image(el, slide_num, staged)
        elif media and media.get("type") == "video" and media.get("local_path"):
            local_name = Path(media["local_path"]).name
            staged = staging_dir / local_name
            if staged.exists():
                self._add_movie(el, slide_num, staged)

    def _add_text(self, el: dict, slide_num: int) -> bool:
        """Add a text item with styling."""
        text_data = el["text_data"]
        raw_chars = text_data.get("characters", "")
        characters = self._escape_text_for_applescript(raw_chars)
        if not characters.strip():
            return False

        style = text_data.get("style", {})
        font_family = style.get("fontFamily", "Helvetica")
        font_size = max(6, min(int(style.get("fontSize") or 16), 400))
        font_weight = style.get("fontWeight", 400)
        italic = style.get("italic", False)

        # Color from fills
        fills = text_data.get("fills", [])
        if fills and fills[0].get("type") == "SOLID":
            c = fills[0].get("color", {})
            r = int(c.get("r", 0) * 65535)
            g = int(c.get("g", 0) * 65535)
            b = int(c.get("b", 0) * 65535)
        else:
            r, g, b = 0, 0, 0

        # Position/size (clip to >= 0)
        x = max(0, int(el.get("x", 0)))
        y = max(0, int(el.get("y", 0)))
        w = max(20, int(el.get("width", 200)))
        h = max(20, int(el.get("height", 50)))

        # Build script
        bold_modifier = ""
        if font_weight >= 700:
            # Try common bold variants
            if font_family.lower() == "sf pro":
                font_family = "SF Pro Bold"
            elif "bold" not in font_family.lower():
                font_family = f"{font_family} Bold"

        script = f'''
        tell application id "{self.bundle_id}"
            tell slide {slide_num} of front document
                set newText to make new text item with properties {{object text:"{characters}", position:{{{x}, {y}}}, width:{w}, height:{h}}}
                tell newText
                    try
                        set the size of object text to {font_size}
                        set the font of object text to "{font_family}"
                        set the color of object text to {{{r}, {g}, {b}}}
                    end try
                end tell
            end tell
            return "OK"
        end tell
        '''
        ok, err = self._run_script(script, timeout=15)
        return ok

    def _add_image(self, el: dict, slide_num: int, image_path: Path) -> bool:
        """Add an image element. Use 'file' property (POSIX file alias)."""
        x = max(0, int(el.get("x", 0)))
        y = max(0, int(el.get("y", 0)))
        w = max(20, int(el.get("width", 200)))
        h = max(20, int(el.get("height", 200)))

        script = f'''
        tell application id "{self.bundle_id}"
            tell slide {slide_num} of front document
                set imgFile to (POSIX file "{image_path}")
                set newImg to make new image with properties {{file:imgFile, position:{{{x}, {y}}}, width:{w}, height:{h}}}
            end tell
            return "OK"
        end tell
        '''
        ok, err = self._run_script(script, timeout=15)
        if not ok:
            print(f"  [image] {err}")
        return ok

    def _add_movie(self, el: dict, slide_num: int, video_path: Path) -> bool:
        """Add a movie (video) element — NATIVE Keynote video embedding.
        Uses POSIX file alias for the path (file name property requires it)."""
        x = max(0, int(el.get("x", 0)))
        y = max(0, int(el.get("y", 0)))
        w = max(20, int(el.get("width", 400)))
        h = max(20, int(el.get("height", 300)))

        script = f'''
        tell application id "{self.bundle_id}"
            tell slide {slide_num} of front document
                set vidFile to (POSIX file "{video_path}")
                set newMovie to make new movie with properties {{file name:vidFile, position:{{{x}, {y}}}, width:{w}, height:{h}}}
            end tell
            return "OK"
        end tell
        '''
        ok, err = self._run_script(script, timeout=60)
        if not ok:
            print(f"  [movie] {err}")
        return ok

    def _save_document(self, sandbox_path: Path) -> bool:
        """Save the front document as .key to a sandbox-accessible path."""
        script = f'''
        tell application id "{self.bundle_id}"
            set d to front document
            save d in POSIX file "{sandbox_path}"
        end tell
        return "OK"
        '''
        ok, err = self._run_script(script, timeout=60)
        if ok and sandbox_path.exists():
            return True
        return False
