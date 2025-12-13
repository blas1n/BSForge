# 📡 주제 수집 시스템 상세 설계

## 1. 개요

### 1.1 목표
- 채널 Config 기반으로 관련 주제를 자동 수집
- 국내/해외 소스 비중을 주제에 따라 동적 조정
- 중복 제거, 스코어링으로 품질 높은 주제만 선별
- 성과 피드백 기반 시리즈 자동 감지

### 1.2 데이터 플로우
```
[소스] → [수집] → [정규화] → [중복제거] → [필터링] → [스코어링] → [큐]
                                                              ↑
                                                    [성과 피드백]
```

---

## 2. 소스 정의

### 2.1 소스 타입
```typescript
type SourceType =
  | 'rss'           // RSS 피드 구독
  | 'api'           // 공식 API (Twitter, Reddit 등)
  | 'scraper'       // 웹 스크래핑
  | 'trend';        // 트렌드 API

type SourceRegion = 'domestic' | 'foreign' | 'global';

type SourceCategory =
  | 'community'     // 커뮤니티
  | 'news'          // 뉴스
  | 'blog'          // 블로그/미디어
  | 'social'        // SNS
  | 'trend'         // 트렌드
  | 'video';        // 영상 플랫폼
```

### 2.2 소스 스키마
```typescript
interface Source {
  id: string;
  name: string;
  type: SourceType;
  region: SourceRegion;
  category: SourceCategory;

  // 연결 정보
  connection: {
    url: string;
    method: 'GET' | 'POST';
    headers?: Record<string, string>;
    auth?: {
      type: 'apiKey' | 'oauth' | 'none';
      credentials?: string;  // 암호화된 자격증명 참조
    };
  };

  // 파싱 설정
  parser: {
    type: 'json' | 'html' | 'xml' | 'rss';
    selectors?: {  // HTML/스크래핑용
      list: string;
      title: string;
      link: string;
      content?: string;
      date?: string;
      score?: string;
      comments?: string;
    };
    mappings?: {  // JSON/API용
      title: string;
      link: string;
      content?: string;
      date?: string;
      score?: string;
    };
  };

  // 필터링
  filters: {
    minScore?: number;        // 최소 추천수/점수
    minComments?: number;     // 최소 댓글수
    maxAgeHours?: number;     // 최대 경과 시간
    keywords?: string[];      // 포함해야 할 키워드
    excludeKeywords?: string[]; // 제외 키워드
  };

  // 스케줄
  schedule: {
    cron: string;             // cron 표현식
    rateLimit: number;        // 분당 최대 요청
    enabled: boolean;
  };

  // 메타
  credibility: number;        // 신뢰도 (1-10)
  categories: string[];       // 이 소스가 커버하는 주제 카테고리
  language: 'ko' | 'en' | 'mixed';
}
```

### 2.3 소스 목록

#### 국내 커뮤니티
```typescript
const domesticCommunities: Source[] = [
  // 메이저
  {
    id: 'clien',
    name: '클리앙',
    type: 'scraper',
    region: 'domestic',
    category: 'community',
    connection: { url: 'https://www.clien.net/service/board/{board}', method: 'GET' },
    parser: {
      type: 'html',
      selectors: {
        list: '.list_item',
        title: '.list_subject',
        link: 'a.list_subject',
        score: '.view_count',
      }
    },
    filters: { minScore: 500, maxAgeHours: 48 },
    schedule: { cron: '0 */2 * * *', rateLimit: 10, enabled: true },
    credibility: 7,
    categories: ['tech', 'lifestyle', 'politics', 'humor'],
    language: 'ko',
  },
  {
    id: 'ruliweb',
    name: '루리웹',
    type: 'scraper',
    region: 'domestic',
    category: 'community',
    // ... 설정
    categories: ['gaming', 'anime', 'entertainment'],
  },
  {
    id: 'fmkorea',
    name: '에펨코리아',
    type: 'scraper',
    region: 'domestic',
    category: 'community',
    // ... 설정
    categories: ['sports', 'entertainment', 'humor', 'politics'],
  },
  {
    id: 'inven',
    name: '인벤',
    type: 'scraper',
    region: 'domestic',
    category: 'community',
    categories: ['gaming'],
  },
  {
    id: 'blind',
    name: '블라인드',
    type: 'api',  // 비공식 API 또는 스크래핑
    region: 'domestic',
    category: 'community',
    categories: ['career', 'company', 'salary'],
  },
  {
    id: 'bobae',
    name: '보배드림',
    type: 'scraper',
    region: 'domestic',
    category: 'community',
    categories: ['auto', 'lifestyle'],
  },

  // 마이너/특화
  {
    id: 'dcinside',
    name: '디시인사이드',
    type: 'scraper',
    region: 'domestic',
    category: 'community',
    connection: {
      url: 'https://gall.dcinside.com/board/lists/?id={gallery}',
      method: 'GET'
    },
    // 갤러리별로 다른 설정 필요
    categories: ['all'],  // 갤러리에 따라 동적
    // 특수: 갤러리 ID를 Config에서 지정
  },
  {
    id: 'todayhumor',
    name: '오늘의유머',
    type: 'scraper',
    region: 'domestic',
    category: 'community',
    categories: ['humor', 'politics', 'social'],
  },
  {
    id: 'ppomppu',
    name: '뽐뿌',
    type: 'scraper',
    region: 'domestic',
    category: 'community',
    categories: ['deals', 'tech', 'lifestyle'],
  },
];

const domesticNews: Source[] = [
  {
    id: 'yozm',
    name: '요즘IT',
    type: 'rss',
    region: 'domestic',
    category: 'blog',
    connection: { url: 'https://yozm.wishket.com/magazine/feed/', method: 'GET' },
    categories: ['tech', 'career', 'startup'],
    credibility: 8,
  },
  {
    id: '44bits',
    name: '44bits',
    type: 'rss',
    region: 'domestic',
    category: 'blog',
    categories: ['tech', 'devops', 'cloud'],
    credibility: 9,
  },
  // 네이버 뉴스, 다음 뉴스 등
];
```

#### 해외 소스
```typescript
const foreignSources: Source[] = [
  // 커뮤니티
  {
    id: 'reddit',
    name: 'Reddit',
    type: 'api',
    region: 'foreign',
    category: 'community',
    connection: {
      url: 'https://www.reddit.com/r/{subreddit}/hot.json',
      method: 'GET',
    },
    parser: {
      type: 'json',
      mappings: {
        title: 'data.children[].data.title',
        link: 'data.children[].data.permalink',
        score: 'data.children[].data.score',
      }
    },
    filters: { minScore: 100 },
    // 서브레딧은 Config에서 지정
    categories: ['all'],
    credibility: 7,
    language: 'en',
  },
  {
    id: 'hackernews',
    name: 'Hacker News',
    type: 'api',
    region: 'foreign',
    category: 'community',
    connection: { url: 'https://hacker-news.firebaseio.com/v0/topstories.json', method: 'GET' },
    categories: ['tech', 'startup', 'programming'],
    credibility: 9,
    language: 'en',
  },
  {
    id: 'twitter',
    name: 'Twitter/X',
    type: 'api',
    region: 'global',
    category: 'social',
    categories: ['all'],  // 검색어/계정 기반
    language: 'mixed',
  },

  // 뉴스/블로그
  {
    id: 'techcrunch',
    name: 'TechCrunch',
    type: 'rss',
    region: 'foreign',
    category: 'news',
    connection: { url: 'https://techcrunch.com/feed/', method: 'GET' },
    categories: ['tech', 'startup', 'funding'],
    credibility: 9,
    language: 'en',
  },
  {
    id: 'theverge',
    name: 'The Verge',
    type: 'rss',
    region: 'foreign',
    category: 'news',
    categories: ['tech', 'gadget', 'entertainment'],
    credibility: 8,
    language: 'en',
  },
  {
    id: 'arstechnica',
    name: 'Ars Technica',
    type: 'rss',
    region: 'foreign',
    category: 'news',
    categories: ['tech', 'science', 'gaming'],
    credibility: 9,
    language: 'en',
  },
  {
    id: 'medium',
    name: 'Medium',
    type: 'rss',
    region: 'foreign',
    category: 'blog',
    // 태그별 피드
    categories: ['tech', 'programming', 'startup', 'productivity'],
    credibility: 6,  // 개인 블로그라 편차 있음
    language: 'en',
  },
  {
    id: 'devto',
    name: 'dev.to',
    type: 'rss',
    region: 'foreign',
    category: 'blog',
    categories: ['programming', 'webdev', 'devops'],
    credibility: 7,
    language: 'en',
  },
];

const trendSources: Source[] = [
  {
    id: 'google-trends',
    name: 'Google Trends',
    type: 'trend',
    region: 'global',
    category: 'trend',
    // pytrends 또는 SerpAPI 사용
    categories: ['all'],
    language: 'mixed',
  },
  {
    id: 'youtube-trending',
    name: 'YouTube Trending',
    type: 'api',
    region: 'global',
    category: 'video',
    // YouTube Data API v3
    categories: ['all'],
    language: 'mixed',
  },
  {
    id: 'naver-realtime',
    name: '네이버 실시간검색',
    type: 'scraper',  // 비공식
    region: 'domestic',
    category: 'trend',
    categories: ['all'],
    language: 'ko',
  },
];
```

---

## 3. 채널별 소스 선택

### 3.1 소스 선택 Config
```typescript
// 채널 Config 내 소스 설정
interface ChannelSourceConfig {
  // 지역 비중 (합계 1.0)
  regionWeights: {
    domestic: number;   // 0.0 - 1.0
    foreign: number;    // 0.0 - 1.0
  };

  // 활성화할 소스 ID 목록
  enabledSources: string[];

  // 소스별 상세 설정
  sourceOverrides: {
    [sourceId: string]: {
      enabled?: boolean;
      weight?: number;          // 이 소스의 가중치
      customFilters?: {
        minScore?: number;
        keywords?: string[];
        excludeKeywords?: string[];
      };
      // 동적 파라미터 (갤러리 ID, 서브레딧 등)
      params?: Record<string, string | string[]>;
    };
  };

  // 트렌드 설정
  trendConfig: {
    enabled: boolean;
    sources: string[];          // 사용할 트렌드 소스
    regions: string[];          // ['KR', 'US', 'global']
    minMomentum: number;        // 최소 상승률
  };
}
```

### 3.2 채널별 소스 설정 예시
```typescript
// 테크 채널 - 해외 비중 높음
const techChannelSources: ChannelSourceConfig = {
  regionWeights: {
    domestic: 0.3,
    foreign: 0.7,
  },
  enabledSources: [
    // 해외
    'reddit', 'hackernews', 'techcrunch', 'theverge', 'devto',
    // 국내
    'clien', 'yozm', '44bits',
    // 트렌드
    'google-trends',
  ],
  sourceOverrides: {
    'reddit': {
      weight: 1.2,
      params: {
        subreddits: ['programming', 'technology', 'MachineLearning', 'artificial'],
      },
    },
    'clien': {
      weight: 0.8,
      params: {
        boards: ['cm_ittalk', 'cm_tech'],  // IT수다, 테크
      },
    },
    'dcinside': {
      enabled: true,
      weight: 0.6,
      params: {
        galleries: ['programming', 'ai'],
      },
      customFilters: {
        minScore: 100,  // 디시는 기준 낮게
      },
    },
  },
  trendConfig: {
    enabled: true,
    sources: ['google-trends', 'youtube-trending'],
    regions: ['KR', 'US'],
    minMomentum: 0.3,
  },
};

// 엔터테인먼트 채널 - 국내 비중 높음
const entertainmentChannelSources: ChannelSourceConfig = {
  regionWeights: {
    domestic: 0.8,
    foreign: 0.2,
  },
  enabledSources: [
    // 국내
    'fmkorea', 'ruliweb', 'dcinside', 'todayhumor',
    // 해외
    'reddit', 'twitter',
    // 트렌드
    'youtube-trending', 'naver-realtime',
  ],
  sourceOverrides: {
    'dcinside': {
      weight: 1.5,  // 디시 밈/이슈가 많음
      params: {
        galleries: ['entertainment', 'drama', 'movie', 'hit'],
      },
    },
    'reddit': {
      params: {
        subreddits: ['kpop', 'kdrama', 'koreanvariety'],
      },
    },
  },
  trendConfig: {
    enabled: true,
    sources: ['youtube-trending', 'naver-realtime', 'twitter'],
    regions: ['KR'],
    minMomentum: 0.5,  // 트렌드 민감하게
  },
};
```

---

## 4. 주제 정규화

### 4.1 Raw Topic → Normalized Topic
```typescript
interface RawTopic {
  sourceId: string;
  sourceUrl: string;
  title: string;
  content?: string;
  summary?: string;
  publishedAt?: Date;
  metrics?: {
    score?: number;
    comments?: number;
    views?: number;
  };
  metadata?: Record<string, any>;
}

interface NormalizedTopic {
  id: string;
  hash: string;                  // 중복 체크용

  // 기본 정보
  title: {
    original: string;
    translated?: string;         // 번역 (해외 소스)
    normalized: string;          // 정제된 제목
  };

  summary: string;               // 200자 이내 요약

  // 소스
  source: {
    id: string;
    name: string;
    url: string;
    region: SourceRegion;
    credibility: number;
  };

  // 분류
  classification: {
    categories: string[];        // 자동 분류된 카테고리
    keywords: string[];          // 추출된 키워드
    entities: Entity[];          // 인물/기업/제품 등
    language: 'ko' | 'en';
    sentiment: 'positive' | 'neutral' | 'negative';
  };

  // 점수
  scores: {
    source: number;              // 원본 점수 (정규화)
    freshness: number;           // 신선도 (0-1)
    trend: number;               // 트렌드 점수 (0-1)
    relevance: number;           // 채널 관련성 (0-1)
    total: number;               // 종합 (0-100)
  };

  // 시간
  timestamps: {
    published: Date;
    collected: Date;
    expires: Date;
  };

  // 상태
  status: 'pending' | 'approved' | 'rejected' | 'used' | 'expired';

  // 시리즈 연결 (있는 경우)
  series?: {
    id: string;
    name: string;
    episode?: number;
  };
}

interface Entity {
  name: string;
  type: 'person' | 'company' | 'product' | 'technology' | 'event' | 'place';
  aliases?: string[];
  sentiment?: 'positive' | 'neutral' | 'negative';
}
```

### 4.2 정규화 파이프라인
```typescript
class TopicNormalizer {
  constructor(
    private translator: TranslationService,
    private summarizer: SummarizationService,
    private classifier: ClassificationService,
    private entityExtractor: EntityExtractionService,
  ) {}

  async normalize(raw: RawTopic, source: Source): Promise<NormalizedTopic> {
    // 1. 언어 감지 및 번역
    const language = this.detectLanguage(raw.title);
    const translatedTitle = language === 'en'
      ? await this.translator.translate(raw.title, 'ko')
      : undefined;

    // 2. 제목 정제 (특수문자, 광고성 문구 제거)
    const normalizedTitle = this.cleanTitle(raw.title);

    // 3. 요약 생성
    const summary = await this.summarizer.summarize(
      raw.content || raw.summary || raw.title,
      { maxLength: 200 }
    );

    // 4. 분류 (카테고리, 키워드)
    const classification = await this.classifier.classify(
      normalizedTitle,
      raw.content || summary
    );

    // 5. 엔티티 추출
    const entities = await this.entityExtractor.extract(
      raw.title,
      raw.content
    );

    // 6. 해시 생성 (중복 체크용)
    const hash = this.generateHash(normalizedTitle, classification.keywords);

    // 7. 만료 시간 계산 (카테고리에 따라)
    const expiresAt = this.calculateExpiry(classification.categories);

    return {
      id: generateUUID(),
      hash,
      title: {
        original: raw.title,
        translated: translatedTitle,
        normalized: normalizedTitle,
      },
      summary,
      source: {
        id: source.id,
        name: source.name,
        url: raw.sourceUrl,
        region: source.region,
        credibility: source.credibility,
      },
      classification: {
        ...classification,
        entities,
        language,
      },
      scores: {
        source: this.normalizeSourceScore(raw.metrics?.score, source),
        freshness: 0,  // 스코어러에서 계산
        trend: 0,
        relevance: 0,
        total: 0,
      },
      timestamps: {
        published: raw.publishedAt || new Date(),
        collected: new Date(),
        expires: expiresAt,
      },
      status: 'pending',
    };
  }

  private calculateExpiry(categories: string[]): Date {
    // 카테고리별 만료 시간
    const expiryHours: Record<string, number> = {
      'breaking': 6,      // 속보
      'news': 24,         // 뉴스
      'trend': 48,        // 트렌드
      'tech': 168,        // 테크 (1주)
      'educational': 720, // 교육 (1달)
      'evergreen': 2160,  // 에버그린 (3달)
    };

    const minExpiry = Math.min(
      ...categories.map(c => expiryHours[c] || 72)
    );

    return new Date(Date.now() + minExpiry * 60 * 60 * 1000);
  }
}
```

---

## 5. 중복 제거

### 5.1 설계 결정

**Hash-Only 중복 제거 채택**

원래 3-level (해시, 시맨틱, 이벤트)로 설계했으나, 다음 이유로 **Hash-Only**로 단순화:

#### 왜 Semantic Similarity를 제거했나?

1. **같은 제목이라도 소스마다 콘텐츠가 다름**
   - Reddit의 "Tesla 주가 급등" → 커뮤니티 반응, 밈
   - TechCrunch의 "Tesla 주가 급등" → 분석 기사, 전문가 의견
   - HN의 "Tesla 주가 급등" → 기술적 논의

2. **페르소나가 여러 소스를 통합해야 함**
   - 각 채널의 페르소나는 같은 이벤트에 대한 다양한 관점을 수집
   - 이를 종합하여 자신만의 의견 생성
   - 유사한 제목이라고 중복 처리하면 다양한 관점 손실

#### 왜 Event Overlap도 제거했나?

1. **같은 이벤트, 다른 소스 = 더 풍부한 콘텐츠**
   - 하나의 토픽을 다루더라도 여러 소스가 있어야 양질의 콘텐츠
   - Reddit + HN + TechCrunch를 모두 수집해야 다각적 관점 제공

2. **페르소나의 역할**
   - 중복 필터링은 Deduplicator가 아닌 Persona가 담당
   - 같은 이벤트에 대한 여러 토픽을 수집 → RAG에서 통합하여 콘텐츠 생성

3. **채널 간 독립성 보장**
   - 채널 A가 "Tesla" 토픽 선택 → 채널 A 스타일로 영상
   - 채널 B도 같은 토픽 선택 가능 → 채널 B 스타일로 다른 영상

**최종 구조:**
| Level | 비교 대상 | Scope | 목적 |
|-------|----------|-------|------|
| Hash | content_hash | Per-channel | 정확히 같은 콘텐츠 중복 방지 |

### 5.2 중복 감지 전략
```python
"""Topic deduplication service.

Hash-only deduplication - only exact content matches are filtered.
Different articles about the same event are intentionally allowed
to provide diverse perspectives for richer content generation.
"""

class DedupReason(str, Enum):
    """Reason for duplicate detection."""
    EXACT_HASH = "exact_hash"


class DedupResult(BaseModel):
    """Result of duplicate detection."""
    is_duplicate: bool
    duplicate_of: str | None = None
    reason: DedupReason | None = None


class TopicDeduplicator:
    """Detects and removes duplicate topics using hash matching.

    Only exact content matches are considered duplicates.
    Different articles about the same event are NOT duplicates
    - they provide diverse perspectives for the persona.
    """

    HASH_KEY_PREFIX = "dedup:hash:"

    def __init__(self, redis: AsyncRedis, config: DedupConfig | None = None):
        self.redis = redis
        self.config = config or DedupConfig()

    async def is_duplicate(
        self, topic: NormalizedTopic, channel_id: str
    ) -> DedupResult:
        """Check if topic is a duplicate via hash match."""
        hash_key = f"{self.HASH_KEY_PREFIX}{channel_id}:{topic.content_hash}"

        existing = await self.redis.get(hash_key)
        if existing:
            return DedupResult(
                is_duplicate=True,
                duplicate_of=topic.content_hash,
                reason=DedupReason.EXACT_HASH,
            )

        return DedupResult(is_duplicate=False)

    async def mark_as_seen(self, topic: NormalizedTopic, channel_id: str) -> None:
        """Mark topic as seen to prevent future duplicates."""
        ttl_seconds = int(timedelta(days=self.config.hash_ttl_days).total_seconds())

        hash_key = f"{self.HASH_KEY_PREFIX}{channel_id}:{topic.content_hash}"
        await self.redis.setex(hash_key, ttl_seconds, topic.title_normalized)
```

### 5.3 토픽 클러스터링 (향후 확장 - RAG 단계)

중복 제거는 Hash-Only이지만, 같은 이벤트에 대한 여러 토픽을 **클러스터링**하여 RAG에서 활용할 수 있음:

```typescript
// 같은 이벤트에 대한 여러 소스 → 클러스터로 묶기 (RAG 단계)
interface TopicCluster {
  id: string;
  event: string;                    // 이벤트 요약
  mainTopic: NormalizedTopic;       // 대표 토픽 (가장 높은 점수)
  relatedTopics: NormalizedTopic[]; // 관련 토픽들 (다른 소스)

  // 클러스터 메타
  sourceCount: number;              // 몇 개 소스에서 나왔는지
  totalScore: number;               // 종합 관심도

  // 종합 정보
  mergedEntities: Entity[];
  mergedKeywords: string[];
}

// 클러스터링 → 더 신뢰성 있는 토픽으로 승격
// 여러 소스에서 같은 이벤트 → 더 풍부한 콘텐츠 생성 가능
```

**주의**: 이 클러스터링은 중복 제거가 아닌, 콘텐츠 생성 품질 향상을 위한 것

---

## 6. 스코어링

### 6.1 스코어 구성 요소
```typescript
interface ScoreComponents {
  // 소스 기반
  sourceCredibility: number;     // 소스 신뢰도 (0-1)
  sourceScore: number;           // 원본 점수 정규화 (0-1)

  // 시간 기반
  freshness: number;             // 신선도 (0-1)

  // 트렌드 기반
  trendMomentum: number;         // 트렌드 상승세 (0-1)
  multiSourceBonus: number;      // 여러 소스 언급 보너스 (0-0.3)

  // 채널 기반
  categoryRelevance: number;     // 카테고리 매칭 (0-1)
  keywordRelevance: number;      // 키워드 매칭 (0-1)
  entityRelevance: number;       // 엔티티 매칭 (0-1)

  // 히스토리 기반
  novelty: number;               // 새로움 (과거에 안 다룬 주제) (0-1)
  seriesBonus: number;           // 시리즈 연속성 보너스 (0-0.3)
}

interface ScoringWeights {
  sourceCredibility: number;
  sourceScore: number;
  freshness: number;
  trendMomentum: number;
  multiSourceBonus: number;
  categoryRelevance: number;
  keywordRelevance: number;
  entityRelevance: number;
  novelty: number;
  seriesBonus: number;
}
```

### 6.2 스코어링 로직
```typescript
class TopicScorer {
  constructor(
    private channelConfig: ChannelConfig,
    private trendService: TrendService,
    private historyService: ContentHistoryService,
    private seriesService: SeriesService,
  ) {}

  async score(topic: NormalizedTopic): Promise<NormalizedTopic> {
    const weights = this.channelConfig.scoringWeights;

    const components: ScoreComponents = {
      // 소스 기반
      sourceCredibility: topic.source.credibility / 10,
      sourceScore: topic.scores.source,

      // 시간 기반
      freshness: this.calculateFreshness(topic.timestamps.published),

      // 트렌드 기반
      trendMomentum: await this.trendService.getMomentum(topic.classification.keywords),
      multiSourceBonus: await this.calculateMultiSourceBonus(topic),

      // 채널 기반
      categoryRelevance: this.calculateCategoryRelevance(topic),
      keywordRelevance: this.calculateKeywordRelevance(topic),
      entityRelevance: this.calculateEntityRelevance(topic),

      // 히스토리 기반
      novelty: await this.calculateNovelty(topic),
      seriesBonus: await this.calculateSeriesBonus(topic),
    };

    // 가중 합계
    const totalScore =
      components.sourceCredibility * weights.sourceCredibility +
      components.sourceScore * weights.sourceScore +
      components.freshness * weights.freshness +
      components.trendMomentum * weights.trendMomentum +
      components.multiSourceBonus +  // 보너스는 가중치 없이 추가
      components.categoryRelevance * weights.categoryRelevance +
      components.keywordRelevance * weights.keywordRelevance +
      components.entityRelevance * weights.entityRelevance +
      components.novelty * weights.novelty +
      components.seriesBonus;  // 보너스는 가중치 없이 추가

    return {
      ...topic,
      scores: {
        ...topic.scores,
        freshness: components.freshness,
        trend: components.trendMomentum,
        relevance: (components.categoryRelevance + components.keywordRelevance + components.entityRelevance) / 3,
        total: Math.round(totalScore * 100),
      },
    };
  }

  // 시리즈 보너스: 이전에 잘 됐던 주제의 후속
  private async calculateSeriesBonus(topic: NormalizedTopic): Promise<number> {
    const series = await this.seriesService.findMatchingSeries(topic);

    if (!series) return 0;

    // 시리즈 성과에 따른 보너스
    const avgPerformance = series.averagePerformance;
    if (avgPerformance >= 0.8) return 0.3;  // 고성과 시리즈
    if (avgPerformance >= 0.5) return 0.15; // 중간 성과
    return 0.05;  // 저성과지만 시리즈 연속성
  }
}
```

---

## 7. 시리즈 자동 감지

### 7.1 시리즈 정의
```typescript
interface Series {
  id: string;
  name: string;                      // "AI 뉴스", "주간 밈 정리"

  // 시리즈 조건
  criteria: {
    keywords: string[];              // 공통 키워드
    categories: string[];            // 공통 카테고리
    minSimilarity: number;           // 최소 유사도
  };

  // 성과
  performance: {
    episodeCount: number;
    averageViews: number;
    averageEngagement: number;
    trend: 'rising' | 'stable' | 'declining';
  };

  // 히스토리
  episodes: SeriesEpisode[];

  // 자동 감지 여부
  autoDetected: boolean;
  confirmedByUser: boolean;
}

interface SeriesEpisode {
  topicId: string;
  videoId?: string;
  episode: number;
  publishedAt: Date;
  performance: {
    views: number;
    likes: number;
    comments: number;
  };
}
```

### 7.2 자동 감지 로직
```typescript
class SeriesDetector {
  constructor(
    private historyService: ContentHistoryService,
    private performanceService: PerformanceService,
  ) {}

  // 성과 데이터 기반으로 시리즈 패턴 감지
  async detectSeries(): Promise<Series[]> {
    // 1. 최근 고성과 콘텐츠 가져오기
    const recentHighPerformers = await this.performanceService.getTopPerformers({
      days: 30,
      minViews: 1000,
      limit: 50,
    });

    // 2. 키워드/카테고리 클러스터링
    const clusters = this.clusterByTopics(recentHighPerformers);

    // 3. 연속 성공 패턴 찾기
    const potentialSeries: Series[] = [];

    for (const cluster of clusters) {
      if (cluster.items.length >= 3) {  // 최소 3개 이상
        const avgPerformance = this.calculateAveragePerformance(cluster.items);

        if (avgPerformance.engagementRate >= 0.05) {  // 5% 이상 engagement
          potentialSeries.push({
            id: generateUUID(),
            name: this.generateSeriesName(cluster),
            criteria: {
              keywords: cluster.commonKeywords,
              categories: cluster.commonCategories,
              minSimilarity: 0.6,
            },
            performance: {
              episodeCount: cluster.items.length,
              averageViews: avgPerformance.views,
              averageEngagement: avgPerformance.engagementRate,
              trend: this.calculateTrend(cluster.items),
            },
            episodes: cluster.items.map((item, idx) => ({
              topicId: item.topicId,
              videoId: item.videoId,
              episode: idx + 1,
              publishedAt: item.publishedAt,
              performance: item.performance,
            })),
            autoDetected: true,
            confirmedByUser: false,
          });
        }
      }
    }

    return potentialSeries;
  }

  // 새 토픽이 기존 시리즈에 맞는지 체크
  async matchToSeries(topic: NormalizedTopic): Promise<Series | null> {
    const activeSeries = await this.getActiveSeries();

    for (const series of activeSeries) {
      const keywordMatch = this.calculateOverlap(
        topic.classification.keywords,
        series.criteria.keywords
      );

      const categoryMatch = this.calculateOverlap(
        topic.classification.categories,
        series.criteria.categories
      );

      const similarity = (keywordMatch + categoryMatch) / 2;

      if (similarity >= series.criteria.minSimilarity) {
        return series;
      }
    }

    return null;
  }
}
```

---

## 8. 주제 큐

### 8.1 큐 구조
```typescript
interface TopicQueue {
  channelId: string;

  // 우선순위 큐 (점수 기반)
  pending: PriorityQueue<NormalizedTopic>;

  // 상태별 저장소
  approved: NormalizedTopic[];
  rejected: NormalizedTopic[];
  used: NormalizedTopic[];

  // 설정
  config: {
    maxPendingSize: number;       // 최대 대기 크기
    minScoreThreshold: number;    // 최소 점수
    autoExpireHours: number;      // 자동 만료 시간
  };
}
```

### 8.2 큐 관리
```typescript
class TopicQueueManager {
  async addTopic(channelId: string, topic: NormalizedTopic): Promise<boolean> {
    const queue = await this.getQueue(channelId);

    // 최소 점수 체크
    if (topic.scores.total < queue.config.minScoreThreshold) {
      return false;
    }

    // 큐 크기 체크
    if (queue.pending.size >= queue.config.maxPendingSize) {
      const lowest = queue.pending.peekLowest();
      if (lowest && topic.scores.total > lowest.scores.total) {
        queue.pending.removeLow();
      } else {
        return false;
      }
    }

    queue.pending.push(topic);
    return true;
  }

  async getNextTopic(channelId: string): Promise<NormalizedTopic | null> {
    const queue = await this.getQueue(channelId);
    return queue.pending.pop();
  }

  // 만료된 토픽 정리
  async cleanup(channelId: string): Promise<number> {
    const queue = await this.getQueue(channelId);
    const now = new Date();

    let removed = 0;
    queue.pending = queue.pending.filter(topic => {
      if (topic.timestamps.expires < now) {
        removed++;
        return false;
      }
      return true;
    });

    return removed;
  }
}
```

---

## 9. 수집 아키텍처: 하이브리드 방식

### 9.1 설계 배경

**문제점**: 순수 채널별 수집의 한계
- 모든 채널이 HN, Google Trends 등을 각각 수집 → API 중복 호출
- 반대로 순수 공통 수집은 불가능 (Reddit의 모든 subreddit 수집? ❌)

**해결책**: 소스 특성에 따른 하이브리드 수집

```
┌─────────────────────────────────────────────────────────────────┐
│                      Source Classification                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   Global Sources (공통 수집)        Scoped Sources (채널별 수집)  │
│   ───────────────────────────      ──────────────────────────── │
│   • HackerNews (top N 고정)        • Reddit (subreddit 지정)     │
│   • Google Trends (trending)       • DCInside (gallery 지정)     │
│   • YouTube Trending (국가별)       • Clien (board 지정)         │
│   • RSS (고정 피드 목록)            • RSS (채널별 피드)           │
│                                                                  │
│           ↓                                   ↓                  │
│     [Global Pool]                    [Channel Collection]        │
│     Redis에 캐싱 (TTL)                직접 수집 후 처리           │
│           ↓                                   ↓                  │
│     채널별 필터링                     정규화/중복제거/스코어링    │
│           ↓                                   ↓                  │
│                      [Channel Queue]                             │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 소스 타입 분류

```python
class SourceScope(str, Enum):
    """소스의 수집 범위 분류."""
    GLOBAL = "global"   # 한 번 수집, 모든 채널 공유
    SCOPED = "scoped"   # 채널별 파라미터로 수집

# 소스별 분류
SOURCE_SCOPES = {
    # Global: 파라미터 없이 top N 수집
    "hackernews": SourceScope.GLOBAL,
    "google_trends": SourceScope.GLOBAL,
    "youtube_trending": SourceScope.GLOBAL,

    # Scoped: 채널별 파라미터 필요
    "reddit": SourceScope.SCOPED,      # subreddits 필요
    "dcinside": SourceScope.SCOPED,    # galleries 필요
    "clien": SourceScope.SCOPED,       # boards 필요
    "rss": SourceScope.SCOPED,         # feed_url 필요 (채널별 다를 수 있음)
}
```

### 9.3 Global Topic Pool

```python
class GlobalTopicPool:
    """Global 소스에서 수집된 토픽을 저장하는 Redis 기반 풀.

    모든 채널이 공유하며, 각 채널은 자신의 필터로 필요한 것만 가져감.
    """

    POOL_KEY_PREFIX = "global_pool:"
    DEFAULT_TTL_HOURS = 24

    def __init__(self, redis: AsyncRedis):
        self.redis = redis

    async def add_topics(
        self,
        source_type: str,
        topics: list[RawTopic],
        ttl_hours: int = DEFAULT_TTL_HOURS
    ) -> int:
        """Global Pool에 토픽 추가.

        Args:
            source_type: 소스 타입 (hackernews, google_trends 등)
            topics: 수집된 RawTopic 리스트
            ttl_hours: 캐시 TTL

        Returns:
            추가된 토픽 수
        """
        key = f"{self.POOL_KEY_PREFIX}{source_type}"

        # 기존 데이터 삭제 후 새로 추가 (최신 데이터로 교체)
        await self.redis.delete(key)

        for topic in topics:
            await self.redis.rpush(key, topic.model_dump_json())

        await self.redis.expire(key, ttl_hours * 3600)
        return len(topics)

    async def get_topics(self, source_type: str) -> list[RawTopic]:
        """Global Pool에서 토픽 조회.

        Args:
            source_type: 소스 타입

        Returns:
            캐시된 RawTopic 리스트 (없으면 빈 리스트)
        """
        key = f"{self.POOL_KEY_PREFIX}{source_type}"
        data = await self.redis.lrange(key, 0, -1)

        return [RawTopic.model_validate_json(item) for item in data]

    async def is_fresh(self, source_type: str) -> bool:
        """캐시가 유효한지 확인."""
        key = f"{self.POOL_KEY_PREFIX}{source_type}"
        return await self.redis.exists(key) > 0
```

### 9.4 수집 흐름

#### Global Collector (별도 스케줄)

```python
@shared_task(name="app.workers.collect.collect_global_sources")
def collect_global_sources():
    """모든 Global 소스를 한 번에 수집하여 Pool에 저장.

    스케줄: 2시간마다 (0 */2 * * *)
    모든 채널보다 먼저 실행되어 Pool을 채움.
    """
    global_sources = ["hackernews", "google_trends", "youtube_trending"]

    for source_type in global_sources:
        topics = collect_from_source(source_type)
        global_pool.add_topics(source_type, topics)
```

#### Channel Collector (채널별 스케줄)

```python
@shared_task(name="app.workers.collect.collect_channel_topics")
def collect_channel_topics(channel_id: str, channel_config: dict):
    """채널별 토픽 수집.

    1. Global Pool에서 해당 채널에 맞는 토픽 필터링
    2. Scoped 소스 직접 수집
    3. 합쳐서 정규화 → 중복제거 → 스코어링 → 큐 추가
    """
    all_topics = []

    # 1. Global Pool에서 가져오기
    for source_type in channel_config["global_sources"]:
        pool_topics = global_pool.get_topics(source_type)
        # 채널 필터 적용
        filtered = apply_channel_filter(pool_topics, channel_config["filters"])
        all_topics.extend(filtered)

    # 2. Scoped 소스 직접 수집
    for source_def in channel_config["scoped_sources"]:
        # 예: {"type": "reddit", "params": {"subreddits": ["python", "programming"]}}
        topics = collect_from_source(
            source_type=source_def["type"],
            params=source_def["params"]
        )
        all_topics.extend(topics)

    # 3. 처리 파이프라인
    for topic in all_topics:
        normalized = normalizer.normalize(topic)
        if deduplicator.is_duplicate(normalized, channel_id):
            continue
        scored = scorer.score(normalized)
        queue_manager.add_topic(channel_id, scored)
```

### 9.5 Scoped 소스 중복 수집 최적화

같은 subreddit을 여러 채널이 관심 있는 경우 캐싱으로 최적화:

```python
class ScopedSourceCache:
    """Scoped 소스의 수집 결과를 짧은 시간 캐싱.

    예: 채널 A, B 모두 r/programming 관심
    → 첫 번째 수집 시 캐시, 두 번째는 캐시에서 가져옴
    """

    CACHE_KEY_PREFIX = "scoped_cache:"
    DEFAULT_TTL_MINUTES = 30  # 30분 캐시

    def _make_key(self, source_type: str, params: dict) -> str:
        """파라미터 기반 캐시 키 생성."""
        # 예: scoped_cache:reddit:subreddits=programming,python
        param_str = ",".join(f"{k}={v}" for k, v in sorted(params.items()))
        return f"{self.CACHE_KEY_PREFIX}{source_type}:{param_str}"

    async def get_or_collect(
        self,
        source_type: str,
        params: dict,
        collector: Callable
    ) -> list[RawTopic]:
        """캐시에 있으면 반환, 없으면 수집 후 캐시."""
        key = self._make_key(source_type, params)

        # 캐시 확인
        cached = await self.redis.get(key)
        if cached:
            return [RawTopic.model_validate_json(t) for t in json.loads(cached)]

        # 수집
        topics = await collector(source_type, params)

        # 캐시 저장
        await self.redis.setex(
            key,
            self.DEFAULT_TTL_MINUTES * 60,
            json.dumps([t.model_dump_json() for t in topics])
        )

        return topics
```

### 9.6 스케줄 구성

```python
# Celery Beat 스케줄 예시
CELERY_BEAT_SCHEDULE = {
    # Global 수집: 2시간마다 (모든 채널보다 먼저)
    "collect-global-sources": {
        "task": "app.workers.collect.collect_global_sources",
        "schedule": crontab(minute=0, hour="*/2"),
        "options": {"queue": "collect-global"},
    },

    # 채널별 수집: 4시간마다 (Global 수집 30분 후)
    "collect-channel-tech": {
        "task": "app.workers.collect.collect_channel_topics",
        "schedule": crontab(minute=30, hour="*/4"),
        "args": ["channel-tech-uuid", {...config...}],
        "options": {"queue": "collect-channel"},
    },
    "collect-channel-entertainment": {
        "task": "app.workers.collect.collect_channel_topics",
        "schedule": crontab(minute=30, hour="*/4"),
        "args": ["channel-ent-uuid", {...config...}],
        "options": {"queue": "collect-channel"},
    },
}
```

### 9.7 채널 Config 예시 (업데이트)

```yaml
# config/channels/tech-channel.yaml
channel:
  id: "tech-channel-uuid"
  name: "테크 뉴스"

topic_collection:
  # Global 소스 (Pool에서 가져옴)
  global_sources:
    - hackernews
    - google_trends
    - youtube_trending

  # Scoped 소스 (직접 수집)
  scoped_sources:
    - type: reddit
      params:
        subreddits: ["programming", "technology", "MachineLearning"]
    - type: dcinside
      params:
        galleries: ["programming", "ai"]
    - type: clien
      params:
        boards: ["cm_ittalk", "cm_tech"]

  # 필터 (Global Pool 토픽에 적용)
  filters:
    include_categories: ["tech", "programming", "ai", "startup"]
    exclude_keywords: ["광고", "홍보"]
    min_score: 50
```
