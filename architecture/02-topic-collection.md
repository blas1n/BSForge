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

### 5.1 중복 감지 전략
```typescript
interface DedupResult {
  isDuplicate: boolean;
  duplicateOf?: string;        // 원본 토픽 ID
  similarity: number;          // 유사도 (0-1)
  reason?: 'exact_hash' | 'similar_title' | 'same_event' | 'keyword_overlap';
}

class TopicDeduplicator {
  constructor(
    private vectorDB: VectorDB,
    private recentTopics: RecentTopicCache,
  ) {}
  
  async checkDuplicate(
    topic: NormalizedTopic,
    config: DedupConfig
  ): Promise<DedupResult> {
    // 1. 해시 완전 일치 (가장 빠름)
    const hashMatch = await this.recentTopics.findByHash(topic.hash);
    if (hashMatch) {
      return {
        isDuplicate: true,
        duplicateOf: hashMatch.id,
        similarity: 1.0,
        reason: 'exact_hash',
      };
    }
    
    // 2. 제목 유사도 체크
    const titleEmbedding = await this.embed(topic.title.normalized);
    const similarByTitle = await this.vectorDB.query({
      vector: titleEmbedding,
      topK: 5,
      filter: {
        collectedAfter: new Date(Date.now() - config.timeWindowHours * 60 * 60 * 1000),
      },
    });
    
    for (const match of similarByTitle) {
      if (match.similarity >= config.titleSimilarityThreshold) {
        return {
          isDuplicate: true,
          duplicateOf: match.id,
          similarity: match.similarity,
          reason: 'similar_title',
        };
      }
    }
    
    // 3. 같은 이벤트 감지 (엔티티 + 시간 기반)
    if (topic.classification.entities.length > 0) {
      const sameEvent = await this.findSameEvent(topic, config);
      if (sameEvent) {
        return {
          isDuplicate: true,
          duplicateOf: sameEvent.id,
          similarity: sameEvent.similarity,
          reason: 'same_event',
        };
      }
    }
    
    return { isDuplicate: false, similarity: 0 };
  }
  
  // 같은 이벤트/사건 감지
  private async findSameEvent(
    topic: NormalizedTopic,
    config: DedupConfig
  ): Promise<{ id: string; similarity: number } | null> {
    const entityNames = topic.classification.entities.map(e => e.name);
    
    const candidates = await this.recentTopics.findByEntities(
      entityNames,
      config.timeWindowHours
    );
    
    for (const candidate of candidates) {
      // 엔티티 오버랩 체크
      const candidateEntities = candidate.classification.entities.map(e => e.name);
      const overlap = this.calculateOverlap(entityNames, candidateEntities);
      
      // 키워드 오버랩 체크
      const keywordOverlap = this.calculateOverlap(
        topic.classification.keywords,
        candidate.classification.keywords
      );
      
      const combinedSimilarity = (overlap + keywordOverlap) / 2;
      
      if (combinedSimilarity >= config.eventSimilarityThreshold) {
        return { id: candidate.id, similarity: combinedSimilarity };
      }
    }
    
    return null;
  }
}
```

### 5.2 이벤트 클러스터링
```typescript
// 같은 이벤트에 대한 여러 소스 → 클러스터로 묶기
interface TopicCluster {
  id: string;
  event: string;                    // 이벤트 요약
  mainTopic: NormalizedTopic;       // 대표 토픽 (가장 높은 점수)
  relatedTopics: NormalizedTopic[]; // 관련 토픽들
  
  // 클러스터 메타
  sourceCount: number;              // 몇 개 소스에서 나왔는지
  totalScore: number;               // 종합 관심도
  
  // 종합 정보
  mergedEntities: Entity[];
  mergedKeywords: string[];
}

// 클러스터링 → 더 신뢰성 있는 토픽으로 승격
// 여러 소스에서 같은 이벤트 → 중요한 이슈일 가능성 높음
```

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

## 9. 수집 스케줄러

```typescript
class CollectionScheduler {
  private jobs: Map<string, CronJob> = new Map();
  
  async initialize(channels: ChannelConfig[]) {
    for (const channel of channels) {
      await this.scheduleForChannel(channel);
    }
  }
  
  private async scheduleForChannel(channel: ChannelConfig) {
    const sources = await this.getEnabledSources(channel);
    
    for (const source of sources) {
      const jobId = `${channel.id}-${source.id}`;
      
      const job = new CronJob(source.schedule.cron, async () => {
        console.log(`[Scheduler] Running collection: ${jobId}`);
        
        try {
          const collector = this.getCollector(source.type);
          const rawTopics = await collector.collect(source, channel.sourceConfig);
          
          for (const raw of rawTopics) {
            await this.processTopic(raw, source, channel);
          }
        } catch (error) {
          console.error(`[Scheduler] Error in ${jobId}:`, error);
        }
      });
      
      this.jobs.set(jobId, job);
      job.start();
    }
  }
  
  private async processTopic(
    raw: RawTopic,
    source: Source,
    channel: ChannelConfig
  ) {
    // 1. 정규화
    const normalized = await this.normalizer.normalize(raw, source);
    
    // 2. 주제 필터링 (include/exclude)
    const filterResult = await this.topicFilter.check(normalized, channel.topicConfig);
    if (!filterResult.passed) {
      return;
    }
    
    // 3. 중복 체크
    const dedupResult = await this.deduplicator.check(normalized);
    if (dedupResult.isDuplicate) {
      return;
    }
    
    // 4. 스코어링
    const scored = await this.scorer.score(normalized);
    
    // 5. 큐에 추가
    await this.queueManager.addTopic(channel.id, scored);
  }
}
```
