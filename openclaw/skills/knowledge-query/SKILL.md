---
name: knowledge-query
description: 在 AI 知识库中检索技术文章和开源项目，按相关性返回结果
allowed-tools:
  - Read
---

# 知识库检索技能

## 触发条件

当用户想要搜索、查询、查找 AI 技术相关的文章或项目时激活此技能。

## 检索流程

### Step 1: 解析查询意图

从用户输入中提取：
- **关键词**：技术术语、项目名称、公司名称
- **标签过滤**：如 `llm`、`agent`、`rag`、`mcp`
- **时间范围**：今天、本周、本月、指定日期
- **来源偏好**：GitHub、Hacker News、arXiv

### Step 2: 执行检索

1. 使用 Glob 定位目标文件：
   ```
   knowledge/articles/{date-pattern}-*.json
   ```

2. 使用 Grep 在文件内容中搜索关键词：
   ```
   grep -l "关键词" knowledge/articles/*.json
   ```

3. 读取匹配的 JSON 文件，提取结构化字段

### Step 3: 排序与过滤

- 按 `relevance_score` 降序排列
- 过滤掉 score < 0.5 的低质量条目
- 取 Top 5 结果（用户可指定数量）

### Step 4: 格式化输出

每条结果输出格式：

```
📌 **{title}**
   来源：{source} | 日期：{collected_at}
   摘要：{summary}
   标签：{tags}
   链接：{url}
```

多条结果之间用分隔线隔开。

## 无结果处理

如果未找到匹配结果：
1. 告知用户"知识库中暂无相关内容"
2. 建议扩大搜索范围（去掉时间限制、换用同义词）
3. 推荐相关标签供用户浏览

## 示例对话

**用户**：搜索最近关于 MCP 协议的文章
**助手**：找到 3 篇相关文章：

📌 **Anthropic MCP 协议 1.0 正式发布**
   来源：Hacker News | 日期：2026-03-15
   摘要：Anthropic 发布 Model Context Protocol 1.0 稳定版，新增 Streamable HTTP 传输...
   标签：mcp, anthropic, protocol
   链接：https://...

---

📌 **OpenAI 宣布支持 MCP 协议**
   来源：GitHub Trending | 日期：2026-03-14
   摘要：OpenAI 在 Agents SDK 中添加 MCP 客户端支持...
   标签：mcp, openai, agents-sdk
   链接：https://...