# 다른 컴퓨터에서 작업 이어가기 / Resume on Another Computer

## 사용법 / How to use

다른 컴퓨터의 Claude Code 세션에서 **아래 프롬프트를 그대로 복사·붙여넣기**하세요.

---

## 📋 복사할 프롬프트 / Prompt to copy

```
figma2keynote_claude 프로젝트 작업 이어가야 해.

GitHub: https://github.com/frognation/figma2keynote_claude
위치 (현재 컴퓨터에 있다면): <Dropbox 경로>/Moltbot/OBS/Projects/Apple Giftcard/figma2keynote_claude/

먼저 다음 순서로 컨텍스트 확보해줘:

1. 프로젝트 폴더가 로컬에 있는지 확인. 없으면 git clone https://github.com/frognation/figma2keynote_claude.git 으로 받아.
2. 폴더 안의 HANDOFF.md 파일을 처음부터 끝까지 정독해. 거기에 현재까지의 상황, 아키텍처, 다음 할 일, 알려진 이슈 다 정리되어 있음.
3. 다음 환경 셋업 확인:
   - Keynote 15.2.1 (com.apple.Keynote) 설치되어 있는지
   - Python 3.11+ 가능한지
   - Figma 토큰 (~/.figma2keynote/config) 있는지 — 없으면 새로 발급 받아야 함
   - 새 컴퓨터면 .venv 새로 만들어야 함:
     python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt python-pptx
4. HANDOFF.md의 "다음에 할 일" 섹션 중 "즉시 (in_progress)" 항목인 영상 임베딩 최종 검증부터 이어가.

진행 전에 확인할 사항:
- 새 컴퓨터에 Keynote 두 개 버전이 있는지? 있으면 어떤 게 신버전인지 (com.apple.Keynote vs com.apple.iWork.Keynote)?
- Figma 토큰을 어떻게 줄지? (보안: 이전 세션에서 토큰이 채팅에 노출됐으니 새 토큰 발급 권장)

작업 컨텍스트 정리되면 알려줘. 그 다음에 영상 임베딩 디버깅부터 시작하자.
```

---

## 🔑 필요한 정보 / Required Info

다른 컴퓨터에서 작업 재개할 때 준비해 둘 것:

### 1. Figma 토큰
- 이전 세션에서 사용된 토큰은 채팅에 노출됐으므로 **반드시 revoke 후 새로 발급**
- 계정: info@jisungpark.work
- 발급 위치: https://www.figma.com/settings (→ Security → Personal access tokens)
- 필요 권한: File content (read-only), Current user (read-only)

### 2. 테스트 Figma 파일
- File key: `PSayE0KkSPlY6VxOuGc4Wt`
- URL: https://www.figma.com/design/PSayE0KkSPlY6VxOuGc4Wt/figmatokeynote_test_0513
- 검증된 노드: `1:74` (텍스트), `1:87` (이미지), `1:470` (영상)

### 3. Keynote 버전 확인
새 컴퓨터에서 미리 실행:
```bash
osascript -e 'tell application id "com.apple.Keynote" to version'      # 신버전 (15.x)
osascript -e 'tell application id "com.apple.iWork.Keynote" to version' # 구버전 (14.x)
```

신버전이 `com.apple.Keynote` (15.x)면 그대로 사용 가능. 없으면 코드에서 자동으로 구버전으로 fallback함.

---

## 🚀 빠른 시작 / Quick Start

```bash
# 1. 클론
git clone https://github.com/frognation/figma2keynote_claude.git
cd figma2keynote_claude

# 2. 환경 셋업
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt python-pptx

# 3. 토큰 설정 (한번만)
python setup_token.py <YOUR_FIGMA_TOKEN>

# 4. HANDOFF.md 정독
cat HANDOFF.md

# 5. 단일 슬라이드로 검증 테스트
python main.py extract --file-key PSayE0KkSPlY6VxOuGc4Wt --node-id "1:74" --output-dir ./tests/check

python -c "
import sys, json
sys.path.insert(0, 'src')
from pathlib import Path
from keynote_builder.native_builder import NativeKeynoteBuilder

with open('tests/check/manifest.json') as f:
    manifest = json.load(f)

builder = NativeKeynoteBuilder()
result = builder.build_from_manifest(
    manifest,
    Path('tests/check/assets'),
    Path('tests/check/output.key'),
)
print(f'Built: {result}')
"

# 6. Keynote에서 열어 확인
open tests/check/output.key
```

성공하면 텍스트 "Project Rufus" (220pt)가 정확한 위치에 보임.

---

## 📂 핵심 파일 위치 / Key Files

| 파일 | 역할 |
|---|---|
| `HANDOFF.md` | 현재 상황·아키텍처·할 일 (필독) |
| `src/keynote_builder/native_builder.py` | 메인 빌더 (AppleScript) |
| `src/figma_extractor/api_client.py` | Figma REST API 클라이언트 |
| `src/diff_engine/differ.py` | 증분 싱크용 diff 엔진 |
| `main.py` | CLI 엔트리포인트 |
| `setup_token.py` | 토큰 설정 도구 |
| `docs/DEVLOG.md` | 초기 리서치 로그 |
