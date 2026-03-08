# ChatGPT Bridge - 知识图谱架构 v4.0

**版本**: v4.0  
**日期**: 2026-03-07  
**状态**: 详细设计完成，分Session实施就绪  
**核心理念**: Graph-Based Knowledge + Heterogeneous Cognition Pipeline + Dependency DAG

---

## 📖 文档说明

本文档是 ChatGPT Bridge 委员会治理架构的**最终完整版**，整合了从v1.0到v3.0的所有设计演进，并基于最新反馈重构为**Graph-Based架构**。

**演进路径**:
- v1.0: 政治委员会隐喻（已废弃）
- v2.0: 治理宪法与风险分级（核心思想保留）
- v3.0: 异构认知管线（核心思想保留）
- **v4.0: Graph-Based + Algorithmic Synthesis + Dependency DAG（当前）**

---

## 1. 架构总览

### 1.1 核心架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Heterogeneous Cognition Pipeline                      │
│  ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐   │
│  │  Divergent Model │      │ Convergent Model │      │  Rule-Based      │   │
│  │   (Generator)    │ ───▶ │   (Validator)    │ ───▶ │     Merger       │   │
│  │  High Recall     │      │  High Precision  │      │ (Deterministic)  │   │
│  └──────────────────┘      └──────────────────┘      └──────────────────┘   │
│           │                         │                         │              │
│           ▼                         ▼                         ▼              │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                    Divergence Metadata + Structured Patches           │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Knowledge Graph Core (Layer 1)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                      │
│  │     Node     │  │     Edge     │  │   Evidence   │                      │
│  │  (Knowledge) │  │  (Relation)  │  │   (Source)   │                      │
│  └──────────────┘  └──────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Concept Synthesis Pipeline (Layer 2-4)                    │
│                                                                             │
│   L1 Chunks ──▶ L2 Concepts ──▶ L3 Domains ──▶ L4 Index                    │
│      │              │               │               │                       │
│      ▼              ▼               ▼               ▼                       │
│   ┌────────┐   ┌────────┐    ┌────────┐    ┌────────┐                      │
│   │HDBSCAN │   │Louvain │    │Summary │    │Centrality│                     │
│   │Cluster │   │Community│   │Generation│  │Ranking   │                     │
│   └────────┘   └────────┘    └────────┘    └────────┘                      │
│                                                                             │
│   Algorithmic Synthesis (NOT LLM heuristic)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Knowledge Dependency DAG                                 │
│                                                                             │
│   Fact Node ──depends_on──▶ Evidence                                       │
│       │                                                                     │
│       ├─derived_from──▶ Concept Node ──aggregates──▶ Domain Node           │
│       │                              │                                      │
│       │                              └─indexes──▶ Index Node               │
│       │                                                                     │
│   [Change Propagation: Stale Detection → Topological Rebuild]              │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 架构组件清单

| 组件 | 职责 | 实现技术 |
|------|------|----------|
| **Divergent Model** | 生成概念候选、高召回 | Claude-3.5-Sonnet / Kimi |
| **Convergent Model** | 边界校验、高精度 | GPT-4 / Opencode |
| **Rule Merger** | 确定性合并、去重 | Python Rule Engine |
| **Knowledge Graph** | 节点、边、证据存储 | PostgreSQL + pgvector |
| **Synthesis Pipeline** | L1→L2→L3→L4转换 | HDBSCAN + Louvain + Centrality |
| **Dependency DAG** | 依赖追踪、级联重建 | Graph Topology + Event System |
| **Divergence Metadata** | 保存认知分歧 | JSONB in PostgreSQL |

---

## 2. Graph-Based Core Model

### 2.1 核心实体

#### Node (知识节点)

```python
class KnowledgeNode(BaseModel):
    """
    知识图谱的核心节点
    取代v3的KnowledgeObject，从文档思维转为图思维
    """
    
    # 基础标识
    id: UUID
    type: NodeType  # fact | concept | domain | index
    
    # 层级位置
    layer: int  # 1 | 2 | 3 | 4
    
    # 内容（类型特定）
    content: NodeContent
    
    # 向量表示
    embedding: Vector  # 用于语义相似度和聚类
    
    # 证据引用（指向Evidence节点）
    evidence_refs: List[UUID]
    
    # 时间语义
    temporal: TemporalMetadata
    
    # 质量指标
    confidence: float  # 0-1
    consensus_score: float  # 0-1，多模型共识度
    
    # 状态
    status: NodeStatus  # active | stale | deprecated
    
    # 生成谱系
    created_by: str  # model_id or agent_id
    created_at: datetime
    updated_at: Optional[datetime]
    
    # 分歧元数据（关键创新）
    divergence: DivergenceMetadata
    
    # 图关系（通过Edge表显式存储）
    # 不在这里存，保持图的标准形式


class NodeType(str, Enum):
    """节点类型 = 知识层级"""
    FACT = "fact"       # L1: 原子事实
    CONCEPT = "concept" # L2: 概念节点
    DOMAIN = "domain"   # L3: 领域聚合
    INDEX = "index"     # L4: 顶层索引


class NodeContent(BaseModel):
    """
    节点内容（根据类型不同）
    使用Union类型支持不同类型
    """
    type: NodeType
    
    # Fact节点内容
    fact_statement: Optional[str]  # 事实陈述
    fact_value: Optional[Any]      # 结构化值
    
    # Concept节点内容
    concept_name: Optional[str]
    concept_definition: Optional[str]
    concept_examples: Optional[List[str]]
    
    # Domain节点内容
    domain_name: Optional[str]
    domain_summary: Optional[str]
    domain_coverage: Optional[float]  # 覆盖率
    
    # Index节点内容
    index_name: Optional[str]
    index_structure: Optional[Dict]  # 导航结构
    index_entries: Optional[List[IndexEntry]]
```

#### Edge (关系边)

```python
class KnowledgeEdge(BaseModel):
    """
    知识节点之间的关系
    显式存储所有关系，支持图遍历
    """
    
    id: UUID
    
    # 端点
    source: UUID  # 源节点ID
    target: UUID  # 目标节点ID
    
    # 关系类型
    type: EdgeType
    
    # 关系强度
    weight: float  # 0-1
    
    # 关系属性
    properties: Dict[str, Any]  # 类型特定属性
    
    # 时间
    created_at: datetime
    valid_until: Optional[datetime]  # 关系过期时间
    
    # 证据
    evidence_refs: List[UUID]


class EdgeType(str, Enum):
    """边类型 = 知识关系语义"""
    # 层级关系
    DERIVED_FROM = "derived_from"      # L2→L1: 概念来源于事实
    AGGREGATES = "aggregates"          # L3→L2: 领域聚合概念
    INDEXES = "indexes"                # L4→L3: 索引指向领域
    
    # 依赖关系（用于DAG）
    DEPENDS_ON = "depends_on"          # 节点依赖（变更传播）
    SUPPORTS = "supports"              # 证据支持
    CONTRADICTS = "contradicts"        # 矛盾关系
    
    # 语义关系
    PART_OF = "part_of"                # 部分-整体
    RELATED_TO = "related_to"          # 相关
    SUPERSEDES = "supersedes"          # 替代（时间）
    SIMILAR_TO = "similar_to"          # 相似
    
    # 推理关系
    IMPLIES = "implies"                # 蕴含
    ENABLES = "enables"                # 使能
```

#### Evidence (证据)

```python
class Evidence(BaseModel):
    """
    证据节点
    支持知识节点的可信度
    """
    
    id: UUID
    
    # 来源类型
    source_type: EvidenceSourceType
    
    # 来源详情
    source_name: str  # 来源名称（如"Python官方文档"）
    source_url: Optional[str]
    source_timestamp: datetime  # 来源时间
    
    # 证据内容
    content: str  # 引用的具体文本/数据
    context: Optional[str]  # 上下文
    
    # 提取信息
    extracted_by: str  # 提取者（模型ID）
    extracted_at: datetime
    
    # 可信度
    confidence: float  # 0-1
    credibility_score: float  # 来源可信度
    
    # 验证状态
    verification_status: VerificationStatus
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    
    # 关联节点
    supports_nodes: List[UUID]  # 支持哪些节点


class EvidenceSourceType(str, Enum):
    """证据来源类型"""
    WEB = "web"                # 网络搜索
    DOCUMENT = "document"      # 文档
    EXPERIMENT = "experiment"  # 实验数据
    EXPERT = "expert"          # 专家意见
    INFERENCE = "inference"    # 推理得出
    OBSERVATION = "observation" # 观察记录
```

### 2.2 图结构示例

```
Knowledge Graph实例:

[Evidence: E1] ──supports──▶ [Fact: F1] ──derived_from──▶ [Concept: C1]
     │                            │                            │
     │                            │                            │
   source:                    confidence:                   confidence:
   Python Docs                0.95                         0.85
   (credibility: 0.9)                                      │
                                                             │
                                                             │part_of
                                                             ▼
                                                [Domain: D1] ◀──aggregates── [Concept: C2]
                                                     │
                                                     │indexes
                                                     ▼
                                                [Index: I1]

依赖关系（DAG）:

F1 ──depends_on──▶ E1
C1 ──depends_on──▶ F1
D1 ──depends_on──▶ C1
D1 ──depends_on──▶ C2
I1 ──depends_on──▶ D1
```

### 2.3 存储方案

```sql
-- PostgreSQL + pgvector Schema

-- 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Node表（核心）
CREATE TABLE knowledge_nodes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    type VARCHAR(20) NOT NULL CHECK (type IN ('fact', 'concept', 'domain', 'index')),
    layer INTEGER NOT NULL CHECK (layer IN (1, 2, 3, 4)),
    
    -- 内容（JSONB存储不同类型）
    content JSONB NOT NULL,
    
    -- 向量（用于语义搜索和聚类）
    embedding VECTOR(1536),  -- OpenAI embedding维度
    
    -- 证据引用
    evidence_refs UUID[],
    
    -- 时间语义
    valid_from TIMESTAMP,
    valid_until TIMESTAMP,
    source_timestamp TIMESTAMP NOT NULL,
    
    -- 质量指标
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    consensus_score FLOAT CHECK (consensus_score >= 0 AND consensus_score <= 1),
    
    -- 状态
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'stale', 'deprecated')),
    
    -- 生成谱系
    created_by VARCHAR(100) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP,
    
    -- 分歧元数据
    divergence JSONB,
    
    -- 索引
    CONSTRAINT valid_dates CHECK (valid_until IS NULL OR valid_until > valid_from)
);

-- Edge表（图关系）
CREATE TABLE knowledge_edges (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    target UUID NOT NULL REFERENCES knowledge_nodes(id) ON DELETE CASCADE,
    type VARCHAR(30) NOT NULL,
    weight FLOAT CHECK (weight >= 0 AND weight <= 1),
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    valid_until TIMESTAMP,
    evidence_refs UUID[]
);

-- Evidence表
CREATE TABLE evidence (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_type VARCHAR(20) NOT NULL,
    source_name TEXT NOT NULL,
    source_url TEXT,
    source_timestamp TIMESTAMP NOT NULL,
    content TEXT NOT NULL,
    context TEXT,
    extracted_by VARCHAR(100) NOT NULL,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
    credibility_score FLOAT CHECK (credibility_score >= 0 AND credibility_score <= 1),
    verification_status VARCHAR(20) DEFAULT 'unverified',
    verified_by VARCHAR(100),
    verified_at TIMESTAMP,
    supports_nodes UUID[]
);

-- 图遍历优化索引
CREATE INDEX idx_nodes_type ON knowledge_nodes(type);
CREATE INDEX idx_nodes_layer ON knowledge_nodes(layer);
CREATE INDEX idx_nodes_status ON knowledge_nodes(status);
CREATE INDEX idx_nodes_embedding ON knowledge_nodes USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX idx_edges_source ON knowledge_edges(source);
CREATE INDEX idx_edges_target ON knowledge_edges(target);
CREATE INDEX idx_edges_type ON knowledge_edges(type);

-- 复合索引用于快速依赖查询
CREATE INDEX idx_edges_dependency ON knowledge_edges(source, type) WHERE type = 'depends_on';

-- GIN索引用于JSONB查询
CREATE INDEX idx_nodes_content ON knowledge_nodes USING GIN (content);
CREATE INDEX idx_nodes_divergence ON knowledge_nodes USING GIN (divergence);
```

---

## 3. Heterogeneous Cognition Pipeline

### 3.1 双模型分工（继承v3）

```
┌─────────────────────────────────────────────────────────────┐
│                 Divergent Model (Generator)                 │
├─────────────────────────────────────────────────────────────┤
│ 职责: 高召回，尽可能多地发现概念和关系                       │
│ 模型: Claude-3.5-Sonnet / Kimi-v2.5                        │
│ 特点: 归纳偏好强，善于发现模式                             │
│                                                             │
│ 输出:                                                       │
│   - Concept Candidates (概念候选)                          │
│   - Relation Candidates (关系候选)                         │
│   - View Candidates (视图候选)                             │
│   - Evidence Candidates (证据候选)                         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                Convergent Model (Validator)                 │
├─────────────────────────────────────────────────────────────┤
│ 职责: 高精度，验证边界和一致性                             │
│ 模型: GPT-4 / Opencode                                      │
│ 特点: 表达惯性严谨，善于挑错                               │
│                                                             │
│ 输出:                                                       │
│   - Boundary Objections (边界异议)                         │
│   - Naming Alternatives (命名备选)                         │
│   - Conflict Notes (冲突标记)                              │
│   - Duplication Detection (重复检测)                       │
│   - Abstraction Risk (抽象风险评估)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│              Rule-Based Merger (Deterministic)              │
├─────────────────────────────────────────────────────────────┤
│ 职责: 确定性合并，无LLM参与                                │
│ 实现: Python Rule Engine                                    │
│ 特点: 幂等、可回滚、无副作用                               │
│                                                             │
│ 操作:                                                       │
│   - Deduplication (基于相似度阈值)                         │
│   - Naming Resolution (优先收敛模型建议)                   │
│   - Boundary Handling (按严重程度处理)                     │
│   - Consensus Calculation (计算共识度)                     │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 输出协议（详细）

#### Divergent Model 输出格式

```yaml
# divergence_output.yaml
pipeline_stage: "l1_to_l2"  # 或 l2_to_l3, l3_to_l4
input_summary:
  source_count: 15
  source_type: "chunks"
  
model_info:
  model_id: "claude-3-5-sonnet-20241022"
  role: "generator"
  
concept_candidates:
  - candidate_id: "cc-001"
    proposed_name: "Python异步编程模式"
    alternative_names: ["asyncio设计模式", "Python协程实践"]
    description: "使用asyncio进行并发编程的常见模式"
    
    # 来源追踪
    source_chunks: ["chunk-uuid-1", "chunk-uuid-5", "chunk-uuid-12"]
    source_quotes: [
      "在对话A中提到asyncio.gather的使用场景...",
      "对话B讨论了TaskGroup的优势..."
    ]
    
    # 证据
    evidence_refs: ["evidence-uuid-1", "evidence-uuid-2"]
    
    # 置信度
    confidence: 0.85
    confidence_reasoning: "多个独立来源支持，且有时效性证据"
    
    # 关联建议
    suggested_relations:
      - target: "cc-003"
        type: "part_of"
        strength: 0.8
      - target: "cc-007"
        type: "related_to"
        strength: 0.6
    
    # 不确定性
    uncertainty_areas:
      - "与多线程的精确边界"
      - "性能基准测试数据"
    
  - candidate_id: "cc-002"
    # ... 更多候选

relation_candidates:
  - source: "cc-001"
    target: "cc-003"
    type: "implements"
    strength: 0.75
    evidence: "..."

view_candidates:
  - view_id: "view-001"
    name: "按使用场景分类"
    structure:
      - node: "cc-001"
        children: ["cc-004", "cc-005"]
      - node: "cc-002"
        children: ["cc-006"]
    rationale: "便于开发者根据场景快速查找"

evidence_candidates:
  - evidence_id: "ev-001"
    source_type: "web"
    source_name: "Python官方文档"
    source_url: "https://docs.python.org/3/library/asyncio.html"
    relevant_content: "asyncio is a library to write concurrent code..."
    timestamp: "2024-01-15"
    credibility: 0.95

metadata:
  processing_time_ms: 3500
  coverage_estimate: 0.88  # 估计召回率
  gaps_identified:
    - "缺少Python 3.10之前的兼容性信息"
    - "缺少与trio库的对比"
```

#### Convergent Model 输出格式

```yaml
# convergence_output.yaml
pipeline_stage: "l1_to_l2"
input: "divergence_output.yaml"

model_info:
  model_id: "gpt-4-turbo"
  role: "validator"

validation_summary:
  total_candidates: 12
  validated: 8
  rejected: 2
  needs_modification: 2

boundary_objections:
  - target_candidate: "cc-001"
    objection_type: "overly_broad"
    severity: "high"
    reasoning: |
      "Python异步编程模式"包含了asyncio、threading、
      multiprocessing三个不同层级的概念，应拆分为：
      - asyncio-specific patterns
      - general concurrency concepts
    suggested_split:
      - original: "cc-001"
        new_candidates: ["cc-001a", "cc-001b"]
        split_criteria: "by_implementation_mechanism"
    
  - target_candidate: "cc-003"
    objection_type: "mixed_abstraction_levels"
    severity: "medium"
    reasoning: "同时包含概念定义和实践指导，应分层"
    suggested_reorganization:
      conceptual_part: "cc-003-concept"
      practical_part: "cc-003-practice"

naming_alternatives:
  - original_name: "Python异步编程模式"
    alternatives:
      - name: "asyncio设计模式"
        appropriateness: 0.9
        reason: "更准确，避免与threading混淆"
      - name: "Python协程最佳实践"
        appropriateness: 0.75
        reason: "强调实践，但范围略窄"
    recommendation: "使用'asyncio设计模式'作为主名，保留其他作为别名"
    confidence: 0.85

conflict_notes:
  - between: ["cc-001", "cc-005"]
    conflict_type: "overlap"
    overlap_degree: 0.65
    shared_content: "都涉及asyncio.gather的使用"
    resolution_suggestion: 
      action: "merge"
      merged_name: "asyncio并发模式"
      primary_aspects: ["cc-001", "cc-005"]

duplication_detection:
  - candidates: ["cc-002", "cc-007"]
    similarity_score: 0.87
    judgment: "duplicate"
    recommendation: "保留cc-002（置信度更高），将cc-007合并"
    merge_strategy: "append_evidence"

abstraction_risks:
  - target: "cc-004"
    risk_level: "high"
    detail: |
      从仅有的2个具体例子归纳出通用模式，
      样本不足，可能存在过度概括。
    mitigation: "标记为'provisional'，收集更多证据"
    
evidence_gaps:
  - related_candidate: "cc-006"
    missing_evidence:
      - type: "benchmark_data"
        description: "缺少asyncio vs threading性能对比数据"
        priority: "medium"
      - type: "version_compatibility"
        description: "未说明Python版本要求"
        priority: "high"

metadata:
  validation_time_ms: 4200
  consensus_analysis:
    high_confidence_candidates: ["cc-001", "cc-003", "cc-008"]
    disputed_candidates: ["cc-002", "cc-004", "cc-006"]
    average_validation_score: 0.72
```

### 3.3 规则合并器（详细）

```python
# backend/src/knowledge/merger.py

class RuleBasedMerger:
    """
    基于规则的确定性合并器
    输入: 发散输出 + 收敛输出
    输出: 结构化知识图谱对象
    """
    
    def merge(
        self,
        divergence: DivergenceOutput,
        convergence: ConvergenceOutput
    ) -> KnowledgeGraphDelta:
        """
        合并双模型输出
        完全确定性，无LLM参与
        """
        delta = KnowledgeGraphDelta()
        
        # 1. 去重处理
        candidates = self._deduplicate(
            divergence.concept_candidates,
            convergence.duplication_detection
        )
        
        # 2. 处理边界异议
        candidates = self._handle_boundary_objections(
            candidates,
            convergence.boundary_objections
        )
        
        # 3. 应用命名修正
        candidates = self._apply_naming(
            candidates,
            convergence.naming_alternatives
        )
        
        # 4. 处理冲突
        candidates, relations = self._resolve_conflicts(
            candidates,
            divergence.relation_candidates,
            convergence.conflict_notes
        )
        
        # 5. 标记抽象风险
        candidates = self._mark_abstraction_risks(
            candidates,
            convergence.abstraction_risks
        )
        
        # 6. 计算共识度
        for candidate in candidates:
            candidate.consensus_score = self._calculate_consensus(
                candidate,
                divergence,
                convergence
            )
        
        # 7. 构建知识节点
        for candidate in candidates:
            node = self._build_node(candidate)
            delta.add_node(node)
        
        # 8. 构建关系边
        for rel in relations:
            edge = self._build_edge(rel)
            delta.add_edge(edge)
        
        # 9. 生成分歧元数据
        delta.divergence_metadata = self._build_divergence_metadata(
            divergence,
            convergence,
            candidates
        )
        
        return delta
    
    def _deduplicate(
        self,
        candidates: List[ConceptCandidate],
        duplicates: List[DuplicateDetection]
    ) -> List[ConceptCandidate]:
        """
        基于收敛模型的去重建议做去重
        规则：
        - similarity > 0.9: 合并
        - similarity 0.7-0.9: 添加交叉链接
        - similarity < 0.7: 保持独立
        """
        to_merge = {}  # id -> merge_target
        
        for dup in duplicates:
            if dup.similarity_score > 0.9:
                # 保留置信度更高的
                primary = max(dup.candidates, key=lambda c: c.confidence)
                for c in dup.candidates:
                    if c.id != primary.id:
                        to_merge[c.id] = primary.id
                        # 合并证据
                        primary.evidence_refs.extend(c.evidence_refs)
        
        # 过滤掉被合并的
        return [c for c in candidates if c.id not in to_merge]
    
    def _apply_naming(
        self,
        candidates: List[ConceptCandidate],
        naming_corrections: List[NamingAlternative]
    ) -> List[ConceptCandidate]:
        """
        应用命名修正
        规则：优先接受收敛模型的推荐
        """
        correction_map = {
            n.original_name: n.recommendation 
            for n in naming_corrections
        }
        
        for candidate in candidates:
            if candidate.proposed_name in correction_map:
                # 保存原名作为别名
                candidate.alternative_names.append(candidate.proposed_name)
                # 应用修正
                candidate.proposed_name = correction_map[candidate.proposed_name]
        
        return candidates
    
    def _calculate_consensus(
        self,
        candidate: ConceptCandidate,
        divergence: DivergenceOutput,
        convergence: ConvergenceOutput
    ) -> float:
        """
        计算共识度（0-1）
        基于：
        - 是否通过边界校验
        - 是否有命名争议
        - 是否有重复争议
        - 原始置信度
        """
        score = candidate.confidence * 0.4  # 基础置信度
        
        # 通过边界校验 +0.3
        boundary_passed = not any(
            obj.target_candidate == candidate.candidate_id 
            for obj in convergence.boundary_objections
        )
        if boundary_passed:
            score += 0.3
        
        # 无命名争议 +0.15
        naming_clean = not any(
            alt.original_name == candidate.proposed_name
            for alt in convergence.naming_alternatives
        )
        if naming_clean:
            score += 0.15
        
        # 无重复争议 +0.15
        duplicate_clean = not any(
            candidate.candidate_id in dup.candidates
            for dup in convergence.duplication_detection
        )
        if duplicate_clean:
            score += 0.15
        
        return min(score, 1.0)
```

---

## 4. Concept Synthesis Pipeline (Algorithmic)

### 4.1 核心原则

**算法合成，非LLM启发式**

L1→L2→L3→L4的转换使用明确的算法：
- **聚类**: HDBSCAN（密度聚类，自动发现簇数）
- **中心性**: Betweenness Centrality（找桥梁节点）
- **社区发现**: Louvain算法（模块度优化）
- **摘要生成**: 基于中心性的关键句提取（非LLM重写）

### 4.2 L1 → L2: Chunk → Concept

```python
# backend/src/synthesis/l1_to_l2.py

class L1ToL2Synthesizer:
    """
    L1 chunks → L2 concept nodes
    使用HDBSCAN聚类 + Betweenness Centrality
    """
    
    def synthesize(
        self,
        chunks: List[KnowledgeNode],  # L1 fact nodes
        min_cluster_size: int = 3
    ) -> List[KnowledgeNode]:  # L2 concept nodes
        """
        算法步骤：
        1. 提取所有chunk的embedding
        2. HDBSCAN聚类
        3. 每个cluster找中心节点
        4. 创建concept node
        """
        
        # 1. 准备数据
        embeddings = np.array([c.embedding for c in chunks])
        
        # 2. HDBSCAN聚类
        # 优势：自动确定簇数，能识别噪声点
        clusterer = hdbscan.HDBSCAN(
            min_cluster_size=min_cluster_size,
            metric='euclidean',
            cluster_selection_method='eom'  # Excess of Mass
        )
        labels = clusterer.fit_predict(embeddings)
        
        # 3. 为每个cluster创建concept
        concepts = []
        unique_labels = set(labels) - {-1}  # -1是噪声
        
        for label in unique_labels:
            cluster_mask = labels == label
            cluster_chunks = [c for i, c in enumerate(chunks) if cluster_mask[i]]
            cluster_embeddings = embeddings[cluster_mask]
            
            # 4. 找中心节点（Betweenness Centrality）
            # 构建临时图：chunk间的相似度
            similarity_matrix = cosine_similarity(cluster_embeddings)
            graph = nx.from_numpy_array(similarity_matrix > 0.8)
            
            # 计算中心性
            centrality = nx.betweenness_centrality(graph)
            center_idx = max(centrality.keys(), key=lambda k: centrality[k])
            center_chunk = cluster_chunks[center_idx]
            
            # 5. 创建concept node
            concept = KnowledgeNode(
                type=NodeType.CONCEPT,
                layer=2,
                content=ConceptContent(
                    concept_name=self._extract_name(center_chunk),
                    concept_definition=center_chunk.content[:500],
                    concept_examples=[c.content[:200] for c in cluster_chunks[:3]]
                ),
                embedding=np.mean(cluster_embeddings, axis=0),  # centroid
                evidence_refs=list(set(
                    ref for c in cluster_chunks for ref in c.evidence_refs
                )),
                confidence=self._calculate_cluster_cohesion(cluster_embeddings),
                source_chunks=[c.id for c in cluster_chunks]
            )
            
            concepts.append(concept)
        
        # 6. 处理噪声点（未聚类的chunks）
        noise_chunks = [c for i, c in enumerate(chunks) if labels[i] == -1]
        for chunk in noise_chunks:
            # 作为独立concept，标记为孤立
            concept = KnowledgeNode(
                type=NodeType.CONCEPT,
                layer=2,
                content=ConceptContent(
                    concept_name=self._extract_name(chunk),
                    concept_definition=chunk.content[:500],
                    concept_examples=[chunk.content[:200]]
                ),
                embedding=chunk.embedding,
                evidence_refs=chunk.evidence_refs,
                confidence=0.5,  # 较低置信度
                is_isolated=True  # 标记为孤立
            )
            concepts.append(concept)
        
        return concepts
    
    def _calculate_cluster_cohesion(self, embeddings: np.ndarray) -> float:
        """计算簇内聚度（0-1）"""
        centroid = np.mean(embeddings, axis=0)
        distances = [np.linalg.norm(e - centroid) for e in embeddings]
        avg_distance = np.mean(distances)
        # 转换为0-1分数（距离越小， cohesion越高）
        return max(0, 1 - avg_distance)
```

### 4.3 L2 → L3: Concept → Domain

```python
# backend/src/synthesis/l2_to_l3.py

class L2ToL3Synthesizer:
    """
    L2 concepts → L3 domain nodes
    使用Louvain社区发现 + 中心性摘要
    """
    
    def synthesize(
        self,
        concepts: List[KnowledgeNode],  # L2 concept nodes
        resolution: float = 1.0
    ) -> List[KnowledgeNode]:  # L3 domain nodes
        """
        算法步骤：
        1. 构建concept关系图
        2. Louvain社区发现
        3. 为每个社区创建domain
        4. 生成摘要（基于中心性）
        """
        
        # 1. 构建图
        graph = nx.Graph()
        for concept in concepts:
            graph.add_node(concept.id, concept=concept)
        
        # 添加边（基于embedding相似度）
        concept_embeddings = {c.id: c.embedding for c in concepts}
        for i, c1 in enumerate(concepts):
            for c2 in concepts[i+1:]:
                sim = cosine_similarity(
                    [c1.embedding],
                    [c2.embedding]
                )[0][0]
                if sim > 0.7:  # 阈值
                    graph.add_edge(c1.id, c2.id, weight=sim)
        
        # 2. Louvain社区发现
        # 优化模块度，自动确定最佳社区数
        communities = community_louvain.best_partition(
            graph,
            resolution=resolution,
            weight='weight'
        )
        
        # 3. 为每个社区创建domain
        domains = []
        community_groups = {}
        for node_id, comm_id in communities.items():
            if comm_id not in community_groups:
                community_groups[comm_id] = []
            community_groups[comm_id].append(node_id)
        
        for comm_id, node_ids in community_groups.items():
            community_concepts = [
                graph.nodes[nid]['concept'] for nid in node_ids
            ]
            
            # 4. 找社区中心（PageRank）
            subgraph = graph.subgraph(node_ids)
            pagerank = nx.pagerank(subgraph, weight='weight')
            center_concept_id = max(pagerank.keys(), key=lambda k: pagerank[k])
            center_concept = graph.nodes[center_concept_id]['concept']
            
            # 5. 生成摘要（基于中心性）
            # 不是用LLM重写，而是提取中心节点的关键信息
            summary = self._generate_summary(community_concepts, pagerank)
            
            # 6. 创建domain node
            domain = KnowledgeNode(
                type=NodeType.DOMAIN,
                layer=3,
                content=DomainContent(
                    domain_name=center_concept.content.concept_name,
                    domain_summary=summary,
                    domain_coverage=len(community_concepts) / len(concepts)
                ),
                embedding=np.mean(
                    [c.embedding for c in community_concepts],
                    axis=0
                ),
                aggregates_concepts=[c.id for c in community_concepts],
                confidence=np.mean([c.confidence for c in community_concepts])
            )
            
            domains.append(domain)
        
        return domains
    
    def _generate_summary(
        self,
        concepts: List[KnowledgeNode],
        centrality: Dict[UUID, float]
    ) -> str:
        """
        基于中心性生成摘要
        不是LLM重写，而是提取关键信息
        """
        # 按中心性排序
        sorted_concepts = sorted(
            concepts,
            key=lambda c: centrality.get(c.id, 0),
            reverse=True
        )
        
        # 取Top 3中心概念的描述
        key_descriptions = [
            c.content.concept_definition[:200]
            for c in sorted_concepts[:3]
        ]
        
        # 简单拼接（未来可以用简单的文本摘要算法）
        summary = " | ".join(key_descriptions)
        
        return summary
```

### 4.4 L3 → L4: Domain → Index

```python
# backend/src/synthesis/l3_to_l4.py

class L3ToL4Synthesizer:
    """
    L3 domains → L4 index nodes
    构建导航索引
    """
    
    def synthesize(
        self,
        domains: List[KnowledgeNode]  # L3 domain nodes
    ) -> KnowledgeNode:  # L4 index node (通常只有一个顶层索引)
        """
        构建顶层导航索引
        """
        
        # 1. 按重要性排序（基于聚合的concept数量）
        sorted_domains = sorted(
            domains,
            key=lambda d: len(d.aggregates_concepts),
            reverse=True
        )
        
        # 2. 构建索引条目
        index_entries = []
        for domain in sorted_domains:
            entry = IndexEntry(
                node_id=domain.id,
                name=domain.content.domain_name,
                description=domain.content.domain_summary[:100],
                coverage=domain.content.domain_coverage,
                child_count=len(domain.aggregates_concepts)
            )
            index_entries.append(entry)
        
        # 3. 构建导航结构
        # 可以基于相似度做层次聚类，形成树形索引
        index_structure = self._build_hierarchical_index(domains)
        
        # 4. 创建index node
        index = KnowledgeNode(
            type=NodeType.INDEX,
            layer=4,
            content=IndexContent(
                index_name="知识库总索引",
                index_structure=index_structure,
                index_entries=index_entries,
                total_domains=len(domains),
                total_concepts=sum(len(d.aggregates_concepts) for d in domains)
            ),
            embedding=np.mean([d.embedding for d in domains], axis=0),
            indexes_domains=[d.id for d in domains],
            confidence=np.mean([d.confidence for d in domains])
        )
        
        return index
    
    def _build_hierarchical_index(
        self,
        domains: List[KnowledgeNode]
    ) -> Dict:
        """
        构建层次化索引结构
        可以基于domain间的相似度做层次聚类
        """
        # 简化版本：扁平列表
        # 未来可以改进为树形结构
        return {
            "type": "flat",
            "domains": [d.id for d in domains],
            "organization": "by_coverage"  # 按覆盖率排序
        }
```

### 4.5 合成算法配置

```yaml
# synthesis_config.yaml

l1_to_l2:
  algorithm: "hdbscan"
  min_cluster_size: 3
  min_samples: 1
  metric: "euclidean"
  cluster_selection_method: "eom"
  
  centrality: "betweenness"
  
  noise_handling: "isolated_concepts"
  noise_confidence_penalty: 0.3

l2_to_l3:
  algorithm: "louvain"
  resolution: 1.0
  weight_threshold: 0.7
  
  centrality: "pagerank"
  
  summary_generation: "centrality_based_extraction"
  top_k_concepts: 3

l3_to_l4:
  organization: "hierarchical"
  sorting: "by_coverage"
  
  index_depth: 2  # 未来支持多级索引
```

---

## 5. Knowledge Dependency DAG

### 5.1 核心设计

**显式依赖追踪，支持级联重建**

```
依赖关系示例:

[Evidence: E1] ──supports──▶ [Fact: F1]
                                    │
                                    │depends_on
                                    ▼
                              [Concept: C1] ──depends_on──▶ [Fact: F2]
                                    │
                                    │depends_on
                                    ▼
                              [Domain: D1] ──depends_on──▶ [Concept: C2]
                                    │
                                    │depends_on
                                    ▼
                              [Index: I1]

变更传播:

F1 updated
  │
  ├─▶ C1 marked as stale
  │     │
  │     ├─▶ D1 marked as stale
  │     │       │
  │     │       └─▶ I1 marked as stale
  │     │
  │     └─▶ (F2 unchanged, unless C1→F2 logic changes)
  │
  └─▶ Trigger rebuild: C1 → D1 → I1
```

### 5.2 依赖图实现

```python
# backend/src/dependency/dag.py

class KnowledgeDependencyGraph:
    """
    知识依赖DAG
    显式追踪节点间的依赖关系
    支持变更的级联传播
    """
    
    def __init__(self, db: Database):
        self.db = db
        self.graph = nx.DiGraph()  # 有向图
        self._load_from_db()
    
    def build_dependencies(self, nodes: List[KnowledgeNode]):
        """
        自动构建依赖边
        基于节点的source_*字段
        """
        for node in nodes:
            if node.type == NodeType.CONCEPT:
                # Concept依赖Fact
                for fact_id in node.source_facts or []:
                    self.add_edge(
                        source=node.id,
                        target=fact_id,
                        type=EdgeType.DEPENDS_ON,
                        metadata={"level_diff": 1}
                    )
            
            elif node.type == NodeType.DOMAIN:
                # Domain依赖Concept
                for concept_id in node.aggregates_concepts or []:
                    self.add_edge(
                        source=node.id,
                        target=concept_id,
                        type=EdgeType.DEPENDS_ON,
                        metadata={"level_diff": 1}
                    )
            
            elif node.type == NodeType.INDEX:
                # Index依赖Domain
                for domain_id in node.indexes_domains or []:
                    self.add_edge(
                        source=node.id,
                        target=domain_id,
                        type=EdgeType.DEPENDS_ON,
                        metadata={"level_diff": 1}
                    )
            
            # 所有节点依赖Evidence
            for evidence_id in node.evidence_refs:
                self.add_edge(
                    source=node.id,
                    target=evidence_id,
                    type=EdgeType.SUPPORTS,
                    metadata={"is_evidence": True}
                )
    
    def on_node_change(
        self,
        node_id: UUID,
        change_type: str  # 'update' | 'delete' | 'deprecate'
    ) -> RebuildPlan:
        """
        节点变更时的处理
        返回重建计划
        """
        plan = RebuildPlan(trigger=node_id, change_type=change_type)
        
        # 1. 找出所有依赖此节点的下游节点
        affected = self.get_dependents(node_id, recursive=True)
        
        # 2. 按层级分组
        by_layer = {1: [], 2: [], 3: [], 4: []}
        for node in affected:
            by_layer[node.layer].append(node)
        
        # 3. 按层级顺序添加重建任务
        # 从低层到高层：L1 → L2 → L3 → L4
        for layer in [2, 3, 4]:
            for node in by_layer[layer]:
                # 标记为stale
                plan.mark_stale(node)
                
                # 添加到重建队列
                plan.add_rebuild_task(
                    node_id=node.id,
                    layer=layer,
                    dependencies=self.get_dependencies(node.id)
                )
        
        return plan
    
    def get_dependents(
        self,
        node_id: UUID,
        recursive: bool = False
    ) -> List[KnowledgeNode]:
        """
        获取依赖某节点的所有下游节点
        即：哪些节点depend_on这个节点
        """
        if not recursive:
            # 直接依赖
            dependent_ids = [
                n for n in self.graph.successors(node_id)
                if self.graph.edges[node_id, n]['type'] == EdgeType.DEPENDS_ON
            ]
            return [self.get_node(nid) for nid in dependent_ids]
        else:
            # 递归所有下游
            # 使用DFS遍历
            downstream = set()
            stack = [node_id]
            
            while stack:
                current = stack.pop()
                successors = [
                    n for n in self.graph.successors(current)
                    if self.graph.edges[current, n]['type'] == EdgeType.DEPENDS_ON
                ]
                for succ in successors:
                    if succ not in downstream:
                        downstream.add(succ)
                        stack.append(succ)
            
            return [self.get_node(nid) for nid in downstream]
    
    def get_dependencies(
        self,
        node_id: UUID
    ) -> List[KnowledgeNode]:
        """
        获取某节点依赖的所有上游节点
        """
        dependency_ids = [
            n for n in self.graph.predecessors(node_id)
            if self.graph.edges[n, node_id]['type'] == EdgeType.DEPENDS_ON
        ]
        return [self.get_node(nid) for nid in dependency_ids]
    
    def topological_sort_rebuild(self, tasks: List[RebuildTask]) -> List[RebuildTask]:
        """
        拓扑排序重建任务
        确保依赖的节点先重建
        """
        # 提取子图
        task_ids = {t.node_id for t in tasks}
        subgraph = self.graph.subgraph(task_ids)
        
        # 拓扑排序
        sorted_ids = list(nx.topological_sort(subgraph))
        
        # 按排序重排任务
        task_map = {t.node_id: t for t in tasks}
        return [task_map[nid] for nid in sorted_ids if nid in task_map]


class RebuildPlan(BaseModel):
    """重建计划"""
    trigger: UUID  # 触发重建的节点
    change_type: str
    stale_nodes: List[UUID] = []
    rebuild_tasks: List[RebuildTask] = []
    
    def mark_stale(self, node: KnowledgeNode):
        """标记节点为stale"""
        self.stale_nodes.append(node.id)
        node.status = NodeStatus.STALE
        # 保存到DB
    
    def add_rebuild_task(self, node_id: UUID, layer: int, dependencies: List[KnowledgeNode]):
        """添加重建任务"""
        self.rebuild_tasks.append(RebuildTask(
            node_id=node_id,
            layer=layer,
            dependencies=[d.id for d in dependencies],
            priority=layer  # 层数越小优先级越高
        ))
```

### 5.3 级联重建执行

```python
# backend/src/dependency/rebuilder.py

class KnowledgeRebuilder:
    """
    知识级联重建执行器
    """
    
    def __init__(
        self,
        dag: KnowledgeDependencyGraph,
        synthesizers: Dict[int, Synthesizer]
    ):
        self.dag = dag
        self.synthesizers = synthesizers  # layer -> synthesizer
    
    async def execute_rebuild(self, plan: RebuildPlan) -> RebuildResult:
        """
        执行重建计划
        """
        result = RebuildResult()
        
        # 1. 拓扑排序任务
        sorted_tasks = self.dag.topological_sort_rebuild(plan.rebuild_tasks)
        
        # 2. 按层分组执行
        by_layer = {}
        for task in sorted_tasks:
            if task.layer not in by_layer:
                by_layer[task.layer] = []
            by_layer[task.layer].append(task)
        
        # 3. 逐层重建
        for layer in sorted(by_layer.keys()):
            tasks = by_layer[layer]
            
            if layer == 2:
                # L2重建：需要重新聚类受影响的L1
                await self._rebuild_l2(tasks, result)
            elif layer == 3:
                # L3重建：需要重新社区发现
                await self._rebuild_l3(tasks, result)
            elif layer == 4:
                # L4重建：重建索引
                await self._rebuild_l4(tasks, result)
        
        return result
    
    async def _rebuild_l2(
        self,
        tasks: List[RebuildTask],
        result: RebuildResult
    ):
        """
        重建L2 concept nodes
        策略：收集所有依赖的L1，重新聚类
        """
        # 收集所有受影响的L1
        affected_l1_ids = set()
        for task in tasks:
            affected_l1_ids.update(task.dependencies)
        
        # 获取这些L1
        l1_nodes = [self.dag.get_node(nid) for nid in affected_l1_ids]
        
        # 重新合成L2
        synthesizer = self.synthesizers[2]
        new_concepts = synthesizer.synthesize(l1_nodes)
        
        # 替换旧的concept nodes
        for task in tasks:
            old_concept = self.dag.get_node(task.node_id)
            # 找到对应的新concept（基于embedding相似度）
            best_match = self._find_best_match(old_concept, new_concepts)
            if best_match:
                # 更新ID，保留历史
                best_match.id = old_concept.id
                best_match.version = old_concept.version + 1
                # 保存
                result.updated_nodes.append(best_match)
    
    async def _rebuild_l3(
        self,
        tasks: List[RebuildTask],
        result: RebuildResult
    ):
        """重建L3 domain nodes"""
        # 类似L2，但操作对象是concepts
        pass
    
    async def _rebuild_l4(
        self,
        tasks: List[RebuildTask],
        result: RebuildResult
    ):
        """重建L4 index"""
        # 重新生成索引
        pass
```

### 5.4 存储方案

```sql
-- 依赖边已存储在knowledge_edges表中
-- type = 'depends_on' 的就是依赖关系

-- 重建日志表
CREATE TABLE rebuild_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trigger_node UUID REFERENCES knowledge_nodes(id),
    change_type VARCHAR(20),
    affected_nodes UUID[],
    rebuilt_nodes UUID[],
    failed_nodes UUID[],
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    execution_time_ms INTEGER
);

-- 节点版本历史（用于回滚）
CREATE TABLE node_versions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    node_id UUID REFERENCES knowledge_nodes(id),
    version INTEGER,
    content JSONB,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    change_reason VARCHAR(100)
);
```

---

## 6. 实施路线图

### Phase 1: Core Graph Model (Week 1-2)

**目标**: 搭建Node/Edge/Evidence基础

**任务**:
- [ ] 实现Node模型（L1/L2/L3/L4）
- [ ] 实现Edge模型（所有关系类型）
- [ ] 实现Evidence模型
- [ ] PostgreSQL schema
- [ ] 基础CRUD API

**产出**:
- 可存储的知识图谱

---

### Phase 2: Heterogeneous Pipeline (Week 3-4)

**目标**: 双模型协作框架

**任务**:
- [ ] 定义Divergent/Convergent输出格式
- [ ] 实现Rule-Based Merger
- [ ] Divergence Metadata系统
- [ ] 端到端测试（一次L1→L2→L3→L4）

**产出**:
- 可运行的认知管线

---

### Phase 3: Algorithmic Synthesis (Week 5-6)

**目标**: 算法合成管道

**任务**:
- [ ] HDBSCAN聚类实现
- [ ] Louvain社区发现
- [ ] Betweenness/PageRank中心性
- [ ] 关键句提取摘要
- [ ] L1→L2→L3→L4完整pipeline

**产出**:
- 自动生成L2/L3/L4

---

### Phase 4: Dependency DAG (Week 7-8)

**目标**: 依赖追踪与级联重建

**任务**:
- [ ] 依赖图构建
- [ ] 变更传播检测
- [ ] 拓扑排序重建
- [ ] Rebuild Planner
- [ ] 版本历史

**产出**:
- 可级联重建的知识系统

---

### Phase 5: Integration (Week 9-10)

**目标**: 系统集成与优化

**任务**:
- [ ] OpenCode Plugin
- [ ] CLI工具
- [ ] 性能优化
- [ ] 测试覆盖
- [ ] 文档完善

**产出**:
- 可用系统

---

## 7. 关键设计决策总结

| 决策 | v4.0选择 | 理由 |
|------|---------|------|
| **核心结构** | Graph (Node/Edge/Evidence) | 支持复杂关系查询和依赖追踪 |
| **认知模型** | Divergent + Convergent + Merger | 高召回+高精度+确定性 |
| **合成算法** | HDBSCAN + Louvain + Centrality | 算法化，非LLM启发式，可扩展 |
| **依赖管理** | 显式DAG + 级联重建 | 支持大规模增量更新 |
| **分歧处理** | 显式保存分歧元数据 | 分歧即知识，支持争议保留 |
| **存储** | PostgreSQL + pgvector | 单数据库支持图+向量+JSON |

---

## 附录

### A. 完整数据库Schema

（见第2.3节）

### B. 算法库依赖

```txt
# requirements.txt

# 数据库
psycopg2-binary>=2.9.0
pgvector>=0.2.0

# 机器学习
scikit-learn>=1.3.0
hdbscan>=0.8.0
sentence-transformers>=2.2.0

# 图算法
networkx>=3.0
python-louvain>=0.16

# 向量操作
numpy>=1.24.0
scipy>=1.10.0

# API
fastapi>=0.100.0
pydantic>=2.0.0
```

### C. 性能指标目标

| 指标 | 目标 | 说明 |
|------|------|------|
| L1→L2合成 | <5s/100chunks | HDBSCAN聚类 |
| L2→L3合成 | <3s/50concepts | Louvain社区 |
| 依赖查询 | <100ms | 图遍历 |
| 级联重建 | <10s/100nodes | 增量更新 |
| 存储占用 | <1GB/10k nodes | 包含向量 |

---

**文档版本**: v4.0  
**最后更新**: 2026-03-07  
**状态**: 详细设计完成，准备分Session实施  
**实施建议**: 按Phase 1-5顺序，每个Phase 1-2周

*本文档整合了v1-v3的所有设计演进，并基于最新反馈重构为Graph-Based架构。*
