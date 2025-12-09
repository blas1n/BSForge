# 🖥️ 검수 대시보드 시스템 설계

## 1. 개요

### 1.1 목표
- 주제/스크립트/영상/업로드 단계별 검수
- AI 분석 결과 + 원본 미리보기
- 빠른 액션 (승인/수정/거절)
- 텔레그램 알림 연동
- 모바일 대응

### 1.2 시스템 구성
```
FastAPI (Backend)
├── REST API
├── WebSocket (실시간 알림)
└── Telegram Bot

React (Frontend)
├── 검수 큐 대시보드
├── 상세 검수 화면
├── 통계/분석
└── 설정
```

---

## 2. FastAPI Backend

### 2.1 API 구조
```python
from fastapi import FastAPI, Depends, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="YouTube Automation Review API",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(channels_router, prefix="/api/channels", tags=["Channels"])
app.include_router(review_router, prefix="/api/review", tags=["Review"])
app.include_router(stats_router, prefix="/api/stats", tags=["Statistics"])
app.include_router(settings_router, prefix="/api/settings", tags=["Settings"])
```

### 2.2 인증
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from datetime import datetime, timedelta
from pydantic import BaseModel


# 설정
SECRET_KEY = "your-secret-key"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: str
    exp: datetime


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> TokenData:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return TokenData(user_id=user_id, exp=payload["exp"])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


# 라우터
from fastapi import APIRouter

auth_router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@auth_router.post("/login", response_model=Token)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    # 간단한 싱글 유저 인증 (또는 DB 조회)
    if request.username == "admin" and verify_password(request.password):
        token = create_access_token(request.username)
        return Token(access_token=token)
    raise HTTPException(status_code=401, detail="Invalid credentials")
```

### 2.3 검수 API
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from enum import Enum


review_router = APIRouter()


# === 스키마 ===

class ReviewType(str, Enum):
    TOPIC = "topic"
    SCRIPT = "script"
    VIDEO = "video"
    UPLOAD = "upload"


class ReviewStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    EDIT = "edit"
    SKIP = "skip"


class ReviewItemSummary(BaseModel):
    id: str
    type: ReviewType
    channel_id: str
    channel_name: str
    title: str
    preview: str  # 짧은 미리보기
    risk_score: float
    risk_reasons: list[str]
    status: ReviewStatus
    created_at: datetime
    expires_at: datetime | None
    
    class Config:
        from_attributes = True


class ReviewQueueResponse(BaseModel):
    items: list[ReviewItemSummary]
    total: int
    page: int
    page_size: int
    has_next: bool


class TopicDetail(BaseModel):
    id: str
    title_original: str
    title_normalized: str
    summary: str
    source_url: str
    source_name: str
    categories: list[str]
    keywords: list[str]
    scores: dict
    published_at: datetime | None


class ScriptDetail(BaseModel):
    id: str
    topic: TopicDetail
    script_text: str
    quality_scores: dict
    quality_issues: list[str]
    estimated_duration: float
    word_count: int
    generation_info: dict


class VideoDetail(BaseModel):
    id: str
    script: ScriptDetail
    video_url: str  # 미리보기 URL
    thumbnail_url: str
    duration_seconds: float
    tts_service: str
    visual_sources: list[str]


class UploadDetail(BaseModel):
    id: str
    video: VideoDetail
    title: str
    description: str
    tags: list[str]
    scheduled_at: datetime | None
    privacy_status: str


class ReviewDetailResponse(BaseModel):
    item: TopicDetail | ScriptDetail | VideoDetail | UploadDetail
    ai_analysis: dict
    similar_past_content: list[dict]  # 유사 과거 콘텐츠


class ReviewActionRequest(BaseModel):
    action: ReviewAction
    notes: str | None = None
    edited_content: dict | None = None  # 수정된 내용


class ReviewActionResponse(BaseModel):
    success: bool
    message: str
    next_item_id: str | None = None


# === 엔드포인트 ===

@review_router.get("/queue", response_model=ReviewQueueResponse)
async def get_review_queue(
    channel_id: str | None = None,
    type: ReviewType | None = None,
    status: ReviewStatus = ReviewStatus.PENDING,
    sort_by: str = "priority",  # priority, created_at, risk_score
    page: int = 1,
    page_size: int = 20,
    user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """검수 큐 조회"""
    query = db.query(ReviewQueue).filter(ReviewQueue.status == status)
    
    if channel_id:
        query = query.filter(ReviewQueue.channel_id == channel_id)
    if type:
        query = query.filter(ReviewQueue.review_type == type)
    
    # 정렬
    if sort_by == "priority":
        query = query.order_by(ReviewQueue.priority.desc(), ReviewQueue.created_at.asc())
    elif sort_by == "risk_score":
        query = query.order_by(ReviewQueue.risk_score.desc())
    else:
        query = query.order_by(ReviewQueue.created_at.asc())
    
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    
    return ReviewQueueResponse(
        items=[_to_summary(item, db) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


@review_router.get("/queue/{review_id}", response_model=ReviewDetailResponse)
async def get_review_detail(
    review_id: str,
    user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """검수 아이템 상세 조회"""
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review item not found")
    
    # 상태 업데이트 (진행 중으로)
    if review.status == ReviewStatus.PENDING:
        review.status = ReviewStatus.IN_PROGRESS
        db.commit()
    
    # 상세 정보 로드
    detail = await _load_detail(review, db)
    
    # AI 분석 결과
    ai_analysis = review.ai_analysis or {}
    
    # 유사 과거 콘텐츠
    similar = await _find_similar_content(review, db)
    
    return ReviewDetailResponse(
        item=detail,
        ai_analysis=ai_analysis,
        similar_past_content=similar,
    )


@review_router.post("/queue/{review_id}/action", response_model=ReviewActionResponse)
async def perform_review_action(
    review_id: str,
    request: ReviewActionRequest,
    user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """검수 액션 수행"""
    review = db.query(ReviewQueue).filter(ReviewQueue.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review item not found")
    
    # 액션 처리
    if request.action == ReviewAction.APPROVE:
        await _handle_approve(review, db)
        message = "승인되었습니다"
    elif request.action == ReviewAction.REJECT:
        await _handle_reject(review, request.notes, db)
        message = "거절되었습니다"
    elif request.action == ReviewAction.EDIT:
        await _handle_edit(review, request.edited_content, db)
        message = "수정되었습니다"
    else:
        message = "스킵되었습니다"
    
    # 검수 기록 업데이트
    review.reviewed_at = datetime.utcnow()
    review.reviewed_by = user.user_id
    review.review_action = request.action
    review.review_notes = request.notes
    review.status = (
        ReviewStatus.APPROVED if request.action == ReviewAction.APPROVE
        else ReviewStatus.REJECTED if request.action == ReviewAction.REJECT
        else review.status
    )
    db.commit()
    
    # 다음 아이템
    next_item = db.query(ReviewQueue).filter(
        ReviewQueue.status == ReviewStatus.PENDING,
        ReviewQueue.channel_id == review.channel_id,
    ).order_by(ReviewQueue.priority.desc()).first()
    
    return ReviewActionResponse(
        success=True,
        message=message,
        next_item_id=str(next_item.id) if next_item else None,
    )


@review_router.get("/stats")
async def get_review_stats(
    channel_id: str | None = None,
    days: int = 7,
    user: TokenData = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """검수 통계"""
    since = datetime.utcnow() - timedelta(days=days)
    
    query = db.query(ReviewQueue).filter(ReviewQueue.created_at >= since)
    if channel_id:
        query = query.filter(ReviewQueue.channel_id == channel_id)
    
    total = query.count()
    pending = query.filter(ReviewQueue.status == ReviewStatus.PENDING).count()
    approved = query.filter(ReviewQueue.status == ReviewStatus.APPROVED).count()
    rejected = query.filter(ReviewQueue.status == ReviewStatus.REJECTED).count()
    
    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "approval_rate": approved / max(approved + rejected, 1),
        "by_type": await _stats_by_type(query),
        "by_day": await _stats_by_day(query, days),
    }


# === 헬퍼 함수 ===

async def _handle_approve(review: ReviewQueue, db: Session):
    """승인 처리"""
    if review.review_type == ReviewType.TOPIC:
        topic = db.query(Topic).filter(Topic.id == review.target_id).first()
        topic.status = TopicStatus.APPROVED
    elif review.review_type == ReviewType.SCRIPT:
        script = db.query(Script).filter(Script.id == review.target_id).first()
        script.status = ScriptStatus.APPROVED
        # 영상 생성 작업 큐에 추가
        await enqueue_video_generation(script.id)
    elif review.review_type == ReviewType.VIDEO:
        video = db.query(Video).filter(Video.id == review.target_id).first()
        video.status = VideoStatus.APPROVED
        # 업로드 작업 큐에 추가
        await enqueue_upload(video.id)
    elif review.review_type == ReviewType.UPLOAD:
        upload = db.query(Upload).filter(Upload.id == review.target_id).first()
        upload.upload_status = "scheduled"
    
    db.commit()
```

### 2.4 WebSocket (실시간 알림)
```python
from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json


class ConnectionManager:
    """WebSocket 연결 관리"""
    
    def __init__(self):
        # channel_id -> set of websockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, channel_id: str):
        await websocket.accept()
        if channel_id not in self.active_connections:
            self.active_connections[channel_id] = set()
        self.active_connections[channel_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, channel_id: str):
        self.active_connections[channel_id].discard(websocket)
    
    async def broadcast(self, channel_id: str, message: dict):
        """채널에 메시지 브로드캐스트"""
        if channel_id in self.active_connections:
            for connection in self.active_connections[channel_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass
    
    async def broadcast_all(self, message: dict):
        """모든 연결에 브로드캐스트"""
        for connections in self.active_connections.values():
            for connection in connections:
                try:
                    await connection.send_json(message)
                except:
                    pass


manager = ConnectionManager()


@app.websocket("/ws/{channel_id}")
async def websocket_endpoint(websocket: WebSocket, channel_id: str):
    await manager.connect(websocket, channel_id)
    try:
        while True:
            # 클라이언트 메시지 대기 (ping/pong)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel_id)


# 새 검수 아이템 알림
async def notify_new_review(review: ReviewQueue):
    await manager.broadcast(str(review.channel_id), {
        "type": "new_review",
        "data": {
            "id": str(review.id),
            "review_type": review.review_type,
            "risk_score": review.risk_score,
        }
    })
```

### 2.5 텔레그램 봇
```python
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from pydantic import BaseModel


class TelegramNotifier:
    """텔레그램 알림 서비스"""
    
    def __init__(self, bot_token: str, chat_ids: list[str]):
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.app = Application.builder().token(bot_token).build()
        
        # 핸들러 등록
        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
    
    async def cmd_start(self, update: Update, context):
        await update.message.reply_text(
            "YouTube 자동화 검수 봇입니다.\n"
            "/status - 대기 중인 검수 확인"
        )
    
    async def cmd_status(self, update: Update, context):
        # DB에서 대기 중인 검수 수 조회
        pending_count = await get_pending_review_count()
        await update.message.reply_text(f"대기 중인 검수: {pending_count}건")
    
    async def handle_callback(self, update: Update, context):
        query = update.callback_query
        await query.answer()
        
        # callback_data 파싱: "approve:{review_id}" or "reject:{review_id}"
        action, review_id = query.data.split(":")
        
        if action == "approve":
            await perform_quick_approve(review_id)
            await query.edit_message_text(f"✅ 승인됨: {review_id[:8]}...")
        elif action == "reject":
            await query.edit_message_text(
                f"거절 사유를 입력해주세요.\n"
                f"또는 대시보드에서 처리: {DASHBOARD_URL}/review/{review_id}"
            )
    
    async def send_review_notification(
        self,
        review: ReviewQueue,
        detail: dict,
    ):
        """검수 알림 전송"""
        
        # 메시지 구성
        risk_emoji = "🔴" if review.risk_score > 70 else "🟡" if review.risk_score > 30 else "🟢"
        
        message = f"""
{risk_emoji} **새 검수 요청**

📌 유형: {review.review_type.value}
📺 채널: {detail.get('channel_name', 'Unknown')}
📝 제목: {detail.get('title', 'No title')[:50]}

⚠️ 리스크: {review.risk_score:.0f}/100
{chr(10).join(f"  • {r}" for r in review.risk_reasons[:3])}

🔗 [대시보드에서 보기]({DASHBOARD_URL}/review/{review.id})
"""
        
        # 빠른 액션 버튼 (리스크 낮을 때만)
        keyboard = None
        if review.risk_score < 30:
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ 승인", callback_data=f"approve:{review.id}"),
                    InlineKeyboardButton("❌ 거절", callback_data=f"reject:{review.id}"),
                ],
                [
                    InlineKeyboardButton("🔍 상세 보기", url=f"{DASHBOARD_URL}/review/{review.id}"),
                ],
            ])
        
        # 전송
        for chat_id in self.chat_ids:
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
    
    async def send_daily_summary(self):
        """일일 요약 전송"""
        stats = await get_daily_stats()
        
        message = f"""
📊 **일일 검수 요약**

✅ 승인: {stats['approved']}건
❌ 거절: {stats['rejected']}건
⏳ 대기: {stats['pending']}건

📈 승인율: {stats['approval_rate']:.1%}
⏱ 평균 처리 시간: {stats['avg_review_time']}분
"""
        
        for chat_id in self.chat_ids:
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode="Markdown",
            )
```

---

## 3. React Frontend

### 3.1 프로젝트 구조
```
src/
├── api/
│   ├── client.ts          # Axios 설정
│   ├── auth.ts            # 인증 API
│   └── review.ts          # 검수 API
├── components/
│   ├── common/
│   │   ├── Button.tsx
│   │   ├── Card.tsx
│   │   ├── Badge.tsx
│   │   └── Modal.tsx
│   ├── review/
│   │   ├── ReviewQueue.tsx
│   │   ├── ReviewCard.tsx
│   │   ├── ReviewDetail.tsx
│   │   ├── TopicReview.tsx
│   │   ├── ScriptReview.tsx
│   │   ├── VideoReview.tsx
│   │   └── ActionButtons.tsx
│   └── stats/
│       ├── StatsDashboard.tsx
│       └── Charts.tsx
├── hooks/
│   ├── useAuth.ts
│   ├── useReview.ts
│   └── useWebSocket.ts
├── pages/
│   ├── LoginPage.tsx
│   ├── DashboardPage.tsx
│   ├── ReviewPage.tsx
│   └── SettingsPage.tsx
├── store/
│   └── reviewStore.ts     # Zustand
├── types/
│   └── index.ts
└── App.tsx
```

### 3.2 타입 정의
```typescript
// src/types/index.ts

export type ReviewType = 'topic' | 'script' | 'video' | 'upload';
export type ReviewStatus = 'pending' | 'in_progress' | 'approved' | 'rejected';
export type ReviewAction = 'approve' | 'reject' | 'edit' | 'skip';

export interface ReviewItem {
  id: string;
  type: ReviewType;
  channelId: string;
  channelName: string;
  title: string;
  preview: string;
  riskScore: number;
  riskReasons: string[];
  status: ReviewStatus;
  createdAt: string;
  expiresAt: string | null;
}

export interface TopicDetail {
  id: string;
  titleOriginal: string;
  titleNormalized: string;
  summary: string;
  sourceUrl: string;
  sourceName: string;
  categories: string[];
  keywords: string[];
  scores: {
    source: number;
    freshness: number;
    trend: number;
    relevance: number;
    total: number;
  };
  publishedAt: string | null;
}

export interface ScriptDetail {
  id: string;
  topic: TopicDetail;
  scriptText: string;
  qualityScores: {
    style: number;
    hook: number;
  };
  qualityIssues: string[];
  estimatedDuration: number;
  wordCount: number;
}

export interface VideoDetail {
  id: string;
  script: ScriptDetail;
  videoUrl: string;
  thumbnailUrl: string;
  durationSeconds: number;
  ttsService: string;
  visualSources: string[];
}

export interface ReviewDetail {
  item: TopicDetail | ScriptDetail | VideoDetail;
  aiAnalysis: {
    riskScore: number;
    riskReasons: string[];
    suggestions: string[];
  };
  similarPastContent: Array<{
    title: string;
    similarity: number;
    performance: {
      views: number;
      engagement: number;
    };
  }>;
}
```

### 3.3 검수 큐 컴포넌트
```tsx
// src/components/review/ReviewQueue.tsx

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { reviewApi } from '../../api/review';
import { ReviewCard } from './ReviewCard';
import { ReviewType, ReviewStatus, ReviewItem } from '../../types';

interface FilterState {
  channelId: string | null;
  type: ReviewType | null;
  status: ReviewStatus;
  sortBy: 'priority' | 'created_at' | 'risk_score';
}

export const ReviewQueue: React.FC = () => {
  const [filters, setFilters] = useState<FilterState>({
    channelId: null,
    type: null,
    status: 'pending',
    sortBy: 'priority',
  });
  const [page, setPage] = useState(1);

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['reviewQueue', filters, page],
    queryFn: () => reviewApi.getQueue({ ...filters, page }),
    refetchInterval: 30000, // 30초마다 갱신
  });

  // 타입별 카운트
  const typeCounts = useTypeCounts(filters.channelId);

  return (
    <div className="review-queue">
      {/* 필터 바 */}
      <div className="filter-bar">
        <ChannelSelect
          value={filters.channelId}
          onChange={(v) => setFilters({ ...filters, channelId: v })}
        />
        
        <TypeTabs
          value={filters.type}
          counts={typeCounts}
          onChange={(v) => setFilters({ ...filters, type: v })}
        />
        
        <SortSelect
          value={filters.sortBy}
          onChange={(v) => setFilters({ ...filters, sortBy: v })}
        />
      </div>

      {/* 통계 요약 */}
      <div className="queue-stats">
        <StatBadge label="대기" value={data?.total || 0} color="yellow" />
        <StatBadge label="오늘 승인" value={typeCounts.todayApproved} color="green" />
        <StatBadge label="오늘 거절" value={typeCounts.todayRejected} color="red" />
      </div>

      {/* 큐 목록 */}
      <div className="queue-list">
        {isLoading ? (
          <LoadingSkeleton count={5} />
        ) : data?.items.length === 0 ? (
          <EmptyState message="대기 중인 검수가 없습니다" />
        ) : (
          data?.items.map((item: ReviewItem) => (
            <ReviewCard
              key={item.id}
              item={item}
              onAction={() => refetch()}
            />
          ))
        )}
      </div>

      {/* 페이지네이션 */}
      {data?.hasNext && (
        <Pagination
          page={page}
          hasNext={data.hasNext}
          onPageChange={setPage}
        />
      )}
    </div>
  );
};
```

### 3.4 검수 카드 컴포넌트
```tsx
// src/components/review/ReviewCard.tsx

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ReviewItem, ReviewType } from '../../types';
import { Badge, Card, Button } from '../common';
import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';

interface Props {
  item: ReviewItem;
  onAction: () => void;
}

const TYPE_LABELS: Record<ReviewType, string> = {
  topic: '주제',
  script: '스크립트',
  video: '영상',
  upload: '업로드',
};

const TYPE_COLORS: Record<ReviewType, string> = {
  topic: 'blue',
  script: 'purple',
  video: 'pink',
  upload: 'green',
};

export const ReviewCard: React.FC<Props> = ({ item, onAction }) => {
  const navigate = useNavigate();

  const riskLevel = 
    item.riskScore > 70 ? 'high' :
    item.riskScore > 30 ? 'medium' : 'low';

  return (
    <Card 
      className={`review-card risk-${riskLevel}`}
      onClick={() => navigate(`/review/${item.id}`)}
    >
      <div className="card-header">
        <Badge color={TYPE_COLORS[item.type]}>
          {TYPE_LABELS[item.type]}
        </Badge>
        <span className="channel-name">{item.channelName}</span>
        <span className="time">
          {formatDistanceToNow(new Date(item.createdAt), { 
            addSuffix: true, 
            locale: ko 
          })}
        </span>
      </div>

      <div className="card-body">
        <h3 className="title">{item.title}</h3>
        <p className="preview">{item.preview}</p>
      </div>

      <div className="card-footer">
        <div className="risk-indicator">
          <RiskMeter value={item.riskScore} />
          <span className="risk-label">
            리스크: {item.riskScore}
          </span>
        </div>

        {item.riskReasons.length > 0 && (
          <div className="risk-reasons">
            {item.riskReasons.slice(0, 2).map((reason, i) => (
              <span key={i} className="reason-tag">{reason}</span>
            ))}
          </div>
        )}

        {/* 빠른 액션 (리스크 낮을 때) */}
        {riskLevel === 'low' && (
          <div className="quick-actions" onClick={(e) => e.stopPropagation()}>
            <Button 
              size="sm" 
              variant="success"
              onClick={() => handleQuickApprove(item.id, onAction)}
            >
              빠른 승인
            </Button>
          </div>
        )}
      </div>
    </Card>
  );
};

// 리스크 미터 컴포넌트
const RiskMeter: React.FC<{ value: number }> = ({ value }) => {
  const color = 
    value > 70 ? '#ef4444' :
    value > 30 ? '#f59e0b' : '#22c55e';

  return (
    <div className="risk-meter">
      <div 
        className="risk-fill" 
        style={{ width: `${value}%`, backgroundColor: color }}
      />
    </div>
  );
};
```

### 3.5 상세 검수 페이지
```tsx
// src/pages/ReviewPage.tsx

import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { reviewApi } from '../api/review';
import { 
  TopicReview, 
  ScriptReview, 
  VideoReview, 
  ActionButtons 
} from '../components/review';
import { ReviewAction } from '../types';

export const ReviewPage: React.FC = () => {
  const { reviewId } = useParams<{ reviewId: string }>();
  const navigate = useNavigate();
  const [editMode, setEditMode] = useState(false);
  const [editedContent, setEditedContent] = useState<any>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['reviewDetail', reviewId],
    queryFn: () => reviewApi.getDetail(reviewId!),
    enabled: !!reviewId,
  });

  const actionMutation = useMutation({
    mutationFn: (params: { action: ReviewAction; notes?: string }) =>
      reviewApi.performAction(reviewId!, params),
    onSuccess: (result) => {
      if (result.nextItemId) {
        navigate(`/review/${result.nextItemId}`);
      } else {
        navigate('/dashboard');
      }
    },
  });

  if (isLoading) return <LoadingSpinner />;
  if (!data) return <NotFound />;

  const { item, aiAnalysis, similarPastContent } = data;

  // 타입에 따른 상세 컴포넌트
  const DetailComponent = {
    topic: TopicReview,
    script: ScriptReview,
    video: VideoReview,
    upload: UploadReview,
  }[data.item.type];

  return (
    <div className="review-page">
      {/* 헤더 */}
      <header className="review-header">
        <Button variant="ghost" onClick={() => navigate(-1)}>
          ← 뒤로
        </Button>
        <h1>검수: {item.title || item.titleNormalized}</h1>
        <div className="header-actions">
          <KeyboardShortcuts />
        </div>
      </header>

      <div className="review-content">
        {/* 메인 콘텐츠 */}
        <main className="review-main">
          <DetailComponent
            item={item}
            editMode={editMode}
            onEdit={setEditedContent}
          />
        </main>

        {/* 사이드바 */}
        <aside className="review-sidebar">
          {/* AI 분석 */}
          <Card title="AI 분석">
            <RiskSummary 
              score={aiAnalysis.riskScore}
              reasons={aiAnalysis.riskReasons}
            />
            {aiAnalysis.suggestions?.length > 0 && (
              <div className="suggestions">
                <h4>개선 제안</h4>
                <ul>
                  {aiAnalysis.suggestions.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>

          {/* 유사 콘텐츠 */}
          {similarPastContent.length > 0 && (
            <Card title="유사 과거 콘텐츠">
              {similarPastContent.map((content, i) => (
                <SimilarContentItem key={i} {...content} />
              ))}
            </Card>
          )}
        </aside>
      </div>

      {/* 하단 액션 바 */}
      <ActionButtons
        onApprove={() => actionMutation.mutate({ action: 'approve' })}
        onReject={(notes) => actionMutation.mutate({ action: 'reject', notes })}
        onEdit={() => setEditMode(!editMode)}
        onSaveEdit={() => {
          actionMutation.mutate({ 
            action: 'edit', 
            editedContent 
          });
        }}
        editMode={editMode}
        isLoading={actionMutation.isPending}
      />
    </div>
  );
};
```

### 3.6 스크립트 검수 컴포넌트
```tsx
// src/components/review/ScriptReview.tsx

import React from 'react';
import { ScriptDetail } from '../../types';
import { Badge, Card, Tabs } from '../common';

interface Props {
  item: ScriptDetail;
  editMode: boolean;
  onEdit: (content: any) => void;
}

export const ScriptReview: React.FC<Props> = ({ item, editMode, onEdit }) => {
  const [activeTab, setActiveTab] = useState('script');

  return (
    <div className="script-review">
      <Tabs
        value={activeTab}
        onChange={setActiveTab}
        tabs={[
          { value: 'script', label: '스크립트' },
          { value: 'topic', label: '원본 주제' },
          { value: 'quality', label: '품질 분석' },
        ]}
      />

      {activeTab === 'script' && (
        <Card>
          <div className="script-meta">
            <Badge>예상 {item.estimatedDuration}초</Badge>
            <Badge>{item.wordCount}자</Badge>
          </div>

          {editMode ? (
            <textarea
              className="script-editor"
              defaultValue={item.scriptText}
              onChange={(e) => onEdit({ scriptText: e.target.value })}
              rows={20}
            />
          ) : (
            <div className="script-text">
              <ScriptHighlighter text={item.scriptText} />
            </div>
          )}

          {/* 품질 이슈 */}
          {item.qualityIssues.length > 0 && (
            <div className="quality-issues">
              <h4>⚠️ 품질 이슈</h4>
              {item.qualityIssues.map((issue, i) => (
                <div key={i} className="issue-item">
                  {issue}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {activeTab === 'topic' && (
        <Card>
          <h3>{item.topic.titleNormalized}</h3>
          <p className="summary">{item.topic.summary}</p>
          
          <div className="topic-meta">
            <a href={item.topic.sourceUrl} target="_blank" rel="noopener">
              출처: {item.topic.sourceName}
            </a>
          </div>

          <div className="keywords">
            {item.topic.keywords.map((kw, i) => (
              <Badge key={i} variant="outline">{kw}</Badge>
            ))}
          </div>
        </Card>
      )}

      {activeTab === 'quality' && (
        <Card>
          <div className="quality-scores">
            <ScoreItem 
              label="스타일 일관성" 
              value={item.qualityScores.style} 
            />
            <ScoreItem 
              label="훅 품질" 
              value={item.qualityScores.hook} 
            />
          </div>
        </Card>
      )}
    </div>
  );
};

// 스크립트 하이라이터 (훅 강조 등)
const ScriptHighlighter: React.FC<{ text: string }> = ({ text }) => {
  const paragraphs = text.split('\n\n');
  
  return (
    <div className="highlighted-script">
      {paragraphs.map((para, i) => (
        <p 
          key={i} 
          className={i === 0 ? 'hook' : i === paragraphs.length - 1 ? 'conclusion' : ''}
        >
          {para}
        </p>
      ))}
    </div>
  );
};
```

### 3.7 WebSocket 훅
```tsx
// src/hooks/useWebSocket.ts

import { useEffect, useRef, useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export const useReviewWebSocket = (channelId: string | null) => {
  const ws = useRef<WebSocket | null>(null);
  const queryClient = useQueryClient();

  useEffect(() => {
    if (!channelId) return;

    const wsUrl = `${WS_BASE_URL}/ws/${channelId}`;
    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      console.log('WebSocket connected');
    };

    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      
      if (message.type === 'new_review') {
        // 검수 큐 갱신
        queryClient.invalidateQueries({ queryKey: ['reviewQueue'] });
        
        // 알림 표시
        showNotification('새 검수 요청', message.data.title);
      }
    };

    ws.current.onclose = () => {
      console.log('WebSocket disconnected');
      // 재연결 로직
      setTimeout(() => {
        // reconnect
      }, 3000);
    };

    // Ping/Pong
    const pingInterval = setInterval(() => {
      if (ws.current?.readyState === WebSocket.OPEN) {
        ws.current.send('ping');
      }
    }, 30000);

    return () => {
      clearInterval(pingInterval);
      ws.current?.close();
    };
  }, [channelId, queryClient]);

  return ws.current;
};
```

---

## 4. 키보드 단축키

```tsx
// src/hooks/useKeyboardShortcuts.ts

import { useEffect } from 'react';

export const useReviewShortcuts = (actions: {
  onApprove: () => void;
  onReject: () => void;
  onSkip: () => void;
  onEdit: () => void;
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 입력 중이면 무시
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) {
        return;
      }

      switch (e.key) {
        case 'a':
        case 'A':
          e.preventDefault();
          actions.onApprove();
          break;
        case 'r':
        case 'R':
          e.preventDefault();
          actions.onReject();
          break;
        case 's':
        case 'S':
          e.preventDefault();
          actions.onSkip();
          break;
        case 'e':
        case 'E':
          e.preventDefault();
          actions.onEdit();
          break;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [actions]);
};

// 단축키 가이드 컴포넌트
export const KeyboardShortcuts: React.FC = () => (
  <div className="keyboard-shortcuts">
    <span><kbd>A</kbd> 승인</span>
    <span><kbd>R</kbd> 거절</span>
    <span><kbd>S</kbd> 스킵</span>
    <span><kbd>E</kbd> 수정</span>
  </div>
);
```

---

## 5. 모바일 대응

```css
/* 반응형 스타일 */
@media (max-width: 768px) {
  .review-page {
    flex-direction: column;
  }
  
  .review-sidebar {
    order: -1;  /* 사이드바를 위로 */
    width: 100%;
  }
  
  .review-main {
    width: 100%;
  }
  
  .action-buttons {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 1rem;
    background: white;
    box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
  }
  
  .quick-actions {
    display: flex;
    gap: 0.5rem;
  }
  
  .quick-actions button {
    flex: 1;
    padding: 1rem;
  }
}
```

---

## 6. 기술 스택 정리

| 컴포넌트 | 기술 | 비고 |
|----------|------|------|
| **Backend** | FastAPI | 비동기, 타입 힌트 |
| **인증** | JWT (python-jose) | 간단한 토큰 인증 |
| **실시간** | WebSocket | 새 검수 알림 |
| **알림** | python-telegram-bot | 텔레그램 연동 |
| **Frontend** | React + TypeScript | SPA |
| **상태관리** | TanStack Query + Zustand | 서버/클라이언트 분리 |
| **스타일** | Tailwind CSS | 유틸리티 |
| **빌드** | Vite | 빠른 개발 |
