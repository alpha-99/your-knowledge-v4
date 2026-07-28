---
name: tech-summary
description: 生成技术摘要，当用户要求分析或总结技术内容时触发
allowed-tools:
  - Read
  - Grep
  - Glob
---

# 技术摘要生成技能

## 触发条件
用户请求对技术文章、项目、论文进行分析和摘要。

## 执行步骤
1. 读取原始数据或用户提供的内容
2. 用 LLM 生成 200 字以内的中文技术摘要
3. 提取关键标签（英文）和相关性评分
4. 输出结构化 JSON

## 输出格式
```json
{
  "summary": "中文技术摘要（200字以内）",
  "tags": ["tag1", "tag2"],
  "relevance_score": 0.85,
  "category": "agent",
  "key_insight": "一句话核心洞察"
}
```