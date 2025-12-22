# 🎬 영상 생성 파이프라인 상세 설계

## 1. 개요

### 1.1 목표
- 스크립트 → 완성된 Shorts 영상 자동 생성
- TTS + 자막 + 배경 영상/이미지 합성
- 채널별 일관된 비주얼 스타일 유지
- 썸네일 자동 생성

### 1.2 파이프라인 흐름
```
스크립트 → TTS 생성 → 자막 생성 → 비주얼 소싱 → 합성 → 썸네일 → 출력
```

---

## 2. TTS (Text-to-Speech)

### 2.1 TTS 서비스 추상화
```python
from abc import ABC, abstractmethod
from pydantic import BaseModel
from enum import Enum
from pathlib import Path


class TTSService(str, Enum):
    EDGE_TTS = "edge-tts"
    ELEVENLABS = "elevenlabs"
    CLOVA = "clova"


class VoiceConfig(BaseModel):
    service: TTSService
    voice_id: str
    speed: float = 1.0          # 0.5 - 2.0
    pitch: float = 0.0          # -20 - 20 (일부 서비스)

    # ElevenLabs 전용
    stability: float | None = None
    similarity_boost: float | None = None


class TTSResult(BaseModel):
    audio_path: Path
    duration_seconds: float
    word_timestamps: list["WordTimestamp"] | None = None


class WordTimestamp(BaseModel):
    word: str
    start: float      # 초
    end: float        # 초


class BaseTTSEngine(ABC):
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        config: VoiceConfig,
        output_path: Path
    ) -> TTSResult:
        pass

    @abstractmethod
    def get_available_voices(self) -> list[dict]:
        pass
```

### 2.2 Edge TTS 구현 (무료)
```python
import edge_tts
import asyncio
from pathlib import Path


class EdgeTTSEngine(BaseTTSEngine):
    """무료 Microsoft Edge TTS"""

    # 추천 한국어 음성
    KOREAN_VOICES = {
        "male": [
            "ko-KR-InJoonNeural",      # 남성, 자연스러움
            "ko-KR-BongJinNeural",     # 남성, 차분함
            "ko-KR-GookMinNeural",     # 남성, 밝음
        ],
        "female": [
            "ko-KR-SunHiNeural",       # 여성, 자연스러움
            "ko-KR-JiMinNeural",       # 여성, 밝음
            "ko-KR-SeoHyeonNeural",    # 여성, 차분함
            "ko-KR-YuJinNeural",       # 여성, 또렷함
        ],
    }

    async def synthesize(
        self,
        text: str,
        config: VoiceConfig,
        output_path: Path
    ) -> TTSResult:
        # 속도 변환 (1.0 → "+0%", 1.2 → "+20%")
        rate = f"{int((config.speed - 1) * 100):+d}%"

        communicate = edge_tts.Communicate(
            text=text,
            voice=config.voice_id,
            rate=rate,
        )

        # 오디오 + 자막 데이터 생성
        audio_path = output_path.with_suffix(".mp3")

        word_timestamps = []

        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                with open(audio_path, "ab") as f:
                    f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_timestamps.append(WordTimestamp(
                    word=chunk["text"],
                    start=chunk["offset"] / 10_000_000,  # 100ns → 초
                    end=(chunk["offset"] + chunk["duration"]) / 10_000_000,
                ))

        # 오디오 길이 계산
        duration = await self._get_audio_duration(audio_path)

        return TTSResult(
            audio_path=audio_path,
            duration_seconds=duration,
            word_timestamps=word_timestamps,
        )

    async def _get_audio_duration(self, path: Path) -> float:
        """ffprobe로 오디오 길이 확인"""
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries",
             "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True
        )
        return float(result.stdout.strip())

    def get_available_voices(self) -> list[dict]:
        return [
            {"id": v, "gender": g, "language": "ko-KR"}
            for g, voices in self.KOREAN_VOICES.items()
            for v in voices
        ]
```

### 2.3 ElevenLabs 구현 (고품질)
```python
from elevenlabs import generate, set_api_key, Voice, VoiceSettings


class ElevenLabsEngine(BaseTTSEngine):
    """고품질 AI 음성 (유료)"""

    def __init__(self, api_key: str):
        set_api_key(api_key)

    async def synthesize(
        self,
        text: str,
        config: VoiceConfig,
        output_path: Path
    ) -> TTSResult:
        voice_settings = VoiceSettings(
            stability=config.stability or 0.5,
            similarity_boost=config.similarity_boost or 0.75,
        )

        audio = generate(
            text=text,
            voice=Voice(
                voice_id=config.voice_id,
                settings=voice_settings,
            ),
            model="eleven_multilingual_v2",  # 다국어 지원
        )

        audio_path = output_path.with_suffix(".mp3")
        with open(audio_path, "wb") as f:
            f.write(audio)

        duration = await self._get_audio_duration(audio_path)

        # ElevenLabs는 word timestamp 미지원 → Whisper로 생성
        word_timestamps = await self._generate_timestamps_with_whisper(audio_path)

        return TTSResult(
            audio_path=audio_path,
            duration_seconds=duration,
            word_timestamps=word_timestamps,
        )

    async def _generate_timestamps_with_whisper(
        self,
        audio_path: Path
    ) -> list[WordTimestamp]:
        """Whisper로 단어별 타임스탬프 생성"""
        import whisper

        model = whisper.load_model("base")  # 또는 "small"
        result = model.transcribe(
            str(audio_path),
            language="ko",
            word_timestamps=True,
        )

        timestamps = []
        for segment in result["segments"]:
            for word_info in segment.get("words", []):
                timestamps.append(WordTimestamp(
                    word=word_info["word"],
                    start=word_info["start"],
                    end=word_info["end"],
                ))

        return timestamps
```

### 2.4 TTS 팩토리
```python
class TTSEngineFactory:
    _engines: dict[TTSService, BaseTTSEngine] = {}

    @classmethod
    def get_engine(cls, service: TTSService) -> BaseTTSEngine:
        if service not in cls._engines:
            if service == TTSService.EDGE_TTS:
                cls._engines[service] = EdgeTTSEngine()
            elif service == TTSService.ELEVENLABS:
                from config import settings
                cls._engines[service] = ElevenLabsEngine(settings.elevenlabs_api_key)
            else:
                raise ValueError(f"Unknown TTS service: {service}")

        return cls._engines[service]
```

---

## 3. 자막 생성

### 3.1 자막 스키마
```python
from pydantic import BaseModel
from enum import Enum


class SubtitleStyle(BaseModel):
    """자막 스타일 설정"""
    font_name: str = "Pretendard"
    font_size: int = 48
    font_color: str = "#FFFFFF"

    # 외곽선
    outline_color: str = "#000000"
    outline_width: int = 2

    # 그림자
    shadow_color: str = "#000000"
    shadow_offset: int = 2

    # 배경 박스
    background_enabled: bool = True
    background_color: str = "#000000"
    background_opacity: float = 0.7
    background_padding: int = 10

    # 위치
    position: str = "bottom"  # bottom, center, top
    margin_bottom: int = 50
    margin_horizontal: int = 30

    # 애니메이션
    highlight_current_word: bool = True
    highlight_color: str = "#FFFF00"
    fade_in: bool = False

    # 줄바꿈
    max_chars_per_line: int = 20
    max_lines: int = 2


class SubtitleSegment(BaseModel):
    """자막 세그먼트"""
    index: int
    start: float        # 초
    end: float          # 초
    text: str
    words: list[WordTimestamp] | None = None


class SubtitleFile(BaseModel):
    """자막 파일"""
    segments: list[SubtitleSegment]
    style: SubtitleStyle
    format: str = "ass"  # ass, srt
```

### 3.2 자막 생성기
```python
import re
from pathlib import Path


class SubtitleGenerator:
    def __init__(self, style: SubtitleStyle | None = None):
        self.style = style or SubtitleStyle()

    def generate_from_timestamps(
        self,
        word_timestamps: list[WordTimestamp],
        style: SubtitleStyle | None = None
    ) -> SubtitleFile:
        """단어 타임스탬프 → 자막 세그먼트"""
        style = style or self.style
        segments = []

        current_segment_words = []
        current_text = ""
        segment_start = None

        for word in word_timestamps:
            test_text = current_text + word.word

            # 줄바꿈 필요 체크
            if len(test_text) > style.max_chars_per_line * style.max_lines:
                # 현재 세그먼트 저장
                if current_segment_words:
                    segments.append(SubtitleSegment(
                        index=len(segments) + 1,
                        start=segment_start,
                        end=current_segment_words[-1].end,
                        text=current_text.strip(),
                        words=current_segment_words.copy(),
                    ))

                # 새 세그먼트 시작
                current_segment_words = [word]
                current_text = word.word
                segment_start = word.start
            else:
                if segment_start is None:
                    segment_start = word.start
                current_segment_words.append(word)
                current_text = test_text

        # 마지막 세그먼트
        if current_segment_words:
            segments.append(SubtitleSegment(
                index=len(segments) + 1,
                start=segment_start,
                end=current_segment_words[-1].end,
                text=current_text.strip(),
                words=current_segment_words,
            ))

        return SubtitleFile(segments=segments, style=style)

    def generate_from_script(
        self,
        script: str,
        audio_duration: float,
        style: SubtitleStyle | None = None
    ) -> SubtitleFile:
        """스크립트 + 오디오 길이 → 균등 분할 자막 (타임스탬프 없을 때)"""
        style = style or self.style

        # 문장 단위로 분할
        sentences = re.split(r'[.!?]\s*', script)
        sentences = [s.strip() for s in sentences if s.strip()]

        # 균등 시간 배분
        time_per_sentence = audio_duration / len(sentences)

        segments = []
        for i, sentence in enumerate(sentences):
            segments.append(SubtitleSegment(
                index=i + 1,
                start=i * time_per_sentence,
                end=(i + 1) * time_per_sentence,
                text=self._wrap_text(sentence, style.max_chars_per_line),
            ))

        return SubtitleFile(segments=segments, style=style)

    def _wrap_text(self, text: str, max_chars: int) -> str:
        """긴 텍스트 줄바꿈"""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            if len(current_line) + len(word) + 1 <= max_chars:
                current_line += (" " if current_line else "") + word
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return "\n".join(lines)

    def to_ass(self, subtitle: SubtitleFile, output_path: Path) -> Path:
        """ASS 포맷으로 저장 (스타일링 지원)"""
        style = subtitle.style

        # ASS 헤더
        ass_content = f"""[Script Info]
Title: Generated Subtitle
ScriptType: v4.00+
PlayDepth: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_name},{style.font_size},{self._color_to_ass(style.font_color)},{self._color_to_ass(style.highlight_color)},{self._color_to_ass(style.outline_color)},{self._color_to_ass(style.background_color, style.background_opacity)},0,0,0,0,100,100,0,0,1,{style.outline_width},{style.shadow_offset},2,{style.margin_horizontal},{style.margin_horizontal},{style.margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # 자막 이벤트
        for seg in subtitle.segments:
            start = self._seconds_to_ass_time(seg.start)
            end = self._seconds_to_ass_time(seg.end)
            text = seg.text.replace("\n", "\\N")

            ass_content += f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}\n"

        output_path = output_path.with_suffix(".ass")
        output_path.write_text(ass_content, encoding="utf-8")
        return output_path

    def to_srt(self, subtitle: SubtitleFile, output_path: Path) -> Path:
        """SRT 포맷으로 저장 (단순)"""
        srt_content = ""

        for seg in subtitle.segments:
            start = self._seconds_to_srt_time(seg.start)
            end = self._seconds_to_srt_time(seg.end)
            srt_content += f"{seg.index}\n{start} --> {end}\n{seg.text}\n\n"

        output_path = output_path.with_suffix(".srt")
        output_path.write_text(srt_content, encoding="utf-8")
        return output_path

    def _color_to_ass(self, hex_color: str, alpha: float = 1.0) -> str:
        """HEX → ASS 컬러 (&HAABBGGRR)"""
        hex_color = hex_color.lstrip("#")
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        a = int((1 - alpha) * 255)
        return f"&H{a:02X}{b:02X}{g:02X}{r:02X}"

    def _seconds_to_ass_time(self, seconds: float) -> str:
        """초 → ASS 시간 (H:MM:SS.CC)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    def _seconds_to_srt_time(self, seconds: float) -> str:
        """초 → SRT 시간 (HH:MM:SS,mmm)"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
```

---

## 4. 비주얼 소싱

### 4.1 비주얼 소스 타입
```python
from enum import Enum
from pydantic import BaseModel
from pathlib import Path


class VisualSourceType(str, Enum):
    STOCK_VIDEO = "stock_video"      # Pexels, Pixabay
    STOCK_IMAGE = "stock_image"      # 정적 이미지
    AI_IMAGE = "ai_image"            # DALL-E 생성
    SOLID_COLOR = "solid_color"      # 단색 배경
    GRADIENT = "gradient"            # 그라데이션


class VisualAsset(BaseModel):
    type: VisualSourceType
    path: Path | None = None
    url: str | None = None
    duration: float | None = None    # 비디오인 경우

    # 이미지/단색 옵션
    color: str | None = None
    gradient_colors: list[str] | None = None

    # 메타
    source: str | None = None        # "pexels", "dalle", etc
    license: str | None = None
    keywords: list[str] = []


class VisualConfig(BaseModel):
    """채널별 비주얼 설정"""

    # 기본 소스 우선순위
    source_priority: list[VisualSourceType] = [
        VisualSourceType.STOCK_VIDEO,
        VisualSourceType.AI_IMAGE,
        VisualSourceType.SOLID_COLOR,
    ]

    # 스톡 설정
    stock_config: dict = {
        "orientation": "portrait",    # Shorts용 세로
        "min_duration": 5,
        "max_results": 10,
    }

    # AI 이미지 설정
    ai_image_config: dict = {
        "model": "dall-e-3",
        "size": "1024x1792",          # 세로
        "quality": "standard",
    }

    # 폴백 설정
    fallback_color: str = "#1a1a2e"
    fallback_gradient: list[str] = ["#1a1a2e", "#16213e"]
```

### 4.2 스톡 영상/이미지 소싱
```python
import httpx
from typing import AsyncIterator


class PexelsClient:
    """Pexels API 클라이언트 (무료)"""

    BASE_URL = "https://api.pexels.com"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"Authorization": api_key}
        )

    async def search_videos(
        self,
        query: str,
        orientation: str = "portrait",
        min_duration: int = 5,
        max_results: int = 10,
    ) -> list[VisualAsset]:
        """비디오 검색"""
        response = await self.client.get(
            f"{self.BASE_URL}/videos/search",
            params={
                "query": query,
                "orientation": orientation,
                "per_page": max_results,
            }
        )
        response.raise_for_status()
        data = response.json()

        assets = []
        for video in data.get("videos", []):
            # HD 버전 선택
            video_file = next(
                (f for f in video["video_files"]
                 if f["quality"] == "hd" and f["width"] < f["height"]),
                video["video_files"][0] if video["video_files"] else None
            )

            if video_file and video["duration"] >= min_duration:
                assets.append(VisualAsset(
                    type=VisualSourceType.STOCK_VIDEO,
                    url=video_file["link"],
                    duration=video["duration"],
                    source="pexels",
                    license="Pexels License",
                    keywords=query.split(),
                ))

        return assets

    async def search_images(
        self,
        query: str,
        orientation: str = "portrait",
        max_results: int = 10,
    ) -> list[VisualAsset]:
        """이미지 검색"""
        response = await self.client.get(
            f"{self.BASE_URL}/v1/search",
            params={
                "query": query,
                "orientation": orientation,
                "per_page": max_results,
            }
        )
        response.raise_for_status()
        data = response.json()

        assets = []
        for photo in data.get("photos", []):
            assets.append(VisualAsset(
                type=VisualSourceType.STOCK_IMAGE,
                url=photo["src"]["large2x"],
                source="pexels",
                license="Pexels License",
                keywords=query.split(),
            ))

        return assets

    async def download(self, url: str, output_path: Path) -> Path:
        """에셋 다운로드"""
        response = await self.client.get(url)
        response.raise_for_status()

        output_path.write_bytes(response.content)
        return output_path


class AIImageGenerator:
    """DALL-E 이미지 생성"""

    def __init__(self, api_key: str):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(api_key=api_key)

    async def generate(
        self,
        prompt: str,
        style: str = "cinematic",
        size: str = "1024x1792",
    ) -> VisualAsset:
        """AI 이미지 생성"""
        # 프롬프트 강화
        enhanced_prompt = f"{prompt}, {style} style, high quality, vertical format"

        response = await self.client.images.generate(
            model="dall-e-3",
            prompt=enhanced_prompt,
            size=size,
            quality="standard",
            n=1,
        )

        return VisualAsset(
            type=VisualSourceType.AI_IMAGE,
            url=response.data[0].url,
            source="dalle",
            keywords=prompt.split()[:5],
        )
```

### 4.3 비주얼 소싱 매니저
```python
class VisualSourcingManager:
    """주제/키워드 기반 비주얼 자동 소싱"""

    def __init__(
        self,
        pexels_client: PexelsClient,
        ai_generator: AIImageGenerator | None = None,
    ):
        self.pexels = pexels_client
        self.ai_generator = ai_generator

    async def source_visuals(
        self,
        keywords: list[str],
        duration_needed: float,
        config: VisualConfig,
    ) -> list[VisualAsset]:
        """필요한 길이만큼 비주얼 소싱"""
        assets = []
        total_duration = 0

        for source_type in config.source_priority:
            if total_duration >= duration_needed:
                break

            if source_type == VisualSourceType.STOCK_VIDEO:
                for keyword in keywords:
                    videos = await self.pexels.search_videos(
                        query=keyword,
                        **config.stock_config,
                    )
                    for video in videos:
                        if total_duration >= duration_needed:
                            break
                        assets.append(video)
                        total_duration += video.duration or 10

            elif source_type == VisualSourceType.STOCK_IMAGE:
                for keyword in keywords:
                    images = await self.pexels.search_images(
                        query=keyword,
                        **config.stock_config,
                    )
                    # 이미지는 5초씩 사용
                    for image in images[:3]:
                        if total_duration >= duration_needed:
                            break
                        image.duration = 5
                        assets.append(image)
                        total_duration += 5

            elif source_type == VisualSourceType.AI_IMAGE and self.ai_generator:
                prompt = " ".join(keywords[:3])
                image = await self.ai_generator.generate(prompt)
                image.duration = duration_needed - total_duration
                assets.append(image)
                total_duration = duration_needed

        # 폴백: 단색 배경
        if total_duration < duration_needed:
            assets.append(VisualAsset(
                type=VisualSourceType.SOLID_COLOR,
                color=config.fallback_color,
                duration=duration_needed - total_duration,
            ))

        return assets
```

---

## 5. 영상 합성 (FFmpeg)

### 5.1 합성 설정
```python
class VideoConfig(BaseModel):
    """영상 출력 설정"""

    # 해상도 (Shorts = 9:16)
    width: int = 1080
    height: int = 1920

    # 코덱
    video_codec: str = "libx264"
    audio_codec: str = "aac"

    # 품질
    crf: int = 23                    # 품질 (낮을수록 좋음, 18-28)
    preset: str = "medium"           # 인코딩 속도
    audio_bitrate: str = "192k"

    # 프레임
    fps: int = 30

    # 출력
    format: str = "mp4"


class CompositionConfig(BaseModel):
    """합성 설정"""
    video: VideoConfig = VideoConfig()
    subtitle_style: SubtitleStyle = SubtitleStyle()

    # 트랜지션
    transition_type: str = "fade"    # fade, none
    transition_duration: float = 0.5

    # 배경 처리
    blur_background: bool = True     # 가로 영상 → 세로 변환 시 블러 배경

    # 오디오
    background_music: Path | None = None
    music_volume: float = 0.1        # 배경 음악 볼륨 (0-1)
```

### 5.2 FFmpeg 합성기
```python
import subprocess
import tempfile
from pathlib import Path


class FFmpegCompositor:
    """FFmpeg 기반 영상 합성"""

    def __init__(self, config: CompositionConfig | None = None):
        self.config = config or CompositionConfig()

    async def compose(
        self,
        audio: TTSResult,
        subtitle: SubtitleFile,
        visuals: list[VisualAsset],
        output_path: Path,
    ) -> Path:
        """전체 합성 파이프라인"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)

            # 1. 비주얼 에셋 다운로드/준비
            visual_paths = await self._prepare_visuals(visuals, tmpdir)

            # 2. 비주얼 시퀀스 생성
            video_sequence = await self._create_video_sequence(
                visual_paths,
                audio.duration_seconds,
                tmpdir,
            )

            # 3. 자막 파일 생성
            subtitle_generator = SubtitleGenerator()
            subtitle_path = subtitle_generator.to_ass(subtitle, tmpdir / "subtitle")

            # 4. 최종 합성
            return await self._final_compose(
                video_path=video_sequence,
                audio_path=audio.audio_path,
                subtitle_path=subtitle_path,
                output_path=output_path,
            )

    async def _prepare_visuals(
        self,
        visuals: list[VisualAsset],
        tmpdir: Path,
    ) -> list[Path]:
        """비주얼 에셋 준비"""
        paths = []

        for i, visual in enumerate(visuals):
            if visual.type == VisualSourceType.SOLID_COLOR:
                # 단색 이미지 생성
                path = await self._create_solid_color_image(
                    visual.color,
                    tmpdir / f"solid_{i}.png",
                )
            elif visual.url:
                # 다운로드
                path = tmpdir / f"asset_{i}{Path(visual.url).suffix or '.mp4'}"
                async with httpx.AsyncClient() as client:
                    response = await client.get(visual.url)
                    path.write_bytes(response.content)
            elif visual.path:
                path = visual.path
            else:
                continue

            paths.append((path, visual.duration or 5))

        return paths

    async def _create_solid_color_image(
        self,
        color: str,
        output_path: Path
    ) -> Path:
        """단색 이미지 생성"""
        from PIL import Image

        img = Image.new(
            "RGB",
            (self.config.video.width, self.config.video.height),
            color,
        )
        img.save(output_path)
        return output_path

    async def _create_video_sequence(
        self,
        visual_paths: list[tuple[Path, float]],
        total_duration: float,
        tmpdir: Path,
    ) -> Path:
        """비주얼 시퀀스 → 단일 비디오"""
        cfg = self.config.video

        # 각 비주얼을 필요한 길이로 변환
        segments = []
        for i, (path, duration) in enumerate(visual_paths):
            segment_path = tmpdir / f"segment_{i}.mp4"

            if path.suffix in [".jpg", ".jpeg", ".png", ".webp"]:
                # 이미지 → 비디오 변환
                cmd = [
                    "ffmpeg", "-y",
                    "-loop", "1",
                    "-i", str(path),
                    "-c:v", cfg.video_codec,
                    "-t", str(duration),
                    "-vf", f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2",
                    "-r", str(cfg.fps),
                    "-pix_fmt", "yuv420p",
                    str(segment_path),
                ]
            else:
                # 비디오 스케일링 + 길이 조정
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(path),
                    "-c:v", cfg.video_codec,
                    "-t", str(duration),
                    "-vf", f"scale={cfg.width}:{cfg.height}:force_original_aspect_ratio=decrease,pad={cfg.width}:{cfg.height}:(ow-iw)/2:(oh-ih)/2",
                    "-r", str(cfg.fps),
                    "-an",  # 오디오 제거
                    "-pix_fmt", "yuv420p",
                    str(segment_path),
                ]

            subprocess.run(cmd, check=True, capture_output=True)
            segments.append(segment_path)

        # concat 파일 생성
        concat_file = tmpdir / "concat.txt"
        concat_content = "\n".join(f"file '{p}'" for p in segments)
        concat_file.write_text(concat_content)

        # 병합
        output_path = tmpdir / "video_sequence.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, capture_output=True)

        return output_path

    async def _final_compose(
        self,
        video_path: Path,
        audio_path: Path,
        subtitle_path: Path,
        output_path: Path,
    ) -> Path:
        """비디오 + 오디오 + 자막 최종 합성"""
        cfg = self.config.video

        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-vf", f"ass={subtitle_path}",
            "-c:v", cfg.video_codec,
            "-crf", str(cfg.crf),
            "-preset", cfg.preset,
            "-c:a", cfg.audio_codec,
            "-b:a", cfg.audio_bitrate,
            "-shortest",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ]

        # 배경 음악 추가
        if self.config.background_music:
            cmd = self._add_background_music(cmd)

        subprocess.run(cmd, check=True, capture_output=True)
        return output_path

    def _add_background_music(self, cmd: list) -> list:
        """배경 음악 믹싱"""
        # TODO: 배경 음악 볼륨 조절 + 믹싱
        return cmd
```

---

## 6. 썸네일 생성

### 6.1 썸네일 설정
```python
class ThumbnailStyle(BaseModel):
    """썸네일 스타일"""
    width: int = 1280
    height: int = 720

    # 텍스트
    title_font: str = "Pretendard-Bold"
    title_size: int = 72
    title_color: str = "#FFFFFF"
    title_stroke_color: str = "#000000"
    title_stroke_width: int = 3

    # 배경
    overlay_color: str = "#000000"
    overlay_opacity: float = 0.4

    # 레이아웃
    text_position: str = "center"    # center, bottom
    padding: int = 40
    max_title_lines: int = 3
```

### 6.2 썸네일 생성기
```python
from PIL import Image, ImageDraw, ImageFont


class ThumbnailGenerator:
    def __init__(self, style: ThumbnailStyle | None = None):
        self.style = style or ThumbnailStyle()

    async def generate(
        self,
        title: str,
        background: VisualAsset | None,
        output_path: Path,
    ) -> Path:
        """썸네일 생성"""
        style = self.style

        # 1. 배경 이미지 준비
        if background and background.path:
            bg = Image.open(background.path)
        elif background and background.url:
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.get(background.url)
                from io import BytesIO
                bg = Image.open(BytesIO(response.content))
        else:
            bg = Image.new("RGB", (style.width, style.height), "#1a1a2e")

        # 리사이즈
        bg = bg.resize((style.width, style.height), Image.Resampling.LANCZOS)

        # 2. 오버레이 추가
        overlay = Image.new("RGBA", bg.size, (*self._hex_to_rgb(style.overlay_color), int(style.overlay_opacity * 255)))
        bg = bg.convert("RGBA")
        bg = Image.alpha_composite(bg, overlay)

        # 3. 텍스트 추가
        draw = ImageDraw.Draw(bg)

        try:
            font = ImageFont.truetype(style.title_font, style.title_size)
        except:
            font = ImageFont.load_default()

        # 텍스트 줄바꿈
        wrapped_title = self._wrap_text(title, font, style.width - style.padding * 2)

        # 텍스트 위치 계산
        bbox = draw.textbbox((0, 0), wrapped_title, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if style.text_position == "center":
            x = (style.width - text_width) // 2
            y = (style.height - text_height) // 2
        else:  # bottom
            x = (style.width - text_width) // 2
            y = style.height - text_height - style.padding * 2

        # 텍스트 그리기 (외곽선 + 본문)
        for dx in range(-style.title_stroke_width, style.title_stroke_width + 1):
            for dy in range(-style.title_stroke_width, style.title_stroke_width + 1):
                draw.text(
                    (x + dx, y + dy),
                    wrapped_title,
                    font=font,
                    fill=style.title_stroke_color
                )

        draw.text((x, y), wrapped_title, font=font, fill=style.title_color)

        # 4. 저장
        output_path = output_path.with_suffix(".jpg")
        bg.convert("RGB").save(output_path, "JPEG", quality=90)

        return output_path

    def _wrap_text(self, text: str, font, max_width: int) -> str:
        """텍스트 줄바꿈"""
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            bbox = font.getbbox(test_line)
            if bbox[2] <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        # 최대 줄 수 제한
        lines = lines[:self.style.max_title_lines]

        return "\n".join(lines)

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
```

---

## 7. 전체 파이프라인 통합

```python
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime


class VideoGenerationResult(BaseModel):
    """영상 생성 결과"""
    video_path: Path
    thumbnail_path: Path
    duration_seconds: float

    # 메타
    script_id: str
    channel_id: str
    generated_at: datetime

    # 사용된 에셋 정보
    tts_service: str
    visual_sources: list[str]


class VideoGenerationPipeline:
    """영상 생성 전체 파이프라인"""

    def __init__(
        self,
        tts_factory: TTSEngineFactory,
        visual_manager: VisualSourcingManager,
        compositor: FFmpegCompositor,
        thumbnail_generator: ThumbnailGenerator,
    ):
        self.tts_factory = tts_factory
        self.visual_manager = visual_manager
        self.compositor = compositor
        self.thumbnail_generator = thumbnail_generator

    async def generate(
        self,
        script: "GeneratedScript",
        persona: "Persona",
        output_dir: Path,
    ) -> VideoGenerationResult:
        """스크립트 → 완성 영상"""

        # 작업 디렉토리 생성
        work_dir = output_dir / script.id
        work_dir.mkdir(parents=True, exist_ok=True)

        # 1. TTS 생성
        tts_engine = self.tts_factory.get_engine(persona.voice.service)
        tts_result = await tts_engine.synthesize(
            text=script.script,
            config=VoiceConfig(
                service=persona.voice.service,
                voice_id=persona.voice.voice_id,
                speed=persona.voice.voice_settings.get("speed", 1.0),
            ),
            output_path=work_dir / "audio",
        )

        # 2. 자막 생성
        subtitle_generator = SubtitleGenerator()
        if tts_result.word_timestamps:
            subtitle = subtitle_generator.generate_from_timestamps(
                tts_result.word_timestamps
            )
        else:
            subtitle = subtitle_generator.generate_from_script(
                script.script,
                tts_result.duration_seconds,
            )

        # 3. 비주얼 소싱
        visuals = await self.visual_manager.source_visuals(
            keywords=script.topic.keywords[:5],
            duration_needed=tts_result.duration_seconds,
            config=VisualConfig(),
        )

        # 4. 영상 합성
        video_path = await self.compositor.compose(
            audio=tts_result,
            subtitle=subtitle,
            visuals=visuals,
            output_path=work_dir / f"{script.id}.mp4",
        )

        # 5. 썸네일 생성
        thumbnail_path = await self.thumbnail_generator.generate(
            title=script.topic.title,
            background=visuals[0] if visuals else None,
            output_path=work_dir / "thumbnail",
        )

        return VideoGenerationResult(
            video_path=video_path,
            thumbnail_path=thumbnail_path,
            duration_seconds=tts_result.duration_seconds,
            script_id=script.id,
            channel_id=script.channel_id,
            generated_at=datetime.utcnow(),
            tts_service=persona.voice.service,
            visual_sources=[v.source for v in visuals if v.source],
        )
```

---

## 8. Scene 기반 영상 생성 시스템 (BSForge 차별화)

### 8.1 개요
BSForge의 핵심 차별화 요소는 **AI 페르소나가 사실(Fact)과 의견(Opinion)을 구분하여 표현**하는 것입니다. Scene 기반 시스템은 이를 시각적으로 구현합니다.

### 8.2 SceneType (장면 유형)
```python
class SceneType(str, Enum):
    HOOK = "hook"              # 오프닝 훅 (시선 끌기)
    INTRO = "intro"            # 주제 소개
    CONTENT = "content"        # 본론 (사실 전달)
    EXAMPLE = "example"        # 예시/사례
    COMMENTARY = "commentary"  # AI 페르소나 의견/해석
    REACTION = "reaction"      # 감정적 반응
    CONCLUSION = "conclusion"  # 결론/요약
    CTA = "cta"               # Call to Action
```

### 8.3 VisualStyle (시각적 스타일)
```python
class VisualStyle(str, Enum):
    NEUTRAL = "neutral"    # 사실 전달 (기본 스타일)
    PERSONA = "persona"    # AI 의견 (강조 스타일: 테두리, 악센트 컬러)
    EMPHASIS = "emphasis"  # 핵심 결론 (화면 가득 텍스트)
```

### 8.4 TransitionType (전환 효과)
```python
class TransitionType(str, Enum):
    NONE = "none"
    FADE = "fade"          # 페이드 인/아웃
    CROSSFADE = "crossfade"
    ZOOM = "zoom"
    FLASH = "flash"        # 사실→의견 전환 시 플래시 효과
    SLIDE = "slide"
```

### 8.5 Scene 기반 파이프라인
```
SceneScript 생성 (LLM)
    ↓
Scene별 TTS 생성
    ↓
Scene별 자막 생성 (스타일 분기)
    ↓
Scene별 비주얼 소싱
    ↓
Scene별 트랜지션 적용
    ↓
FFmpeg 합성
```

### 8.6 시각적 차별화 예시
| Scene Type | Visual Style | 특징 |
|------------|--------------|------|
| CONTENT | NEUTRAL | 기본 배경, 흰색 자막 |
| COMMENTARY/REACTION | PERSONA | 악센트 컬러 테두리, 강조 효과 |
| CONCLUSION | EMPHASIS | 화면 중앙 큰 텍스트 |

### 8.7 자동 트랜지션 추천
```python
def apply_recommended_transitions(scenes: list[Scene]) -> list[Scene]:
    """연속된 Scene 간 적절한 트랜지션 자동 적용"""
    for i, scene in enumerate(scenes[1:], 1):
        prev = scenes[i-1]

        # 사실 → 의견: 플래시 효과
        if prev.visual_style == VisualStyle.NEUTRAL and scene.visual_style == VisualStyle.PERSONA:
            scene.transition_in = TransitionType.FLASH

        # 의견 → 사실: 페이드
        elif prev.visual_style == VisualStyle.PERSONA and scene.visual_style == VisualStyle.NEUTRAL:
            scene.transition_in = TransitionType.FADE

        # HOOK → 본론: 줌
        elif prev.scene_type == SceneType.HOOK:
            scene.transition_in = TransitionType.ZOOM
```

---

## 9. BGM (배경 음악) 시스템

### 9.1 개요
자동으로 YouTube에서 로열티 프리 BGM을 다운로드하고 영상에 믹싱합니다.

### 9.2 BGM 설정
```python
class BGMTrack(BaseModel):
    """개별 BGM 트랙 정보."""
    name: str                        # 트랙 식별 이름
    youtube_url: HttpUrl             # YouTube URL
    tags: list[str] = []             # 분위기 태그 (upbeat, calm, tech 등)
    default_volume: float = 0.15     # 기본 볼륨 (0.0-1.0)

class BGMConfig(BaseModel):
    """BGM 시스템 설정."""
    enabled: bool = True
    volume: float = 0.15             # 전체 BGM 볼륨
    cache_dir: str = "data/bgm"      # 다운로드 캐시 경로
    download_timeout: int = 300      # 다운로드 타임아웃 (초)
    tracks: list[BGMTrack] = []      # 사용할 트랙 목록
```

### 9.3 BGM 다운로더
```python
class BGMDownloader:
    """YouTube에서 BGM 다운로드 (yt-dlp 사용)."""

    async def download(self, track: BGMTrack) -> Path:
        """트랙 다운로드 (캐시된 경우 스킵)."""
        output_path = self.config.get_cache_path(track)

        if output_path.exists():
            return output_path

        # yt-dlp로 오디오만 추출 → MP3 변환
        ydl_opts = {
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([track.youtube_url])

        return output_path

    async def ensure_all_downloaded(self, tracks: list[BGMTrack]) -> dict[str, Path]:
        """모든 트랙 다운로드 보장."""
        results = {}
        for track in tracks:
            results[track.name] = await self.download(track)
        return results
```

### 9.4 BGM 선택기
```python
class BGMSelector:
    """영상에 맞는 BGM 선택."""

    def select(self, tags: list[str] | None = None) -> tuple[BGMTrack, Path] | None:
        """태그 기반 BGM 선택 (미래: 분위기 매칭)."""
        if not self._cached_tracks:
            return None

        # 현재: 랜덤 선택
        # TODO: 태그 매칭, 시리즈 일관성 등
        track = random.choice(list(self._cached_tracks.values()))
        return track
```

### 9.5 BGM 매니저
```python
class BGMManager:
    """BGM 파이프라인 통합 관리."""

    async def initialize(self) -> None:
        """시작 시 모든 트랙 다운로드."""
        self._cached_tracks = await self._downloader.ensure_all_downloaded(
            self.config.tracks
        )
        self._selector = BGMSelector(self.config, self._cached_tracks)

    async def get_bgm_for_video(self, mood_tags: list[str] | None = None) -> Path | None:
        """영상용 BGM 경로 반환."""
        if not self.config.enabled:
            return None

        result = self._selector.select(tags=mood_tags)
        return result[1] if result else None

    def get_volume(self) -> float:
        """설정된 볼륨 반환."""
        return self.config.volume
```

### 9.6 FFmpeg 믹싱
```python
# 음성 + BGM 믹싱 명령어
ffmpeg_cmd = [
    "ffmpeg", "-y",
    "-i", str(video_path),           # 원본 영상 (음성 포함)
    "-i", str(bgm_path),             # BGM
    "-filter_complex",
    f"[1:a]volume={bgm_volume}[bgm];"   # BGM 볼륨 조절
    "[0:a][bgm]amix=inputs=2:duration=first[aout]",  # 믹싱
    "-map", "0:v",                   # 원본 비디오
    "-map", "[aout]",                # 믹싱된 오디오
    "-c:v", "copy",                  # 비디오 재인코딩 안함
    "-c:a", "aac",
    str(output_path),
]
```

---

## 10. 구현 상세

### 10.1 실제 구현된 모듈

**TTS Services (`app/services/generator/tts/`)**:
- `BaseTTSEngine`: 추상 기반 클래스
- `EdgeTTSEngine`: 무료 Microsoft Edge TTS
- `ElevenLabsEngine`: 고품질 유료 TTS
- `TTSEngineFactory`: 서비스 선택 팩토리

**Subtitle (`app/services/generator/subtitle.py`)**:
- `SubtitleGenerator`: ASS/SRT 생성
- `SubtitleStyle`: 스타일 설정 (폰트, 색상, 위치)
- 단어 타임스탬프 기반 세그먼트 분할

**Visual (`app/services/generator/visual/`)**:
- `PexelsClient`: 스톡 영상/이미지 검색
- `AIImageGenerator`: DALL-E 이미지 생성
- `VisualSourcingManager`: 소싱 우선순위 관리

**Compositor (`app/services/generator/`)**:
- `FFmpegWrapper`: FFmpeg 명령어 래퍼
- `VideoCompositor`: 전체 합성 파이프라인
- Scene별 트랜지션 적용

**BGM (`app/services/generator/bgm/`)**:
- `BGMDownloader`: yt-dlp 기반 다운로더
- `BGMSelector`: 트랙 선택 로직
- `BGMManager`: 통합 관리자

**Scene (`app/models/scene.py`)**:
- `SceneType`: 8가지 장면 유형
- `VisualStyle`: 3가지 시각 스타일
- `TransitionType`: 6가지 전환 효과
- `Scene`, `SceneScript`: Pydantic 모델

### 10.2 파일 구조
```
app/services/generator/
├── __init__.py
├── pipeline.py              # 전체 파이프라인 통합
├── compositor.py            # FFmpeg 합성
├── ffmpeg.py               # FFmpeg 래퍼
├── subtitle.py             # 자막 생성
├── thumbnail.py            # 썸네일 생성
├── tts/
│   ├── __init__.py
│   ├── base.py             # BaseTTSEngine
│   ├── edge.py             # EdgeTTSEngine
│   ├── elevenlabs.py       # ElevenLabsEngine
│   └── factory.py          # TTSEngineFactory
├── visual/
│   ├── __init__.py
│   ├── pexels.py           # PexelsClient
│   ├── ai_image.py         # AIImageGenerator
│   └── manager.py          # VisualSourcingManager
└── bgm/
    ├── __init__.py
    ├── downloader.py       # BGMDownloader
    ├── selector.py         # BGMSelector
    └── manager.py          # BGMManager
```

---

## 11. 기술 스택 정리

| 컴포넌트 | 라이브러리 | 비고 |
|----------|------------|------|
| **TTS** | edge-tts, elevenlabs | 무료/유료 |
| **자막** | 자체 ASS/SRT 생성 | 스타일링 지원 |
| **비주얼** | httpx (Pexels API), openai (DALL-E) | 스톡/AI |
| **이미지 처리** | Pillow | 썸네일, 단색 배경 |
| **영상 합성** | FFmpeg (subprocess) | 핵심 |
| **음성 인식** | whisper | 타임스탬프 생성 |
| **BGM 다운로드** | yt-dlp | YouTube 오디오 추출 |
| **Scene 모델** | Pydantic | 타입 안전성 |
