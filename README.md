# figma2keynote_claude

Figma Slides → Apple Keynote converter with full media support.

## Features (Target)
- **Editable text** — Native Keynote text objects, not rasterized images
- **Video embedding** — MP4/MOV files placed directly into .key
- **Layout preservation** — Absolute coordinate mapping from Figma to Keynote
- **Asset management** — All media exported to organized asset folder
- **Incremental sync** — Only changed slides update on re-export

## Architecture
```
Figma REST/Plugin API → JSON manifest + media files
                              ↓
                    keynote-builder (Python)
                              ↓
                      Native .key file
```

## Stack
- Python 3.11+ (keynote-parser, protobuf)
- Figma REST API / Plugin API
- Apple Keynote .key format (Snappy + Protobuf IWA)
