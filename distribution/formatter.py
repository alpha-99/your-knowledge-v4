"""
格式化模块 — V4 发布流水线的一部分，负责将结构化文章数据转换为多种输出格式。

纯函数集合，不涉及网络请求或持久化（这些职责归 publisher.py）。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TELEGRAM_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"


def _score_emoji(score: float) -> str:
    """返回相关性评分的 emoji 指标。

    Args:
        score: 相关性评分，区间 [0, 1]。

    Returns:
        🟢 当 score >= 0.8，🟟 当 0.8 > score >= 0.6，否则 🔴。
    """
    if score >= 0.8:
        return "\U0001F7E2"  # 🟢
    if score >= 0.6:
        return "\U0001F7DF"  # 🟟
    return "\U0001F534"  # 🔴


def _escape_telegram(text: str) -> str:
    """对 Telegram MarkdownV2 需要转义的特殊字符进行反斜线转义。

    Args:
        text: 原始文本。

    Returns:
        转义后的文本。
    """
    result: list[str] = []
    for ch in text:
        if ch in _TELEGRAM_ESCAPE_CHARS:
            result.append("\\")
        result.append(ch)
    return "".join(result)


def _feishu_color(score: float) -> str:
    """根据相关性评分返回飞书卡片 header 的颜色名。

    Args:
        score: 相关性评分。

    Returns:
        'green' 当 score >= 0.8，'yellow' 当 0.8 > score >= 0.6，否则 'red'。
    """
    if score >= 0.8:
        return "green"
    if score >= 0.6:
        return "yellow"
    return "red"


def json_to_markdown(article: dict[str, Any]) -> str:
    """将单篇文章转换为 Markdown 文本。

    包含标题、来源、日期、相关性评分（含 emoji）、标签、摘要和原文链接。

    Args:
        article: 符合 v3 Organizer 产出的单篇文章 dict。

    Returns:
        格式化后的 Markdown 字符串。
    """
    title = article.get("title", "(无标题)")
    source = article.get("source", "unknown")
    collected_at = article.get("collected_at", "")
    date_str = collected_at[:10] if collected_at else "未知日期"
    score = float(article.get("relevance_score", 0))
    summary = article.get("summary", "")
    url = article.get("url", "")
    tags = article.get("tags", []) or []

    emoji = _score_emoji(score)
    tag_str = ", ".join(tags)

    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(f"- **来源**: {source}")
    lines.append(f"- **日期**: {date_str}")
    lines.append(f"- **相关性**: {emoji} {score:.2f}")
    lines.append(f"- **标签**: {tag_str}")
    if summary:
        lines.append("")
        lines.append(f"> {summary}")
    lines.append("")
    if url:
        lines.append(f"**原文链接**: [{url}]({url})")
    lines.append("")
    return "\n".join(lines)


def json_to_telegram(article: dict[str, Any]) -> str:
    """将单篇文章转换为 Telegram MarkdownV2 消息。

    自动转义所有 MarkdownV2 特殊字符，标题以 Markdown 链接形式呈现，
    标签中的空格替换为下划线。

    Args:
        article: 单篇文章 dict。

    Returns:
        Telegram MarkdownV2 格式的字符串。
    """
    title = article.get("title", "(无标题)")
    source = article.get("source", "unknown")
    url = article.get("url", "")
    summary = article.get("summary", "")
    score = float(article.get("relevance_score", 0))
    tags = [t.replace(" ", "_") for t in (article.get("tags", []) or [])]

    emoji = _score_emoji(score)
    tag_str = "  ".join(tags) if tags else ""

    escaped_title = _escape_telegram(title)
    escaped_summary = _escape_telegram(summary) if summary else ""
    escaped_source = _escape_telegram(source)
    escaped_tag_str = _escape_telegram(tag_str) if tag_str else ""

    lines: list[str] = []
    if url:
        escaped_url = _escape_telegram(url)
        lines.append(f"[{escaped_title}]({escaped_url})")
    else:
        lines.append(f"*{escaped_title}*")

    if escaped_summary:
        lines.append(escaped_summary)

    lines.append(f"{emoji} 相关性: {score}")
    lines.append(f"来源: {escaped_source}")
    if escaped_tag_str:
        lines.append(f"标签: {escaped_tag_str}")

    return "\n".join(lines)


def json_to_feishu(article: dict[str, Any]) -> dict[str, Any]:
    """将单篇文章转换为飞书 interactive 卡片消息的 dict。

    header 颜色根据相关性评分自动选择 green / yellow / red。

    Args:
        article: 单篇文章 dict。

    Returns:
        飞书 interactive 卡片格式的 dict，可直接作为飞书 API 的请求体。
    """
    title = article.get("title", "(无标题)")
    source = article.get("source", "unknown")
    url = article.get("url", "")
    summary = article.get("summary", "")
    collected_at = article.get("collected_at", "")
    date_str = collected_at[:10] if collected_at else "未知日期"
    score = float(article.get("relevance_score", 0))
    tags = article.get("tags", []) or []
    key_insight = article.get("key_insight", "")

    color = _feishu_color(score)
    emoji = _score_emoji(score)
    tag_str = ", ".join(tags) if tags else ""

    elements: list[dict[str, Any]] = []

    if summary:
        elements.append({
            "tag": "markdown",
            "content": summary,
        })

    info_lines: list[str] = []
    info_lines.append(f"{emoji} **相关性**: {score:.2f}")
    info_lines.append(f"**来源**: {source}")
    info_lines.append(f"**日期**: {date_str}")
    if tag_str:
        info_lines.append(f"**标签**: {tag_str}")
    if key_insight:
        info_lines.append(f"**关键洞察**: {key_insight}")

    elements.append({
        "tag": "markdown",
        "content": "\n".join(info_lines),
    })

    if url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看原文"},
                "type": "default",
                "url": url,
            }],
        })

    return {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": title,
                },
                "template": color,
            },
            "elements": elements,
        },
    }


def json_to_wechat(article: dict[str, Any], max_line_len: int = 42) -> str:
    """将单篇文章转换为适合微信聊天窗口的纯文本消息。

    使用纯文本加 emoji，不含任何 Markdown 语法。
    标签中的空格替换为下划线；原文链接过长时省略。
    每行长度控制在 ``max_line_len`` 以内以适配手机屏幕。

    Args:
        article: 单篇文章 dict。
        max_line_len: 单行最大字符数（含中文全角字符），默认 42。

    Returns:
        微信聊天风格的纯文本字符串。
    """
    title = article.get("title", "(无标题)")
    source = article.get("source", "unknown")
    collected_at = article.get("collected_at", "")
    date_str = collected_at[:10] if collected_at else "未知日期"
    score = float(article.get("relevance_score", 0))
    summary = article.get("summary", "")
    url = article.get("url", "")
    tags = [t.replace(" ", "_") for t in (article.get("tags", []) or [])]

    emoji = _score_emoji(score)
    tag_str = " ".join(tags) if tags else ""

    lines: list[str] = []
    lines.append(title)
    lines.append(f"来源: {source}  日期: {date_str}")
    lines.append(f"相关性: {emoji} ({score:.2f})")
    lines.append(f"标签: {tag_str}" if tag_str else "标签: (无)")

    if summary:
        lines.append("")
        # 按 max_line_len 折行
        while len(summary) > max_line_len:
            lines.append(summary[:max_line_len])
            summary = summary[max_line_len:]
        if summary:
            lines.append(summary)

    if url and len(url) <= max_line_len:
        lines.append("")
        lines.append(f"原文: {url}")

    return "\n".join(lines)


def generate_daily_digest(
    knowledge_dir: str = "knowledge/articles",
    date: str | None = None,
    top_n: int = 5,
) -> dict[str, Any]:
    """生成当日的知识简报，包含 Markdown、Telegram、飞书三种格式。

    Args:
        knowledge_dir: 知识条目 JSON 文件所在的目录路径。
        date: ISO 格式日期字符串（如 "2026-04-11"），None 表示使用今天（UTC）。
        top_n: 按 relevance_score 降序取前 N 篇。

    Returns:
        dict:
            * 当日有文章时: ``{"markdown": str, "telegram": str, "feishu": list[dict]}``
            * 当日无文章时: ``{"markdown": str, "telegram": str, "feishu": list[dict]}``
              其中各字段均为 "📭 {date} 暂无新增知识条目" 或空列表。
    """
    if date is None:
        date = datetime.now(timezone.utc).date().isoformat()

    dir_path = Path(knowledge_dir)
    pattern = f"{date}-*.json"
    article_files = sorted(dir_path.glob(pattern))

    articles: list[dict[str, Any]] = []
    for fp in article_files:
        try:
            article = json.loads(fp.read_text(encoding="utf-8"))
            articles.append(article)
        except (json.JSONDecodeError, OSError):
            continue

    if not articles:
        empty_msg = f"\U0001F4ED {date} 暂无新增知识条目"
        return {
            "markdown": empty_msg,
            "telegram": empty_msg,
            "feishu": [],
        }

    articles.sort(key=lambda a: float(a.get("relevance_score", 0)), reverse=True)
    top_articles = articles[:top_n]

    md_parts: list[str] = []
    md_parts.append(f"# \U0001F4D6 知识简报 — {date}")
    md_parts.append("")
    for art in top_articles:
        md_parts.append(json_to_markdown(art))
        md_parts.append("---")
        md_parts.append("")

    tg_parts: list[str] = []
    for art in top_articles:
        tg_parts.append(json_to_telegram(art))

    feishu_cards: list[dict[str, Any]] = []
    for art in top_articles:
        feishu_cards.append(json_to_feishu(art))

    return {
        "markdown": "\n".join(md_parts),
        "telegram": "\n\n".join(tg_parts),
        "feishu": feishu_cards,
    }
