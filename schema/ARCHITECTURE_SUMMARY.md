# ChatGPT Bridge - Architecture Evolution Summary

**Date**: 2026-03-07  
**Status**: v4.0 Design Complete  
**Recommendation**: Use v4.0 for implementation

---

## 📚 文档清单

| 文档 | 行数 | 版本 | 状态 | 说明 |
|------|------|------|------|------|
| ARCHITECTURE_DESIGN.md | ~1000 | v1.0 | 历史参考 | 初始委员会治理架构 |
| ARCHITECTURE_DESIGN_v2.md | ~1200 | v2.0 | 历史参考 | 治理重构版（四分法/宪法） |
| ARCHITECTURE_DESIGN_v3.md | ~600 | v3.0 | 核心思想保留 | 异构认知管线 |
| **ARCHITECTURE_DESIGN_v4.md** | **1671** | **v4.0** | **⭐ 推荐使用** | Graph-Based完整架构 |
| IMPLEMENTATION_CHECKLIST.md | ~400 | - | 参考 | Session清单 |

---

## 🎯 版本演进

### v1.0 → v2.0: 治理重构
**问题**: v1.0的政治委员会隐喻过于复杂  
**解决**: 
- 知识四分法（事实/解释/结构/策略）
- 风险分级治理（低/中/高）
- 治理宪法（acceptance criteria）
- 时间语义（valid_from/until）

### v2.0 → v3.0: 认知分工
**问题**: v2.0仍偏重人工流程  
**解决**:
- 异构双模型：发散(Generator) + 收敛(Validator)
- 分歧元数据：保存争议点作为知识
- 规则合并器：LLM不直接落盘
- 两阶段默认：低成本默认路径

### v3.0 → v4.0: Graph-Based
**问题**: v3.0仍是document-based，缺少算法化  
**解决**:
- Graph核心：Node/Edge/Evidence（非文档）
- 算法合成：HDBSCAN + Louvain + Centrality（非LLM）
- 依赖DAG：显式追踪 + 级联重建
- 四层pipeline：L1→L2→L3→L4自动合成

---

## ⭐ v4.0 核心创新

### 1. Graph-Based Knowledge
```
v3: KnowledgeObject (文档思维)
v4: Node + Edge + Evidence (图思维)

优势:
- 复杂关系查询（图遍历）
- 依赖追踪（DAG路径）
- 支持networkx算法库
```

### 2. Algorithmic Synthesis
```
v3: LLM heuristic (L1→L2→L3)
v4: 明确算法
  - L1→L2: HDBSCAN聚类 + Betweenness中心性
  - L2→L3: Louvain社区 + PageRank中心性
  - L3→L4: 层次索引构建

优势:
- 可扩展（不随数据量线性减速）
- 可解释（算法确定）
- 可重复（非随机）
```

### 3. Dependency DAG
```
v3: 无显式依赖
v4: 显式DAG + 级联重建

优势:
- 增量更新（只重建受影响节点）
- 拓扑排序（正确重建顺序）
- 版本历史（支持回滚）
```

### 4. Heterogeneous Cognition
```
继承v3核心思想：
- Divergent Model (高召回)
- Convergent Model (高精度)
- Rule-Based Merger (确定性)
- Divergence Metadata (分歧保存)
```

---

## 🚀 v4.0 实施路线

### Phase 1: Core Graph Model (Week 1-2)
**目标**: 搭建Node/Edge/Evidence基础

**关键任务**:
- [ ] Node模型（L1/L2/L3/L4）
- [ ] Edge模型（所有关系类型）
- [ ] Evidence模型
- [ ] PostgreSQL + pgvector schema
- [ ] 基础CRUD API

**产出**: 可存储的知识图谱

---

### Phase 2: Heterogeneous Pipeline (Week 3-4)
**目标**: 双模型协作框架

**关键任务**:
- [ ] Divergent输出格式
- [ ] Convergent输出格式
- [ ] Rule-Based Merger
- [ ] Divergence Metadata
- [ ] 端到端测试

**产出**: 可运行的认知管线

---

### Phase 3: Algorithmic Synthesis (Week 5-6)
**目标**: 算法合成管道

**关键任务**:
- [ ] HDBSCAN聚类
- [ ] Louvain社区发现
- [ ] Betweenness/PageRank中心性
- [ ] 关键句提取摘要
- [ ] L1→L2→L3→L4完整pipeline

**产出**: 自动生成L2/L3/L4

---

### Phase 4: Dependency DAG (Week 7-8)
**目标**: 依赖追踪与级联重建

**关键任务**:
- [ ] 依赖图构建
- [ ] 变更传播检测
- [ ] 拓扑排序重建
- [ ] Rebuild Planner
- [ ] 版本历史

**产出**: 可级联重建的知识系统

---

### Phase 5: Integration (Week 9-10)
**目标**: 系统集成

**关键任务**:
- [ ] OpenCode Plugin
- [ ] CLI工具
- [ ] 性能优化
- [ ] 测试覆盖
- [ ] 文档完善

**产出**: 可用系统

---

## 📊 技术栈

### 数据库
- **PostgreSQL**: 主存储
- **pgvector**: 向量扩展
- **UUID**: 节点标识
- **JSONB**: 灵活内容

### 机器学习
- **HDBSCAN**: 密度聚类
- **scikit-learn**: 基础ML
- **sentence-transformers**: Embedding

### 图算法
- **networkx**: 图操作
- **python-louvain**: 社区发现

### 核心模型
- **Divergent**: Claude-3.5-Sonnet / Kimi
- **Convergent**: GPT-4 / Opencode
- **Merger**: Python Rule Engine

---

## 🎯 关键设计决策

| 决策 | v4.0选择 | 理由 |
|------|---------|------|
| **存储结构** | Graph (Node/Edge/Evidence) | 支持复杂关系和依赖追踪 |
| **合成方式** | Algorithmic (HDBSCAN/Louvain) | 可扩展、可解释、非LLM |
| **依赖管理** | Explicit DAG + Cascade | 支持增量更新 |
| **认知模型** | Divergent + Convergent + Merger | 高召回+高精度+确定性 |
| **分歧处理** | Metadata preservation | 分歧即知识 |
| **时间语义** | valid_from/until + version | 支持历史追溯 |

---

## 📈 性能目标

| 指标 | 目标 | 说明 |
|------|------|------|
| L1→L2合成 | <5s/100chunks | HDBSCAN聚类 |
| L2→L3合成 | <3s/50concepts | Louvain社区 |
| 依赖查询 | <100ms | 图遍历 |
| 级联重建 | <10s/100nodes | 增量更新 |
| 存储 | <1GB/10k nodes | 含向量 |

---

## 🔗 相关文档

- **完整设计**: `ARCHITECTURE_DESIGN_v4.md` (1671行)
- **实施清单**: `IMPLEMENTATION_CHECKLIST.md`
- **GitHub**: https://github.com/eziothean-git/GPT-md-Skill

---

## ✅ 准备就绪

v4.0架构设计已完成，包含：
- ✅ 完整的Graph-Based数据模型
- ✅ 详细的算法合成pipeline
- ✅ 显式Dependency DAG设计
- ✅ 异构认知管线实现方案
- ✅ 分Phase实施计划（10周）
- ✅ 技术栈和性能目标

**建议**: 从Phase 1开始实施，按周推进。

---

**总结**: 
- v1/v2/v3: 演进探索（保留核心思想）
- **v4.0: 生产就绪（推荐实施）**

*文档创建*: 2026-03-07  
*最后更新*: 2026-03-07
