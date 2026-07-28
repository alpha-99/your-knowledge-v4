---
name: github-trending
description: 采集 GitHub Trending 数据，当用户要求获取今日热门项目时触发
allowed-tools:
  - Read
  - Write
  - Bash
---

# GitHub Trending 采集技能

## 触发条件
用户请求采集 GitHub Trending 数据或查看今日热门项目。

## 执行步骤
1. 调用 GitHub Search API 获取近期高星 AI/LLM/Agent 仓库
2. 提取关键字段: full_name, description, stars, language, url
3. 写入 `knowledge/raw/github-trending-{YYYY-MM-DD}.json`

## 输出格式
```json
[
  {
    "source": "github",
    "title": "owner/repo-name",
    "url": "https://github.com/owner/repo",
    "description": "项目描述",
    "stars": 1234,
    "language": "Python",
    "collected_at": "2026-03-17T10:00:00Z"
  }
]
```