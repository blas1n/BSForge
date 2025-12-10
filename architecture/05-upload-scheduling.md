# 📤 업로드 & 최적 시간 시스템 상세 설계

## 1. 개요

### 1.1 목표
- YouTube API 통한 자동 업로드
- 채널별 최적 업로드 시간 분석 및 적용
- 메타데이터 (제목, 설명, 태그) 자동 생성
- 멀티 플랫폼 확장 대비 (TikTok, Reels)

### 1.2 파이프라인 흐름
```
영상 완성 → 메타데이터 생성 → 최적 시간 계산 → 스케줄링 → 업로드 → 성과 추적
```

---

## 2. YouTube API 연동

### 2.1 인증 설정
```python
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pathlib import Path
import pickle


class YouTubeAuth:
    """YouTube API 인증 관리"""
    
    SCOPES = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]
    
    def __init__(
        self,
        client_secrets_file: Path,
        token_file: Path,
    ):
        self.client_secrets_file = client_secrets_file
        self.token_file = token_file
        self._credentials: Credentials | None = None
    
    def get_credentials(self) -> Credentials:
        """OAuth 인증 정보 획득"""
        if self._credentials and self._credentials.valid:
            return self._credentials
        
        # 저장된 토큰 확인
        if self.token_file.exists():
            with open(self.token_file, "rb") as f:
                self._credentials = pickle.load(f)
        
        # 토큰 갱신 또는 새 인증
        if not self._credentials or not self._credentials.valid:
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.client_secrets_file),
                    self.SCOPES,
                )
                self._credentials = flow.run_local_server(port=0)
            
            # 토큰 저장
            with open(self.token_file, "wb") as f:
                pickle.dump(self._credentials, f)
        
        return self._credentials
    
    def get_youtube_service(self):
        """YouTube Data API 서비스 객체"""
        return build("youtube", "v3", credentials=self.get_credentials())
    
    def get_analytics_service(self):
        """YouTube Analytics API 서비스 객체"""
        return build("youtubeAnalytics", "v2", credentials=self.get_credentials())
```

### 2.2 업로드 서비스
```python
from pydantic import BaseModel
from enum import Enum
from datetime import datetime
from typing import Optional
import httplib2


class PrivacyStatus(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    UNLISTED = "unlisted"


class VideoCategory(str, Enum):
    """YouTube 카테고리 ID"""
    FILM = "1"
    AUTOS = "2"
    MUSIC = "10"
    PETS = "15"
    SPORTS = "17"
    GAMING = "20"
    PEOPLE_BLOGS = "22"
    COMEDY = "23"
    ENTERTAINMENT = "24"
    NEWS = "25"
    HOWTO_STYLE = "26"
    EDUCATION = "27"
    SCIENCE_TECH = "28"
    NONPROFITS = "29"


class UploadMetadata(BaseModel):
    """업로드 메타데이터"""
    title: str
    description: str
    tags: list[str]
    category_id: str = VideoCategory.SCIENCE_TECH
    
    # 공개 설정
    privacy_status: PrivacyStatus = PrivacyStatus.PRIVATE
    
    # 예약 업로드
    scheduled_at: datetime | None = None
    
    # Shorts 관련
    is_shorts: bool = True
    
    # 추가 설정
    made_for_kids: bool = False
    default_language: str = "ko"
    
    # 썸네일
    thumbnail_path: Path | None = None


class UploadResult(BaseModel):
    """업로드 결과"""
    video_id: str
    youtube_url: str
    status: str
    uploaded_at: datetime
    scheduled_at: datetime | None = None


class YouTubeUploader:
    """YouTube 업로드 서비스"""
    
    MAX_RETRIES = 3
    
    def __init__(self, auth: YouTubeAuth):
        self.auth = auth
        self.youtube = auth.get_youtube_service()
    
    async def upload(
        self,
        video_path: Path,
        metadata: UploadMetadata,
    ) -> UploadResult:
        """영상 업로드"""
        
        # 요청 바디 구성
        body = {
            "snippet": {
                "title": metadata.title[:100],  # 최대 100자
                "description": metadata.description[:5000],  # 최대 5000자
                "tags": metadata.tags[:500],  # 최대 500개
                "categoryId": metadata.category_id,
                "defaultLanguage": metadata.default_language,
            },
            "status": {
                "privacyStatus": metadata.privacy_status,
                "selfDeclaredMadeForKids": metadata.made_for_kids,
            },
        }
        
        # 예약 업로드
        if metadata.scheduled_at and metadata.privacy_status == PrivacyStatus.PRIVATE:
            body["status"]["privacyStatus"] = "private"
            body["status"]["publishAt"] = metadata.scheduled_at.isoformat() + "Z"
        
        # 미디어 파일
        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024,  # 1MB 청크
        )
        
        # 업로드 요청
        request = self.youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )
        
        # 재개 가능한 업로드 실행
        response = await self._resumable_upload(request)
        
        # 썸네일 업로드
        if metadata.thumbnail_path:
            await self._upload_thumbnail(response["id"], metadata.thumbnail_path)
        
        return UploadResult(
            video_id=response["id"],
            youtube_url=f"https://youtube.com/shorts/{response['id']}" if metadata.is_shorts 
                        else f"https://youtube.com/watch?v={response['id']}",
            status=response["status"]["uploadStatus"],
            uploaded_at=datetime.utcnow(),
            scheduled_at=metadata.scheduled_at,
        )
    
    async def _resumable_upload(self, request) -> dict:
        """재개 가능한 업로드 (청크 단위)"""
        response = None
        error = None
        retry = 0
        
        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    print(f"Upload progress: {int(status.progress() * 100)}%")
            except httplib2.HttpLib2Error as e:
                error = e
                if retry < self.MAX_RETRIES:
                    retry += 1
                    print(f"Retry {retry}/{self.MAX_RETRIES}")
                    continue
                raise
        
        return response
    
    async def _upload_thumbnail(self, video_id: str, thumbnail_path: Path):
        """썸네일 업로드"""
        media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
        
        self.youtube.thumbnails().set(
            videoId=video_id,
            media_body=media,
        ).execute()
    
    async def update_metadata(
        self,
        video_id: str,
        metadata: UploadMetadata,
    ):
        """메타데이터 업데이트"""
        body = {
            "id": video_id,
            "snippet": {
                "title": metadata.title,
                "description": metadata.description,
                "tags": metadata.tags,
                "categoryId": metadata.category_id,
            },
        }
        
        self.youtube.videos().update(
            part="snippet",
            body=body,
        ).execute()
    
    async def set_publish_time(
        self,
        video_id: str,
        publish_at: datetime,
    ):
        """공개 예약 시간 설정"""
        body = {
            "id": video_id,
            "status": {
                "privacyStatus": "private",
                "publishAt": publish_at.isoformat() + "Z",
            },
        }
        
        self.youtube.videos().update(
            part="status",
            body=body,
        ).execute()
```

---

## 3. 메타데이터 자동 생성

### 3.1 메타데이터 생성기
```python
from pydantic import BaseModel


class MetadataGeneratorConfig(BaseModel):
    """메타데이터 생성 설정"""
    
    # 제목
    max_title_length: int = 70       # 클릭 유도 위해 짧게
    include_emoji: bool = True
    title_style: str = "hook"        # hook, question, statement
    
    # 설명
    max_description_length: int = 500
    include_timestamps: bool = False  # Shorts는 불필요
    include_hashtags: bool = True
    
    # 태그
    max_tags: int = 30
    include_trending_tags: bool = True
    
    # 채널 고정 정보
    channel_hashtags: list[str] = []
    channel_links: list[str] = []


class MetadataGenerator:
    """LLM 기반 메타데이터 생성"""
    
    def __init__(
        self, 
        llm_client,
        config: MetadataGeneratorConfig | None = None,
    ):
        self.llm = llm_client
        self.config = config or MetadataGeneratorConfig()
    
    async def generate(
        self,
        script: str,
        topic: dict,
        channel_info: dict,
    ) -> UploadMetadata:
        """메타데이터 자동 생성"""
        
        # 1. 제목 생성
        title = await self._generate_title(script, topic)
        
        # 2. 설명 생성
        description = await self._generate_description(script, topic, channel_info)
        
        # 3. 태그 생성
        tags = await self._generate_tags(script, topic)
        
        return UploadMetadata(
            title=title,
            description=description,
            tags=tags,
            is_shorts=True,
        )
    
    async def _generate_title(self, script: str, topic: dict) -> str:
        """클릭 유도 제목 생성"""
        prompt = f"""YouTube Shorts 제목을 생성해주세요.

스크립트:
{script[:500]}

주제: {topic.get('title', '')}
키워드: {', '.join(topic.get('keywords', []))}

요구사항:
- 최대 {self.config.max_title_length}자
- 호기심 유발, 클릭 유도
- 과장 없이 핵심만
- 이모지 {'1-2개 포함' if self.config.include_emoji else '미포함'}
- 스타일: {self.config.title_style}

제목만 출력:"""

        response = await self.llm.complete(prompt)
        return response.strip()[:self.config.max_title_length]
    
    async def _generate_description(
        self, 
        script: str, 
        topic: dict,
        channel_info: dict,
    ) -> str:
        """설명 생성"""
        prompt = f"""YouTube Shorts 설명을 생성해주세요.

스크립트:
{script[:500]}

주제: {topic.get('title', '')}

요구사항:
- 최대 {self.config.max_description_length}자
- 첫 2줄이 가장 중요 (미리보기에 표시됨)
- 핵심 내용 요약
- 해시태그 3-5개 포함

설명만 출력:"""

        description = await self.llm.complete(prompt)
        
        # 채널 고정 정보 추가
        if self.config.channel_hashtags:
            hashtags = " ".join(f"#{tag}" for tag in self.config.channel_hashtags)
            description += f"\n\n{hashtags}"
        
        if self.config.channel_links:
            description += "\n\n" + "\n".join(self.config.channel_links)
        
        return description[:5000]
    
    async def _generate_tags(self, script: str, topic: dict) -> list[str]:
        """태그 생성"""
        # 기본 태그: 주제 키워드
        tags = list(topic.get('keywords', []))[:10]
        
        # LLM으로 추가 태그 생성
        prompt = f"""YouTube 검색 최적화를 위한 태그를 생성해주세요.

주제: {topic.get('title', '')}
키워드: {', '.join(topic.get('keywords', []))}

요구사항:
- 관련 검색어 15개
- 한국어 + 영어 혼합
- 구체적인 것부터 일반적인 것 순서
- 쉼표로 구분하여 출력

태그만 출력:"""

        response = await self.llm.complete(prompt)
        additional_tags = [t.strip() for t in response.split(",")]
        
        tags.extend(additional_tags)
        
        # 중복 제거 + 개수 제한
        seen = set()
        unique_tags = []
        for tag in tags:
            if tag.lower() not in seen and tag:
                seen.add(tag.lower())
                unique_tags.append(tag)
        
        return unique_tags[:self.config.max_tags]
```

---

## 4. 최적 업로드 시간 분석

### 4.1 시간 분석 스키마
```python
from pydantic import BaseModel
from datetime import datetime, time
from enum import Enum


class TimeSlot(BaseModel):
    """시간대 슬롯"""
    hour: int                    # 0-23
    day_of_week: int | None = None  # 0=월, 6=일 (None이면 모든 요일)
    
    # 성과 지표
    avg_views: float = 0
    avg_engagement: float = 0
    sample_count: int = 0
    
    # 점수 (정규화)
    score: float = 0


class TimeAnalysisResult(BaseModel):
    """시간 분석 결과"""
    channel_id: str
    analyzed_at: datetime
    
    # 최적 시간 (순위별)
    best_slots: list[TimeSlot]
    
    # 피해야 할 시간
    worst_slots: list[TimeSlot]
    
    # 요일별 최적 시간
    best_by_day: dict[int, list[TimeSlot]]  # day -> slots
    
    # 분석 기간
    data_from: datetime
    data_to: datetime
    total_videos_analyzed: int


class SchedulePreference(BaseModel):
    """업로드 스케줄 선호 설정"""
    
    # 허용 시간대
    allowed_hours: list[int] = list(range(6, 24))  # 6시-23시
    
    # 선호 요일 (None이면 모든 요일)
    preferred_days: list[int] | None = None
    
    # 최소 간격 (같은 채널 영상 간)
    min_interval_hours: int = 4
    
    # 최대 일일 업로드
    max_daily_uploads: int = 3
    
    # 피크 시간 가중치
    peak_hour_weight: float = 1.5
```

### 4.2 YouTube Analytics 수집기
```python
from datetime import datetime, timedelta


class YouTubeAnalyticsCollector:
    """YouTube Analytics 데이터 수집"""
    
    def __init__(self, auth: YouTubeAuth):
        self.analytics = auth.get_analytics_service()
        self.youtube = auth.get_youtube_service()
    
    async def get_video_performance(
        self,
        channel_id: str,
        days: int = 90,
    ) -> list[dict]:
        """채널 영상별 성과 데이터"""
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)
        
        # 채널 영상 목록 조회
        videos = await self._get_channel_videos(channel_id)
        
        performance_data = []
        
        for video in videos:
            video_id = video["id"]
            published_at = datetime.fromisoformat(
                video["snippet"]["publishedAt"].replace("Z", "+00:00")
            )
            
            # Analytics 데이터 조회
            response = self.analytics.reports().query(
                ids=f"channel=={channel_id}",
                startDate=start_date.isoformat(),
                endDate=end_date.isoformat(),
                metrics="views,likes,comments,averageViewDuration,averageViewPercentage",
                dimensions="video",
                filters=f"video=={video_id}",
            ).execute()
            
            if response.get("rows"):
                row = response["rows"][0]
                performance_data.append({
                    "video_id": video_id,
                    "published_at": published_at,
                    "published_hour": published_at.hour,
                    "published_day": published_at.weekday(),
                    "views": row[1],
                    "likes": row[2],
                    "comments": row[3],
                    "avg_view_duration": row[4],
                    "avg_view_percentage": row[5],
                    "engagement_rate": (row[2] + row[3]) / max(row[1], 1),
                })
        
        return performance_data
    
    async def _get_channel_videos(self, channel_id: str) -> list[dict]:
        """채널의 모든 영상 조회"""
        videos = []
        next_page_token = None
        
        while True:
            response = self.youtube.search().list(
                channelId=channel_id,
                part="id,snippet",
                type="video",
                maxResults=50,
                pageToken=next_page_token,
            ).execute()
            
            videos.extend(response.get("items", []))
            
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
        
        return videos
    
    async def get_audience_retention(
        self,
        channel_id: str,
        days: int = 28,
    ) -> dict:
        """시청자 활동 시간대 분석"""
        end_date = datetime.utcnow().date()
        start_date = end_date - timedelta(days=days)
        
        response = self.analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date.isoformat(),
            endDate=end_date.isoformat(),
            metrics="views",
            dimensions="day,hour",  # 요일 + 시간
        ).execute()
        
        # 시간대별 집계
        hourly_views = {}
        for row in response.get("rows", []):
            day = int(row[0])  # 요일
            hour = int(row[1])  # 시간
            views = row[2]
            
            key = (day, hour)
            hourly_views[key] = hourly_views.get(key, 0) + views
        
        return hourly_views
```

### 4.3 최적 시간 분석기
```python
import numpy as np


class OptimalTimeAnalyzer:
    """최적 업로드 시간 분석"""
    
    def __init__(self, analytics_collector: YouTubeAnalyticsCollector):
        self.collector = analytics_collector
    
    async def analyze(
        self,
        channel_id: str,
        days: int = 90,
    ) -> TimeAnalysisResult:
        """채널 최적 업로드 시간 분석"""
        
        # 1. 영상 성과 데이터 수집
        performance_data = await self.collector.get_video_performance(channel_id, days)
        
        # 2. 시청자 활동 시간대 수집
        audience_activity = await self.collector.get_audience_retention(channel_id)
        
        # 3. 시간대별 집계
        time_slots = self._aggregate_by_time(performance_data)
        
        # 4. 시청자 활동 반영 (가중치)
        time_slots = self._apply_audience_weight(time_slots, audience_activity)
        
        # 5. 점수 계산 및 정규화
        time_slots = self._calculate_scores(time_slots)
        
        # 6. 결과 정리
        sorted_slots = sorted(time_slots, key=lambda x: x.score, reverse=True)
        
        return TimeAnalysisResult(
            channel_id=channel_id,
            analyzed_at=datetime.utcnow(),
            best_slots=sorted_slots[:10],
            worst_slots=sorted_slots[-5:],
            best_by_day=self._group_by_day(sorted_slots),
            data_from=datetime.utcnow() - timedelta(days=days),
            data_to=datetime.utcnow(),
            total_videos_analyzed=len(performance_data),
        )
    
    def _aggregate_by_time(self, data: list[dict]) -> list[TimeSlot]:
        """시간대별 집계"""
        slots = {}
        
        for item in data:
            key = (item["published_hour"], item["published_day"])
            
            if key not in slots:
                slots[key] = {
                    "hour": item["published_hour"],
                    "day_of_week": item["published_day"],
                    "views": [],
                    "engagements": [],
                }
            
            slots[key]["views"].append(item["views"])
            slots[key]["engagements"].append(item["engagement_rate"])
        
        return [
            TimeSlot(
                hour=v["hour"],
                day_of_week=v["day_of_week"],
                avg_views=np.mean(v["views"]) if v["views"] else 0,
                avg_engagement=np.mean(v["engagements"]) if v["engagements"] else 0,
                sample_count=len(v["views"]),
            )
            for v in slots.values()
        ]
    
    def _apply_audience_weight(
        self,
        slots: list[TimeSlot],
        audience_activity: dict,
    ) -> list[TimeSlot]:
        """시청자 활동 시간대 가중치 적용"""
        if not audience_activity:
            return slots
        
        max_activity = max(audience_activity.values()) if audience_activity else 1
        
        for slot in slots:
            key = (slot.day_of_week, slot.hour)
            activity = audience_activity.get(key, 0)
            
            # 시청자 활동이 많은 시간대에 가중치
            activity_weight = 1 + (activity / max_activity) * 0.5
            slot.avg_views *= activity_weight
        
        return slots
    
    def _calculate_scores(self, slots: list[TimeSlot]) -> list[TimeSlot]:
        """점수 계산 및 정규화"""
        if not slots:
            return slots
        
        # Min-Max 정규화
        max_views = max(s.avg_views for s in slots) or 1
        max_engagement = max(s.avg_engagement for s in slots) or 1
        
        for slot in slots:
            view_score = slot.avg_views / max_views
            engagement_score = slot.avg_engagement / max_engagement
            
            # 샘플 수에 따른 신뢰도 가중치
            confidence = min(slot.sample_count / 10, 1.0)
            
            # 종합 점수 (views 60%, engagement 40%)
            slot.score = (view_score * 0.6 + engagement_score * 0.4) * confidence
        
        return slots
    
    def _group_by_day(self, slots: list[TimeSlot]) -> dict[int, list[TimeSlot]]:
        """요일별 그룹화"""
        by_day = {}
        for slot in slots:
            day = slot.day_of_week
            if day not in by_day:
                by_day[day] = []
            by_day[day].append(slot)
        
        # 각 요일별로 점수순 정렬
        for day in by_day:
            by_day[day] = sorted(by_day[day], key=lambda x: x.score, reverse=True)[:3]
        
        return by_day
```

### 4.4 스케줄러
```python
from datetime import datetime, timedelta
import heapq


class UploadScheduler:
    """업로드 스케줄 관리"""
    
    def __init__(
        self,
        time_analyzer: OptimalTimeAnalyzer,
        preference: SchedulePreference | None = None,
    ):
        self.analyzer = time_analyzer
        self.preference = preference or SchedulePreference()
        
        # 채널별 분석 캐시
        self._analysis_cache: dict[str, TimeAnalysisResult] = {}
        
        # 스케줄 큐 (힙)
        self._schedule_queue: list[tuple[datetime, str, str]] = []  # (time, channel_id, video_id)
    
    async def get_next_optimal_time(
        self,
        channel_id: str,
        after: datetime | None = None,
    ) -> datetime:
        """다음 최적 업로드 시간 계산"""
        after = after or datetime.utcnow()
        
        # 분석 결과 캐시 또는 새로 분석
        if channel_id not in self._analysis_cache:
            self._analysis_cache[channel_id] = await self.analyzer.analyze(channel_id)
        
        analysis = self._analysis_cache[channel_id]
        
        # 최근 업로드 시간 확인 (최소 간격 체크)
        last_upload = await self._get_last_upload_time(channel_id)
        if last_upload:
            min_next = last_upload + timedelta(hours=self.preference.min_interval_hours)
            after = max(after, min_next)
        
        # 일일 업로드 제한 체크
        today_count = await self._get_today_upload_count(channel_id)
        if today_count >= self.preference.max_daily_uploads:
            # 내일로 넘기기
            after = datetime(after.year, after.month, after.day) + timedelta(days=1, hours=6)
        
        # 최적 시간 찾기
        best_time = self._find_next_best_time(analysis, after)
        
        return best_time
    
    def _find_next_best_time(
        self,
        analysis: TimeAnalysisResult,
        after: datetime,
    ) -> datetime:
        """after 이후 가장 좋은 시간 찾기"""
        candidates = []
        
        # 향후 7일 내 후보 시간 생성
        for days_ahead in range(7):
            target_date = after.date() + timedelta(days=days_ahead)
            target_day = target_date.weekday()
            
            # 선호 요일 체크
            if self.preference.preferred_days and target_day not in self.preference.preferred_days:
                continue
            
            # 해당 요일의 최적 시간대
            day_slots = analysis.best_by_day.get(target_day, analysis.best_slots[:3])
            
            for slot in day_slots:
                if slot.hour not in self.preference.allowed_hours:
                    continue
                
                candidate = datetime(
                    target_date.year,
                    target_date.month,
                    target_date.day,
                    slot.hour,
                    0,  # 정시
                )
                
                if candidate > after:
                    candidates.append((candidate, slot.score))
        
        if not candidates:
            # 폴백: 다음날 오전 9시
            return datetime(after.year, after.month, after.day, 9, 0) + timedelta(days=1)
        
        # 점수 높은 순 + 빠른 시간 순으로 정렬
        candidates.sort(key=lambda x: (-x[1], x[0]))
        
        return candidates[0][0]
    
    async def schedule_upload(
        self,
        channel_id: str,
        video_id: str,
        preferred_time: datetime | None = None,
    ) -> datetime:
        """업로드 스케줄 등록"""
        if preferred_time:
            scheduled_time = preferred_time
        else:
            scheduled_time = await self.get_next_optimal_time(channel_id)
        
        heapq.heappush(
            self._schedule_queue,
            (scheduled_time, channel_id, video_id)
        )
        
        return scheduled_time
    
    async def get_pending_uploads(self) -> list[tuple[datetime, str, str]]:
        """대기 중인 업로드 목록"""
        return sorted(self._schedule_queue)
    
    async def _get_last_upload_time(self, channel_id: str) -> datetime | None:
        """채널의 마지막 업로드 시간"""
        # TODO: DB에서 조회
        return None
    
    async def _get_today_upload_count(self, channel_id: str) -> int:
        """오늘 업로드 수"""
        # TODO: DB에서 조회
        return 0
```

---

## 5. 업로드 파이프라인 통합

```python
class UploadPipeline:
    """업로드 전체 파이프라인"""
    
    def __init__(
        self,
        uploader: YouTubeUploader,
        metadata_generator: MetadataGenerator,
        scheduler: UploadScheduler,
    ):
        self.uploader = uploader
        self.metadata_gen = metadata_generator
        self.scheduler = scheduler
    
    async def process_upload(
        self,
        video_result: "VideoGenerationResult",
        script: "GeneratedScript",
        channel: "Channel",
        immediate: bool = False,
    ) -> UploadResult:
        """영상 → 메타데이터 생성 → 스케줄링 → 업로드"""
        
        # 1. 메타데이터 생성
        metadata = await self.metadata_gen.generate(
            script=script.script,
            topic={
                "title": script.topic.title,
                "keywords": script.topic.keywords,
            },
            channel_info={
                "name": channel.name,
                "hashtags": channel.default_hashtags,
            },
        )
        
        # 2. 업로드 시간 결정
        if immediate:
            metadata.privacy_status = PrivacyStatus.PUBLIC
            metadata.scheduled_at = None
        else:
            scheduled_time = await self.scheduler.get_next_optimal_time(channel.id)
            metadata.scheduled_at = scheduled_time
            metadata.privacy_status = PrivacyStatus.PRIVATE
        
        # 3. 썸네일 설정
        metadata.thumbnail_path = video_result.thumbnail_path
        
        # 4. 업로드
        result = await self.uploader.upload(
            video_path=video_result.video_path,
            metadata=metadata,
        )
        
        # 5. 스케줄 등록 (추적용)
        await self.scheduler.schedule_upload(
            channel_id=channel.id,
            video_id=result.video_id,
            preferred_time=metadata.scheduled_at,
        )
        
        return result
```

---

## 6. 초기 설정 (분석 데이터 없을 때)

```python
class DefaultTimeSlots:
    """분석 데이터 없을 때 기본 시간대"""
    
    # 한국 시간 기준 일반적인 골든타임
    KOREAN_GOLDEN_HOURS = {
        # 평일
        0: [7, 12, 18, 21],   # 월
        1: [7, 12, 18, 21],   # 화
        2: [7, 12, 18, 21],   # 수
        3: [7, 12, 18, 21],   # 목
        4: [7, 12, 18, 22],   # 금
        # 주말
        5: [10, 14, 18, 21],  # 토
        6: [10, 14, 18, 21],  # 일
    }
    
    # 카테고리별 추천 시간
    CATEGORY_HOURS = {
        "tech": [9, 12, 18],           # 직장인 대상
        "entertainment": [12, 18, 21, 23],  # 저녁/밤
        "education": [7, 9, 19],       # 출퇴근 + 저녁
        "gaming": [15, 18, 21, 23],    # 오후/밤
        "lifestyle": [7, 10, 18],      # 아침/저녁
    }
    
    @classmethod
    def get_default_slots(
        cls, 
        category: str = "tech",
        timezone: str = "Asia/Seoul",
    ) -> list[TimeSlot]:
        """기본 추천 시간대"""
        hours = cls.CATEGORY_HOURS.get(category, cls.CATEGORY_HOURS["tech"])
        
        slots = []
        for day in range(7):
            for hour in hours:
                # 주말은 다른 시간대
                if day in [5, 6] and hour < 10:
                    continue
                    
                slots.append(TimeSlot(
                    hour=hour,
                    day_of_week=day,
                    score=0.8 if hour in cls.KOREAN_GOLDEN_HOURS.get(day, []) else 0.5,
                ))
        
        return sorted(slots, key=lambda x: x.score, reverse=True)
```

---

## 7. 기술 스택 정리

| 컴포넌트 | 라이브러리 | 비고 |
|----------|------------|------|
| **YouTube API** | google-api-python-client | 업로드, Analytics |
| **OAuth** | google-auth-oauthlib | 인증 |
| **HTTP** | httpx | 비동기 요청 |
| **스케줄링** | APScheduler | 예약 업로드 실행 |
| **분석** | numpy | 통계 계산 |
