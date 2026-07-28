# AGENTS.md — AI 知识库 V3 (Multi-Agent)

> 本文件是项目的"大脑"——OpenCode 启动时自动加载，指导所有 Agent 的行为。
>
> **V3 在 V2 基础上新增**: LangGraph 工作流、设计模式（Router/Supervisor）、生产加固（成本守卫/安全模块/评估测试）。

## 项目定义

**AI Knowledge Base V3（AI 知识库 — Multi-Agent 版）** 是一个多 Agent 协作的技术情报系统。它在 V2 的自动化流水线基础上，引入 LangGraph 状态图实现工作流编排，加入审核循环（Review Loop）保证输出质量，并通过 Router 和 Supervisor 两种设计模式展示不同的 Agent 协作范式。

### 核心价值
- **LangGraph 工作流**: 用状态图编排 采集→分析→整理→审核→保存 流水线
- **审核循环（Review Loop）**: 核心教学点——条件边实现质量门控，最多 3 次迭代
- **设计模式**: Router（意图路由）和 Supervisor（主管调度）两种经典 Agent 模式
- **生产加固**: 成本守卫、安全防护（防注入/PII检测）、评估测试

### V1 → V2 → V3 演进

| 版本 | 核心能力 | 新增模块 |
|------|---------|---------|
| V1 | 骨架项目，Agent 角色定义 | AGENTS.md, .opencode/, knowledge/ |
| V2 | 自动化流水线，Hooks 事件驱动 | pipeline/, hooks/, .github/ |
| **V3** | **Multi-Agent 工作流，设计模式，生产加固** | **workflows/, patterns/, tests/** |

## 项目结构

```
v3-multi-agent/
├── AGENTS.md                          # 项目记忆文件（本文件）
├── README.md                          # 使用说明
├── .env.example                       # 环境变量模板
├── requirements.txt                   # Python 依赖
│
├── workflows/                         # 【V3 核心】LangGraph 工作流
│   ├── state.py                       #   状态定义 (KBState TypedDict)
│   ├── nodes.py                       #   5 个节点函数
│   ├── graph.py                       #   工作流图 + 条件边 (Review Loop)
│   └── model_client.py                #   LLM 调用客户端
│
├── patterns/                          # 【V3 新增】Agent 设计模式
│   ├── router.py                      #   Router 模式 — 意图路由
│   └── supervisor.py                  #   Supervisor 模式 — 主管调度
│
├── tests/                             # 【V3 新增】生产加固
│   ├── cost_guard.py                  #   成本守卫 — Token 预算控制
│   ├── security.py                    #   安全模块 — 防注入/PII/限流
│   └── eval_test.py                   #   评估测试 — pytest 格式
│
├── pipeline/                          # V2 遗留流水线（向后兼容）
│   └── model_client.py                #   → 复用 workflows/model_client.py
│
├── hooks/                             # V2 遗留 Hooks
│   └── pre_commit.sh                  #   提交前检查
│
├── .opencode/
│   ├── agents/
│   │   ├── collector.md               #   采集 Agent
│   │   ├── analyzer.md                #   分析 Agent
│   │   ├── organizer.md               #   整理 Agent
│   │   ├── reviewer.md                #   审核 Agent（V3 新增）
│   │   └── supervisor.md              #   主管 Agent（V3 新增）
│   └── skills/
│       ├── github-trending/SKILL.md   #   GitHub Trending 采集技能
│       └── tech-summary/SKILL.md      #   技术摘要生成技能
│
├── .github/workflows/
│   └── daily-collect.yml              #   每日自动采集 (GitHub Actions)
│
└── knowledge/
    ├── raw/                           #   原始采集数据
    └── articles/                      #   整理后的知识条目
```

## 编码规范

### 文件命名
- 原始数据：`knowledge/raw/{source}-{YYYY-MM-DD}.json`
- 知识条目：`knowledge/articles/{YYYY-MM-DD}-{NNN}.json`
- 索引文件：`knowledge/articles/index.json`

### JSON 格式
- 2 空格缩进，UTF-8 编码
- 日期格式：ISO 8601
- 每个条目必须包含：`id`, `title`, `source`, `url`, `collected_at`, `summary`, `tags`, `relevance_score`, `category`, `key_insight`

### 语言约定
- 代码、JSON 键名、文件名：英文
- 摘要、分析、注释：中文
- 标签：英文小写，连字符分隔

## 工作流规则

### LangGraph 工作流（核心）

```
[collect] → [analyze] → [organize] → [review] ─→ [save] → END
                            ↑                      │
                            └──── (未通过) ────────┘
                           Review Loop（最多 3 次）
```

**审核循环是本项目的核心教学点**：
1. `review` 节点评估文章质量（4 个维度，各 1-5 分）
2. 总分 >= 3.5 → 通过 → 进入 `save`
3. 总分 < 3.5 → 未通过 → 反馈给 `organize` → 根据反馈修正 → 重新审核
4. 第 3 次迭代强制通过，防止无限循环

### 设计模式

| 模式 | 文件 | 适用场景 |
|------|------|---------|
| Router | `patterns/router.py` | 单一请求 → 一个处理器（1:1） |
| Supervisor | `patterns/supervisor.py` | 复杂任务 → 多个工人 → 汇总（1:N） |

### Agent 协作规则

1. **单向数据流**：Collector → Analyzer → Organizer → Reviewer → Saver
2. **职责隔离**：每个节点只修改自己负责的状态字段
3. **幂等性**：重复运行不产生重复条目
4. **质量门控**：Review Loop 确保输出质量
5. **成本控制**：CostGuard 追踪每次 LLM 调用的 token 用量

### Agent 调用方式

```
# 方式 1: 运行 LangGraph 工作流（推荐）
python -m workflows.graph

# 方式 2: 使用 Router 模式
python patterns/router.py "搜索最近的 AI Agent 框架"

# 方式 3: 使用 Supervisor 模式
python patterns/supervisor.py "采集并分析今天的 AI 领域进展"

# 方式 4: 在 OpenCode 中调用特定 Agent
@collector 采集今天的 GitHub Trending 数据
@reviewer 审核最新一批知识条目
@supervisor 规划并执行一次完整的采集分析任务
```

### 错误处理
- 网络请求失败：记录错误并跳过，不中断流程
- LLM 调用失败：审核自动通过，保存已有结果
- 预算超标：抛出 `BudgetExceededError`，中止工作流
- Prompt 注入：检测并标记，记入审计日志

## 技术栈
- **工作流引擎**：LangGraph (StateGraph + 条件边)
- **LLM**：DeepSeek / Qwen（OpenAI 兼容 API）
- **运行时**：Python 3.11+ / OpenCode
- **数据源**：GitHub API v3
- **测试**：pytest
- **CI/CD**：GitHub Actions