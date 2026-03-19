# Shorts Quality Uplift Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 데모 영상을 실제 YouTube Shorts 출시 가능 퀄리티로 끌어올린다 — 비주얼 품질, 시청 유지율, 차별화 세 축.

**Architecture:**
- Python 파이프라인 (Phase A): VisualSourcingManager 통합으로 Wan AI 비디오 자동 폴백, Pexels HD 강제 필터
- Remotion 컴포지션 (Phase B-C): 패턴 인터럽트 / 키네틱 타이포그래피 / SFX 레이어를 각각 독립 컴포넌트로 추가
- 프롬프트 (Phase C): CTA에 훅 콜백을 넣어 루프 설계 완성

**Tech Stack:** Python 3.11, Remotion 4 (React/TSX), FFmpeg, EdgeTTS, WanVideoSource

---

## Task 1: Pexels HD 강제 — SD 폴백 제거

**Files:**
- Modify: `app/services/generator/visual/pexels.py:383-430`
- Test: `tests/unit/services/generator/visual/test_pexels.py`

### 무엇을 바꾸나
`_select_best_video_file`가 HD 파일이 없을 때 SD 전체로 폴백해서 720p 영상이 들어온다.
HD 필터 통과 파일이 없으면 `None`을 반환하도록 수정 → 상위 로직이 Wan/fallback을 시도하게 된다.

```python
# pexels.py _select_best_video_file 내부
# 변경 전
hd_files = [f for f in files if f.get("height", 0) >= min_height]
if hd_files:
    files = hd_files          # HD만 사용
# else: files 유지 (SD 폴백)  ← 제거

# 변경 후
hd_files = [f for f in files if f.get("height", 0) >= min_height]
if not hd_files:
    return None               # HD 없으면 skip, 상위에서 Wan 시도
files = hd_files
```

**Step 1:** 실패 테스트 작성
```python
# test_pexels.py
def test_select_best_video_file_returns_none_when_no_hd():
    client = PexelsClient(api_key="test")
    sd_files = [{"width": 720, "height": 1280, "quality": "sd", "link": "http://x.com/v.mp4"}]
    result = client._select_best_video_file(sd_files, "portrait", min_height=1080)
    assert result is None
```

**Step 2:** 테스트 실패 확인 `pytest tests/unit/services/generator/visual/test_pexels.py -v`

**Step 3:** `pexels.py` `_select_best_video_file` 수정 (SD 폴백 라인 제거)

**Step 4:** 테스트 통과 확인

**Step 5:** Commit `fix(pexels): reject SD-only results to force Wan/fallback`

---

## Task 2: demo_pipeline.py → VisualSourcingManager 교체

**Files:**
- Modify: `scripts/demo_pipeline.py`

### 무엇을 바꾸나
현재 `demo_pipeline.py`가 `PexelsClient`를 직접 쓴다 → Wan이 전혀 사용되지 않는다.
`VisualSourcingManager`(이미 구현됨)를 쓰도록 교체하면 자동으로:
- Pexels 비디오 → Pexels 이미지 → Wan AI 비디오 → solid fallback 순으로 시도한다.

```python
# 추가할 import
from app.config.video import VisualConfig, WanConfig
from app.services.generator.visual.manager import VisualSourcingManager
from app.services.generator.visual.wan_video_source import WanVideoSource

# Phase 5 교체
http_client = HTTPClient()
pexels = PexelsClient()
wan = WanVideoSource(http_client=http_client)
visual_config = VisualConfig(metadata_score_threshold=0.1)
visual_manager = VisualSourcingManager(
    http_client=http_client,
    config=visual_config,
    pexels_client=pexels,
    wan_video_source=wan,
)

scene_visuals = await visual_manager.source_visuals_for_scenes(
    scenes=scenes,
    scene_results=scene_tts_results,
    output_dir=visuals_dir,
    orientation="portrait",
)
await visual_manager.close()
```

**Step 1:** Modify `demo_pipeline.py` Phase 5 시각 소싱 부분 교체 (위 코드로)

**Step 2:** Run `uv run python scripts/demo_pipeline.py --dry` 또는 import check
```bash
uv run python -c "import scripts.demo_pipeline"
```

**Step 3:** Commit `refactor(demo): use VisualSourcingManager for Pexels→Wan→fallback priority`

---

## Task 3: Wan 프롬프트 — 시네마틱 템플릿

**Files:**
- Modify: `app/services/generator/visual/wan_video_source.py:122-145`

### 무엇을 바꾸나
현재 Wan에 `keyword`를 raw string으로 넘긴다. 시네마틱 수식어를 붙이면 영상 품질이 올라간다.

```python
# generate() 호출 전에 프롬프트 강화
def _enhance_prompt(self, prompt: str, orientation: str = "portrait") -> str:
    orientation_hint = "vertical 9:16 composition" if orientation == "portrait" else "horizontal"
    return (
        f"{prompt}, {orientation_hint}, cinematic lighting, "
        "dramatic atmosphere, sharp focus, professional film quality, "
        "social media short video aesthetic"
    )
```

**Step 1:** `wan_video_source.py`에 `_enhance_prompt` 추가, `generate()` 내부에서 `prompt = self._enhance_prompt(prompt, orientation)` 호출

**Step 2:** `test_wan_video_source.py`에 프롬프트 강화 테스트 추가

**Step 3:** Commit `feat(wan): cinematic prompt enhancement for higher quality generation`

---

## Task 4: BGM — FFmpeg 앰비언트 트랙 생성 스크립트

**Files:**
- Create: `scripts/setup_demo_assets.py`
- Create: `data/bgm/.gitkeep`

### 무엇을 바꾸나
`data/bgm/`가 비어 있어 BGM이 없다. FFmpeg로 60초 Lo-Fi 앰비언트 트랙을 생성하는 스크립트를 추가한다.

```python
# scripts/setup_demo_assets.py
"""Generate demo BGM and SFX assets using FFmpeg."""
import asyncio
import subprocess
from pathlib import Path

BGM_DIR = Path("data/bgm")
SFX_DIR = Path("data/sfx")

async def generate_bgm() -> None:
    BGM_DIR.mkdir(parents=True, exist_ok=True)
    output = BGM_DIR / "ambient_lofi.mp3"
    if output.exists():
        print(f"BGM already exists: {output}")
        return
    # 528Hz sine + brown noise blend → lo-fi ambient feel
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=528:sample_rate=44100",
        "-f", "lavfi", "-i", "aevalsrc=0.02*random(0):s=44100:c=stereo",
        "-filter_complex",
        "[0][1]amix=inputs=2:duration=first,volume=0.4,atempo=1.0,afade=t=in:st=0:d=3,afade=t=out:st=57:d=3",
        "-t", "60",
        "-ar", "44100",
        "-ac", "2",
        "-q:a", "3",
        str(output),
    ]
    subprocess.run(cmd, check=True)
    print(f"Generated BGM: {output}")

async def generate_sfx() -> None:
    """Generate whoosh, pop, ding SFX using FFmpeg lavfi."""
    SFX_DIR.mkdir(parents=True, exist_ok=True)

    sfx_specs = {
        "whoosh.mp3": (
            "aevalsrc=0.3*sin(2*PI*t*(400+300*t)):s=44100:d=0.4,"
            "afade=t=in:st=0:d=0.05,afade=t=out:st=0.3:d=0.1"
        ),
        "pop.mp3": (
            "aevalsrc=0.5*sin(2*PI*880*t)*exp(-12*t):s=44100:d=0.15,"
            "afade=t=out:st=0.1:d=0.05"
        ),
        "ding.mp3": (
            "aevalsrc=0.4*sin(2*PI*1047*t)*exp(-4*t)+0.2*sin(2*PI*1568*t)*exp(-5*t):s=44100:d=0.6,"
            "afade=t=out:st=0.4:d=0.2"
        ),
    }

    for filename, filter_str in sfx_specs.items():
        output = SFX_DIR / filename
        if output.exists():
            print(f"SFX already exists: {output}")
            continue
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"aevalsrc={filter_str.split(',')[0]}:s=44100",
            "-af", ",".join(filter_str.split(",")[1:]) if "," in filter_str else "anull",
            "-t", "1",
            "-ar", "44100",
            "-ac", "1",
            "-q:a", "4",
            str(output),
        ]
        subprocess.run(cmd, check=True)
        print(f"Generated SFX: {output}")

if __name__ == "__main__":
    asyncio.run(generate_bgm())
    asyncio.run(generate_sfx())
```

**Step 1:** 스크립트 작성, `data/bgm/.gitkeep` 및 `data/sfx/.gitkeep` 생성

**Step 2:** `uv run python scripts/setup_demo_assets.py` 실행 → BGM/SFX 파일 생성 확인

**Step 3:** `.gitignore`에 `data/bgm/*.mp3`, `data/sfx/*.mp3` 추가 (실제 파일은 커밋 안 함)

**Step 4:** Commit `feat(demo): add setup_demo_assets script for BGM/SFX generation`

---

## Task 5: 패턴 인터럽트 — BackgroundVisual.tsx 마이크로 줌 펄스

**Files:**
- Modify: `remotion/src/KoreanShorts/components/BackgroundVisual.tsx`

### 무엇을 바꾸나
2.5초마다 서브틀한 줌인 펄스(1.0 → 1.03 → 1.0, 6프레임)를 추가해 시청자 주의를 잡아둔다.
기존 Ken Burns/카메라 무브먼트 transform에 펄스 scale을 곱한다.

```tsx
// BackgroundVisual.tsx SingleVisual 컴포넌트 안에 추가
const INTERRUPT_INTERVAL_SEC = 2.5;
const INTERRUPT_DURATION_FRAMES = 6;

function getPatternInterruptScale(frameOffset: number, fps: number): number {
  const intervalFrames = Math.round(fps * INTERRUPT_INTERVAL_SEC);
  const posInInterval = frameOffset % intervalFrames;
  if (posInInterval >= INTERRUPT_DURATION_FRAMES) return 1.0;
  // Spring-like: scale up then back
  return interpolate(
    posInInterval,
    [0, INTERRUPT_DURATION_FRAMES / 2, INTERRUPT_DURATION_FRAMES],
    [1.0, 1.03, 1.0],
    { easing: Easing.inOut(Easing.quad), extrapolateRight: "clamp" }
  );
}
```

`mediaStyle`의 transform에 `interruptScale`을 곱한다:
```tsx
const interruptScale = getPatternInterruptScale(frameOffset, fps);
// cameraStyle의 scale에 곱함
```

**Step 1:** `getPatternInterruptScale` 함수 추가, `SingleVisual`에 적용

**Step 2:** `npx tsc --noEmit` 로 타입 에러 없음 확인 (`cd remotion && npx tsc --noEmit`)

**Step 3:** Commit `feat(remotion): add 2.5s pattern interrupt micro-zoom pulse`

---

## Task 6: 키네틱 타이포그래피 — KineticTypography.tsx

**Files:**
- Create: `remotion/src/KoreanShorts/components/KineticTypography.tsx`
- Modify: `remotion/src/KoreanShorts/types.ts` (KoreanShortsProps에 필드 추가)
- Modify: `remotion/src/KoreanShorts/index.tsx` (Layer 추가)

### 무엇을 바꾸나
씬 전환 순간에 emphasis_words 중 첫 단어를 화면 중앙에 크게 팝인 → 0.7초 표시 → 페이드아웃.
기존 SubtitleTrack(하단)과 별개의 레이어.

```tsx
// KineticTypography.tsx
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { SafeZone, SceneInfo, Theme } from "../types";

interface KineticTypographyProps {
  scenes: SceneInfo[];
  theme?: Theme;
  safeZone?: SafeZone;
}

export const KineticTypography: React.FC<KineticTypographyProps> = ({ scenes, theme, safeZone }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTimeSec = frame / fps;

  // Find scene that just started (within first 0.8s of scene)
  const activeScene = scenes.find(
    (s) => currentTimeSec >= s.start_time && currentTimeSec < s.start_time + 0.8
  );

  if (!activeScene || !activeScene.emphasis_words.length) return null;

  const keyword = activeScene.emphasis_words[0];
  const sceneStartFrame = Math.round(activeScene.start_time * fps);
  const elapsed = frame - sceneStartFrame;
  const displayFrames = Math.round(fps * 0.7); // 0.7s display

  if (elapsed < 0 || elapsed > displayFrames) return null;

  // Pop in with spring, fade out at end
  const scaleSpring = spring({ frame: elapsed, fps, config: { damping: 12, stiffness: 250, mass: 0.6 } });
  const scale = interpolate(scaleSpring, [0, 1], [0.4, 1.0]);
  const opacity = interpolate(elapsed, [0, 4, displayFrames - 8, displayFrames], [0, 1, 1, 0], {
    extrapolateRight: "clamp",
  });

  const accentColor = theme?.accent_color ?? "#FF6B6B";
  const fontFamily = `'${theme?.font_family ?? "Pretendard"}', sans-serif`;
  const safeLeft = safeZone?.left_px ?? 120;
  const safeRight = safeZone?.right_px ?? 120;

  return (
    <AbsoluteFill
      style={{
        justifyContent: "center",
        alignItems: "center",
        pointerEvents: "none",
      }}
    >
      <div
        style={{
          paddingLeft: safeLeft,
          paddingRight: safeRight,
          opacity,
          transform: `scale(${scale})`,
        }}
      >
        <div
          style={{
            fontFamily,
            fontSize: 160,
            fontWeight: 900,
            fontStyle: "italic",
            color: accentColor,
            textAlign: "center",
            lineHeight: 1.0,
            textShadow: [
              "-4px -4px 0 #000", "4px -4px 0 #000",
              "-4px 4px 0 #000", "4px 4px 0 #000",
              "0 0 40px rgba(0,0,0,0.8)",
            ].join(", "),
            wordBreak: "keep-all",
          }}
        >
          {keyword}
        </div>
      </div>
    </AbsoluteFill>
  );
};
```

**Step 1:** `KineticTypography.tsx` 생성

**Step 2:** `index.tsx` Layer 3.5 (Headline 다음, SubtitleTrack 전)에 `<KineticTypography>` 추가
```tsx
{scenes && scenes.length > 0 && (
  <KineticTypography scenes={scenes} theme={theme} safeZone={safe_zone} />
)}
```

**Step 3:** `npx tsc --noEmit`로 타입 에러 없음 확인

**Step 4:** Commit `feat(remotion): add KineticTypography component for emphasis word pop-in`

---

## Task 7: SFX 레이어 — SFXTrack.tsx + 씬 전환 whoosh

**Files:**
- Create: `remotion/src/KoreanShorts/components/SFXTrack.tsx`
- Modify: `remotion/src/KoreanShorts/types.ts` (KoreanShortsProps에 sfx_dir 추가)
- Modify: `remotion/src/KoreanShorts/index.tsx`
- Modify: `app/services/generator/remotion_compositor.py` (props에 sfx_paths 전달)

### 무엇을 바꾸나
씬 전환마다 whoosh SFX, hook 씬에 pop SFX, CTA에 ding SFX를 재생한다.
SFX 파일은 `data/sfx/`에서 공급 (Task 4에서 생성).

```tsx
// SFXTrack.tsx
import React from "react";
import { Audio, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { SceneInfo } from "../types";

interface SfxEvent {
  startFrame: number;
  sfxPath: string;
  volume: number;
}

interface SFXTrackProps {
  scenes: SceneInfo[];
  sfxPaths: Record<string, string>; // { whoosh: "...", pop: "...", ding: "..." }
}

export const SFXTrack: React.FC<SFXTrackProps> = ({ scenes, sfxPaths }) => {
  const { fps } = useVideoConfig();
  const frame = useCurrentFrame();

  const events: SfxEvent[] = scenes.map((s) => {
    let sfxPath = sfxPaths.whoosh;
    if (s.scene_type === "hook") sfxPath = sfxPaths.pop ?? sfxPaths.whoosh;
    if (s.scene_type === "cta") sfxPath = sfxPaths.ding ?? sfxPaths.whoosh;
    return {
      startFrame: Math.round(s.start_time * fps),
      sfxPath: sfxPath ?? "",
      volume: s.scene_type === "hook" ? 0.6 : 0.35,
    };
  }).filter((e) => e.sfxPath);

  return (
    <>
      {events.map((event, idx) => (
        event.startFrame === frame ? (
          <Audio
            key={`sfx-${idx}-${event.startFrame}`}
            src={staticFile(event.sfxPath)}
            startFrom={0}
            volume={event.volume}
          />
        ) : null
      ))}
    </>
  );
};
```

**주의:** Remotion에서 Audio를 조건부 렌더하면 frame-exact 재생이 가능하다.
실제로는 `<Sequence>` 래퍼가 더 안정적:

```tsx
import { Sequence } from "remotion";
// 각 SFX를 Sequence(from={event.startFrame})로 감싸기
```

**Step 1:** `SFXTrack.tsx` 생성 (Sequence 기반)

**Step 2:** `types.ts`에 `sfx_paths?: Record<string, string>` 추가

**Step 3:** `index.tsx`에 `<SFXTrack>` 추가

**Step 4:** `remotion_compositor.py` `compose_scenes()`에서 SFX 파일 스테이징 + props에 `sfx_paths` 추가

**Step 5:** `npx tsc --noEmit`

**Step 6:** Commit `feat(remotion): add SFXTrack for scene-transition sound effects`

---

## Task 8: 루프 설계 — ScriptGenerator CTA 훅 콜백

**Files:**
- Modify: `app/prompts/templates/scene_script_generation.yaml`

### 무엇을 바꾸나
CTA 씬이 "구독과 좋아요!"로 끝나면 루프가 없다.
프롬프트에 "CTA는 hook 주제로 돌아오는 질문으로 끝낸다"를 명시한다.

```yaml
# scene_script_generation.yaml CTA 지침에 추가:
# CTA scene must end with a question that references the hook topic,
# creating a loop: viewer curiosity → watch again.
# Example: "그래서 진짜로 [hook 주제]를 써봤어? 댓글로 알려줘!"
```

**Step 1:** `scene_script_generation.yaml` CTA 씬 지침 수정

**Step 2:** Commit `feat(prompt): CTA loop design — callback to hook topic`

---

## Task 9: 전체 테스트 + 린트

**Commands:**
```bash
cd /workspace
uv run ruff check app/ scripts/
uv run pytest tests/unit/services/generator/visual/test_pexels.py -v
uv run pytest tests/unit/services/generator/visual/test_wan_video_source.py -v
cd remotion && npx tsc --noEmit
```

Expected: 모두 통과
