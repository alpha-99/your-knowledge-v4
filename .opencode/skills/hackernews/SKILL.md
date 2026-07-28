---
name: hackernews
description: 从 Hacker News (news.ycombinator.com) 采集当日 Top 50 热门文章，过滤 AI/LLM/Agent/ML 相关内容，输出结构化 JSON 数组。使用此技能当用户提到 "hacker news"、"HN"、"HackerNews"、"hackernews"、HN 热门/头条/Top/Top50、采集/抓取/获取 HN/技术新闻/技术资讯、hacker news top stories、hackernews AI/LLM/Agent、HN trending、hacker news 最新/今日 等。也不区分大小写。
allowed-tools:
  - WebFetch
---

# Hacker News 采集技能

## 使用场景

从 Hacker News Firebase API 获取当日 Top 50 热门文章，按标题和正文内容匹配 AI/LLM/Agent/ML 相关关键词，输出过滤后的结构化 JSON 数组。仅输出到 stdout，不写入文件；不去重（由调用方处理）。

## 执行步骤

### 第一步：获取 Top 50 文章 ID

调用 Hacker News Firebase API：

```
GET https://hacker-news.firebaseio.com/v0/topstories.json
```

返回整数 ID 数组，取前 50 个。

### 第二步：并行获取文章详情

对每个 ID 并行请求详情：

```
GET https://hacker-news.firebaseio.com/v0/item/{id}.json
```

每篇返回字段：`title`、`url`、`score`、`text`（若有）、`type`。仅处理 `type` 为 `"story"` 的条目。

### 第三步：关键词过滤

检查每篇文章的 `title`（必查）和 `text`（若有），不区分大小写，匹配以下关键词：

| 关键词 | 匹配变体示例 |
|--------|------------|
| `ai` | AI, Ai, artificial intelligence, A.I. |
| `llm` | LLM, large language model(s) |
| `agent` | Agent, agents, autonomous agent, AI agent |
| `ml` | ML, machine learning |

匹配到任意一个关键词即纳入结果。将命中的关键词记录为 `topics`。

### 第四步：构建输出字段

| 字段 | 来源 | 类型 | 说明 |
|------|------|------|------|
| `name` | `title` | string | 文章标题 |
| `url` | `url` 或 `"https://news.ycombinator.com/item?id={id}"` | string | 文章链接；若无外部链接则使用 HN 讨论页 |
| `topics` | 匹配结果 | string[] | 命中的关键词（如 `["ai", "llm"]`），至少 1 项 |
| `stars` | `score` | integer | HN 投票得分（≥ 0） |
| `description` | `text` | string | 正文摘要；若无则用 `title`；超过 200 字则截断 |

### 第五步：输出 JSON 数组

将过滤后的条目组成 JSON 数组，输出到 stdout。输出必须满足以下 JSON Schema 验证：

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "array",
  "items": {
    "type": "object",
    "required": ["name", "url", "topics", "stars", "description"],
    "properties": {
      "name": { "type": "string", "minLength": 1 },
      "url": { "type": "string", "format": "uri" },
      "topics": {
        "type": "array",
        "items": { "type": "string", "enum": ["ai", "llm", "agent", "ml"] },
        "minItems": 1
      },
      "stars": { "type": "integer", "minimum": 0 },
      "description": { "type": "string" }
    }
  }
}
```

## 容错与边界

- **执行时限**：单次执行 < 10 秒。并行请求尽量在时限内完成；超时则返回已获取到的条目。
- **失败不抛异常**：API 完全不可用时返回空数组 `[]`。
- **不做去重**：不过滤历史已采集的条目，由调用方负责去重。
- **JSON 有效性**：输出必须为合法 JSON 数组，可通过 `JSON.parse()` 解析且通过上述 schema 验证。
- **截断处理**：`description` 截取原文前 200 个字符，末尾加 `…` 标记。
