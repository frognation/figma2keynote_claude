# figma2keynote_claude — Dev Log / 개발 로그

## 2026-05-13 — Project Kickoff / 프로젝트 착수

### Research Summary / 리서치 요약

**Problem / 문제:**
No existing tool converts Figma Slides → Keynote with video embedding + editable text.
Figma Slides → Keynote 변환 시 영상 포함 + 편집 가능 텍스트를 모두 지원하는 도구가 없음.

**Existing tools surveyed / 조사한 기존 도구:**

| Tool | What it does | Limitation |
|---|---|---|
| Pitchdeck (Figma plugin) | Figma → .pptx export | No video in export; commercial |
| aviranrevach/figma-to-keynote | SVG clipboard copy to Keynote | Per-frame only; no video/text |
| psobot/keynote-parser | Unpack/repack .key files (YAML ↔ Protobuf) | Read/write tool, not a converter |
| obriensp/iWorkFileFormat | .key Protobuf schema docs + .proto files | Documentation only |
| eth-siplab/SVG2Keynote-lib | SVG → Keynote vector conversion (C++) | C++ only; shapes only |

**Architecture decision / 아키텍처 결정:**
Hybrid approach — use python-pptx for reliable PPTX generation (Keynote reads PPTX natively with editable text), with optional AppleScript-based .pptx → .key conversion.
하이브리드 — python-pptx로 안정적 PPTX 생성(Keynote가 PPTX를 편집 가능 텍스트로 네이티브 읽기), 선택적 AppleScript 기반 .pptx → .key 변환.

**Why not direct .key generation? / 왜 직접 .key 생성이 아닌가?**
- .key format is undocumented Protobuf; creating from scratch is fragile
- keynote-parser requires an existing .key template to modify
- python-pptx is mature, stable, and Keynote has excellent .pptx compatibility
- Video embedding works in .pptx and Keynote preserves it when opening

### Implementation / 구현

**Phase 1 (Completed):**
- [x] Project structure + GitHub repo
- [x] Figma REST API extractor (text, images, video detection, layout)
- [x] Keynote builder via python-pptx (text boxes, shapes, images, video)
- [x] Character-level style override support (bold/italic mixed text)
- [x] Diff engine for incremental sync
- [x] Manifest store for snapshot comparison
- [x] CLI with export/sync/diff/extract commands
- [x] Mock tests passing

**Phase 2 (Next):**
- [ ] Test with real Figma file via REST API
- [ ] Video embedding test with actual .mp4 files
- [ ] AppleScript .pptx → .key auto-conversion
- [ ] Asset folder organization (images/videos/posters)
- [ ] Handle Figma Slides-specific node types (SLIDE, SLIDE_ROW, etc.)

**Phase 3 (Future):**
- [ ] Figma Plugin for direct video binary extraction
- [ ] Selective slide update (rebuild only changed slides)
- [ ] Gradient / shadow / blur style mapping
- [ ] Figma component → Keynote master slide mapping

### Key Technical Findings / 핵심 기술 발견

1. **Figma Video in REST API**: Video fills have `type: "VIDEO"` with a `videoRef`, but REST API doesn't expose video binary download. Plugin API's `exportAsync()` may work but needs testing.

2. **python-pptx video support**: `slide.shapes.add_movie()` embeds video directly into .pptx. Keynote opens these with full playback. This is the most reliable video embedding path.

3. **Keynote .pptx compatibility**: Keynote opens .pptx files with fully editable text, preserving fonts/sizes/colors. No rasterization. This is why PPTX-first approach works.

4. **Diff detection**: Comparing manifest JSON snapshots catches text changes, layout moves, media swaps. Element IDs from Figma are stable across re-fetches.

---

## GitHub
Repository: https://github.com/frognation/figma2keynote_claude
