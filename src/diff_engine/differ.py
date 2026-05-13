"""
Diff engine for incremental Figma → Keynote sync.

Compares two manifest snapshots and identifies:
- New slides
- Deleted slides
- Modified slides (text changes, layout changes, media changes)

Produces a diff report that the builder can use to selectively update.
"""

import json
import hashlib
from pathlib import Path
from typing import Optional
from copy import deepcopy


class ManifestDiffer:
    """
    Compares two manifest files to detect changes.

    Usage:
        differ = ManifestDiffer()
        diff = differ.diff(old_manifest, new_manifest)
        # diff.changed_slides → list of slide IDs to re-export
    """

    def diff(self, old: dict, new: dict) -> "DiffResult":
        """Compare two manifests and return a DiffResult."""
        old_slides = {s["id"]: s for s in old.get("slides", [])}
        new_slides = {s["id"]: s for s in new.get("slides", [])}

        old_ids = set(old_slides.keys())
        new_ids = set(new_slides.keys())

        added = new_ids - old_ids
        removed = old_ids - new_ids
        common = old_ids & new_ids

        modified = {}
        unchanged = set()

        for sid in common:
            changes = self._compare_slides(old_slides[sid], new_slides[sid])
            if changes:
                modified[sid] = changes
            else:
                unchanged.add(sid)

        return DiffResult(
            added=added,
            removed=removed,
            modified=modified,
            unchanged=unchanged,
            old_manifest=old,
            new_manifest=new,
        )

    def _compare_slides(self, old_slide: dict, new_slide: dict) -> Optional[dict]:
        """
        Compare two slide dicts. Returns change details or None if identical.
        """
        changes = {}

        # Background change
        if old_slide.get("background") != new_slide.get("background"):
            changes["background"] = {
                "old": old_slide.get("background"),
                "new": new_slide.get("background"),
            }

        # Element-level comparison
        old_els = {e["id"]: e for e in self._flatten_elements(old_slide.get("elements", []))}
        new_els = {e["id"]: e for e in self._flatten_elements(new_slide.get("elements", []))}

        old_el_ids = set(old_els.keys())
        new_el_ids = set(new_els.keys())

        el_changes = {
            "added": list(new_el_ids - old_el_ids),
            "removed": list(old_el_ids - new_el_ids),
            "modified": [],
        }

        for eid in old_el_ids & new_el_ids:
            el_diff = self._compare_elements(old_els[eid], new_els[eid])
            if el_diff:
                el_changes["modified"].append({
                    "id": eid,
                    "changes": el_diff,
                })

        if (el_changes["added"] or el_changes["removed"] or el_changes["modified"]):
            changes["elements"] = el_changes

        return changes if changes else None

    def _compare_elements(self, old_el: dict, new_el: dict) -> Optional[dict]:
        """Compare two elements. Returns dict of changed fields."""
        changes = {}

        # Position/size
        for field in ("x", "y", "width", "height", "rotation", "opacity"):
            if abs(old_el.get(field, 0) - new_el.get(field, 0)) > 0.5:
                changes[field] = {"old": old_el.get(field), "new": new_el.get(field)}

        # Text content
        old_text = old_el.get("text_data", {}).get("characters", "")
        new_text = new_el.get("text_data", {}).get("characters", "")
        if old_text != new_text:
            changes["text_content"] = {"old": old_text, "new": new_text}

        # Text style
        old_style = old_el.get("text_data", {}).get("style", {})
        new_style = new_el.get("text_data", {}).get("style", {})
        if old_style != new_style:
            changes["text_style"] = {"old": old_style, "new": new_style}

        # Media
        old_media = old_el.get("media_data")
        new_media = new_el.get("media_data")
        if old_media != new_media:
            changes["media"] = {"old": old_media, "new": new_media}

        # Shape fills
        old_shape = old_el.get("shape_data", {}).get("fills", [])
        new_shape = new_el.get("shape_data", {}).get("fills", [])
        if old_shape != new_shape:
            changes["shape_fills"] = {"old": old_shape, "new": new_shape}

        return changes if changes else None

    def _flatten_elements(self, elements: list) -> list:
        """Flatten nested element tree into a flat list."""
        result = []
        for el in elements:
            result.append(el)
            if el.get("children"):
                result.extend(self._flatten_elements(el["children"]))
        return result


class DiffResult:
    """Structured diff result."""

    def __init__(self, added, removed, modified, unchanged, old_manifest, new_manifest):
        self.added = added            # set of slide IDs
        self.removed = removed        # set of slide IDs
        self.modified = modified      # {slide_id: {change details}}
        self.unchanged = unchanged    # set of slide IDs
        self.old_manifest = old_manifest
        self.new_manifest = new_manifest

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    @property
    def changed_slide_ids(self) -> set:
        return self.added | set(self.modified.keys())

    def summary(self) -> str:
        """Human-readable summary of changes."""
        lines = ["=== Figma → Keynote Diff Report ==="]

        if not self.has_changes:
            lines.append("No changes detected.")
            return "\n".join(lines)

        if self.added:
            lines.append(f"\n+ {len(self.added)} new slide(s)")
            for sid in self.added:
                new_slides = {s["id"]: s for s in self.new_manifest.get("slides", [])}
                name = new_slides.get(sid, {}).get("name", sid)
                lines.append(f"  + {name}")

        if self.removed:
            lines.append(f"\n- {len(self.removed)} removed slide(s)")
            for sid in self.removed:
                old_slides = {s["id"]: s for s in self.old_manifest.get("slides", [])}
                name = old_slides.get(sid, {}).get("name", sid)
                lines.append(f"  - {name}")

        if self.modified:
            lines.append(f"\n~ {len(self.modified)} modified slide(s)")
            for sid, changes in self.modified.items():
                new_slides = {s["id"]: s for s in self.new_manifest.get("slides", [])}
                name = new_slides.get(sid, {}).get("name", sid)
                change_types = list(changes.keys())
                lines.append(f"  ~ {name}: {', '.join(change_types)}")

                # Detail element-level changes
                if "elements" in changes:
                    el_ch = changes["elements"]
                    if el_ch.get("added"):
                        lines.append(f"    + {len(el_ch['added'])} new element(s)")
                    if el_ch.get("removed"):
                        lines.append(f"    - {len(el_ch['removed'])} removed element(s)")
                    for mod in el_ch.get("modified", []):
                        mod_fields = list(mod["changes"].keys())
                        lines.append(f"    ~ {mod['id']}: {', '.join(mod_fields)}")

        lines.append(f"\n= {len(self.unchanged)} unchanged slide(s)")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dict."""
        return {
            "added": list(self.added),
            "removed": list(self.removed),
            "modified": self.modified,
            "unchanged": list(self.unchanged),
            "summary": self.summary(),
        }


class ManifestStore:
    """
    Stores manifest snapshots for diff tracking.
    Saves to a .figma2keynote/ directory alongside the output.
    """

    def __init__(self, project_dir: Path):
        self.store_dir = Path(project_dir) / ".figma2keynote"
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save_snapshot(self, manifest: dict, label: str = "latest"):
        """Save a manifest snapshot."""
        path = self.store_dir / f"manifest_{label}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

    def load_snapshot(self, label: str = "latest") -> Optional[dict]:
        """Load a previous manifest snapshot."""
        path = self.store_dir / f"manifest_{label}.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def get_diff(self, new_manifest: dict) -> Optional[DiffResult]:
        """Compare new manifest against the latest saved snapshot."""
        old = self.load_snapshot("latest")
        if old is None:
            return None
        differ = ManifestDiffer()
        return differ.diff(old, new_manifest)
