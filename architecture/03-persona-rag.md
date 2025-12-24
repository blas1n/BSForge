# 🎭 페르소나 RAG 시스템 상세 설계

## 1. 개요

### 1.1 목표
- 채널마다 고유한 "분신"을 만들어 일관된 콘텐츠 생성
- 과거 콘텐츠 기반으로 스타일 유지 (RAG)
- 성과 피드백으로 점진적 개선
- 파인튜닝 데이터 자동 수집

### 1.2 핵심 철학
> **"채널 = 화자"** - 브랜드/채널 자체가 말하는 스타일

실제 사람이나 캐릭터가 아닌, 채널 브랜드가 직접 이야기하는 느낌.

### 1.3 데이터 플로우
```
[주제] → [관련 과거 콘텐츠 검색] → [페르소나 컨텍스트 구성] → [LLM 생성] → [후처리]
              ↑                              ↑                              ↓
         [벡터 DB]                    [페르소나 Config]               [스타일 검증]
```

---

## 2. 페르소나 정의

### 2.1 페르소나 스키마
```typescript
interface Persona {
  id: string;
  channelId: string;                   // 연결된 채널

  // === 정체성 ===
  identity: {
    name: string;                      // 채널명
    tagline: string;                   // 한 줄 소개
    description: string;               // 상세 설명
    expertise: string[];               // 전문 분야
  };

  // === 음성 설정 ===
  voice: {
    gender: 'male' | 'female';
    ttsService: 'edge-tts' | 'elevenlabs' | 'clova' | 'typecast';
    voiceId: string;                   // TTS 음성 ID
    voiceSettings?: {
      speed: number;                   // 0.5 - 2.0
      pitch: number;                   // -20 - 20
      stability?: number;              // ElevenLabs용
      clarity?: number;
    };
  };

  // === 커뮤니케이션 스타일 ===
  communication: {
    // 기본 톤
    tone: 'friendly' | 'professional' | 'casual' | 'authoritative' | 'humorous';
    formality: 'formal' | 'semi-formal' | 'informal';

    // 말투 패턴
    speechPatterns: {
      sentenceEndings: string[];       // ["~해요", "~입니다", "~거든요"]
      connectors: string[];            // ["그래서", "근데", "사실"]
      emphasisWords: string[];         // ["진짜", "핵심은", "중요한 건"]
      fillerWords: string[];           // 자연스러움을 위한 추임새
    };

    // 금지 표현
    avoidPatterns: {
      words: string[];                 // ["혁신적인", "패러다임", "시너지"]
      phrases: string[];               // ["구독과 좋아요", "알람 설정"]
      styles: string[];                // ["과장", "클릭베이트"]
    };

    // 구조 선호
    structurePreference: {
      hookStyle: 'question' | 'statement' | 'statistic' | 'story';
      usesAnalogies: boolean;
      exampleFrequency: 'rare' | 'moderate' | 'frequent';
      ctaStyle: 'soft' | 'direct' | 'none';
    };
  };

  // === 관점/사고방식 ===
  perspective: {
    coreValues: string[];              // ["실용성", "솔직함", "깊이"]
    biases: string[];                  // 인정하는 편향
    contrarian?: string[];             // 주류와 다른 의견 (있다면)
  };

  // === 콘텐츠 철학 ===
  contentPhilosophy: {
    targetAudience: string;            // "주니어 개발자", "테크 관심있는 직장인"
    uniqueAngle: string;               // 차별화 포인트
    contentGoals: string[];            // ["정보 전달", "인사이트 제공", "재미"]
  };

  // === 예시 (Few-shot) ===
  examples: {
    scripts: ScriptExample[];          // 좋은 스크립트 예시
    reactions: ReactionExample[];      // 상황별 반응 예시
    badExamples?: BadExample[];        // 피해야 할 예시
  };

  // === 메타 ===
  metadata: {
    createdAt: Date;
    updatedAt: Date;
    version: number;
  };
}

interface ScriptExample {
  topic: string;
  category: string;
  script: string;
  performance?: {
    views: number;
    engagement: number;
  };
  notes?: string;                      // 왜 이게 좋은 예시인지
}

interface ReactionExample {
  situation: string;                   // "새로운 AI 도구가 나왔을 때"
  reaction: string;                    // 전형적인 반응
  reasoning: string;                   // 왜 이렇게 반응하는지
}

interface BadExample {
  script: string;
  problems: string[];                  // 무엇이 문제인지
}
```

### 2.2 페르소나 예시: 테크 채널
```typescript
const techPersona: Persona = {
  id: 'persona-tech-001',
  channelId: 'channel-tech-001',

  identity: {
    name: '테크브로',
    tagline: '뻔한 소리 없이 핵심만',
    description: '현업 개발자 시선으로 테크 트렌드를 정리합니다. 과장 없이, 실용적으로.',
    expertise: ['백엔드 개발', 'AI/ML', '스타트업', '개발자 커리어'],
  },

  voice: {
    gender: 'male',
    ttsService: 'edge-tts',
    voiceId: 'ko-KR-InJoonNeural',
    voiceSettings: {
      speed: 1.1,
      pitch: 0,
    },
  },

  communication: {
    tone: 'friendly',
    formality: 'semi-formal',

    speechPatterns: {
      sentenceEndings: ['~해요', '~거든요', '~인 거죠', '~잖아요'],
      connectors: ['근데', '사실', '솔직히', '그래서'],
      emphasisWords: ['핵심은', '중요한 건', '진짜', '결국'],
      fillerWords: ['음', '뭐'],
    },

    avoidPatterns: {
      words: ['혁신적인', '패러다임', '시너지', '레버리지', '게임체인저'],
      phrases: ['구독과 좋아요', '알람 설정', '끝까지 시청', '놓치지 마세요'],
      styles: ['과장', '공포 마케팅', '클릭베이트'],
    },

    structurePreference: {
      hookStyle: 'statement',
      usesAnalogies: true,
      exampleFrequency: 'frequent',
      ctaStyle: 'none',
    },
  },

  perspective: {
    coreValues: ['실용성', '솔직함', '깊이있는 단순함'],
    biases: [
      '오버엔지니어링 싫어함',
      '검증된 기술 선호',
      '트렌드보다 본질 중시',
    ],
    contrarian: [
      'AI 만능론에 회의적',
      '새 프레임워크 맹신 반대',
      '"빠르게 실패하라" 맹신 경계',
    ],
  },

  contentPhilosophy: {
    targetAudience: '개발자, 테크에 관심있는 직장인',
    uniqueAngle: '현업 경험 기반, 과장 없는 팩트 중심',
    contentGoals: ['정보 전달', '인사이트 제공', '실용적 관점'],
  },

  examples: {
    scripts: [
      {
        topic: 'AI 코딩 도구',
        category: 'tech',
        script: `요즘 AI 코딩 도구 엄청 쏟아지잖아요.

근데 솔직히, 대부분 비슷비슷해요.

제가 2주 동안 실제로 써본 결과,
진짜 쓸만한 건 딱 두 가지 상황이에요.

하나는 보일러플레이트 코드 짤 때.
두 번째는 익숙하지 않은 언어로 뭔가 빠르게 만들어야 할 때.

복잡한 비즈니스 로직? 아직 멀었어요.
AI가 우리 도메인을 이해할 리가 없잖아요.

핵심은, 도구로 쓰되 의존하지 말라는 거죠.`,
        performance: { views: 15000, engagement: 0.08 },
        notes: '개인 경험 기반, 과장 없음, 실용적 결론',
      },
    ],
    reactions: [
      {
        situation: '새로운 프레임워크가 핫해졌을 때',
        reaction: '일단 지켜봄. 6개월 뒤에도 쓰는 사람 있으면 그때 봄.',
        reasoning: '트렌드에 휩쓸리지 않고 검증된 것만',
      },
      {
        situation: 'AI가 개발자를 대체한다는 기사',
        reaction: '또 시작이네. 코딩은 타이핑이 아니라 문제 정의인데.',
        reasoning: 'AI 과대평가에 회의적, 본질을 봄',
      },
      {
        situation: '스타트업 대량 해고 뉴스',
        reaction: '거품 빠지는 과정. 결국 실력 있는 사람은 괜찮음.',
        reasoning: '냉정하지만 현실적인 시각',
      },
    ],
    badExamples: [
      {
        script: `혁신적인 AI 도구가 개발 패러다임을 완전히 바꾸고 있습니다!
이 도구를 활용하면 생산성이 10배 향상됩니다.
지금 바로 도입하지 않으면 뒤처질 것입니다!`,
        problems: ['과장된 표현', '공포 마케팅', '검증 안 된 수치', '뻔한 결론'],
      },
    ],
  },

  metadata: {
    createdAt: new Date(),
    updatedAt: new Date(),
    version: 1,
  },
};
```

---

## 3. 콘텐츠 벡터 DB

### 3.1 저장 콘텐츠 유형
```typescript
type ContentType =
  | 'script'          // 영상 스크립트
  | 'draft'           // 미완성 초안
  | 'outline'         // 아웃라인
  | 'note';           // 관점/의견 메모

interface StoredContent {
  id: string;
  channelId: string;
  type: ContentType;

  // 원본
  content: string;
  title?: string;

  // 분류
  classification: {
    topics: string[];              // 주제 태그
    categories: string[];          // 카테고리
    keywords: string[];
    entities: string[];
  };

  // 콘텐츠 특성
  characteristics: {
    hasOpinion: boolean;           // 의견 포함
    hasExample: boolean;           // 예시 포함
    hasAnalogy: boolean;           // 비유 사용
    emotionalTone: string;         // 감정 톤
    contentType: 'informative' | 'opinion' | 'reaction' | 'tutorial';
  };

  // 성과 (발행된 경우)
  performance?: {
    videoId: string;
    views: number;
    likes: number;
    comments: number;
    watchTime: number;
    engagementRate: number;
  };

  // 메타
  metadata: {
    createdAt: Date;
    publishedAt?: Date;
    source?: string;               // 어떤 주제에서 생성됐는지
    series?: string;               // 시리즈 ID
  };
}
```

### 3.2 청킹 전략
```typescript
interface ChunkConfig {
  maxTokens: number;               // 최대 토큰
  overlap: number;                 // 오버랩 토큰
  splitBy: 'paragraph' | 'sentence' | 'semantic';

  // 패턴 기반 분류 (설정 가능)
  opinionPatterns: string[];       // 의견 탐지 패턴
  examplePatterns: string[];       // 예시 탐지 패턴
  analogyPatterns: string[];       // 비유 탐지 패턴

  // LLM 기반 분류 (선택)
  useLlmClassification: boolean;   // 더 정확한 분류
}

interface ContentChunk {
  id: string;
  contentId: string;               // 원본 콘텐츠 ID
  channelId: string;

  // 청크 내용
  text: string;
  index: number;                   // 청크 순서

  // 컨텍스트
  context: {
    before?: string;               // 이전 청크 요약
    after?: string;                // 다음 청크 요약
    position: 'hook' | 'body' | 'conclusion';
  };

  // 청크 특성 (검색 필터용)
  // 패턴 기반 또는 LLM 기반으로 자동 분류
  characteristics: {
    isOpinion: boolean;            // 의견 부분
    isExample: boolean;            // 예시 부분
    isAnalogy: boolean;            // 비유 부분
    keywords: string[];
  };

  // 임베딩
  embedding: number[];
}

// 스크립트 특화 청킹
class ScriptChunker {
  constructor(
    private config: ChunkConfig,
    private llmClassifier?: ContentClassifier
  ) {}

  async chunk(script: string): Promise<ContentChunk[]> {
    // 스크립트 구조 파악
    const sections = this.identifySections(script);

    // Hook / Body / Conclusion 분리
    const chunks: ContentChunk[] = [];

    // Hook은 통째로 (보통 짧음)
    if (sections.hook) {
      chunks.push(await this.createChunk(sections.hook, 'hook', 0));
    }

    // Body는 의미 단위로 분할
    const bodyChunks = this.splitBody(sections.body, this.config);
    for (let i = 0; i < bodyChunks.length; i++) {
      chunks.push(await this.createChunk(bodyChunks[i], 'body', i + 1));
    }

    // Conclusion도 통째로
    if (sections.conclusion) {
      chunks.push(await this.createChunk(sections.conclusion, 'conclusion', chunks.length));
    }

    return chunks;
  }

  private identifySections(script: string) {
    // Hook: 처음 2-3문장
    // Body: 중간 내용
    // Conclusion: 마지막 1-2문장

    const paragraphs = script.split('\n\n').filter(p => p.trim());

    return {
      hook: paragraphs.slice(0, 1).join('\n\n'),
      body: paragraphs.slice(1, -1).join('\n\n'),
      conclusion: paragraphs.slice(-1).join('\n\n'),
    };
  }

  // 특성 추출: 패턴 기반 (빠름) 또는 LLM 기반 (정확함)
  private async extractCharacteristics(text: string): Promise<Characteristics> {
    // 1. 패턴 기반 분류 (항상 실행)
    const patternBased = {
      isOpinion: this.matchesPatterns(text, this.config.opinionPatterns),
      isExample: this.matchesPatterns(text, this.config.examplePatterns),
      isAnalogy: this.matchesPatterns(text, this.config.analogyPatterns),
    };

    // 2. LLM 기반 분류 (선택)
    if (this.config.useLlmClassification && this.llmClassifier) {
      try {
        const llmBased = await this.llmClassifier.classify(text);
        // LLM 결과로 덮어쓰기 (더 정확함)
        return { ...patternBased, ...llmBased };
      } catch (error) {
        // 실패 시 패턴 기반 결과 사용
        return patternBased;
      }
    }

    return patternBased;
  }

  private matchesPatterns(text: string, patterns: string[]): boolean {
    const lowerText = text.toLowerCase();
    return patterns.some(pattern =>
      new RegExp(pattern, 'i').test(lowerText)
    );
  }
}

// LLM 기반 콘텐츠 분류기 (선택 사용)
class ContentClassifier {
  constructor(private llm: AnthropicClient) {}

  async classify(text: string): Promise<{
    isOpinion: boolean;
    isExample: boolean;
    isAnalogy: boolean;
  }> {
    const prompt = `Analyze this text and classify:

Text: "${text}"

Answer with ONLY "yes" or "no":
1. Is this an OPINION?
2. Is this an EXAMPLE?
3. Is this an ANALOGY?

Format:
opinion: yes/no
example: yes/no
analogy: yes/no`;

    const response = await this.llm.complete(prompt, {
      model: 'claude-3-5-haiku-20241022',
      maxTokens: 50,
    });

    return this.parseResponse(response);
  }
}
```

### 3.3 임베딩
```typescript
interface EmbeddingConfig {
  model: 'bge-m3' | 'openai-3-small' | 'multilingual-e5';
  dimensions: number;
  batchSize: number;
}

// 추천 설정
const defaultEmbeddingConfig: EmbeddingConfig = {
  model: 'bge-m3',                 // 다국어, 한국어 성능 좋음
  dimensions: 1024,
  batchSize: 32,
};

class ContentEmbedder {
  async embed(chunk: ContentChunk): Promise<number[]> {
    // 검색 품질 향상을 위해 메타데이터 포함
    const textToEmbed = this.prepareText(chunk);
    return await this.embeddingModel.encode(textToEmbed);
  }

  private prepareText(chunk: ContentChunk): string {
    const parts: string[] = [];

    // 위치 정보
    if (chunk.context.position === 'hook') {
      parts.push('[훅]');
    }

    // 특성 정보
    if (chunk.characteristics.isOpinion) {
      parts.push('[의견]');
    }
    if (chunk.characteristics.isExample) {
      parts.push('[예시]');
    }

    // 키워드
    if (chunk.characteristics.keywords.length > 0) {
      parts.push(`[키워드: ${chunk.characteristics.keywords.join(', ')}]`);
    }

    // 본문
    parts.push(chunk.text);

    return parts.join(' ');
  }
}
```

---

## 4. 검색 (Retrieval)

### 4.1 하이브리드 검색
```typescript
interface RetrievalConfig {
  // 시맨틱 검색
  semantic: {
    enabled: boolean;
    weight: number;                // 0.0 - 1.0
    topK: number;
  };

  // 키워드 검색 (BM25)
  keyword: {
    enabled: boolean;
    weight: number;
    topK: number;
  };

  // 리랭킹
  reranking: {
    enabled: boolean;
    model: 'bge-reranker' | 'cohere';
  };

  // 결과 다양성 (MMR)
  diversity: {
    enabled: boolean;
    lambda: number;                // 관련성 vs 다양성 (0.5 - 1.0)
  };

  // 필터
  filters: {
    contentTypes?: ContentType[];
    minPerformance?: number;       // 고성과 콘텐츠 우선
    recencyBoost?: boolean;        // 최신 콘텐츠 부스트
    characteristicFilters?: {
      requireOpinion?: boolean;
      requireExample?: boolean;
    };
  };

  // 최종 결과
  finalTopK: number;
}

const defaultRetrievalConfig: RetrievalConfig = {
  semantic: { enabled: true, weight: 0.7, topK: 20 },
  keyword: { enabled: true, weight: 0.3, topK: 20 },
  reranking: { enabled: true, model: 'bge-reranker' },
  diversity: { enabled: true, lambda: 0.7 },
  filters: {
    minPerformance: 0,
    recencyBoost: false,
  },
  finalTopK: 5,
};
```

### 4.2 검색 파이프라인
```typescript
class RAGRetriever {
  async retrieve(
    query: string,
    channelId: string,
    config: RetrievalConfig = defaultRetrievalConfig
  ): Promise<ContentChunk[]> {
    // 1. 쿼리 확장
    const expandedQueries = await this.expandQuery(query);

    // 2. 하이브리드 검색
    let results: ScoredChunk[] = [];

    for (const q of expandedQueries) {
      // 시맨틱 검색
      if (config.semantic.enabled) {
        const semanticResults = await this.semanticSearch(q, channelId, config);
        results.push(...semanticResults.map(r => ({
          ...r,
          score: r.score * config.semantic.weight,
        })));
      }

      // 키워드 검색
      if (config.keyword.enabled) {
        const keywordResults = await this.keywordSearch(q, channelId, config);
        results.push(...keywordResults.map(r => ({
          ...r,
          score: r.score * config.keyword.weight,
        })));
      }
    }

    // 3. 결과 병합 및 중복 제거
    results = this.mergeResults(results);

    // 4. 필터 적용
    results = this.applyFilters(results, config.filters);

    // 5. 리랭킹
    if (config.reranking.enabled) {
      results = await this.rerank(query, results, config.reranking);
    }

    // 6. 다양성 적용 (MMR)
    if (config.diversity.enabled) {
      results = this.applyMMR(results, config.diversity.lambda);
    }

    return results.slice(0, config.finalTopK).map(r => r.chunk);
  }

  // 쿼리 확장
  private async expandQuery(query: string): Promise<string[]> {
    const queries = [query];

    // LLM으로 관련 검색어 생성
    const expanded = await this.llm.complete(`
      주제: "${query}"

      이 주제를 다른 관점에서 검색할 수 있는 쿼리 2개를 생성해주세요.
      JSON 배열로 반환: ["쿼리1", "쿼리2"]
    `);

    queries.push(...JSON.parse(expanded));
    return queries;
  }

  // MMR (Maximal Marginal Relevance)
  private applyMMR(results: ScoredChunk[], lambda: number): ScoredChunk[] {
    const selected: ScoredChunk[] = [];
    const remaining = [...results];

    while (selected.length < results.length && remaining.length > 0) {
      let bestScore = -Infinity;
      let bestIdx = 0;

      for (let i = 0; i < remaining.length; i++) {
        // 관련성
        const relevance = remaining[i].score;

        // 이미 선택된 것들과의 최대 유사도
        const maxSim = selected.length > 0
          ? Math.max(...selected.map(s => this.similarity(s, remaining[i])))
          : 0;

        // MMR 점수
        const mmr = lambda * relevance - (1 - lambda) * maxSim;

        if (mmr > bestScore) {
          bestScore = mmr;
          bestIdx = i;
        }
      }

      selected.push(remaining[bestIdx]);
      remaining.splice(bestIdx, 1);
    }

    return selected;
  }
}
```

### 4.3 특화 검색 유형
```typescript
class SpecializedRetriever extends RAGRetriever {
  // 의견/관점 검색 - 특정 주제에 대한 과거 의견
  async retrieveOpinions(
    topic: string,
    channelId: string
  ): Promise<ContentChunk[]> {
    return this.retrieve(topic, channelId, {
      ...defaultRetrievalConfig,
      filters: {
        characteristicFilters: {
          requireOpinion: true,
        },
      },
    });
  }

  // 예시 검색 - 유사한 예시/비유
  async retrieveExamples(
    topic: string,
    channelId: string
  ): Promise<ContentChunk[]> {
    return this.retrieve(topic, channelId, {
      ...defaultRetrievalConfig,
      filters: {
        characteristicFilters: {
          requireExample: true,
        },
      },
    });
  }

  // 고성과 콘텐츠 검색
  async retrieveHighPerformers(
    topic: string,
    channelId: string
  ): Promise<ContentChunk[]> {
    return this.retrieve(topic, channelId, {
      ...defaultRetrievalConfig,
      filters: {
        minPerformance: 0.7,  // 상위 30%
      },
    });
  }

  // 훅 검색 - 좋은 도입부
  async retrieveHooks(
    topic: string,
    channelId: string
  ): Promise<ContentChunk[]> {
    const results = await this.retrieve(topic, channelId, {
      ...defaultRetrievalConfig,
      filters: {
        minPerformance: 0.5,
      },
    });

    // Hook 위치 청크만 필터
    return results.filter(r => r.context.position === 'hook');
  }
}
```

---

## 5. 스크립트 생성

### 5.1 컨텍스트 구성
```typescript
interface GenerationContext {
  // 주제
  topic: {
    title: string;
    summary: string;
    keywords: string[];
    categories: string[];
    source?: string;
    series?: {
      id: string;
      name: string;
      previousEpisodes: number;
    };
  };

  // 검색된 관련 콘텐츠
  retrieved: {
    similar: ContentChunk[];       // 유사 주제 콘텐츠
    opinions: ContentChunk[];      // 관련 의견
    examples: ContentChunk[];      // 관련 예시
    hooks: ContentChunk[];         // 좋은 훅 예시
  };

  // 페르소나
  persona: Persona;

  // 생성 설정
  config: {
    format: 'shorts' | 'long';
    targetDuration: number;        // 초
    style: 'informative' | 'opinion' | 'reaction' | 'tutorial';
    mustInclude?: string[];
    mustAvoid?: string[];
  };
}

class ContextBuilder {
  constructor(
    private retriever: SpecializedRetriever,
    private personaManager: PersonaManager,
  ) {}

  async build(
    topic: NormalizedTopic,
    channelId: string,
    config: GenerationConfig
  ): Promise<GenerationContext> {
    const persona = await this.personaManager.get(channelId);

    // 병렬로 다양한 타입의 콘텐츠 검색
    const [similar, opinions, examples, hooks] = await Promise.all([
      this.retriever.retrieve(topic.title.normalized, channelId),
      this.retriever.retrieveOpinions(topic.title.normalized, channelId),
      this.retriever.retrieveExamples(topic.title.normalized, channelId),
      this.retriever.retrieveHooks(topic.title.normalized, channelId),
    ]);

    return {
      topic: {
        title: topic.title.normalized,
        summary: topic.summary,
        keywords: topic.classification.keywords,
        categories: topic.classification.categories,
        source: topic.source.name,
        series: topic.series,
      },
      retrieved: {
        similar,
        opinions,
        examples,
        hooks,
      },
      persona,
      config,
    };
  }
}
```

### 5.2 프롬프트 템플릿
```typescript
class PromptBuilder {
  build(context: GenerationContext): string {
    return `# 역할
당신은 "${context.persona.identity.name}" 채널입니다.
${context.persona.identity.description}

# 채널 특성
- 전문 분야: ${context.persona.identity.expertise.join(', ')}
- 말투: ${context.persona.communication.tone}, ${context.persona.communication.formality}
- 핵심 가치: ${context.persona.perspective.coreValues.join(', ')}

# 말투 규칙
- 문장 끝: ${context.persona.communication.speechPatterns.sentenceEndings.join(', ')}
- 연결어: ${context.persona.communication.speechPatterns.connectors.join(', ')}
- 강조 표현: ${context.persona.communication.speechPatterns.emphasisWords.join(', ')}
- 절대 쓰지 말 것: ${context.persona.communication.avoidPatterns.words.join(', ')}
- 피할 스타일: ${context.persona.communication.avoidPatterns.styles.join(', ')}

# 관점
${context.persona.perspective.biases.map(b => `- ${b}`).join('\n')}
${context.persona.perspective.contrarian ?
  `\n# 주류와 다른 시각\n${context.persona.perspective.contrarian.map(c => `- ${c}`).join('\n')}` : ''}

# 과거에 비슷한 주제로 작성한 콘텐츠
${context.retrieved.similar.map((chunk, i) => `
## 예시 ${i + 1}
${chunk.text}
`).join('\n')}

${context.retrieved.opinions.length > 0 ? `
# 이 주제에 대한 채널의 기존 관점
${context.retrieved.opinions.map(chunk => chunk.text).join('\n\n')}
` : ''}

${context.retrieved.hooks.length > 0 ? `
# 참고할 훅 스타일
${context.retrieved.hooks.map(chunk => chunk.text).join('\n---\n')}
` : ''}

# 오늘의 주제
제목: ${context.topic.title}
요약: ${context.topic.summary}
키워드: ${context.topic.keywords.join(', ')}
${context.topic.source ? `출처: ${context.topic.source}` : ''}
${context.topic.series ? `
# 시리즈 정보
이 콘텐츠는 "${context.topic.series.name}" 시리즈의 ${context.topic.series.previousEpisodes + 1}번째 에피소드입니다.
이전 에피소드들의 톤을 유지하세요.
` : ''}

# 작성 요청
위 주제에 대해 ${context.config.format === 'shorts' ? 'YouTube Shorts (60초 이내)' : 'YouTube 영상'} 스크립트를 작성해주세요.

## 요구사항
- 목표 길이: 약 ${context.config.targetDuration}초 분량
- 스타일: ${context.config.style}
- 과거 콘텐츠의 톤앤매너를 반드시 유지
- 당신만의 관점과 의견을 녹여내기
- 뻔한 정보 나열 금지, 인사이트 제공
${context.config.mustInclude ? `- 반드시 언급: ${context.config.mustInclude.join(', ')}` : ''}
${context.config.mustAvoid ? `- 피해야 할 것: ${context.config.mustAvoid.join(', ')}` : ''}

## 구조
1. 훅 (${context.persona.communication.structurePreference.hookStyle} 스타일, 3초 내 시선 잡기)
2. 본론 (핵심 내용 + 당신의 관점)
3. 마무리 (짧은 요약 또는 생각할 거리)

## 주의
- "안녕하세요" 등 뻔한 인사 금지
- CTA(구독, 좋아요 요청) ${context.persona.communication.structurePreference.ctaStyle === 'none' ? '넣지 말 것' : '최소화'}
- 과장된 표현 금지
- 정보 나열 금지, 자연스러운 흐름으로

---

# 스크립트`;
  }
}
```

### 5.3 생성 파이프라인
```typescript
interface GeneratedScript {
  id: string;
  channelId: string;
  topicId: string;

  // 스크립트
  script: string;

  // 메타
  metadata: {
    generatedAt: Date;
    model: string;
    contextChunksUsed: number;
    estimatedDuration: number;
    version: number;
  };

  // 품질 체크 결과
  qualityCheck: {
    styleScore: number;            // 스타일 일관성 (0-1)
    avoidWordsFound: string[];     // 발견된 금지어
    hookScore: number;             // 훅 품질 (0-1)
    passed: boolean;
  };

  // 상태
  status: 'generated' | 'reviewed' | 'approved' | 'rejected';
}

class ScriptGenerator {
  async generate(
    topic: NormalizedTopic,
    channelId: string,
    config: GenerationConfig
  ): Promise<GeneratedScript> {
    // 1. 컨텍스트 구성
    const context = await this.contextBuilder.build(topic, channelId, config);

    // 2. 프롬프트 빌딩
    const prompt = this.promptBuilder.build(context);

    // 3. LLM 생성
    const rawScript = await this.llm.complete({
      model: 'claude-3-5-sonnet',
      messages: [{ role: 'user', content: prompt }],
      temperature: 0.7,
      maxTokens: 2000,
    });

    // 4. 후처리 및 품질 체크
    const { script, qualityCheck } = await this.postProcess(rawScript, context.persona);

    // 5. 품질 미달 시 재생성 (최대 2회)
    if (!qualityCheck.passed) {
      return this.regenerate(topic, channelId, config, qualityCheck);
    }

    return {
      id: generateUUID(),
      channelId,
      topicId: topic.id,
      script,
      metadata: {
        generatedAt: new Date(),
        model: 'claude-3-5-sonnet',
        contextChunksUsed: this.countChunks(context.retrieved),
        estimatedDuration: this.estimateDuration(script),
        version: 1,
      },
      qualityCheck,
      status: 'generated',
    };
  }

  private async postProcess(
    rawScript: string,
    persona: Persona
  ): Promise<{ script: string; qualityCheck: QualityCheck }> {
    let script = rawScript;

    // 1. 금지어 체크
    const avoidWordsFound = this.findAvoidWords(script, persona);

    // 2. 금지어 대체
    if (avoidWordsFound.length > 0) {
      script = await this.replaceAvoidWords(script, avoidWordsFound, persona);
    }

    // 3. 스타일 점수 계산
    const styleScore = await this.calculateStyleScore(script, persona);

    // 4. 훅 품질 평가
    const hookScore = await this.evaluateHook(script);

    // 5. 길이 조정
    const duration = this.estimateDuration(script);
    if (duration > 65) {  // Shorts 제한
      script = await this.trimScript(script, 55);
    }

    const passed = styleScore >= 0.7 && hookScore >= 0.5 && avoidWordsFound.length <= 2;

    return {
      script,
      qualityCheck: {
        styleScore,
        avoidWordsFound,
        hookScore,
        passed,
      },
    };
  }
}
```

---

## 6. 파인튜닝 데이터 수집

### 6.1 데이터 수집 기준
```typescript
interface FineTuningCriteria {
  // 성과 기준
  performance: {
    minViews: number;
    minEngagementRate: number;
    minWatchTimeRatio: number;       // 평균 시청 비율
  };

  // 품질 기준
  quality: {
    minStyleScore: number;
    noAvoidWords: boolean;
    manuallyApproved: boolean;
  };
}

const defaultCriteria: FineTuningCriteria = {
  performance: {
    minViews: 1000,
    minEngagementRate: 0.05,         // 5%
    minWatchTimeRatio: 0.6,          // 60%
  },
  quality: {
    minStyleScore: 0.8,
    noAvoidWords: true,
    manuallyApproved: true,          // 검수 통과 필수
  },
};
```

### 6.2 데이터셋 구조
```typescript
interface FineTuningExample {
  // 입력
  input: {
    topic: string;
    keywords: string[];
    category: string;
    context?: string;                // 관련 정보 (선택)
  };

  // 출력
  output: {
    script: string;
  };

  // 메타
  metadata: {
    channelId: string;
    source: 'approved' | 'high_performer' | 'manual';
    performance?: {
      views: number;
      engagementRate: number;
    };
    collectedAt: Date;
  };
}

// 파인튜닝 포맷 (Chat 형식)
interface ChatFineTuningFormat {
  messages: [
    { role: 'system'; content: string },   // 페르소나 요약
    { role: 'user'; content: string },     // 주제 + 요청
    { role: 'assistant'; content: string } // 스크립트
  ];
}
```

### 6.3 데이터 수집 파이프라인
```typescript
class FineTuningDataCollector {
  async collectFromHighPerformers(
    channelId: string,
    criteria: FineTuningCriteria
  ): Promise<FineTuningExample[]> {
    // 1. 고성과 콘텐츠 조회
    const highPerformers = await this.db.scripts.find({
      channelId,
      'performance.views': { $gte: criteria.performance.minViews },
      'performance.engagementRate': { $gte: criteria.performance.minEngagementRate },
      'qualityCheck.styleScore': { $gte: criteria.quality.minStyleScore },
      status: 'published',
    });

    // 2. 파인튜닝 데이터로 변환
    return highPerformers.map(script => ({
      input: {
        topic: script.topic.title,
        keywords: script.topic.keywords,
        category: script.topic.categories[0],
      },
      output: {
        script: script.script,
      },
      metadata: {
        channelId,
        source: 'high_performer',
        performance: script.performance,
        collectedAt: new Date(),
      },
    }));
  }

  // 파인튜닝 포맷으로 변환
  toFineTuningFormat(
    examples: FineTuningExample[],
    persona: Persona
  ): ChatFineTuningFormat[] {
    const systemPrompt = this.createSystemPrompt(persona);

    return examples.map(ex => ({
      messages: [
        { role: 'system', content: systemPrompt },
        {
          role: 'user',
          content: `주제: ${ex.input.topic}\n키워드: ${ex.input.keywords.join(', ')}\n\n위 주제에 대한 스크립트를 작성해주세요.`
        },
        { role: 'assistant', content: ex.output.script },
      ],
    }));
  }
}
```

---

## 7. 기술 스택 정리

| 컴포넌트 | 선택 | 비고 |
|----------|------|------|
| **임베딩** | BGE-M3 | 다국어, 한국어 성능 우수, 1024차원 |
| **벡터 DB** | pgvector (PostgreSQL extension) | 단일 DB, HNSW 인덱스 (m=16, ef_construction=64), 운영 간편 |
| **키워드 검색** | PostgreSQL Full-Text Search | 벡터 검색과 통합 쿼리 가능 |
| **리랭커** | BGE-Reranker | 오픈소스, 성능 좋음 |
| **콘텐츠 분류** | 패턴 기반 + LLM (선택) | 빠른 패턴 매칭, 필요시 Claude Haiku로 정확도 향상 |
| **LLM (생성)** | Claude 3.5 Sonnet | 긴 컨텍스트, 한국어 품질 |
| **LLM (분류)** | Claude 3.5 Haiku | 빠르고 저렴, 간단한 분류 태스크 |
| **LLM (파인튜닝)** | Llama 3 + LoRA | 비용 효율 |
| **TTS** | Edge TTS (기본) → ElevenLabs (업그레이드) | 비용 단계적 |

---

## 8. 구현 상세

### 8.1 실제 구현된 모델

**Database Models (PostgreSQL + pgvector)**:
- `scripts`: 생성된 스크립트 저장
  - hook, body, conclusion 섹션 분리 저장
  - quality_passed, style_score, hook_score 등 품질 메트릭
  - generation_metadata: 생성 설정 JSON
  - status: GENERATED, REVIEWED, APPROVED, REJECTED, PRODUCED

- `content_chunks`: 벡터 검색용 청크
  - embedding: Vector(1024) - BGE-M3 임베딩
  - is_opinion, is_example, is_analogy: 콘텐츠 특성 (패턴 또는 LLM 분류)
  - position: HOOK, BODY, CONCLUSION
  - keywords: 키워드 배열
  - performance_score: 성과 피드백
  - HNSW 인덱스: `CREATE INDEX USING hnsw (embedding vector_cosine_ops)`

**RAG Services (app/services/rag/)**:
1. **ContentEmbedder**: BGE-M3 임베딩 생성
   - 메타데이터 태그 추가 (위치, 특성, 키워드)
   - 배치 처리 지원

2. **RAGRetriever / SpecializedRetriever**: 하이브리드 검색
   - 70% 시맨틱 (벡터) + 30% BM25 (키워드)
   - 쿼리 확장 (Claude API)
   - 특화 검색: 의견, 예시, 훅, 고성과 콘텐츠

3. **RAGReranker**: 재순위화
   - BGE-Reranker로 정밀도 향상
   - MMR (λ=0.7)로 다양성 확보

4. **ContentClassifier**: LLM 기반 분류 (선택)
   - Claude Haiku 사용
   - 의견/예시/비유 자동 탐지
   - 패턴 매칭 실패 시 사용

5. **ScriptChunker**: 구조 기반 청킹
   - Hook/Body/Conclusion 자동 분리
   - 설정 가능한 패턴 (한국어 + English)
   - 선택적 LLM 분류 지원

6. **ContextBuilder**: 생성 컨텍스트 구성
   - 병렬 검색 (유사 콘텐츠, 의견, 예시, 훅)
   - Persona 통합

7. **PromptBuilder**: 프롬프트 템플릿
   - Persona 정보 + 검색 결과 + 주제

8. **ScriptGenerator**: 전체 파이프라인 통합
   - Context → Prompt → LLM → Quality Check
   - 품질 게이트: style_score ≥ 0.7, hook_score ≥ 0.5
   - 실패 시 자동 재시도 (최대 2회)
   - 스크립트 저장 → 청킹 → 임베딩 → 벡터 DB 저장
   - **Scene 기반 스크립트 생성** (`generate_scene_script()` 메서드)

### 8.3 Scene 기반 스크립트 생성 (BSForge 핵심 차별점)

BSForge의 핵심 차별점은 **AI 페르소나가 사실(Fact)과 의견(Opinion)을 명확히 구분하여 표현**하는 것입니다.
이를 위해 Scene 기반 스크립트 구조를 사용합니다.

**Scene 타입 (8가지)**:
```python
class SceneType(str, Enum):
    # 정보 전달 (Factual)
    HOOK = "hook"              # 0-3초, 주의 끌기
    INTRO = "intro"            # 3-5초, 맥락 설정
    CONTENT = "content"        # 5-10초, 핵심 정보
    EXAMPLE = "example"        # 3-5초, 구체적 예시

    # 페르소나 의견 (Commentary) ← BSForge 핵심
    COMMENTARY = "commentary"  # 3-8초, 페르소나 생각/해석/의견
    REACTION = "reaction"      # 2-4초, 짧은 리액션

    # 마무리
    CONCLUSION = "conclusion"  # 2-4초, 요약
    CTA = "cta"               # 2-3초, 행동 유도 (선택적)
```

**Scene 기반 스크립트 생성 흐름**:
```
주제 + 페르소나
    ↓
LLM이 Scene 단위로 스크립트 생성
    ↓
각 Scene에 scene_type 태그 부여
    ↓
COMMENTARY/REACTION Scene에 자동으로 VisualStyle.PERSONA 적용
    ↓
Scene 간 트랜지션 자동 추천 (Fact→Opinion: FLASH)
```

**SceneScript 모델**:
```python
class SceneScript(BaseModel):
    scenes: list[Scene]           # 장면 목록
    title_text: str | None        # 썸네일/오버레이용 제목
    headline_keyword: str | None  # 2줄 헤드라인 (키워드)
    headline_hook: str | None     # 2줄 헤드라인 (훅)

    def validate_structure(self) -> list[str]:
        """스크립트 구조 검증 (HOOK 시작, 길이 체크, COMMENTARY 권장)"""

    def apply_recommended_transitions(self) -> None:
        """자동 트랜지션 적용 (Fact→Opinion: FLASH 등)"""
```

**Scene 모델**:
```python
class Scene(BaseModel):
    scene_type: SceneType          # 장면 유형
    text: str                      # 자막 텍스트
    tts_text: str | None           # TTS 발음 (다를 경우만)
    keyword: str | None            # 비주얼 검색 키워드
    visual_hint: VisualHintType    # 비주얼 소싱 힌트
    visual_style: VisualStyle | None  # 시각 스타일 (자동 추론)
    transition_in: TransitionType  # 진입 전환
    emphasis_words: list[str]      # 강조 단어

    @property
    def is_persona_scene(self) -> bool:
        """COMMENTARY 또는 REACTION인지 확인"""
        return self.scene_type in (SceneType.COMMENTARY, SceneType.REACTION)
```

**Configuration (app/config/rag.py)**:
- ChunkingConfig: 패턴 리스트 (opinion/example/analogy), LLM 토글
- RetrievalConfig: 하이브리드 가중치, MMR λ, 리랭킹 설정
- GenerationConfig: LLM 설정, 스타일, 길이
- QualityCheckConfig: 품질 게이트 기준

### 8.2 확장성 설계

**다국어 지원**:
- 패턴 기반 분류: ChunkingConfig에 언어별 패턴 추가
  ```python
  opinion_patterns = [
    r"i think", r"i believe",  # English
    r"제 생각", r"생각하는",     # Korean
    r"思います", r"考えます",     # Japanese (예시)
  ]
  ```

**분류 정확도 조정**:
- 빠른 환경: `use_llm_classification=False` (패턴만)
- 정확한 환경: `use_llm_classification=True` (LLM 분류)

**성능 최적화**:
- HNSW 인덱스로 1000배 빠른 벡터 검색
- 배치 임베딩으로 처리량 향상
- 병렬 검색으로 레이턴시 감소
