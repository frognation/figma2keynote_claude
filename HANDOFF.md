# figma2keynote_claude — Handoff / 핸드오프 문서

> **세션 종료 시점:** 2026-05-13
> **GitHub:** https://github.com/frognation/figma2keynote_claude
> **위치:** `<Dropbox>/Moltbot/OBS/Projects/Apple Giftcard/figma2keynote_claude/`

---

## TL;DR (한 문장)

Figma 디자인을 Keynote로 변환하는 도구를 만들고 있고, **PPTX 우회 없이 AppleScript로 Keynote에 직접 슬라이드를 생성**하는 방식이 작동 검증됨. 텍스트·이미지는 완벽, 영상은 마지막 디버깅 직전에 중단.

---

## 전체 아키텍처 / Overall Architecture

```
Figma File
   │
   ├─ REST API ───────► 디자인 정보 (텍스트, 폰트, 좌표, 색)
   │                       └─► manifest.json (per-slide JSON)
   │
   ├─ REST API (images) ► 이미지 어셋 다운로드
   │                       └─► assets/*.png
   │
   ├─ MCP (보조) ────────► (현재 미사용, 향후 어셋 보강용)
   │
   └─ 영상 어셋 ────────► (사용자가 직접 supply, 또는 Figma 데스크탑 export)

                            │
                            ▼
              ┌─────────────────────────────┐
              │ NativeKeynoteBuilder        │
              │  (AppleScript via osascript)│
              └─────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────────┐
              │ Keynote v15 (com.apple.Keynote)│
              │  - make new document           │
              │  - make new slide              │
              │  - make new text item          │
              │  - make new image              │
              │  - make new movie  ←영상!      │
              │  - save (sandbox container)    │
              └─────────────────────────────┘
                            │
                            ▼
                     .key 파일 (네이티브)
                            │
                            ▼
              (사용자 출력 폴더로 자동 이동)
```

---

## 현재 상태 / Current Status

### ✅ 동작 검증됨
- **REST API 추출** — 정확한 JSON 데이터 (텍스트 220pt/40pt/30pt, 좌표 1:1)
- **Native Keynote .key 생성** — PPTX 없이 직접 .key 파일 생성
- **텍스트 임베딩** — 폰트/크기/색/위치 정확히 매핑
- **이미지 임베딩** — POSIX file alias 방식으로 작동
- **Keynote v15 고정** — `com.apple.Keynote` bundle ID로 신버전만 사용
- **샌드박스 우회** — 샌드박스 Documents에 저장 → 사용자 폴더로 이동
- **Blank 슬라이드 레이아웃** — placeholder 제거 자동화
- **Diff 엔진** — manifest 비교로 변경된 슬라이드 감지

### ⚠️ 진행 중 (중단된 지점)
- **영상 임베딩** — `_add_movie`를 POSIX file alias로 수정했지만 마지막 빌드 테스트 도중 멈춤
  - 수동 테스트로는 작동 확인됨 (osascript에서 직접 movie 생성 성공)
  - 빌더 통합 후 끝까지 검증 필요

### ❌ 미해결
- **Figma 영상 바이너리 추출** — REST API/MCP 둘 다 영상 파일 제공 안 함
  - 현재 워크어라운드: 사용자가 영상 파일을 `assets/`에 직접 넣음
  - 향후: Figma 데스크탑 앱을 AppleScript로 제어해 export 추출
- **글자 단위 스타일 오버라이드** — characterStyleOverrides 처리 미구현 (예: "Apple Logo + Project Rufus" 같이 한 텍스트 내 다른 폰트)
- **195개 슬라이드 전체 빌드** — 작은 슬라이드만 테스트, 풀 파일 미테스트
- **증분 싱크 통합** — Diff 엔진은 완성, 빌더와 연결 필요

---

## 핵심 발견 / Key Findings

### 1. 사용자 시스템에 Keynote 2개 설치돼 있음
| 위치 | 버전 | Bundle ID | 비고 |
|---|---|---|---|
| `/Applications/Keynote.app` | 14.5 | `com.apple.iWork.Keynote` | 구버전 (보존) |
| `/Applications/Keynote Creator Studio.app` | **15.2.1** | `com.apple.Keynote` | 신버전 (이거 사용) |

→ AppleScript에서 `tell application id "com.apple.Keynote"`로 신버전 고정

### 2. Keynote v15 App-Sandbox 적용됨
- `save` 명령은 `~/Library/Containers/com.apple.Keynote/Data/Documents/` 안에만 가능
- 우리 도구: 샌드박스에 저장 → Python(샌드박스 밖)이 사용자 폴더로 이동
- 미디어 파일도 샌드박스 stage path로 복사 후 참조 (`figma2keynote_staging/`)

### 3. AppleScript 객체 생성 시 POSIX file alias 필요
```applescript
-- ✗ 실패
set newMovie to make new movie with properties {file name:"/path/to/video.mp4", ...}

-- ✓ 성공
set vidFile to (POSIX file "/path/to/video.mp4")
set newMovie to make new movie with properties {file name:vidFile, ...}
```

### 4. PPTX 우회는 실패였음
- python-pptx로 생성한 PPTX를 Keynote v15가 import 거부 ("can't be imported")
- 결국 AppleScript로 Keynote 객체를 직접 생성하는 게 정답

---

## 파일 구조 / File Structure

```
figma2keynote_claude/
├── README.md
├── HANDOFF.md                    # ← 이 파일
├── docs/
│   └── DEVLOG.md                 # 초기 리서치 로그
├── requirements.txt
├── main.py                       # CLI 엔트리포인트 (export/sync/diff/extract)
├── setup_token.py                # 토큰 검증·저장
├── src/
│   ├── figma_extractor/
│   │   ├── api_client.py         # REST API + 토큰 관리
│   │   └── mcp_extractor.py      # MCP 기반 추출 (보조)
│   ├── keynote_builder/
│   │   ├── builder.py            # PPTX 빌더 (구버전, 더 이상 사용 X)
│   │   └── native_builder.py     # AppleScript 빌더 (현재 메인)
│   └── diff_engine/
│       └── differ.py             # manifest diff 엔진
└── tests/
    ├── test_builder_mock.py      # mock 데이터 테스트
    ├── test_real_figma.py        # MCP 기반 테스트 (구방식)
    ├── rest_test/                # 단일 슬라이드 추출/빌드 결과
    ├── img_test/                 # 이미지 슬라이드 (작동 ✓)
    └── video_test/               # 영상 슬라이드 (마지막 디버깅)
```

**중요 파일:**
- `src/keynote_builder/native_builder.py` — 메인 빌더 (모든 마법이 여기)
- `src/figma_extractor/api_client.py` — REST API 추출
- `main.py` — CLI

---

## 다음에 할 일 (TODO 리스트) / Next Steps

### 즉시 (in_progress)
- [ ] **영상 임베딩 최종 검증** — `_add_movie` POSIX 수정 후 풀빌드 테스트
  - 마지막 시도가 hang됨 (Keynote 프로세스 안 닫혀서일 수도 있음)
  - 깨끗한 환경에서 재시도

### 단기 (Phase 2)
- [ ] **하이브리드 어셋 추출기** — REST API + MCP 결합
- [ ] **영상 추출 전략 모듈** — Figma 데스크탑 AppleScript / 사용자 supply / poster fallback 3-단계
- [ ] **다중 슬라이드 빌드 테스트** (5개, 영상 슬라이드 포함)
- [ ] **풀 파일 빌드** (195 슬라이드)

### 중기 (Phase 3)
- [ ] **글자 단위 스타일 오버라이드** — `characterStyleOverrides` 처리
- [ ] **증분 싱크 통합** — `sync` 명령에서 변경된 슬라이드만 재빌드
- [ ] **그라데이션, 그림자, 블러** 스타일 매핑
- [ ] **Figma 컴포넌트 → Keynote 마스터 슬라이드**

---

## 테스트 파일 / Test Files

**Figma 디자인 파일 (테스트용):**
- 슬라이드 파일 (MCP 지원 X): https://www.figma.com/slides/M1nv3RcKTSR9DcGhJ6ogUw/figmatokeynote_test_0513
- **디자인 파일 (실제 사용):** https://www.figma.com/design/PSayE0KkSPlY6VxOuGc4Wt/figmatokeynote_test_0513
  - File key: `PSayE0KkSPlY6VxOuGc4Wt`
  - 195 슬라이드, 영상 2개 포함

**검증된 노드 ID:**
- `1:74` — 단순 텍스트 슬라이드 (Project Rufus 타이틀) ✓ 검증
- `1:87` — 텍스트 + 이미지 슬라이드 ✓ 검증
- `1:470` — 텍스트 + 이미지 + 영상 슬라이드 (Grizzly Bear) ⚠️ 영상 검증 미완료

---

## 환경 설정 / Environment Setup

### 의존성
- Python 3.11+
- macOS (AppleScript 필요)
- Keynote 15.2.1 (`com.apple.Keynote`)
- Figma 토큰 (info@jisungpark.work 계정)

### 토큰 위치
`~/.figma2keynote/config` (chmod 600)
```
FIGMA_ACCESS_TOKEN=figd_...
```

⚠️ **보안 주의**: 이전 세션에서 토큰이 채팅에 노출됨. 작업 재개 전 Figma에서 revoke 후 새 토큰 발급 권장.

---

## 사용법 (현재까지) / Usage

```bash
cd "<Dropbox>/Moltbot/OBS/Projects/Apple Giftcard/figma2keynote_claude"

# 처음 환경 셋업
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt python-pptx

# 토큰 설정 (한번만)
python setup_token.py figd_xxxxx

# 단일 슬라이드 추출
python main.py extract --file-key PSayE0KkSPlY6VxOuGc4Wt --node-id "1:87" --output-dir ./tests/my_test

# 빌드 (네이티브 .key)
python -c "
import sys, json
sys.path.insert(0, 'src')
from pathlib import Path
from keynote_builder.native_builder import NativeKeynoteBuilder

with open('tests/my_test/manifest.json') as f:
    manifest = json.load(f)

builder = NativeKeynoteBuilder()
result = builder.build_from_manifest(
    manifest,
    Path('tests/my_test/assets'),
    Path('tests/my_test/output.key'),
)
print(f'Built: {result}')
"
```

---

## 알려진 이슈 / Known Issues

1. **Keynote가 hang하는 경우** — pkill -9 Keynote 후 재시작
2. **POSIX 경로 vs file alias** — `image`/`movie`는 `(POSIX file "...")` 별칭 필수
3. **샌드박스 경로** — 미디어는 `~/Library/Containers/com.apple.Keynote/Data/Documents/figma2keynote_staging/`에 stage됨
4. **글자 단위 스타일** — `characterStyleOverrides` 미구현, 한 텍스트의 일부만 굵게/색 다르게 안 됨

---

## 참고 자료 / References

- [Keynote .sdef 사전](file:///Applications/Keynote%20Creator%20Studio.app/Contents/Resources/Keynote.sdef)
- [Figma REST API 문서](https://developers.figma.com/docs/rest-api/)
- [obriensp/iWorkFileFormat](https://github.com/obriensp/iWorkFileFormat) (.key Protobuf 스키마)
- [psobot/keynote-parser](https://github.com/psobot/keynote-parser) (Python .key 조작)
