# 🧪 A/B 테스트 시스템 설계

## 1. 개요

### 1.1 목표
- 채널 성과가 나오지 않을 때 **데이터 기반 최적화**
- 다양한 콘텐츠 변수를 체계적으로 테스트
- 통계적 유의성 기반 자동 의사결정
- 승리한 변형을 자동으로 기본값에 반영

### 1.2 핵심 원칙
```
1. 한 번에 하나의 변수만 테스트 (다변량은 고급)
2. 충분한 샘플 크기 확보 (최소 30개/변형)
3. 통계적 유의성 확인 (p < 0.05)
4. 실험 기간 고정 (외부 요인 통제)
```

---

## 2. 테스트 가능한 변수

### 2.1 변수 카테고리
```python
from enum import Enum


class ExperimentCategory(str, Enum):
    TOPIC = "topic"           # 주제 선정
    HOOK = "hook"             # 도입부 스타일
    TITLE = "title"           # 제목 형식
    THUMBNAIL = "thumbnail"   # 썸네일 스타일
    VOICE = "voice"           # TTS 설정
    SUBTITLE = "subtitle"     # 자막 스타일
    TIMING = "timing"         # 업로드 시간
    METADATA = "metadata"     # 태그, 설명


class ExperimentVariable(str, Enum):
    # Topic
    TOPIC_CATEGORY_MIX = "topic_category_mix"
    TOPIC_SOURCE_WEIGHT = "topic_source_weight"
    TOPIC_FRESHNESS_WEIGHT = "topic_freshness_weight"

    # Hook
    HOOK_STYLE = "hook_style"           # question, shock, info, story
    HOOK_LENGTH = "hook_length"         # short, medium, long
    HOOK_PERSONA_INTENSITY = "hook_persona_intensity"

    # Title
    TITLE_EMOJI = "title_emoji"         # none, minimal, heavy
    TITLE_LENGTH = "title_length"       # short (<40), medium, long (>60)
    TITLE_STYLE = "title_style"         # question, statement, clickbait

    # Thumbnail
    THUMB_COLOR_SCHEME = "thumb_color_scheme"   # bright, dark, contrast
    THUMB_TEXT_SIZE = "thumb_text_size"         # small, large, none
    THUMB_FACE = "thumb_face"                   # with_face, no_face
    THUMB_STYLE = "thumb_style"                 # minimal, busy, branded

    # Voice
    VOICE_GENDER = "voice_gender"
    VOICE_SPEED = "voice_speed"         # 0.9, 1.0, 1.1, 1.2
    VOICE_STYLE = "voice_style"         # calm, energetic, serious

    # Subtitle
    SUB_POSITION = "sub_position"       # bottom, center, top
    SUB_HIGHLIGHT = "sub_highlight"     # none, word, sentence
    SUB_SIZE = "sub_size"               # small, medium, large
    SUB_BACKGROUND = "sub_background"   # none, semi, solid

    # Timing
    UPLOAD_TIME_SLOT = "upload_time_slot"   # morning, lunch, evening, night
    UPLOAD_DAY = "upload_day"               # weekday, weekend

    # Metadata
    META_TAG_STRATEGY = "meta_tag_strategy"     # broad, niche, mixed
    META_DESC_LENGTH = "meta_desc_length"       # short, detailed
    META_HASHTAG_COUNT = "meta_hashtag_count"   # few (3), medium (5), many (8+)
```

### 2.2 변수별 변형 정의
```python
VARIABLE_VARIANTS = {
    ExperimentVariable.HOOK_STYLE: {
        "question": {
            "description": "질문으로 시작",
            "prompt_modifier": "Start with an engaging question",
            "examples": ["왜 개발자들이 ~할까요?", "~가 정말 필요할까요?"],
        },
        "shock": {
            "description": "충격적 사실로 시작",
            "prompt_modifier": "Start with a surprising fact or statistic",
            "examples": ["충격적이게도 ~", "믿기 힘들겠지만 ~"],
        },
        "info": {
            "description": "핵심 정보로 바로 시작",
            "prompt_modifier": "Start directly with the key information",
            "examples": ["오늘 알려드릴 건 ~", "핵심만 말씀드리면 ~"],
        },
        "story": {
            "description": "짧은 스토리/상황으로 시작",
            "prompt_modifier": "Start with a brief relatable scenario",
            "examples": ["어제 회사에서 ~", "최근에 이런 일이 있었는데 ~"],
        },
    },

    ExperimentVariable.TITLE_EMOJI: {
        "none": {
            "description": "이모지 없음",
            "config": {"include_emoji": False},
        },
        "minimal": {
            "description": "이모지 1개",
            "config": {"include_emoji": True, "max_emoji": 1},
        },
        "heavy": {
            "description": "이모지 2-3개",
            "config": {"include_emoji": True, "max_emoji": 3},
        },
    },

    ExperimentVariable.VOICE_SPEED: {
        "slow": {"speed": 0.9, "description": "느리게 (0.9x)"},
        "normal": {"speed": 1.0, "description": "보통 (1.0x)"},
        "fast": {"speed": 1.1, "description": "빠르게 (1.1x)"},
        "very_fast": {"speed": 1.2, "description": "매우 빠르게 (1.2x)"},
    },

    ExperimentVariable.THUMB_COLOR_SCHEME: {
        "bright": {
            "description": "밝은 색상 (노랑, 흰색 계열)",
            "config": {"background_colors": ["#FFEB3B", "#FFF9C4", "#FFFFFF"]},
        },
        "dark": {
            "description": "어두운 색상 (검정, 남색 계열)",
            "config": {"background_colors": ["#1a1a2e", "#16213e", "#0f0f23"]},
        },
        "contrast": {
            "description": "고대비 (빨강, 파랑)",
            "config": {"background_colors": ["#FF5252", "#2196F3", "#FF9800"]},
        },
    },

    ExperimentVariable.UPLOAD_TIME_SLOT: {
        "morning": {"hours": [7, 8, 9], "description": "아침 (7-9시)"},
        "lunch": {"hours": [11, 12, 13], "description": "점심 (11-13시)"},
        "evening": {"hours": [18, 19, 20], "description": "저녁 (18-20시)"},
        "night": {"hours": [21, 22, 23], "description": "밤 (21-23시)"},
    },

    # ... 나머지 변수들
}
```

---

## 3. 실험 스키마

### 3.1 데이터 모델
```python
from pydantic import BaseModel
from datetime import datetime
from enum import Enum
import uuid


class ExperimentStatus(str, Enum):
    DRAFT = "draft"           # 설정 중
    RUNNING = "running"       # 진행 중
    PAUSED = "paused"         # 일시 중지
    COMPLETED = "completed"   # 완료 (결과 확정)
    CANCELLED = "cancelled"   # 취소


class Variant(BaseModel):
    """실험 변형"""
    id: str
    name: str
    description: str

    # 변형 설정
    config: dict              # 적용할 설정값

    # 할당
    allocation_percent: float  # 트래픽 비율 (합계 100%)

    # 결과
    sample_count: int = 0
    metrics: dict = {}         # 수집된 지표


class Experiment(BaseModel):
    """A/B 테스트 실험"""
    id: str = str(uuid.uuid4())
    channel_id: str

    # 기본 정보
    name: str
    description: str
    hypothesis: str           # "훅을 질문형으로 바꾸면 시청 유지율이 높아질 것이다"

    # 실험 설정
    category: ExperimentCategory
    variable: ExperimentVariable
    variants: list[Variant]   # 최소 2개 (control + treatment)

    # 성공 지표
    primary_metric: str       # 주요 지표 (e.g., "avg_view_percentage")
    secondary_metrics: list[str] = []

    # 목표
    minimum_sample_size: int = 30      # 변형당 최소 샘플
    minimum_detectable_effect: float = 0.1  # 10% 차이 감지
    confidence_level: float = 0.95     # 95% 신뢰도

    # 기간
    start_date: datetime | None = None
    end_date: datetime | None = None
    max_duration_days: int = 14

    # 상태
    status: ExperimentStatus = ExperimentStatus.DRAFT

    # 결과
    winner_variant_id: str | None = None
    statistical_significance: float | None = None
    result_summary: str | None = None

    # 자동 적용
    auto_apply_winner: bool = True
    applied_at: datetime | None = None

    # 타임스탬프
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()


class ExperimentAssignment(BaseModel):
    """콘텐츠별 실험 할당"""
    experiment_id: str
    variant_id: str

    # 할당된 콘텐츠
    content_type: str         # "video", "script", "upload"
    content_id: str

    # 할당 시점
    assigned_at: datetime = datetime.utcnow()
```

### 3.2 DB 모델 (SQLAlchemy)
```python
class Experiment(Base, UUIDMixin, TimestampMixin):
    """A/B 테스트 실험"""
    __tablename__ = "experiments"

    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id")
    )

    # 기본 정보
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    hypothesis: Mapped[str] = mapped_column(Text, nullable=True)

    # 실험 설정
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    variable: Mapped[str] = mapped_column(String(50), nullable=False)
    variants: Mapped[list] = mapped_column(JSONB, nullable=False)

    # 지표
    primary_metric: Mapped[str] = mapped_column(String(50), nullable=False)
    secondary_metrics: Mapped[list] = mapped_column(ARRAY(String), default=list)

    # 설정
    min_sample_size: Mapped[int] = mapped_column(Integer, default=30)
    confidence_level: Mapped[float] = mapped_column(Float, default=0.95)
    max_duration_days: Mapped[int] = mapped_column(Integer, default=14)

    # 기간
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 상태
    status: Mapped[str] = mapped_column(String(20), default="draft")

    # 결과
    winner_variant_id: Mapped[str] = mapped_column(String(50), nullable=True)
    statistical_significance: Mapped[float] = mapped_column(Float, nullable=True)
    result_summary: Mapped[str] = mapped_column(Text, nullable=True)

    # 자동 적용
    auto_apply_winner: Mapped[bool] = mapped_column(Boolean, default=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)

    # 관계
    channel: Mapped["Channel"] = relationship()
    assignments: Mapped[list["ExperimentAssignment"]] = relationship(
        back_populates="experiment"
    )


class ExperimentAssignment(Base, UUIDMixin, TimestampMixin):
    """실험 할당 기록"""
    __tablename__ = "experiment_assignments"

    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id")
    )
    variant_id: Mapped[str] = mapped_column(String(50), nullable=False)

    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # 관계
    experiment: Mapped["Experiment"] = relationship(back_populates="assignments")

    __table_args__ = (
        Index("idx_assignment_experiment", "experiment_id"),
        Index("idx_assignment_content", "content_type", "content_id"),
    )
```

---

## 4. 실험 서비스

### 4.1 실험 관리
```python
from typing import Optional
import random


class ExperimentService:
    """A/B 테스트 실험 관리"""

    def __init__(self, db: Session):
        self.db = db

    async def create_experiment(
        self,
        channel_id: str,
        name: str,
        variable: ExperimentVariable,
        variants: list[dict],
        primary_metric: str,
        hypothesis: str | None = None,
    ) -> Experiment:
        """새 실험 생성"""

        # 변형 검증
        if len(variants) < 2:
            raise ValueError("At least 2 variants required (control + treatment)")

        total_allocation = sum(v.get("allocation_percent", 0) for v in variants)
        if abs(total_allocation - 100) > 0.01:
            raise ValueError("Variant allocations must sum to 100%")

        # 기존 실행 중 실험 체크 (같은 변수)
        existing = self.db.query(Experiment).filter(
            Experiment.channel_id == channel_id,
            Experiment.variable == variable.value,
            Experiment.status == "running",
        ).first()

        if existing:
            raise ValueError(f"Experiment for {variable} already running")

        experiment = Experiment(
            channel_id=channel_id,
            name=name,
            hypothesis=hypothesis,
            category=self._get_category(variable).value,
            variable=variable.value,
            variants=variants,
            primary_metric=primary_metric,
        )

        self.db.add(experiment)
        self.db.commit()

        return experiment

    async def start_experiment(self, experiment_id: str) -> Experiment:
        """실험 시작"""
        experiment = self._get_experiment(experiment_id)

        if experiment.status != "draft":
            raise ValueError(f"Cannot start experiment in {experiment.status} status")

        experiment.status = "running"
        experiment.start_date = datetime.utcnow()
        self.db.commit()

        return experiment

    async def assign_variant(
        self,
        channel_id: str,
        variable: ExperimentVariable,
        content_type: str,
        content_id: str,
    ) -> Optional[tuple[str, dict]]:
        """콘텐츠에 변형 할당"""

        # 실행 중인 실험 찾기
        experiment = self.db.query(Experiment).filter(
            Experiment.channel_id == channel_id,
            Experiment.variable == variable.value,
            Experiment.status == "running",
        ).first()

        if not experiment:
            return None

        # 가중치 기반 랜덤 할당
        variant = self._weighted_random_choice(experiment.variants)

        # 할당 기록
        assignment = ExperimentAssignment(
            experiment_id=experiment.id,
            variant_id=variant["id"],
            content_type=content_type,
            content_id=content_id,
        )
        self.db.add(assignment)
        self.db.commit()

        return variant["id"], variant.get("config", {})

    def _weighted_random_choice(self, variants: list[dict]) -> dict:
        """가중치 기반 랜덤 선택"""
        weights = [v["allocation_percent"] for v in variants]
        return random.choices(variants, weights=weights, k=1)[0]

    def _get_category(self, variable: ExperimentVariable) -> ExperimentCategory:
        """변수의 카테고리 반환"""
        category_map = {
            "topic_": ExperimentCategory.TOPIC,
            "hook_": ExperimentCategory.HOOK,
            "title_": ExperimentCategory.TITLE,
            "thumb_": ExperimentCategory.THUMBNAIL,
            "voice_": ExperimentCategory.VOICE,
            "sub_": ExperimentCategory.SUBTITLE,
            "upload_": ExperimentCategory.TIMING,
            "meta_": ExperimentCategory.METADATA,
        }
        for prefix, category in category_map.items():
            if variable.value.startswith(prefix):
                return category
        return ExperimentCategory.TOPIC
```

### 4.2 결과 분석
```python
import numpy as np
from scipy import stats


class ExperimentAnalyzer:
    """실험 결과 분석"""

    def __init__(self, db: Session):
        self.db = db

    async def analyze_experiment(
        self,
        experiment_id: str,
    ) -> dict:
        """실험 결과 분석"""
        experiment = self.db.query(Experiment).filter(
            Experiment.id == experiment_id
        ).first()

        if not experiment:
            raise ValueError("Experiment not found")

        # 변형별 데이터 수집
        variant_data = {}
        for variant in experiment.variants:
            data = await self._collect_variant_data(
                experiment.id,
                variant["id"],
                experiment.primary_metric,
            )
            variant_data[variant["id"]] = data

        # 통계 분석
        analysis = await self._statistical_analysis(
            variant_data,
            experiment.confidence_level,
        )

        # 샘플 크기 체크
        is_sufficient = all(
            len(data) >= experiment.min_sample_size
            for data in variant_data.values()
        )

        return {
            "experiment_id": experiment_id,
            "variant_data": variant_data,
            "analysis": analysis,
            "is_sufficient_sample": is_sufficient,
            "can_conclude": is_sufficient and analysis["is_significant"],
        }

    async def _collect_variant_data(
        self,
        experiment_id: str,
        variant_id: str,
        metric: str,
    ) -> list[float]:
        """변형별 지표 데이터 수집"""

        # 할당된 콘텐츠 조회
        assignments = self.db.query(ExperimentAssignment).filter(
            ExperimentAssignment.experiment_id == experiment_id,
            ExperimentAssignment.variant_id == variant_id,
        ).all()

        values = []
        for assignment in assignments:
            # 성과 데이터 조회
            if assignment.content_type == "video":
                performance = self.db.query(Performance).join(
                    Upload, Upload.id == Performance.upload_id
                ).join(
                    Video, Video.id == Upload.video_id
                ).filter(
                    Video.id == assignment.content_id
                ).first()

                if performance:
                    value = getattr(performance, metric, None)
                    if value is not None:
                        values.append(value)

        return values

    async def _statistical_analysis(
        self,
        variant_data: dict[str, list[float]],
        confidence_level: float,
    ) -> dict:
        """통계적 유의성 분석"""

        variants = list(variant_data.keys())

        if len(variants) < 2:
            return {"error": "Need at least 2 variants"}

        # 2개 변형: t-test
        if len(variants) == 2:
            control_data = variant_data[variants[0]]
            treatment_data = variant_data[variants[1]]

            if len(control_data) < 2 or len(treatment_data) < 2:
                return {
                    "is_significant": False,
                    "reason": "Insufficient data",
                }

            # Welch's t-test (unequal variance)
            t_stat, p_value = stats.ttest_ind(
                control_data,
                treatment_data,
                equal_var=False
            )

            # 효과 크기 (Cohen's d)
            effect_size = self._cohens_d(control_data, treatment_data)

            # 각 변형 통계
            variant_stats = {}
            for variant_id, data in variant_data.items():
                variant_stats[variant_id] = {
                    "n": len(data),
                    "mean": np.mean(data) if data else 0,
                    "std": np.std(data) if data else 0,
                    "ci_95": self._confidence_interval(data, 0.95) if data else (0, 0),
                }

            # 승자 결정
            winner = None
            if p_value < (1 - confidence_level):
                means = {v: np.mean(d) for v, d in variant_data.items() if d}
                winner = max(means, key=means.get)

            return {
                "test": "welch_t_test",
                "t_statistic": t_stat,
                "p_value": p_value,
                "effect_size": effect_size,
                "is_significant": p_value < (1 - confidence_level),
                "confidence_level": confidence_level,
                "variant_stats": variant_stats,
                "winner": winner,
                "improvement": self._calculate_improvement(variant_data, winner) if winner else None,
            }

        # 3개 이상: ANOVA
        else:
            groups = [variant_data[v] for v in variants if variant_data[v]]
            f_stat, p_value = stats.f_oneway(*groups)

            return {
                "test": "anova",
                "f_statistic": f_stat,
                "p_value": p_value,
                "is_significant": p_value < (1 - confidence_level),
            }

    def _cohens_d(self, group1: list, group2: list) -> float:
        """Cohen's d 효과 크기"""
        n1, n2 = len(group1), len(group2)
        var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)

        pooled_std = np.sqrt(((n1 - 1) * var1 + (n2 - 1) * var2) / (n1 + n2 - 2))

        if pooled_std == 0:
            return 0

        return (np.mean(group1) - np.mean(group2)) / pooled_std

    def _confidence_interval(self, data: list, confidence: float) -> tuple:
        """신뢰구간 계산"""
        n = len(data)
        mean = np.mean(data)
        se = stats.sem(data)
        h = se * stats.t.ppf((1 + confidence) / 2, n - 1)
        return (mean - h, mean + h)

    def _calculate_improvement(
        self,
        variant_data: dict,
        winner: str,
    ) -> float:
        """개선율 계산"""
        variants = list(variant_data.keys())
        control = variants[0]  # 첫 번째가 control

        control_mean = np.mean(variant_data[control])
        winner_mean = np.mean(variant_data[winner])

        if control_mean == 0:
            return 0

        return (winner_mean - control_mean) / control_mean * 100


class ExperimentConcluder:
    """실험 종료 및 적용"""

    def __init__(self, db: Session, analyzer: ExperimentAnalyzer):
        self.db = db
        self.analyzer = analyzer

    async def check_and_conclude(self, experiment_id: str) -> dict:
        """실험 종료 조건 체크 및 결론"""
        experiment = self.db.query(Experiment).filter(
            Experiment.id == experiment_id
        ).first()

        if experiment.status != "running":
            return {"status": "not_running"}

        # 분석
        analysis = await self.analyzer.analyze_experiment(experiment_id)

        # 종료 조건 체크
        should_conclude = False
        reason = None

        # 1. 충분한 샘플 + 유의미한 결과
        if analysis["can_conclude"]:
            should_conclude = True
            reason = "significant_result"

        # 2. 최대 기간 도달
        if experiment.start_date:
            days_running = (datetime.utcnow() - experiment.start_date).days
            if days_running >= experiment.max_duration_days:
                should_conclude = True
                reason = "max_duration_reached"

        if should_conclude:
            return await self._conclude_experiment(experiment, analysis, reason)

        return {
            "status": "running",
            "analysis": analysis,
        }

    async def _conclude_experiment(
        self,
        experiment: Experiment,
        analysis: dict,
        reason: str,
    ) -> dict:
        """실험 종료 처리"""

        winner = analysis["analysis"].get("winner")
        significance = analysis["analysis"].get("p_value")
        improvement = analysis["analysis"].get("improvement")

        # 결과 요약 생성
        if winner:
            summary = f"Winner: {winner} ({improvement:+.1f}% improvement, p={significance:.4f})"
        else:
            summary = f"No significant winner found (p={significance:.4f})"

        # 실험 업데이트
        experiment.status = "completed"
        experiment.end_date = datetime.utcnow()
        experiment.winner_variant_id = winner
        experiment.statistical_significance = 1 - significance if significance else None
        experiment.result_summary = summary

        self.db.commit()

        # 자동 적용
        if experiment.auto_apply_winner and winner:
            await self._apply_winner(experiment, winner)

        return {
            "status": "completed",
            "reason": reason,
            "winner": winner,
            "summary": summary,
            "applied": experiment.auto_apply_winner and winner is not None,
        }

    async def _apply_winner(self, experiment: Experiment, winner_id: str):
        """승리한 변형을 채널 설정에 적용"""

        # 변형 찾기
        winner_variant = next(
            (v for v in experiment.variants if v["id"] == winner_id),
            None
        )

        if not winner_variant:
            return

        config = winner_variant.get("config", {})

        # 채널 설정 업데이트
        channel = self.db.query(Channel).filter(
            Channel.id == experiment.channel_id
        ).first()

        # 변수 타입에 따라 적절한 설정 업데이트
        variable = ExperimentVariable(experiment.variable)

        if variable.value.startswith("hook_"):
            channel.content_config = {
                **channel.content_config,
                "hook": {**channel.content_config.get("hook", {}), **config},
            }
        elif variable.value.startswith("title_"):
            channel.content_config = {
                **channel.content_config,
                "title": {**channel.content_config.get("title", {}), **config},
            }
        elif variable.value.startswith("voice_"):
            persona = channel.persona
            persona.voice_settings = {**persona.voice_settings, **config}
        # ... 다른 변수들

        experiment.applied_at = datetime.utcnow()
        self.db.commit()
```

---

## 5. 파이프라인 통합

### 5.1 스크립트 생성 시 실험 적용
```python
class ScriptGenerator:
    def __init__(
        self,
        experiment_service: ExperimentService,
        # ... 기존 의존성
    ):
        self.experiment_service = experiment_service

    async def generate(
        self,
        topic: Topic,
        persona: Persona,
        channel: Channel,
    ) -> GeneratedScript:

        # 실험 변형 할당 체크
        hook_config = persona.communication_style.get("hook", {})

        # 훅 스타일 실험
        hook_assignment = await self.experiment_service.assign_variant(
            channel_id=str(channel.id),
            variable=ExperimentVariable.HOOK_STYLE,
            content_type="script",
            content_id=str(topic.id),
        )

        if hook_assignment:
            variant_id, variant_config = hook_assignment
            hook_config = {**hook_config, **variant_config}

        # 생성 컨텍스트에 실험 설정 반영
        generation_config = GenerationConfig(
            hook_style=hook_config.get("style", "info"),
            hook_prompt_modifier=hook_config.get("prompt_modifier"),
            # ... 기타 설정
        )

        script = await self._generate_with_config(topic, persona, generation_config)

        return script
```

### 5.2 메타데이터 생성 시 실험 적용
```python
class MetadataGenerator:
    async def generate(
        self,
        script: GeneratedScript,
        channel: Channel,
    ) -> UploadMetadata:

        # 제목 이모지 실험
        title_assignment = await self.experiment_service.assign_variant(
            channel_id=str(channel.id),
            variable=ExperimentVariable.TITLE_EMOJI,
            content_type="video",
            content_id=str(script.id),
        )

        title_config = self.default_title_config.copy()
        if title_assignment:
            _, variant_config = title_assignment
            title_config.update(variant_config)

        title = await self._generate_title(script, title_config)

        # ...
```

---

## 6. 대시보드 UI

### 6.1 실험 목록
```tsx
// 실험 목록 카드
const ExperimentCard: React.FC<{ experiment: Experiment }> = ({ experiment }) => {
  const statusColors = {
    draft: 'gray',
    running: 'blue',
    completed: 'green',
    cancelled: 'red',
  };

  return (
    <Card>
      <CardHeader>
        <Badge color={statusColors[experiment.status]}>
          {experiment.status}
        </Badge>
        <h3>{experiment.name}</h3>
        <span className="variable">{experiment.variable}</span>
      </CardHeader>

      <CardBody>
        <p className="hypothesis">{experiment.hypothesis}</p>

        {/* 변형별 현황 */}
        <div className="variants">
          {experiment.variants.map(variant => (
            <VariantProgress
              key={variant.id}
              variant={variant}
              targetSample={experiment.min_sample_size}
            />
          ))}
        </div>

        {/* 중간 결과 (실행 중) */}
        {experiment.status === 'running' && (
          <InterimResults experimentId={experiment.id} />
        )}

        {/* 최종 결과 (완료) */}
        {experiment.status === 'completed' && (
          <FinalResults
            winner={experiment.winner_variant_id}
            summary={experiment.result_summary}
          />
        )}
      </CardBody>
    </Card>
  );
};
```

### 6.2 실험 생성 폼
```tsx
const CreateExperimentForm: React.FC = () => {
  const [variable, setVariable] = useState<ExperimentVariable | null>(null);

  return (
    <Form onSubmit={handleSubmit}>
      <FormField label="실험 변수">
        <Select
          options={Object.values(ExperimentVariable)}
          value={variable}
          onChange={setVariable}
        />
      </FormField>

      {variable && (
        <>
          <FormField label="가설">
            <Textarea
              placeholder="예: 질문형 훅이 시청 유지율을 높일 것이다"
            />
          </FormField>

          <FormField label="변형">
            <VariantSelector
              variable={variable}
              variants={VARIABLE_VARIANTS[variable]}
            />
          </FormField>

          <FormField label="주요 지표">
            <Select options={METRIC_OPTIONS} />
          </FormField>

          <FormField label="최소 샘플 크기">
            <NumberInput min={10} max={100} defaultValue={30} />
          </FormField>
        </>
      )}

      <Button type="submit">실험 생성</Button>
    </Form>
  );
};
```

### 6.3 결과 시각화
```tsx
const ExperimentResults: React.FC<{ experimentId: string }> = ({ experimentId }) => {
  const { data: analysis } = useQuery(['experiment-analysis', experimentId]);

  return (
    <div className="experiment-results">
      {/* 변형별 비교 차트 */}
      <Card title="변형별 성과 비교">
        <BarChart
          data={Object.entries(analysis.variant_stats).map(([id, stats]) => ({
            variant: id,
            mean: stats.mean,
            ci_lower: stats.ci_95[0],
            ci_upper: stats.ci_95[1],
          }))}
          xKey="variant"
          yKey="mean"
          errorBars={true}
        />
      </Card>

      {/* 통계 요약 */}
      <Card title="통계 분석">
        <StatRow label="테스트" value={analysis.analysis.test} />
        <StatRow label="p-value" value={analysis.analysis.p_value.toFixed(4)} />
        <StatRow
          label="유의성"
          value={analysis.analysis.is_significant ? '✅ 유의미' : '❌ 유의미하지 않음'}
        />
        {analysis.analysis.winner && (
          <>
            <StatRow label="승자" value={analysis.analysis.winner} />
            <StatRow
              label="개선율"
              value={`${analysis.analysis.improvement.toFixed(1)}%`}
            />
          </>
        )}
      </Card>

      {/* 신뢰구간 시각화 */}
      <Card title="신뢰구간 (95%)">
        <ConfidenceIntervalChart data={analysis.variant_stats} />
      </Card>
    </div>
  );
};
```

---

## 7. 자동 실험 제안

### 7.1 성과 저조 시 자동 제안
```python
class ExperimentSuggester:
    """채널 성과 기반 실험 제안"""

    # 지표별 개선 제안
    METRIC_SUGGESTIONS = {
        "low_ctr": [
            (ExperimentVariable.TITLE_STYLE, "제목 스타일이 CTR에 영향"),
            (ExperimentVariable.THUMB_COLOR_SCHEME, "썸네일 색상이 클릭 유도"),
            (ExperimentVariable.TITLE_EMOJI, "이모지가 눈길을 끔"),
        ],
        "low_retention": [
            (ExperimentVariable.HOOK_STYLE, "훅 스타일이 초반 이탈에 영향"),
            (ExperimentVariable.VOICE_SPEED, "말 속도가 집중도에 영향"),
            (ExperimentVariable.HOOK_LENGTH, "훅 길이가 이탈률에 영향"),
        ],
        "low_engagement": [
            (ExperimentVariable.HOOK_STYLE, "감정적 훅이 반응 유도"),
            (ExperimentVariable.META_HASHTAG_COUNT, "해시태그가 노출에 영향"),
        ],
        "low_views": [
            (ExperimentVariable.UPLOAD_TIME_SLOT, "업로드 시간이 노출에 영향"),
            (ExperimentVariable.TOPIC_CATEGORY_MIX, "주제 선정이 수요에 영향"),
        ],
    }

    async def suggest_experiments(
        self,
        channel_id: str,
        recent_days: int = 14,
    ) -> list[dict]:
        """채널 성과 분석 후 실험 제안"""

        # 최근 성과 분석
        performance = await self._analyze_recent_performance(channel_id, recent_days)

        suggestions = []

        # CTR 저조
        if performance["avg_ctr"] < 0.02:  # 2% 미만
            for variable, reason in self.METRIC_SUGGESTIONS["low_ctr"]:
                if not await self._has_recent_experiment(channel_id, variable):
                    suggestions.append({
                        "variable": variable,
                        "reason": reason,
                        "priority": "high" if performance["avg_ctr"] < 0.01 else "medium",
                        "current_value": f"CTR {performance['avg_ctr']:.1%}",
                    })

        # 시청 유지율 저조
        if performance["avg_retention"] < 0.4:  # 40% 미만
            for variable, reason in self.METRIC_SUGGESTIONS["low_retention"]:
                if not await self._has_recent_experiment(channel_id, variable):
                    suggestions.append({
                        "variable": variable,
                        "reason": reason,
                        "priority": "high",
                        "current_value": f"유지율 {performance['avg_retention']:.0%}",
                    })

        # ... 다른 지표들

        return sorted(suggestions, key=lambda x: x["priority"] == "high", reverse=True)
```

---

## 8. 성과 지표 정의

```python
class ExperimentMetrics:
    """실험에 사용할 수 있는 지표"""

    METRICS = {
        # 노출/클릭
        "impressions": {
            "name": "노출수",
            "description": "영상이 노출된 횟수",
            "higher_is_better": True,
        },
        "ctr": {
            "name": "클릭률",
            "description": "노출 대비 클릭 비율",
            "higher_is_better": True,
        },

        # 시청
        "views": {
            "name": "조회수",
            "description": "총 조회수",
            "higher_is_better": True,
        },
        "avg_view_duration": {
            "name": "평균 시청 시간",
            "description": "평균 시청 시간 (초)",
            "higher_is_better": True,
        },
        "avg_view_percentage": {
            "name": "평균 시청 비율",
            "description": "영상 길이 대비 시청 비율",
            "higher_is_better": True,
        },

        # 참여
        "likes": {
            "name": "좋아요",
            "description": "좋아요 수",
            "higher_is_better": True,
        },
        "comments": {
            "name": "댓글",
            "description": "댓글 수",
            "higher_is_better": True,
        },
        "engagement_rate": {
            "name": "참여율",
            "description": "(좋아요+댓글) / 조회수",
            "higher_is_better": True,
        },

        # 구독
        "subscribers_gained": {
            "name": "신규 구독자",
            "description": "영상을 통한 신규 구독자",
            "higher_is_better": True,
        },
    }

    # 추천 주요 지표 (변수별)
    RECOMMENDED_PRIMARY = {
        ExperimentVariable.HOOK_STYLE: "avg_view_percentage",
        ExperimentVariable.TITLE_EMOJI: "ctr",
        ExperimentVariable.THUMB_COLOR_SCHEME: "ctr",
        ExperimentVariable.VOICE_SPEED: "avg_view_percentage",
        ExperimentVariable.UPLOAD_TIME_SLOT: "views",
    }
```

---

## 9. 기술 스택 추가

| 컴포넌트 | 라이브러리 | 비고 |
|----------|------------|------|
| **통계 분석** | scipy.stats | t-test, ANOVA |
| **수치 계산** | numpy | 평균, 표준편차 |
| **시각화** | recharts (React) | 차트 |
