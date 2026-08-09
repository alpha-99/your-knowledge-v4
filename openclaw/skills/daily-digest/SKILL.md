---
name: daily-digest
description: 生成今日 AI 技术简报，汇总当天采集的 Top 5 知识条目，按相关性排序
allowed-tools:
  - Read
---

# 每日简报技能

## 触发条件

当用户想要查看今日 / 本周 AI 技术汇总时激活。
典型触发词：简报、摘要、今日、daily、digest、briefing

## 生成流程

> **重要 · 只允许 Read**：本技能不能用 Glob / Grep / exec。所有操作从 `Read knowledge/articles/index.json` 开始。

### Step 1: 读索引定位今日数据

用 `Read` 读 `knowledge/articles/index.json`（含每篇文章的 `id` / `title` / `category` / `relevance_score` / `tags` / `collected_at`）。

**在内存里筛**今日的条目（`collected_at` 字段以今日日期开头）；今日无数据则回退到最近 7 天。

> **不要尝试 Glob 或 grep 文件名** —— 索引文件已经聚合了所有元信息，一次 Read 就够了。

### Step 2: 内存过滤 + 排序

1. 过滤 `relevance_score >= 0.6` 的条目
2. 按 `relevance_score` 降序排序
3. 取 Top 5

只对最终要进简报的 Top 5，用 `Read knowledge/articles/{id}.json` 拿 `summary` / `url` 等完整字段（**不要批量读全部**）。

### Step 3: 按 category 分组生成 Markdown 简报

## 与 Publisher 的分工

- **本 Skill**：格式化文本，生成 Markdown 简报
- **distribution/publisher.py**：把简报推送到 Telegram / 飞书 / 文件

Skill 负责"写"，Publisher 负责"发"。